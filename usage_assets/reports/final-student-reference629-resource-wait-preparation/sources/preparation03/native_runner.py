#!/usr/bin/env python3
"""Root-operated one-attempt full reference629 matrix. Writing this file starts nothing."""
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
from types import ModuleType
import uuid

from support import HERE, IMAGE, GPU, LOCK, SOURCE_SHAS, verify_contract, check as check_record
# Each actual value is bound explicitly from the separately reviewed new contract.
ROOT = Path('/home/dzp/projects/php_parkour')
OLD = BASE = CPU_PLAN = CPU_OVERLAY = HOST = NAME = CPU_PLAN_SHA = None
CONTRACT_PATH = CONTRACT_SHA = None
OBSERVER = HERE / 'frozen/observe_container_pids.py'
OBSERVER_SHA = 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0'
MODEL_SHAS = None



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
    contract = verify_contract(CONTRACT_PATH, CONTRACT_SHA)
    models = {}
    for name, sha in MODEL_SHAS.items():
        models[name] = fp(OLD / 'inputs' / CURRENT_KIND / 'assets/student' / name)
        require(models[name]['sha256'] == sha, 'Actual fetched official model changed')
    require(fp(OBSERVER)['sha256'] == OBSERVER_SHA, 'Frozen observer changed')
    return {'source_files_verified': 5184, 'freeze_manifest': contract['freeze_manifest'],
            'models': models, 'cpu_reference_plan': fp(CPU_PLAN), 'observer': fp(OBSERVER)}



