#!/usr/bin/env python3
"""Read-only transfer of genuine completed pure-student events, manifest and YAML."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

SSH = ['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
       '-o', 'ControlMaster=auto', '-o', 'ControlPersist=10m', '-o', 'ControlPath=~/.ssh/php-parkour-%C']
REMOTE = r'''import hashlib,json,stat
from pathlib import Path
root=Path('/diff/dzp_is_sb/php-parkour-research/outputs')
def fp(p):
 if any(x.is_symlink() for x in (p,*p.parents)) or not stat.S_ISREG(p.stat().st_mode):raise ValueError('Regular original required')
 a=p.stat();h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8388608),b''):h.update(b)
 z=p.stat()
 if (a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns):raise ValueError('Original changed while reading')
 return {'path':str(p),'bytes':z.st_size,'sha256':h.hexdigest()}
manifest=root/'official-full/official/manifests/student-pure.json';mf=fp(manifest);raw=manifest.read_bytes();m=json.loads(raw)
if len(raw)!=mf['bytes'] or hashlib.sha256(raw).hexdigest()!=mf['sha256']:raise ValueError('Manifest changed')
if not(m['label']=='student-pure' and m['profile']=='official' and m['status']=='passed' and type(m['returncode']) is int and m['returncode']==0 and type(m['checkpoint_iteration']) is int and m['checkpoint_iteration']==9999 and m['finished_utc']):raise ValueError('Actual official final pure manifest required')
checkpoint=Path(m['checkpoint']);prefix=Path('/outputs/official-full/official/student-pure/PHP-research')
if '..' in checkpoint.parts or not checkpoint.is_relative_to(prefix) or len(checkpoint.relative_to(prefix).parts)!=2 or checkpoint.name!='model_09999.pt':raise ValueError('Original run identity differs')
run=root/checkpoint.parent.relative_to('/outputs');events=sorted(run.glob('events.out.tfevents.*'))
if not events:raise ValueError('Original events missing')
files=[dict(fp(manifest),role='native_manifest',basename=manifest.name)]
for event in events:files.append(dict(fp(event),role='event',basename=event.name,native_path=str(checkpoint.parent/event.name)))
config=run/'config.yaml'
if not config.is_file():raise ValueError('Original saved YAML missing')
files.append(dict(fp(config),role='configuration',basename=config.name,native_path=str(checkpoint.parent/config.name)))
if fp(manifest)!=mf or [p.name for p in sorted(run.glob('events.out.tfevents.*'))]!=[p.name for p in events]:raise ValueError('Original identity/set changed')
print(json.dumps({'status':'genuine_pure_final_original_files','native_run_directory':str(checkpoint.parent),'checkpoint_sha256':m['checkpoint_sha256'],'files':files}))
'''

def fp(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(8388608),b''):h.update(data)
    return {'path':str(path.absolute()),'bytes':path.stat().st_size,'sha256':h.hexdigest()}

def main():
    base=Path('outputs/research/official-full/student-pure-final-curves-input-01').absolute()
    assert not base.exists();base.mkdir();artifacts=base/'artifacts';artifacts.mkdir();commands=[]
    def invoke(label,argv,input_data=None):
        result=subprocess.run(argv,input=input_data,capture_output=True)
        out=base/(label+'.stdout');err=base/(label+'.stderr');out.write_bytes(result.stdout);err.write_bytes(result.stderr)
        commands.append({'label':label,'argv':argv,'actual_wait':result.returncode,'stdout':fp(out),'stderr':fp(err)})
        assert result.returncode==0, 'Original transfer command failed; partial retained'
        return result.stdout
    receipt={'status':'running','remote_read_only':True,'scientific_files_modified':False,'commands':commands}
    try:
        before=json.loads(invoke('remote-before',SSH+['tencent-231','python3 -B -'],REMOTE.encode()))
        receipt['remote_before']=before
        for index,row in enumerate(before['files']):
            assert Path(row['basename']).name==row['basename'] and '..' not in row['basename'] and row['basename']
            target=artifacts/row['basename'];assert not target.exists()
            invoke('copy-'+str(index),['rsync','-a','--partial','--protect-args','--checksum','-e',shlex.join(SSH),'tencent-231:'+row['path'],str(target)])
            actual=fp(target);assert actual['bytes']==row['bytes'] and actual['sha256']==row['sha256']
        after=json.loads(invoke('remote-after',SSH+['tencent-231','python3 -B -'],REMOTE.encode()))
        assert before==after
        assert sorted(x.name for x in artifacts.iterdir())==sorted(r['basename'] for r in before['files'])
        receipt.update(status='passed_genuine_pure_final_events_transfer',remote_after=after,local_files=[fp(p) for p in sorted(artifacts.iterdir())])
    except Exception as error:
        receipt.update(status='failed_partial_preserved',error=type(error).__name__+': '+str(error))
    (base/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'path':str(base),'files':len(receipt.get('local_files',[]))}))
    return 0 if receipt['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
