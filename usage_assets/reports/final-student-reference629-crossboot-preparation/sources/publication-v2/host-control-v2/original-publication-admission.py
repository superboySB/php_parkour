"""Read-only formal two-student publication admission, source-only candidate.

No CLI, publication writes, subprocesses, Docker/SSH calls or scientific imports.
Future callers must supply actual reviewed contract/start/exit paths and hashes.
This module has not been imported or executed against future artifacts. A ready
return is an execution/provenance claim only; skill/quality remain unverified.
The caller must retain inventory expectations through copying and recheck them
before atomically publishing; this module does not implement publication.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys
from types import ModuleType, SimpleNamespace

ROOT = Path('/home/dzp/projects/php_parkour')
PREPARATION = ROOT/'outputs/research/final-student-reference629-preparation-01'
PREPARATION_SHA = '481d54ee84d4b2d9c439580fe83d00927a44bfc8e2a11101b58862b536d49ce0'
LAUNCHER = ROOT/'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
PUBLISHER = ROOT/'scripts/research/publish_full_scene_matrix.py'
PUBLISHER_SHA = '35432cb8fb8cc46391dc855f51065aaa3ca017ee9ad57a808ded567be29b19ca'
PULL = ROOT/'scripts/research/pull_final_students.py'
PULL_SHA = 'a88f9731f23e3f1469d6d46f54cce5410ee2f5a40c0055523194e6f8ce0912bb'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
KINDS = ('pure', 'finetune')
WORKER_SHA = '023fed0f9f31f79b506b370a96013c18e8b1c94239e0504eca4bcea6076c3f4d'
MATRIX_SHA = '599c75df14c5ac902d57f88bfd3d752317e332abce5751153bef8d20d8d0bb70'
OBSERVER_SHA = 'e2f8c31fc7136027ebd2d8ec6a973753d56a7a60fdd5434e741b0db4022f40d0'
FINALIZER_SHA = 'ef529f29d68d25beab780c56f20207df285d956231ab65335a0facb0362407bb'


def require(value, message):
    if not value:
        raise ValueError(message)


def zero(value):
    return type(value) is int and value == 0


def regular(path):
    path = Path(path).absolute()
    require('..' not in path.parts and
            (path.is_relative_to(ROOT/'outputs/research') or path in (PUBLISHER, PULL)),
            'Unexpected evidence/source path: '+str(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink evidence rejected')
    require(stat.S_ISREG(path.stat().st_mode), 'Actual regular evidence required')
    return path


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: '+key)
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON literal: '+value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


class Evidence:
    """Lock expectations on first read, not by rehashing after verification."""
    def __init__(self):
        self.files = {}
        self.trees = {}

    def fingerprint(self, path, raw=False):
        path = regular(path)
        before = path.stat()
        digest = hashlib.sha256()
        chunks = [] if raw else None
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8*1024*1024), b''):
                digest.update(block)
                if raw:
                    chunks.append(block)
        after = path.stat()
        require((before.st_ino, before.st_mtime_ns, before.st_size) ==
                (after.st_ino, after.st_mtime_ns, after.st_size), 'Evidence changed while reading')
        record = {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}
        require(str(path) not in self.files or self.files[str(path)] == record,
                'Evidence changed since initial verification: '+str(path))
        self.files[str(path)] = record
        return (record, b''.join(chunks)) if raw else record

    def read(self, path, expected=None):
        record, raw = self.fingerprint(path, True)
        if expected is not None:
            require(record['sha256'] == expected, 'Explicit reviewed SHA differs: '+str(path))
        return strict_json(raw)

    def bound(self, record, translate=lambda p: Path(p)):
        actual = self.fingerprint(translate(record['path']))
        require(actual['sha256'] == record['sha256'] and
                actual['bytes'] == record.get('bytes', record.get('size')),
                'Original bound bytes differ: '+record['path'])
        return actual

    def tree(self, directory):
        directory = Path(directory)
        require(directory.is_dir() and not any(p.is_symlink() for p in (directory, *directory.parents)),
                'Actual nonsymlink evidence tree required')
        rows = []
        for path in sorted(directory.rglob('*')):
            require(not path.is_symlink(), 'Symlink in original evidence tree')
            if path.is_dir():
                continue
            rows.append(self.fingerprint(path))
        names = {row['path'] for row in rows}
        key = str(directory)
        require(key not in self.trees or self.trees[key] == names, 'Original evidence file-set changed')
        self.trees[key] = names
        return rows

    def recheck(self):
        for record in list(self.files.values()):
            self.bound(record)
        for directory in list(self.trees):
            self.tree(directory)


def module_from_bytes(path, name, evidence):
    record, raw = evidence.fingerprint(path, True)
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ''
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


@contextmanager
def reviewed_modules(evidence, publisher_path):
    """Load checked bytes without bytecode or executing live matrix imports."""
    manifest = evidence.read(PREPARATION/'preparation-manifest.json', PREPARATION_SHA)
    require(len(manifest['files']) == 35, 'Exact reviewed preparation35 required')
    names = set()
    for row in manifest['files']:
        rel = Path(row['path'])
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in names,
                'Unsafe/duplicate preparation dependency')
        names.add(str(rel))
        evidence.bound(dict(row, path=str(PREPARATION/rel)))
    evidence.bound({'path': str(publisher_path), 'bytes': regular(publisher_path).stat().st_size,
                    'sha256': PUBLISHER_SHA})
    sentinel = object()
    keys = ('support', 'reference_commands', 'scripts', 'scripts.research',
            'scripts.research.sim2sim_scene_matrix')
    prior = {key: sys.modules.get(key, sentinel) for key in keys}
    prior_path, prior_bytecode = sys.path[:], sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        support = module_from_bytes(PREPARATION/'support.py', '_formal_publication_support', evidence)
        sys.modules['support'] = support
        prior_gate = module_from_bytes(PREPARATION/'admission.py', '_formal_publication_prior_gate', evidence)
        reference = module_from_bytes(PREPARATION/'frozen/reference_commands.py', '_formal_reference_commands', evidence)
        sys.modules['reference_commands'] = reference
        matrix = module_from_bytes(PREPARATION/'frozen/sim2sim_scene_matrix.py', '_formal_native_matrix', evidence)
        for key in ('scripts', 'scripts.research'):
            package = ModuleType(key)
            package.__path__ = []
            sys.modules[key] = package
        sys.modules['scripts.research.sim2sim_scene_matrix'] = matrix
        publisher = module_from_bytes(publisher_path, '_formal_publication_readers', evidence)
        yield support, prior_gate, publisher
    finally:
        sys.path[:] = prior_path
        sys.dont_write_bytecode = prior_bytecode
        for key, old in prior.items():
            if old is sentinel:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = old


def process_stat(text):
    fields = text[text.rfind(')')+2:].split()
    return {'pid': int(text.split('(', 1)[0]), 'state': fields[0], 'ppid': int(fields[1]),
            'pgid': int(fields[2]), 'sid': int(fields[3]), 'start_time_clock_ticks': int(fields[19])}


def outer_parent(evidence, start_path, start_sha, exit_path, exit_sha, contract_path, contract_sha):
    evidence.bound({'path': str(LAUNCHER), 'bytes': 2184, 'sha256': LAUNCHER_SHA})
    evidence.tree(Path(start_path).parent)
    start, end = evidence.read(start_path, start_sha), evidence.read(exit_path, exit_sha)
    expected = ['/usr/bin/python3', '-B', str(PREPARATION/'adapter.py'), 'execute',
                '--preparation-sha256', PREPARATION_SHA, '--contract', str(contract_path),
                '--contract-sha256', contract_sha, '--root-authorized-start']
    adapter = evidence.fingerprint(PREPARATION/'adapter.py')
    require(start['argv'] == expected and start['helper_sha256'] == adapter['sha256']
            and start['launcher_sha256'] == LAUNCHER_SHA and zero(end['actual_wait_returncode'])
            and end['pending_signals'] == [] and end['finished_utc']
            and all(end.get(key) == value for key, value in start.items()),
            'Actual original outer launcher/start/child.wait0/argv binding required')
    process = process_stat(start['stat'])
    require(start['pid'] == process['pid'] == process['pgid'] == process['sid']
            and process['start_time_clock_ticks'] > 0 and process['ppid'] == start['parent_pid']
            and process_stat(start['parent_stat'])['pid'] == start['parent_pid']
            and re.fullmatch(r'[0-9a-f-]{36}', start['boot_id']), 'Outer actual PID/session/birth/boot missing')
    evidence.fingerprint(Path(start_path).parent/'stdout.raw')
    evidence.fingerprint(Path(start_path).parent/'stderr.raw')
    require(Path(start_path).name == 'process-start.json' and Path(exit_path) == Path(start_path).with_name('process-exit.json'),
            'Use the same actual outer start/exit directory')
    return start, process


def mounts(info, expected):
    actual = info['Mounts']
    require(len(actual) == len(expected) and len({x['Destination'] for x in actual}) == len(actual)
            and {(x['Source'], x['Destination'], x['RW'], x['Type']) for x in actual} ==
            {(str(source), destination, rw, 'bind') for source, destination, rw in expected},
            'Exact private mount contract differs')


def stopped(stop, cid, reference, image=IMAGE):
    require(stop['container_id'] == cid and stop['running_after_stop'] is False, 'Exact own stop receipt missing')
    for info in (stop['before'], stop['after']):
        require(all(info[key] == reference[key] for key in ('Id', 'Image', 'Name'))
                and info['Id'] == cid and info['Image'] == image
                and info['State']['StartedAt'] == reference['State']['StartedAt']
                and info['Config']['Labels'] == reference['Config']['Labels']
                and sorted(info['Mounts'], key=lambda x: x['Destination']) ==
                    sorted(reference['Mounts'], key=lambda x: x['Destination']),
                'Own container identity/birth/mounts changed')
    require(stop['after']['State']['Running'] is False, 'Own container still running')


def cpu_job(evidence, base, kind, mode, target, expected_report):
    row = evidence.read(target/'launch.json')
    cid, argv = row['container_id'], row['create_argv']
    require(re.fullmatch('[0-9a-f]{64}', cid) and row['status'] == 'passed' and row['kind'] == kind
            and row['mode'] == mode and row['errors'] == row['cleanup_errors'] == []
            and row['native_started'] is False and row['gpu_started'] is False
            and zero(row['create']['returncode']) and row['create']['stdout_raw'].strip() == cid
            and zero(row['actual_container_exit_code']), 'CPU actual create/wait0/report gate failed')
    infos = (row['started_inspect'], row['final_inspect'])
    info = infos[0]
    token = info['Config']['Labels']['php.final-reference629.owner']
    require(re.fullmatch('[0-9a-f]{32}', token), 'CPU unique ownership token missing')
    name = 'php-final-reference629-'+mode+'-'+token[:12]
    expected_mounts = [(base/'source', '/workspace/php_parkour', False),
                       (base/'overlay', '/workspace/php_parkour/scripts/research', False),
                       (base/'inputs'/kind, '/data', False), (base/'control', '/control', False),
                       (target, '/preflight' if mode == 'prepare' else '/validation', True)]
    if mode == 'finalize':
        expected_mounts.append((base/'runs'/kind/'outputs', '/outputs', False))
    command = ['/opt/php/bin/inference-python', '-B', '/control/cpu_prepare.py'] if mode == 'prepare' else [
        '/opt/php/bin/inference-python', '-B', '/control/frozen/validate_scene_matrix.py',
        '--plan', '/outputs/reference629/plan.json', '--matrix', '/outputs/reference629/matrix.json',
        '--output', '/validation/validation.json', '--matrix-module',
        '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py']
    env = {'CUDA_VISIBLE_DEVICES': '', 'NVIDIA_VISIBLE_DEVICES': 'void', 'PHP_DOCKER': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true',
           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'OMP_NUM_THREADS': '1',
           'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MUJOCO_EGL_DEVICE_ID': '0'}
    expected_argv = ['docker', 'create', '--name', name, '--label', 'php.final-reference629.owner='+token,
                     '--runtime', 'runc', '--network', 'none', '--ipc', 'private', '--init', '--shm-size',
                     '1g', '--memory', '12g', '--cpus', '2', '--workdir', '/workspace/php_parkour',
                     '--entrypoint', command[0]]
    for key, value in env.items():
        expected_argv += ['--env', key+'='+value]
    for source, destination, rw in expected_mounts:
        expected_argv += ['--mount', f'type=bind,src={source},dst={destination}'+('' if rw else ',readonly')]
    expected_argv += [IMAGE, *command[1:]]
    require(argv == expected_argv, 'CPU argv does not execute the exact frozen full job')
    for value in infos:
        h = value['HostConfig']
        actual_env = dict(entry.split('=', 1) for entry in value['Config']['Env'])
        require(all(sum(entry.split('=', 1)[0] == key for entry in value['Config']['Env']) == 1 for key in env),
                'CPU controlled environment keys must be unique')
        require(value['Id'] == cid and value['Image'] == IMAGE and value['Name'] == '/'+name
                and value['Config']['Labels'].get('php.final-reference629.owner') == token
                and value['Config']['Entrypoint'] == [command[0]] and value['Config']['Cmd'] == command[1:]
                and all(actual_env.get(k) == v for k, v in env.items())
                and h['Runtime'] == 'runc' and h['NetworkMode'] == 'none' and h['IpcMode'] == 'private'
                and not h.get('PidMode') and h['Init'] is True and h['Privileged'] is False
                and not h.get('DeviceRequests') and h['Memory'] == 12884901888
                and h['NanoCpus'] == 2000000000 and h['ShmSize'] == 1073741824,
                'CPU actual runtime is not isolated runc/network-none/GPU-hidden')
        mounts(value, expected_mounts)
    require(info['State']['StartedAt'] == infos[1]['State']['StartedAt']
            and not info['State']['StartedAt'].startswith('0001-')
            and infos[1]['State']['Running'] is False and zero(infos[1]['State']['ExitCode']),
            'CPU actual final inspect lacks same-birth exit0')
    for label, expected in [('start', ['docker', 'start', cid]), ('wait', ['docker', 'wait', cid]),
                            ('container-logs', ['docker', 'logs', cid])]:
        child = evidence.read(target/(label+'.json'))
        require(child['argv'] == expected and zero(child['returncode']), 'CPU child command did not actually return0')
        out = evidence.bound(child['stdout'])
        evidence.bound(child['stderr'])
        require(Path(out['path']) == target/(label+'.stdout.raw'), 'CPU original child stdout path differs')
        if label == 'wait':
            require(Path(out['path']).read_bytes().strip() == b'0', 'Actual docker-wait stdout is not container0')
    stopped(row['owned_container_stop'], cid, infos[1])
    require(zero(row['owned_container_stop']['after']['State']['ExitCode']), 'CPU stop is not actual terminal0')
    require(evidence.bound(row['report']) == evidence.fingerprint(expected_report), 'CPU report binding differs')
    return row


def kind_admission(evidence, publisher, contract, kind, phase, parent_start, parent_process):
    base = Path(contract['base'])
    run = base/'runs'/kind
    target = run/'cpu-final'
    native_path = run/'host/launch-receipt.json'
    evidence.tree(run/'host')
    evidence.tree(target)
    evidence.tree(run/'outputs')
    native = evidence.read(native_path)
    require(evidence.bound(phase['native']) == evidence.fingerprint(native_path), 'Pair phase refers to another native receipt')
    require(native['status'] == 'native_reference629_completed_worker1258_hostwriter1258'
            and native['errors'] == native['cleanup_errors'] == native['pending_signals'] == []
            and native['image_id'] == IMAGE and native['gpu_uuid'] == GPU
            and native['boot_id'] == parent_start['boot_id']
            and all(native['host_process'][key] == parent_process[key]
                    for key in ('pid', 'ppid', 'pgid', 'sid', 'start_time_clock_ticks'))
            and native['quality_verified'] is native['obstacle_course_completion_verified'] is False
            and zero(native['native']['actual_wait_returncode']) and zero(native['observer']['actual_wait_returncode'])
            and native['completed_configurations'] == 629 and native['completed_scenarios'] == 17
            and native['native_workers_exit0'] == 1258 and native['source_before'] == native['source_after'],
            'Kind must bind actual native/observer0 to the SAME outer adapter process, not a fabricated kind parent')
    evidence.bound(native['helper'])
    require(native['helper'] == evidence.fingerprint(PREPARATION/'native_runner.py'), 'Wrong actual native helper')
    before = native['source_before']
    expected_models = {Path(row['path']).name: evidence.fingerprint(base/'inputs'/kind/'assets/student'/Path(row['path']).name)
                       for row in contract['admission']['models'] if row['kind'] == kind}
    require(before == {'source_files_verified': 5184, 'freeze_manifest': contract['freeze_manifest'],
                       'models': expected_models, 'cpu_reference_plan': contract['kinds'][kind]['cpu_plan'],
                       'observer': evidence.fingerprint(PREPARATION/'frozen/observe_container_pids.py')},
            'Actual source_before contract/official models/CPU plan/observer binding differs')
    require(before['observer']['sha256'] == OBSERVER_SHA, 'Wrong observer source')
    require(set(native['overlay']) == {'sim2sim.py', 'sim2sim_scene_matrix.py', 'reference_commands.py'},
            'Exact three reviewed reference overlay files required')
    for name, item in native['overlay'].items():
        source = evidence.bound(item['source'])
        copied = evidence.bound(item['copy'])
        require(Path(source['path']) == base/'overlay'/name and Path(copied['path']) == run/'overlay'/name
                and source['sha256'] == copied['sha256'], 'Per-kind overlay is not the prepared source')
    cid = native['container_id']
    require(re.fullmatch('[0-9a-f]{64}', cid), 'Exact own full GPU CID required')
    for info in (native['created_inspect'], native['running_inspect']):
        h = info['HostConfig']
        require(info['Id'] == cid and info['Image'] == IMAGE and info['Name'] == '/'+native['container_name']
                and info['Config']['Labels'].get('php.reference629.owner') == native['ownership_token']
                and h['NetworkMode'] == 'none' and h['IpcMode'] == 'private' and not h.get('PidMode')
                and h['Init'] is True and h['ShmSize'] == 8589934592 and not h['Privileged']
                and len(h.get('DeviceRequests') or []) == 1 and h['DeviceRequests'][0]['DeviceIDs'] == [GPU],
                'Exact own GPU identity/isolation/UUID differs')
    require(native['container_name'] == 'php-final-reference629-'+kind+'-'+contract['contract_identity'][:12]
            and native['running_inspect']['State']['Running'] is True, 'Kind container name/start differs')
    stopped(native['owned_container_stop'], cid, native['running_inspect'])
    publisher.REFERENCE_NAMESPACE = publisher.reference_namespace(run, native)
    translate = publisher.host_path
    expected_mounts = [(base/'source', '/workspace/php_parkour', False),
                       (run/'overlay', '/workspace/php_parkour/scripts/research', False),
                       (base/'inputs'/kind, '/data', False), (run/'cache', '/data/cache', True),
                       (run/'checks', '/checks', True), (run/'outputs', '/outputs', True)]
    mounts(native['running_inspect'], expected_mounts)
    plan_path = run/'outputs/reference629/plan.json'
    matrix_path = run/'outputs/reference629/matrix.json'
    plan, matrix = evidence.read(plan_path), evidence.read(matrix_path)
    for key, actual_path in [('native_plan', plan_path), ('native_matrix', matrix_path),
                             ('observer_summary', run/'host/observer/summary.json')]:
        require(evidence.bound(native[key]) == evidence.fingerprint(actual_path), 'Native terminal file binding differs')
    require(evidence.bound(native['prelaunch_plan'])['sha256'] == contract['kinds'][kind]['cpu_plan']['sha256']
            == evidence.fingerprint(plan_path)['sha256'], 'Actual CPU/prelaunch/saved plan bytes differ')
    publisher.validate_plan(plan, matrix, contract['kinds'][kind]['native_plan_identity'], MATRIX_SHA, False)
    require(plan['reference_commands'] is True and plan['worker_harness_record']['sha256'] == WORKER_SHA
            and plan['worker_harness_record']['path'] == '/workspace/php_parkour/scripts/research/sim2sim.py'
            and plan['model_sha256'] ==
            {name: row['sha256'] for name, row in expected_models.items()}, 'Plan does not use the formal pair/reference callbacks')
    expected_argv = ['docker', 'exec', cid, '/opt/php/bin/inference-python', '-B',
                     '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py',
                     '--matrix', '/data/matrix.json', '--models', '/data/assets/student', '--output',
                     '/outputs/reference629', '--all-configs', '--reference-commands', '--image-id', IMAGE, '--gl', 'egl']
    require(native['native']['argv'] == expected_argv and matrix['status'] == 'completed'
            and matrix['configuration_coverage_complete'] is True and matrix['completed_configurations'] == 629
            and matrix['completed_scenarios'] == 17 and matrix['last_invocation']['case_ids'] == []
            and matrix['last_invocation']['case_limit'] is None and matrix['last_invocation']['resume'] is False
            and matrix['last_invocation']['requested_configurations'] == 629, 'Full fresh unfiltered reference execution required')
    for command in native['commands']:
        require(zero(command['returncode']), 'Native actual setup child failed')
        evidence.bound(command['stdout']); evidence.bound(command['stderr'])
    observed = evidence.read(run/'host/observer/summary.json')
    launch = evidence.read(run/'host/observer/launch.json')
    require(native['observer']['argv'] == ['/usr/bin/python3', '-B',
            str(PREPARATION/'frozen/observe_container_pids.py'), '--container-id', cid,
            '--expected-image', IMAGE, '--output', str(run/'host/observer'), '--stop-file',
            str(run/'host/observer.stop'), '--interval', '0.2', '--max-seconds', '86400'],
            'Original observer argv/scope differs')
    identity = observed['identity']
    require(all(observed.get(key) == value for key, value in launch.items()) and
            observed['source_sha256'] == OBSERVER_SHA and observed['mapping_scope_complete'] is True
            and observed['errors'] == [] and observed['stop_reason'] == 'stop_file'
            and identity['container_id'] == cid and identity['image_id'] == IMAGE
            and identity['started_at'] == native['running_inspect']['State']['StartedAt'], 'Actual observer scope/source/container birth differs')
    report_path = target/'validation.json'
    require(evidence.bound(phase['cpu_final']) == evidence.fingerprint(report_path)
            and evidence.bound(phase['cpu_launch']) == evidence.fingerprint(target/'launch.json'), 'Pair CPU phase binding differs')
    cpu_launch = cpu_job(evidence, base, kind, 'finalize', target, report_path)
    report = evidence.read(report_path)
    require(not any(key in report for key in ('error', 'failed_video')) and
            report['helper']['sha256'] == FINALIZER_SHA, 'Failed/other CPU finalizer cannot establish completion')
    evidence.bound(report['helper'], lambda p: base/'control'/Path(p).relative_to('/control'))
    cpu_cases = publisher.validate_cpu_report(report, plan, evidence.fingerprint(matrix_path)['sha256'],
                                               evidence.fingerprint(plan_path)['sha256'], False, matrix['selections'])
    require(len(report['inputs']) == len({row['path'] for row in report['inputs']}), 'CPU input fingerprint duplicates')
    for row in report['inputs']:
        evidence.bound(row, translate)
    all_dirs = [translate(row['output']).resolve() for row in matrix['selections']]
    records = native['host_native_mappings']
    require(len(records) == 1258 and len({(x['case_id'], x['role']) for x in records}) == 1258,
            'All1258 distinct case-role host mappings required')
    mapping_rows = {(x['case_id'], x['role']): x for x in records}
    identities, cases, archives, sealed_workers = set(), [], [], []
    for row in matrix['selections']:
        require(len(row['attempts']) == 1 and row['status'] == 'completed'
                and zero(row['returncode']) and zero(row['attempts'][0]['returncode'])
                and row['attempts'][0]['status'] == 'completed', 'First failure/retry cannot be erased or published as completed')
        case = publisher.validate_case(plan, row, cpu_cases[row['case_id']])
        archive = publisher.validate_attempt_archive(plan, row, row['attempts'][0], all_dirs)
        require(archive['sealed'], 'Only original sealed complete attempts accepted')
        for original in archive['files']:
            evidence.bound(original)
        cases.append(case); archives.append(archive)
        simulation = case['result']['simulation']
        for key in ('minimum_pelvis_height_m', 'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m'):
            require(math.isfinite(float(simulation[key])), 'Nonfinite retained scalar')
        require(len(simulation['final_position_xyz_m']) == 3 and all(math.isfinite(float(x)) for x in simulation['final_position_xyz_m']),
                'Nonfinite retained final physical position')
        for original in case['evidence']['worker_receipts']:
            sealed_workers.append(evidence.bound(original, translate))
        workers = evidence.read(case['directory']/'worker-processes.json')['events'][-1]['workers']
        require(all(zero(worker['returncode']) for worker in workers), 'Native worker returncode must be an actual integer0')
        for role in ('simulator', 'inference'):
            item = mapping_rows[(row['case_id'], role)]
            entry_path = case['directory']/(role+'-process-start.json')
            require(evidence.bound(item['entry']) == evidence.fingerprint(entry_path), 'Host mapping has another original entry')
            entry = evidence.read(entry_path)['process']
            matches = [m for m in observed['command_writer_mappings'] if m['role'] == role and
                       m['worker_output'] == row['output'] and m['container_tgid'] == entry['pid'] and
                       m['owner_start_time_clock_ticks'] == entry['start_time_clock_ticks']]
            require(len(matches) == 1 and matches[0] == item['mapping'], 'Missing/ambiguous original host writer birth')
            m = matches[0]
            require(m['nspid'] == [m['host_tid'], m['container_tid']] and
                    m['nstgid'] == [m['host_tgid'], entry['pid']], 'Writer namespace/owner mismatch')
            key = (m['host_tid'], m['start_time_clock_ticks'])
            require(key not in identities, 'Writer identity reused across case roles')
            identities.add(key)
    require(sealed_workers == native['sealed_worker_receipt_files'] and len(sealed_workers) == 1887
            and native['total_reference_frames'] == report['total_policy_ticks'], 'Worker seals/frame aggregation differs')
    return {'kind': kind, 'base': run, 'native_receipt': native, 'cpu_launch': cpu_launch,
            'cpu_report': report, 'plan': plan, 'matrix': matrix, 'cases': cases, 'archives': archives,
            'namespace': publisher.REFERENCE_NAMESPACE, 'host_writer_identities': identities}


def admit(*, contract_path, contract_sha256, parent_start, parent_start_sha256,
          parent_exit, parent_exit_sha256, publisher_path=PUBLISHER):
    """Future read-only admission. Missing/future/null evidence raises; no writes.

    parent_start/exit are the ONE host_owned_launch pair for adapter.execute.
    No per-kind parent or old CPU execution schema is manufactured. Returned
    original inventory expectations must be preserved by the later publisher.
    Runtime execution and future bindings of this candidate remain unverified.
    """
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
                for value in (contract_sha256, parent_start_sha256, parent_exit_sha256)),
            'Explicit actual reviewed contract/outer-start/outer-exit SHA required')
    contract_path = regular(contract_path)
    evidence = Evidence()
    contract = evidence.read(contract_path, contract_sha256)
    start, process = outer_parent(evidence, parent_start, parent_start_sha256,
                                  parent_exit, parent_exit_sha256, contract_path, contract_sha256)
    with reviewed_modules(evidence, Path(publisher_path)) as (support, prior_gate, publisher):
        require(support.verify_contract(contract_path, contract_sha256) == contract, 'Actual reviewed contract changed')
        require(contract['preparation_manifest']['sha256'] == PREPARATION_SHA
                and contract['preparation_manifest']['path'] == str(PREPARATION/'preparation-manifest.json'),
                'Contract is not the frozen formal35 dependency preparation')
        prior = contract['admission']
        require(evidence.fingerprint(PULL)['sha256'] == PULL_SHA, 'Actual selective transfer validator source changed')
        args = SimpleNamespace(transfer=Path(prior['transfer']['destination']), native58_base=Path(prior['native58_base']),
            native58_exit=Path(prior['actual_parent_wait']['path']), native58_exit_sha256=prior['actual_parent_wait']['sha256'],
            native58_review=Path(prior['independent_review']['path']), native58_review_sha256=prior['independent_review']['sha256'])
        require(prior_gate.admission(args) == prior and prior['status'] == 'ready', 'Actual32fetch/58/60ORT/pose/review admission differs')
        for row in prior['bound_files']:
            evidence.bound(row)
        freeze = evidence.read(contract['freeze_manifest']['path'])
        require({row['relative']: row for row in freeze['files'] if row['relative'].startswith('source/')} ==
                {row['relative']: row for row in support.source_rows()},
                'Frozen5184 original source inventory differs')
        for row in freeze['files']:
            evidence.bound(dict(row, path=str(Path(contract['base'])/row['relative'])))
        base = Path(contract['base'])
        prepared = evidence.read(PREPARATION/'preparation-manifest.json', PREPARATION_SHA)
        for row in prepared['files']:
            evidence.bound(dict(row, path=str(base/'control'/row['path'])))
        pair_path = base/'runs/launch-receipt.json'
        pair = evidence.read(pair_path)
        require(pair['status'] == 'completed' and pair['errors'] == pair['pending_signals'] == []
                and pair['contract'] == evidence.fingerprint(contract_path)
                and pair['quality_verified'] is pair['obstacle_course_completion_verified'] is False
                and [phase['kind'] for phase in pair['phases']] == list(KINDS)
                and all(pair[key] == value for key, value in
                        {'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}.items()),
                'Actual outer ordered1258/2516/2516/1258 completion missing')
        preparation_cids = []
        for kind in KINDS:
            item = contract['kinds'][kind]
            target = base/'host'/('cpu-'+kind)
            evidence.tree(target)
            preparation_cids.append(cpu_job(evidence, base, kind, 'prepare', target, target/'summary.json')['container_id'])
            summary, onnx = evidence.read(target/'summary.json'), evidence.read(target/'onnx.json')
            require(summary['status'] == onnx['status'] == 'passed' and summary['image_id'] == IMAGE
                    and summary['configurations'] == 629 and summary['scenarios'] == 17 and summary['ort_cases'] == 30
                    and len(onnx['cases']) == 30 and summary['pose'] == prior['poses'][kind]
                    == onnx['native_default_pose_compatibility'], 'Actual per-kind CPU plans/30ORT/deployment pose mismatch')
            model_table = {Path(x['path']).name: (x['bytes'], x['sha256']) for x in prior['models'] if x['kind'] == kind}
            require({Path(x['path']).name: (x['bytes'], x['sha256']) for x in onnx['models']} == model_table,
                    'CPU ORT used another formal pair')
            require(evidence.bound(item['cpu_plan']) == evidence.fingerprint(target/'reference-plan.json')
                    and evidence.bound(item['cpu_summary']) == evidence.fingerprint(target/'summary.json')
                    and evidence.bound(item['cpu_launch']) == evidence.fingerprint(target/'launch.json'), 'Prepared CPU actual receipt mismatch')
        kinds = [kind_admission(evidence, publisher, contract, kind, phase, start, process)
                 for kind, phase in zip(KINDS, pair['phases'])]
        for phase in pair['phases']:
            require({key: phase[key] for key in ('cases', 'workers', 'host_maps', 'full_decodes')} ==
                    {'cases': 629, 'workers': 1258, 'host_maps': 1258, 'full_decodes': 629}, 'Kind phase counts differ')
        require(len({item['native_receipt']['container_id'] for item in kinds}) == 2
                and len({item['cpu_launch']['container_id'] for item in kinds}) == 2
                and len(set(preparation_cids + [item['native_receipt']['container_id'] for item in kinds]
                            + [item['cpu_launch']['container_id'] for item in kinds])) == 6
                and len(set.union(*(item['host_writer_identities'] for item in kinds))) == 2516,
                'Kinds share containers or host writer births')
        require(support.verify_contract(contract_path, contract_sha256) == contract, 'Prepared source/models changed during admission')
    evidence.recheck()
    return {'status': 'ready_for_separately_reviewed_publication', 'contract': contract,
            'actual_parent_start': evidence.files[str(Path(parent_start).absolute())],
            'actual_parent_exit': evidence.files[str(Path(parent_exit).absolute())], 'pair_receipt': pair,
            'kinds': kinds, 'inventory': list(evidence.files.values()),
            'expected_file_sets': {key: sorted(value) for key, value in evidence.trees.items()},
            'counts': {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258},
            'quality_verified': False, 'obstacle_course_completion_verified': False,
            'publication_created': False, 'science_executed_by_admission': False,
            'scope': 'Original 32-file delivery + actual58 + same-outer-process formal two-kind native/CPU terminal evidence; no inferred old schemas'}
