import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

root = Path('/home/dzp/projects/php_parkour')
prep = root / 'outputs/research/final-student-delivery-waiter-preparation'
evidence = root / 'outputs/research/final-student-delivery-waiter-root-arm-01'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def write(name, value):
    with (evidence / name).open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
def birth(pid):
    proc = Path('/proc') / str(pid)
    raw = (proc / 'stat').read_text();parts = raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'pgid':int(parts[2]),'sid':int(parts[3]),'start_time_clock_ticks':int(parts[19]),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'argv':(proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')}
assert sha(prep / 'manifest.json') == 'bb38b86c4d9dad5f75910e38fb8ca607567152c1653ce736d1fa2903920345d8'
manifest = read(prep / 'manifest.json')
for item in manifest['files']:
    p = prep / item['relative']
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
assert sha(prep/'independent-review/review.json') == 'b8fe3948ff55e35563ab6c5c597633667a88528691e154e8c47831fe0f093e4f'
assert sha(prep/'wait_final_students.py') == '049678a74ff34776120fda26da9c6ebb54c215f084929629a60fc5bfba50535f'
assert sha(prep/'contract.json') == 'b4cde2ba7b361bd5f18cce9a0a10b1c234fa1519cfe5787fa14e9aef0f0d7f4f'
suite = ET.parse(prep/'cpu-validation-transport-final/tests.xml').getroot()
entries = list(suite.iter('testcase'))
assert len(entries) == 55 and all(not list(x) for x in entries)
receipt = read(prep/'preparation-receipt.json')
assert all(not Path(p).exists() for p in receipt['dedicated_paths_absent'])
evidence.mkdir(exist_ok=False)
before = subprocess.check_output(['docker','ps','-aq','--no-trunc'],text=True).splitlines()
write('local-container-ids-before.json',before)
check = subprocess.run(receipt['check_argv'],cwd=root,text=True,capture_output=True)
(evidence/'check.stdout.log').write_text(check.stdout);(evidence/'check.stderr.log').write_text(check.stderr)
assert check.returncode == 0 and json.loads(check.stdout)['status'] == 'prepared_only'
write('root-check.json',{'argv':receipt['check_argv'],'returncode':check.returncode,'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
argv = receipt['root_launch_argv']
with (evidence/'watch.stdout.log').open('x') as stdout,(evidence/'watch.stderr.log').open('x') as stderr:
    child = subprocess.Popen(argv,cwd=root,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
    ident = birth(child.pid)
    assert ident['pid'] == ident['pgid'] == ident['sid'] and ident['argv'] == argv
    launch = {'status':'started_only','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'identity':ident,'argv':argv,'contract_sha256':sha(prep/'contract.json'),'waiter_sha256':sha(prep/'wait_final_students.py'),
              'review_sha256':sha(prep/'independent-review/review.json'),'preparation_manifest_sha256':sha(prep/'manifest.json'),
              'stdin':'/dev/null','start_new_session':True,'authorization':'Existing user instruction to complete the full training, synchronization and final-model verification; no separate confirmation requested',
              'automatic_retry':False,'completion_verified':False}
    write('launch.json',launch)
    deadline = time.monotonic()+45
    state_path=prep/'execution/state.json'
    while time.monotonic()<deadline:
        assert child.poll() is None, 'Waiter exited; retain all raw logs and execution state for review'
        if state_path.exists():
            state=read(state_path)
            if state.get('polls',0)>=1:break
        time.sleep(.2)
    else: raise RuntimeError('Initial observation still pending; do not kill/restart the running waiter')
    assert state['status']=='waiting' and state['stage']=='official_artifacts'
    assert state['fetch_attempted'] is state['prepare_attempted'] is state['run_attempted'] is False
    assert state['remote_status']['status']=='waiting' and state['remote_status']['transfer_started'] is False
    assert not (root/'outputs/research/final-student-transfer/waiter-delivery-01').exists()
    assert not (root/'outputs/research/final-student-native58-delivery-01').exists()
    after=subprocess.check_output(['docker','ps','-aq','--no-trunc'],text=True).splitlines()
    write('local-container-ids-after.json',after);assert before==after
    assert birth(child.pid)==ident
    write('initial-state.json',state)
    write('initial-observation.json',{'status':'actual_waiting','observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
          'identity':ident,'alive':True,'execution_state_path':str(state_path),'state_sha256':sha(state_path),
          'local_container_ids_unchanged':True,'actual_ssh_status_executed':True,'actual_fetch_executed':False,
          'actual_native58_prepare_executed':False,'actual_native_gpu_run_executed':False,'completion_verified':False})
    print(json.dumps({'evidence':str(evidence.relative_to(root)),'pid':child.pid,'state':state['status'],'polls':state['polls'],'remaining_stages':len(state['remote_status']['stage_blockers'])}))
