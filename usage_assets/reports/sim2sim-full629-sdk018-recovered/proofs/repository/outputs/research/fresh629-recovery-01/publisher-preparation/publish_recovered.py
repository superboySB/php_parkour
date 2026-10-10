#!/usr/bin/env python3
"""Publish the recovered629 proof, preserving original143 and separate four attempts.

Host stdlib only. This adapter does not start containers, decode media, or run
native code. Root must explicitly execute it after reviewing its frozen contract.
The pinned shared gate does read-only Docker GETs; its entire result is retained.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
REC = ROOT / 'outputs/research/fresh629-recovery-01'
FOUR = REC / 'missing-four-run-01'
PREP = REC / 'publisher-preparation'
DESTINATION = ROOT / 'usage_assets/reports/sim2sim-full629-sdk018-recovered'
CHUNK_BYTES = 25_000_000
PLAN_ID = '1e3483f7b35dd7592d9e5e0b02c13143a44e4f17a5cd0ba24def25c0229a6e6f'
MATRIX_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
STRICT_SHA = '5b0d967f96f0d62ca474dcf4746e53f0a4aecd459790d0591aa31d2e89679a7a'
GATE_SHA = 'dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525'


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and path.is_relative_to(ROOT)
            and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe source/output: ' + str(path))
    return path


def fp(path):
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ino, after.st_ctime_ns), 'File changed during hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    return json.loads(safe(path).read_text(), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def load_module(path, digest, name):
    require(fp(path)['sha256'] == digest, 'Frozen helper source differs: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(fp(path)['sha256'] == digest, 'Helper changed during import')
    return module


def translate(value, output):
    path = Path(value)
    for prefix, target in (('/workspace/php_parkour', OLD / 'source'),
                           ('/data', OLD / 'inputs'), ('/outputs', output)):
        if path.is_relative_to(prefix):
            return safe(target / path.relative_to(prefix))
    return safe(path if path.is_absolute() else ROOT / path)


def load_publisher(path, native):
    # Reuse the proven isolated import binding from publish_fresh629.py: the
    # unchanged strict publisher imports the already SHA-verified frozen module.
    names = ('scripts', 'scripts.research', 'scripts.research.sim2sim_scene_matrix')
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in names}
    old_path = list(sys.path)
    package = ModuleType('scripts'); package.__path__ = [str(OLD / 'source/scripts')]
    research = ModuleType('scripts.research'); research.__path__ = [str(OLD / 'source/scripts/research')]
    package.research = research; research.sim2sim_scene_matrix = native
    try:
        sys.modules.update({'scripts': package, 'scripts.research': research, names[2]: native})
        return load_module(path, STRICT_SHA, '_recovered629_strict_publisher')
    finally:
        sys.path[:] = old_path
        for name, value in previous.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class Copies:
    def __init__(self, staging):
        self.staging = staging
        self.records = {}
        self.copies = {}

    def copy(self, path, relative=None, expected=None):
        path = safe(path)
        record = fp(path)
        if expected is not None:
            require(record['sha256'] == expected['sha256']
                    and record['bytes'] == expected.get('bytes', expected.get('size', record['bytes'])),
                    'Verified original changed before copy: ' + str(path))
        if str(path) in self.copies:
            require(self.records[str(path)] == record, 'Previously copied original changed')
            return self.copies[str(path)]
        relative = relative or ('proofs/repository/' + path.relative_to(ROOT).as_posix())
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe publication name')
        target = self.staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        require(not target.exists(), 'Publication collision: ' + relative)
        # JSONL observation streams are kept as contiguous chunks even when
        # small. Oversize proof files use the same exact concatenation scheme.
        chunked = path.name == 'snapshots.jsonl' or record['bytes'] > CHUNK_BYTES
        if chunked:
            parts, whole = [], hashlib.sha256()
            with path.open('rb') as stream:
                offset = 0
                for ordinal, block in enumerate(iter(lambda: stream.read(CHUNK_BYTES), b'')):
                    part_rel = relative + f'.chunks/part-{ordinal:04d}.bin'
                    part = self.staging / part_rel
                    part.parent.mkdir(parents=True, exist_ok=True)
                    with part.open('xb') as destination:
                        destination.write(block)
                    part.chmod(0o644)
                    whole.update(block)
                    parts.append({'path': part_rel, 'offset': offset, 'bytes': len(block),
                                  'sha256': hashlib.sha256(block).hexdigest()})
                    offset += len(block)
            require(offset == record['bytes'] and whole.hexdigest() == record['sha256'], 'Chunk whole SHA differs')
            index_rel = relative + '.chunks.json'
            write(self.staging / index_rel, {'schema_version': 1, 'whole_original': record,
                  'chunk_limit_bytes': CHUNK_BYTES, 'method': 'Concatenate parts in listed order; no compression or newline edits',
                  'parts': parts})
            copied = {'kind': 'contiguous_chunks', 'index': index_rel, 'parts': parts, 'whole_original': record}
        else:
            shutil.copyfile(path, target)
            target.chmod(0o644)
            require(fp(target)['sha256'] == record['sha256'], 'Copied byte SHA differs')
            copied = {'kind': 'byte_copy', 'path': relative, 'whole_original': record}
        require(fp(path) == record, 'Source changed during publication copy')
        self.records[str(path)], self.copies[str(path)] = record, copied
        return copied

    def tree(self, root):
        root = safe(root)
        if not root.exists():
            return
        for path in sorted(root.rglob('*')):
            safe(path)
            if '__pycache__' in path.parts:
                continue
            require(path.is_dir() or path.is_file(), 'Special proof file')
            if path.is_file():
                self.copy(path)

    def finish(self):
        for path, record in self.records.items():
            require(fp(path) == record, 'Raw proof changed before sealing: ' + path)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    path.chmod(0o644)


def verified_cases(publisher, frozen_matrix, plan, matrix, output, selected=None):
    # Only namespace plumbing is supplied. The original native schema3 receipt
    # validator and strict case/history validators execute unchanged.
    publisher.host_path = lambda value: translate(value, output)
    publisher.validate_worker_receipts = frozen_matrix.validate_worker_receipts
    publisher.validate_plan(plan, matrix, plan['plan_sha256'], MATRIX_SHA, False)
    for record in [plan['source_matrix_record'], *plan['dependencies'], *plan['models'],
                   *(record for case in plan['selections'] for record in case['source_files'])]:
        publisher.check_record(record)
    result = []
    for row in matrix['selections']:
        if selected is not None and row['case_id'] not in selected:
            continue
        item = publisher.validate_case(plan, row)
        require(len(row['attempts']) == 1 and row['attempts'][0]['number'] == 1,
                'Each original or independent supplement must be once-only')
        directories = [publisher.host_path(attempt['output']).resolve() for attempt in row['attempts']]
        item['attempt_archives'] = [publisher.validate_attempt_archive(plan, row, attempt, directories)
                                    for attempt in row['attempts']]
        result.append(item)
    return result


def copy_case(copies, publisher, item, cohort, ordinal):
    row, native = item['row'], item['result']
    sim = native['simulation']
    prefix = f'raw/{cohort}/{row["scenario"]}/config-{row["configuration_index"]:04d}'
    attempt = row['attempts'][0]
    directory = item['directory']
    archive = item['attempt_archives'][0]
    copied_files = []
    for record in archive['files']:
        path = Path(record['path'])
        mapped = copies.copy(path, prefix + '/attempt-0001/' + path.relative_to(directory).as_posix(), record)
        require(mapped['kind'] == 'byte_copy', 'Native per-case artifact too large for direct gallery; retain partial and review')
        copied_files.append(mapped['path'])
    parent_log = copies.copy(translate(attempt['log']['path'], OLD / 'outputs' if cohort == 'original' else FOUR / 'outputs'),
                             prefix + '/attempt-0001/parent-execution.log', attempt['log'])
    current = prefix + '/attempt-0001'
    svg = prefix + '/world-xy.svg'
    (copies.staging / svg).write_text(publisher.trajectory_svg(item['trajectory']))
    details = {'cohort': cohort, 'number': 1, 'status': attempt['status'], 'returncode': attempt['returncode'],
               'files': copied_files, 'parent_log': parent_log['path'], 'original_receipt': attempt,
               'sealed': archive['sealed'], 'integrity_scope': archive['integrity_scope']}
    videos = []
    for check in native['video_checks']:
        stream = check['probe']['streams'][0]
        videos.append({'path': current + '/' + check['video'], 'thumbnail': current + '/' + check['thumbnail'],
                       'duration_seconds': float(check['probe']['format']['duration']),
                       'width': stream['width'], 'height': stream['height']})
    return {'ordinal': ordinal, **{key: row[key] for key in ('case_id', 'scenario', 'configuration', 'configuration_index', 'command', 'mesh_sha256')},
            'cohort': cohort, 'status': 'completed', 'policy_ticks': native['inference']['ticks'],
            'policy_seconds': sim['policy_simulation_seconds'], 'threshold_event': sim['fall_detected'],
            **{key: sim[key] for key in ('minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m', 'final_position_xyz_m')},
            'videos': videos, 'trajectory_svg': svg, 'trajectory_csv': current + '/trajectory.csv',
            'result_json': current + '/result.json', 'case_evidence': current + '/case-evidence.json',
            'attempts_json': prefix + '/attempts.json', 'attempts': [details],
            'quality_verified': False, 'obstacle_course_completion_verified': False}


def publish(contract, control_records):
    helpers = contract['frozen_helpers']
    expected_helpers = {
        'gate': {'path': str(REC / 'controller-adapter/previous_recovered_02.py'), 'sha256': GATE_SHA},
        'strict_publisher': {'path': str(ROOT / 'outputs/research/fresh629-publication-preparation/publisher_source.py'), 'sha256': STRICT_SHA},
        'matrix_validator': {'path': str(OLD / 'source/scripts/research/sim2sim_scene_matrix.py'), 'sha256': MATRIX_SHA},
    }
    require(helpers == expected_helpers, 'Exact reviewed shared gate/strict publisher/frozen validator required')
    gate = load_module(helpers['gate']['path'], helpers['gate']['sha256'], '_recovered629_public_gate')
    admission = gate.previous_recovered()
    if admission.get('ready') is not True:
        return {'status': 'waiting', 'published': False, 'reason': admission.get('reason'), 'quality_verified': False}
    require(admission['status'] == 'recovered_previous_ready'
            and admission['original_session54334_exit_code'] == 143
            and admission['original_root_normal_exit_verified'] is False
            and admission['original_unique_host_writer_mappings'] == 1250
            and admission['original_missing_historical_writer_mappings'] == 8
            and admission['supplement_host_writer_mappings'] == 8
            and admission['supplement_full_video_decodes'] == 4, 'Recovered gate schema differs')
    parent_exit = read(REC / 'missing-four-preparation/process-exit.json')
    require(parent_exit['actual_wait_returncode'] == 0 and parent_exit['original_session54334_exit_code'] == 143,
            'Independent four-case outer actual wait0 is required')
    frozen_matrix = load_module(helpers['matrix_validator']['path'], MATRIX_SHA, '_recovered629_frozen_matrix')
    require(frozen_matrix.ROOT == OLD / 'source', 'Frozen receipt validator ROOT differs')
    publisher = load_publisher(helpers['strict_publisher']['path'], frozen_matrix)
    plan = read(OLD / 'inputs/native-plan.json')
    require(plan['plan_sha256'] == PLAN_ID, 'Original frozen plan changed')
    original_matrix = read(OLD / 'outputs/all-configs/matrix.json')
    supplement_plan = read(FOUR / 'outputs/missing-four-plan.json')
    supplement_matrix = read(FOUR / 'outputs/missing-four/matrix.json')
    original = verified_cases(publisher, frozen_matrix, plan, original_matrix, OLD / 'outputs')
    supplement = verified_cases(publisher, frozen_matrix, supplement_plan, supplement_matrix,
                                FOUR / 'outputs', admission['separate_supplement_case_ids'])
    require(len(original) == 629 and len(supplement) == 4, 'Exact629+4 original attempts required')
    safe(DESTINATION)
    require(not DESTINATION.exists(), 'Never overwrite an existing publication')
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=DESTINATION.name + '.partial-', dir=DESTINATION.parent))
    staging.chmod(0o755)
    copies = Copies(staging)
    try:
        # Preserve raw matrices/plans without constructing a fabricated merged
        # matrix, success driver receipt, or replacement worker birth list.
        copies.copy(OLD / 'inputs/native-plan.json', 'plan.json')
        copies.copy(OLD / 'outputs/all-configs/matrix.json', 'matrix.json')
        write(staging / 'gate-admission.json', admission)
        write(staging / 'publication-control-inputs.json', control_records)
        cases = [copy_case(copies, publisher, item, 'original', index) for index, item in enumerate(original)]
        supplements = [copy_case(copies, publisher, item, 'separate-missing-writer-supplement', index)
                       for index, item in enumerate(supplement)]
        supplement_by_id = {row['case_id']: row for row in supplements}
        for row in cases:
            extra = supplement_by_id.get(row['case_id'])
            if extra is not None:
                row['attempts'].extend(extra['attempts'])
                row['independent_supplement'] = extra
            write(staging / row['attempts_json'], row['attempts'])
        for row in supplements:
            write(staging / row['attempts_json'], row['attempts'])

        # All raw/receipt/control evidence is local to this publication. The
        # full5206 source/input tree is explicitly a reproduction prerequisite,
        # rather than being incorrectly described as copied evidence.
        freeze = read(OLD / 'freeze-manifest.json')['files']
        require(isinstance(freeze, list) and len(freeze) == 5206, 'Exact5206 frozen list required')
        frozen_input_paths = {str(safe(OLD / record['relative'])): record for record in freeze}
        require(len(frozen_input_paths) == 5206, 'Duplicate frozen input identity')
        source_proof_paths = {translate(record['path'], OLD / 'outputs') for record in plan['dependencies']
                              if Path(record['path']).suffix in ('.py', '.sh')
                              or '/docker/bin/' in record['path']}
        source_proof_paths.update(OLD / 'control' / name for name in (
            'run_frozen_matrix.py', 'finalize_fresh629.py', 'observe_container_pids.py'))
        for path in sorted(source_proof_paths):
            copies.copy(path, 'source-proof/' + path.relative_to(OLD).as_posix())
        for helper in helpers.values():
            copies.copy(Path(helper['path']), expected=helper)
        copies.copy(Path(__file__), expected=control_records[str(Path(__file__).absolute())])
        copies.copy(PREP / 'contract.json', expected=control_records[str(PREP / 'contract.json')])
        copies.copy(OLD / 'freeze-manifest.json')
        for path, record in admission['evidence'].items():
            if path not in frozen_input_paths or Path(path) in source_proof_paths:
                copies.copy(Path(path), expected=record)
        for directory in (OLD / 'host', REC / 'manager', REC / 'observer', REC / 'cpu-final-validation',
                          REC / 'writer-mapping-audit-final-01', REC / 'root-terminal-verification-01',
                          REC / 'controller-adapter', REC / 'missing-four-preparation', FOUR / 'host', PREP):
            copies.tree(directory)
        for path in sorted(REC.iterdir()):
            if path.is_file():
                copies.copy(path)
        for directory in contract['additional_historical_gate_call_directories']:
            copies.tree(Path(directory))

        external = []
        for path, record in frozen_input_paths.items():
            if path not in copies.copies:
                external.append({'original_path': path, 'frozen_relative_path': str(Path(path).relative_to(OLD)),
                                 'bytes': record.get('bytes', record.get('size')), 'sha256': record['sha256']})
        write(staging / 'reproduction-inputs-external.json', {
            'schema_version': 1, 'scope': 'Reproduction inputs only; not missing publication evidence.',
            'full_original_machine_tree_independently_restorable': False,
            'frozen5206_manifest': copies.copies[str(OLD / 'freeze-manifest.json')],
            'steps': [
                'Load the verified canonical SDK018 Docker image; scientific dependencies remain inside Docker.',
                'Restore the frozen source context and generated motion/geometry inputs using the repository note.md/usage.md workflows and release-assets.json; this publication does not repeat that GB-scale tree.',
                'Use the exact two released student ONNX SHA values from plan.json, not future self-trained student weights.',
                'Compare every resulting file to the retained5206 freeze manifest and all native plan source/model/dependency SHA records before any future native execution. A Git revision alone is insufficient for generated inputs.',
            ], 'files': external})
        scenes = []
        for name, count in publisher.SCENARIO_COUNTS.items():
            selected = [row for row in cases if row['scenario'] == name]
            flags = sum(row['threshold_event'] for row in selected)
            scenes.append({'scenario': name, 'planned_configurations': count, 'configurations': len(selected),
                           'threshold_events': flags, 'no_threshold_events': len(selected) - flags,
                           'historical_noncompleted_attempts': 0})
        representatives = [next(row for row in cases if row['scenario'] == name and row['configuration_index'] == 0)
                           for name in publisher.SCENARIO_COUNTS]
        summary = {'schema_version': 2, 'status': 'recovered629_publication', 'preview': False,
                   'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'plan_sha256': plan['plan_sha256'], 'matrix_sha256': fp(OLD / 'outputs/all-configs/matrix.json')['sha256'],
                   'image_id': plan['image_id'], 'model_sha256': plan['model_sha256'],
                   'configurations': 629, 'unique_configurations': 629, 'actual_attempts': 633,
                   'original_attempts': 629, 'separate_supplement_attempts': 4,
                   'planned_configurations': 629, 'policy_ticks': sum(row['policy_ticks'] for row in cases),
                   'policy_seconds': sum(row['policy_seconds'] for row in cases),
                   'threshold_events': sum(row['threshold_event'] for row in cases),
                   'no_threshold_events': sum(not row['threshold_event'] for row in cases), 'scenarios': scenes,
                   'original_clean_workers': 1258, 'original_full_video_decodes': 629,
                   'original_unique_host_writer_mappings': 1250, 'original_missing_historical_writer_mappings': 8,
                   'supplement_clean_workers': 8, 'supplement_host_writer_mappings': 8, 'supplement_full_video_decodes': 4,
                   'original_session54334_exit_code': 143, 'original_host_transaction_normal_exit_verified': False,
                   'original_continuous1258_host_mappings_verified': False,
                   'historical_host_observer_gap_preserved': True, 'configuration_coverage_complete': True,
                   'evidence_publication_self_contained': True, 'reproduction_inputs_external': True,
                   'quality_verified': False, 'obstacle_course_completion_verified': False,
                   'scope': '629 original native rollouts plus4 separately recorded historical-writer-gap attempts. Original143 and8 missing original host observations are preserved, not retroactively repaired.',
                   'representative_rule': 'Original configuration_index0 of each of17 scenarios, independent of threshold outcome',
                   'supplement_threshold_events': sum(row['threshold_event'] for row in supplements),
                   'publisher_sha256': fp(__file__)['sha256']}
        for name, value in (('summary.json', summary), ('cases.json', cases), ('scenarios.json', scenes),
                            ('supplement-cases.json', supplements), ('representatives.json', representatives),
                            ('proof-path-map.json', copies.copies)):
            write(staging / name, value)
        fields = ['ordinal', 'case_id', 'scenario', 'configuration_index', 'configuration', 'command', 'mesh_sha256',
                  'policy_ticks', 'policy_seconds', 'threshold_event', 'result_json', 'trajectory_csv']
        with (staging / 'cases.csv').open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(cases)
        banner = ('<p class="warning"><strong>Recovered transaction:633 actual attempts /629 unique configurations.</strong> '
                  '原host session54334真实exit143永久保留。原1258worker中1250个历史host映射、8个旧缺口；'
                  '另四例补验独立记录8个新映射和4段全片decode，不能填入旧worker出生身份。'
                  '<a href="index.md">恢复边界与原始证明</a> · <a href="supplement.html">四例独立补验</a></p>')
        page = publisher.make_page(summary, cases)
        require(page.count('</h1>') == 1, 'Frozen renderer layout changed')
        (staging / 'playback.html').write_text(page.replace('</h1>', '</h1>' + banner, 1))
        supplement_html = '<!doctype html><meta charset="utf-8"><title>Four separate writer-gap attempts</title><h1>四例独立补验</h1><p>新birth单独保存；原八个历史映射缺口仍存在。quality_verified=false。</p>'
        for row in supplements:
            supplement_html += '<h2>' + html.escape(row['case_id']) + '</h2><p>threshold_event=' + str(row['threshold_event']) + '</p>'
            for video in row['videos']:
                supplement_html += '<video controls preload="none" width="640" src="' + html.escape(video['path']) + '" poster="' + html.escape(video['thumbnail']) + '"></video>'
            supplement_html += '<p><a href="' + html.escape(row['result_json']) + '">原始result</a> · <a href="' + html.escape(row['attempts_json']) + '">原始attempt</a></p>'
        (staging / 'supplement.html').write_text(supplement_html)
        index = ('# recovered629真实物理结果\n\n[629配置离线画廊](playback.html) · [四例独立补验](supplement.html) · [机器汇总](summary.json) · [公共gate真实返回](gate-admission.json) · [全部proof路径映射](proof-path-map.json)\n\n'
                 '实际633次attempt，覆盖629个唯一配置。原629/1258worker/629全片decode的CPU证明与原1250host映射保留；speed-vault cfg0004–0007的八个旧映射仍明确缺失，另四次新attempt提供八个独立新映射、四段全片decode。原host退出143不改写为0，不声称原连续1258映射。所有阈值事件保留，quality_verified=false。\n\n'
                 '本画廊的629主结果始终显示原629结果，不挑选四例补验覆盖原结果。每场景固定原config0的17个代表视频如下。\n\n')
        for row in representatives:
            index += '- [' + row['scenario'] + '](' + row['videos'][0]['path'] + ') · [PNG](' + row['videos'][0]['thumbnail'] + ')\n'
        index += ('\n原始结果、worker收据、sealed reports、控制源码和完整observer流均以原字节收入本发布。超过25MB或observer JSONL按连续不超过25,000,000B分块，.chunks.json保留whole bytes/SHA和顺序；拼接后须核whole SHA。原始JSON保留历史绝对路径，proof-path-map.json给出其实际发布副本或分块位置。\n\n'
                  'evidence_publication_self_contained=true仅指验收raw证据闭包。[reproduction-inputs-external.json](reproduction-inputs-external.json)明确保留5206冻结树/大模型/生成几何的外部恢复前提和精确SHA；本包不声称独立还原原机器GB级树。恢复原始输入应使用仓库note.md/usage.md、官方release资产与原plan/freeze SHA逐文件核验。\n')
        (staging / 'index.md').write_text(index)
        copies.finish()
        final_admission = gate.previous_recovered()
        require(final_admission == admission, 'Shared recovered gate changed during publication')
        for path, expected in control_records.items():
            require(fp(path) == expected, 'Publication control source changed')
        records = [{'path': path.relative_to(staging).as_posix(), 'bytes': path.stat().st_size,
                    'sha256': fp(path)['sha256']} for path in sorted(staging.rglob('*')) if path.is_file()]
        write(staging / 'evidence-manifest.json', {'schema_version': 2, 'status': summary['status'],
              'files': records, 'bytes_excluding_manifest': sum(row['bytes'] for row in records),
              'byte_copies_or_contiguous_chunks': list(copies.copies.values()),
              'gate_sha256': helpers['gate']['sha256'], 'actual_attempts': 633, 'unique_configurations': 629,
              'evidence_publication_self_contained': True, 'reproduction_inputs_external': True,
              'original_session54334_exit_code': 143, 'quality_verified': False})
        staging.rename(DESTINATION)
        return summary
    except BaseException as error:
        # Preserve partial copied evidence for review; never overwrite or retry
        # raw attempts, and never publish a partially constructed directory.
        write(staging / 'publication-error.json', {'status': 'publication_failed', 'error': repr(error),
              'original_inputs_modified': False, 'quality_verified': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-authorized-publish', action='store_true')
    parser.add_argument('--expected-contract-sha256', required=True)
    args = parser.parse_args()
    require(args.root_authorized_publish, 'Root must explicitly authorize this CPU-only publication')
    require(fp(PREP / 'contract.json')['sha256'] == args.expected_contract_sha256,
            'Publication contract differs from reviewed root invocation')
    contract = read(PREP / 'contract.json')
    require(contract['publication'] == str(DESTINATION) and contract['chunk_limit_bytes'] == CHUNK_BYTES,
            'Frozen publication destination/contract differs')
    require(contract['adapter_sha256'] == fp(__file__)['sha256'], 'Adapter differs from reviewed contract')
    control_records = {str(Path(path).absolute()): fp(path) for path in (
        Path(__file__), PREP / 'contract.json', *(row['path'] for row in contract['frozen_helpers'].values()))}
    print(json.dumps(publish(contract, control_records), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
