#!/usr/bin/env python3
"""Retain own actual existing CPU Docker exec and typed before/after inspect."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour')
REPRO=ROOT/'outputs/research/reproduction-20261015'
OUT=REPRO/'local-checks/first-lowstep-boundary-cpu-host-01'
CID='8b75023251acd7fa4bc982a01b6d12d320baf6e291191e141d123da4e3ba9394'
IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
SCRIPT=REPRO/'lowstep_boundary_media_cpu.py'

def fp(p):
    raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def main():
    OUT.mkdir(exist_ok=False);commands=[]
    def run(argv,label):
        started=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (OUT/(label+'.stdout.raw')).open('xb') as stdout,(OUT/(label+'.stderr.raw')).open('xb') as stderr:
            child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            birth=Path(f'/proc/{child.pid}/stat').read_text();code=child.wait()
        row={'argv':argv,'child_pid':child.pid,'child_stat':birth,'actual_wait_returncode':code,'started_utc':started,
             'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stdout':fp(OUT/(label+'.stdout.raw')),'stderr':fp(OUT/(label+'.stderr.raw'))}
        commands.append(row);(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        return row
    def inspect(label):
        row=run(['docker','inspect','--type','container',CID],label);assert row['actual_wait_returncode']==0
        value=json.loads(Path(row['stdout']['path']).read_bytes());assert len(value)==1;v=value[0]
        env=dict(x.split('=',1) for x in v['Config']['Env'] if '=' in x);h=v['HostConfig']
        assert v['Id']==CID and v['Image']==IMAGE and v['State']['Running'] is True
        assert h['Runtime']=='runc' and h['NetworkMode']=='none' and not h.get('DeviceRequests') and not h.get('Privileged')
        assert env.get('NVIDIA_VISIBLE_DEVICES')=='void' and env.get('CUDA_VISIBLE_DEVICES')==''
        assert any(m['Destination']=='/workspace/php_parkour' and m['Source']==str(ROOT) and m['RW'] is False for m in v['Mounts'])
        return v
    before=inspect('inspect-before');source_before=fp(SCRIPT)
    command=run(['docker','exec','-e','PYTHONDONTWRITEBYTECODE=1',CID,'python3','-B','/workspace/php_parkour/outputs/research/reproduction-20261015/lowstep_boundary_media_cpu.py'],'docker-exec')
    after=inspect('inspect-after');assert before==after and source_before==fp(SCRIPT)
    receipt={'scope':'Own actual existing CPU Docker exec only. Repo RO with existing independent local-checks RW submount, no GPU/network or simulator. No container start/stop/config change.',
             'container_id':CID,'container_started_at':before['State']['StartedAt'],'actual_wait_returncode':command['actual_wait_returncode'],
             'source_before':source_before,'source_after':fp(SCRIPT),'commands':commands,'container_before_after_equal':before==after}
    (OUT/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'actual_wait_returncode':command['actual_wait_returncode'],'container_started_at':receipt['container_started_at'],'execution':fp(OUT/'execution.json')}))
    return int(command['actual_wait_returncode']!=0)
if __name__=='__main__':raise SystemExit(main())
