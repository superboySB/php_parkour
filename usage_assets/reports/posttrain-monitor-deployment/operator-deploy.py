"""One-off stdlib SSH deployment; retained as an exact operator receipt."""
import datetime as dt
import json
from pathlib import Path
import shlex
import subprocess
import sys

directory = Path('/home/dzp/projects/php_parkour/outputs/research/posttrain-monitor-deployment')
directory.mkdir(parents=True, exist_ok=True)
tree, phase = sys.argv[1:]
assert len(tree) == 64 and all(c in '0123456789abcdef' for c in tree)
assert phase in ('audit', 'launch', 'status')
remote = r'''
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

tree, phase = sys.argv[1:]
root = Path('/diff/dzp_is_sb/php-parkour-research')
source = root / 'source' / tree
script = source / 'scripts/research/posttrain_coverage.py'
official = root / 'outputs/official-full'
coverage = root / 'outputs/coverage-official-final'
image = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
gpu = 'GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5'
def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()
def capture(argv):
    return subprocess.check_output(argv, text=True).strip()
def training():
    info = json.loads(capture(['docker', 'inspect', 'php-parkour-cloud-research']))[0]
    top = capture(['docker', 'top', 'php-parkour-cloud-research', '-eo', 'pid,args'])
    return {'image': info['Image'], 'running':info['State']['Running'],
            'source_mount':next(m['Source'] for m in info['Mounts'] if m['Destination']=='/workspace/php_parkour'),
            'native_training_processes':[line for line in top.splitlines() if 'wbt_training.train_agent' in line],
            'docker_ids':capture(['docker', 'ps', '-aq']).splitlines()}
before = training()
assert before['running'] and before['image'] == image
assert before['source_mount'] == str(root / 'source' / '0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab')
assert before['native_training_processes']
command = ['python3', '-B', str(script), 'watch', '--source-tree', tree, '--poll-seconds', '60']
record = {'observed_utc':now(),'phase':phase,'source_tree':tree,'monitor_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),
          'image':image,'gpu_uuid':gpu,'training_before':before,'command':command,
          'completion_verified':False,'quality_verified':False}
if phase == 'audit':
    spec=importlib.util.spec_from_file_location('posttrain_coverage_frozen',script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args=SimpleNamespace(root=root,source_tree=tree,image=image)
    module.verify_snapshot(args)
    record['source_and_image_independently_verified']=True
    dry_command=command[:3]+['dry-run','--source-tree',tree]
    existed=coverage.exists()
    result=subprocess.run(dry_command,text=True,capture_output=True)
    record.update(dry_run_command=dry_command,dry_run_exit=result.returncode,dry_run_stdout=result.stdout,dry_run_stderr=result.stderr)
    assert result.returncode==0
    record['dry_run']=json.loads(result.stdout)
    assert record['dry_run']['status']=='waiting' and record['dry_run']['gpu_started'] is False
    assert coverage.exists()==existed
    record['dry_run_created_coverage_directory']=False
elif phase == 'launch':
    found=[]
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                values=(entry/'cmdline').read_bytes().decode().split(chr(0))
                if str(script) in values and 'watch' in values:
                    found.append(int(entry.name))
            except (OSError,UnicodeError):
                pass
    assert not found, 'An identical monitor is already alive; do not duplicate it'
    coverage.mkdir(parents=True,exist_ok=True)
    log=root/'outputs/posttrain-monitor.log'
    with log.open('ab',buffering=0) as stream:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    record.update(pid=child.pid,started_utc=now(),log=str(log),detached=True)
    time.sleep(2)
    record['actual_returncode_after_two_seconds']=child.poll()
    assert record['actual_returncode_after_two_seconds'] is None
    status=json.loads((coverage/'monitor-status.json').read_text())
    assert status['status']=='waiting' and status.get('gpu_started') is False
    record['actual_status']=status
    (root/'outputs/posttrain-monitor-launch.json').write_text(json.dumps(record,indent=2)+'\n')
else:
    record['launch']=json.loads((root/'outputs/posttrain-monitor-launch.json').read_text())
    pid=record['launch']['pid']
    record['actual_process_arguments']=(Path('/proc')/str(pid)/'cmdline').read_bytes().decode().split(chr(0))
    assert str(script) in record['actual_process_arguments'] and 'watch' in record['actual_process_arguments']
    record['actual_status']=json.loads((coverage/'monitor-status.json').read_text())
    record['log_bytes']=(root/'outputs/posttrain-monitor.log').stat().st_size
    record['coverage_files']=sorted(str(path.relative_to(coverage)) for path in coverage.rglob('*') if path.is_file())
after=training()
record['training_after']=after
assert before['source_mount']==after['source_mount']
assert after['native_training_processes']
assert before['docker_ids']==after['docker_ids']
record['no_new_Docker_containers_observed']=True
record['training_source_mount_unchanged']=True
record['status']='passed'
print(json.dumps(record,indent=2))
'''
argv=['ssh','-p','22','-o','BatchMode=yes','-o','PasswordAuthentication=no','tencent-231',shlex.join(['python3','-B','-',tree,phase])]
started=dt.datetime.now(dt.timezone.utc).isoformat()
result=subprocess.run(argv,input=remote,text=True,capture_output=True)
(directory/f'{phase}-stdout.json').write_text(result.stdout)
(directory/f'{phase}-stderr.log').write_text(result.stderr)
(directory/f'{phase}-remote.py').write_text(remote)
receipt={'started_utc':started,'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'phase':phase,'source_tree':tree,'argv':argv,'returncode':result.returncode}
(directory/f'{phase}-exit.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
if result.returncode:
    print(result.stderr[-3000:])
    raise SystemExit(result.returncode)
value=json.loads(result.stdout)
print(json.dumps({'status':value['status'],'phase':phase,'monitor_pid':value.get('pid',value.get('launch',{}).get('pid')),'actual_status':value.get('actual_status',{}).get('status'),'GPU_started':False,'training_mount_unchanged':value['training_source_mount_unchanged']}))
