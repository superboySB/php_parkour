#!/usr/bin/env python3
"""Isolated native evaluation of one source clip, stopping at its first event.

Used by eval_source_coverage.py. This module changes neither the native sampler
nor termination predicates. Run only inside the research Docker environment.
"""
from __future__ import annotations

import argparse
import ast
import functools
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import textwrap
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.eval_quality import METRICS, atomic_json, sha256


def fingerprint(path):
    path = Path(path)
    return {"path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size}


def retain_file(source, target):
    """Retain identical bytes with host-readable permissions, including 0600 temp OBJ."""
    shutil.copyfile(source, target)
    Path(target).chmod(0o644)


@functools.lru_cache(maxsize=1)
def native_alignment_formula():
    """Compile only the native current-frame relative-target cache assignments.

    Native WBT reset_all clears these buffers, then tests termination before
    command.step refreshes them. The isolated evaluator repairs that cache
    lifecycle for its two zero-action warmups, without advancing the command.
    """
    from holosoma.managers.command.terms import wbt
    source, first_line = inspect.getsourcelines(wbt.MotionCommand.step)
    tree = ast.parse(textwrap.dedent("".join(source)))
    statements = tree.body[0].body
    start = next(i for i, node in enumerate(statements) if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "use_root")
    end = next(i for i, node in enumerate(statements) if isinstance(node, ast.Assign)
               and isinstance(node.targets[0], ast.Attribute) and node.targets[0].attr == "body_pos_relative_w")
    selected = statements[start:end + 1]
    # Fail closed if upstream moves effects into this formerly pure cache block.
    writes = {target.attr for node in selected if isinstance(node, ast.Assign)
              for target in node.targets if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"}
    if writes != {"body_pos_relative_w", "body_quat_relative_w"}:
        raise ValueError("Native alignment block no longer only updates the two relative-target caches")
    function = ast.parse("def alignment_only(self):\n    pass\n").body[0]
    function.body = selected
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = dict(vars(wbt))
    exec(compile(module, "<native MotionCommand.step alignment-only AST>", "exec"), namespace)
    metadata = {"enabled": True, "scope": "isolated evaluation warmups only; current-frame cache refresh, no command.step",
                "native_source": fingerprint(inspect.getsourcefile(wbt.MotionCommand)),
                "native_formula_lines": [first_line + selected[0].lineno - 1, first_line + selected[-1].end_lineno - 1],
                "formula_ast_sha256": hashlib.sha256(ast.dump(module, include_attributes=False).encode()).hexdigest(),
                "native_cache_bug": "WholeBodyTrackingManager.reset_all init_buffers clears targets; termination/logging precede command.step target refresh"}
    return namespace["alignment_only"], metadata


def refresh_relative_targets(command):
    """Refresh exactly the upstream cache formula and prove clocks/RNG unchanged."""
    import pickle
    import random
    import numpy as np
    import torch
    formula, metadata = native_alignment_formula()
    def clocks():
        return {"time_steps": command.time_steps.tolist(), "motion_ids": command.motion_ids.tolist(),
                "motion_end_reset": command.motion_end_reset.tolist(),
                "episode_length_buf": command._env.episode_length_buf.tolist()}
    def rng():
        states = {"python": pickle.dumps(random.getstate()), "numpy": pickle.dumps(np.random.get_state()),
                  "torch_cpu": torch.get_rng_state().numpy().tobytes()}
        if torch.cuda.is_initialized():
            states.update({f"torch_cuda_{index}": state.cpu().numpy().tobytes() for index, state in enumerate(torch.cuda.get_rng_state_all())})
        return {key: hashlib.sha256(value).hexdigest() for key, value in states.items()}
    def caches():
        return {name: getattr(command, name).detach().cpu().tolist() for name in ("body_pos_relative_w", "body_quat_relative_w")}
    clock_before, rng_before, cache_before = clocks(), rng(), caches()
    with torch.no_grad():
        formula(command)
    clock_after, rng_after, cache_after = clocks(), rng(), caches()
    if clock_before != clock_after or rng_before != rng_after:
        raise RuntimeError("Alignment-only refresh changed the native command clock or RNG")
    return {"formula": metadata, "clock_before": clock_before, "clock_after": clock_after,
            "rng_sha256_before": rng_before, "rng_sha256_after": rng_after,
            "clock_unchanged": True, "rng_unchanged": True,
            "cache_before": cache_before, "cache_after": cache_after}


def verify_preprocessed_source(case, motion_file):
    """Bind the actual reference table to the retained source, allowing XY layout translation."""
    import numpy as np
    record = case["source"]
    with np.load(record["source_motion"], allow_pickle=False) as source, np.load(motion_file, allow_pickle=False) as actual:
        unchanged = ("fps", "joint_pos", "joint_vel", "body_quat_w", "body_lin_vel_w", "body_ang_vel_w", "vel_cmd", "joint_names", "body_names")
        for key in unchanged:
            if not np.array_equal(source[key], actual[key]):
                raise ValueError(f"Preprocessed {key} is not the selected source's one-variant table")
        before, after = source["body_pos_w"], actual["body_pos_w"]
        if before.shape != after.shape:
            raise ValueError("Preprocessed body positions changed source length/body order")
        translation = after[0, 0].astype(float) - before[0, 0].astype(float)
        if abs(translation[2]) > 1e-5 or not np.allclose(after, before + translation, rtol=0, atol=1e-5):
            raise ValueError("Source body positions changed beyond the native constant XY layout translation")
        if np.flatnonzero(actual["motion_ends"]).tolist() != [record["frames"] - 1] or set(actual["motion_idxs"].tolist()) != {0}:
            raise ValueError("Preprocessed source boundary or singleton expert ID is inconsistent")
    return {"status": "matched_selected_source", "unchanged_fields": list(unchanged),
            "body_position_translation_xyz_m": translation.tolist(), "translation_tolerance_m": 1e-5}


class StopAttempt(Exception):
    """The requested first attempt ended; this is not an execution failure."""


def guarded_evaluate(algo, native_evaluate, max_eval_steps):
    """Use the actual native loop and finalize its callbacks exactly once."""
    try:
        return native_evaluate(algo, max_eval_steps=max_eval_steps)
    except StopAttempt:
        return algo._post_evaluate_policy()
    except BaseException as error:
        # Native loops have no finally around callbacks. Restore our hooks and
        # retain the partial attempt, while allowing the original error to fail.
        for callback in algo.eval_callbacks:
            if isinstance(callback, SourceCoverageProbe) and not callback.finalized:
                callback.execution_error = f"{type(error).__name__}: {error}"
                try:
                    callback.on_post_evaluate_policy()
                except BaseException as final_error:
                    print(f"Coverage finalization also failed: {final_error}", file=sys.stderr, flush=True)
                    callback.restore()
        raise


class SourceCoverageProbe:
    """Read native pre-reset flags and distinguish both reset_all warmups."""

    def __init__(self, config, training_loop):
        import numpy as np
        self.np, self.config, self.loop = np, config, training_loop
        self.case = config["case"]
        self.directory = Path(self.case["output"])
        self.env = training_loop._unwrap_env() if hasattr(training_loop, "_unwrap_env") else training_loop.env
        self.cmd = self.env.command_manager.get_state("motion_command")
        self.started, self.started_unix = time.monotonic(), time.time()
        self.phase, self.rows, self.pending = "initialization_warmup", [], None
        self.refresh_events = []
        self.stop_reason = self.execution_error = None
        self.finalized, self.in_step, self.policy_steps = False, False, 0
        self.original_step, self.original_log = self.env.step, self.env._update_log_dict
        self.actual = self.validate_singleton()
        (self.directory / "trajectory.jsonl").touch(exist_ok=False)
        self.env.step, self.env._update_log_dict = self.step, self.capture_log

    def array(self, tensor):
        return tensor.detach().cpu().numpy().copy()

    def reference(self):
        frame = int(self.cmd.time_steps[0].item())
        return {"reference_frame": frame, "loader_id": int(self.cmd.motion_ids[0].item()),
                "native_expert_id": int(self.cmd.motion.motion_idxs[frame].item()),
                "reference_is_boundary": bool(self.cmd.motion.motion_ends[frame].item())}

    def validate_singleton(self):
        record, env, cmd = self.case["source"], self.env, self.cmd
        ends = self.array(cmd.motion.motion_ends).nonzero()[0].tolist()
        experts = self.array(cmd.motion.motion_idxs).tolist()
        balancing = getattr(cmd, "_expert_balancing_active", lambda: False)()
        if (env.num_envs != 1 or cmd.motion.num_motions != 1 or cmd.motion.time_step_total != record["frames"]
                or ends != [record["frames"] - 1] or set(experts) != {0} or balancing):
            raise ValueError("Actual native loader is not the requested one-source, one-variant singleton")
        if abs(env.dt * record["fps"] - 1) > 1e-6:
            raise ValueError("Control dt does not match source FPS; harness does not resample time")
        motion_cfg = cmd.motion_cfg
        if (motion_cfg.freeze_at_timestep_zero_prob != 0 or not motion_cfg.resample_on_motion_end
                or motion_cfg.enable_default_pose_prepend or motion_cfg.enable_default_pose_append
                or motion_cfg.default_pose_transition_strategy != "none"):
            raise ValueError("Motion timing was modified; source-frame coverage is not directly mappable")
        actual = {"num_envs": env.num_envs, "loader_num_motions": cmd.motion.num_motions,
                  "frames": cmd.motion.time_step_total, "boundary_indices_inclusive": ends,
                  "native_expert_ids": sorted(set(experts)), "expert_balancing_active": bool(balancing),
                  "freeze_at_timestep_zero_prob": motion_cfg.freeze_at_timestep_zero_prob,
                  "resample_on_motion_end": motion_cfg.resample_on_motion_end,
                  "control_dt_seconds": env.dt, "source_fps": record["fps"],
                  "phase_zero_source": "native eval reset; no time_steps assignment by harness"}
        if "source_motion" in record:
            actual["source_table_verification"] = verify_preprocessed_source(self.case, motion_cfg.motion_file)
        native_config = Path(self.loop.log_dir) / "holosoma_config.yaml"
        if native_config.exists():
            import yaml
            contents = yaml.safe_load(native_config.read_text())
            terrain_obj = contents["terrain"]["terrain_term"]["obj_file_path"]
            assets = self.directory / "runtime-assets"
            assets.mkdir(exist_ok=True)
            for key, source, name in (("motion", motion_cfg.motion_file, "motion.npz"),
                                      ("terrain_obj", terrain_obj, "terrain.obj"),
                                      ("saved_eval_config", native_config, "holosoma_config.yaml")):
                target = assets / name
                retain_file(source, target)
                actual[key] = {"native_path": str(source), "retained": fingerprint(target)}
            actual["actual_preprocess_hook_kwargs"] = json.loads(contents["training"]["preprocess_hook_kwargs"])
        return actual

    def capture_log(self):
        self.original_log()
        if not self.in_step:
            return
        env, np = self.env, self.np
        metrics = {key: float(self.array(env.log_dict[key]).reshape(-1)[0]) for key in METRICS}
        self.pending = {"failed": bool(env.termination_manager.terminated[0].item()),
                        "timeout": bool(env.termination_manager.time_outs[0].item()),
                        "episode_length_steps_pre_reset": int(env.episode_length_buf[0].item()),
                        "metrics": {key: value if np.isfinite(value) else None for key, value in metrics.items()},
                        "finite_metrics": all(bool(np.isfinite(value)) for value in metrics.values())}
        root = self.array(env.simulator.robot_root_states[:])
        self.pending["finite_root_state"] = bool(np.isfinite(root).all())
        self.pending["root_height_m_pre_reset"] = float(root[0, 2]) if np.isfinite(root[0, 2]) else None

    def step(self, actor_state, *args, **kwargs):
        np = self.np
        before = self.reference()
        if self.phase.endswith("warmup") and before["reference_frame"] != 0:
            raise ValueError(f"Native {self.phase} did not initialize this source at phase zero: {before}")
        if self.phase.endswith("warmup"):
            refresh = refresh_relative_targets(self.cmd)
            refresh["phase"] = self.phase
            self.refresh_events.append(refresh)
            atomic_json(self.directory / "warmup-cache-refresh.json", {"enabled": True, "events": self.refresh_events})
        actions = self.array(actor_state["actions"])
        self.pending, self.in_step = None, True
        try:
            result = self.original_step(actor_state, *args, **kwargs)
        finally:
            self.in_step = False
        if self.pending is None:
            raise RuntimeError("Native env.step did not expose _update_log_dict before reset")
        row = {"sequence": len(self.rows), "phase": self.phase,
               "policy_step": int(actor_state["step"]) if self.phase == "policy" else None,
               **before, **self.pending, "post_reference_frame": int(self.cmd.time_steps[0].item()),
               "motion_end_reset": bool(self.cmd.motion_end_reset[0].item()),
               "finite_action": bool(np.isfinite(actions).all()),
               "max_abs_action": float(np.abs(actions).max()) if np.isfinite(actions).all() else None,
               "actions": actions.reshape(-1).tolist() if np.isfinite(actions).all() else None}
        self.rows.append(row)
        if self.phase == "policy":
            self.policy_steps += 1
        if self.phase != "initialization_warmup":
            # Termination flags belong to the old source frame. A command reset
            # after the same failure cannot turn that step into a completion.
            if row["failed"]:
                self.stop_reason = "failed_during_native_warmup" if self.phase != "policy" else "failed"
            elif row["timeout"]:
                self.stop_reason = "timeout_during_native_warmup" if self.phase != "policy" else "timeout"
            elif row["motion_end_reset"]:
                self.stop_reason = "native_boundary_during_warmup" if self.phase != "policy" else "native_boundary"
        # JSONL survives abnormal exit and labels initialization separately.
        with (self.directory / "trajectory.jsonl").open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
        if not row["finite_action"] or not row["finite_root_state"] or not row["finite_metrics"]:
            raise ValueError("Non-finite native action, state or tracking metric")
        return result

    def on_pre_evaluate_policy(self):
        if len(self.rows) != 1 or self.rows[0]["phase"] != "initialization_warmup":
            raise ValueError("Expected exactly one native initialization reset_all warmup before on_pre")
        self.phase = "attempt_warmup"

    def on_pre_eval_env_step(self, actor_state):
        if self.stop_reason:
            raise StopAttempt(self.stop_reason)
        if "step" in actor_state:
            self.phase = "policy"
            if self.reference()["reference_frame"] != self.policy_steps + 1:
                raise ValueError("Policy reference frames are not continuous from 1 after native phase-zero warmup")
        return actor_state

    def on_post_eval_env_step(self, actor_state):
        if self.stop_reason:
            raise StopAttempt(self.stop_reason)
        return actor_state

    def restore(self):
        self.env.step, self.env._update_log_dict = self.original_step, self.original_log

    def on_post_evaluate_policy(self):
        if self.finalized:
            raise RuntimeError("Coverage callback finalized more than once")
        self.finalized = True
        self.restore()
        recorder = getattr(self.env.simulator, "video_recorder", None)
        if recorder is not None:
            recorder.stop_recording()
        np = self.np
        policy = [row for row in self.rows if row["phase"] == "policy"]
        warmup = [row for row in self.rows if row["phase"] == "attempt_warmup"]
        initialization = [row for row in self.rows if row["phase"] == "initialization_warmup"]

        def summarize(rows):
            summary = {}
            for key, unit in METRICS.items():
                values = np.array([row["metrics"][key] for row in rows], dtype=float)
                finite = values[np.isfinite(values)]
                summary[key] = {"samples": len(values), "finite": bool(np.isfinite(values).all()) if len(values) else None,
                                "unit": unit, "mean": float(finite.mean()) if len(finite) else None,
                                "max": float(finite.max()) if len(finite) else None,
                                "p95": float(np.percentile(finite, 95)) if len(finite) else None}
            return summary

        frames = [row["reference_frame"] for row in policy]
        expected = list(range(1, self.case["source"]["frames"] - 1))
        consecutive = frames == expected[:len(frames)]
        reason = self.stop_reason or ("execution_error" if self.execution_error else "max_steps")
        boundary_complete = reason == "native_boundary" and consecutive and frames == expected
        videos = []
        for path in sorted((self.directory / "native").rglob("*.mp4")):
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
            duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0)) if probe.returncode == 0 else 0
            videos.append({**fingerprint(path), "duration_seconds": duration, "ffprobe_exit_code": probe.returncode,
                           "association": "native env0 episode recording; may include initialization/zero-action warmup, not a policy-only cut"})
        report = {"schema_version": 1, "status": "execution_failed" if self.execution_error else "completed",
                  "execution_error": self.execution_error, "quality_verified": False,
                  "scope": "One source pair, singleton native registry, one terrain variant, seed42, first attempt only; not all training variants or convergence.",
                  "case_id": self.case["case_id"], "policy": self.case.get("policy"), "source": self.case["source"],
                  "singleton_provenance_sha256": self.case.get("singleton_provenance_sha256"),
                  "inventory_identity_sha256": self.case["inventory_sha256"],
                  "source_inventory": self.case.get("source_inventory"), "harness_sources": self.case.get("harness_sources"),
                  "callback_target": "scripts.research.source_coverage_probe.SourceCoverageProbe",
                  "checkpoint": fingerprint(self.case["checkpoint"]),
                  "checkpoint_iteration": int(self.loop.current_learning_iteration),
                  "actual_native": self.actual, "native_argv": self.case["native_argv"], "seed": 42,
                  "warmup_cache_repair": {"enabled": True, "events": self.refresh_events,
                                          "native_formula": native_alignment_formula()[1]},
                  "stop_reason": reason, "stop_mechanism": "dedicated StopAttempt caught around unchanged native evaluate_policy; native post callbacks flushed once",
                  "first_attempt_reference_boundary_reached": boundary_complete,
                  "policy_reference_frames_contiguous_from_one": consecutive,
                  "policy_reference_frames": frames, "expected_policy_interval_inclusive": [1, self.case["source"]["frames"] - 2],
                  "missing_policy_reference_frames": sorted(set(expected) - set(frames)),
                  "source_frame_zero": "native initialization at phase0, then zero-action attempt warmup; not controlled by policy",
                  "source_last_frame": "boundary sentinel triggering command reset; no independent policy action",
                  "control_steps": len(policy), "attempt_warmup_steps": len(warmup), "initialization_steps": len(initialization),
                  "policy_sim_seconds": len(policy) * self.env.dt,
                  "attempt_including_warmup_sim_seconds": (len(policy) + len(warmup)) * self.env.dt,
                  "wall_seconds": time.monotonic() - self.started,
                  "failed_resets": sum(row["failed"] for row in policy + warmup),
                  "timeout_resets": sum(row["timeout"] for row in policy + warmup),
                  "metrics": summarize(policy), "attempt_warmup_metrics": summarize(warmup),
                  "initialization_metrics": summarize(initialization),
                  "finite_actions": all(row["finite_action"] for row in policy) if policy else None,
                  "finite_root_states": all(row["finite_root_state"] for row in policy) if policy else None,
                  "initialization_events": initialization, "attempt_warmup_events": warmup,
                  "first_event": self.rows[-1] if self.stop_reason else None,
                  "trajectory": fingerprint(self.directory / "trajectory.jsonl"), "videos": videos,
                  "capture_phase": "pre-action reference; after native _update_log_dict before reset flags/errors; motion_end_reset after complete native env.step"}
        from torch.utils.tensorboard import SummaryWriter
        tb = self.directory / "tensorboard"
        with SummaryWriter(log_dir=str(tb)) as writer:
            for tag in ("control_steps", "failed_resets", "timeout_resets", "policy_sim_seconds"):
                writer.add_scalar(f"Coverage/{tag}", report[tag], len(policy))
            writer.add_scalar("Coverage/reference_boundary_reached", int(boundary_complete), len(policy))
            for phase, metrics in (("policy", report["metrics"]), ("attempt_warmup", report["attempt_warmup_metrics"])):
                for key, metric in metrics.items():
                    if metric["mean"] is not None:
                        writer.add_scalar(f"Coverage/{phase}/{key}/mean", metric["mean"], len(policy))
            writer.flush()
        report["tensorboard_events"] = [fingerprint(path) for path in sorted(tb.glob("events.out.tfevents.*"))]
        atomic_json(self.directory / "quality.json", report)
        print(f"Source coverage: {report['case_id']} {reason}, {len(policy)} policy steps; quality_verified=false", flush=True)


