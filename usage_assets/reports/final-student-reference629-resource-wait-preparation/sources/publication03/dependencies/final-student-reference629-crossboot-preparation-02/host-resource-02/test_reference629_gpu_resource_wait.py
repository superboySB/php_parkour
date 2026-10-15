#!/usr/bin/env python3
"""Ordinary CPU protocol fixtures only; no nvidia/Docker/native execution."""
import ast
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
from types import ModuleType
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
WORKSPACE = Path('/home/dzp/projects/php_parkour')
CANDIDATE = WORKSPACE/'outputs/research/final-student-reference629-crossboot-preparation-02'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'


class ResourceProtocol(unittest.TestCase):
    def setUp(self):
        evidence_root = os.environ.get('REFERENCE629_CPU_PROTOCOL_EVIDENCE')
        self.tmp = None if evidence_root else tempfile.TemporaryDirectory()
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=evidence_root)) if evidence_root else Path(self.tmp.name)
        (self.root/'fixture-scope.json').write_text(json.dumps({'scope':'Synthetic ordinary CPU protocol only. Actual child argv are Python; no nvidia/Docker/native/scientific run.','test':self._testMethodName})+'\n')
        self.source = self.root/'gpu_resource_wait.py'
        self.source.write_bytes((CANDIDATE/'reference629_gpu_resource_wait.py').read_bytes())
        self.m = ModuleType('cpu_fixture_resource_helper')
        self.m.__file__ = str(self.source)
        exec(compile(self.source.read_bytes(), str(self.source), 'exec'), self.m.__dict__)
        self.lock_path = self.root/'gpu.lock'
        self.lock = self.lock_path.open('a+')
        fcntl.flock(self.lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.expected = self.m.fp(self.source)
        self.pending = []
        self.actual_query = self.m.query
        self.executions = []

    def tearDown(self):
        self.lock.close()
        if self.tmp is not None:
            self.tmp.cleanup()

    def run_wait(self, **kwargs):
        return self.m.wait_for_idle(self.lock.fileno(), self.lock_path, GPU, self.root/'result',
                                    self.pending, self.expected, wait_seconds=kwargs.pop('wait_seconds', 2),
                                    poll_seconds=kwargs.pop('poll_seconds', .01), **kwargs)

    def dispatcher(self, computes=None, delay=0, failure=False, after=None):
        values = iter(computes or [''])
        last = ['']
        def dispatch(argv, directory, label, pending, deadline, proof):
            if label == 'gpu-identity':
                value = GPU+'\n'
            else:
                last[0] = next(values, last[0]); value = last[0]
            code = 'import sys,time;time.sleep(float(sys.argv[1]));sys.stdout.write(sys.argv[2]);sys.exit(int(sys.argv[3]))'
            actual = [sys.executable, '-B', '-c', code, str(delay), value, '7' if failure else '0']
            self.executions.append(actual)
            result = self.actual_query(actual, directory, label, pending, deadline, proof)
            if after:
                after(label)
            return result
        return dispatch

    def test_busy_then_idle_preserves_actual_raw_wait_and_lock(self):
        busy = GPU+', 12345\n'
        with patch.object(self.m, 'query', side_effect=self.dispatcher([busy, ''])):
            receipt = self.run_wait()
        self.assertEqual(receipt['status'], 'ready')
        self.assertEqual([r['status'] for r in receipt['rounds']], ['busy', 'idle'])
        self.assertGreaterEqual(receipt['elapsed_real_seconds'], .01)
        self.assertEqual(receipt['mutex_initial']['inode'], receipt['mutex_final']['inode'])
        for r in receipt['rounds']:
            for key in ('identity_query', 'compute_query'):
                q=r[key]
                self.assertEqual(q['argv'][0],sys.executable)
                self.assertEqual(q['actual_wait_returncode'],0)
                self.assertEqual(q['remaining_owned_query_session_members'],[])
                self.assertEqual(q['signals_to_owned_query'],[])
        self.assertEqual((self.root/'result/round-00000/gpu-compute.stdout.raw').read_text(),busy)

    def test_busy_budget_is_bounded_and_no_native_started(self):
        with patch.object(self.m, 'query', side_effect=self.dispatcher([GPU+', 12345\n'])):
            with self.assertRaisesRegex(ValueError, 'budget|timed out'):
                self.run_wait(wait_seconds=.20)
        r=json.loads((self.root/'result/receipt.json').read_text())
        self.assertEqual(r['status'],'failed')
        self.assertLess(r['elapsed_real_seconds'],2)
        self.assertFalse(r['native_started']);self.assertFalse(r['gpu_started'])
        self.assertTrue(all(q['argv'][0]==sys.executable for q in self._query_receipts()))

    def _query_receipts(self):
        return [json.loads(p.read_text()) for p in (self.root/'result').rglob('*.execution.json')]

    def test_query_failure_is_not_retried_or_parsed_as_busy(self):
        with patch.object(self.m,'query',side_effect=self.dispatcher(failure=True)):
            with self.assertRaisesRegex(ValueError,'query failed'):
                self.run_wait()
        self.assertEqual(len(self.executions),1)
        self.assertEqual(self._query_receipts()[0]['actual_wait_returncode'],7)
        self.assertEqual(json.loads((self.root/'result/receipt.json').read_text())['status'],'failed')

    def test_query_timeout_signals_only_exact_owned_pidfd_then_reaps(self):
        self.m.QUERY_TIMEOUT_SECONDS=.08
        with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)):
            with self.assertRaisesRegex(ValueError,'timed out'):
                self.run_wait()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(q['signals_to_owned_query'],[{'signal':signal.SIGTERM,'pid':q['child_identity']['pid'],
                          'start_time_clock_ticks':q['child_identity']['start_time_clock_ticks'],'pidfd':True,'ownership_basis':'actual_pidfd'}])

    def test_pending_signal_reaps_own_query_before_return(self):
        timer=threading.Timer(.08, lambda:self.pending.append({'signal':signal.SIGTERM,'unix':time.time()}))
        timer.start()
        try:
            with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)):
                with self.assertRaisesRegex(ValueError,'cancelled'):
                    self.run_wait()
        finally:
            timer.cancel();timer.join()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(len(json.loads((self.root/'result/receipt.json').read_text())['pending_signals']),1)

    def test_diagnostic_write_failure_after_spawn_still_reaps(self):
        original=self.m.save
        failed=[False]
        def save(path,value):
            if path.name.endswith('.execution.json') and not failed[0]:
                failed[0]=True;raise OSError('CPU fixture one-time diagnostic failure')
            return original(path,value)
        with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)), patch.object(self.m,'save',side_effect=save):
            with self.assertRaisesRegex(OSError,'diagnostic failure'):
                self.run_wait()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(q['status'],'failed')

    def test_pidfd_open_failure_uses_only_unreaped_Popen_and_bounded_actual_wait(self):
        started=time.monotonic()
        with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)), patch.object(self.m.os,'pidfd_open',side_effect=OSError('CPU injected pidfd_open failure')):
            with self.assertRaisesRegex(OSError,'pidfd_open failure'):
                self.run_wait()
        self.assertLess(time.monotonic()-started,2)
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(q['signals_to_owned_query'][0]['pid'],q['actual_Popen_child_pid'])
        self.assertEqual(q['signals_to_owned_query'][0]['ownership_basis'],'owned_unreaped_direct_Popen')
        self.assertFalse(q['signals_to_owned_query'][0]['pidfd'])

    def test_child_metadata_failure_still_cleans_exact_actual_pidfd(self):
        original=self.m.birth
        def birth(pid):
            if pid!=os.getpid():raise OSError('CPU injected child metadata failure')
            return original(pid)
        started=time.monotonic()
        with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)), patch.object(self.m,'birth',side_effect=birth):
            with self.assertRaisesRegex(OSError,'metadata failure'):
                self.run_wait()
        self.assertLess(time.monotonic()-started,2)
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertTrue(any(r['phase']=='session-check' for r in q['errors']))
        remaining=self.m.empty_query_session(q['actual_Popen_child_pid'])
        (self.root/'metadata-failure-postcheck.json').write_text(json.dumps({'scope':'Actual readonly postcheck after synthetic metadata fault is removed.','owned_query_pid':q['actual_Popen_child_pid'],'remaining_owned_query_session_members':remaining})+'\n')
        self.assertEqual(remaining,[])
        self.assertEqual(q['signals_to_owned_query'][0]['ownership_basis'],'actual_pidfd')
        self.assertIsNone(q['signals_to_owned_query'][0]['start_time_clock_ticks'])

    def test_pidfd_signal_error_is_retained_and_only_direct_Popen_is_signalled(self):
        self.m.QUERY_TIMEOUT_SECONDS=.08
        with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)), patch.object(self.m.signal,'pidfd_send_signal',side_effect=OSError('CPU injected pidfd signal failure')):
            with self.assertRaisesRegex(ValueError,'timed out'):
                self.run_wait()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(q['signals_to_owned_query'][0]['ownership_basis'],'owned_unreaped_direct_Popen_after_pidfd_error')
        self.assertTrue(any(r['phase']=='pidfd-signal' for r in q['errors']))

    def test_own_query_ignoring_term_is_killed_via_same_pidfd_and_reaped(self):
        self.m.QUERY_TIMEOUT_SECONDS=.3
        def dispatch(argv,directory,label,pending,deadline,proof):
            actual=[sys.executable,'-B','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("CPU fixture ready",flush=True);time.sleep(30)']
            self.executions.append(actual)
            return self.actual_query(actual,directory,label,pending,deadline,proof)
        started=time.monotonic()
        with patch.object(self.m,'query',side_effect=dispatch):
            with self.assertRaisesRegex(ValueError,'timed out'):
                self.run_wait(wait_seconds=1)
        self.assertLess(time.monotonic()-started,7.5)
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGKILL)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual([r['signal'] for r in q['signals_to_owned_query']],[signal.SIGTERM,signal.SIGKILL])
        self.assertTrue(all(r['pidfd'] and r['pid']==q['child_identity']['pid'] for r in q['signals_to_owned_query']))

    def test_completion_observed_past_query_deadline_retains_real_wait0_but_fails(self):
        self.m.QUERY_TIMEOUT_SECONDS=.05
        original_Popen=self.m.subprocess.Popen
        class DelayedFirstPoll:
            def __init__(self,*args,**kwargs):
                self.actual=original_Popen(*args,**kwargs);self.delayed=False
            def __getattr__(self,name):return getattr(self.actual,name)
            def poll(self):
                if not self.delayed:
                    self.delayed=True;time.sleep(.10)
                return self.actual.poll()
        with patch.object(self.m,'query',side_effect=self.dispatcher()), patch.object(self.m.subprocess,'Popen',DelayedFirstPoll):
            with self.assertRaisesRegex(ValueError,'timed out before actual completion'):
                self.run_wait()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],0)
        self.assertEqual(q['status'],'failed')
        self.assertEqual(q['signals_to_owned_query'],[])
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        self.assertEqual(len(self.executions),1)

    def test_unheld_mutex_refuses_before_any_query_or_output(self):
        fcntl.flock(self.lock,fcntl.LOCK_UN)
        with patch.object(self.m,'query') as query:
            with self.assertRaisesRegex(ValueError,'exclusive kernel'):
                self.run_wait()
        query.assert_not_called();self.assertFalse((self.root/'result').exists())

    def test_replaced_mutex_refuses_before_any_query(self):
        self.lock_path.rename(self.root/'old.lock');self.lock_path.touch()
        with patch.object(self.m,'query') as query:
            with self.assertRaisesRegex(ValueError,'canonical mutex inode'):
                self.run_wait()
        query.assert_not_called()

    def test_lost_mutex_midquery_reaps_and_retains_primary_plus_final_failure(self):
        timer=threading.Timer(.08,lambda:fcntl.flock(self.lock,fcntl.LOCK_UN))
        timer.start()
        try:
            with patch.object(self.m,'query',side_effect=self.dispatcher(delay=30)):
                with self.assertRaisesRegex(ValueError,'exclusive kernel'):
                    self.run_wait()
        finally:
            timer.cancel();timer.join()
        q=self._query_receipts()[0]
        self.assertEqual(q['actual_wait_returncode'],-signal.SIGTERM)
        self.assertEqual(q['remaining_owned_query_session_members'],[])
        r=json.loads((self.root/'result/receipt.json').read_text())
        self.assertIn('exclusive kernel',r['error']['message'])
        self.assertEqual(r['final_errors'][0]['phase'],'mutex_final')

    def test_source_change_after_actual_query_never_returns_ready(self):
        def mutate(label):
            if label=='gpu-compute':self.source.write_bytes(self.source.read_bytes()+b'\n# synthetic mutation\n')
        with patch.object(self.m,'query',side_effect=self.dispatcher(after=mutate)):
            with self.assertRaisesRegex(ValueError,'Final host resource'):
                self.run_wait()
        r=json.loads((self.root/'result/receipt.json').read_text())
        self.assertEqual(r['status'],'failed');self.assertNotEqual(r['source_after'],self.expected)

    def test_invalid_budgets_refuse_without_query(self):
        for value in (True,False,0,-1,3600.01,float('nan'),float('inf')):
            with patch.object(self.m,'query') as query:
                with self.assertRaises(ValueError):self.run_wait(wait_seconds=value)
            query.assert_not_called()
        self.assertFalse((self.root/'result').exists())

    def test_malformed_or_duplicate_compute_output_rejected(self):
        for raw in ('garbage',GPU+', 0',GPU+', notpid',GPU+', 5\n'+GPU+', 5\n'):
            with self.assertRaises(ValueError):self.m.parse_compute(raw,GPU)
        self.assertEqual(self.m.parse_compute('GPU-00000000-0000-0000-0000-000000000000, 9\n',GPU),[])

    def test_runner_science_and_timeouts_recover_original_exact_bytes(self):
        current=(CANDIDATE/'native_runner.py').read_text()
        original=(CANDIDATE/'host-resource-02/native_runner-before.py').read_text()
        a=current.index('        # Host-only resource admission under')
        b=current.index('        mounts = ',a)
        x=original.index("        devices = capture(['nvidia-smi'")
        y=original.index('        mounts = ',x)
        restored=(current[:a]+original[x:y]+current[b:]).replace('from types import ModuleType\n','')
        self.assertEqual(restored,original)
        old=ast.parse(original);new=ast.parse(current)
        for node in old.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name!='run_kind':
                other=next(n for n in new.body if isinstance(n,type(node)) and n.name==node.name)
                self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(other,include_attributes=False))
        self.assertIn('wait_seconds=1800.0, poll_seconds=5.0',current)
        self.assertLess(current.index('helper.wait_for_idle('),current.index("argv = ['docker', 'create'"))


if __name__=='__main__':
    unittest.main(verbosity=2)
