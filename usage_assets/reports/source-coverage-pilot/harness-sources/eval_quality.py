#!/usr/bin/env python3
"""Run the native teacher/student evaluator with a read-only pre-reset probe.

All unrecognized arguments pass unchanged to the native evaluator. Metrics
describe this rollout; no error threshold or successful training is inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
METRICS = {"motion/error_ref_pos": "m", "motion/error_ref_rot": "rad",
           "motion/error_body_pos": "m", "motion/error_joint_pos": "rad (joint-vector L2)"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


class QualityProbe:
    """Capture native flags after termination checks and BEFORE env resets."""

    def __init__(self, config, training_loop):
        self.config, self.training_loop = config, training_loop

    def on_pre_evaluate_policy(self):
        import numpy as np
        self.np = np
        loop = self.training_loop
        self.env = loop._unwrap_env() if hasattr(loop, "_unwrap_env") else loop.env
        env = self.env
        self.command = env.command_manager.get_state("motion_command")
        self.started, self.started_unix = time.monotonic(), time.time()
        self.steps = self.completions = 0
        self.record_step = False  # Native reset_all performs an uncounted warmup env.step.
        self.failed = np.zeros(env.num_envs, dtype=int)
        self.timeouts = self.failed.copy()
        self.first_failure = np.full(env.num_envs, np.nan)
        self.clips, self.experts, self.rows, self.expert_events = set(), set(), [], {}
        self.episode_lengths, self.minimum_height = [], float("inf")
        self.finite_actions = self.finite_states = True
        self.max_action = 0.0
        self.original_log = env._update_log_dict

        def capture():
            self.original_log()
            self.capture_before_reset()

        env._update_log_dict = capture

    def array(self, tensor):
        return tensor.detach().cpu().numpy().copy()

    def capture_before_reset(self):
        if not self.record_step:
            return
        np, env, cmd = self.np, self.env, self.command
        self.steps += 1
        failed = self.array(env.termination_manager.terminated).astype(bool)
        timeout = self.array(env.termination_manager.time_outs).astype(bool)
        self.failed += failed
        self.timeouts += timeout
        self.first_failure[failed & np.isnan(self.first_failure)] = self.steps * env.dt
        self.episode_lengths.extend(self.array(env.episode_length_buf)[failed | timeout].tolist())
        self.pending_reset = failed | timeout
        clips = self.array(cmd.motion_ids).astype(int)
        experts = self.array(cmd.motion.motion_idxs[cmd.time_steps]).astype(int)
        self.clips.update(clips.tolist())
        self.experts.update(experts.tolist())
        for expert in np.unique(experts):
            counts = self.expert_events.setdefault(str(int(expert)), {"failed_resets": 0, "timeout_resets": 0, "env_steps": 0})
            mask = experts == expert
            counts["failed_resets"] += int((failed & mask).sum())
            counts["timeout_resets"] += int((timeout & mask).sum())
            counts["env_steps"] += int(mask.sum())
        values = {key: self.array(env.log_dict[key]).reshape(-1) for key in METRICS}
        self.rows.append((experts, values))
        root = self.array(env.simulator.robot_root_states[:])  # Isaac exposes RootStatesProxy.
        self.finite_states &= bool(np.isfinite(root).all())
        self.minimum_height = min(self.minimum_height, float(root[:, 2].min()))

    def on_pre_eval_env_step(self, actor_state):
        self.record_step = "step" in actor_state
        return actor_state

    def on_post_eval_env_step(self, actor_state):
        np = self.np
        action = self.array(actor_state["actions"])
        self.finite_actions &= bool(np.isfinite(action).all())
        self.max_action = max(self.max_action, float(np.abs(action).max()))
        ended = self.array(self.command.motion_end_reset).astype(bool)
        self.completions += int((ended & ~self.pending_reset).sum())
        return actor_state

    def on_post_evaluate_policy(self):
        np, env, loop = self.np, self.env, self.training_loop
        env._update_log_dict = self.original_log
        recorder = getattr(env.simulator, "video_recorder", None)
        if recorder is not None:
            recorder.stop_recording()  # Flush the final partial episode before Isaac shutdown.

        def summarize(expert=None):
            result = {}
            for key, unit in METRICS.items():
                batches = [values[key] if expert is None else values[key][ids == expert]
                           for ids, values in self.rows]
                data = np.concatenate(batches) if batches else np.array([])
                finite = data[np.isfinite(data)]
                result[key] = {"unit": unit, "samples": int(data.size), "finite": bool(np.isfinite(data).all()),
                               "mean": float(finite.mean()) if finite.size else None,
                               "p95": float(np.percentile(finite, 95)) if finite.size else None,
                               "max": float(finite.max()) if finite.size else None}
            return result

        videos = []
        # Environment and algorithm each create their own timestamped log dir.
        for path in sorted(Path(loop.log_dir).parent.rglob("*.mp4")):
            if path.stat().st_mtime < self.started_unix:
                continue
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
            duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0)) if probe.returncode == 0 else 0
            if duration > 0:
                videos.append({"path": str(path.resolve()), "sha256": sha256(path), "duration_seconds": duration})
        checkpoint = Path(self.config["checkpoint"])
        saved_config = Path(loop.log_dir) / "holosoma_config.yaml"
        report = {"schema_version": 1, "status": "completed", "quality_verified": False,
                  "scope": "Measured rollout only; clip completion is not course completion or convergence.",
                  "checkpoint": str(checkpoint), "checkpoint_sha256": sha256(checkpoint),
                  "checkpoint_iteration": int(loop.current_learning_iteration),
                  "native_argv": list(self.config["argv"]), "seed": int(env.training_config.seed),
                  "registry_order": str(env.training_config.registry_name).split(","),
                  "saved_eval_config": str(saved_config), "saved_eval_config_sha256": sha256(saved_config),
                  "num_envs": env.num_envs, "control_dt_seconds": env.dt, "control_steps": self.steps,
                  "sim_seconds_per_env": self.steps * env.dt, "total_env_seconds": self.steps * env.dt * env.num_envs,
                  "wall_seconds": time.monotonic() - self.started, "failed_resets": int(self.failed.sum()),
                  "timeout_resets": int(self.timeouts.sum()), "failed_resets_by_env": self.failed.tolist(),
                  "timeout_resets_by_env": self.timeouts.tolist(),
                  "first_failure_sim_seconds_by_env": [float(x) if np.isfinite(x) else None for x in self.first_failure],
                  "ended_episode_lengths_steps": self.episode_lengths,
                  "clip_completions_excluding_failed_timeout_steps": self.completions,
                  "observed_clip_ids": sorted(self.clips), "available_clip_count": int(self.command.motion.motion_end_idx.numel()),
                  "observed_expert_ids": sorted(self.experts), "metrics": summarize(),
                  "metrics_by_expert": {str(i): summarize(i) for i in sorted(self.experts)},
                  "resets_by_expert": self.expert_events,
                  "finite_actions": self.finite_actions, "finite_root_states": self.finite_states,
                  "max_abs_action": self.max_action, "minimum_root_height_m": self.minimum_height if np.isfinite(self.minimum_height) else None,
                  "videos": videos, "capture_phase": "after native _update_log_dict, before reset_envs_idx"}
        from torch.utils.tensorboard import SummaryWriter
        tensorboard_dir = Path(self.config["output"]).parent / "tensorboard"
        with SummaryWriter(log_dir=str(tensorboard_dir)) as writer:
            for tag, value in {"failed_resets": report["failed_resets"], "timeouts": report["timeout_resets"],
                               "control_steps": self.steps, "sim_seconds_per_env": report["sim_seconds_per_env"],
                               "clip_completions": self.completions}.items():
                writer.add_scalar(f"Evaluation/{tag}", value, self.steps)
            for key, metric in report["metrics"].items():
                for aggregate in ("mean", "p95", "max"):
                    if metric[aggregate] is not None:
                        writer.add_scalar(f"Evaluation/tracking_error/{key.removeprefix('motion/')}/{aggregate}", metric[aggregate], self.steps)
            writer.flush()
        report["tensorboard_events"] = [str(path.resolve()) for path in sorted(tensorboard_dir.glob("events.out.tfevents.*"))]
        atomic_json(self.config["output"], report)
        print(f"Quality report: {self.config['output']} ({self.steps} steps, {report['failed_resets']} failed resets)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("teacher", "student"))
    parser.add_argument("--quality-output", type=Path, required=True)
    args, native_argv = parser.parse_known_args()
    if "--checkpoint" not in native_argv:
        parser.error("native --checkpoint is required")
    checkpoint = native_argv[native_argv.index("--checkpoint") + 1]
    if not Path(checkpoint).is_file():
        parser.error("Use an existing, resolved local PT checkpoint")
    from holosoma.config_types.eval_callback import EvalCallbacksConfig
    collect = EvalCallbacksConfig.collect_active_callbacks

    def with_quality(self):
        configs = collect(self)
        configs["research_quality"] = SimpleNamespace(_target_="scripts.research.eval_quality.QualityProbe", config=
                                      {"output": str(args.quality_output.resolve()), "checkpoint": checkpoint, "argv": native_argv})
        return configs

    EvalCallbacksConfig.collect_active_callbacks = with_quality
    sys.argv = [f"eval_{args.kind}", *native_argv]
    importlib.import_module(f"wbt_training.training_runs.eval_{args.kind}").main()


if __name__ == "__main__":
    main()
