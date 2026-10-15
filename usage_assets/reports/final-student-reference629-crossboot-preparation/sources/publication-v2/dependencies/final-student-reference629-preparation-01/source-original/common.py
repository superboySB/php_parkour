"""Local stdlib contracts; importing this module never starts any process."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
UUID = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
REVISION = '6cb2ae2492ef7bf66da7c5a72da87d6f60f0636f'
TREE = '02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c'
PULL_SHA = 'a88f9731f23e3f1469d6d46f54cce5410ee2f5a40c0055523194e6f8ce0912bb'
MATRIX_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
SUPERVISOR_SHA = 'd9f958830bfb887b18239ee25a2306ddf1c88201bc1415571e6b6665263cd873'
SDK = {'simulator': '9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926',
       'inference': 'fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4'}
KINDS = ('pure', 'finetune')
PHASES = ('directions', 'scenes')
MODELS = ('depth_backbone.onnx', 'student.onnx')
HOST_WORKSPACE = Path('/home/dzp/projects/php_parkour')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON token: '+value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    temporary.replace(path)


def regular(path, root=None):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink ancestor rejected: '+str(path))
    require(path.is_file(), 'Missing regular file: '+str(path))
    if root is not None:
        require(path.resolve().is_relative_to(Path(root).resolve()), 'Path escapes its dedicated root')
    return path


def record(path):
    path = regular(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def verify_record(item):
    path = regular(item['path'])
    require(sha(path) == item['sha256'] and path.stat().st_size == item['bytes'], 'Changed sealed file: '+str(path))


def copy(source, target, expected=None, size=None):
    source = regular(source)
    target = Path(target)
    require(not target.exists() and not target.is_symlink(), 'Never overwrite snapshot destination')
    before = record(source)
    require(expected is None or expected == before['sha256'], 'Source SHA differs')
    require(size is None or size == before['bytes'], 'Source byte size differs')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o444)
    require(sha(target) == before['sha256'] and record(source) == before, 'Source mutated while copying')
    return record(target)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, regular(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transfer(workspace, destination):
    """No guessing/latest selection, no SSH, no writes or Docker inspection."""
    require(destination is None or '..' not in Path(destination).parts,'Parent traversal in transfer path rejected')
    if destination is None or not Path(destination).exists():
        return {'status': 'waiting', 'reason': 'Explicit completed final-student fetch directory is not available',
                'fetch_executed': False, 'native_started': False, 'gpu_started': False}
    destination = Path(destination).absolute()
    root = Path(workspace).resolve()/'outputs/research/final-student-transfer'
    require(destination.is_relative_to(root), 'Use the dedicated final-student-transfer subtree')
    require(not any(p.is_symlink() for p in (destination, *destination.parents)), 'Transfer path has symlink ancestor')
    helper = Path(workspace)/'scripts/research/pull_final_students.py'
    require(sha(helper) == PULL_SHA, 'Reviewed selective transfer helper changed')
    pull = load(helper, 'native58_reviewed_pull')
    before = read(regular(destination/'remote-before.json'))
    after = read(regular(destination/'remote-after.json'))
    files = pull.validate_receipt(before)
    require(before['payload'] == after.get('payload') and before['snapshot_identity'] == after.get('snapshot_identity')
            and after.get('status') == 'ready', 'Remote before/after immutable receipt differs')
    require(before['payload']['source_tree'] == TREE and before['payload']['coverage_output'] == pull.COVERAGE_DIRECTORY
            and before['payload']['remote_root'] == pull.REMOTE_ROOT,
            'Final receipt belongs to another reviewed coverage tree/directory')
    report = read(regular(destination/'fetch-status.json'))
    require(report['status'] == 'completed' and report['snapshot_identity'] == before['snapshot_identity']
            and report['destination'] == str(destination) and report['files'] == 32
            and report['transfer_tool_sha256'] == PULL_SHA and report['quality_verified'] is False
            and report['total_bytes'] == sum(x['bytes'] for x in files), 'Fetch is not a completed SHA-bound selective transfer')
    pull.verify_download(destination/'raw', files)
    coverage = before['payload']['coverage_output']
    selection = read(destination/'raw'/coverage/'selection.json')
    cpu = read(destination/'raw'/coverage/'cpu-ready.json')
    require(selection['schema_version'] == 2 and selection['coverage_source_tree'] == TREE
            and selection['host_coverage_output'] == before['payload']['host_coverage_output']
            and selection['image'] == before['payload']['image']
            and selection['input_identity'] == before['payload']['selection_identity']
            and selection['input_identity'] == identity({k:v for k,v in selection.items() if k != 'input_identity'})
            and cpu['status'] == 'cpu_scientific_checks_passed' and cpu['input_identity'] == selection['input_identity']
            and cpu['runtime_robot_assets'] == selection['runtime_robot_assets'], 'Transferred CPU selection contract changed')
    expected = []
    for pair in before['payload']['pairs']:
        for name, item in pair['models'].items():
            target = regular(destination/'models'/pair['kind']/name)
            require(sha(target) == item['sha256'] and target.stat().st_size == item['bytes'], 'Materialized final model differs from cloud export')
            expected.append({'kind': pair['kind'], 'source_relative': item['relative'], **record(target)})
    require(len(expected) == 4 and sorted(report['models'], key=lambda x:x['path']) == sorted(expected, key=lambda x:x['path']),
            'Fetch materialized model table is not exact four models')
    origins = [record(destination/name) for name in ('remote-before.json', 'remote-after.json', 'fetch-status.json')]
    origins += [record(destination/'raw'/x['relative']) for x in files]
    origins += [record(x['path']) for x in expected]
    return {'status': 'ready', 'destination': str(destination), 'cohort': before['cohort'],
            'snapshot_identity': before['snapshot_identity'], 'selection_identity': selection['input_identity'],
            'cloud_payload': before['payload'], 'models': expected, 'origin_files': origins,
            'fetch_executed': False, 'native_started': False, 'gpu_started': False, 'quality_verified': False}


def phase_specs():
    return [{'id': kind+'-'+phase, 'kind':kind, 'phase':phase,
             'cases':12 if phase == 'directions' else 17, 'ticks':400 if phase == 'directions' else 500,
             'seconds':8.0 if phase == 'directions' else 10.0,
             'native_wall_timeout_seconds':373.0 if phase == 'directions' else 413.0,
             'startup_timeout_seconds':180.0,
             'host_timeout_seconds':4596 if phase == 'directions' else 7141}
            for kind in KINDS for phase in PHASES]
