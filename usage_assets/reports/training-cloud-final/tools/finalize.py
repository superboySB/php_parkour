from __future__ import annotations
import hashlib,json,math,os,pathlib,time,traceback
ROOT=pathlib.Path('/outputs/final-training-acceptance')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8388608),b''):h.update(b)
 return h.hexdigest()
while True:
 try:s=json.loads((ROOT/'driver-status.json').read_text())
 except (OSError,ValueError):time.sleep(5);continue
 if s['status']!='running':break
 time.sleep(5)
if s['status']!='failed' or 'Expected seven training weight update reports' not in s.get('error',''):
 raise SystemExit('Refusing to finalize an unexpected driver status/error; original evidence preserved')
(ROOT/'driver-initial-status.json').write_text(json.dumps(s,indent=2)+'\n')
try:
 manifests={p.stem:json.loads(p.read_text()) for p in (ROOT/'smoke/manifests').glob('*.json')}
 assert len(manifests)==22 and all(m['status']=='passed' for m in manifests.values())
 weights=s['weight_update_reports'];assert len(weights)==13
 for w in weights:
  d=json.loads(pathlib.Path(w['report']).read_text())
  assert d['status']=='passed' and d['nontrivial_policy_weight_change_verified']
  assert d['before']['iteration']==0 and d['after']['iteration']==1
  assert sha(pathlib.Path(d['before']['path']))==d['before']['sha256']
  assert sha(pathlib.Path(d['after']['path']))==d['after']['sha256']
 assert s['pipeline_stages_verified']==22 and len(s['quality_reports'])==7
 teacher=json.loads((ROOT/'smoke/teacher-onnx-validation/summary.json').read_text())
 assert teacher['status']=='passed' and len(teacher['teachers'])==5 and sum(t['cpu_cases'] for t in teacher['teachers'])==60
 from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
 events=[];by_path={}
 for event in sorted((ROOT/'smoke').rglob('events.out.tfevents.*')):
  a=EventAccumulator(str(event),size_guidance={'scalars':0});a.Reload()
  series={tag:a.Scalars(tag) for tag in a.Tags()['scalars']}
  assert all(math.isfinite(x.value) for v in series.values() for x in v)
  row={'path':str(event),'sha256':sha(event),'bytes':event.stat().st_size,'scalar_tags':list(series),'series':{tag:[{'step':x.step,'value':x.value} for x in v] for tag,v in series.items()},'all_scalars_finite':True}
  events.append(row);by_path[str(event)]=row
 training=[]
 for label,m in manifests.items():
  if 'checkpoint' not in m or label.startswith(('eval-','export-')):continue
  candidates=list(pathlib.Path(m['checkpoint']).parent.glob('events.out.tfevents.*'));assert len(candidates)==1
  row=by_path[str(candidates[0])];series=row['series']
  losses=[tag for tag in series if tag.startswith('Loss/')];assert losses
  for tag in losses+['Train/mean_reward']:
   assert {0,1}.issubset({v['step'] for v in series[tag]}),(label,tag)
  training.append({'label':label,'path':row['path'],'sha256':row['sha256'],'loss_tags':losses,'loss_reward_steps_0_1_verified':True,'all_scalars_finite':True})
 assert len(training)==13
 (ROOT/'independent-validation/tensorboard.json').write_text(json.dumps({'status':'passed','events':events,'training_runs':training},indent=2)+'\n')
 s['tensorboard_events_verified']=len(events);s['training_tensorboard_runs_verified']=13
 for label in ('export-student-pure','export-student-finetune'):
  reports=manifests[label]['onnx_validation_reports'];assert reports
  for entry in reports:
   d=json.loads(pathlib.Path(entry['report']).read_text());assert d['status']=='passed' and len(d['cases'])==30
 s['student_onnx_cpu_cases_per_kind']=30
 source=pathlib.Path('/workspace/php_parkour');before=json.loads((ROOT/'source-critical-before.json').read_text())
 after={p:sha(source/p) for p in before};assert before==after
 (ROOT/'source-critical-after.json').write_text(json.dumps(after,indent=2)+'\n')
 full=json.loads((source/'source-manifest.json').read_text())
 for item in full['files']:
  p=source/item['path'];actual=hashlib.sha256(os.readlink(p).encode()).hexdigest() if item['symlink'] else sha(p)
  assert actual==item['sha256'],item['path'];assert p.lstat().st_mode&0o777==item['mode'],item['path']
 full_report={'status':'passed','source_tree_sha256':full['source_tree_sha256'],'git_head':full['git_head'],'files_verified':len(full['files']),'hashes_and_modes_match':True}
 (ROOT/'source-snapshot-after.json').write_text(json.dumps(full_report,indent=2)+'\n')
 s['source_critical_sha_unchanged']=True;s['source_snapshot_verified_files']=len(full['files'])
 s['driver_bookkeeping_correction']='Initial standalone driver counted 13 native training stages but asserted 7. Preserved initial failure; all 13 weight checks passed. Independent finalizer verified completed artifacts without repeating training, evaluation or ONNX inference.'
 s['initial_driver_error']=s.pop('error');s['status']='passed';s['final_validation_finished_unix']=time.time()
except Exception:
 s['status']='failed';s['finalizer_error']=traceback.format_exc();print(s['finalizer_error'],flush=True)
finally:
 (ROOT/'driver-final-status.json').write_text(json.dumps(s,indent=2)+'\n')
 (ROOT/'driver-status.json').write_text(json.dumps(s,indent=2)+'\n')
 print('Finalizer: '+s['status'],flush=True)
if s['status']!='passed':raise SystemExit(1)
