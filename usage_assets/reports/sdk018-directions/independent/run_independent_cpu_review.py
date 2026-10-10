"""Fresh no-GPU Docker terminal evidence review; never attaches native workers."""
import hashlib,json,re,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent.parent.parent
BASE=HERE.parent/'commands12-sdk018-6cb2ae2-prepared01';OUT=HERE/'actual-independent-review'
IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
def call(argv,timeout=30):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
r=json.loads((BASE/'host/launch-receipt.json').read_text())
if r['status']!='completed' or r['owned_container_running_after_stop'] or r['driver_returncode']!=0:raise ValueError('Wait for actual native complete/GPU released; no CPU review before terminal')
OUT.mkdir(exist_ok=False);cid=None
create=['docker','create','--name','php-commands12-independent-cpu-'+hashlib.sha256(str(OUT).encode()).hexdigest()[:12],
        '--runtime','runc','--network','none','--ipc','private','--init','--shm-size','1g','--env','CUDA_VISIBLE_DEVICES=',
        '--env','NVIDIA_VISIBLE_DEVICES=void','--env','PYTHONDONTWRITEBYTECODE=1','--workdir','/workspace/php_parkour','--entrypoint','/bin/bash']
for source,target,ro in [(BASE,'/cohort',True),(BASE/'source','/workspace/php_parkour',True),(BASE/'inputs','/data',True),
                         (BASE/'outputs','/outputs',True),(HERE,'/verify',True),(OUT,'/review',False)]:
    create+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
create+=[IMAGE,'-lc','exec sleep 900'];receipt={'status':'starting','native_started':False,'create_argv':create,'started_unix':time.time(),
    'helper_sha256':hashlib.sha256((HERE/'verify_actual.py').read_bytes()).hexdigest()};write(OUT/'launch.json',receipt)
try:
    cid=call(create).strip()
    if not re.fullmatch('[0-9a-f]{64}',cid):raise ValueError('Full exact new CPU CID required')
    receipt['container_id']=cid;call(['docker','start',cid]);info=json.loads(call(['docker','inspect',cid]))[0]
    if info['Id']!=cid or info['Image']!=IMAGE or info['HostConfig']['Runtime']!='runc' or info['HostConfig']['DeviceRequests'] or info['HostConfig']['NetworkMode']!='none' or info['HostConfig']['IpcMode']!='private' or info['HostConfig'].get('PidMode'):raise ValueError('Actual CPU namespace/device/image differs')
    write(OUT/'container-inspect.json',info)
    argv=['docker','exec',cid,'/opt/php/bin/inference-python','/verify/verify_actual.py','--output','/review/report.json'];receipt['argv']=argv
    done=subprocess.run(argv,capture_output=True,text=True,timeout=600)
    (OUT/'stdout.log').write_text(done.stdout);(OUT/'stderr.log').write_text(done.stderr);receipt['returncode']=done.returncode
    if done.returncode:raise RuntimeError('Independent actual CPU verification failed; preserved raw')
    receipt['status']='passed'
except BaseException as error:receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
finally:
    if cid:
        info=json.loads(call(['docker','inspect',cid]))[0]
        if info['Id']!=cid or info['Image']!=IMAGE:raise ValueError('Refuse stop foreign changed CPU identity')
        receipt['owned_container_stop']=call(['docker','stop','--time','5',cid]);receipt['owned_container_running_after_stop']=json.loads(call(['docker','inspect',cid]))[0]['State']['Running']
    receipt['finished_unix']=time.time();write(OUT/'launch.json',receipt)
print(json.dumps({'status':receipt['status'],'report':str(OUT/'report.json')}))
