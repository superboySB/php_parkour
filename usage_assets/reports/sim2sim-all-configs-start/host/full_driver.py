from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import subprocess
import time

root=Path('/outputs/sim2sim-all-configs-host')
output=Path('/outputs/sim2sim/all-configs-final')
source=Path('/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py')
expected='284e3eabfc888303f5090f0d3c22dd8a3c35c5478285dc030778209079d746d2'
image='sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f'
assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
command=['/opt/php/bin/train-python',str(source),'--all-configs','--matrix','/outputs/motion-matching/matrix.json','--models','/data/assets/student','--output',str(output),'--image-id',image,'--seconds','10','--gl','egl','--resume']
receipt=root/'full-driver.json'
assert not receipt.exists()
report={'status':'starting','pid':os.getpid(),'command':command,'image_id':image,'harness_sha256':expected,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'quality_verified':False,'completion_verified':False}
def save():
    temporary=receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    temporary.replace(receipt)
save()
started=time.monotonic()
try:
    with (root/'full-execution.log').open('x') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd='/workspace/php_parkour',env=os.environ|{'OMP_NUM_THREADS':'4'})
        report.update(status='running',native_driver_pid=process.pid)
        save()
        code=process.wait()
    matrix=json.loads((output/'matrix.json').read_text())
    complete=code==0 and matrix['status']=='completed' and matrix['completed_configurations']==629 and matrix['configuration_coverage_complete'] is True
    report.update(status='completed' if complete else 'execution_failed',returncode=code,completion_verified=complete,completed_configurations=matrix.get('completed_configurations'),matrix_sha256=hashlib.sha256((output/'matrix.json').read_bytes()).hexdigest())
except BaseException as error:
    report.update(status='execution_failed',error=f'{type(error).__name__}: {error}')
    raise
finally:
    report.update(wall_seconds=time.monotonic()-started,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    save()
