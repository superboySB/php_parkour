#!/usr/bin/env python3
"""Prepare or explicitly execute one isolated SDK018 five-case native pilot.

`prepare` only reads/copies/checks local files. `run` is a separate, explicitly
root-authorized operation. Never operates on an existing container or old cohort.
"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:caf61487b69ce478980b3bf9df38a7f1fcaaae4b109d971dfbea10b09bf441aa'
NATIVE_ROOT = Path('/workspace/php_parkour')
EXPECTED_IDS = (
    'low_speed_step:0041:right_45_walk1.5s_step0s',
    'low_speed_climb_58:0022:left_90_walk2.0s_plat0s',
    'low_speed_climb_58:0031:right_45_walk2.0s_plat1.2s',
    'high_speed_climb_58:0000:run_forward_0.6s_step0.1s',
    'high_speed_climb_58:0023:run_left_90_1.5s_step1.0s')
MODELS = {'depth_backbone.onnx': '5b22466a218944e3b0ab0f4f82a910e3eec35375ee03e7fb94eb65fa88431b56',
          'student.onnx': 'e426c4206181d511b838c76efc48e43636299b76cb5a15183977011589931628'}
EXPECTED_EXTENSIONS = {'simulator': '9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926',
                       'inference': 'fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4'}
HELPERS = {'pilot_executor.py': 'scripts/research/sdk018_pilot_executor.py',
           'sdk_actual_probe.py': 'scripts/research/sdk018_actual_probe.py'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def run(*argv, timeout=30):
    result = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} {argv[1] if len(argv)>1 else ""} returned {result.returncode}: {result.stderr}')
    return result.stdout


def load_module(path):
    spec = importlib.util.spec_from_file_location('pilot_frozen_module', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def canonical_source(value, workspace):
    path = Path(value)
    if path.is_relative_to(NATIVE_ROOT):
        result = workspace / path.relative_to(NATIVE_ROOT)
    elif path.is_relative_to('/outputs'):
        result = workspace / 'outputs/research' / path.relative_to('/outputs')
    else:
        raise ValueError(f'Unexpected noncanonical source: {path}')
    resolved = result.resolve(strict=True)
    if not resolved.is_relative_to(workspace.resolve()) or result.is_symlink() or not result.is_file():
        raise ValueError('Source escapes workspace or is not a regular file')
    return resolved


def copy_checked(source, target, expected=None):
    source = Path(source).resolve(strict=True)
    before = sha(source)
    if expected is not None and before != expected:
        raise ValueError(f'Input SHA changed: {source}')
    if target.exists():
        raise ValueError(f'Duplicate snapshot destination: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha(target) != before or sha(source) != before:
        raise ValueError('Input changed while copying snapshot')
    # Source/input mounts are also Docker read-only. Keep raw file modes simple.
    target.chmod(0o444)
    return {'sha256': before, 'bytes': target.stat().st_size}


def validate_historical(cases):
    if tuple(case['case_id'] for case in cases) != EXPECTED_IDS:
        raise ValueError('Require exact five historical case identities and fixed order')
    for case in cases:
        triple = case['source_files']
        if (len(triple) != 3 or len({item['path'] for item in triple}) != 3
                or {Path(item['path']).suffix for item in triple} != {'.npz', '.npy', '.obj'}
                or case['original_parent_returncode'] != 1
                or case['command'] != (1 if case['scenario'].startswith('low_speed_') else 6)
                or len([i for i in triple if i['path'] == case['mesh'] and i['sha256'] == case['mesh_sha256']]) != 1):
            raise ValueError('Historical case identity, command, source triple or mesh differs')


def prepare(args):
    workspace, base = args.workspace.resolve(strict=True), args.output.resolve()
    if not re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', args.gpu_uuid):
        raise ValueError('Require an explicit full physical GPU UUID; no GPU indices')
    if base.exists():
        raise ValueError('Fresh cohort output required; no overwrite/resume of old attempts')
    if not base.is_relative_to(workspace / 'outputs/research'):
        raise ValueError('Pilot output must be an owned ignored local research directory')
    if sha(workspace / 'scripts/research/sim2sim.py') != args.harness_sha256:
        raise ValueError('Root-reviewed supervisor SHA differs')
    if sha(workspace / 'scripts/research/sim2sim_scene_matrix.py') != args.matrix_sha256:
        raise ValueError('Root-reviewed schema3 validator SHA differs')
    historical = json.loads(args.cases.read_text())
    validate_historical(historical['cases'])
    matrix_path = workspace / 'outputs/research/motion-matching/matrix.json'
    source_matrix = json.loads(matrix_path.read_text())
    selected = {case['case_id']: case for case in load_module(workspace / 'scripts/research/sim2sim_scene_matrix.py').select(source_matrix, True)}
    for case in historical['cases']:
        current = selected[case['case_id']]
        if any(current[key] != case[key] for key in ('scenario', 'configuration_index', 'configuration', 'command', 'mesh', 'mesh_sha256', 'source_files')):
            raise ValueError('Historical identity differs from complete source matrix')
    closure = load_module(workspace / 'scripts/research/sim2sim_scene_matrix.py').dependencies()
    # Python imports parent package initializers even when the AST names only a
    # leaf module. Preserve them instead of turning regular packages into namespaces.
    included = {item['path'] for item in closure}
    for item in list(closure):
        for parent in Path(item['path']).parents:
            if parent == workspace or not parent.is_relative_to(workspace):
                break
            initializer = parent / '__init__.py'
            if initializer.is_file() and str(initializer) not in included:
                closure.append({'path': str(initializer), 'sha256': sha(initializer), 'bytes': initializer.stat().st_size})
                included.add(str(initializer))
    # Make any partially copied preparation recognizable; never silently replace.
    base.mkdir(parents=True, exist_ok=False)
    for directory in ('source', 'inputs', 'outputs', 'cache', 'host'):
        (base / directory).mkdir()
    write(base / 'preparation-status.json', {'status': 'preparing', 'native_started': False})
    files, dependencies = [], []
    for item in closure:
        source = Path(item['path']).resolve(strict=True)
        if not source.is_relative_to(workspace):
            raise ValueError('Execution dependency escapes workspace')
        relative = source.relative_to(workspace)
        native = str(NATIVE_ROOT / relative)
        record = copy_checked(source, base / 'source' / relative, item['sha256'])
        files.append({'relative': str(Path('source') / relative), **record})
        dependencies.append({'path': native, **record})
    for filename, relative in HELPERS.items():
        record = copy_checked(HERE / filename, base / 'source' / relative)
        files.append({'relative': str(Path('source') / relative), **record})
        dependencies.append({'path': str(NATIVE_ROOT / relative), **record})
    for filename in ('sdk018_native_pilot.py', 'observe_container_pids.py'):
        record = copy_checked(HERE / filename, base / 'host' / filename)
        files.append({'relative': 'host/' + filename, **record})
    for case in historical['cases']:
        for item in case['source_files']:
            relative = Path(item['path']).relative_to(NATIVE_ROOT)
            record = copy_checked(canonical_source(item['path'], workspace), base / 'source' / relative, item['sha256'])
            if record['bytes'] != item.get('size', item.get('bytes')):
                raise ValueError('Generated source size differs')
            files.append({'relative': str(Path('source') / relative), **record})
    matrix_record = copy_checked(matrix_path, base / 'inputs/matrix.json')
    files.append({'relative': 'inputs/matrix.json', **matrix_record})
    model_records = []
    for filename, expected in MODELS.items():
        target = Path('assets/student') / filename
        record = copy_checked(workspace / 'outputs/research/assets/student' / filename, base / 'inputs' / target, expected)
        files.append({'relative': str(Path('inputs') / target), **record})
        model_records.append({'path': str(Path('/data') / target), **record})
    selections = []
    for case in historical['cases']:
        output = '/outputs/cases/' + case['scenario'] + '-' + f"{case['configuration_index']:04d}-" + identity(case['case_id'])[:12]
        command = ['/opt/php/bin/inference-python', str(NATIVE_ROOT / 'scripts/research/sim2sim.py'),
                   '--models', '/data/assets/student', '--terrain', 'custom', '--mesh', case['mesh'],
                   '--commands', str(case['command']), '--seconds-per-command', '10.0', '--seed', '42', '--gl', 'egl',
                   '--wall-timeout', '120', '--startup-timeout', '90',
                   '--python-faulthandler', '--sim-python', '/opt/php/bin/train-python',
                   '--inference-python', '/opt/php/bin/inference-python', '--output', output]
        selections.append(dict(case, output=output, launch=command))
    harness = next(item for item in dependencies if item['path'] == str(NATIVE_ROOT / 'scripts/research/sim2sim.py'))
    native_plan = {'schema_version': 3, 'pilot_scope': 'SDK018 five historical failures; each once', 'image_id': IMAGE,
                   'seed': 42, 'seconds_per_configuration': 10.0, 'python_faulthandler': True,
                   'source_matrix_record': dict(matrix_record, path='/data/matrix.json'),
                   'source_matrix_sha256': matrix_record['sha256'], 'models': model_records,
                   'model_sha256': MODELS, 'dependencies': sorted(dependencies, key=lambda item: item['path']),
                   'worker_harness_record': harness,
                   'worker_interpreters': {'simulator': '/opt/php/bin/train-python', 'inference': '/opt/php/bin/inference-python'},
                   'selections': selections, 'quality_verified': False, 'obstacle_course_completion_verified': False}
    native_plan['plan_sha256'] = identity(native_plan)
    write(base / 'inputs/native-plan.json', native_plan)
    files.append({'relative': 'inputs/native-plan.json', 'sha256': sha(base / 'inputs/native-plan.json'), 'bytes': (base / 'inputs/native-plan.json').stat().st_size})
    mounts = [{'source': str(base / 'source'), 'destination': str(NATIVE_ROOT), 'readonly': True},
              {'source': str(base / 'inputs'), 'destination': '/data', 'readonly': True},
              {'source': str(base / 'outputs'), 'destination': '/outputs', 'readonly': False},
              {'source': str(base / 'cache'), 'destination': '/data/cache', 'readonly': False}]
    plan = {'schema_version': 1, 'status': 'prepared_only', 'native_started': False, 'cohort': base.name,
            'image_id': IMAGE, 'gpu_uuid': args.gpu_uuid, 'workspace': str(workspace), 'output': str(base),
            'container_name': 'php-sdk018-pilot-' + identity(str(base))[:16], 'historical_case_source_sha256': sha(args.cases),
            'historical_source_plan_sha256': historical['source_plan'], 'native_plan_sha256': native_plan['plan_sha256'],
            'snapshot_files': sorted(files, key=lambda item: item['relative']), 'mounts': mounts,
            'expected_sdk_extension_sha256': EXPECTED_EXTENSIONS,
            'isolation': {'network': 'none', 'ipc': 'private', 'pid': 'private', 'init': True, 'shm_bytes': 8589934592},
            'scope': 'Five exact historical failed geometries, once each; 500 policy ticks/10 simulation seconds. SDK lifecycle pilot, not full629 or skill-success evidence.'}
    plan['plan_sha256'] = identity(plan)
    write(base / 'pilot-plan.json', plan)
    write(base / 'preparation-status.json', {'status': 'prepared_only', 'native_started': False, 'plan_sha256': plan['plan_sha256']})
    print(json.dumps({'status': 'prepared_only', 'plan': str(base / 'pilot-plan.json'), 'native_started': False,
                      'snapshot_files': len(files), 'native_plan_sha256': native_plan['plan_sha256']}))


def verify_snapshot(base, plan):
    original = dict(plan)
    recorded = original.pop('plan_sha256')
    if identity(original) != recorded or str(base.resolve()) != plan['output'] or plan['image_id'] != IMAGE:
        raise ValueError('Pilot identity/path/image changed')
    if plan.get('native_started') is not False or plan.get('status') != 'prepared_only':
        raise ValueError('Only an untouched prepared cohort may start once')
    for item in plan['snapshot_files']:
        path = base / item['relative']
        if (not path.resolve().is_relative_to(base.resolve()) or path.is_symlink() or not path.is_file()
                or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']):
            raise ValueError('Snapshot artifact changed: ' + item['relative'])
    return plan


def local_docker():
    context = run('docker', 'context', 'show').strip()
    info = json.loads(run('docker', 'context', 'inspect', context))[0]
    endpoint = os.environ.get('DOCKER_HOST') or info['Endpoints']['docker']['Host']
    if not endpoint.startswith('unix://'):
        raise ValueError('Only a local Unix Docker endpoint is permitted')
    return {'context': context, 'endpoint': endpoint}


def gpu_idle(uuid):
    entries = run('nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader').splitlines()
    if entries.count(uuid) != 1:
        raise ValueError('Explicit physical GPU UUID is not unique/present')
    processes = run('nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits')
    if any(line.split(',')[0].strip() == uuid for line in processes.splitlines() if line.strip()):
        raise ValueError('Selected physical GPU has an existing compute job; never stop it')
    return {'selected_gpu_uuid': uuid, 'matching_compute_processes': []}


def container_arguments(plan):
    argv = ['docker', 'create', '--name', plan['container_name'], '--network', 'none', '--ipc', 'private',
            '--init', '--shm-size', '8g', '--gpus', 'device=' + plan['gpu_uuid'],
            '--workdir', str(NATIVE_ROOT), '--entrypoint', '/bin/bash']
    for key, value in {'PHP_DOCKER': '1', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true',
                       'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                       'MUJOCO_EGL_DEVICE_ID': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                       'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility,graphics'}.items():
        argv += ['--env', key + '=' + value]
    for mount in plan['mounts']:
        value = f"type=bind,src={mount['source']},dst={mount['destination']}"
        argv += ['--mount', value + (',readonly' if mount['readonly'] else '')]
    argv += [plan['image_id'], '-lc', 'exec sleep infinity']
    return argv


def verify_container(info, plan, container_id):
    host = info['HostConfig']
    requests = host.get('DeviceRequests', [])
    mounts = sorted((m['Source'], m['Destination'], not m['RW'], m['Type']) for m in info['Mounts'])
    expected = sorted((m['source'], m['destination'], m['readonly'], 'bind') for m in plan['mounts'])
    if (info['Id'] != container_id or info['Image'] != plan['image_id']
            or info['Name'] != '/' + plan['container_name'] or info['Config']['WorkingDir'] != str(NATIVE_ROOT)
            or host.get('NetworkMode') != 'none' or host.get('IpcMode') != 'private'
            or host.get('PidMode', '') != '' or host.get('Privileged') is not False
            or host.get('Init') is not True or host.get('ShmSize') != 8589934592
            or len(requests) != 1 or requests[0].get('DeviceIDs') != [plan['gpu_uuid']]
            or requests[0].get('Count') != 0 or mounts != expected):
        raise ValueError('Isolated container identity, namespaces, UUID, mounts or working directory differ')


def verify_host_mappings(observer, native_summary, base):
    if not observer.get('mapping_scope_complete') or observer.get('errors'):
        raise ValueError('Host observer failed or did not map both native roles')
    matches = []
    for case in native_summary['cases']:
        directory = base / 'outputs' / Path(case['output']).relative_to('/outputs')
        for role in ('simulator', 'inference'):
            entry = json.loads((directory / (role + '-process-start.json')).read_text())
            native = entry['process']
            found = [mapping for mapping in observer['command_writer_mappings']
                     if mapping['role'] == role and mapping['worker_output'] == case['output']
                     and mapping['container_tgid'] == native['pid']
                     and mapping['owner_start_time_clock_ticks'] == native['start_time_clock_ticks']]
            if not found:
                raise ValueError('Missing exact native PID/birth→host command_writer mapping: ' + case['case_id'] + '/' + role)
            matches.append({'case_id': case['case_id'], 'role': role, 'native_entry_sha256': sha(directory / (role + '-process-start.json')),
                            'mappings': found})
    if len(matches) != 10:
        raise ValueError('Require both native workers for all five cases')
    return matches


def execute(args):
    if not args.root_authorized_start:
        raise ValueError('Explicit root start authorization is required; prepare never starts jobs')
    base = args.plan.resolve().parent
    plan = verify_snapshot(base, json.loads(args.plan.read_text()))
    # The root lock serializes this pilot across different output directories.
    with (Path(plan['workspace']) / 'outputs/research/.sdk018-native-pilot.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = base / 'host/launch-receipt.json'
        if receipt_path.exists() or any((base / 'outputs').iterdir()):
            raise ValueError('Cohort already attempted; new output required, never retry in place')
        endpoint = local_docker()
        gpu = gpu_idle(plan['gpu_uuid'])
        actual_image = json.loads(run('docker', 'image', 'inspect', plan['image_id']))[0]
        if actual_image['Id'] != plan['image_id']:
            raise ValueError('Immutable candidate image not locally present')
        # Inspect an absent name; only create may reserve it atomically.
        existing = subprocess.run(['docker', 'inspect', '--type', 'container', plan['container_name']], capture_output=True, text=True)
        if existing.returncode == 0:
            raise ValueError('Pilot container name already exists; never replace or attach to it')
        receipt = {'schema_version': 1, 'status': 'starting', 'plan_sha256': plan['plan_sha256'],
                   'started_unix': time.time(), 'endpoint': endpoint, 'gpu_preflight': gpu,
                   'create_argv': container_arguments(plan), 'native_started': False}
        write(receipt_path, receipt)
        cid, observer, job = None, None, None
        stop_file = base / 'host/observer-stop'
        try:
            cid = run(*receipt['create_argv']).strip()
            if not re.fullmatch(r'[0-9a-f]{64}', cid):
                raise ValueError('Docker create did not return an exact full container ID')
            receipt['container_id'] = cid
            write(receipt_path, receipt)
            run('docker', 'start', cid)
            inspected = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
            verify_container(inspected, plan, cid)
            write(base / 'host/container-inspect.json', inspected)
            # A second idle check catches another job appearing during create.
            receipt['gpu_before_native'] = gpu_idle(plan['gpu_uuid'])
            observer_argv = [sys.executable, str(base / 'host/observe_container_pids.py'), '--container-id', cid,
                             '--expected-image', plan['image_id'], '--output', str(base / 'host/observer'),
                             '--stop-file', str(stop_file), '--interval', '0.2', '--max-seconds', '900']
            receipt['observer_argv'] = observer_argv
            with (base / 'host/observer.log').open('x') as observer_log:
                observer = subprocess.Popen(observer_argv, stdout=observer_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 15
                while not (base / 'host/observer/launch.json').is_file():
                    if observer.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Host observer did not become ready before native start')
                    time.sleep(.1)
                command = ['docker', 'exec', cid, '/opt/php/bin/inference-python',
                           str(NATIVE_ROOT / 'scripts/research/sdk018_pilot_executor.py'), '--plan', '/data/native-plan.json',
                           '--summary', '/outputs/pilot-summary.json']
                receipt.update(status='running', native_started=True, native_start_unix=time.time(), native_argv=command)
                write(receipt_path, receipt)
                with (base / 'host/driver.log').open('x') as stream:
                    job = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
                    receipt['docker_exec_host_pid'] = job.pid
                    write(receipt_path, receipt)
                    receipt['driver_timeout_seconds'] = 850
                    write(receipt_path, receipt)
                    receipt['driver_returncode'] = job.wait(timeout=850)
                stop_file.touch(exist_ok=False)
                receipt['observer_returncode'] = observer.wait(timeout=30)
            native = json.loads((base / 'outputs/pilot-summary.json').read_text())
            observe = json.loads((base / 'host/observer/summary.json').read_text())
            for role, expected in plan['expected_sdk_extension_sha256'].items():
                if native['sdk'][role]['sha256'] != expected or native['sdk'][role]['version'] != '0.1.8':
                    raise ValueError('Actual native SDK extension differs from CPU-verified SDK018 candidate')
            receipt['host_native_mappings'] = verify_host_mappings(observe, native, base)
            if (receipt['driver_returncode'] != 0 or receipt['observer_returncode'] != 0 or native['status'] != 'completed'
                    or len(native['cases']) != 5 or native['remaining_native_pids'] != []
                    or any(case['status'] != 'completed' or case['policy_ticks'] != 500 for case in native['cases'])):
                raise RuntimeError('Pilot did not pass all five cases with clean native exits and 500 ticks')
            receipt.update(status='completed', native_summary_sha256=sha(base / 'outputs/pilot-summary.json'),
                           observer_summary_sha256=sha(base / 'host/observer/summary.json'))
        except BaseException as error:
            receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            # Stop only the newly created fixed ID owned by this receipt. Keep
            # the stopped container and every raw output for root review.
            if observer is not None and observer.poll() is None:
                stop_file.touch(exist_ok=True)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    receipt['observer_returncode'] = observer.wait(timeout=30)
            if cid is not None:
                try:
                    info = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
                    verify_container(info, plan, cid)
                    receipt['owned_container_stop'] = run('docker', 'stop', '--time', '20', cid, timeout=35).strip()
                    info = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
                    receipt['owned_container_running_after_stop'] = info['State']['Running']
                    if info['State']['Running']:
                        receipt['status'] = 'failed'
                    write(base / 'host/container-final-inspect.json', info)
                except BaseException as error:
                    receipt.update(status='failed', cleanup_error=f'{type(error).__name__}: {error}')
            if job is not None:
                try:
                    receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # This is our own local Docker CLI Popen, after its fixed
                    # owned container has been stopped; no other job is signalled.
                    job.terminate()
                    try:
                        receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        job.kill()
                        receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                    receipt.update(status='failed', cleanup_driver_cli_terminated=True)
            receipt['finished_unix'] = time.time()
            write(receipt_path, receipt)
        return 0 if receipt['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    plan = sub.add_parser('prepare')
    plan.add_argument('--workspace', type=Path, required=True)
    plan.add_argument('--cases', type=Path, required=True)
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--gpu-uuid', required=True)
    plan.add_argument('--harness-sha256', required=True)
    plan.add_argument('--matrix-sha256', required=True)
    start = sub.add_parser('run')
    start.add_argument('--plan', type=Path, required=True)
    start.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    return prepare(args) if args.action == 'prepare' else execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