def native_arguments(case):
    return ["--training.num-envs", "1", "--training.headless", "True", "--training.seed", "42",
            "--training.max-eval-steps", str(case["max_steps"]), "--training.export-onnx", "False",
            "--training.registry-name", case["registry_uri"],
            "--training.preprocess-hook-kwargs", json.dumps({"add_onpath_obstacle": True, "num_variants": 1, "obstacle_seed": 42}),
            "--terrain.terrain-term.spawn.randomize-tiles", "True", "logger:disabled",
            "--logger.base-dir", str(Path(case["output"]) / "native"), "--logger.video.enabled", "True",
            "--logger.video.interval", "1", "--logger.video.upload-to-wandb", "False"]


def recover_config(case, preprocess=False):
    from holosoma.utils.eval_utils import CheckpointConfig
    from wbt_training.utils.checkpoint import load_saved_experiment_config, parse_saved_config_overrides, apply_preprocess_hook
    saved, _ = load_saved_experiment_config(CheckpointConfig(checkpoint=case["checkpoint"]))
    targets = {"teacher": "holosoma.agents.ppo.ppo.PPO", "pure": "wbt_training.utils.student_teacher.PhpDistillation",
               "finetune": "wbt_training.utils.student_teacher.PhpDistillationPPO"}
    if saved.algo._target_ != targets[case["policy"]]:
        raise ValueError(f"Checkpoint algorithm {saved.algo._target_!r} is not policy {case['policy']!r}")
    cfg = parse_saved_config_overrides(saved.get_eval_config(), native_arguments(case))
    if preprocess:
        cfg = apply_preprocess_hook(cfg)
    return saved, cfg


