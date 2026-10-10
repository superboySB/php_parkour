"""Read-only host stdlib process audit; scientific TensorBoard read runs in Docker."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import subprocess

ROOT=Path('/diff/dzp_is_sb/php-parkour-research')
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def capture(argv): return subprocess.check_output(argv,text=True).strip()
def process(pid):
    p=Path('/proc')/str(pid)
    return {'pid':pid,'cmdline':(p/'cmdline').read_bytes().decode().split('\0'),'stat':(p/'stat').read_text(),
            'status':(p/'status').read_text(),'cwd':str((p/'cwd').resolve())}
report={'observed_utc':now(),'scope':'One actual read-only cloud observation; no restart, package installation, bind change or GPU job',
        'quality_verified':False,'completion_verified':False}
info=json.loads(capture(['docker','inspect','php-parkour-cloud-research']))[0]
top=capture(['docker','top','php-parkour-cloud-research','-eo','pid,ppid,args'])
native=[line for line in top.splitlines() if 'wbt_training.train_agent' in line]
report['training']={'image':info['Image'],'running':info['State']['Running'],
 'source_mount':next(m for m in info['Mounts'] if m['Destination']=='/workspace/php_parkour'),
 'native_processes':[process(int(line.split(None,1)[0])) for line in native], 'top':top}
launch=json.loads((ROOT/'outputs/posttrain-monitor-launch.json').read_text())
monitor=process(3940821)
status_path=ROOT/'outputs/coverage-official-final/monitor-status.json'
status=json.loads(status_path.read_text())
log=ROOT/'outputs/posttrain-monitor.log'; logdata=log.read_bytes()
script=Path(launch['command'][2])
report['monitor']={'process':monitor,'source_tree':launch['source_tree'],
 'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'status':status,'status_file_mtime_utc':dt.datetime.fromtimestamp(status_path.stat().st_mtime,dt.timezone.utc).isoformat(),
 'status_age_seconds':(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(status['observed_utc'])).total_seconds(),
 'log_bytes':len(logdata),'waiting_log_entries':logdata.count(b'"status": "waiting"'),
 'latest_log_tail':logdata[-3000:].decode(),'coverage_files':sorted(str(p.relative_to(ROOT/'outputs/coverage-official-final')) for p in (ROOT/'outputs/coverage-official-final').rglob('*') if p.is_file())}
scientific='''from pathlib import Path
import datetime as dt,json,math
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root=Path('/outputs/official-full')
manifest=json.loads((root/'official/manifests/teacher-locomotion.json').read_text())
run=sorted((root/'official/teacher-locomotion/PHP-research').glob('*'))[-1]
acc=EventAccumulator(str(run),size_guidance={'scalars':0});acc.Reload()
values={}
for name in ('Loss/Value','Loss/Surrogate','Loss/Entropy','Train/mean_reward'):
 rows=acc.Scalars(name)
 values[name]={'samples':len(rows),'first_step':rows[0].step,'last_step':rows[-1].step,'last_value':rows[-1].value,'last_wall_time_utc':dt.datetime.fromtimestamp(rows[-1].wall_time,dt.timezone.utc).isoformat(),'all_finite':all(math.isfinite(x.value) for x in rows)}
print(json.dumps({'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'run':str(run),'selected_scalars':values,'manifest':manifest,'checkpoint_files':[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(run.glob('*.pt'))],'scientific_read_in_docker_cpu':True,'quality_verified':False}))
'''
result=subprocess.run(['docker','exec','-i','-e','CUDA_VISIBLE_DEVICES=','-e','OMP_NUM_THREADS=1','php-parkour-cloud-research','/opt/php/bin/train-python','-'],input=scientific,text=True,capture_output=True)
report['scientific_read_returncode']=result.returncode
report['scientific_read_stderr']=result.stderr
if result.returncode==0: report['tensorboard']=json.loads(result.stdout)
else: report['scientific_read_stdout']=result.stdout
errors=[]
if report['training']['source_mount']['Source']!=str(ROOT/'source/0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab'): errors.append('Training source binding changed')
if info['Image']!='sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd': errors.append('Training image changed')
if not native: errors.append('No native training process')
if str(script) not in monitor['cmdline'] or 'watch' not in monitor['cmdline']: errors.append('PID3940821 does not match watcher')
if status['status']!='waiting' or status.get('gpu_started') is not False: errors.append('Unexpected current monitor status')
if report['monitor']['status_age_seconds']>90: errors.append('Monitor status stale beyond60s poll+30s margin')
if result.returncode: errors.append('Docker TensorBoard CPU read failed')
elif not all(row['all_finite'] for row in report['tensorboard']['selected_scalars'].values()): errors.append('Nonfinite selected TensorBoard scalars')
report.update(status='verified_wait' if not errors else 'anomaly',errors=errors,finished_utc=now())
print(json.dumps(report,indent=2))
