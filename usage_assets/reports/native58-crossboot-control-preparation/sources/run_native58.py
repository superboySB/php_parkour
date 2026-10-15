#!/usr/bin/env python3
"""Transparent host-only wrapper; replace exactly native58.recovered_previous in memory."""
from __future__ import annotations
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GATE_SHA = '842726d3b6c671c0f863094c17f36262e772f7eb7acda6c4642a03ef419e7ec6'


def load_gate():
    path = HERE / 'crossboot_gate.py'
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != GATE_SHA:
        raise ValueError('Pinned crossboot gate source changed before import')
    spec = importlib.util.spec_from_file_location('native58_explicit_crossboot_gate', path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity():
    raw = Path('/proc/self/stat').read_text()
    fields = raw.rsplit(')', 1)[1].split()
    return {'pid': os.getpid(), 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
            'start_time_clock_ticks': int(fields[19]), 'stat': raw,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'actual_proc_argv': [x.decode() for x in Path('/proc/self/cmdline').read_bytes().split(b'\0') if x]}


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def install_signal_handlers(row, receipt):
    """First signal unwinds original execute; later signals leave its cleanup running."""
    def on_signal(number, frame):
        row['signals'].append({'signal': number, 'observed_utc': utc()})
        write(receipt, row)
        if not row.get('signal_interruption_issued'):
            row['signal_interruption_issued'] = True
            raise KeyboardInterrupt('Explicit wrapper received signal ' + str(number))
    return {number: signal.signal(number, on_signal) for number in (signal.SIGINT, signal.SIGTERM)}


def wait_recovered(gate, data, contract_fp, prep, plan, row, receipt, deadline, poll):
    while True:
        proof = gate.evaluate(data, contract_fp, prep, plan)
        row['gate_calls'].append(proof)
        write(receipt, row)
        if proof['ready']:
            return proof
        if time.monotonic() >= deadline:
            raise gate.Waiting('Read-only admission still waiting; original native receipt/phases never started')
        time.sleep(max(0, min(poll, deadline - time.monotonic())))


def final_control_identity(gate, data, observations):
    """Fresh control identity after original cleanup; no lock/GPU admission claim."""
    observations['boot_id'] = gate.boot_id()
    gate.require(observations['boot_id'] == data['current_boot_id'], 'Boot changed during original execute')
    observations['unix_endpoint'] = gate.endpoint_identity()
    gate.require(observations['unix_endpoint'] == gate.read(data['unix_endpoint_observation'])['paths']['/var/run/docker.sock'],
                 'Unix endpoint changed during original execute')
    observations['actor_context'] = {}
    gate.actor_context(data, observations['actor_context'])
    observations['daemon'] = {}
    daemon = gate.docker_get('/info', observations['daemon'])
    gate.require(gate.daemon_identity(daemon) == data['daemon'], 'Unix daemon changed during original execute')


def load_native(gate, base):
    """Original __file__ and all global science symbols remain their genuine originals."""
    gate.require('common' not in sys.modules and 'phase_cpu' not in sys.modules, 'Ambiguous preloaded common/phase_cpu module rejected')
    gate.require(gate.fingerprint(base / 'control/phase_cpu.py')['sha256'] == gate.PHASE_CPU_SHA, 'Original phase_cpu bytes changed')
    sys.path.insert(0, str(base / 'control'))
    common = gate.load(base / 'control/common.py', 'common')
    sys.modules['common'] = common
    phase_cpu = gate.load(base / 'control/phase_cpu.py', 'phase_cpu')
    sys.modules['phase_cpu'] = phase_cpu
    native = gate.load(base / 'control/native58.py', 'native58_original_frozen_crossboot_host')
    gate.require(native.contracts is common and Path(native.__file__) == base / 'control/native58.py',
                 'Original native/common import provenance differs')
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run',))
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh control receipt directory outside the frozen native base')
    parser.add_argument('--root-authorized-start', action='store_true')
    parser.add_argument('--admission-wait-seconds', type=float, default=0, help='Explicit finite pre-native waiting budget; busy/lock timeout returns waiting exit2')
    parser.add_argument('--poll-seconds', type=float, default=5)
    args = parser.parse_args()
    gate = load_gate()
    gate.require(0 <= args.admission_wait_seconds <= 7 * 86400 and 0.1 <= args.poll_seconds <= 60, 'Bounded finite admission wait/poll required')
    admission_deadline = time.monotonic() + args.admission_wait_seconds
    gate.require(args.root_authorized_start, 'Explicit root native start authorization required')
    data, contract_fp, prep, plan = gate.contract(args.contract, args.contract_sha256)
    base = Path(data['plan']['path']).parent
    output = gate.safe(args.output)
    gate.require(not output.is_relative_to(base) and not base.is_relative_to(output), 'Control output must not overlap original prepared base')
    gate.require(not output.is_relative_to(HERE) and not HERE.is_relative_to(output), 'Control output must not overlap preparation sources')
    native = load_native(gate, base)
    native.verify_snapshot(base, plan)
    native.verify_host_sources(base)
    source_rows = gate.control_records(data, contract_fp, prep)
    source_rows += [gate.fingerprint(base / 'control' / name) for name in ('native58.py', 'common.py', 'phase_cpu.py', 'previous_recovered_02.py')]
    for row in source_rows:
        gate.verify(row)
    # Busy resources return waiting BEFORE calling original execute or creating
    # a native receipt/phase. This never stops unrelated work. The original
    # execute reacquires the lock and repeats the full gate, closing the race.
    while True:
        with gate.safe(gate.MUTEX).open('r+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                precheck = {'status': 'waiting', 'reason': 'Original GPU mutex is held', 'ready_for_original_execute': False, 'native_started': False}
            else:
                precheck = gate.idle_precheck(data)
        if precheck['ready_for_original_execute']:
            break
        print(json.dumps(precheck, allow_nan=False), flush=True)
        if time.monotonic() >= admission_deadline:
            return 2
        time.sleep(max(0, min(args.poll_seconds, admission_deadline - time.monotonic())))
    output.mkdir(parents=True, exist_ok=False)
    row = {'schema_version': 2, 'status': 'starting', 'started_utc': utc(), 'identity': identity(),
           'control_mode': 'explicit_crossboot_native58_single_host_function_override',
           'contract': contract_fp, 'preparation': data['preparation'], 'source_review': data['source_review'],
           'plan': data['plan'], 'original_native': gate.fingerprint(native.__file__),
           'original_common': gate.fingerprint(native.contracts.__file__), 'sources_before': source_rows,
           'pre_execute_idle_check': precheck,
           'replacement': {'module': 'native58', 'symbol': 'recovered_previous',
                           'replacement_source': gate.fingerprint(gate.__file__), 'historical_boot_id': gate.OLD_BOOT},
           'signals': [], 'gate_calls': [], 'quality_verified': False, 'new_scientific_result_claimed_by_wrapper': False}
    receipt = output / 'control-receipt.json'
    write(receipt, row)
    def recovered():
        # The only override in native58. Its original execute owns the mutex.
        return wait_recovered(gate, data, contract_fp, prep, plan, row, receipt, admission_deadline, args.poll_seconds)

    native.recovered_previous = recovered
    original_handler = install_signal_handlers(row, receipt)
    code = 1
    try:
        row['status'] = 'original_execute_called'
        write(receipt, row)
        result = native.execute(argparse.Namespace(plan=Path(data['plan']['path']), root_authorized_start=True))
        gate.require(result['status'] == 'completed' and result['cases'] == 58
                     and result['worker_exit0_empty_groups'] == result['exact_host_maps'] == 116
                     and result['full_decoded_mp4_count'] == 58, 'Original execute did not reach complete58 terminal gate')
        row.update(status='completed_original_native58', original_result=result)
        code = 0
    except gate.Waiting as error:
        gate.require(not (base / 'host/launch-receipt.json').exists() and not any((base / 'phases').iterdir()),
                     'Waiting is allowed only before any original native receipt/phase')
        row.update(status='waiting_native_not_started', reason=str(error))
        code = 2
    except BaseException as error:
        row.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
        code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        # Cleanup remains the original native58 try/finally. Prevent a second
        # signal from interrupting our final receipt after that cleanup returns.
        for number in original_handler:
            signal.signal(number, lambda number, frame: row['signals'].append({'signal': number, 'observed_utc': utc(), 'during_final_receipt': True}))
        try:
            final = row.setdefault('final_control_observations', {})
            final_control_identity(gate, data, final)
            row['final_control_identity_verified'] = True
        except BaseException as error:
            row.update(status='failed', final_control_error=str(error), final_control_identity_verified=False)
            code = 1
        try:
            for item in source_rows:
                gate.verify(item)
            row['sources_after'] = source_rows
            row['sources_unchanged'] = True
        except BaseException as error:
            row.update(status='failed', final_source_error=str(error), sources_unchanged=False)
            code = 1
        try:
            original_receipt = base / 'host/launch-receipt.json'
            if original_receipt.exists():
                row['actual_original_native_receipt'] = gate.fingerprint(original_receipt)
        except BaseException as error:
            row.update(status='failed', final_native_receipt_error=str(error))
            code = 1
        row.update(finished_utc=utc(), wrapper_returncode=code, identity_after=identity())
        write(receipt, row)
        for number, handler in original_handler.items():
            signal.signal(number, handler)
    print(json.dumps({'status': row['status'], 'control_receipt': gate.fingerprint(receipt), 'wrapper_returncode': code}, indent=2))
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'rejected_before_native_execute', 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
