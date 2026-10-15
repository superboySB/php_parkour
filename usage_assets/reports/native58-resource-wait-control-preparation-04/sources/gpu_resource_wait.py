"""Recorded host GPU availability checks; never signal any GPU workload."""
from __future__ import annotations
import ast
import datetime
import hashlib
import io
import json
import locale
import signal
from pathlib import Path
import subprocess
import time
import types

BUSY = 'Selected GPU has existing compute; never stop other work'


class ResourceWait:
    def __init__(self, native, gate, contract, plan, output, receipt_callback):
        self.native, self.gate, self.contract, self.plan = native, gate, contract, plan
        self.output = output; self.output.mkdir(exist_ok=False)
        self.flush = receipt_callback
        self.execute_started = None
        self.current_call_deadline = None
        self.calls, self.queries = [], []
        self.budget = contract.get('resource_wait_seconds', 1800)
        self.poll = contract.get('resource_poll_seconds', 5)
        gate.require(type(self.budget) in (int, float) and 0 < self.budget <= 3600
                     and type(self.poll) in (int, float) and .1 <= self.poll <= 60, 'Finite bounded host resource waiting policy required')
        raw = Path(native.__file__).read_bytes()
        gate.require(hashlib.sha256(raw).hexdigest() == gate.NATIVE_SHA, 'Original native GPU guard source changed')
        tree = ast.parse(raw)
        nodes = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
                 for name in ('call', 'gpu_idle')]
        self.guard_ast_sha256 = hashlib.sha256(ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False).encode()).hexdigest()
        namespace = {'subprocess': types.SimpleNamespace(run=self.query), 'require': native.require, 'UUID': native.UUID}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), native.__file__, 'exec'), namespace)
        self.original_checks = namespace['gpu_idle']

    def owned(self):
        self.gate.require(self.gate.boot_id() == self.contract['current_boot_id'], 'Actual wrapper boot changed')
        row = self.gate.require_owned_mutex()
        self.gate.verify_reviewed_mutex(row, self.contract)
        return row

    def overall_remaining(self):
        if self.execute_started is None:
            return float('inf')
        remaining = self.plan['host_total_timeout_seconds'] - (time.monotonic() - self.execute_started)
        self.gate.require(remaining > 0, 'Original whole58 host wall limit reached during resource admission')
        return remaining

    @staticmethod
    def text(raw):
        with io.TextIOWrapper(io.BytesIO(raw), encoding=locale.getpreferredencoding(False), newline=None) as stream:
            return stream.read()

    def query(self, argv, **kwargs):
        self.owned()
        self.gate.require(argv in (['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'],
                                  ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'])
                          and kwargs == {'capture_output': True, 'text': True, 'timeout': 60},
                          'Only the exact original native GPU query guard is accepted')
        timeout = min(30, self.overall_remaining(),
                      float('inf') if self.current_call_deadline is None else self.current_call_deadline - time.monotonic())
        self.gate.require(timeout > 0, 'Finite GPU resource wait budget reached before query')
        index = len(self.queries)
        row = {'index': index, 'argv': argv, 'requested_original_call_timeout_seconds': 60,
               'actual_query_timeout_seconds': timeout, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'started_monotonic': time.monotonic(), 'mutex': self.owned()}
        child = None
        failure = None
        stdout = stderr = b''
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            try:
                child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
                row.update(pid=child.pid, child_created=True)
            finally:
                # A pending original wrapper signal is delivered inside this
                # owning try, after the Popen handle has become available.
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            try:
                row['stat'] = Path('/proc', str(child.pid), 'stat').read_text()
            except FileNotFoundError as error:
                self.gate.require(child.poll() is not None, 'Own query process metadata vanished while child remains live')
                row['metadata_unavailable_after_actual_child_exit'] = str(error)
            stdout, stderr = child.communicate(timeout=timeout)
        except BaseException as error:
            failure = error
            row['metadata_or_communication_error'] = type(error).__name__ + ': ' + str(error)
            # This exact Popen owns only our nvidia-smi client. Never target a
            # compute PID, GPU container, process group or another task.
            if child is not None:
                try:
                    # Blocked INT/TERM can be inherited during the atomic
                    # spawn window. Kill only this still-owned query client;
                    # SIGKILL is unblocked and the true negative wait is kept.
                    if child.poll() is None:
                        child.kill(); row['own_query_cleanup_signal'] = int(signal.SIGKILL)
                    stdout, stderr = child.communicate(timeout=5)
                except BaseException as cleanup:
                    row['own_query_cleanup_error'] = type(cleanup).__name__ + ': ' + str(cleanup)
                    stdout = getattr(cleanup, 'stdout', None) or stdout
                    stderr = getattr(cleanup, 'stderr', None) or stderr
                    child.poll()
            else:
                row['child_created'] = False
        row.update(actual_wait_returncode=None if child is None else child.returncode, finished_monotonic=time.monotonic(),
                   finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   timed_out=isinstance(failure, subprocess.TimeoutExpired))
        for label, raw in (('stdout', stdout), ('stderr', stderr)):
            path = self.output / f'{index:05d}.{label}.raw'
            with path.open('xb') as stream:
                stream.write(raw)
            row[label] = self.gate.fingerprint(path)
        if failure is not None:
            row['error'] = {'type': type(failure).__name__, 'message': str(failure)}
        self.queries.append(row)
        with (self.output / f'{index:05d}.json').open('x') as stream:
            json.dump(row, stream, indent=2, allow_nan=False); stream.write('\n')
        self.flush()
        if failure is not None:
            raise failure
        return subprocess.CompletedProcess(argv, child.returncode, self.text(stdout), self.text(stderr))

    def observe(self):
        """Single exact original guard; busy becomes waiting only in this host gate."""
        initial = len(self.queries)
        try:
            result = self.original_checks()
            idle = True
        except ValueError as error:
            if type(error) is not ValueError or str(error) != BUSY:
                raise
            result, idle = None, False
        return {'uuid': self.native.UUID, 'idle': idle, 'existing_compute_processes': [] if idle else ['see exact raw query stdout'],
                'original_guard_result': result, 'query_records': self.queries[initial:]}

    def wait(self):
        """The second native host override; real waiting counts toward original12h."""
        started = time.monotonic()
        self.current_call_deadline = started + self.budget
        call = {'index': len(self.calls), 'started_monotonic': started, 'budget_seconds': self.budget,
                'original_overall_limit_seconds': self.plan['host_total_timeout_seconds'], 'rounds': [], 'status': 'checking'}
        self.calls.append(call); self.flush()
        try:
            while True:
                mutex = self.owned(); remaining = self.overall_remaining()
                self.gate.require(time.monotonic() - started <= self.budget, 'Finite GPU resource wait budget reached')
                first = len(self.queries)
                try:
                    result = self.original_checks()
                except ValueError as error:
                    if type(error) is not ValueError or str(error) != BUSY:
                        raise
                    call['rounds'].append({'status': 'exact_original_gpu_busy', 'observed_monotonic': time.monotonic(),
                                           'queries': self.queries[first:], 'mutex': mutex})
                    self.flush()
                    remaining = min(self.budget - (time.monotonic() - started), self.overall_remaining())
                    self.gate.require(remaining > 0, 'Finite GPU resource wait budget reached')
                    time.sleep(min(self.poll, remaining))
                    continue
                self.owned(); self.overall_remaining()
                self.gate.require(time.monotonic() - started <= self.budget, 'Finite GPU resource wait budget reached')
                call['rounds'].append({'status': 'exact_original_gpu_idle', 'observed_monotonic': time.monotonic(), 'queries': self.queries[first:]})
                call['status'] = 'idle'
                return result
        except BaseException as error:
            call.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
            raise
        finally:
            self.current_call_deadline = None
            call.update(finished_monotonic=time.monotonic(), actual_wall_seconds=time.monotonic() - started)
            self.flush()
