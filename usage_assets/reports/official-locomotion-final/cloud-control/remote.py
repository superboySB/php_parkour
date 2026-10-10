
from pathlib import Path
import datetime as dt, hashlib, json, subprocess
base = Path('/diff/dzp_is_sb/php-parkour-research')
tree = '0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab'
source = base / 'source' / tree
cid = 'f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
def fp(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda: stream.read(8388608), b''): h.update(b)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': h.hexdigest()}
def process(pid):
    p = Path('/proc') / str(pid)
    try:
        raw = (p / 'stat').read_text(); fields = raw[raw.rfind(')')+2:].split()
        return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]),
                'pgid': int(fields[2]), 'sid': int(fields[3]), 'birth': int(fields[19]),
                'stat': raw, 'command': (p/'cmdline').read_bytes().replace(b'\0',b' ').decode()}
    except FileNotFoundError: return {'pid': pid, 'missing': True}
d = json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
assert d['Id'] == cid and d['Image'] == 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
assert d['State']['Running'] and d['State']['StartedAt'] == '2026-10-10T04:01:22.880471283Z'
mount = next(m for m in d['Mounts'] if m['Destination']=='/workspace/php_parkour')
assert mount['Source'] == str(source)
driver = process(3836907); monitor = process(4074213)
assert driver['birth']==700458612 and driver['state'] not in ('Z','X')
assert monitor['birth']==702550493 and monitor['state'] not in ('Z','X')
files = ['scripts/research/train_pipeline.py','scripts/research/run_official_acceptance.sh',
         'scripts/research/validate_teacher_exports.py','scripts/research/validate_teacher_onnx.py',
         'wbt_training/training_runs/run_terrain_teacher.sh',
         'wbt_training/config_values/experiment.py',
         'thirdparty/holosoma/src/holosoma/holosoma/agents/ppo/ppo.py',
         'thirdparty/holosoma/src/holosoma/holosoma/agents/base_algo/base_algo.py']
records = [fp(source/name) for name in files]
assert records[0]['sha256']=='5f85596f40b796b8626e05058d54824d93ba97e3788129e1763ba5c461284adb'
assert records[1]['sha256']=='f2c0eb73772f311487df3e2ccb5b674f34df943abe74a5b41d0e1e6c7b0b0360'
manifests = base/'outputs/official-full/official/manifests'
first_path = manifests/'teacher-locomotion.json'; first_raw=first_path.read_bytes(); first=json.loads(first_raw)
assert first['status']=='passed' and first['returncode']==0 and first['checkpoint_iteration']==19999
assert first['overrides']=={'num_envs':None,'iterations_target':None}
second_path=manifests/'teacher-low-step.json'; second_raw=second_path.read_bytes(); second=json.loads(second_raw)
assert second['status']=='running'
top = subprocess.check_output(['docker','top',cid,'-eo','pid,ppid,pgid,sid,args'],text=True)
next_native=[]
for row in top.splitlines()[1:]:
    parts=row.split(None,4)
    if len(parts)==5 and 'wbt_training.train_agent' in parts[4] and '/isaac-sim/kit/python/bin/python3' in parts[4]:
        p=process(int(parts[0])); assert 'teacher-low-step' in p['command']; next_native.append(p)
assert len(next_native)==1
log=base/'outputs'/Path(first['log']).relative_to('/outputs')
assert records==[fp(source/name) for name in files]
assert first_path.read_bytes()==first_raw
print(json.dumps({'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
 'scope':'First official teacher actual wait0 and automatic next-stage transition; full schedule and policy quality incomplete',
 'container_id':d['Id'],'image_id':d['Image'],'started_at':d['State']['StartedAt'],
 'container_running':d['State']['Running'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'source_tree':tree,'source_mount':mount,'source_records_before_equal_after':True,'source_records':records,
 'first_manifest':{'fingerprint':fp(first_path),'raw':first_raw.decode()},
 'first_closed_training_log':fp(log),'next_manifest':{'fingerprint':fp(second_path),'raw':second_raw.decode()},
 'original_driver':driver,'original_monitor':monitor,'old_first_native':process(3836987),
 'next_native':next_native,'top_raw':top,'device_requests':d['HostConfig']['DeviceRequests'],
 'remote_read_only':True,'full_official_complete':False,'quality_verified':False}))
