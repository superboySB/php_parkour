#!/usr/bin/env python3
"""Source-only future official-pair carrier; prepare and execute need separate reviews."""
from __future__ import annotations
import argparse
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from support import *
from admission import admission

def capture(argv,directory,label):
    with (directory/(label+'.stdout.raw')).open('xb') as out,(directory/(label+'.stderr.raw')).open('xb') as err:
        done=subprocess.run(argv,stdout=out,stderr=err)
    row={'argv':argv,'returncode':done.returncode,'stdout':fp(directory/(label+'.stdout.raw')),'stderr':fp(directory/(label+'.stderr.raw'))}
    write(directory/(label+'.json'),row)
    require(done.returncode==0,'Command failed; preserve partial: '+label)
    return (directory/(label+'.stdout.raw')).read_text()

def inspect(cid):
    done=subprocess.run(['docker','inspect','--type','container',cid],capture_output=True,text=True)
    require(done.returncode==0,'Cannot inspect exact own container')
    return json.loads(done.stdout)[0]

def verify_container(info,cid,spec,started=None):
    h=info['HostConfig']
    require(info['Id']==cid and info['Image']==IMAGE and info['Name']=='/'+spec['name']
      and info['Config']['Labels'].get('php.final-reference629.owner')==spec['token']
      and h['NetworkMode']=='none' and h['IpcMode']=='private' and not h.get('PidMode')
      and h['Init'] is True and h['Privileged'] is False and h['Runtime']=='runc'
      and not h.get('DeviceRequests') and h['Memory']==12884901888 and h['NanoCpus']==2000000000
      and sorted((m['Source'],m['Destination'],m['RW'],m['Type']) for m in info['Mounts'])
        ==sorted((str(s),d,rw,'bind') for s,d,rw in spec['mounts'])
      and len(info['Mounts'])==len(spec['mounts']),'Own CPU identity/isolation differs')
    if started:require(info['State']['StartedAt']==started,'CPU container restarted')

