"""CPU control-plane fixtures only; no real full publication or native execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace, ModuleType

import pytest

SPEC = importlib.util.spec_from_file_location('fresh_publication_under_test', Path(__file__).with_name('publish_fresh629.py'))
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


@pytest.mark.parametrize('state', ['starting', 'running', 'native_completed'])
@pytest.mark.parametrize('action', ['status', 'prepare', 'publish'])
def test_running_waits_without_output_or_full_verification(tmp_path, monkeypatch, capsys, state, action):
    monkeypatch.setattr(p, 'header', lambda base: ({}, {'status': state}))
    monkeypatch.setattr(p, 'verify_all', lambda base: pytest.fail('Waiting must not verify/copy/import native helpers'))
    output = tmp_path/'not-created'/'publication'
    monkeypatch.setattr(p.sys, 'argv', ['tool', action, '--output', str(output)])
    assert p.main() == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'waiting'
    assert not output.parent.exists()


def test_failed_host_does_not_publish(monkeypatch):
    monkeypatch.setattr(p, 'header', lambda base: ({}, {'status': 'failed'}))
    with pytest.raises(ValueError, match='launcher failed'):
        p.status(Path('/unused'))


@pytest.mark.parametrize('value', ['/data/../escaped', '/outputs/../escaped', '/etc/passwd', 'relative/path'])
def test_namespace_escape_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        p.mapped(tmp_path, value)


def test_namespace_maps_frozen_source_outputs_inputs(tmp_path):
    assert p.mapped(tmp_path, '/workspace/php_parkour/scripts/a.py') == tmp_path/'source/scripts/a.py'
    assert p.mapped(tmp_path, '/outputs/all-configs/a') == tmp_path/'outputs/all-configs/a'
    assert p.mapped(tmp_path, '/data/assets/student/a.onnx') == tmp_path/'inputs/assets/student/a.onnx'


def test_symlink_namespace_rejected(tmp_path):
    (tmp_path/'source').symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError, match='Symlink'):
        p.mapped(tmp_path, '/workspace/php_parkour/a.py')


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}'])
def test_strict_json_rejects_invalid_evidence(raw):
    with pytest.raises(ValueError):
        p.parse_json(raw)


def test_chunk_copy_exact_offsets_and_reassembly(tmp_path):
    original = tmp_path/'original.jsonl'; original.write_bytes(b'abcdefghijklmnopq')
    result = p.chunk_copy(original, tmp_path/'chunks', p.sha(original), limit=5)
    assert [x['offset'] for x in result['chunks']] == [0, 5, 10, 15]
    assert all(x['bytes'] <= 5 for x in result['chunks'])
    assert b''.join(Path(x['path']).read_bytes() for x in result['chunks']) == original.read_bytes()
    assert result['source_sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()


def test_bytecopy_never_replaces_original_expected_hash(tmp_path):
    original = tmp_path/'original'; original.write_bytes(b'original')
    expected = p.sha(original); original.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='before copy'):
        p.byte_copy(original, tmp_path/'copy', expected)
    assert not (tmp_path/'copy').exists()


def observer_fixture(tmp_path):
    event = {'utc': '2026-10-10T00:00:00Z', 'monotonic': 1.0, 'processes': []}
    mappings = []
    for i, role in enumerate(('simulator', 'inference')):
        thread = {'host_tid': 100+i, 'start_time_clock_ticks': 50+i, 'container_tid': 10+i, 'container_tgid': 20+i,
                  'host_tgid': 200+i, 'owner_start_time_clock_ticks': 60+i, 'nspid': [100+i, 10+i],
                  'nstgid': [200+i, 20+i], 'status': {'State': 'S'}}
        process = {'role': role, 'worker_output': '/outputs/case', 'command_writer_threads': [thread]}
        event['processes'].append(process)
        mappings.append({'role': role, 'worker_output': '/outputs/case', **thread,
                         'first_observed_utc': event['utc'], 'last_observed_utc': event['utc']})
    path = tmp_path/'host/observer/snapshots.jsonl'; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(event)+'\n')
    return {'snapshots': 1, 'worker_roles_observed': ['inference', 'simulator'],
            'command_writer_roles_mapped': ['inference', 'simulator'], 'command_writer_mappings': mappings}


def test_original_observer_summary_recomputed_from_all_lines(tmp_path):
    observed = observer_fixture(tmp_path)
    assert p.verify_observer_log(tmp_path/'host/observer/snapshots.jsonl', observed)['snapshots'] == 1


@pytest.mark.parametrize('field', ['snapshots', 'worker_roles_observed', 'command_writer_mappings'])
def test_observer_summary_mutation_rejected(tmp_path, field):
    observed = observer_fixture(tmp_path)
    observed[field] = 2 if field == 'snapshots' else []
    with pytest.raises(ValueError, match='reproduce'):
        p.verify_observer_log(tmp_path/'host/observer/snapshots.jsonl', observed)


def test_observer_keeps_native_first_status_last_seen_semantics(tmp_path):
    observed = observer_fixture(tmp_path)
    path = tmp_path/'host/observer/snapshots.jsonl'; event = json.loads(path.read_text())
    event['utc'] = '2026-10-10T00:00:01Z'; event['monotonic'] = 2.0
    for process in event['processes']:
        process['command_writer_threads'][0]['status']['State'] = 'R'
    path.write_text(path.read_text()+json.dumps(event)+'\n')
    observed['snapshots'] = 2
    for mapping in observed['command_writer_mappings']:
        mapping['last_observed_utc'] = event['utc']
    p.verify_observer_log(path, observed)


@pytest.fixture
def terminal(tmp_path):
    base = tmp_path
    observer = base/'control/observe_container_pids.py'; observer.parent.mkdir(); observer.write_text('# fixture observer\n')
    observed = observer_fixture(base)
    cid = 'a'*64; cpu = 'b'*64
    inspected = {'Id': cid, 'Image': p.IMAGE, 'State': {'StartedAt': 'fixture-start'},
                 'HostConfig': {'NetworkMode': 'none', 'IpcMode': 'private', 'PidMode': '', 'Privileged': False,
                                'Init': True, 'ShmSize': 8589934592, 'DeviceRequests': [{'DeviceIDs': [p.UUID], 'Count': 0}]},
                 'Config': {'WorkingDir': '/workspace/php_parkour'}, 'Mounts': []}
    for source, target, rw in [('source', '/workspace/php_parkour', False), ('inputs', '/data', False),
                               ('control', '/control', False), ('outputs', '/outputs', True), ('cache', '/data/cache', True)]:
        inspected['Mounts'].append({'Source': str(base/source), 'Destination': target, 'RW': rw, 'Type': 'bind'})
    observation_identity = {'container_id': cid, 'image_id': p.IMAGE, 'started_at': 'fixture-start'}
    observed.update(identity=observation_identity, mapping_scope_complete=True, errors=[], stop_reason='stop_file',
                    source_sha256=p.sha(observer))
    put(base/'host/container-inspect.json', inspected); put(base/'host/observer/summary.json', observed)
    put(base/'host/observer/launch.json', {'identity': observation_identity})
    plan = {'fixture': True}
    put(base/'outputs/all-configs/plan.json', plan)
    matrix = {'status': 'completed', 'completed_configurations': 629, 'completed_scenarios': 17,
              'configuration_coverage_complete': True,
              'last_invocation': {'case_ids': [], 'case_limit': None, 'resume': False, 'requested_configurations': 629}}
    put(base/'outputs/all-configs/matrix.json', matrix)
    post = {'status': 'passed', 'native_plan_sha256': p.NATIVE_PLAN, 'matrix_sha256': p.sha(base/'outputs/all-configs/matrix.json'),
            'worker_exit0_empty_group_count': 1258, 'full_decoded_mp4_count': 629, 'configurations': 629, 'scenarios': 17,
            'cases': [{} for _ in range(629)], 'quality_verified': False, 'obstacle_course_completion_verified': False}
    put(base/'host/final-validation/full-validation.json', post)
    host = {'native_args': ['--all-configs'], 'matrix_source_sha256': p.MATRIX_SOURCE, 'control_wrapper_sha256': 'c'*64}
    receipt = {'status': 'completed', 'native_started': True, 'driver_returncode': 0, 'driver_returncode_after_stop': 0,
               'observer_returncode': 0, 'cpu_validation_returncode': 0, 'snapshot_files_verified': 5206,
               'snapshot_files_verified_after_native': 5206, 'quality_verified': False,
               'obstacle_course_completion_verified': False, 'finished_unix': 1.0, 'container_id': cid, 'cpu_container_id': cpu,
               'full_validation_sha256': p.sha(base/'host/final-validation/full-validation.json')}
    for role, identifier in [('gpu', cid), ('cpu', cpu)]:
        receipt['owned_'+role+'_container_stop'] = {'container_id': identifier, 'running_after_stop': False,
                                                   'state': {'Running': False, 'Restarting': False}}
    receipt['native_argv'] = ['docker', 'exec', cid, '/opt/php/bin/inference-python', '/control/run_frozen_matrix.py',
                             '--expected-plan', '/data/native-plan.json', '--matrix-sha256', p.MATRIX_SOURCE,
                             '--helper-sha256', 'c'*64, '--', '--all-configs']
    receipt['cpu_validation_argv'] = ['docker', 'exec', cpu, '/opt/php/bin/inference-python', '/control/finalize_fresh629.py',
                                     '--plan', '/data/native-plan.json', '--output', '/validation/full-validation.json']
    return base, host, receipt, plan, matrix


def test_true_terminal_contract_fixture_passes(terminal):
    post, observed = p.verify_terminal(*terminal)
    assert post['full_decoded_mp4_count'] == 629
    assert observed['stop_reason'] == 'stop_file'


@pytest.mark.parametrize('field,value', [('status', 'running'), ('driver_returncode', 1), ('observer_returncode', 1),
    ('driver_returncode_after_stop', 1), ('cpu_validation_returncode', 1), ('snapshot_files_verified', 5205),
    ('snapshot_files_verified_after_native', 5205), ('quality_verified', True), ('native_started', False),
    ('cleanup_error', 'fixture'), ('native_argv', ['fake']), ('cpu_validation_argv', ['fake'])])
def test_terminal_receipt_mutations_rejected(terminal, field, value):
    base, host, receipt, plan, matrix = terminal; receipt[field] = value
    with pytest.raises(ValueError):
        p.verify_terminal(base, host, receipt, plan, matrix)


@pytest.mark.parametrize('role', ['gpu', 'cpu'])
def test_running_owned_container_rejected(terminal, role):
    base, host, receipt, plan, matrix = terminal
    receipt['owned_'+role+'_container_stop']['state']['Running'] = True
    with pytest.raises(ValueError, match='not stopped'):
        p.verify_terminal(base, host, receipt, plan, matrix)


@pytest.mark.parametrize('field,value', [('resume', True), ('case_limit', 1), ('case_ids', ['case']), ('requested_configurations', 628)])
def test_subset_resume_cannot_publish_full(terminal, field, value):
    base, host, receipt, plan, matrix = terminal; matrix['last_invocation'][field] = value
    with pytest.raises(ValueError, match='unfiltered'):
        p.verify_terminal(base, host, receipt, plan, matrix)


def test_post_receipt_changed_bytes_rejected(terminal):
    base, host, receipt, plan, matrix = terminal
    with (base/'host/final-validation/full-validation.json').open('a') as stream: stream.write(' ')
    with pytest.raises(ValueError, match='receipt SHA'):
        p.verify_terminal(base, host, receipt, plan, matrix)


@pytest.mark.parametrize('change', ['rw-source', 'wrong-uuid', 'public-ipc'])
def test_isolation_mutation_rejected(terminal, change):
    base, host, receipt, plan, matrix = terminal
    path = base/'host/container-inspect.json'; info = p.load(path)
    if change == 'rw-source': info['Mounts'][0]['RW'] = True
    elif change == 'wrong-uuid': info['HostConfig']['DeviceRequests'][0]['DeviceIDs'] = ['foreign']
    else: info['HostConfig']['IpcMode'] = 'host'
    put(path, info)
    with pytest.raises(ValueError, match='isolation'):
        p.verify_terminal(base, host, receipt, plan, matrix)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 'NaN', '1.0', None])
def test_numeric_ui_metrics_reject_nonfinite_or_strings(value):
    result = {'simulation': {'minimum_pelvis_height_m': value, 'minimum_base_up_z': 1.0, 'final_base_up_z': 1.0,
                             'path_length_xy_m': 1.0, 'final_position_xyz_m': [0.0, 0.0, 1.0]}}
    with pytest.raises(ValueError, match='statistics'):
        p.finite_statistics(result)


def test_failed_publication_stage_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'WORKSPACE', tmp_path)
    monkeypatch.setattr(p, 'status', lambda base: {'status': 'terminal_receipt_present'})
    monkeypatch.setattr(p, 'verify_all', lambda base: (_ for _ in ()).throw(ValueError('fixture failed seal')))
    output = tmp_path/'outputs/research/publication'
    with pytest.raises(ValueError, match='fixture failed seal'):
        p.publish(tmp_path/'cohort', output)
    assert not output.exists()
    partials = list(output.parent.glob('publication.partial-*'))
    assert len(partials) == 1
    receipt = p.load(partials[0]/'publication-attempt.json')
    assert receipt['status'] == 'failed' and receipt['stage'] == 'verification'
    assert 'fixture failed seal' in receipt['error']


@pytest.fixture
def sealed_fixture(tmp_path):
    records = []; index = {}; digest = hashlib.sha256(b'x').hexdigest()
    for group, count in [('source', 5184), ('control', 4), ('host', 13), ('inputs', 5)]:
        (tmp_path/group).mkdir()
        for i in range(count):
            relative = f'{group}/file-{i:04d}'
            (tmp_path/relative).write_bytes(b'x')
            item = {'relative': relative, 'bytes': 1, 'sha256': digest}
            records.append(item); index[relative] = item
    put(tmp_path/'freeze-manifest.json', {'files': records})
    def native(relative):
        prefix = '/workspace/php_parkour/' if relative.startswith('source/') else '/data/'
        name = relative.split('/', 1)[1]
        return {'path': prefix+name, 'size': 1, 'sha256': digest}
    plan = {'source_matrix_record': native('inputs/file-0000'),
            'dependencies': [native(f'source/file-{i:04d}') for i in range(376)],
            'models': [native('inputs/file-0003'), native('inputs/file-0004')],
            'selections': [{'source_files': [native(f'source/file-{376+i*3+j:04d}') for j in range(3)]} for i in range(629)]}
    return tmp_path, plan


def test_all5206_records_and2266_native_bindings_fixture(sealed_fixture):
    base, plan = sealed_fixture
    result = p.verify_freeze(base, {}, plan)
    assert result['files'] == 5206 and result['native_records_bound'] == 2266


@pytest.mark.parametrize('mutation', ['extra-source', 'extra-control', 'extra-input', 'changed-bytes', 'unbound-native', 'wrong-native-size'])
def test_frozen_closure_mutations_fail(sealed_fixture, mutation):
    base, plan = sealed_fixture
    if mutation.startswith('extra-'):
        group = {'extra-source': 'source', 'extra-control': 'control', 'extra-input': 'inputs'}[mutation]
        (base/group/'unsealed').write_bytes(b'x')
    elif mutation == 'changed-bytes':
        (base/'inputs/file-0003').write_bytes(b'changed')
    elif mutation == 'unbound-native':
        plan['models'][0]['path'] = '/data/not-frozen.onnx'
    else:
        plan['models'][0]['size'] = 999
    with pytest.raises(ValueError):
        p.verify_freeze(base, {}, plan)


def test_frozen_symlink_file_rejected(sealed_fixture):
    base, plan = sealed_fixture
    (base/'source/unsealed-link').symlink_to(base/'source/file-0000')
    with pytest.raises(ValueError, match='Symlink'):
        p.verify_freeze(base, {}, plan)


def test_hostwriter_mappings_bind_all1258_exact_native_births(tmp_path):
    cases = []; mappings = []; receipt_mappings = []
    for i in range(629):
        directory = tmp_path/'outputs'/f'case-{i}'; directory.mkdir(parents=True)
        row = {'case_id': f'case-{i}', 'attempts': [{'output': f'/outputs/case-{i}'}]}
        cases.append({'row': row, 'directory': directory})
        for j, role in enumerate(('simulator', 'inference')):
            ordinal = 2*i+j
            process = {'pid': ordinal+10, 'start_time_clock_ticks': ordinal+100}
            path = put(directory/(role+'-process-start.json'), {'process': process})
            mapping = {'worker_output': f'/outputs/case-{i}', 'role': role, 'container_tgid': process['pid'],
                       'owner_start_time_clock_ticks': process['start_time_clock_ticks'],
                       'host_tid': ordinal+2000, 'start_time_clock_ticks': ordinal+3000,
                       'host_tgid': ordinal+4000, 'container_tid': ordinal+5000,
                       'nspid': [ordinal+2000, ordinal+5000], 'nstgid': [ordinal+4000, process['pid']]}
            mappings.append(mapping)
            receipt_mappings.append({'case_id': row['case_id'], 'role': role, 'entry_sha256': p.sha(path), 'mappings': [mapping]})
    receipt = {'host_native_mappings': receipt_mappings}; observed = {'command_writer_mappings': mappings}
    assert len(p.verify_mappings(tmp_path, receipt, observed, cases)) == 1258
    observed['command_writer_mappings'] = mappings[:-1]
    with pytest.raises(ValueError, match='Missing/duplicate'):
        p.verify_mappings(tmp_path, receipt, observed, cases)


@pytest.fixture
def cpu_case_fixture(tmp_path):
    directory = tmp_path/'outputs/case'; directory.mkdir(parents=True)
    put(directory/'result.json', {'fixture': True}); video = directory/'video.mp4'; video.write_bytes(b'fixture-video')
    receipts = [{'path': str(directory/name), 'bytes': 1, 'sha256': 'a'*64} for name in
                ('worker-processes.json', 'simulator-process-start.json', 'inference-process-start.json')]
    native = SimpleNamespace(validate_worker_receipts=lambda *a, **kw: receipts)
    item = {'row': {'case_id': 'fixture'}, 'directory': directory,
            'result': {'survival_passed': False, 'videos': ['video.mp4']}}
    evidence = {'case_id': 'fixture', 'native_result_sha256': p.sha(directory/'result.json'), 'parent_returncode': 0,
                'worker_exit0_empty_groups': 2, 'policy_ticks': 500, 'quality_verified': False,
                'obstacle_course_completion_verified': False, 'survival_heuristic_passed': False,
                'worker_receipts': [{**r, 'path': '/outputs/case/'+Path(r['path']).name} for r in receipts],
                'videos': [{'path': '/outputs/case/video.mp4', 'full_decode': True, 'returncode': 0, 'stderr': '',
                            'bytes': video.stat().st_size, 'sha256': p.sha(video),
                            'command': ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads', '1',
                                        '-i', '/outputs/case/video.mp4', '-f', 'null', '-']}]}
    return tmp_path, {}, {'cases': [copy.deepcopy(evidence) for _ in range(629)]}, [item]*629, native


def test_cpu_decode_and_receipts_bind_each629_original(cpu_case_fixture):
    p.verify_cpu_cases(*cpu_case_fixture)


@pytest.mark.parametrize('mutation', ['wrong-case', 'wrong-result-sha', 'nonzero-decode', 'not-fulldecode', 'wrong-video-sha', 'wrong-worker-sha', 'wrong-command'])
def test_cpu_final_mutations_rejected(cpu_case_fixture, mutation):
    base, plan, post, cases, native = cpu_case_fixture; item = post['cases'][0]
    if mutation == 'wrong-case': item['case_id'] = 'foreign'
    elif mutation == 'wrong-result-sha': item['native_result_sha256'] = 'b'*64
    elif mutation == 'nonzero-decode': item['videos'][0]['returncode'] = 1
    elif mutation == 'not-fulldecode': item['videos'][0]['full_decode'] = False
    elif mutation == 'wrong-video-sha': item['videos'][0]['sha256'] = 'b'*64
    elif mutation == 'wrong-worker-sha': item['worker_receipts'][0]['sha256'] = 'b'*64
    else: item['videos'][0]['command'].remove('-xerror')
    with pytest.raises(ValueError):
        p.verify_cpu_cases(base, plan, post, cases, native)


def test_private_import_without_B_preserves_frozen_file_set(tmp_path, monkeypatch):
    module = tmp_path/'frozen.py'; module.write_text('VALUE = 42\n')
    monkeypatch.setattr(p.sys, 'dont_write_bytecode', False)
    before = list(tmp_path.rglob('*'))
    assert p.private_module('fixture_private_module', module).VALUE == 42
    assert list(tmp_path.rglob('*')) == before
    assert p.sys.dont_write_bytecode is True


def test_frozen_publisher_import_never_uses_live_or_cached_native(tmp_path, monkeypatch):
    source = tmp_path/'source/scripts/research/sim2sim_scene_matrix.py'
    source.parent.mkdir(parents=True)
    source.write_text('from pathlib import Path\nROOT=Path(__file__).resolve().parents[2]\nMARKER="frozen"\n'
                      'def validate_worker_receipts(*args, **kwargs): return MARKER\n')
    helper = tmp_path/'helpers'; helper.mkdir()
    frozen_pub = helper/'publisher_source.py'
    frozen_pub.write_text('from scripts.research.sim2sim_scene_matrix import MARKER\n')
    monkeypatch.setattr(p, 'HERE', helper); monkeypatch.setattr(p, 'MATRIX_SOURCE', p.sha(source))
    monkeypatch.setattr(p, 'PUBLISHER_SOURCE', p.sha(frozen_pub))
    live = ModuleType('scripts.research.sim2sim_scene_matrix'); live.MARKER = 'live-sentinel'
    monkeypatch.setitem(p.sys.modules, 'scripts.research.sim2sim_scene_matrix', live)
    old_path = list(p.sys.path)
    pub, native = p.modules(tmp_path)
    assert pub.MARKER == native.MARKER == 'frozen'
    assert p.sys.modules['scripts.research.sim2sim_scene_matrix'] is live
    assert p.sys.path == old_path
    assert not list(tmp_path.rglob('__pycache__'))


def fake_verified_publication(base):
    """Mock scientific gate only; exercise actual temporary copy/render/seal flow."""
    original = base/'outputs/all-configs/case'; original.mkdir(parents=True)
    sources = {'video.mp4': b'fixture-video', 'video.png': b'fixture-png', 'trajectory.csv': b'x_m,y_m\n0,0\n',
               'result.json': b'{"fixture":true}', 'case-evidence.json': b'{"fixture":true}'}
    archive = []
    for name, content in sources.items():
        path = original/name; path.write_bytes(content)
        archive.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': p.sha(path)})
    log = base/'outputs/all-configs/parent.log'; log.write_text('fixture parent\n')
    for name in ('host-plan.json', 'outputs/all-configs/plan.json', 'outputs/all-configs/matrix.json',
                 'host/launch-receipt.json', 'host/final-validation/full-validation.json'):
        put(base/name, {'fixture': True})
    observer = base/'host/observer/snapshots.jsonl'; observer.parent.mkdir(); observer.write_bytes(b'fixture-original-observer-log\n'*3)
    frozen_records = []
    for name in ('control/finalize_fresh629.py', 'inputs/native-plan.json',
                 'source/scripts/research/sim2sim_scene_matrix.py', 'source/scripts/research/sim2sim.py'):
        path = base/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture original\n')
        frozen_records.append({'relative': name, 'bytes': path.stat().st_size, 'sha256': p.sha(path)})
    put(base/'freeze-manifest.json', {'files': frozen_records})
    sim = {'policy_simulation_seconds': 10.0, 'fall_detected': True, 'minimum_pelvis_height_m': .2,
           'minimum_base_up_z': .1, 'final_base_up_z': .2, 'path_length_xy_m': 1.0, 'final_position_xyz_m': [1.0, 0.0, .2]}
    result = {'simulation': sim, 'video_checks': [{'video': 'video.mp4', 'thumbnail': 'video.png',
              'probe': {'format': {'duration': '10.0'}, 'streams': [{'width': 1, 'height': 1}]}}]}
    cases = []
    for i in range(629):
        attempt = {'number': 1, 'status': 'completed', 'returncode': 0, 'output': '/outputs/all-configs/case',
                   'log': {'path': '/outputs/all-configs/parent.log', 'bytes': log.stat().st_size, 'sha256': p.sha(log)}}
        row = {'scenario': 'fixture', 'configuration_index': i, 'configuration': f'fixture-{i}', 'case_id': f'fixture:{i}',
               'command': 6, 'mesh_sha256': 'a'*64, 'attempts': [attempt]}
        cases.append({'row': row, 'directory': original, 'result': result, 'trajectory': [{'x_m': '0', 'y_m': '0'}],
                      'attempt_archives': [{'files': archive, 'integrity_scope': 'CPUfixture mocked scientific gate'}]})
    source_guards = [{'path': str(base/name), 'sha256': p.sha(base/name)} for name in
                     ('host-plan.json', 'freeze-manifest.json', 'outputs/all-configs/plan.json', 'outputs/all-configs/matrix.json')]
    return {'publisher': SimpleNamespace(SCENARIO_COUNTS={'fixture': 629}, trajectory_svg=lambda rows: '<svg/>',
                                         make_page=lambda summary, cases: '<html>CPUfixture</html>'),
            'plan': {'model_sha256': {'student.onnx': 'a'*64, 'depth_backbone.onnx': 'b'*64}}, 'host': {},
            'cases': cases, 'freeze': {'files': 5206}, 'host_records': p.snapshot_records(base/'host'), 'source_guards': source_guards}


def publication_fixture(tmp_path, monkeypatch):
    base = tmp_path/'cohort'; verified = fake_verified_publication(base)
    monkeypatch.setattr(p, 'WORKSPACE', tmp_path); monkeypatch.setattr(p, 'CHUNK_LIMIT', 25)
    monkeypatch.setattr(p, 'status', lambda base: {'status': 'terminal_receipt_present'})
    monkeypatch.setattr(p, 'verify_all', lambda base: verified)
    monkeypatch.setattr(p, 'verify_freeze', lambda *a: {'files': 5206})
    return base, verified, tmp_path/'outputs/research/publication'


def test_atomic_publication_copy_chunks_manifest_fixture(tmp_path, monkeypatch):
    base, verified, output = publication_fixture(tmp_path, monkeypatch)
    original_before = p.snapshot_records(base)
    summary = p.publish(base, output)
    assert summary['configurations'] == 629 and summary['quality_verified'] is False
    assert p.snapshot_records(base) == original_before
    assert not list(output.parent.glob('publication.partial-*'))
    manifest = p.load(output/'evidence-manifest.json')
    for item in manifest['files']:
        assert p.sha(output/item['relative']) == item['sha256']
    chunked = p.load(output/'chunked-originals.json')['files']
    assert chunked and all(c['bytes'] <= 25 for original in chunked for c in original['chunks'])
    for original in chunked:
        combined = b''.join((output/chunk['path']).read_bytes() for chunk in original['chunks'])
        assert len(combined) == original['source_bytes']
        assert hashlib.sha256(combined).hexdigest() == original['source_sha256']
    assert (output/'cases/fixture/config-0000/attempt-0001/video.mp4').read_bytes() == b'fixture-video'


@pytest.mark.parametrize('relative', ['outputs/all-configs/matrix.json', 'host/launch-receipt.json',
                                    'host/final-validation/full-validation.json'])
def test_verification_to_copy_mutations_fail_and_retain_partial(tmp_path, monkeypatch, relative):
    base, verified, output = publication_fixture(tmp_path, monkeypatch)
    def late_change(base):
        with (base/relative).open('a') as stream: stream.write(' ')
        return verified
    monkeypatch.setattr(p, 'verify_all', late_change)
    with pytest.raises(ValueError, match='changed before copy'):
        p.publish(base, output)
    assert not output.exists()
    partial = next(output.parent.glob('publication.partial-*'))
    assert p.load(partial/'publication-attempt.json')['status'] == 'failed'


def test_copy_failure_keeps_partial_and_original_bytes(tmp_path, monkeypatch):
    base, verified, output = publication_fixture(tmp_path, monkeypatch)
    original_before = p.snapshot_records(base); original_copy = p.byte_copy
    def fail_video(source, target, expected_sha):
        if source.name == 'video.mp4':
            raise OSError('fixture video copy failure')
        return original_copy(source, target, expected_sha)
    monkeypatch.setattr(p, 'byte_copy', fail_video)
    with pytest.raises(OSError, match='fixture video'):
        p.publish(base, output)
    assert p.snapshot_records(base) == original_before
    assert not output.exists()
    partial = next(output.parent.glob('publication.partial-*'))
    report = p.load(partial/'publication-attempt.json')
    assert report['status'] == 'failed' and report['stage'] == 'copy'
