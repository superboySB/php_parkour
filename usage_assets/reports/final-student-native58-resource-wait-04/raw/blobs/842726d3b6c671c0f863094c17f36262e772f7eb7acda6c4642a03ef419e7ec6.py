#!/usr/bin/env python3
"""Explicit, read-only cross-boot recovery admission; never starts/stops native work."""
from __future__ import annotations
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
sys.dont_write_bytecode = True

ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
OLD_BOOT = 'a4856e87-ac1b-4883-8b4e-d8cd48861796'
OLD_GATE_SHA = 'dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525'
NATIVE_SHA = '31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43'
COMMON_SHA = 'bef9e7af9a67c9d10360145de7f6715cb167a8722fccb1e44aaaf4c7118371b2'
PHASE_CPU_SHA = '855d56494c662cbfcd19a96043b6f0baaa49a093f52c47b46a9005657e46bb0f'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
MUTEX = ROOT / ('outputs/research/.local-native-' + GPU + '.lock')


class Waiting(Exception):
    pass


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require(path.is_relative_to(ROOT) and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe control path: ' + str(path))
    return path


def fingerprint(path):
    path = safe(path)
    first = path.stat()
    require(stat.S_ISREG(first.st_mode), 'Regular control file required')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    last = path.stat()
    require((first.st_ino, first.st_size, first.st_mtime_ns, first.st_ctime_ns)
            == (last.st_ino, last.st_size, last.st_mtime_ns, last.st_ctime_ns), 'Control file changed during read')
    return {'path': str(path), 'bytes': last.st_size, 'sha256': h.hexdigest()}


def verify(row):
    require(fingerprint(row['path']) == row, 'External control fingerprint differs: ' + row['path'])
    return safe(row['path'])


def read(row):
    raw = verify(row).read_bytes()
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'JSON changed during read')
    return json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, safe(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def endpoint_identity():
    path = Path('/var/run/docker.sock')
    info = path.stat()
    require(stat.S_ISSOCK(info.st_mode) and not path.is_symlink(), 'Original local Docker socket required')
    return {'resolved': str(path.resolve()), 'dev': info.st_dev, 'inode': info.st_ino,
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': oct(stat.S_IMODE(info.st_mode)),
            'socket': True, 'leaf_symlink': False, 'readable': os.access(path, os.R_OK), 'writable': os.access(path, os.W_OK)}


def actor_context(data, observations=None):
    certificate = read(data['unix_endpoint_observation'])
    actor = {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid(), 'egid': os.getegid(), 'groups': os.getgroups()}
    require(actor == certificate['actor'], 'Current actor differs from reviewed Unix endpoint observation')
    commands = []
    if observations is not None:
        observations.update(actor=actor, actual_readonly_commands=commands)

    def command(argv):
        done = subprocess.run(argv, capture_output=True, timeout=30)
        commands.append({'argv': argv, 'actual_wait_returncode': done.returncode,
                         'stdout_hex': done.stdout.hex(), 'stderr_hex': done.stderr.hex()})
        require(done.returncode == 0, 'Read-only Docker CLI context/daemon identity failed')
        return done.stdout

    name = command(['docker', 'context', 'show']).decode().strip()
    expected_name = verify({**certificate['commands'][0]['stdout'],
                            'path': str(ROOT / certificate['commands'][0]['stdout']['path'])}).read_text().strip()
    require(name == expected_name and os.environ.get('DOCKER_CONTEXT', name) == name
            and os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock') == 'unix:///var/run/docker.sock',
            'Docker CLI context/environment differs from reviewed local endpoint')
    context = json.loads(command(['docker', 'context', 'inspect', name]))
    require(len(context) == 1 and context[0]['Name'] == name
            and context[0]['Endpoints']['docker']['Host'] == 'unix:///var/run/docker.sock', 'Docker CLI context targets a different daemon')
    info = json.loads(command(['docker', 'info', '--format', '{{json .}}']))
    require({'id': info['ID'], 'docker_root': info['DockerRootDir'], 'os_type': info['OSType']} == data['daemon'],
            'Docker CLI and direct Unix API daemon identities differ')
    return {'actor': actor, 'context_name': name, 'actual_readonly_commands': commands}


class UnixDocker(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def docker_get(route, observations=None):
    require(os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock') == 'unix:///var/run/docker.sock',
            'Only the reviewed local Unix Docker endpoint is allowed')
    require(route == '/info' or re.fullmatch(r'/containers/[0-9a-f]{64}/json', route), 'Read-only exact Docker route required')
    connection = UnixDocker('localhost', timeout=15)
    try:
        connection.request('GET', route)
        response = connection.getresponse()
        raw = response.read()
        row = {'method': 'GET', 'route': route, 'http_status': response.status,
               'headers': response.getheaders(), 'body_hex': raw.hex(), 'body_bytes': len(raw),
               'body_sha256': hashlib.sha256(raw).hexdigest()}
        if observations is not None:
            observations.update(row)
        row['json'] = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
        if observations is not None:
            observations.update(row)
        return row
    finally:
        connection.close()


def daemon_identity(row):
    require(row['http_status'] == 200 and row['route'] == '/info', 'Current daemon identity unavailable')
    data = row['json']
    return {'id': data['ID'], 'docker_root': data['DockerRootDir'], 'os_type': data['OSType']}


def typed_absent(row, cid):
    return (row['http_status'] == 404 and row['route'] == '/containers/' + cid + '/json'
            and row['json'] == {'message': 'No such container: ' + cid})


def require_owned_mutex():
    """Prove this PID owns the original whole-job flock; do not acquire another lock."""
    path = safe(MUTEX)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), 'Original shared mutex is not a regular file')
    matches = []
    for line in Path('/proc/locks').read_text().splitlines():
        parts = line.split()
        if len(parts) < 8 or parts[1:4] != ['FLOCK', 'ADVISORY', 'WRITE'] or parts[4] != str(os.getpid()) or parts[6:8] != ['0', 'EOF']:
            continue
        major, minor, inode = parts[5].split(':')
        if (int(major, 16), int(minor, 16), int(inode)) == (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino):
            matches.append(line)
    require(len(matches) == 1, 'Current wrapper PID must hold the original GPU mutex before gate admission')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
            'owner_pid': os.getpid(), 'actual_proc_locks_line': matches[0]}


