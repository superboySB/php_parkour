#!/usr/bin/env python3
"""Read-only CPU evidence audit; never executes Docker/native/DDS/FFmpeg/GPU."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

BASE = Path('/home/dzp/projects/php_parkour/outputs/research/sdk018-native-pilot-20261010T0915')
OUT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def record(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def translate(value):
    p = Path(value)
    if p.is_relative_to('/outputs'):
        return str(BASE / 'outputs' / p.relative_to('/outputs'))
    if p.is_relative_to('/workspace/php_parkour'):
        return str(BASE / 'source' / p.relative_to('/workspace/php_parkour'))
    raise ValueError('Unexpected receipt output namespace')

plan_path = BASE / 'inputs/native-plan.json'
plan = json.loads(plan_path.read_text())
host = json.loads((BASE / 'host/launch-receipt.json').read_text())
summary = json.loads((BASE / 'outputs/pilot-summary.json').read_text())
observer = json.loads((BASE / 'host/observer/summary.json').read_text())
pilot = json.loads((BASE / 'pilot-plan.json').read_text())
module_path = BASE / 'source/scripts/research/sim2sim_scene_matrix.py'
spec = importlib.util.spec_from_file_location('frozen_native_validator', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert sha(module_path) == '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
assert plan['schema_version'] == 3 and plan['image_id'] == host['create_argv'][-3] == pilot['image_id']
assert plan['plan_sha256'] == summary['native_plan_sha256'] == pilot['native_plan_sha256']
assert host['status'] == summary['status'] == 'completed'
assert host['driver_returncode'] == host['driver_returncode_after_container_stop'] == host['observer_returncode'] == 0
assert host['owned_container_running_after_stop'] is False and summary['remaining_native_pids'] == []
assert observer['mapping_scope_complete'] is True and observer['errors'] == [] and observer['stop_reason'] == 'stop_file'
assert observer['identity']['container_id'] == host['container_id']
assert observer['identity']['image_id'] == pilot['image_id']
assert len(summary['cases']) == len(plan['selections']) == 5
assert len(host['host_native_mappings']) == 10
assert summary['quality_verified'] is False and summary['obstacle_course_completion_verified'] is False
snapshot_checked = 0
for item in pilot['snapshot_files']:
    path = BASE / item['relative']
    assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
    snapshot_checked += 1
cases = []
raw_files = [record(plan_path), record(BASE / 'pilot-plan.json'), record(BASE / 'host/launch-receipt.json'),
             record(BASE / 'host/observer/summary.json'), record(BASE / 'outputs/pilot-summary.json')]
for case, selection in zip(summary['cases'], plan['selections']):
    assert case['case_id'] == selection['case_id'] and case['launch'] == selection['launch']
    assert case['returncode'] == 0 and case['status'] == 'completed' and case['policy_ticks'] == 500
    directory = Path(translate(case['output']))
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text())
    assert sha(result_path) == case['result_sha256']
    assert result['config']['python_faulthandler'] is True and result['config']['commands'] == [selection['command']]
    assert result['config']['duration'] == 10.0 and result['config']['mesh_sha256'] == selection['mesh_sha256']
    assert result['config']['model_sha256'] == plan['model_sha256']
    assert result['quality_verified'] is False and result['obstacle_course_completion_verified'] is False
    assert result['inference']['ticks'] == 500 and result['inference']['control_period_simulation_seconds'] == .02
    receipts = module.validate_worker_receipts(directory, plan, result, translate=translate)
    assert {(Path(p['path']).name, p['sha256'], p['bytes']) for p in receipts} == {(Path(p['path']).name, p['sha256'], p['bytes']) for p in case['worker_receipts']}
    process = json.loads((directory / 'worker-processes.json').read_text())
    assert process['schema_version'] == 2
    final = process['events'][-1]
    assert final['event'] == 'finally_wait_complete' and final['cleanup_errors'] == final['unreaped_roles'] == []
    assert len(final['workers']) == 2
    worker_reports = []
    for role in ['simulator', 'inference']:
        worker = next(w for w in final['workers'] if w['role'] == role)
        assert worker['returncode'] == worker['exit_code'] == 0 and worker['status'] == 'exited'
        assert worker['signal_number'] is None and worker['process_group']['live_members'] == []
        assert worker['process_group']['ownership_verified'] is True and worker['process_group']['ownership_lost'] is False
        entry_path = directory / (role + '-process-start.json')
        entry = json.loads(entry_path.read_text())
        native_pid, birth = entry['process']['pid'], entry['process']['start_time_clock_ticks']
        mapping = next(m for m in host['host_native_mappings'] if m['case_id'] == case['case_id'] and m['role'] == role)
        assert mapping['native_entry_sha256'] == sha(entry_path)
        observed = [m for m in observer['command_writer_mappings'] if m['role'] == role and m['worker_output'] == case['output']
                    and m['container_tgid'] == native_pid and m['owner_start_time_clock_ticks'] == birth]
        assert observed and observed == mapping['mappings']
        for thread in observed:
            assert thread['host_tgid'] == int(thread['status']['Tgid'])
            assert thread['host_tid'] == int(thread['status']['Pid']) == thread['nspid'][0]
            assert thread['nspid'][-1] == thread['container_tid']
            assert thread['nstgid'][0] == thread['host_tgid'] and thread['nstgid'][-1] == native_pid
            assert thread['start_time_clock_ticks'] >= birth
        worker_reports.append({'role': role, 'direct_returncode': 0, 'native_container_pid': native_pid,
                               'native_start_clock_ticks': birth, 'native_entry': record(entry_path),
                               'empty_verified_group': True, 'host_command_writer_mappings': observed})
    rows = list(csv.DictReader((directory / 'trajectory.csv').open()))
    assert rows and all(math.isfinite(float(v)) for row in rows for v in row.values())
    active = [r for r in rows if float(r['policy_seconds']) >= 0]
    assert len(active) >= 500 and all(float(r['gantry_enabled']) == 0 for r in active)
    assert case['video_full_decodes'] and {v['file'] for v in case['video_full_decodes']} == set(result['videos'])
    videos = []
    for video in case['video_full_decodes']:
        path = (directory / video['file']).resolve()
        assert path.is_relative_to(directory.resolve()) and not path.is_symlink()
        assert video['full_decode'] is True and video['returncode'] == 0
        assert '-xerror' in video['command'] and video['command'][-3:] == ['-f', 'null', '-']
        assert path.stat().st_size == video['bytes'] and sha(path) == video['sha256']
        videos.append(record(path) | {'full_decode_recorded_returncode': 0, 'decode_stdout_scope': 'Native executor already ran ffmpeg; audit only rereads immutable receipt'})
    parent_log = Path(translate(case['log']))
    assert sha(parent_log) == case['log_sha256']
    raw_files += [record(result_path), record(parent_log), record(directory / 'trajectory.csv'), *receipts, *videos]
    cases.append({'case_id': case['case_id'], 'status': 'passed', 'wall_seconds': case['finished_unix'] - case['started_unix'],
                  'parent_returncode': case['returncode'], 'policy_ticks': 500,
                  'policy_simulation_seconds': result['simulation']['policy_simulation_seconds'],
                  'workers': worker_reports, 'videos': videos, 'active_finite_unsupported_trajectory_samples': len(active),
                  'quality_events': {key: result['simulation'][key] for key in ['fall_detected','fall_detection_is_heuristic','low_pelvis_detected',
                                     'tilt_threshold_sample_seconds','minimum_pelvis_height_m','minimum_base_up_z','final_position_xyz_m','final_base_up_z']},
                  'survival_heuristic_passed': result['survival_passed'], 'quality_verified': False, 'obstacle_course_completion_verified': False})
report = {'schema_version': 1, 'status': 'passed', 'scope': 'Independent read-only CPU audit of five completed native SDK018 pilot cases; no Docker exec, new decode, DDS or GPU calls',
          'cohort': str(BASE), 'image_id': pilot['image_id'], 'container_id': host['container_id'],
          'native_plan_sha256': plan['plan_sha256'], 'host_plan_sha256': pilot['plan_sha256'],
          'snapshot_files_hash_and_size_verified': snapshot_checked,
          'validator_source': record(module_path), 'audit_source': record(Path(__file__).resolve()),
          'host_wall_seconds_including_create_observer_stop': host['finished_unix'] - host['started_unix'],
          'native_driver_wall_seconds': summary['finished_unix'] - summary['started_unix'],
          'parent_exit0_cases': 5, 'worker_exit0_empty_verified_group_count': 10, 'exact_native_host_command_writer_mapping_count': 10,
          'full_decoded_mp4_count': sum(len(c['videos']) for c in cases), 'cases': cases,
          'source_receipts': raw_files,
          'boundary': 'Five once-only historical failed identities now execute and exit cleanly under candidate SDK018. This does not establish SDK upgrade causality, eliminate an intermittent race statistically, validate all629 configurations, or establish terrain skill success.'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
print(json.dumps({k: report[k] for k in ['status','snapshot_files_hash_and_size_verified','host_wall_seconds_including_create_observer_stop',
     'native_driver_wall_seconds','parent_exit0_cases','worker_exit0_empty_verified_group_count','exact_native_host_command_writer_mapping_count','full_decoded_mp4_count']}))
