#!/usr/bin/env python3
"""Root-owned CPU validation for the frozen reference629 cohort; starts nothing on import."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path('/home/dzp/projects/php_parkour')
NATIVE = ROOT / 'outputs/research/reference-native629-01'
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
CONTROLLER = ROOT / 'outputs/research/reference629-native-controller-01.py'
CONTROLLER_SHA = 'e25f6be50253044770bae37ba37e8b1db10098b65bf585d2d2af99d42e2e32f0'
PARENT = ROOT / 'outputs/research/reference629-native-parent-01'
PLAN = ROOT / 'outputs/research/reference629-cpu-plan-01/checks/reference629-plan.json'
PLAN_SHA = '7729d5e6b4ea740e69511172c2331dd880cb7aaac3c75a07ccebb8e50d47311f'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'


def require(value, message):
    if not value:
        raise ValueError(message)


def fp(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Regular file required: ' + str(path))
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def full_native_gate(controller, receipt):
    start_path, exit_path = PARENT / 'process-start.json', PARENT / 'process-exit.json'
    start, terminal = json.loads(start_path.read_text()), json.loads(exit_path.read_text())
    require(terminal['actual_wait_returncode'] == 0 and not terminal['pending_signals']
            and all(terminal[key] == value for key, value in start.items())
            and start['helper_sha256'] == CONTROLLER_SHA and start['argv'][2] == str(CONTROLLER),
            'Independent native parent has not actually waited exit0')
    require(receipt['status'] == 'native_reference629_completed_worker1258_hostwriter1258'
            and not receipt['errors'] and not receipt['cleanup_errors'] and not receipt['pending_signals']
            and receipt['native']['actual_wait_returncode'] == receipt['observer']['actual_wait_returncode'] == 0
            and receipt['source_before'] == receipt['source_after'], 'Original native controller did not finish normally')
    actual = json.loads(subprocess.check_output(['docker', 'inspect', receipt['container_id']], text=True))[0]
    stopped = receipt['owned_container_stop']['after']
    require(actual['Id'] == stopped['Id'] == receipt['container_id'] and actual['Image'] == IMAGE
            and actual['State']['StartedAt'] == stopped['State']['StartedAt']
            and actual['State']['Running'] is False and stopped['State']['Running'] is False,
            'Original native owned container is not stopped with its original identity')
    verified = controller.verify_matrix_and_host_mappings()
    require(all(receipt[key] == value for key, value in verified.items()), 'Original native terminal seals/maps changed')
    return {'controller_receipt': fp(NATIVE / 'host/launch-receipt.json'),
            'parent_start': fp(start_path), 'parent_exit': fp(exit_path),
            'stopped_native_container': actual, 'native_workers_exit0': 1258, 'host_writer_mappings': 1258}


def native_gate_equal(before, after):
    """Compare every retained field; only Docker Mounts list order is immaterial.

    Both original raw inspect dictionaries remain in execution.json. Sorting
    full mount records retains duplicates and every mount field/value.
    """
    values = []
    for raw in (before, after):
        value = copy.deepcopy(raw)
        value['stopped_native_container']['Mounts'].sort(
            key=lambda mount: json.dumps(mount, sort_keys=True, allow_nan=False))
        values.append(value)
    return values[0] == values[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-authorized-start', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--validator', type=Path, required=True)
    parser.add_argument('--validator-sha256', required=True)
    parser.add_argument('--preview-case-id', action='append', default=[])
    args = parser.parse_args()
    require(args.root_authorized_start, 'Explicit root operation required')
    base = args.output.resolve()
    require(base.parent == ROOT / 'outputs/research' and base.name.startswith('reference629-cpu-')
            and not base.exists(), 'Fresh independent reference629-cpu output required')
    require(fp(CONTROLLER)['sha256'] == CONTROLLER_SHA and fp(PLAN)['sha256'] == PLAN_SHA, 'Frozen controller/plan changed')
    validator = args.validator.resolve()
    require(fp(validator)['sha256'] == args.validator_sha256, 'Reviewed validator changed')
    spec = importlib.util.spec_from_file_location('original_reference_controller', CONTROLLER)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    base.mkdir()
    for name in ('host', 'control', 'validation'):
        (base / name).mkdir()
    report_path = base / 'host/execution.json'
    row = {'schema_version': 1, 'status': 'starting', 'helper': fp(Path(__file__).resolve()),
           'started_unix': time.time(), 'image_id': IMAGE, 'preview': bool(args.preview_case_id),
           'quality_verified': False, 'errors': [], 'cleanup_errors': [], 'commands': []}
    token = uuid.uuid4().hex
    name = 'php-reference629-cpu-' + token[:12]
    cid = started_at = None

    def persist():
        write(report_path, row)

    def capture(argv, label, check=True):
        value = subprocess.run(argv, text=True, capture_output=True)
        out, err = base / 'host' / (label + '.stdout.raw'), base / 'host' / (label + '.stderr.raw')
        out.write_text(value.stdout)
        err.write_text(value.stderr)
        row['commands'].append({'argv': argv, 'returncode': value.returncode, 'stdout': fp(out), 'stderr': fp(err)})
        persist()
        if check:
            require(value.returncode == 0, label + ' failed; retained original stdout/stderr')
        return value

    def own_inspect():
        value = json.loads(subprocess.check_output(['docker', 'inspect', cid], text=True))[0]
        require(value['Id'] == cid and value['Image'] == IMAGE and value['Name'] == '/' + name
                and value['Config']['Labels'].get('php.reference629.cpu.owner') == token,
                'Exact owned CPU container identity differs')
        if started_at is not None:
            require(value['State']['StartedAt'] == started_at, 'Owned CPU container restarted')
        return value

    try:
        native_receipt = json.loads((NATIVE / 'host/launch-receipt.json').read_text())
        row['source_before'] = controller.snapshot()
        require(row['source_before'] == native_receipt['source_before'], 'Original native input snapshot differs')
        if not args.preview_case_id:
            row['native_terminal_gate'] = full_native_gate(controller, native_receipt)
        copied = base / 'control/validate_scene_matrix.py'
        copied.write_bytes(validator.read_bytes())
        require(fp(copied)['sha256'] == args.validator_sha256, 'Validator changed while freezing')
        row['validation_helper'] = fp(copied)
        for filename, expected in controller.SOURCE_SHAS.items():
            require(fp(NATIVE / 'overlay' / filename)['sha256'] == expected, 'Frozen native overlay changed')
        mounts = [(OLD / 'source', '/workspace/php_parkour', True),
                  (NATIVE / 'overlay', '/workspace/php_parkour/scripts/research', True),
                  (OLD / 'inputs', '/data', True), (NATIVE / 'outputs', '/outputs', True),
                  (PLAN, '/plan.json', True), (base / 'control', '/control', True),
                  (base / 'validation', '/validation', False)]
        argv = ['docker', 'create', '--name', name, '--label', 'php.reference629.cpu.owner=' + token,
                '--runtime', 'runc', '--network', 'none', '--ipc', 'private', '--init', '--cpus', '2',
                '--memory', '8g', '--workdir', '/workspace/php_parkour', '--entrypoint', '/bin/bash']
        for key, value in {'NVIDIA_VISIBLE_DEVICES': 'void', 'CUDA_VISIBLE_DEVICES': '', 'PHP_DOCKER': '1',
                           'PYTHONDONTWRITEBYTECODE': '1', 'WANDB_DISABLED': 'true', 'WANDB_MODE': 'disabled',
                           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'OMP_NUM_THREADS': '1',
                           'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}.items():
            argv += ['--env', key + '=' + value]
        for source, destination, readonly in mounts:
            argv += ['--mount', f'type=bind,src={source},dst={destination}' + (',readonly' if readonly else '')]
        created = capture([*argv, IMAGE, '-lc', 'exec sleep infinity'], 'create')
        cid = created.stdout.strip()
        require(len(cid) == 64 and all(char in '0123456789abcdef' for char in cid), 'Exact full owned CID required')
        row['container_id'] = cid
        row['created_inspect'] = own_inspect()
        hc = row['created_inspect']['HostConfig']
        require(hc['Runtime'] == 'runc' and not hc.get('DeviceRequests') and not hc.get('Devices')
                and hc['NetworkMode'] == 'none' and hc['IpcMode'] == 'private' and not hc.get('PidMode')
                and not hc['Privileged'] and hc['Init'] is True, 'CPU isolation differs')
        require({(m['Source'], m['Destination'], not m['RW']) for m in row['created_inspect']['Mounts']}
                == {(str(s), d, ro) for s, d, ro in mounts}, 'CPU mounts differ')
        capture(['docker', 'start', cid], 'start')
        row['running_inspect'] = own_inspect()
        require(row['running_inspect']['State']['Running'], 'Owned CPU container failed to start')
        started_at = row['running_inspect']['State']['StartedAt']
        command = ['docker', 'exec', cid, '/opt/php/bin/inference-python', '-B',
                   '/control/validate_scene_matrix.py', '--plan', '/plan.json', '--matrix', '/outputs/reference629/matrix.json',
                   '--matrix-module', '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py',
                   '--output', '/validation/validation.json']
        for case_id in args.preview_case_id:
            command += ['--preview-case-id', case_id]
        row.update(status='running', command=command)
        persist()
        with (base / 'host/validation.stdout.raw').open('xb') as out, (base / 'host/validation.stderr.raw').open('xb') as err:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            row['cpu_client_pid'] = child.pid
            persist()
            row['actual_wait_returncode'] = child.wait()
        require(row['actual_wait_returncode'] == 0, 'Actual CPU validator failed; retain first failure')
        row['validation_report'] = fp(base / 'validation/validation.json')
        report = json.loads((base / 'validation/validation.json').read_text())
        require(report['native_plan_file_sha256'] == PLAN_SHA and report['preview'] is bool(args.preview_case_id)
                and report['helper']['sha256'] == args.validator_sha256
                and report['status'] == ('preview_validated' if args.preview_case_id else 'passed')
                and report['completion_verified'] is (not bool(args.preview_case_id)), 'CPU validation scope differs')
        row['source_after'] = controller.snapshot()
        require(row['source_before'] == row['source_after'] and fp(copied) == row['validation_helper'], 'Frozen inputs/helper changed')
        if not args.preview_case_id:
            row['native_terminal_gate_after'] = full_native_gate(controller, native_receipt)
            require(native_gate_equal(row['native_terminal_gate'], row['native_terminal_gate_after']), 'Native terminal gate changed')
        row['status'] = 'completed'
    except BaseException as error:
        row['status'] = 'failed'
        row['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if cid is not None:
            try:
                before = own_inspect()
                if before['State']['Running']:
                    capture(['docker', 'stop', '--time', '20', cid], 'stop')
                after = own_inspect()
                require(after['State']['Running'] is False, 'Owned CPU container still running')
                waited = capture(['docker', 'wait', cid], 'container-wait')
                row['owned_container_stop'] = {'container_id': cid, 'before': before, 'after': after,
                                               'running_after_stop': False, 'actual_container_exit_code': int(waited.stdout.strip())}
            except BaseException as error:
                row['cleanup_errors'].append(str(error))
        if row['cleanup_errors']:
            row['status'] = 'failed'
        row['finished_unix'] = time.time()
        persist()
    print(json.dumps({'status': row['status'], 'preview': row['preview'], 'receipt': str(report_path)}))
    return 0 if row['status'] == 'completed' else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
