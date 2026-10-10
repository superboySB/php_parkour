#!/usr/bin/env python3
"""Only a new runc/network-none/GPU-hidden CPU unittest container. No native GUI."""
from __future__ import annotations
import argparse,json,os,secrets,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
from common import fingerprint,write
from host_runner import IMAGE,PROJECT,endpoint


def call(argv):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=120)
    if r.returncode:raise RuntimeError(f'{argv[:3]}: {r.returncode}: {r.stderr}')
    return r.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    here=Path(__file__).resolve().parent;out=args.output.resolve();out.mkdir(exist_ok=False)
    context=PROJECT/'outputs/research/sdk018-canonical-build-6cb2ae2/context'
    before={p.name:fingerprint(p) for p in sorted(here.glob('*.py'))}
    report={'scope':'CPU fixtures and an ordinary stdlib PTY child only; no Xserver/GUI/SDK objects/DDS/native/GPU',
            'started_unix':time.time(),'endpoint':endpoint(),'source_before':before,'image_id':IMAGE,'status':'running'}
    cid=None;name='php-reset-allkeys-cpu-'+secrets.token_hex(8)
    def inspect_owned():
        obj=json.loads(call(['docker','inspect',cid]))[0];host=obj['HostConfig']
        if (obj['Id']!=cid or obj['Name']!='/'+name or obj['Image']!=IMAGE or host['Runtime']!='runc'
                or host['NetworkMode']!='none' or host.get('DeviceRequests') or host.get('PidMode')
                or host['IpcMode']!='private' or host['Privileged']):raise ValueError('CPU-only exact own container identity differs')
        return obj
    try:
        argv=['docker','create','--name',name,'--runtime','runc','--network','none','--ipc','private','--init',
            '--shm-size','1g','--workdir','/workspace/php_parkour','--entrypoint','/bin/bash',
            '--env','CUDA_VISIBLE_DEVICES=','--env','NVIDIA_VISIBLE_DEVICES=void','--env','PYTHONDONTWRITEBYTECODE=1',
            '--env','WANDB_MODE=disabled','--mount',f'type=bind,src={context},dst=/workspace/php_parkour,readonly',
            '--mount',f'type=bind,src={here},dst=/controls,readonly','--mount',f'type=bind,src={out},dst=/evidence',
            IMAGE,'-lc','exec sleep infinity']
        report['create_argv']=argv;cid=call(argv).strip();report['container_id']=cid
        write(out/'created-inspect.json',inspect_owned());call(['docker','start',cid]);write(out/'running-inspect.json',inspect_owned())
        argv=['docker','exec',cid,'/opt/php/bin/inference-python','/controls/run_cpu_tests.py','--output','/evidence/tests']
        report['test_argv']=argv;write(out/'launch.json',report)
        r=subprocess.run(argv,capture_output=True,text=True,timeout=120)
        (out/'stdout.txt').write_text(r.stdout);(out/'stderr.txt').write_text(r.stderr);report['returncode']=r.returncode
        if r.returncode:raise RuntimeError('CPU tests returned nonzero')
        report['status']='passed'
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
    finally:
        if cid:
            try:
                inspect_owned();call(['docker','stop','--timeout','10',cid]);after=inspect_owned();write(out/'stopped-inspect.json',after)
                report['running_after_stop']=after['State']['Running']
                if report['running_after_stop']:raise RuntimeError('Own CPU container remains running')
                call(['docker','rm',cid]);report['own_container_removed']=True
            except BaseException as error:report.update(status='failed',cleanup_error=f'{type(error).__name__}: {error}')
        report['source_after']={p.name:fingerprint(p) for p in sorted(here.glob('*.py'))}
        if report['source_after']!=before:report.update(status='failed',source_changed=True)
        report['finished_unix']=time.time();write(out/'launch.json',report)
    print(json.dumps({'status':report['status'],'returncode':report.get('returncode'),'receipt':str(out/'launch.json')}))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
