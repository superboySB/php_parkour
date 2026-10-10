#!/usr/bin/env python3
"""Prepare or explicitly run the exact waiting-watcher audit/upgrade over SSH.

Default prints a reviewable argv and executes nothing. Root must first commit
and sync the new immutable source, then explicitly run audit and upgrade with
the same --attempt. Neither helper installs a host package or mutates Docker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

APPROVED_TREE = '02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-tree', default=APPROVED_TREE)
    parser.add_argument('--phase', choices=('audit', 'upgrade'), default='audit')
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--receipt-dir', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}', args.source_tree) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', args.attempt):
        parser.error('Use a full source tree SHA and safe unique attempt name')
    if args.source_tree != APPROVED_TREE:
        parser.error('This receipt helper is bound to root-reviewed synced source ' + APPROVED_TREE)
    remote_path = Path(__file__).with_name('upgrade_waiting_watch_remote.py')
    raw = remote_path.read_bytes()
    code_sha = hashlib.sha256(raw).hexdigest()
    argv = ['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=10m', '-o', 'ControlPath=~/.ssh/php-parkour-%C',
            'tencent-231', shlex.join(['python3', '-B', '-', args.source_tree, args.phase, args.attempt, code_sha])]
    preview = {'status': 'preview_only_no_ssh' if not args.execute else 'explicit_operator_execution',
               'command': argv, 'remote_helper_sha256': code_sha, 'remote_phase': args.phase,
               'source_tree': args.source_tree, 'attempt': args.attempt,
               'remote_receipt': '/diff/dzp_is_sb/php-parkour-research/outputs/posttrain-monitor-upgrade-v2/' + args.attempt + '/' + args.phase}
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return 0
    if args.receipt_dir is None:
        parser.error('--execute requires a fresh --receipt-dir')
    args.receipt_dir.mkdir(parents=True, exist_ok=False)
    (args.receipt_dir / 'remote-source.py').write_bytes(raw)
    (args.receipt_dir / 'host-source.py').write_bytes(Path(__file__).read_bytes())
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    timeout_error = None
    try:
        result = subprocess.run(argv, input=raw, capture_output=True, timeout=600)
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, returncode = error.stdout or b'', error.stderr or b'', None
        timeout_error = str(error)
    (args.receipt_dir / 'stdout.json').write_bytes(stdout)
    (args.receipt_dir / 'stderr.log').write_bytes(stderr)
    receipt = {**preview, 'started_utc': started, 'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'returncode': returncode, 'timeout_error': timeout_error,
               'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(stderr).hexdigest()}
    (args.receipt_dir / 'launch-exit.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return returncode if returncode is not None else 124


if __name__ == '__main__':
    raise SystemExit(main())
