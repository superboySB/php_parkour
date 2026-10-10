"""Pure-stdlib validation of observations; never writes native state."""
from __future__ import annotations
import math


LOW = {'w': 1, 's': 11, 'a': 2, 'd': 4, 'q': 3, 'e': 5}
HIGH = {'w': 6, 's': 11, 'a': 7, 'd': 9, 'q': 8, 'e': 10}
MIN_LABEL_TICKS = 10


def validate_state(state):
    for key in ('time', 'physics_dt'):
        if not isinstance(state[key], (int, float)) or not math.isfinite(state[key]):
            raise ValueError('Nonfinite physical state: ' + key)
    for key, size in (('qpos', state['nq']), ('qvel', state['nv']), ('ctrl', state['nu']), ('model_qpos0', state['nq'])):
        if (not isinstance(size, int) or size <= 0 or len(state[key]) != size
                or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in state[key])):
            raise ValueError('Invalid complete physical state: ' + key)
    if state['physics_dt'] <= 0 or state['time'] < 0:
        raise ValueError('Invalid actual simulation clock')


def onehot_matches(policy, code):
    return (policy.get('active_velocity_command_idx') == code
            and policy.get('velocity_command') == [[float(i == code) for i in range(15)]])


def validate_reset(observation, request_unix, previous_reset_count, observed_reset_count):
    before, after = observation['before'], observation['after']
    validate_state(before); validate_state(after)
    if observation['scope'] not in ('within_original_render', 'between_render_samples'):
        raise ValueError('Unknown read-only reset observation scope')
    if (observation['unix'] < request_unix or observed_reset_count != previous_reset_count + 1
            or any(before[k] != after[k] for k in ('nq', 'nv', 'nu', 'nkey', 'model_qpos0', 'physics_dt'))
            or before['time'] < 1.0 or after['time'] >= before['time']
            or after['time'] > .1):
        raise ValueError('No single new actual Backspace clock reset after genuine window input')
    qpos_delta = max(abs(a-b) for a,b in zip(before['qpos'], after['qpos']))
    if qpos_delta <= 1e-9:
        raise ValueError('Backspace clock changed without an observed qpos change')
    return {'actual_clock_drop': before['time'] - after['time'], 'qpos_max_abs_change': qpos_delta,
            'qpos0_max_abs_error': max(abs(a-b) for a,b in zip(after['qpos'], after['model_qpos0'])),
            'observed_time_after': after['time'], 'observation_scope': observation['scope'],
            'scope': 'Observed MuJoCo physical data reset only; policy history/gantry/SDK are not claimed reset'}
