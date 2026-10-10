#!/usr/bin/env python3
"""Root-operator-only prepared reload runner. Default is read-only command preview.

Explicit --execute is for root's later authorized GPU window, after SDK pilot
and the new canonical Docker. This file never creates/restarts a container.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = next((parent for parent in BASE.parents if (parent / 'wbt_training').is_dir()), Path('/workspace/php_parkour'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def capture(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    check(result.returncode == 0, result.stderr or 'read-only command failed')
    return result.stdout


def verify_inputs(plan):
    check(plan['schema_version'] == 1 and len(plan['cases']) == 5, 'exact five planned presets required')
    for item in [*plan['source_closure'], *plan['cpu_provenance'], *plan['preparation_helpers'], *(i for row in plan['cases'] for i in row['inputs'])]:
        path = Path(item['host_path'])
        check(path.is_file() and not path.is_symlink() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'frozen input changed: ' + str(path))
    check(all('--training.export-onnx' in row['native_overrides'] and row['native_overrides'][row['native_overrides'].index('--training.export-onnx') + 1] == 'False' for row in plan['cases']), 'export must stay disabled')
    verify_robot_assets(plan)


def verify_robot_assets(plan):
    root = plan.get('runtime_robot_root')
    check(root == '/outputs/teacher-preset-runtime-assets-v3/robots', 'independent writable robot root required')
    assets = plan.get('robot_assets', [])
    check(assets and len({i['relative_path'] for i in assets}) == len(assets), 'unique original URDF and meshes required')
    for item in assets:
        relative = Path(item['relative_path'])
        check(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix() == item['relative_path'], 'robot asset path escape')
        source, copied = item['source'], item['copy']
        check(copied['native_path'] == root + '/' + relative.as_posix(), 'copied robot asset outside runtime root')
        check(Path(copied['host_path']).resolve() == ROOT/'outputs/research'/copied['native_path'].removeprefix('/outputs/'), 'runtime robot host mapping differs')
        for record in (source,copied):
            path = Path(record['host_path'])
            check(path.is_file() and not path.is_symlink() and path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], 'original/copied robot asset changed')
        check(source['sha256'] == copied['sha256'] and source['bytes'] == copied['bytes'], 'robot asset copy differs')
    for row in plan['cases']:
        argv = row['native_overrides']
        check('--robot.asset.asset-root' in argv and argv[argv.index('--robot.asset.asset-root')+1] == root, 'native asset root override differs')


def container_gate(info, plan, image_id):
    check(info['Image'] == image_id and info['State']['Running'], 'canonical running image differs')
    check(info['HostConfig']['NetworkMode'] == 'none' and info['HostConfig'].get('PidMode', '') == ''
          and info['HostConfig']['IpcMode'] in ('', 'private'), 'network/PID/IPC isolation differs')
    mounts = {item['Destination']: item for item in info['Mounts']}
    check('/workspace/php_parkour' in mounts and mounts['/workspace/php_parkour']['RW'] is False, 'frozen source must be RO')
    check('/outputs' in mounts and mounts['/outputs']['RW'] is True
          and Path(mounts['/outputs']['Source']).resolve() == ROOT / 'outputs/research', 'outputs mount differs')
    check('/data/assets' in mounts and mounts['/data/assets']['RW'] is False, 'assets must be RO')
    check(not any(path.startswith('/workspace/php_parkour/') or path.startswith('/data/assets/') or path.startswith('/outputs/') for path in mounts), 'nested mounts can override verified inputs')


def build_launch(row, container_id):
    return ['docker', 'exec', '-w', '/workspace/php_parkour',
        '-e', 'CHECKPOINT=' + row['checkpoint'], '-e', 'REGISTRY=file:///data/assets/motions-locomotion',
        '-e', 'NUM_ENVS=16', '-e', 'MAX_EVAL_STEPS=100', '-e', 'LOGGER=tensorboard', '-e', 'WANDB_MODE=disabled',
        '-e', 'CUDA_VISIBLE_DEVICES=0', '-e', 'PYTHONFAULTHANDLER=1',
        container_id, '/usr/bin/timeout', '--signal=TERM', '--kill-after=30s', '600s',
        'bash', 'scripts/research/eval_quality.sh', 'teacher', row['native_output'] + '/quality.json',
        '--training.headless', 'True', '--logger.base-dir', row['native_output'],
        '--logger.video.interval', '1', '--logger.video.upload-to-wandb', 'False',
        '--robot.asset.asset-root', '/outputs/teacher-preset-runtime-assets-v3/robots']


def fingerprint(path):
    path=Path(path)
    check(path.is_file() and not path.is_symlink(), 'regular receipt artifact required')
    return {'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha(path)}


def native_path(path):
    return '/outputs/'+str(Path(path).resolve().relative_to(ROOT/'outputs/research'))


def cpu_launch(args, receipt):
    return ['docker','exec','-w','/workspace/php_parkour','-e','CUDA_VISIBLE_DEVICES=','-e','OMP_NUM_THREADS=1',
        args.container_id,'/opt/php/bin/train-python',native_path(BASE/'cpu_preflight.py'),
        '--plan',native_path(args.plan),'--output',native_path(Path(receipt).parent/'cpu-report.json')]


def inspect(args, plan):
    check(re.fullmatch(r'[0-9a-f]{64}',args.container_id) and re.fullmatch(r'sha256:[0-9a-f]{64}',args.expected_image), 'use full fixed container/image identities')
    info=json.loads(capture(['docker','inspect','--type','container',args.container_id]))[0]
    check(info['Id']==args.container_id, 'container identity differs')
    container_gate(info,plan,args.expected_image)
    return info


def verify_native_inputs(args,plan):
    records=[*plan['source_closure'],*plan['preparation_helpers'],*(i for row in plan['cases'] for i in row['inputs']),
             *(i for asset in plan['robot_assets'] for i in (asset['source'],asset['copy']))]
    expected=[{'path':i['native_path'],'sha256':i['sha256']} for i in records]
    code='import hashlib,json,pathlib,sys; assert all(hashlib.sha256(pathlib.Path(i["path"]).read_bytes()).hexdigest()==i["sha256"] for i in json.loads(sys.argv[1]))'
    capture(['docker','exec',args.container_id,'/opt/php/bin/motion-python','-c',code,json.dumps(expected)])


def validate_cpu_receipt(path, args, plan, info):
    path=Path(path)
    check(path.is_file() and not path.is_symlink(),'fresh actual CPU launch receipt required')
    receipt=json.loads(path.read_text())
    check(receipt.get('schema_version')==1 and receipt.get('status')=='passed' and type(receipt.get('returncode')) is int
          and receipt['returncode']==0, 'CPU launch failed or unknown')
    check(receipt.get('container_id')==args.container_id==info['Id']
          and receipt.get('image_id')==args.expected_image==info['Image']
          and receipt.get('container_started_at')==info['State']['StartedAt'], 'CPU container/image/restart identity differs')
    check(receipt.get('plan_sha256')==sha(args.plan)
          and receipt.get('runner_sha256')==sha(Path(__file__))
          and receipt.get('preflight_source_sha256')==sha(BASE/'cpu_preflight.py'), 'CPU source or plan changed')
    check(receipt.get('command')==cpu_launch(args,path),'CPU launch argv differs')
    for key,name in [('cpu_report','cpu-report.json'),('stdout','stdout.log'),('stderr','stderr.log')]:
        check(receipt.get(key)==fingerprint(path.parent/name),'CPU report/stdout/stderr changed')
    report=json.loads((path.parent/'cpu-report.json').read_text())
    check(report.get('status')=='passed' and report.get('plan_sha256')==sha(args.plan)
          and report.get('cuda_initialized') is False and report.get('isaac_started') is False
          and report.get('physics_verified') is False and report.get('quality_verified') is False,
          'CPU report status/scope differs')
    rows=report.get('rows',[])
    check(len(rows)==len(plan['cases'])==5,'exact five CPU rows required')
    for actual,expected in zip(rows,plan['cases']):
        pt=next(item for item in expected['inputs'] if item['native_path']==expected['checkpoint'])
        check(actual.get('preset')==expected['preset'] and actual.get('checkpoint_sha256')==pt['sha256']
              and actual.get('checkpoint_iteration')==1 and actual.get('actual_saved_contract')==expected['contract']
              and actual.get('native_parser_passed') is True and actual.get('num_envs')==16
              and actual.get('max_eval_steps')==100 and actual.get('export_onnx') is False
              and actual.get('logger_base_dir')==expected['native_output']
              and actual.get('native_overrides')==expected['native_overrides']
              and actual.get('runtime_robot_asset_root')=='/outputs/teacher-preset-runtime-assets-v3/robots'
              and actual.get('runtime_urdf')=='g1/main_mesh_arm_collision_halfspherehand.urdf', 'CPU row preset/PT/effective config differs')
    return receipt


def record_cpu_preflight(args,plan):
    check(args.cpu_preflight_receipt is not None,'--cpu-preflight-receipt is required to record CPU launch')
    before=inspect(args,plan)
    verify_native_inputs(args,plan)
    path=args.cpu_preflight_receipt.resolve()
    native_path(path)  # Require its fresh cohort beneath the outputs mount.
    check(not path.parent.exists(),'CPU receipt directory must be fresh')
    path.parent.mkdir(parents=True,exist_ok=False)
    command=cpu_launch(args,path)
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    (path.parent/'stdout.log').write_text(result.stdout)
    (path.parent/'stderr.log').write_text(result.stderr)
    receipt={'schema_version':1,'status':'passed' if result.returncode==0 else 'failed','returncode':result.returncode,
        'container_id':args.container_id,'image_id':args.expected_image,'container_started_at':before['State']['StartedAt'],
        'plan_sha256':sha(args.plan),'runner_sha256':sha(Path(__file__)), 'preflight_source_sha256':sha(BASE/'cpu_preflight.py'),
        'command':command,'stdout':fingerprint(path.parent/'stdout.log'),'stderr':fingerprint(path.parent/'stderr.log')}
    if (path.parent/'cpu-report.json').is_file(): receipt['cpu_report']=fingerprint(path.parent/'cpu-report.json')
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    check(result.returncode==0,'CPU parser failed; retain partial receipt/logs')
    verify_inputs(plan)
    verify_native_inputs(args,plan)
    after=inspect(args,plan)
    validate_cpu_receipt(path,args,plan,after)
    print(json.dumps({'status':'cpu_preflight_passed','receipt':str(path),'image_id':args.expected_image,'gpu_started':False}))
    return 0


def validate_native_quality(row):
    path = ROOT/'outputs/research'/row['native_output'].removeprefix('/outputs/')/'quality.json'
    check(path.is_file() and not path.is_symlink(), 'native exit0 without fresh quality.json is execution failure')
    report = json.loads(path.read_text())
    pt = next(i for i in row['inputs'] if i['native_path'] == row['checkpoint'])
    check(report.get('schema_version') == 1 and report.get('status') == 'completed'
          and report.get('checkpoint') == row['checkpoint'] and report.get('checkpoint_sha256') == pt['sha256']
          and report.get('checkpoint_iteration') == 1, 'native quality checkpoint/iteration differs')
    check(report.get('num_envs') == 16 and report.get('control_steps') == 100 and report.get('seed') == 42
          and report.get('registry_order') == ['file:///data/assets/motions-locomotion'], 'native quality run settings differ')
    check(report.get('native_argv') == ['--checkpoint',row['checkpoint'],*row['native_overrides']], 'native quality argv differs')
    check(report.get('finite_actions') is True and report.get('finite_root_states') is True, 'nonfinite actions or root states')
    metrics = report.get('metrics',{})
    names = {'motion/error_ref_pos','motion/error_ref_rot','motion/error_body_pos','motion/error_joint_pos'}
    check(set(metrics) == names, 'four native tracking metrics required')
    for metric in metrics.values():
        check(metric.get('samples') == 1600 and metric.get('finite') is True, 'native metric samples/finiteness differ')
        check(all(type(metric.get(k)) in (int,float) and math.isfinite(metric[k]) for k in ('mean','p95','max')), 'native metric aggregate not finite')
    check(type(report.get('failed_resets')) is int and report['failed_resets'] >= 0
          and type(report.get('timeout_resets')) is int and report['timeout_resets'] >= 0, 'native raw reset counts missing')
    check(report.get('quality_verified') is False, 'quality must remain explicitly unverified')
    saved = report.get('saved_eval_config')
    check(isinstance(saved,str) and saved.startswith(row['native_output']+'/'), 'saved config outside fresh native target')
    saved_path = ROOT/'outputs/research'/saved.removeprefix('/outputs/')
    check(fingerprint(saved_path)['sha256'] == report.get('saved_eval_config_sha256'), 'native saved config missing/changed')
    return {'quality':fingerprint(path),'saved_eval_config':fingerprint(saved_path),
            'failed_resets':report['failed_resets'],'timeout_resets':report['timeout_resets'],
            'control_steps':100,'tracking_samples_per_key':1600,'physics_verified':True,'quality_verified':False}


def execute(args, plan):
    check(args.cpu_preflight_receipt is not None,'execute requires explicit --cpu-preflight-receipt from the same actual container/image')
    info=inspect(args,plan)
    validate_cpu_receipt(args.cpu_preflight_receipt,args,plan,info)
    native_checks = [{'path': i['native_path'], 'sha256': i['sha256']} for i in [*plan['source_closure'], *(j for row in plan['cases'] for j in row['inputs'])]]
    # This container command uses stdlib only and never imports Isaac or CUDA.
    code = 'import hashlib,json,pathlib,sys; d=json.loads(sys.argv[1]); assert all(hashlib.sha256(pathlib.Path(i["path"]).read_bytes()).hexdigest()==i["sha256"] for i in d); assert all(not pathlib.Path(p).exists() for p in json.loads(sys.argv[2]))'
    capture(['docker', 'exec', args.container_id, '/opt/php/bin/motion-python', '-c', code, json.dumps(native_checks), json.dumps([row['native_output'] for row in plan['cases']])])
    check(not args.output.exists(), 'use fresh output; failed attempts are not overwritten')
    lock_path = ROOT / 'outputs/research/.teacher-preset-reload.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Read-only GPU query occurs only in explicitly authorized execute mode.
        active = capture(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader']).strip()
        check(not active, 'GPU compute processes still active; do not start reload')
        args.output.mkdir(parents=True, exist_ok=False)
        results = []
        for row in plan['cases']:
            verify_inputs(plan)
            command = build_launch(row, args.container_id)
            log_path = args.output / (row['preset'] + '.log')
            started = datetime.datetime.now(datetime.timezone.utc).isoformat()
            failure = None
            with log_path.open('x') as stream:
                try:
                    process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=660)
                    returncode = process.returncode
                except (OSError, subprocess.TimeoutExpired) as error:
                    returncode = None
                    failure = type(error).__name__ + ': ' + str(error)
            try:
                verify_inputs(plan)
            except (ValueError, OSError) as error:
                failure = 'Inputs changed during reload: ' + str(error)
            evidence = None
            if returncode == 0 and failure is None:
                try:
                    evidence = validate_native_quality(row)
                except (ValueError,OSError,KeyError,TypeError) as error:
                    failure = 'Native evidence validation failed: ' + str(error)
            result = {'preset': row['preset'], 'started_utc': started, 'command': command, 'returncode': returncode,
                'status': 'native_exit_zero_pending_evidence_validation' if returncode == 0 and failure is None else 'execution_failed', 'error': failure,
                'log_sha256': sha(log_path), 'native_quality': row['native_output'] + '/quality.json', 'native_evidence':evidence, 'quality_verified': False}
            results.append(result)
            (args.output / 'execution.json').write_text(json.dumps({'status': 'running', 'cases': results, 'quality_verified': False}, indent=2) + '\n')
            # Timeout/other nonzero preserves output and stops; no new physics
            # starts while a failed child's cleanup remains to be inspected.
            if returncode != 0 or failure is not None:
                break
        status = 'native_exits_zero_pending_evidence_validation' if len(results) == 5 and all(r['status'] == 'native_exit_zero_pending_evidence_validation' for r in results) else 'execution_failed'
        (args.output / 'execution.json').write_text(json.dumps({'status': status, 'cases': results, 'quality_verified': False}, indent=2) + '\n')
        return 0 if status.startswith('native_exits_zero') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=BASE / 'plan.json')
    parser.add_argument('--container-id', default='<NEW_CANONICAL_FULL_CONTAINER_ID>')
    parser.add_argument('--expected-image', default='<NEW_CANONICAL_IMAGE_SHA256>')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/research/teacher-preset-reload-execution-v3-01')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--record-cpu-preflight',action='store_true')
    parser.add_argument('--cpu-preflight-receipt',type=Path)
    args = parser.parse_args()
    parser.error('--execute and --record-cpu-preflight are exclusive') if args.execute and args.record_cpu_preflight else None
    plan = json.loads(args.plan.read_text())
    verify_inputs(plan)
    if args.record_cpu_preflight:
        return record_cpu_preflight(args,plan)
    if not args.execute:
        print(json.dumps({'status': 'prepared_not_executed', 'gpu_started': False, 'commands': [build_launch(row, args.container_id) for row in plan['cases']]}, indent=2))
        return 0
    return execute(args, plan)


if __name__ == '__main__':
    raise SystemExit(main())