def mutex_identity(row):
    return {k: row[k] for k in ('path', 'device', 'inode', 'owner_pid')}


def verify_reviewed_mutex(row, data):
    require({k: row[k] for k in ('path', 'device', 'inode')} == data['mutex'], 'Original reviewed mutex inode/device/path changed')


def gpu_idle():
    rows = []
    for query in ('--query-gpu=uuid', '--query-compute-apps=gpu_uuid,pid'):
        argv = ['nvidia-smi', query, '--format=csv,noheader,nounits']
        done = subprocess.run(argv, capture_output=True, timeout=30)
        rows.append({'argv': argv, 'actual_wait_returncode': done.returncode,
                     'stdout_hex': done.stdout.hex(), 'stderr_hex': done.stderr.hex()})
        require(done.returncode == 0, 'Read-only physical GPU query failed')
    ids = bytes.fromhex(rows[0]['stdout_hex']).decode().splitlines()
    require(ids.count(GPU) == 1, 'Approved physical GPU UUID must occur exactly once')
    processes = bytes.fromhex(rows[1]['stdout_hex']).decode().splitlines()
    busy = [line for line in processes if line.strip() and line.split(',')[0].strip() == GPU]
    return {'uuid': GPU, 'idle': not busy, 'existing_compute_processes': busy, 'actual_queries': rows}


