#!/usr/bin/env python3
"""Archive actual first-attempt evidence and verify local source completion.

Run after fetching a terminal coverage directory. Raw JSON/arrays/events are
losslessly compressed, MP4 bytes stay unchanged, and restoration uses a fresh
directory. ffprobe/ffmpeg run only in the existing CPU Docker environment.
"""
from __future__ import annotations
import argparse
import collections
import datetime
import gzip
import hashlib
import html
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess

POLICIES = ('teacher', 'pure', 'finetune')
SKILLS = ('locomotion', 'low-step', 'high-step', 'low-climb-76', 'high-climb-76')
PREFIX = PurePosixPath('/outputs/posttrain-coverage')
INVENTORY_IDENTITY = '77017c028ffcc428f9361cf93c66ade581e2c5ed6f5db42c601f2b659f07dba9'
HARNESS = {'eval_source_coverage.py': '3c792390e11f25df94d2744a57e949293a239825f5c45672deebd1cebe342ab0',
           'source_coverage_probe.py': '10ee5fdf2d1d3019983637164207b627a573a1899dfb2edfef480cebce20db31',
           'motion_coverage.py': '01d9648d52618df6d6bc861bb6c58cd8bd2a70ad2da0fbbbd43e90bfea1470bc',
           'eval_quality.py': '5cbb7f483f2aacbf83633b45ccd99872be796a7322e7846d042de1f550bee17e',
           'runtime_robot_assets.py': '445acc80ca982d5034e5ba2c0a47853b7e0199c54e2c64612647bd74e108b5fb'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def local(root, original):
    path = PurePosixPath(original)
    require(path.is_relative_to(PREFIX) and '..' not in path.parts, 'Evidence escapes the actual coverage output')
    target = root / path.relative_to(PREFIX)
    require(target.is_file() and not any(p.is_symlink() for p in (target, *target.parents)), 'Missing/aliased original evidence: ' + str(target))
    return target


def checked_record(root, record):
    path = local(root, record['path'])
    require(sha(path) == record['sha256'] and ('bytes' not in record or path.stat().st_size == record['bytes']), 'Retained original fingerprint differs: ' + record['path'])
    return path


def robot_config(contract):
    return {'asset_root': contract['runtime_root'], 'urdf_file': contract['urdf_file'], 'usd_file': None,
            'manifest_sha256': contract['manifest']['sha256'], 'original_files': len(contract['files'])}


def validate_quality(root, quality, case):
    require(quality['status'] == 'completed' and quality['quality_verified'] is False
            and quality['execution_error'] is None and quality['checkpoint']['path'] == case['checkpoint']
            and quality['checkpoint']['sha256'] == case['checkpoint_sha256'], 'Passed native report/model/status differs')
    for qkey, ckey in (('case_id', 'case_id'), ('policy', 'policy'), ('source', 'source'),
                      ('singleton_provenance_sha256', 'singleton_provenance_sha256'), ('inventory_identity_sha256', 'inventory_sha256'),
                      ('source_inventory', 'source_inventory'), ('harness_sources', 'harness_sources'),
                      ('runtime_robot_assets', 'runtime_robot_assets'), ('native_argv', 'native_argv')):
        require(quality[qkey] == case[ckey], 'Passed native identity differs: ' + qkey)
    runtime = quality['actual_native']
    require(runtime['robot_asset_config'] == robot_config(case['runtime_robot_assets'])
            and runtime['source_table_verification']['status'] == 'matched_selected_source'
            and runtime['num_envs'] == runtime['loader_num_motions'] == 1
            and runtime['frames'] == case['source']['frames'] and runtime['boundary_indices_inclusive'] == [case['source']['frames'] - 1],
            'Passed native singleton/reference/robot identity differs')
    records = [quality['trajectory'], *quality['tensorboard_events'], *quality['videos']]
    records.extend(runtime[name]['retained'] for name in ('motion', 'terrain_obj', 'saved_eval_config'))
    require(quality['tensorboard_events'] and quality['videos'] and any(row['duration_seconds'] > 0 for row in quality['videos']), 'Passed native event/video evidence missing')
    for record in records:
        require(PurePosixPath(record['path']).is_relative_to(case['output']), 'Native evidence belongs to another case')
        checked_record(root, record)
    require(set(quality['metrics']) == {'motion/error_' + name for name in ('ref_pos', 'ref_rot', 'body_pos', 'joint_pos')}, 'Four native tracking metrics required')
    for metric in quality['metrics'].values():
        require(metric['samples'] == quality['control_steps'] and metric['finite'] is (True if quality['control_steps'] else None), 'Native tracking scope differs')


def verify_input_chain(root, selection, summary):
    """Stdlib provenance checks; the actual seven-PT science is already recorded."""
    require(selection['input_identity'] == identity({key: value for key, value in selection.items() if key != 'input_identity'}), 'Selection canonical identity differs')
    ready = read(root / 'cpu-ready.json')
    require(ready['status'] == 'cpu_scientific_checks_passed' and ready['input_identity'] == selection['input_identity']
            and ready['total_sources'] == 296 and ready['simulation_started'] is False and ready['quality_verified'] is False
            and ready['runtime_robot_assets'] == selection['runtime_robot_assets'], 'Actual complete CPU-ready identity differs')
    labels = ['teacher-' + skill for skill in SKILLS] + ['student-pure', 'student-finetune']
    require(set(selection['checkpoints']) == set(labels) and [row['label'] for row in ready['checkpoints']] == labels, 'All seven ordered final PTs required')
    for row in ready['checkpoints']:
        expected = selection['checkpoints'][row['label']]
        teacher = row['label'].startswith('teacher-')
        kind = 'teacher' if teacher else row['label'].removeprefix('student-')
        target = {'teacher': 'holosoma.agents.ppo.ppo.PPO', 'pure': 'wbt_training.utils.student_teacher.PhpDistillation',
                  'finetune': 'wbt_training.utils.student_teacher.PhpDistillationPPO'}[kind]
        registry = 'file:///data/assets/motions-' + row['label'].removeprefix('teacher-') if teacher else ','.join('file:///data/assets/motions-' + skill for skill in SKILLS)
        require(all(row.get(key) == value for key, value in expected.items()) and row['embedded_config_verified'] is True,
                'CPU report/final selected PT differs')
        require((expected['iteration'], expected['num_envs'], expected['num_variants']) ==
                ((19999, 4096, 64) if teacher else (9999 if kind == 'pure' else 29999, 2048, 3)), 'Canonical final schedule differs')
        require(row['algorithm'] == target and row['registry'] == registry and len(row['tensor_counts']) == (2 if teacher else 1)
                and all(type(count) is int and count > 0 for count in row['tensor_counts']), 'CPU algorithm/registry/finite tensor receipt differs')
        if not teacher:
            experts = row['frozen_experts']
            require(len(experts) == 5 and [item['original_expert_ordinal'] for item in experts] == list(range(5))
                    and all(item['bitwise_equal_to_final_teacher'] is True and item['actor_tensors'] == 8 and item['normalizer_tensors'] == 3 for item in experts), 'Five frozen final expert proofs missing')
    assets = selection['runtime_robot_assets']
    require(len(assets['files']) == 35, 'Canonical 35-file runtime robot closure required')
    checked_record(root, assets['manifest'])
    for item in assets['files']:
        checked_record(root, {'path': str(PurePosixPath(assets['runtime_root']) / item['relative_path']),
                              'bytes': item['bytes'], 'sha256': item['copy_sha256']})
        require(item['source_sha256'] == item['copy_sha256'], 'Original/copied robot asset SHA differs')
    require([row['policy'] for row in ready['plans']] == list(POLICIES), 'All three ordered actual CPU plans required')
    attempts = {(row['policy'], row['case_id']): row for row in summary['cases']}
    cases, source_order = {}, None
    identity_keys = ('source_clip_id', 'global_ordinal', 'expert_ordinal', 'source_ordinal', 'source_motion_sha256',
                     'source_terrain_sha256', 'source_obj_sha256', 'frames', 'fps', 'source_bounds')
    for policy, plan_record in zip(POLICIES, ready['plans']):
        plan_path = checked_record(root, plan_record)
        require(plan_path == root / policy / 'plan.json' and plan_record['sources'] == 296, 'CPU plan path/source count differs')
        plan = read(plan_path)
        require(plan['schema_version'] == 2 and plan['policy'] == policy and plan['selected_sources'] == plan['inventory_total_sources'] == len(plan['cases']) == 296
                and plan['runtime_robot_assets'] == assets, 'Full schema2 source plan required')
        require([row['path'] for row in plan['harness_sources']] == ['/workspace/php_parkour/scripts/research/' + name for name in HARNESS]
                and {Path(row['path']).name: row['sha256'] for row in plan['harness_sources']} == HARNESS,
                'Original frozen five-file scientific harness differs')
        inventory = read(checked_record(root, plan['source_inventory']))
        records = inventory['records']
        require(len(records) == inventory['total_files'] == 296
                and identity([{key: item[key] for key in identity_keys} for item in records]) == inventory['inventory_sha256'] == plan['inventory_sha256'] == ready['inventory_sha256'] == INVENTORY_IDENTITY, 'Complete canonical source inventory identity differs')
        require(all(item['skill'] == SKILLS[item['expert_ordinal']] and item['registry_component'] == 'motions-' + item['skill']
                    and item['source_clip_id'] == item['registry_component'] + '/' + item['relative_motion'] and item['fps'] == 50.0 for item in records),
                'Original expert/source registry labels differ')
        ids = [item['source_clip_id'] for item in records]
        require(len(set(ids)) == 296 and [item['source_clip_id'] for item in plan['cases']] == ids
                and (source_order is None or source_order == ids), 'Filtered/reordered/replaced source coverage')
        require(collections.Counter(item['skill'] for item in records) == dict(zip(SKILLS, (100, 56, 60, 40, 40))), 'Original five source groups differ')
        source_order = ids
        cpu_summary = read(root / policy / 'cpu-preflight-summary.json')
        require(cpu_summary['status'] == 'completed' and len(cpu_summary['cases']) == 296
                and checked_record(root, cpu_summary['plan']) == plan_path, 'Full actual CPU preflight summary required')
        for item, source, cpu_row in zip(plan['cases'], records, cpu_summary['cases']):
            case_path = checked_record(root, item['case'])
            case = read(case_path)
            label = 'teacher-' + source['skill'] if policy == 'teacher' else 'student-' + policy
            checkpoint = selection['checkpoints'][label]
            require(case['schema_version'] == 2 and case['case_id'] == item['case_id'] == cpu_row['case_id']
                    and case['policy'] == policy and case['source'] == source and case['source_inventory'] == plan['source_inventory']
                    and case['inventory_sha256'] == inventory['inventory_sha256'] and case['runtime_robot_assets'] == assets
                    and case['harness_sources'] == plan['harness_sources'] and case['max_steps'] == source['frames']
                    and case['output'] == str(PREFIX / policy / 'cases' / case['case_id'])
                    and (case['checkpoint'], case['checkpoint_sha256']) == (checkpoint['path'], checkpoint['sha256'])
                    and item['checkpoint'] == {'path': checkpoint['path'], 'sha256': checkpoint['sha256'], **({'bytes': item['checkpoint']['bytes']} if 'bytes' in item['checkpoint'] else {})}, 'Case/source/final model binding differs')
            require(cpu_row['status'] == 'cpu_preflight_passed_gpu_not_run' and cpu_row['return_code'] == 0, 'CPU source preflight did not pass')
            cpu = read(checked_record(root, cpu_row['report']))
            require(cpu['status'] == 'cpu_preflight_passed_gpu_not_run' and cpu['case_id'] == case['case_id'] and cpu['source'] == source
                    and cpu['checkpoint']['path'] == case['checkpoint'] and cpu['checkpoint']['sha256'] == case['checkpoint_sha256']
                    and cpu['runtime_robot_assets'] == assets and cpu['robot_asset_config'] == robot_config(assets)
                    and cpu['actual_frames'] == source['frames'] and cpu['actual_boundary_indices_inclusive'] == [source['frames'] - 1]
                    and cpu['source_table_verification']['status'] == 'matched_selected_source', 'CPU singleton/model/source proof differs')
            require(cpu['simulation_started'] is False and cpu['num_envs'] == 1 and cpu['actual_native_expert_ids'] == [0]
                    and cpu['expert_balancing_active'] is False and cpu['original_expert_ordinal'] == source['expert_ordinal'], 'CPU singleton/expert scope differs')
            for qkey, ckey in (('policy', 'policy'), ('singleton_provenance_sha256', 'singleton_provenance_sha256'),
                              ('inventory_identity_sha256', 'inventory_sha256'), ('registry_uri', 'registry_uri'), ('harness_sources', 'harness_sources')):
                require(cpu[qkey] == case[ckey], 'CPU actual identity differs: ' + qkey)
            require({Path(row['path']).name for row in cpu['artifacts']} == {'holosoma_config.yaml', 'motion.npz', 'terrain.obj'}, 'CPU retained native artifact set differs')
            for artifact in cpu['artifacts']: checked_record(root, artifact)
            provenance = read(checked_record(root, {'path': case['singleton_provenance'], 'sha256': case['singleton_provenance_sha256']}))
            require(provenance['record'] == source and provenance['registry_uri'] == case['registry_uri']
                    and provenance['original_expert_ordinal'] == source['expert_ordinal'] and provenance['singleton_native_expert_ordinal'] == 0, 'Byte-preserving original source provenance differs')
            for record in provenance['files']:
                require(record['sha256'] == source['source_' + record['role'] + '_sha256'], 'Materialized source differs from the released inventory')
                checked_record(root, record)
            attempt = attempts[(policy, case['case_id'])]
            require(attempt['input_identity'] == selection['input_identity'] and attempt['case_sha256'] == item['case']['sha256']
                    and attempt['source_clip_id'] == source['source_clip_id'] and attempt['quality_verified'] is False
                    and read(case_path.with_name('posttrain-attempt.json')) == attempt, 'Original first attempt/plan/summary differs')
            for artifact in attempt['artifacts']: checked_record(root, artifact)
            require(attempt['status'] in ('execution_passed', 'execution_failed'), 'Nonterminal source attempt')
            if attempt['status'] == 'execution_passed':
                require(type(attempt['returncode']) is int and attempt['returncode'] == 0 and not attempt.get('error'), 'Passed native worker did not actually return0')
                validate_quality(root, read(case_path.with_name('quality.json')), case)
            cases[(policy, case['case_id'])] = case
    require(len(cases) == 888 and set(cases) == set(attempts), 'Original attempt/case coverage differs')
    failures = sum(row['status'] == 'execution_failed' for row in attempts.values())
    require(summary['execution_failed'] == failures and summary['execution_passed'] == 888 - failures
            and summary['status'] == ('execution_failed' if failures else 'completed') and summary['quality_verified'] is False,
            'Terminal first-attempt counters/status differ')
    return cases


def completion(quality, trajectory):
    """Recompute the narrow source-boundary predicate from every original row."""
    policy = [row for row in trajectory if row['phase'] == 'policy']
    warmup = [row for row in trajectory if row['phase'] == 'attempt_warmup']
    # Initialization is a separate reset; only the actual attempt is scored.
    frames = [row['reference_frame'] for row in policy]
    expected = list(range(1, quality['source']['frames'] - 1))
    require(frames == quality['policy_reference_frames'] and len(policy) == quality['control_steps'], 'Original report/trajectory policy-frame mismatch')
    require([row['policy_step'] for row in policy] == list(range(len(policy))), 'Original policy step order mismatch')
    require(all(row['finite_action'] and row['finite_root_state'] and row['finite_metrics'] for row in policy + warmup), 'Nonfinite original attempt row')
    require(sum(row['failed'] for row in policy + warmup) == quality['failed_resets']
            and sum(row['timeout'] for row in policy + warmup) == quality['timeout_resets'], 'Original reset counters mismatch')
    complete = (quality['status'] == 'completed' and quality['execution_error'] is None
                and quality['stop_reason'] == 'native_boundary' and frames == expected and bool(policy)
                and policy[-1]['motion_end_reset'] and not any(row['failed'] or row['timeout'] for row in policy + warmup))
    require(quality['first_attempt_reference_boundary_reached'] is complete, 'Original boundary declaration/trajectory mismatch')
    return {'source_boundary_completed': complete, 'policy_steps': len(policy),
            'expected_policy_steps': len(expected), 'policy_frames_contiguous_from_one': frames == expected[:len(frames)],
            'failed_resets': quality['failed_resets'], 'timeout_resets': quality['timeout_resets'],
            'scope': 'One original source, one terrain variant, seed42, first attempt. Frame0 is zero-action warmup; frameT-1 is a boundary sentinel. Not a complete obstacle course.'}


def media_check(path, output):
    require(Path('/.dockerenv').exists(), 'Decode only inside the existing CPU Docker image')
    require(not any(Path('/dev').glob('nvidia[0-9]*')), 'Media check must have no GPU devices')
    argv = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
            'stream=nb_read_frames,width,height,r_frame_rate:format=duration', '-of', 'json', str(path)]
    probed = subprocess.run(argv, capture_output=True)
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-hwaccel', 'none', '-i', str(path), '-map', '0:v:0',
                              '-an', '-sn', '-dn', '-f', 'null', '-'], capture_output=True)
    metadata = json.loads(probed.stdout) if probed.returncode == 0 else None
    rows = metadata.get('streams', []) if metadata else []
    frames = int(rows[0].get('nb_read_frames', '0')) if rows else 0
    require(probed.returncode == decoded.returncode == 0 and frames > 0, 'Original MP4 full decode failed: ' + str(path))
    report = {'sha256': sha(path), 'bytes': path.stat().st_size, 'ffprobe_returncode': probed.returncode,
              'ffmpeg_returncode': decoded.returncode, 'decoded_frames': frames, 'metadata': metadata,
              'ffprobe_stderr': probed.stderr.decode(errors='replace'), 'ffmpeg_stderr': decoded.stderr.decode(errors='replace')}
    save(output, report)
    return report