def cpu_preflight(case):
    """Use actual PT recovery, hook, MotionLoader and Php branch on CPU."""
    from holosoma.managers.command.terms.wbt import MotionLoader
    from wbt_training.config_values.motion_command import PhpMotionCommand
    saved, cfg = recover_config(case, preprocess=True)
    mc = cfg.command.setup_terms["motion_command"].params["motion_config"]
    get = lambda key: mc[key] if isinstance(mc, dict) else getattr(mc, key)
    motion = MotionLoader(get("motion_file"), get("body_names_to_track"), cfg.robot.dof_names, device="cpu")
    balancing = PhpMotionCommand._expert_balancing_active(SimpleNamespace(motion=motion))
    source_verification = verify_preprocessed_source(case, get("motion_file"))
    ends = motion.motion_ends.nonzero().flatten().tolist()
    if (motion.time_step_total != case["source"]["frames"] or ends != [case["source"]["frames"] - 1]
            or motion.num_motions != 1 or motion.motion_idxs.unique().tolist() != [0] or balancing):
        raise ValueError("Actual CPU preprocessed loader does not match singleton source")
    directory = Path(case["output"]) / "cpu-preflight"
    directory.mkdir()
    cfg.save_config(str(directory / "holosoma_config.yaml"))
    for source, name in ((get("motion_file"), "motion.npz"), (cfg.terrain.terrain_term.obj_file_path, "terrain.obj")):
        retain_file(source, directory / name)
    report = {"status": "cpu_preflight_passed_gpu_not_run", "simulation_started": False,
              "scope": "Real saved PT config, native PHP preprocessing, CPU MotionLoader and student balancing predicate; no native reset, policy, physics or video.",
              "case_id": case["case_id"], "policy": case["policy"],
              "singleton_provenance_sha256": case["singleton_provenance_sha256"],
              "checkpoint": fingerprint(case["checkpoint"]), "source": case["source"],
              "registry_uri": case["registry_uri"], "inventory_identity_sha256": case["inventory_sha256"],
              "harness_sources": case.get("harness_sources"),
              "planned_eval_only_warmup_cache_repair": native_alignment_formula()[1],
              "saved_algorithm_target": saved.algo._target_, "num_envs": cfg.training.num_envs,
              "actual_frames": motion.time_step_total, "actual_boundary_indices_inclusive": ends,
              "actual_native_expert_ids": motion.motion_idxs.unique().tolist(), "expert_balancing_active": balancing,
              "original_expert_ordinal": case["source"]["expert_ordinal"], "singleton_native_expert_ordinal": 0,
              "preprocess_hook_kwargs": json.loads(cfg.training.preprocess_hook_kwargs),
              "source_table_verification": source_verification,
              "artifacts": [fingerprint(path) for path in sorted(directory.iterdir())]}
    atomic_json(directory / "report.json", report)
    return report