def idle_precheck(data):
    """An optional pre-execute check; original execute repeats the complete gate under its lock."""
    require(boot_id() == data['current_boot_id'] != OLD_BOOT, 'Current boot changed before idle precheck')
    mutex = require_owned_mutex()
    verify_reviewed_mutex(mutex, data)
    endpoint = read(data['unix_endpoint_observation'])['paths']['/var/run/docker.sock']
    require(endpoint_identity() == endpoint, 'Local Unix endpoint changed before idle precheck')
    daemon = docker_get('/info')
    require(daemon_identity(daemon) == data['daemon'], 'Local Unix daemon changed before idle precheck')
    cli = actor_context(data)
    gpu = gpu_idle()
    require(boot_id() == data['current_boot_id'] and endpoint_identity() == endpoint, 'Boot/socket changed during idle precheck')
    return {'status': 'idle_precheck_only' if gpu['idle'] else 'waiting', 'ready_for_original_execute': gpu['idle'],
            'mutex': mutex, 'daemon': daemon, 'actor_context': cli, 'gpu': gpu, 'native_started': False}


def historical_stop(module, stop, cid, gpu):
    """Validate recorded facts separately; never substitute them for a current inspect."""
    require(re.fullmatch('[0-9a-f]{64}', cid) and stop['container_id'] == cid
            and stop['running_after_stop'] is False and not stop.get('remaining_owned_host_children', [])
            and not stop.get('remaining_host_children', []), 'Historical exact-CID stop differs')
    before, after = stop['before'], stop['after']
    require(before['Id'] == after['Id'] == cid and before['Image'] == after['Image'] == module.IMAGE
            and before['State']['StartedAt'] == after['State']['StartedAt']
            and bool(after['State']['StartedAt']) and after['State']['Running'] is False
            and not after['State'].get('Restarting') and not after['State'].get('Paused'), 'Historical birth/image/stop differs')
    mounts, host = after['Mounts'], after['HostConfig']
    require(len({m['Destination'] for m in mounts}) == len(mounts) and bool(after['Name']), 'Historical mounts/name invalid')
    require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and not host.get('PidMode')
            and host['Init'] is True and not host['Privileged'], 'Historical isolation differs')
    requests = host.get('DeviceRequests') or []
    if gpu:
        require(len(requests) == 1 and requests[0]['DeviceIDs'] == [GPU] and host['ShmSize'] == 8589934592,
                'Historical physical GPU differs')
    else:
        require(not requests and host['Runtime'] == 'runc', 'Historical CPU isolation differs')
    require(all(not m['RW'] for m in mounts if m['Destination'] in ('/workspace/php_parkour', '/data', '/control')),
            'Historical source/input/control are not RO')
    if cid == module.CID:
        require(after['State']['StartedAt'] == module.STARTED, 'Historical original birth differs')
    return {'container_id': cid, 'historical_started_at': after['State']['StartedAt'],
            'historical_image_id': module.IMAGE, 'historical_running_after_stop': False}


