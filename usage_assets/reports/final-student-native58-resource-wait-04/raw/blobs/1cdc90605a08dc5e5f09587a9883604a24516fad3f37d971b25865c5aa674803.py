"""Ordinary CPU controls only. Synthetic historical/resource fixtures are NOT scientific receipts."""
import argparse
import contextlib
import copy
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_crossboot_gate', HERE / 'crossboot_gate.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
spec = importlib.util.spec_from_file_location('tested_crossboot_wrapper', HERE / 'run_native58.py')
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
HISTORICAL = G.ROOT / 'outputs/research/final-student-native58-recovered-preparation-01/previous_recovered_02.py'
BASE = G.ROOT / 'outputs/research/final-student-native58-resource-wait-02'
NEW_BOOT = 'synthetic-new-boot-cpu-control'
DAEMON = {'id': 'synthetic-daemon-cpu-control', 'docker_root': '/synthetic', 'os_type': 'linux'}
CID_LIST = [str(n) * 64 for n in range(1, 6)]


def inspect_fixture(module, cid, gpu):
    return {'Id': cid, 'Image': module.IMAGE, 'Name': '/synthetic-control-' + cid[:3],
            'State': {'StartedAt': module.STARTED if cid == module.CID else 'synthetic-historical-start',
                      'Running': False, 'Restarting': False, 'Paused': False},
            'Mounts': [{'Destination': '/control', 'Source': '/synthetic/control', 'RW': False}],
            'Config': {'Cmd': ['synthetic-cpu-fixture']},
            'HostConfig': {'NetworkMode': 'none', 'IpcMode': 'private', 'PidMode': '', 'Init': True, 'Privileged': False,
                           'DeviceRequests': [{'DeviceIDs': [G.GPU]}] if gpu else [], 'ShmSize': 8589934592, 'Runtime': 'runc'}}


