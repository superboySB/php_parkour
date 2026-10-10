"""CPU post-run validation of actual pilot; this does not execute a policy."""
import itertools
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/workspace/php_parkour/scripts/research')
import sim2sim_scene_matrix as matrix

base = Path('/outputs/rollout')
checks = Path('/checks')
host = json.loads(Path('/host-launch.json').read_text())
assert host['native']['actual_wait_returncode'] == host['observer']['actual_wait_returncode'] == 0
assert not host['errors'] and not host['cleanup_errors']
assert host['owned_container_stop']['running_after_stop'] is False
assert len(host['host_native_mappings']) == 2
cfg = json.loads((base / 'run.json').read_text())
reference = matrix.load_reference_commands(cfg['reference_motion']['path'])
closure = matrix.dependencies()
harness = next(item for item in closure if item['path'].endswith('/scripts/research/sim2sim.py'))
assert harness['sha256'] == host['overlay']['sim2sim.py']['copy']['sha256']
plan = {'schema_version': 3, 'python_faulthandler': True, 'reference_commands': True,
        'seconds_per_configuration': None, 'seed': cfg['seed'], 'dependencies': closure,
        'worker_harness_record': harness, 'model_sha256': cfg['model_sha256'],
        'models': [matrix.fingerprint(Path(cfg['models']) / name) for name in ('depth_backbone.onnx', 'student.onnx')],
        'worker_interpreters': {'simulator': '/opt/php/bin/train-python', 'inference': '/opt/php/bin/inference-python'}}
for model in plan['models']:
    assert model['sha256'] == host['source_before']['models'][Path(model['path']).name]['sha256']
selection = {'reference_commands': reference, 'mesh': cfg['mesh'], 'mesh_sha256': cfg['mesh_sha256'],
             'launch': host['native']['argv'][3:]}
inputs = {'scope': 'Post-run validator inputs reconstructed from actual frozen pilot receipts; not a pre-launch batch plan',
          'plan': plan, 'selection': selection, 'host_receipt': matrix.fingerprint('/host-launch.json')}
(checks / 'validation-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
result = matrix.validate_result(base / 'result.json', plan, selection)
decodes = []
for index, name in enumerate(result['videos']):
    argv = ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(base / name), '-f', 'null', '-']
    p = subprocess.run(argv, capture_output=True)
    (checks / f'decode-{index}.stdout.raw').write_bytes(p.stdout)
    (checks / f'decode-{index}.stderr.raw').write_bytes(p.stderr)
    decodes.append({'argv': argv, 'actual_returncode': p.returncode, 'original_video': matrix.fingerprint(base / name)})
    p.check_returncode()
runs, start = [], 0
for code, group in itertools.groupby(reference['codes']):
    length = len(list(group))
    runs.append({'start_frame': start, 'end_frame_exclusive': start + length, 'code': code})
    start += length
report = {'status': 'passed_actual_native_reference_execution_checks', 'frames': reference['frames'], 'fps': reference['fps'],
          'command_runs': runs, 'decodes': decodes, 'simulation': result['simulation'],
          'quality_verified': False, 'obstacle_course_completion_verified': False,
          'scope': 'Exact command delivery, physical policy execution, native recording, worker shutdown and video decoding; skill success unverified'}
(checks / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
