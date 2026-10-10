"""Diagnostic method observers. Every original is called once, with unchanged args.

Only the fresh isolated snapshot uses these entry shims. The canonical checkout,
actor, SDK implementation, input sources, key mappings and recorder stay intact.
"""
from __future__ import annotations
import atexit
import functools
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time
import traceback

from common import load, sha, write

REPORT = {}
LOCK = threading.RLock()
OUT = None


def event(kind, **values):
    record = {'kind': kind, 'unix': time.time(), 'monotonic': time.monotonic(), **values}
    with LOCK:
        REPORT['last_event'] = record
        with (OUT / 'observations.jsonl').open('a') as stream:
            stream.write(json.dumps(record, allow_nan=False) + '\n')
        write(OUT / 'state.json', REPORT)


def policy_state(policy):
    result = {key: getattr(policy, key, None) for key in (
        'use_policy_action', 'get_ready_state', '_stiff_hold_active', '_damping_mode_active',
        '_recording', '_record_toggle_request', 'speed_mode', 'active_velocity_command_idx')}
    commands = getattr(policy, 'velocity_command', None)
    result['velocity_command'] = commands.tolist() if commands is not None else None
    result['recorded_frames'] = len(getattr(policy, '_record_qpos', []))
    return result


def install_inference():
    import numpy as np
    from holosoma_inference.policies.base import BasePolicy
    from holosoma_inference.policies.depth_distillation import DepthDistillationPolicy as Policy
    from holosoma_inference.sdk.unitree.unitree_interface import UnitreeInterface
    from holosoma_inference.sensors.depth_shm import DepthShmSensor

    original_init, original_dispatch = Policy.__init__, Policy._dispatch_command
    original_service = Policy._service_recording
    original_sent, original_send = BasePolicy._on_command_sent, UnitreeInterface.send_low_command
    original_liveness = DepthShmSensor.liveness

    @functools.wraps(original_liveness)
    def liveness(self):
        # Observe the native poll's return once. Never add a heartbeat poll,
        # consume a message, reattach SHM or modify the returned status.
        result = original_liveness(self)
        if result is not None and result.checked:
            with LOCK:
                before = REPORT.get('depth_heartbeat', {})
                advances = before.get('advances', 0) + int(before.get('seq') is not None and result.seq > before['seq'])
                REPORT['depth_heartbeat'] = {'seq': result.seq, 'advances': advances,
                    'state': result.state, 'stale_s': result.stale_s, 'restarted': result.restarted}
        return result

    @functools.wraps(original_init)
    def initialize(self, *args, **kwargs):
        result = original_init(self, *args, **kwargs)
        with LOCK:
            REPORT['policy'] = policy_state(self)
            event('policy_initialized', state=REPORT['policy'])
        return result

    @functools.wraps(original_dispatch)
    def dispatch(self, command):
        before = policy_state(self)
        result = original_dispatch(self, command)
        with LOCK:
            REPORT['policy'] = policy_state(self)
            event('native_dispatch', command=command.name, before=before, after=REPORT['policy'])
        return result

    @functools.wraps(original_service)
    def recording_service(self, *args, **kwargs):
        before = (self._recording, self._record_toggle_request)
        result = original_service(self, *args, **kwargs)
        with LOCK:
            REPORT['policy'] = policy_state(self)
            if before != (self._recording, self._record_toggle_request):
                event('native_recording_service', state=REPORT['policy'])
        return result

    @functools.wraps(original_sent)
    def sent(self, command, state):
        result = original_sent(self, command, state)
        with LOCK:
            count = REPORT.get('control_ticks', 0) + 1
            REPORT['control_ticks'] = count
            # Read the same native command buffer used by the unchanged recorder.
            label = policy_state(self)['velocity_command']
            record_control_label(label, getattr(self, 'active_velocity_command_idx', None))
            if count % 5 == 0:
                if not np.isfinite(command).all() or not np.isfinite(state).all():
                    raise ValueError('Actual native command/state became nonfinite')
                REPORT['policy'] = policy_state(self)
                event('native_control_sample', state=REPORT['policy'], command=command.tolist(),
                      low_state=state.tolist(), world_root_is_placeholder=True)
        return result

    @functools.wraps(original_send)
    def send(self, *args, **kwargs):
        result = original_send(self, *args, **kwargs)
        with LOCK:
            count = REPORT.get('sdk_send_calls', 0) + 1
            REPORT['sdk_send_calls'] = count
            if count % 5 == 0:
                kp, kd = kwargs.get('kp_override'), kwargs.get('kd_override')
                kp = np.asarray(self.robot_config.motor_kp if kp is None else kp) * self._kp_level
                kd = np.asarray(self.robot_config.motor_kd if kd is None else kd) * self._kd_level
                REPORT['last_python_sender_gains'] = {'kp': kp.tolist(), 'kd': kd.tolist(),
                    'scope': 'Observed original Python send arguments/scale after original call; not measured motor torque or C++ delivery acknowledgement'}
                event('python_sender_gain_sample', **REPORT['last_python_sender_gains'])
        return result

    Policy.__init__, Policy._dispatch_command, Policy._service_recording = initialize, dispatch, recording_service
    BasePolicy._on_command_sent, UnitreeInterface.send_low_command = sent, send
    DepthShmSensor.liveness = liveness


