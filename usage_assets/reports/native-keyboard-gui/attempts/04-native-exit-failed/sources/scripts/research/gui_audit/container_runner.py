"""Operator-run private Docker GUI supervisor. Imports no native code itself."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import sys
import termios
import time
import traceback

from common import (HARNESS_SHA, birth_group, cleanup_group, fingerprint, identity, load,
                    sha, signal_native, verify_files, write)


def controlling_tty():
    # Popen start_new_session has already made this child's PGID=SID=PID.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.tcsetpgrp(0, os.getpgrp())


def spawn_pty(argv, env, cwd):
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                                   start_new_session=True, preexec_fn=controlling_tty, close_fds=True)
    except BaseException:
        os.close(master)
        raise
    finally:
        os.close(slave)
    os.set_blocking(master, False)
    return process, master


def decode(path):
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-i', str(path), '-f', 'null', '-']
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    value = {'command': command, 'returncode': result.returncode, 'stderr': result.stderr, **fingerprint(path)}
    if result.returncode:
        raise RuntimeError('Actual native MP4 full decode failed: ' + str(path))
    return value


def native_argv(output, token):
    # The unchanged wrapper already selects terrain:terrain-load-step. Tyro
    # rejects a second terrain subcommand; explicitly override its mesh enum.
    sim = ['bash', './run_php_sim.sh', '--terrain.terrain-term.mesh-type', 'PLANE', '--simulator.config.bridge.interface', 'lo',
           '--simulator.config.sim.control-decimation', '10', '--simulator.config.virtual-gantry.length', '0.5',
           '--training.headless', 'False', '--training.seed', '42', '--device', 'cpu',
           '--logger.video.enabled', 'True', '--logger.video.width', '640', '--logger.video.height', '360',
           '--logger.video.save-dir', str(output / 'video'), '--logger.video.upload-to-wandb', 'False']
    infer = ['bash', './run_php_inference.sh', '--task.velocity-input', 'keyboard', '--task.state-input', 'keyboard',
             '--task.record-dir', str(output / 'recordings'), '--task.record-label', token]
    return sim, infer


class Session:
    def __init__(self, plan, output):
        import tkinter as tk
        from x11_owned import OwnedDisplay
        self.plan, self.output, self.tk = plan, output, tk
        self.deadline = time.monotonic() + 300
        self.module = load('/workspace/php_parkour/scripts/research/sim2sim.py', 'gui_supervisor_ownership')
        if sha('/workspace/php_parkour/scripts/research/sim2sim.py') != HARNESS_SHA:
            raise ValueError('Reviewed birth-identity supervisor changed')
        self.workers, self.events, self.cleanup, self.errors = {}, [], [], []
        self.root = self.display = None

    def initialize(self):
        tk = self.tk
        plan = self.plan
        from x11_owned import OwnedDisplay
        self.root = tk.Tk()
        self.root.report_callback_exception = lambda kind, value, tb: self.errors.append('Tk callback: ' + str(value))
        self.root.title('PHP GUI audit policy terminal ' + plan['token'])
        self.root.geometry('900x250+0+930')
        self.text = tk.Text(self.root, background='white', foreground='black', wrap='word')
        self.text.pack(fill='both', expand=True)
        self.text.bind('<KeyPress>', self.terminal_key)
        self.root.protocol('WM_DELETE_WINDOW', lambda: self.errors.append('Operator closed audit terminal'))
        self.root.update()
        self.display = OwnedDisplay(plan['private_display'], plan['token'])
        self.terminal_xid = self.text.winfo_id()
        self.display.mark_pid(self.root.winfo_id(), os.getpid())
        self.display.mark_pid(self.terminal_xid, os.getpid())
        self.allowed = {self.terminal_xid, self.root.winfo_id()}
        self.native_xid = None
        self.last_receipt = 0

    def record(self, kind, **values):
        item = {'kind': kind, 'unix': time.time(), 'monotonic': time.monotonic(), **values}
        self.events.append(item)
        with (self.output / 'operator-events.jsonl').open('a') as stream:
            stream.write(json.dumps(item, allow_nan=False) + '\n')

    def terminal_key(self, event):
        if 'inference' not in self.workers:
            return 'break'
        value = event.char
        if value:
            payload = value.encode('utf-8')
            os.write(self.workers['inference']['master'], payload)
            self.record('real_terminal_key_to_pty', keysym=event.keysym, bytes_hex=payload.hex(),
                        tty=os.ttyname(self.workers['inference']['master']), terminal_xid=self.terminal_xid)
        return 'break'

    def start(self, role, argv):
        directory = self.output / role
        directory.mkdir(exist_ok=True)
        env = os.environ | {'PHP_GUI_OUTPUT': str(self.output), 'PYTHONFAULTHANDLER': '1', 'PHP_DOCKER': '1',
                            'BACKBONE': '/data/assets/student/depth_backbone.onnx', 'STUDENT': '/data/assets/student/student.onnx'}
        process, master = spawn_pty(argv, env, '/workspace/php_parkour')
        worker = {'process': process, 'master': master, 'group': None, 'argv': argv,
                  'raw': None, 'text': None, 'entry': None, 'console': ''}
        # Register before any diagnostic write so failures still reach cleanup.
        self.workers[role] = worker
        worker['group'] = birth_group(self.module, process)
        worker['raw'] = (directory / 'pty.raw').open('xb')
        worker['text'] = (directory / 'stdout.txt').open('x')
        self.record('worker_spawned', role=role, argv=argv, group=worker['group'],
                    pty_master_tty=os.ttyname(master), parent_pid=os.getpid())
        self.persist()

    def state(self, role):
        path = self.output / role / 'state.json'
        return json.loads(path.read_text()) if path.is_file() else {}

    def persist(self):
        workers = []
        for role, w in self.workers.items():
            status = self.module.worker_group_status(w['group']) if w['group'] else {'ownership_verified': False, 'live_members': None}
            workers.append({'role': role, 'argv': w['argv'], 'pid': w['process'].pid,
                            'return_status': self.module.process_return_status(w['process']), 'process_group': status,
                            'native_entry': w['entry']})
        write(self.output / 'worker-receipts.json', {'schema_version': 1, 'scope': 'GUI wrapper/PTYS; distinct from matrix schema3',
              'plan_sha256': self.plan['plan_sha256'], 'unix': time.time(), 'workers': workers,
              'cleanup_actions': self.cleanup, 'errors': self.errors})

    def pump(self, allow_exited=False):
        if time.monotonic() > self.deadline:
            raise TimeoutError('Bounded GUI session exceeded300 seconds')
        self.root.update()
        if self.errors:
            raise RuntimeError('; '.join(self.errors))
        for role, w in self.workers.items():
            self.module.worker_group_status(w['group'])
            while select.select([w['master']], [], [], 0)[0]:
                try:
                    raw = os.read(w['master'], 65536)
                except OSError as error:
                    if error.errno == 5:
                        break
                    raise
                if not raw:
                    break
                w['raw'].write(raw); w['raw'].flush()
                text = raw.decode('utf-8', errors='replace')
                w['text'].write(text); w['text'].flush()
                w['console'] += text
                if role == 'inference':
                    self.text.insert('end', re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text))
                    self.text.see('end')
            entry_path = self.output / role / 'process-entry.json'
            if w['entry'] is None and entry_path.is_file():
                entry = json.loads(entry_path.read_text())
                native = entry['process']
                known = {'pid': native['pid'], 'start_time_clock_ticks': native['start_time_clock_ticks']}
                group = self.module.worker_group_status(w['group'])
                if (known not in group['known_members'] or native['process_group_id'] != w['process'].pid
                        or native['session_id'] != w['process'].pid or not entry['tty']['stdin_isatty']
                        or entry['tty']['foreground_pgid'] != w['process'].pid):
                    raise ValueError('Native entry is not birth-bound to the private foreground PTY group')
                w['entry'] = entry
                self.record('native_entry_observed', role=role, raw_sha256=sha(entry_path), process=native, tty=entry['tty'])
            if not allow_exited and w['process'].poll() is not None:
                raise RuntimeError(role + ' wrapper exited before requested shutdown: ' + str(w['process'].returncode))
        if time.monotonic() - self.last_receipt >= .5:
            self.persist(); self.last_receipt = time.monotonic()
        time.sleep(.02)

    def wait(self, predicate, description, seconds=12, allow_exited=False):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError(description)
            self.pump(allow_exited)
        self.record('acknowledged', condition=description)

    def focus_terminal(self):
        # Tk has a per-toplevel logical focus in addition to X11 focus.
        # Set it on our own console widget before XTEST; never a native state.
        self.text.focus_force()
        self.root.update()
        if self.root.focus_get() is not self.text:
            raise RuntimeError('Tk focus did not reach the owned terminal widget')
        self.record('owned_terminal_tk_focus', terminal_xid=self.terminal_xid,
                    tk_focus=str(self.root.focus_get()))

    def tap(self, keysym, target=None):
        self.guard_display()
        target = self.terminal_xid if target is None else target
        if target == self.terminal_xid:
            self.focus_terminal()
        self.record('xtest_key_down_requested', keysym=keysym, target_xid=target)
        self.display.key(target, keysym, True, self.allowed)
        for _ in range(4):
            self.pump()
        self.display.key(target, keysym, False, self.allowed)
        self.record('xtest_key_up_requested', keysym=keysym, target_xid=target)
        self.pump()

    def hold_forward(self, expected):
        self.guard_display()
        self.focus_terminal()
        self.record('xtest_direction_down_requested', keysym='w', target_xid=self.terminal_xid)
        self.display.key(self.terminal_xid, 'w', True, self.allowed)
        try:
            self.wait(lambda: self.state('inference').get('policy', {}).get('active_velocity_command_idx') == expected,
                      'native direction command ' + str(expected))
            until = time.monotonic() + .8
            while time.monotonic() < until:
                self.pump()
            self.capture('forward-' + str(expected))
        finally:
            self.display.key(self.terminal_xid, 'w', False, self.allowed)
            self.record('xtest_direction_up_requested', keysym='w', target_xid=self.terminal_xid)
        self.wait(lambda: self.state('inference').get('policy', {}).get('active_velocity_command_idx') == 0,
                  'native release returns to command0')

    def guard_display(self):
        allowed_pids = {os.getpid()}
        for w in self.workers.values():
            current = self.module.worker_group_status(w['group'])
            if not current['ownership_verified']:
                raise RuntimeError('Private worker ownership unavailable before input')
            allowed_pids.update(v['pid'] for v in current['live_members'])
        for window in self.display.windows():
            if window['pid'] not in allowed_pids:
                raise RuntimeError('Unexpected named client on private display; refuse input')

    def capture(self, label):
        if self.native_xid is None:
            raise RuntimeError('Owned MuJoCo drawable not identified')
        path = self.output / (label + '.png')
        value = self.display.capture(self.native_xid, path, self.allowed)
        self.record('native_window_capture', label=label, path=str(path), **value, **fingerprint(path))

    def find_native_window(self):
        w = self.workers['simulator']
        status = self.module.worker_group_status(w['group'])
        pids = {item['pid'] for item in status.get('live_members') or []}
        windows = [v for v in self.display.windows() if 'MuJoCo' in v['title'] and v['pid'] in pids]
        if len(windows) != 1:
            return False
        self.native_xid = windows[0]['xid']; self.allowed.add(self.native_xid)
        self.record('owned_native_window_identified', **windows[0])
        self.record('owned_native_window_placed', **self.display.place_native_window(self.native_xid, self.allowed))
        return True

    def interrupt(self, role):
        w = self.workers[role]
        if w['entry'] is None:
            raise RuntimeError('No native entry identity for requested normal interrupt')
        native = w['entry']['process']
        self.record('normal_interrupt_requested', role=role, signal_number=int(signal.SIGINT),
                    target='exact observed native Python PID; waiting Bash is not interrupted', process=native,
                    actual_master_foreground_pgid=os.tcgetpgrp(w['master']))
        signal_native(self.module, w['group'], native, signal.SIGINT)
        self.wait(lambda: w['process'].poll() is not None, role + ' wrapper actual exit', 25, True)
        self.pump(True)
        group = self.module.worker_group_status(w['group'])
        state = self.state(role)
        self.record('normal_interrupt_completed', role=role, actual_wrapper_status=self.module.process_return_status(w['process']),
                    original_main_lifecycle=state.get('lifecycle'), process_group=group)
        if w['process'].returncode != 0 or state.get('lifecycle') != 'main_returned':
            raise RuntimeError(role + ' did not complete original main with actual wrapper rc0')
        if not self.module.wait_worker_shutdown(w['process'], w['group'], 3):
            raise RuntimeError(role + ' has a live descendant after wrapper rc0')

    def initial_settle(self):
        # Visible Xephyr/GLFW rendering can run slower than real time. Keep
        # the actual1000tick=2simulation-second requirement, allowing bounded
        # wall time without changing physics/policy timing or accepting timeout.
        self.wait(lambda: self.state('simulator').get('physics_ticks', 0) >= 1000,
                  'actual simulator initial settle1000ticks=2simseconds', seconds=60)

    def run(self):
        sim, infer = native_argv(self.output, self.plan['token'])
        if list(Path('/dev/shm').glob('*depth*')):
            raise ValueError('Fresh private container has unexpected preexisting depth SHM; no launcher deletion allowed')
        self.start('simulator', sim)
        self.wait(lambda: self.state('simulator').get('ready') and self.find_native_window(), 'actual MuJoCo initialization/window', 60)
        self.start('inference', infer)
        self.wait(lambda: bool(self.state('inference').get('policy')), 'actual depth policy initialized', 60)
        if 'hold-to-move' not in self.workers['inference']['console']:
            self.wait(lambda: 'hold-to-move' in self.workers['inference']['console'], 'real X11 hold listener enabled')
        self.wait(lambda: (lambda beat: beat.get('advances', 0) >= 3 and beat.get('state') == 'OK' and beat.get('stale_s', 999) < .5)
                  (self.state('inference').get('depth_heartbeat', {})),
                  'original native liveness polls observed3 producer sequence advances')
        self.initial_settle()
        self.capture('initial-stiff')
        self.tap('8', self.native_xid)
        self.wait(lambda: self.state('simulator').get('simulation', {}).get('gantry_length', 0) > .55, 'actual gantry8 increase')
        self.tap('9', self.native_xid)
        self.wait(lambda: self.state('simulator').get('simulation', {}).get('gantry_enabled') is False, 'actual gantry disabled')
        self.tap('bracketright')
        self.wait(lambda: self.state('inference').get('policy', {}).get('use_policy_action') is True, 'native ] starts policy')
        self.tap('c')
        self.wait(lambda: self.state('inference').get('policy', {}).get('_recording') is True, 'native recording begins')
        self.hold_forward(1)
        self.wait(lambda: self.state('inference').get('policy', {}).get('recorded_frames', 0) >= 80, 'manual clip80 actual frames')
        self.tap('c')
        clips = lambda: sorted((self.output / 'recordings').glob('*.npz'))
        self.wait(lambda: len(clips()) == 1, 'native c manual save')
        manual = clips()[0]
        self.tap('equal')
        self.wait(lambda: self.state('inference').get('policy', {}).get('speed_mode') == 1, 'native = high speed')
        self.tap('c')
        self.wait(lambda: self.state('inference').get('policy', {}).get('_recording') is True, 'second real recorder starts')
        self.hold_forward(6)
        self.wait(lambda: self.state('inference').get('policy', {}).get('recorded_frames', 0) >= 45, 'autosave clip45 actual frames')
        self.tap('o')
        self.wait(lambda: self.state('inference').get('policy', {}).get('_damping_mode_active') is True and len(clips()) == 2,
                  'native o damping and automatic recording save')
        auto = next(p for p in clips() if p != manual)
        self.wait(lambda: all(v == 0 for v in self.state('inference').get('last_python_sender_gains', {}).get('kp', [1]))
                  and all(v > 0 for v in self.state('inference').get('last_python_sender_gains', {}).get('kd', [0])),
                  'observed Python sender damping gains')
        self.capture('damping')
        self.tap('i')
        self.wait(lambda: self.state('inference').get('policy', {}).get('_stiff_hold_active') is True
                  and self.state('inference').get('policy', {}).get('_damping_mode_active') is False, 'native i stiff hold')
        self.capture('final-stiff')
        self.record('terminal_capture', **self.display.capture(self.terminal_xid, self.output / 'policy-terminal.png', self.allowed))
        self.interrupt('inference')
        # DirectSimulation.run is while True with Ctrl-C handler; closing the
        # passive viewer is not an exit guarantee. Use its original SIGINT path.
        self.interrupt('simulator')
        from check_recordings import check
        recording_checks = [check(manual, 1), check(auto, 6)]
        videos = sorted((self.output / 'video').rglob('*.mp4'))
        if not videos:
            raise RuntimeError('Native video was not saved during simulator cleanup')
        for w in self.workers.values():
            if re.search(r'Segmentation fault|core dumped|Fatal Python error|Traceback \(most recent call last\)', w['console']):
                raise RuntimeError('Native worker emitted fatal/error text')
        return {'recordings': recording_checks, 'video_decodes': [{'path': str(p), **decode(p)} for p in videos],
                'mandatory_native_key_transitions': True, 'actual_policy_window_and_tty': True,
                'quality_verified': False, 'obstacle_course_completion_verified': False}

    def close(self):
        try:
            if self.display:
                self.display.release_all()
        except BaseException as error:
            self.errors.append('key release: ' + str(error))
        for role in ('inference', 'simulator'):
            if role not in self.workers:
                continue
            w = self.workers[role]
            try:
                if w['group'] is None:
                    raise RuntimeError('No trustworthy spawn birth; refuse unknown process-group signal')
                final = cleanup_group(self.module, w['process'], w['group'], self.cleanup, .2)
                if not final['ownership_verified'] or final['live_members'] != []:
                    raise RuntimeError('Group ownership/empty observation failed')
            except BaseException as error:
                self.errors.append(role + ' cleanup: ' + str(error))
            finally:
                for item in ('raw', 'text'):
                    try:
                        if w[item]:
                            w[item].close()
                    except BaseException as error:
                        self.errors.append(role + ' log close: ' + str(error))
                try:
                    os.close(w['master'])
                except OSError:
                    pass
        try:
            self.persist()
        finally:
            try:
                if self.display:
                    self.display.close()
            finally:
                if self.root:
                    self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    old = dict(plan); recorded = old.pop('plan_sha256')
    if identity(old) != recorded or not Path('/.dockerenv').exists() or os.environ.get('PHP_GUI_TOKEN') != plan['token']:
        raise ValueError('Explicit isolated Docker execution identity differs')
    verify_files('/data/cohort', plan['files'])
    output = Path('/outputs')
    if (output / 'summary.json').exists():
        raise ValueError('Never repeat or overwrite a GUI attempt')
    report = {'schema_version': 1, 'status': 'running', 'plan_sha256': recorded, 'started_unix': time.time(),
              'scope': 'One native keyboard/GUI interface test on plane; not terrain skill acceptance'}
    write(output / 'summary.json', report)
    session = None
    try:
        with Path('/tmp/php-parkour-sim2sim-matrix.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            session = Session(plan, output)
            try:
                session.initialize()
                report.update(session.run(), status='completed')
            finally:
                session.close()
            if session.cleanup or session.errors:
                raise RuntimeError('Non-normal cleanup or receipt errors remain: ' + str(session.errors))
    except BaseException as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
    finally:
        report['finished_unix'] = time.time()
        if session:
            report['cleanup_actions'], report['cleanup_errors'] = session.cleanup, session.errors
        write(output / 'summary.json', report)
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
