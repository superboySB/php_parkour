"""Read actual fetch, native58 parent wait, CPU/pose and independent review; no writes."""
from __future__ import annotations
import math
from pathlib import Path
from support import *

def admission(args):
    required=('transfer','native58_base','native58_exit','native58_exit_sha256','native58_review','native58_review_sha256')
    missing=[name for name in required if not getattr(args,name,None)]
    if missing:return {'status':'waiting','missing_explicit_prerequisites':missing,'native_started':False,'gpu_started':False}
    paths=[safe(getattr(args,name),False) for name in ('transfer','native58_base','native58_exit','native58_review')]
    if any(not x.exists() for x in paths):return {'status':'waiting','missing_actual_paths':[str(x) for x in paths if not x.exists()], 'native_started':False,'gpu_started':False}
    common=load(HERE/'frozen/common.py','final629_transfer_gate')
    origin=common.transfer(WORKSPACE,paths[0])
    if origin['status']!='ready':return origin
    base=paths[1];bound=list(origin['origin_files'])
    def actual(path):
        record=fp(path);bound.append(record);return read(path)
    plan=actual(base/'host-plan.json')
    require(plan['plan_sha256']==identity({k:v for k,v in plan.items() if k!='plan_sha256'})
      and plan['output']==str(base) and plan['image_id']==IMAGE and plan['gpu_uuid']==GPU
      and plan['origin_transfer']==origin and plan['expected_counts']=={'policies':2,'cases':58,'worker_exit0_empty_groups':116,'exact_host_maps':116,'full_mp4_decodes':58,'cpu_ort_cases':60},'Actual58 plan/source/model identity differs')
    freeze=actual(base/'freeze-manifest.json');require(fp(base/'freeze-manifest.json')['sha256']==plan['freeze_manifest_sha256'],'Actual58 frozen manifest differs')
    for item in freeze['files']:
        rel=Path(item['relative']);require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe58 freeze path')
        a=fp(base/rel);require((a['bytes'],a['sha256'])==(item['bytes'],item['sha256']),'58 input/control/CPU receipt changed')
        bound.append(a)
    # A completed JSON alone cannot establish the host's actual child wait.
    exit_file=paths[2];require(fp(exit_file)['sha256']==args.native58_exit_sha256,'Actual58 parent wait SHA differs')
    exited=actual(exit_file)
    expected_argv=['/usr/bin/python3',str(base/'control/native58.py'),'run','--workspace',str(WORKSPACE),'--plan',str(base/'host-plan.json'),'--root-authorized-start']
    require(exited['argv']==expected_argv and type(exited['returncode']) is int and exited['returncode']==0
      and exited['remaining_session_members']==[] and 'finished_utc' in exited
      and not any(k in exited for k in ('error','cleanup_error','source_verification_error','session_diagnostic_error'))
      and exited['source_sha256']==exited['source_sha256_after'],'Missing actual frozen native58 run child wait0/session cleanup')
    ident=exited['child_identity'];require(ident['pid']==ident['pgid']==ident['sid'] and ident['start_time_clock_ticks']>0,'Actual58 child session/birth absent')
    expected_controls={'native58.py':'31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43',
      'common.py':'bef9e7af9a67c9d10360145de7f6715cb167a8722fccb1e44aaaf4c7118371b2'}
    for name,digest in expected_controls.items():
        require(fp(base/'control'/name)['sha256']==digest and digest in exited['source_sha256'].values(), 'Actual58 parent/control source is not the reviewed one')
    for suffix,key in (('.stdout.log','stdout_sha256'),('.stderr.log','stderr_sha256')):
        f=exit_file.with_suffix(suffix);r=fp(f);bound.append(r);require(r['sha256']==exited[key],'Actual58 parent log changed')
    result=actual(base/'host/launch-receipt.json')
    require(result['status']=='completed' and result['plan_sha256']==plan['plan_sha256']
      and result['cases']==58 and result['worker_exit0_empty_groups']==116
      and result['exact_host_maps']==116 and result['full_decoded_mp4_count']==58
      and result['quality_verified'] is False,'Actual58 terminal counters differ')
    require([x['id'] for x in result['phases']]==[x['id'] for x in plan['phases']],'Actual58 ordered phases differ')
    for stage,expected in zip(result['phases'],plan['phases']):
        require(stage['status']=='completed' and all(type(stage[k]) is int and stage[k]==0 for k in ('driver_returncode','observer_returncode','driver_returncode_after_stop'))
          and stage['owned_gpu_container_stop']['running_after_stop'] is False
          and stage['worker_exit0_empty_groups']==2*expected['cases'] and len(stage['host_maps'])==2*expected['cases']
          and stage['full_decoded_mp4_count']==expected['cases'],'Actual58 phase/direct exit/maps/decode/stop failed')
        post_path=base/'phases'/stage['id']/'cpu-final/summary.json';require(fp(post_path)==stage['cpu_final'],'Actual58 CPU final SHA/path differs')
        post=actual(post_path);require(post['status']=='passed' and post['case_count']==expected['cases']
          and post['worker_exit0_empty_groups']==2*expected['cases'] and post['full_decoded_mp4_count']==expected['cases'],'Actual58 CPU full decode counts differ')
        require(len(post['cases'])==expected['cases'],'Actual58 CPU case rows missing')
        for case in post['cases']:
            require(case['worker_exit0_empty_groups']==2 and case['quality_verified'] is False and len(case['video_full_decodes'])==1,'Actual58 per-case CPU gate differs')
            for r in case['files']:
                native_path=Path(r['path']);require(native_path.is_absolute() and '..' not in native_path.parts,'Unsafe58 native evidence path')
                host_path=base/'phases'/stage['id']/'outputs'/native_path.relative_to('/outputs')
                a=fp(host_path);require((a['bytes'],a['sha256'])==(r['bytes'],r['sha256']),'Actual58 retained evidence changed');bound.append(a)
        for m in stage['host_maps']:
            require(m['phase']==stage['id'] and m['role'] in ('simulator','inference')
              and m['mapping']['nspid']==[m['mapping']['host_tid'],m['mapping']['container_tid']], 'Actual58 host namespace mapping differs')
    poses={}
    for kind in KINDS:
        where=base/'host'/('cpu-'+kind);cpu=actual(where/'launch.json');summary=actual(where/'summary.json');onnx=actual(where/'onnx.json')
        require(cpu['status']=='passed' and cpu['mode']=='prepare' and cpu['kind']==kind and cpu['returncode']==cpu['container_exit_code']==0
          and cpu['owned_container_stop']['running_after_stop'] is False,'Original58 actual CPU0/stopped receipt missing')
        require(summary['status']=='passed' and summary['ort_cases']==30 and summary['directions_cases']==12
          and summary['scene_cases']==17 and summary['image_id']==IMAGE
          and summary['source_sha256']=='855d56494c662cbfcd19a96043b6f0baaa49a093f52c47b46a9005657e46bb0f'
          and onnx['status']=='passed' and len(onnx['cases'])==30,'Actual58 60ORT/source/image gate failed')
        pairs={Path(x['path']).name:(x['bytes'],x['sha256']) for x in origin['models'] if x['kind']==kind}
        require({Path(x['path']).name:(x['bytes'],x['sha256']) for x in onnx['models']}==pairs,'Actual58 ORT used another pair')
        for name,(size,sha) in pairs.items():
            a=fp(base/'inputs'/kind/'assets/student'/name);bound.append(a);require((a['bytes'],a['sha256'])==(size,sha),'Actual58 native model differs')
        pose=onnx['native_default_pose_compatibility'];require(pose['status']=='passed' and len(pose['native_joint_names'])==29
          and math.isfinite(pose['max_default_pose_absolute_error']) and pose['max_default_pose_absolute_error']<=.000501,'Original58 deployment pose mismatch')
        poses[kind]=pose
    # Future root/independent review has an explicit small schema; no invented future path/hash.
    review_file=paths[3];require(fp(review_file)['sha256']==args.native58_review_sha256,'Independent58 review is not the explicitly reviewed SHA')
    review=actual(review_file)
    require(review['status']=='passed_readonly_native58_postexecution_review' and review['must_fix']==[]
      and review['native58_plan_sha256']==plan['plan_sha256'] and review['actual_parent_wait']==fp(exit_file)
      and review['image_id']==IMAGE and review['models']==origin['models'] and review['poses']==poses,
      'Independent58 postexecution admission is missing or refers to other inputs')
    fingerprints=review['evidence_fingerprints']
    for key in ('host/launch-receipt.json','host/cpu-pure/onnx.json','host/cpu-finetune/onnx.json',*[f'phases/{x["id"]}/cpu-final/summary.json' for x in plan['phases']]):
        require(fp(base/key) in fingerprints,'Independent58 review omits critical actual evidence')
    for r in fingerprints:check(r)
    bound.extend(fingerprints)
    unique={r['path']:r for r in bound}
    require(len(unique)<=len(bound),'Invalid admission records')
    return {'status':'ready','transfer':origin,'models':origin['models'],'poses':poses,'native58_base':str(base),
      'native58_plan_sha256':plan['plan_sha256'],'actual_parent_wait':fp(exit_file),'independent_review':fp(review_file),
      'bound_files':list(unique.values()),'native_started':False,'gpu_started':False,'quality_verified':False}
