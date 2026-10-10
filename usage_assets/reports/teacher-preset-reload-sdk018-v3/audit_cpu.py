#!/usr/bin/env python3
"""Actual CPU-only independent native5 outputs/checkpoint/video/TB audit."""
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path('/workspace/php_parkour')
RESEARCH = Path('/outputs')
PREP = RESEARCH/'teacher-preset-reload-preparation-v3'
RUN = RESEARCH/'teacher-preset-reload-execution-v3-01'
sys.path.insert(0,str(ROOT))


def check(value,message):
    if not value: raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def artifact(path):
    path=Path(path)
    check(path.is_file() and not path.is_symlink(),'regular artifact required: '+str(path))
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def main():
    import torch
    import yaml
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from scripts.research.validate_teacher_presets import inspect_config
    plan=json.loads((PREP/'plan.json').read_text())
    execution=json.loads((RUN/'execution.json').read_text())
    check(execution['status']=='native_exits_zero_pending_evidence_validation' and len(execution['cases'])==5,'terminal five cases required')
    result={'schema_version':1,'status':'running','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'Independent CPU post-validation of original iteration1 nondefault teacher reloading; no convergence or raw clip coverage claim.',
        'plan_sha256':sha(PREP/'plan.json'),'execution_sha256':sha(RUN/'execution.json'),
        'physics_verified':False,'quality_verified':False,'cases':[]}
    try:
        immutable=[]
        for item in [*plan['source_closure'],*plan['preparation_helpers'],
                     *(i for c in plan['cases'] for i in c['inputs']),
                     *(i for a in plan['robot_assets'] for i in (a['source'],a['copy']))]:
            observed=artifact(item['native_path'])
            check(observed['sha256']==item['sha256'] and observed['bytes']==item['bytes'],'immutable input changed: '+item['native_path'])
            immutable.append(observed)
        result['immutable_inputs']=immutable
        for row,execution_row in zip(plan['cases'],execution['cases']):
            check(row['preset']==execution_row['preset'] and execution_row['returncode']==0 and execution_row['error'] is None,'native execution row differs')
            log=RUN/(row['preset']+'.log')
            check(sha(log)==execution_row['log_sha256'],'native raw log changed')
            check('Traceback (most recent call last):' not in log.read_text(errors='replace'),'native traceback despite exit0')
            output=Path(row['native_output']);quality=output/'quality.json';q=json.loads(quality.read_text())
            check(q['schema_version']==1 and q['status']=='completed' and q['quality_verified'] is False,'native quality scope/status differs')
            check(q['checkpoint']==row['checkpoint'] and q['checkpoint_sha256']==sha(row['checkpoint']) and q['checkpoint_iteration']==1,'wrong original PT')
            check(q['native_argv']==['--checkpoint',row['checkpoint'],*row['native_overrides']],'native argv changed')
            check(q['num_envs']==16 and q['control_steps']==100 and q['seed']==42 and q['control_dt_seconds']==.02
                  and q['sim_seconds_per_env']==2 and q['total_env_seconds']==32,'actual rollout size/timing differs')
            check(q['registry_order']==['file:///data/assets/motions-locomotion'],'actual registry differs')
            check(q['finite_actions'] is True and q['finite_root_states'] is True
                  and finite(q['max_abs_action']) and finite(q['minimum_root_height_m']),'nonfinite actual action/root evidence')
            names={'motion/error_ref_pos','motion/error_ref_rot','motion/error_body_pos','motion/error_joint_pos'}
            check(set(q['metrics'])==names,'four native metrics required')
            for metric in q['metrics'].values():
                check(metric['samples']==1600 and metric['finite'] is True and all(finite(metric[k]) for k in ('mean','p95','max')),'1600 finite actual samples required')
            check(q['failed_resets']==sum(q['failed_resets_by_env']) and q['timeout_resets']==sum(q['timeout_resets_by_env'])
                  and len(q['failed_resets_by_env'])==len(q['timeout_resets_by_env'])==16,'raw reset counts differ')
            saved=Path(q['saved_eval_config']);check(saved.is_relative_to(output) and sha(saved)==q['saved_eval_config_sha256'],'native saved config changed')
            cfg=yaml.safe_load(saved.read_text())
            check(cfg['training']['num_envs']==16 and cfg['training']['max_eval_steps']==100 and cfg['training']['seed']==42
                  and cfg['training']['export_onnx'] is False,'native saved training settings differ')
            kwargs=cfg['training']['preprocess_hook_kwargs']
            if isinstance(kwargs,str):kwargs=json.loads(kwargs)
            check(kwargs=={'add_onpath_obstacle':True,'num_variants':1,'obstacle_seed':42},'native geometry variant/seed differs')
            check(cfg['robot']['asset']['asset_root']==plan['runtime_robot_root']
                  and cfg['robot']['asset']['urdf_file']=='g1/main_mesh_arm_collision_halfspherehand.urdf','native robot asset root differs')
            loaded=torch.load(row['checkpoint'],map_location='cpu',weights_only=False)
            check(loaded['iter']==1,'actual PT iteration differs')
            state=loaded['actor_model_state_dict'];dim=state['actor_module.module.0.weight'].shape[1]
            check(all(torch.isfinite(v).all().item() for v in state.values()),'actual PT nonfinite')
            pt_contract=inspect_config(row['preset'],loaded['experiment_config'],dim)
            native_contract=inspect_config(row['preset'],cfg,dim)
            check(pt_contract==native_contract==row['contract'],'native obs/anchor/scaling changed')
            videos=[]
            declared={v['path']:v for v in q['videos']}
            check(declared,'fresh quality-linked video required')
            for video in sorted(output.rglob('*.mp4')):
                before=artifact(video)
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-show_entries','stream=width,height,nb_frames','-of','json',str(video)],capture_output=True,text=True,timeout=30)
                check(probe.returncode==0,'MP4 metadata unreadable: '+str(video))
                metadata=json.loads(probe.stdout);duration=float(metadata['format']['duration'])
                check(duration>0 and before['bytes']>0,'empty or zero-duration fresh MP4')
                command=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-threads','1','-i',str(video),'-f','null','-']
                decoded=subprocess.run(command,capture_output=True,text=True,timeout=120)
                check(decoded.returncode==0 and sha(video)==before['sha256'],'full immutable MP4 decode failed')
                if str(video) in declared:
                    check(declared[str(video)]['sha256']==before['sha256'] and abs(declared[str(video)]['duration_seconds']-duration)<1e-6,'quality video fingerprint differs')
                videos.append({**before,'duration_seconds':duration,'metadata':metadata,'quality_linked':str(video) in declared,
                               'decode_command':command,'decode_returncode':decoded.returncode,'decode_stderr':decoded.stderr,'full_decode':True})
            check(set(declared)<=set(v['path'] for v in videos),'declared fresh video missing')
            events=[]
            expected={'Evaluation/failed_resets':q['failed_resets'],'Evaluation/timeouts':q['timeout_resets'],
                      'Evaluation/control_steps':100,'Evaluation/sim_seconds_per_env':2,'Evaluation/clip_completions':q['clip_completions_excluding_failed_timeout_steps']}
            for key,metric in q['metrics'].items():
                for aggregate in ('mean','p95','max'):
                    expected['Evaluation/tracking_error/'+key.removeprefix('motion/')+'/'+aggregate]=metric[aggregate]
            check(q['tensorboard_events'],'actual quality TensorBoard event required')
            merged={}
            for name in q['tensorboard_events']:
                path=Path(name);check(path.is_relative_to(output),'TB event outside fresh target')
                before=artifact(path);acc=EventAccumulator(str(path),size_guidance={'scalars':0});acc.Reload()
                values={tag:[{'step':v.step,'value':v.value,'wall_time':v.wall_time} for v in acc.Scalars(tag)] for tag in acc.Tags()['scalars']}
                check(values and all(finite(v['value']) for rows in values.values() for v in rows),'empty/nonfinite TensorBoard scalars')
                check(sha(path)==before['sha256'],'TensorBoard changed during audit')
                merged.update(values);events.append({**before,'scalars':values})
            for key,value in expected.items():
                check(key in merged and merged[key][-1]['step']==100 and math.isclose(merged[key][-1]['value'],value,rel_tol=1e-6,abs_tol=1e-6),'TB/quality value mismatch: '+key)
            result['cases'].append({'preset':row['preset'],'status':'execution_evidence_verified','checkpoint':artifact(row['checkpoint']),
                'checkpoint_iteration':1,'saved_config':artifact(saved),'native_contract':native_contract,
                'num_envs':16,'control_steps':100,'num_variants':1,'seed':42,'sim_seconds_per_env':2,
                'wall_seconds':q['wall_seconds'],'metrics':q['metrics'],'finite_actions':True,'finite_root_states':True,
                'failed_resets':q['failed_resets'],'timeout_resets':q['timeout_resets'],
                'ended_episode_lengths_steps':q['ended_episode_lengths_steps'],
                'observed_clip_ids':q['observed_clip_ids'],'available_loader_ids':q['available_clip_count'],
                'loader_id_note':'Merged MotionLoader ID0 does not enumerate original source100 clips and proves no original-clip coverage.',
                'quality':artifact(quality),'log':artifact(log),'videos':videos,'tensorboard_events':events,
                'physics_verified':True,'quality_verified':False})
        check(not torch.cuda.is_initialized(),'CPU audit unexpectedly initialized CUDA')
        result.update(status='passed_execution_evidence',physics_verified=True,quality_verified=False,
            cuda_initialized=False,actual_checkpoint_count=5,actual_config_count=5,
            full_decoded_video_count=sum(len(c['videos']) for c in result['cases']),
            quality_linked_video_count=sum(sum(v['quality_linked'] for v in c['videos']) for c in result['cases']),
            tensorboard_event_count=sum(len(c['tensorboard_events']) for c in result['cases']),
            failed_resets_total=sum(c['failed_resets'] for c in result['cases']),
            timeout_resets_total=sum(c['timeout_resets'] for c in result['cases']))
    except BaseException as error:
        result.update(status='failed_postvalidation',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        Path('/audit/review.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
