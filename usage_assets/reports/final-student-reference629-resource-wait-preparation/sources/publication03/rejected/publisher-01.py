#!/usr/bin/env python3
"""Source-only formal-pair publisher draft; no future evidence is manufactured.

All scientific/parent/container gates belong to the reviewed admission module.
The existing publisher supplies pure readers, reference metadata and rendering;
its old single-controller receipt schema is never synthesized or bypassed.
This file has not been imported or invoked. Actual publication/recovery/browser
checks still need future model/contract/evidence and separate operator review.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import ModuleType

ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
LEGACY = ROOT / 'scripts/research/publish_full_scene_matrix.py'
LEGACY_SHA = '35432cb8fb8cc46391dc855f51065aaa3ca017ee9ad57a808ded567be29b19ca'
CHUNK_LIMIT = 25_000_000
GIT_BLOB_LIMIT = 100_000_000
KINDS = ('pure', 'finetune')
MEDIA_SUFFIXES = {'.mp4', '.png', '.jpg', '.jpeg', '.gif', '.webm', '.svg'}


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_path(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            'Parent traversal or symlink path rejected: ' + str(path))
    return path


def fingerprint(path):
    path = safe_path(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode), 'File changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def check(record):
    require(fingerprint(record['path']) == record, 'Initially bound evidence changed: ' + record['path'])


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def reviewed_preparation(expected_sha):
    require(isinstance(expected_sha, str) and re.fullmatch('[0-9a-f]{64}', expected_sha),
            'Explicit reviewed publication-preparation SHA required')
    path = HERE / 'preparation-manifest.json'
    record = fingerprint(path)
    require(record['sha256'] == expected_sha, 'Publication preparation differs from reviewed SHA')
    manifest = read_json(path)
    records, seen = [record], set()
    for item in manifest['files']:
        rel = Path(item['path'])
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in seen,
                'Unsafe/duplicate preparation dependency')
        seen.add(str(rel))
        bound = dict(item, path=str(HERE / rel))
        check(bound)
        records.append(bound)
    require({'publisher.py', 'admission.py'} <= seen, 'Both reviewed publication modules required')
    require(safe_path(__file__) == HERE / 'publisher.py', 'Unexpected executed publisher location')
    return records


def load_admission(records):
    """Only checked bytes are loaded; no site package or live matrix is imported."""
    path = HERE / 'admission.py'
    bound = next(r for r in records if r['path'] == str(path))
    raw = path.read_bytes()
    require(len(raw) == bound['bytes'] and hashlib.sha256(raw).hexdigest() == bound['sha256'],
            'Admission changed before loading')
    module = ModuleType('_reviewed_formal_pair_publication_admission')
    module.__file__, module.__package__ = str(path), ''
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def original_modes(inventory):
    modes = {}
    for row in inventory:
        path = safe_path(row['path'])
        before = path.stat()
        check(row)
        after = path.stat()
        require((before.st_ino, before.st_mode) == (after.st_ino, after.st_mode),
                'Original mode changed while initially binding publication modes')
        modes[row['path']] = stat.S_IMODE(after.st_mode)
    return modes


def recheck(inventory, file_sets, modes=None):
    for row in inventory:
        check(row)
        if modes is not None:
            require(stat.S_IMODE(safe_path(row['path']).stat().st_mode) == modes[row['path']],
                    'Original mode changed since publication admission')
    for directory, expected in file_sets.items():
        base = safe_path(directory)
        actual = set()
        for path in base.rglob('*'):
            require(not path.is_symlink(), 'Symlink introduced into terminal evidence')
            if path.is_dir():
                continue
            require(stat.S_ISREG(path.stat().st_mode), 'Nonregular terminal evidence')
            actual.add(str(path.absolute()))
        require(actual == set(expected), 'Terminal evidence file-set changed: ' + directory)


class Copies:
    """Streaming form of legacy _publish copy/archive closure, with SHA dedup.

    The old closure is not a callable library API. This small derived version
    retains its locked expected SHA, before/after byte checks, 25MB contiguous
    chunks and whole SHA. Original-path aliases are retained in restore-map.
    No external absolute path is treated as a recoverable source substitute.
    """
    def __init__(self, output, inventory, modes):
        self.output = output
        self.expected = {row['path']: row for row in inventory}
        self.modes = dict(modes)
        require(len(self.expected) == len(inventory), 'Duplicate inventory source')
        self.records, self.links, self.storage = [], {}, {}

    def generated(self, relative, data):
        target = self.output / relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                'Unsafe generated path')
        require(len(data) < GIT_BLOB_LIMIT, 'Generated Git blob reaches 100MB')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        target.chmod(0o644)
        return relative

    def json(self, relative, data):
        return self.generated(relative, (json.dumps(data, indent=2, ensure_ascii=False,
                                                   allow_nan=False) + '\n').encode())

    def archive(self, row):
        require(self.expected[row['path']] == row, 'Copy expectation was not initially sealed')
        check(row)
        source = Path(row['path'])
        require(stat.S_IMODE(source.stat().st_mode) == self.modes[row['path']], 'Original mode changed before copy')
        require(source.is_relative_to(ROOT), 'Restore evidence must have a workspace-relative mapping')
        suffix = source.suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9_]{1,16}', suffix):
            suffix = '.bin'
        media = suffix in MEDIA_SUFFIXES
        require(not media or row['bytes'] < GIT_BLOB_LIMIT,
                'Original media reaches 100MB; stop for an explicit external-media contract, never omit/transcode it')
        key = (row['sha256'], row['bytes'], suffix)
        if key in self.storage:
            stored = self.storage[key]
            check(row)
        else:
            relative = 'raw/blobs/' + row['sha256'] + suffix
            if row['bytes'] <= CHUNK_LIMIT or media:
                target = self.output / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, length = hashlib.sha256(), 0
                with source.open('rb') as src, target.open('xb') as dst:
                    for block in iter(lambda: src.read(8 * 1024 * 1024), b''):
                        dst.write(block); digest.update(block); length += len(block)
                require(length == row['bytes'] and digest.hexdigest() == row['sha256'],
                        'Original evidence changed during copy')
                check(row)
                target.chmod(0o644)
                require(fingerprint(target)['sha256'] == row['sha256'], 'Copied bytes differ')
                stored = {'kind': 'file', 'path': relative}
            else:
                chunks, whole, length = [], hashlib.sha256(), 0
                with source.open('rb') as stream:
                    ordinal = 0
                    while block := stream.read(CHUNK_LIMIT):
                        name = relative + f'.parts/{ordinal:06d}.bin'
                        self.generated(name, block)
                        chunks.append({'path': name, 'offset': length, 'bytes': len(block),
                                       'sha256': hashlib.sha256(block).hexdigest()})
                        whole.update(block); length += len(block); ordinal += 1
                require(length == row['bytes'] and whole.hexdigest() == row['sha256'],
                        'Original large evidence changed during chunk copy')
                check(row)
                descriptor = {'schema_version': 1, 'original_relative': relative,
                              'source': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256'],
                              'chunks': chunks, 'reconstruction': 'Concatenate exact chunks by offset; verify bytes and whole SHA256'}
                link = self.json(relative + '.chunks.json', descriptor)
                stored = {'kind': 'chunks', 'path': link, 'restored_relative': relative}
            self.storage[key] = stored
        require(stat.S_IMODE(source.stat().st_mode) == self.modes[row['path']], 'Original mode changed after copy')
        self.links[row['path']] = stored['path']
        self.records.append({'original_path': row['path'], 'workspace_relative': source.relative_to(ROOT).as_posix(),
                             'bytes': row['bytes'], 'sha256': row['sha256'], 'mode': self.modes[row['path']],
                             'mode_octal': oct(self.modes[row['path']]), 'storage': dict(stored)})

    def link(self, source, page=''):
        original = str(Path(source).absolute())
        require(original in self.links, 'Validated original was not retained: ' + original)
        return os.path.relpath(self.links[original], page or '.')


def kind_page(legacy, item, copies):
    kind, plan, matrix = item['kind'], item['plan'], item['matrix']
    legacy.REFERENCE_NAMESPACE = item['namespace']
    cases = []
    for ordinal, (verified, archive) in enumerate(zip(item['cases'], item['archives'], strict=True)):
        row, result = verified['row'], verified['result']
        directory, simulation = Path(verified['directory']), result['simulation']
        prefix = f'{kind}/cases/{row["scenario"]}/config-{row["configuration_index"]:04d}'
        attempts = []
        require(len(row['attempts']) == 1 and archive['sealed'], 'Unsealed/retried execution cannot become complete publication')
        attempt = row['attempts'][0]
        for record in archive['files']:
            require(str(Path(record['path']).absolute()) in copies.links, 'Attempt original missing from locked archive')
        attempts.append({'number': attempt['number'], 'status': attempt['status'], 'returncode': attempt['returncode'],
                         'files': [copies.link(r['path'], kind) for r in archive['files']],
                         'parent_log': copies.link(legacy.host_path(attempt['log']['path']), kind),
                         'original_receipt': attempt, 'sealed': archive['sealed'], 'integrity_scope': archive['integrity_scope']})
        attempts_path = copies.json(prefix + '/attempts.json', attempts)
        svg = copies.generated(prefix + '/world-xy.svg', legacy.trajectory_svg(verified['trajectory']).encode())
        videos = []
        for check in result['video_checks']:
            probe = check['probe']; stream = probe['streams'][0]
            videos.append({'path': copies.link(directory / check['video'], kind),
                           'thumbnail': copies.link(directory / check['thumbnail'], kind),
                           'duration_seconds': float(probe['format']['duration']),
                           'width': stream['width'], 'height': stream['height']})
        info = legacy.reference_info(row)
        recording = result['inference']['lifecycle']['recording_toggle_and_stop_autosave'][0]['file']
        cases.append({'ordinal': ordinal, 'model_kind': kind,
                      **{key: row[key] for key in ('case_id', 'scenario', 'configuration', 'configuration_index', 'mesh_sha256')},
                      'command': None, 'status': 'completed', 'policy_ticks': result['inference']['ticks'],
                      'policy_seconds': simulation['policy_simulation_seconds'], 'threshold_event': simulation['fall_detected'],
                      **{key: simulation[key] for key in ('minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z',
                                                          'path_length_xy_m', 'final_position_xyz_m')},
                      'videos': videos, 'trajectory_svg': os.path.relpath(svg, kind),
                      'trajectory_csv': copies.link(directory / 'trajectory.csv', kind),
                      'result_json': copies.link(directory / 'result.json', kind),
                      'case_evidence': copies.link(directory / 'case-evidence.json', kind),
                      'attempts_json': os.path.relpath(attempts_path, kind), 'attempts': attempts,
                      **{key: info[key] for key in ('reference_commands', 'reference_frames', 'reference_fps', 'reference_motion', 'command_runs')},
                      'reference_policy_seconds': info['duration'], 'reference_motion_sha256': info['reference_motion']['sha256'],
                      'reference_motion_path': info['reference_motion']['path'], 'policy_recording': copies.link(directory / recording, kind),
                      'quality_verified': False, 'obstacle_course_completion_verified': False})
    require(len(cases) == 629, 'Kind gallery must include all629 actual configurations')
    scenarios = []
    for scenario, count in legacy.SCENARIO_COUNTS.items():
        rows = [case for case in cases if case['scenario'] == scenario]
        flags = sum(case['threshold_event'] for case in rows)
        require(len(rows) == count, 'Named scenario configuration coverage missing')
        scenarios.append({'scenario': scenario, 'planned_configurations': count, 'configurations': len(rows),
                          'threshold_events': flags, 'no_threshold_events': len(rows) - flags,
                          'historical_noncompleted_attempts': 0, 'reference_frames': sum(r['reference_frames'] for r in rows),
                          'reference_policy_seconds': sum(r['reference_frames'] for r in rows) / 50})
    base = Path(item['base'])
    summary = {'schema_version': 1, 'status': 'completed_publication', 'model_kind': kind, 'preview': False,
               'legacy_normal_exit_unverified': False, 'plan_sha256': plan['plan_sha256'],
               'matrix_sha256': item['native_receipt']['native_matrix']['sha256'], 'image_id': plan['image_id'],
               'model_sha256': plan['model_sha256'], 'configurations': 629, 'planned_configurations': 629,
               'policy_ticks': sum(r['policy_ticks'] for r in cases), 'policy_seconds': sum(r['policy_seconds'] for r in cases),
               'reference_commands': True, 'reference_fps': 50, 'reference_frames': sum(r['reference_frames'] for r in cases),
               'reference_policy_seconds': sum(r['reference_frames'] for r in cases) / 50,
               'threshold_events': sum(r['threshold_event'] for r in cases), 'no_threshold_events': sum(not r['threshold_event'] for r in cases),
               'scenarios': scenarios, 'configuration_coverage_complete': True, 'quality_verified': False,
               'obstacle_course_completion_verified': False, 'full_video_decode_verified': True,
               'native_parent_exit_verified': True, 'host_writer_coverage_verified': True, 'host_mappings_verified': 1258,
               'native_parent_scope': 'One actual outer adapter.execute parent shared by both inline run_kind calls',
               'cpu_execution_exit_verified': True, 'cpu_parent_exit_verified': False,
               'cpu_execution_scope': 'Original cpu_job create/start/docker.wait0 and same own CID stopped; no separate CPU-parent receipt is manufactured',
               'raw_links': {name: copies.link(base / 'outputs/reference629' / name, kind) for name in ('plan.json', 'matrix.json')},
               'scope': 'Actual formal ' + kind + ' model, complete source 50Hz labels through native physics; parent/worker/CPU execution and hashes verified. Skills/course/convergence/hardware unverified.'}
    copies.json(kind + '/summary.json', summary)
    copies.json(kind + '/cases.json', cases)
    copies.json(kind + '/scenarios.json', scenarios)
    fields = ['ordinal', 'model_kind', 'case_id', 'scenario', 'configuration_index', 'configuration', 'mesh_sha256',
              'policy_ticks', 'policy_seconds', 'reference_frames', 'reference_fps', 'reference_policy_seconds',
              'reference_motion_sha256', 'reference_motion_path', 'command_runs', 'threshold_event',
              'minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m',
              'result_json', 'trajectory_csv', 'policy_recording']
    text = io.StringIO(newline=''); writer = csv.DictWriter(text, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows([{**r, 'command_runs': json.dumps(r['command_runs'], separators=(',', ':'))} for r in cases])
    copies.generated(kind + '/cases.csv', text.getvalue().encode())
    page = legacy.make_page(summary, cases)
    title = 'G1 · all 629 configuration rollouts'
    phrase = '使用发布学生ONNX、原生DDS/深度SHM、MuJoCo/PD，'
    require(page.count(title) == 2 and page.count(phrase) == 1, 'Pinned legacy renderer text contract changed')
    page = page.replace(title, html.escape('G1 · 正式自训学生 ' + kind + ' · 全629配置'))
    identification = '使用正式自训学生 ' + kind + '（' + ', '.join(name + ' SHA ' + sha for name, sha in sorted(plan['model_sha256'].items())) + '）、原生DDS/深度SHM、MuJoCo/PD，'
    page = page.replace(phrase, html.escape(identification))
    page = page.replace('原生SDK策略录制NPZ（root XYZ为占位零，物理位置见CSV）',
                        '原生SDK策略录制NPZ或分块描述（root XYZ为占位零，物理位置见CSV）')
    copies.generated(kind + '/playback.html', page.encode())
    return summary


def publish(args, preparation):
    gate = load_admission(preparation)
    require(args.root_authorized_publish, 'Explicit internal root publication gate required')
    context = gate.admit(contract_path=args.contract, contract_sha256=args.contract_sha256,
                         parent_start=args.parent_start, parent_start_sha256=args.parent_start_sha256,
                         parent_exit=args.parent_exit, parent_exit_sha256=args.parent_exit_sha256,
                         publisher_path=LEGACY)
    require(context['status'] == 'ready_for_separately_reviewed_publication'
            and context['counts'] == {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}
            and [item['kind'] for item in context['kinds']] == list(KINDS), 'Actual formal pair admission incomplete')
    inventory = {row['path']: row for row in context['inventory']}
    for row in preparation:
        require(row['path'] not in inventory or inventory[row['path']] == row, 'Publication control conflicts with admitted bytes')
        inventory[row['path']] = row
    inventory = [dict(row) for row in inventory.values()]
    file_sets = {path: list(names) for path, names in context['expected_file_sets'].items()}
    freeze_record = context['contract']['freeze_manifest']
    check(freeze_record)
    freeze = read_json(freeze_record['path'])
    base = Path(context['contract']['base'])
    for group in ('source', 'overlay', 'inputs', 'control'):
        file_sets[str(base / group)] = [str(base / row['relative']) for row in freeze['files']
                                      if row['relative'].startswith(group + '/')]
    check(freeze_record)
    modes = original_modes(inventory)
    recheck(inventory, file_sets, modes)
    output = safe_path(args.output)
    require(output.is_relative_to(ROOT / 'usage_assets/reports') or output.is_relative_to(ROOT / 'outputs/research'),
            'Use an explicit new report directory inside this workspace')
    require(not output.exists(), 'New publication directory only; never overwrite partial/history')
    require(not any(Path(row['path']).is_relative_to(output) or output.is_relative_to(Path(row['path']).parent)
                    for row in inventory), 'Publication may not contain or change original evidence')
    for row in inventory:
        require(Path(row['path']).suffix.lower() not in MEDIA_SUFFIXES or row['bytes'] < GIT_BLOB_LIMIT,
                'Original media reaches100MB; no partial media publication is allowed')
    # Only the new result directory is owned; existing ancestors are not edited.
    require(output.parent.is_dir(), 'Create/review the report parent separately; publication owns only its new output')
    output.mkdir(exist_ok=False)
    output.chmod(0o755)
    copies = Copies(output, inventory, modes)
    try:
        copies.json('publication-incomplete.json', {'status': 'copying_admitted_originals_not_yet_published',
                                                   'complete_manifest_created': False})
        for row in inventory:
            copies.archive(row)
        library_evidence = gate.Evidence()
        with gate.reviewed_modules(library_evidence, LEGACY) as (_, _, legacy):
            for record in library_evidence.files.values():
                require(inventory and record in inventory, 'Rendering imported an unsealed source')
            summaries = [kind_page(legacy, item, copies) for item in context['kinds']]
            library_evidence.recheck()
        total = {'schema_version': 1, 'status': 'completed_formal_pair_publication', 'policies': 2,
                 **context['counts'], 'kind_order': list(KINDS), 'image_id': context['contract']['image_id'],
                 'gpu_uuid': context['contract']['gpu_uuid'], 'contract_identity': context['contract']['contract_identity'],
                 'contract_sha256': args.contract_sha256, 'actual_outer_parent_start_sha256': args.parent_start_sha256,
                 'actual_outer_parent_exit_sha256': args.parent_exit_sha256,
                 'kinds': [dict({key: value for key, value in s.items() if key != 'raw_links'},
                                summary_json=s['model_kind'] + '/summary.json',
                                playback=s['model_kind'] + '/playback.html') for s in summaries],
                 'reference_frames': sum(s['reference_frames'] for s in summaries),
                 'reference_policy_seconds': sum(s['reference_frames'] for s in summaries) / 50,
                 'policy_seconds': sum(s['policy_seconds'] for s in summaries),
                 'threshold_events': sum(s['threshold_events'] for s in summaries),
                 'no_threshold_events': sum(s['no_threshold_events'] for s in summaries),
                 'quality_verified': False, 'obstacle_course_completion_verified': False,
                 'published_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                 'scope': 'Two actual formal pairs, each full629 native reference execution and CPU full-decode acceptance; not1258 independent geometries or successful skills.'}
        copies.json('summary.json', total)
        copies.json('bindings.json', {'contract': copies.link(args.contract), 'outer_parent_start': copies.link(args.parent_start),
                                     'outer_parent_exit': copies.link(args.parent_exit), 'pair_receipt': copies.link(Path(context['contract']['base']) / 'runs/launch-receipt.json'),
                                     'kinds': [{'kind': item['kind'], 'native': copies.link(Path(item['base']) / 'host/launch-receipt.json'),
                                                'cpu_launch': copies.link(Path(item['base']) / 'cpu-final/launch.json'),
                                                'cpu_validation': copies.link(Path(item['base']) / 'cpu-final/validation.json'),
                                                'models': item['plan']['model_sha256']} for item in context['kinds']]})
        copies.json('restore-map.json', {'schema_version': 1, 'original_workspace': str(ROOT), 'files': copies.records,
                                        'external_file_dependencies': [], 'all_inventory_files_retained': True,
                                        'policy': 'Restore into a fresh workspace; for chunks concatenate in offset order and verify each SHA plus whole bytes/SHA, then map workspace_relative and chmod each original mode. Byte aliases may share storage even when their original modes differ. Do not restore uid/gid. Never overwrite active/partial/history. Containers/image layers and physical hardware are not file evidence and are not included.'})
        index = ('# 正式两学生：全629逐帧参考指令物理结果\n\n'
                 '本包使用实际正式自训pure/finetune模型，各629配置，共1258例、2516个正常worker/宿主writer出生映射、1258段完整视频解码。每模型覆盖全部17命名场景，按各原NPZ完整15维50Hz标签运行。629是配置数量，不代表629独立几何或技能成功；高度/倾斜阈值事件完整保留。quality_verified=false，课程、收敛、PT↔ONNX parity与实机成功未由此证明。\n\n'
                 '- [pure完整图库](pure/playback.html) · [逐例JSON](pure/cases.json) · [CSV](pure/cases.csv)\n'
                 '- [finetune完整图库](finetune/playback.html) · [逐例JSON](finetune/cases.json) · [CSV](finetune/cases.csv)\n'
                 '- [双模型汇总](summary.json) · [真实合同/父wait/CPU收据绑定](bindings.json)\n'
                 '- [原路径恢复映射](restore-map.json) · [完整SHA清单](evidence-manifest.json)\n\n'
                 '原MP4/PNG/NPZ/日志/JSON/CSV与所有已验输入逐字节保存；相同字节按SHA共享存储，每个原路径均保留恢复映射及原mode。大raw按不超过25,000,000字节连续分块，可用原publisher的restore-chunks恢复blob后按restore-map映射到全新workspace，逐项chmod原mode；不恢复uid/gid。媒体保持原片，不重新编码；世界XY仅由实际CSV生成。文件证据自包含，Docker镜像层/驱动与硬件仍按项目配置恢复。图库可file://离线打开或使用标准库HTTP。所有原阈值与firstattempt原件均保留；不存在失败后自动重试择优。本包自身不是浏览器验收报告或Git推送证明，另由Root真实操作封存。\n')
        copies.generated('index.md', index.encode())
        recheck(inventory, file_sets, modes)
        (output / 'publication-incomplete.json').unlink()
        files = []
        for path in sorted(output.rglob('*')):
            require(not path.is_symlink(), 'Symlink in produced publication')
            if path.is_dir():
                path.chmod(0o755)
            if path.is_file():
                record = fingerprint(path)
                require(record['bytes'] < GIT_BLOB_LIMIT, 'Actual published Git blob reaches100MB')
                files.append(dict(record, path=path.relative_to(output).as_posix()))
        # Last write is the only complete manifest. Earlier failures leave raw partials.
        manifest_data = {'schema_version': 1, 'status': 'complete_formal_pair_publication',
                                              'counts': context['counts'], 'files': files,
                                              'bytes_excluding_manifest': sum(r['bytes'] for r in files),
                                              'original_inventory': inventory, 'all_original_bytes_retained': True,
                                              'legacy_publisher_sha256': LEGACY_SHA,
                                              'publication_preparation_sha256': args.preparation_sha256,
                                              'quality_verified': False, 'obstacle_course_completion_verified': False}
        raw_manifest = (json.dumps(manifest_data, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
        copies.generated('evidence-manifest.pending.json', raw_manifest)
        recheck(inventory, file_sets, modes)
        # Atomic completion marker is the final IO. No read failure after sealing
        # can turn an otherwise completed file set into a retained success marker.
        (output / 'evidence-manifest.pending.json').replace(output / 'evidence-manifest.json')
        return {'status': total['status'], 'output': str(output),
                'manifest': {'path': str(output / 'evidence-manifest.json'), 'bytes': len(raw_manifest),
                             'sha256': hashlib.sha256(raw_manifest).hexdigest()},
                'counts': context['counts'], 'quality_verified': False, 'obstacle_course_completion_verified': False}
    except BaseException as error:
        # Generated evidence is ours; originals and prior outputs are never edited.
        manifest = output / 'evidence-manifest.json'
        try:
            if manifest.exists():
                manifest.unlink()
            copies.json('publication-failed.json', {'status': 'failed_partial_not_published', 'error': type(error).__name__ + ': ' + str(error),
                                               'complete_manifest_created': False, 'automatic_retry': False,
                                               'scope': 'Original source evidence remains untouched; this new directory is retained as an incomplete first publication attempt.'})
        except BaseException as diagnostic_error:
            print('Partial publication diagnostic IO failed; preserve directory and original exception: ' + str(diagnostic_error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'publish'))
    parser.add_argument('--preparation-sha256', required=True)
    for name in ('contract', 'parent-start', 'parent-exit', 'output'):
        parser.add_argument('--' + name, type=Path)
    for name in ('contract-sha256', 'parent-start-sha256', 'parent-exit-sha256'):
        parser.add_argument('--' + name)
    parser.add_argument('--root-authorized-publish', action='store_true')
    args = parser.parse_args()
    preparation = reviewed_preparation(args.preparation_sha256)
    for name in ('contract_sha256', 'parent_start_sha256', 'parent_exit_sha256'):
        value = getattr(args, name)
        if value is not None:
            require(re.fullmatch('[0-9a-f]{64}', value), 'Invalid explicit actual evidence SHA: ' + name)
    required = ('contract', 'contract_sha256', 'parent_start', 'parent_start_sha256', 'parent_exit', 'parent_exit_sha256')
    missing = [name for name in required if getattr(args, name) is None]
    if args.action == 'status' and missing:
        answer = {'status': 'waiting', 'missing_explicit_actual_prerequisites': missing, 'publication_created': False,
                  'native_started': False, 'gpu_started': False, 'scope': 'Source preparation and absent future inputs only; no execution/publication acceptance.'}
    elif args.action == 'status':
        missing_paths = [str(getattr(args, name)) for name in ('contract', 'parent_start', 'parent_exit') if not Path(getattr(args, name)).exists()]
        if missing_paths:
            answer = {'status': 'waiting', 'missing_actual_paths': missing_paths, 'publication_created': False, 'native_started': False, 'gpu_started': False}
        else:
            context = load_admission(preparation).admit(contract_path=args.contract, contract_sha256=args.contract_sha256,
                parent_start=args.parent_start, parent_start_sha256=args.parent_start_sha256,
                parent_exit=args.parent_exit, parent_exit_sha256=args.parent_exit_sha256, publisher_path=LEGACY)
            answer = {'status': context['status'], 'counts': context['counts'], 'publication_created': False,
                      'native_started': False, 'gpu_started': False, 'quality_verified': False}
    else:
        require(not missing and args.output is not None, 'Actual reviewed contract/outer parent and explicit fresh output required')
        answer = publish(args, preparation)
    print(json.dumps(answer, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