def run_native(case):
    from holosoma.config_types.eval_callback import EvalCallbacksConfig
    from holosoma.utils.eval_utils import CheckpointConfig
    output = Path(case["output"])
    if any((output / name).exists() for name in ("native", "quality.json", "trajectory.jsonl", "runtime-assets", "tensorboard")):
        raise ValueError("Use a fresh case output for native evaluation; old evidence is retained")
    saved, cfg = recover_config(case)
    kind = "teacher" if case["policy"] == "teacher" else "student"
    module = importlib.import_module(f"wbt_training.training_runs.eval_{kind}")
    original_get_class, original_collect = module.get_class, EvalCallbacksConfig.collect_active_callbacks
    original_setup, original_close = module.setup_simulation_environment, module.close_simulation_app
    application, closed = None, False

    def setup(config):
        nonlocal application
        env, device, application = original_setup(config)
        return env, device, application

    def close(app):
        nonlocal closed
        closed = True
        return original_close(app)

    def get_class(target):
        native = original_get_class(target)
        class GuardedNative(native):
            def evaluate_policy(self, max_eval_steps=None):
                return guarded_evaluate(self, native.evaluate_policy, max_eval_steps)
        return GuardedNative

    def collect(self):
        return {"source_coverage": SimpleNamespace(_target_="scripts.research.source_coverage_probe.SourceCoverageProbe", config={"case": case})}

    module.get_class, EvalCallbacksConfig.collect_active_callbacks = get_class, collect
    module.setup_simulation_environment, module.close_simulation_app = setup, close
    try:
        module.run_eval(cfg, CheckpointConfig(checkpoint=case["checkpoint"]), saved, None, eval_cbs_cfg=EvalCallbacksConfig())
    finally:
        module.get_class, EvalCallbacksConfig.collect_active_callbacks = original_get_class, original_collect
        module.setup_simulation_environment, module.close_simulation_app = original_setup, original_close
        if application is not None and not closed:
            original_close(application)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--cpu-preflight", action="store_true")
    args = parser.parse_args()
    case = json.loads(args.case.read_text())
    verify_case(case)
    os.environ["LOGGER"], os.environ["WANDB_MODE"] = "tensorboard", "disabled"
    try:
        if args.cpu_preflight:
            cpu_preflight(case)
        else:
            run_native(case)
    except BaseException as error:
        atomic_json(Path(case["output"]) / "worker-error.json", {
            "status": "execution_failed", "case_id": case["case_id"],
            "quality_verified": False, "error": f"{type(error).__name__}: {error}",
            "cpu_preflight_only": args.cpu_preflight})
        raise


