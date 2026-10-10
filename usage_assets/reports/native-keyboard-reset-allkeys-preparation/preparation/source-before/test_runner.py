"""CPU-only guard/TTY/failure tests. No X server, key injection, SDK or DDS."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zlib
import common
import container_runner as runner
import host_runner as host
from x11_owned import OwnedDisplay, png_rgb

SUPERVISOR = Path(os.environ.get('GUI_TEST_SUPERVISOR', '/workspace/php_parkour/scripts/research/sim2sim.py'))
CPU_OBSERVATIONS = []


class EvidenceTests(unittest.TestCase):
    def test_changed_input_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); file = root / 'a'; file.write_bytes(b'one')
            record = {'relative': 'a', **common.fingerprint(file)}
            common.verify_files(root, [record]); file.write_bytes(b'two')
            with self.assertRaises(ValueError): common.verify_files(root, [record])

    def test_traversal_absolute_duplicate_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / 'a').write_bytes(b'a'); (root / 'link').symlink_to(root / 'a')
            valid = {'relative': 'a', **common.fingerprint(root / 'a')}
            for records in ([valid, valid], [{'relative': '../a'}], [{'relative': '/tmp/a'}],
                            [{'relative': 'link', **common.fingerprint(root / 'a')}]):
                with self.subTest(records=records), self.assertRaises(ValueError): common.verify_files(root, records)

    def test_sealed_plan_tamper_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); file = root / 'plan.json'
            plan = {'schema_version': 1, 'image_id': host.IMAGE, 'gpu_uuid': host.GPU, 'status': 'prepared_not_executed',
                    'owner_uid': os.getuid(), 'cohort_root': str(root.resolve()), 'token': 'a'*32, 'private_display': ':91',
                    'files': [], 'operator_helpers': {}, 'container_hostname': 'php-gui-'+'a'*32}
            plan['plan_sha256'] = common.identity(plan); common.write(file, plan)
            self.assertEqual(host.checked_plan(file)['token'], 'a'*32)
            plan['private_display'] = ':0'; common.write(file, plan)
            with self.assertRaises(ValueError): host.checked_plan(file)

    def test_high_private_display_guard(self):
        for value in (':0', ':49', 'localhost:91', ':91.0', ':1000', '', ':x'):
            with self.subTest(value=value), self.assertRaises(ValueError): host.display_number(value)
        self.assertEqual(host.display_number(':91'), 91)

    def test_x11_refuses_host_display_without_import_or_connection(self):
        with patch.dict(os.environ, {'DISPLAY': ':0'}), self.assertRaises(ValueError): OwnedDisplay(':0', 'token')
        with patch.dict(os.environ, {'DISPLAY': ':0'}), self.assertRaises(ValueError): OwnedDisplay(':91', 'token')

    def test_xid_guard_before_x11_access(self):
        display = OwnedDisplay.__new__(OwnedDisplay)
        with self.assertRaises(ValueError): display.focus(123, {456})
        with self.assertRaises(ValueError): display.capture(123, '/unused', {456})
        with self.assertRaises(ValueError): display.place_native_window(123, {456})

    def test_png_exact_rgb_bytes_crc(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / 'rgb.png'; rgb = bytes(range(18)); png_rgb(path, 3, 2, rgb)
            data = path.read_bytes(); self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            chunks = {}; index = 8
            while index < len(data):
                size = struct.unpack('!I', data[index:index+4])[0]; name = data[index+4:index+8]
                payload = data[index+8:index+8+size]; crc = struct.unpack('!I', data[index+8+size:index+12+size])[0]
                self.assertEqual(crc, zlib.crc32(name+payload)&0xffffffff); chunks[name] = payload; index += 12+size
            self.assertEqual(zlib.decompress(chunks[b'IDAT']), b'\0'+rgb[:9]+b'\0'+rgb[9:])
            with self.assertRaises(ValueError): png_rgb(path, 3, 2, b'bad')

    def test_new_container_args_bind_private_identity(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            plan = {'token': 'abc', 'cohort_root': str(root / 'cohort'), 'private_display': ':91', 'container_hostname': 'php-gui-abc'}
            argv = host.create_argv(plan, root, root / 'auth')
            self.assertEqual(argv[argv.index('--network')+1], 'none')
            self.assertEqual(argv[argv.index('--ipc')+1], 'private')
            self.assertEqual(argv[argv.index('--gpus')+1], 'device='+host.GPU)
            self.assertEqual(argv[argv.index('--hostname')+1], plan['container_hostname'])
            mounts = [argv[i+1] for i, token in enumerate(argv[:-1]) if token == '--mount']
            self.assertTrue(any('dst=/workspace/php_parkour,readonly' in m for m in mounts))
            self.assertTrue(any('dst=/tmp/.X11-unix/X91,readonly' in m for m in mounts))
            self.assertFalse(any('X0' in m or 'docker.sock' in m for m in mounts))
            self.assertIn(host.IMAGE, argv)
            self.assertIn('MUJOCO_GL=egl', argv)
            self.assertNotIn('MUJOCO_GL=glfw', argv)

    def test_foreign_container_never_stopped_or_execed(self):
        with patch.object(host, 'command') as command:
            command.return_value = json.dumps([{'Id': '0'*64, 'Name': '/foreign', 'Image': host.IMAGE,
                'Config': {'Labels': {}}, 'HostConfig': {'NetworkMode': 'none', 'IpcMode': 'private'}}])
            with self.assertRaises(ValueError): host.inspect_owned('0'*64, 'own', {'image_id': host.IMAGE, 'token': 'own'})
            self.assertEqual(command.call_count, 1)
            self.assertEqual(command.call_args.args[0][1], 'inspect')

    def test_native_argv_original_wrappers_keyboard_and_offline_video(self):
        sim, infer = runner.native_argv(Path('/outputs'), 'tok')
        self.assertEqual(sim[:2], ['bash', './run_php_sim.sh']); self.assertEqual(infer[:2], ['bash', './run_php_inference.sh'])
        self.assertEqual(infer[infer.index('--task.velocity-input')+1], 'keyboard')
        self.assertEqual(infer[infer.index('--task.state-input')+1], 'keyboard')
        self.assertEqual(sim[sim.index('--training.headless')+1], 'False')
        self.assertEqual(sim[sim.index('--logger.video.upload-to-wandb')+1], 'False')
        self.assertNotIn('injected', infer)
        self.assertEqual(sim[sim.index('--terrain.terrain-term.mesh-type')+1], 'PLANE')

    def test_exact_local_auth_supported_and_wild_rejected_by_real_xlib(self):
        from Xlib import xauth, error
        # Synthetic bytes only, never an actual display credential.
        cookie = bytes(range(16))
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / 'auth'
            path.write_bytes(host.auth_record('php-gui-synthetic', ':91', cookie))
            authority = xauth.Xauthority(str(path))
            self.assertEqual(authority.get_best_auth(xauth.FamilyLocal, b'php-gui-synthetic', 91), (b'MIT-MAGIC-COOKIE-1',cookie))
            with self.assertRaises(error.XNoAuthError): authority.get_best_auth(xauth.FamilyLocal, b'other-host', 91)
            authority.entries = [(65535,b'php-gui-synthetic',b'91',b'MIT-MAGIC-COOKIE-1',cookie)]
            with self.assertRaises(error.XNoAuthError): authority.get_best_auth(xauth.FamilyLocal,b'php-gui-synthetic',91)

    def test_host_mapping_requires_exact_birth_and_real_writer_thread(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); (root / 'host/observer').mkdir(parents=True)
            for i, role in enumerate(('simulator', 'inference')):
                directory = root / 'outputs' / role; directory.mkdir(parents=True)
                common.write(directory / 'process-entry.json', {'process': {'pid': i+1, 'start_time_clock_ticks': 10}})
            p = lambda pid, birth: {'container_pid': pid, 'host_pid': pid+1000, 'start_time_clock_ticks': birth,
                                   'nspid': [pid+1000, pid], 'command_writer_threads': [{'container_tid': 42}]}
            path = root / 'host/observer/snapshots.jsonl'
            path.write_text(json.dumps({'unix': 1, 'processes': [p(1,10), p(2,11)]})+'\n')
            with self.assertRaises(RuntimeError): host.verify_host_mappings(root)
            path.write_text(json.dumps({'unix': 2, 'processes': [p(1,10), p(2,10)]})+'\n')
            self.assertEqual(set(host.verify_host_mappings(root)), {'simulator', 'inference'})


class OwnershipTests(unittest.TestCase):
    def test_slow_initial_settle_still_requires1000actual_ticks(self):
        session = runner.Session.__new__(runner.Session)
        ticks = {'physics_ticks':999}; session.state = lambda role: ticks
        calls = []
        def wait(predicate, description, seconds):
            self.assertFalse(predicate()); ticks['physics_ticks'] = 1000
            self.assertTrue(predicate()); calls.append((description,seconds))
        session.wait = wait; session.initial_settle()
        self.assertEqual(calls[0][1], 60)
        self.assertIn('1000ticks', calls[0][0])
    def test_terminal_focus_is_verified_before_any_x11_key(self):
        calls=[]
        session=runner.Session.__new__(runner.Session)
        session.text=types.SimpleNamespace(focus_force=lambda:calls.append('tk_focus_force'))
        session.root=types.SimpleNamespace(update=lambda:calls.append('tk_update'),focus_get=lambda:session.text)
        session.terminal_xid=7;session.record=lambda kind,**kw:calls.append(kind)
        session.focus_terminal()
        self.assertEqual(calls,['tk_focus_force','tk_update','owned_terminal_tk_focus'])
        calls.clear();session.root.focus_get=lambda:None
        with self.assertRaises(RuntimeError):session.focus_terminal()
        self.assertEqual(calls,['tk_focus_force','tk_update'])

    def test_terminal_tap_focus_failure_prevents_xtest(self):
        session=runner.Session.__new__(runner.Session)
        session.terminal_xid=7;session.guard_display=lambda:None
        session.focus_terminal=lambda:(_ for _ in ()).throw(RuntimeError('focus mismatch'))
        session.display=types.SimpleNamespace(key=lambda *args:self.fail('XTEST must not be called'))
        with self.assertRaisesRegex(RuntimeError,'focus mismatch'):session.tap('bracketright')

    def test_reused_native_birth_never_signalled(self):
        old = {'pid': 123, 'start_time_clock_ticks': 10, 'process_group_id': 123, 'session_id': 123}
        module = types.SimpleNamespace(process_identity=lambda pid: old | {'start_time_clock_ticks': 11},
            worker_group_status=lambda group: {'ownership_verified': True, 'known_members': [{'pid': 123, 'start_time_clock_ticks': 10}]})
        with patch.object(os, 'kill') as kill, self.assertRaises(RuntimeError): common.signal_native(module, {}, old, signal.SIGINT)
        kill.assert_not_called()

    def test_cleanup_even_if_log_open_fails_after_spawn(self):
        session = runner.Session.__new__(runner.Session)
        session.output = Path('/unused'); session.workers = {}; session.plan = {'token': 'abc'}
        process = types.SimpleNamespace(pid=123)
        with patch.object(Path, 'mkdir'), patch.object(runner, 'spawn_pty', return_value=(process, 456)), \
                patch.object(runner, 'birth_group', return_value={'own': True}), patch.object(Path, 'open', side_effect=OSError('disk')):
            session.module = object()
            with self.assertRaises(OSError): session.start('inference', ['unused'])
        self.assertIs(session.workers['inference']['process'], process)
        self.assertEqual(session.workers['inference']['group'], {'own': True})

    def test_unknown_display_client_blocks_before_input(self):
        session = runner.Session.__new__(runner.Session)
        session.workers = {}; session.display = types.SimpleNamespace(windows=lambda: [{'pid': 999999, 'xid': 123}])
        with self.assertRaises(RuntimeError): session.guard_display()

    def test_native_nonzero_not_rewritten(self):
        session = runner.Session.__new__(runner.Session)
        process = types.SimpleNamespace(pid=123, returncode=130, poll=lambda: 130)
        session.workers = {'inference': {'process': process, 'entry': {'process': {'pid': 123}}, 'master': 4, 'group': {}}}
        session.record = lambda *a, **k: None; session.wait = lambda *a, **k: None; session.pump = lambda *a: None
        session.module = types.SimpleNamespace(worker_group_status=lambda group: {}, process_return_status=lambda p: {'returncode': p.returncode})
        session.state = lambda role: {'lifecycle': 'main_returned'}
        with patch.object(os, 'tcgetpgrp', return_value=123), patch.object(runner, 'signal_native'), self.assertRaises(RuntimeError):
            session.interrupt('inference')
        self.assertEqual(process.returncode, 130)

    def test_owned_real_pty_input_and_original_sigint_handler(self):
        # Actual ordinary stdlib CPU subprocess; no simulation/SDK/native libs.
        module = common.load(SUPERVISOR, 'gui_cpu_pty_ownership')
        script = """import json,os,sys,tty,time
