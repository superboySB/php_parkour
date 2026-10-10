#!/usr/bin/env python3
"""One Root-operated native resume transaction after explicit629 recovery.

Writing this helper did not execute/import/test it. `status` only reads files,
Docker endpoint/previous-container inspect; it creates no files and takes no lock.
Native calls have no time limit. A cleanup uncertainty keeps the mutex held until
Root makes this exact owned container observably stopped; it never kills foreign
processes, restarts a container, removes a container, or retries a training stage.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
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
PROJECT = Path('/home/dzp/projects/php_parkour')
HERE = PROJECT / 'outputs/research/native-resume-root-transaction-continuation-01'
HISTORY = PROJECT / 'outputs/research/native-resume-root-transaction-recovered-01'
HISTORY_HELPER_SHA = 'bdcf969feffb053b0dd6f7db86df8f6d96f207d404b2d33d27e1899bcb7b6db0'
HISTORY_RECEIPT_SHA = '8cf7e26ab8f036bdee82bec888e694968b245b4515c8224edd4375fd5941650e'
HISTORY_EXIT_SHA = 'aeec6bccbe81d8a31169afcd7793c34a07a7f26cd535b2fa0b3819a20acc922a'
HISTORY_CID = '08cc4ae903a041b0deb78de3b95e80f9fc15b7093ca0c5e36b0f311cbb2170f9'
HISTORY_STEP_SHA = (
    'e0c2848609ac9163d14ae03c380852b8bb0b8efdd2e595f78dc03e6389062561',
    'ff023876d83790345b08dbf3c8e68171aba37359cf84a6db542866912075ff1b',
    '0b219fdc40ed089397871767a18ff7a1d3ce1085f8e30cc233ecc8f3bab4145b',
)
CONTINUATION_NAME = 'php-native-resume-sdk018-continuation-01'
# Exact stdin adapter changes only native_load_log of the original CPU reader.
LOG_ADAPTER = PROJECT / 'outputs/research/native-resume-continuation-cpu-adapter-01/verify_resume.py'
LOG_ADAPTER_SHA = '5c552a2e9470a243e81ba9e1615d39fa04a30f51405611e837105bc10c8cdcc1'
ORIGINAL = PROJECT / 'outputs/research/native-resume-root-transaction-01/run.py'
ORIGINAL_SHA = 'd9c0a3bd6afadcb59d16bce9a4a37bdc11b0e36ccbd6adedeabd25879f0c764e'
RECOVERY_GATE = PROJECT / 'outputs/research/fresh629-recovery-01/controller-adapter/previous_recovered_02.py'
RECOVERY_GATE_SHA = 'dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525'
PREP = PROJECT / 'outputs/research/native-resume-acceptance-preparation-01'
PREVIOUS = PROJECT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
SOURCE = PREP / 'source'
OUTPUT = PREP / 'run-output-final-frozen'
RECEIPT_DIR = HERE / 'actual'
SESSION = PROJECT / 'outputs/research/fresh629-root-terminal-01/session54334.json'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
LOCK = PROJECT / ('outputs/research/.local-native-' + GPU + '.lock')
PREVIOUS_PLAN = '44d6e71e8ef1d12c5b479d8e3bcb411c39e8d7daa1c3bac109d6edd7417502d0'
PINS = {
    'readiness.json': 'e9f9f66516b64ebf4eb2630e043b222497dc159fc98f618332beee53344054f2',
    'preparation-manifest.json': 'b2f25a276f6d7eaddafa8e5a1e5d4bb9023f480968eab1cca4268f17da1f3f06',
    'root-commands.json': 'd573aa8075fe70f9264a20d6f6db8051c121fd3270170e728d5ec2fc2fa60996',
    'control/contract.json': 'ab7d1cfd5618ed53d13078a85fe1f52ad0cbd2115b8901e2d393964e8435b593',
    'source-manifest.json': 'a4cad190211066d88a1ce35166dcd1a7581fadbe6233826b77edfbd1e4da02ba',
    'registry-inputs.json': '665671942a4591d04f8d751125ddbaafd8c8a487bb11d1318be66face47b5f0e',
    'run-output-final-frozen/runtime-robot-assets-contract.json': '4bb773208db1a4af24f929423ab6bc3f7ad82ed131f01a84f512c7305f81d2ed',
    'run-output-final-frozen/runtime-robot-assets/manifest.json': '22c822637f8f4099d45ccfb6b85093cdf5ae5c91293474f261c5f0415fde0aba',
}
LABELS = ('teacher-locomotion', 'student-pure', 'student-finetune')
OPERATIONS = ('baseline-target2', 'archive', 'resume-target4', 'verify-resume', 'verify-onnx', 'check-skip')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'Parent traversal rejected')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink rejected: ' + str(path))
    return path


def fingerprint(path):
    path = safe(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Nonregular file: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def load(path):
    path = safe(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Nonregular JSON')
    return json.loads(path.read_text(), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def write(path, value, exclusive=False):
    path = safe(path)
    data = json.dumps(value, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x') as stream:
            stream.write(data)
    else:
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('w') as stream:
            stream.write(data)
        temporary.replace(path)


def checked(row, path=None):
    actual = fingerprint(path or row['path'])
    require(all(actual[k] == row[k] for k in ('bytes', 'sha256')), 'Frozen file differs: ' + actual['path'])
    return actual


def fileset(root):
    root = safe(root)
    result = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'Symlink in frozen tree')
        if path.is_file():
            result.add(str(path.absolute()))
        else:
            require(path.is_dir(), 'Special file in frozen tree')
    return result


def inputs():
    result = {}
    for relative, expected in PINS.items():
        row = fingerprint(PREP / relative)
        require(row['sha256'] == expected, 'Hard-pinned preparation differs: ' + relative)
        result[row['path']] = row
    preparation = load(PREP / 'preparation-manifest.json')['files']
    require(len(preparation) == 72, 'Expected72 preparation records')
    for row in preparation:
        path = safe(row['path'])
        require(path.is_relative_to(PREP), 'Preparation path escaped')
        result[str(path)] = checked(row)
    source = load(PREP / 'source-manifest.json')['files']
    registry = load(PREP / 'registry-inputs.json')['files']
    require(len(source) == 3298 and len(registry) == 201, 'Source/registry counts differ')
    for rows, root in ((source, SOURCE), (registry, PROJECT / 'outputs/research/assets/motions-locomotion')):
        expected = set()
        for row in rows:
            path = safe(row['path'])
            require(path.is_relative_to(root), 'Source/registry record escaped')
            expected.add(str(path))
            result[str(path)] = checked(row)
        require(fileset(root) == expected, 'Source/registry actual file-set differs')
    robot = load(OUTPUT / 'runtime-robot-assets-contract.json')
    require(len(robot['files']) == 35, 'Expected35 robot assets')
    source_root = SOURCE / 'thirdparty/holosoma/src/holosoma/holosoma/data/robots'
    copy_root = OUTPUT / 'runtime-robot-assets/robots'
    for row in robot['files']:
        relative = Path(row['relative_path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe robot path')
        for root, key in ((source_root, 'source_sha256'), (copy_root, 'copy_sha256')):
            actual = fingerprint(root / relative)
            require(actual['bytes'] == row['bytes'] and actual['sha256'] == row[key], 'Robot original/copy differs')
            result[actual['path']] = actual
    require(not any(p.is_symlink() for p in copy_root.rglob('*')), 'Runtime robot symlink rejected')
    return result


def call(argv, timeout=20):
    completed = subprocess.run(argv, capture_output=True, timeout=timeout)
    require(completed.returncode == 0, 'Read/control command failed: ' + repr(argv[:4]) + ': ' + completed.stderr.decode(errors='replace'))
    return completed.stdout.decode()


def endpoint():
    context = call(['docker', 'context', 'show']).strip()
    config = json.loads(call(['docker', 'context', 'inspect', context]))[0]
    address = os.environ.get('DOCKER_HOST') or config['Endpoints']['docker']['Host']
    require(address == 'unix:///var/run/docker.sock', 'Only reviewed local Docker socket is allowed')
    return {'context': context, 'endpoint': address}


def inspect(cid):
    require(re.fullmatch('[0-9a-f]{64}', cid), 'Exact full CID required')
    info = json.loads(call(['docker', 'inspect', '--type', 'container', cid]))[0]
    require(info['Id'] == cid and info['Image'] == IMAGE, 'Container identity changed')
    return info


def selected(info):
    return {key: info[key] for key in ('Id', 'Image', 'Name', 'State', 'Mounts')} | {
        'HostConfig': {k: info['HostConfig'].get(k) for k in ('NetworkMode', 'IpcMode', 'PidMode', 'Init', 'ShmSize', 'DeviceRequests')},
        'Config': {k: info['Config'].get(k) for k in ('WorkingDir', 'Entrypoint', 'Cmd')},
    }


def previous():
    # Load only the reviewed stdlib gate, with bytecode disabled. Its distinct
    # recovery proof never turns the original session143/receipt into normal0.
    row = fingerprint(RECOVERY_GATE)
    require(row['sha256'] == RECOVERY_GATE_SHA, 'Frozen recovered lifecycle gate changed')
    require(fingerprint(ORIGINAL)['sha256'] == ORIGINAL_SHA, 'Preserved original candidate changed')
    spec = importlib.util.spec_from_file_location('_native_resume_previous_recovered', RECOVERY_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.previous_recovered()
    require(fingerprint(RECOVERY_GATE) == row, 'Recovered gate changed during admission')
    return result


def tool_exit(path):
    require(safe(path) == SESSION, 'Only original session54334 receipt is allowed')
    row, value = fingerprint(path), load(path)
    require(row['sha256'] == '97b6568848785bbf720bb1782086dbc385b6053577921765ec76694c9a293209'
            and value['session_id'] == 54334 and value['status'] == 'completed'
            and value['exit_code'] == value['actual_tool_result']['exit_code'] == 143
            and value['normal_zero_exit_verified'] is False,
            'Original actual143 must remain unchanged; readiness comes from the recovered gate')
    require(fingerprint(RECOVERY_GATE)['sha256'] == RECOVERY_GATE_SHA, 'Recovered gate source changed')
    return row


def gpu_idle():
    uuids = call(['nvidia-smi', '-i', GPU, '--query-gpu=uuid', '--format=csv,noheader']).strip().splitlines()
    require(uuids == [GPU], 'Selected physical GPU UUID differs')
    rows = call(['nvidia-smi', '-i', GPU, '--query-compute-apps=pid', '--format=csv,noheader,nounits']).strip()
    require(not rows, 'Selected GPU already has compute processes')
    return {'uuid': GPU, 'compute_processes': []}


def stat_fields(raw):
    rest = raw.rsplit(')', 1)[1].split()
    return {'state': rest[0], 'ppid': int(rest[1]), 'pgid': int(rest[2]), 'sid': int(rest[3]), 'start_time_clock_ticks': rest[19]}


def process(pid, cid):
    path = Path('/proc') / str(pid)
    first = stat_fields((path / 'stat').read_text())
    cgroup = (path / 'cgroup').read_text()
    components = {p for line in cgroup.splitlines() for p in line.split(':', 2)[-1].split('/')}
    if cid not in components and 'docker-' + cid + '.scope' not in components:
        return None
    status = (path / 'status').read_text()
    argv = (path / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    last = stat_fields((path / 'stat').read_text())
    require(first['start_time_clock_ticks'] == last['start_time_clock_ticks'] and first['ppid'] == last['ppid'],
            'Process birth/ancestry changed while observing')
    data = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in status.splitlines() if ':' in line}
    nspid = [int(n) for n in data.get('NSpid', '').split()]
    require(nspid and nspid[0] == pid, 'Host/container PID namespace mapping unavailable')
    return {'host_pid': pid, 'container_pid': nspid[-1], 'nspid': nspid,
            'nstgid': [int(n) for n in data.get('NStgid', '').split()], **last,
            'argv': [a.decode(errors='replace') for a in argv] if argv != [b''] else [],
            'cgroup': cgroup, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def snapshot(cid):
    raw = call(['docker', 'top', cid, '-eo', 'pid,ppid,stat,args'], timeout=2)
    rows = []
    for line in raw.splitlines()[1:]:
        if not line.strip():
            continue
        pid = int(line.split(None, 1)[0])
        try:
            row = process(pid, cid)
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(row is not None, 'Docker top process is outside exact CID cgroup')
        rows.append(row)
    return {'utc': utc(), 'monotonic': time.monotonic(), 'docker_top': raw, 'processes': rows}


def remaining_host(cid):
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            row = process(int(path.name), cid)
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row and row['state'] != 'Z':
            rows.append(row)
    return rows


def verify_container(info, commands, running):
    require(info['Name'] == '/' + commands['name'] and info['State']['Running'] is running, 'Own name/running state differs')
    actual = {(m['Source'], m['Destination'], m['RW']) for m in info['Mounts']}
    expected = {(m['source'], m['destination'], m['rw']) for m in commands['mounts']}
    require(actual == expected and len(info['Mounts']) == 5, 'Exact5 own mounts differ')
    config, host = info['Config'], info['HostConfig']
    require(config['WorkingDir'] == commands['working_dir'] and config['Entrypoint'] == commands['entrypoint']
            and config['Cmd'] == ['-lc', 'exec sleep infinity'], 'Own process config differs')
    require(host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and host['PidMode'] in ('', 'private')
            and host['Init'] is True and host['ShmSize'] == 8 * 1024 ** 3, 'Own isolation differs')
    requests = host.get('DeviceRequests') or []
    require(len(requests) == 1 and requests[0].get('DeviceIDs') == [GPU], 'Own unique GPU request differs')
    env = dict(v.split('=', 1) for v in config['Env'] if '=' in v)
    require(all(env.get(k) == v for k, v in commands['environment'].items()), 'Own selected environment differs')


def native_mappings(stage, event, row):
    matches = list((OUTPUT / 'exec-receipts').glob(stage + '-*.json'))
    require(len(matches) <= 1, 'Duplicate native exec receipt')
    if not matches:
        return
    receipt = load(matches[0])
    recorded = fingerprint(matches[0])
    require(receipt['stage'] == stage, 'Native receipt stage differs')
    if row.get('native_exec_receipt'):
        require(row['native_exec_receipt'] == recorded, 'Native exec receipt changed')
    row['native_exec_receipt'] = recorded
    processes = {p['host_pid']: p for p in event['processes']}
    wrappers = [p for p in processes.values() if p['container_pid'] == receipt['pid']
                and p['start_time_clock_ticks'] == str(receipt['start_time_clock_ticks']) and p['state'] != 'Z']
    require(len(wrappers) <= 1, 'Ambiguous native wrapper')
    if not wrappers:
        return
    wrapper = wrappers[0]
    require(wrapper['container_pid'] != 1 and wrapper['pgid'] > 0 and wrapper['sid'] > 0, 'Invalid wrapper mapping')
    row['wrapper_mapping'] = wrapper
    children = []
    for child in processes.values():
        argv = child['argv']
        if child['state'] == 'Z' or len(argv) < 3 or argv[0] != '/isaac-sim/kit/python/bin/python3':
            continue
        if argv[1:3] != ['-m', 'wbt_training.train_agent']:
            continue
        require(argv[1:] == receipt['actual_exec_argv'][1:], 'Real native Kit argv differs from adapter transport')
        ancestry, current = [child], child
        for _ in range(16):
            if current['host_pid'] == wrapper['host_pid']:
                break
            current = processes.get(current['ppid'])
            if current is None:
                break
            ancestry.append(current)
        if ancestry[-1]['host_pid'] == wrapper['host_pid']:
            children.append((child, ancestry))
    require(len(children) <= 1, 'Ambiguous learner Kit child')
    if children:
        child, ancestry = children[0]
        require(child['host_pid'] != wrapper['host_pid'], 'Wrapper cannot stand in for real Kit child')
        identity = (child['host_pid'], child['start_time_clock_ticks'])
        if row.get('kit_mapping'):
            old = row['kit_mapping']
            require(identity == (old['host_pid'], old['start_time_clock_ticks']), 'Native Kit child was replaced')
        row['kit_mapping'] = child
        row['ancestry'] = ancestry


def idle(cid, baseline):
    deadline = time.monotonic() + 10
    while True:
        event = snapshot(cid)
        live = {(r['host_pid'], r['start_time_clock_ticks']) for r in event['processes'] if r['state'] != 'Z'}
        if live == baseline:
            return event
        require(time.monotonic() < deadline, 'Own container retains unexpected children after exec completion')
        time.sleep(.25)


def hostpath(native):
    path = Path(native)
    require(path.is_absolute() and '..' not in path.parts, 'Unsafe native evidence path')
    for prefix, root in (('/outputs', OUTPUT), ('/workspace/php_parkour', SOURCE), ('/control', PREP / 'control')):
        if path.is_relative_to(prefix):
            return safe(root / path.relative_to(prefix))
    raise ValueError('Evidence path outside reviewed mounts: ' + native)


def verify_report_files(value):
    if isinstance(value, dict):
        if value.get('fixed_manifest_may_change') is True:
            # Frozen archive intentionally permits the fixed pipeline manifest
            # to advance; its original bytes are retained in this exact copy.
            require(set(value) == {'original', 'retained', 'fixed_manifest_may_change'}, 'Unexpected mutable archive record')
            checked(value['retained'], hostpath(value['retained']['path']))
            return
        if all(k in value for k in ('path', 'bytes', 'sha256')):
            checked(value, hostpath(value['path']))
        for child in value.values():
            verify_report_files(child)
    elif isinstance(value, list):
        for child in value:
            verify_report_files(child)


def cpu_report(stage):
    label = next(label for label in LABELS if stage.startswith(label + '-'))
    operation = stage[len(label) + 1:]
    if operation == 'archive':
        path, expected = OUTPUT / 'baseline-archive' / label / 'archive.json', 'archived'
    else:
        suffix = {'verify-resume': '', 'verify-onnx': '-onnx', 'check-skip': '-skip'}[operation]
        path, expected = OUTPUT / 'resume-evidence' / (label + suffix + '.json'), 'passed'
    row, value = fingerprint(path), load(path)
    require(value['status'] == expected and value['label'] == label, 'CPU scientific report did not pass')
    verify_report_files(value)
    require(fingerprint(path) == row, 'CPU report changed during validation')
    return row


def teacher_checkpoint():
    path = OUTPUT / 'resume-smoke/smoke/manifests/teacher-locomotion.json'
    manifest = load(path)
    require(manifest['status'] == 'passed' and manifest['returncode'] == 0 and manifest['checkpoint_iteration'] == 3,
            'Teacher target4 must complete before students')
    row = fingerprint(hostpath(manifest['checkpoint']))
    require(row['sha256'] == manifest['checkpoint_sha256'], 'Teacher PT differs')
    return row


def historical_prefix(commands, current_inputs):
    """Accept only the three already completed steps of the preserved failure."""
    proof = {}
    for path, expected in ((HISTORY/'run.py', HISTORY_HELPER_SHA),
                           (HISTORY/'actual/receipt.json', HISTORY_RECEIPT_SHA),
                           (HISTORY/'actual-parent-01/process-exit.json', HISTORY_EXIT_SHA)):
        row = fingerprint(path)
        require(row['sha256'] == expected, 'Preserved failed attempt changed')
        proof[str(path)] = row
    old = load(HISTORY/'actual/receipt.json')
    parent = load(HISTORY/'actual-parent-01/process-exit.json')
    require(parent['actual_wait_returncode'] == 1 and parent['helper_sha256'] == HISTORY_HELPER_SHA
            and old['status'] == 'failed' and old['cleanup_errors'] == []
            and old['error'] == 'ValueError: Actual docker exec returned nonzero: teacher-locomotion-verify-resume'
            and old['input_postcheck_unchanged'] is True and old['container_id'] == HISTORY_CID,
            'Only the specific terminal CPU-log validation failure is eligible')
    try:
        live = stat_fields((Path('/proc')/str(parent['pid'])/'stat').read_text())
    except FileNotFoundError:
        live = None
    old_birth = stat_fields(parent['stat'])['start_time_clock_ticks']
    require(live is None or live['state'] == 'Z' or live['start_time_clock_ticks'] != old_birth,
            'Preserved attempt helper is still live')
    info = inspect(HISTORY_CID);verify_container(info, commands, False)
    stop = old['owned_container_stop']
    require(stop['running_after_stop'] is False and stop['after']['Id'] == HISTORY_CID
            and info['State']['StartedAt'] == stop['after']['State']['StartedAt']
            == old['selected_container']['State']['StartedAt'] and not remaining_host(HISTORY_CID),
            'Preserved own container/birth is not fully stopped')
    for name in ('input-before.json','input-after.json'):
        path = HISTORY/'actual'/name
        require(fingerprint(path)['sha256'] == 'cb5a719d6f8cba7d08704b885cb41949c7edaf2c27afd919ca13237a9e893759'
                and load(path) == current_inputs, 'Preserved input pre/post/current proof differs')
        proof[str(path)] = fingerprint(path)
    require(len(old['steps']) == 4 and old['steps'][3]['stage'] == commands['steps'][3]['stage']
            and old['steps'][3]['returncode'] == 1, 'Preserved failure is not exactly step4')
    prefix = []
    for index, (step, expected) in enumerate(zip(commands['steps'][:3], HISTORY_STEP_SHA), 1):
        path = HISTORY/'actual'/f'{index:02d}-{step["stage"]}'/'step.json'
        row = fingerprint(path);require(row['sha256'] == expected, 'Historical passed step changed')
        proof[str(path)] = row
        actual = load(path)
        expected_argv = [HISTORY_CID if x == '<EXACT_OWNED_CID_FROM_CREATE>' else x for x in step['argv']]
        require(actual == old['steps'][index-1] and actual['stage'] == step['stage']
                and actual['kind'] == step['kind'] and actual['argv'] == expected_argv and actual['returncode'] == 0,
                'Historical original argv/step outcome differs')
        for key in ('stdout','stderr','process_samples'):
            proof[actual[key]['path']] = checked(actual[key])
        if step['kind'] == 'actual_native_training_future_only':
            receipt = checked(actual['native_exec_receipt']);proof[receipt['path']] = receipt
            native = load(receipt['path'])
            wrapper, kit, ancestry = actual['wrapper_mapping'], actual['kit_mapping'], actual['ancestry']
            require(wrapper['container_pid'] == native['pid']
                    and wrapper['start_time_clock_ticks'] == str(native['start_time_clock_ticks'])
                    and kit['argv'][:3] == ['/isaac-sim/kit/python/bin/python3','-m','wbt_training.train_agent']
                    and kit['argv'][1:] == native['actual_exec_argv'][1:]
                    and ancestry[0] == kit and ancestry[-1] == wrapper and len(ancestry) >= 2
                    and wrapper['nspid'] == [wrapper['host_pid'], wrapper['container_pid']]
                    and kit['nspid'] == [kit['host_pid'], kit['container_pid']],
                    'Historical native wrapper/real Kit ancestry differs')
            require(all(a['ppid'] == b['host_pid'] for a,b in zip(ancestry, ancestry[1:])),
                    'Historical Kit ancestry is disconnected')
        else:
            require(cpu_report(step['stage']) == actual['cpu_report'], 'Historical archive/report differs')
        prefix.append(actual)
    failure = HISTORY/'actual/04-teacher-locomotion-verify-resume/stderr.raw'
    require('ValueError: Missing real native load/shutdown file log' in failure.read_text(),
            'Historical failed validation reason differs')
    proof[str(failure)] = fingerprint(failure)
    return {'status':'historical_prefix_verified_original_attempt_failed', 'original_actual_wait_returncode':1,
            'original_failed_stage':commands['steps'][3]['stage'], 'historical_command_exit0_count':3,
            'container_stopped':selected(info), 'evidence':proof, 'steps':prefix,
            'teacher_checkpoint':teacher_checkpoint()}


def native_exit_admission(stage, result):
    label = next(label for label in LABELS if stage == label+'-verify-resume')
    rows = result['historical_prefix']['steps'] + result['steps']
    found = [r for r in rows if r['stage'] == label+'-resume-target4']
    require(len(found) == 1, 'Exactly one actual completed resume must precede CPU adaptation')
    native = found[0]
    require(native['kind'] == 'actual_native_training_future_only' and native['returncode'] == 0
            and all(k in native for k in ('wrapper_mapping','kit_mapping','ancestry','idle_after','native_exec_receipt')),
            'Native exit/birth/idle proof incomplete')
    cid = HISTORY_CID if label == 'teacher-locomotion' else result['container_id']
    require(native['wrapper_mapping']['cgroup'].find(cid) >= 0
            and native['kit_mapping']['cgroup'].find(cid) >= 0, 'Native admission exact CID differs')
    archive = load(OUTPUT/'baseline-archive'/label/'archive.json')
    proof = {'schema_version':1,'status':'native_completed_zero_and_container_idle','label':label,
             'stage':label+'-resume-target4','container_id':cid,'native_stage':native,
             'expected_resume_checkpoint':archive['baseline_manifest']['checkpoint'],
             'historical_teacher_from_failed_attempt':label == 'teacher-locomotion',
             'host_helper':result['helper']}
    directory = safe(OUTPUT/'continuation-admission')
    directory.mkdir(exist_ok=True)
    path = directory/(label+'-native.json')
    write(path,proof,exclusive=True)
    return fingerprint(path), '/outputs/continuation-admission/'+path.name


def step_run(cid, step, baseline, result, number):
    argv = [cid if x == '<EXACT_OWNED_CID_FROM_CREATE>' else x for x in step['argv']]
    stage = step['stage']
    row = {'stage': stage, 'kind': step['kind'], 'argv': argv, 'started_utc': utc(), 'started_monotonic': time.monotonic()}
    adapter = stage.endswith('-verify-resume')
    if adapter:
        require(fingerprint(LOG_ADAPTER)['sha256'] == LOG_ADAPTER_SHA, 'Reviewed CPU log adapter changed')
        row['original_frozen_argv'] = list(argv)
        require(argv.count('/control/resume_evidence.py') == 1 and argv[:2] == ['docker','exec'],
                'Only original verify-resume CPU transport may be adapted')
        argv[argv.index('/control/resume_evidence.py')] = '-'
        argv.insert(2,'-i')
        admission, native_path = native_exit_admission(stage,result)
        argv += ['--native-exit-proof',native_path,'--native-exit-proof-sha256',admission['sha256']]
        row['native_exit_admission'] = admission
        row['argv'] = argv;row['stdin_adapter'] = fingerprint(LOG_ADAPTER)
    result['steps'].append(row)
    target = RECEIPT_DIR / 'receipt.json'
    write(target, result)
    directory = RECEIPT_DIR / f'{number:02d}-{stage}'
    directory.mkdir()
    native = step['kind'] == 'actual_native_training_future_only'
    if native:
        require(not list((OUTPUT / 'exec-receipts').glob(stage + '-*.json')), 'Native stage was previously attempted')
    idle(cid, baseline)
    if native:
        row['gpu_before_native'] = gpu_idle()
    job = None
    try:
        with (directory / 'stdout.raw').open('xb') as stdout, (directory / 'stderr.raw').open('xb') as stderr, (directory / 'process-samples.jsonl').open('x') as samples:
            if adapter:
                with LOG_ADAPTER.open('rb') as stdin:
                    job = subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            else:
                job = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
            result['_active_job'] = job
            row['docker_exec_host_pid'] = job.pid
            while True:
                event = snapshot(cid)
                samples.write(json.dumps(event, allow_nan=False) + '\n'); samples.flush()
                if native:
                    native_mappings(stage, event, row)
                code = job.poll()
                if code is not None:
                    row['returncode'] = code
                    break
                time.sleep(.25)
            require(row['returncode'] == 0, 'Actual docker exec returned nonzero: ' + stage)
        result.pop('_active_job', None)
        row['finished_utc'] = utc()
        row['duration_seconds'] = time.monotonic() - row['started_monotonic']
        row['stdout'] = fingerprint(directory / 'stdout.raw')
        row['stderr'] = fingerprint(directory / 'stderr.raw')
        row['process_samples'] = fingerprint(directory / 'process-samples.jsonl')
        row['idle_after'] = idle(cid, baseline)
        if native:
            require(all(k in row for k in ('native_exec_receipt', 'wrapper_mapping', 'kit_mapping', 'ancestry')),
                    'Missing observed live wrapper/real Kit ancestry')
        else:
            row['cpu_report'] = cpu_report(stage)
        if adapter:
            require(fingerprint(LOG_ADAPTER) == row['stdin_adapter'], 'CPU log adapter changed during invocation')
            checked(row['native_exit_admission'])
            label = stage[:-len('-verify-resume')]
            sidecar_path = OUTPUT/'continuation-admission'/(label+'-shutdown-log-validation.json')
            sidecar = load(sidecar_path)
            require(sidecar['status'] == 'actual_native_zero_kit_gone_and_shutdown_begin_verified'
                    and sidecar['label'] == label and sidecar['actual_native_parent_returncode'] == 0
                    and sidecar['simulation_app_close_return_verified'] is False
                    and sidecar['host_admission']['sha256'] == row['native_exit_admission']['sha256'],
                    'CPU shutdown-log adapter did not return its explicit limited proof')
            verify_report_files(sidecar)
            row['shutdown_log_validation'] = fingerprint(sidecar_path)
        write(directory / 'step.json', row, exclusive=True)
        write(target, result)
    except BaseException:
        # Caller still owns and reaps this exact CLI after stopping the own CID.
        if job is not None:
            result['_active_job'] = job
        raise


def persist(result):
    write(RECEIPT_DIR / 'receipt.json', {k: v for k, v in result.items() if not k.startswith('_')})


def stop_owned(cid, commands, started_at):
    before = inspect(cid)
    verify_container(before, commands, before['State']['Running'])
    require(not started_at or before['State']['StartedAt'] == started_at, 'Own container was restarted externally')
    response = call([cid if x == '<EXACT_OWNED_CID_FROM_CREATE>' else x for x in commands['finally_stop_argv']], timeout=45)
    after = inspect(cid)
    verify_container(after, commands, False)
    survivors = remaining_host(cid)
    require(not survivors, 'Owned host native processes survived container stop')
    return {'argv': [cid if x == '<EXACT_OWNED_CID_FROM_CREATE>' else x for x in commands['finally_stop_argv']],
            'stdout': response, 'before': selected(before), 'after': selected(after), 'running_after_stop': False, 'remaining_host_processes': survivors}


def transaction(args):
    require(args.root_authorized_start, 'Explicit --root-authorized-start required')
    endpoint_info = endpoint()
    session_row = tool_exit(args.previous_tool_exit_receipt)
    safe(LOCK)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(LOCK, flags, 0o644)
    require(stat.S_ISREG(os.fstat(fd).st_mode), 'Mutex is not a regular file')
    # Install both handlers before taking the lock: no signal can escape a
    # protected interval, including uncertain-cleanup sleeps and diagnostic IO.
    pending_signals = []
    handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    def delayed(signum, frame):
        pending_signals.append({'utc': utc(), 'signal': signum})
    for signum in handlers:
        signal.signal(signum, delayed)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        raise
    cid = None
    started_at = None
    result = None
    commands = None
    try:
        prior = previous()
        require(prior['status'] == 'recovered_previous_ready' and prior['ready'] is True,
                'Recovered629 and separate four-case lifecycle proof not actually ready/stopped')
        before = inputs()
        commands = load(PREP / 'root-commands.json')
        require(commands['global_mutex'] == str(LOCK) and commands['image_id'] == IMAGE and commands['gpu_uuid'] == GPU
                and commands['required_previous_receipt'] == str(PREVIOUS / 'host/launch-receipt.json'), 'Frozen transaction contract differs')
        require([s['stage'] for s in commands['steps']] == [label + '-' + op for label in LABELS for op in OPERATIONS],
                'Original18 step order differs')
        require(len(commands['steps']) == 18, 'Expected18 original commands')
        prefix = historical_prefix(commands, before)
        require(fingerprint(LOG_ADAPTER)['sha256'] == LOG_ADAPTER_SHA, 'Reviewed CPU adapter is not frozen')
        for label in LABELS:
            require(not (OUTPUT/'resume-evidence'/(label+'.json')).exists(), 'Resume validation was already attempted successfully')
        for label in LABELS[1:]:
            require(not (OUTPUT/'baseline-archive'/label).exists()
                    and not list((OUTPUT/'exec-receipts').glob(label+'-*.json')),
                    'Student was previously attempted; no automatic retry')
        require(len(list((OUTPUT/'exec-receipts').glob('*.json'))) == 2, 'Expected only the two historical teacher calls')
        require(not (OUTPUT/'continuation-admission').exists(), 'Previous continuation admission retained; no retry')
        require(not safe(RECEIPT_DIR).exists(), 'Transaction was previously attempted')
        commands['original_name'] = commands['name']
        name_index = commands['create_argv'].index('--name') + 1
        require(commands['create_argv'][name_index] == commands['name'], 'Original container name transport differs')
        commands['name'] = CONTINUATION_NAME
        commands['create_argv'][name_index] = CONTINUATION_NAME
        require(not call(['docker', 'ps', '-aq', '--filter', 'name=^/' + commands['name'] + '$']).strip(), 'Own new container name already exists')
        gpu = gpu_idle()
        require(json.loads(call(['docker', 'image', 'inspect', IMAGE]))[0]['Id'] == IMAGE, 'Fixed image is absent')
        RECEIPT_DIR.mkdir()
        result = {'schema_version': 1, 'status': 'starting', 'started_utc': utc(), 'started_monotonic': time.monotonic(),
                  'helper': fingerprint(__file__), 'endpoint': endpoint_info, 'session54334_exit': session_row,
                  'previous': prior, 'image_id': IMAGE, 'gpu_uuid': GPU, 'gpu_before': gpu,
                  'lifecycle_contract': 'recovered629_and_separate_four_case_supplement',
                  'original_session54334_actual_exit_code': 143, 'original_root_normal_exit_verified': False,
                  'preserved_original_helper': fingerprint(ORIGINAL), 'recovered_gate': fingerprint(RECOVERY_GATE),
                  'pending_signals': pending_signals,
                  'root_commands': fingerprint(PREP / 'root-commands.json'), 'steps': [], 'native_started': False,
                  'historical_prefix':prefix, 'continuation_from_original_step':4,
                  'new_steps_planned':15, 'cpu_log_adapter':fingerprint(LOG_ADAPTER),
                  'original_failed_attempt_preserved':True, 'automatic_retry':False,
                  'quality_verified': False, 'bitwise_continuation_verified': False, 'cleanup_errors': []}
        write(RECEIPT_DIR / 'input-before.json', before, exclusive=True)
        persist(result)
        result['create_argv'] = commands['create_argv']
        persist(result)
        raw_cid = call(commands['create_argv']).strip()
        require(re.fullmatch('[0-9a-f]{64}', raw_cid), 'docker create did not return exact full CID')
        cid = raw_cid
        result['container_id'] = cid
        verify_container(inspect(cid), commands, False)
        persist(result)
        result['start_argv'] = [cid if x == '<EXACT_OWNED_CID_FROM_CREATE>' else x for x in commands['start_argv']]
        result['start_stdout'] = call(result['start_argv'])
        info = inspect(cid)
        verify_container(info, commands, True)
        started_at = info['State']['StartedAt']
        result['selected_container'] = selected(info)
        result['container_uuid_argv'] = ['docker', 'exec', cid, 'nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader']
        require(call(result['container_uuid_argv']).strip().splitlines() == [GPU], 'Container exposes unexpected GPU UUID')
        initial = snapshot(cid)
        live = [p for p in initial['processes'] if p['state'] != 'Z']
        require(len(live) == 2 and any(p['container_pid'] == 1 for p in live)
                and any(p['argv'] == ['sleep', 'infinity'] for p in live), 'New container idle init/sleep differs')
        baseline = {(p['host_pid'], p['start_time_clock_ticks']) for p in live}
        result['initial_idle'] = initial
        persist(result)
        teacher = prefix['teacher_checkpoint']
        for number, step in enumerate(commands['steps'][3:], 4):
            require(fingerprint(__file__) == result['helper'], 'Actual host helper changed during transaction')
            require(fingerprint(PREP / 'root-commands.json') == result['root_commands'], 'Original18 argv changed')
            require(tool_exit(args.previous_tool_exit_receipt) == session_row, 'Original tool receipt changed')
            current = inspect(cid)
            verify_container(current, commands, True)
            require(current['State']['StartedAt'] == started_at, 'Own container restarted during transaction')
            if step['stage'].startswith('student-'):
                require(teacher is not None and teacher_checkpoint() == teacher, 'Final fixed teacher changed before student')
            result['status'] = 'running'
            result['native_started'] |= step['kind'] == 'actual_native_training_future_only'
            step_run(cid, step, baseline, result, number)
            if step['stage'] == 'teacher-locomotion-check-skip':
                teacher = teacher_checkpoint()
                result['fixed_teacher_checkpoint'] = teacher
                persist(result)
        accepted = prefix['steps'] + result['steps']
        native = [r for r in accepted if r['kind'] == 'actual_native_training_future_only']
        cpu = [r for r in accepted if r['kind'] == 'CPU_evidence_validation']
        require(len(result['steps']) == 15 and len(native) == 6 and len(cpu) == 12
                and all(r['returncode'] == 0 for r in accepted), 'Historical3 plus actual15 command outcomes incomplete')
        require(len({(r['wrapper_mapping']['host_pid'], r['wrapper_mapping']['start_time_clock_ticks']) for r in native}) == 6
                and len({(r['kit_mapping']['host_pid'], r['kit_mapping']['start_time_clock_ticks']) for r in native}) == 6,
                'Six unique real wrapper/Kit births required')
        require(len(list((OUTPUT / 'exec-receipts').glob('*.json'))) == 6, 'Expected6 unique native exec receipts')
        for row in cpu:
            require(cpu_report(row['stage']) == row['cpu_report'], 'CPU report changed after acceptance')
        for row in prefix['evidence'].values():checked(row)
        result.update(status='steps_passed_pending_cleanup', new_command_exit0_count=15,
                      historical_command_exit0_count=3, aggregate_command_exit0_count=18,
                      new_native_call_count=4, historical_native_call_count=2, wrapper_mapping_count=6,
                      native_kit_mapping_count=6, cpu_validation_count=12)
    except BaseException as error:
        if result is not None:
            result.update(status='failed', error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        else:
            raise
    finally:
        if result is not None:
            # Never let a failed diagnostic write bypass own-CID shutdown/reaping.
            try:
                persist(result)
            except BaseException as error:
                result['cleanup_errors'].append('pre-cleanup receipt: ' + repr(error))
            if cid is not None:
                try:
                    result['owned_container_stop'] = stop_owned(cid, commands, started_at)
                except BaseException as error:
                    result['cleanup_errors'].append('own stop: ' + repr(error))
                    result['status'] = 'failed_cleanup_uncertain_mutex_held'
                    # Read-only wait, no second stop/retry/foreign signal. Root may
                    # resolve the exact owned CID manually; do not release its GPU.
                    while True:
                        try:
                            info = inspect(cid)
                            verify_container(info, commands, False)
                            require(not remaining_host(cid), 'Owned processes remain')
                            result['owned_container_stop'] = {'after': selected(info), 'running_after_stop': False,
                                                               'resolved_after_uncertain_cleanup': True}
                            break
                        except BaseException as pending:
                            try:
                                persist(result)
                                print('Cleanup uncertain; mutex retained for own CID ' + cid + ': ' + repr(pending), file=sys.stderr, flush=True)
                            except BaseException:
                                pass
                            time.sleep(2)
            job = result.pop('_active_job', None)
            if job is not None:
                try:
                    result['active_cli_returncode_after_own_stop'] = job.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result['cleanup_errors'].append('Own docker exec CLI did not return after own container stop')
                    try:
                        job.terminate()
                        try:
                            result['active_cli_returncode_after_own_stop'] = job.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            job.kill()
                            result['active_cli_returncode_after_own_stop'] = job.wait(timeout=5)
                    except BaseException as error:
                        result['cleanup_errors'].append('Own CLI reap: ' + repr(error))
                except BaseException as error:
                    result['cleanup_errors'].append('Own CLI wait: ' + repr(error))
            try:
                after = inputs()
                write(RECEIPT_DIR / 'input-after.json', after, exclusive=True)
                require(after == before, 'Source/registry/robot original/copy changed')
                require(fingerprint(__file__) == result['helper'], 'Actual host helper changed')
                result['input_postcheck_unchanged'] = True
            except BaseException as error:
                result['cleanup_errors'].append('Input postcheck: ' + repr(error))
            if result['status'] == 'steps_passed_pending_cleanup' and not result['cleanup_errors']:
                require(result.get('owned_container_stop', {}).get('running_after_stop') is False, 'Actual own stop missing')
                result['status'] = 'completed'
            elif result['cleanup_errors']:
                result['status'] = 'failed'
            result['finished_utc'] = utc()
            result['duration_seconds'] = time.monotonic() - result['started_monotonic']
            try:
                persist(result)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                for signum, handler in handlers.items():
                    signal.signal(signum, handler)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
    print(json.dumps({'status': result['status'], 'receipt': str(RECEIPT_DIR / 'receipt.json')}, allow_nan=False))
    return 0 if result['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    run = sub.add_parser('run')
    run.add_argument('--root-authorized-start', action='store_true')
    run.add_argument('--previous-tool-exit-receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'status':
        result = {'endpoint': endpoint(), **previous(), 'native_started': False, 'output_created': False,
                  'lock_acquired': False, 'container_created': False}
        if result['status'] == 'recovered_previous_ready':
            result['session54334_exit'] = tool_exit(SESSION)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    return transaction(args)


if __name__ == '__main__':
    raise SystemExit(main())
