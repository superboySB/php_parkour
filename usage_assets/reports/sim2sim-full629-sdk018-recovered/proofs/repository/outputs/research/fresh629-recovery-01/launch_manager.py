#!/usr/bin/env python3
"""Detached parent records the real manager child's return code."""
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys

BASE = Path(__file__).resolve().parent
HELPER = BASE / 'manage.py'
EXPECTED = '3fc5a0c45bb5efb48f7c45514a885a0ea986ddae2dd309c819186aec582cccec'

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == EXPECTED
    assert not (BASE / 'manager-process-start.json').exists()
    pending = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda value, frame: pending.append({'utc': utc(), 'signal': value}))
    argv = ['/usr/bin/python3', '-B', str(HELPER), '--root-authorized-adopt']
    with (BASE / 'manager.stdout.raw').open('xb') as out, (BASE / 'manager.stderr.raw').open('xb') as err:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, close_fds=True)
        start = {'argv': argv, 'pid': child.pid, 'stat': Path(f'/proc/{child.pid}/stat').read_text(), 'started_utc': utc(), 'helper_sha256': EXPECTED, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        (BASE / 'manager-process-start.json').open('x').write(json.dumps(start, indent=2) + '\n')
        code = child.wait()
    (BASE / 'manager-process-exit.json').open('x').write(json.dumps({'argv': argv, 'pid': child.pid, 'actual_wait_returncode': code, 'finished_utc': utc(), 'pending_signals': pending, 'original_session54334_exit_code': 143}, indent=2) + '\n')
    return code

if __name__ == '__main__':
    sys.exit(main())
