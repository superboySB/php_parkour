#!/usr/bin/env python3
"""Freeze low-step-only copies and input wiring; never executes Docker/science."""
from pathlib import Path
import ast
import datetime as dt
import difflib
import hashlib
import json
import shutil

BASE = Path(__file__).resolve().parent
PARENT = BASE.parent
ORIGINAL = PARENT / 'teacher-locomotion-final-cpu-02'
TRANSFER = PARENT / 'teacher-low-step-final-01'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'


def fp(path):
    path = Path(path).absolute()
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Regular nonsymlink file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            digest.update(block)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Expected one exact original source fragment: ' + old[:70])
    return source.replace(old, new)


def copy(src, dst):
    shutil.copyfile(src, dst)
    dst.chmod(0o644)
    if (fp(src)['bytes'], fp(src)['sha256']) != (fp(dst)['bytes'], fp(dst)['sha256']):
        raise ValueError('Copied source/input differs: ' + str(dst))


def main():
    source = BASE / 'source'; inputs = BASE / 'input'; diffs = BASE / 'diffs'; before = BASE / 'source-original'
    for path in (source, inputs, diffs, before):
        path.mkdir(exist_ok=False)
    transfer = json.loads((TRANSFER / 'receipt.json').read_bytes())
    inventory = json.loads((TRANSFER / 'inventory-before.stdout.raw').read_bytes())
    if transfer['status'] != 'completed' or not transfer['remote_source_unchanged'] or not inventory['initial_checkpoint_exists']:
        raise ValueError('Completed exact transfer with same-run native baseline required')
    if len(inventory['event_file_names']) != 1:
        raise ValueError('Original scalar checker requires exactly one actual event file; review multiple segments explicitly')
    artifact_records = {Path(row['local']['path']).name: row['local'] for row in transfer['artifact_mapping']}
    for row in artifact_records.values():
        if fp(row['path']) != row:
            raise ValueError('Transferred input changed')
    originals = [ORIGINAL / 'source' / name for name in ('accept_teacher.py', 'plot_learning_curves.py', 'run_cpu_phases.py', 'validate_teacher_onnx.py')]
    original_launcher = PARENT / 'teacher-locomotion-final-cpu-launch-02.py'
    originals.append(original_launcher)
    original_fp = [fp(path) for path in originals]
    for path in originals:
        copy(path, before / path.name)
    accept = originals[0].read_text()
    start = accept.index('ARTIFACTS = {\n')
    end = accept.index('\n}\n', start) + 3
    mapping = 'ARTIFACTS = {\n' + ''.join('    ' + repr(name) + ': (' + str(row['bytes']) + ', ' + repr(row['sha256']) + '),\n' for name, row in artifact_records.items()) + '}\n'
    accept = accept[:start] + mapping + accept[end:]
    accept = accept.replace('teacher-locomotion', 'teacher-low-step').replace('motions-locomotion', 'motions-low-step')
    accept = accept.replace('One completed locomotion teacher', 'One completed low-step teacher')
    accept = accept.replace('Completed first official locomotion teacher', 'Completed second official low-step teacher')
    old_event = 'events.out.tfevents.1791606211.pro5000-6.47700.0'
    accept = accept.replace(old_event, inventory['event_file_names'][0])
    accept = replace_once(accept, 'baseline_record = fingerprint(args.baseline)', "baseline_record = artifact(args.baseline.parent, 'model_00000.pt')")
    accept = replace_once(accept, "    contract = config_contract(config)\n", "    contract = config_contract(config)\n    baseline_contract = config_contract(baseline['experiment_config'])\n    require(baseline_contract == contract and baseline['experiment_config'] == config,\n            'Same-run iteration-zero and final checkpoint full configurations must match')\n")
    accept = replace_once(accept, "'configuration_serialization':", "'baseline_config_binding': {'full_config_equal': True, 'contract': baseline_contract,\n                                        'source': 'Same low-step native run, remote before/after SHA and actual baseline ARTIFACTS pin'},\n            'configuration_serialization':")
    (source / 'accept_teacher.py').write_text(accept)
    plot = originals[1].read_text().replace('teacher-locomotion', 'teacher-low-step')
    plot = plot.replace('first teacher', 'second low-step teacher').replace('first-teacher', 'second-teacher')
    plot = plot.replace('Official locomotion teacher — first', 'Official low-step teacher — second')
    plot = plot.replace('FIRST TEACHER COMPLETED', 'SECOND TEACHER COMPLETED')
    plot = plot.replace('first official locomotion teacher', 'second official low-step teacher')
    plot = plot.replace('rendered_completed_first_teacher_curves', 'rendered_completed_second_teacher_curves')
    (source / 'plot_learning_curves.py').write_text(plot)
    for path in originals[2:4]:
        copy(path, source / path.name)
    for path in source.glob('*.py'):
        ast.parse(path.read_bytes()); path.chmod(0o644)
    expected = {name: fp(source / name)['sha256'] for name in ('accept_teacher.py', 'plot_learning_curves.py')}
    launcher = original_launcher.read_text()
    launcher = launcher.replace('ROOT=Path(__file__).resolve().parents[3]', 'ROOT=Path(__file__).resolve().parents[4]')
    launcher = replace_once(launcher, "BASE=Path(__file__).parent/'teacher-locomotion-final-cpu-02'", 'BASE=Path(__file__).resolve().parent')
    launcher = launcher.replace('php-official-locomotion-final-cpu-02', 'php-official-low-step-final-cpu-01')
    launcher = launcher.replace('official-locomotion-final-cpu-02', 'official-low-step-final-cpu-01')
    launcher = launcher.replace('61b43730942cbd5af868007bc7a013fbbdb4a5ae261050c3e160fcfd80decc9a', expected['accept_teacher.py'])
    launcher = launcher.replace('84d7ab2a0d26e35d21fc25e6f1c9bafe93422d0d80cbb264526a39bf2b5d82c2', expected['plot_learning_curves.py'])
    launcher = replace_once(launcher, "Path(__file__).parent/'teacher-locomotion-final-01/artifacts'", "BASE.parent/'teacher-low-step-final-01/artifacts'")
    (BASE / 'run_cpu.py').write_text(launcher)
    ast.parse(launcher)
    for original, current in [*[(ORIGINAL / 'source' / name, source / name) for name in ('accept_teacher.py', 'plot_learning_curves.py', 'run_cpu_phases.py', 'validate_teacher_onnx.py')], (original_launcher, BASE / 'run_cpu.py')]:
        diff = ''.join(difflib.unified_diff(original.read_text().splitlines(True), current.read_text().splitlines(True), fromfile=str(original), tofile=str(current)))
        (diffs / (current.name + '.diff')).write_text(diff)
    selected = {
        'teacher-low-step.json': TRANSFER / 'teacher-low-step.json',
        'transfer-receipt.json': TRANSFER / 'receipt.json',
        'inventory-before.json': TRANSFER / 'inventory-before.stdout.raw',
        'inventory-after.json': TRANSFER / 'inventory-after.stdout.raw',
        'runtime-resolution-source.py': TRANSFER / 'runtime-resolution-source.py',
        'model_00000.pt': TRANSFER / 'artifacts/model_00000.pt',
    }
    for name, path in selected.items():
        copy(path, inputs / name)
    records = []
    for path in sorted(inputs.iterdir()):
        row = fp(path); row['path'] = '/control/' + path.name; records.append(row)
    for name, row in sorted(artifact_records.items()):
        records.append({'path': '/artifacts/' + name, 'bytes': row['bytes'], 'sha256': row['sha256']})
    save(inputs / 'input-manifest.json', {'schema_version': 1, 'scope': 'Actual low-step same-run final PT/ONNX/YAML/event and iteration-zero baseline; no synthetic or other-teacher inputs', 'records': records})
    mounts = [{'source': str(source), 'destination': '/code', 'read_only': True},
              {'source': str(inputs), 'destination': '/control', 'read_only': True},
              {'source': str(TRANSFER / 'artifacts'), 'destination': '/artifacts', 'read_only': True},
              {'source': str(BASE / 'validation'), 'destination': '/validation', 'read_only': False}]
    contract = {'schema_version': 1, 'status': 'prepared_not_executed', 'container_name': 'php-official-low-step-final-cpu-01',
        'image': IMAGE, 'runtime': 'runc', 'network': 'none', 'gpu_device_requests': [], 'cpus': 2, 'memory': '12g',
        'environment': {'CUDA_VISIBLE_DEVICES': '', 'NVIDIA_VISIBLE_DEVICES': 'void', 'PYTHONDONTWRITEBYTECODE': '1',
                        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'ACCEPT_EULA': 'Y', 'OMNI_KIT_ACCEPT_EULA': 'YES'},
        'mounts': mounts, 'container_argv': ['/usr/bin/python3', '-B', '/code/run_cpu_phases.py'],
        'root_launch_argv': ['python3', '-B', str(BASE / 'run_cpu.py')], 'source_files': [fp(p) for p in sorted(source.glob('*.py'))],
        'host_runner': fp(BASE / 'run_cpu.py'), 'input_manifest': fp(inputs / 'input-manifest.json'),
        'actual_transfer': fp(TRANSFER / 'receipt.json'), 'actual_remote_inventory': fp(TRANSFER / 'inventory-before.stdout.raw'),
        'actual_event_file': inventory['event_file_names'][0], 'baseline_source': next(r for r in inventory['artifacts'] if r['path'].endswith('/model_00000.pt')),
        'baseline_local_artifact': artifact_records['model_00000.pt'], 'baseline_control_copy': fp(inputs / 'model_00000.pt'),
        'baseline_config_gate': 'Require actual native baseline and final full experiment_config equality, and both official low-step contracts',
        'expected_dimensions_not_yet_numerically_verified': {'actor': 449, 'critic': 575, 'action': 29},
        'configuration_evidence': {'yaml': artifact_records['holosoma_config.yaml'], 'text_fields_observed': ['teacher-low-step', 'file:///data/assets/motions-low-step', 'num_envs: 4096', 'seed: 42', 'num_variants: 64', 'add_onpath_obstacle: true', 'obstacle_seed: 42', 'action_scale: 1.0']},
        'cpu_acceptance_executed': False, 'quality_verified': False, 'convergence_verified': False, 'official_schedule_complete': False,
        'fresh_output_required': [str(BASE / 'host'), str(BASE / 'validation')], 'failure_policy': 'Keep all raw outputs and partial failures; no automatic retry or overwrite'}
    save(BASE / 'contract.json', contract)
    if [fp(path) for path in originals] != original_fp:
        raise ValueError('Original first-teacher source changed during preparation')
    for name in ('run_cpu_phases.py', 'validate_teacher_onnx.py'):
        if fp(source / name)['sha256'] != fp(ORIGINAL / 'source' / name)['sha256']:
            raise ValueError('Generic CPU phase/ONNX source must remain byte-exact')
    save(BASE / 'preparation.json', {'schema_version': 1, 'status': 'prepared_not_executed',
        'prepared_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'preparer': fp(__file__),
        'original_sources_before': original_fp, 'original_sources_after': [fp(path) for path in originals],
        'source_files': contract['source_files'], 'host_runner': contract['host_runner'], 'contract': fp(BASE / 'contract.json'),
        'input_manifest': contract['input_manifest'], 'diffs': [fp(p) for p in sorted(diffs.iterdir())],
        'generic_sources_byte_exact': True, 'ast_parse_only': True, 'cpu_container_created': False,
        'scientific_imports_executed': False, 'native_or_gpu_started': False})
    print(json.dumps({'status': 'prepared_not_executed', 'contract': fp(BASE / 'contract.json'), 'cpu_container_created': False}))


if __name__ == '__main__':
    main()
