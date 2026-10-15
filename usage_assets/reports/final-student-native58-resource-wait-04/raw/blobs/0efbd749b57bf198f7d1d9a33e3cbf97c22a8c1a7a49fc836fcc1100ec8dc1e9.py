#!/usr/bin/env python3
"""Own the actual frozen launcher for one reviewed formal reference629 run.

The pinned original host_owned_launch.py remains the adapter's direct parent.
Only that original source emits its own process-start/process-exit receipts.
This additional wrapper records its own identity, source/contract pins, actual
launcher wait and session cleanup separately. It never manufactures old receipts.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
PREPARATION = ROOT / 'outputs/research/final-student-reference629-preparation-01'
PREPARATION_SHA = '481d54ee84d4b2d9c439580fe83d00927a44bfc8e2a11101b58862b536d49ce0'
ADAPTER = PREPARATION / 'adapter.py'
ADAPTER_SHA = 'ce216a06b36b06b21aa1c110b50f33483a036e17c64f309827ca8480166bbe53'
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and path.is_relative_to(ROOT / 'outputs/research'), 'Explicit research path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path rejected')
    return path


def fp(path):
    path = safe(path)
    require(path.is_file(), 'Actual regular file required: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(data)
    after = path.stat()
    key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(key(before) == key(after), 'File changed during source/evidence hash')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def process(pid):
    text = Path(f'/proc/{pid}/stat').read_text()
    fields = text[text.rfind(')') + 2:].split()
    return {'pid': int(text.split('(', 1)[0]), 'state': fields[0], 'ppid': int(fields[1]),
            'pgid': int(fields[2]), 'sid': int(fields[3]), 'start_time_clock_ticks': int(fields[19]), 'stat': text}


def session_members(pgid, sid):
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            row = process(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row['pgid'] == pgid or row['sid'] == sid:
            rows.append(row)
    return sorted(rows, key=lambda x: x['pid'])


def verify_sources(contract_path, contract_sha):
    sources = [fp(__file__), fp(LAUNCHER), fp(ADAPTER), fp(PREPARATION / 'preparation-manifest.json'), fp(contract_path)]
    require(sources[1]['sha256'] == LAUNCHER_SHA and sources[1]['bytes'] == 2184, 'Original parent launcher changed')
    require(sources[2]['sha256'] == ADAPTER_SHA and sources[3]['sha256'] == PREPARATION_SHA
            and sources[4]['sha256'] == contract_sha, 'Reviewed adapter/preparation/actual contract differs')
    manifest = read(PREPARATION / 'preparation-manifest.json')
    require(len(manifest['files']) == 35, 'Exact reviewed35 preparation files required')
    seen = set()
    for row in manifest['files']:
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in seen, 'Unsafe preparation manifest')
        seen.add(str(relative))
        actual = fp(PREPARATION / relative)
        require((actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256']), 'Frozen preparation dependency changed')
        sources.append(actual)
    contract = read(contract_path)
    require(contract['schema_version'] == 1 and contract['status'] == 'prepared_for_separate_review'
            and contract['contract_identity'] == identity({k: v for k, v in contract.items() if k != 'contract_identity'})
            and contract['expected'] == {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}
            and contract['kind_order'] == ['pure', 'finetune'] and Path(contract['base']) / 'contract.json' == contract_path
            and contract['preparation_manifest'] == sources[3], 'Actual reviewed formal contract identity differs')
    require(not (safe(contract['base']) / 'runs').exists(), 'An already-started scientific attempt is never retried')
    return sources


def run_owned(launcher_argv, adapter_argv, output, sources_before, recheck, science_scope='ordinary_CPU_parent_protocol'):
    """Run an actual original parent; usable with harmless CPU fixtures in tests."""
    output = safe(output)
    require(not output.exists() and output.parent.is_dir(), 'Fresh output with existing parent required')
    output.mkdir()
    pending, forwarded = [], []
    previous_handlers = {}
    for number in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[number] = signal.signal(number, lambda signum, frame: pending.append({'signal': signum, 'utc': now()}))
    receipt = {'schema_version': 1, 'status': 'starting', 'wrapper': fp(__file__), 'launcher_argv': launcher_argv,
        'expected_adapter_argv': adapter_argv, 'started_utc': now(), 'wrapper_process': process(os.getpid()),
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'sources_before': sources_before,
        'pending_signals': pending, 'forwarded_signals': forwarded, 'errors': [], 'quality_verified': False,
        'signal_forwarding_failures': [],
        'science_scope': science_scope,
        'scope': 'Additional real wrapper; original launcher owns the actual adapter Popen/wait and original receipts.'}
    save(output / 'wrapper-start.json', receipt)
    child = None
    result = 1
    handled = 0

    def observe(event, **details):
        nonlocal result
        try:
            with (output / 'wrapper-observations.jsonl').open('a') as stream:
                stream.write(json.dumps({'utc': now(), 'event': event, **details}, allow_nan=False) + '\n')
        except Exception as error:
            # Diagnostic I/O failure must not abandon a live original owner.
            receipt['status'] = 'failed_partial_preserved'
            receipt['errors'].append('observation_write: ' + type(error).__name__ + ': ' + str(error))
            result = 1

    def forward_pending():
        """Retry observation, never signal an unverified or replaced adapter."""
        nonlocal handled
        start_path = output / 'original-parent/process-start.json'
        while handled < len(pending) and start_path.exists():
            request = pending[handled]
            try:
                start = read(start_path)
                require(start['argv'] == adapter_argv and start['launcher_sha256'] == LAUNCHER_SHA
                        and start['parent_pid'] == child.pid and start['boot_id'] == receipt['boot_id'],
                        'Original parent/child argv, source or boot differs before signal forwarding')
                birth = process_stat_from_saved(start['stat'])
                pid = start['pid']
                require(birth['pid'] == birth['pgid'] == birth['sid'] == pid
                        and birth['ppid'] == child.pid and birth['start_time_clock_ticks'] > 0,
                        'Original saved adapter is not the direct private-session child')
                descriptor = os.pidfd_open(pid)
                try:
                    actual = process(pid)
                    require(actual['pid'] == actual['pgid'] == actual['sid'] == pid
                            and actual['ppid'] == child.pid
                            and actual['start_time_clock_ticks'] == birth['start_time_clock_ticks'],
                            'Adapter PID/birth/direct parent reused or unobservable')
                    signal.pidfd_send_signal(descriptor, request['signal'])
                finally:
                    os.close(descriptor)
                forwarded.append(dict(request, adapter_pid=pid, start_time_clock_ticks=birth['start_time_clock_ticks'],
                                      result='sent_to_exact_adapter_birth'))
                handled += 1
            except ProcessLookupError:
                forwarded.append(dict(request, result='already_exited'))
                handled += 1
            except Exception as error:
                # A partial start-file write or failed identity observation is
                # never permission to signal another PID. Keep the real owner
                # under observation and retain diagnostics for operator review.
                message = type(error).__name__ + ': ' + str(error)
                key = {'request_index': handled, 'error': message}
                if not any(all(row.get(k) == v for k, v in key.items()) for row in receipt['signal_forwarding_failures']):
                    failure = {**key, 'utc': now(), 'result': 'awaiting_verified_identity_no_signal_sent'}
                    receipt['signal_forwarding_failures'].append(failure)
                    observe('signal_forwarding_blocked', **failure)
                break

    def wait_for_original_owner():
        while child.poll() is None:
            forward_pending()
            time.sleep(.2)
        return child.wait()

    try:
        with (output / 'launcher.stdout.raw').open('xb') as stdout, (output / 'launcher.stderr.raw').open('xb') as stderr:
            child = subprocess.Popen(launcher_argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                     start_new_session=True, close_fds=True)
            receipt['launcher_process'] = process(child.pid)
            require(receipt['launcher_process']['pid'] == receipt['launcher_process']['pgid'] == receipt['launcher_process']['sid'],
                    'Original launcher must be an observed private session leader')
            save(output / 'launcher-birth.json', receipt['launcher_process'])
            receipt['actual_launcher_wait_returncode'] = wait_for_original_owner()
        receipt['remaining_launcher_session_members'] = session_members(child.pid, child.pid)
        require(receipt['actual_launcher_wait_returncode'] == 0 and receipt['remaining_launcher_session_members'] == []
                and not pending, 'Launcher actual wait/session/operator interruption failed')
        start = read(output / 'original-parent/process-start.json')
        end = read(output / 'original-parent/process-exit.json')
        require(start['argv'] == adapter_argv and start['launcher_sha256'] == LAUNCHER_SHA
                and end['actual_wait_returncode'] == 0 and end['pending_signals'] == []
                and all(end.get(k) == v for k, v in start.items()), 'Original direct-parent start/exit receipt differs')
        adapter = process_stat_from_saved(start['stat'])
        require(adapter['pid'] == adapter['pgid'] == adapter['sid'] == start['pid']
                and adapter['ppid'] == start['parent_pid'] == child.pid and adapter['start_time_clock_ticks'] > 0,
                'Adapter direct original-parent identity differs')
        receipt['remaining_adapter_session_members'] = session_members(adapter['pgid'], adapter['sid'])
        require(receipt['remaining_adapter_session_members'] == [], 'Adapter session was not empty after actual wait')
        receipt['sources_after'] = recheck()
        require(receipt['sources_after'] == sources_before, 'Reviewed sources/contract changed during actual run')
        receipt['original_parent_receipts'] = {name: fp(output / 'original-parent' / name) for name in
            ('process-start.json', 'process-exit.json', 'stdout.raw', 'stderr.raw')}
        receipt['status'] = 'completed_actual_original_parent_wait'
        result = 0
    except BaseException as error:
        receipt['status'] = 'failed_partial_preserved'
        receipt['errors'].append(type(error).__name__ + ': ' + str(error))
        observe('wrapper_supervision_failed', error=receipt['errors'][-1])
        if child is not None:
            # Never abandon the original owner's wait; it remains responsible for
            # the adapter. No timeout kill, cleanup substitution or automatic retry.
            receipt['actual_launcher_wait_returncode'] = wait_for_original_owner()
            receipt['remaining_launcher_session_members'] = session_members(child.pid, child.pid)
    finally:
        receipt['launcher_logs'] = [fp(p) for p in (output / 'launcher.stdout.raw', output / 'launcher.stderr.raw') if p.exists()]
        receipt['original_parent_receipts'] = {name: fp(output / 'original-parent' / name) for name in
            ('process-start.json', 'process-exit.json', 'stdout.raw', 'stderr.raw')
            if (output / 'original-parent' / name).is_file()}
        try:
            receipt['sources_after'] = recheck()
            require(receipt['sources_after'] == sources_before, 'Sources changed before final wrapper receipt')
        except BaseException as error:
            receipt['status'] = 'failed_partial_preserved'
            receipt['errors'].append('final_source_check: ' + type(error).__name__ + ': ' + str(error))
            result = 1
        start_path = output / 'original-parent/process-start.json'
        try:
            if child is not None:
                require(child.poll() is not None, 'Actual original owner is still running')
                receipt['remaining_launcher_session_members'] = session_members(child.pid, child.pid)
                require(start_path.is_file(), 'Original parent start receipt is missing')
                adapter = process_stat_from_saved(read(start_path)['stat'])
                receipt['remaining_adapter_session_members'] = session_members(adapter['pgid'], adapter['sid'])
                require(receipt['remaining_launcher_session_members'] == receipt['remaining_adapter_session_members'] == []
                        and not pending, 'Final owned sessions are not empty or an operator signal was received')
        except BaseException as error:
            receipt['status'] = 'failed_partial_preserved'
            receipt['errors'].append('final_session_check: ' + type(error).__name__ + ': ' + str(error))
            result = 1
        if receipt['signal_forwarding_failures']:
            receipt['status'] = 'failed_partial_preserved'
            result = 1
        receipt['finished_utc'] = now()
        try:
            save(output / 'wrapper-exit.json', receipt)
        finally:
            for number, handler in previous_handlers.items():
                signal.signal(number, handler)
    print(json.dumps({'status': receipt['status'], 'actual_launcher_wait': receipt.get('actual_launcher_wait_returncode'),
                      'wrapper_receipt': fp(output / 'wrapper-exit.json')}))
    return result


def process_stat_from_saved(text):
    fields = text[text.rfind(')') + 2:].split()
    return {'pid': int(text.split('(', 1)[0]), 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
            'start_time_clock_ticks': int(fields[19])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    require(args.root_authorized_start, 'Explicit reviewed operator start required')
    contract_path, output = safe(args.contract), safe(args.output)
    sources = verify_sources(contract_path, args.contract_sha256)
    adapter_argv = ['/usr/bin/python3', '-B', str(ADAPTER), 'execute', '--preparation-sha256', PREPARATION_SHA,
                    '--contract', str(contract_path), '--contract-sha256', args.contract_sha256, '--root-authorized-start']
    launcher_argv = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(ADAPTER), '--sha256', ADAPTER_SHA,
                     '--output', str(output / 'original-parent'), '--', *adapter_argv]
    # Post-run verification rehashes the same sources. The one-attempt runs gate
    # applies only before launch; successful execution necessarily creates runs/.
    return run_owned(launcher_argv, adapter_argv, output, sources, lambda: [fp(r['path']) for r in sources],
                     science_scope='formal_two_student_reference629_execution')


if __name__ == '__main__':
    raise SystemExit(main())
