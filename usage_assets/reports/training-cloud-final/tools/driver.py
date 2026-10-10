from __future__ import annotations
import hashlib,json,math,os,pathlib,subprocess,threading,time,traceback

ROOT=pathlib.Path('/outputs/final-training-acceptance')
SOURCE=pathlib.Path('/workspace/php_parkour')
ROOT.mkdir(exist_ok=False)
launch=json.loads(pathlib.Path('/outputs/tools/final-acceptance-launch.json').read_text())
(ROOT/'launch.json').write_text(json.dumps(launch,indent=2)+'\n')
started=time.time();stop=threading.Event()
status={'status':'running','started_unix':started,'scope':'Final-image/cloud-source 22-stage bounded smoke only; not full training schedules or policy quality','stages':[]}

def save():
 p=ROOT/'driver-status.tmp';p.write_text(json.dumps(status,indent=2)+'\n');p.replace(ROOT/'driver-status.json')

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()

critical=['scripts/research/run_training_acceptance.sh','scripts/research/train_pipeline.py','scripts/research/eval_quality.py','scripts/research/validate_teacher_exports.py','scripts/research/verify_weight_update.py','wbt_training/config_values/experiment.py']
before={p:sha(SOURCE/p) for p in critical}
(ROOT/'source-critical-before.json').write_text(json.dumps(before,indent=2)+'\n')

