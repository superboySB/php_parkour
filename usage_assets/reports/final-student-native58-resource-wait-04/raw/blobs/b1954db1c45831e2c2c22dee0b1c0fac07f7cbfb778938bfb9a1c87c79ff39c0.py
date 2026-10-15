"""Ordinary CPU nvidia-smi stand-ins; never query or signal a real GPU workload."""
import importlib.util
import copy
import http.client
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
import fcntl

HERE = Path(__file__).resolve().parent
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value); return value
G = load(HERE / 'crossboot_gate.py', 'resource_cpu_gate')
W = load(HERE / 'run_native58.py', 'resource_cpu_wrapper')
R = load(HERE / 'gpu_resource_wait.py', 'resource_cpu_wait')
ORIGINAL_DOCKER_GET = G.docker_get


class ResourceControls(unittest.TestCase):
    def setUp(self):
        artifacts = os.environ.get('NATIVE58_CPU_CONTROL_ARTIFACTS')
        if artifacts:
            self.root = Path(artifacts) / self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
            (self.root / 'scope.json').write_text(json.dumps({'scope': 'ordinary_CPU_stand_in_queries_not_actual_GPU_or_native58', 'test': self._testMethodName}) + '\n')
        else:
            self.temp = tempfile.TemporaryDirectory(dir=HERE); self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
        self.lock = self.root / 'cpu-only-mutex'; self.lock.touch()
        self.stream = self.lock.open('r+'); fcntl.flock(self.stream, fcntl.LOCK_EX); self.addCleanup(self.stream.close)
        self.before_path = sys.path[:]; old = {k: sys.modules.pop(k, None) for k in ('common', 'phase_cpu')}
        self.native = W.load_native(G, G.ROOT / 'outputs/research/final-student-native58-resource-wait-02')
        def restore():
            sys.path[:] = self.before_path
            for key, value in old.items():
                sys.modules.pop(key, None)
                if value is not None: sys.modules[key] = value
        self.addCleanup(restore)
        self.cfg = self.root / 'synthetic-query-config.json'
        self.cfg.write_text(json.dumps({'mode': 'idle'}))
        binary = self.root / 'nvidia-smi'
        binary.write_text('''#!/usr/bin/python3
import json,os,sys,time
from pathlib import Path
p=Path(os.environ['SYNTHETIC_CPU_NVIDIA_CONFIG']);c=json.loads(p.read_text())
if c['mode']=='timeout':
 print('synthetic query started',flush=True);time.sleep(10)
if c['mode']=='failure':
 print('synthetic CPU query failure',file=sys.stderr);raise SystemExit(7)
if '--query-gpu=uuid' in sys.argv:
 print('synthetic-wrong-uuid' if c['mode']=='uuid' else 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25')
else:
 count=c.get('compute_calls',0);c['compute_calls']=count+1;p.write_text(json.dumps(c))
 if c['mode']=='busy' or (c['mode']=='busy_once' and count==0):
  print('GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25, 123456789')
'''); binary.chmod(0o755)
        env = patch.dict(os.environ, {'PATH': str(self.root) + ':' + os.environ['PATH'], 'SYNTHETIC_CPU_NVIDIA_CONFIG': str(self.cfg)})
        env.start(); self.addCleanup(env.stop)
        patched = patch.object(G, 'MUTEX', self.lock); patched.start(); self.addCleanup(patched.stop)
        s = self.lock.stat()
        data = {'current_boot_id': G.boot_id(), 'mutex': {'path': str(self.lock), 'device': s.st_dev, 'inode': s.st_ino},
                'resource_wait_seconds': 2, 'resource_poll_seconds': .01}
        data['resource_poll_seconds'] = .1
        self.r = R.ResourceWait(self.native, G, data, {'host_total_timeout_seconds': 43200}, self.root / 'queries', lambda: None)
        self.r.execute_started = time.monotonic()

    def mode(self, mode): self.cfg.write_text(json.dumps({'mode': mode}))

    def test_busy_then_idle_uses_fresh_original_guards_and_actual_cpu_queries(self):
        self.mode('busy_once'); result = self.r.wait()
        self.assertEqual(result['uuid'], self.native.UUID)
        self.assertEqual([x['status'] for x in self.r.calls[0]['rounds']], ['exact_original_gpu_busy', 'exact_original_gpu_idle'])
        self.assertEqual(len(self.r.queries), 4)
        self.assertTrue(all(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode'] == 0 for x in self.r.queries))
        self.assertTrue(all(Path(x['stdout']['path']).exists() for x in self.r.queries))

    def test_query_failure7_is_immediate_not_retried_as_busy(self):
        self.mode('failure')
        with self.assertRaisesRegex(ValueError, 'Command failed 7'): self.r.wait()
        self.assertEqual(len(self.r.queries), 1); self.assertEqual(self.r.queries[0]['actual_wait_returncode'], 7)

    def test_wrong_uuid_is_immediate_not_retried(self):
        self.mode('uuid')
        with self.assertRaisesRegex(ValueError, 'UUID'): self.r.wait()
        self.assertEqual(len(self.r.queries), 1)

    def test_per_call_budget_stops_continuous_busy(self):
        self.mode('busy'); self.r.budget = .2
        with self.assertRaises((ValueError, R.subprocess.TimeoutExpired)): self.r.wait()
        self.assertEqual(self.r.calls[0]['status'], 'failed')
        self.assertLess(self.r.calls[0]['actual_wall_seconds'], 2)

    def test_original_overall_wall_guard_fails_before_query(self):
        self.r.execute_started = time.monotonic() - 43201
        with self.assertRaisesRegex(ValueError, 'whole58 host wall'): self.r.wait()
        self.assertEqual(self.r.queries, [])

    def test_query_timeout_saves_raw_negative_wait_and_only_own_client_cleanup(self):
        self.mode('timeout'); self.r.budget = .15
        with self.assertRaises(R.subprocess.TimeoutExpired): self.r.wait()
        query = self.r.queries[0]
        self.assertTrue(query['timed_out']); self.assertLess(query['actual_wait_returncode'], 0)
        self.assertEqual(query['own_query_cleanup_signal'], int(signal.SIGKILL))
        self.assertIn(b'synthetic query started', Path(query['stdout']['path']).read_bytes())
        self.assertFalse(Path('/proc', str(query['pid'])).exists())

    def test_spawn_failure_has_null_real_wait_and_preserved_query_receipt(self):
        with patch.object(R.subprocess, 'Popen', side_effect=FileNotFoundError('synthetic missing client')):
            with self.assertRaises(FileNotFoundError): self.r.wait()
        query = self.r.queries[0]
        self.assertIsNone(query['actual_wait_returncode']); self.assertFalse(query['child_created'])

    def test_actual_self_sigterm_unwinds_wrapper_handler_and_reaps_own_cpu_query(self):
        self.mode('timeout')
        receipt = self.root / 'synthetic-signal-receipt.json'
        row = {'signals': [], 'scope': 'ordinary_CPU_self_signal_control_not_native_or_GPU'}
        handlers = W.install_signal_handlers(row, receipt)
        timer = threading.Timer(.1, lambda: os.kill(os.getpid(), signal.SIGTERM))
        try:
            timer.start()
            with self.assertRaises(KeyboardInterrupt): self.r.wait()
        finally:
            timer.cancel(); timer.join()
            for number, handler in handlers.items(): signal.signal(number, handler)
        query = self.r.queries[0]
        self.assertEqual(row['signals'][0]['signal'], int(signal.SIGTERM))
        self.assertEqual(query['actual_wait_returncode'], -int(signal.SIGKILL))
        self.assertEqual(query['error']['type'], 'KeyboardInterrupt')
        self.assertFalse(Path('/proc', str(query['pid'])).exists())

    def test_expired_mutex_or_replaced_inode_rejects_before_query(self):
        fcntl.flock(self.stream, fcntl.LOCK_UN)
        with self.assertRaisesRegex(ValueError, 'must hold'): self.r.wait()
        self.assertEqual(self.r.queries, [])

    def test_does_not_modify_original_time_call_or_execute_bindings(self):
        self.assertIs(self.native.time, time)
        self.assertIs(self.native.call.__globals__['subprocess'], R.subprocess)
        self.assertEqual(self.native.execute.__name__, 'execute')


class FailedPreviousControls(unittest.TestCase):
    """Actual archived JSON, synthetic offline current API/session observations only."""
    def setUp(self):
        self.fp = G.fingerprint(G.ROOT / 'outputs/research/reproduction-20261015/native58-failed41-independent-audit-02/review.json')
        self.review = G.read(self.fp)
        self.assertEqual(self.fp['sha256'], G.FAILED_REVIEW_SHA)
        self.recorded = {item['container_id']: G.read(item['execution']['stdout'])[0]
                         for item in self.review['stopped_gpu_containers']}
        self.data = {'failed41_review': self.fp, 'current_boot_id': G.boot_id()}
        self.api_calls = []
        def api(route):
            self.api_calls.append(route)
            cid = route.split('/')[2]
            return {'http_status': 404, 'route': route, 'json': {'message': 'No such container: ' + cid},
                    'scope': 'synthetic_offline_current_API_not_actual_resource_observation'}
        for item in (patch.object(G, 'verify', side_effect=lambda row: Path(row['path'])),
                     patch.object(G, 'current_session_members', return_value=[]),
                     patch.object(G, 'docker_get', side_effect=api)):
            item.start(); self.addCleanup(item.stop)

    def test_offline_typed404_is_separate_from_actual_archived_stopped143(self):
        result = G.failed_previous(self.data)
        self.assertFalse(result['is_complete58_admission'])
        self.assertEqual(len(self.api_calls), 6)
        self.assertTrue(all(item['current_status'] == 'current_absent_typed_404' for item in result['containers']))
        self.assertTrue(all(item['actual_current_request']['http_status'] == 404 for item in result['containers']))

    def test_same_boot_live_owned_session_is_rejected_without_API_calls(self):
        G.current_session_members.return_value = [{'pid': 123456789, 'scope': 'synthetic CPU fixture'}]
        with self.assertRaisesRegex(ValueError, 'owned session still has members'): G.failed_previous(self.data)
        self.assertEqual(self.api_calls, [])

    def test_same_exactCID_changed_startedAt200_is_rejected(self):
        def changed(route):
            info = copy.deepcopy(self.recorded[route.split('/')[2]])
            info['State']['StartedAt'] = 'synthetic-changed-birth'
            return {'http_status': 200, 'route': route, 'json': info}
        G.docker_get.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'full container identity'): G.failed_previous(self.data)

    def test_typed404_to200_recheck_is_rejected(self):
        def changed(route):
            self.api_calls.append(route); cid = route.split('/')[2]
            if len(self.api_calls) > 3:
                return {'http_status': 200, 'route': route, 'json': copy.deepcopy(self.recorded[cid])}
            return {'http_status': 404, 'route': route, 'json': {'message': 'No such container: ' + cid}}
        G.docker_get.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'absent CID changed during recheck'): G.failed_previous(self.data)

    def set_current200(self, change=None):
        def api(route):
            self.api_calls.append(route)
            info = copy.deepcopy(self.recorded[route.split('/')[2]])
            if len(self.api_calls) > 3:
                info['Mounts'].reverse()
                if change is not None: change(info)
            return {'http_status': 200, 'route': route, 'json': info,
                    'scope': 'synthetic_offline_current_API_not_actual_resource_observation'}
        G.docker_get.side_effect = api

    def test_mount_order_alone_preserves_full_inspect_and_raw_observations(self):
        self.set_current200()
        result = G.failed_previous(self.data)
        for item in result['containers']:
            self.assertEqual(item['current_status'], 'current_stopped143_full_identity_verified')
            before, after = item['actual_current_request']['json'], item['actual_current_recheck']['json']
            self.assertTrue(G.inspect_equal(before, after))
            self.assertEqual(after['Mounts'], list(reversed(before['Mounts'])))

    def test_mount_row_content_change_is_rejected_despite_order_normalization(self):
        self.set_current200(lambda info: info['Mounts'][0].update(RW=not info['Mounts'][0]['RW']))
        with self.assertRaisesRegex(ValueError, 'inspect changed during recheck'): G.failed_previous(self.data)

    def test_state_change_is_rejected_despite_order_normalization(self):
        self.set_current200(lambda info: info['State'].update(Running=True))
        with self.assertRaisesRegex(ValueError, 'inspect changed during recheck'): G.failed_previous(self.data)

    def test_diagnostics_keep_raw_bytes_before_later_validation_failure(self):
        with tempfile.TemporaryDirectory(dir=G.ROOT / 'outputs/research/reproduction-20261015') as temporary:
            old_directory, old_records = G.DIAGNOSTIC_DIRECTORY, G.DIAGNOSTIC_RECORDS
            try:
                records = G.configure_diagnostics(Path(temporary) / 'observations', G.ROOT / 'outputs/research/final-student-native58-resource-wait-02')
                raw = b'{synthetic invalid JSON ordinary CPU response bytes\n'
                class Response:
                    status = 200
                    def read(self): return raw
                    def getheaders(self): return [('Content-Type', 'application/json')]
                class Connection:
                    def __init__(self, *args, **kwargs): pass
                    def request(self, method, route): pass
                    def getresponse(self): return Response()
                    def close(self): pass
                with patch.object(G, 'UnixDocker', Connection):
                    with self.assertRaises(ValueError): ORIGINAL_DOCKER_GET('/info')
                self.assertEqual(len(records), 2)
                record = G.read(records[0]); self.assertEqual(Path(record['body']['path']).read_bytes(), raw)
            finally:
                G.DIAGNOSTIC_DIRECTORY, G.DIAGNOSTIC_RECORDS = old_directory, old_records

    def test_incomplete_http_body_keeps_actual_partial_bytes_status_and_headers(self):
        with tempfile.TemporaryDirectory(dir=G.ROOT / 'outputs/research/reproduction-20261015') as temporary:
            old_directory, old_records = G.DIAGNOSTIC_DIRECTORY, G.DIAGNOSTIC_RECORDS
            try:
                records = G.configure_diagnostics(Path(temporary) / 'observations', G.ROOT / 'outputs/research/final-student-native58-resource-wait-02')
                raw = b'actual ordinary CPU incomplete response prefix'
                class Response:
                    status = 200
                    def read(self): raise http.client.IncompleteRead(raw, 100)
                    def getheaders(self): return [('Content-Length', str(len(raw) + 100))]
                class Connection:
                    def __init__(self, *args, **kwargs): pass
                    def request(self, method, route): pass
                    def getresponse(self): return Response()
                    def close(self): pass
                with patch.object(G, 'UnixDocker', Connection):
                    with self.assertRaises(http.client.IncompleteRead): ORIGINAL_DOCKER_GET('/info')
                record = G.read(records[0]); observation = record['observation']
                self.assertEqual(observation['http_status'], 200)
                self.assertEqual(observation['headers'], [['Content-Length', str(len(raw) + 100)]])
                self.assertTrue(observation['response_body_incomplete'])
                self.assertEqual(Path(record['body_partial']['path']).read_bytes(), raw)
                self.assertNotIn('body_sha256', observation)
            finally:
                G.DIAGNOSTIC_DIRECTORY, G.DIAGNOSTIC_RECORDS = old_directory, old_records


if __name__ == '__main__': unittest.main(verbosity=2)