def record_control_label(label, active):
    if (not isinstance(label, list) or len(label) != 1 or len(label[0]) != 15
            or any(v not in (0.0, 1.0) for v in label[0]) or sum(label[0]) != 1.0
            or active != label[0].index(1.0)):
        raise ValueError('Actual native velocity command is not the matching15-wide one-hot')
    counts = REPORT.setdefault('velocity_command_tick_counts', {str(i): 0 for i in range(15)})
    counts[str(active)] += 1


def simulator_state(sim):
    # Read Classic MuJoCo data directly. Never refresh/cache/write native state.
    state = [*sim.root_data.qpos[:7].tolist(), *sim.root_data.qvel[:6].tolist()]
    result = {'root_state': state, 'root_layout': 'MuJoCo XYZ+wxyz+linear/angular qvel',
              'gantry_enabled': bool(sim.virtual_gantry.enabled), 'gantry_length': float(sim.virtual_gantry.length),
              'time': float(sim.root_data.time), 'qpos': sim.root_data.qpos.tolist(),
              'qvel': sim.root_data.qvel.tolist(), 'ctrl': sim.root_data.ctrl.tolist(),
              'model_qpos0': sim.root_model.qpos0.tolist(), 'nq': int(sim.root_model.nq),
              'nv': int(sim.root_model.nv), 'nu': int(sim.root_model.nu),
              'nkey': int(sim.root_model.nkey), 'physics_dt': float(sim.root_model.opt.timestep),
              'camera_tracking': bool(sim.simulator_config.viewer.enable_tracking),
              'show_text_overlay': bool(sim.show_text_overlay)}
    # stdlib validation keeps this observer usable in isolated CPU fixtures.
    from reset_checks import validate_state
    validate_state(result)
    return result


def record_render(before, after):
    previous = REPORT.get('last_render_transition')
    transition = {'before': before, 'after': after, 'physics_ticks': REPORT.get('physics_ticks', 0),
                  'render_index': REPORT.get('render_calls', 0) + 1}
    REPORT['render_calls'] = transition['render_index']
    candidates = [('within_original_render', before, after)]
    if previous is not None:
        candidates.append(('between_render_samples', previous['after'], before))
    for scope, left, right in candidates:
        if right['time'] < left['time']:
            value = {'scope': scope, 'before': left, 'after': right,
                     'physics_ticks': transition['physics_ticks'], 'render_index': transition['render_index'],
                     'unix': time.time()}
            REPORT.setdefault('physics_clock_drop_observations', []).append(value)
            event('actual_physics_clock_drop', **value)
    REPORT['last_render_transition'] = transition
    REPORT['simulation'] = after
    event('original_render_readonly_before_after', **transition)


