#!/usr/bin/env python3
"""Root-operated one-attempt reference pilot. Writing this file starts nothing."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
BASE = ROOT / 'outputs/research/reference-native-pilot-01'
HOST = BASE / 'host'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
LOCK = ROOT / ('outputs/research/.local-native-' + GPU + '.lock')
NAME = 'php-reference-native-pilot-01'
FREEZE_SHA = '599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169'
SOURCE_SHAS = {
    'sim2sim.py': '023fed0f9f31f79b506b370a96013c18e8b1c94239e0504eca4bcea6076c3f4d',
    'reference_commands.py': '1af208fc1f57bac61d37256a4bdbb20fa45b05817291c3372c92b5a8c3807d57',
}
OBSERVER = OLD / 'control/observe_container_pids.py'
OBSERVER_SHA = 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0'
SCENARIO = ROOT / 'outputs/research/motion-matching/scenarios/high_speed_speed_vault'
INPUT_SHAS = {
    'run_left_45_0.3s_motion.npz': '26e0a95c7d64692cf62ddc148cb3cec7df759a9c979343dadc6a513400b6b3a4',
    'run_left_45_0.3s_terrain.obj': 'e93fc19dec85ab981e0dcbddcb5f391f94e477e864c0785caa9cac3ef8e36bfe',
}
MODEL_SHAS = {
    'depth_backbone.onnx': '5b22466a218944e3b0ab0f4f82a910e3eec35375ee03e7fb94eb65fa88431b56',
    'student.onnx': 'e426c4206181d511b838c76efc48e43636299b76cb5a15183977011589931628',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fp(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Require regular file: ' + str(path))
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def birth(pid):
    text = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = text[text.rfind(')') + 2:].split()
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]),
            'pgid': int(fields[2]), 'sid': int(fields[3]), 'start_time_clock_ticks': int(fields[19])}


def snapshot():
    manifest = OLD / 'freeze-manifest.json'
    require(fp(manifest)['sha256'] == FREEZE_SHA, 'Original frozen manifest changed')
    records = [row for row in json.loads(manifest.read_text())['files'] if row['relative'].startswith('source/')]
    require(len(records) == 5184, 'Original full source must contain 5184 frozen files')
    expected = set()
    for row in records:
        relative = Path(row['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe frozen source path')
        expected.add(relative.relative_to('source').as_posix())
        actual = fp(OLD / relative)
        require((actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256']), 'Original source changed: ' + str(relative))
    actual_files = {path.relative_to(OLD / 'source').as_posix() for path in (OLD / 'source').rglob('*') if path.is_file()}
    require(actual_files == expected, 'Original source file set changed')
    models = {}
    for name, sha in MODEL_SHAS.items():
        models[name] = fp(OLD / 'inputs/assets/student' / name)
        require(models[name]['sha256'] == sha, 'Released model changed: ' + name)
    require(fp(OBSERVER)['sha256'] == OBSERVER_SHA, 'Original observer changed')
    return {'source_files_verified': len(records), 'freeze_manifest': fp(manifest), 'models': models,
            'observer': fp(OBSERVER)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    if not args.root_authorized_start:
        parser.error('Root must explicitly authorize this reviewed single native attempt')
    require(not BASE.exists(), 'One-attempt output already exists; never retry or overwrite it')
    token = uuid.uuid4().hex
    native = observer = None
    native_logs = observer_logs = None
    cid = started_at = None
    pending = []
    prior_handlers = {}
    receipt = {'schema_version': 1, 'status': 'starting', 'helper': fp(Path(__file__).resolve()),
               'image_id': IMAGE, 'gpu_uuid': GPU, 'container_name': NAME, 'ownership_token': token,
               'host_process': birth(os.getpid()), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'commands': [], 'errors': [], 'cleanup_errors': [], 'quality_verified': False,
               'obstacle_course_completion_verified': False}

    def persist():
        write(HOST / 'launch-receipt.json', receipt)

    def capture(argv, label, completed=None, check=True, diagnostics=True):
        result = subprocess.run(argv, text=True, capture_output=True, check=False)
        # Record ownership immediately after create, before any diagnostic IO.
        if completed is not None:
            completed(result)
        if diagnostics:
            index = len(receipt['commands'])
            out, err = HOST / f'{index:02d}-{label}.stdout.raw', HOST / f'{index:02d}-{label}.stderr.raw'
            out.write_text(result.stdout)
            err.write_text(result.stderr)
            receipt['commands'].append({'argv': argv, 'returncode': result.returncode,
                                        'stdout': fp(out), 'stderr': fp(err)})
            persist()
        else:
            # Cleanup must still reach stop/wait if diagnostic storage failed.
            receipt.setdefault('cleanup_commands', []).append({'argv': argv, 'returncode': result.returncode,
                                                              'stdout_raw': result.stdout, 'stderr_raw': result.stderr})
        if check:
            require(result.returncode == 0, label + ' failed; inspect original stdout/stderr')
        return result

    def inspect(diagnostics=True):
        value = json.loads(capture(['docker', 'inspect', '--type', 'container', cid], 'own-inspect', diagnostics=diagnostics).stdout)[0]
        require(value['Id'] == cid and value['Image'] == IMAGE and value['Name'] == '/' + NAME
                and value['Config']['Labels'].get('php.reference-pilot.owner') == token,
                'Exact own container identity differs; do not stop an unknown container')
        if started_at is not None:
            require(value['State']['StartedAt'] == started_at, 'Own container was restarted')
        return value

    def stop_own():
        if cid is None:
            return
        before = inspect(diagnostics=False)
        if before['State']['Running']:
            capture(['docker', 'stop', '--time', '20', cid], 'own-stop', diagnostics=False)
        after = inspect(diagnostics=False)
        require(after['State']['Running'] is False, 'Own container still running')
        waited = capture(['docker', 'wait', cid], 'own-container-wait', diagnostics=False)
        receipt['owned_container_stop'] = {'container_id': cid, 'before': before, 'after': after,
                                         'running_after_stop': False, 'actual_container_exit_code': int(waited.stdout.strip()),
                                         'scope': 'sleep container exit, separate from actual native docker-exec wait'}

    def remember_create(result):
        nonlocal cid
        value = result.stdout.strip()
        if re.fullmatch('[0-9a-f]{64}', value):
            cid = value
            receipt['container_id'] = cid

    # Pending operator signals never escape while native/observer cleanup owns resources.
    for number in (signal.SIGINT, signal.SIGTERM):
        prior_handlers[number] = signal.signal(number, lambda signum, frame: pending.append({'signal': signum, 'unix': time.time()}))
    lock = LOCK.open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        BASE.mkdir()
        HOST.mkdir()
        for directory in ('overlay', 'reference', 'outputs', 'cache'):
            (BASE / directory).mkdir()
        persist()
        receipt['source_before'] = snapshot()
        receipt['overlay'] = {}
        for name, sha in SOURCE_SHAS.items():
            source = ROOT / 'scripts/research' / name
            require(fp(source)['sha256'] == sha, 'Reviewed pilot source changed: ' + name)
            copied = BASE / 'overlay' / name
            copied.write_bytes(source.read_bytes())
            require(fp(copied)['sha256'] == sha, 'Pilot source changed while copied')
            receipt['overlay'][name] = {'source': fp(source), 'copy': fp(copied)}
        receipt['reference_inputs'] = {}
        for name, sha in INPUT_SHAS.items():
            source, copied = SCENARIO / name, BASE / 'reference' / name
            require(fp(source)['sha256'] == sha, 'Original reference input changed: ' + name)
            copied.write_bytes(source.read_bytes())
            require(fp(copied)['sha256'] == sha, 'Reference input changed while copied')
            receipt['reference_inputs'][name] = {'source': fp(source), 'copy': fp(copied)}
        endpoint = os.environ.get('DOCKER_HOST')
        if endpoint is None:
            context = capture(['docker', 'context', 'show'], 'docker-context').stdout.strip()
            endpoint = json.loads(capture(['docker', 'context', 'inspect', context], 'docker-context-inspect').stdout)[0]['Endpoints']['docker']['Host']
        require(endpoint.startswith('unix://'), 'Host birth observer requires local Unix Docker')
        receipt['docker_endpoint'] = endpoint
        devices = capture(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], 'gpu-identity').stdout.splitlines()
        require(devices.count(GPU) == 1, 'Exact GPU UUID is not uniquely present')
        compute = capture(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'], 'gpu-idle-inside-lock').stdout
        require(not any(line.split(',')[0].strip() == GPU for line in compute.splitlines() if line.strip()),
                'GPU occupied; do not kill or interrupt another task')
        mounts = [(OLD / 'source', '/workspace/php_parkour', True),
                  (BASE / 'overlay', '/workspace/php_parkour/scripts/research', True),
                  (OLD / 'inputs', '/data', True), (BASE / 'cache', '/data/cache', False),
                  (BASE / 'reference', '/reference', True), (BASE / 'outputs', '/outputs', False)]
        argv = ['docker', 'create', '--name', NAME, '--label', 'php.reference-pilot.owner=' + token,
                '--network', 'none', '--ipc', 'private', '--init', '--shm-size', '8g',
                '--gpus', 'device=' + GPU, '--workdir', '/workspace/php_parkour', '--entrypoint', '/bin/bash']
        for key, value in {'PHP_DOCKER': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'MUJOCO_GL': 'egl',
                           'MUJOCO_EGL_DEVICE_ID': '0', 'PYOPENGL_PLATFORM': 'egl', 'WANDB_MODE': 'disabled',
                           'WANDB_DISABLED': 'true', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                           'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility,graphics', 'OMP_NUM_THREADS': '1',
                           'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}.items():
            argv += ['--env', key + '=' + value]
        for source, destination, readonly in mounts:
            argv += ['--mount', f'type=bind,src={source},dst={destination}' + (',readonly' if readonly else '')]
        argv += [IMAGE, '-lc', 'exec sleep infinity']
        capture(argv, 'own-create', completed=remember_create)
        require(cid is not None, 'Create did not return an exact full CID')
        created = inspect()
        host = created['HostConfig']
        require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and not host.get('PidMode')
                and host['Init'] is True and host['ShmSize'] == 8589934592 and not host['Privileged'], 'Container isolation differs')
        require({(m['Source'], m['Destination'], not m['RW']) for m in created['Mounts']} ==
                {(str(s), d, ro) for s, d, ro in mounts} and len(created['Mounts']) == len(mounts), 'Container mounts differ')
        require(len(host.get('DeviceRequests') or []) == 1 and host['DeviceRequests'][0]['DeviceIDs'] == [GPU], 'GPU request differs')
        receipt['created_inspect'] = created
        capture(['docker', 'start', cid], 'own-start')
        running = inspect()
        require(running['State']['Running'] is True, 'Own container did not start')
        started_at = running['State']['StartedAt']
        receipt['running_inspect'] = running
        receipt['host_container_init'] = birth(running['State']['Pid'])
        stop = HOST / 'observer.stop'
        observer_argv = [sys.executable, '-B', str(OBSERVER), '--container-id', cid, '--expected-image', IMAGE,
                         '--output', str(HOST / 'observer'), '--stop-file', str(stop), '--interval', '0.2', '--max-seconds', '600']
        observer_logs = [(HOST / 'observer.stdout.raw').open('w'), (HOST / 'observer.stderr.raw').open('w')]
        observer = subprocess.Popen(observer_argv, stdout=observer_logs[0], stderr=observer_logs[1], start_new_session=True)
        receipt['observer'] = {'argv': observer_argv, 'host_identity_at_spawn': birth(observer.pid)}
        persist()
        deadline = time.monotonic() + 30
        while not (HOST / 'observer/launch.json').is_file():
            require(observer.poll() is None, 'Observer exited before its true startup receipt')
            require(time.monotonic() < deadline, 'Read-only observer startup timeout')
            time.sleep(.1)
        native_argv = ['docker', 'exec', cid, '/opt/php/bin/inference-python',
                      '/workspace/php_parkour/scripts/research/sim2sim.py', '--models', '/data/assets/student',
                      '--output', '/outputs/rollout', '--terrain', 'custom', '--mesh', '/reference/run_left_45_0.3s_terrain.obj',
                      '--reference-motion', '/reference/run_left_45_0.3s_motion.npz', '--reference-spawn', '--record-policy',
                      '--gl', 'egl', '--seed', '42', '--ort-threads', '1', '--python-faulthandler']
        native_logs = [(HOST / 'native.stdout.raw').open('w'), (HOST / 'native.stderr.raw').open('w')]
        native = subprocess.Popen(native_argv, stdout=native_logs[0], stderr=native_logs[1], start_new_session=True)
        receipt['native'] = {'argv': native_argv, 'host_identity_at_spawn': birth(native.pid),
                             'scope': 'host docker-exec client; native worker births are separate observer/entry evidence'}
        persist()
        receipt['native']['actual_wait_returncode'] = native.wait()  # Core owns its bounded wall timeout; no outer native timeout.
        stop.touch()
        receipt['observer']['actual_wait_returncode'] = observer.wait()
        persist()
        require(receipt['native']['actual_wait_returncode'] == receipt['observer']['actual_wait_returncode'] == 0,
                'Native or observer failed; retain the first failure')
        result = json.loads((BASE / 'outputs/rollout/result.json').read_text())
        require(result['status'] == 'completed' and result['config']['reference_motion']['sha256'] == INPUT_SHAS['run_left_45_0.3s_motion.npz'],
                'Actual result is not completed or references another motion')
        workers = json.loads((BASE / 'outputs/rollout/worker-processes.json').read_text())
        final = workers['events'][-1]
        require(workers['harness_sha256'] == SOURCE_SHAS['sim2sim.py'] and final['event'] == 'finally_wait_complete'
                and not final['cleanup_errors'] and not final['unreaped_roles'] and len(final['workers']) == 2,
                'Native final worker receipt failed')
        for worker in final['workers']:
            group = worker['process_group']
            require(worker['returncode'] == 0 and group['live_members'] == [] and group['ownership_verified'] is True
                    and group['ownership_state'] == 'retired_empty' and not group['ownership_lost'], 'A native worker did not exit0/empty')
        observed = json.loads((HOST / 'observer/summary.json').read_text())
        require(observed['mapping_scope_complete'] is True and not observed['errors'], 'Host birth observer incomplete')
        receipt['host_native_mappings'] = []
        for role in ('simulator', 'inference'):
            entry_path = BASE / 'outputs/rollout' / (role + '-process-start.json')
            entry = json.loads(entry_path.read_text())['process']
            matching = [m for m in observed['command_writer_mappings'] if m['role'] == role
                        and m['worker_output'] == '/outputs/rollout' and m['container_tgid'] == entry['pid']
                        and m['owner_start_time_clock_ticks'] == entry['start_time_clock_ticks']]
            require(len(matching) == 1, 'Missing or ambiguous actual host writer birth: ' + role)
            receipt['host_native_mappings'].append({'role': role, 'entry': fp(entry_path), 'mapping': matching[0]})
        receipt['result'] = fp(BASE / 'outputs/rollout/result.json')
        receipt['status'] = 'native_and_worker_exit0_observed_two_host_writers'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        # Even diagnostic IO failures wait for the already-started native core's
        # own finally. No foreign PID signal, native timeout or automatic retry.
        for job, key in ((native, 'native'),):
            if job is not None:
                try:
                    receipt.setdefault(key, {})['actual_wait_returncode'] = job.wait()
                except BaseException as error:
                    receipt['cleanup_errors'].append(str(error))
        if observer is not None:
            try:
                (HOST / 'observer.stop').touch()
            except BaseException as error:
                receipt['cleanup_errors'].append(str(error))
            try:
                receipt.setdefault('observer', {})['actual_wait_returncode'] = observer.wait()
            except BaseException as error:
                receipt['cleanup_errors'].append(str(error))
        for handles in (native_logs, observer_logs):
            for handle in handles or []:
                try:
                    handle.close()
                except BaseException as error:
                    receipt['cleanup_errors'].append(str(error))
        try:
            stop_own()
        except BaseException as error:
            receipt['cleanup_errors'].append(str(error))
            # Unknown stop never releases the UUID mutex. Root may resolve only
            # this exact labelled CID; subsequent checks perform read-only GETs.
            while cid is not None:
                try:
                    if inspect(diagnostics=False)['State']['Running'] is False:
                        break
                except BaseException:
                    pass
                time.sleep(1)
        if BASE.exists():
            try:
                receipt['source_after'] = snapshot()
                require(receipt.get('source_before') == receipt['source_after'], 'Frozen source/model/observer changed')
                for item in list(receipt.get('overlay', {}).values()) + list(receipt.get('reference_inputs', {}).values()):
                    require(fp(item['source']['path']) == item['source'] and fp(item['copy']['path']) == item['copy'], 'Overlay/reference input changed')
            except BaseException as error:
                receipt['cleanup_errors'].append(str(error))
            receipt['pending_signals'] = pending
            if receipt['cleanup_errors'] or pending:
                receipt['status'] = 'failed'
            receipt['finished_unix'] = time.time()
            try:
                persist()
            except BaseException as error:
                receipt['status'] = 'failed'
                print('Final diagnostic IO failed: ' + str(error), file=sys.stderr)
        lock.close()
        for number, handler in prior_handlers.items():
            signal.signal(number, handler)
    print(json.dumps({'status': receipt['status'], 'receipt': str(HOST / 'launch-receipt.json'),
                      'quality_verified': False, 'obstacle_course_completion_verified': False}))
    return 0 if receipt['status'] == 'native_and_worker_exit0_observed_two_host_writers' else 1


if __name__ == '__main__':
    raise SystemExit(main())
