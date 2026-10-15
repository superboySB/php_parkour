"""Bounded host resource admission before any GPU container/worker starts.

All time.monotonic calls are real wall clock. The caller's existing flock is
continuously checked, never acquired or released here. Only this function's
own readonly query clients can receive pidfd signals on timeout/cancellation.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

DEFAULT_WAIT_SECONDS = 1800.0
MAX_WAIT_SECONDS = 3600.0
DEFAULT_POLL_SECONDS = 5.0
QUERY_TIMEOUT_SECONDS = 15.0


def require(value, message):
    if not value:
        raise ValueError(message)


def fp(path):
    path = Path(path)
    a = path.stat()
    require(stat.S_ISREG(a.st_mode) and not path.is_symlink(), 'Regular readonly evidence required')
    raw = path.read_bytes()
    b = path.stat()
    require((a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) ==
            (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns), 'Readonly evidence changed during hash')
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def birth(pid):
    raw = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = raw.rsplit(')', 1)[1].split()
    return {'pid': int(raw.split('(', 1)[0]), 'ppid': int(fields[1]), 'pgid': int(fields[2]),
            'sid': int(fields[3]), 'start_time_clock_ticks': int(fields[19]), 'state': fields[0], 'stat_raw': raw}


def stable_process(row, expected):
    return all(row[k] == expected[k] for k in ('pid', 'ppid', 'pgid', 'sid', 'start_time_clock_ticks'))


def mutex_proof(fd, path, identity, boot):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'GPU mutex path has an alias')
    held, canonical = os.fstat(fd), path.stat()
    require(stat.S_ISREG(held.st_mode) and stat.S_ISREG(canonical.st_mode)
            and (held.st_dev, held.st_ino) == (canonical.st_dev, canonical.st_ino),
            'Caller no longer holds the canonical mutex inode')
    current = birth(os.getpid())
    require(stable_process(current, identity) and current['state'] != 'Z'
            and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot,
            'Host mutex owner birth/boot changed')
    matching = []
    for line in Path('/proc/locks').read_text().splitlines():
        fields = line.split()
        if len(fields) != 8 or fields[1:4] != ['FLOCK', 'ADVISORY', 'WRITE']:
            continue
        device = fields[5].split(':')
        if len(device) != 3:
            continue
        if (int(device[0], 16), int(device[1], 16), int(device[2]), int(fields[4])) == (
                os.major(held.st_dev), os.minor(held.st_dev), held.st_ino, os.getpid()):
            require(fields[6:] == ['0', 'EOF'], 'Unexpected partial GPU flock')
            matching.append(line)
    require(len(matching) == 1, 'Exact current-process exclusive kernel GPU flock absent')
    return {'path': str(path), 'fd': fd, 'device': held.st_dev, 'inode': held.st_ino,
            'owner': current, 'boot_id': boot, 'actual_proc_locks_line': matching[0]}


def empty_query_session(pid):
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            row = birth(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if row['pgid'] == pid or row['sid'] == pid:
            rows.append(row)
    require(not rows, 'Owned readonly query session remains live after actual wait')
    return rows


def query(argv, directory, label, pending, deadline, proof):
    """Actual owned readonly client wait; failures never become busy retries."""
    stdout, stderr = directory / (label + '.stdout.raw'), directory / (label + '.stderr.raw')
    target = directory / (label + '.execution.json')
    receipt = {'argv': argv, 'status': 'starting', 'signals_to_owned_query': [], 'errors': [],
               'scope': 'Only this readonly query client; never a GPU task or scientific worker.'}
    child = handle = identity = None
    failure = None
    started = time.monotonic()

    def remember(error, phase):
        nonlocal failure
        receipt['status'] = 'failed'
        receipt['errors'].append({'phase': phase, 'type': type(error).__name__, 'message': str(error)})
        if failure is None:
            failure = error

    try:
        require(not pending and started < deadline, 'Resource wait cancelled or budget exhausted before query')
        receipt['mutex_before'] = proof()
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
            receipt['actual_Popen_child_pid'] = child.pid
            receipt['actual_direct_parent_pid'] = os.getpid()
            # This unreaped direct child cannot have its PID reused. Bind its
            # pidfd before any diagnostic write or polling which could reap it.
            handle = os.pidfd_open(child.pid)
            identity = birth(child.pid)
            require(identity['pid'] == identity['pgid'] == identity['sid'] and identity['ppid'] == os.getpid()
                    and identity['start_time_clock_ticks'] > 0,
                    'Own readonly query client birth/session differs')
            require(stable_process(birth(child.pid), identity), 'Readonly query PID changed before pidfd binding')
            receipt['child_identity'] = identity
            save(target, receipt)
            query_deadline = min(deadline, started + QUERY_TIMEOUT_SECONDS)
            while child.poll() is None:
                proof()
                require(not pending, 'Operator cancelled host resource admission')
                require(time.monotonic() < query_deadline, 'Readonly GPU query timed out or resource budget exhausted')
                time.sleep(.02)
            receipt['actual_wait_returncode'] = child.wait(timeout=5)
            require(time.monotonic() <= query_deadline, 'Readonly GPU query timed out before actual completion')
            receipt['mutex_after'] = proof()
            require(not pending and time.monotonic() <= deadline, 'Resource wait cancelled or budget exhausted after query')
            require(type(receipt['actual_wait_returncode']) is int and receipt['actual_wait_returncode'] == 0,
                    'Readonly GPU query failed; no query retry')
            receipt['status'] = 'completed'
    except BaseException as error:
        remember(error, 'query')
    finally:
        # A Popen direct child cannot have its PID reused before this parent
        # reaps it. The actual pidfd, when available, pins that same child even
        # if a later /proc diagnostic fails. A missing pidfd uses only this
        # still-unreaped Popen object; it never signals a discovered PID/PGID.
        if child is not None:
            def own_signal(number):
                if child.poll() is not None:
                    return
                via = 'actual_pidfd' if handle is not None else 'owned_unreaped_direct_Popen'
                delivered_pidfd = False
                if handle is not None:
                    try:
                        signal.pidfd_send_signal(handle, number)
                        delivered_pidfd = True
                    except OSError as error:
                        remember(error, 'pidfd-signal')
                        if child.poll() is not None:
                            return
                        via = 'owned_unreaped_direct_Popen_after_pidfd_error'
                if not delivered_pidfd:
                    if number == signal.SIGTERM:
                        child.terminate()
                    else:
                        child.kill()
                receipt['signals_to_owned_query'].append({'signal': number, 'pid': child.pid,
                    'start_time_clock_ticks': identity['start_time_clock_ticks'] if identity else None,
                    'pidfd': delivered_pidfd, 'ownership_basis': via})

            try:
                if child.poll() is None:
                    try:
                        own_signal(signal.SIGTERM)
                    except BaseException as error:
                        remember(error, 'own-term')
                    try:
                        receipt['actual_wait_returncode'] = child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            own_signal(signal.SIGKILL)
                        except BaseException as error:
                            remember(error, 'own-kill')
                        receipt['actual_wait_returncode'] = child.wait(timeout=5)
                else:
                    receipt['actual_wait_returncode'] = child.wait(timeout=5)
            except BaseException as error:
                # Preserve unresolved cleanup as failure, never fabricate a
                # wait or empty session. Every actual wait has a finite bound.
                remember(error, 'cleanup')
                receipt['owned_query_cleanup_unresolved'] = child.poll() is None
            try:
                receipt['remaining_owned_query_session_members'] = empty_query_session(child.pid)
            except BaseException as error:
                remember(error, 'session-check')
        if handle is not None:
            try:
                os.close(handle)
            except OSError as error:
                remember(error, 'pidfd-close')
        receipt['elapsed_real_seconds'] = time.monotonic() - started
        for label_name, path in [('stdout', stdout), ('stderr', stderr)]:
            try:
                if path.is_file():
                    receipt[label_name] = fp(path)
            except BaseException as error:
                remember(error, 'raw-output-hash')
        try:
            save(target, receipt)
        except BaseException as error:
            remember(error, 'final-receipt-write')
    if failure is not None:
        raise failure
    return stdout.read_text(), receipt


def parse_compute(raw, gpu):
    selected = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = [part.strip() for part in line.split(',')]
        require(len(fields) == 2 and re.fullmatch(r'GPU-[0-9a-fA-F-]+', fields[0])
                and fields[1].isdecimal() and int(fields[1]) > 0, 'Malformed GPU compute query output')
        if fields[0] == gpu:
            selected.append({'gpu_uuid': fields[0], 'pid': int(fields[1])})
    require(len({(r['gpu_uuid'], r['pid']) for r in selected}) == len(selected), 'Duplicate selected GPU compute process')
    return selected


def wait_for_idle(fd, lock_path, gpu, output, pending, source_expected,
                  wait_seconds=DEFAULT_WAIT_SECONDS, poll_seconds=DEFAULT_POLL_SECONDS):
    require(type(wait_seconds) in (int, float) and math.isfinite(wait_seconds) and 0 < wait_seconds <= MAX_WAIT_SECONDS,
            'Finite positive resource wait budget <=3600s required')
    require(type(poll_seconds) in (int, float) and math.isfinite(poll_seconds) and .01 <= poll_seconds <= 60,
            'Finite resource poll interval required')
    output = Path(output).absolute()
    require(not output.exists() and output.parent.is_dir()
            and not any(p.is_symlink() for p in (output, *output.parents)), 'Fresh unaliased host resource evidence directory required')
    require(fp(__file__) == source_expected, 'Frozen resource helper source differs')
    identity = birth(os.getpid())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    proof = lambda: mutex_proof(fd, lock_path, identity, boot)
    initial_lock = proof()
    started = time.monotonic()
    deadline = started + wait_seconds
    output.mkdir()
    receipt = {'schema_version': 1, 'status': 'waiting', 'gpu_uuid': gpu,
               'source': source_expected, 'budget_seconds': wait_seconds, 'poll_seconds': poll_seconds,
               'query_timeout_seconds': QUERY_TIMEOUT_SECONDS, 'owner': identity, 'boot_id': boot,
               'mutex_initial': initial_lock, 'rounds': [], 'native_started': False, 'gpu_started': False,
               'science_time_or_timeout_modified': False,
               'scope': 'Host pre-container resource admission only; original worker/native clocks remain real and unchanged.'}

    def persist():
        save(output / 'receipt.json', receipt)

    persist()
    try:
        while True:
            require(not pending, 'Operator cancelled host resource admission')
            require(time.monotonic() < deadline, 'GPU remained busy beyond finite host resource wait budget')
            require(fp(__file__) == source_expected, 'Frozen resource helper changed during admission')
            index = len(receipt['rounds'])
            directory = output / f'round-{index:05d}'
            directory.mkdir()
            row = {'index': index, 'status': 'querying', 'mutex_before': proof()}
            receipt['rounds'].append(row)
            persist()
            devices, q1 = query(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader,nounits'],
                                directory, 'gpu-identity', pending, deadline, proof)
            row['identity_query'] = q1
            persist()
            require(devices.splitlines().count(gpu) == 1, 'Exact GPU UUID is not uniquely present')
            compute, q2 = query(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'],
                                directory, 'gpu-compute', pending, deadline, proof)
            row['compute_query'] = q2
            row['existing_selected_compute_processes'] = parse_compute(compute, gpu)
            row['mutex_after'] = proof()
            row['status'] = 'busy' if row['existing_selected_compute_processes'] else 'idle'
            row['elapsed_real_seconds'] = time.monotonic() - started
            persist()
            require(not pending and time.monotonic() <= deadline, 'Resource wait cancelled or budget exhausted after GPU observations')
            if not row['existing_selected_compute_processes']:
                receipt['status'] = 'ready'
                break
            remaining = min(poll_seconds, deadline - time.monotonic())
            while remaining > 0:
                before_sleep = time.monotonic()
                require(not pending, 'Operator cancelled host resource admission')
                proof()
                time.sleep(min(.1, remaining))
                remaining -= time.monotonic() - before_sleep
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        # Always attempt to retain the first failure and independent final
        # diagnostics. A secondary proof/hash error must never erase it.
        receipt['elapsed_real_seconds'] = time.monotonic() - started
        receipt['pending_signals'] = list(pending)
        final_errors = []
        for label, operation in [('mutex_final', proof), ('source_after', lambda: fp(__file__))]:
            try:
                receipt[label] = operation()
            except BaseException as error:
                final_errors.append({'phase': label, 'type': type(error).__name__, 'message': str(error)})
        if receipt.get('source_after') != source_expected:
            final_errors.append({'phase': 'source_after', 'type': 'ValueError',
                                 'message': 'Resource helper source changed before return'})
        if final_errors:
            receipt['status'] = 'failed'
            receipt['final_errors'] = final_errors
        try:
            persist()
        except BaseException as error:
            # The outer original runner retains this failure as well. Preserve
            # the first admission error when final diagnostics cannot be stored.
            if 'error' not in receipt:
                raise
            print('Resource admission final diagnostic write failed: '+str(error), file=sys.stderr)
        if final_errors and 'error' not in receipt:
            raise ValueError('Final host resource admission proof failed; inspect retained receipt')
    return receipt
