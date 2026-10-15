#!/usr/bin/env python3
"""Container-only canonical12 original commands. No retries; isolated new evidence only."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/workspace/php_parkour')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def load_matrix():
    spec = importlib.util.spec_from_file_location('frozen_scene_matrix', ROOT / 'scripts/research/sim2sim_scene_matrix.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_plan(plan, matrix):
    original=dict(plan);recorded=original.pop('plan_sha256')
    if matrix.identity(original)!=recorded:raise ValueError('Native plan identity changed')
    if (plan.get('schema_version')!=3 or plan.get('pilot_scope')!='SDK018 canonical12 original plane commands; each once'
            or plan.get('seconds_per_configuration')!=8.0 or plan.get('seed')!=42 or plan.get('python_faulthandler') is not True
            or len(plan.get('selections',[]))!=12 or [c['command'] for c in plan['selections']]!=list(range(12))
            or len({c['case_id'] for c in plan['selections']})!=12):raise ValueError('Not the exact original12 commands/400ticks/seed42')
    for item in plan['control_files']:
        if sha(item['path'])!=item['sha256']:raise ValueError('Frozen command control changed')
    for code,case in enumerate(plan['selections']):
        argv=case['launch'];expected=case['expected_config']
        if (case['mesh'] is not None or case['mesh_sha256'] is not None or case['source_files']!=[]
                or case['output']!=f'/outputs/commands/command-{code:02d}' or '--python-faulthandler' not in argv
                or '--wall-timeout' in argv or argv[argv.index('--commands')+1]!=str(code)
                or argv[argv.index('--seconds-per-command')+1]!='8.0' or argv[argv.index('--seed')+1]!='42'
                or argv[argv.index('--terrain')+1]!='plane' or argv[argv.index('--startup-timeout')+1]!='180.0'
                or argv[argv.index('--settle-seconds')+1]!='3.0' or argv[argv.index('--ort-threads')+1]!='1'
                or expected['wall_timeout']!=373.0):raise ValueError('Native command/default timing/output differs from original baseline')
        matrix.verify_inputs(plan,case)



def sdk_receipt(executable):
    # Import/metadata only. Never constructs a Robot or DDS participant.
    result = subprocess.run([executable, '/control/sdk_actual_probe.py'],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'SDK metadata import failed: {result.stderr}')
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if value['version'] != '0.1.8':
        raise ValueError('Both native workers must use SDK0.1.8')
    return value


def decode_videos(directory, result):
    checks = []
    for relative in result['videos']:
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file() or path.is_symlink():
            raise ValueError('Unsafe or missing video')
        before = sha(path)
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads','1','-i', str(path), '-f', 'null', '-']
        decoded = subprocess.run(command, capture_output=True, text=True, timeout=120)
        report = {'file': relative, 'bytes': path.stat().st_size, 'sha256': before,
                  'command': command, 'returncode': decoded.returncode,
                  'stderr': decoded.stderr, 'full_decode': decoded.returncode == 0}
        checks.append(report)
        if decoded.returncode or before != sha(path):
            raise ValueError(f'Full MP4 decode or immutable hash failed: {relative}')
    if not checks:
        raise ValueError('No videos to decode')
    return checks


def execute(plan, matrix, output):
    if output.exists():
        raise ValueError('Pilot summary already exists; no retries or overwrites')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'status': 'running', 'started_unix': time.time(),
              'native_plan_sha256': plan['plan_sha256'], 'image_id': plan['image_id'],
              'scope': plan['pilot_scope'], 'quality_verified': False,
              'obstacle_course_completion_verified': False, 'cases': []}
    save(output, report)
    try:
        verify_plan(plan, matrix)
        if matrix.running_children():
            raise ValueError('Existing native child in this private container')
        report['sdk'] = {role: sdk_receipt(executable) for role, executable in plan['worker_interpreters'].items()}
        for role,expected in plan['expected_sdk_extension_sha256'].items():
            if report['sdk'][role]['sha256']!=expected:raise ValueError('Actual native SDK extension differs from CPU gate')
        save(output, report)
        for selection in plan['selections']:
            verify_plan(plan,matrix)
            matrix.verify_inputs(plan, selection)
            if matrix.running_children():
                raise ValueError('Prior native child remains; refusing subsequent DDS job')
            directory = Path(selection['output'])
            if directory.exists():
                raise ValueError('Fresh case directory required; never overwrite a historical or attempted case')
            log = output.parent / (directory.name + '.parent.log')
            case = {'case_id': selection['case_id'], 'output': str(directory), 'launch': selection['launch'],
                    'status': 'running', 'started_unix': time.time(), 'log': str(log)}
            report['cases'].append(case)
            save(output, report)
            with log.open('x') as stream:
                # Native harness owns timeout and complete worker-group cleanup.
                process = subprocess.Popen(selection['launch'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                case['parent_pid'] = process.pid
                save(output, report)
                case['returncode'] = process.wait()
            case['finished_unix'] = time.time()
            case['log_sha256'] = sha(log)
            if matrix.running_children():
                case['status'] = 'unreaped_native_failure'
                save(output, report)
                raise RuntimeError('Native processes remain after parent; stop pilot without starting another case')
            try:
                if case['returncode']:
                    raise RuntimeError('Native parent returned nonzero; preserved all raw evidence')
                result = matrix.validate_result(directory / 'result.json', plan, selection)
                if result['config']!=selection['expected_config']:raise ValueError('New native config differs from original12 baseline apart from fatal diagnostics')
                case['worker_receipts'] = matrix.validate_worker_receipts(directory, plan, result)
                case['video_full_decodes'] = decode_videos(directory, result)
                case['result_sha256'] = sha(directory / 'result.json')
                case['policy_ticks'] = result['inference']['ticks']
                case['policy_simulation_seconds'] = result['simulation']['policy_simulation_seconds']
                case['survival_passed'] = result['survival_passed']
                case['status'] = 'completed'
            except Exception as error:
                case.update(status='failed', error=f'{type(error).__name__}: {error}')
            save(output, report)
            # A cleanly reaped failed attempt stays failed; remaining exact cases
            # may each run once. Unknown/reused/live groups are never continued.
            receipt_path = directory / 'worker-processes.json'
            if case['status'] != 'completed':
                receipt = json.loads(receipt_path.read_text())
                final = receipt['events'][-1]
                workers = final.get('workers', [])
                if (final.get('event') != 'finally_wait_complete' or final.get('unreaped_roles') != []
                        or final.get('cleanup_errors') != [] or len(workers) != 2
                        or any(w.get('process_group', {}).get('live_members') != []
                               or w.get('process_group', {}).get('ownership_verified') is not True for w in workers)):
                    raise RuntimeError('Failed attempt lacks verified empty worker groups; no next DDS job')
        report['status'] = 'completed' if all(c['status'] == 'completed' for c in report['cases']) else 'failed'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_unix'] = time.time()
        report['remaining_native_pids'] = matrix.running_children()
        if report['remaining_native_pids']:
            report['status'] = 'failed'
        save(output, report)
    return 0 if report['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--summary', type=Path, default=Path('/outputs/pilot-summary.json'))
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or os.environ.get('PHP_DOCKER') != '1':
        raise SystemExit('Only the independently isolated Docker pilot may execute this helper')
    matrix = load_matrix()
    plan = json.loads(args.plan.read_text())
    with matrix.GLOBAL_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(plan, matrix, args.summary)


if __name__ == '__main__':
    raise SystemExit(main())