def verify_matrix_and_host_mappings(container_id, started_at):
    expected = json.loads(CPU_PLAN.read_text())
    output = BASE / 'outputs/reference629'
    saved = output / 'plan.json'
    require(fp(saved)['sha256'] == CPU_PLAN_SHA and saved.read_bytes() == CPU_PLAN.read_bytes(),
            'Native saved plan differs from the actual CPU plan')
    matrix_path = output / 'matrix.json'
    matrix = json.loads(matrix_path.read_text())
    require(matrix['status'] == 'completed' and matrix['completed_configurations'] == 629
            and matrix['completed_scenarios'] == 17 and matrix['configuration_coverage_complete'] is True,
            'Reference629 native matrix is not fully completed')
    require(all(matrix.get(key) == value for key, value in expected.items() if key not in ('status', 'selections')),
            'Native matrix top-level identity changed')
    invocation = matrix['last_invocation']
    require(invocation['case_ids'] == [] and invocation['case_limit'] is None and invocation['resume'] is False
            and invocation['requested_configurations'] == 629, 'Native invocation was partial or resumed')
    observed = json.loads((HOST / 'observer/summary.json').read_text())
    require(observed['mapping_scope_complete'] is True and not observed['errors']
            and observed['stop_reason'] == 'stop_file', 'Host observer incomplete or expired')
    require(observed['identity']['container_id'] == container_id
            and observed['identity']['image_id'] == IMAGE and observed['identity']['started_at'] == started_at,
            'Host observer is from a different actual container birth')
    rows = matrix['selections']
    require(len(rows) == len(expected['selections']) == 629, 'Native configuration count changed')
    mappings, worker_receipts = [], []

    def host_path(value):
        path = Path(value)
        require(path.is_absolute() and '..' not in path.parts, 'Unsafe retained path')
        return BASE / 'outputs' / path.relative_to('/outputs')

    def verify_record(record):
        actual = fp(host_path(record['path']))
        require((actual['sha256'], actual['bytes']) == (record['sha256'], record['bytes']),
                'Sealed evidence changed: ' + record['path'])
        return actual

    for planned, actual in zip(expected['selections'], rows):
        require(all(actual.get(key) == value for key, value in planned.items()), 'Configuration identity changed')
        attempts = actual['attempts']
        require(actual['status'] == 'completed' and len(attempts) == 1 and attempts[0]['status'] == 'completed'
                and attempts[0]['returncode'] == 0, 'Keep first failure; no retries permitted')
        attempt = attempts[0]
        require(attempt['output'] == planned['output'] and attempt['launch'] == planned['launch'], 'Attempt differs')
        seal_path = host_path(attempt['evidence']['path'])
        verify_record(attempt['evidence'])
        evidence = json.loads(seal_path.read_text())
        case_input = {key: expected[key] for key in ('plan_sha256', 'image_id', 'source_matrix_sha256', 'model_sha256')}
        case_input.update(case_id=planned['case_id'], source_files=planned['source_files'], launch=planned['launch'])
        require(evidence['case_input'] == case_input and evidence['expected_policy_ticks'] == planned['reference_commands']['frames'],
                'Sealed case inputs/reference frame count changed')
        require(evidence['execution'] == {'output': planned['output'], 'launch': planned['launch'],
                                         'log': attempt['log'], 'returncode': 0}, 'Sealed execution changed')
        verify_record(attempt['log'])
        for artifact in evidence['files']:
            verify_record(artifact)
        directory = host_path(planned['output'])
        result_path = directory / 'result.json'
        result = json.loads(result_path.read_text())
        require(fp(result_path)['sha256'] == evidence['result_sha256'] and result == actual['result']
                and result['inference']['ticks'] == planned['reference_commands']['frames']
                and result['quality_verified'] is False and result['obstacle_course_completion_verified'] is False,
                'Native result or reference ticks changed')
        workers_path = directory / 'worker-processes.json'
        workers = json.loads(workers_path.read_text())
        final = workers['events'][-1]
        require(workers['schema_version'] == 2 and workers['harness_sha256'] == SOURCE_SHAS['sim2sim.py']
                and final['event'] == 'finally_wait_complete' and not final['cleanup_errors']
                and not final['unreaped_roles'] and len(final['workers']) == 2,
                'Native final worker receipt failed')
        require({worker['role'] for worker in final['workers']} == {'simulator', 'inference'}, 'Worker roles changed')
        for worker in final['workers']:
            group = worker['process_group']
            require(worker['returncode'] == 0 and group['live_members'] == [] and group['ownership_verified'] is True
                    and group['ownership_state'] == 'retired_empty' and not group['ownership_lost'],
                    'Native worker did not exit0 with empty owned group')
            role = worker['role']
            entry_path = directory / (role + '-process-start.json')
            entry = json.loads(entry_path.read_text())['process']
            matching = [mapping for mapping in observed['command_writer_mappings'] if mapping['role'] == role
                        and mapping['worker_output'] == planned['output'] and mapping['container_tgid'] == entry['pid']
                        and mapping['owner_start_time_clock_ticks'] == entry['start_time_clock_ticks']]
            require(len(matching) == 1, 'Missing or ambiguous host writer birth: ' + planned['case_id'] + ':' + role)
            mapping = matching[0]
            require(mapping['nspid'] == [mapping['host_tid'], mapping['container_tid']]
                    and mapping['nstgid'] == [mapping['host_tgid'], entry['pid']], 'Host writer namespace/owner mismatch')
            mappings.append({'case_id': planned['case_id'], 'role': role, 'entry': fp(entry_path), 'mapping': matching[0]})
        require(len(evidence['worker_receipts']) == 3 and all(record in evidence['files'] for record in evidence['worker_receipts']),
                'Sealed mandatory worker receipts missing')
        worker_receipts.extend(verify_record(record) for record in evidence['worker_receipts'])
    require(len(mappings) == 1258 and len(worker_receipts) == 1887, 'Full native worker coverage changed')
    require(len({(row['mapping']['host_tid'], row['mapping']['start_time_clock_ticks']) for row in mappings}) == 1258,
            'Host writer identity is reused between native workers')
    return {'native_plan': fp(saved), 'native_matrix': fp(matrix_path), 'observer_summary': fp(HOST / 'observer/summary.json'),
            'completed_configurations': 629, 'completed_scenarios': 17, 'native_workers_exit0': 1258,
            'sealed_worker_receipt_files': worker_receipts, 'host_native_mappings': mappings,
            'total_reference_frames': sum(row['reference_commands']['frames'] for row in expected['selections']),
            'full_video_decode_verified': False,
            'scope': 'Full reference-command physical replay execution plus sealed artifacts/worker exits and actual host births; skill/course quality unverified; separate full MP4 decode remains required'}