def cpu_job(base,kind,mode,target):
    """Caller owns signals/mutex; stop only this exact new CPU CID, even on IO failure."""
    import uuid
    target.mkdir(parents=True,exist_ok=False);token=uuid.uuid4().hex
    name='php-final-reference629-'+mode+'-'+token[:12]
    mounts=[(base/'source','/workspace/php_parkour',False),(base/'overlay','/workspace/php_parkour/scripts/research',False),
      (base/'inputs'/kind,'/data',False),(base/'control','/control',False),(target,'/preflight' if mode=='prepare' else '/validation',True)]
    if mode=='finalize':mounts.append((base/'runs'/kind/'outputs','/outputs',False))
    command=['/opt/php/bin/inference-python','-B','/control/cpu_prepare.py'] if mode=='prepare' else [
      '/opt/php/bin/inference-python','-B','/control/frozen/validate_scene_matrix.py','--plan','/outputs/reference629/plan.json',
      '--matrix','/outputs/reference629/matrix.json','--output','/validation/validation.json',
      '--matrix-module','/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py']
    argv=['docker','create','--name',name,'--label','php.final-reference629.owner='+token,'--runtime','runc','--network','none',
      '--ipc','private','--init','--shm-size','1g','--memory','12g','--cpus','2','--workdir','/workspace/php_parkour',
      '--entrypoint',command[0]]
    for key,value in {'CUDA_VISIBLE_DEVICES':'','NVIDIA_VISIBLE_DEVICES':'void','PHP_DOCKER':'1','PYTHONDONTWRITEBYTECODE':'1',
      'WANDB_MODE':'disabled','WANDB_DISABLED':'true','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'1',
      'MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MUJOCO_EGL_DEVICE_ID':'0'}.items():argv+=['--env',key+'='+value]
    for source,destination,rw in mounts:argv+=['--mount',f'type=bind,src={source},dst={destination}'+('' if rw else ',readonly')]
    argv += [IMAGE,*command[1:]];spec={'name':name,'token':token,'mounts':mounts};cid=None;started=None
    row={'status':'running','kind':kind,'mode':mode,'create_argv':argv,'errors':[],'cleanup_errors':[],'native_started':False,'gpu_started':False}
    try:
        # Capture CID before any diagnostic write, so all later IO failures still clean it.
        made=subprocess.run(argv,capture_output=True,text=True)
        if re.fullmatch('[0-9a-f]{64}',made.stdout.strip()):cid=made.stdout.strip();row['container_id']=cid
        row['create']={'returncode':made.returncode,'stdout_raw':made.stdout,'stderr_raw':made.stderr}
        require(cid is not None and made.returncode==0,'Own CPU create failed')
        verify_container(inspect(cid),cid,spec)
        write(target/'launch.json',row)
        capture(['docker','start',cid],target,'start');info=inspect(cid);verify_container(info,cid,spec)
        started=info['State']['StartedAt'];row['started_inspect']=info
        # The create command is the CPU job; docker wait records its actual exit.
        waited=capture(['docker','wait',cid],target,'wait');after=inspect(cid);verify_container(after,cid,spec,started)
        row['actual_container_exit_code']=int(waited.strip());row['final_inspect']=after
        require(row['actual_container_exit_code']==0 and after['State']['ExitCode']==0 and not after['State']['Running'],'Actual CPU job failed')
        # docker logs is evidence only, never a substitute for actual wait.
        capture(['docker','logs',cid],target,'container-logs')
        report_path=target/('summary.json' if mode=='prepare' else 'validation.json');report=read(report_path)
        require(report['status']=='passed','CPU science report failed')
        if mode=='prepare':require(report['configurations']==629 and report['scenarios']==17 and report['ort_cases']==30,'CPU preparation scope differs')
        else:require(report['preview'] is False and report['completion_verified'] is True and report['configurations']==629
          and report['scenarios']==17 and report['worker_exit0_empty_group_count']==1258 and report['full_decoded_mp4_count']==629,
          'CPU final must cover all629/1258/629 with no preview')
        row.update(status='passed',report=fp(report_path))
    except BaseException as error:
        row['errors'].append(f'{type(error).__name__}: {error}');row['status']='failed';raise
    finally:
        if cid:
            while True:
                try:
                    before=inspect(cid);verify_container(before,cid,spec,started)
                    if before['State']['Running']:
                        done=subprocess.run(['docker','stop','--time','20',cid],capture_output=True,text=True)
                        row.setdefault('cleanup_commands',[]).append({'argv':['docker','stop','--time','20',cid],'returncode':done.returncode,'stdout_raw':done.stdout,'stderr_raw':done.stderr})
                    after=inspect(cid);verify_container(after,cid,spec,started);require(not after['State']['Running'],'Own CPU not stopped')
                    row['owned_container_stop']={'container_id':cid,'before':before,'after':after,'running_after_stop':False};break
                except BaseException as error:
                    row['cleanup_errors'].append(str(error));row['status']='failed'
                    # Unknown ownership/stop must not release the outer GPU mutex.
                    time.sleep(2)
        write(target/'launch.json',row)
    require(row['status']=='passed','CPU cleanup failure');return row

