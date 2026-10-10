"""Root operator receipt helper: replace only an exact, still-waiting watcher.

This is sent to the remote host on stdin by upgrade_waiting_watch.py. It has no
Docker mutation command, no process-group signal and no native/GPU execution.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path('/diff/dzp_is_sb/php-parkour-research')
APPROVED_TREE = '02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c'
OLD_TREE = '8d9ee8a4dea5cccb8bac5664fb779fe8f5a102d6fd38104649ab28bd33010772'
TRAIN_TREE = '0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab'
IMAGE = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
GPU = 'GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5'
OLD_PID, OLD_START = 3940821, 701292491
NEW_COVERAGE = ROOT / 'outputs/coverage-official-final-ro-assets-v2'
NEW_LOG = ROOT / 'outputs/posttrain-monitor-ro-assets-v2.log'
OLD_COVERAGE = ROOT / 'outputs/coverage-official-final'
OLD_COMMAND = ['python3', '-B', str(ROOT / 'source' / OLD_TREE / 'scripts/research/posttrain_coverage.py'),
               'watch', '--source-tree', OLD_TREE, '--poll-seconds', '60']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def read(path):
    return json.loads(Path(path).read_text())


def capture(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, f'Read-only command failed: {argv!r}: {result.stderr}')
    return result.stdout.strip()


def stat_fields(raw):
    tail = raw.rsplit(') ', 1)[1].split()
    return {'state': tail[0], 'pgid': int(tail[2]), 'sid': int(tail[3]), 'start_ticks': int(tail[19])}


def process(pid, proc=Path('/proc')):
    base = proc / str(pid)
    boot_before = (proc / 'sys/kernel/random/boot_id').read_text().strip()
    first = stat_fields((base / 'stat').read_text())
    command = [part.decode() for part in (base / 'cmdline').read_bytes().split(b'\0') if part]
    last = stat_fields((base / 'stat').read_text())
    boot_after = (proc / 'sys/kernel/random/boot_id').read_text().strip()
    require(first['start_ticks'] == last['start_ticks'] and first['pgid'] == last['pgid']
            and first['sid'] == last['sid'] and boot_before == boot_after,
            'Process birth/namespace changed during observation')
    require(re.fullmatch(r'[0-9a-f-]{36}', boot_before), 'Invalid boot ID')
    return {'pid': pid, **last, 'cmdline': command, 'boot_id': boot_before}


def old_identity(record, boot=None):
    require(record['pid'] == OLD_PID and record['start_ticks'] == OLD_START
            and record['pgid'] == record['sid'] == OLD_PID and record['cmdline'] == OLD_COMMAND
            and record['state'] not in ('Z', 'X') and (boot is None or record['boot_id'] == boot),
            'Old PID is not the exact archived waiting watcher; refusing any signal')


def waiting_status(path):
    value = read(path)
    require(value['status'] == 'waiting' and value.get('gpu_started') is False,
            'Watcher has left the waiting state')
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(value['observed_utc'])).total_seconds()
    require(-5 <= age <= 95, 'Watcher waiting status is stale')
    return value


def system_snapshot():
    ids = sorted(capture(['docker', 'ps', '-aq', '--no-trunc']).splitlines())
    all_info = json.loads(capture(['docker', 'inspect', *ids])) if ids else []
    require(not any((info.get('Config', {}).get('Labels') or {}).get('php.posttrain.role')
                    or info.get('Name', '').startswith('/php-parkour-posttrain-') for info in all_info),
            'A CPU/GPU posttrain container already exists; do not replace its monitor')
    selected = [info for info in all_info if info.get('Name') == '/php-parkour-cloud-research']
    require(len(selected) == 1, 'Official container is absent/ambiguous')
    info = selected[0]
    require(info['Image'] == IMAGE and info['State']['Running'], 'Official container image/running state changed')
    mounts = sorted(info['Mounts'], key=lambda item: item['Destination'])
    source = next(item for item in mounts if item['Destination'] == '/workspace/php_parkour')
    require(source['Source'] == str(ROOT / 'source' / TRAIN_TREE), 'Official source binding changed')
    top = capture(['docker', 'top', info['Id'], '-eo', 'pid,args'])
    native = []
    for line in top.splitlines()[1:]:
        if 'wbt_training.train_agent' in line:
            value = process(int(line.split(None, 1)[0]))
            require(value['state'] not in ('Z', 'X'), 'Official native training process is not live')
            # Scheduler state R/S may change while birth/arguments must not.
            native.append({key: value[key] for key in ('pid', 'start_ticks', 'pgid', 'sid', 'cmdline', 'boot_id')})
    require(native, 'No official native training process; upgrade only a still-waiting monitor')
    return {'docker_ids': ids, 'official': {'Id': info['Id'], 'Image': info['Image'],
        'Pid': info['State']['Pid'], 'StartedAt': info['State']['StartedAt'], 'Running': info['State']['Running'],
        'Mounts': mounts}, 'native_training': sorted(native, key=lambda item: item['pid'])}


def old_guard(boot=None):
    identity = process(OLD_PID)
    old_identity(identity, boot)
    waiting = waiting_status(OLD_COVERAGE / 'monitor-status.json')
    entries = list(OLD_COVERAGE.rglob('*'))
    require(all(path.is_file() and not path.is_symlink() for path in entries), 'Old coverage has directories/links or nonregular evidence')
    files = sorted(path.relative_to(OLD_COVERAGE).as_posix() for path in entries)
    require(files == ['monitor-status.json', 'monitor.lock'], 'Old coverage contains selection/attempts or unexpected files')
    launch = read(ROOT / 'outputs/posttrain-monitor-launch.json')
    require(launch['pid'] == OLD_PID and launch['source_tree'] == OLD_TREE and launch['command'] == OLD_COMMAND,
            'Original watcher launch receipt differs from its exact live process')
    require(sha(Path(OLD_COMMAND[2]).read_bytes()) == '00b7ad8d215f04d603ae696cafa613d15cd1287066a1387ddde376ba7203dff0',
            'Old frozen watcher source changed')
    require(not NEW_COVERAGE.exists() and not NEW_LOG.exists(), 'New cohort/log already exists; preserve it and refuse overwrite')
    return {'process': identity, 'waiting': waiting, 'coverage_files': files}


def command(tree, action):
    return ['python3', '-B', str(ROOT / 'source' / tree / 'scripts/research/posttrain_coverage.py'), action,
        '--root', str(ROOT), '--source-tree', tree, '--image', IMAGE, '--gpu-uuid', GPU,
        '--coverage-output', str(NEW_COVERAGE), '--poll-seconds', '60']


def verify_new_source(tree):
    source = ROOT / 'source' / tree
    script = source / 'scripts/research/posttrain_coverage.py'
    require(tree not in (OLD_TREE, TRAIN_TREE), 'Use a genuinely new committed coverage tree')
    spec = importlib.util.spec_from_file_location('posttrain_upgrade_candidate', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_snapshot(SimpleNamespace(root=ROOT, source_tree=tree, image=IMAGE))
    require(module.TRAIN_TREE == TRAIN_TREE and module.IMAGE_CONTENTS == '2a43037e2397fac3e343e8d621dd42c41ea7c27da82602789d575fddda112482',
            'Accepted official image/source fingerprint changed')
    argv = command(tree, 'dry-run')
    result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
    require(result.returncode == 0, 'Candidate read-only dry-run failed: ' + result.stderr)
    value = json.loads(result.stdout)
    require(value['status'] == 'waiting' and value.get('gpu_started') is False and not NEW_COVERAGE.exists(),
            'Candidate is not waiting or dry-run created the new cohort')
    return {'script_sha256': sha(script.read_bytes()), 'source_manifest_sha256': sha((source / 'source-manifest.json').read_bytes()),
            'dry_run': value, 'dry_run_command': argv, 'dry_run_stdout': result.stdout,
            'dry_run_stderr': result.stderr, 'dry_run_returncode': result.returncode}


def retain_regular(source, target):
    source = Path(source)
    require(not source.is_symlink() and stat.S_ISREG(source.stat().st_mode), 'Only regular original watcher files may be archived')
    with source.open('rb') as stream:
        first = os.fstat(stream.fileno())
        raw = stream.read()
        last = os.fstat(stream.fileno())
    require((first.st_ino, first.st_size, first.st_mtime_ns) == (last.st_ino, last.st_size, last.st_mtime_ns),
            'Watcher file changed while being archived; retry a fresh audit')
    with Path(target).open('xb') as stream:
        stream.write(raw)
    return {'source': str(source), 'retained': str(target), 'bytes': len(raw), 'sha256': sha(raw)}


def terminate_exact_old(expected, timeout=20, receipt=None):
    """Pidfd is required: no PID-only fallback can close the reuse race."""
    receipt = {} if receipt is None else receipt
    receipt.update(pid=OLD_PID, start_ticks=OLD_START, boot_id=expected['boot_id'],
                   signal='SIGTERM', mechanism='pidfd', signal_sent=False, exit_observed=False)
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'),
            'Safe pidfd signalling is unavailable; no PID-only signal was sent')
    old_identity(process(OLD_PID), expected['boot_id'])
    descriptor = os.pidfd_open(OLD_PID, 0)
    try:
        old_identity(process(OLD_PID), expected['boot_id'])
        signal.pidfd_send_signal(descriptor, signal.SIGTERM, None, 0)
        receipt['signal_sent'] = True
        poll = select.poll()
        poll.register(descriptor, select.POLLIN)
        require(bool(poll.poll(int(timeout * 1000))), 'Old watcher did not exit after its sole SIGTERM; no escalation')
        receipt['exit_observed'] = True
    finally:
        os.close(descriptor)
    try:
        remaining = process(OLD_PID)
    except FileNotFoundError:
        remaining = None
    if remaining is not None:
        require(remaining['start_ticks'] != OLD_START or remaining['state'] in ('Z', 'X'),
                'Old watcher remains live after pidfd exit receipt')
    receipt['remaining_pid_observation'] = remaining
    return receipt


def global_lock_free():
    # Existing inode only; do not create/replace the lock used by the monitor.
    path = ROOT / 'outputs/.posttrain-coverage.lock'
    require(path.is_file() and not path.is_symlink(), 'Existing global monitor lock is absent/unsafe')
    with path.open('r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(stream, fcntl.LOCK_UN)
    return {'path': str(path), 'available': True}


def run(tree, phase, attempt, helper_sha256):
    require(re.fullmatch(r'[0-9a-f]{64}', tree) and re.fullmatch(r'[0-9a-f]{64}', helper_sha256), 'Invalid source/helper SHA')
    require(tree == APPROVED_TREE, 'Source SHA is not the exact root-reviewed and synced upgrade tree')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', attempt), 'Invalid attempt name')
    require(phase in ('audit', 'upgrade'), 'Unknown phase')
    base = ROOT / 'outputs/posttrain-monitor-upgrade-v2' / attempt
    directory = base / phase
    directory.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'phase': phase, 'source_tree': tree, 'helper_sha256': helper_sha256,
              'started_utc': now(), 'status': 'running', 'completion_verified': False, 'quality_verified': False,
              'docker_mutations': [], 'signals': [], 'watch_command': command(tree, 'watch')}
    report['pidfd_capabilities'] = {'pidfd_open': hasattr(os, 'pidfd_open'),
                                  'pidfd_send_signal': hasattr(signal, 'pidfd_send_signal')}
    before = None
    try:
        before = system_snapshot()
        report['training_before'] = before
        audit = read(base / 'audit/report.json') if phase == 'upgrade' else None
        if audit:
            require(audit['status'] == 'passed' and audit['source_tree'] == tree
                    and audit['helper_sha256'] == helper_sha256 and audit['training_after'] == before,
                    'Successful audit identity/helper/training fingerprint no longer matches')
        old = old_guard(audit['old_watch']['process']['boot_id'] if audit else None)
        report['old_watch'] = old
        report['candidate'] = verify_new_source(tree)
        if audit:
            require(report['candidate'] == audit['candidate'], 'Candidate source/dry-run changed since the audit')
            for item in audit['archived_originals']:
                require(sha(Path(item['retained']).read_bytes()) == item['sha256'], 'Original watcher archive changed')
        report['archived_originals'] = [retain_regular(path, directory / label) for path, label in (
            (OLD_COVERAGE / 'monitor-status.json', 'old-monitor-status.json'),
            (ROOT / 'outputs/posttrain-monitor.log', 'old-monitor.log'),
            (ROOT / 'outputs/posttrain-monitor-launch.json', 'old-monitor-launch.json'))]
        require(system_snapshot() == before, 'Official container/native process/Docker IDs changed during preparation')
        if phase == 'upgrade':
            # Recheck status/no-child immediately before the only allowed signal.
            old_guard(old['process']['boot_id'])
            event = {}
            report['signals'].append(event)
            terminate_exact_old(old['process'], receipt=event)
            report['released_global_lock'] = global_lock_free()
            require(system_snapshot() == before, 'Official task changed after stopping the waiting watcher')
            second = verify_new_source(tree)
            require(second == report['candidate'], 'Candidate changed immediately before new watcher launch')
            NEW_COVERAGE.mkdir(exist_ok=False)
            launched_utc = now()
            with NEW_LOG.open('xb', buffering=0) as log:
                child = subprocess.Popen(command(tree, 'watch'), stdin=subprocess.DEVNULL, stdout=log,
                                         stderr=subprocess.STDOUT, start_new_session=True, cwd=str(ROOT))
            report['new_watch'] = {'pid': child.pid, 'command': command(tree, 'watch'), 'log': str(NEW_LOG), 'launched_utc': launched_utc}
            write(directory / 'new-started.json', report['new_watch'])
            time.sleep(2)
            require(child.poll() is None, 'New watcher exited; preserve its new cohort/log and do not retry automatically')
            new = process(child.pid)
            require(new['cmdline'] == command(tree, 'watch') and new['pgid'] == new['sid'] == child.pid
                    and new['boot_id'] == old['process']['boot_id'] and new['state'] not in ('Z', 'X'),
                    'New watcher birth/arguments/session differ')
            report['new_watch']['process'] = new
            report['new_watch']['waiting'] = waiting_status(NEW_COVERAGE / 'monitor-status.json')
            require(report['new_watch']['waiting']['observed_utc'] >= report['new_watch']['launched_utc'],
                    'New watcher status predates its own launch')
            require(sorted(path.name for path in NEW_COVERAGE.iterdir()) == ['monitor-status.json', 'monitor.lock'],
                    'New watcher created CPU/GPU selection instead of remaining waiting')
            write(directory / 'new-launch.json', report['new_watch'])
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['status'] = 'failed'
        raise
    finally:
        try:
            after = system_snapshot()
            report['training_after'] = after
            report['official_native_and_docker_unchanged'] = before is not None and after == before
            if before is not None:
                require(after == before, 'Official/Docker identity changed; no Docker stop/start or further signal is permitted')
            if report['status'] != 'failed':
                report['status'] = 'passed'
        except BaseException as error:
            report['final_observation_error'] = f'{type(error).__name__}: {error}'
            report['status'] = 'failed'
        report['finished_utc'] = now()
        write(directory / 'report.json', report)
        print(json.dumps(report, indent=2), flush=True)
    require(report['status'] == 'passed', 'Upgrade audit/operation failed; preserve every receipt and do not automatically retry')
    return report


if __name__ == '__main__':
    run(*sys.argv[1:])
