#!/usr/bin/env python3
"""Isolated final-student 58-case control plane; status never starts anything.

prepare refuses absent/partial final fetches, then uses short no-GPU Docker CPU
jobs. run requires a separately reviewed prepared snapshot and root start flag.
Neither operation performs SSH, rsync, training or changes a previous cohort.
"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from common import *
import common as contracts

HERE=Path(__file__).resolve().parent
ROOT=Path('/workspace/php_parkour')
CONTROL=('common.py','native58.py','phase_cpu.py','scene17.py','commands_executor.py',
         'sdk_actual_probe.py','verify_snapshot_imports.py','observe_container_pids.py','run_frozen_matrix.py',
         'previous_recovered_02.py')
RECOVERED_GATE_SHA='dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525'
RECOVERED_PREVIOUS=HOST_WORKSPACE/'outputs/research/fresh629-recovery-01/missing-four-run-01/host/launch-receipt.json'
LIFECYCLE='recovered_original629_and_separate_four_preserving_root143'


def recovered_previous():
    """Read the exact recovery proof; the original root exit143 remains143."""
    path=HERE/'previous_recovered_02.py'
    require(not path.is_symlink() and path.is_file() and sha(path)==RECOVERED_GATE_SHA,
            'Reviewed recovered lifecycle gate changed')
    spec=importlib.util.spec_from_file_location('native58_recovered_previous',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.previous_recovered()
    require(sha(path)==RECOVERED_GATE_SHA,'Recovered lifecycle gate changed during read')
    require(result.get('status') in ('waiting','recovered_previous_ready')
            and result.get('original_session54334_exit_code')==143,'Recovered lifecycle proof schema differs')
    if result.get('ready'):
        require(result['status']=='recovered_previous_ready' and result['original_root_normal_exit_verified'] is False
                and result['original_host_observer_gap_preserved'] is True,'Recovery must preserve the original failure/gap')
    else:require(result['status']=='waiting','Recovery readiness differs')
    return result


def call(argv, timeout=60):
    done=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    require(done.returncode==0, f'Command failed {done.returncode}: {argv[0]}: {done.stderr}')
    return done.stdout


def local_docker():
    context=call(['docker','context','show']).strip()
    info=json.loads(call(['docker','context','inspect',context]))[0]
    endpoint=os.environ.get('DOCKER_HOST') or info['Endpoints']['docker']['Host']
    require(endpoint.startswith('unix://'),'Exact host/proc observer requires local Unix Docker endpoint')
    return {'context':context,'endpoint':endpoint}


def gpu_idle():
    ids=call(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader']).splitlines()
    require(ids.count(UUID)==1,'Approved physical GPU UUID not unique/present')
    apps=call(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'])
    require(not any(line.split(',')[0].strip()==UUID for line in apps.splitlines() if line.strip()),
            'Selected GPU has existing compute; never stop other work')
    return {'uuid':UUID,'existing_compute_processes':[]}


def inspect(cid):return json.loads(call(['docker','inspect','--type','container',cid]))[0]


def mount_specs(base, kind, outputs=None, evidence=None, cache=False):
    mounts=[(base/'source',str(ROOT),False),(base/'inputs'/kind,'/data',False),(base/'control','/control',False)]
    if outputs is not None:mounts.append((outputs,'/outputs',cache))
    if cache:mounts.append((base/'cache'/kind,'/data/cache',True))
    if evidence is not None:mounts.append((evidence,'/preflight' if outputs is None else '/validation',True))
    return [{'source':str(src),'destination':dst,'rw':rw} for src,dst,rw in mounts]


def container_spec(base, kind, name, command, gpu=False, outputs=None, evidence=None):
    mounts=mount_specs(base,kind,outputs,evidence,cache=gpu)
    argv=['docker','create','--name',name,'--network','none','--ipc','private','--init',
          '--shm-size','8g' if gpu else '1g','--workdir',str(ROOT),'--entrypoint',command[0]]
    if gpu:argv+=['--gpus','device='+UUID]
    else:argv+=['--runtime','runc','--env','CUDA_VISIBLE_DEVICES=','--env','NVIDIA_VISIBLE_DEVICES=void']
    env={'PHP_DOCKER':'1','WANDB_MODE':'disabled','WANDB_DISABLED':'true','HF_HUB_OFFLINE':'1',
         'HF_DATASETS_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','MUJOCO_EGL_DEVICE_ID':'0','PYTHONDONTWRITEBYTECODE':'1'}
    if gpu:env['NVIDIA_DRIVER_CAPABILITIES']='compute,utility,graphics'
    for key,value in env.items():argv+=['--env',key+'='+value]
    for item in mounts:
        argv+=['--mount',f"type=bind,src={item['source']},dst={item['destination']}"+('' if item['rw'] else ',readonly')]
    return {'name':name,'mounts':mounts,'gpu':gpu,'command':command,'argv':argv+[IMAGE,*command[1:]]}


def verify_container(info,cid,spec):
    require(re.fullmatch('[0-9a-f]{64}',cid) is not None,'Exact full container ID required')
    host=info['HostConfig'];devices=host.get('DeviceRequests') or []
    actual=sorted((m['Source'],m['Destination'],m['RW'],m['Type']) for m in info['Mounts'])
    expected=sorted((m['source'],m['destination'],m['rw'],'bind') for m in spec['mounts'])
    require(info['Id']==cid and info['Image']==IMAGE and info['Name']=='/'+spec['name']
        and info['Config']['WorkingDir']==str(ROOT) and info['Config']['Entrypoint']==[spec['command'][0]]
        and info['Config']['Cmd']==spec['command'][1:] and actual==expected
        and host['NetworkMode']=='none' and host['IpcMode']=='private' and not host.get('PidMode','')
        and host['Privileged'] is False and host.get('Init') is True
        and host['ShmSize']==(8589934592 if spec['gpu'] else 1073741824),'Owned container identity/isolation differs')
    if spec['gpu']:
        require(len(devices)==1 and devices[0].get('DeviceIDs')==[UUID] and devices[0].get('Count')==0,
                'Only the approved single GPU UUID is allowed')
    else:require(not devices and host['Runtime']=='runc','CPU container must have no GPU request/runtime')


def stop_owned(cid,spec):
    verify_container(inspect(cid),cid,spec)
    call(['docker','stop','--time','20',cid],timeout=35)
    final=inspect(cid);verify_container(final,cid,spec)
    require(final['State']['Running'] is False,'Owned fixed container did not stop')
    return {'container_id':cid,'running_after_stop':False,'state':final['State']}


def cpu_job(base,kind,mode,evidence,phase=None,outputs=None):
    evidence.mkdir(parents=True,exist_ok=False)
    command=['/opt/php/bin/inference-python','/control/phase_cpu.py',mode]
    if phase:command+=['--phase',phase]
    command+=['--output',('/preflight' if mode=='prepare' else '/validation')+'/summary.json']
    name='php-native58-cpu-'+identity([str(base),kind,mode,phase])[:16]
    spec=container_spec(base,kind,name,command,False,outputs,evidence)
    receipt={'schema_version':1,'status':'starting','native_started':False,'gpu_started':False,
             'mode':mode,'kind':kind,'phase':phase,'create_argv':spec['argv'],'started_unix':time.time()}
    target=evidence/'launch.json';write(target,receipt);cid=None
    try:
        cid=call(spec['argv']).strip();require(re.fullmatch('[0-9a-f]{64}',cid),'Full new CPU container ID required')
        receipt['container_id']=cid;verify_container(inspect(cid),cid,spec);write(target,receipt)
        argv=['docker','start','-a',cid]
        with (evidence/'stdout.log').open('x') as stdout,(evidence/'stderr.log').open('x') as stderr:
            done=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=900 if mode=='prepare' else 3600)
        actual=inspect(cid);verify_container(actual,cid,spec);write(evidence/'container-inspect.json',actual)
        receipt.update(returncode=done.returncode,container_exit_code=actual['State']['ExitCode'])
        require(done.returncode==actual['State']['ExitCode']==0 and not actual['State']['Running'],'Actual CPU job failed or remains running')
        report=read(evidence/'summary.json');require(report['status']=='passed','Actual CPU report failed')
        if mode=='prepare':require(report['ort_cases']==30 and report['directions_cases']==12 and report['scene_cases']==17,
                                   'Actual final-pair CPU preparation counts differ')
        receipt['status']='passed'
    except BaseException as error:
        receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if cid is not None:
            try:receipt['owned_container_stop']=stop_owned(cid,spec)
            except BaseException as error:receipt.update(status='failed',cleanup_error=f'{type(error).__name__}: {error}')
        receipt['finished_unix']=time.time();write(target,receipt)
    require(receipt['status']=='passed','CPU job cleanup failed')
    return report


def prepare(args):
    workspace=args.workspace.resolve(strict=True)
    origin=transfer(workspace,args.transfer)
    if origin['status']=='waiting':return origin
    base=args.output.absolute()
    require('..' not in base.parts and base.is_relative_to(workspace/'outputs/research') and not base.exists()
            and not any(p.is_symlink() for p in (base,*base.parents)),'Fresh isolated research output required')
    require(workspace==HOST_WORKSPACE,'Use the reviewed local workspace and shared GPU mutex')
    context=workspace/'outputs/research/sdk018-canonical-build-6cb2ae2/context'
    manifest=read(context.parent/'source-manifest.json')
    require(manifest['root_revision']==REVISION and len(manifest['files'])==3297,'Canonical source commit/count changed')
    matrix=load(context/'scripts/research/sim2sim_scene_matrix.py','native58_selector')
    require(sha(context/'scripts/research/sim2sim_scene_matrix.py')==MATRIX_SHA
            and sha(context/'scripts/research/sim2sim.py')==SUPERVISOR_SHA,'Canonical core SHA differs')
    old=workspace/'outputs/research/commands12-sdk018-6cb2ae2-prepared01/inputs/native-plan.json'
    native_old=read(old)
    require(native_old['image_id']==IMAGE and len(native_old['dependencies'])==376,'Canonical direction baseline dependency identity differs')
    matrix_path=workspace/'outputs/research/motion-matching/matrix.json'
    full=matrix.select(read(matrix_path),True)
    require(len(full)==629 and len({s['scenario'] for s in full})==17,'Source all629 geometry inventory changed')
    generated=[item for case in full for item in case['source_files']]
    require(len(generated)==len({x['path'] for x in generated})==1887,'Expected1887 generated source inputs')
    for item in read(HERE/'reused-sources.json')['files']:
        require(sha(HERE/item['name'])==item['sha256'] and sha(workspace/item['origin'])==item['sha256'],'Frozen reused helper changed')
    endpoint=local_docker()
    require(json.loads(call(['docker','image','inspect',IMAGE]))[0]['Id']==IMAGE,'Canonical immutable local image absent')
    base.mkdir()
    for name in ('source','control','inputs','cache','host','phases'):(base/name).mkdir()
    write(base/'preparation-status.json',{'status':'copying','native_started':False,'gpu_started':False})
    try:
        for item in manifest['files']:
            rel=Path(item['path']);require(not rel.is_absolute() and '..' not in rel.parts and '.git' not in rel.parts,'Unsafe source archive path')
            copy(context/rel,base/'source'/rel,item['sha256'],item['bytes'])
        for item in generated:
            path=Path(item['path']);require(path.is_relative_to(ROOT),'Unexpected native generated input namespace')
            rel=path.relative_to(ROOT);copy(workspace/rel,base/'source'/rel,item['sha256'],item.get('bytes',item.get('size')))
        for name in CONTROL:copy(HERE/name,base/'control'/name)
        copy(HERE/'reused-sources.json',base/'control/reused-sources.json')
        copy(context.parent/'source-manifest.json',base/'inputs/original-source-manifest.json')
        write(base/'inputs/transfer-contract.json',origin)
        for kind in KINDS:
            data=base/'inputs'/kind;data.mkdir();(data/'cache').mkdir();(base/'cache'/kind).mkdir()
            copy(matrix_path,data/'matrix.json');copy(old,data/'baseline-native-plan.json')
            copy(old.parent/'baseline-matrix.json',data/'baseline-matrix.json',
                 native_old['source_matrix_record']['sha256'],native_old['source_matrix_record']['bytes'])
            for item in origin['models']:
                if item['kind']==kind:copy(item['path'],data/'assets/student'/Path(item['path']).name,item['sha256'],item['bytes'])
            report=cpu_job(base,kind,'prepare',base/'host'/('cpu-'+kind))
            for phase in PHASES:copy(base/'host'/('cpu-'+kind)/(phase+'-plan.json'),data/(phase+'-plan.json'))
        phases=phase_specs()
        for phase in phases:
            p=read(base/'inputs'/phase['kind']/(phase['phase']+'-plan.json'))
            phase['native_plan_sha256']=p['plan_sha256'];phase['native_plan_file_sha256']=sha(base/'inputs'/phase['kind']/(phase['phase']+'-plan.json'))
            phase['container_name']='php-native58-'+identity([str(base),phase['id']])[:16]
        for item in origin['origin_files']:verify_record(item)
        files=[]
        for group in ('source','inputs','control','host'):
            for p in sorted((base/group).rglob('*')):
                require(not p.is_symlink(),'Unexpected snapshot symlink')
                if p.is_file():files.append({'relative':str(p.relative_to(base)),'sha256':sha(p),'bytes':p.stat().st_size})
        write(base/'freeze-manifest.json',{'schema_version':1,'files':files})
        plan={'schema_version':1,'status':'prepared_only','native_started':False,'gpu_started':False,
              'workspace':str(workspace),'output':str(base),'image_id':IMAGE,'gpu_uuid':UUID,'revision':REVISION,
              'freeze_manifest_sha256':sha(base/'freeze-manifest.json'),'origin_transfer':origin,'phases':phases,
              'expected_counts':{'policies':2,'cases':58,'worker_exit0_empty_groups':116,'exact_host_maps':116,'full_mp4_decodes':58,'cpu_ort_cases':60},
              'global_host_lock':str(workspace/'outputs/research'/('.local-native-'+UUID+'.lock')),
              'previous_cohort_receipt':str(RECOVERED_PREVIOUS),'previous_lifecycle':LIFECYCLE,
              'previous_gate':{'relative':'control/previous_recovered_02.py','sha256':RECOVERED_GATE_SHA},
              'endpoint':endpoint,'host_total_timeout_seconds':43200,
              'scope':'Two final official student pairs, each original12 plane directions and17 representative constant-forward geometries; not full629 or skill-success evidence',
              'quality_verified':False,'obstacle_course_completion_verified':False}
        plan['plan_sha256']=identity(plan);write(base/'host-plan.json',plan)
        write(base/'preparation-status.json',{'status':'prepared_only','native_started':False,'gpu_started':False,'plan_sha256':plan['plan_sha256']})
        return {'status':'prepared_only','plan':str(base/'host-plan.json'),'plan_sha256':plan['plan_sha256'],'frozen_files':len(files),
                'cases':58,'workers':116,'actual_cpu_ort_cases':60,'native_started':False,'gpu_started':False}
    except BaseException as error:
        write(base/'preparation-failure.json',{'status':'failed','native_started':False,'gpu_started':False,'error':f'{type(error).__name__}: {error}'})
        raise


def verify_snapshot(base,plan):
    require('..' not in base.parts,'Parent traversal in prepared cohort path rejected')
    original=dict(plan);recorded=original.pop('plan_sha256')
    require(identity(original)==recorded and plan['output']==str(base.absolute()) and plan['image_id']==IMAGE and plan['gpu_uuid']==UUID
            and plan['revision']==REVISION and plan['status']=='prepared_only' and plan['native_started'] is False,'Frozen host plan identity differs')
    workspace=Path(plan['workspace'])
    lock=HOST_WORKSPACE/'outputs/research'/('.local-native-'+UUID+'.lock')
    previous=RECOVERED_PREVIOUS
    require(workspace==HOST_WORKSPACE and base.is_relative_to(workspace/'outputs/research')
            and plan['global_host_lock']==str(lock) and plan['previous_cohort_receipt']==str(previous)
            and plan.get('previous_lifecycle')==LIFECYCLE
            and plan.get('previous_gate')=={'relative':'control/previous_recovered_02.py','sha256':RECOVERED_GATE_SHA}
            and not any(p.is_symlink() for path in (base,lock,previous) for p in (path,*path.parents)),
            'Canonical workspace/global GPU mutex/previous cohort path contract differs')
    require(sha(base/'control/previous_recovered_02.py')==RECOVERED_GATE_SHA,'Frozen recovered gate SHA differs')
    require(sha(base/'freeze-manifest.json')==plan['freeze_manifest_sha256'],'Frozen manifest changed')
    records=read(base/'freeze-manifest.json')['files'];seen=set()
    for item in records:
        rel=Path(item['relative']);require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in seen,'Unsafe/duplicate frozen path')
        seen.add(str(rel));verify_record(dict(item,path=str(base/rel)))
    for item in plan['origin_transfer']['origin_files']:verify_record(item)
    require([p['id'] for p in plan['phases']]==[p['id'] for p in phase_specs()],'Ordered four phases changed')
    for phase,expected in zip(plan['phases'],phase_specs()):
        require(all(phase[k]==v for k,v in expected.items()),'Default phase timing/count changed')
        path=base/'inputs'/phase['kind']/(phase['phase']+'-plan.json')
        require(sha(path)==phase['native_plan_file_sha256'] and read(path)['plan_sha256']==phase['native_plan_sha256'],'Native phase plan changed')
        cpu=read(base/'host'/('cpu-'+phase['kind'])/'launch.json')
        require(cpu['status']=='passed' and cpu['returncode']==cpu['container_exit_code']==0
                and cpu['owned_container_stop']['running_after_stop'] is False,'Actual completed CPU container receipt absent')
    require(plan['expected_counts']=={'policies':2,'cases':58,'worker_exit0_empty_groups':116,'exact_host_maps':116,'full_mp4_decodes':58,'cpu_ort_cases':60},
            'Exact final count contract changed')
    return len(records)


def mappings(base,phase,cid,info,report):
    observer=read(report/'observer/summary.json')
    require(observer['identity']['container_id']==cid and observer['identity']['image_id']==IMAGE
            and observer['identity']['started_at']==info['State']['StartedAt'] and observer['stop_reason']=='stop_file'
            and observer['mapping_scope_complete'] and observer['errors']==[],'Observer container/birth/whole-phase scope differs')
    raw=report/'outputs'
    if phase['phase']=='directions':
        native=read(raw/'pilot-summary.json');cases=native['cases']
        require(native['status']=='completed' and native['native_plan_sha256']==phase['native_plan_sha256']
                and native['remaining_native_pids']==[],'Directions native phase incomplete')
        outputs=[case['output'] for case in cases]
    else:
        native=read(raw/'scenes17/matrix.json');cases=native['selections']
        require(native['status']=='completed' and native['plan_sha256']==phase['native_plan_sha256'],'Scene native phase incomplete')
        require(all(len(c['attempts'])==1 for c in cases),'Only once-attempted scenes allowed')
        outputs=[case['attempts'][0]['output'] for case in cases]
    require(len(cases)==phase['cases'],'Native count differs before host maps')
    result=[];threads=set()
    for case,output in zip(cases,outputs):
        require(case['status']=='completed','Native failed case remains failed')
        for role in ('simulator','inference'):
            entry=regular(raw/Path(output).relative_to('/outputs')/(role+'-process-start.json'),raw)
            native=read(entry)['process']
            found=[m for m in observer['command_writer_mappings'] if m['role']==role and m['worker_output']==output
                   and m['container_tgid']==native['pid'] and m['owner_start_time_clock_ticks']==native['start_time_clock_ticks']]
            require(len(found)==1,'Missing exact host PID/birth→command_writer mapping')
            m=found[0];key=(m['host_tid'],m['start_time_clock_ticks'])
            require(key not in threads and m['nspid']==[m['host_tid'],m['container_tid']]
                    and m['nstgid']==[m['host_tgid'],native['pid']],'Host thread namespace/owner uniqueness differs')
            threads.add(key);result.append({'phase':phase['id'],'case_id':case['case_id'],'role':role,'entry_sha256':sha(entry),'mapping':m})
    require(len(result)==2*phase['cases'],'Exact worker mapping count changed')
    return result


def native_command(base,phase):
    if phase['phase']=='directions':
        return ['/opt/php/bin/inference-python','/control/commands_executor.py','--plan','/data/directions-plan.json','--summary','/outputs/pilot-summary.json']
    from phase_cpu import scene_args
    return ['/opt/php/bin/inference-python','/control/scene17.py','--expected-plan','/data/scenes-plan.json',
            '--matrix-sha256',MATRIX_SHA,'--helper-sha256',sha(base/'control/scene17.py'),'--',*scene_args()]


def cleanup_phase(cid,spec,observer,job,stop,item):
    """Diagnostic/observer errors never bypass owned-container/CLI cleanup."""
    errors=[]
    def failed(stage,error):
        errors.append({'stage':stage,'error':f'{type(error).__name__}: {error}'})
    if observer is not None:
        try:
            if observer.poll() is None:
                try:stop.touch(exist_ok=True)
                except BaseException as error:failed('observer_stop_marker',error)
                try:item['observer_returncode']=observer.wait(timeout=30)
                except BaseException as error:
                    failed('observer_wait',error)
                    # Only our own readonly observer Popen is ever signalled.
                    try:
                        if observer.poll() is None:observer.terminate()
                        try:item['observer_returncode']=observer.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            observer.kill();item['observer_returncode']=observer.wait(timeout=5)
                    except BaseException as error:failed('own_observer_cleanup',error)
        except BaseException as error:failed('observer_poll',error)
    if cid is not None:
        try:item['owned_gpu_container_stop']=stop_owned(cid,spec)
        except BaseException as error:failed('owned_container_stop',error)
    if job is not None:
        try:item['driver_returncode_after_stop']=job.wait(timeout=5)
        except BaseException as error:
            failed('own_docker_cli_wait',error)
            try:
                if job.poll() is None:job.terminate()
                try:item['driver_returncode_after_stop']=job.wait(timeout=5)
                except subprocess.TimeoutExpired:job.kill();item['driver_returncode_after_stop']=job.wait(timeout=5)
            except BaseException as error:failed('own_docker_cli_cleanup',error)
    if errors:item.update(status='failed',cleanup_errors=errors)
    item['native_finished_unix']=time.time()


def verify_host_sources(base):
    require(sha(__file__)==sha(base/'control/native58.py')
            and sha(contracts.__file__)==sha(base/'control/common.py'),
            'Run the exact frozen adapter/common source, not a changed preparer')


def execute(args):
    require(args.root_authorized_start,'Explicit root start authorization required')
    base=args.plan.absolute().parent;plan=read(args.plan);verify_snapshot(base,plan)
    verify_host_sources(base)
    with Path(plan['global_host_lock']).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt_path=base/'host/launch-receipt.json'
        require(not receipt_path.exists() and not any((base/'phases').iterdir()),'Fresh never-attempted output required; no retry/resume')
        previous=recovered_previous()
        require(previous.get('ready') is True and previous['status']=='recovered_previous_ready',
                'Recovered original629 plus separate four must be verified and released first')
        receipt={'schema_version':1,'status':'starting','native_started':False,'plan_sha256':plan['plan_sha256'],
                 'started_unix':time.time(),'endpoint':local_docker(),'gpu_before':gpu_idle(),'phases':[],
                 'previous_lifecycle':LIFECYCLE,'previous_recovered_proof':previous,
                 'quality_verified':False,'obstacle_course_completion_verified':False}
        write(receipt_path,receipt);deadline=time.monotonic()+plan['host_total_timeout_seconds']
        try:
            for phase in plan['phases']:
                require(time.monotonic()<deadline,'Whole58 batch bound reached before next phase')
                verify_snapshot(base,plan);gpu_idle()
                target=base/'phases'/phase['id'];target.mkdir();(target/'outputs').mkdir()
                item={'id':phase['id'],'status':'starting','started_unix':time.time(),'native_started':False}
                receipt['phases'].append(item);write(receipt_path,receipt)
                spec=container_spec(base,phase['kind'],phase['container_name'],['/bin/bash','-lc','exec sleep infinity'],True,target/'outputs')
                cid=observer=job=None;stop=target/'observer-stop'
                try:
                    cid=call(spec['argv']).strip();require(re.fullmatch('[0-9a-f]{64}',cid),'Full new GPU CID required')
                    item.update(container_id=cid,create_argv=spec['argv']);write(receipt_path,receipt)
                    call(['docker','start',cid]);info=inspect(cid);verify_container(info,cid,spec);write(target/'container-inspect.json',info)
                    gpu_idle()
                    observe=[sys.executable,str(base/'control/observe_container_pids.py'),'--container-id',cid,'--expected-image',IMAGE,
                             '--output',str(target/'observer'),'--stop-file',str(stop),'--interval','0.2',
                             '--max-seconds',str(phase['host_timeout_seconds']+120)]
                    item['observer_argv']=observe
                    with (target/'observer.log').open('x') as output:
                        observer=subprocess.Popen(observe,stdout=output,stderr=subprocess.STDOUT)
                        ready=time.monotonic()+15
                        while not (target/'observer/launch.json').is_file():
                            require(observer.poll() is None and time.monotonic()<ready,'Observer did not become ready');time.sleep(.1)
                        command=['docker','exec',cid,*native_command(base,phase)]
                        item.update(status='running',native_started=True,native_argv=command);receipt['native_started']=True;write(receipt_path,receipt)
                        with (target/'driver.log').open('x') as log:
                            job=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
                            item['docker_exec_host_pid']=job.pid;write(receipt_path,receipt)
                            timeout=min(phase['host_timeout_seconds'],deadline-time.monotonic())
                            require(timeout>0,'Whole58 batch time bound reached')
                            item['driver_returncode']=job.wait(timeout=timeout)
                        stop.touch(exist_ok=False);item['observer_returncode']=observer.wait(timeout=30)
                    require(item['driver_returncode']==item['observer_returncode']==0,'Real native driver/observer must exit0')
                    item['host_maps']=mappings(base,phase,cid,info,target)
                    item['status']='native_completed'
                except BaseException as error:
                    item.update(status='failed',error=f'{type(error).__name__}: {error}');raise
                finally:
                    cleanup_phase(cid,spec,observer,job,stop,item)
                    write(receipt_path,receipt)
                require(item['status']=='native_completed' and item['driver_returncode_after_stop']==0,'Native phase/cleanup failed; remaining phases never start')
                final=cpu_job(base,phase['kind'],'finalize',target/'cpu-final',phase['phase'],target/'outputs')
                require(final['worker_exit0_empty_groups']==2*phase['cases'] and final['full_decoded_mp4_count']==phase['cases'],
                        'CPU final phase exact receipts/video count differs')
                item.update(status='completed',cpu_final=record(target/'cpu-final/summary.json'),
                            worker_exit0_empty_groups=final['worker_exit0_empty_groups'],full_decoded_mp4_count=final['full_decoded_mp4_count'])
                write(receipt_path,receipt)
            require(sum(x['worker_exit0_empty_groups'] for x in receipt['phases'])==116
                    and sum(len(x['host_maps']) for x in receipt['phases'])==116
                    and sum(x['full_decoded_mp4_count'] for x in receipt['phases'])==58,'Complete58/116/116/58 terminal gate failed')
            verify_snapshot(base,plan);receipt.update(status='completed',cases=58,worker_exit0_empty_groups=116,exact_host_maps=116,full_decoded_mp4_count=58)
        except BaseException as error:
            receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
        finally:receipt['finished_unix']=time.time();write(receipt_path,receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('status','prepare','run'))
    p.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--transfer',type=Path,help='Explicit completed fetch attempt; never newest-directory discovery')
    p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--root-authorized-start',action='store_true')
    a=p.parse_args()
    if a.action=='status':result=transfer(a.workspace,a.transfer)
    elif a.action=='prepare':
        require(a.output is not None,'prepare needs a fresh explicit --output');result=prepare(a)
    else:
        require(a.plan is not None,'run needs reviewed --plan');result=execute(a)
    print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'rejected','error':f'{type(error).__name__}: {error}','quality_verified':False}),file=sys.stderr)
        raise SystemExit(1)
