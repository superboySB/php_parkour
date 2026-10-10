#!/usr/bin/env python3
"""Read-only fresh629 verifier and atomic publisher. Never starts any process."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import uuid

HERE = Path(__file__).resolve().parent
WORKSPACE = Path('/home/dzp/projects/php_parkour')
COHORT = WORKSPACE / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
HOST_PLAN = '44d6e71e8ef1d12c5b479d8e3bcb411c39e8d7daa1c3bac109d6edd7417502d0'
HOST_PLAN_FILE = '960c5e1ef7e75d05b91f253d152a4d01fd5c07716091c48868c57f86ba74fa5d'
NATIVE_PLAN = '1e3483f7b35dd7592d9e5e0b02c13143a44e4f17a5cd0ba24def25c0229a6e6f'
NATIVE_PLAN_FILE = 'dc8a2994f246a221d2b745a355dd8512964434397db9e47b9ed6131bbb06f287'
FREEZE = '599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169'
MATRIX_SOURCE = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
PUBLISHER_SOURCE = '5b0d967f96f0d62ca474dcf4746e53f0a4aecd459790d0591aa31d2e89679a7a'
UUID = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
CHUNK_LIMIT = 25 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON literal: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def load(path):
    return parse_json(regular(path).read_bytes())


def regular(path):
    path = Path(path)
    require('..' not in path.parts, 'Parent path traversal is forbidden')
    require(path.is_file() and not path.is_symlink(), 'Regular file required: ' + str(path))
    require(not any(p.is_symlink() for p in path.parents), 'Symlink parent is forbidden: ' + str(path))
    return path


def files(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Regular directory required: ' + str(directory))
    result = []
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Symlink in evidence tree: ' + str(path))
        if path.is_dir():
            continue
        result.append(regular(path))
    return result


def mapped(base, value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'Native path must be absolute and canonical')
    for prefix, target in ((Path('/workspace/php_parkour'), base/'source'),
                           (Path('/outputs'), base/'outputs'), (Path('/data'), base/'inputs')):
        if path.is_relative_to(prefix):
            result = target / path.relative_to(prefix)
            require(not any(p.is_symlink() for p in (result, *result.parents)), 'Symlink native path')
            return result
    raise ValueError('Native path outside reviewed namespaces: ' + str(value))


def check_record(item, path):
    path = regular(path)
    size = item.get('bytes', item.get('size'))
    require(size is not None and path.stat().st_size == size and sha(path) == item['sha256'],
            'Retained bytes/SHA changed: ' + str(path))
    return path


def signed(value, field):
    result = dict(value)
    recorded = result.pop(field)
    require(identity(result) == recorded, 'JSON identity changed: ' + field)
    return recorded


def header(base):
    base = Path(base)
    require(base == COHORT and base.resolve() == base, 'Only the exact reviewed fresh629 cohort is accepted')
    host = load(base/'host-plan.json')
    require(sha(base/'host-plan.json') == HOST_PLAN_FILE and signed(host, 'plan_sha256') == HOST_PLAN,
            'Frozen host plan differs')
    require(host['image_id'] == IMAGE and host['gpu_uuid'] == UUID and host['output'] == str(base)
            and host['workspace'] == str(WORKSPACE) and host['configurations'] == 629 and host['scenarios'] == 17,
            'Host image/UUID/workspace/count contract differs')
    require(host['freeze_manifest_sha256'] == FREEZE and sha(base/'freeze-manifest.json') == FREEZE,
            'Frozen manifest changed')
    require(host['native_plan_sha256'] == NATIVE_PLAN and host['native_plan_file_sha256'] == NATIVE_PLAN_FILE
            and sha(base/'inputs/native-plan.json') == NATIVE_PLAN_FILE, 'Frozen native plan changed')
    receipt = load(base/'host/launch-receipt.json')
    require(receipt.get('schema_version') == 1 and receipt.get('plan_sha256') == HOST_PLAN,
            'Real host launch receipt identity differs')
    state = receipt.get('status')
    require(state in ('starting', 'running', 'native_completed', 'completed', 'failed'), 'Unknown host receipt state')
    return host, receipt


def status(base):
    _, receipt = header(base)
    if receipt['status'] != 'completed':
        require(receipt['status'] != 'failed', 'Actual host launcher failed; preserve original evidence')
        return {'status': 'waiting', 'reason': 'Actual fresh629 host launcher and CPU finalizer are not completed',
                'host_status': receipt['status'], 'cohort': str(base), 'publication_created': False,
                'process_started': False, 'quality_verified': False}
    return {'status': 'terminal_receipt_present', 'cohort': str(base), 'full_verification_required': True,
            'publication_created': False, 'process_started': False, 'quality_verified': False}


def private_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def modules(base):
    source = base/'source/scripts/research/sim2sim_scene_matrix.py'
    require(sha(regular(source)) == MATRIX_SOURCE, 'Frozen native validator changed')
    require(sha(regular(HERE/'publisher_source.py')) == PUBLISHER_SOURCE, 'Frozen reused publisher changed')
    sys.path.insert(0, str(WORKSPACE))
    native = private_module('fresh629_native_validator', source)
    publisher = private_module('fresh629_private_publisher', HERE/'publisher_source.py')
    require(native.ROOT.resolve() == (base/'source').resolve(), 'Frozen native validator ROOT differs')
    publisher.host_path = lambda value: mapped(base, value)
    publisher.validate_worker_receipts = native.validate_worker_receipts
    return publisher, native


def verify_freeze(base, host, plan):
    manifest = load(base/'freeze-manifest.json')
    records = manifest['files']
    require(len(records) == 5206, 'Expected5206 frozen records')
    index = {}
    for item in records:
        relative = Path(item['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in index,
                'Unsafe or duplicate frozen relative path')
        index[str(relative)] = item
        check_record(item, base/relative)
    groups = Counter(Path(name).parts[0] for name in index)
    require(dict(groups) == {'source': 5184, 'control': 4, 'host': 13, 'inputs': 5}, 'Frozen file groups differ')
    for group in ('source', 'control', 'inputs'):
        expected = {str(base/name) for name in index if Path(name).parts[0] == group}
        require({str(p) for p in files(base/group)} == expected, 'Unsealed addition/removal in ' + group)
    expected_records = [plan['source_matrix_record'], *plan['dependencies'], *plan['models'],
                        *(record for selection in plan['selections'] for record in selection['source_files'])]
    require(len(expected_records) == 2266, 'Expected2266 native input/dependency/model records')
    for item in expected_records:
        path = mapped(base, item['path'])
        frozen = index.get(path.relative_to(base).as_posix())
        require(frozen is not None and frozen['sha256'] == item['sha256']
                and frozen['bytes'] == item.get('bytes', item.get('size')), 'Native record is not bound to frozen bytes')
    return {'files': 5206, 'groups': dict(groups), 'native_records_bound': 2266,
            'manifest_sha256': sha(base/'freeze-manifest.json')}


def verify_terminal(base, host, receipt, plan, matrix):
    require(receipt['status'] == 'completed' and receipt.get('native_started') is True
            and all(type(receipt.get(k)) is int and receipt[k] == 0 for k in
                    ('driver_returncode', 'driver_returncode_after_stop', 'observer_returncode', 'cpu_validation_returncode')),
            'Actual terminal driver/observer/CPU exits must all be zero')
    require(receipt.get('snapshot_files_verified') == receipt.get('snapshot_files_verified_after_native') == 5206,
            'Before/after frozen5206 verification missing')
    require(receipt.get('quality_verified') is False and receipt.get('obstacle_course_completion_verified') is False
            and receipt.get('finished_unix') and not any(k in receipt for k in
                ('error', 'cleanup_error', 'post_validation_error', 'cpu_cleanup_error', 'own_docker_cli_terminated')),
            'Host receipt is failed or incorrectly claims quality')
    for role, id_key in (('gpu', 'container_id'), ('cpu', 'cpu_container_id')):
        stopped = receipt['owned_'+role+'_container_stop']
        require(stopped['container_id'] == receipt[id_key] and stopped['running_after_stop'] is False
                and stopped['state']['Running'] is False and not stopped['state'].get('Restarting'),
                'Owned '+role+' container is not stopped')
    require(matrix['status'] == 'completed' and matrix['completed_configurations'] == 629
            and matrix['completed_scenarios'] == 17 and matrix['configuration_coverage_complete'] is True,
            'Actual native matrix is incomplete')
    invocation = matrix['last_invocation']
    require(invocation['case_ids'] == [] and invocation['case_limit'] is None and invocation['resume'] is False
            and invocation['requested_configurations'] == 629, 'Fresh629 must be unfiltered and once-only')
    require(load(base/'outputs/all-configs/plan.json') == plan, 'Executed native plan differs')
    expected_argv = ['docker', 'exec', receipt['container_id'], '/opt/php/bin/inference-python', '/control/run_frozen_matrix.py',
                     '--expected-plan', '/data/native-plan.json', '--matrix-sha256', host['matrix_source_sha256'],
                     '--helper-sha256', host['control_wrapper_sha256'], '--', *host['native_args']]
    require(receipt['native_argv'] == expected_argv, 'Actual native argv differs')
    require(receipt['cpu_validation_argv'] == ['docker', 'exec', receipt['cpu_container_id'], '/opt/php/bin/inference-python',
             '/control/finalize_fresh629.py', '--plan', '/data/native-plan.json', '--output', '/validation/full-validation.json'],
            'Actual CPU finalizer argv differs')
    post_path = base/'host/final-validation/full-validation.json'
    require(sha(regular(post_path)) == receipt['full_validation_sha256'], 'Actual CPU final receipt SHA differs')
    post = load(post_path)
    require(post['status'] == 'passed' and post['native_plan_sha256'] == NATIVE_PLAN
            and post['matrix_sha256'] == sha(base/'outputs/all-configs/matrix.json')
            and post['worker_exit0_empty_group_count'] == 1258 and post['full_decoded_mp4_count'] == 629
            and post['configurations'] == 629 and post['scenarios'] == 17 and len(post['cases']) == 629
            and post['quality_verified'] is False and post['obstacle_course_completion_verified'] is False,
            'CPU full629/1258worker/629decode contract differs')
    inspected = load(base/'host/container-inspect.json')
    observed = load(base/'host/observer/summary.json')
    launch = load(base/'host/observer/launch.json')
    require(inspected['Id'] == receipt['container_id'] and inspected['Image'] == IMAGE
            and observed['identity'] == launch['identity'] and observed['identity']['container_id'] == receipt['container_id']
            and observed['identity']['image_id'] == IMAGE
            and observed['identity']['started_at'] == inspected['State']['StartedAt']
            and observed['mapping_scope_complete'] is True and observed['errors'] == []
            and observed['stop_reason'] == 'stop_file', 'Actual host observer identity/completeness differs')
    require(observed['source_sha256'] == sha(base/'control/observe_container_pids.py'), 'Observer executed source differs')
    configuration = inspected['HostConfig']
    requests = configuration.get('DeviceRequests') or []
    expected_mounts = sorted((str(base/source), target, read_only, 'bind') for source, target, read_only in
                            [('source', '/workspace/php_parkour', True), ('inputs', '/data', True),
                             ('control', '/control', True), ('outputs', '/outputs', False), ('cache', '/data/cache', False)])
    require(configuration['NetworkMode'] == 'none' and configuration['IpcMode'] == 'private'
            and not configuration.get('PidMode') and not configuration['Privileged'] and configuration['Init'] is True
            and configuration['ShmSize'] == 8589934592 and len(requests) == 1 and requests[0]['DeviceIDs'] == [UUID]
            and requests[0]['Count'] == 0 and inspected['Config']['WorkingDir'] == '/workspace/php_parkour'
            and sorted((m['Source'], m['Destination'], not m['RW'], m['Type']) for m in inspected['Mounts']) == expected_mounts,
            'Actual GPU container isolation/mount/UUID differs')
    verify_observer_log(base/'host/observer/snapshots.jsonl', observed)
    return post, observed


def verify_observer_log(path, observed):
    mappings = {}; roles = set(); writer_roles = set(); count = 0; previous = None
    with regular(path).open('rb') as stream:
        for line in stream:
            event = parse_json(line)
            require(type(event['monotonic']) in (int, float) and math.isfinite(event['monotonic'])
                    and (previous is None or event['monotonic'] >= previous), 'Observer snapshot chronology differs')
            previous = event['monotonic']; count += 1
            for process in event['processes']:
                role = process['role']
                if role:
                    roles.add(role)
                for thread in process['command_writer_threads']:
                    if role and thread['container_tid'] is not None and thread['container_tgid'] is not None:
                        writer_roles.add(role)
                    key = (thread['host_tid'], thread['start_time_clock_ticks'])
                    mapping = {'role': role, 'worker_output': process.get('worker_output'), **thread}
                    if key not in mappings:
                        mappings[key] = mapping | {'first_observed_utc': event['utc']}
                    mappings[key]['last_observed_utc'] = event['utc']
    require(count == observed['snapshots'] and sorted(roles) == observed['worker_roles_observed']
            and sorted(writer_roles) == observed['command_writer_roles_mapped']
            and sorted(mappings.values(), key=lambda m: (m['host_tid'], m['start_time_clock_ticks'])) == observed['command_writer_mappings'],
            'Observer summary does not reproduce the full original snapshots')
    return {'snapshots': count, 'source_sha256': sha(path), 'bytes': Path(path).stat().st_size}


def verify_mappings(base, receipt, observed, cases):
    index = {}
    for mapping in observed['command_writer_mappings']:
        key = (mapping['worker_output'], mapping['role'], mapping['container_tgid'], mapping['owner_start_time_clock_ticks'])
        index.setdefault(key, []).append(mapping)
    result = []
    seen = set()
    for item in cases:
        row = item['row']; attempt = row['attempts'][0]
        for role in ('simulator', 'inference'):
            path = item['directory']/(role+'-process-start.json'); process = load(path)['process']
            matches = index.get((attempt['output'], role, process['pid'], process['start_time_clock_ticks']), [])
            require(len(matches) == 1, 'Missing/duplicate exact hostwriter mapping: '+row['case_id']+'/'+role)
            mapping = matches[0]
            require(mapping['nspid'][0] == mapping['host_tid'] and mapping['nspid'][-1] == mapping['container_tid']
                    and mapping['nstgid'][0] == mapping['host_tgid'] and mapping['nstgid'][-1] == process['pid'],
                    'Hostwriter namespace ownership differs')
            thread = (mapping['host_tid'], mapping['start_time_clock_ticks'])
            require(thread not in seen, 'Hostwriter birth reused between workers'); seen.add(thread)
            result.append({'case_id': row['case_id'], 'role': role, 'entry_sha256': sha(path), 'mappings': matches})
    require(len(result) == 1258 and result == receipt['host_native_mappings'], 'Actual1258 mappings differ from host terminal receipt')
    return result


def finite_statistics(result):
    sim = result['simulation']
    values = [sim[key] for key in ('minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m')]
    require(len(sim['final_position_xyz_m']) == 3, 'Final XYZ must contain3 values')
    values.extend(sim['final_position_xyz_m'])
    require(all(type(value) in (int, float) and math.isfinite(value) for value in values), 'Nonfinite or nonnumeric measured statistics')


def verify_cpu_cases(base, plan, post, verified, native):
    require(len(verified) == 629, 'Need629 actual verified cases')
    for evidence, item in zip(post['cases'], verified):
        row = item['row']; directory = item['directory']; result = item['result']
        require(evidence['case_id'] == row['case_id'] and evidence['native_result_sha256'] == sha(directory/'result.json')
                and evidence['parent_returncode'] == 0 and evidence['worker_exit0_empty_groups'] == 2
                and evidence['policy_ticks'] == 500 and evidence['quality_verified'] is False
                and evidence['obstacle_course_completion_verified'] is False
                and evidence['survival_heuristic_passed'] == result['survival_passed'], 'CPU final case/result identity differs')
        sealed = native.validate_worker_receipts(directory, plan, result, translate=lambda value: mapped(base, value))
        expected = [{**record, 'path': str(mapped(base, record['path']))} for record in evidence['worker_receipts']]
        require(sealed == expected, 'CPU final native receipt fingerprints differ')
        require(len(evidence['videos']) == len(result['videos']) == 1, 'Need629 original single native videos')
        video = evidence['videos'][0]; path = mapped(base, video['path'])
        require(path == directory/result['videos'][0] and video['full_decode'] is True
                and type(video['returncode']) is int and video['returncode'] == 0 and video['stderr'] == ''
                and video['command'] == ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads', '1',
                                         '-i', video['path'], '-f', 'null', '-'], 'Actual full video decode command/result differs')
        check_record(video, path)


def verify_all(base):
    host, receipt = header(base)
    require(receipt['status'] == 'completed', 'Full verification requires actual completed host receipt')
    plan = load(base/'inputs/native-plan.json'); matrix = load(base/'outputs/all-configs/matrix.json')
    require(signed(plan, 'plan_sha256') == NATIVE_PLAN, 'Native plan identity differs')
    publisher, native = modules(base)
    publisher.validate_plan(plan, matrix, NATIVE_PLAN, MATRIX_SOURCE, False)
    frozen = verify_freeze(base, host, plan)
    post, observed = verify_terminal(base, host, receipt, plan, matrix)
    verified = []
    for row in matrix['selections']:
        require(len(row['attempts']) == 1 and row['attempts'][0]['number'] == 1, 'Fresh cohort cannot contain retries')
        item = publisher.validate_case(plan, row)
        finite_statistics(item['result'])
        item['attempt_archives'] = [publisher.validate_attempt_archive(plan, row, row['attempts'][0], [item['directory']])]
        verified.append(item)
    verify_cpu_cases(base, plan, post, verified, native)
    mappings = verify_mappings(base, receipt, observed, verified)
    return {'base': base, 'host': host, 'receipt': receipt, 'plan': plan, 'matrix': matrix, 'publisher': publisher,
            'cases': verified, 'freeze': frozen, 'mappings': mappings, 'post': post}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    temporary.replace(path)


def byte_copy(source, target, expected_sha):
    source = regular(source)
    require(sha(source) == expected_sha, 'Source changed before copy: '+str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not target.exists(), 'Copy target already exists')
    shutil.copyfile(source, target)
    require(sha(source) == sha(target) == expected_sha, 'Source changed during byte copy')
    return {'path': str(target), 'bytes': target.stat().st_size, 'sha256': expected_sha}


def chunk_copy(source, directory, expected_sha, limit=CHUNK_LIMIT):
    source = regular(source); whole = hashlib.sha256(); offset = 0; chunks = []
    require(sha(source) == expected_sha, 'Large source changed before copy')
    directory.mkdir(parents=True, exist_ok=False)
    with source.open('rb') as stream:
        while block := stream.read(limit):
            path = directory/f'chunk-{len(chunks):06d}.bin'; path.write_bytes(block); whole.update(block)
            chunks.append({'path': str(path), 'offset': offset, 'bytes': len(block), 'sha256': sha(path)})
            offset += len(block)
    require(whole.hexdigest() == expected_sha == sha(source) and offset == source.stat().st_size,
            'Large source changed during exact chunk copy')
    return {'source_bytes': offset, 'source_sha256': expected_sha, 'chunk_limit_bytes': limit,
            'reconstruction': 'Concatenate chunks in listed order; verify contiguous offsets, total bytes and whole SHA256',
            'chunks': chunks}


def snapshot_records(directory):
    return [{'relative': p.relative_to(directory).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files(directory)]


def publish(base, output):
    ready = status(base)
    if ready['status'] == 'waiting':
        return ready
    output = Path(output)
    require(output.is_absolute() and '..' not in output.parts and output.resolve() == output,
            'Publication output must be a canonical absolute path without symlinks')
    require(not output.exists() and not output.is_relative_to(base) and not base.is_relative_to(output),
            'Fresh publication outside original cohort required')
    require(output.is_relative_to(WORKSPACE/'usage_assets') or output.is_relative_to(WORKSPACE/'outputs/research'),
            'Publication must remain within workspace usage_assets or ignored research output')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name+'.partial-'+uuid.uuid4().hex)
    staging.mkdir(exist_ok=False)
    progress = {'schema_version': 1, 'status': 'running', 'stage': 'verification', 'cohort': str(base),
                'output': str(output), 'staging': str(staging), 'quality_verified': False}
    write(staging/'publication-attempt.json', progress)
    try:
        verified = verify_all(base); pub = verified['publisher']; plan = verified['plan']; rows = verified['cases']
        host_records = snapshot_records(base/'host')
        source_guards = [{'path': str(base/path), 'sha256': sha(base/path)} for path in
                         ('host-plan.json', 'freeze-manifest.json', 'outputs/all-configs/plan.json', 'outputs/all-configs/matrix.json')]
        progress.update(stage='copy', host_files=len(host_records)); write(staging/'publication-attempt.json', progress)
        copied = []; chunked = []
        def copy(source, relative, expected):
            record = byte_copy(source, staging/relative, expected)
            record.update(path=relative, source=str(source)); copied.append(record); return relative
        for guard in source_guards:
            relative = Path(guard['path']).relative_to(base).as_posix()
            copy(Path(guard['path']), 'raw/'+relative, guard['sha256'])
        for group in ('inputs', 'control'):
            expected_frozen = {item['relative']: item for item in load(base/'freeze-manifest.json')['files']}
            for source in files(base/group):
                # Large ONNX input bytes remain referenced by the exact frozen input proof.
                if group == 'inputs' and source.suffix == '.onnx':
                    continue
                relative = source.relative_to(base).as_posix()
                copy(source, 'raw/'+relative, expected_frozen[relative]['sha256'])
        for source in (regular(__file__), regular(HERE/'publisher_source.py')):
            copy(source, 'sources/'+source.name, sha(source))
        for record in host_records:
            source = base/'host'/record['relative']; relative = 'raw/host/'+record['relative']
            if record['bytes'] > CHUNK_LIMIT:
                chunks = chunk_copy(source, staging/(relative+'.chunks'), record['sha256'])
                for chunk in chunks['chunks']:
                    chunk['path'] = Path(chunk['path']).relative_to(staging).as_posix()
                chunked.append({'source': str(source), 'original_relative': relative, **chunks})
            else:
                copy(source, relative, record['sha256'])
        cases = []
        for ordinal, item in enumerate(rows):
            row = item['row']; result = item['result']; sim = result['simulation']; attempt = row['attempts'][0]
            prefix = f'cases/{row["scenario"]}/config-{row["configuration_index"]:04d}'
            folder = prefix+'/attempt-0001'; directory = item['directory']; archive = item['attempt_archives'][0]
            retained = [copy(Path(record['path']), folder+'/'+Path(record['path']).relative_to(directory).as_posix(), record['sha256'])
                        for record in archive['files']]
            log = attempt['log']; parent_log = copy(mapped(base, log['path']), folder+'/parent-execution.log', log['sha256'])
            attempts = [{'number': 1, 'status': 'completed', 'returncode': 0, 'files': retained, 'parent_log': parent_log,
                         'original_receipt': attempt, 'sealed': True, 'integrity_scope': archive['integrity_scope']}]
            write(staging/(prefix+'/attempts.json'), attempts)
            svg = prefix+'/world-xy.svg'; (staging/svg).write_text(pub.trajectory_svg(item['trajectory']))
            videos = [{'path': folder+'/'+check['video'], 'thumbnail': folder+'/'+check['thumbnail'],
                       'duration_seconds': float(check['probe']['format']['duration']),
                       'width': check['probe']['streams'][0]['width'], 'height': check['probe']['streams'][0]['height']}
                      for check in result['video_checks']]
            cases.append({'ordinal': ordinal, **{key: row[key] for key in
                          ('case_id', 'scenario', 'configuration', 'configuration_index', 'command', 'mesh_sha256')},
                          'status': 'completed', 'policy_ticks': 500, 'policy_seconds': sim['policy_simulation_seconds'],
                          'threshold_event': sim['fall_detected'], **{key: sim[key] for key in
                          ('minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m', 'final_position_xyz_m')},
                          'videos': videos, 'trajectory_svg': svg, 'trajectory_csv': folder+'/trajectory.csv',
                          'result_json': folder+'/result.json', 'case_evidence': folder+'/case-evidence.json',
                          'attempts_json': prefix+'/attempts.json', 'attempts': attempts,
                          'quality_verified': False, 'obstacle_course_completion_verified': False})
        scenarios = []
        for scenario, count in pub.SCENARIO_COUNTS.items():
            selected = [case for case in cases if case['scenario'] == scenario]
            flags = sum(case['threshold_event'] for case in selected)
            scenarios.append({'scenario': scenario, 'planned_configurations': count, 'configurations': len(selected),
                              'threshold_events': flags, 'no_threshold_events': len(selected)-flags,
                              'historical_noncompleted_attempts': 0})
        summary = {'schema_version': 1, 'status': 'completed_publication', 'preview': False,
                   'legacy_normal_exit_unverified': False, 'observed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                   'plan_sha256': NATIVE_PLAN, 'host_plan_sha256': HOST_PLAN, 'image_id': IMAGE,
                   'matrix_sha256': sha(base/'outputs/all-configs/matrix.json'), 'model_sha256': plan['model_sha256'],
                   'configurations': 629, 'planned_configurations': 629, 'policy_ticks': 629*500,
                   'policy_seconds': sum(case['policy_seconds'] for case in cases),
                   'threshold_events': sum(case['threshold_event'] for case in cases),
                   'no_threshold_events': sum(not case['threshold_event'] for case in cases), 'scenarios': scenarios,
                   'worker_exit0_empty_group_count': 1258, 'exact_hostwriter_mapping_count': 1258,
                   'full_decoded_mp4_count': 629, 'snapshot_files_verified': 5206, 'native_records_frozen': 2266,
                   'configuration_coverage_complete': True, 'quality_verified': False,
                   'obstacle_course_completion_verified': False,
                   'scope': '629 configurations across17 scenarios; released-policy constant-forward closed-loop runtime coverage, not skill success',
                   'media_policy': 'Exact original video/PNG/CSV/JSON/log bytes; full original host observer logs retained in lossless chunks',
                   'publisher_sha256': sha(__file__), 'reused_publisher_sha256': PUBLISHER_SOURCE}
        write(staging/'summary.json', summary); write(staging/'cases.json', cases); write(staging/'scenarios.json', scenarios)
        write(staging/'chunked-originals.json', {'schema_version': 1, 'files': chunked})
        write(staging/'source-input-proof.json', {'scope': 'External immutable source/input bytes verified; ONNX bytes not duplicated',
                                               'freeze': verified['freeze'], 'native_plan_file_sha256': NATIVE_PLAN_FILE,
                                               'original_freeze_manifest': 'raw/freeze-manifest.json',
                                               'canonical_image_id': IMAGE, 'model_sha256': plan['model_sha256']})
        (staging/'playback.html').write_text(pub.make_page(summary, cases))
        import csv
        fields = ['ordinal', 'case_id', 'scenario', 'configuration_index', 'configuration', 'command', 'mesh_sha256',
                  'policy_ticks', 'policy_seconds', 'threshold_event', 'minimum_pelvis_height_m', 'minimum_base_up_z',
                  'final_base_up_z', 'path_length_xy_m', 'result_json', 'trajectory_csv']
        with (staging/'cases.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(cases)
        progress.update(stage='final_seal'); write(staging/'publication-attempt.json', progress)
        require(snapshot_records(base/'host') == host_records, 'Original host bytes/file set changed during publication')
        for guard in source_guards:
            require(sha(guard['path']) == guard['sha256'], 'Original plan/matrix changed during publication')
        # Revalidate the full original freeze and native input file sets after all byte copies.
        verify_freeze(base, verified['host'], plan)
        progress.update(status='completed', stage='completed'); write(staging/'publication-attempt.json', progress)
        manifest = {'schema_version': 1, 'scope': summary['scope'], 'cohort': str(base), 'host_plan_sha256': HOST_PLAN,
                    'native_plan_sha256': NATIVE_PLAN, 'files': snapshot_records(staging), 'byte_copies': copied,
                    'chunked_originals': chunked, 'quality_verified': False}
        write(staging/'evidence-manifest.json', manifest)
        require(not output.exists(), 'Publication output appeared during copy; preserve partial attempt')
        staging.rename(output)
        return summary
    except BaseException as error:
        progress.update(status='failed', error=f'{type(error).__name__}: {error}')
        try:
            write(staging/'publication-attempt.json', progress)
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'prepare', 'publish'))
    parser.add_argument('--cohort', type=Path, default=COHORT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        ready = status(args.cohort)
        if ready['status'] == 'waiting' or args.action == 'status':
            result = ready
        elif args.action == 'prepare':
            verified = verify_all(args.cohort)
            result = {'status': 'verified_ready_to_publish', 'cohort': str(args.cohort), 'configurations': len(verified['cases']),
                      'worker_exit0_empty_group_count': 1258, 'exact_hostwriter_mapping_count': len(verified['mappings']),
                      'full_decoded_mp4_count': 629, 'snapshot_files_verified': 5206, 'publication_created': False,
                      'process_started': False, 'quality_verified': False}
        else:
            require(args.output is not None, 'publish needs explicit fresh --output')
            result = publish(args.cohort, args.output)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        print(json.dumps({'status': 'rejected', 'error': f'{type(error).__name__}: {error}',
                          'publication_created': False, 'process_started': False, 'quality_verified': False}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
