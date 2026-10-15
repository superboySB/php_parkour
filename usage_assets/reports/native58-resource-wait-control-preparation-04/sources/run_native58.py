#!/usr/bin/env python3
"""Explicit two host overrides: recovered_previous and bounded recorded gpu_idle."""
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
GATE_SHA = 'd5f85fde8c36de1c98b25b5521d12652e5ccf6f64b129b13652c2245c468a188'
RESOURCE_SHA = '8e0914a76f18e5d7a3611b5a93f6f4ad85b32f1082583e63dd52797b326c2b79'


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
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root-authorized-start', action='store_true')
    parser.add_argument('--admission-wait-seconds', type=float, default=0)
    parser.add_argument('--poll-seconds', type=float, default=5)
    args = parser.parse_args(); gate = load_gate()
    gate.require(args.root_authorized_start and 0 <= args.admission_wait_seconds <= 7 * 86400
                 and .1 <= args.poll_seconds <= 60, 'Explicit start and finite admission waiting policy required')
    data, contract_fp, prep, plan = gate.contract(args.contract, args.contract_sha256)
    gate.require(plan['host_total_timeout_seconds'] == 43200, 'Original12h host total wall bound must remain unchanged')
    base = Path(data['plan']['path']).parent; output = gate.safe(args.output)
    gate.require(not output.is_relative_to(base) and not base.is_relative_to(output)
                 and not output.is_relative_to(HERE) and not HERE.is_relative_to(output), 'Fresh independent control receipt tree required')
    native = load_native(gate, base)
    native.verify_snapshot(base, plan); native.verify_host_sources(base)
    gate.require(native.time is time, 'Original native time module must remain real and unmodified')
    resource_path = HERE / 'gpu_resource_wait.py'
    gate.require(gate.fingerprint(resource_path)['sha256'] == RESOURCE_SHA, 'Pinned host resource source changed')
    resource_module = gate.load(resource_path, 'native58_recorded_resource_wait')
    sources = gate.control_records(data, contract_fp, prep)
    for item in sources:
        gate.verify(item)
    output.mkdir(parents=True, exist_ok=False); receipt = output / 'control-receipt.json'
    row = {'schema_version': 3, 'status': 'waiting_for_admission', 'started_utc': utc(), 'identity': identity(),
           'control_mode': 'explicit_crossboot_native58_two_host_function_overrides', 'contract': contract_fp,
           'preparation': data['preparation'], 'source_review': data['source_review'], 'plan': data['plan'],
           'failed41_review': data['failed41_review'], 'original_native': gate.fingerprint(native.__file__),
           'original_common': gate.fingerprint(native.contracts.__file__), 'sources_before': sources,
           'host_overrides': ['recovered_previous', 'gpu_idle'], 'time_module_unmodified': True,
           'resource_policy': {'per_gpu_idle_call_budget_seconds': data.get('resource_wait_seconds', 1800),
               'max_contract_budget_seconds': 3600, 'query_timeout_seconds_max': 30,
               'overall_original_wall_seconds': 43200, 'waiting_counts_against_original_wall': True,
               'original_plan_and_worker_timers_unchanged': True},
           'signals': [], 'gate_calls': [], 'pre_execute_idle_checks': [], 'quality_verified': False,
           'new_scientific_result_claimed_by_wrapper': False}
    write(receipt, row)
    row['readonly_diagnostic_records'] = gate.configure_diagnostics(output / 'readonly-observations', base)
    resource = resource_module.ResourceWait(native, gate, data, plan, output / 'gpu-queries', lambda: write(receipt, row))
    row['gpu_queries'], row['resource_wait_calls'] = resource.queries, resource.calls
    row['original_gpu_guard_ast_sha256'] = resource.guard_ast_sha256
    row['resource_source'] = gate.fingerprint(resource_path)
    gate.QUERY_OBSERVER = resource.observe
    deadline = time.monotonic() + args.admission_wait_seconds

    def recovered():
        return wait_recovered(gate, data, contract_fp, prep, plan, row, receipt, deadline, args.poll_seconds)

    native.recovered_previous = recovered
    native.gpu_idle = resource.wait
    handlers = install_signal_handlers(row, receipt); code = 1
    try:
        while True:
            with gate.safe(gate.MUTEX).open('r+') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    checked = {'status': 'waiting', 'reason': 'Original GPU mutex is held', 'ready_for_original_execute': False}
                else:
                    checked = gate.idle_precheck(data)
            row['pre_execute_idle_checks'].append(checked); write(receipt, row)
            if checked['ready_for_original_execute']:
                break
            if time.monotonic() >= deadline:
                raise gate.Waiting('Pre-execute GPU/mutex admission still waiting')
            time.sleep(max(0, min(args.poll_seconds, deadline - time.monotonic())))
        resource.execute_started = time.monotonic()
        row.update(status='original_execute_called', original_execute_started_monotonic=resource.execute_started,
                   overall_guard_start_scope='Conservative actual host monotonic immediately before original execute, earlier than its local deadline')
        write(receipt, row)
        result = native.execute(argparse.Namespace(plan=Path(data['plan']['path']), root_authorized_start=True))
        gate.require(result['status'] == 'completed' and result['cases'] == result['full_decoded_mp4_count'] == 58
                     and result['worker_exit0_empty_groups'] == result['exact_host_maps'] == 116,
                     'Original native58 terminal gate did not complete')
        gate.require(native.time is time, 'Native host time binding changed')
        row.update(status='completed_original_native58', original_result=result); code = 0
    except gate.Waiting as pending:
        gate.require(not (base / 'host/launch-receipt.json').exists() and not any((base / 'phases').iterdir()),
                     'Waiting status is valid only before actual native starts')
        row.update(status='waiting_native_not_started', reason=str(pending)); code = 2
    except BaseException as error:
        row.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
        code = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        for number in handlers:
            signal.signal(number, lambda number, frame: row['signals'].append({'signal': number, 'observed_utc': utc(), 'during_final_receipt': True}))
        try:
            final_control_identity(gate, data, row.setdefault('final_control_observations', {}))
            row['final_control_identity_verified'] = True
        except BaseException as error:
            row.update(status='failed', final_control_error=str(error), final_control_identity_verified=False); code = 1
        try:
            for item in sources:
                gate.verify(item)
            row.update(sources_after=sources, sources_unchanged=True)
        except BaseException as error:
            row.update(status='failed', final_source_error=str(error), sources_unchanged=False); code = 1
        try:
            original = base / 'host/launch-receipt.json'
            if original.exists():
                row['actual_original_native_receipt'] = gate.fingerprint(original)
        except BaseException as error:
            row.update(status='failed', final_native_receipt_error=str(error)); code = 1
        row.update(finished_utc=utc(), wrapper_returncode=code, identity_after=identity())
        write(receipt, row)
        for number, handler in handlers.items():
            signal.signal(number, handler)
    print(json.dumps({'status': row['status'], 'control_receipt': gate.fingerprint(receipt), 'wrapper_returncode': code}))
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'rejected_before_native_execute', 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)

