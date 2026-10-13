"""Read actual public replay evidence without rerunning scientific phases."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import math

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
PUB = ROOT / 'usage_assets/reports/official-low-climb-76-final'
OLD = BASE.with_name('teacher-low-climb-76-final-cpu-01')
ORIGINAL = BASE.with_name('teacher-low-climb-76-final-01') / 'artifacts'

def read(path):
    return json.loads(path.read_bytes())

def fp(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8388608), b''):
            h.update(b)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': h.hexdigest()}

def exact(record, path):
    actual = fp(path)
    assert (record['bytes'], record['sha256']) == (actual['bytes'], actual['sha256']), str(path)

def native(record):
    p = Path(record['path'])
    m = {'code': PUB / 'cpu-01/source', 'control': PUB / 'cpu-01/input',
         'artifacts': BASE / 'artifacts', 'validation': BASE / 'validation'}
    exact(record, m[p.parts[1]] / Path(*p.parts[2:]))

h = read(BASE / 'host/execution.json')
p = read(BASE / 'validation/phases.json')
assert h['status'] == 'passed'
assert h['create_returncode'] == h['actual_attached_wait_returncode'] == h['actual_container_exit_code'] == 0
assert not h['container_running_after_cleanup'] and h['actual_phase_exits'] == [0] * 5
assert len(h['inputs_before']) == 11 and h['inputs_before'] == h['inputs_after']
assert p['status'] == 'passed' and p['inputs_unchanged'] and len(p['inputs_before']) == 16
assert p['inputs_before'] == p['inputs_after']
assert [x['phase'] for x in p['phases']] == ['checkpoint', 'scalars', 'onnx', 'bind', 'plots']
assert [x['actual_wait_returncode'] for x in p['phases']] == [0] * 5
for r in h['inputs_before']:
    exact(r, Path(r['host_path']))
for r in p['inputs_before']:
    native(r)
cid = h['container_id']
assert cid == '280eeadcff9ebe45cfb29db89f6210bd3ecc9ae8e205a2e289b1728fce561393'
mounts = [(str(PUB / 'cpu-01/source'), '/code', False),
          (str(PUB / 'cpu-01/input'), '/control', False),
          (str(BASE / 'artifacts'), '/artifacts', False),
          (str(BASE / 'validation'), '/validation', True)]
for name in ['host/inspect-before.json', 'host/inspect-after.json', 'root-terminal-inspect.raw.json']:
    i = read(BASE / name)
    if isinstance(i, list):
        assert len(i) == 1
        i = i[0]
    assert i['Id'] == cid and i['Image'] == 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
    c = i['HostConfig']
    assert c['Runtime'] == 'runc' and c['NetworkMode'] == 'none' and not c['DeviceRequests']
    assert c['NanoCpus'] == 2000000000 and c['Memory'] == 12884901888
    assert 'CUDA_VISIBLE_DEVICES=' in i['Config']['Env'] and 'NVIDIA_VISIBLE_DEVICES=void' in i['Config']['Env']
    assert sorted((v['Source'], v['Destination'], v['RW']) for v in i['Mounts']) == sorted(mounts)
    assert not i['State']['OOMKilled']
terminal = read(BASE / 'root-terminal-inspect.raw.json')[0]['State']
assert not terminal['Running'] and terminal['ExitCode'] == 0 and terminal['Status'] == 'exited'
restored = []
for artifact in sorted((BASE / 'artifacts').iterdir()):
    assert artifact.is_file() and not artifact.is_symlink()
    current = fp(artifact)
    exact(current, ORIGINAL / artifact.name)
    restored.append(current)
assert len(restored) == 5 and sum(x['bytes'] for x in restored) == 640979040
reports = {}
for name in ['checkpoint', 'scalars', 'onnx', 'bind']:
    a = read(BASE / 'validation' / (name + '.json'))
    b = read(OLD / 'validation' / (name + '.json'))
    allowed = set() if name == 'onnx' else {'started_utc', 'finished_utc'}
    if name == 'bind':
        allowed.add('reports')
        for r in a['reports'] + a['artifacts']:
            native(r)
    assert set(a) == set(b)
    assert {k: v for k, v in a.items() if k not in allowed} == {k: v for k, v in b.items() if k not in allowed}
    reports[name] = a
ck, sc, on = [reports[k] for k in ['checkpoint', 'scalars', 'onnx']]
assert ck['iteration'] == 19999 and ck['tensor_count'] == 68 and ck['all_checkpoint_tensors_finite']
assert [ck['contract'][k] for k in ['actor_observation_dim', 'critic_observation_dim', 'actions_dim']] == [449, 575, 29]
assert ck['baseline_config_binding']['full_config_equal'] and ck['resolved_yaml_full_config_equal']
assert len(sc['scalars']) == 4 and sc['samples_per_tag'] == 20000
for rows in sc['scalars'].values():
    assert [x['step'] for x in rows] == list(range(20000))
    assert all(math.isfinite(x['value']) and math.isfinite(x['wall_time']) for x in rows)
assert on['motion_frames'] == 2100096 and len(on['cases']) == 12
pl = read(BASE / 'validation/plots/plot-report.json')
oldpl = read(OLD / 'validation/plots/plot-report.json')
for r in [pl['input'], pl['plot_source'], *pl['figures']]:
    native(r)
for key in ['scope', 'training_status', 'smoothing', 'tags', 'backend', 'matplotlib']:
    assert pl[key] == oldpl[key]
png = (BASE / 'validation/plots/learning-curves.png').read_bytes()
assert png[:8] == b'\x89PNG\r\n\x1a\n' and [int.from_bytes(png[n:n+4], 'big') for n in [16, 20]] == [2160, 1392]
for report in [ck, sc, reports['bind'], pl]:
    assert not report['quality_verified'] and not report['official_schedule_complete'] and not report['convergence_verified']
report = {
    'schema_version': 1, 'status': 'passed_root_actual_public_replay_verification',
    'verified_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    'actual_tool_terminal': {'launch_chunk_id': '4c37a0', 'session_id': 36344, 'terminal_chunk_id': 'eea35f', 'exit_code': 0},
    'container_id': cid, 'actual_host_attach_wait': 0, 'actual_container_exit': 0,
    'actual_phase_waits': [0] * 5, 'naturally_stopped': True, 'OOMKilled': False,
    'started_at': terminal['StartedAt'], 'finished_at': terminal['FinishedAt'],
    'runtime': 'runc', 'network': 'none', 'GPU_hidden': True, 'three_RO_one_RW_mounts_exact': True,
    'cpus': 2, 'memory_bytes': 12884901888, 'actual_cgroup_memory_peak_bytes': p['cgroup_memory_peak_bytes'],
    'restored_actual_artifacts': restored, 'restored_five_artifact_bytes': 640979040,
    'host11inputs_and_phase16inputs_exact_original_and_current': True,
    'scientific_comparisons': {
        'checkpoint': 'All fields exact original except genuine timestamps',
        'scalars': 'All fields and 80,000 original sample values/walltimes exact except genuine report timestamps',
        'onnx': 'Whole report exact original,12 actual cases/T2100096',
        'bind': 'All scientific fields exact; current actual report SHA links independently rehashed',
        'plots': 'Current input/source/figure bindings exact, original smoothing same, actual PNG2160x1392'},
    'public_manifest': fp(PUB / 'evidence-manifest.json'),
    'evidence_fingerprints': [fp(x) for x in sorted(BASE.rglob('*')) if x.is_file() and 'artifacts' not in x.relative_to(BASE).parts],
    'quality_verified': False, 'convergence_verified': False, 'PT_ONNX_numeric_parity_verified': False,
    'official_schedule_complete': False, 'scientific_phases_rerun_for_verification': False, 'must_fix': []}
out = BASE / 'root-verification.json'
with out.open('x') as f:
    f.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'report': fp(out), 'container_id': cid, 'all_actual_phase_exits': [0]*5}))