def prepare(args,manifest):
    admitted=admission(args)
    if admitted['status']!='ready':return admitted
    base=safe(args.output,False);require(not base.exists(),'Fresh output only; no resume/retry/overwrite')
    # All actual admissions precede any cohort directory or CPU container creation.
    rows=source_rows()
    for row in rows:
        a=fp(OLD/row['relative']);require((a['bytes'],a['sha256'])==(row['bytes'],row['sha256']),'External canonical source changed')
    matrix=fp(OLD/'inputs/matrix.json');require(matrix['sha256']=='ed413845f4b82156964e11ad6ee3faca30e3c0b10dbfdc295a8284f9ee3308ed','Source geometry matrix differs')
    # 58 and reference629 use the same deployed robot/policy/SDK source, except
    # the explicitly reviewed three reference orchestration files.
    prior_base=Path(admitted['native58_base'])
    prior_geometry=fp(prior_base/'inputs/pure/matrix.json')
    require((prior_geometry['bytes'],prior_geometry['sha256'])==(matrix['bytes'],matrix['sha256']), 'Geometry differs from original58')
    for row in rows:
        relative=Path(row['relative']).relative_to('source')
        if relative.parts[:2]==('scripts','research') and relative.name in SOURCE_SHAS:continue
        before=fp(prior_base/'source'/relative)
        require((before['bytes'],before['sha256'])==(row['bytes'],row['sha256']), 'Reference snapshot differs from actual58 source: '+str(relative))
    base.mkdir();(base/'overlay').mkdir();(base/'inputs').mkdir();(base/'host').mkdir()
    # Exclusive partials remain on any failure; this command is never an automatic retry.
    for row in rows:
        destination=base/row['relative'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/row['relative'],destination)
        require(fp(destination)['sha256']==row['sha256'],'Source copy changed')
    shutil.copytree(HERE,base/'control')
    for name in SOURCE_SHAS:shutil.copyfile(HERE/'frozen'/name,base/'overlay'/name)
    pending=[];handlers={n:signal.signal(n,lambda signum,frame:pending.append(signum)) for n in (signal.SIGINT,signal.SIGTERM)}
    try:
        kinds={}
        for kind in KINDS:
            inputs=base/'inputs'/kind;(inputs/'assets/student').mkdir(parents=True);(inputs/'cache').mkdir()
            shutil.copyfile(matrix['path'],inputs/'matrix.json')
            for r in admitted['models']:
                if r['kind']==kind:
                    dst=inputs/'assets/student'/Path(r['path']).name;shutil.copyfile(r['path'],dst)
                    require((fp(dst)['bytes'],fp(dst)['sha256'])==(r['bytes'],r['sha256']),'Official pair copy changed')
            target=base/'host'/('cpu-'+kind);launch=cpu_job(base,kind,'prepare',target);summary=read(target/'summary.json');plan=read(target/'reference-plan.json')
            require(summary['pose']==admitted['poses'][kind],'Reference plan uses another native deployment pose')
            require(plan['model_sha256']=={Path(x['path']).name:x['sha256'] for x in admitted['models'] if x['kind']==kind},'Actual CPU plan used another model')
            kinds[kind]={'cpu_plan':fp(target/'reference-plan.json'),'native_plan_identity':plan['plan_sha256'],
              'cpu_summary':fp(target/'summary.json'),'cpu_launch':fp(target/'launch.json'),'reference_frames':summary['reference_frames']}
        require(not pending,'Operator signal during CPU preparation; preserve partial, do not execute')
        admitted_after=admission(args);require(admitted_after==admitted,'Actual fetch/58/review changed during CPU preparation')
        records=[]
        for group in ('source','overlay','inputs','control','host'):
            for path in sorted((base/group).rglob('*')):
                require(not path.is_symlink(),'Symlink in prepared tree')
                if path.is_file():r=fp(path);records.append({'relative':path.relative_to(base).as_posix(),'bytes':r['bytes'],'sha256':r['sha256']})
        write(base/'freeze-manifest.json',{'files':records});verify_tree(base,records)
        contract={'schema_version':1,'status':'prepared_for_separate_review','base':str(base),'preparation_manifest':manifest,
          'image_id':IMAGE,'gpu_uuid':GPU,'global_host_lock':str(LOCK),'kind_order':list(KINDS),'admission':admitted,
          'freeze_manifest':fp(base/'freeze-manifest.json'),'kinds':kinds,
          'expected':{'policies':2,'cases':1258,'workers':2516,'host_maps':2516,'full_decodes':1258},
          'native_started':False,'gpu_started':False,'quality_verified':False,'obstacle_course_completion_verified':False}
        contract['contract_identity']=identity(contract);write(base/'contract.json',contract)
        return {'status':'prepared_for_separate_review','contract':fp(base/'contract.json'),'native_started':False,'gpu_started':False}
    finally:
        for n,h in handlers.items():signal.signal(n,h)

