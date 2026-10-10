from pathlib import Path
import datetime as dt,json,os,signal
base=Path('/outputs/sim2sim-cohort-halt-20261010T0749')
report=json.loads((base/'control-start.json').read_text())
script='/workspace/php_parkour/scripts/research/sim2sim.py'
live=[];dead=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=(p/'cmdline').read_bytes().decode().split('\0')
  if script in args and '--output' in args and Path(args[args.index('--output')+1]).is_relative_to('/outputs/sim2sim/all-configs-final'):
   state=(p/'status').read_text();item={'pid':int(p.name),'cmdline':args,'status':state}
   (dead if '\nState:\tZ' in state else live).append(item)
 except (OSError,UnicodeError,IndexError):pass
current=Path('/proc/18570')
args=(current/'cmdline').read_bytes().decode().split('\0')
assert '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py' in args
assert (current/'stat').read_text().split()[21]==report['driver']['stat'].split()[21]
assert '\nState:\tT' in (current/'status').read_text()
result={'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'live_native':live,'zombies':dead,'driver_stopped':True,'sources_changed':False}
if not live:
 result['action']='send SIGINT then SIGCONT to verified stopped matrix Python only'
 (base/'pre-driver-interrupt.json').write_text(json.dumps(result,indent=2)+'\n')
 os.kill(18570,signal.SIGINT);os.kill(18570,signal.SIGCONT)
 result['interrupt_sent']=True
else:result['interrupt_sent']=False
(base/'cleanup-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'live_native':len(live),'interrupt_sent':result['interrupt_sent']}))
