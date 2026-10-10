from pathlib import Path
from collections import Counter
import datetime as dt,fcntl,hashlib,json,shutil
out=Path('/outputs/sim2sim-cohort-halt-20261010T0749');root=Path('/workspace/php_parkour');base=Path('/outputs/sim2sim/all-configs-final')
report={'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'orderly_interrupted_incomplete','native_processes':[],'cloud_training_affected':False,'configuration_coverage_complete':False,'quality_verified':False}
for entry in Path('/proc').glob('[0-9]*'):
 try:
  args=(entry/'cmdline').read_bytes().decode().split('\0')
  if str(root/'scripts/research/sim2sim.py') in args or str(root/'scripts/research/sim2sim_scene_matrix.py') in args or any('holosoma_inference.run_policy'==x or 'holosoma.sim2sim.run_sim'==x for x in args):
   report['native_processes'].append({'pid':int(entry.name),'cmdline':args,'status':(entry/'status').read_text()})
 except (OSError,UnicodeError):pass
assert not report['native_processes'],report['native_processes']
locks=[]
for name in ('/tmp/php-parkour-sim2sim-matrix.lock',str(base)+'.lock'):
 with Path(name).open('a') as stream:
  fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append({'path':name,'available':True});fcntl.flock(stream,fcntl.LOCK_UN)
report['locks']=locks
receipt=json.loads(Path('/outputs/sim2sim-all-configs-host/full-driver.json').read_text())
assert receipt['status']=='execution_failed' and receipt['returncode']==1 and receipt['completion_verified'] is False and receipt['finished_utc']
report['actual_outer_driver_returncode']=receipt['returncode'];report['driver_finished_utc']=receipt['finished_utc'];report['reason']='User-authorized verification work: stop known-invalid SDK/lifecycle cohort after confirmed missing-final-exit-code gate; original artifacts and states preserved'
for name in ('plan.json','matrix.json'):(out/('after-'+name)).write_bytes((base/name).read_bytes())
for name in ('full-driver.json','full-execution.log'):(out/('after-'+name)).write_bytes((Path('/outputs/sim2sim-all-configs-host')/name).read_bytes())
plan=json.loads((base/'plan.json').read_text());matrix=json.loads((base/'matrix.json').read_text())
report['selection_states']=dict(Counter(x.get('status','planned') for x in matrix['selections']))
report['original_top_level_counts']= {key:matrix.get(key) for key in ('status','completed_configurations','configuration_coverage_complete')}
report['frozen_plan_identity']=plan['plan_sha256'];sources=[]
for item in plan['dependencies']:
 p=Path(item['path']);assert p.is_relative_to(root)
 data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256']
 target=out/'frozen-dependencies'/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(0o644)
 sources.append({'original':str(p),'archive':str(target.relative_to(out)),'bytes':len(data),'sha256':item['sha256']})
(out/'frozen-dependencies-manifest.json').write_text(json.dumps({'scope':'All 340 exact old native source/robot dependencies captured before any replacement or source repair','files':sources},indent=2)+'\n')
report['frozen_dependency_count']=len(sources);report['frozen_dependency_bytes']=sum(x['bytes'] for x in sources)
report['future_work']='New reviewed source + SDK018 candidate must pass true worker-exit/native/CPU tests; then create a new plan/output/image cohort, never resume or edit old 571dfb cohort'
(out/'halt-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({key:report[key] for key in ('status','actual_outer_driver_returncode','selection_states','frozen_dependency_count','frozen_dependency_bytes','native_processes','locks')},indent=2))
