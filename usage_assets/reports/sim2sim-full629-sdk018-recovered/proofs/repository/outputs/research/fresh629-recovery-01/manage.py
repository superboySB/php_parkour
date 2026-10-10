#!/usr/bin/env python3
"""Manually adopt one already-running629 exec; never start/retry native work.

This source was written without executing/importing/testing it. Root must review
and explicitly pass --root-authorized-adopt. SIGINT/SIGTERM are only recorded:
they cannot prematurely stop the adopted simulation or escape locked cleanup.
Original session143, launch receipt, source, observer and outputs stay unchanged.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
BASE = ROOT / 'outputs/research/fresh629-recovery-01'
WORK = BASE / 'manager'
VALIDATION = BASE / 'cpu-final-validation'
CID = '2d09d396cf6936c28334e3798a03db87eeceac6562bbc280ab0586e99253a8e1'
EXEC_ID = 'cf999427f555e83d4e45a8d49c682c46022a3e80cae1b66d0b0585e6581e480a'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
STARTED = '2026-10-10T10:02:25.221860961Z'
BOOT = 'a4856e87-ac1b-4883-8b4e-d8cd48861796'
LOCK = ROOT / ('outputs/research/.local-native-' + GPU + '.lock')
CPU_NAME = 'php-fresh629-recovery-cpu-final-01'
OBSERVER_PID = 1914028
OBSERVER_BIRTH = 106696455
ORIGINAL_PID = 787400
ORIGINAL_BIRTH = 105453999
PLAN_SHA = '44d6e71e8ef1d12c5b479d8e3bcb411c39e8d7daa1c3bac109d6edd7417502d0'
FINALIZER_SHA = 'e9d6705ed343915faa2cecffb84d9d977cb10ff491a7e28fc062c4be66e0faca'
PINS = {
    ROOT / 'outputs/research/fresh629-root-terminal-01/session54334.json': '97b6568848785bbf720bb1782086dbc385b6053577921765ec76694c9a293209',
    OLD / 'host/launch-receipt.json': '826d07cfd7a5e268134628ec8fed3f577a2b596a8a4ab5fc18554a31e034305e',
    OLD / 'host-plan.json': '960c5e1ef7e75d05b91f253d152a4d01fd5c07716091c48868c57f86ba74fa5d',
    OLD / 'freeze-manifest.json': '599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169',
    OLD / 'control/finalize_fresh629.py': FINALIZER_SHA,
    OLD / 'control/observe_container_pids.py': 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0',
    OLD / 'control/run_frozen_matrix.py': 'fc0c1a74adb252b818a3d1353fe9209b3f11a90868729e92072a5ae99a2c25fa',
    BASE / 'original-exec-inspect-01.json': 'fbf717581ff8164448dbdce458f2cd42cf6b963aef6481e65f8f5cbdeeddea35',
    BASE / 'observer-launch.json': '6e29251b901dc0b640190350017c13287adf5020a005d0c607d2cc1eb4e1a89c',
    BASE / 'observer/launch.json': '99f3359d5aaad7c94c9b335ee21e06975f87e4cb28a10f85e0dd68279a749c01',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe/symlink path')
    return path


def fp(path):
    path = safe(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Regular file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def read(path):
    path = safe(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Regular JSON required')
    return json.loads(path.read_text(), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def write(path, value, exclusive=False):
    path = safe(path)
    text = json.dumps(value, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x') as stream:
            stream.write(text)
    else:
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('w') as stream:
            stream.write(text)
        temporary.replace(path)


def files(root):
    result = set()
    for path in safe(root).rglob('*'):
        require(not path.is_symlink(), 'Symlink in immutable tree')
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), 'Special file in immutable tree')
    return result


def freeze():
    rows = {}
    for path, digest in PINS.items():
        row = fp(path)
        require(row['sha256'] == digest, 'Hard-pinned original/recovery evidence differs: ' + str(path))
        rows[str(path)] = row
    plan = read(OLD / 'host-plan.json')
    require(plan['plan_sha256'] == PLAN_SHA and plan['image_id'] == IMAGE and plan['gpu_uuid'] == GPU
            and plan['output'] == str(OLD), 'Original plan identity differs')
    original = read(OLD / 'host/launch-receipt.json')
    require(original['status'] == 'running' and original['container_id'] == CID
            and original['plan_sha256'] == PLAN_SHA and original['snapshot_files_verified'] == 5206,
            'Original running launch receipt differs; never rewrite it')
    tool = read(ROOT / 'outputs/research/fresh629-root-terminal-01/session54334.json')
    require(tool['session_id'] == 54334 and tool['exit_code'] == 143 and tool['actual_tool_result']['exit_code'] == 143,
            'Actual original tool143 must remain explicit')
    manifest = read(OLD / 'freeze-manifest.json')['files']
    require(len(manifest) == 5206, 'Expected5206 frozen records')
    grouped = {'source': set(), 'control': set(), 'inputs': set()}
    for item in manifest:
        relative = Path(item['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe original freeze path')
        row = fp(OLD / relative)
        require(row['sha256'] == item['sha256'] and row['bytes'] == item['bytes'], 'Original sealed file differs')
        rows[row['path']] = row
        if relative.parts[0] in grouped:
            grouped[relative.parts[0]].add(Path(*relative.parts[1:]).as_posix())
    require({key: len(value) for key, value in grouped.items()} == {'source': 5184, 'control': 4, 'inputs': 5},
            'Original immutable groups differ')
    for group, expected in grouped.items():
        require(files(OLD / group) == expected, 'Extra/missing original source/control/input file')
    require(fp(OLD / 'inputs/native-plan.json')['sha256'] == plan['native_plan_file_sha256'], 'Original native plan bytes differ')
    return rows


def old_host_guard():
    return {name: fp(OLD / 'host' / name) for name in sorted(files(OLD / 'host'))}


def call(argv, timeout=25):
    result = subprocess.run(argv, capture_output=True, timeout=timeout)
    require(result.returncode == 0, 'Control/read command failed: ' + repr(argv[:4]) + ': ' + result.stderr.decode(errors='replace'))
    return result.stdout.decode()


def endpoint():
    context = call(['docker', 'context', 'show']).strip()
    config = json.loads(call(['docker', 'context', 'inspect', context]))[0]
    address = os.environ.get('DOCKER_HOST') or config['Endpoints']['docker']['Host']
    require(address == 'unix:///var/run/docker.sock', 'Only reviewed local Docker socket accepted')
    return {'context': context, 'endpoint': address}


class LocalDocker(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def exec_info():
    connection = LocalDocker('localhost', timeout=10)
    try:
        connection.request('GET', '/exec/' + EXEC_ID + '/json')
        response = connection.getresponse()
        raw = response.read()
        require(response.status == 200, 'Original exec inspection HTTP' + str(response.status))
        value = json.loads(raw)
        original = read(OLD / 'host/launch-receipt.json')['native_argv']
        require(value['ID'] == EXEC_ID and value['ContainerID'] == CID
                and value['ProcessConfig']['entrypoint'] == original[3]
                and value['ProcessConfig']['arguments'] == original[4:]
                and value['ProcessConfig']['tty'] is False
                and value['ProcessConfig']['privileged'] is False,
                'Daemon exec identity/entrypoint/arguments differs')
        return value
    finally:
        connection.close()


def inspect(cid):
    require(re.fullmatch('[0-9a-f]{64}', cid), 'Exact full CID required')
    value = json.loads(call(['docker', 'inspect', '--type', 'container', cid]))[0]
    require(value['Id'] == cid and value['Image'] == IMAGE, 'Exact adopted/owned container identity differs')
    return value


def selected(value):
    return {k: value[k] for k in ('Id', 'Image', 'Name', 'State', 'Mounts')} | {
        'HostConfig': {k: value['HostConfig'].get(k) for k in ('NetworkMode', 'IpcMode', 'PidMode', 'Runtime', 'Privileged', 'Init', 'ShmSize', 'DeviceRequests')},
        'Config': {k: value['Config'].get(k) for k in ('WorkingDir', 'Entrypoint', 'Cmd')}}


def mounts(cpu):
    common = [(OLD / 'source', '/workspace/php_parkour', False), (OLD / 'inputs', '/data', False), (OLD / 'control', '/control', False)]
    return common + ([(OLD / 'outputs', '/outputs', False), (VALIDATION, '/validation', True)] if cpu
                     else [(OLD / 'outputs', '/outputs', True), (OLD / 'cache', '/data/cache', True)])


def container(value, cpu=False):
    expected_name = CPU_NAME if cpu else read(OLD / 'host-plan.json')['container_name']
    host, config = value['HostConfig'], value['Config']
    require(value['Image'] == IMAGE and value['Name'] == '/' + expected_name, 'Container name/image changed')
    actual = {(m['Source'], m['Destination'], m['RW'], m['Type']) for m in value['Mounts']}
    require(actual == {(str(src), dst, rw, 'bind') for src, dst, rw in mounts(cpu)} and len(value['Mounts']) == 5,
            'Exact5 isolated mounts differ')
    require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and not host.get('PidMode')
            and not host['Privileged'] and host['Init'] is True and config['WorkingDir'] == '/workspace/php_parkour'
            and config['Entrypoint'] == ['/bin/bash'] and config['Cmd'] == ['-lc', 'exec sleep infinity'], 'Container isolation/process differs')
    if cpu:
        require(host['Runtime'] == 'runc' and not host.get('DeviceRequests') and host['ShmSize'] == 1073741824,
                'Recovery CPU container must hide all GPUs')
        env = dict(item.split('=', 1) for item in config['Env'] if '=' in item)
        require(env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void'
                and env.get('PYTHONDONTWRITEBYTECODE') == '1', 'CPU hidden-GPU/bytecode guards differ')
    else:
        requests = host.get('DeviceRequests') or []
        require(value['Id'] == CID and value['State']['StartedAt'] == STARTED
                and host['ShmSize'] == 8589934592 and len(requests) == 1 and requests[0].get('DeviceIDs') == [GPU],
                'Original CID/start/GPU birth differs')


def proc_stat(raw):
    fields = raw.rsplit(')', 1)[1].split()
    return {'state': fields[0], 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]), 'birth': int(fields[19])}


def proc(pid, expected_cid=None):
    root = Path('/proc') / str(pid)
    first = proc_stat((root / 'stat').read_text())
    cgroup = (root / 'cgroup').read_text()
    if expected_cid:
        parts = {p for line in cgroup.splitlines() for p in line.split(':', 2)[-1].split('/')}
        if expected_cid not in parts and 'docker-' + expected_cid + '.scope' not in parts:
            return None
    status = (root / 'status').read_text()
    command = (root / 'cmdline').read_bytes()
    last = proc_stat((root / 'stat').read_text())
    require(first['birth'] == last['birth'] and first['ppid'] == last['ppid'], 'PID birth/ancestry raced')
    nsline = next((line for line in status.splitlines() if line.startswith('NSpid:')), 'NSpid:')
    nspid = [int(n) for n in nsline.split(':', 1)[1].split()]
    return {'pid': pid, **last, 'nspid': nspid, 'argv': [a.decode(errors='replace') for a in command.split(b'\0') if a],
            'cmdline_sha256': hashlib.sha256(command).hexdigest(), 'cgroup_sha256': hashlib.sha256(cgroup.encode()).hexdigest()}


def top(cid):
    raw = call(['docker', 'top', cid, '-eo', 'pid,ppid,stat,args'])
    result = []
    for line in raw.splitlines()[1:]:
        if not line.strip():
            continue
        try:
            value = proc(int(line.split()[0]), cid)
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(value is not None, 'Docker top escaped exact owned cgroup')
        result.append(value)
    return {'utc': utc(), 'raw_top': raw, 'processes': result}


def host_live(cid):
    result = []
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                value = proc(int(path.name), cid)
            except (FileNotFoundError, ProcessLookupError):
                continue
            if value and value['state'] != 'Z':
                result.append(value)
    return result


def adopted_birth():
    value = proc(ORIGINAL_PID, CID)
    require(value and value['birth'] == ORIGINAL_BIRTH and value['nspid'] == [ORIGINAL_PID, 10]
            and value['cmdline_sha256'] == '6143fe0258131b32e2d5efc975b47421466a3fc820e63e3421a98097d4424283',
            'Original native driver PID/birth/command no longer matches')
    return value


def observer_gone():
    try:
        value = proc(OBSERVER_PID)
    except (FileNotFoundError, ProcessLookupError):
        return True
    return value['birth'] != OBSERVER_BIRTH


def persist(result):
    write(WORK / 'receipt.json', result)


def wait_terminal(result):
    """GET only. Unknown state retains lock and waits; never stops native work."""
    stream = None
    try:
        try:
            stream = (WORK / 'exec-observations.jsonl').open('a')
        except BaseException as error:
            result['errors'].append('Exec observation log open: ' + repr(error))
        while True:
            try:
                value = exec_info()
                info = inspect(CID); container(info)
                if stream is not None:
                    try:
                        stream.write(json.dumps({'utc': utc(), 'exec': value}, allow_nan=False) + '\n'); stream.flush()
                    except BaseException as error:
                        result['errors'].append('Exec observation log write: ' + repr(error))
                if value['Running']:
                    require(value['Pid'] == ORIGINAL_PID and value['ExitCode'] is None, 'Running original exec identity differs')
                    try:
                        adopted_birth()
                    except (FileNotFoundError, ProcessLookupError):
                        # It may naturally exit between GET and /proc. A new
                        # daemon GET, never this disappearance, decides exit0.
                        result['driver_proc_raced_exit_observed'] = True
                        continue
                else:
                    require(isinstance(value['ExitCode'], int), 'Daemon terminal exit code unavailable')
                    result['original_daemon_terminal'] = {'utc': utc(), 'exec': value}
                    try:
                        persist(result)
                    except BaseException as error:
                        result['errors'].append('Terminal receipt write: ' + repr(error))
                    return value
            except BaseException as error:
                # Diagnostic/control failures are retained; no native restart or
                # premature stop. Only Root may resolve an unknown daemon state.
                result['read_errors'].append({'utc': utc(), 'error': repr(error)})
                try:
                    persist(result)
                    print('Waiting for exact adopted daemon terminal: ' + repr(error), file=sys.stderr, flush=True)
                except BaseException:
                    pass
            time.sleep(2)
    finally:
        if stream is not None:
            try:
                stream.close()
            except BaseException as error:
                result['errors'].append('Exec observation log close: ' + repr(error))


def stop_observer(result):
    launch = read(BASE / 'observer-launch.json')
    require(launch['pid'] == OBSERVER_PID and proc_stat(launch['stat'])['birth'] == OBSERVER_BIRTH
            and launch['boot_id'] == BOOT and launch['container_id'] == CID and launch['started_at'] == STARTED,
            'Recovery observer original birth differs')
    if not observer_gone():
        current = proc(OBSERVER_PID)
        require(current['birth'] == OBSERVER_BIRTH and current['argv'] == launch['argv'], 'Recovery observer PID was replaced')
    marker = safe(BASE / 'observer-stop')
    if not marker.exists():
        with marker.open('x') as stream:
            stream.write('Original adopted daemon is terminal; stop this read-only segment.\n')
    while not observer_gone():
        time.sleep(.5)
    path = BASE / 'observer/summary.json'
    row, summary = fp(path), read(path)
    require(summary['identity']['container_id'] == CID and summary['identity']['image_id'] == IMAGE
            and summary['identity']['started_at'] == STARTED
            and summary['source_sha256'] == PINS[OLD / 'control/observe_container_pids.py']
            and summary['stop_reason'] == 'stop_file' and not summary['errors']
            and fp(path) == row, 'Recovery observer summary failed/changed')
    result['recovery_observer_stop'] = {'summary': row, 'original_pid': OBSERVER_PID,
         'original_birth': OBSERVER_BIRTH, 'original_birth_no_longer_present': True,
         'os_returncode_observed': False,
         'scope': 'This manager is not the observer parent; only summary and original PID disappearance are verified.'}
    persist(result)


def idle_original(result):
    baseline = {(787093, 105453969), (787237, 105453983)}
    while True:
        event = top(CID)
        live = {(p['pid'], p['birth']) for p in event['processes'] if p['state'] != 'Z'}
        if live == baseline:
            result['original_idle_after_terminal'] = event
            persist(result)
            return
        time.sleep(.5)


def stop_container(cid, cpu=False):
    before = inspect(cid); container(before, cpu)
    argv = ['docker', 'stop', '--time', '20', cid]
    response = call(argv, timeout=35) if before['State']['Running'] else ''
    after = inspect(cid); container(after, cpu)
    require(not after['State']['Running'] and not host_live(cid), 'Exact container still has running host children')
    return {'container_id': cid, 'argv': argv, 'stdout': response, 'before': selected(before), 'after': selected(after),
            'running_after_stop': False, 'remaining_owned_host_children': []}


def observe_stopped(cid, cpu, result):
    while True:
        try:
            value = inspect(cid); container(value, cpu)
            require(not value['State']['Running'] and not host_live(cid), 'Exact owned container/children remain')
            return {'container_id': cid, 'after': selected(value), 'running_after_stop': False,
                    'remaining_owned_host_children': [], 'resolved_after_uncertain_cleanup': True}
        except BaseException as pending:
            try:
                persist(result)
                print('Cleanup uncertain; mutex retained for exact CID ' + cid + ': ' + repr(pending), file=sys.stderr, flush=True)
            except BaseException:
                pass
            time.sleep(2)


def cleanup_once_then_observe(cid, cpu, result):
    """One stop attempt. An uncertain stop never triggers another stop/signal."""
    try:
        return stop_container(cid, cpu)
    except BaseException as error:
        result['errors'].append('Container cleanup uncertain; mutex held: ' + repr(error))
        return observe_stopped(cid, cpu, result)


def matrix_terminal():
    path = OLD / 'outputs/all-configs/matrix.json'
    row, value = fp(path), read(path)
    plan = read(OLD / 'inputs/native-plan.json')
    require(value['status'] == 'completed' and value['plan_sha256'] == plan['plan_sha256']
            and value['completed_configurations'] == 629 and value['completed_scenarios'] == 17
            and value['configuration_coverage_complete'] is True and len(value['selections']) == 629,
            'Original native matrix is not complete629')
    invocation = value['last_invocation']
    require(not invocation['case_ids'] and invocation['case_limit'] is None and not invocation['resume']
            and invocation['requested_configurations'] == 629, 'Original native execution was filtered/resumed')
    for expected, case in zip(plan['selections'], value['selections']):
        require(case['case_id'] == expected['case_id'] and case['status'] == 'completed'
                and len(case['attempts']) == 1 and case['attempts'][0]['status'] == 'completed'
                and case['attempts'][0]['returncode'] == 0, 'Original once-only native case incomplete')
    require(fp(path) == row, 'Original terminal matrix changed during check')
    return row


def cpu_create():
    argv = ['docker', 'create', '--name', CPU_NAME, '--runtime', 'runc', '--network', 'none', '--ipc', 'private',
            '--init', '--shm-size', '1g', '--workdir', '/workspace/php_parkour', '--entrypoint', '/bin/bash']
    env = {'CUDA_VISIBLE_DEVICES': '', 'NVIDIA_VISIBLE_DEVICES': 'void', 'PYTHONDONTWRITEBYTECODE': '1',
           'PHP_DOCKER': '1', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true', 'HF_HUB_OFFLINE': '1',
           'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    for key, value in env.items():
        argv += ['--env', key + '=' + value]
    for source, target, rw in mounts(True):
        argv += ['--mount', 'type=bind,src=' + str(source) + ',dst=' + target + ('' if rw else ',readonly')]
    return argv + [IMAGE, '-lc', 'exec sleep infinity']


def cpu_post(matrix):
    path = VALIDATION / 'full-validation.json'
    row, post = fp(path), read(path)
    require(post['status'] == 'passed' and post['configurations'] == 629 and post['scenarios'] == 17
            and post['worker_exit0_empty_group_count'] == 1258 and post['full_decoded_mp4_count'] == 629
            and post['matrix_sha256'] == matrix['sha256'] and len(post['cases']) == 629,
            'Actual CPU full629/1258/629 finalization failed')
    expected = read(OLD / 'inputs/native-plan.json')
    require([r['case_id'] for r in post['cases']] == [r['case_id'] for r in expected['selections']], 'CPU final case identities differ')
    for case in post['cases']:
        require(case['parent_returncode'] == 0 and case['worker_exit0_empty_groups'] == 2 and case['policy_ticks'] == 500
                and len(case['videos']) == 1 and case['videos'][0]['returncode'] == 0 and case['videos'][0]['full_decode'] is True,
                'CPU final case/video evidence incomplete')
    require(fp(path) == row, 'CPU final report changed')
    return row


def manage(args):
    require(args.root_authorized_adopt, 'Manual --root-authorized-adopt required')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'Recorded host boot changed')
    local = endpoint()
    before = freeze()
    guards = old_host_guard()
    original = inspect(CID); container(original)
    current = exec_info()
    require(current['Running'] is True and current['Pid'] == ORIGINAL_PID and current['ExitCode'] is None,
            'Adopt only the exact still-running original exec; no new execution')
    birth = adopted_birth()
    require(not safe(WORK).exists() and not safe(VALIDATION).exists(), 'Fresh manager/CPU evidence directories required')
    require(not call(['docker', 'ps', '-aq', '--filter', 'name=^/' + CPU_NAME + '$']).strip(), 'Recovery CPU name already exists')
    fd = os.open(safe(LOCK), os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o644)
    require(stat.S_ISREG(os.fstat(fd).st_mode), 'Mutex must be a regular file')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    pending_signals = []
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def delayed(signum, frame):
        pending_signals.append({'utc': utc(), 'signal': signum})
    for sig in handlers:
        signal.signal(sig, delayed)
    result = None
    cpu_cid = None
    cpu_job = None
    adopted = False
    terminal = None
    try:
        # Recheck identities under the same shared GPU mutex before adoption.
        require(exec_info()['Running'] is True, 'Original exec finished before locked adoption')
        require(adopted_birth() == birth, 'Original exec birth changed before adoption')
        require(freeze() == before and old_host_guard() == guards, 'Original evidence changed before adoption')
        WORK.mkdir()
        result = {'schema_version': 1, 'status': 'adopting_existing_native_exec', 'started_utc': utc(),
                  'helper': fp(__file__), 'endpoint': local, 'container_id': CID, 'exec_id': EXEC_ID,
                  'original_session_exit_code': 143, 'original_host_transaction_normal_exit_verified': False,
                  'original_observer_whole_scope_complete': False, 'host_observer_gap_preserved': True,
                  'native_restarted': False, 'new_native_started': False, 'quality_verified': False,
                  'initial_container': selected(original), 'initial_daemon_exec': current, 'original_driver_birth': birth,
                  'read_errors': [], 'errors': [], 'pending_signals': pending_signals,
                  'scope': 'Adopt existing native run and execute original CPU finalizer; does not repair historical hostwriter observations or replace old receipts.'}
        write(WORK / 'frozen-before.json', before, exclusive=True)
        write(WORK / 'original-host-before.json', guards, exclusive=True)
        persist(result)
        adopted = True
        terminal = wait_terminal(result)
        result['status'] = 'original_daemon_terminal'
        require(terminal['ExitCode'] == 0, 'Original native daemon exec did not actually exit0')
        result['terminal_matrix'] = matrix_terminal()
        stop_observer(result)
        idle_original(result)
        result['adopted_gpu_container_stop'] = cleanup_once_then_observe(CID, False, result)
        require(freeze() == before and old_host_guard() == guards, 'Original sealed/source/host evidence changed')
        VALIDATION.mkdir()
        result['cpu_create_argv'] = cpu_create()
        persist(result)
        cpu_cid = call(result['cpu_create_argv']).strip()
        require(re.fullmatch('[0-9a-f]{64}', cpu_cid), 'New CPU create must return full CID')
        result['cpu_container_id'] = cpu_cid
        container(inspect(cpu_cid), True)
        result['cpu_start_argv'] = ['docker', 'start', cpu_cid]
        result['cpu_start_stdout'] = call(result['cpu_start_argv'])
        cpu_info = inspect(cpu_cid); container(cpu_info, True)
        require(cpu_info['State']['Running'], 'New recovery CPU container did not start')
        result['cpu_selected_inspect'] = selected(cpu_info)
        result['cpu_finalizer_sha256'] = FINALIZER_SHA
        argv = ['docker', 'exec', cpu_cid, '/opt/php/bin/inference-python', '/control/finalize_fresh629.py',
                '--plan', '/data/native-plan.json', '--output', '/validation/full-validation.json']
        result['cpu_validation_argv'] = argv
        result['status'] = 'running_original_cpu_finalizer'
        persist(result)
        with (WORK / 'cpu.stdout.raw').open('xb') as stdout, (WORK / 'cpu.stderr.raw').open('xb') as stderr:
            cpu_job = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
            result['cpu_cli_host_pid'] = cpu_job.pid
            persist(result)
            result['cpu_validation_returncode'] = cpu_job.wait()
        require(result['cpu_validation_returncode'] == 0, 'Actual original CPU finalizer returned nonzero')
        result['cpu_stdout'] = fp(WORK / 'cpu.stdout.raw')
        result['cpu_stderr'] = fp(WORK / 'cpu.stderr.raw')
        result['full_validation'] = cpu_post(result['terminal_matrix'])
        require(freeze() == before and old_host_guard() == guards, 'Original bytes changed during recovery CPU finalization')
        result['snapshot_files_verified_before'] = 5206
        result['snapshot_files_verified_after'] = 5206
        result['status'] = 'validation_passed_pending_cleanup'
    except BaseException as error:
        if result is not None:
            result.update(status='failed', error=repr(error), traceback=traceback.format_exc())
        else:
            raise
    finally:
        # Both handlers remain deferred through ALL cleanup/diagnostic intervals,
        # including sleeps and final writes, until actual stopped proof exists.
        if result is not None and adopted:
            try:
                persist(result)
            except BaseException as error:
                result['errors'].append('pre-cleanup receipt: ' + repr(error))
            if terminal is None:
                terminal = wait_terminal(result)
                result['errors'].append('Failure before native terminal; waited naturally without restarting/stopping it')
            if not result.get('recovery_observer_stop'):
                try:
                    stop_observer(result)
                except BaseException as error:
                    result['errors'].append('recovery observer summary/disappearance: ' + repr(error))
            if not result.get('adopted_gpu_container_stop'):
                try:
                    value = inspect(CID); container(value)
                    if value['State']['Running']:
                        idle_original(result)
                    result['adopted_gpu_container_stop'] = cleanup_once_then_observe(CID, False, result)
                except BaseException as error:
                    result['errors'].append('Adopted GPU pre-stop state uncertain; mutex held: ' + repr(error))
                    result['adopted_gpu_container_stop'] = observe_stopped(CID, False, result)
            if cpu_cid is not None:
                result['owned_cpu_container_stop'] = cleanup_once_then_observe(cpu_cid, True, result)
            if cpu_job is not None:
                try:
                    result['cpu_cli_returncode_after_stop'] = cpu_job.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result['errors'].append('Own CPU docker CLI did not return after exact CPU container stop')
                    cpu_job.terminate()
                    try:
                        result['cpu_cli_returncode_after_stop'] = cpu_job.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        cpu_job.kill(); result['cpu_cli_returncode_after_stop'] = cpu_job.wait(timeout=5)
                except BaseException as error:
                    result['errors'].append('Own CPU CLI reap: ' + repr(error))
            try:
                after = freeze()
                host_after = old_host_guard()
                write(WORK / 'frozen-after.json', after, exclusive=True)
                write(WORK / 'original-host-after.json', host_after, exclusive=True)
                require(after == before and host_after == guards and fp(__file__) == result['helper'], 'Original bytes/helper changed')
                result['original_inputs_and_host_bytes_unchanged'] = True
            except BaseException as error:
                result['errors'].append('immutable postcheck: ' + repr(error))
            if (result['status'] == 'validation_passed_pending_cleanup' and not result['errors'] and not result['read_errors']
                    and result.get('owned_cpu_container_stop', {}).get('running_after_stop') is False):
                result['status'] = 'recovered_native_and_cpu_completed_with_host_observer_gap'
            else:
                result['status'] = 'failed'
            result['finished_utc'] = utc()
            try:
                persist(result)
            finally:
                # A failure to write receipt cannot prevent resource cleanup;
                # this point is only reached after both exact owned stops above.
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print(json.dumps({'status': result['status'], 'receipt': str(WORK / 'receipt.json')}, allow_nan=False))
    return 0 if result['status'] == 'recovered_native_and_cpu_completed_with_host_observer_gap' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-authorized-adopt', action='store_true')
    return manage(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
