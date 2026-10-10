"""CPU diagnosis using native MotionCommand + BadTracking and retained real motion.

Only mathematical state is emulated. No physics, model inference or GPU is run.
The alignment-only reference is compiled from the upstream step's actual AST.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path('/workspace/php_parkour')
sys.path.insert(0, str(ROOT))
from holosoma.managers.command.terms import wbt
from holosoma.managers.termination.terms.wbt import BadTracking
from wbt_training.config_values.terrain import g1_29dof_wbt_terrain_termination

CASE = ROOT / 'outputs/research/source-coverage-cpu-final/teacher/cases/teacher-e0-000-fef9f7ce29d0'
quality = json.loads((CASE / 'quality.json').read_text())
motion_path = CASE / 'runtime-assets/motion.npz'

tree = ast.parse(textwrap.dedent(inspect.getsource(wbt.MotionCommand.step)))
function = tree.body[0]
start = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'use_root')
end = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
           and isinstance(node.targets[0], ast.Attribute) and node.targets[0].attr == 'body_pos_relative_w')
alignment = ast.FunctionDef(name='alignment_only', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self')],
    vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
    body=function.body[start:end+1], decorator_list=[])
module = ast.fix_missing_locations(ast.Module(body=[alignment], type_ignores=[]))
namespace = dict(vars(wbt))
exec(compile(module, '<upstream MotionCommand.step alignment AST>', 'exec'), namespace)
alignment_only = namespace['alignment_only']

term_cfg = g1_29dof_wbt_terrain_termination.terms['bad_tracking']
tracked_names = term_cfg.params['body_names_to_track']
term = BadTracking(term_cfg, SimpleNamespace(device='cpu'))

with np.load(motion_path, allow_pickle=False) as archive:
    arrays = {key: archive[key].copy() for key in archive.files}
names = arrays['body_names'].tolist()
tracked = torch.tensor([names.index(name) for name in tracked_names])
ref_index, root_index = names.index('torso_link'), names.index('pelvis')


def make_command(xy_shift=(0., 0.)):
    cmd = object.__new__(wbt.MotionCommand)
    body = torch.tensor(arrays['body_pos_w'], dtype=torch.float32)
    body[:, :, :2] += torch.tensor(xy_shift)
    quats = torch.tensor(arrays['body_quat_w'], dtype=torch.float32)
    roots = torch.zeros(1,13)
    roots[:, :3], roots[:, 3:7] = body[0,root_index], quats[0,root_index]
    cmd._env = SimpleNamespace(episode_length_buf=torch.zeros(1,dtype=torch.long), is_evaluating=True,
        simulator=SimpleNamespace(scene=SimpleNamespace(env_origins=torch.zeros(1,3)),
            robot_root_states=roots, _rigid_body_pos=body[0:1].clone(), _rigid_body_rot=quats[0:1].clone()))
    cmd.num_envs, cmd.device = 1, 'cpu'
    cmd.motion_cfg = SimpleNamespace(body_names_to_track=tracked_names, use_adaptive_timesteps_sampler=False,
        freeze_at_timestep_zero_prob=0., resample_on_motion_end=True)
    cmd.motion = SimpleNamespace(_body_pos_w=body, _body_quat_w=quats,
        motion_ends=torch.tensor(arrays['motion_ends']), time_step_total=len(body), motion_start_idx=torch.tensor([0]))
    cmd._tracked_body_indexes_in_motion, cmd.tracked_body_indexes = tracked, tracked
    cmd._ref_body_index_in_motion, cmd._root_body_index_in_motion = ref_index, root_index
    cmd.ref_body_index = ref_index
    cmd.init_buffers()
    return cmd


def error(cmd):
    per_body = torch.linalg.vector_norm(cmd.body_pos_relative_w-cmd.robot_body_pos_w, dim=-1)
    return {'mean_body_error_m': per_body.mean().item(), 'max_body_error_m': per_body.max().item(),
            'bad_motion_body_pos': term.bad_motion_body_pos(cmd).item()}


cases=[]
for shift in ((0.,0.), (10.,-20.), (-100.,100.)):
    cmd=make_command(shift)
    before=error(cmd)
    time_before=cmd.time_steps.clone()
    motion_ids_before=cmd.motion_ids.clone()
    boundary_before=cmd.motion_end_reset.clone()
    rng_before=torch.get_rng_state().clone()
    alignment_only(cmd)
    after=error(cmd)
    assert torch.equal(time_before, cmd.time_steps) and torch.equal(motion_ids_before,cmd.motion_ids)
    assert torch.equal(boundary_before, cmd.motion_end_reset) and torch.equal(rng_before,torch.get_rng_state())
    assert before['bad_motion_body_pos'] and not after['bad_motion_body_pos']
    cases.append({'extra_world_xy_shift':shift,'before_zero_cache':before,'after_native_alignment':after,
                  'frame_before':time_before.item(),'frame_after':cmd.time_steps.item(),
                  'motion_ids_unchanged':True,'motion_end_reset_unchanged':True,'torch_rng_unchanged':True})

cmd=make_command()
cmd.step()  # Native control naturally advances frame0 to frame1; no rewind is used.
position, quaternion = cmd.body_pos_relative_w.clone(), cmd.body_quat_relative_w.clone()
native_frame=cmd.time_steps.clone()
cmd.body_pos_relative_w.zero_()
cmd.body_quat_relative_w.zero_()
alignment_only(cmd)  # Rebuild at current frame1, without touching the clock.
assert torch.equal(position,cmd.body_pos_relative_w) and torch.equal(quaternion,cmd.body_quat_relative_w)
assert torch.equal(native_frame,cmd.time_steps)

source=Path(inspect.getsourcefile(wbt.MotionCommand))
result={'schema_version':1,'scope':'CPU mathematical diagnosis with actual native classes and retained real source; not physics or policy success',
    'gpu_used':False,'native_source':{'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'alignment_lines':[1063,1088]},'actual_runtime_motion':{'path':str(motion_path),'sha256':hashlib.sha256(motion_path.read_bytes()).hexdigest()},
    'real_warmup_body_errors_m':[row['metrics']['motion/error_body_pos'] for key in ('initialization_events','attempt_warmup_events') for row in quality[key]],
    'cpu_cases':cases,'native_step_parity':{'position_bitwise_equal':True,'quaternion_bitwise_equal':True,
        'naturally_advanced_native_frame':native_frame.item(),'alignment_only_frame_unchanged':True},
    'minimal_eval_hook':'In SourceCoverageProbe.step, only initialization_warmup/attempt_warmup, before original_step after native reset_all root/DOF writes, recompute current-frame alignment caches. Never command.step, resample, alter time_steps, RNG, source, termination or training.'}
print(json.dumps(result,indent=2))