def archive(root, output):
    """Content deduplication preserves every original path, byte and mode."""
    body, media = output / 'archive', output / 'media'
    body.mkdir(); media.mkdir()
    inventory = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Original input contains a file or directory symlink')
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.lstat().st_mode), 'Original input contains non-regular evidence')
        record = {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
                  'sha256': sha(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
        if path.suffix.lower() == '.mp4':
            require(record['bytes'] < 100_000_000, 'MP4 exceeds the publication file limit; no silent transcoding')
            target = media / (record['sha256'] + '.mp4')
            if not target.exists(): shutil.copyfile(path, target)
            require(sha(target) == record['sha256'], 'Original MP4 changed during copying')
            record.update(storage='original', stored=target.relative_to(output).as_posix())
        else:
            target = body / (record['sha256'] + '.gz')
            if not target.exists() and not target.with_suffix('.chunks.json').exists():
                copied = hashlib.sha256()
                with path.open('rb') as source, target.open('wb') as encoded, gzip.GzipFile(fileobj=encoded, mode='wb', mtime=0) as zipped:
                    while block := source.read(1024 * 1024):
                        copied.update(block)
                        zipped.write(block)
                require(copied.hexdigest() == record['sha256'], 'Original input changed during archive')
                # A source binary/observation stream can exceed Git's per-file
                # limit even after compression. Keep continuous 25 MB chunks.
                if target.stat().st_size > 25_000_000:
                    chunks = []
                    with target.open('rb') as stream:
                        index = 0
                        while block := stream.read(25_000_000):
                            chunk = target.with_suffix(f'.part{index:04d}')
                            chunk.write_bytes(block)
                            chunks.append({'path': chunk.relative_to(output).as_posix(), 'offset': index * 25_000_000,
                                           'bytes': len(block), 'sha256': sha(chunk)})
                            index += 1
                    save(target.with_suffix('.chunks.json'), {'chunks': chunks, 'compressed_sha256': sha(target), 'compressed_bytes': target.stat().st_size})
                    target.unlink()
            chunks_path = target.with_suffix('.chunks.json')
            record.update(storage='gzip', stored=(chunks_path if chunks_path.exists() else target).relative_to(output).as_posix())
        inventory.append(record)
    save(output / 'raw-inventory.json', inventory)
    return {row['path']: row for row in inventory}


def build(root, output, expected):
    require(not output.is_relative_to(root) and not root.is_relative_to(output), 'Input and output must be separate')
    require(sha(root / 'selection.json') == expected, 'Actual selection SHA differs')
    selection, summary = read(root / 'selection.json'), read(root / 'summary.json')
    require(summary['input_identity'] == selection['input_identity'] and summary['status'] in ('completed', 'execution_failed'), 'A terminal original batch is required')
    monitor = read(root / 'monitor-status.json')
    require(monitor['status'] == summary['status'] and monitor['container_exit_code'] == (0 if summary['status'] == 'completed' else 1)
            and monitor['container'] == 'php-parkour-posttrain-gpu-' + selection['input_identity'][:12],
            'The actual frozen host final verification and stopped GPU-container exit are required')
    require(len(summary['cases']) == 888 and len({(row['policy'], row['case_id']) for row in summary['cases']}) == 888, 'Expected all 888 unique first attempts')
    require(collections.Counter(row['policy'] for row in summary['cases']) == dict.fromkeys(POLICIES, 296), 'Each policy must retain all 296 sources')
    cases = verify_input_chain(root, selection, summary)
    require(not output.exists(), 'Use a fresh output; retain failed publication stages')
    output.mkdir()
    inventory = archive(root, output)
    (output / 'media-validation').mkdir()
    rows, checked, bound_videos = [], {}, set()
    for record in inventory.values():
        if record['storage'] == 'original' and record['stored'].endswith('.mp4') and record['sha256'] not in checked:
            checked[record['sha256']] = media_check(root / record['path'], output / 'media-validation' / (record['sha256'] + '.json'))
    for attempt in summary['cases']:
        case_path = root / attempt['policy'] / 'cases' / attempt['case_id'] / 'case.json'
        require(sha(case_path) == attempt['case_sha256'], 'Original case SHA differs')
        case = cases[(attempt['policy'], attempt['case_id'])]
        require(read(case_path.with_name('posttrain-attempt.json')) == attempt, 'Original attempt/summary mismatch')
        row = {key: attempt.get(key) for key in ('policy', 'case_id', 'source_clip_id', 'status', 'returncode', 'error', 'stop_reason')}
        row.update(skill=case['source']['skill'], source_frames=case['source']['frames'],
                   checkpoint_sha256=case['checkpoint_sha256'], source_boundary_completed=False, videos=[])
        for item in attempt['artifacts']:
            require(sha(local(root, item['path'])) == item['sha256'], 'Original attempt artifact SHA differs')
        quality_path = case_path.with_name('quality.json')
        if quality_path.is_file():
            quality = read(quality_path)
            row.update(stop_reason=quality.get('stop_reason'), policy_steps=quality.get('control_steps'), tracking_metrics=quality.get('metrics'))
            if quality.get('status') == 'completed':
                require(quality['policy'] == attempt['policy'] and quality['source'] == case['source']
                        and quality['checkpoint']['sha256'] == case['checkpoint_sha256'], 'Original source/model identity differs')
                trajectory = local(root, quality['trajectory']['path'])
                require(sha(trajectory) == quality['trajectory']['sha256'], 'Original trajectory SHA differs')
                observed = completion(quality, [json.loads(line) for line in trajectory.read_text().splitlines()])
                observed['reference_boundary_observed'] = observed['source_boundary_completed']
                observed['source_boundary_completed'] = (observed['source_boundary_completed']
                                                          and attempt['status'] == 'execution_passed' and attempt['returncode'] == 0)
                row.update(observed)
            for video in quality.get('videos', []):
                path = local(root, video['path'])
                require(sha(path) == video['sha256'], 'Original video SHA differs')
                record = inventory[path.relative_to(root).as_posix()]
                bound_videos.add(record['path'])
                row['videos'].append({'url': record['stored'], 'sha256': record['sha256'],
                                      'duration_seconds': float(checked[record['sha256']]['metadata']['format']['duration']),
                                      'association': video['association'], 'quality_bound': True})
            row['policy_video_span_covers_policy_steps'] = bool(row['videos']) and max(video['duration_seconds'] for video in row['videos']) >= quality.get('policy_sim_seconds', 0) - .04
        prefix = case_path.parent.relative_to(root).as_posix() + '/'
        for record in inventory.values():
            if record['path'].startswith(prefix) and record['storage'] == 'original' and record['path'] not in bound_videos:
                row['videos'].append({'url': record['stored'], 'sha256': record['sha256'],
                    'duration_seconds': float(checked[record['sha256']]['metadata']['format']['duration']),
                    'quality_bound': False, 'association': 'Original MP4 absent from this quality report; retained and decoded, not proof of completion.'})
        rows.append(row)
    groups = []
    for policy in POLICIES:
        for skill in SKILLS:
            chosen = [row for row in rows if row['policy'] == policy and row['skill'] == skill]
            groups.append({'policy': policy, 'skill': skill, 'attempts': len(chosen),
                           'execution_passed': sum(row['status'] == 'execution_passed' for row in chosen),
                           'source_boundary_completed': sum(row['source_boundary_completed'] for row in chosen),
                           'stop_reasons': dict(collections.Counter(row.get('stop_reason') or 'execution_error' for row in chosen))})
    save(output / 'cases.json', rows)
    save(output / 'orphan-media.json', [record for record in inventory.values() if record['storage'] == 'original' and record['path'] not in bound_videos])
    save(output / 'summary.json', {'input_identity': selection['input_identity'], 'original_batch_status': summary['status'],
                                 'attempts': 888, 'groups': groups, 'unique_videos_full_decoded': len(checked),
                                 'terminal_monitor_sha256': sha(root / 'monitor-status.json'),
                                 'quality_verified': False, 'obstacle_course_completion_verified': False})
    write_gallery(output, rows, groups)
    shutil.copy2(__file__, output / 'cloud888_report.py')
    for record in inventory.values():
        original = root / record['path']
        require(original.stat().st_size == record['bytes'] and sha(original) == record['sha256'], 'Original raw input changed during publication')
    save(output / 'evidence-manifest.json', {'schema_version': 1,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'selection_sha256': expected, 'source_input_files': len(inventory),
        'files': [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                  for path in sorted(output.rglob('*')) if path.is_file()],
        'scope': 'Complete original coverage byte archive and generated first-attempt report; no training, convergence or course-success claim.'})


def restore(package, output):
    """Restore original coverage bytes/modes only; never run any scientific job."""
    require(not output.exists() and not output.is_relative_to(package), 'Use a fresh separate restore directory')
    verify_package(package)
    output.mkdir()
    restored = set()
    for record in read(package / 'raw-inventory.json'):
        relative = PurePosixPath(record['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in restored, 'Unsafe/duplicate original path')
        restored.add(str(relative))
        stored = PurePosixPath(record['stored'])
        require(not stored.is_absolute() and '..' not in stored.parts, 'Unsafe archive path')
        source = package / stored
        require(not any(p.is_symlink() for p in (source, *source.parents)), 'Aliased archive input')
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        if record['storage'] == 'gzip' and source.name.endswith('.chunks.json'):
            description = read(source)
            temporary = output / ('.compressed-' + record['sha256'])
            offset = 0
            with temporary.open('xb') as assembled:
                for item in description['chunks']:
                    chunk_relative = PurePosixPath(item['path'])
                    require(not chunk_relative.is_absolute() and '..' not in chunk_relative.parts, 'Unsafe compressed chunk path')
                    chunk = package / chunk_relative
                    require(item['offset'] == offset and chunk.stat().st_size == item['bytes']
                            and sha(chunk) == item['sha256'], 'Compressed chunk mismatch')
                    with chunk.open('rb') as stream: shutil.copyfileobj(stream, assembled, 1024 * 1024)
                    offset += item['bytes']
            require(offset == description['compressed_bytes'] and sha(temporary) == description['compressed_sha256'], 'Compressed whole bytes/SHA mismatch')
            source = temporary
        if record['storage'] == 'gzip':
            with gzip.open(source, 'rb') as stream, target.open('xb') as raw:
                shutil.copyfileobj(stream, raw, 1024 * 1024)
        else:
            require(record['storage'] == 'original', 'Unknown original storage format')
            shutil.copyfile(source, target)
        require(target.stat().st_size == record['bytes'] and sha(target) == record['sha256'], 'Restored original bytes/SHA mismatch')
        target.chmod(record['mode'])
        if temporary: temporary.unlink()
    return {'status': 'original_coverage_bytes_restored', 'files': len(restored), 'scientific_jobs_started': False}


def verify_package(package):
    """Verify the whole sealed publication before creating any restore output."""
    manifest = read(package / 'evidence-manifest.json')
    expected = {}
    for row in manifest['files']:
        path = PurePosixPath(row['path'])
        require(not path.is_absolute() and '..' not in path.parts and str(path) not in expected
                and str(path) != 'evidence-manifest.json', 'Unsafe/duplicate publication manifest path')
        expected[str(path)] = row
    actual = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlink in sealed publication')
        if path.is_file() and path.relative_to(package).as_posix() != 'evidence-manifest.json':
            actual.add(path.relative_to(package).as_posix())
    require(actual == set(expected), 'Publication file set differs from the complete seal')
    for name, row in expected.items():
        path = package / name
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Publication file SHA/bytes differ: ' + name)
    for row in read(package / 'raw-inventory.json'):
        require(row['stored'] in expected, 'Original inventory storage is outside the publication seal')
        if row['stored'].endswith('.chunks.json'):
            description = read(package / row['stored'])
            digest, offset = hashlib.sha256(), 0
            for chunk in description['chunks']:
                require(chunk['path'] in expected and chunk['offset'] == offset and 0 < chunk['bytes'] <= 25_000_000
                        and expected[chunk['path']]['bytes'] == chunk['bytes'] and expected[chunk['path']]['sha256'] == chunk['sha256'],
                        'Compressed original chunk differs from the complete publication seal')
                with (package / chunk['path']).open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
                offset += chunk['bytes']
            require(offset == description['compressed_bytes'] and digest.hexdigest() == description['compressed_sha256'], 'Compressed original whole SHA/offset differs')
    return {'status': 'complete_publication_seal_verified', 'files': len(expected)}


def write_gallery(output, rows, groups):
    intro = '<p>正式最终模型：3 策略 × 296 原始 source，seed 42、单地形变体、仅首次尝试。局部 source 完成按原始逐步轨迹独立核对；不代表完整越障课程或泛化成功。</p>'
    summary = '<table><tr><th>策略</th><th>技能</th><th>首次尝试</th><th>正常执行</th><th>局部 source 完成</th></tr>'
    for row in groups:
        summary += '<tr>' + ''.join(f'<td>{html.escape(str(row[key]))}</td>' for key in ('policy', 'skill', 'attempts', 'execution_passed', 'source_boundary_completed')) + '</tr>'
    summary += '</table>'
    data = json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c')
    page = '<!doctype html><meta charset="utf-8"><title>正式模型逐源首次尝试</title><style>body{font:16px system-ui;background:#111827;color:#e5e7eb;max-width:1200px;margin:30px auto;padding:0 20px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:8px;text-align:left;border-bottom:1px solid #374151}input,select,button{font:inherit;padding:8px;margin:5px}article{border:1px solid #374151;border-radius:10px;padding:15px;margin:15px 0}video{max-width:100%;width:640px}a{color:#93c5fd}</style><h1>正式模型的 888 次逐源首次尝试</h1>' + intro + summary
    page += '<select id="policy"><option value="">所有策略</option>' + ''.join(f'<option>{x}</option>' for x in POLICIES) + '</select><select id="skill"><option value="">所有技能</option>' + ''.join(f'<option>{x}</option>' for x in SKILLS) + '</select><select id="result"><option value="">所有结果</option><option value="complete">局部 source 完成</option><option value="incomplete">未完成 source</option></select><input id="search" placeholder="搜索 source"><button id="prev">上一页</button><button id="next">下一页</button><p id="count"></p><main></main>'
    page += '<script>const rows=' + data + r''';let page=0;const $=s=>document.querySelector(s);function render(){const filtered=rows.filter(r=>(!$('#policy').value||r.policy===$('#policy').value)&&(!$('#skill').value||r.skill===$('#skill').value)&&(!$('#result').value||r.source_boundary_completed===($('#result').value==='complete'))&&r.source_clip_id.toLowerCase().includes($('#search').value.toLowerCase()));const pages=Math.max(1,Math.ceil(filtered.length/12));page=Math.max(0,Math.min(page,pages-1));$('#count').textContent=`${filtered.length} 项 · 第 ${page+1}/${pages} 页`;$('main').replaceChildren();for(const r of filtered.slice(page*12,page*12+12)){const a=document.createElement('article');const h=document.createElement('h3');h.textContent=`${r.policy} · ${r.skill} · ${r.source_clip_id}`;a.append(h);const p=document.createElement('p');p.textContent=`执行 ${r.status} / 停止 ${r.stop_reason||r.error||'无报告'} / policy ${r.policy_steps??0}/${r.expected_policy_steps??r.source_frames-2} 步 / 局部 source ${r.source_boundary_completed?'完成':'未完成'}`;a.append(p);const videos=[...r.videos].sort((a,b)=>b.duration_seconds-a.duration_seconds);if(videos.length){const v=document.createElement('video');v.controls=true;v.preload='metadata';v.src=videos[0].url;a.append(v);const note=document.createElement('p');note.textContent='最长原始片段；可能包含初始化和零动作 warmup。';a.append(note);for(const [i,video] of videos.entries()){const l=document.createElement('a');l.href=video.url;l.textContent=`原片 ${i+1} (${video.duration_seconds.toFixed(2)} s) `;a.append(l)}}$('main').append(a)}}for(const id of ['policy','skill','result','search'])$('#'+id).addEventListener('input',()=>{page=0;render()});$('#prev').onclick=()=>{page--;render()};$('#next').onclick=()=>{page++;render()};render();</script>'''
    (output / 'playback.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('publish', 'restore'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection-sha256')
    parser.add_argument('--manifest-sha256', help='Actual complete publication manifest SHA, required for restore')
    args = parser.parse_args()
    if args.action == 'publish':
        require(args.selection_sha256, 'Explicit actual selection SHA required')
        build(args.input.resolve(), args.output.resolve(), args.selection_sha256)
    else:
        require(args.manifest_sha256 and sha(args.input / 'evidence-manifest.json') == args.manifest_sha256, 'Explicit actual publication manifest SHA required')
        manifest = read(args.input / 'evidence-manifest.json')
        inventories = [row for row in manifest['files'] if row['path'] == 'raw-inventory.json']
        require(len(inventories) == 1 and sha(args.input / 'raw-inventory.json') == inventories[0]['sha256'], 'Publication original inventory SHA differs')
        print(json.dumps(restore(args.input.resolve(), args.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