def run_kind(contract, kind, already_held_fd, contract_sha):
    """Called only by adapter.execute while its single UUID flock remains held.

    No nested lock acquisition, lock carrier, fcntl monkeypatch, or implicit
    function replacement. Closing our duplicate fd cannot unlock the outer fd.
    """
    global OLD, BASE, CPU_PLAN, CPU_OVERLAY, HOST, NAME, CPU_PLAN_SHA, MODEL_SHAS
    global CONTRACT_PATH, CONTRACT_SHA, CURRENT_KIND
    CURRENT_KIND = kind
    require(kind in ('pure', 'finetune'), 'Unknown official student kind')
    OLD = Path(contract['base'])
    CONTRACT_PATH, CONTRACT_SHA = OLD / 'contract.json', contract_sha
    require(verify_contract(CONTRACT_PATH, CONTRACT_SHA) == contract, 'Explicit contract changed')
    BASE = OLD / 'runs' / kind
    HOST = BASE / 'host'
    CPU_PLAN = Path(contract['kinds'][kind]['cpu_plan']['path'])
    CPU_PLAN_SHA = contract['kinds'][kind]['cpu_plan']['sha256']
    CPU_OVERLAY = OLD / 'overlay'
    MODEL_SHAS = {Path(row['path']).name: row['sha256'] for row in contract['admission']['models'] if row['kind'] == kind}
    require(set(MODEL_SHAS) == {'depth_backbone.onnx', 'student.onnx'}, 'Exact actual official pair required')
    NAME = 'php-final-reference629-' + kind + '-' + contract['contract_identity'][:12]
    held, canonical = os.fstat(already_held_fd), LOCK.stat()
    require((held.st_dev, held.st_ino) == (canonical.st_dev, canonical.st_ino) and not LOCK.is_symlink(),
            'Caller fd is not the canonical already-held UUID mutex')
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
                and value['Config']['Labels'].get('php.reference629.owner') == token,
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
    lock = os.fdopen(os.dup(already_held_fd), 'a+')
    try:
        # The adapter owns the only flock for pure native+CPU then finetune native+CPU.
        require(os.fstat(lock.fileno()).st_ino == held.st_ino, 'Borrowed fd identity changed')
        BASE.mkdir()
        HOST.mkdir()
        for directory in ('overlay', 'checks', 'outputs', 'cache'):
            (BASE / directory).mkdir()
        persist()
        receipt['source_before'] = snapshot()
        receipt['overlay'] = {}
        for name, sha in SOURCE_SHAS.items():
            source = CPU_OVERLAY / name
            require(fp(source)['sha256'] == sha, 'Reviewed CPU overlay changed: ' + name)
            copied = BASE / 'overlay' / name
            copied.write_bytes(source.read_bytes())
            require(fp(copied)['sha256'] == sha, 'CPU overlay changed while copied')
            receipt['overlay'][name] = {'source': fp(source), 'copy': fp(copied)}
        endpoint = os.environ.get('DOCKER_HOST')
        if endpoint is None:
            context = capture(['docker', 'context', 'show'], 'docker-context').stdout.strip()
            endpoint = json.loads(capture(['docker', 'context', 'inspect', context], 'docker-context-inspect').stdout)[0]['Endpoints']['docker']['Host']
        require(endpoint.startswith('unix://'), 'Host birth observer requires local Unix Docker')
        receipt['docker_endpoint'] = endpoint
        # Host-only resource admission under the adapter's original held
        # UUID flock, before creating any GPU container or native worker.
        # Both kinds use this same real-clock bound; native/worker clocks below
        # are unchanged. No other task can receive a signal here.
        helper_path = HERE / 'reference629_gpu_resource_wait.py'
        manifest = json.loads(Path(contract['preparation_manifest']['path']).read_text())
        helper_rows = [row for row in manifest['files'] if row['path'] == 'reference629_gpu_resource_wait.py']
        require(len(helper_rows) == 1, 'Frozen host resource helper is absent or duplicated')
        helper_source = fp(helper_path)
        require((helper_source['bytes'], helper_source['sha256']) ==
                (helper_rows[0]['bytes'], helper_rows[0]['sha256']), 'Frozen host resource helper differs')
        helper_raw = helper_path.read_bytes()
        require(hashlib.sha256(helper_raw).hexdigest() == helper_source['sha256'],
                'Host resource helper changed before loading')
        helper = ModuleType('reference629_gpu_resource_wait')
        helper.__file__ = str(helper_path)
        exec(compile(helper_raw, str(helper_path), 'exec'), helper.__dict__)
        receipt['host_resource_admission'] = helper.wait_for_idle(
            lock.fileno(), LOCK, GPU, HOST / 'resource-admission', pending, helper_source,
            wait_seconds=1800.0, poll_seconds=5.0)
        receipt['host_resource_admission_receipt'] = fp(HOST / 'resource-admission/receipt.json')
        persist()
        mounts = [(OLD / 'source', '/workspace/php_parkour', True),
                  (BASE / 'overlay', '/workspace/php_parkour/scripts/research', True),
                  (OLD / 'inputs' / kind, '/data', True), (BASE / 'cache', '/data/cache', False),
                  (BASE / 'checks', '/checks', False), (BASE / 'outputs', '/outputs', False)]
        argv = ['docker', 'create', '--name', NAME, '--label', 'php.reference629.owner=' + token,
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
                         '--output', str(HOST / 'observer'), '--stop-file', str(stop), '--interval', '0.2', '--max-seconds', '86400']
        observer_logs = [(HOST / 'observer.stdout.raw').open('w'), (HOST / 'observer.stderr.raw').open('w')]
        observer = subprocess.Popen(observer_argv, stdout=observer_logs[0], stderr=observer_logs[1], start_new_session=True)
        receipt['observer'] = {'argv': observer_argv, 'host_identity_at_spawn': birth(observer.pid)}
        persist()
        deadline = time.monotonic() + 30
        while not (HOST / 'observer/launch.json').is_file():
            require(observer.poll() is None, 'Observer exited before its true startup receipt')
            require(time.monotonic() < deadline, 'Read-only observer startup timeout')
            time.sleep(.1)
        matrix_argv = ['/opt/php/bin/inference-python', '-B',
                       '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py',
                       '--matrix', '/data/matrix.json', '--models', '/data/assets/student',
                       '--output', '/outputs/reference629', '--all-configs', '--reference-commands',
                       '--image-id', IMAGE, '--gl', 'egl']
        # Only a /checks plan is created; native output must remain absent.
        capture(['docker', 'exec', cid, *matrix_argv, '--plan',
                 '--plan-output', '/checks/verified-prelaunch-plan.json'], 'actual-prelaunch-plan')
        prelaunch = BASE / 'checks/verified-prelaunch-plan.json'
        require(fp(prelaunch)['sha256'] == CPU_PLAN_SHA and prelaunch.read_bytes() == CPU_PLAN.read_bytes(),
                'Future native namespace or plan differs from the actual CPU plan')
        require(not (BASE / 'outputs/reference629').exists(), 'Prelaunch CPU plan unexpectedly created native output')
        receipt['prelaunch_plan'] = fp(prelaunch)
        persist()
        native_argv = ['docker', 'exec', cid, *matrix_argv]
        native_logs = [(HOST / 'native.stdout.raw').open('w'), (HOST / 'native.stderr.raw').open('w')]
        native = subprocess.Popen(native_argv, stdout=native_logs[0], stderr=native_logs[1], start_new_session=True)
        receipt['native'] = {'argv': native_argv, 'host_identity_at_spawn': birth(native.pid),
                             'scope': 'host docker-exec client; native worker births are separate observer/entry evidence'}
        receipt['status'] = 'native_reference629_running'
        persist()
        receipt['native']['actual_wait_returncode'] = native.wait()  # Core owns its bounded wall timeout; no outer native timeout.
        stop.touch()
        receipt['observer']['actual_wait_returncode'] = observer.wait()
        persist()
        require(receipt['native']['actual_wait_returncode'] == receipt['observer']['actual_wait_returncode'] == 0,
                'Native or observer failed; retain the first failure')
        receipt.update(verify_matrix_and_host_mappings(cid, started_at))
        receipt['status'] = 'native_reference629_completed_worker1258_hostwriter1258'
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
                for item in list(receipt.get('overlay', {}).values()):
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
    return 0 if receipt['status'] == 'native_reference629_completed_worker1258_hostwriter1258' else 1


if __name__ == '__main__':
    raise SystemExit('Use the separately reviewed adapter execute entry; no standalone GPU start')