def contract(path, digest):
    fp = fingerprint(path)
    require(fp['sha256'] == digest and re.fullmatch('[0-9a-f]{64}', digest), 'Explicit external contract SHA differs')
    data = read(fp)
    require(data['schema_version'] == 1 and data['status'] == 'root_reviewed_crossboot_native58_control'
            and data['historical_boot_id'] == OLD_BOOT and data['current_boot_id'] != OLD_BOOT,
            'Explicit reviewed cross-boot authorization required')
    prep = read(data['preparation'])
    require(data['preparation']['path'] == str(HERE / 'manifest.json')
            and prep['status'] == 'source_only_crossboot_native58_control_preparation', 'Wrong control preparation')
    require(prep['prepared_plan'] == data['plan'], 'Contract must use the one already completed original CPU60 prepared plan')
    dependencies = prep['dependencies']
    require(len({x['path'] for x in dependencies}) == len(dependencies), 'Duplicate source dependencies')
    for row in dependencies:
        verify(row)
    expected = {str(HERE / x) for x in ('crossboot_gate.py', 'run_native58.py')}
    require(expected <= {x['path'] for x in dependencies}, 'Wrapper/gate must be sealed dependencies')
    source_review = read(data['source_review'])
    require(source_review['status'] == 'passed_readonly_crossboot_native58_source_review'
            and source_review['must_fix'] == [] and source_review['preparation'] == data['preparation'],
            'Actual independent source review does not bind this preparation')
    plan = read(data['plan'])
    base = safe(data['plan']['path']).parent
    require(data['plan']['path'] == str(base / 'host-plan.json') and plan['global_host_lock'] == str(MUTEX), 'Wrong frozen plan/mutex')
    for name, sha in [('native58.py', NATIVE_SHA), ('common.py', COMMON_SHA), ('phase_cpu.py', PHASE_CPU_SHA), ('previous_recovered_02.py', OLD_GATE_SHA)]:
        require(fingerprint(base / 'control' / name)['sha256'] == sha, 'Original frozen control bytes changed: ' + name)
    cpu_review = read(data['cpu_prepare_review'])
    require(cpu_review['status'] == 'passed_readonly_native58_cpu_preparation_review' and cpu_review['must_fix'] == []
            and cpu_review['plan'] == data['plan'] and cpu_review['cpu_ort_cases'] == 60
            and cpu_review['native_started'] is False and cpu_review['gpu_started'] is False, 'Actual original CPU60 review required')
    parent = read(cpu_review['actual_parent_wait'])
    require(parent['launcher_sha256'] == LAUNCHER_SHA and parent['helper_sha256'] == NATIVE_SHA
            and parent['actual_wait_returncode'] == 0 and parent['pending_signals'] == []
            and parent['boot_id'] == data['current_boot_id'] and parent['argv'][:4] ==
            ['/usr/bin/python3', '-B', str(ROOT / 'outputs/research/final-student-native58-recovered-preparation-01/native58.py'), 'prepare']
            and parent['argv'][-2:] == ['--output', str(base)], 'Actual original CPU prepare parent wait differs')
    audit = read(data['resource_audit'])
    require(audit['status'] == 'passed_readonly_crossboot_fetch_and_current_resource_audit'
            and audit['historical_boot_id'] == OLD_BOOT and audit['actual_current_boot_id'] == data['current_boot_id']
            and audit['actual_daemon_id'] == data['daemon']['id'] and audit['actual_docker_root'] == data['daemon']['docker_root']
            and audit['current_owned_cgroup_processes'] == [], 'Actual current resource audit differs')
    require(data['daemon']['os_type'] == 'linux', 'Linux local daemon required')
    mutex_observation = read(audit['mutex_observation'])
    mutex = mutex_observation['mutex']
    require(mutex_observation['current_boot_id'] == data['current_boot_id'] and mutex['acquired'] is True
            and mutex['released'] is True and {k: mutex[k] for k in ('path', 'device', 'inode')} == data['mutex']
            and data['mutex']['path'] == str(MUTEX), 'Contract must bind actual original mutex inode observation')
    endpoint = read(data['unix_endpoint_observation'])
    require(endpoint['schema'] == 'actual_readonly_local_unix_endpoint_observation_v1'
            and endpoint['boot_id'] == data['current_boot_id']
            and endpoint['paths']['/var/run/docker.sock'] == endpoint['paths']['/run/docker.sock'], 'Actual canonical Unix endpoint observation required')
    rows = audit['current_five_original_containers']
    require(len(rows) == len({x['container_id'] for x in rows}) == 5, 'Five actual resource records required')
    for row in rows:
        request = row['actual_request']
        raw = verify(request['body']).read_bytes()
        require(request['method'] == 'GET' and request['route'] == '/containers/' + row['container_id'] + '/json'
                and request['status'] in (200, 404), 'Resource certificate exact-CID route differs')
        if request['status'] == 404:
            require(json.loads(raw) == {'message': 'No such container: ' + row['container_id']}, 'Historical current404 body is untyped')
    return data, fp, prep, plan


def control_records(data, contract_fp, preparation):
    """Keep referenced actual raw certificate/CPU bytes stable as well as their JSON parents."""
    rows = preparation['dependencies'] + [contract_fp] + [data[x] for x in
        ('preparation', 'source_review', 'plan', 'cpu_prepare_review', 'resource_audit', 'unix_endpoint_observation')]
    audit = read(data['resource_audit'])
    rows += [audit['mutex_observation']] + [x['actual_request']['body'] for x in audit['current_five_original_containers']]
    endpoint = read(data['unix_endpoint_observation'])
    for command in endpoint['commands']:
        rows += [{**command[key], 'path': str(ROOT / command[key]['path'])} for key in ('stdout', 'stderr')]
    cpu = read(data['cpu_prepare_review'])
    rows += [cpu['actual_parent_wait'], cpu['freeze']]
    unique = {}
    for row in rows:
        require(unique.get(row['path'], row) == row, 'Conflicting referenced control fingerprint')
        unique[row['path']] = row
    return list(unique.values())


