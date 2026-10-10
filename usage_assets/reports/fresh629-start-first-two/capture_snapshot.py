#!/usr/bin/env python3
import collections, datetime, hashlib, json, shutil, subprocess, time
from pathlib import Path
ROOT=Path('/home/dzp/projects/php_parkour')
BASE=ROOT/'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
OUT=Path(__file__).resolve().parent
SNAP=OUT/'snapshot';SNAP.mkdir(exist_ok=False)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def write(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 if sha(src)!=sha(dst):raise ValueError('Changed during copy: '+str(src))
 return {'source':str(src),'retained':str(dst.relative_to(OUT)),'bytes':dst.stat().st_size,'sha256':sha(dst)}
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
retained=[]
for rel in ['host-plan.json','freeze-manifest.json','inputs/native-plan.json','outputs/all-configs/plan.json','outputs/all-configs/matrix.json','host/launch-receipt.json','host/container-inspect.json','host/observer/launch.json','host/cpu-preflight/launch.json']:
 retained.append(copy(BASE/rel,SNAP/rel))
report=json.loads((SNAP/'outputs/all-configs/matrix.json').read_text());plan=json.loads((SNAP/'inputs/native-plan.json').read_text())
cases=report['selections'][:2]
assert len(cases)==2 and all(c['status']=='completed' for c in cases)
entries={};case_sources=[]
for ordinal,case in enumerate(cases):
 attempt=case['attempts'][0];directory=BASE/'outputs'/Path(attempt['output']).relative_to('/outputs')
 for name in ['result.json','case-evidence.json','worker-processes.json','simulator-process-start.json','inference-process-start.json','trajectory.csv','run.json','simulator.log','inference.log']:
  src=directory/name
  if src.is_file():retained.append(copy(src,SNAP/'cases'/str(ordinal)/name))
 src=BASE/'outputs'/Path(attempt['log']['path']).relative_to('/outputs');retained.append(copy(src,SNAP/'cases'/str(ordinal)/'parent-execution.log'))
 for role in ['simulator','inference']:
  entry=json.loads((directory/(role+'-process-start.json')).read_text());p=entry['process']
  entries[(attempt['output'],role,p['pid'],p['start_time_clock_ticks'])]={'ordinal':ordinal,'case_id':case['case_id'],'role':role,'entry':entry,'entry_sha256':sha(directory/(role+'-process-start.json'))}
 case_sources.append({'ordinal':ordinal,'case_id':case['case_id'],'directory':str(directory),'output':attempt['output']})
# Capture a bounded complete-line prefix of the append-only observer. Keep only
# exact raw observations relevant to these two terminal workers, never synthesize proc reads.
source=BASE/'host/observer/snapshots.jsonl';prefix_bytes=source.stat().st_size
with source.open('rb') as f:prefix=f.read(prefix_bytes)
cut=prefix.rfind(b'\n')+1;prefix=prefix[:cut]
mappings={};selected_lines=[];raw_count=0
for raw in prefix.splitlines(keepends=True):
 row=json.loads(raw);raw_count+=1;relevant=False
 for proc in row['processes']:
  key=(proc.get('worker_output'),proc.get('role'),proc.get('container_pid'),proc.get('start_time_clock_ticks'))
  if key not in entries:continue
  for thread in proc['command_writer_threads']:
   assert thread['container_tgid']==key[2] and thread['owner_start_time_clock_ticks']==key[3]
   tkey=(*key,thread['host_tid'],thread['start_time_clock_ticks'])
   if tkey not in mappings:mappings[tkey]=entries[key]|{'thread':thread,'owner':{k:v for k,v in proc.items() if k!='command_writer_threads'},'first_observed_utc':row['utc']}
   mappings[tkey]['last_observed_utc']=row['utc'];relevant=True
 if relevant:selected_lines.append(raw)
(SNAP/'host/observer/selected-snapshots.jsonl').write_bytes(b''.join(selected_lines))
assert len(mappings)==4 and len({(x['thread']['host_tid'],x['thread']['start_time_clock_ticks']) for x in mappings.values()})==4
write(SNAP/'host/observer/selected-mappings.json',{'scope':'First two terminal cases only; exact existing host /proc observations','mappings':list(mappings.values())})
# Read-only actual live identity. No exec into GPU container.
launch=json.loads((SNAP/'host/launch-receipt.json').read_text())
cmd=['docker','inspect','--type','container',launch['container_id']];p=subprocess.run(cmd,capture_output=True,text=True,check=True)
(SNAP/'host/container-inspect-at-snapshot.json').write_text(p.stdout)
counts=dict(collections.Counter(c.get('status','planned') for c in report['selections']))
write(OUT/'snapshot.json',{'schema_version':1,'snapshot_utc':started,'capture_finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Only first two terminal cases independently verified. Batch was running at snapshot; no whole629 claim.','live_matrix_status':report['status'],'live_matrix_counts':counts,'case_count':2,'cases':case_sources,'retained':retained,'observer_prefix':{'source':str(source),'read_complete_line_bytes':cut,'sha256':hashlib.sha256(prefix).hexdigest(),'complete_lines':raw_count,'selected_raw_lines':len(selected_lines),'mapping_count':len(mappings)},'read_only_docker_inspect_argv':cmd,'no_native_started':True,'no_live_source_or_output_modified':True})
print(json.dumps({'snapshot_utc':started,'counts':counts,'selected_mappings':len(mappings),'retained':len(retained)}))
