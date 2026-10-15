"""Read actual e238/new-wrapper native58 receipts; no Docker/GPU/network calls.

This is the shared host-only admission for the v2 independent native58 review
and formal629 preparation. It never translates a new actual argv into an old
one, executes a scientific worker, or reruns the runtime admission gate.
"""
from __future__ import annotations
import ast
import datetime
import subprocess
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import stat
import types

ROOT = Path('/home/dzp/projects/php_parkour')
HERE = ROOT / 'outputs/research/reproduction-20261015'
CONTROL = ROOT / 'outputs/research/final-student-native58-crossboot-control-04'
PREPARATION_SHA = 'b4699127bc12b6f3721d55733fedc9749a9364dc7562d345f89593090d4146f5'
GATE_SHA = 'd5f85fde8c36de1c98b25b5521d12652e5ccf6f64b129b13652c2245c468a188'
WRAPPER_SHA = '0bcc23829d9fc51a5066bf7cb25f879ff7abe3f6090f980c73a7e06b1a9080ed'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
OUTER_SOURCE_SHA = '0efbd749b57bf198f7d1d9a33e3cbf97c22a8c1a7a49fc836fcc1100ec8dc1e9'
ROOT_LAUNCH_SHA = '143beb014c539e2cfae55764f05ca49795c6799780997c3676efffa80d122429'
ROOT_LAUNCH_REVIEW_SHA = '207c8009afc1b3fbca2c1106a5765922de865afe9fe038ca6d10872f3973221b'
RESOURCE_SHA = '8e0914a76f18e5d7a3611b5a93f6f4ad85b32f1082583e63dd52797b326c2b79'
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
    canonical = keep(HERE / 'native58_resource_wait_control.py')
    loaded = keep(__file__)
    require((loaded['bytes'], loaded['sha256']) == (canonical['bytes'], canonical['sha256']),
            'Loaded copied verifier differs from the canonical reviewed bytes')
    return canonical


def original_gpu_nodes(base, keep):
    source = keep(Path(base) / 'control/native58.py')
    require(source['sha256'] == '31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43',
            'Original frozen GPU guard source differs')
    tree = ast.parse(safe(source['path']).read_bytes())
    return [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            for name in ('call', 'gpu_idle')]


