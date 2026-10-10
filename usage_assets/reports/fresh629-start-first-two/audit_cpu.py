#!/usr/bin/env python3
"""Read-only evidence review for a fixed TWO-case snapshot; no simulation imports."""
import collections,csv,datetime,hashlib,importlib.util,json,math,os,subprocess,time
from pathlib import Path
OUT=Path('/audit');SNAP=OUT/'snapshot';COHORT=Path('/cohort')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text())
def write(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def require(value,message):
 if not value:raise ValueError(message)
def command(argv,timeout=120):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(f'{argv[0]} returned {p.returncode}: {p.stderr}')
 return p
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
result={'schema_version':1,'status':'running','scope':'Exactly first two terminal cases, independent CPU verification of immutable inputs, native receipts, recorded host mappings and full MP4 decode. No whole629 completion or skill-success claim.','started_utc':started,'cases':[]}
try:
 require(os.environ.get('CUDA_VISIBLE_DEVICES')=='','CPU-only CUDA visibility')
 require(not list(Path('/dev').glob('nvidia*')),'Unexpected NVIDIA device in CPU container')
 snapshot=load(OUT/'snapshot.json');host=load(SNAP/'host-plan.json');plan=load(SNAP/'inputs/native-plan.json');report=load(SNAP/'outputs/all-configs/matrix.json')
 require(snapshot['live_matrix_status']=='running' and report['status']=='running','Snapshot must describe a running batch')
 require(load(SNAP/'outputs/all-configs/plan.json')==plan,'Executed plan differs')
 payload=dict(host);recorded=payload.pop('plan_sha256')
 require(hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==recorded,'Host plan identity changed')
 require(sha(SNAP/'freeze-manifest.json')==host['freeze_manifest_sha256'],'Freeze manifest hash changed')
 require(sha(SNAP/'inputs/native-plan.json')==host['native_plan_file_sha256'] and plan['plan_sha256']==host['native_plan_sha256'],'Plan SHA mismatch')
 frozen=load(SNAP/'freeze-manifest.json');counts=collections.Counter();size=0
 for item in frozen['files']:
  path=COHORT/item['relative']
  require(path.resolve().is_relative_to(COHORT.resolve()) and not path.is_symlink() and path.is_file(),'Unsafe frozen file')
  require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],'Frozen bytes changed: '+item['relative'])
  counts[item['relative'].split('/')[0]]+=1;size+=item['bytes']
 require(len(frozen['files'])==5206,'Expected fixed5206 frozen files')
 generated=sum('motion-matching/scenarios/' in x['relative'] for x in frozen['files'])
 require(generated==1887 and counts['source']-generated==3297,'Frozen fullsource/generated set counts differ')
 for item in snapshot['retained']:
  require(sha(OUT/item['retained'])==item['sha256'],'Snapshot copy changed')
 live=load(SNAP/'host/container-inspect-at-snapshot.json')[0];initial=load(SNAP/'host/container-inspect.json');observer=load(SNAP/'host/observer/launch.json');launch=load(SNAP/'host/launch-receipt.json')
 require(live['Id']==initial['Id']==observer['identity']['container_id']==launch['container_id'],'Live CID identity differs')
 require(live['Image']==initial['Image']==observer['identity']['image_id']==host['image_id']==plan['image_id'],'Image mismatch')
 require(live['State']['StartedAt']==initial['State']['StartedAt']==observer['identity']['started_at'],'Container restarted')
 require(live['State']['Running'] and launch['status']=='running','Recorded launch should be running')
 require(live['HostConfig']['NetworkMode']=='none' and live['HostConfig']['IpcMode']=='private' and not live['HostConfig'].get('PidMode'),'Native private namespace mismatch')
 require(live['HostConfig']['DeviceRequests'][0]['DeviceIDs']==[host['gpu_uuid']],'Native physicalGPU UUID mismatch')
 require(launch['snapshot_files_verified']==5206 and launch['plan_sha256']==host['plan_sha256'],'Launch freeze mismatch')
 mappings=load(SNAP/'host/observer/selected-mappings.json')['mappings'];require(len(mappings)==4,'Four exact writer mappings required')
 modulepath=Path('/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py')
 require(sha(modulepath)==host['matrix_source_sha256'],'Validator source SHA changed')
 spec=importlib.util.spec_from_file_location('frozen_matrix',modulepath);matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
 seen=set()
 for index,(expected,case) in enumerate(zip(plan['selections'][:2],report['selections'][:2])):
  require(all(case.get(k)==v for k,v in expected.items()),'Case identity mismatch')
  require(case['status']=='completed' and len(case['attempts'])==1 and case['attempts'][0]['status']=='completed','Once-only completed attempt required')
  attempt=case['attempts'][0];directory=Path(attempt['output'])
  matrix.verify_inputs(plan,expected);matrix.verify_completed(attempt,plan,case)
  native=load(directory/'result.json');receipts=matrix.validate_worker_receipts(directory,plan,native)
  require(native==load(SNAP/'cases'/str(index)/'result.json'),'Native result changed since snapshot')
  infer=native['inference'];sim=native['simulation']
  require(infer['ticks']==500 and infer['control_period_simulation_seconds']==.02 and native['config']['seed']==42,'Ticks/period/seed mismatch')
  rows=list(csv.DictReader((directory/'trajectory.csv').open()));active=[r for r in rows if float(r['policy_seconds'])>=0]
  times=[float(r['policy_seconds']) for r in active]
  require(len(times)==501 and abs(times[-1]-times[0]-10)<1e-8 and all(abs(b-a-.02)<1e-8 for a,b in zip(times,times[1:])),'Policy simulation clock not500 regular ticks')
  require(abs(sim['policy_simulation_seconds']-times[-1])<1e-8 and abs(times[0]-infer['commands'][0]['seconds'])<1e-8,'Startup clock offset not accounted')
  require(all(math.isfinite(float(v)) for row in rows for v in row.values()),'Nonfinite trajectory')
  workers=[]
  for role in ('simulator','inference'):
   entry=load(directory/(role+'-process-start.json'));process=entry['process']
   chosen=[m for m in mappings if m['case_id']==case['case_id'] and m['role']==role]
   require(len(chosen)==1,'One mapped thread per worker required');mapping=chosen[0];thread=mapping['thread'];owner=mapping['owner']
   require(mapping['entry']==entry and mapping['entry_sha256']==sha(directory/(role+'-process-start.json')),'Recorded entry SHA/identity differs')
   require(owner['worker_output']==attempt['output'] and owner['container_pid']==process['pid'] and owner['start_time_clock_ticks']==process['start_time_clock_ticks'],'Host owner/container entry mismatch')
   require(thread['container_tgid']==process['pid'] and thread['owner_start_time_clock_ticks']==process['start_time_clock_ticks'],'Writer birth owner differs')
   require(thread['nspid']==[thread['host_tid'],thread['container_tid']] and thread['nstgid']==[thread['host_tgid'],process['pid']] and thread['host_tgid']==owner['host_pid'],'Namespace writer mapping differs')
   identity=(thread['host_tid'],thread['start_time_clock_ticks']);require(identity not in seen,'Writer thread reused across roles');seen.add(identity)
   workers.append({'role':role,'native_pid':process['pid'],'native_start_time_clock_ticks':process['start_time_clock_ticks'],'host_pid':owner['host_pid'],'host_tid':thread['host_tid'],'thread_start_time_clock_ticks':thread['start_time_clock_ticks'],'container_tid':thread['container_tid'],'nspid':thread['nspid'],'nstgid':thread['nstgid'],'first_observed_utc':mapping['first_observed_utc'],'last_observed_utc':mapping['last_observed_utc']})
  videos=[]
  require(len(native['videos'])==1,'One MP4 per case required')
  for rel in native['videos']:
   path=(directory/rel).resolve();require(path.is_relative_to(directory.resolve()) and not path.is_symlink(),'Unsafe video')
   before=sha(path);probe=command(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)])
   info=json.loads(probe.stdout);duration=float(info['format']['duration']);require(math.isfinite(duration) and duration>0,'Video duration invalid')
   argv=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-threads','1','-i',str(path),'-f','null','-'];decode=command(argv)
   require(not decode.stderr.strip() and before==sha(path),'Video changed or full decode errors')
   png=OUT/('case-'+str(index)+'-decoded.png');frame_seconds=min(duration*.5,3)
   screenshot_argv=['ffmpeg','-hide_banner','-loglevel','error','-threads','1','-ss',str(frame_seconds),'-i',str(path),'-frames:v','1','-y',str(png)];command(screenshot_argv)
   videos.append({'path':str(path),'bytes':path.stat().st_size,'sha256':before,'duration_seconds':duration,'streams':info['streams'],'full_decode':True,'decode_argv':argv,'decode_returncode':0,'decode_stderr':decode.stderr,'screenshot':{'path':str(png),'sha256':sha(png),'source_seconds':frame_seconds,'argv':screenshot_argv}})
  result['cases'].append({'case_id':case['case_id'],'scenario':case['scenario'],'configuration_index':case['configuration_index'],'parent_returncode':attempt['returncode'],'native_result_sha256':sha(directory/'result.json'),'case_evidence_sha256':sha(directory/'case-evidence.json'),'receipts':receipts,'workers_exit0_empty_groups':2,'mapped_writers':workers,'policy_ticks':500,'normal_clock':{'active_samples':len(times),'first_policy_seconds':times[0],'last_policy_seconds':times[-1],'delta_simulation_seconds':.02,'native_policy_simulation_seconds':sim['policy_simulation_seconds'],'startup_clock_offset_seconds':infer['commands'][0]['seconds'],'wall_seconds':sim['wall_seconds']},'result_config':native['config'],'simulation':sim,'survival_heuristic_passed':native['survival_passed'],'quality_verified':native['quality_verified'],'obstacle_course_completion_verified':native['obstacle_course_completion_verified'],'videos':videos})
 require(len(seen)==4,'Four unique hostbirth writer mappings required')
 result.update(status='passed',snapshot_utc=snapshot['snapshot_utc'],batch_status_at_snapshot=report['status'],batch_counts_at_snapshot=snapshot['live_matrix_counts'],validated_cases=2,worker_exit0_empty_group_count=4,exact_hostbirth_writer_mappings=4,full_decoded_mp4_count=2,frozen_input_check={'total_files':5206,'total_bytes':size,'fullsource_files':3297,'generated_motion_terrain_files':1887,'other_metadata_control_files':22,'all_sha256_unchanged':True,'manifest_sha256':sha(SNAP/'freeze-manifest.json')},plan_file_sha256=sha(SNAP/'inputs/native-plan.json'),host_plan_identity_sha256=host['plan_sha256'],native_plan_identity_sha256=plan['plan_sha256'],image_id=host['image_id'],native_container_id=launch['container_id'],gpu_uuid=host['gpu_uuid'],matrix_validator_sha256=sha(modulepath),worker_harness_sha256=plan['worker_harness_record']['sha256'],survival_heuristic_passed_cases=sum(c['survival_heuristic_passed'] for c in result['cases']),fall_threshold_triggered_cases=sum(c['simulation']['fall_detected'] for c in result['cases']),quality_verified=False,obstacle_course_completion_verified=False,no_simulator_inference_dds_or_gpu_started=True)
except BaseException as error:
 result.update(status='failed',error=f'{type(error).__name__}: {error}');raise
finally:
 result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();write(OUT/'cpu-review.json',result)
print(json.dumps({'status':result['status'],'cases':2,'workers':4,'mapped_writers':4,'videos':2,'full_frozen_files':5206,'quality_verified':False}))
