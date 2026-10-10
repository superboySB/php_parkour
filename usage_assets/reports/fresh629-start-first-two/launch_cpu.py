#!/usr/bin/env python3
import datetime,json,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;BASE=OUT.parent/'fresh629-sdk018-6cb2ae2-prepared02'
IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
name='php-first2-cpu-audit-'+str(time.time_ns())
argv=['docker','create','--name',name,'--runtime','runc','--network','none','--ipc','private','--init','--shm-size','1g','--workdir','/workspace/php_parkour','--entrypoint','/opt/php/bin/inference-python']
for key,value in {'CUDA_VISIBLE_DEVICES':'','NVIDIA_VISIBLE_DEVICES':'void','PYTHONDONTWRITEBYTECODE':'1','WANDB_MODE':'disabled','WANDB_DISABLED':'true','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}.items():argv+=['--env',key+'='+value]
for src,dst,ro in [(BASE/'source','/workspace/php_parkour',True),(BASE/'inputs','/data',True),(BASE/'outputs','/outputs',True),(BASE,'/cohort',True),(OUT,'/audit',False)]:argv+=['--mount','type=bind,src='+str(src)+',dst='+dst+(',readonly' if ro else '')]
argv += [IMAGE,'/audit/audit_cpu.py']
receipt={'schema_version':1,'scope':'Only independent CPU hashing/receipt validation/full MP4 decode; no native/GPU/DDS','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'create_argv':argv}
def save(): (OUT/'cpu-container-launch.json').write_text(json.dumps(receipt,indent=2)+'\n')
create=subprocess.run(argv,capture_output=True,text=True,check=True);cid=create.stdout.strip();receipt['container_id']=cid;save()
try:
 info=json.loads(subprocess.run(['docker','inspect',cid],capture_output=True,text=True,check=True).stdout)[0]
 assert info['Image']==IMAGE and info['HostConfig']['Runtime']=='runc' and not info['HostConfig'].get('DeviceRequests') and info['HostConfig']['NetworkMode']=='none'
 (OUT/'cpu-container-inspect-before.json').write_text(json.dumps(info,indent=2)+'\n')
 with (OUT/'cpu-stdout.log').open('x') as out,(OUT/'cpu-stderr.log').open('x') as err:
  p=subprocess.run(['docker','start','--attach',cid],stdout=out,stderr=err,timeout=300)
 receipt['start_attach_returncode']=p.returncode
finally:
 final=json.loads(subprocess.run(['docker','inspect',cid],capture_output=True,text=True,check=True).stdout)[0]
 assert final['Id']==cid and final['Image']==IMAGE
 if final['State']['Running']:
  receipt['owned_cpu_stop']=subprocess.run(['docker','stop','--time','5',cid],capture_output=True,text=True).returncode
  final=json.loads(subprocess.run(['docker','inspect',cid],capture_output=True,text=True,check=True).stdout)[0]
 (OUT/'cpu-container-inspect-after.json').write_text(json.dumps(final,indent=2)+'\n')
 receipt['owned_cpu_running_after']=final['State']['Running'];receipt['container_exitcode']=final['State']['ExitCode'];receipt['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
print(json.dumps({'container_id':cid,'returncode':receipt['start_attach_returncode'],'container_exitcode':receipt['container_exitcode'],'running':receipt['owned_cpu_running_after']}))
raise SystemExit(receipt['container_exitcode'])