def replay_original_gpu_guard(base, queries, keep):
    """Offline replay of the two original function ASTs over actual raw bytes."""
    require(len(queries) == 2, 'Exactly two successful original guard queries required')
    expected = [['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'],
                ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits']]
    position = 0

    def run(argv, **kwargs):
        nonlocal position
        require(position < 2 and argv == expected[position]
                and kwargs == {'capture_output': True, 'text': True, 'timeout': 60}, 'Offline original query arguments differ')
        row = queries[position]; position += 1
        require(row['argv'] == argv and type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0,
                'Successful actual GPU query wait0 required')
        raw = [safe(keep(row[label]['path'], row[label])['path']).read_bytes() for label in ('stdout', 'stderr')]
        return subprocess.CompletedProcess(argv, row['actual_wait_returncode'], *(value.decode() for value in raw))

    namespace = {'subprocess': types.SimpleNamespace(run=run), 'require': require,
                 'UUID': 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'}
    exec(compile(ast.Module(body=original_gpu_nodes(base, keep), type_ignores=[]),
                 str(Path(base) / 'control/native58.py'), 'exec'), namespace)
    try:
        result = namespace['gpu_idle']()
    except ValueError as error:
        require(type(error) is ValueError and str(error) == 'Selected GPU has existing compute; never stop other work',
                'Only the exact original busy predicate can be a recorded waiting round')
        require(position == 2, 'Original busy guard did not read both query receipts')
        return 'busy'
    require(position == 2 and result == {'uuid': namespace['UUID'], 'existing_compute_processes': []},
            'Offline original idle return differs')
    return 'idle'


def verify_resource_queries(control, data, plan, base, keep, read, mutex):
    budget, poll = data.get('resource_wait_seconds', 1800), data.get('resource_poll_seconds', 5)
    require(type(budget) in (int, float) and 0 < budget <= 3600
            and type(poll) in (int, float) and .1 <= poll <= 60 and plan['host_total_timeout_seconds'] == 43200,
            'Explicit bounded host waiting policy differs')
    require(control['resource_policy'] == {'per_gpu_idle_call_budget_seconds': budget,
            'max_contract_budget_seconds': 3600, 'query_timeout_seconds_max': 30,
            'overall_original_wall_seconds': 43200, 'waiting_counts_against_original_wall': True,
            'original_plan_and_worker_timers_unchanged': True}, 'Actual resource policy declaration differs')
    nodes = original_gpu_nodes(base, keep)
    require(control['original_gpu_guard_ast_sha256'] == hashlib.sha256(ast.dump(
            ast.Module(body=nodes, type_ignores=[]), include_attributes=False).encode()).hexdigest(),
            'Actual resource guard AST does not bind the original call/gpu_idle functions')
    queries = control['gpu_queries']
    require(queries and [row['index'] for row in queries] == list(range(len(queries))), 'Complete contiguous actual query inventory required')
    expected = [['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'],
                ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits']]
    for row in queries:
        require(row['argv'] in expected and row['child_created'] is True and type(row['pid']) is int and row['pid'] > 0
                and type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0
                and row['timed_out'] is False and 0 < row['actual_query_timeout_seconds'] <= 30
                and row['requested_original_call_timeout_seconds'] == 60
                and math.isfinite(row['started_monotonic']) and math.isfinite(row['finished_monotonic'])
                and row['finished_monotonic'] >= row['started_monotonic']
                and not any(key in row for key in ('error', 'metadata_or_communication_error', 'own_query_cleanup_error', 'own_query_cleanup_signal')),
                'Actual successful query birth/wait/budget differs')
        mutex(row['mutex'])
        if 'stat' in row:
            birth = process(row['stat'])
            require(birth['pid'] == row['pid'] and birth['ppid'] == row['mutex']['owner_pid'] and birth['start_time_clock_ticks'] > 0, 'Query raw birth differs')
        else:
            require(bool(row.get('metadata_unavailable_after_actual_child_exit')), 'Query birth or explicit fast-exit observation required')
        for label in ('stdout', 'stderr'):
            keep(row[label]['path'], row[label])
        require(read(Path(row['stdout']['path']).with_name(f"{row['index']:05d}.json")) == row,
                'Actual per-query JSON and aggregate record differ')
    calls = control['resource_wait_calls']
    require(len(calls) == 9 and [call['index'] for call in calls] == list(range(9)),
            'Original native initial plus four pairs of GPU idle calls required')
    origin = control['original_execute_started_monotonic']
    require(math.isfinite(origin) and control['overall_guard_start_scope'] ==
            'Conservative actual host monotonic immediately before original execute, earlier than its local deadline',
            'Real original host wall budget provenance differs')
    used = set()
    for call in calls:
        require(call['status'] == 'idle' and call['budget_seconds'] == budget
                and call['original_overall_limit_seconds'] == 43200 and 'error' not in call
                and origin <= call['started_monotonic'] <= call['finished_monotonic'] <= origin + 43200
                and math.isfinite(call['actual_wall_seconds']) and call['actual_wall_seconds'] >= call['finished_monotonic'] - call['started_monotonic'],
                'Actual finite GPU resource waiting call or original host wall differs')
        rounds = call['rounds']
        require(rounds and [r['status'] for r in rounds] == ['exact_original_gpu_busy'] * (len(rounds)-1) + ['exact_original_gpu_idle'],
                'Only exact original busy rounds followed by actual idle are permitted')
        for number, round_ in enumerate(rounds):
            require(call['started_monotonic'] <= round_['observed_monotonic'] <= min(call['finished_monotonic'], call['started_monotonic'] + budget), 'GPU round time outside its real call')
            if 'mutex' in round_:
                mutex(round_['mutex'])
            rows = round_['queries']
            for row in rows:
                require(row == queries[row['index']] and row['index'] not in used, 'Resource round reused or changed an actual query')
                used.add(row['index'])
            require(replay_original_gpu_guard(base, rows, keep) == ('idle' if number == len(rounds)-1 else 'busy'),
                    'Recorded original busy/idle predicate differs from actual raw query bytes')
    return queries, used


def normalized_inspect(value):
    require(isinstance(value, dict) and isinstance(value.get('Mounts'), list), 'Complete inspect and Mounts list required')
    mounts = value['Mounts']
    require(all(isinstance(row, dict) and isinstance(row.get('Destination'), str) for row in mounts)
            and len({row['Destination'] for row in mounts}) == len(mounts), 'Unique complete Docker mount rows required')
    return {**value, 'Mounts': sorted(mounts, key=lambda row: row['Destination'])}


def verify_failed41_release(release, data, gate, keep, read):
    review = read(data['failed41_review']['path'], data['failed41_review'])
    require(data['failed41_review']['sha256'] == gate.FAILED_REVIEW_SHA and review['status'] == 'passed_readonly_preserved_failed41_partial_audit'
            and review['must_fix'] == [] and review['actual_native_status'] == 'failed', 'Pinned actual failed41 audit differs')
    require(release['status'] == 'preserved_failed41_current_resources_released'
            and release['failed41_review'] == data['failed41_review'] and release['current_boot_id'] == data['current_boot_id']
            and release['original_parent_wait_returncode'] == 1 and release['original_completed_cases'] == 41
            and release['current_owned_session_members'] == [] and release['is_complete58_admission'] is False,
            'Actual previous failed41 was concealed or not released')
    require(release['evidence'] == list({row['path']: row for row in review['evidence_fingerprints']}.values()),
            'Full preserved failed41 evidence binding differs')
    for row in release['evidence']:
        keep(row['path'], row)
    require(len(release['containers']) == 3, 'Three previous failed-cohort containers required')
    for row, old in zip(release['containers'], review['stopped_gpu_containers']):
        cid = row['container_id']
        require(cid == old['container_id'] and row['historical_inspect'] == old['execution']['stdout'], 'Previous exact CID changed')
        archived = read(row['historical_inspect']['path'], row['historical_inspect'])[0]
        response = row['actual_current_request']; actual = recorded_api(response, '/containers/' + cid + '/json')
        final = row['actual_current_recheck']; final_json = recorded_api(final, '/containers/' + cid + '/json')
        if row['current_status'] == 'current_absent_typed_404':
            require(gate.typed_absent(response, cid) and gate.typed_absent(final, cid), 'Previous failed container absence lacks typed404')
        else:
            require(row['current_status'] == 'current_stopped143_full_identity_verified' and response['http_status'] == 200
                    and final['http_status'] == 200 and normalized_inspect(final_json) == normalized_inspect(actual)
                    and all(actual[key] == archived[key] for key in ('Id', 'Image', 'Name', 'Config', 'HostConfig', 'State'))
                    and actual['State']['Running'] is False and actual['State']['ExitCode'] == 143
                    and sorted(actual['Mounts'], key=lambda x: x['Destination']) == sorted(archived['Mounts'], key=lambda x: x['Destination']),
                    'Previous failed container current identity/stop143 differs')
    previous_root = HERE / 'student-native58-crossboot-host-01'
    evidence_map = {row['path']: row for row in release['evidence']}
    parent = read(previous_root / 'original-parent/process-exit.json', evidence_map[str(previous_root / 'original-parent/process-exit.json')])
    outer = read(previous_root / 'wrapper-exit.json', evidence_map[str(previous_root / 'wrapper-exit.json')])
    birth = process(parent['stat'])
    expected_owners = [outer['wrapper_process'], outer['launcher_process'],
                       {'pid': parent['pid'], 'sid': birth['sid'], 'start_time_clock_ticks': birth['start_time_clock_ticks']}]
    require(parent['boot_id'] == outer['boot_id'] == data['current_boot_id']
            and type(parent['actual_wait_returncode']) is int and parent['actual_wait_returncode'] == 1
            and type(outer['actual_launcher_wait_returncode']) is int and outer['actual_launcher_wait_returncode'] == 1,
            'Actual previous failed41 parent/outerwait1 differ')
    require([row['historical_identity'] for row in release['current_pid_checks']] == expected_owners, 'Three exact real previous owners required')
    for row in release['current_pid_checks']:
        identity = row['historical_identity']
        empty_session(identity['sid'])
        require(row['current_status'] in ('absent_same_boot', 'different_birth_or_zombie_same_boot'), 'Previous owner release scope differs')
        if 'actual_stat' in row:
            now = process(row['actual_stat'])
            require(now['pid'] == identity['pid'] and (now['start_time_clock_ticks'] != identity['start_time_clock_ticks'] or now['state'] == 'Z'),
                    'Previous same-boot owner remained live')
    return {'failed41_review': data['failed41_review'], 'release_status': release['status'],
            'current_boot_id': data['current_boot_id'], 'actual_original_parent_wait_returncode': 1,
            'original_partial_completed_cases': 41, 'never_complete58_evidence': True}


def verify_readonly_diagnostics(control, control_dir, keep, read):
    directory = safe(Path(control_dir) / 'readonly-observations')
    records = control['readonly_diagnostic_records']
    require(records, 'Actual readonly API/CLI raw journal is required')
    api_keys = ('method', 'route', 'http_status', 'headers', 'body_hex', 'body_bytes', 'body_sha256')
    cli_keys = ('argv', 'actual_wait_returncode', 'stdout_hex', 'stderr_hex')
    api_observations, cli_observations, files = set(), set(), set()

    def signature(row, keys):
        return json.dumps({key: row[key] for key in keys}, sort_keys=True, separators=(',', ':'), allow_nan=False)

    for index, reference in enumerate(records):
        path = safe(reference['path'])
        require(path.parent == directory and path.name.startswith(f'{index:05d}.'), 'Diagnostic record path/index differs')
        record = read(path, reference); files.add(str(path))
        require(record['index'] == index and record['scope'] == 'actual_readonly_control_observation_not_scientific_completion',
                'Actual readonly diagnostic provenance differs')
        row, kind = record['observation'], record['kind']
        require(kind in ('docker_api', 'docker_cli'), 'Completed run has a failed or unexpected readonly diagnostic')
        require(path.name == f'{index:05d}.{kind}.json', 'Diagnostic kind/file differs')
        if kind == 'docker_api':
            require(row['method'] == 'GET' and (row['route'] == '/info' or re.fullmatch(r'/containers/[0-9a-f]{64}/json', row['route']))
                    and type(row['http_status']) is int and row['http_status'] in (200, 404)
                    and 'error' not in row and not row.get('incomplete_body', False), 'Actual readonly API failed or incomplete')
            raw_fp = keep(record['body']['path'], record['body']); files.add(raw_fp['path'])
            raw = safe(raw_fp['path']).read_bytes()
            recorded_api({**row, 'json': parse(raw)}, row['route'])
            require(raw == bytes.fromhex(row['body_hex']) and raw_fp['sha256'] == row['body_sha256']
                    and raw_fp['bytes'] == row['body_bytes'] and safe(raw_fp['path']).parent == directory,
                    'Actual readonly API body bytes differ')
            api_observations.add(signature(row, api_keys))
        else:
            require(type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0
                    and (row['argv'] in (['docker', 'context', 'show'], ['docker', 'info', '--format', '{{json .}}'])
                         or (len(row['argv']) == 4 and row['argv'][:3] == ['docker', 'context', 'inspect'] and isinstance(row['argv'][3], str) and row['argv'][3])),
                    'Actual readonly CLI wait/argv failed')
            for label in ('stdout', 'stderr'):
                raw_fp = keep(record[label]['path'], record[label]); files.add(raw_fp['path'])
                require(safe(raw_fp['path']).parent == directory
                        and safe(raw_fp['path']).read_bytes() == bytes.fromhex(row[label + '_hex']),
                        'Actual readonly CLI raw bytes differ')
            cli_observations.add(signature(row, cli_keys))

    def require_observed(value):
        if isinstance(value, dict):
            if all(key in value for key in api_keys):
                require(signature(value, api_keys) in api_observations, 'Control API proof is absent from actual raw diagnostic journal')
            elif all(key in value for key in cli_keys):
                require(signature(value, cli_keys) in cli_observations, 'Control CLI proof is absent from actual raw diagnostic journal')
            for item in value.values():
                require_observed(item)
        elif isinstance(value, list):
            for item in value:
                require_observed(item)

    require_observed(control)
    actual_files = set()
    for path in directory.rglob('*'):
        safe(path)
        if path.is_file():
            actual_files.add(str(path))
        else:
            require(path.is_dir(), 'Special readonly diagnostic file')
    require(actual_files == files, 'Closed readonly diagnostic file set differs from complete journal')
    return {'directory': str(directory), 'record_count': len(records), 'complete_raw_journal_bound': True}


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
    for name, digest in (('manifest.json', PREPARATION_SHA), ('crossboot_gate.py', GATE_SHA), ('run_native58.py', WRAPPER_SHA), ('gpu_resource_wait.py', RESOURCE_SHA)):
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
    require(control['schema_version'] == 3 and control['status'] == 'completed_original_native58'
            and type(control['wrapper_returncode']) is int and control['wrapper_returncode'] == 0
            and control['control_mode'] == 'explicit_crossboot_native58_two_host_function_overrides'
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
            and control['host_overrides'] == ['recovered_previous', 'gpu_idle']
            and control['time_module_unmodified'] is True
            and control['resource_source'] == keep(CONTROL / 'gpu_resource_wait.py')
            and control['failed41_review'] == data['failed41_review'], 'Actual two host overrides differ')
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
    root_launch = keep(HERE / 'launch_native58_resource_wait04.py')
    launcher_source = keep(ROOT / 'outputs/research/host_owned_launch.py')
    require(outer_protocol['sha256'] == OUTER_SOURCE_SHA and root_launch['sha256'] == ROOT_LAUNCH_SHA
            and launcher_source['sha256'] == LAUNCHER_SHA and outer['wrapper'] == outer_protocol, 'Actual outer/root/original launcher source differs')
    root_launch_review = read(HERE / 'native58-resource-wait-root-launcher-independent-static-review-04.json')
    require(keep(HERE / 'native58-resource-wait-root-launcher-independent-static-review-04.json')['sha256'] == ROOT_LAUNCH_REVIEW_SHA
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

    resource_queries, used_queries = verify_resource_queries(control, data, plan, base, keep, read, mutex)

    def gpu_record(row, expected_state=None):
        require(row['uuid'] == gate.GPU and len(row['query_records']) == 2, 'Both exact original GPU query receipts required')
        for query in row['query_records']:
            require(query == resource_queries[query['index']], 'Gate GPU query differs from complete recorded query inventory')
            used_queries.add(query['index'])
        state = replay_original_gpu_guard(base, row['query_records'], keep)
        require(expected_state is None or state == expected_state, 'Recorded original GPU idle predicate differs')
        require(row['idle'] is (state == 'idle') and row['existing_compute_processes'] ==
                ([] if state == 'idle' else ['see exact raw query stdout']) and row['original_guard_result'] ==
                ({'uuid': gate.GPU, 'existing_compute_processes': []} if state == 'idle' else None), 'Actual observer state differs from the original guard')

    def idle(row):
        gpu_record(row, 'idle')

    prechecks = control['pre_execute_idle_checks']
    require(prechecks and [i for i, row in enumerate(prechecks) if row['ready_for_original_execute']] == [len(prechecks) - 1],
            'Exactly one final successful actual pre-native check required')
    for checked in prechecks:
        if 'gpu' in checked:
            gpu_record(checked['gpu'])
    pre = prechecks[-1]
    require(pre['ready_for_original_execute'] is True and pre['native_started'] is False, 'No successful real pre-native check')
    mutex(pre['mutex']); daemon(pre['daemon']); actor_context(pre['actor_context']); idle(pre['gpu'])
    calls = control['gate_calls']
    require(calls and [i for i, row in enumerate(calls) if row['ready']] == [len(calls) - 1], 'Exactly one final ready runtime gate required')
    for checked in calls:
        for key in ('gpu_before', 'gpu_after'):
            if key in checked:
                gpu_record(checked[key])
    require(used_queries == set(range(len(resource_queries))), 'Actual query inventory contains an unbound query')
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
            and ready['quality_verified'] is False and ready['native_started_by_gate'] is False and ready['scientific_sources_and_inputs_written'] is False
            and ready['local_query_receipts_written'] is True and ready['local_readonly_diagnostics_written'] is True,
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
                    and initial['http_status'] == final['http_status'] == 200 and normalized_inspect(initial['json']) == normalized_inspect(final['json']), 'Recorded current stopped CID changed')
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
    failed_release = verify_failed41_release(ready['failed41_prerequisite'], data, gate, keep, read)
    daemon(ready['daemon_after_failed41']); mutex(ready['mutex_after_failed41'])
    final = control['final_control_observations']
    require(final['boot_id'] == data['current_boot_id'] and final['unix_endpoint'] == socket_identity, 'Actual final boot/socket changed')
    daemon(final['daemon']); actor_context(final['actor_context'])
    readonly_journal = verify_readonly_diagnostics(control, control_dir, keep, read)
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
    host = {'status': 'verified_actual_resource_wait_native58_parent_and_control', 'control_revision': 4, 'original_parent_start': keep(exit_path.with_name('process-start.json')),
            'actual_parent_wait': keep(exit_path), 'outer_supervisor_exit': keep(outer_dir / 'wrapper-exit.json'),
            'actual_wrapper_control': keep(control_dir / 'control-receipt.json'), 'contract': contract_fp,
            'preparation': data['preparation'], 'source_review': data['source_review'], 'shared_verifier': canonical_source,
            'resource_source': keep(CONTROL / 'gpu_resource_wait.py'), 'failed41_review': data['failed41_review'],
            'failed41_release': failed_release, 'resource_policy': control['resource_policy'], 'readonly_diagnostics': readonly_journal,
            'root_launcher': root_launch, 'root_launcher_source_review': keep(HERE / 'native58-resource-wait-root-launcher-independent-static-review-04.json'),
            'outer_protocol': outer_protocol, 'original_parent_source': launcher_source,
            'historical_boot_id': OLD_BOOT, 'actual_run_boot_id': data['current_boot_id'],
            'control_directory': str(control_dir), 'original_parent_directory': str(exit_path.parent),
            'operational_directories': [str(outer_dir), str(control_dir)],
            'original_session54334_exit_code': 143, 'historical_missing_writer_mappings': 8,
            'remaining_owned_sessions': [], 'scope': 'Actual new host control and parent wait only; scientific/worker/pose/video validation remains mandatory in the caller.'}
    return {'status': 'ready', 'actual_parent_wait': keep(exit_path), 'host_control': host, 'bound_files': list(evidence.values())}
