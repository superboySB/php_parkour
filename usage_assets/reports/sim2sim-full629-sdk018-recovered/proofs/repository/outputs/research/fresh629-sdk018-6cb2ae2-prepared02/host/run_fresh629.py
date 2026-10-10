#!/usr/bin/env python3
"""Explicitly authorized fresh629 host supervisor; no resume or old-container use."""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from prepare_fresh629 import IMAGE,UUID,sha,identity,write


def call(argv,timeout=60):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise RuntimeError(f'{argv[0]} failed {result.returncode}: {result.stderr}')
    return result.stdout


def inspect(cid):return json.loads(call(['docker','inspect','--type','container',cid]))[0]


def verify_snapshot(base,plan):
    original=dict(plan);recorded=original.pop('plan_sha256')
    if identity(original)!=recorded or plan['output']!=str(base.resolve()) or plan['image_id']!=IMAGE or plan['gpu_uuid']!=UUID:
        raise ValueError('Frozen host identity/path/image/UUID differs')
    if sha(base/'freeze-manifest.json')!=plan['freeze_manifest_sha256']:raise ValueError('Frozen manifest changed')
    manifest=json.loads((base/'freeze-manifest.json').read_text())
    for item in manifest['files']:
        path=base/item['relative']
        if (not path.resolve().is_relative_to(base.resolve()) or not path.is_file() or path.is_symlink()
                or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']):raise ValueError('Frozen source/input/helper changed: '+item['relative'])
    if sha(base/'inputs/native-plan.json')!=plan['native_plan_file_sha256']:raise ValueError('CPU native plan changed')
    if sha(base/'host/cpu-preflight/launch.json')!=plan['cpu_preflight_receipt_sha256']:raise ValueError('CPU-preflight receipt changed')
    preflight=json.loads((base/'host/cpu-preflight/launch.json').read_text())
    if preflight['status']!='passed' or preflight['owned_container_running_after_stop'] or len(preflight['commands'])!=3 or any(c['returncode']!=0 for c in preflight['commands']):raise ValueError('Actual CPU-preflight receipt not passed')
    return len(manifest['files'])


def local_docker():
    context=call(['docker','context','show']).strip();settings=json.loads(call(['docker','context','inspect',context]))[0]
    endpoint=os.environ.get('DOCKER_HOST') or settings['Endpoints']['docker']['Host']
    if not endpoint.startswith('unix://'):raise ValueError('Local host/proc requires Unix Docker endpoint')
    return {'context':context,'endpoint':endpoint}


def gpu_idle():
    uuids=call(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader']).splitlines()
    if uuids.count(UUID)!=1:raise ValueError('Physical GPU UUID not uniquely present')
    apps=call(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'])
    if any(line.split(',')[0].strip()==UUID for line in apps.splitlines() if line.strip()):raise ValueError('Foreign compute job present; never stop it')
    return {'uuid':UUID,'existing_compute_processes':[]}


def mounts(base,gpu=True):
    selected=[(base/'source','/workspace/php_parkour',True),(base/'inputs','/data',True),(base/'control','/control',True)]
    if gpu:selected += [(base/'outputs','/outputs',False),(base/'cache','/data/cache',False)]
    else:selected += [(base/'outputs','/outputs',True),(base/'host/final-validation','/validation',False)]
    return selected


def create_args(base,plan,gpu=True):
    name=plan['container_name'] if gpu else plan['container_name']+'-cpu-final'
    argv=['docker','create','--name',name,'--network','none','--ipc','private','--init','--shm-size','8g' if gpu else '1g',
          '--workdir','/workspace/php_parkour','--entrypoint','/bin/bash']
    if gpu:argv += ['--gpus','device='+UUID]
    else:argv += ['--runtime','runc','--env','CUDA_VISIBLE_DEVICES=','--env','NVIDIA_VISIBLE_DEVICES=void']
    environment={'PHP_DOCKER':'1','WANDB_MODE':'disabled','WANDB_DISABLED':'true','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
                 'TRANSFORMERS_OFFLINE':'1','PYTHONDONTWRITEBYTECODE':'1','MUJOCO_EGL_DEVICE_ID':'0'}
    if gpu:environment['NVIDIA_DRIVER_CAPABILITIES']='compute,utility,graphics'
    for key,value in environment.items():argv += ['--env',key+'='+value]
    for source,dest,ro in mounts(base,gpu):argv += ['--mount',f'type=bind,src={source},dst={dest}'+(',readonly' if ro else '')]
    return argv+[IMAGE,'-lc','exec sleep infinity']


def verify_container(info,cid,base,plan,gpu):
    host=info['HostConfig'];requests=host.get('DeviceRequests') or []
    expected_name=plan['container_name'] if gpu else plan['container_name']+'-cpu-final'
    actual=sorted((m['Source'],m['Destination'],not m['RW'],m['Type']) for m in info['Mounts'])
    expected=sorted((str(src),dst,ro,'bind') for src,dst,ro in mounts(base,gpu))
    if (info['Id']!=cid or info['Image']!=IMAGE or info['Name']!='/'+expected_name
            or host['NetworkMode']!='none' or host['IpcMode']!='private' or host.get('PidMode','') or host['Privileged']
            or not host.get('Init') or host['ShmSize']!=(8589934592 if gpu else 1073741824)
            or info['Config']['WorkingDir']!='/workspace/php_parkour' or actual!=expected):raise ValueError('Owned isolated container identity differs')
    if gpu:
        if len(requests)!=1 or requests[0].get('DeviceIDs')!=[UUID] or requests[0].get('Count')!=0:raise ValueError('One exact physical GPU UUID required')
    elif requests or host['Runtime']!='runc':raise ValueError('CPU finalizer must have no GPU request/runtime')


def stop_owned(cid,base,plan,gpu):
    verify_container(inspect(cid),cid,base,plan,gpu)
    call(['docker','stop','--time','20',cid],timeout=35)
    final=inspect(cid)
    if final['State']['Running']:raise RuntimeError('Owned container remains running')
    return {'container_id':cid,'running_after_stop':False,'state':final['State']}


def host_mappings(base,plan,cid):
    observed=json.loads((base/'host/observer/summary.json').read_text())
    inspected=json.loads((base/'host/container-inspect.json').read_text())
    if (observed['identity']['container_id']!=cid or inspected['Id']!=cid or observed['identity']['image_id']!=IMAGE
            or observed['identity']['started_at']!=inspected['State']['StartedAt']):raise ValueError('Observer fixed container/birth differs')
    if not observed['mapping_scope_complete'] or observed['errors'] or observed['stop_reason']!='stop_file':raise ValueError('Whole-run host observer incomplete')
    native=json.loads((base/'outputs/all-configs/matrix.json').read_text());expected=json.loads((base/'inputs/native-plan.json').read_text())
    if (native['status']!='completed' or native['completed_configurations']!=629 or len(native['selections'])!=629
            or native['plan_sha256']!=plan['native_plan_sha256']):raise ValueError('Complete629 native matrix required')
    index={}
    for mapping in observed['command_writer_mappings']:
        index.setdefault((mapping['worker_output'],mapping['role'],mapping['container_tgid'],mapping['owner_start_time_clock_ticks']),[]).append(mapping)
    result=[];seen_threads=set()
    for selection,case in zip(expected['selections'],native['selections']):
        if case['case_id']!=selection['case_id'] or len(case['attempts'])!=1 or case['attempts'][0]['returncode']!=0:raise ValueError('Fresh exact once-only native case differs')
        attempt=case['attempts'][0];directory=base/'outputs'/Path(attempt['output']).relative_to('/outputs')
        for role in ('simulator','inference'):
            path=directory/(role+'-process-start.json');entry=json.loads(path.read_text());process=entry['process']
            matches=index.get((attempt['output'],role,process['pid'],process['start_time_clock_ticks']),[])
            if len(matches)!=1:raise ValueError('Require one exact host writer mapping: '+case['case_id']+'/'+role)
            for mapping in matches:
                if (mapping['nspid'][0]!=mapping['host_tid'] or mapping['nspid'][-1]!=mapping['container_tid']
                        or mapping['nstgid'][0]!=mapping['host_tgid'] or mapping['nstgid'][-1]!=process['pid']):raise ValueError('Host thread namespace owner differs')
                thread=(mapping['host_tid'],mapping['start_time_clock_ticks'])
                if thread in seen_threads:raise ValueError('Host writer thread mapped to multiple workers')
                seen_threads.add(thread)
            result.append({'case_id':case['case_id'],'role':role,'entry_sha256':sha(path),'mappings':matches})
    if len(result)!=1258:raise ValueError('Require1258 native worker/thread mappings')
    return result


def execute(args):
    if not args.root_authorized_start:raise ValueError('Explicit root start authorization required; preparation never starts GPU')
    base=args.plan.resolve().parent;plan=json.loads(args.plan.read_text())
    count=verify_snapshot(base,plan)
    with Path(plan['global_host_lock']).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        target=base/'host/launch-receipt.json'
        if target.exists() or any((base/'outputs').iterdir()):raise ValueError('Fresh never-attempted cohort required; no resume/overwrite')
        receipt={'schema_version':1,'status':'starting','plan_sha256':plan['plan_sha256'],'started_unix':time.time(),
                 'endpoint':local_docker(),'gpu_preflight':gpu_idle(),'snapshot_files_verified':count,'native_started':False}
        if json.loads(call(['docker','image','inspect',IMAGE]))[0]['Id']!=IMAGE:raise ValueError('Fixed canonical image absent')
        cid=observer=job=None;stopfile=base/'host/observer-stop'
        write(target,receipt)
        try:
            argv=create_args(base,plan,True);receipt['create_argv']=argv;write(target,receipt)
            cid=call(argv).strip()
            if not re.fullmatch('[0-9a-f]{64}',cid):raise ValueError('Exact full new container ID required')
            receipt['container_id']=cid;write(target,receipt);call(['docker','start',cid])
            info=inspect(cid);verify_container(info,cid,base,plan,True);write(base/'host/container-inspect.json',info)
            receipt['gpu_before_native']=gpu_idle()
            observe=[sys.executable,str(base/'control/observe_container_pids.py'),'--container-id',cid,'--expected-image',IMAGE,
                     '--output',str(base/'host/observer'),'--stop-file',str(stopfile),'--interval','0.5',
                     '--max-seconds',str(plan['host_observer_timeout_seconds'])]
            receipt['observer_argv']=observe
            with (base/'host/observer.log').open('x') as log:
                observer=subprocess.Popen(observe,stdout=log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+15
                while not (base/'host/observer/launch.json').is_file():
                    if observer.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Host observer not ready')
                    time.sleep(.1)
                command=['docker','exec',cid,'/opt/php/bin/inference-python','/control/run_frozen_matrix.py',
                         '--expected-plan','/data/native-plan.json','--matrix-sha256',plan['matrix_source_sha256'],
                         '--helper-sha256',plan['control_wrapper_sha256'],'--',*plan['native_args']]
                receipt.update(status='running',native_started=True,native_start_unix=time.time(),native_argv=command);write(target,receipt)
                with (base/'host/driver.log').open('x') as output:
                    job=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT);receipt['docker_exec_host_pid']=job.pid;write(target,receipt)
                    receipt['driver_returncode']=job.wait(timeout=plan['host_driver_timeout_seconds'])
                receipt['native_finished_unix']=time.time();stopfile.touch(exist_ok=False)
                receipt['observer_returncode']=observer.wait(timeout=30)
            if receipt['driver_returncode'] or receipt['observer_returncode']:raise RuntimeError('Real native driver/observer did not exit0')
            receipt['host_native_mappings']=host_mappings(base,plan,cid)
            receipt['status']='native_completed'
        except BaseException as error:
            receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
        finally:
            if observer is not None and observer.poll() is None:
                stopfile.touch(exist_ok=True)
                with contextlib.suppress(subprocess.TimeoutExpired):receipt['observer_returncode']=observer.wait(timeout=30)
            if cid is not None:
                try:receipt['owned_gpu_container_stop']=stop_owned(cid,base,plan,True)
                except BaseException as error:receipt.update(status='failed',cleanup_error=f'{type(error).__name__}: {error}')
            if job is not None:
                try:receipt['driver_returncode_after_stop']=job.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    job.terminate()
                    try:receipt['driver_returncode_after_stop']=job.wait(timeout=5)
                    except subprocess.TimeoutExpired:job.kill();receipt['driver_returncode_after_stop']=job.wait(timeout=5)
                    receipt.update(status='failed',own_docker_cli_terminated=True)
            receipt['gpu_released_unix']=time.time();write(target,receipt)
        if receipt['status']!='native_completed':return 1
        print('Native matrix complete; owned GPU container stopped. Starting CPU-only final receipts/MP4 decode.',flush=True)
        validation=base/'host/final-validation';validation.mkdir(exist_ok=False);cpu=None
        try:
            command=create_args(base,plan,False);receipt['cpu_create_argv']=command;cpu=call(command).strip()
            if not re.fullmatch('[0-9a-f]{64}',cpu):raise ValueError('Exact full new CPU container ID required')
            receipt['cpu_container_id']=cpu;call(['docker','start',cpu]);verify_container(inspect(cpu),cpu,base,plan,False)
            argv=['docker','exec',cpu,'/opt/php/bin/inference-python','/control/finalize_fresh629.py',
                  '--plan','/data/native-plan.json','--output','/validation/full-validation.json']
            receipt['cpu_validation_argv']=argv;write(target,receipt)
            with (validation/'driver.log').open('x') as output:
                completed=subprocess.run(argv,stdout=output,stderr=subprocess.STDOUT,timeout=3600)
            receipt['cpu_validation_returncode']=completed.returncode
            if completed.returncode:raise RuntimeError('CPU full629 evidence/video finalizer failed')
            post=json.loads((validation/'full-validation.json').read_text())
            if post['status']!='passed' or post['worker_exit0_empty_group_count']!=1258 or post['full_decoded_mp4_count']!=629:raise ValueError('CPU final exact counts differ')
            receipt['snapshot_files_verified_after_native']=verify_snapshot(base,plan)
            receipt.update(status='completed',full_validation_sha256=sha(validation/'full-validation.json'),quality_verified=False,obstacle_course_completion_verified=False)
        except BaseException as error:
            receipt.update(status='failed',post_validation_error=f'{type(error).__name__}: {error}');raise
        finally:
            if cpu is not None:
                try:receipt['owned_cpu_container_stop']=stop_owned(cpu,base,plan,False)
                except BaseException as error:receipt.update(status='failed',cpu_cleanup_error=f'{type(error).__name__}: {error}')
            receipt['finished_unix']=time.time();write(target,receipt)
        return 0 if receipt['status']=='completed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--root-authorized-start',action='store_true');args=parser.parse_args();return execute(args)

if __name__=='__main__':raise SystemExit(main())