def monitor():
 previous={}
 with (ROOT/'gpu.csv').open('w') as f:
  f.write('unix,memory_used_mib,utilization_percent\n')
  while not stop.is_set():
   r=subprocess.run(['nvidia-smi','-i',launch['gpu_uuid'],'--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True)
   if r.returncode==0:
    memory,utilization=map(int,r.stdout.strip().split(','));f.write(f'{time.time()},{memory},{utilization}\n');f.flush()
   current=[]
   for p in sorted((ROOT/'smoke/manifests').glob('*.json')):
    try:d=json.loads(p.read_text())
    except (OSError,ValueError):continue
    current.append({'label':d['label'],'status':d['status'],'elapsed_seconds':d.get('elapsed_seconds'),'error':d.get('error')})
    if previous.get(d['label'])!=d['status']:
     print(f"Stage {d['label']}: {d['status']}",flush=True);previous[d['label']]=d['status']
   status['stages']=current;status['elapsed_seconds']=time.time()-started;save()
   stop.wait(1)

thread=threading.Thread(target=monitor,daemon=True);thread.start()
try:
 with (ROOT/'pipeline.log').open('w') as f:
  r=subprocess.run(launch['command'],cwd=SOURCE,env=os.environ|launch['environment'],stdout=f,stderr=subprocess.STDOUT)
 status['pipeline_returncode']=r.returncode
 if r.returncode:raise RuntimeError('Acceptance pipeline failed; see running/failed stage and pipeline.log. Frozen source preserved.')
 manifests={p.stem:json.loads(p.read_text()) for p in (ROOT/'smoke/manifests').glob('*.json')}
 if len(manifests)!=22 or any(m['status']!='passed' for m in manifests.values()):raise RuntimeError('Expected exactly 22 passed stage manifests')
 status['pipeline_stages_verified']=22
 qualities=[]
 for label,m in manifests.items():
  if not label.startswith('eval-'):continue
  q=json.loads(pathlib.Path(m['evaluation_quality_report']).read_text())
  if len(q['metrics'])!=4 or not all(x['finite'] and x['samples']==250*q['num_envs'] for x in q['metrics'].values()):raise RuntimeError('Quality sample contract failed: '+label)
  if q['control_steps']!=250 or not q['finite_actions'] or not q['finite_root_states'] or not q['videos'] or not q['tensorboard_events']:raise RuntimeError('Incomplete quality artifacts: '+label)
  if sha(pathlib.Path(m['evaluation_quality_report']))!=m['evaluation_quality_sha256']:raise RuntimeError('Quality hash mismatch: '+label)
  for v in q['videos']:
   if sha(pathlib.Path(v['path']))!=v['sha256'] or pathlib.Path(v['path']).stat().st_mtime<started:raise RuntimeError('Video freshness/hash mismatch')
  qualities.append({'label':label,'quality_report':m['evaluation_quality_report'],'quality_sha256':m['evaluation_quality_sha256'],'metrics':q['metrics'],'failed_resets':q['failed_resets'],'timeout_resets':q['timeout_resets'],'videos':q['videos'],'tensorboard_events':q['tensorboard_events']})
 if len(qualities)!=7:raise RuntimeError('Expected 7 teacher/student evaluation quality reports')
 status['quality_reports']=qualities;save()
 validation=ROOT/'independent-validation';validation.mkdir()
 cmd=['/opt/php/bin/train-python','scripts/research/validate_teacher_exports.py','--output',str(ROOT),'--profile','smoke']
 with (validation/'teacher-onnx.log').open('w') as f:subprocess.run(cmd,cwd=SOURCE,stdout=f,stderr=subprocess.STDOUT,check=True)
 teacher=json.loads((ROOT/'smoke/teacher-onnx-validation/summary.json').read_text())
 if teacher['status']!='passed' or sum(t['cpu_cases'] for t in teacher['teachers'])!=60:raise RuntimeError('Expected 60 teacher ORT cases')
 status['teacher_onnx_cpu_cases']=60;save()
 weights=[];events=[]
 for label,m in manifests.items():
  if not (label.startswith('teacher-') or label.startswith('student-')):continue
  after=pathlib.Path(m['checkpoint']);before_pt=after.parent/'model_00000.pt'
  if after.name!='model_00001.pt':raise RuntimeError('Two-iteration smoke did not finish at model1')
  target=validation/f'{label}-weight-update.json'
  with (validation/f'{label}-weight-update.log').open('w') as f:
   subprocess.run(['/opt/php/bin/train-python','scripts/research/verify_weight_update.py','--before',str(before_pt),'--after',str(after),'--output',str(target)],cwd=SOURCE,stdout=f,stderr=subprocess.STDOUT,check=True)
  w=json.loads(target.read_text())
  if w['status']!='passed' or not w['nontrivial_policy_weight_change_verified']:raise RuntimeError('Actual finite weight update failed')
  weights.append({'label':label,'report':str(target)})
  events.extend(after.parent.glob('events.out.tfevents.*'))
 status['weight_update_reports']=weights
 if len(weights)!=7:raise RuntimeError('Expected seven training weight update reports')
 from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
 training=[]
 for event in sorted((ROOT/'smoke').rglob('events.out.tfevents.*')):
  accumulator=EventAccumulator(str(event),size_guidance={'scalars':0});accumulator.Reload()
  tags=accumulator.Tags()['scalars'];series={tag:accumulator.Scalars(tag) for tag in tags}
  if any(not math.isfinite(x.value) for values in series.values() for x in values):raise RuntimeError('Non-finite TensorBoard scalar')
  training.append({'path':str(event),'sha256':sha(event),'scalar_tags':tags,'steps_by_tag':{tag:[x.step for x in values] for tag,values in series.items()},'all_scalars_finite':True})
 (validation/'tensorboard.json').write_text(json.dumps(training,indent=2)+'\n')
 status['tensorboard_events_verified']=len(training)
 for label in ('export-student-pure','export-student-finetune'):
  reports=manifests[label]['onnx_validation_reports']
  if not reports:raise RuntimeError('Missing student ONNX report')
  for entry in reports:
   d=json.loads(pathlib.Path(entry['report']).read_text())
   if d['status']!='passed' or len(d['cases'])!=30:raise RuntimeError('Student ORT case contract failed')
 status['student_onnx_cpu_cases_per_kind']=30
 after_source={p:sha(SOURCE/p) for p in critical}
 (ROOT/'source-critical-after.json').write_text(json.dumps(after_source,indent=2)+'\n')
 if before!=after_source:raise RuntimeError('Frozen source changed')
 status['source_critical_sha_unchanged']=True;status['status']='passed'
except Exception:
 status['status']='failed';status['error']=traceback.format_exc();print(status['error'],flush=True)
finally:
 stop.set();thread.join();status['elapsed_seconds']=time.time()-started;status['finished_unix']=time.time();save();print('Final acceptance: '+status['status'],flush=True)
if status['status']!='passed':raise SystemExit(1)