class GateControls(unittest.TestCase):
    def setUp(self):
        self.module = G.load(HISTORICAL, 'historical_gate_cpu_fixture')
        self.module.CID = CID_LIST[0]
        self.responses = {}
        self.calls = []
        self.stops = []
        for n, cid in enumerate(CID_LIST):
            gpu = n in (0, 2)
            info = inspect_fixture(self.module, cid, gpu)
            self.stops.append(({'container_id': cid, 'running_after_stop': False, 'before': copy.deepcopy(info), 'after': info}, cid, gpu))
            self.responses['/containers/' + cid + '/json'] = {'http_status': 404, 'route': '/containers/' + cid + '/json',
                                                           'json': {'message': 'No such container: ' + cid}}
        self.responses['/info'] = {'http_status': 200, 'route': '/info', 'json': {'ID': DAEMON['id'], 'DockerRootDir': DAEMON['docker_root'], 'OSType': 'linux'}}
        self.data = {'current_boot_id': NEW_BOOT, 'daemon': DAEMON, 'plan': {'path': str(BASE / 'host-plan.json')},
                     'mutex': {'path': 'synthetic-lock', 'device': 1, 'inode': 2},
                     **{x: {'path': 'synthetic-' + x} for x in ('preparation', 'source_review', 'cpu_prepare_review', 'resource_audit', 'unix_endpoint_observation')}}
        self.contract_fp = {'path': 'synthetic-contract'}
        self.endpoint = {'synthetic': 'socket-identity'}
        self.oldEvidence = self.module.Evidence
        self.module.Evidence = lambda: types.SimpleNamespace(records={}, finish=lambda: self.calls.append('evidence_finish'))
        self.module.original_proof = lambda evidence: ({}, {})

        def manager(evidence, old, plan):
            self.assertFalse(self.module.same_process_live(123, 456))
            return {}, [self.module.stopped(*s) for s in self.stops[:2]]

        self.module.manager_proof = manager
        self.module.historical_mappings = lambda evidence, plan: self.calls.append('historical_mappings')
        self.module.four_proof = lambda evidence, manager, plan: ({}, [self.module.stopped(*s) for s in self.stops[2:]])
        self.module.host_children_gone = lambda cids: self.calls.append(('cgroups', cids))

        def api(route):
            self.calls.append(route)
            return copy.deepcopy(self.responses[route])

        self.module.docker_get = lambda route: api(route)['json']
        self.patches = [patch.object(G, 'boot_id', return_value=NEW_BOOT),
                        patch.object(G, 'control_records', return_value=[]),
                        patch.object(G, 'failed_previous', return_value={'scope':'synthetic control only'}),
                        patch.object(G, 'verify', side_effect=lambda row: Path(row['path'])),
                        patch.object(G, 'read', side_effect=lambda row: {'paths': {'/var/run/docker.sock': self.endpoint}} if row['path'] == 'synthetic-unix_endpoint_observation' else {'current_five_original_containers': [{'container_id': x} for x in CID_LIST]}),
                        patch.object(G, 'require_owned_mutex', return_value={'path': 'synthetic-lock', 'device': 1, 'inode': 2, 'owner_pid': os.getpid(), 'actual_proc_locks_line': '1: fixture'}),
                        patch.object(G, 'endpoint_identity', return_value=self.endpoint),
                        patch.object(G, 'actor_context', return_value={'synthetic': 'same-context'}),
                        patch.object(G, 'docker_get', side_effect=api),
                        patch.object(G, 'gpu_idle', return_value={'idle': True}),
                        patch.object(G, 'load', return_value=self.module),
                        patch.object(G, 'fingerprint', side_effect=lambda path: {'path': str(path), 'sha256': G.OLD_GATE_SHA, 'bytes': 0})]
        self.started = [x.start() for x in self.patches]

    def tearDown(self):
        for x in reversed(self.patches):
            x.stop()

    def run_gate(self):
        return G.evaluate(self.data, self.contract_fp, {'dependencies': []}, {})

    def test_five_typed404_stay_separate_from_historical_facts(self):
        result = self.run_gate()
        self.assertTrue(result['ready'])
        self.assertEqual(self.module.BOOT, G.OLD_BOOT)
        self.assertEqual(len(result['current_resources']), 5)
        for item in result['current_resources']:
            self.assertEqual(item['actual_current_request']['http_status'], 404)
            self.assertNotIn('State', item['actual_current_request']['json'])
            self.assertIn('historical_started_at', item)
            self.assertEqual(item['actual_current_recheck']['http_status'], 404)
        self.assertFalse(result['historical_pid_checks'][0]['current_proc_read'])
        self.assertIn('historical_mappings', self.calls)
        self.assertIn('evidence_finish', self.calls)
        self.assertEqual(len([x for x in self.calls if isinstance(x, tuple)]), 2)

    def test_busy_waits_without_loading_historical_proofs(self):
        with patch.object(G, 'gpu_idle', return_value={'idle': False, 'existing_compute_processes': ['synthetic-other-user']}), patch.object(G, 'load') as loaded:
            result = self.run_gate()
        self.assertEqual(result['status'], 'waiting')
        loaded.assert_not_called()

    def test_same_boot_rejected(self):
        with patch.object(G, 'boot_id', return_value=G.OLD_BOOT):
            with self.assertRaisesRegex(ValueError, 'boot'):
                self.run_gate()

    def test_untyped404_rejected(self):
        self.responses['/containers/' + CID_LIST[0] + '/json']['json'] = {'message': 'permission denied'}
        with self.assertRaisesRegex(ValueError, 'neither typed404'):
            self.run_gate()

    def test_500_never_means_absent(self):
        self.responses['/containers/' + CID_LIST[0] + '/json']['http_status'] = 500
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_200_uses_original_complete_identity_validator(self):
        route = '/containers/' + CID_LIST[0] + '/json'
        self.responses[route] = {'http_status': 200, 'route': route, 'json': copy.deepcopy(self.stops[0][0]['after'])}
        result = self.run_gate()
        self.assertEqual(result['current_resources'][0]['current_status'], 'current_stopped_original_full_identity_verified')
        self.assertGreaterEqual(self.calls.count(route), 4)

    def test_200_restarted_rejected(self):
        route = '/containers/' + CID_LIST[0] + '/json'
        info = copy.deepcopy(self.stops[0][0]['after'])
        info['State']['StartedAt'] = 'synthetic-restarted'
        self.responses[route] = {'http_status': 200, 'route': route, 'json': info}
        with self.assertRaisesRegex(ValueError, 'restarted'):
            self.run_gate()

    def test_changed_daemon_at_end_rejected(self):
        original = G.docker_get
        count = 0

        def changed(route):
            nonlocal count
            row = original(route)
            if route == '/info':
                count += 1
                if count > 1:
                    row['json']['ID'] = 'synthetic-other-daemon'
            return row

        with patch.object(G, 'docker_get', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Daemon generation'):
                self.run_gate()

    def test_current_404_becomes_200_rejected(self):
        original = G.docker_get
        route0 = '/containers/' + CID_LIST[0] + '/json'
        count = 0

        def changed(route):
            nonlocal count
            row = original(route)
            if route == route0:
                count += 1
                if count > 1:
                    row['http_status'] = 200
                    row['json'] = self.stops[0][0]['after']
            return row

        with patch.object(G, 'docker_get', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Previously absent'):
                self.run_gate()

    def test_actual_liveness_cgroup_failure_not_swallowed(self):
        self.module.host_children_gone = lambda cids: G.require(False, 'synthetic live current cgroup')
        with self.assertRaisesRegex(ValueError, 'live current cgroup'):
            self.run_gate()

    def test_mutex_output_sequence_is_not_identity(self):
        a = {'path': 'x', 'device': 1, 'inode': 2, 'owner_pid': 3, 'actual_proc_locks_line': '8: x'}
        b = {**a, 'actual_proc_locks_line': '19: x'}
        self.assertEqual(G.mutex_identity(a), G.mutex_identity(b))

    def test_replaced_mutex_inode_rejected(self):
        self.data['mutex']['inode'] = 999
        with self.assertRaisesRegex(ValueError, 'mutex inode'):
            self.run_gate()


class ActualCPUControls(unittest.TestCase):
    def final_fixture(self, wrong_daemon=False):
        endpoint = {'synthetic': 'socket'}
        data = {'current_boot_id': NEW_BOOT, 'unix_endpoint_observation': {}, 'daemon': DAEMON}
        def get(route, observations):
            row = {'http_status': 200, 'route': route, 'json': {'ID': 'different' if wrong_daemon else DAEMON['id'], 'DockerRootDir': DAEMON['docker_root'], 'OSType': 'linux'}}
            observations.update(row)
            return row
        return data, endpoint, get

    def test_final_identity_after_cleanup_does_not_require_mutex_or_idle(self):
        data, endpoint, get = self.final_fixture()
        observations = {}
        with patch.object(G, 'boot_id', return_value=NEW_BOOT), patch.object(G, 'endpoint_identity', return_value=endpoint), patch.object(G, 'read', return_value={'paths': {'/var/run/docker.sock': endpoint}}), patch.object(G, 'actor_context'), patch.object(G, 'docker_get', side_effect=get), patch.object(G, 'gpu_idle') as idle, patch.object(G, 'require_owned_mutex') as mutex:
            W.final_control_identity(G, data, observations)
        idle.assert_not_called()
        mutex.assert_not_called()
        self.assertEqual(observations['daemon']['http_status'], 200)

    def test_final_wrong_daemon_rejects_and_retains_partial_observation(self):
        data, endpoint, get = self.final_fixture(wrong_daemon=True)
        observations = {}
        with patch.object(G, 'boot_id', return_value=NEW_BOOT), patch.object(G, 'endpoint_identity', return_value=endpoint), patch.object(G, 'read', return_value={'paths': {'/var/run/docker.sock': endpoint}}), patch.object(G, 'actor_context'), patch.object(G, 'docker_get', side_effect=get):
            with self.assertRaisesRegex(ValueError, 'daemon changed'):
                W.final_control_identity(G, data, observations)
        self.assertEqual(observations['daemon']['json']['ID'], 'different')
        self.assertEqual(observations['boot_id'], NEW_BOOT)

    def test_waiting_rechecks_then_returns_only_fresh_ready(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'synthetic-wait-control.json'
            row = {'scope': 'synthetic_cpu_wait_control', 'gate_calls': []}
            with patch.object(G, 'evaluate', side_effect=[{'status': 'waiting', 'ready': False}, {'status': 'recovered_previous_ready', 'ready': True}]):
                result = W.wait_recovered(G, {}, {}, {}, {}, row, path, time.monotonic() + 2, .001)
            self.assertTrue(result['ready'])
            self.assertEqual(len(row['gate_calls']), 2)
            self.assertEqual(json.loads(path.read_text()), row)

    def test_waiting_timeout_remains_distinct_from_native_failure(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'synthetic-wait-control.json'
            with patch.object(G, 'evaluate', return_value={'status': 'waiting', 'ready': False}):
                with self.assertRaises(G.Waiting):
                    W.wait_recovered(G, {}, {}, {}, {}, {'gate_calls': []}, path, time.monotonic() - 1, .001)

    def test_waiting_never_swallows_contradictory_evidence(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            with patch.object(G, 'evaluate', side_effect=ValueError('synthetic contradictory identity')):
                with self.assertRaisesRegex(ValueError, 'contradictory'):
                    W.wait_recovered(G, {}, {}, {}, {}, {'gate_calls': []}, Path(directory) / 'receipt.json', time.monotonic() + 1, .001)

    def actor_fixture(self, directory, wrong_context=False, wrong_daemon=False):
        file = Path(directory) / 'context.stdout.raw'
        file.write_text('default\n')
        actor = {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid(), 'egid': os.getegid(), 'groups': os.getgroups()}
        cert = {'actor': actor, 'commands': [{'stdout': {**G.fingerprint(file), 'path': str(file.relative_to(G.ROOT))}}]}
        context = [{'Name': 'default', 'Endpoints': {'docker': {'Host': 'ssh://different' if wrong_context else 'unix:///var/run/docker.sock'}}}]
        info = {'ID': 'different' if wrong_daemon else DAEMON['id'], 'DockerRootDir': DAEMON['docker_root'], 'OSType': 'linux'}
        results = [subprocess.CompletedProcess([], 0, b'default\n', b''),
                   subprocess.CompletedProcess([], 0, json.dumps(context).encode(), b''),
                   subprocess.CompletedProcess([], 0, json.dumps(info).encode(), b'')]
        return cert, results

    def test_actor_context_matches_cli_and_direct_daemon(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            cert, results = self.actor_fixture(directory)
            with patch.object(G, 'read', return_value=cert), patch.object(G.subprocess, 'run', side_effect=results), patch.dict(os.environ, {}, clear=True):
                result = G.actor_context({'unix_endpoint_observation': {}, 'daemon': DAEMON})
            self.assertEqual(result['context_name'], 'default')
            self.assertEqual(len(result['actual_readonly_commands']), 3)

    def test_actor_different_context_endpoint_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            cert, results = self.actor_fixture(directory, wrong_context=True)
            with patch.object(G, 'read', return_value=cert), patch.object(G.subprocess, 'run', side_effect=results), patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'different daemon'):
                    G.actor_context({'unix_endpoint_observation': {}, 'daemon': DAEMON})

    def test_actor_different_cli_daemon_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            cert, results = self.actor_fixture(directory, wrong_daemon=True)
            with patch.object(G, 'read', return_value=cert), patch.object(G.subprocess, 'run', side_effect=results), patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'daemon identities'):
                    G.actor_context({'unix_endpoint_observation': {}, 'daemon': DAEMON})

    def test_actor_environment_context_redirect_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            cert, results = self.actor_fixture(directory)
            with patch.object(G, 'read', return_value=cert), patch.object(G.subprocess, 'run', side_effect=results), patch.dict(os.environ, {'DOCKER_CONTEXT': 'unexpected'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'context/environment'):
                    G.actor_context({'unix_endpoint_observation': {}, 'daemon': DAEMON})

    def test_real_original_scene_and_direction_command_imports(self):
        before_path = sys.path[:]
        old = {k: sys.modules.pop(k, None) for k in ('common', 'phase_cpu')}
        try:
            native = W.load_native(G, BASE)
            self.assertEqual(G.fingerprint(native.__file__)['sha256'], G.NATIVE_SHA)
            scene = native.native_command(BASE, {'phase': 'scenes'})
            direction = native.native_command(BASE, {'phase': 'directions'})
            self.assertIn('/control/scene17.py', scene)
            self.assertIn('--seconds', scene)
            self.assertEqual(scene[scene.index('--seconds') + 1], '10.0')
            self.assertIn('/control/commands_executor.py', direction)
            self.assertEqual(Path(sys.modules['phase_cpu'].__file__), BASE / 'control/phase_cpu.py')
        finally:
            sys.path[:] = before_path
            for k, value in old.items():
                sys.modules.pop(k, None)
                if value is not None:
                    sys.modules[k] = value

    def test_actual_mutex_ownership_and_unlocked_refusal(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'cpu-only-mutex'
            path.touch()
            with patch.object(G, 'MUTEX', path):
                with self.assertRaisesRegex(ValueError, 'must hold'):
                    G.require_owned_mutex()
                with path.open('r+') as stream:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    row = G.require_owned_mutex()
                    self.assertEqual(row['owner_pid'], os.getpid())
                    self.assertEqual(row['inode'], path.stat().st_ino)
                    fcntl.flock(stream, fcntl.LOCK_UN)
                with self.assertRaises(ValueError):
                    G.require_owned_mutex()

    def test_real_wrapper_wrong_contract_sha_refuses_before_output(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            source = Path(directory) / 'fake-contract.json'
            source.write_text('{}')
            target = Path(directory) / 'must-not-exist'
            done = subprocess.run(['/usr/bin/python3', '-B', str(HERE / 'run_native58.py'), 'run',
                                   '--contract', str(source), '--contract-sha256', '0' * 64,
                                   '--output', str(target), '--root-authorized-start'], capture_output=True)
            self.assertEqual(done.returncode, 1)
            self.assertFalse(target.exists())
            self.assertIn(b'contract SHA differs', done.stderr)


from test_gpu_resource_wait import ResourceControls, FailedPreviousControls

if __name__ == '__main__':
    unittest.main(verbosity=2)
