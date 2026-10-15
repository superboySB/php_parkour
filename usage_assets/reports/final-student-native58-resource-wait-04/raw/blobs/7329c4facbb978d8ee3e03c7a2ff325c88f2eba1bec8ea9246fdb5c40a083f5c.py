#!/usr/bin/env python3
"""Run real ordinary CPU tests and original-parent 0/7/TERM protocols; no Docker/GPU/native."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'


def fp(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--focused-revision', action='store_true', help='Only changed inspect/diagnostic guards plus the original fast e238 protocols')
    a = p.parse_args()
    output = a.output.absolute()
    if fp(LAUNCHER)['sha256'] != LAUNCHER_SHA:
        raise ValueError('Original actual-parent launcher differs')
    output.mkdir(parents=True, exist_ok=False)
    before = [fp(x) for x in sorted(HERE.glob('*')) if x.is_file()]
    records = []
    commands = [('unit', ['/usr/bin/python3', '-B', str(HERE / 'test_crossboot_control.py')]),
                ('wrapper-help', ['/usr/bin/python3', '-B', str(HERE / 'run_native58.py'), '--help']),
                ('gate-help', ['/usr/bin/python3', '-B', str(HERE / 'crossboot_gate.py'), '--help'])]
    if a.focused_revision:
        names = ('test_mount_order_alone_preserves_full_inspect_and_raw_observations',
                 'test_mount_row_content_change_is_rejected_despite_order_normalization',
                 'test_state_change_is_rejected_despite_order_normalization',
                 'test_diagnostics_keep_raw_bytes_before_later_validation_failure',
                 'test_incomplete_http_body_keeps_actual_partial_bytes_status_and_headers')
        commands[0] = ('unit', ['/usr/bin/python3', '-B', '-m', 'unittest', '-v',
                        *['test_gpu_resource_wait.FailedPreviousControls.' + name for name in names]])
    for name, argv in commands:
        with (output / (name + '.stdout.raw')).open('xb') as out, (output / (name + '.stderr.raw')).open('xb') as err:
            environment = dict(os.environ)
            if name == 'unit':
                environment['NATIVE58_CPU_CONTROL_ARTIFACTS'] = str(output / 'ordinary-cpu-query-artifacts')
            process = subprocess.Popen(argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=environment, cwd=HERE)
            code = process.wait(timeout=30)
        records.append({'name': name, 'argv': argv, 'actual_wait_returncode': code,
                        'stdout': fp(output / (name + '.stdout.raw')), 'stderr': fp(output / (name + '.stderr.raw'))})
        if code != 0:
            raise ValueError('CPU command failed: ' + name)
    child = HERE / 'cpu_protocol_child.py'
    for name, expected in [('zero', 0), ('seven', 7), ('sigterm', 130)]:
        directory = output / ('protocol-' + name)
        directory.mkdir()
        parent_output = directory / 'original-parent'
        helper_output = directory / 'cpu-child'
        helper_argv = ['/usr/bin/python3', '-B', str(child), '--output', str(helper_output), '--code', str(expected)]
        if name == 'sigterm':
            helper_argv.append('--wait-for-signal')
        argv = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(child), '--sha256', fp(child)['sha256'],
                '--output', str(parent_output), '--', *helper_argv]
        with (directory / 'launcher.stdout.raw').open('xb') as out, (directory / 'launcher.stderr.raw').open('xb') as err:
            process = subprocess.Popen(argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True)
            signals = []
            if name == 'sigterm':
                deadline = time.monotonic() + 10
                while not (helper_output / 'ready').exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise ValueError('Ordinary CPU child did not become ready')
                    time.sleep(.01)
                started = read(parent_output / 'process-start.json')
                actual = read(helper_output / 'cpu-control.json')['identity']
                pid = started['pid']
                fd = os.pidfd_open(pid)
                try:
                    current = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
                    if (started['argv'] != helper_argv or actual['pid'] != pid or int(current[1]) != process.pid
                            or int(current[19]) != actual['start_time_clock_ticks'] or started['parent_pid'] != process.pid):
                        raise ValueError('CPU signal target birth/parent/source argv differs')
                    for index in range(2):
                        signal.pidfd_send_signal(fd, signal.SIGTERM)
                        signals.append({'signal': signal.SIGTERM, 'target_pid': pid, 'birth': actual['start_time_clock_ticks'],
                                        'transport': 'verified_exact_pidfd', 'index': index})
                        time.sleep(.05)
                finally:
                    os.close(fd)
            code = process.wait(timeout=30)
        start = read(parent_output / 'process-start.json')
        exited = read(parent_output / 'process-exit.json')
        actual_child = read(helper_output / 'cpu-control.json')
        if (code != expected or exited['actual_wait_returncode'] != expected or exited['pending_signals'] != []
                or start['argv'] != helper_argv or exited['argv'] != helper_argv or exited['launcher_sha256'] != LAUNCHER_SHA
                or start['pid'] != exited['pid'] or not actual_child['cleanup_completed']):
            raise ValueError('Real ordinary CPU parent/cleanup protocol differs: ' + name)
        if name == 'sigterm' and len(actual_child['signals']) != 2:
            raise ValueError('Both actual TERM signals must be retained through cleanup')
        records.append({'name': name, 'scope': 'ordinary_cpu_only_not_native58_or_historical629',
                        'argv': argv, 'actual_wait_returncode': code, 'signals': signals,
                        'process_start': fp(parent_output / 'process-start.json'),
                        'process_exit': fp(parent_output / 'process-exit.json'),
                        'cpu_child': fp(helper_output / 'cpu-control.json'),
                        'raw_original_parent_stdout': fp(parent_output / 'stdout.raw'),
                        'raw_original_parent_stderr': fp(parent_output / 'stderr.raw')})
    after = [fp(x) for x in sorted(HERE.glob('*')) if x.is_file()]
    if before != after:
        raise ValueError('Prepared source changed during CPU controls')
    report = {'schema_version': 1, 'status': 'passed_ordinary_cpu_crossboot_control_tests',
              'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'records': records,
              'sources_before': before, 'sources_after': after, 'sources_unchanged': True,
              'unit_tests_expected': 5 if a.focused_revision else 43,
              'focused_revision_controls': a.focused_revision,
              'ordinary_cpu_query_artifacts': [fp(path) for path in sorted((output / 'ordinary-cpu-query-artifacts').rglob('*')) if path.is_file()],
              'scope': 'Synthetic historical/API/session fixtures, actual archived failed41 JSON with offline synthetic current observations, real original native command imports, mutex ownership, ordinary CPU query Popen/timeout/self-signal cleanup, and original e238 CPU parent wait/signals. Query raw receipts retained separately as ordinary CPU stand-ins. No actual historical re-admission, native/GPU run or future scientific result.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'report': fp(output / 'report.json')}))


if __name__ == '__main__':
    raise SystemExit(main())
