#!/usr/bin/env python3
"""Prepare only by default. Explicit `run` creates one isolated native GUI attempt.

Host uses the standard library and existing docker/Xephyr/xauth/xprop tools.
No existing container, display, auth file, source checkout or process is changed.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import traceback
from common import HARNESS_SHA, birth_group, cleanup_group, fingerprint, identity, load, sha, verify_files, write

IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
SUPERVISOR = 'scripts/research/sim2sim.py'
OBSERVER_RELATIVE = 'outputs/research/sdk018-native-pilot-20261010T0915/host/observe_container_pids.py'
HELPERS = ('common.py', 'container_runner.py', 'observe_native.py', 'x11_owned.py', 'check_recordings.py',
           'cpu_preflight.py', 'host_observer.py', 'host_runner.py', 'private_x11_probe.py')


def command(argv, **kwargs):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=kwargs.pop('timeout', 30), **kwargs)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {argv[0:3]!r}: {result.stderr}')
    return result.stdout


def endpoint():
    name = command(['docker', 'context', 'show']).strip()
    config = json.loads(command(['docker', 'context', 'inspect', name]))[0]
    actual = os.environ.get('DOCKER_HOST') or config['Endpoints']['docker']['Host']
    if actual != 'unix:///var/run/docker.sock':
        raise ValueError('Only reviewed local Docker socket is allowed')
    return {'context': name, 'endpoint': actual}


def records(base, exclude=()):
    result = []
    for path in sorted(base.rglob('*')):
        relative = path.relative_to(base).as_posix()
        if any(relative == value or relative.startswith(value + '/') for value in exclude):
            continue
        if path.is_symlink():
            raise ValueError('Symlink is not allowed in frozen GUI cohort')
        if path.is_file():
            result.append({'relative': path.relative_to(base).as_posix(), **fingerprint(path)})
    return result


def verify_host_mappings(destination):
    entries = {role: json.loads((destination / 'outputs' / role / 'process-entry.json').read_text())
               for role in ('simulator', 'inference')}
    found = {role: [] for role in entries}
    for line in (destination / 'host/observer/snapshots.jsonl').read_text().splitlines():
        event = json.loads(line)
        for process in event['processes']:
            for role, entry in entries.items():
                native = entry['process']
                if (process['container_pid'] == native['pid'] and process['start_time_clock_ticks'] == native['start_time_clock_ticks']
                        and process['command_writer_threads']):
                    found[role].append({'unix': event['unix'], 'host_pid': process['host_pid'], 'container_pid': native['pid'],
                        'start_time_clock_ticks': native['start_time_clock_ticks'], 'nspid': process['nspid'],
                        'command_writer_threads': process['command_writer_threads']})
    if not all(found.values()):
        raise RuntimeError('Exact native host/container birth + SDK thread observation missing')
    return {role: {'samples': len(values), 'first': values[0], 'last': values[-1],
                   'raw_entry': fingerprint(destination / 'outputs' / role / 'process-entry.json')} for role, values in found.items()}


def display_number(value):
    if not re.fullmatch(r':[0-9]+', value) or not 50 <= int(value[1:]) <= 999:
        raise ValueError('Require an explicitly private display :50..:999')
    return int(value[1:])


def checked_plan(path):
    plan = json.loads(path.read_text())
    content = dict(plan); digest = content.pop('plan_sha256')
    if identity(content) != digest or plan['schema_version'] != 1 or plan['image_id'] != IMAGE or plan['gpu_uuid'] != GPU:
        raise ValueError('Frozen GUI plan/expected canonical identity differs')
    if plan['owner_uid'] != os.getuid() or plan['status'] != 'prepared_not_executed':
        raise ValueError('Plan ownership/prepared status differs')
    display_number(plan['private_display'])
    if plan['cohort_root'] != str(path.parent.resolve()) or len(plan['token']) != 32:
        raise ValueError('Plan path/session identity differs')
    if plan['container_hostname'] != 'php-gui-' + plan['token']:
        raise ValueError('Private authority hostname is not bound to the unique session')
    verify_files(path.parent, plan['files'])
    # The operator host script and helpers must be the reviewed prepared bytes.
    for name, expected in plan['operator_helpers'].items():
        if fingerprint(Path(__file__).parent / name) != expected:
            raise ValueError('Operator helper changed since prepare: ' + name)
    return plan


def prepare(args):
    source = args.source.resolve(strict=True)
    project = args.project.resolve(strict=True)
    destination = args.destination.resolve()
    display_number(args.display)
    if args.image != IMAGE:
        raise ValueError('This reviewed runner requires the exact new canonical image')
    if source == project or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Use separate immutable build context and fresh destination')
    context_endpoint = endpoint()
    image = json.loads(command(['docker', 'image', 'inspect', args.image]))[0]
    if image['Id'] != IMAGE or sha(source / SUPERVISOR) != HARNESS_SHA:
        raise ValueError('Canonical image/supervisor differs')
    destination.mkdir(parents=True, exist_ok=False)
    cohort = destination / 'cohort'; cohort.mkdir()
    frozen = cohort / 'source'
    shutil.copytree(source, frozen)
    before = records(frozen)
    helpers = frozen / 'scripts/research/gui_audit'; helpers.mkdir(exist_ok=False)
    for name in HELPERS:
        shutil.copy2(Path(__file__).parent / name, helpers / name)
    observer = project / OBSERVER_RELATIVE
    shutil.copy2(observer, helpers / 'observe_container_pids.py')
    overlays = []
    entries = [('inference', 'scripts/research/run_native_policy.py', 'run_native_policy.gui-original.py'),
               ('simulator', 'thirdparty/holosoma/src/holosoma/holosoma/run_sim.py', 'run_sim.gui-original.py')]
    for role, relative, original_name in entries:
        path = frozen / relative
        original_sha = sha(path)
        original = path.with_name(original_name)
        if original.exists():
            raise ValueError('Unexpected existing diagnostic original')
        shutil.copy2(path, original)
        body = ("import sys\nfrom pathlib import Path\n"
                "sys.path.insert(0, '/workspace/php_parkour/scripts/research/gui_audit')\n"
                "from observe_native import launch\n"
                f"launch({role!r}, Path(__file__).with_name({original_name!r}), {original_sha!r})\n")
        path.write_text(body)
        overlays.append({'path': relative, 'before_sha256': original_sha, 'after_sha256': sha(path),
                         'exact_original_copy': original.relative_to(frozen).as_posix(),
                         'scope': 'Diagnostic entry shim; original main/original methods called unchanged once'})
    models = cohort / 'assets/student'; models.mkdir(parents=True)
    for name in ('depth_backbone.onnx', 'student.onnx'):
        shutil.copy2(project / 'outputs/research/assets/student' / name, models / name)
    # Empty nested mountpoints are created before their read-only parent is mounted.
    (cohort / 'cache').mkdir()
    for name in ('host', 'outputs', 'cache'):
        (destination / name).mkdir()
    write(destination / 'host/source-before.json', {'files': before, 'identity_sha256': identity(before)})
    source_after = records(frozen)
    write(destination / 'host/source-after.json', {'files': source_after, 'identity_sha256': identity(source_after), 'overlays': overlays})
    token = secrets.token_hex(16)
    plan = {'schema_version': 1, 'status': 'prepared_not_executed', 'created_unix': time.time(), 'owner_uid': os.getuid(),
            'cohort_root': str(cohort), 'token': token, 'container_hostname': 'php-gui-' + token, 'private_display': args.display,
            'parent_display': os.environ.get('DISPLAY'), 'parent_xauthority': os.environ.get('XAUTHORITY'),
            'image_id': IMAGE, 'image_rootfs': image['RootFS'], 'gpu_uuid': GPU, 'docker_endpoint': context_endpoint,
            'gpu_lock': str(project / 'outputs/research' / ('.local-native-' + GPU + '.lock')),
            'source_context': str(source), 'canonical_source_count': len(before), 'canonical_source_identity': identity(before),
            'source_after_identity': identity(source_after), 'diagnostic_overlays': overlays,
            'operator_helpers': {name: fingerprint(Path(__file__).parent / name) for name in HELPERS},
            'host_observer_sha256': sha(observer), 'files': records(cohort),
            'scope': 'One native MuJoCo plane GUI and real terminal keyboard workflow. No obstacle or robot-hardware success claim.',
            'expected_transitions': ['window8', 'window9', 'terminal]', 'held_w_code1', 'c_manual_save',
                                     'equal_speed', 'held_w_code6', 'o_damping_autosave', 'i_stiff', 'original_SIGINT_exit'],
            'receipt_contract': 'GUI schema1; never reuse matrix worker argv validator',
            'max_operator_seconds': 420}
    plan['plan_sha256'] = identity(plan)
    write(cohort / 'plan.json', plan)
    print(json.dumps({'status': plan['status'], 'plan': str(cohort / 'plan.json'), 'plan_sha256': plan['plan_sha256'],
                      'source_files': len(source_after), 'native_started': False}))


def gpu_idle():
    text = command(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name', '--format=csv,noheader,nounits'])
    values = [line.strip() for line in text.splitlines() if line.strip()]
    matches = [line for line in values if line.split(',')[0].strip() == GPU]
    if matches:
        raise RuntimeError('Selected GPU has compute processes; do not start the GUI cohort')
    return {'selected_gpu_uuid': GPU, 'matching_compute_processes': []}


def inspect_owned(cid, name, plan):
    if not re.fullmatch(r'[0-9a-f]{64}', cid):
        raise ValueError('Need full exact own container ID')
    info = json.loads(command(['docker', 'inspect', '--type', 'container', cid]))[0]
    host = info['HostConfig']
    if (info['Id'] != cid or info['Name'] != '/' + name or info['Image'] != plan['image_id']
            or info['Config']['Labels'].get('php.gui.audit.token') != plan['token']
            or host['NetworkMode'] != 'none' or host['IpcMode'] != 'private' or host.get('PidMode')
            or info['Config']['Hostname'] != plan['container_hostname']):
        raise ValueError('Exact owned private Docker identity differs; no stop/exec allowed')
    expected_source = str(Path(plan['cohort_root']) / 'source')
    mounts = {m['Destination']: m for m in info['Mounts']}
    if mounts['/workspace/php_parkour']['Source'] != expected_source or mounts['/workspace/php_parkour']['RW']:
        raise ValueError('Source bind is not the exact frozen read-only snapshot')
    return info


def auth_record(hostname, display_name, cookie):
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,63}', hostname) or len(cookie) != 16:
        raise ValueError('Invalid explicit local authority identity')
    parts = [hostname.encode(), str(display_number(display_name)).encode(), b'MIT-MAGIC-COOKIE-1', cookie]
    return struct.pack('!H', 256) + b''.join(struct.pack('!H', len(value)) + value for value in parts)


def make_authority(path, display_name, container_hostname):
    # python-xlib0.33 ignores FamilyWild; use exact FamilyLocal records for the
    # host and explicitly fixed new container hostname. Never print the cookie.
    path.touch(mode=0o600, exist_ok=False)
    os.chmod(path, 0o600)
    cookie = secrets.token_bytes(16)
    path.write_bytes(auth_record(socket.gethostname(), display_name, cookie)
                     + auth_record(container_hostname, display_name, cookie))


def create_argv(plan, destination, auth):
    cohort = Path(plan['cohort_root'])
    argv = ['docker', 'create', '--name', 'php-native-gui-' + plan['token'], '--hostname', plan['container_hostname'],
            '--label', 'php.gui.audit.token=' + plan['token'],
            '--network', 'none', '--ipc', 'private', '--init', '--shm-size', '8g', '--gpus', 'device=' + GPU,
            '--workdir', '/workspace/php_parkour', '--entrypoint', '/bin/bash']
    values = {'PHP_DOCKER': '1', 'PHP_GUI_TOKEN': plan['token'], 'DISPLAY': plan['private_display'],
              'XAUTHORITY': '/run/php-gui.xauth', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true',
              'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
              'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility,graphics', 'PYTHONDONTWRITEBYTECODE': '1',
              'MUJOCO_GL': 'egl', 'MUJOCO_EGL_DEVICE_ID': '0', 'OMP_NUM_THREADS': '1',
              'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'PYTHONFAULTHANDLER': '1'}
    for key, value in values.items():
        argv += ['--env', key + '=' + value]
    for source, target, readonly in ((cohort, '/data/cohort', True), (cohort / 'source', '/workspace/php_parkour', True),
            (cohort / 'assets/student', '/data/assets/student', True), (destination / 'outputs', '/outputs', False),
            (destination / 'cache', '/data/cache', False), (auth, '/run/php-gui.xauth', True),
            (Path('/tmp/.X11-unix') / ('X' + plan['private_display'][1:]),
             '/tmp/.X11-unix/X' + plan['private_display'][1:], True)):
        if ',' in str(source):
            raise ValueError('Unsafe comma in Docker mount source')
        argv += ['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')]
    return argv + [IMAGE, '-lc', 'exec sleep infinity']


def run(args):
    plan = checked_plan(args.plan.resolve(strict=True))
    destination = Path(plan['cohort_root']).parent
    host = destination / 'host'
    receipt_path = host / 'launch-receipt.json'
    if receipt_path.exists() or any((destination / 'outputs').iterdir()):
        raise ValueError('Never rerun/overwrite an actual attempt; prepare a fresh cohort')
    if endpoint() != plan['docker_endpoint']:
        raise ValueError('Docker endpoint differs')
    image = json.loads(command(['docker', 'image', 'inspect', IMAGE]))[0]
    if image['Id'] != IMAGE or image['RootFS'] != plan['image_rootfs']:
        raise ValueError('Canonical image rootfs identity differs')
    if not plan['parent_display'] or not Path(plan['parent_xauthority'] or '').is_file():
        raise ValueError('Prepared parent display/auth authority is unavailable')
    number = display_number(plan['private_display'])
    supervisor = load(Path(plan['cohort_root']) / 'source' / SUPERVISOR, 'gui_host_ownership')
    receipt = {'schema_version': 1, 'status': 'running', 'plan_sha256': plan['plan_sha256'], 'started_unix': time.time(),
               'native_started': False, 'scope': plan['scope'], 'cleanup': [], 'errors': []}
    cid = xephyr = xephyr_group = observer = execution = None
    observer_group = execution_group = None
    name = 'php-native-gui-' + plan['token']
    auth = host / 'private.xauth'
    with Path(plan['gpu_lock']).open('a') as gpu_lock, Path(f'/tmp/php-native-gui-display-{number}.lock').open('a') as display_lock:
        # Same cross-container lock as the new 629 sweep. Never wait while a job owns it.
        fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(display_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if Path(f'/tmp/.X11-unix/X{number}').exists() or Path(f'/tmp/.X{number}-lock').exists():
                raise ValueError('Private display is already in use; do not reuse/remove it')
            receipt['gpu_idle'] = gpu_idle()
            make_authority(auth, plan['private_display'], plan['container_hostname'])
            xenv = os.environ | {'DISPLAY': plan['parent_display'], 'XAUTHORITY': plan['parent_xauthority']}
            xargv = ['Xephyr', plan['private_display'], '-screen', '1920x1200', '-noreset', '-nolisten', 'tcp', '-auth', str(auth)]
            with (host / 'xephyr.log').open('xb') as stream:
                xephyr = subprocess.Popen(xargv, stdout=stream, stderr=subprocess.STDOUT, env=xenv, start_new_session=True)
            xephyr_group = birth_group(supervisor, xephyr)
            receipt['xephyr'] = {'argv': xargv, 'group': xephyr_group}
            write(receipt_path, receipt)
            until = time.monotonic() + 15
            while not Path(f'/tmp/.X11-unix/X{number}').is_socket():
                if xephyr.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('Owned Xephyr failed to start')
                time.sleep(.1)
            private_env = os.environ | {'DISPLAY': plan['private_display'], 'XAUTHORITY': str(auth)}
            details = command(['xdpyinfo', '-display', plan['private_display']], env=private_env)
            (host / 'private-xdpyinfo.txt').write_text(details)
            if not all(name in details for name in ('XTEST', 'RECORD', 'GLX')):
                raise RuntimeError('Owned Xephyr lacks GUI extensions')
            command(['xprop', '-display', plan['private_display'], '-root', '-f', '_PHP_GUI_AUDIT_TOKEN', '8s',
                     '-set', '_PHP_GUI_AUDIT_TOKEN', plan['token']], env=private_env)
            argv = create_argv(plan, destination, auth)
            receipt['create_argv'] = argv
            cid = command(argv).strip()
            receipt['container_id'] = cid
            info = inspect_owned(cid, name, plan)
            write(host / 'created-container.json', info)
            command(['docker', 'start', cid])
            info = inspect_owned(cid, name, plan)
            receipt['container_host_init_identity'] = supervisor.process_identity(info['State']['Pid'])
            write(receipt_path, receipt)
            # These two fresh-interpreter imports parse exact CLI but never construct
            # Robot/SDK, camera, viewer, policy or simulation objects.
            helper = '/workspace/php_parkour/scripts/research/gui_audit/'
            receipt['private_x11_probe_stdout'] = command(['docker', 'exec', cid, '/opt/php/bin/inference-python',
                helper + 'private_x11_probe.py', '--output', '/outputs/private-x11-probe.json'], timeout=30)
            for role, interpreter in (('simulator', '/opt/php/bin/train-python'), ('inference', '/opt/php/bin/inference-python')):
                preflight_argv = ['docker', 'exec', cid, interpreter, helper + 'cpu_preflight.py', '--role', role]
                result = command(preflight_argv, timeout=90)
                (host / (role + '-cpu-preflight.txt')).write_text(result)
            receipt['gpu_before_native'] = gpu_idle()
            observer_argv = [sys.executable, str(Path(__file__).with_name('host_observer.py')), '--plan', str(args.plan.resolve()),
                             '--container-id', cid, '--output', str(host / 'observer')]
            observer_log = (host / 'observer-driver.log').open('xb')
            try:
                observer = subprocess.Popen(observer_argv, stdout=observer_log, stderr=subprocess.STDOUT, start_new_session=True)
                observer_group = birth_group(supervisor, observer)
            finally:
                observer_log.close()
            # Observational readiness before spawning any native child.
            until = time.monotonic() + 10
            while not (host / 'observer/ready.json').exists():
                if observer.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('Read-only own-container host PID observer failed readiness')
                time.sleep(.1)
            native_argv = ['docker', 'exec', cid, '/opt/php/bin/inference-python', helper + 'container_runner.py',
                           '--plan', '/data/cohort/plan.json']
            receipt.update(native_driver_started=True, gui_driver_start_unix=time.time(), native_argv=native_argv)
            write(receipt_path, receipt)
            with (host / 'docker-exec.log').open('xb') as stream:
                execution = subprocess.Popen(native_argv, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                execution_group = birth_group(supervisor, execution)
            receipt['docker_exec_identity'] = supervisor.process_identity(execution.pid)
            write(receipt_path, receipt)
            receipt['docker_exec_returncode'] = execution.wait(timeout=plan['max_operator_seconds'])
            if execution.returncode:
                raise RuntimeError('Actual GUI execution returned nonzero; retained raw receipt')
            result = json.loads((destination / 'outputs/summary.json').read_text())
            if result['status'] != 'completed' or result['plan_sha256'] != plan['plan_sha256']:
                raise RuntimeError('Actual GUI terminal receipt does not match plan')
            receipt['status'] = 'completed'
        except BaseException as error:
            receipt.update(status='failed', error=str(error), traceback=traceback.format_exc())
        finally:
            # Closing diagnostic I/O must never bypass own resource cleanup.
            if observer:
                try:
                    (host / 'observer/stop').touch()
                    receipt['observer_returncode'] = observer.wait(timeout=15)
                    if observer.returncode:
                        raise RuntimeError('Own host PID observation failed')
                    if receipt['status'] == 'completed':
                        receipt['native_host_pid_mappings'] = verify_host_mappings(destination)
                except BaseException as error:
                    receipt['errors'].append('observer: ' + str(error))
                    if observer_group:
                        try:
                            receipt['observer_final_group'] = cleanup_group(supervisor, observer, observer_group, receipt['cleanup'], .1)
                        except BaseException as cleanup_error:
                            receipt['errors'].append('observer reap: ' + str(cleanup_error))
            if cid:
                try:
                    info = inspect_owned(cid, name, plan)
                    receipt['container_before_stop'] = {'state': info['State'], 'host_identity': supervisor.process_identity(info['State']['Pid'])}
                    if info['State']['Running']:
                        command(['docker', 'stop', '--timeout', '15', cid], timeout=30)
                    after = inspect_owned(cid, name, plan)
                    receipt['container_stopped'] = not after['State']['Running']
                    if not receipt['container_stopped']:
                        raise RuntimeError('Own container remains running')
                except BaseException as error:
                    receipt['errors'].append('container cleanup: ' + str(error))
            if execution:
                try:
                    receipt['docker_exec_final_returncode'] = execution.wait(timeout=10)
                except BaseException as error:
                    receipt['errors'].append('docker exec reap: ' + str(error))
                    if execution_group:
                        try:
                            receipt['exec_final_group'] = cleanup_group(supervisor, execution, execution_group, receipt['cleanup'], .1)
                        except BaseException as cleanup_error:
                            receipt['errors'].append('docker exec group: ' + str(cleanup_error))
            if xephyr:
                try:
                    if xephyr_group is None:
                        raise RuntimeError('Missing own Xephyr birth; refuse unverified group signal')
                    receipt['xephyr_final_group'] = cleanup_group(supervisor, xephyr, xephyr_group, receipt['cleanup'], .1)
                    receipt['xephyr_returncode'] = xephyr.returncode
                except BaseException as error:
                    receipt['errors'].append('Xephyr cleanup: ' + str(error))
            # Never unlink an authority still possibly used by our owned X server.
            if auth.exists() and (xephyr is None or xephyr.poll() is not None):
                auth.unlink()
            if receipt['errors']:
                receipt['status'] = 'failed'
            receipt['native_worker_entries_present'] = [role for role in ('simulator', 'inference')
                if (destination / 'outputs' / role / 'process-entry.json').exists()]
            receipt['native_started'] = bool(receipt['native_worker_entries_present'])
            receipt['finished_unix'] = time.time()
            try:
                write(receipt_path, receipt)
            finally:
                entries = [r for r in records(destination, exclude=('cache', 'host/private.xauth')) if r['relative'] != 'manifest.json'
                           and not r['relative'].endswith('.tmp')]
                write(destination / 'manifest.json', {'schema_version': 1, 'files': entries, 'identity_sha256': identity(entries),
                      'includes_all_raw_success_and_failure_evidence': True, 'excludes_private_auth_cookie': True,
                      'excludes_runtime_cache': True})
    print(json.dumps({'status': receipt['status'], 'receipt': str(receipt_path)}))
    return 0 if receipt['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    prep = modes.add_parser('prepare', help='CPU filesystem copy + Docker image inspect only; no server/container start')
    prep.add_argument('--source', type=Path, required=True)
    prep.add_argument('--project', type=Path, required=True)
    prep.add_argument('--destination', type=Path, required=True)
    prep.add_argument('--image', required=True)
    prep.add_argument('--display', default=':91')
    launch = modes.add_parser('run', help='OPERATOR ONLY: real isolated GUI/native/DDS/GPU execution')
    launch.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args); return 0
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
