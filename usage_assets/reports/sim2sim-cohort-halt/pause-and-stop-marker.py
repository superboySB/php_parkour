from pathlib import Path
import datetime as dt,hashlib,json,os,signal,time
base=Path('/outputs/sim2sim-cohort-halt-20261010T0749')
case_root=Path('/outputs/sim2sim/all-configs-final')
root=Path('/workspace/php_parkour')
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def proc(pid):
 p=Path('/proc')/str(pid)
 return {'pid':pid,'cmdline':(p/'cmdline').read_bytes().decode().split('\0'),'status':(p/'status').read_text(),'stat':(p/'stat').read_text()}
plan=json.loads((case_root/'plan.json').read_text())
assert plan['plan_sha256']=='571dfb1e11c1cb862f8b6e8a3b8760b5cb899e039a5bfeb3b1012213d0b59158'
matrix_source=root/'scripts/research/sim2sim_scene_matrix.py'
assert hashlib.sha256(matrix_source.read_bytes()).hexdigest()=='284e3eabfc888303f5090f0d3c22dd8a3c35c5478285dc030778209079d746d2'
driver=proc(18570)
assert str(matrix_source) in driver['cmdline'] and '--all-configs' in driver['cmdline']
wrapper=proc(18564)
assert '/outputs/sim2sim-all-configs-host/full_driver.py' in wrapper['cmdline']
for name in ('plan.json','matrix.json'):(base/('before-'+name)).write_bytes((case_root/name).read_bytes())
(base/'before-full-driver.json').write_bytes(Path('/outputs/sim2sim-all-configs-host/full-driver.json').read_bytes())
report={'status':'pausing_driver','observed_utc':now(),'reason':'Confirmed final worker exit-code gate omission and SDK shutdown crashes hidden behind parent completed; preserve old cohort and rebuild fresh verified cohort','driver':driver,'wrapper':wrapper,'plan_identity':plan['plan_sha256'],'cloud_affected':False}
(base/'control-start.json').write_text(json.dumps(report,indent=2)+'\n')
os.kill(18570,signal.SIGSTOP)
for _ in range(100):
 if '\nState:\tT' in proc(18570)['status']:break
 time.sleep(.01)
else:raise RuntimeError('Driver did not stop; no source change allowed')
current=json.loads((case_root/'matrix.json').read_text())
(base/'paused-matrix.json').write_bytes((case_root/'matrix.json').read_bytes())
script=str(root/'scripts/research/sim2sim.py')
native=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  item=proc(int(p.name));args=item['cmdline']
  if script in args and '--output' in args:
   path=Path(args[args.index('--output')+1])
   if path.is_relative_to(case_root):
    item['output']=str(path);native.append(item)
 except (OSError,UnicodeError,IndexError):pass
outputs={x['output'] for x in native}
assert len(outputs)<=1,outputs
for value in outputs:
 path=Path(value);assert path.exists()
 (path/'stop').touch()
report.update(status='waiting_native_cleanup',driver_paused_utc=now(),paused_driver=proc(18570),native_before_stop=native,stop_markers=sorted(outputs))
(base/'control-start.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'driver_pid':18570,'native_processes':len(native),'stop_markers':sorted(outputs)}))
