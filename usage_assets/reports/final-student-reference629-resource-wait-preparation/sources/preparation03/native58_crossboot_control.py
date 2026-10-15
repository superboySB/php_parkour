"""Read actual e238/new-wrapper native58 receipts; no Docker/GPU/network calls.

This is the shared host-only admission for the v2 independent native58 review
and formal629 preparation. It never translates a new actual argv into an old
one, executes a scientific worker, or reruns the runtime admission gate.
"""
from __future__ import annotations
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import types

ROOT = Path('/home/dzp/projects/php_parkour')
HERE = ROOT / 'outputs/research/reproduction-20261015'
CONTROL = ROOT / 'outputs/research/final-student-native58-crossboot-control-01'
PREPARATION_SHA = 'e1845f7c53efdbf9348ef876c945017b616077d58069d51f7f90ac1a6ded70fd'
GATE_SHA = '842726d3b6c671c0f863094c17f36262e772f7eb7acda6c4642a03ef419e7ec6'
WRAPPER_SHA = '119a374c80d986ab24c1f6516bccccdd8fbd52338ec08b57a3be400b3421266f'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
OUTER_SOURCE_SHA = '0efbd749b57bf198f7d1d9a33e3cbf97c22a8c1a7a49fc836fcc1100ec8dc1e9'
ROOT_LAUNCH_SHA = 'b2fe8b053fbf985acbe9ed390f137af99ac290b2864a82c5def1f239d8cba615'
ROOT_LAUNCH_REVIEW_SHA = '7fba09496eb91a72b3124c8a1cc7cb15649b6e8ef20c8f8b16f210cffae8ac26'
OLD_BOOT = 'a4856e87-ac1b-4883-8b4e-d8cd48861796'


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require(path.is_relative_to(ROOT) and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe actual control path: ' + str(path))
    return path


def fp(path):
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular actual control file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    sig = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(sig(before) == sig(after), 'Actual control changed during hash')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def parse(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'Duplicate control JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def process(raw):
    fields = raw.rsplit(')', 1)[1].split()
    return {'pid': int(raw.split('(', 1)[0]), 'state': fields[0], 'ppid': int(fields[1]),
            'pgid': int(fields[2]), 'sid': int(fields[3]), 'start_time_clock_ticks': int(fields[19])}


def empty_session(pid):
    matches = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            row = process((directory / 'stat').read_text())
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row['pgid'] == pid or row['sid'] == pid:
            matches.append(row)
    require(not matches, 'Actual owned session is not empty after parent wait')
    return matches


def recorded_api(row, route):
    raw = bytes.fromhex(row['body_hex'])
    require(row['method'] == 'GET' and row['route'] == route
            and len(raw) == row['body_bytes'] and hashlib.sha256(raw).hexdigest() == row['body_sha256']
            and parse(raw) == row['json'], 'Recorded real Unix response fingerprint/route differs')
    return row['json']


def verify_outer_logs(outer, outer_dir, keep):
    expected = [keep(Path(outer_dir) / name) for name in ('launcher.stdout.raw', 'launcher.stderr.raw')]
    require(outer['launcher_logs'] == expected, 'Actual outer must bind exactly both original launcher raw logs')
    require('sources_unchanged' not in outer or outer['sources_unchanged'] is True, 'Actual outer source unchanged declaration failed')


def verify_outer_birth(outer, owner):
    keys = ('pid', 'ppid', 'pgid', 'sid', 'start_time_clock_ticks')
    wrapper, launcher = outer['wrapper_process'], outer['launcher_process']
    for row in (wrapper, launcher):
        saved = process(row['stat'])
        require(all(type(row[k]) is int and row[k] == saved[k] for k in keys)
                and row['start_time_clock_ticks'] > 0, 'Actual outer process stat/structured birth differs')
    require(all(launcher[k] == owner[k] for k in keys)
            and owner['ppid'] == launcher['ppid'] == wrapper['pid'],
            'Original e238 owner is not the actual root outer direct child')


def canonical_verifier(keep):
    canonical = keep(HERE / 'native58_crossboot_control.py')
    loaded = keep(__file__)
    require((loaded['bytes'], loaded['sha256']) == (canonical['bytes'], canonical['sha256']),
            'Loaded copied verifier differs from the canonical reviewed bytes')
    return canonical


def verify_actual_parent(base, parent_exit, parent_exit_sha256, retain=None):
    """Return actual_parent_wait, host_control and all bound_files, or refuse.

    Paths come from the explicit externally pinned e238 exit and its exact new
    argv. ``retain(path, expected=None)`` can be the caller's evidence collector.
    This function imports the pinned gate solely for its file-reading contract
    and source records, never evaluate()/main()/Docker/GPU helpers.
    """
    base, exit_path = safe(base), safe(parent_exit)
    evidence = {}

    def keep(path, expected=None):
        row = fp(path)
        if expected is not None:
            require(row == {k: expected[k] for k in ('path', 'bytes', 'sha256')}, 'Actual bound control bytes differ: ' + str(path))
        require(evidence.get(row['path'], row) == row, 'Conflicting bound control fingerprint')
        evidence[row['path']] = row
        if retain is not None:
            require(retain(path, row) == row, 'Caller evidence collector changed a control fingerprint')
        return row

    def read(path, expected=None):
        row = keep(path, expected)
        raw = safe(path).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Actual JSON changed during read')
        return parse(raw)

    def reference(row):
        return read(row['path'], row)

    require(exit_path.name == 'process-exit.json' and exit_path.parent.name == 'original-parent', 'Exact e238 parent exit path required')
    require(keep(exit_path)['sha256'] == parent_exit_sha256, 'Explicit actual e238 exit SHA differs')
    outer_dir = exit_path.parent.parent
    outer = read(outer_dir / 'wrapper-exit.json')
    start = read(exit_path.with_name('process-start.json'))
    ended = read(exit_path)
    argv = ended['argv']
    require(len(argv) == 15 and argv[:4] == ['/usr/bin/python3', '-B', str(CONTROL / 'run_native58.py'), 'run']
            and argv[4] == '--contract' and argv[6] == '--contract-sha256' and argv[8] == '--output'
            and argv[10] == '--admission-wait-seconds' and argv[12] == '--poll-seconds'
            and argv[14] == '--root-authorized-start', 'Actual new wrapper argv differs; old/native argv is never synthesized')
    wait, poll = float(argv[11]), float(argv[13])
    require(math.isfinite(wait) and math.isfinite(poll) and 0 <= wait <= 7 * 86400 and .1 <= poll <= 60, 'Actual finite waiting argv differs')
    contract_path, contract_sha = safe(argv[5]), argv[7]
    control_dir = safe(argv[9])
    require(argv[5] == str(contract_path) and argv[9] == str(control_dir), 'Actual argv must use canonical absolute paths')
    for name, digest in (('manifest.json', PREPARATION_SHA), ('crossboot_gate.py', GATE_SHA), ('run_native58.py', WRAPPER_SHA)):
        require(keep(CONTROL / name)['sha256'] == digest, 'Reviewed crossboot control source differs')
    spec = importlib.util.spec_from_file_location('readonly_crossboot_receipt_contract', CONTROL / 'crossboot_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    data, contract_fp, prep, plan = gate.contract(contract_path, contract_sha)
    require(data['preparation']['sha256'] == PREPARATION_SHA and data['plan'] == keep(base / 'host-plan.json'), 'Actual root contract refers to another preparation/base')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == data['current_boot_id'] != OLD_BOOT, 'Postexecution review must bind the actual run boot')
    for row in gate.control_records(data, contract_fp, prep):
        keep(row['path'], row)
    control = read(control_dir / 'control-receipt.json')
    terminal = read(base / 'host/launch-receipt.json')
    require(control['schema_version'] == 2 and control['status'] == 'completed_original_native58'
            and type(control['wrapper_returncode']) is int and control['wrapper_returncode'] == 0
            and control['control_mode'] == 'explicit_crossboot_native58_single_host_function_override'
            and control['signals'] == [] and control['sources_unchanged'] is True
            and control['sources_before'] == control['sources_after']
            and control['final_control_identity_verified'] is True
            and control['quality_verified'] is False and control['new_scientific_result_claimed_by_wrapper'] is False
            and not any(k in control for k in ('error', 'final_source_error', 'final_control_error', 'final_native_receipt_error')),
            'Actual wrapper did not complete cleanly with unchanged sources/final identity')
    for key in ('contract', 'preparation', 'source_review', 'plan'):
        require(control[key] == (contract_fp if key == 'contract' else data[key]), 'Actual wrapper control binding differs: ' + key)
    require(control['actual_original_native_receipt'] == keep(base / 'host/launch-receipt.json')
            and control['original_result'] == terminal, 'Actual wrapper did not return the original native result')
    require(control['original_native'] == keep(base / 'control/native58.py')
            and control['original_common'] == keep(base / 'control/common.py')
            and control['replacement'] == {'module': 'native58', 'symbol': 'recovered_previous',
                'replacement_source': keep(CONTROL / 'crossboot_gate.py'), 'historical_boot_id': OLD_BOOT}, 'Actual single host override provenance differs')
    for row in control['sources_before']:
        keep(row['path'], row)

    require(type(ended['actual_wait_returncode']) is int and ended['actual_wait_returncode'] == 0
            and ended['pending_signals'] == [] and ended['launcher_sha256'] == LAUNCHER_SHA
            and ended['helper_sha256'] == WRAPPER_SHA and all(ended.get(k) == v for k, v in start.items()), 'Original e238 did not actually wait0 for this wrapper')
    child, owner = process(start['stat']), process(start['parent_stat'])
    require(child['pid'] == child['pgid'] == child['sid'] == start['pid']
            and child['ppid'] == owner['pid'] == start['parent_pid'] and child['start_time_clock_ticks'] > 0
            and start['boot_id'] == data['current_boot_id'], 'Actual e238 direct child session/birth/boot differs')
    for identity in (control['identity'], control['identity_after']):
        require(all(identity[k] == child[k] for k in ('pid', 'ppid', 'pgid', 'sid', 'start_time_clock_ticks'))
                and identity['boot_id'] == data['current_boot_id'] and identity['actual_proc_argv'] == argv,
                'Actual wrapper self identity differs from original parent')
    require(datetime.datetime.fromisoformat(ended['finished_utc']) >= datetime.datetime.fromisoformat(start['started_utc']), 'Actual parent time order differs')
    outer_protocol = keep(HERE / 'run_formal_reference629.py')
    root_launch = keep(HERE / 'launch_native58_crossboot.py')
    launcher_source = keep(ROOT / 'outputs/research/host_owned_launch.py')
    require(outer_protocol['sha256'] == OUTER_SOURCE_SHA and root_launch['sha256'] == ROOT_LAUNCH_SHA
            and launcher_source['sha256'] == LAUNCHER_SHA and outer['wrapper'] == outer_protocol, 'Actual outer/root/original launcher source differs')
    root_launch_review = read(HERE / 'native58-crossboot-root-launcher-independent-static-review-01.json')
    require(keep(HERE / 'native58-crossboot-root-launcher-independent-static-review-01.json')['sha256'] == ROOT_LAUNCH_REVIEW_SHA
            and root_launch_review['must_fix'] == [] and root_launch_review['root_launcher'] == root_launch
            and root_launch_review['generic_actual_parent_protocol'] == outer_protocol
            and root_launch_review['original_parent'] == launcher_source, 'Independent root launcher source review differs')
    expected_launcher = ['/usr/bin/python3', '-B', launcher_source['path'], '--helper', str(CONTROL / 'run_native58.py'),
                         '--sha256', WRAPPER_SHA, '--output', str(exit_path.parent), '--', *argv]
    require(outer['status'] == 'completed_actual_original_parent_wait'
            and type(outer['actual_launcher_wait_returncode']) is int and outer['actual_launcher_wait_returncode'] == 0
            and outer['launcher_argv'] == expected_launcher and outer['expected_adapter_argv'] == argv
            and outer['boot_id'] == data['current_boot_id'] and outer['pending_signals'] == outer['forwarded_signals'] == []
            and outer['errors'] == outer['signal_forwarding_failures'] == []
            and outer['remaining_launcher_session_members'] == outer['remaining_adapter_session_members'] == []
            and outer['sources_before'] == outer['sources_after'], 'Actual outer owner wait/session/source failed')
    require(outer['launcher_process']['pid'] == outer['launcher_process']['pgid'] == outer['launcher_process']['sid'] == owner['pid']
            and outer['launcher_process']['start_time_clock_ticks'] == owner['start_time_clock_ticks'], 'Actual outer child birth differs from e238 self stat')
    verify_outer_birth(outer, owner)
    outer_start = read(outer_dir / 'wrapper-start.json')
    require(outer_start['status'] == 'starting' and all(outer_start[k] == outer[k] for k in
            ('wrapper', 'launcher_argv', 'expected_adapter_argv', 'started_utc', 'wrapper_process', 'boot_id', 'sources_before'))
            and read(outer_dir / 'launcher-birth.json') == outer['launcher_process'], 'Actual outer start/birth/exit records differ')
    for row in outer['sources_before']:
        keep(row['path'], row)
    require(root_launch in outer['sources_before'] and contract_fp in outer['sources_before'], 'Outer source guard omits real root launch or contract')
    for name in ('process-start.json', 'process-exit.json', 'stdout.raw', 'stderr.raw'):
        require(outer['original_parent_receipts'][name] == keep(exit_path.parent / name), 'Actual e238 original parent bytes differ')
    verify_outer_logs(outer, outer_dir, keep)
    raw_stdout = safe(exit_path.parent / 'stdout.raw').read_text()
    decoder, position, messages = json.JSONDecoder(), 0, []
    while raw_stdout[position:].strip():
        position += len(raw_stdout[position:]) - len(raw_stdout[position:].lstrip())
        message, end = decoder.raw_decode(raw_stdout, position)
        messages.append(message); position = end
    require(messages and messages[-1] == {'status': control['status'],
            'control_receipt': keep(control_dir / 'control-receipt.json'), 'wrapper_returncode': 0},
            'Original parent raw stdout does not bind the actual final control receipt')

    endpoint = reference(data['unix_endpoint_observation'])
    socket_identity = endpoint['paths']['/var/run/docker.sock']

    def daemon(row):
        recorded_api(row, '/info')
        require(gate.daemon_identity(row) == data['daemon'], 'Recorded actual daemon differs from contract')

    def actor_context(row):
        require(row['actor'] == endpoint['actor'], 'Recorded actual actor differs')
        commands = row['actual_readonly_commands']
        require(len(commands) == 3 and all(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode'] == 0 for x in commands), 'Actual CLI identity requests failed')
        expected_name = Path(gate.verify({**endpoint['commands'][0]['stdout'], 'path': str(ROOT / endpoint['commands'][0]['stdout']['path'])})).read_text().strip()
        require(commands[0]['argv'] == ['docker', 'context', 'show'] and bytes.fromhex(commands[0]['stdout_hex']).decode().strip() == expected_name
                and commands[1]['argv'] == ['docker', 'context', 'inspect', expected_name]
                and commands[2]['argv'] == ['docker', 'info', '--format', '{{json .}}'], 'Actual CLI context argv differs')
        context = parse(bytes.fromhex(commands[1]['stdout_hex']))
        info = parse(bytes.fromhex(commands[2]['stdout_hex']))
        require(len(context) == 1 and context[0]['Name'] == expected_name
                and context[0]['Endpoints']['docker']['Host'] == 'unix:///var/run/docker.sock'
                and {'id': info['ID'], 'docker_root': info['DockerRootDir'], 'os_type': info['OSType']} == data['daemon'], 'Recorded CLI and actual Unix daemon differ')

    def mutex(row):
        require({k: row[k] for k in ('path', 'device', 'inode')} == data['mutex'] and row['owner_pid'] == child['pid'], 'Actual mutex is not the original inode owned by the real wrapper')
        fields = row['actual_proc_locks_line'].split()
        major, minor, inode = fields[5].split(':')
        require(fields[1:4] == ['FLOCK', 'ADVISORY', 'WRITE'] and int(fields[4]) == child['pid'] and fields[6:] == ['0', 'EOF']
                and (int(major, 16), int(minor, 16), int(inode)) == (os.major(row['device']), os.minor(row['device']), row['inode']), 'Actual kernel flock raw identity differs')

    def idle(row):
        queries = row['actual_queries']
        require(row['uuid'] == gate.GPU and row['idle'] is True and row['existing_compute_processes'] == []
                and len(queries) == 2 and all(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode'] == 0 for x in queries), 'Actual pre-native GPU was not idle')
        require([x['argv'] for x in queries] == [['nvidia-smi', q, '--format=csv,noheader,nounits'] for q in ('--query-gpu=uuid', '--query-compute-apps=gpu_uuid,pid')]
                and bytes.fromhex(queries[0]['stdout_hex']).decode().splitlines().count(gate.GPU) == 1
                and not any(line.split(',')[0].strip() == gate.GPU for line in bytes.fromhex(queries[1]['stdout_hex']).decode().splitlines() if line.strip()), 'Recorded physical GPU query differs')

    pre = control['pre_execute_idle_check']
    require(pre['ready_for_original_execute'] is True and pre['native_started'] is False, 'No successful real pre-native check')
    mutex(pre['mutex']); daemon(pre['daemon']); actor_context(pre['actor_context']); idle(pre['gpu'])
    calls = control['gate_calls']
    require(calls and [i for i, row in enumerate(calls) if row['ready']] == [len(calls) - 1], 'Exactly one final ready runtime gate required')
    ready = calls[-1]
    require(ready == terminal['previous_recovered_proof'] and ready['status'] == 'recovered_previous_ready'
            and ready['admission_mode'] == 'explicit_crossboot_continuation' and ready['contract'] == contract_fp
            and ready['historical_boot_id'] == OLD_BOOT and ready['current_boot_id'] == data['current_boot_id']
            and ready['original_session54334_exit_code'] == 143 and ready['original_root_normal_exit_verified'] is False
            and ready['original_host_observer_gap_preserved'] is True and ready['original_missing_historical_writer_mappings'] == 8
            and ready['original_configurations'] == 629 and ready['original_clean_workers'] == 1258
            and ready['original_full_video_decodes'] == 629 and ready['original_unique_host_writer_mappings'] == 1250
            and ready['supplement_clean_workers'] == ready['supplement_host_writer_mappings'] == 8
            and ready['supplement_full_video_decodes'] == 4 and ready['owned_host_children_absent'] is True
            and ready['gpu_mutex_owned_by_current_process'] is True and ready['gpu_idle_verified'] is True
            and ready['quality_verified'] is False and ready['native_started_by_gate'] is False and ready['writes'] is False,
            'Actual gate concealed historical failure/gaps or refers to another result')
    require(ready['gate'] == keep(CONTROL / 'crossboot_gate.py') and ready['historical_gate'] == keep(base / 'control/previous_recovered_02.py'), 'Actual ready gate source differs')
    mutex(ready['mutex']); mutex(ready['mutex_after'])
    daemon(ready['daemon_before']); daemon(ready['daemon_after'])
    actor_context(ready['actor_context_before']); actor_context(ready['actor_context_after'])
    idle(ready['gpu_before']); idle(ready['gpu_after'])
    require(ready['unix_endpoint_before'] == ready['unix_endpoint_after'] == socket_identity, 'Actual pre-native socket changed')
    for row in ready['historical_evidence'].values():
        keep(row['path'], row)
    historical = gate.load(base / 'control/previous_recovered_02.py', 'readonly_original_historical_stop_facts')
    manager = reference(ready['historical_evidence'][str(historical.BASE / 'manager/receipt.json')])
    supplement = reference(ready['historical_evidence'][str(historical.FOUR / 'host/launch-receipt.json')])
    stops = [(manager['adopted_gpu_container_stop'], historical.CID, True),
             (manager['owned_cpu_container_stop'], manager['cpu_container_id'], False),
             (supplement['owned_gpu_container_stop'], supplement['gpu_container_id'], True),
             (supplement['owned_plan_container_stop'], supplement['cpu_plan_container_id'], False),
             (supplement['owned_final_container_stop'], supplement['cpu_final_container_id'], False)]
    require(len(ready['current_resources']) == 5 and ready['historical_containers_stopped'] == ready['current_resources'], 'Five separate historical/current resources required')
    for row, (stop, cid, gpu) in zip(ready['current_resources'], stops):
        facts = gate.historical_stop(historical, stop, cid, gpu)
        require(all(row[k] == value for k, value in facts.items()), 'Historical stop facts were rewritten')
        initial, final = row['actual_current_request'], row['actual_current_recheck']
        recorded_api(initial, '/containers/' + cid + '/json'); recorded_api(final, '/containers/' + cid + '/json')
        if row['current_status'] == 'current_absent_typed_404':
            require(gate.typed_absent(initial, cid) and gate.typed_absent(final, cid), 'Current missing CID has no genuine typed404')
        else:
            require(row['current_status'] == 'current_stopped_original_full_identity_verified'
                    and initial['http_status'] == final['http_status'] == 200 and initial['json'] == final['json'], 'Recorded current stopped CID changed')
            # Explicit OFFLINE validation of actual recorded JSON through the
            # unchanged original function; never presented as a fresh inspect.
            offline = types.FunctionType(historical.stopped.__code__, {**historical.stopped.__globals__, 'docker_get': lambda route, item=initial: item['json']})
            offline(stop, cid, gpu)
    expected_pids = [(2007976, 106799627), (1914028, 106696455)]
    expected_pids += [(x['host_cli_pid'], x['host_cli_identity']['birth']) for x in supplement['commands']]
    expected_pids += [(supplement['observer_host_pid'], supplement['observer_host_identity']['birth'])]
    require(ready['separate_supplement_case_ids'] == historical.CASE_IDS
            and [(x['historical_pid'], x['historical_start_time_clock_ticks']) for x in ready['historical_pid_checks']] == expected_pids
            and all(x['historical_boot_id'] == OLD_BOOT and x['current_boot_id'] == data['current_boot_id']
                    and x['status'] == 'historical_identity_not_applicable_after_boot_change' and x['current_proc_read'] is False for x in ready['historical_pid_checks']), 'Cross-boot interpretation escaped the exact historical identities')
    final = control['final_control_observations']
    require(final['boot_id'] == data['current_boot_id'] and final['unix_endpoint'] == socket_identity, 'Actual final boot/socket changed')
    daemon(final['daemon']); actor_context(final['actor_context'])
    require(empty_session(owner['pid']) == empty_session(child['pid']) == [], 'Actual owned session is not empty')
    tree_sets = []
    for directory in (outer_dir, control_dir):
        names = set()
        for path in directory.rglob('*'):
            safe(path)
            if path.is_file():
                names.add(str(path.relative_to(directory))); keep(path)
            else:
                require(path.is_dir(), 'Special control evidence file')
        tree_sets.append((directory, names))
    for path, row in list(evidence.items()):
        require(fp(path) == row, 'Actual control evidence changed before admission')
    for directory, names in tree_sets:
        require({str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()} == names, 'Actual closed control file set changed')
    canonical_source = canonical_verifier(keep)
    host = {'status': 'verified_actual_crossboot_native58_parent_and_control', 'original_parent_start': keep(exit_path.with_name('process-start.json')),
            'actual_parent_wait': keep(exit_path), 'outer_supervisor_exit': keep(outer_dir / 'wrapper-exit.json'),
            'actual_wrapper_control': keep(control_dir / 'control-receipt.json'), 'contract': contract_fp,
            'preparation': data['preparation'], 'source_review': data['source_review'], 'shared_verifier': canonical_source,
            'root_launcher': root_launch, 'root_launcher_source_review': keep(HERE / 'native58-crossboot-root-launcher-independent-static-review-01.json'),
            'outer_protocol': outer_protocol, 'original_parent_source': launcher_source,
            'historical_boot_id': OLD_BOOT, 'actual_run_boot_id': data['current_boot_id'],
            'control_directory': str(control_dir), 'original_parent_directory': str(exit_path.parent),
            'operational_directories': [str(outer_dir), str(control_dir)],
            'original_session54334_exit_code': 143, 'historical_missing_writer_mappings': 8,
            'remaining_owned_sessions': [], 'scope': 'Actual new host control and parent wait only; scientific/worker/pose/video validation remains mandatory in the caller.'}
    return {'status': 'ready', 'actual_parent_wait': keep(exit_path), 'host_control': host, 'bound_files': list(evidence.values())}
