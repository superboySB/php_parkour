#!/usr/bin/env python3
"""Read existing mixed-student evaluation files and stream a SHA-bound tar; no writes."""
import hashlib,io,json,pathlib,stat,sys,tarfile,time
ROOT=pathlib.Path('/diff/dzp_is_sb/php-parkour-research/outputs')
def require(ok,msg):
 if not ok:raise ValueError(msg)
def actual(native):
 p=pathlib.Path(native);require(p.is_absolute() and '..' not in p.parts and p.is_relative_to('/outputs/official-full/official'),'invalid native path')
 result=ROOT/p.relative_to('/outputs');require(not any(x.is_symlink() for x in (result,*result.parents)) and stat.S_ISREG(result.stat().st_mode),'regular no-symlink source required');return result
manifest_native='/outputs/official-full/official/manifests/eval-student-finetune.json'
train_native='/outputs/official-full/official/manifests/student-finetune.json'
m=json.loads(actual(manifest_native).read_bytes());q=json.loads(actual(m['evaluation_quality_report']).read_bytes())
require(m['status']=='passed' and m['returncode']==0 and m['label']=='eval-student-finetune','native eval final0 required')
paths=[manifest_native,train_native,m['evaluation_quality_report'],q['saved_eval_config'],m['log']]+m['evaluation_tensorboard_events']+[x['path'] for x in m['evaluation_videos']]
require(len(paths)==len(set(paths)),'duplicate remote inputs')
def fingerprint(native):
 p=actual(native);st=p.stat();h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''):h.update(c)
 after=p.stat();require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'source changed during hashing')
 return {'native_path':native,'actual_remote_path':str(p),'bytes':st.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(st.st_mode),'path':'/artifacts/'+str(pathlib.Path(native).relative_to('/outputs'))}
before=[fingerprint(p) for p in paths]
all_video_files=sorted('/outputs/'+str(p.relative_to(ROOT)) for p in (ROOT/'official-full/official/eval-student-finetune').rglob('*.mp4'))
require(set(all_video_files)=={x['path'] for x in m['evaluation_videos']},'directory/native-described video set differs')
started=time.time()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for native in paths:
  archive.add(actual(native),arcname='artifacts/'+str(pathlib.Path(native).relative_to('/outputs')),recursive=False)
 after=[fingerprint(p) for p in paths];require(before==after,'remote source changed during transfer')
 receipt={'schema_version':1,'status':'read_only_transfer_complete','started_unix':started,'finished_unix':time.time(),'remote_inputs_before':before,'remote_inputs_after':after,'remote_inputs_unchanged':True,'all_video_files':all_video_files,'native_described_video_count':len(m['evaluation_videos']),'quality_bound_video_count':len(q['videos']),'selected_files':len(paths),'scope':'Read-only existing final mixed-student evidence; no training, evaluation or source mutation.'}
 raw=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode();info=tarfile.TarInfo('transfer/remote-receipt.json');info.size=len(raw);info.mode=0o644;archive.addfile(info,io.BytesIO(raw))