def verify_case(case):
    if sha256(case["checkpoint"]) != case["checkpoint_sha256"]:
        raise ValueError("Checkpoint changed after plan creation")
    if sha256(case["singleton_provenance"]) != case["singleton_provenance_sha256"]:
        raise ValueError("Singleton provenance changed after plan creation")
    provenance = json.loads(Path(case["singleton_provenance"]).read_text())
    if (case["source"] != provenance["record"] or case["registry_uri"] != provenance["registry_uri"]
            or case["original_expert_ordinal"] != provenance["original_expert_ordinal"]
            or case["singleton_native_expert_ordinal"] != provenance["singleton_native_expert_ordinal"]):
        raise ValueError("Case source or registry identity does not match singleton provenance")
    for item in provenance["files"]:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("Singleton asset changed after plan creation")
    if "source_inventory" in case:
        from scripts.research.motion_coverage import validate_inventory
        item = case["source_inventory"]
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("Source inventory changed after plan creation")
        inventory = json.loads(Path(item["path"]).read_text())
        validate_inventory(inventory)
        if (inventory["inventory_sha256"] != case["inventory_sha256"]
                or case["source"] not in inventory["records"]):
            raise ValueError("Case source does not belong to this inventory")
    for source in case.get("harness_sources", []):
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError("Harness source changed after plan creation")


if __name__ == "__main__":
    # Dynamic native instantiate must share StopAttempt/isinstance identity
    # with the script entry point, rather than importing a second module copy.
    sys.modules["scripts.research.source_coverage_probe"] = sys.modules[__name__]
    main()
