"""CPU-only synthetic read-only guard cases; no TB or tunnel starts."""
import copy
import json
import os
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tb_adoption_observe_v3 as observer


class Guards(unittest.TestCase):
    def mapping_fixture(self):
        init = {'pid': 1, 'start_time_clock_ticks': 101, 'pid_namespace': 'pid:[synthetic]', 'status_raw': 'synthetic'}
        owner = {'pid': 22, 'start_time_clock_ticks': 202, 'pid_namespace': init['pid_namespace'], 'stable_birth': True,
                 'argv': ['/opt/php/bin/train-python', '-m', 'tensorboard.main', '--logdir', '/outputs/official-full', '--host', '127.0.0.1', '--port', '6006', '--load_fast', 'false'],
                 'socket_inodes': ['987'], 'state': 'S'}
        probe = {'schema_version': 1, 'effective_uid': 0, 'init': init,
                 'snapshot': {'port': 6006, 'listeners': [{'inode': '987'}], 'owners': [owner], 'unowned_inodes': []}}
        info = {'Id': 'a' * 64, 'State': {'Pid': 1001, 'StartedAt': 'synthetic-container-birth'}}
        births = {1001: {'pid': 1001, 'start_time_clock_ticks': 101, 'nspid': [1001, 1], 'nstgid': [1001, 1], 'stable_birth': True},
                  2002: {'pid': 2002, 'start_time_clock_ticks': 202, 'nspid': [2002, 22], 'nstgid': [2002, 22], 'stable_birth': True}}
        return probe, info, {1001, 2002}, births

    def test_v2_same_birth_namespace_join_maps_container_owner_to_host_pid(self):
        probe, info, pids, births = self.mapping_fixture()
        owner = observer.map_owner(probe, info, pids, pids, births)
        self.assertEqual(owner['pid'], 2002)
        self.assertEqual(owner['container_pid'], 22)
        self.assertEqual(owner['mapping']['host_init']['pid'], 1001)
        args = SimpleNamespace(expected_pid=2002, expected_start_ticks=202, container_init_pid=1001)
        snapshot = {**probe['snapshot'], 'owners': [owner], 'container': {'id': 'a' * 64, 'host_init_pid': 1001}, 'container_init_identity': probe['init']}
        self.assertEqual(observer.owner_guard(snapshot, args)['pid'], 2002)

    def test_v2_rejects_reused_birth_missing_top_and_wrong_namespace(self):
        for mode in ('birth', 'init_birth', 'top', 'namespace', 'unowned'):
            probe, info, pids, births = self.mapping_fixture()
            after = pids.copy()
            if mode == 'birth': births[2002]['start_time_clock_ticks'] += 1
            if mode == 'init_birth': births[1001]['start_time_clock_ticks'] += 1
            if mode == 'top': after.remove(2002)
            if mode == 'namespace': probe['snapshot']['owners'][0]['pid_namespace'] = 'pid:[other]'
            if mode == 'unowned': probe['snapshot']['unowned_inodes'] = ['888']
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                observer.map_owner(probe, info, pids, after, births)

    def test_v2_rejects_ambiguous_host_mapping(self):
        probe, info, pids, births = self.mapping_fixture()
        births[3003] = {**births[2002], 'pid': 3003, 'nspid': [3003, 22], 'nstgid': [3003, 22]}
        pids.add(3003)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            observer.map_owner(probe, info, pids, pids, births)

    def test_v2_host_listener_scan_never_reads_foreign_uid_fd_or_namespace(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'net').mkdir(); (root / 'sys/kernel/random').mkdir(parents=True)
            (root / 'sys/kernel/random/boot_id').write_text('synthetic-boot')
            (root / 'net/tcp').write_text('synthetic header\n0: 0100007F:1776 00000000:0000 0A 0 0 0 0 0 987 1\n')
            (root / 'net/tcp6').write_text('synthetic header\n')
            proc = root / '123'; proc.mkdir()
            foreign_uid = 0 if os.geteuid() != 0 else 1000
            (proc / 'status').write_text('Uid:\t' + '\t'.join([str(foreign_uid)] * 4) + '\n')
            with mock.patch.object(observer.os, 'readlink', side_effect=AssertionError('foreign fd/ns must never be accessed')):
                report = observer.port_snapshot(6006, root)
            self.assertEqual(report['owners'], [])
            self.assertEqual(report['unowned_inodes'], ['987'])
            self.assertEqual(report['listeners'][0]['inode'], '987')

    def test_v2_host_birth_uses_only_world_readable_stat_status(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); proc = root / '123'; proc.mkdir()
            fields = ['0'] * 30; fields[0] = 'S'; fields[19] = '456'
            (proc / 'stat').write_text('123 (synthetic cpu root owner) ' + ' '.join(fields))
            (proc / 'status').write_text('Pid:\t123\nTgid:\t123\nNSpid:\t123\t22\nNStgid:\t123\t22\nUid:\t0\t0\t0\t0\n')
            with mock.patch.object(observer.os, 'readlink', side_effect=AssertionError('host namespace must never be accessed')):
                identity = observer.host_birth(123, root)
            self.assertEqual(identity['nspid'], [123, 22])
            self.assertEqual(identity['start_time_clock_ticks'], 456)
            self.assertTrue(identity['stable_birth'])

    def test_v2_generated_container_probe_parses_and_contains_only_readonly_calls(self):
        raw = observer.probe_source()
        tree = ast.parse(raw)
        self.assertIn(b'Exact container UID0', raw)
        self.assertIn(b'Private container init PID/status', raw)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {'write_text', 'write_bytes', 'unlink', 'kill', 'Popen', 'run'})

    def test_v2_top_requires_unique_exact_host_pids(self):
        self.assertEqual(observer.top_pids(b'PID PPID COMMAND\n1001 1 synthetic\n2002 1001 synthetic\n'), {1001, 2002})
        for raw in (b'UID PID\n0 1001\n', b'PID PPID\n1001 1\n1001 1\n', b'PID PPID\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): observer.top_pids(raw)

    def test_v2_snapshot_uses_exact_cid_readonly_exec_and_retains_source(self):
        probe, info, pids, births = self.mapping_fixture()
        probe['snapshot']['host_boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        info.update(Image='synthetic-image', Config={'User': ''}, Mounts=[], HostConfig={'NetworkMode': 'host', 'PidMode': ''})
        info['State']['Running'] = True
        commands = []
        def docker(argv, output, name, data=None):
            commands.append((argv, data))
            if argv[1:3] == ['container', 'inspect']:
                raw = json.dumps([info]).encode()
            elif argv[1] == 'top':
                raw = b'PID PPID COMMAND\n1001 1 synthetic-init\n2002 1001 synthetic-tb\n'
            else:
                self.assertEqual(argv, ['docker', 'exec', '--user', '0', '-i', 'a' * 64, '/usr/bin/python3', '-B', '-'])
                self.assertEqual(data, observer.probe_source())
                raw = json.dumps(probe).encode()
            return raw, {'synthetic_cpu_fixture': True, 'argv': argv, 'stdin_present': data is not None}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(observer, 'docker_read', side_effect=docker), mock.patch.object(observer, 'host_birth', side_effect=lambda pid: births[pid]):
                snapshot = observer.container_snapshot('a' * 64, Path(directory), 'synthetic-v2')
        self.assertEqual(snapshot['owners'][0]['pid'], 2002)
        self.assertEqual(len(commands), 5)
        self.assertTrue(snapshot['read_only_docker']['container_probe']['stdin_present'])

    def test_v2_snapshot_refuses_abbreviated_cid_before_any_docker_call(self):
        with mock.patch.object(observer, 'docker_read') as called, self.assertRaisesRegex(ValueError, 'full exact'):
            observer.container_snapshot('short', Path('/synthetic-unused'), 'synthetic-v2')
        called.assert_not_called()

    def test_v2_docker_timeout_preserves_partial_stdout_stderr_and_stdin(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            error = observer.subprocess.TimeoutExpired(['docker', 'top'], 30, output=b'synthetic partial stdout', stderr=b'synthetic partial stderr')
            with mock.patch.object(observer.subprocess, 'run', side_effect=error), self.assertRaisesRegex(ValueError, 'observation failed'):
                observer.docker_read(['docker', 'top', 'a' * 64], output, 'synthetic-timeout', b'print("synthetic readonly probe")')
            receipt = observer.read(output / 'synthetic-timeout.execution.json')
            self.assertTrue(receipt['timed_out'])
            self.assertIsNone(receipt['actual_wait_returncode'])
            self.assertEqual((output / 'synthetic-timeout.stdout.raw').read_bytes(), b'synthetic partial stdout')
            self.assertEqual((output / 'synthetic-timeout.stderr.raw').read_bytes(), b'synthetic partial stderr')
            self.assertIn('stdin', receipt)

    def test_downsampled_real_shape_keeps_original_final_step_value(self):
        result = observer.scalar_guard([[1., 0, 2.], [2., 10, 3.]], {'step': 10, 'value': 3.})
        self.assertEqual(result['samples_returned'], 2)
        self.assertEqual(result['last_step'], 10)

    def test_rejects_missing_wrong_final_nonfinite_duplicate_and_boolean_step(self):
        for values in ([], [[1., 9, 3.]], [[1., 10, 4.]], [[1., 10, float('nan')]], [[1., 10, 3.], [2., 10, 3.]], [[1., True, 3.]]):
            with self.subTest(values=values), self.assertRaises(ValueError): observer.scalar_guard(values, {'step': 10, 'value': 3.})

    def test_listener_identity_ignores_ordinary_runtime_status_changes(self):
        before = {'pid': 4, 'start_time_clock_ticks': 9, 'argv': ['ssh'], 'socket_inodes': ['7'], 'pid_namespace': 'pid:[8]', 'stable_birth': True,
                  'state': 'S', 'status_raw': 'voluntary_ctxt_switches: 10'}
        after = copy.deepcopy(before); after.update(state='R', status_raw='voluntary_ctxt_switches: 12')
        self.assertEqual(observer.owner_identity(before), observer.owner_identity(after))
        after['start_time_clock_ticks'] += 1
        self.assertNotEqual(observer.owner_identity(before), observer.owner_identity(after))

    def test_event_inventory_rejects_directory_alias_and_fingerprints_raw(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); path = root / 'events.out.tfevents.synthetic_control_fixture'; path.write_bytes(b'clearly synthetic bytes')
            rows = observer.events(root); self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['sha256'], observer.sha(path))
            (root / 'alias').symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Alias'): observer.events(root)
            with self.assertRaisesRegex(ValueError, 'Alias'): observer.events(root / 'alias')

    def test_new_cid_real_shape_inspect_is_bound_to_adoption_and_original_birth(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); event_root = root / 'official-full'; event_root.mkdir()
            cid = 'a' * 64
            result = root / 'synthetic-adoption-result.json'
            observer.save(result, {'status': 'passed_default_sdk018_control_adoption', 'new_container_id': cid,
                'original_container_id': 'b' * 64, 'scope': 'Synthetic test only; not real adoption'})
            original = {'Id': cid, 'Image': 'sha256:fdfb7221af88ad70236d8b40c463008677f9a622343972394efa99055ad71df3',
                'State': {'Running': True, 'StartedAt': 'synthetic_original_birth', 'Pid': os.getpid()},
                'Mounts': [{'Destination': '/outputs', 'Source': str(root)}], 'Config': {'synthetic_fixture': True}, 'HostConfig': {'NetworkMode': 'host'}}
            archived = root / 'synthetic-original-inspect.json'; observer.save(archived, original)
            args = SimpleNamespace(adoption_result=result, adoption_result_sha256=observer.sha(result), url='http://127.0.0.1:6006',
                adoption_container_inspect=archived, adoption_container_inspect_sha256=observer.sha(archived), event_root=event_root, container_init_pid=None)
            output = root / 'protocol-output'; output.mkdir()
            fake = SimpleNamespace(returncode=0, stdout=json.dumps([original]).encode(), stderr=b'')
            with mock.patch.object(observer.subprocess, 'run', return_value=fake) as call:
                bound = observer.adopted_container(args, output)
                self.assertEqual(bound['new_container_id'], cid)
                self.assertEqual(args.container_init_pid, os.getpid())
                self.assertEqual(call.call_args.args[0], ['docker', 'container', 'inspect', cid])
            changed = copy.deepcopy(original); changed['State']['StartedAt'] = 'synthetic_restarted_birth'
            fake.stdout = json.dumps([changed]).encode()
            output = root / 'protocol-output-changed'; output.mkdir()
            with mock.patch.object(observer.subprocess, 'run', return_value=fake), self.assertRaisesRegex(ValueError, 'birth'):
                observer.adopted_container(args, output)

    def adoption_v4_order_fixture(self, change=None):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); event_root = root / 'official-full'; event_root.mkdir()
        cid = 'a' * 64; result = root / 'synthetic-SDKv4-adoption-result.json'
        observer.save(result, {'status': 'passed_default_sdk018_control_adoption', 'new_container_id': cid,
            'original_container_id': 'b' * 64, 'control_revision': 4, 'scope': 'Synthetic ordinary CPU compatible result, not actual adoption'})
        original = {'Id': cid, 'Image': 'sha256:fdfb7221af88ad70236d8b40c463008677f9a622343972394efa99055ad71df3',
            'State': {'Running': True, 'StartedAt': 'synthetic-birth', 'Pid': os.getpid()},
            'Mounts': [{'Destination': '/outputs', 'Source': str(root), 'Type': 'bind', 'RW': True},
                       {'Destination': '/source', 'Source': '/synthetic/source', 'Type': 'bind', 'RW': False}],
            'Config': {'synthetic_only': True}, 'HostConfig': {'NetworkMode': 'host'}}
        archived = root / 'synthetic-original-inspect.json'; observer.save(archived, original)
        current = copy.deepcopy(original); current['Mounts'].reverse()
        if change: change(current)
        args = SimpleNamespace(adoption_result=result, adoption_result_sha256=observer.sha(result), url='http://127.0.0.1:6006',
            adoption_container_inspect=archived, adoption_container_inspect_sha256=observer.sha(archived),
            event_root=event_root, container_init_pid=None)
        output = root / 'protocol'; output.mkdir()
        fake = SimpleNamespace(returncode=0, stdout=json.dumps([current]).encode(), stderr=b'')
        return args, output, fake, original, current

    def test_v3_accepts_v4_result_schema_and_mount_order_preserving_original_raw(self):
        args, output, fake, original, current = self.adoption_v4_order_fixture()
        before = args.adoption_container_inspect.read_bytes()
        with mock.patch.object(observer.subprocess, 'run', return_value=fake):
            bound = observer.adopted_container(args, output)
        self.assertEqual(bound['new_container_id'], 'a' * 64)
        self.assertEqual(observer.container_identity(original), observer.container_identity(current))
        self.assertEqual(args.adoption_container_inspect.read_bytes(), before)
        raw = Path(bound['current_inspect_command']['stdout']['path']).read_bytes()
        self.assertEqual(raw, fake.stdout)

    def test_v3_rejects_changed_full_mount_row_despite_reordering(self):
        args, output, fake, _, _ = self.adoption_v4_order_fixture(lambda info: info['Mounts'][0].update(RW=True))
        with mock.patch.object(observer.subprocess, 'run', return_value=fake), self.assertRaises(ValueError):
            observer.adopted_container(args, output)

    def test_v3_rejects_changed_birth_despite_mount_order(self):
        args, output, fake, _, _ = self.adoption_v4_order_fixture(lambda info: info['State'].update(StartedAt='synthetic-restart'))
        with mock.patch.object(observer.subprocess, 'run', return_value=fake), self.assertRaises(ValueError):
            observer.adopted_container(args, output)


if __name__ == '__main__': unittest.main(verbosity=2)
