#!/usr/bin/env python3
"""Run and retain exactly one bounded SSH observation."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import subprocess

BASE = Path(__file__).resolve().parent
argv = ['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
        '-o', 'ControlMaster=auto', '-o', 'ControlPersist=10m', '-o', 'ControlPath=~/.ssh/php-parkour-%C',
        'tencent-231', 'python3 -B -']
source = BASE / 'observe_remote.py'
record = {'argv': argv, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'remote_helper_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'read_only': True, 'remote_files_modified': False}
with (BASE / 'stdout.raw').open('xb') as out, (BASE / 'stderr.raw').open('xb') as err:
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err)
    record['ssh_pid'] = child.pid
    child.stdin.write(source.read_bytes()); child.stdin.close()
    try:
        record['actual_wait_returncode'] = child.wait(timeout=90)
    except subprocess.TimeoutExpired:
        # This only closes the local read-only SSH client; it sends no Docker or
        # remote training-process signals and never restarts any job.
        child.terminate()
        record['actual_wait_returncode'] = child.wait()
        record['bounded_observation_timed_out'] = True
record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
for name in ('stdout.raw', 'stderr.raw', 'observe_remote.py', 'run.py'):
    raw = (BASE / name).read_bytes()
    record[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
with (BASE / 'execution.json').open('x') as stream:
    json.dump(record, stream, indent=2); stream.write('\n')
print(json.dumps(record))
raise SystemExit(record['actual_wait_returncode'] != 0)