def execute(args):
    require(args.root_authorized_start,'Separate explicit root authorization required')
    contract=verify_contract(args.contract,args.contract_sha256);base=Path(contract['base']);runs=base/'runs'
    require(not runs.exists(),'Never resume/overwrite a started attempt')
    safe(LOCK,False);lock=LOCK.open('a+');pending=[];handlers={}
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Signals remain deferred from acquisition through native+CPU cleanup and final input checks.
        for n in (signal.SIGINT,signal.SIGTERM):handlers[n]=signal.signal(n,lambda signum,frame:pending.append(signum))
        verify_contract(args.contract,args.contract_sha256);runs.mkdir();receipt={'status':'running','contract':fp(args.contract),'phases':[],
          'pending_signals':pending,'errors':[],'quality_verified':False,'obstacle_course_completion_verified':False}
        write(runs/'launch-receipt.json',receipt)
        native=load(HERE/'native_runner.py','official_reference_native_runner')
        try:
            for kind in KINDS:
                require(not pending,'Operator requested stop; no next kind is started')
                verify_contract(args.contract,args.contract_sha256)
                code=native.run_kind(contract,kind,lock.fileno(),args.contract_sha256)
                require(code==0,'Native reference629 failed; no retry or next kind')
                actual=read(runs/kind/'host/launch-receipt.json')
                require(actual['status']=='native_reference629_completed_worker1258_hostwriter1258'
                  and actual['native']['actual_wait_returncode']==actual['observer']['actual_wait_returncode']==0
                  and actual['owned_container_stop']['running_after_stop'] is False,'Native actual wait/host map/stop failed')
                post=cpu_job(base,kind,'finalize',runs/kind/'cpu-final')
                receipt['phases'].append({'kind':kind,'native':fp(runs/kind/'host/launch-receipt.json'),'cpu_final':fp(runs/kind/'cpu-final/validation.json'),
                  'cpu_launch':fp(runs/kind/'cpu-final/launch.json'),'cases':629,'workers':1258,'host_maps':1258,'full_decodes':629})
                write(runs/'launch-receipt.json',receipt)
            verify_contract(args.contract,args.contract_sha256);require(not pending,'Operator signal retained; no success claim')
            require([x['kind'] for x in receipt['phases']]==list(KINDS),'Ordered full official pair phases incomplete')
            receipt.update(status='completed',cases=1258,workers=2516,host_maps=2516,full_decodes=1258)
        except BaseException as error:
            receipt.update(status='failed');receipt['errors'].append(f'{type(error).__name__}: {error}');raise
        finally:write(runs/'launch-receipt.json',receipt)
        return receipt
    finally:
        # run_kind and cpu_job cannot return while their own container stop is unknown.
        lock.close()
        for n,h in handlers.items():signal.signal(n,h)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('status','prepare','execute'))
    p.add_argument('--preparation-sha256',required=True)
    for name in ('transfer','native58-base','native58-exit','native58-review','output','contract'):p.add_argument('--'+name,type=Path)
    for name in ('native58-exit-sha256','native58-review-sha256','contract-sha256'):p.add_argument('--'+name)
    p.add_argument('--root-authorized-start',action='store_true');args=p.parse_args();manifest=verify_preparation(args.preparation_sha256)
    if args.action=='status':answer=admission(args)
    elif args.action=='prepare':require(args.output is not None,'Explicit fresh output required');answer=prepare(args,manifest)
    else:require(args.contract is not None and args.contract_sha256,'Explicit separately reviewed actual contract required');answer=execute(args)
    print(json.dumps(answer,indent=2,allow_nan=False))

if __name__=='__main__':main()
