"""Read-only post-run science checks in an isolated runc/noGPU container."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
import numpy as np
import torch
import yaml
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

sys.path.insert(0, '/workspace/php_parkour')
from scripts.research.eval_source_coverage import verify_plan, validate_cpu_report, validate_native_report
from scripts.research.runtime_robot_assets import verify as verify_robot_assets


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fp(path):
    p = Path(path)
    return {'path': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size}


def require(ok, label):
    if not ok:
        raise ValueError(label)


plan_path = Path('/outputs/teacher/plan.json')
plan = verify_plan(plan_path)
require(plan['selected_sources'] == 1 and plan['policy'] == 'teacher', 'Expected one exact teacher source')
case = json.loads(Path(plan['cases'][0]['case']['path']).read_text())
base = Path(case['output'])
cpu = json.loads((base / 'cpu-preflight/report.json').read_text())
validate_cpu_report(cpu, case)
q = json.loads((base / 'quality.json').read_text())
validate_native_report(q, case)
summary = json.loads((plan_path.parent / 'native-first-attempt-summary.json').read_text())
require(summary['status'] == 'completed' and summary['execution_passed'] == 1 and summary['execution_failed'] == 0, 'Native first attempt driver failed')
require(q['checkpoint']['sha256'] == case['checkpoint_sha256'] == 'd38d7c626fab4750e40eacfc05bc8178a56141055a569f9abca9f71c7584e87a', 'Original iter500 checkpoint changed')
checkpoint = torch.load(case['checkpoint'], map_location='cpu', weights_only=False)
require(checkpoint['iter'] == checkpoint['iteration'] == q['checkpoint_iteration'] == 500, 'Actual checkpoint iteration differs')
state = checkpoint['actor_model_state_dict']
require(tuple(state['actor_module.module.0.weight'].shape) == (512, 449), 'Expected original449 actor')
require(all(torch.isfinite(v).all().item() for v in state.values() if torch.is_tensor(v) and v.is_floating_point()), 'Nonfinite PT actor')
require(q['status'] == 'completed' and q['quality_verified'] is False and q['finite_actions'] and q['finite_root_states'], 'Native report/finite contract failed')
require(case['max_steps'] == case['source']['frames'] == q['actual_native']['frames'] == 920, 'Original source920frames/cap changed')
require(q['actual_native']['boundary_indices_inclusive'] == [919] and q['actual_native']['native_expert_ids'] == [0], 'Native singleton boundary/expert identity changed')
require(q['seed'] == 42 and q['actual_native']['num_envs'] == 1 and q['actual_native']['actual_preprocess_hook_kwargs'] == {'add_onpath_obstacle': True, 'num_variants': 1, 'obstacle_seed': 42}, 'Actual eval1env/1variant/seed42 changed')
actual = q['actual_native']
require(actual['source_table_verification']['status'] == 'matched_selected_source', 'Actual reference table not matched to full source')
require(math.isclose(actual['control_dt_seconds'], .02, abs_tol=1e-12) and actual['source_fps'] == 50, 'Source/control clock differs')
config_path = Path(actual['saved_eval_config']['retained']['path'])
config = yaml.safe_load(config_path.read_text())
require(config['training']['num_envs'] == 1 and config['training']['seed'] == 42 and config['training']['max_eval_steps'] == 920 and config['training']['export_onnx'] is False, 'Saved native eval training overrides differ')
require(config['robot']['asset']['asset_root'] == case['runtime_robot_assets']['runtime_root'] and config['robot']['asset']['urdf_file'] == 'g1/main_mesh_arm_collision_halfspherehand.urdf', 'Saved eval asset path differs')
verify_robot_assets(case['runtime_robot_assets'])
require(len(case['runtime_robot_assets']['files']) == 35, 'Expected35 immutable original asset files')
asset_root = Path(case['runtime_robot_assets']['runtime_root'])
original = {r['relative_path'] for r in case['runtime_robot_assets']['files']}
generated = [p for p in sorted(asset_root.rglob('*')) if p.is_file() and p.relative_to(asset_root).as_posix() not in original]
require(any(p.suffix.lower() in ('.usd', '.usda', '.usdc') for p in generated), 'No actual convertedUSD cache in independentRW asset root')
trajectory = [json.loads(line) for line in Path(q['trajectory']['path']).read_text().splitlines()]
policy = [r for r in trajectory if r['phase'] == 'policy']
init = [r for r in trajectory if r['phase'] == 'initialization_warmup']
warmup = [r for r in trajectory if r['phase'] == 'attempt_warmup']
require(len(init) == len(warmup) == 1 and len(policy) == q['control_steps'] > 0, 'Actual warmups/policy steps missing')
require(init[0]['reference_frame'] == warmup[0]['reference_frame'] == 0 and init[0]['post_reference_frame'] == warmup[0]['post_reference_frame'] == 1, 'Native warmup clocks changed')
require([r['reference_frame'] for r in policy] == list(range(1, len(policy) + 1)), 'Actual policy frames not contiguous from1')
require(all(r['finite_action'] and r['finite_root_state'] and r['finite_metrics'] and np.isfinite(r['actions']).all() for r in trajectory), 'Nonfinite actual trajectory')
require(q['policy_reference_frames_contiguous_from_one'] and q['expected_policy_interval_inclusive'] == [1,918], 'Actionable reference interval changed')
require(q['failed_resets'] == sum(r['failed'] for r in policy + warmup) and q['timeout_resets'] == sum(r['timeout'] for r in policy + warmup), 'Termination counts not matched to first attempt rows')
for key, metric in q['metrics'].items():
    values = np.array([r['metrics'][key] for r in policy], dtype=np.float64)
    require(metric['samples'] == len(values) and metric['finite'] is True and np.isfinite(values).all(), 'Tracking samples not all finite')
    require(math.isclose(metric['mean'], float(values.mean()), abs_tol=1e-12) and math.isclose(metric['max'], float(values.max()), abs_tol=1e-12) and math.isclose(metric['p95'], float(np.percentile(values,95)), abs_tol=1e-12), 'Raw tracking metric summary mismatch')
cache = q['warmup_cache_repair']
require(cache['enabled'] and len(cache['events']) == 2, 'Expected two exact eval-only cache refreshes')
for event in cache['events']:
    require(event['clock_unchanged'] and event['rng_unchanged'] and event['clock_before'] == event['clock_after'] and event['rng_sha256_before'] == event['rng_sha256_after'], 'Cache repair changed clock/RNG')
    require(event['formula']['formula_ast_sha256'] == '155892b6ef1326d34b9bed8adcee2320681efc38df55dcb03b955088cca864ea', 'Original native formula changed')
    require(event['clock_before']['time_steps'] == [0] and event['clock_before']['motion_ids'] == [0], 'Warmup initial identity differs')
    for group in ['cache_before','cache_after']:
        require(all(np.isfinite(value).all() for value in event[group].values()), 'Nonfinite relative cache')
videos=[]
for p in sorted(base.rglob('*.mp4')):
    raw=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,nb_frames','-of','json',str(p)],text=True,timeout=30)
    meta=json.loads(raw);duration=float(meta['format']['duration']);require(duration>0,'Empty video')
    decoded=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(p),'-f','null','-'],capture_output=True,text=True,timeout=90)
    require(decoded.returncode==0 and not decoded.stderr.strip(),'Native MP4 full decode failed')
    videos.append({**fp(p),'duration_seconds':duration,'streams':meta['streams'],'full_decode_returncode':decoded.returncode,'quality_linked':str(p) in {v['path'] for v in q['videos']}})
require(videos,'No fresh native video')
events=[]
for p in sorted(base.rglob('events.out.tfevents.*')):
    accumulator=EventAccumulator(str(p));accumulator.Reload();values={}
    for tag in accumulator.Tags()['scalars']:
        vals=[float(e.value) for e in accumulator.Scalars(tag)];require(all(math.isfinite(v) for v in vals),'NonfiniteTB scalar');values[tag]={'samples':len(vals),'last':vals[-1]}
    events.append({**fp(p),'scalar_tags':values})
require(events and any(e['scalar_tags'] for e in events),'No actual readable finiteTensorBoard scalar')
report={'schema_version':1,'status':'execution_evidence_verified_skill_failed' if not q['first_attempt_reference_boundary_reached'] else 'execution_evidence_verified_reference_boundary_reached',
        'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'One original locomotion source/iter500 teacher; independentCPU post-validation, not full296/888 or convergence.','simulation_started_by_auditor':False,'quality_verified':False,
        'plan':fp(plan_path),'quality':fp(base/'quality.json'),'trajectory':fp(Path(q['trajectory']['path'])),'checkpoint':q['checkpoint'],'checkpoint_iteration':500,
        'case_id':case['case_id'],'source':case['source'],'harness_sources':case['harness_sources'],'runtime_robot_assets':case['runtime_robot_assets'],
        'actual_saved_config':fp(config_path),'actual_num_envs':1,'actual_num_variants':1,'seed':42,'source_frames':920,'max_steps':920,'actual_boundary_indices_inclusive':[919],
        'control_steps':len(policy),'policy_sim_seconds':q['policy_sim_seconds'],'stop_reason':q['stop_reason'],'failed_resets':q['failed_resets'],'timeout_resets':q['timeout_resets'],
        'first_attempt_reference_boundary_reached':q['first_attempt_reference_boundary_reached'],'policy_reference_frames':q['policy_reference_frames'],
        'finite_actions':q['finite_actions'],'finite_root_states':q['finite_root_states'],'metrics':q['metrics'],'warmup_cache_repair_events':2,'cache_clock_rng_unchanged':True,
        'generated_runtime_asset_files':[fp(p) for p in generated],'native_videos':videos,'tensorboard_events':events,
        'limits':['Native termination/quality result remains unchanged. A completed execution is not a completed source clip.','Frame0 native warmup and final919boundary sentinel are separate from policy-controlled frames1..918.','Public native source remains original/full920frames, expert0 external and local; no original whole296coverage claim.']}
Path('/audit/review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({key:report[key] for key in ['status','case_id','control_steps','policy_sim_seconds','stop_reason','failed_resets','quality_verified']}))
