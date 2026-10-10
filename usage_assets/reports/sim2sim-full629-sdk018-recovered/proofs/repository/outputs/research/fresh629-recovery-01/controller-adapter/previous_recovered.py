#!/usr/bin/env python3
"""Read-only admission proof for the explicitly recovered629 transaction.

Never changes the original running receipt or session143, acquires a lock,
starts/stops a container, signals a process, or runs scientific/native code.
Missing/not-yet-terminal evidence means waiting; contradictory evidence fails.
Callers must retain their own GPU mutex, idle check and lifecycle cleanup.
Written for review only; no invocation/import/test was performed by its author.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
BASE = ROOT / 'outputs/research/fresh629-recovery-01'
FOUR = BASE / 'missing-four-run-01'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
CID = '2d09d396cf6936c28334e3798a03db87eeceac6562bbc280ab0586e99253a8e1'
EXEC_ID = 'cf999427f555e83d4e45a8d49c682c46022a3e80cae1b66d0b0585e6581e480a'
STARTED = '2026-10-10T10:02:25.221860961Z'
BOOT = 'a4856e87-ac1b-4883-8b4e-d8cd48861796'
MANAGER_SHA = '3fc5a0c45bb5efb48f7c45514a885a0ea986ddae2dd309c819186aec582cccec'
FINALIZER_SHA = 'e9d6705ed343915faa2cecffb84d9d977cb10ff491a7e28fc062c4be66e0faca'
CASE_IDS = [
    'high_speed_speed_vault:0004:run_left_45_0.3s',
    'high_speed_speed_vault:0005:run_left_45_0.5s',
    'high_speed_speed_vault:0006:run_left_45_0.9s',
    'high_speed_speed_vault:0007:run_left_45_1.2s',
]
PINS = {
    BASE / 'manage.py': MANAGER_SHA,
    BASE / 'launch_manager.py': '2c0e09ae91363fdce6740571e4b7d64dccded301aab8f3121e47ef4c509e4f87',
    BASE / 'manager-process-start.json': '2bc8f39f6f77008081b45d93e8ffc455b34e47cdffa956319fa7ab27170894a4',
    BASE / 'manager-process-exit.json': 'efb903170724b1ae207dcedeaefa14a7d2736bf3f47f3d70dfddbdd3c35755ca',
    BASE / 'manager/receipt.json': '9e511c2c0c92621ce327eb30e82327ed97cfe9b2d29d0664e14894ff945065d3',
    BASE / 'cpu-final-validation/full-validation.json': '66aae4c05f16a5f5d7dcb5651b9016adfba7013c087e200488223941b5a2630a',
    BASE / 'detached-manager-launch.json': '6661fb43e137567eeed41c68126aee8d974b2161737ada0b1069d259cca3d612',
    ROOT / 'outputs/research/fresh629-root-terminal-01/session54334.json': '97b6568848785bbf720bb1782086dbc385b6053577921765ec76694c9a293209',
    OLD / 'host/launch-receipt.json': '826d07cfd7a5e268134628ec8fed3f577a2b596a8a4ab5fc18554a31e034305e',
    OLD / 'host-plan.json': '960c5e1ef7e75d05b91f253d152a4d01fd5c07716091c48868c57f86ba74fa5d',
    OLD / 'freeze-manifest.json': '599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169',
    OLD / 'inputs/native-plan.json': 'dc8a2994f246a221d2b745a355dd8512964434397db9e47b9ed6131bbb06f287',
    OLD / 'control/finalize_fresh629.py': FINALIZER_SHA,
    BASE / 'writer-mapping-audit-final-01/analysis.json': 'e8c82545397d2ddff97738d336a39f14672d7e6b4100d22783a6fec4d76be06e',
    BASE / 'writer-mapping-audit-final-01/final-original-worker-mappings.json': '7cf07f84f5004c463f8043866cce7ea3bbe9afd8c88f6fc344f42315608346cf',
    BASE / 'missing-four-preparation/run.py': 'edb80857753566e1d3b4f4c9e73093bb5a36ace96340b65e7dd8ce21c02870e7',
    BASE / 'missing-four-preparation/subset_check.py': 'ff3502675b28d24b9ae4c831b35442ff8eaff19269a450b52d065aada0fa2496',
    BASE / 'missing-four-preparation/contract.json': '98ace89ffbaf0716c203104bac3e4616eda7593776d142cb650181079ee0f83f',
}


class Waiting(Exception):
    pass


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and path.is_relative_to(ROOT)
            and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe proof path: ' + str(path))
    return path


def fingerprint(path):
    path = safe(path)
    initial = path.stat()
    require(stat.S_ISREG(initial.st_mode), 'Regular proof file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    final = path.stat()
    require((initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
            == (final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns), 'Proof changed during read')
    return {'path': str(path), 'bytes': final.st_size, 'sha256': digest.hexdigest()}


def file_set(root):
    root = safe(root)
    result = set()
    for path in root.rglob('*'):
        safe(path)
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), 'Special file in frozen proof tree')
    return result


class Evidence:
    def __init__(self):
        self.records = {}

    def fp(self, path, expected=None):
        row = fingerprint(path)
        require(self.records.get(row['path'], row) == row, 'Previously read proof changed')
        if expected is not None:
            require(row['sha256'] == expected['sha256'] and row['bytes'] == expected['bytes'], 'Referenced proof bytes differ')
        self.records[row['path']] = row
        return row

    def read(self, path, expected=None):
        row = self.fp(path, expected)
        raw = safe(path).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'JSON changed during read')
        return json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))

    def finish(self):
        for path, row in self.records.items():
            require(fingerprint(path) == row, 'Evidence changed before admission: ' + path)


def mapped(path, output=OLD / 'outputs'):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Unsafe namespace proof path')
    for prefix, target in [('/workspace/php_parkour', OLD / 'source'), ('/data', OLD / 'inputs'),
                           ('/outputs', output), ('/validation', BASE / 'cpu-final-validation')]:
        if path.is_relative_to(prefix):
            return safe(target / path.relative_to(prefix))
    return safe(path)


def referenced(evidence, row, output=OLD / 'outputs'):
    return evidence.fp(mapped(row['path'], output), row)


def proc_identity(raw):
    fields = raw.rsplit(')', 1)[1].split()
    return {'state': fields[0], 'birth': int(fields[19])}


def same_process_live(pid, birth):
    try:
        first = Path('/proc', str(pid), 'stat').read_text()
        final = Path('/proc', str(pid), 'stat').read_text()
    except (FileNotFoundError, ProcessLookupError):
        return False
    a, b = proc_identity(first), proc_identity(final)
    require(a['birth'] == b['birth'], 'PID changed during liveness read')
    return a['birth'] == birth and a['state'] != 'Z'


class LocalDocker(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def docker_get(path):
    require(os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock') == 'unix:///var/run/docker.sock',
            'Only the reviewed local Docker socket is allowed')
    connection = LocalDocker('localhost', timeout=15)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        raw = response.read()
        require(response.status == 200, 'Read-only Docker identity unavailable: ' + str(response.status))
        return json.loads(raw)
    finally:
        connection.close()


def host_children_gone(cids):
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            initial = proc_identity((directory / 'stat').read_text())
            cgroup = (directory / 'cgroup').read_text()
            components = {p for line in cgroup.splitlines() for p in line.split(':', 2)[-1].split('/')}
            matched = any(cid in components or 'docker-' + cid + '.scope' in components for cid in cids)
            if not matched:
                continue
            final = proc_identity((directory / 'stat').read_text())
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(initial['birth'] == final['birth'], 'Owned PID reused during read')
        require(final['state'] == 'Z', 'Owned native/container process is still live: ' + directory.name)


def stopped(stop, cid, gpu):
    require(re.fullmatch('[0-9a-f]{64}', cid) and stop['container_id'] == cid
            and stop['running_after_stop'] is False and not stop.get('remaining_owned_host_children', [])
            and not stop.get('remaining_host_children', []),
            'Stopped proof must bind the exact owned CID')
    before, after = stop['before'], stop['after']
    require(before['Id'] == after['Id'] == cid and before['Image'] == after['Image'] == IMAGE
            and before['State']['StartedAt'] == after['State']['StartedAt']
            and bool(after['State']['StartedAt']) and after['State']['Running'] is False,
            'Recorded container birth/image/stop identity differs')
    current = docker_get('/containers/' + cid + '/json')
    require(current['Id'] == cid and current['Image'] == IMAGE
            and current['State']['StartedAt'] == after['State']['StartedAt']
            and current['State']['Running'] is False and not current['State'].get('Restarting')
            and not current['State'].get('Paused'), 'Owned container restarted or remains running')
    for key in ('Mounts', 'Name'):
        require(current[key] == after[key], 'Owned container static identity differs')
    for key, expected in after['HostConfig'].items():
        require(current['HostConfig'].get(key) == expected, 'Owned container isolation differs')
    for key, expected in after['Config'].items():
        require(current['Config'].get(key) == expected, 'Owned container command differs')
    host = current['HostConfig']
    require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and not host.get('PidMode')
            and host['Init'] is True and not host['Privileged'], 'Expected private isolated container')
    requests = host.get('DeviceRequests') or []
    if gpu:
        require(len(requests) == 1 and requests[0]['DeviceIDs'] == [GPU] and host['ShmSize'] == 8589934592,
                'Physical GPU UUID differs')
    else:
        require(not requests and host['Runtime'] == 'runc', 'CPU proof container exposes GPU')
    require(all(not mount['RW'] for mount in current['Mounts']
                if mount['Destination'] in ('/workspace/php_parkour', '/data', '/control')), 'Source/input/control must remain RO')
    if cid == CID:
        require(current['State']['StartedAt'] == STARTED, 'Original GPU container birth differs')
    return {'container_id': cid, 'started_at': current['State']['StartedAt'], 'image_id': IMAGE, 'running': False}


def original_proof(evidence):
    for path, digest in PINS.items():
        require(evidence.fp(path)['sha256'] == digest, 'Pinned historical evidence differs: ' + str(path))
    tool = evidence.read(ROOT / 'outputs/research/fresh629-root-terminal-01/session54334.json')
    require(tool['session_id'] == 54334 and tool['exit_code'] == tool['actual_tool_result']['exit_code'] == 143
            and tool['normal_zero_exit_verified'] is False, 'Original real143 must remain preserved')
    old = evidence.read(OLD / 'host/launch-receipt.json')
    require(old['status'] == 'running' and old['container_id'] == CID and old['snapshot_files_verified'] == 5206,
            'Never replace the original incomplete host receipt')
    freeze = evidence.read(OLD / 'freeze-manifest.json')['files']
    require(len(freeze) == 5206, 'Expected original5206 freeze records')
    groups = {'source': set(), 'control': set(), 'inputs': set()}
    for row in freeze:
        relative = Path(row['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe original freeze path')
        evidence.fp(OLD / relative, row)
        if relative.parts[0] in groups:
            groups[relative.parts[0]].add(Path(*relative.parts[1:]).as_posix())
    require({k: len(v) for k, v in groups.items()} == {'source': 5184, 'control': 4, 'inputs': 5}, 'Frozen groups differ')
    for key, names in groups.items():
        require(file_set(OLD / key) == names, 'Extra/missing frozen source/control/input file')
    for prefix in ('frozen', 'original-host'):
        before = evidence.read(BASE / ('manager/' + prefix + '-before.json'))
        after = evidence.read(BASE / ('manager/' + prefix + '-after.json'))
        require(before == after, 'Manager original bytes before/after differ')
        for key, row in before.items():
            path = OLD / 'host' / key if prefix == 'original-host' else Path(key)
            evidence.fp(path, row)
        if prefix == 'original-host':
            require(file_set(OLD / 'host') == set(before), 'Original host evidence file-set differs')
    return old, evidence.read(OLD / 'inputs/native-plan.json')


def manager_proof(evidence, old, plan):
    receipt = evidence.read(BASE / 'manager/receipt.json')
    if receipt['status'] not in ('recovered_native_and_cpu_completed_with_host_observer_gap', 'failed'):
        raise Waiting('Recovery manager has not completed naturally')
    require(receipt['status'] == 'recovered_native_and_cpu_completed_with_host_observer_gap'
            and not receipt['errors'] and not receipt['read_errors']
            and receipt['original_session_exit_code'] == 143
            and receipt['original_host_transaction_normal_exit_verified'] is False
            and receipt['original_observer_whole_scope_complete'] is False
            and receipt['host_observer_gap_preserved'] is True
            and receipt['native_restarted'] is False and receipt['new_native_started'] is False,
            'Recovery manager failed or concealed original host gap')
    evidence.fp(BASE / 'manage.py', receipt['helper'])
    process = evidence.read(BASE / 'manager-process-start.json')
    exited = evidence.read(BASE / 'manager-process-exit.json')
    expected_argv = ['/usr/bin/python3', '-B', str(BASE / 'manage.py'), '--root-authorized-adopt']
    require(process['argv'] == exited['argv'] == expected_argv and process['pid'] == exited['pid'] == 2007976
            and process['helper_sha256'] == MANAGER_SHA and process['boot_id'] == BOOT
            and proc_identity(process['stat'])['birth'] == 106799627
            and exited['actual_wait_returncode'] == 0 and exited['original_session54334_exit_code'] == 143
            and not same_process_live(2007976, 106799627), 'Recovery launcher did not observe actual manager exit0')
    terminal = receipt['original_daemon_terminal']['exec']
    require(terminal['ID'] == EXEC_ID and terminal['ContainerID'] == CID and terminal['Running'] is False
            and terminal['ExitCode'] == 0 and terminal['ProcessConfig']['entrypoint'] == old['native_argv'][3]
            and terminal['ProcessConfig']['arguments'] == old['native_argv'][4:]
            and terminal['ProcessConfig']['tty'] is False and terminal['ProcessConfig']['privileged'] is False,
            'Original native daemon exact exec did not actually exit0')
    observer = receipt['recovery_observer_stop']
    summary = evidence.read(BASE / 'observer/summary.json', observer['summary'])
    require(observer['original_pid'] == 1914028 and observer['original_birth'] == 106696455
            and observer['original_birth_no_longer_present'] is True and observer['os_returncode_observed'] is False
            and not same_process_live(1914028, 106696455)
            and summary['identity']['container_id'] == CID and summary['identity']['image_id'] == IMAGE
            and summary['identity']['started_at'] == STARTED and summary['stop_reason'] == 'stop_file'
            and not summary['errors'], 'Recovery observer segment summary/disappearance differs')
    matrix = evidence.read(OLD / 'outputs/all-configs/matrix.json', receipt['terminal_matrix'])
    require(matrix['status'] == 'completed' and matrix['completed_configurations'] == 629
            and matrix['completed_scenarios'] == 17 and matrix['configuration_coverage_complete'] is True
            and matrix['plan_sha256'] == plan['plan_sha256'] and len(matrix['selections']) == 629
            and matrix['last_invocation']['case_ids'] == [] and matrix['last_invocation']['case_limit'] is None
            and matrix['last_invocation']['resume'] is False and matrix['last_invocation']['requested_configurations'] == 629,
            'Original native matrix not unfiltered completed629')
    post = evidence.read(BASE / 'cpu-final-validation/full-validation.json', receipt['full_validation'])
    require(receipt['cpu_finalizer_sha256'] == FINALIZER_SHA and receipt['cpu_validation_returncode'] == 0
            and receipt['cpu_cli_returncode_after_stop'] == 0
            and receipt['snapshot_files_verified_before'] == receipt['snapshot_files_verified_after'] == 5206
            and receipt['original_inputs_and_host_bytes_unchanged'] is True
            and post['status'] == 'passed' and post['configurations'] == 629 and post['scenarios'] == 17
            and post['worker_exit0_empty_group_count'] == 1258 and post['full_decoded_mp4_count'] == 629
            and post['native_plan_sha256'] == plan['plan_sha256']
            and post['matrix_sha256'] == receipt['terminal_matrix']['sha256'], 'Original CPU629/1258/629 validation differs')
    cpu_cases(evidence, plan, matrix, post, OLD / 'outputs', 629)
    referenced(evidence, receipt['cpu_stdout']); referenced(evidence, receipt['cpu_stderr'])
    containers = [stopped(receipt['adopted_gpu_container_stop'], CID, True),
                  stopped(receipt['owned_cpu_container_stop'], receipt['cpu_container_id'], False)]
    return receipt, containers


def cpu_cases(evidence, plan, matrix, post, output, count, selected=None):
    expected = plan['selections'] if selected is None else [case for case in plan['selections'] if case['case_id'] in selected]
    actual = matrix['selections'] if selected is None else [case for case in matrix['selections'] if case['case_id'] in selected]
    require(len(expected) == len(actual) == len(post['cases']) == count
            and [c['case_id'] for c in expected] == [c['case_id'] for c in actual] == [c['case_id'] for c in post['cases']],
            'CPU/native case identity order differs')
    for wanted, case, checked in zip(expected, actual, post['cases']):
        require(all(case.get(k) == v for k, v in wanted.items()) and case['status'] == 'completed'
                and len(case['attempts']) == 1 and case['attempts'][0]['status'] == 'completed'
                and case['attempts'][0]['returncode'] == checked['parent_returncode'] == 0
                and checked['worker_exit0_empty_groups'] == 2 and checked['policy_ticks'] == 500,
                'Once-only native case/CPU verdict differs')
        directory = mapped(case['attempts'][0]['output'], output)
        require(directory.is_relative_to(output), 'Case output escaped its own cohort')
        require(evidence.fp(directory / 'result.json')['sha256'] == checked['native_result_sha256'], 'Native result differs from CPU postcheck')
        require(len(checked['worker_receipts']) == 3 and len(checked['videos']) == 1, 'Three worker receipts/one decoded MP4 required')
        for row in checked['worker_receipts']:
            require(mapped(row['path'], output).parent == directory, 'Worker receipt escaped its case')
            referenced(evidence, row, output)
        video = checked['videos'][0]
        require(video['returncode'] == 0 and video['full_decode'] is True
                and mapped(video['path'], output).is_relative_to(directory), 'Actual full video decode missing')
        referenced(evidence, video, output)


def historical_mappings(evidence, plan):
    audit = evidence.read(BASE / 'writer-mapping-audit-final-01/analysis.json')
    rows = evidence.read(BASE / 'writer-mapping-audit-final-01/final-original-worker-mappings.json', audit['worker_mapping_rows'])
    require(audit['status'] == 'original1250_unique_exact8_historical_mapping_gaps_verified'
            and audit['completed_cases'] == 629 and audit['expected_completed_worker_entries'] == 1258
            and audit['exactly_one_writer_mapping_workers'] == 1250 and audit['missing_mapping_workers'] == 8
            and audit['missing_mapping_cases'] == 4 and audit['missing_case_ids'] == CASE_IDS
            and audit['ambiguous_mapping_workers'] == 0 and not audit['identity_errors']
            and audit['unique_host_process_birth_mappings'] == audit['unique_host_thread_birth_mappings'] == 1250,
            'Closed original streams must retain exact8 historical gaps')
    identity = audit['container_identity']
    require(identity['container_id'] == CID and identity['image_id'] == IMAGE and identity['started_at'] == STARTED,
            'Historical observer container identity differs')
    require([row['name'] for row in audit['segments']] == ['original', 'recovery'], 'Exactly the two original observation segments required')
    for row in audit['segments']:
        require(row['whole_stream'] is True and row['trailing_incomplete_line_bytes'] == 0, 'Whole closed observation stream required')
        evidence.fp(row['path'], row)
    for row in audit['proofs'].values():
        evidence.fp(row['path'], row)
    matrix = evidence.read(OLD / 'outputs/all-configs/matrix.json')
    index = {case['case_id']: case for case in matrix['selections']}
    expected = [(case['case_id'], role) for case in plan['selections'] for role in ('simulator', 'inference')]
    require([(row['case_id'], row['role']) for row in rows] == expected, 'Historical1258 worker identity/order differs')
    missing, seen = [], set()
    for row in rows:
        case, role = index[row['case_id']], row['role']
        directory = mapped(case['attempts'][0]['output'])
        entry_path = directory / (role + '-process-start.json')
        require(safe(row['entry']['path']) == entry_path and row['native_output'] == case['attempts'][0]['output'],
                'Historical mapping is bound to a different attempt')
        entry = evidence.read(entry_path, row['entry'])
        evidence.fp(directory / 'case-evidence.json', row['case_evidence'])
        process = entry['process']
        require(entry['role'] == role and process['pid'] == row['native_pid']
                and process['start_time_clock_ticks'] == row['native_birth'], 'Historical native worker birth differs')
        if row['case_id'] in CASE_IDS:
            require(row['mapping_status'] == 'missing_historical_observation'
                    and row['mapping_count'] == 0 and row['mappings'] == [], 'Do not replace original missing births with supplement births')
            missing.append(row)
            continue
        require(row['mapping_status'] == 'unique_observed' and row['mapping_count'] == len(row['mappings']) == 1,
                'Original non-gap worker must have one unique observed mapping')
        writer = row['mappings'][0]['identity']
        require(writer['role'] == role and writer['worker_output'] == row['native_output']
                and writer['container_tgid'] == row['native_pid'] and writer['owner_start_time_clock_ticks'] == row['native_birth']
                and writer['nspid'][0] == writer['host_tid'] and writer['nspid'][-1] == writer['container_tid']
                and writer['nstgid'][0] == writer['host_tgid'] and writer['nstgid'][-1] == row['native_pid'],
                'Historical hostwriter PID/owner/namespace identity differs')
        key = writer['host_tid'], writer['start_time_clock_ticks']
        require(key not in seen, 'Historical writer birth duplicated')
        seen.add(key)
    require(len(seen) == 1250 and missing == audit['missing_workers'], 'Historical exact missing-eight set differs')


def four_proof(evidence, manager, plan):
    receipt = evidence.read(FOUR / 'host/launch-receipt.json')
    if receipt['status'] not in ('completed', 'failed'):
        raise Waiting('Four independent missing-writer attempts are not terminal')
    require(receipt['status'] == 'completed' and not receipt['errors']
            and receipt['image_id'] == IMAGE and receipt['gpu_uuid'] == GPU and receipt['case_ids'] == CASE_IDS
            and receipt['original_session54334_exit_code'] == 143 and receipt['historical_host_observer_gap_preserved'] is True
            and receipt['separate_attempts_for_original_missing_observations'] is True
            and receipt['native_started'] is True
            and all(receipt[key] == 0 for key in ('native_returncode', 'observer_returncode', 'cpu_plan_returncode', 'cpu_validation_returncode'))
            and receipt['source_snapshot_files_verified_before'] == receipt['source_snapshot_files_verified_after'] == 5206
            and receipt['original_inputs_and_controls_unchanged'] is True
            and receipt['worker_exit0_empty_group_count'] == receipt['host_writer_mapping_count'] == 8
            and receipt['full_decoded_mp4_count'] == 4, 'Four-case independent execution incomplete/failed')
    prep = BASE / 'missing-four-preparation'
    for key, path in [('helper', prep / 'run.py'), ('subset_checker', prep / 'subset_check.py'), ('contract', prep / 'contract.json')]:
        evidence.fp(path, receipt[key])
    require(receipt['contract_sha256'] == PINS[prep / 'contract.json'], 'Four-case producer contract differs')
    prior_paths = {'receipt': BASE / 'manager/receipt.json', 'process_start': BASE / 'manager-process-start.json',
                   'process_exit': BASE / 'manager-process-exit.json', 'full_validation': BASE / 'cpu-final-validation/full-validation.json'}
    for key, path in prior_paths.items():
        evidence.fp(path, receipt['manager_prerequisite'][key])
    for key, path in [('analysis', BASE / 'writer-mapping-audit-final-01/analysis.json'),
                      ('worker_rows', BASE / 'writer-mapping-audit-final-01/final-original-worker-mappings.json')]:
        evidence.fp(path, receipt['historical_gap_audit'][key])
    before = evidence.read(FOUR / 'host/frozen-before.json', receipt['frozen_before'])
    after = evidence.read(FOUR / 'host/frozen-after.json', receipt['frozen_after'])
    require(before == after == evidence.read(BASE / 'manager/frozen-before.json'), 'Supplement changed original frozen inputs')
    contract = evidence.read(prep / 'contract.json')
    require(contract['proposed_new_host_base'] == str(FOUR) and contract['expected_native_result']['requested_cases'] == CASE_IDS,
            'Four-case source/output identity differs')
    # Compare the actual CPU-produced plan to the hard-pinned original, changing
    # only its independent output namespace and the resulting self identity.
    def relocate(value):
        if isinstance(value, str):
            prefix = '/outputs/all-configs'
            return '/outputs/missing-four' + value[len(prefix):] if value == prefix or value.startswith(prefix + '/') else value
        if isinstance(value, list):
            return [relocate(child) for child in value]
        if isinstance(value, dict):
            return {key: relocate(child) for key, child in value.items()}
        return value
    expected = relocate(plan)
    expected.pop('plan_sha256')
    expected['plan_sha256'] = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    actual = evidence.read(FOUR / 'outputs/missing-four-plan.json', receipt['native_plan'])
    require(actual == expected and actual['plan_sha256'] == receipt['native_plan_sha256'], 'Supplement model/geometry/source/launch drift')
    plan_check = evidence.read(FOUR / 'outputs/plan-validation.json', receipt['plan_validation'])
    require(plan_check['status'] == 'passed' and plan_check['mode'] == 'plan'
            and plan_check['native_plan_sha256'] == actual['plan_sha256'] and plan_check['selected_case_ids'] == CASE_IDS,
            'Actual CPU plan validation unavailable')
    matrix = evidence.read(FOUR / 'outputs/missing-four/matrix.json', receipt['native_matrix'])
    require(matrix['status'] == 'completed_subset' and matrix['completed_configurations'] == 4
            and matrix['completed_scenarios'] == 1 and matrix['configuration_coverage_complete'] is False
            and len(matrix['selections']) == 629 and matrix['last_invocation']['case_ids'] == CASE_IDS
            and matrix['last_invocation']['case_limit'] is None and matrix['last_invocation']['resume'] is False
            and matrix['last_invocation']['requested_configurations'] == 4
            and all(matrix.get(k) == v for k, v in actual.items() if k not in ('status', 'selections')), 'Actual fresh subset identity differs')
    for wanted, case in zip(actual['selections'], matrix['selections']):
        require(all(case.get(k) == v for k, v in wanted.items()), 'Supplement case source identity differs')
        if case['case_id'] not in CASE_IDS:
            require(not case.get('attempts') and 'status' not in case, 'Unselected case was attempted')
    post = evidence.read(FOUR / 'outputs/full-validation.json', receipt['cpu_post'])
    require(post['status'] == 'passed' and post['mode'] == 'final' and post['configurations'] == 4
            and post['worker_exit0_empty_group_count'] == 8 and post['full_decoded_mp4_count'] == 4
            and post['native_plan_sha256'] == actual['plan_sha256'] and post['matrix_sha256'] == receipt['native_matrix']['sha256'],
            'Actual subset CPU8worker/4decode proof differs')
    cpu_cases(evidence, actual, matrix, post, FOUR / 'outputs', 4, CASE_IDS)
    commands = receipt['commands']
    require([row['name'] for row in commands] == ['cpu-plan', 'cpu-plan-check', 'native', 'cpu-final-check']
            and all(row['returncode'] == row['returncode_after_cleanup'] == 0 for row in commands), 'Actual four-command process exits incomplete')
    require(commands[0]['argv'] == ['docker', 'exec', receipt['cpu_plan_container_id'], *contract['cpu_plan_argv']]
            and commands[2]['argv'] == ['docker', 'exec', receipt['gpu_container_id'], *contract['native_argv']], 'Actual native/CPU plan argv differs')
    common = ['--plan', '/outputs/missing-four-plan.json', '--matrix', '/outputs/missing-four/matrix.json']
    cases_argv = [value for case_id in CASE_IDS for value in ('--case-id', case_id)]
    for row, cid, mode, filename in [(commands[1], receipt['cpu_plan_container_id'], 'plan', 'plan-validation.json'),
                                     (commands[3], receipt['cpu_final_container_id'], 'final', 'full-validation.json')]:
        require(row['argv'] == ['docker', 'exec', '-i', cid, '/opt/php/bin/inference-python', '-', mode,
                                *common, '--output', '/outputs/' + filename, *cases_argv]
                and 'stdin_source' in row, 'Actual CPU checker argv/stdin differs')
    for row in commands:
        referenced(evidence, row['stdout'], FOUR / 'outputs'); referenced(evidence, row['stderr'], FOUR / 'outputs')
        if 'stdin_source' in row:
            require(evidence.fp(prep / 'subset_check.py', row['stdin_source'])['sha256'] == PINS[prep / 'subset_check.py'], 'CPU checker stdin bytes differ')
        birth = row['host_cli_identity']['birth']
        require(not same_process_live(row['host_cli_pid'], birth), 'Supplement Docker CLI has not exited')
    summary = evidence.read(FOUR / 'host/observer/summary.json', receipt['observer_summary'])
    identity = summary['identity']
    require(summary['stop_reason'] == 'stop_file' and summary['mapping_scope_complete'] is True and not summary['errors']
            and summary['source_sha256'] == 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0'
            and identity['container_id'] == receipt['gpu_container_id'] and identity['image_id'] == IMAGE
            and identity['started_at'] == receipt['owned_gpu_container_stop']['after']['State']['StartedAt'], 'Supplement observer scope/identity differs')
    require(not same_process_live(receipt['observer_host_pid'], receipt['observer_host_identity']['birth']), 'Supplement observer still live')
    mappings = receipt['host_native_mappings']
    require([(row['case_id'], row['role']) for row in mappings] == [(case_id, role) for case_id in CASE_IDS for role in ('simulator', 'inference')],
            'Supplement exactly8 worker mapping identities required')
    cases = {row['case_id']: row for row in matrix['selections'] if row['case_id'] in CASE_IDS}
    seen = set()
    for row in mappings:
        case, role = cases[row['case_id']], row['role']
        directory = mapped(case['attempts'][0]['output'], FOUR / 'outputs')
        entry_path = directory / (role + '-process-start.json')
        entry = evidence.read(entry_path)
        require(evidence.fp(entry_path)['sha256'] == row['entry_sha256'] and len(row['mappings']) == 1, 'Supplement entry↔writer seal differs')
        writer = row['mappings'][0]
        process = entry['process']
        require(entry['role'] == writer['role'] == role and writer['worker_output'] == case['attempts'][0]['output']
                and writer['container_tgid'] == process['pid'] and writer['owner_start_time_clock_ticks'] == process['start_time_clock_ticks']
                and writer['nspid'][0] == writer['host_tid'] and writer['nspid'][-1] == writer['container_tid']
                and writer['nstgid'][0] == writer['host_tgid'] and writer['nstgid'][-1] == process['pid']
                and writer in summary['command_writer_mappings'], 'Supplement actual hostwriter birth differs')
        key = writer['host_tid'], writer['start_time_clock_ticks']
        require(key not in seen, 'Supplement writer birth duplicated')
        seen.add(key)
    containers = [stopped(receipt['owned_gpu_container_stop'], receipt['gpu_container_id'], True),
                  stopped(receipt['owned_plan_container_stop'], receipt['cpu_plan_container_id'], False),
                  stopped(receipt['owned_final_container_stop'], receipt['cpu_final_container_id'], False)]
    return receipt, containers


def previous_recovered():
    """Return a distinct proof; never pretends the old root transaction passed."""
    evidence = Evidence()
    try:
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'Host boot differs from actual recovery')
        old, plan = original_proof(evidence)
        manager, containers = manager_proof(evidence, old, plan)
        historical_mappings(evidence, plan)
        supplement, new_containers = four_proof(evidence, manager, plan)
        containers += new_containers
        cids = [row['container_id'] for row in containers]
        require(len(cids) == len(set(cids)) == 5, 'Five distinct exact original/recovery/supplement CIDs required')
        host_children_gone(cids)
        evidence.finish()
        return {'schema_version': 1, 'status': 'recovered_previous_ready', 'ready': True,
                'original_session54334_exit_code': 143, 'original_root_normal_exit_verified': False,
                'original_host_observer_gap_preserved': True, 'original_daemon_exit_code': 0,
                'original_configurations': 629, 'original_clean_workers': 1258, 'original_full_video_decodes': 629,
                'original_unique_host_writer_mappings': 1250, 'original_missing_historical_writer_mappings': 8,
                'separate_supplement_case_ids': CASE_IDS, 'supplement_clean_workers': 8,
                'supplement_host_writer_mappings': 8, 'supplement_full_video_decodes': 4,
                'containers_stopped': containers, 'owned_host_children_absent': True,
                'gpu_mutex_acquired': False, 'gpu_idle_verified': False, 'quality_verified': False,
                'gate': fingerprint(__file__), 'evidence': evidence.records,
                'scope': 'Recovered original native+CPU run and separate missing-writer supplement; original root143 and historical observation gap remain permanent.'}
    except (FileNotFoundError, Waiting) as pending:
        return {'schema_version': 1, 'status': 'waiting', 'ready': False, 'reason': str(pending),
                'original_session54334_exit_code': 143, 'writes': False, 'lock_acquired': False, 'native_started': False}


if __name__ == '__main__':
    print(json.dumps(previous_recovered(), indent=2, allow_nan=False))
