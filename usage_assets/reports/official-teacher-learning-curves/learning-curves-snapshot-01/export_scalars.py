#!/usr/bin/env python3
"""Read one unfinished official run without changing its trainer or container."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CID = 'f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
IMAGE = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
START = '2026-10-10T04:01:22.880471283Z'
SSH = ['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no', 'tencent-231']
CODE = '''import datetime, json, math
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
run=Path('/outputs/official-full/official/teacher-locomotion/PHP-research/20261010_042104-teacher-locomotion-locomotion')
ea=EventAccumulator(str(run),size_guidance={'scalars':0});ea.Reload()
scalars={}
for tag in ('Train/mean_reward','Loss/Value','Loss/Surrogate','Loss/Entropy'):
    rows=[{'wall_time':s.wall_time,'step':s.step,'value':s.value} for s in ea.Scalars(tag)]
    assert rows and all(math.isfinite(r['value']) and math.isfinite(r['wall_time']) for r in rows)
    assert all(b['step']>a['step'] for a,b in zip(rows,rows[1:]))
    scalars[tag]=rows
print(json.dumps({'schema_version':1,'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running','partial':True,'run':str(run),'official_target_iterations':20000,'scalars':scalars,'completion_verified':False,'quality_verified':False},allow_nan=False,separators=(',',':')))
'''

def remote(argv, input_bytes=None):
    command = SSH + [shlex.join(argv)]
    result = subprocess.run(command, input=input_bytes, capture_output=True)
    return command, result

def inspect(label):
    fmt = '{{json .Id}}\n{{json .Image}}\n{{json .State}}'
    command, result = remote(['docker', 'inspect', '--type', 'container', '--format', fmt, CID])
    (HERE / (label + '.stdout.raw')).write_bytes(result.stdout)
    (HERE / (label + '.stderr.raw')).write_bytes(result.stderr)
    assert result.returncode == 0
    rows = [json.loads(line) for line in result.stdout.decode().splitlines()]
    assert len(rows) == 3 and rows[0] == CID and rows[1] == IMAGE
    assert rows[2]['Running'] is True and rows[2]['StartedAt'] == START
    return {'argv': command, 'returncode': result.returncode, 'container_id': rows[0], 'image_id': rows[1], 'state': rows[2]}

def digest(path):
    return {'path': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    assert not (HERE / 'scalars.json').exists(), 'No overwrite of a previous observation'
    before = inspect('inspect-before')
    argv, result = remote(['docker', 'exec', '-i', '-e', 'CUDA_VISIBLE_DEVICES=', CID, '/opt/php/bin/train-python', '-'], CODE.encode())
    (HERE / 'export.stdout.raw').write_bytes(result.stdout)
    (HERE / 'export.stderr.raw').write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    after = inspect('inspect-after')
    value = json.loads(result.stdout[result.stdout.index(b'{'):])
    assert value['status'] == 'running' and value['partial'] and not value['completion_verified'] and not value['quality_verified']
    (HERE / 'scalars.json').write_text(json.dumps(value, allow_nan=False, separators=(',', ':')) + '\n')
    receipt = {'schema_version': 1, 'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'snapshot_exported', 'partial': True, 'completion_verified': False, 'quality_verified': False, 'source_fingerprint': '0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab', 'before': before, 'after': after, 'export_argv': argv, 'returncode': result.returncode, 'scalar_counts': {t: {'samples': len(r), 'first_step': r[0]['step'], 'last_step': r[-1]['step'], 'last_value': r[-1]['value']} for t,r in value['scalars'].items()}, 'files': [digest(p) for p in sorted(HERE.iterdir()) if p.is_file()]}
    (HERE / 'export-receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': receipt['status'], 'scalar_counts': receipt['scalar_counts'], 'scalars': digest(HERE / 'scalars.json')}, indent=2))

if __name__ == '__main__':
    main()
