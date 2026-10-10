#!/usr/bin/env python3
"""Prepare or explicitly execute one isolated SDK018 canonical12 original command cohort.

`prepare` only reads/copies/checks local files. `run` is a separate, explicitly
root-authorized operation. Never operates on an existing container or old cohort.
"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
NATIVE_ROOT = Path('/workspace/php_parkour')
MODELS = {'depth_backbone.onnx': '5b22466a218944e3b0ab0f4f82a910e3eec35375ee03e7fb94eb65fa88431b56',
          'student.onnx': 'e426c4206181d511b838c76efc48e43636299b76cb5a15183977011589931628'}
EXPECTED_EXTENSIONS = {'simulator': '9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926',
                       'inference': 'fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def run(*argv, timeout=30):
    result = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} {argv[1] if len(argv)>1 else ""} returned {result.returncode}: {result.stderr}')
    return result.stdout


def load_module(path):
    spec = importlib.util.spec_from_file_location('pilot_frozen_module', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value





def copy_checked(source, target, expected=None):
    source = Path(source).resolve(strict=True)
    before = sha(source)
    if expected is not None and before != expected:
        raise ValueError(f'Input SHA changed: {source}')
    if target.exists():
        raise ValueError(f'Duplicate snapshot destination: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha(target) != before or sha(source) != before:
        raise ValueError('Input changed while copying snapshot')
    # Source/input mounts are also Docker read-only. Keep raw file modes simple.
    target.chmod(0o444)
    return {'sha256': before, 'bytes': target.stat().st_size}








def prepare(args):
    workspace=args.workspace.resolve(strict=True);base=args.output.resolve();context=args.context.resolve(strict=True)
    if base.exists() or not base.is_relative_to(workspace/'outputs/research'):raise ValueError('Fresh owned ignored cohort required')
    if args.gpu_uuid!='GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25':raise ValueError('Root-approved exact physical UUID required')
    source_manifest=json.loads(args.source_manifest.read_text())
    if source_manifest['root_revision']!='6cb2ae2492ef7bf66da7c5a72da87d6f60f0636f' or len(source_manifest['files'])!=3297:raise ValueError('Canonical source commit/count differs')
    oldbase=workspace/'outputs/research/sim2sim/plane-directions';oldmatrix=oldbase/'matrix.json'
    old=json.loads(oldmatrix.read_text())
    if old['status']!='completed' or [c['command'] for c in old['commands']]!=list(range(12)) or old['seed']!=42 or old['terrain']!='plane':raise ValueError('Exact previous12 command baseline required')
    configs=[]
    for code in range(12):
        cfg=json.loads((oldbase/f'command-{code:02d}/run.json').read_text())
        expected={'commands':[code],'terrain':'plane','mesh':None,'mesh_sha256':None,'seed':42,'duration':8.0,'seconds_per_command':8.0,
                  'settle_seconds':3.0,'startup_timeout':180.0,'wall_timeout':373.0,'gl':'egl','ort_threads':1,'model_sha256':MODELS}
        if any(cfg.get(k)!=v for k,v in expected.items()) or cfg.get('record_policy',False) or cfg.get('course_guide',False):raise ValueError('Original command/seed/duration/native defaults changed')
        configs.append(cfg)
    base.mkdir(parents=True)
    for name in ['source','inputs','outputs','cache','host','control','inputs/cache','host/cpu-preflight']:(base/name).mkdir()
    write(base/'preparation-status.json',{'status':'preparing','native_started':False})
    files=[]
    def copy(source,relative,expected=None,size=None):
        if source.is_symlink():raise ValueError('Symlink source prohibited')
        record=copy_checked(source,base/relative,expected)
        if size is not None and record['bytes']!=size:raise ValueError('Snapshot size differs')
        files.append({'relative':str(relative),**record});return record
    for item in source_manifest['files']:
        relative=Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:raise ValueError('Unsafe source archive path')
        copy(context/relative,Path('source')/relative,item['sha256'],item['bytes'])
    copy(args.source_manifest,Path('inputs/original-source-manifest.json'))
    baseline=copy(oldmatrix,Path('inputs/baseline-matrix.json'))
    for code in range(12):copy(oldbase/f'command-{code:02d}/run.json',Path(f'inputs/baseline-runs/command-{code:02d}.json'))
    origin=copy(args.dependency_plan,Path('inputs/dependency-origin-native-plan.json'))
    dependency_plan=json.loads(args.dependency_plan.read_text());dependencies=dependency_plan['dependencies']
    if dependency_plan['image_id']!=IMAGE or len(dependencies)!=376:raise ValueError('Require same canonical376 source dependency closure')
    for item in dependencies:
        path=Path(item['path']);relative=path.relative_to(NATIVE_ROOT)
        if sha(base/'source'/relative)!=item['sha256']:raise ValueError('Canonical dependency differs')
    model_records=[]
    for filename,expected in MODELS.items():
        relative=Path('inputs/assets/student')/filename;record=copy(workspace/'outputs/research/assets/student'/filename,relative,expected)
        model_records.append({'path':str(Path('/data/assets/student')/filename),**record})
    control=[]
    for name in ['commands_executor.py','sdk_actual_probe.py','verify_snapshot_imports.py','cpu_plan_gate.py']:
        record=copy(HERE/name,Path('control')/name);control.append({'path':'/control/'+name,**record})
    for name in ['sdk018_commands.py','observe_container_pids.py']:copy(HERE/name,Path('host')/name)
    selections=[]
    for code,cfg in enumerate(configs):
        output=f'/outputs/commands/command-{code:02d}'
        command=['/opt/php/bin/inference-python',str(NATIVE_ROOT/'scripts/research/sim2sim.py'),'--models','/data/assets/student',
                 '--terrain','plane','--commands',str(code),'--seconds-per-command','8.0','--settle-seconds','3.0',
                 '--startup-timeout','180.0','--seed','42','--gl','egl','--ort-threads','1','--python-faulthandler',
                 '--sim-python','/opt/php/bin/train-python','--inference-python','/opt/php/bin/inference-python','--output',output]
        name=old['commands'][code]['result']['inference']['commands'][0]['name']
        selections.append({'case_id':f'command-{code:02d}:{name}','scenario':'plane','configuration_index':code,
                           'configuration':name,'command':code,'mesh':None,'mesh_sha256':None,'source_files':[],
                           'output':output,'launch':command,'baseline_run_sha256':sha(base/f'inputs/baseline-runs/command-{code:02d}.json'),
                           'expected_config':cfg|{'record_policy':False,'course_guide':False,'python_faulthandler':True}})
    harness=next(item for item in dependencies if item['path']==str(NATIVE_ROOT/'scripts/research/sim2sim.py'))
    native={'schema_version':3,'pilot_scope':'SDK018 canonical12 original plane commands; each once','image_id':IMAGE,'seed':42,
            'seconds_per_configuration':8.0,'python_faulthandler':True,'source_matrix_record':dict(baseline,path='/data/baseline-matrix.json'),
            'source_matrix_sha256':baseline['sha256'],'model_sha256':MODELS,'models':model_records,'dependencies':dependencies,
            'worker_harness_record':harness,'worker_interpreters':{'simulator':'/opt/php/bin/train-python','inference':'/opt/php/bin/inference-python'},
            'control_files':control,'dependency_origin_sha256':origin['sha256'],'selections':selections,
            'expected_sdk_extension_sha256':EXPECTED_EXTENSIONS,'quality_verified':False,'obstacle_course_completion_verified':False}
    native['plan_sha256']=identity(native);write(base/'inputs/native-plan.json',native)
    files.append({'relative':'inputs/native-plan.json','bytes':(base/'inputs/native-plan.json').stat().st_size,'sha256':sha(base/'inputs/native-plan.json')})
    mounts=[{'source':str(base/'source'),'destination':str(NATIVE_ROOT),'readonly':True},
            {'source':str(base/'inputs'),'destination':'/data','readonly':True},
            {'source':str(base/'outputs'),'destination':'/outputs','readonly':False},
            {'source':str(base/'cache'),'destination':'/data/cache','readonly':False},
            {'source':str(base/'control'),'destination':'/control','readonly':True}]
    cpu=base/'host/cpu-preflight';cid=None
    create=['docker','create','--name','php-commands12-cpu-'+identity(str(base))[:12],'--runtime','runc','--network','none','--ipc','private','--init','--shm-size','1g',
            '--env','CUDA_VISIBLE_DEVICES=','--env','NVIDIA_VISIBLE_DEVICES=void','--env','PHP_DOCKER=1','--env','PYTHONDONTWRITEBYTECODE=1','--env','MUJOCO_EGL_DEVICE_ID=0',
            '--workdir',str(NATIVE_ROOT),'--entrypoint','/bin/bash']
    for src,dst,ro in [(base/'source',str(NATIVE_ROOT),True),(base/'inputs','/data',True),(base/'control','/control',True),(cpu,'/preflight',False)]:
        create+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if ro else '')]
    create += [IMAGE,'-lc','exec sleep 1200']
    receipt={'status':'starting','native_started':False,'create_argv':create,'commands':[],'started_unix':time.time()};write(cpu/'launch.json',receipt)
    try:
        cid=run(*create).strip()
        if not re.fullmatch('[0-9a-f]{64}',cid):raise ValueError('Full new CPU CID required')
        receipt['container_id']=cid;run('docker','start',cid);info=json.loads(run('docker','inspect',cid))[0]
        if info['Id']!=cid or info['Image']!=IMAGE or info['HostConfig']['Runtime']!='runc' or info['HostConfig']['DeviceRequests'] or info['HostConfig']['NetworkMode']!='none' or info['HostConfig']['IpcMode']!='private' or info['HostConfig'].get('PidMode'):raise ValueError('CPU identity/isolation differs')
        write(cpu/'container-inspect.json',info)
        commands=[('plan',['/opt/php/bin/inference-python','/control/cpu_plan_gate.py','--plan','/data/native-plan.json','--output','/preflight/plan.json']),
                  ('simulator',['/opt/php/bin/train-python','/control/verify_snapshot_imports.py','--role','simulator','--plan','/data/native-plan.json','--output','/preflight/simulator.json']),
                  ('inference',['/opt/php/bin/inference-python','/control/verify_snapshot_imports.py','--role','inference','--plan','/data/native-plan.json','--output','/preflight/inference.json'])]
        for name,command in commands:
            argv=['docker','exec',cid,*command];entry={'name':name,'argv':argv,'started_unix':time.time()};receipt['commands'].append(entry);write(cpu/'launch.json',receipt)
            completed=subprocess.run(argv,capture_output=True,text=True,timeout=240)
            (cpu/(name+'.stdout.log')).write_text(completed.stdout);(cpu/(name+'.stderr.log')).write_text(completed.stderr)
            entry.update(returncode=completed.returncode,finished_unix=time.time());write(cpu/'launch.json',receipt)
            if completed.returncode:raise RuntimeError('Actual CPU '+name+' preflight failed; preserved raw')
        for role,expected in EXPECTED_EXTENSIONS.items():
            value=json.loads((cpu/(role+'.json')).read_text())
            if value['status']!='passed' or value['sdk']['version']!='0.1.8' or value['sdk']['sha256']!=expected or value['robot_or_dds_construction_attempts']:raise ValueError('Actual CPU SDK/constructor guard differs')
        receipt['status']='passed'
    except BaseException as error:
        receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if cid:
            receipt['owned_container_stop']=run('docker','stop','--time','5',cid,timeout=15).strip()
            receipt['owned_container_running_after_stop']=json.loads(run('docker','inspect',cid))[0]['State']['Running']
        receipt['finished_unix']=time.time();write(cpu/'launch.json',receipt)
    if receipt['owned_container_running_after_stop']:raise ValueError('CPU preflight CID still running')
    for path in sorted(cpu.iterdir()):files.append({'relative':str(path.relative_to(base)),'bytes':path.stat().st_size,'sha256':sha(path)})
    plan={'schema_version':1,'status':'prepared_only','native_started':False,'cohort':base.name,'image_id':IMAGE,'gpu_uuid':args.gpu_uuid,
          'workspace':str(workspace),'output':str(base),'container_name':'php-sdk018-commands-'+identity(str(base))[:16],
          'root_revision':source_manifest['root_revision'],'source_manifest_sha256':sha(base/'inputs/original-source-manifest.json'),
          'baseline_matrix_sha256':baseline['sha256'],'native_plan_sha256':native['plan_sha256'],'native_plan_file_sha256':sha(base/'inputs/native-plan.json'),
          'snapshot_files':sorted(files,key=lambda item:item['relative']),'mounts':mounts,'expected_sdk_extension_sha256':EXPECTED_EXTENSIONS,
          'cpu_preflight_receipt_sha256':sha(cpu/'launch.json'),'host_driver_timeout_seconds':5500,'host_observer_timeout_seconds':5600,
          'scope':'Canonical SDK018 original12 plane commands,8s/400ticks each,24workers; native DDS/depth/PD; no skill-quality assertion'}
    plan['plan_sha256']=identity(plan);write(base/'pilot-plan.json',plan)
    write(base/'preparation-status.json',{'status':'prepared_only','native_started':False,'plan_sha256':plan['plan_sha256']})
    print(json.dumps({'status':'prepared_only','plan':str(base/'pilot-plan.json'),'native_started':False,'snapshot_files':len(files),'native_plan_sha256':native['plan_sha256']}))



def verify_snapshot(base, plan):
    original = dict(plan)
    recorded = original.pop('plan_sha256')
    if identity(original) != recorded or str(base.resolve()) != plan['output'] or plan['image_id'] != IMAGE:
        raise ValueError('Pilot identity/path/image changed')
    if plan.get('native_started') is not False or plan.get('status') != 'prepared_only':
        raise ValueError('Only an untouched prepared cohort may start once')
    for item in plan['snapshot_files']:
        path = base / item['relative']
        if (not path.resolve().is_relative_to(base.resolve()) or path.is_symlink() or not path.is_file()
                or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']):
            raise ValueError('Snapshot artifact changed: ' + item['relative'])
    native_path=base/'inputs/native-plan.json'
    if sha(native_path)!=plan['native_plan_file_sha256'] or json.loads(native_path.read_text())['plan_sha256']!=plan['native_plan_sha256']:raise ValueError('Frozen native command plan changed')
    preflight=base/'host/cpu-preflight/launch.json'
    cpu=json.loads(preflight.read_text())
    if sha(preflight)!=plan['cpu_preflight_receipt_sha256'] or cpu['status']!='passed' or cpu['owned_container_running_after_stop'] or len(cpu['commands'])!=3 or any(c['returncode']!=0 for c in cpu['commands']):raise ValueError('Actual CPU-only preflight receipt invalid')
    return plan


def local_docker():
    context = run('docker', 'context', 'show').strip()
    info = json.loads(run('docker', 'context', 'inspect', context))[0]
    endpoint = os.environ.get('DOCKER_HOST') or info['Endpoints']['docker']['Host']
    if not endpoint.startswith('unix://'):
        raise ValueError('Only a local Unix Docker endpoint is permitted')
    return {'context': context, 'endpoint': endpoint}


def gpu_idle(uuid):
    entries = run('nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader').splitlines()
    if entries.count(uuid) != 1:
        raise ValueError('Explicit physical GPU UUID is not unique/present')
    processes = run('nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits')
    if any(line.split(',')[0].strip() == uuid for line in processes.splitlines() if line.strip()):
        raise ValueError('Selected physical GPU has an existing compute job; never stop it')
    return {'selected_gpu_uuid': uuid, 'matching_compute_processes': []}


def container_arguments(plan):
    argv = ['docker', 'create', '--name', plan['container_name'], '--network', 'none', '--ipc', 'private',
            '--init', '--shm-size', '8g', '--gpus', 'device=' + plan['gpu_uuid'],
            '--workdir', str(NATIVE_ROOT), '--entrypoint', '/bin/bash']
    for key, value in {'PHP_DOCKER': '1', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true',
                       'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                       'MUJOCO_EGL_DEVICE_ID': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                       'NVIDIA_DRIVER_CAPABILITIES': 'compute,utility,graphics'}.items():
        argv += ['--env', key + '=' + value]
    for mount in plan['mounts']:
        value = f"type=bind,src={mount['source']},dst={mount['destination']}"
        argv += ['--mount', value + (',readonly' if mount['readonly'] else '')]
    argv += [plan['image_id'], '-lc', 'exec sleep infinity']
    return argv


def verify_container(info, plan, container_id):
    host = info['HostConfig']
    requests = host.get('DeviceRequests', [])
    mounts = sorted((m['Source'], m['Destination'], not m['RW'], m['Type']) for m in info['Mounts'])
    expected = sorted((m['source'], m['destination'], m['readonly'], 'bind') for m in plan['mounts'])
    if (info['Id'] != container_id or info['Image'] != plan['image_id']
            or info['Name'] != '/' + plan['container_name'] or info['Config']['WorkingDir'] != str(NATIVE_ROOT)
            or host.get('NetworkMode') != 'none' or host.get('IpcMode') != 'private'
            or host.get('PidMode', '') != '' or host.get('Privileged') is not False
            or host.get('Init') is not True or host.get('ShmSize') != 8589934592
            or len(requests) != 1 or requests[0].get('DeviceIDs') != [plan['gpu_uuid']]
            or requests[0].get('Count') != 0 or mounts != expected):
        raise ValueError('Isolated container identity, namespaces, UUID, mounts or working directory differ')


def verify_host_mappings(observer, native_summary, base):
    if not observer.get('mapping_scope_complete') or observer.get('errors'):
        raise ValueError('Host observer failed or did not map both native roles')
    matches = []
    for case in native_summary['cases']:
        directory = base / 'outputs' / Path(case['output']).relative_to('/outputs')
        for role in ('simulator', 'inference'):
            entry = json.loads((directory / (role + '-process-start.json')).read_text())
            native = entry['process']
            found = [mapping for mapping in observer['command_writer_mappings']
                     if mapping['role'] == role and mapping['worker_output'] == case['output']
                     and mapping['container_tgid'] == native['pid']
                     and mapping['owner_start_time_clock_ticks'] == native['start_time_clock_ticks']]
            if len(found)!=1:
                raise ValueError('Missing exact native PID/birth→host command_writer mapping: ' + case['case_id'] + '/' + role)
            matches.append({'case_id': case['case_id'], 'role': role, 'native_entry_sha256': sha(directory / (role + '-process-start.json')),
                            'mappings': found})
    if len(matches) != 24:
        raise ValueError('Require both native workers for all12 commands')
    return matches


def execute(args):
    if not args.root_authorized_start:
        raise ValueError('Explicit root start authorization is required; prepare never starts jobs')
    base = args.plan.resolve().parent
    plan = verify_snapshot(base, json.loads(args.plan.read_text()))
    # The root lock serializes this pilot across different output directories.
    with (Path(plan['workspace']) / 'outputs/research/.local-native-GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = base / 'host/launch-receipt.json'
        if receipt_path.exists() or any((base / 'outputs').iterdir()):
            raise ValueError('Cohort already attempted; new output required, never retry in place')
        endpoint = local_docker()
        gpu = gpu_idle(plan['gpu_uuid'])
        actual_image = json.loads(run('docker', 'image', 'inspect', plan['image_id']))[0]
        if actual_image['Id'] != plan['image_id']:
            raise ValueError('Immutable candidate image not locally present')
        # Inspect an absent name; only create may reserve it atomically.
        existing = subprocess.run(['docker', 'inspect', '--type', 'container', plan['container_name']], capture_output=True, text=True)
        if existing.returncode == 0:
            raise ValueError('Pilot container name already exists; never replace or attach to it')
        receipt = {'schema_version': 1, 'status': 'starting', 'plan_sha256': plan['plan_sha256'],
                   'started_unix': time.time(), 'endpoint': endpoint, 'gpu_preflight': gpu,
                   'create_argv': container_arguments(plan), 'native_started': False}
        write(receipt_path, receipt)
        cid, observer, job = None, None, None
        stop_file = base / 'host/observer-stop'
        try:
            cid = run(*receipt['create_argv']).strip()
            if not re.fullmatch(r'[0-9a-f]{64}', cid):
                raise ValueError('Docker create did not return an exact full container ID')
            receipt['container_id'] = cid
            write(receipt_path, receipt)
            run('docker', 'start', cid)
            inspected = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
            verify_container(inspected, plan, cid)
            write(base / 'host/container-inspect.json', inspected)
            # A second idle check catches another job appearing during create.
            receipt['gpu_before_native'] = gpu_idle(plan['gpu_uuid'])
            observer_argv = [sys.executable, str(base / 'host/observe_container_pids.py'), '--container-id', cid,
                             '--expected-image', plan['image_id'], '--output', str(base / 'host/observer'),
                             '--stop-file', str(stop_file), '--interval', '0.2', '--max-seconds', str(plan['host_observer_timeout_seconds'])]
            receipt['observer_argv'] = observer_argv
            with (base / 'host/observer.log').open('x') as observer_log:
                observer = subprocess.Popen(observer_argv, stdout=observer_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 15
                while not (base / 'host/observer/launch.json').is_file():
                    if observer.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Host observer did not become ready before native start')
                    time.sleep(.1)
                command = ['docker', 'exec', cid, '/opt/php/bin/inference-python',
                           '/control/commands_executor.py', '--plan', '/data/native-plan.json',
                           '--summary', '/outputs/pilot-summary.json']
                receipt.update(status='running', native_started=True, native_start_unix=time.time(), native_argv=command)
                write(receipt_path, receipt)
                with (base / 'host/driver.log').open('x') as stream:
                    job = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
                    receipt['docker_exec_host_pid'] = job.pid
                    write(receipt_path, receipt)
                    receipt['driver_timeout_seconds'] = plan['host_driver_timeout_seconds']
                    write(receipt_path, receipt)
                    receipt['driver_returncode'] = job.wait(timeout=plan['host_driver_timeout_seconds'])
                stop_file.touch(exist_ok=False)
                receipt['observer_returncode'] = observer.wait(timeout=30)
            native = json.loads((base / 'outputs/pilot-summary.json').read_text())
            observe = json.loads((base / 'host/observer/summary.json').read_text())
            for role, expected in plan['expected_sdk_extension_sha256'].items():
                if native['sdk'][role]['sha256'] != expected or native['sdk'][role]['version'] != '0.1.8':
                    raise ValueError('Actual native SDK extension differs from CPU-verified SDK018 candidate')
            if observe['identity']['container_id']!=cid or observe['identity']['image_id']!=IMAGE or observe['identity']['started_at']!=inspected['State']['StartedAt'] or observe['stop_reason']!='stop_file':raise ValueError('Whole-run observer fixed container/birth/stop differs')
            receipt['host_native_mappings'] = verify_host_mappings(observe, native, base)
            if (receipt['driver_returncode'] != 0 or receipt['observer_returncode'] != 0 or native['status'] != 'completed'
                    or len(native['cases']) != 12 or native['remaining_native_pids'] != []
                    or any(case['status'] != 'completed' or case['policy_ticks'] != 400 for case in native['cases'])):
                raise RuntimeError('Commands did not pass all12 cases with clean native exits and400 ticks')
            receipt.update(status='completed', native_summary_sha256=sha(base / 'outputs/pilot-summary.json'),
                           observer_summary_sha256=sha(base / 'host/observer/summary.json'))
        except BaseException as error:
            receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            # Stop only the newly created fixed ID owned by this receipt. Keep
            # the stopped container and every raw output for root review.
            if observer is not None and observer.poll() is None:
                stop_file.touch(exist_ok=True)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    receipt['observer_returncode'] = observer.wait(timeout=30)
            if cid is not None:
                try:
                    info = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
                    verify_container(info, plan, cid)
                    receipt['owned_container_stop'] = run('docker', 'stop', '--time', '20', cid, timeout=35).strip()
                    info = json.loads(run('docker', 'inspect', '--type', 'container', cid))[0]
                    receipt['owned_container_running_after_stop'] = info['State']['Running']
                    if info['State']['Running']:
                        receipt['status'] = 'failed'
                    write(base / 'host/container-final-inspect.json', info)
                except BaseException as error:
                    receipt.update(status='failed', cleanup_error=f'{type(error).__name__}: {error}')
            if job is not None:
                try:
                    receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # This is our own local Docker CLI Popen, after its fixed
                    # owned container has been stopped; no other job is signalled.
                    job.terminate()
                    try:
                        receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        job.kill()
                        receipt['driver_returncode_after_container_stop'] = job.wait(timeout=5)
                    receipt.update(status='failed', cleanup_driver_cli_terminated=True)
            receipt['finished_unix'] = time.time()
            write(receipt_path, receipt)
        return 0 if receipt['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    plan = sub.add_parser('prepare')
    plan.add_argument('--workspace', type=Path, required=True)
    plan.add_argument('--context',type=Path,required=True)
    plan.add_argument('--source-manifest',type=Path,required=True)
    plan.add_argument('--dependency-plan',type=Path,required=True)
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--gpu-uuid', required=True)
    start = sub.add_parser('run')
    start.add_argument('--plan', type=Path, required=True)
    start.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    return prepare(args) if args.action == 'prepare' else execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
