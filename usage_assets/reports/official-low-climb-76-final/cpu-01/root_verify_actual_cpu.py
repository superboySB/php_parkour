"""Read the actual CPU evidence only; no scientific phase is rerun."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import math

BASE = Path(__file__).resolve().parent
TRANSFER = BASE.with_name('teacher-low-climb-76-final-01')

def read(path):
    return json.loads(path.read_bytes())

def fp(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            digest.update(block)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}

def same_namespace(record):
    p = Path(record['path'])
    mapped = {'code': BASE / 'source', 'control': BASE / 'input', 'artifacts': TRANSFER / 'artifacts', 'validation': BASE / 'validation'}
    actual = fp(mapped[p.parts[1]] / Path(*p.parts[2:]))
    assert (actual['bytes'], actual['sha256']) == (record['bytes'], record['sha256'])

c = read(BASE / 'contract.json'); h = read(BASE / 'host/execution.json'); ph = read(BASE / 'validation/phases.json')
assert h['create_actual_returncode'] == h['actual_start_attached_wait_returncode'] == h['actual_container_exit_code'] == 0
assert not h['container_running'] and h['source_unchanged'] and h['source_before'] == h['source_after'] == c['source_files']
assert ph['status'] == 'passed' and ph['inputs_unchanged'] and ph['inputs_before'] == ph['inputs_after']
assert [v['phase'] for v in ph['phases']] == ['checkpoint', 'scalars', 'onnx', 'bind', 'plots']
assert [v['actual_wait_returncode'] for v in ph['phases']] == [0] * 5 and len(ph['inputs_before']) == 16
cid = h['container_id']; assert cid == '7e262db960de80cd447468a35ca44935e213ff115a2c744e457548d50d1b3f4a'
inspection_names = ['host/inspect-before.raw.json', 'root-launch-inspect.raw.json', 'host/inspect-after.raw.json', 'root-terminal-inspect.raw.json']
inspects = [read(BASE / n)[0] for n in inspection_names]
for i in inspects:
    assert i['Id'] == cid and i['Image'] == c['image'] and i['HostConfig']['Runtime'] == 'runc' and i['HostConfig']['NetworkMode'] == 'none'
    assert not i['HostConfig']['DeviceRequests'] and i['HostConfig']['NanoCpus'] == 2000000000 and i['HostConfig']['Memory'] == 12884901888
    assert 'CUDA_VISIBLE_DEVICES=' in i['Config']['Env'] and 'NVIDIA_VISIBLE_DEVICES=void' in i['Config']['Env']
    mounts = [{'source': v['Source'], 'destination': v['Destination'], 'read_only': not v['RW']} for v in i['Mounts']]
    assert len(mounts) == 4 and len({v['destination'] for v in mounts}) == 4
    assert sorted(mounts, key=lambda v: v['destination']) == sorted(c['mounts'], key=lambda v: v['destination'])
    assert not i['State']['OOMKilled']
assert not inspects[-1]['State']['Running'] and inspects[-1]['State']['ExitCode'] == 0 and 'owned_cleanup_stop_returncode' not in h
for record in ph['inputs_before']:
    same_namespace(record)
ck = read(BASE / 'validation/checkpoint.json'); sc = read(BASE / 'validation/scalars.json')
on = read(BASE / 'validation/onnx.json'); bi = read(BASE / 'validation/bind.json'); pl = read(BASE / 'validation/plots/plot-report.json')
for report in (ck, sc, bi):
    assert report['status'] == 'passed' and not report['quality_verified'] and not report['official_schedule_complete'] and not report['convergence_verified'] and not report['pt_onnx_numerical_parity_verified']
    same_namespace(report['source'])
assert ck['iteration'] == 19999 and ck['tensor_count'] == len(ck['tensor_inventory']) == 68 and ck['all_checkpoint_tensors_finite'] and not ck['cuda_initialized']
assert ck['normalizers'] == {'actor': None, 'critic': None}
assert [ck['contract'][k] for k in ('actor_observation_dim', 'critic_observation_dim', 'actions_dim')] == [449, 575, 29]
assert ck['contract']['num_envs'] == 4096 and ck['contract']['seed'] == 42 and ck['contract']['registry'] == 'file:///data/assets/motions-low-climb-76'
assert ck['baseline_config_binding']['full_config_equal'] and ck['baseline_config_binding']['contract'] == ck['contract']
for role, count in (('actor', 9), ('critic', 8)):
    updates = ck['baseline_to_final_updates'][role]
    assert len(updates['tensors']) == count and all(v['changed_elements'] > 0 and math.isfinite(v['max_absolute_delta']) and v['max_absolute_delta'] > 0 for v in updates['tensors'])
    assert updates['adam_baseline_unique_steps'] == [20] and updates['adam_final_unique_steps'] == [400000]
assert sc['stage'] == 'teacher-low-climb-76' and sc['samples_per_tag'] == 20000 and sc['first_step'] == 0 and sc['last_step'] == 19999
last = {}
for tag, rows in sc['scalars'].items():
    assert len(rows) == 20000 and [v['step'] for v in rows] == list(range(20000))
    assert all(math.isfinite(v['wall_time']) and math.isfinite(v['value']) for v in rows)
    last[tag] = rows[-1]['value']
assert len(last) == 4
assert on['status'] == 'passed' and on['self_contained'] and on['motion_frames'] == 2100096 and len(on['cases']) == 12 and on['expected_observation_dim'] == 449
assert [(v['name'], v['shape']) for v in on['inputs']] == [('obs', [1, 449]), ('time_step', [1, 1])]
assert all(math.isfinite(v['action_min']) and math.isfinite(v['action_max']) and 0 <= v['reference_index'] < on['motion_frames'] for v in on['cases'])
assert json.loads(on['metadata']['experiment_config']) == json.loads(ck['experiment_config_json'])
assert bi['teacher_onnx_cpu_cases'] == 12 and bi['full_config_equal_pt_onnx'] and bi['full_config_equal_pt_resolved_yaml'] and not bi['skills_verified']
assert ck['resolved_yaml_full_config_equal'] and ck['yaml_runtime_resolution']['raw_yaml_value'] == ['robot_action_dim'] and ck['yaml_runtime_resolution']['saved_pt_value'] == [29]
for record in bi['reports'] + bi['artifacts']:
    same_namespace(record)
assert pl['status'] == 'rendered_completed_fourth_teacher_curves' and not pl['quality_verified'] and not pl['convergence_verified'] and not pl['official_schedule_complete']
for record in [pl['input'], pl['plot_source'], *pl['figures']]:
    same_namespace(record)
report = {'verified_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'passed_root_actual_postexecution_verification',
    'actual_tool_terminal': {'session_id': 37710, 'launch_chunk_id': '20a9f9', 'terminal_chunk_id': '124fe1', 'exit_code': 0},
    'container_id': cid, 'actual_start_attached_wait_returncode': 0, 'actual_container_exit_code': 0, 'actual_five_phase_wait_returns': [0] * 5,
    'container_naturally_stopped': True, 'OOMKilled': False, 'runtime': 'runc', 'network': 'none', 'GPU_hidden': True, 'cpus': 2,
    'memory_bytes': 12884901888, 'actual_cgroup_memory_peak_bytes': ph['cgroup_memory_peak_bytes'],
    'actual_inputs_before_after_same': True, 'actual_input_record_count_including_sources': 16, 'actual_input_bodies_rehashed': True,
    'source_and_launcher_unchanged': True, 'checkpoint_tensor_count': 68, 'all_checkpoint_tensors_finite': True, 'iteration': 19999,
    'actor_critic_action_dims': [449, 575, 29], 'same_run_baseline_full_config_equal': True, 'baseline_already_optimized_not_untrained': True,
    'actor_critic_saved_Adam_steps': [20, 400000], 'four_tags_exact_20000_finite_samples': True, 'actual_scalar_last_values': last,
    'ONNX_CPU_cases': 12, 'reference_table_frames': 2100096, 'PT_ONNX_full_config_equal': True, 'YAML_sole_robot_action_dim_to29_resolution': True,
    'evidence_fingerprints': [fp(p) for p in sorted(BASE.rglob('*')) if p.is_file()],
    'numeric_PT_ONNX_parity_verified': False, 'convergence_verified': False, 'quality_verified': False,
    'official_schedule_complete': False, 'goal_status': 'active', 'must_fix': []}
out = BASE / 'root-postexecution-verification.json'
with out.open('x') as f:
    f.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'root_proof': fp(out), 'last_scalars': last, 'actual_CPU_phases': [0] * 5, 'quality_verified': False}))