def install_simulator():
    import numpy as np
    from holosoma.simulator.mujoco.mujoco import MuJoCo
    from holosoma.utils.sim_utils import DirectSimulation
    original_init, original_key, original_step = DirectSimulation.initialize, MuJoCo._key_callback, MuJoCo.simulate_at_each_physics_step
    original_render = MuJoCo.render

    @functools.wraps(original_render)
    def render(self, *args, **kwargs):
        before = simulator_state(self)
        result = original_render(self, *args, **kwargs)
        after = simulator_state(self)
        with LOCK:
            record_render(before, after)
        return result

    @functools.wraps(original_init)
    def initialize(self):
        result = original_init(self)
        with LOCK:
            REPORT['simulation'] = simulator_state(self.simulator)
            REPORT['ready'] = True
            event('simulator_initialized', state=REPORT['simulation'])
        return result

    @functools.wraps(original_key)
    def key(self, keycode):
        before = simulator_state(self)
        result = original_key(self, keycode)
        with LOCK:
            REPORT['simulation'] = simulator_state(self)
            event('native_window_key_callback', keycode=keycode, before=before, after=REPORT['simulation'])
        return result

    @functools.wraps(original_step)
    def step(self):
        result = original_step(self)
        with LOCK:
            count = REPORT.get('physics_ticks', 0) + 1
            REPORT['physics_ticks'] = count
            if count % 25 == 0:
                REPORT['simulation'] = simulator_state(self)
                if not np.isfinite(REPORT['simulation']['root_state']).all():
                    raise ValueError('Actual simulator root state became nonfinite')
                event('simulator_state_sample', state=REPORT['simulation'])
        return result

    DirectSimulation.initialize, MuJoCo._key_callback, MuJoCo.simulate_at_each_physics_step = initialize, key, step
    MuJoCo.render = render


def launch(role, original, expected_sha):
    global OUT
    output = Path(os.environ['PHP_GUI_OUTPUT'])
    OUT = output / role
    OUT.mkdir(exist_ok=True)
    if (OUT / 'process-entry.json').exists() or sha(original) != expected_sha:
        raise ValueError('Native original changed or role already attempted')
    module = load(Path('/workspace/php_parkour/scripts/research/sim2sim.py'), 'gui_observer_ownership')
    REPORT.update(schema_version=1, role=role, process=module.process_identity(os.getpid()),
                  argv=list(sys.argv), original_source={'path': str(original), 'sha256': expected_sha},
                  tty={'stdin_isatty': sys.stdin.isatty(), 'ttyname': os.ttyname(0) if sys.stdin.isatty() else None,
                       'foreground_pgid': os.tcgetpgrp(0) if sys.stdin.isatty() else None},
                  lifecycle='entry', observer_sha256=sha(Path(__file__)))
    write(OUT / 'process-entry.json', REPORT)
    atexit.register(lambda: event('python_atexit'))
    try:
        if role == 'simulator':
            install_simulator()
        elif role == 'inference':
            install_inference()
        else:
            raise ValueError('Unknown role')
        event('observers_installed')
        if role == 'inference':
            # Guarded canonical bootstrap original is imported unchanged; main's
            # return value was ignored by its original __main__ and remains so.
            original_module = load(original, 'gui_canonical_keyboard_bootstrap')
            original_module.main()
        else:
            runpy.run_path(str(original), run_name='__main__')
        REPORT['lifecycle'] = 'main_returned'
        event('original_main_returned')
    except BaseException as error:
        REPORT['lifecycle'] = 'main_raised'
        REPORT['exception_type'] = type(error).__name__
        if isinstance(error, SystemExit):
            REPORT['system_exit_code'] = error.code
        event('original_main_raised', exception_type=type(error).__name__, detail=str(error), traceback=traceback.format_exc())
        raise
