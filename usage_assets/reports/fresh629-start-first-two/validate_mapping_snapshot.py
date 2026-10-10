import datetime,hashlib,json
from pathlib import Path
base=Path('/audit');raw=base/'snapshot/host/observer/selected-snapshots.jsonl';mappings=json.loads((raw.parent/'selected-mappings.json').read_text())['mappings'];rows=[json.loads(r) for r in raw.read_text().splitlines()]
for mapping in mappings:
 observations=[]
 for row in rows:
  for proc in row['processes']:
   owner={k:v for k,v in proc.items() if k!='command_writer_threads'}
   if owner!=mapping['owner']:continue
   if mapping['thread'] in proc['command_writer_threads']:observations.append(row['utc'])
 # Other sampled fields (running/sleeping state, Threads count) can vary.
 # Match the immutable owner identity + exact recorded thread for all observations.
 observations=[]
 for row in rows:
  for proc in row['processes']:
   o=mapping['owner']
   if (proc.get('worker_output'),proc['role'],proc['host_pid'],proc['container_pid'],proc['start_time_clock_ticks'])!=(o.get('worker_output'),o['role'],o['host_pid'],o['container_pid'],o['start_time_clock_ticks']):continue
   for thread in proc['command_writer_threads']:
    t=mapping['thread']
    if all(thread.get(k)==t[k] for k in ['host_tid','host_tgid','container_tid','container_tgid','nspid','nstgid','owner_start_time_clock_ticks','start_time_clock_ticks']):observations.append(row['utc'])
 assert observations and min(observations)==mapping['first_observed_utc'] and max(observations)==mapping['last_observed_utc']
launch=json.loads((raw.parent/'launch.json').read_text());source=Path('/cohort/control/observe_container_pids.py')
assert hashlib.sha256(source.read_bytes()).hexdigest()==launch['source_sha256']
r={'schema_version':1,'status':'passed','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Four derived writer mappings were independently joined to actual retained raw observer rows by owner PID/birth, exact namespace lists and writer TID/birth. No process or simulation started.','raw_selected_snapshots_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'raw_rows':len(rows),'exact_mappings':len(mappings),'observer_source_sha256':launch['source_sha256'],'container_id':launch['identity']['container_id'],'container_started_at':launch['identity']['started_at']}
(base/'host-mapping-source-proof.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