def evaluate(data, contract_fp, preparation, plan):
    """Called only from the original native58 execute while its original mutex is held."""
    observations = {'schema_version': 1, 'status': 'waiting', 'ready': False,
                    'admission_mode': 'explicit_crossboot_continuation', 'contract': contract_fp,
                    'historical_boot_id': OLD_BOOT, 'current_boot_id': boot_id(),
                    'original_session54334_exit_code': 143, 'quality_verified': False,
                    'native_started_by_gate': False, 'writes': False}
    require(observations['current_boot_id'] == data['current_boot_id'] != OLD_BOOT, 'Current boot changed or historical boot reused')
    source_rows = control_records(data, contract_fp, preparation)
    for row in source_rows:
        verify(row)
    observations['mutex'] = require_owned_mutex()
    verify_reviewed_mutex(observations['mutex'], data)
    endpoint = read(data['unix_endpoint_observation'])['paths']['/var/run/docker.sock']
    observations['unix_endpoint_before'] = endpoint_identity()
    require(observations['unix_endpoint_before'] == endpoint, 'Current local Unix socket identity changed')
    daemon_before = docker_get('/info')
    require(daemon_identity(daemon_before) == data['daemon'], 'Current Unix daemon differs from reviewed certificate')
    observations['daemon_before'] = daemon_before
    observations['actor_context_before'] = actor_context(data)
    gpu = gpu_idle()
    observations['gpu_before'] = gpu
    if not gpu['idle']:
        observations['reason'] = 'Selected GPU currently has compute; no process/container is stopped or ignored'
        return observations
    module = load(Path(data['plan']['path']).parent / 'control/previous_recovered_02.py', 'crossboot_original_recovery')
    require(module.BOOT == OLD_BOOT, 'Historical BOOT constant must remain unchanged')
    evidence = module.Evidence()
    pid_checks, current, stop_records = [], [], {}
    original_stopped = module.stopped

    def historical_pid_not_applicable(pid, birth):
        require(boot_id() == data['current_boot_id'] != module.BOOT, 'Boot changed during historical PID interpretation')
        pid_checks.append({'historical_pid': pid, 'historical_start_time_clock_ticks': birth,
                           'historical_boot_id': module.BOOT, 'current_boot_id': data['current_boot_id'],
                           'status': 'historical_identity_not_applicable_after_boot_change', 'current_proc_read': False})
        return False

    def stopped_across_boot(stop, cid, gpu):
        require(cid not in stop_records, 'Historical CID stop duplicated')
        stop_records[cid] = (stop, gpu)
        historical = historical_stop(module, stop, cid, gpu)
        actual = docker_get('/containers/' + cid + '/json')
        if typed_absent(actual, cid):
            disposition = 'current_absent_typed_404'
        else:
            require(actual['http_status'] == 200, 'Current exact-CID API is neither typed404 nor200')
            # The original function performs another REAL Unix API inspect and
            # complete image/birth/mount/config/isolation check. No synthetic GET.
            checked = original_stopped(stop, cid, gpu)
            require(checked['started_at'] == actual['json']['State']['StartedAt']
                    and actual['json']['Id'] == cid and actual['json']['State']['Running'] is False,
                    'Current stopped container changed between real reads')
            disposition = 'current_stopped_original_full_identity_verified'
        result = {**historical, 'current_status': disposition, 'actual_current_request': actual}
        current.append(result)
        return result

    # These explicit historical-module hooks do not change native58, its BOOT,
    # disk bytes, Docker data, plans, models, scientific source or worker code.
    module.same_process_live = historical_pid_not_applicable
    module.stopped = stopped_across_boot
    try:
        old, historical_plan = module.original_proof(evidence)
        manager, containers = module.manager_proof(evidence, old, historical_plan)
        module.historical_mappings(evidence, historical_plan)
        supplement, more = module.four_proof(evidence, manager, historical_plan)
        containers += more
        cids = [x['container_id'] for x in containers]
        require(len(cids) == len(set(cids)) == 5, 'Five distinct historical exact CIDs required')
        audit_cids = {x['container_id'] for x in read(data['resource_audit'])['current_five_original_containers']}
        require(set(cids) == audit_cids, 'Historical proof and reviewed current certificate CIDs differ')
        module.host_children_gone(cids)
        evidence.finish()
        for item in current:
            cid = item['container_id']
            final = docker_get('/containers/' + cid + '/json')
            if item['current_status'] == 'current_absent_typed_404':
                require(typed_absent(final, cid), 'Previously absent exact historical CID changed during admission')
            else:
                require(final['http_status'] == 200 and final['json'] == item['actual_current_request']['json'],
                        'Current stopped inspect changed during admission')
                original_stopped(stop_records[cid][0], cid, stop_records[cid][1])
            item['actual_current_recheck'] = final
        module.host_children_gone(cids)
    except (FileNotFoundError, module.Waiting) as pending:
        observations.update(reason=str(pending), historical_evidence=evidence.records,
                            historical_pid_checks=pid_checks, current_resources=current)
        return observations
    daemon_after = docker_get('/info')
    require(daemon_identity(daemon_after) == data['daemon'] == daemon_identity(daemon_before), 'Daemon generation changed during admission')
    require(boot_id() == data['current_boot_id'] != module.BOOT, 'Boot changed during admission')
    observations['unix_endpoint_after'] = endpoint_identity()
    require(observations['unix_endpoint_after'] == endpoint, 'Local Unix socket changed during admission')
    observations['actor_context_after'] = actor_context(data)
    for row in source_rows:
        verify(row)
    require(fingerprint(module.__file__)['sha256'] == OLD_GATE_SHA, 'Historical gate source changed')
    mutex_after = require_owned_mutex()
    verify_reviewed_mutex(mutex_after, data)
    require(mutex_identity(mutex_after) == mutex_identity(observations['mutex']), 'Original mutex ownership changed')
    observations['mutex_after'] = mutex_after
    gpu_after = gpu_idle()
    observations.update(daemon_after=daemon_after, gpu_after=gpu_after, current_resources=current,
                        historical_pid_checks=pid_checks, historical_evidence=evidence.records)
    if not gpu_after['idle']:
        observations['reason'] = 'Selected GPU became busy during read-only admission'
        return observations
    observations.update(status='recovered_previous_ready', ready=True,
        original_root_normal_exit_verified=False, original_host_observer_gap_preserved=True,
        original_daemon_exit_code=0, original_configurations=629, original_clean_workers=1258,
        original_full_video_decodes=629, original_unique_host_writer_mappings=1250,
        original_missing_historical_writer_mappings=8, separate_supplement_case_ids=module.CASE_IDS,
        supplement_clean_workers=8, supplement_host_writer_mappings=8, supplement_full_video_decodes=4,
        historical_containers_stopped=containers, owned_host_children_absent=True,
        gpu_mutex_owned_by_current_process=True, gpu_idle_verified=True,
        historical_gate=fingerprint(module.__file__), gate=fingerprint(__file__),
        scope='Explicit cross-boot control admission. Original root143 and eight historical mapping gaps remain permanent. No new scientific result.')
    return observations


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--contract-sha256', required=True)
    args = p.parse_args()
    data, fp, prep, plan = contract(args.contract, args.contract_sha256)
    # A check owns the same original mutex only for the read-only inspection.
    # It never calls native58 execute and cannot create containers or workers.
    with safe(MUTEX).open('r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'waiting', 'ready': False, 'reason': 'Original shared GPU mutex is held', 'native_started': False}))
            return 2
        result = evaluate(data, fp, prep, plan)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result['ready'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'rejected', 'error': str(error), 'native_started': False}), file=sys.stderr)
        raise SystemExit(1)
