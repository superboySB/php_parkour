"""Shared pure-stdlib evidence/ownership helpers; no native imports."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HARNESS_SHA = 'd9f958830bfb887b18239ee25a2306ddf1c88201bc1415571e6b6665263cd873'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def fingerprint(path):
    path = Path(path)
    return {'sha256': sha(path), 'bytes': path.stat().st_size}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_files(base, records):
    base = Path(base).resolve(strict=True)
    seen = set()
    for item in records:
        relative = Path(item['relative'])
        if relative.is_absolute() or '..' in relative.parts or str(relative) in seen:
            raise ValueError('Unsafe/duplicate frozen input')
        seen.add(str(relative))
        path = base / relative
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(base) or not path.is_file():
            raise ValueError('Frozen input is not an owned regular file')
        if fingerprint(path) != {key: item[key] for key in ('sha256', 'bytes')}:
            raise ValueError('Frozen input changed: ' + str(relative))


def birth_group(module, process):
    value = module.process_identity(process.pid)
    if value.get('process_group_id') != process.pid or value.get('session_id') != process.pid or not isinstance(value.get('start_time_clock_ticks'), int):
        raise RuntimeError('Private worker leader birth identity unavailable')
    birth = {key: value[key] for key in ('pid', 'start_time_clock_ticks')}
    return {'process_group_id': process.pid, 'session_id': process.pid, 'leader_identity': birth,
            'known_members': [dict(birth)], 'retired': False, 'ownership_lost': False}


def ensure_native_identity(module, group, native):
    current = module.process_identity(native['pid'])
    status = module.worker_group_status(group)
    known = {'pid': native['pid'], 'start_time_clock_ticks': native['start_time_clock_ticks']}
    if (not status['ownership_verified'] or known not in status['known_members']
            or any(current.get(key) != native.get(key) for key in ('pid', 'start_time_clock_ticks', 'process_group_id', 'session_id'))
            or current.get('state') == 'Z'):
        raise RuntimeError('Native process birth/group ownership differs')
    return current


def signal_native(module, group, native, number):
    # Exact observed native Python only. Do not interrupt the waiting shell first.
    ensure_native_identity(module, group, native)
    os.kill(native['pid'], number)


def cleanup_group(module, process, group, events, grace=5):
    import signal
    try:
        if module.wait_worker_shutdown(process, group, grace):
            return module.worker_group_status(group)
        for number, delay in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
            events.append({'unix': time.time(), 'pid': process.pid, 'requested_signal': number})
            module.signal_worker_group(group, number)
            if module.wait_worker_shutdown(process, group, delay):
                return module.worker_group_status(group)
        raise RuntimeError('Owned process group still has live members')
    finally:
        # wait() of the direct child is independent of diagnostic persistence.
        try:
            process.wait(timeout=.1)
        except subprocess.TimeoutExpired:
            pass
