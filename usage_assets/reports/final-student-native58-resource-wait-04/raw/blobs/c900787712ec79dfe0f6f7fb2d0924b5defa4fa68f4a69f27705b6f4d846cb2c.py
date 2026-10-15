#!/usr/bin/env python3
"""Audit the preserved failed partial native58 cohort; never admit it as58 complete.

No native rollout, GPU, network, scientific-source write or container mutation.
The explicitly supplied running CPU container performs fresh full MP4 decodes.
"""
from __future__ import annotations
import argparse
import ast
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
WORKSPACE = Path('/home/dzp/projects/php_parkour')
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
PINS = {'common.py': 'bef9e7af9a67c9d10360145de7f6715cb167a8722fccb1e44aaaf4c7118371b2',
        'native58.py': '31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43',
        'phase_cpu.py': '855d56494c662cbfcd19a96043b6f0baaa49a093f52c47b46a9005657e46bb0f'}
MATRIX_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
KINDS = ('pure', 'finetune')


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and path.is_relative_to(WORKSPACE), 'Workspace path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path rejected')
    return path


def fp(path):
    path = safe(path)
    require(path.is_file(), 'Missing actual regular file: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(data)
    after = path.stat()
    signature = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    require(signature(before) == signature(after), 'Evidence changed during hash')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify(args):
    base, exit_path, output = map(safe, (args.base, args.parent_exit, args.output))
    require(not output.exists(), 'Fresh review output required')
    evidence = {}

    def retain(path, expected=None):
        actual = fp(path)
        if expected is not None:
            require(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'], 'Retained bytes differ: ' + str(path))
        require(actual['path'] not in evidence or evidence[actual['path']] == actual, 'Conflicting evidence record')
        evidence[actual['path']] = actual
        return actual

    def actual(path):
        retain(path)
        return read(path)

    review_source = retain(__file__)

    def cpu_inspect(path, cid):
        info = actual(path)
        env = dict(x.split('=', 1) for x in info['Config']['Env'])
        require(info['Id'] == cid and info['Image'] == IMAGE and info['State']['ExitCode'] == 0
                and info['State']['Running'] is False and info['State']['OOMKilled'] is False
                and info['HostConfig']['Runtime'] == 'runc' and info['HostConfig']['NetworkMode'] == 'none'
                and not info['HostConfig'].get('Devices') and not info['HostConfig'].get('DeviceRequests')
                and env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void',
                'Actual CPU container isolation/image/normal exit differs')

    plan = actual(base / 'host-plan.json')
    require(plan['plan_sha256'] == identity({k: v for k, v in plan.items() if k != 'plan_sha256'})
            and plan['output'] == str(base) and plan['image_id'] == IMAGE and plan['gpu_uuid'] == GPU,
            'Plan identity/output/image/GPU differs')
    require(plan['expected_counts'] == {'policies': 2, 'cases': 58, 'worker_exit0_empty_groups': 116,
            'exact_host_maps': 116, 'full_mp4_decodes': 58, 'cpu_ort_cases': 60}, 'Plan counts differ')
    expected_phases = [kind + '-' + phase for kind in KINDS for phase in ('directions', 'scenes')]
    require([p['id'] for p in plan['phases']] == expected_phases, 'Four ordered phases required')
    freeze = actual(base / 'freeze-manifest.json')
    require(fp(base / 'freeze-manifest.json')['sha256'] == plan['freeze_manifest_sha256'], 'Frozen manifest differs')
    frozen_paths = set()
    for row in freeze['files']:
        relative = Path(row['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in frozen_paths, 'Unsafe/duplicate frozen path')
        frozen_paths.add(str(relative))
        retain(base / relative, row)
    for name, digest in PINS.items():
        require(retain(base / 'control' / name)['sha256'] == digest, 'Frozen control changed: ' + name)
    terminal = actual(base / 'host/launch-receipt.json')
    require(terminal['status'] == 'failed' and terminal['native_started'] is True
            and terminal['plan_sha256'] == plan['plan_sha256']
            and terminal['error'] == 'ValueError: Selected GPU has existing compute; never stop other work'
            and terminal['quality_verified'] is False, 'Original failure identity differs')
    require([p['id'] for p in terminal['phases']] == expected_phases[:3]
            and not (base / 'phases/finetune-scenes').exists(), 'Exact preserved first-three-only scope required')
    outer_root = safe(args.outer)
    outer = actual(outer_root / 'wrapper-exit.json')
    waited = actual(exit_path)
    control = actual(safe(args.control) / 'control-receipt.json')
    require(type(waited['actual_wait_returncode']) is int and waited['actual_wait_returncode'] == 1
            and waited['pending_signals'] == [] and waited['finished_utc'], 'Real e238 failure wait1 required')
    require(type(outer['actual_launcher_wait_returncode']) is int and outer['actual_launcher_wait_returncode'] == 1
            and outer['status'] == 'failed_partial_preserved' and outer['remaining_launcher_session_members'] == []
            and outer['remaining_adapter_session_members'] == [] and outer['forwarded_signals'] == []
            and outer['signal_forwarding_failures'] == [] and outer['pending_signals'] == [], 'Outer failure/empty sessions differ')
    require(control['status'] == 'failed' and control['wrapper_returncode'] == 1
            and control['error'] == {'type': 'ValueError', 'message': 'Selected GPU has existing compute; never stop other work'}
            and control['final_control_identity_verified'] is True and control['sources_unchanged'] is True
            and control['actual_original_native_receipt'] == fp(base / 'host/launch-receipt.json'), 'Actual control failure differs')
    require(outer['sources_before'] == outer['sources_after'], 'Outer sources changed')
    for row in outer['sources_before']:
        retain(row['path'], row)
    for row in outer['original_parent_receipts'].values():
        retain(row['path'], row)
    for row in outer['launcher_logs']:
        retain(row['path'], row)
    start = actual(exit_path.with_name('process-start.json'))
    require({k: v for k,v in waited.items() if k not in ('actual_wait_returncode', 'finished_utc', 'pending_signals')} == start,
            'Original e238 start/exit common bytes-fields differ')
    matrix_path = base / 'source/scripts/research/sim2sim_scene_matrix.py'
    require(retain(matrix_path)['sha256'] == MATRIX_SHA, 'Original matrix source differs')
    text = matrix_path.read_text()
    tree = ast.parse(text)
    worker_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_worker_receipts')
    namespace = {'Path': Path, 'json': json, 'math': math, 're': re, 'ROOT': base / 'source',
                 'digest': lambda p: fp(p)['sha256'], 'fingerprint': fp}
    exec(compile(ast.Module(body=[worker_fn], type_ignores=[]), str(matrix_path), 'exec'), namespace)
    validate_workers = namespace['validate_worker_receipts']  # Exact original function AST; no module entrypoint/imports.
    videos, mappings, case_count = [], set(), 0
    for stage, expected in zip(terminal['phases'], plan['phases']):
        count = 12 if expected['phase'] == 'directions' else 17
        require(expected['cases'] == count and expected['ticks'] == (400 if count == 12 else 500), 'Phase scope changed')
        require(stage['status'] == 'completed' and all(type(stage[k]) is int and stage[k] == 0 for k in
                ('driver_returncode', 'observer_returncode', 'driver_returncode_after_stop'))
                and stage['owned_gpu_container_stop']['running_after_stop'] is False
                and stage['worker_exit0_empty_groups'] == 2 * count and len(stage['host_maps']) == 2 * count
                and stage['full_decoded_mp4_count'] == count, 'Actual phase/direct waits/cleanup/counts differ')
        phase_root = base / 'phases' / expected['id']
        post_path = phase_root / 'cpu-final/summary.json'
        require(retain(post_path) == stage['cpu_final'], 'CPU summary fingerprint differs')
        post = read(post_path)
        require(post['status'] == 'passed' and post['case_count'] == count and len(post['cases']) == count
                and post['worker_exit0_empty_groups'] == 2 * count and post['full_decoded_mp4_count'] == count,
                'CPU phase was not complete')
        cpu_launch = actual(phase_root / 'cpu-final/launch.json')
        require(cpu_launch['status'] == 'passed' and cpu_launch['mode'] == 'finalize'
                and cpu_launch['returncode'] == cpu_launch['container_exit_code'] == 0
                and cpu_launch['owned_container_stop']['running_after_stop'] is False, 'CPU finalizer actual wait absent')
        cpu_inspect(phase_root / 'cpu-final/container-inspect.json', cpu_launch['container_id'])
        observer = actual(phase_root / 'observer/summary.json')
        info = actual(phase_root / 'container-inspect.json')
        require(observer['identity']['container_id'] == stage['container_id'] == info['Id']
                and observer['identity']['image_id'] == IMAGE == info['Image']
                and observer['identity']['started_at'] == info['State']['StartedAt']
                and observer['stop_reason'] == 'stop_file' and observer['mapping_scope_complete'] and observer['errors'] == [],
                'Observer scope/container birth differs')
        native_plan = actual(base / 'inputs' / expected['kind'] / (expected['phase'] + '-plan.json'))
        require(native_plan['plan_sha256'] == expected['native_plan_sha256'] and fp(base / 'inputs' / expected['kind'] /
                (expected['phase'] + '-plan.json'))['sha256'] == expected['native_plan_file_sha256'], 'Native phase plan changed')

        def translate(value):
            path = Path(value)
            for prefix, target in ((Path('/outputs'), phase_root / 'outputs'), (Path('/workspace/php_parkour'), base / 'source'),
                                   (Path('/data'), base / 'inputs' / expected['kind']), (Path('/control'), base / 'control')):
                if path.is_relative_to(prefix):
                    return str(target / path.relative_to(prefix))
            return str(path)

        require([x['case_id'] for x in post['cases']] == [x['case_id'] for x in native_plan['selections']], 'Case order differs')
        for case in post['cases']:
            require(case['worker_exit0_empty_groups'] == 2 and case['ticks'] == expected['ticks']
                    and case['quality_verified'] is False and len(case['video_full_decodes']) == 1, 'Per-case CPU gate differs')
            directory = safe(translate(case['output']))
            for row in case['files']:
                retain(translate(row['path']), row)
            result = actual(directory / 'result.json')
            require(fp(directory / 'result.json')['sha256'] == case['native_result_sha256']
                    and result['status'] == 'completed' and result['inference']['ticks'] == expected['ticks']
                    and result['inference']['control_period_simulation_seconds'] == .02
                    and result['config']['model_sha256'] == native_plan['model_sha256']
                    and result['config']['wall_timeout'] == expected['native_wall_timeout_seconds']
                    and result['config']['startup_timeout'] == 180.0 and result['quality_verified'] is False,
                    'Actual result/model/ticks/default timing differs')
            receipts = validate_workers(directory, native_plan, result, translate)
            require(len(receipts) == 3, 'Three original worker receipt files required')
            for row in receipts:
                retain(row['path'], row)
            for role in ('simulator', 'inference'):
                entry_path = directory / (role + '-process-start.json')
                native = actual(entry_path)['process']
                found = [m for m in stage['host_maps'] if m['case_id'] == case['case_id'] and m['role'] == role]
                require(len(found) == 1, 'Missing/duplicate terminal host map')
                saved = found[0]
                m = saved['mapping']
                require(saved['phase'] == stage['id'] and saved['entry_sha256'] == fp(entry_path)['sha256']
                        and m in observer['command_writer_mappings'] and m['worker_output'] == case['output']
                        and m['container_tgid'] == native['pid'] and m['owner_start_time_clock_ticks'] == native['start_time_clock_ticks']
                        and m['nspid'] == [m['host_tid'], m['container_tid']] and m['nstgid'] == [m['host_tgid'], native['pid']],
                        'Actual command_writer host namespace/birth mapping differs')
                key = (m['host_tid'], m['start_time_clock_ticks'])
                require(key not in mappings, 'Duplicate host writer birth identity')
                mappings.add(key)
            decode = case['video_full_decodes'][0]
            video = safe(directory / decode['file'])
            require(video.is_relative_to(directory) and decode['full_decode'] is True and decode['returncode'] == 0
                    and decode['command'] == ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads', '1',
                        '-i', str(Path(case['output']) / decode['file']), '-f', 'null', '-'], 'Original CPU full decode receipt differs')
            retain(video, decode)
            videos.append(video)
            with (directory / 'trajectory.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            require(rows and all(math.isfinite(float(v)) for r in rows for v in r.values()), 'Nonfinite/missing trajectory')
            active = [r for r in rows if float(r['policy_seconds']) >= 0]
            require(len(active) >= expected['ticks'] and all(float(r['gantry_enabled']) == 0 for r in active), 'Unsupported trajectory coverage absent')
            case_count += 1

    require(case_count == len(videos) == 41 and len(mappings) == 82, 'Failed partial exact41/82 counts differ')
    stopped = []
    for stage in terminal['phases']:
        cid = stage['container_id']
        argv = ['docker', 'container', 'inspect', cid]
        name = stage['id']
        out, err = output.parent / (name + '.inspect.stdout.raw'), output.parent / (name + '.inspect.stderr.raw')
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        with out.open('xb') as stdout, err.open('xb') as stderr:
            child = subprocess.Popen(argv, stdout=stdout, stderr=stderr)
            code = child.wait()
        receipt = {'argv': argv, 'actual_wait_returncode': code, 'started_utc': started,
                   'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'child_pid': child.pid,
                   'stdout': retain(out), 'stderr': retain(err)}
        receipt_path = output.parent / (name + '.inspect.execution.json')
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        retain(receipt_path)
        require(type(code) is int and code == 0, 'Actual readonly inspect failed')
        values = json.loads(out.read_bytes())
        require(isinstance(values,list) and len(values) == 1, 'Exact single inspect required')
        current = values[0]
        archived = actual(base / 'phases' / name / 'container-inspect.json')
        stopped_state = stage['owned_gpu_container_stop']['state']
        require(current['Id'] == archived['Id'] == cid and current['Image'] == archived['Image'] == IMAGE
                and current['State']['StartedAt'] == archived['State']['StartedAt'] == stopped_state['StartedAt']
                and current['Config'] == archived['Config'] and current['HostConfig'] == archived['HostConfig']
                and sorted(current['Mounts'], key=lambda m: m['Destination']) == sorted(archived['Mounts'], key=lambda m: m['Destination'])
                and current['State']['Running'] is False and current['State']['Pid'] == 0
                and current['State']['OOMKilled'] is False and current['State']['Error'] == ''
                and current['State']['ExitCode'] == stopped_state['ExitCode'] == 143,
                'Exact stopped original GPU sleep-container generation differs')
        stopped.append({'phase': name, 'container_id': cid, 'current_state': current['State'], 'execution': receipt})
    session_ids = [outer['launcher_process']['sid'], start['pid']]
    sessions = {str(sid): [] for sid in session_ids}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            raw = (path / 'stat').read_text()
            fields = raw[raw.rfind(')')+2:].split()
            sid = int(fields[3])
            if sid in session_ids:
                sessions[str(sid)].append({'pid': int(path.name), 'stat': raw})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    require(all(not members for members in sessions.values()), 'Owned old sessions have live members')
    for row in list(evidence.values()):
        require(fp(row['path']) == row, 'Actual failed evidence changed during audit')
    report = {'schema_version': 1, 'status': 'passed_readonly_preserved_failed41_partial_audit', 'must_fix': [],
              'reviewed_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'review_source': review_source,
              'scope': 'Preserved failed original cohort; no58 admission, rerun, physics or fresh media decode.',
              'actual_native_status': terminal['status'], 'actual_parent_wait_returncode': 1,
              'actual_outer_launcher_wait_returncode': 1, 'actual_control_returncode': 1,
              'failed_before_phase': 'finetune-scenes', 'exact_original_error': terminal['error'],
              'instantaneous_rejected_gpu_query_available': False,
              'rejection_attribution': 'Undetermined: original failing gpu_idle query was not persisted; later idle is a separate observation.',
              'completed_cases': case_count, 'worker_exit0_empty_groups': len(mappings),
              'original_cpu_full_decodes_verified': len(videos), 'fresh_full_decodes_performed': 0,
              'stopped_gpu_container_exit_code': 143, 'stopped_gpu_containers': stopped,
              'owned_sessions_current_members': sessions, 'evidence_fingerprints': list(evidence.values()),
              'quality_verified': False, 'course_completion_claimed': False}
    output.write_text(json.dumps(report, indent=2) + '\n')
    return fp(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('base', 'parent-exit', 'outer', 'control', 'output'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    output = safe(args.output)
    require(not output.parent.exists(), 'Fresh audit directory required')
    output.parent.mkdir(parents=True)
    result = verify(args)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
