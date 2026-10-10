#!/usr/bin/env python3
"""Root-operated, once-only independent acceptance of four missing observations.

Written only. Root must review and execute explicitly after the recovery manager
actually exits0. This never changes old native outputs, controls, receipts or143.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
REC = ROOT / 'outputs/research/fresh629-recovery-01'
PREP = REC / 'missing-four-preparation'
BASE = REC / 'missing-four-run-01'
HOST = BASE / 'host'
MANAGER = REC / 'manage.py'
MANAGER_SHA = '3fc5a0c45bb5efb48f7c45514a885a0ea986ddae2dd309c819186aec582cccec'
CONTRACT_SHA = '98ace89ffbaf0716c203104bac3e4616eda7593776d142cb650181079ee0f83f'
CORE_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
OBSERVER_SHA = 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0'
CHECKER_SHA = 'ff3502675b28d24b9ae4c831b35442ff8eaff19269a450b52d065aada0fa2496'
GAP_ANALYSIS_SHA = 'e8c82545397d2ddff97738d336a39f14672d7e6b4100d22783a6fec4d76be06e'
GAP_ROWS_SHA = '7cf07f84f5004c463f8043866cce7ea3bbe9afd8c88f6fc344f42315608346cf'
NAMES = {'plan': 'php-missing-four-cpu-plan-01', 'gpu': 'php-missing-four-gpu-01',
         'final': 'php-missing-four-cpu-final-01'}


def require(value, message):
    if not value:
        raise ValueError(message)


def module():
    # Import only this exact reviewed stdlib module; its CLI guard stays false.
    import hashlib
    require(hashlib.sha256(MANAGER.read_bytes()).hexdigest() == MANAGER_SHA, 'Frozen manager source changed')
    spec = importlib.util.spec_from_file_location('_missing_four_readonly_contract', MANAGER)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def same(row, m):
    require(m.fp(row['path']) == row, 'Bound file changed: ' + row['path'])


def manager_ready(m):
    """Read existing true completion; never wait, synthesize or repair a receipt."""
    paths = {key: REC / path for key, path in (
        ('receipt', 'manager/receipt.json'), ('process_start', 'manager-process-start.json'),
        ('process_exit', 'manager-process-exit.json'), ('full_validation', 'cpu-final-validation/full-validation.json'))}
    fingerprints = {key: m.fp(path) for key, path in paths.items()}
    receipt, start, end, post = (m.read(paths[key]) for key in paths)
    require(receipt['status'] == 'recovered_native_and_cpu_completed_with_host_observer_gap'
            and receipt['helper']['sha256'] == MANAGER_SHA, 'Recovery manager has not truly completed')
    require(start['helper_sha256'] == MANAGER_SHA and start['pid'] == end['pid']
            and start['argv'] == end['argv'] == ['/usr/bin/python3', '-B', str(MANAGER), '--root-authorized-adopt']
            and end['actual_wait_returncode'] == 0 and end['original_session54334_exit_code'] == 143,
            'Original manager parent did not observe actual child0')
    require(not receipt['errors'] and not receipt['read_errors'] and receipt['cpu_validation_returncode'] == 0
            and receipt['original_inputs_and_host_bytes_unchanged'] is True
            and receipt['snapshot_files_verified_before'] == receipt['snapshot_files_verified_after'] == 5206,
            'Recovery manager acceptance is incomplete')
    terminal = receipt['original_daemon_terminal']['exec']
    require(terminal['ID'] == m.EXEC_ID and terminal['ContainerID'] == m.CID
            and terminal['Running'] is False and terminal['ExitCode'] == 0,
            'Original native daemon exit0 unavailable')
    native_argv = m.read(m.OLD / 'host/launch-receipt.json')['native_argv']
    require(terminal['ProcessConfig']['entrypoint'] == native_argv[3]
            and terminal['ProcessConfig']['arguments'] == native_argv[4:], 'Captured original daemon arguments differ')
    require(receipt['full_validation'] == fingerprints['full_validation']
            and post['status'] == 'passed' and post['configurations'] == 629
            and post['scenarios'] == 17 and post['worker_exit0_empty_group_count'] == 1258
            and post['full_decoded_mp4_count'] == 629 and len(post['cases']) == 629,
            'Original real CPU629/1258/629 validation missing')
    require(receipt['terminal_matrix'] == m.fp(m.OLD / 'outputs/all-configs/matrix.json')
            and post['matrix_sha256'] == receipt['terminal_matrix']['sha256'], 'Original native matrix changed')
    for key, cid, cpu in (('adopted_gpu_container_stop', m.CID, False),
                          ('owned_cpu_container_stop', receipt['cpu_container_id'], True)):
        stop = receipt[key]
        require(stop['container_id'] == cid and stop['running_after_stop'] is False
                and stop['after']['Id'] == cid and not stop['after']['State']['Running'],
                'Prior stop receipt is not bound to its exact CID')
        actual = m.inspect(cid)
        m.container(actual, cpu)
        require(not actual['State']['Running']
                and actual['State']['StartedAt'] == stop['after']['State']['StartedAt']
                and not m.host_live(cid), 'Prior exact container is not actually stopped/empty')
    for row in fingerprints.values():
        same(row, m)
    return fingerprints


def gpu_idle(m):
    values = m.call(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader']).strip().splitlines()
    require(values.count(m.GPU) == 1, 'Exact physical GPU UUID not uniquely present')
    raw = m.call(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'])
    require(not any(line.split(',')[0].strip() == m.GPU for line in raw.splitlines() if line.strip()),
            'GPU is occupied; never stop a foreign process')
    return {'gpu_uuid': m.GPU, 'compute_processes': []}


def persist(m, result):
    m.write(HOST / 'launch-receipt.json', result)


def env(cpu):
    value = {'PHP_DOCKER': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'WANDB_MODE': 'disabled',
             'WANDB_DISABLED': 'true', 'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
             'TRANSFORMERS_OFFLINE': '1', 'MUJOCO_GL': 'egl', 'MUJOCO_EGL_DEVICE_ID': '0'}
    if cpu:
        value.update(CUDA_VISIBLE_DEVICES='', NVIDIA_VISIBLE_DEVICES='void')
    else:
        value['NVIDIA_DRIVER_CAPABILITIES'] = 'compute,utility,graphics'
    return value


def create_argv(m, contract, role):
    cpu = role != 'gpu'
    argv = ['docker', 'create', '--name', NAMES[role], '--network', 'none', '--ipc', 'private',
            '--init', '--shm-size', '1g' if cpu else '8g', '--workdir', '/workspace/php_parkour',
            '--entrypoint', '/bin/bash']
    argv += ['--runtime', 'runc'] if cpu else ['--gpus', 'device=' + m.GPU]
    for key, value in env(cpu).items():
        argv += ['--env', key + '=' + value]
    for row in contract['namespace_mounts']:
        argv += ['--mount', 'type=bind,src=' + row['source'] + ',dst=' + row['destination']
                 + (',readonly' if row['readonly'] else '')]
    return argv + [m.IMAGE, '-lc', 'exec sleep infinity']


def verify_container(m, contract, owned, running=None):
    value = m.inspect(owned['cid'])
    cpu = owned['role'] != 'gpu'
    host, config = value['HostConfig'], value['Config']
    expected = {(row['source'], row['destination'], not row['readonly'], 'bind')
                for row in contract['namespace_mounts']}
    actual = {(row['Source'], row['Destination'], row['RW'], row['Type']) for row in value['Mounts']}
    require(value['Name'] == '/' + NAMES[owned['role']] and actual == expected and len(value['Mounts']) == 5,
            'Exact own name/five mounts differ')
    require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and not host.get('PidMode')
            and not host['Privileged'] and host['Init'] is True
            and host['ShmSize'] == (1073741824 if cpu else 8589934592)
            and config['WorkingDir'] == '/workspace/php_parkour'
            and config['Entrypoint'] == ['/bin/bash'] and config['Cmd'] == ['-lc', 'exec sleep infinity'],
            'Own container isolation/process contract differs')
    actual_env = dict(row.split('=', 1) for row in config['Env'] if '=' in row)
    require(all(actual_env.get(k) == v for k, v in env(cpu).items()), 'Own environment differs')
    requests = host.get('DeviceRequests') or []
    require((cpu and host['Runtime'] == 'runc' and not requests) or
            (not cpu and len(requests) == 1 and requests[0].get('DeviceIDs') == [m.GPU]), 'Own GPU isolation differs')
    if owned.get('started_at') is not None:
        require(value['State']['StartedAt'] == owned['started_at'], 'Own container was restarted')
    if running is not None:
        require(value['State']['Running'] is running, 'Unexpected own running state')
    return value


def start(m, contract, role, owned, result):
    argv = create_argv(m, contract, role)
    result[role + '_create_argv'] = argv
    persist(m, result)
    cid = m.call(argv).strip()
    require(re.fullmatch('[0-9a-f]{64}', cid), 'Create did not return exact full own CID')
    item = {'cid': cid, 'role': role, 'started_at': None, 'stop': None}
    owned.append(item)  # Cleanup owns it before any diagnostic or start operation.
    result[{'gpu': 'gpu_container_id', 'plan': 'cpu_plan_container_id', 'final': 'cpu_final_container_id'}[role]] = cid
    verify_container(m, contract, item, False)
    m.call(['docker', 'start', cid])
    info = verify_container(m, contract, item, True)
    item['started_at'] = info['State']['StartedAt']
    result[role + '_selected_inspect'] = m.selected(info)
    if role == 'gpu':
        require(m.call(['docker', 'exec', cid, 'nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader']).strip() == m.GPU,
                'New container exposes a different GPU')
    persist(m, result)
    return item


def stop(m, contract, item, result):
    if item['stop'] is not None:
        # A cached stop is not permission to overlook an external restart.
        while True:
            try:
                verify_container(m, contract, item, False)
                require(not m.host_live(item['cid']), 'Previously stopped own container has live children')
                break
            except BaseException as pending:
                try:
                    persist(m, result)
                    print('Previously stopped own identity uncertain; mutex held: ' + repr(pending), file=sys.stderr, flush=True)
                except BaseException:
                    pass
                time.sleep(2)
        return item['stop']
    try:
        before = verify_container(m, contract, item)
        argv = ['docker', 'stop', '--time', '20', item['cid']]
        output = m.call(argv, timeout=35) if before['State']['Running'] else ''
        after = verify_container(m, contract, item, False)
        require(not m.host_live(item['cid']), 'Own host children remain after stop')
        item['stop'] = {'container_id': item['cid'], 'argv': argv, 'stdout': output,
                        'before': m.selected(before), 'after': m.selected(after),
                        'running_after_stop': False, 'remaining_host_children': []}
    except BaseException as error:
        result['errors'].append('Own stop uncertain, holding mutex: ' + repr(error))
        # No stop retry, foreign signal or permission-changing workaround.
        while True:
            try:
                after = verify_container(m, contract, item, False)
                require(not m.host_live(item['cid']), 'Own host children remain')
                item['stop'] = {'container_id': item['cid'], 'after': m.selected(after),
                                'running_after_stop': False, 'remaining_host_children': [],
                                'resolved_after_uncertain_cleanup': True}
                break
            except BaseException as pending:
                try:
                    persist(m, result)
                    print('Own cleanup uncertain; mutex held: ' + repr(pending), file=sys.stderr, flush=True)
                except BaseException:
                    pass
                time.sleep(2)
    result['owned_' + item['role'] + '_container_stop'] = item['stop']
    return item['stop']


def command(m, item, argv, name, result, jobs, stdin_path=None):
    """Native has no timeout. Every exact Popen is retained for finally wait."""
    row = {'name': name, 'argv': argv, 'started_utc': m.utc(), 'container_id': item['cid']}
    result['commands'].append(row)
    persist(m, result)
    stdin = None
    try:
        if stdin_path is not None:
            stdin = stdin_path.open('rb')
            row['stdin_source'] = m.fp(stdin_path)
        with (HOST / (name + '.stdout.raw')).open('xb') as out, (HOST / (name + '.stderr.raw')).open('xb') as err:
            job = subprocess.Popen(argv, stdin=stdin, stdout=out, stderr=err, start_new_session=True)
            jobs.append({'job': job, 'role': item['role'], 'row': row})
            row['host_cli_pid'] = job.pid
            try:
                row['host_cli_identity'] = m.proc(job.pid)
                persist(m, result)
            except BaseException as error:
                result['errors'].append('CLI birth/receipt diagnostic: ' + repr(error))
            row['returncode'] = job.wait()
        row['finished_utc'] = m.utc()
        row['stdout'] = m.fp(HOST / (name + '.stdout.raw'))
        row['stderr'] = m.fp(HOST / (name + '.stderr.raw'))
        persist(m, result)
        require(row['returncode'] == 0, name + ' actual child returned nonzero')
        return row
    finally:
        if stdin is not None:
            stdin.close()


def observer_stop(m, observer, result):
    if observer is None or observer.get('stopped'):
        return
    marker = HOST / 'observer-stop'
    while not marker.exists():
        try:
            with marker.open('x') as stream:
                stream.write('Exact own native CLI is terminal; end own observation.\n')
        except BaseException as error:
            result['errors'].append('Own observer stop-marker IO: ' + repr(error))
            time.sleep(2)
    code = observer['job'].wait()
    observer['stopped'] = True
    result['observer_returncode'] = code
    require(code == 0, 'Actual own observer child returned nonzero')
    path = HOST / 'observer/summary.json'
    summary, row = m.read(path), m.fp(path)
    require(summary['stop_reason'] == 'stop_file' and summary['mapping_scope_complete'] is True
            and not summary['errors'] and summary['source_sha256'] == OBSERVER_SHA,
            'Actual own observer summary failed')
    result['observer_summary'] = row
    return summary


def host_mappings(m, summary, gpu, case_ids):
    identity = summary['identity']
    require(identity['container_id'] == gpu['cid'] and identity['image_id'] == m.IMAGE
            and identity['started_at'] == gpu['started_at'], 'Own observer container birth differs')
    matrix = m.read(BASE / 'outputs/missing-four/matrix.json')
    cases = [row for row in matrix['selections'] if row.get('status') == 'completed']
    require([row['case_id'] for row in cases] == case_ids, 'Native subset identities differ')
    index = {}
    require(len(summary['command_writer_mappings']) == 8, 'Exactly eight own writer mappings required')
    for row in summary['command_writer_mappings']:
        index.setdefault((row['worker_output'], row['role'], row['container_tgid'], row['owner_start_time_clock_ticks']), []).append(row)
    seen, result = set(), []
    for case in cases:
        require(len(case['attempts']) == 1 and case['attempts'][0]['returncode'] == 0, 'Fresh once-only case required')
        attempt = case['attempts'][0]
        directory = BASE / 'outputs' / Path(attempt['output']).relative_to('/outputs')
        for role in ('simulator', 'inference'):
            path = directory / (role + '-process-start.json')
            entry = m.read(path)
            require(entry['role'] == role, 'Native entry role differs')
            process = entry['process']
            matches = index.get((attempt['output'], role, process['pid'], process['start_time_clock_ticks']), [])
            require(len(matches) == 1, 'Exactly one actual own hostwriter birth required')
            mapping = matches[0]
            require(mapping['nspid'][0] == mapping['host_tid'] and mapping['nspid'][-1] == mapping['container_tid']
                    and mapping['nstgid'][0] == mapping['host_tgid'] and mapping['nstgid'][-1] == process['pid'],
                    'Hostwriter owner/NSpid/NStgid differs')
            key = (mapping['host_tid'], mapping['start_time_clock_ticks'])
            require(key not in seen, 'Hostwriter birth duplicated across workers')
            seen.add(key)
            result.append({'case_id': case['case_id'], 'role': role, 'entry_sha256': m.fp(path)['sha256'], 'mappings': matches})
    require(len(result) == 8, 'Require eight real hostwriter births')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    require(args.root_authorized_start, 'Explicit internal Root start flag required')
    m = module()
    m.endpoint()
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == m.BOOT, 'Host boot differs')
    contract_path, checker = PREP / 'contract.json', PREP / 'subset_check.py'
    contract_fp, checker_fp, own_fp = m.fp(contract_path), m.fp(checker), m.fp(__file__)
    require(contract_fp['sha256'] == CONTRACT_SHA, 'Frozen four-case contract changed')
    require(checker_fp['sha256'] == CHECKER_SHA, 'Frozen four-case CPU checker changed')
    require(m.fp(m.OLD / 'source/scripts/research/sim2sim_scene_matrix.py')['sha256'] == CORE_SHA,
            'Frozen native matrix source changed')
    contract = m.read(contract_path)
    require(contract['proposed_new_host_base'] == str(BASE) and contract['image_id'] == m.IMAGE
            and contract['gpu_uuid'] == m.GPU and contract['shared_host_mutex'] == str(m.LOCK), 'Four-case identity differs')
    case_ids = contract['expected_native_result']['requested_cases']
    require(len(case_ids) == 4 and len(set(case_ids)) == 4, 'Four unique exact cases required')
    gap_files = {name: m.fp(REC / 'writer-mapping-audit-final-01' / filename) for name, filename in (
        ('analysis', 'analysis.json'), ('worker_rows', 'final-original-worker-mappings.json'))}
    require(gap_files['analysis']['sha256'] == GAP_ANALYSIS_SHA and gap_files['worker_rows']['sha256'] == GAP_ROWS_SHA,
            'Final original observation-gap audit changed')
    gap = m.read(gap_files['analysis']['path'])
    require(gap['completed_cases'] == 629 and gap['expected_completed_worker_entries'] == 1258
            and gap['exactly_one_writer_mapping_workers'] == 1250 and gap['missing_mapping_workers'] == 8
            and gap['missing_case_ids'] == case_ids and gap['ambiguous_mapping_workers'] == 0
            and not gap['identity_errors'], 'Exact original1250+8 observation boundary differs')
    prior = manager_ready(m)  # No output, Docker create or lock before actual readiness.
    before, guards = m.freeze(), m.old_host_guard()
    require(not m.safe(BASE).exists(), 'No automatic retry; fresh four-case base required')
    require((m.OLD / 'inputs/cache').is_dir(), 'Readonly /data nested cache mountpoint missing')
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(m.safe(m.LOCK), flags, 0o644)
    require(stat.S_ISREG(os.fstat(fd).st_mode), 'Shared mutex is not a regular file')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    pending = []
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in handlers:
        signal.signal(sig, lambda number, frame: pending.append({'utc': m.utc(), 'signal': number}))
    owned, jobs, observer, result = [], [], None, None
    try:
        require(manager_ready(m) == prior and m.freeze() == before and m.old_host_guard() == guards,
                'Prior completion/input bytes changed before locked start')
        gpu_before = gpu_idle(m)
        for name in NAMES.values():
            require(not m.call(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$']).strip(), 'Own new name already exists')
        HOST.mkdir(parents=True)
        (BASE / 'outputs').mkdir()
        (BASE / 'cache').mkdir()
        result = {'schema_version': 1, 'status': 'starting', 'started_utc': m.utc(), 'contract_sha256': CONTRACT_SHA,
                  'helper': own_fp, 'subset_checker': checker_fp, 'contract': contract_fp, 'manager_prerequisite': prior,
                  'historical_gap_audit': gap_files,
                  'image_id': m.IMAGE, 'gpu_uuid': m.GPU, 'case_ids': case_ids, 'commands': [], 'errors': [],
                  'pending_signals': pending, 'gpu_before': gpu_before, 'native_started': False,
                  'original_session54334_exit_code': 143, 'historical_host_observer_gap_preserved': True,
                  'separate_attempts_for_original_missing_observations': True, 'quality_verified': False,
                  'obstacle_course_completion_verified': False}
        m.write(HOST / 'frozen-before.json', before, exclusive=True)
        m.write(HOST / 'original-host-before.json', guards, exclusive=True)
        result['frozen_before'] = m.fp(HOST / 'frozen-before.json')
        result['source_snapshot_files_verified_before'] = 5206
        persist(m, result)
        plan_cpu = start(m, contract, 'plan', owned, result)
        plan_command = ['docker', 'exec', plan_cpu['cid'], *contract['cpu_plan_argv']]
        result['cpu_plan_returncode'] = command(m, plan_cpu, plan_command, 'cpu-plan', result, jobs)['returncode']
        check_common = ['--plan', '/outputs/missing-four-plan.json', '--matrix', '/outputs/missing-four/matrix.json']
        check_cases = [value for case in case_ids for value in ('--case-id', case)]
        checker_command = ['docker', 'exec', '-i', plan_cpu['cid'], '/opt/php/bin/inference-python', '-', 'plan',
                           *check_common, '--output', '/outputs/plan-validation.json', *check_cases]
        command(m, plan_cpu, checker_command, 'cpu-plan-check', result, jobs, checker)
        plan_check = m.read(BASE / 'outputs/plan-validation.json')
        require(plan_check['status'] == 'passed', 'Real CPU plan comparison failed')
        result['plan_validation'] = m.fp(BASE / 'outputs/plan-validation.json')
        result['native_plan'] = m.fp(BASE / 'outputs/missing-four-plan.json')
        result['native_plan_sha256'] = m.read(BASE / 'outputs/missing-four-plan.json')['plan_sha256']
        stop(m, contract, plan_cpu, result)
        same(checker_fp, m); same(own_fp, m)
        require(m.freeze() == before, 'Original inputs changed before native')
        result['gpu_before_native'] = gpu_idle(m)
        gpu = start(m, contract, 'gpu', owned, result)
        initial = m.top(gpu['cid'])
        baseline = {(p['pid'], p['birth']) for p in initial['processes'] if p['state'] != 'Z'}
        require(len(baseline) == 2 and any(p['argv'] == ['sleep', 'infinity'] for p in initial['processes']),
                'New private GPU container is not init/sleep idle')
        observer_source = m.OLD / 'control/observe_container_pids.py'
        require(m.fp(observer_source)['sha256'] == OBSERVER_SHA, 'Frozen observer source differs')
        observer_argv = ['/usr/bin/python3', '-B', str(observer_source), '--container-id', gpu['cid'],
                         '--expected-image', m.IMAGE, '--output', str(HOST / 'observer'),
                         '--stop-file', str(HOST / 'observer-stop'), '--interval', '0.5', '--max-seconds', '43500']
        observer_out, observer_err = (HOST / 'observer.stdout.raw').open('xb'), (HOST / 'observer.stderr.raw').open('xb')
        observer = {'job': subprocess.Popen(observer_argv, stdin=subprocess.DEVNULL, stdout=observer_out,
                                            stderr=observer_err, start_new_session=True),
                    'out': observer_out, 'err': observer_err, 'stopped': False}
        result['observer_argv'] = observer_argv
        result['observer_host_pid'] = observer['job'].pid
        result['observer_host_identity'] = m.proc(observer['job'].pid)
        deadline = time.monotonic() + 30
        while not (HOST / 'observer/launch.json').is_file():
            require(observer['job'].poll() is None and time.monotonic() < deadline, 'Own observer did not become ready')
            time.sleep(.1)
        launch = m.read(HOST / 'observer/launch.json')
        require(launch['source_sha256'] == OBSERVER_SHA and launch['identity']['container_id'] == gpu['cid']
                and launch['identity']['started_at'] == gpu['started_at'], 'Own observer ready identity differs')
        result['observer_launch'] = m.fp(HOST / 'observer/launch.json')
        result['status'], result['native_started'] = 'running_four_separate_native_attempts', True
        native = command(m, gpu, ['docker', 'exec', gpu['cid'], *contract['native_argv']], 'native', result, jobs)
        result['native_returncode'] = native['returncode']
        summary = observer_stop(m, observer, result)
        result['host_native_mappings'] = host_mappings(m, summary, gpu, case_ids)
        result['host_writer_mapping_count'] = 8
        result['native_matrix'] = m.fp(BASE / 'outputs/missing-four/matrix.json')
        event = m.top(gpu['cid'])
        require({(p['pid'], p['birth']) for p in event['processes'] if p['state'] != 'Z'} == baseline,
                'Native children remain after four-case parent terminal')
        result['gpu_idle_after_native'] = event
        stop(m, contract, gpu, result)
        final_cpu = start(m, contract, 'final', owned, result)
        final_argv = ['docker', 'exec', '-i', final_cpu['cid'], '/opt/php/bin/inference-python', '-', 'final',
                      *check_common, '--output', '/outputs/full-validation.json', *check_cases]
        result['cpu_validation_returncode'] = command(m, final_cpu, final_argv, 'cpu-final-check', result, jobs, checker)['returncode']
        post = m.read(BASE / 'outputs/full-validation.json')
        require(post['status'] == 'passed' and post['configurations'] == 4
                and post['worker_exit0_empty_group_count'] == 8 and post['full_decoded_mp4_count'] == 4
                and [row['case_id'] for row in post['cases']] == case_ids, 'Four-case actual CPU acceptance differs')
        for row in post['cases']:
            require(row['parent_returncode'] == 0 and row['worker_exit0_empty_groups'] == 2
                    and row['policy_ticks'] == 500 and len(row['videos']) == 1
                    and row['videos'][0]['returncode'] == 0 and row['videos'][0]['full_decode'] is True,
                    'Four-case worker/video evidence incomplete')
            for role in ('simulator', 'inference'):
                sealed = [item for item in row['worker_receipts'] if item['path'].endswith('/' + role + '-process-start.json')]
                mapped = [item for item in result['host_native_mappings'] if item['case_id'] == row['case_id'] and item['role'] == role]
                require(len(sealed) == len(mapped) == 1 and sealed[0]['sha256'] == mapped[0]['entry_sha256'],
                        'CPU-sealed native entry differs from observed hostwriter binding')
        require(post['matrix_sha256'] == result['native_matrix']['sha256']
                and post['native_plan_sha256'] == result['native_plan_sha256'], 'CPU subset plan/matrix binding differs')
        result['cpu_post'] = m.fp(BASE / 'outputs/full-validation.json')
        result['worker_exit0_empty_group_count'], result['full_decoded_mp4_count'] = 8, 4
        result['status'] = 'passed_pending_cleanup'
    except BaseException as error:
        if result is not None:
            result.update(status='failed', error=repr(error), traceback=traceback.format_exc())
        else:
            raise
    finally:
        # Deferred signals cover every diagnostic/cleanup sleep until all own
        # resources are stopped. An IO error cannot bypass the resource list.
        if result is not None:
            for entry in jobs:
                if entry['role'] == 'gpu' and entry['job'].poll() is None:
                    result['errors'].append('Diagnostic failure during native; waited for its natural terminal')
                    entry['row']['returncode_after_error'] = entry['job'].wait()
            if observer is not None:
                try:
                    observer_stop(m, observer, result)
                except BaseException as error:
                    result['errors'].append('Own observer terminal: ' + repr(error))
                finally:
                    for stream in (observer['out'], observer['err']):
                        try:
                            stream.close()
                        except BaseException as error:
                            result['errors'].append('Own observer diagnostic close: ' + repr(error))
            for item in reversed(owned):
                stop(m, contract, item, result)
            for entry in jobs:
                try:
                    entry['row']['returncode_after_cleanup'] = entry['job'].wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result['errors'].append('Own docker CLI did not exit after exact container stop')
                    entry['job'].terminate()
                    try:
                        entry['row']['returncode_after_cleanup'] = entry['job'].wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        entry['job'].kill(); entry['row']['returncode_after_cleanup'] = entry['job'].wait(timeout=5)
                except BaseException as error:
                    result['errors'].append('Own docker CLI reap: ' + repr(error))
            try:
                after = m.freeze()
                require(after == before and m.old_host_guard() == guards and manager_ready(m) == prior,
                        'Original source/host/prior evidence changed')
                for row in (own_fp, checker_fp, contract_fp):
                    same(row, m)
                for row in gap_files.values():
                    same(row, m)
                m.write(HOST / 'frozen-after.json', after, exclusive=True)
                result['frozen_after'] = m.fp(HOST / 'frozen-after.json')
                result['source_snapshot_files_verified_after'] = 5206
                result['original_inputs_and_controls_unchanged'] = True
            except BaseException as error:
                result['errors'].append('Frozen input postcheck: ' + repr(error))
            if result['status'] == 'passed_pending_cleanup' and not result['errors']:
                require(len(owned) == 3 and all(item['stop']['running_after_stop'] is False for item in owned),
                        'All three exact own containers must be stopped')
                result['status'] = 'completed'
            else:
                result['status'] = 'failed'
            result['finished_utc'] = m.utc()
            try:
                persist(m, result)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        else:
            # No own resource can be created before result is initialized.
            require(not owned and observer is None and not jobs, 'Unexpected untracked own resource')
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print(json.dumps({'status': result['status'], 'receipt': str(HOST / 'launch-receipt.json')}, allow_nan=False))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