print(json.dumps({'ready':True,'isatty':os.isatty(0),'pid':os.getpid(),'pgid':os.getpgrp(),'sid':os.getsid(0),'fg':os.tcgetpgrp(0)}),flush=True)
tty.setraw(0)
received=os.read(0,2)
print(json.dumps({'received':received.decode()}),flush=True)
try:
 while True: time.sleep(.1)
except KeyboardInterrupt:
 print('ORIGINAL_MAIN_RETURNED',flush=True)
"""
        process, master = runner.spawn_pty([sys.executable, '-u', '-c', script], os.environ.copy(), '/')
        group = common.birth_group(module, process); payload = bytearray()
        def until(marker):
            stop = time.monotonic()+5
            while marker not in payload:
                if time.monotonic() > stop: self.fail('ordinary CPU PTY did not acknowledge: '+repr(payload))
                if select.select([master], [], [], .1)[0]:
                    try: payload.extend(os.read(master, 65536))
                    except OSError: break
        try:
            until(b'"ready": true'); entry = json.loads(payload.splitlines()[0])
            self.assertTrue(entry['isatty'])
            self.assertEqual({entry[k] for k in ('pid', 'pgid', 'sid', 'fg')}, {process.pid})
            # Ready was printed just before tty.setraw; wait briefly for raw mode.
            time.sleep(.05); os.write(master, b']c'); until(b'"received": "]c"')
            native = module.process_identity(process.pid)
            common.signal_native(module, group, native, signal.SIGINT)
            self.assertEqual(process.wait(timeout=5), 0)
            until(b'ORIGINAL_MAIN_RETURNED')
            self.assertTrue(module.wait_worker_shutdown(process, group, 2))
            CPU_OBSERVATIONS.append({'scope': 'ordinary stdlib CPU child; no native/DDS/X',
                'entry': entry, 'birth': native, 'actual_returncode': process.returncode,
                'raw_pty_utf8': payload.decode(errors='replace'), 'final_group': module.worker_group_status(group)})
        finally:
            common.cleanup_group(module, process, group, [], .1)
            os.close(master)


class RecordingTests(unittest.TestCase):
    def test_real_schema_cpu_fixture_not_motion_quality(self):
        import numpy as np
        from check_recordings import check
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / 'synthetic.npz'
            qpos = np.zeros((4,36),dtype=np.float32); qpos[:,0] = 1
            command = np.zeros((4,15),dtype=np.float32); command[:,1] = 1
            np.savez(path,qpos=qpos,vel_cmd=command,fps=np.array(50))
            result = check(path, 1); self.assertTrue(result['not_a_training_bundle'])
            with self.assertRaises(ValueError): check(path, 6)
            command[0,2] = 1
            np.savez(path,qpos=qpos,vel_cmd=command,fps=np.array(50))
            with self.assertRaises(ValueError): check(path, 1)


class ObserverTests(unittest.TestCase):
    def test_observers_call_each_original_once_preserve_return_and_heartbeat(self):
        import numpy as np
        import observe_native as observer
        class Policy:
            def __init__(self):
                self.initialized = 1; self.velocity_command = np.eye(15, dtype=np.float32)[:1]
                self._recording = False; self._record_toggle_request = False; self._record_qpos = []
            def _dispatch_command(self, command): self.dispatched = command; return 12
            def _service_recording(self, *args, **kwargs): self._recording = True; return 13
        class Base:
            def _on_command_sent(self, command, state): self.sent = getattr(self, 'sent', 0)+1; return 14
        class Interface:
            def send_low_command(self, *args, **kwargs): self.calls = getattr(self, 'calls', 0)+1; return 15
        class Sensor:
            def liveness(self):
                self.calls = getattr(self, 'calls', 0)+1
                self.last = types.SimpleNamespace(checked=True, seq=self.calls, state='OK', stale_s=0., restarted=False)
                return self.last
        leaves = {'holosoma_inference.policies.base': {'BasePolicy': Base},
                  'holosoma_inference.policies.depth_distillation': {'DepthDistillationPolicy': Policy},
                  'holosoma_inference.sdk.unitree.unitree_interface': {'UnitreeInterface': Interface},
                  'holosoma_inference.sensors.depth_shm': {'DepthShmSensor': Sensor}}
        modules = {}
        for name, attrs in leaves.items():
            parts = name.split('.')
            for i in range(1,len(parts)+1):
                prefix = '.'.join(parts[:i]); modules.setdefault(prefix, types.ModuleType(prefix)); modules[prefix].__path__ = []
            modules[name].__dict__.update(attrs)
        with tempfile.TemporaryDirectory() as value, patch.dict(sys.modules, modules):
            observer.OUT = Path(value); observer.REPORT.clear(); observer.install_inference()
            policy = Policy(); command = types.SimpleNamespace(name='fixture')
            self.assertEqual(policy.initialized, 1); self.assertEqual(policy._dispatch_command(command), 12)
            self.assertIs(policy.dispatched, command); self.assertEqual(policy._service_recording(None), 13)
            for _ in range(5): self.assertEqual(Base._on_command_sent(policy, np.ones(29), np.ones((1,65))), 14)
            self.assertEqual(policy.sent, 5)
            interface = Interface(); interface.robot_config = types.SimpleNamespace(motor_kp=np.ones(29), motor_kd=np.ones(29))
            interface._kp_level = 0; interface._kd_level = 1
            for _ in range(5): self.assertEqual(interface.send_low_command(None), 15)
            self.assertEqual(interface.calls, 5)
            sensor = Sensor()
            for _ in range(3): self.assertIs(sensor.liveness(), sensor.last)
            self.assertEqual(sensor.calls, 3); self.assertEqual(observer.REPORT['depth_heartbeat']['advances'], 2)
            self.assertEqual(observer.REPORT['last_python_sender_gains']['kp'], [0.]*29)

    def test_sim_state_readonly_no_cache_refresh(self):
        import numpy as np
        from observe_native import simulator_state
        qpos = np.arange(36, dtype=float); qvel = np.arange(35, dtype=float)
        sim = types.SimpleNamespace(root_data=types.SimpleNamespace(qpos=qpos, qvel=qvel),
                                    virtual_gantry=types.SimpleNamespace(enabled=True, length=.5))
        before = qpos.copy(); result = simulator_state(sim)
        self.assertTrue(np.array_equal(qpos, before)); self.assertEqual(result['root_state'], list(qpos[:7])+list(qvel[:6]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
