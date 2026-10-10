# Singleton warmup failure: relative-target cache diagnosis

The first real teacher singleton run executed normally but terminated both zero-action warmups before applying a policy action. The source data and root reset were coherent. The large body error comes from an existing native `reset_all` cache-initialization ordering defect, rather than evidence that the checkpoint cannot perform this source clip. No production code, training process, cloud source, termination threshold or source motion was changed by this review.

## Actual evidence

`source-coverage-cpu-final/teacher/cases/teacher-e0-000-fef9f7ce29d0/quality.json` retained body errors of **2.557042 m** (initialization A) and **2.581872 m** (first-attempt warmup B), whereas reference-anchor errors were 0.031218 m and 0.022718 m. The preprocessed source has constant XY translation `[0.01484278, 2.48135757]`; joint fields are unchanged. The runtime motion hash is `3c5f4991817c4462a66e25d468e5b093cc56751b724d96215dc9916b52bcb0aa`.

## Source chain

Let `H` denote `thirdparty/holosoma/src/holosoma/holosoma/`.

1. `H/envs/wbt/wbt_manager.py:93–97`: every `WholeBodyTrackingManager.reset_all()` calls `motion_command.init_buffers()` before the base reset.
2. `H/managers/command/terms/wbt.py:1270–1284`: `init_buffers` creates all-zero `body_pos_relative_w`, an unrelated initial `body_quat_relative_w`, zero time steps and boundary flags. The caches are not rebuilt in `reset`.
3. `H/envs/base_task/base_task.py:230–241`: native `reset_all` resets the robot, writes root/DOF states into the simulator, then performs a zero-action environment step.
4. `H/envs/base_task/base_task.py:481–500`: for Isaac WBT, termination/reward/logging occur before the later command-manager step. `H/managers/termination/terms/wbt.py:96–102` computes full-3D end-effector errors against the still-zero relative-position cache, and `H/managers/command/terms/wbt.py:1296–1298` logs its mean body error. The target is near world zero while the robot has been correctly initialized around Y=2.48 m.
5. `H/managers/command/terms/wbt.py:1063–1088`: only the later native command step recomputes current relative body position/quaternion targets using the motion reference, robot reference/root pose, relative yaw and height offset.

The unchanged root fields in `joint_pos` do **not** cause this discrepancy: native `MotionCommand.reset` initializes robot root position from translated `motion._body_pos_w` plus environment origin (`H/managers/command/terms/wbt.py:857–868`). It obtains the 29 actuated joints separately through `get_joint_pos`.

This is not a singleton-only bug. World translation increases the error from a zero target. The prior 64-environment rollout metrics did not count the two warmups: `scripts/research/eval_quality.py:48–71` attaches its capture in `on_pre_evaluate_policy` after A, leaves `record_step=False`, and `:104–105` enables counting only when the native actor-state has a policy `step`. By the first counted policy step, the preceding native command update has rebuilt the target caches. Its small body error therefore does not contradict this diagnosis.

## CPU proof with native classes and the actual retained motion

`warmup-relative-cache-review.py` uses the real `MotionCommand.init_buffers`, `MotionCommand.step`, `BadTracking` and the actual retained 920-frame motion. It constructs mathematical robot/reference tensors, not a physical simulator. The alignment-only reference is compiled from the **actual upstream AST statements** starting at `use_root` and ending at `body_pos_relative_w`; it shares the native module's quaternion functions. It does not approximate the formula or call a step-and-rewind workaround.

| Extra world XY shift | Zero-cache mean body error | After native alignment | Native body-position termination |
| --- | ---: | ---: | --- |
| `[0, 0]` | 2.586534 m | 0.001970 m | true → false |
| `[10, -20]` | 20.188177 m | 0.001970 m | true → false |
| `[-100, 100]` | 143.184464 m | 0.001968 m | true → false |

In all three cases, reference frame remains 0 and motion IDs, boundary flags and Torch RNG state remain unchanged. A separate control invokes the native `step` naturally from frame 0 to 1, saves its targets, clears only those target caches, then rebuilds them at current frame 1 through the extracted alignment. Positions and quaternions are bitwise equal to the native result; the reference clock remains at 1. Evidence and exact source/motion hashes are in `warmup-relative-cache-review.json`; stderr is separately retained.

## Minimal local evaluation repair

Use an evaluation-only helper in `SourceCoverageProbe.step`, **only** for `initialization_warmup` and `attempt_warmup`, immediately before `original_step`. At this point the native `reset_all` has written the requested root/DOF states and the current reference frame is still 0. Recompute both relative-position and relative-quaternion caches with the native `MotionCommand.step:1063–1088` alignment formula, including its `episode_length==0 | motion_end_reset` root fallback. Then run the original zero-action physics, termination, reward and reset path unchanged.

Record that this repair was active, the upstream formula's source SHA/lines, reference frame/IDs/boundary before and after, RNG before and after, and cache changes for both warmups. Assert those clocks/IDs/flags/RNG do not change. Do not call `command.step`, resample, alter `time_steps`, modify source bytes, bypass failed termination, suppress warmups, or change the frozen training source. Preserve the failed pre-repair GPU result and prepare fresh plans/output paths after the helper fingerprint changes.

This repair makes the first-attempt measurement meaningful; it does not guarantee a successful warmup or policy rollout. Initial pose noise, physical integration and the unchanged BadTracking thresholds can still produce legitimate failure, which the harness must retain. A fresh real Isaac run is required to establish the repaired measurement's actual result.
