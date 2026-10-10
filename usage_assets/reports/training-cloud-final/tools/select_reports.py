from __future__ import annotations
import csv,hashlib,json,pathlib,shutil

repo=pathlib.Path.cwd();base=repo/'outputs/research/final-cloud-acceptance';raw=base/'results'
target=repo/'usage_assets/reports/training-cloud-final';target.mkdir(parents=True,exist_ok=True)
tbroot=repo/'usage_assets/tensorboard/final-cloud';media=repo/'usage_assets/videos/final-cloud';media.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def local(remote):
 return raw/pathlib.Path(remote).relative_to('/outputs/final-training-acceptance')
def copy(p,rel):
 t=target/rel;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t);return t
def write(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
status=json.loads((raw/'driver-status.json').read_text());assert status['status']=='passed'
launch=json.loads((raw/'launch.json').read_text());verified=[]
manifests={p.stem:json.loads(p.read_text()) for p in (raw/'smoke/manifests').glob('*.json')};assert len(manifests)==22
for p in [raw/'launch.json',raw/'driver-status.json',raw/'driver-initial-status.json',raw/'driver-final-status.json',raw/'source-critical-before.json',raw/'source-critical-after.json',raw/'source-snapshot-after.json',raw/'gpu.csv',raw/'gpu-handoff.json']:
 copy(p,p.name)
for p in [base/'driver.py',base/'finalize.py',base/'finalizer-tool.json']:
 copy(p,'tools/'+p.name)
stages=[];qualities=[];media_rows=[]
for label,m in manifests.items():
 copy(raw/'smoke/manifests'/f'{label}.json','manifests/'+label+'.json')
 log=local(m['log']);copy(log,'logs/'+label+'.log')
 for a in m.get('artifact_fingerprints',[]):
  p=local(a['path']);assert p.is_file() and sha(p)==a['sha256'];verified.append({'remote_path':a['path'],'local_path':str(p.relative_to(repo)),'sha256':a['sha256']})
 row={'label':label,'status':m['status'],'elapsed_seconds':m['elapsed_seconds'],'quality_verified':False}
 if 'checkpoint' in m:
  checkpoint=local(m['checkpoint']);assert sha(checkpoint)==m['checkpoint_sha256'];verified.append({'remote_path':m['checkpoint'],'local_path':str(checkpoint.relative_to(repo)),'sha256':m['checkpoint_sha256']})
  row.update(checkpoint_iteration=m['checkpoint_iteration'],checkpoint_sha256=m['checkpoint_sha256'],performance=m.get('performance'))
  config=checkpoint.parent/'holosoma_config.yaml';copy(config,'config/'+label+'.yaml')
 if label.startswith('eval-'):
  q=json.loads(local(m['evaluation_quality_report']).read_text());assert sha(local(q['saved_eval_config']))==q['saved_eval_config_sha256'];copy(local(q['saved_eval_config']),'config/'+label+'.yaml')
  copy(local(m['evaluation_quality_report']),'quality/'+label+'.json')
  qualities.append({'label':label,'num_envs':q['num_envs'],'control_steps':q['control_steps'],'failed_resets':q['failed_resets'],'timeout_resets':q['timeout_resets'],'metrics':q['metrics'],'quality_verified':q['quality_verified']})
  video=max(q['videos'],key=lambda v:v['duration_seconds']);source=local(video['path']);assert sha(source)==video['sha256']
  selected=media/(label+'.mp4');shutil.copyfile(source,selected)
  media_rows.append({'label':label,'file':str(selected.relative_to(repo)),'source_remote_path':video['path'],'sha256':video['sha256'],'duration_seconds':video['duration_seconds'],'scope':'Longest recorded episode from 250-step untrained smoke rollout; execution evidence, not learned skill quality'})
 for entry in m.get('onnx_validation_reports',[]):copy(local(entry['report']),'student-onnx/'+label+'-'+pathlib.Path(entry['report']).name)
 stages.append(row)
for p in (raw/'independent-validation').glob('*'):
 if p.is_file():copy(p,'independent-validation/'+p.name)
for p in (raw/'independent-validation').glob('*-weight-update.json'):
 w=json.loads(p.read_text())
 for section in ('before','after'):
  artifact=local(w[section]['path']);assert sha(artifact)==w[section]['sha256']
  verified.append({'remote_path':w[section]['path'],'local_path':str(artifact.relative_to(repo)),'sha256':w[section]['sha256']})
for p in (raw/'smoke/teacher-onnx-validation').glob('*.json'):copy(p,'teacher-onnx/'+p.name)
teacher=json.loads((raw/'smoke/teacher-onnx-validation/summary.json').read_text())
assert teacher['status']=='passed' and sum(t['cpu_cases'] for t in teacher['teachers'])==60
for t in teacher['teachers']:
 artifact=local(t['onnx']);assert sha(artifact)==t['onnx_sha256'];verified.append({'remote_path':t['onnx'],'local_path':str(artifact.relative_to(repo)),'sha256':t['onnx_sha256']})
tb=json.loads((raw/'independent-validation/tensorboard.json').read_text());events=[]
for row in tb['events']:
 p=local(row['path']);assert sha(p)==row['sha256'];relative=p.relative_to(raw/'smoke');dest=tbroot/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 events.append({'file':str(dest.relative_to(repo)),'sha256':row['sha256'],'bytes':row['bytes']})
handoff=json.loads((raw/'gpu-handoff.json').read_text())
gpu=[row for row in csv.DictReader((raw/'gpu.csv').open()) if float(row['unix'])<=handoff['pipeline_log_finished_unix']];peak=max(int(r['memory_used_mib']) for r in gpu)
verified=list({row['remote_path']:row for row in verified}.values())
summary={'status':'passed','scope':'Final unified image plus frozen cloud source: 22-stage 64-env/2-iteration smoke and 250-step evaluations. Not the full official training schedules, convergence or policy quality.','quality_verified':False,'image':launch['image'],'local_image':launch['local_image'],'image_contents_sha256':launch['image_contents_sha256'],'source_tree_sha256':launch['source_tree_sha256'],'git_commit':launch['git_commit'],'gpu_uuid':launch['gpu_uuid'],'physical_gpu_index':1,'started_unix':status['started_unix'],'driver_elapsed_seconds':status['elapsed_seconds'],'pipeline_elapsed_seconds':handoff['pipeline_log_finished_unix']-status['started_unix'],'final_validation_finished_unix':status['final_validation_finished_unix'],'pipeline_stage_count':22,'stages':stages,'quality_reports':qualities,'teacher_real_ort_cpu_cases':60,'student_real_ort_cpu_cases_per_kind':30,'finite_actual_weight_updates_verified':13,'training_tensorboard_loss_reward_steps_0_1_verified':13,'tensorboard_events':events,'gpu_sampling':{'interval_seconds_approximately':1,'samples':len(gpu),'peak_memory_mib':peak,'cutoff_unix':handoff['pipeline_log_finished_unix'],'scope':'Best-effort sampled peak until pipeline.log finished, before GPU handoff. Raw gpu.csv may also include later CPU verification time and successor jobs; those rows are excluded. May miss shorter spikes'},'download_verified_artifacts':verified,'source_verification':json.loads((raw/'source-snapshot-after.json').read_text()),'standalone_driver_correction':status['driver_bookkeeping_correction'],'raw_local_results':str(raw.relative_to(repo)),'raw_bytes':sum(p.stat().st_size for p in raw.rglob('*') if p.is_file()),'media':media_rows}
write(target/'summary.json',summary);write(target/'media.json',media_rows)
report_manifest={'scope':summary['scope'],'files':[]}
for p in sorted([p for p in target.rglob('*') if p.is_file()]+[repo/e['file'] for e in events]+[repo/m['file'] for m in media_rows]):
 report_manifest['files'].append({'file':str(p.relative_to(repo)),'bytes':p.stat().st_size,'sha256':sha(p)})
write(target/'evidence-manifest.json',report_manifest)
print(json.dumps({'selected_files':len(report_manifest['files']),'peak_mib':peak,'raw_bytes':summary['raw_bytes'],'quality_reports':len(qualities),'tb_events':len(events),'download_verified_artifacts':len(verified)},indent=2))
