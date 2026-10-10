
import json,hashlib,math
from pathlib import Path
import numpy as np,yaml
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
q=json.loads(Path('/outputs/official-pilot-local-eval/quality.json').read_text())
p=Path(q['saved_eval_config']);cfg=yaml.safe_load(p.read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==q['saved_eval_config_sha256']
kwargs=json.loads(cfg['training']['preprocess_hook_kwargs']);assert kwargs['num_variants']==1 and kwargs['obstacle_seed']==42
assert cfg['training']['num_envs']==64 and cfg['logger']['video']['record_env_id']==0
mc=cfg['command']['setup_terms']['motion_command']['params']['motion_config']
motion=Path(mc['motion_file']);mesh=Path(cfg['terrain']['terrain_term']['obj_file_path'])
with np.load(motion) as d:
    ends=np.flatnonzero(d['motion_ends'])
    motion_info={'path':str(motion),'bytes':motion.stat().st_size,'sha256':hashlib.sha256(motion.read_bytes()).hexdigest(),'source_boundaries':len(ends),'first_end_frame':int(ends[0]),'expert_ids':np.unique(d['motion_idxs']).tolist()}
assert motion_info['source_boundaries']==100
records=[]
for v in q['videos']:
    f=Path(v['path']);assert hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256'];records.append({'path':str(f),'bytes':f.stat().st_size,'sha256':v['sha256'],'duration_seconds':v['duration_seconds']})
assert len(records)==64
expected={'Evaluation/failed_resets':q['failed_resets'],'Evaluation/timeouts':q['timeout_resets'],'Evaluation/control_steps':q['control_steps'],'Evaluation/sim_seconds_per_env':q['sim_seconds_per_env'],'Evaluation/clip_completions':q['clip_completions_excluding_failed_timeout_steps']}
for key,v in q['metrics'].items():
    assert v['samples']==16000 and v['finite']
    for stat in ['mean','p95','max']:expected['Evaluation/tracking_error/'+key.split('/')[-1]+'/'+stat]=v[stat]
events=[]
for event in q['tensorboard_events']:
    ea=EventAccumulator(event);ea.Reload();tags=ea.Tags()['scalars'];assert len(tags)==17
    scalars={tag:[{'step':e.step,'value':e.value,'wall_time':e.wall_time} for e in ea.Scalars(tag)] for tag in tags}
    for tag,wanted in expected.items():
        assert len(scalars[tag])==1 and scalars[tag][0]['step']==250
        assert math.isclose(scalars[tag][0]['value'],wanted,rel_tol=1e-6,abs_tol=1e-6),tag
    events.append({'path':event,'sha256':hashlib.sha256(Path(event).read_bytes()).hexdigest(),'scalars':scalars})
report={'status':'passed','scope':'CPU inspection after actual local Isaac evaluation; no independent replay or policy convergence claim','num_envs':cfg['training']['num_envs'],'preprocess_kwargs':kwargs,'saved_config_sha256':q['saved_eval_config_sha256'],'record_env_id':cfg['logger']['video']['record_env_id'],'motion':motion_info,'mesh':{'path':str(mesh),'bytes':mesh.stat().st_size,'sha256':hashlib.sha256(mesh.read_bytes()).hexdigest()},'videos':records,'tensorboard':events,'all_four_metrics_16000_finite_samples':True,'quality_verified':False}
print(json.dumps(report,indent=2))
