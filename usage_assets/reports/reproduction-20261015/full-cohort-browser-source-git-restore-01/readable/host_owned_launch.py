#!/usr/bin/env python3
"""Record the actual parent wait for one reviewed, independently owned job."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    helper = args.helper.resolve(strict=True)
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == args.sha256
    argv = args.argv[1:] if args.argv and args.argv[0] == '--' else args.argv
    assert argv[:3] == ['/usr/bin/python3', '-B', str(helper)]
    args.output.mkdir(parents=True, exist_ok=False)
    pending = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda value, frame: pending.append({'utc': utc(), 'signal': value}))
    row = {'argv': argv, 'helper_sha256': args.sha256, 'parent_pid': os.getpid(),
           'parent_stat': Path('/proc/self/stat').read_text(), 'started_utc': utc(),
           'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
           'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (args.output / 'stdout.raw').open('xb') as out, (args.output / 'stderr.raw').open('xb') as err:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                 start_new_session=True, close_fds=True)
        row.update(pid=child.pid, stat=Path(f'/proc/{child.pid}/stat').read_text())
        (args.output / 'process-start.json').open('x').write(json.dumps(row, indent=2) + '\n')
        code = child.wait()
    row.update(actual_wait_returncode=code, finished_utc=utc(), pending_signals=pending)
    (args.output / 'process-exit.json').open('x').write(json.dumps(row, indent=2) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
