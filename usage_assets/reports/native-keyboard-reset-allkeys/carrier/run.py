#!/usr/bin/env python3
"""Explicit operator carrier: original frozen GUI, distinct recovered prerequisite.

Preparation only wrote this file. Running it starts the original native GUI job.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = ROOT / 'outputs/research/fresh629-recovery-01/gui-carrier'
ORIGINAL = ROOT / 'outputs/research/native-keyboard-reset-allkeys-preparation-01'
PLAN = ROOT / 'outputs/research/native-keyboard-reset-allkeys-cohort-01/cohort/plan.json'
GATE = ROOT / 'outputs/research/fresh629-recovery-01/controller-adapter/previous_recovered_02.py'
PINS = {
    ORIGINAL / 'codefreeze.json': '23a5f69799a791de9edf95cbbd030b0d9189d40bd87b7b91a5cc44c2ae1d7f2c',
    ORIGINAL / 'manifest.json': '5c99684ef9c19f6e6e3750c810c2613b72e0a691fae2552038b4c5445289ccf2',
    PLAN: 'c7380ca2cd625df98486c0f090baef22c3ea7af52238f37ea1be649dd93c7402',
    GATE: 'dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525',
}


def fingerprint(path):
    path = Path(path)
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(ROOT):
        raise ValueError('Unsafe carrier dependency: ' + str(path))
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('Carrier dependency changed while reading')
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def frozen_sources():
    result = {}
    for path, expected in PINS.items():
        record = fingerprint(path)
        if record['sha256'] != expected:
            raise ValueError('Frozen carrier prerequisite differs: ' + str(path))
        result[str(path)] = record
    records = json.loads((ORIGINAL / 'codefreeze.json').read_bytes())['files']
    if len(records) != 14 or len({r['relative'] for r in records}) != 14:
        raise ValueError('Require the original fourteen frozen GUI sources')
    for expected in records:
        relative = Path(expected['relative'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe original codefreeze path')
        actual = fingerprint(ORIGINAL / relative)
        if any(actual[key] != expected[key] for key in ('bytes', 'sha256')):
            raise ValueError('Original GUI source differs: ' + str(relative))
        result[str(ORIGINAL / relative)] = actual
    result[str(HERE / 'run.py')] = fingerprint(HERE / 'run.py')
    return result


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(value):
    path = HERE / 'carrier-receipt.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['run'])
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    if not args.root_authorized_start or args.plan != PLAN or Path(__file__).resolve() != HERE / 'run.py':
        raise ValueError('Explicit root flag, exact existing prepared plan and exact carrier path required')
    initial = frozen_sources()
    # Reserve this carrier attempt before any import or resource creation.
    with (HERE / 'carrier-receipt.json').open('x') as stream:
        stream.write('{}\n')
    pending = []
    old_handlers = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    def deferred(number, frame):
        pending.append({'signal': number, 'unix': time.time()})
    for number in old_handlers:
        signal.signal(number, deferred)
    record = {'schema_version': 1, 'status': 'starting_original_frozen_gui', 'started_unix': time.time(),
              'source_before': initial, 'plan': str(PLAN), 'pending_signals': pending,
              'original_14_sources_modified': False, 'substitution': 'previous_completed() only', 'errors': []}
    gate = host = None
    original_run_entered = False
    rc = 1
    old_common = sys.modules.get('common')
    had_common = 'common' in sys.modules
    try:
        save(record)
        gate = load(GATE, '_php_gui_recovered_gate_02')
        sys.modules['common'] = load(ORIGINAL / 'common.py', '_php_gui_frozen_common')
        try:
            host = load(ORIGINAL / 'host_runner.py', '_php_gui_frozen_host')
        finally:
            if had_common:
                sys.modules['common'] = old_common
            else:
                sys.modules.pop('common', None)
        def previous_recovered_only():
            if frozen_sources() != initial:
                raise ValueError('Carrier sources changed before the locked prerequisite gate')
            proof = gate.previous_recovered()
            if proof.get('status') != 'recovered_previous_ready' or proof.get('ready') is not True:
                raise ValueError('Recovered prerequisite is not ready: ' + json.dumps(proof, allow_nan=False))
            return proof | {'carrier': initial[str(HERE / 'run.py')], 'original_gui_sources': initial,
                            'prerequisite_contract': 'recovered original plus separate four attempts; old root143 retained'}
        host.previous_completed = previous_recovered_only
        original_run_entered = True
        rc = host.run(args)
        record['original_runner_returncode'] = rc
    except BaseException as error:
        record['errors'].append(str(error))
        record['traceback'] = traceback.format_exc()
    finally:
        # External INT/TERM remain deferred across original run(), its finally,
        # and this read-only exact own-CID stop confirmation. Never signal native.
        own_receipt = PLAN.parent.parent / 'host/launch-receipt.json'
        stop_confirmed = not original_run_entered
        cid = None
        try:
            original = json.loads(own_receipt.read_bytes()) if own_receipt.exists() else {}
            record['original_receipt'] = fingerprint(own_receipt) if original else None
            cid = original.get('container_id')
            if cid:
                info = gate.docker_get('/containers/' + cid + '/json')
                if (info['Id'] != cid or info['Image'] != host.IMAGE
                        or info['Name'] != '/php-native-gui-' + json.loads(PLAN.read_bytes())['token']
                        or info['State']['StartedAt'] != original['container_before_stop']['state']['StartedAt']
                        or info['State']['Running'] or info['State'].get('Restarting') or info['State'].get('Paused')):
                    raise ValueError('Exact GUI owned CID is not confirmed stopped')
                record['own_container_stop_observed'] = {'container_id': cid, 'state': info['State'], 'image': info['Image']}
                stop_confirmed = True
            elif original.get('status') == 'failed' and original.get('native_started') is False:
                stop_confirmed = True
            record['source_after'] = frozen_sources()
            if record['source_after'] != initial:
                raise ValueError('Carrier/frozen sources changed during original GUI execution')
            if rc == 0 and (original.get('status') != 'completed' or original.get('container_stopped') is not True or not cid):
                raise ValueError('Original GUI completion and owned container stop are required')
        except BaseException as error:
            record['errors'].append('Postcondition: ' + str(error))
        if not stop_confirmed:
            record['status'] = 'cleanup_unknown_readonly_wait'
            try:
                save(record)
            except BaseException as error:
                print('Carrier diagnostic write failed during cleanup wait: ' + str(error), file=sys.stderr)
            # Do not restore signal handlers or exit while own resource stop is
            # unknown. Root must inspect the exact CID; this loop only reads.
            while not stop_confirmed:
                time.sleep(5)
                try:
                    original = json.loads(own_receipt.read_bytes())
                    cid = original.get('container_id')
                    if not cid:
                        continue
                    info = gate.docker_get('/containers/' + cid + '/json')
                    if (info['Id'] == cid and info['Image'] == host.IMAGE
                            and info['Name'] == '/php-native-gui-' + json.loads(PLAN.read_bytes())['token']
                            and info['State']['StartedAt'] == original['container_before_stop']['state']['StartedAt']
                            and info['State']['Running'] is False and not info['State'].get('Restarting')
                            and not info['State'].get('Paused')):
                        record['own_container_stop_observed'] = {'container_id': cid, 'state': info['State'], 'image': info['Image']}
                        stop_confirmed = True
                except BaseException:
                    pass
        record['status'] = 'completed' if rc == 0 and not record['errors'] else 'failed'
        record['finished_unix'] = time.time()
        try:
            save(record)
        finally:
            for number, handler in old_handlers.items():
                signal.signal(number, handler)
    print(json.dumps({'status': record['status'], 'carrier_receipt': str(HERE / 'carrier-receipt.json'),
                      'original_receipt': str(own_receipt), 'pending_signals': pending}))
    return 0 if record['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
