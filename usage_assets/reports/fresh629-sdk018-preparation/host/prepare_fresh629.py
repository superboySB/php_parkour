#!/usr/bin/env python3
"""Freeze full canonical source/all629 inputs, then CPU-only native plan/imports.

This preparer never creates a GPU container or constructs Robot/DDS/simulation.
All source, inputs and owned controls are copied into a fresh output directory.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT_NATIVE = Path('/workspace/php_parkour')
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
ROOT_REVISION = '6cb2ae2492ef7bf66da7c5a72da87d6f60f0636f'
MODELS = {'depth_backbone.onnx':'5b22466a218944e3b0ab0f4f82a910e3eec35375ee03e7fb94eb65fa88431b56',
          'student.onnx':'e426c4206181d511b838c76efc48e43636299b76cb5a15183977011589931628'}
EXPECTED_SDK = {'simulator':'9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926',
                'inference':'fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4'}
UUID = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def copy(source, target, expected=None, expected_size=None):
    source = Path(source)
    if not source.is_file() or source.is_symlink() or target.exists():raise ValueError('Expected fresh regular snapshot source/destination')
    before = sha(source)
    if expected is not None and before != expected:raise ValueError('Input/source SHA changed: '+str(source))
    if expected_size is not None and source.stat().st_size != expected_size:raise ValueError('Input/source size changed')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    if sha(target) != before or sha(source) != before:raise ValueError('Source mutated during copy')
    target.chmod(0o444)
    return {'sha256':before,'bytes':target.stat().st_size}


def load_module(path):
    spec=importlib.util.spec_from_file_location('canonical_scene_matrix',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def evidence_records(directory, base):
    records=[]
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.is_symlink():raise ValueError('Unexpected CPU-preflight evidence path')
        # Docker output can be root-owned. Integrity is bound by SHA and these
        # files are never mounted writable into the native execution container.
        records.append({'relative':str(path.relative_to(base)),'sha256':sha(path),'bytes':path.stat().st_size})
    return records


def call(argv, timeout=60):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise RuntimeError(f'{argv[0]} command failed {result.returncode}: {result.stderr}')
    return result.stdout


def prepare(args):
    workspace=args.workspace.resolve(strict=True);context=args.context.resolve(strict=True);base=args.output.resolve()
    if base.exists() or not base.is_relative_to(workspace/'outputs/research'):raise ValueError('Fresh ignored research cohort required')
    source_manifest=json.loads(args.source_manifest.read_text())
    if source_manifest['root_revision'] != ROOT_REVISION or len(source_manifest['files']) != 3297:raise ValueError('Canonical committed source identity/count differs')
    matrix=load_module(context/'scripts/research/sim2sim_scene_matrix.py')
    source_path=workspace/'outputs/research/motion-matching/matrix.json'
    source=json.loads(source_path.read_text());selections=matrix.select(source,True)
    if len(selections)!=629 or len({s['scenario'] for s in selections})!=17 or len({s['mesh_sha256'] for s in selections})!=580:
        raise ValueError('Require exact629 configurations/17 scenarios/580 unique OBJ hashes')
    source_files=[item for case in selections for item in case['source_files']]
    if len(source_files)!=1887 or len({item['path'] for item in source_files})!=1887:raise ValueError('Require1887 unique generated input paths')
    base.mkdir(parents=True,exist_ok=False)
    for name in ['source','inputs','outputs','cache','host','control','inputs/cache','host/cpu-preflight']:(base/name).mkdir()
    manifest=[]
    write(base/'preparation-status.json',{'status':'copying','native_started':False})
    for item in source_manifest['files']:
        relative=Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or any(part=='.git' for part in relative.parts):raise ValueError('Unsafe source archive path')
        record=copy(context/relative,base/'source'/relative,item['sha256'],item['bytes'])
        manifest.append({'relative':str(Path('source')/relative),**record})
    for item in source_files:
        native=Path(item['path'])
        if not native.is_relative_to(ROOT_NATIVE):raise ValueError('Unexpected generated input namespace')
        relative=native.relative_to(ROOT_NATIVE);source_file=workspace/relative
        if not source_file.resolve().is_relative_to(workspace):raise ValueError('Generated input escapes workspace')
        record=copy(source_file,base/'source'/relative,item['sha256'],item.get('size',item.get('bytes')))
        manifest.append({'relative':str(Path('source')/relative),**record})
    for source_file,relative,expected in [(source_path,Path('inputs/matrix.json'),None),
                                        (args.source_manifest,Path('inputs/original-source-manifest.json'),None),
                                        *[(workspace/'outputs/research/assets/student'/name,Path('inputs/assets/student')/name,digest) for name,digest in MODELS.items()]]:
        record=copy(source_file,base/relative,expected);manifest.append({'relative':str(relative),**record})
    controls=['run_frozen_matrix.py','observe_container_pids.py','verify_snapshot_imports.py','finalize_fresh629.py']
    for filename in controls:
        record=copy(HERE/filename,base/'control'/filename);manifest.append({'relative':'control/'+filename,**record})
    for filename in ['prepare_fresh629.py','run_fresh629.py']:
        record=copy(HERE/filename,base/'host'/filename);manifest.append({'relative':'host/'+filename,**record})
    native_args=['--matrix','/data/matrix.json','--models','/data/assets/student','--output','/outputs/all-configs',
                 '--seconds','10.0','--seed','42','--gl','egl','--sim-python','/opt/php/bin/train-python',
                 '--inference-python','/opt/php/bin/inference-python','--image-id',IMAGE,'--all-configs']
    cpu=base/'host/cpu-preflight';cid=None
    create=['docker','create','--name','php-fresh629-cpu-'+identity(str(base))[:12],'--runtime','runc','--network','none',
            '--ipc','private','--init','--shm-size','1g','--env','CUDA_VISIBLE_DEVICES=','--env','NVIDIA_VISIBLE_DEVICES=void',
            '--env','PHP_DOCKER=1','--env','PYTHONDONTWRITEBYTECODE=1','--env','MUJOCO_EGL_DEVICE_ID=0','--env','WANDB_MODE=disabled',
            '--workdir',str(ROOT_NATIVE),'--entrypoint','/bin/bash']
    for src,dst,ro in [(base/'source',str(ROOT_NATIVE),True),(base/'inputs','/data',True),(base/'control','/control',True),(cpu,'/preflight',False)]:
        create+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if ro else '')]
    create += [IMAGE,'-lc','exec sleep 1200']
    receipt={'schema_version':1,'status':'starting','native_started':False,'scope':'CPU-only native all629 plan/hash checks and import/config-only preflight',
             'create_argv':create,'started_unix':time.time(),'commands':[]}
    write(cpu/'launch.json',receipt)
    try:
        cid=call(create).strip()
        if not re.fullmatch(r'[0-9a-f]{64}',cid):raise ValueError('Exact full new CPU container ID required')
        receipt['container_id']=cid;call(['docker','start',cid])
        inspected=json.loads(call(['docker','inspect',cid]))[0]
        if (inspected['Id']!=cid or inspected['Image']!=IMAGE or inspected['HostConfig']['Runtime']!='runc'
                or inspected['HostConfig']['DeviceRequests'] or inspected['HostConfig']['NetworkMode']!='none'
                or inspected['HostConfig']['IpcMode']!='private' or inspected['HostConfig'].get('PidMode')):raise ValueError('CPU isolation identity differs')
        write(cpu/'container-inspect.json',inspected)
        commands=[('plan',['/opt/php/bin/inference-python',str(ROOT_NATIVE/'scripts/research/sim2sim_scene_matrix.py'),*native_args,
                            '--plan','--plan-output','/preflight/native-plan.json']),
                  ('simulator',['/opt/php/bin/train-python','/control/verify_snapshot_imports.py','--role','simulator','--plan','/preflight/native-plan.json','--output','/preflight/simulator.json']),
                  ('inference',['/opt/php/bin/inference-python','/control/verify_snapshot_imports.py','--role','inference','--plan','/preflight/native-plan.json','--output','/preflight/inference.json'])]
        for name,command in commands:
            argv=['docker','exec',cid,*command];entry={'name':name,'argv':argv,'started_unix':time.time()};receipt['commands'].append(entry);write(cpu/'launch.json',receipt)
            result=subprocess.run(argv,capture_output=True,text=True,timeout=240)
            (cpu/(name+'.stdout.log')).write_text(result.stdout);(cpu/(name+'.stderr.log')).write_text(result.stderr)
            entry.update(returncode=result.returncode,finished_unix=time.time());write(cpu/'launch.json',receipt)
            if result.returncode:raise RuntimeError('CPU '+name+' preflight failed; raw retained')
        native_plan=json.loads((cpu/'native-plan.json').read_text())
        if (native_plan['schema_version']!=3 or native_plan['planned_configurations']!=629 or native_plan['planned_scenarios']!=17
                or len(native_plan['selections'])!=629 or len({case['mesh_sha256'] for case in native_plan['selections']})!=580):raise ValueError('Actual native plan counts differ')
        for role,expected in EXPECTED_SDK.items():
            report=json.loads((cpu/(role+'.json')).read_text())
            if report['status']!='passed' or report['sdk']['version']!='0.1.8' or report['sdk']['sha256']!=expected or report['robot_or_dds_construction_attempts']:
                raise ValueError('CPU actual SDK/import guard differs')
        record=copy(cpu/'native-plan.json',base/'inputs/native-plan.json');manifest.append({'relative':'inputs/native-plan.json',**record})
        receipt['status']='passed'
    except BaseException as error:
        receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if cid:
            receipt['owned_container_stop']=call(['docker','stop','--time','5',cid],timeout=15).strip()
            info=json.loads(call(['docker','inspect',cid]))[0];receipt['owned_container_running_after_stop']=info['State']['Running']
        receipt['finished_unix']=time.time();write(cpu/'launch.json',receipt)
    if receipt.get('owned_container_running_after_stop') is not False:raise ValueError('CPU preflight container not confirmed stopped')
    manifest.extend(evidence_records(cpu,base))
    write(base/'freeze-manifest.json',{'schema_version':1,'files':sorted(manifest,key=lambda i:i['relative'])})
    plan={'schema_version':1,'status':'prepared_only','native_started':False,'image_id':IMAGE,'root_revision':ROOT_REVISION,
          'submodule_revision':source_manifest['submodule_revision'],'workspace':str(workspace),'output':str(base),
          'gpu_uuid':UUID,'container_name':'php-fresh629-'+identity(str(base))[:16],
          'source_manifest_sha256':sha(base/'inputs/original-source-manifest.json'),'freeze_manifest_sha256':sha(base/'freeze-manifest.json'),
          'native_plan_sha256':native_plan['plan_sha256'],'native_plan_file_sha256':sha(base/'inputs/native-plan.json'),
          'cpu_preflight_receipt_sha256':sha(cpu/'launch.json'),
          'source_files':3297,'generated_input_files':1887,'configurations':629,'scenarios':17,'unique_obj_sha256':580,
          'native_args':native_args,'control_wrapper_sha256':sha(base/'control/run_frozen_matrix.py'),
          'matrix_source_sha256':sha(base/'source/scripts/research/sim2sim_scene_matrix.py'),
          'expected_sdk_extension_sha256':EXPECTED_SDK,'expected_worker_mapping_count':1258,
          'host_driver_timeout_seconds':43200,'host_observer_timeout_seconds':43500,
          'global_host_lock':str(workspace/'outputs/research'/('.local-native-'+UUID+'.lock')),
          'quality_verified':False,'obstacle_course_completion_verified':False,
          'scope':'Fresh all629 native execution cohort; constant forward commands, no reference replay; full success requires real driver0/1258worker0+threadmappings/629fullMP4decodes'}
    plan['plan_sha256']=identity(plan);write(base/'host-plan.json',plan)
    write(base/'preparation-status.json',{'status':'prepared_only','native_started':False,'plan_sha256':plan['plan_sha256']})
    print(json.dumps({'status':'prepared_only','plan':str(base/'host-plan.json'),'native_plan_sha256':native_plan['plan_sha256'],
                      'frozen_files':len(manifest),'configurations':629,'scenarios':17,'unique_obj_sha256':580,'native_started':False}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--context',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:prepare(args)
    except BaseException as error:
        if args.output.is_dir():
            write(args.output/'preparation-failure.json',{'status':'failed','native_started':False,'error':f'{type(error).__name__}: {error}','finished_unix':time.time()})
        raise


if __name__=='__main__':main()
