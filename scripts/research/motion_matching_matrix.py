#!/usr/bin/env python3
"""Run every registered motion scenario; record artifacts and bounded failures.

Run inside the project Docker environment. Default: all configurations in all
17 public scenarios. --representatives tests the first configuration of each
scenario; this is explicitly recorded and never called full configuration
coverage. --skills additionally executes every traversal skill independently.
Generated trajectories are kinematic references, not policy/physics rollouts.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gc
import hashlib
import inspect
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def catalog(seed: int) -> dict:
    import numpy as np
    from motion_matching.scenarios import builtin
    from motion_matching.scenarios.skill_registry import SKILL_REGISTRY, resolve_paths
    scenarios = []
    for name, fn in inspect.getmembers(builtin, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != builtin.__name__:
            continue
        np.random.seed(seed)
        random.seed(seed)
        configs, speed = fn()
        scenarios.append({
            "name": name, "config_count": len(configs), "speed_up_ratio": speed,
            "skills": sorted({step["skill_name"] for cfg in configs for step in cfg["steps"] if step["type"] == "skill"}),
            "config_names": [cfg["name"] for cfg in configs],
            "offpath_clutter_configs": sum("offpath_obstacles" in cfg for cfg in configs),
        })
    skills = []
    for name, cfg in SKILL_REGISTRY.items():
        binary, features = resolve_paths(name, cfg)
        skills.append({"name": name, "database": binary, "feature_cache": features, **cfg})
    return {"scenarios": scenarios, "skills": skills}


def validate_motion(path: Path) -> dict:
    import numpy as np
    import trimesh
    from motion_matching.motion_visualizer import load_motion_data
    joints, root, qpos, fps, commands = load_motion_data(path)
    with np.load(path, allow_pickle=False) as motion:
        required = {"fps", "joint_pos", "joint_vel", "body_pos_w", "body_quat_w", "body_lin_vel_w", "body_ang_vel_w", "vel_cmd"}
        if not required.issubset(motion.files):
            raise ValueError(f"missing fields: {sorted(required - set(motion.files))}")
        if fps != 50 or len(joints) < 2:
            raise ValueError("expected >= 2 frames at 50 FPS")
        for name in required:
            if not np.isfinite(motion[name]).all():
                raise ValueError(f"non-finite values in {name}")
        if commands.shape != (len(joints), 15):
            raise ValueError(f"unexpected command shape: {commands.shape}")
        if not np.all((commands == 0) | (commands == 1)) or not np.all(commands.sum(axis=1) == 1):
            raise ValueError("velocity commands must be one-hot")
        norm_error = float(np.max(np.abs(np.linalg.norm(motion["body_quat_w"], axis=-1) - 1)))
        if norm_error > 1e-4:
            raise ValueError(f"quaternion norm error: {norm_error}")
        shapes = {key: list(motion[key].shape) for key in sorted(motion.files)}
    terrain = path.with_name(path.name.replace("_motion.npz", "_terrain.npy"))
    mesh_path = path.with_name(path.name.replace("_motion.npz", "_terrain.obj"))
    boxes = np.load(terrain, allow_pickle=False)
    if boxes.ndim != 3 or boxes.shape[1:] != (10, 10) or not np.isfinite(boxes).all():
        raise ValueError(f"invalid terrain variants: {boxes.shape}")
    if len(boxes) and np.any(boxes[:, :, 7:10] <= 0):
        raise ValueError("terrain extents must be positive")
    mesh = trimesh.load(mesh_path, force="mesh", process=False)
    if not len(mesh.vertices) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError("invalid terrain OBJ")
    return {
        "status": "passed", "frames": len(joints), "fps": fps,
        "duration_seconds": len(joints) / fps,
        "array_shapes": shapes, "terrain_shape": list(boxes.shape),
        "terrain_vertices": len(mesh.vertices), "terrain_faces": len(mesh.faces),
        "command_indices": sorted(np.unique(np.argmax(commands, axis=1)).tolist()),
        "quaternion_max_norm_error": norm_error,
        "root_start_xyz": root[0, :3].tolist(), "root_end_xyz": root[-1, :3].tolist(),
        "files": [{"path": str(p.resolve()), "size": p.stat().st_size, "sha256": sha256(p)} for p in (path, terrain, mesh_path)],
    }


def child(args: argparse.Namespace) -> None:
    import numpy as np
    from motion_matching import run as mm
    from motion_matching.scenarios import builtin
    from motion_matching.scenarios.skill_registry import SKILL_REGISTRY
    np.random.seed(args.seed)
    random.seed(args.seed)
    # Explicit-seeded terrain RNGs (off-path clutter) retain their original seed.
    original_rng = np.random.default_rng
    np.random.default_rng = lambda seed=None: original_rng(args.seed if seed is None else seed)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.child_skill:
        name = args.child_skill
        mm.init_worker(required_skills={name})
        system = mm._worker_sys
        cfg = SKILL_REGISTRY[name]
        qpos, commands = mm.generate_skill_sequence(system, name, vel_cmd_idx=1)
        if len(qpos) < 2 or not np.isfinite(qpos).all():
            raise ValueError(f"skill {name} did not produce a finite multi-frame traversal")
        result = {
            "name": name, "status": "passed", "frames_60hz": len(qpos),
            "execution_scope": "synthetic isolated skill executor; not a complete scenario or physical success",
            "database_start_ground_height": cfg.get("height_range", [0, 0])[0],
            "database_end_ground_height": cfg.get("height_range", [0, 0])[1],
            "final_motion_state": system.motion_state,
        }
        dump(output / "result.json", result)
        return
    configs, speed = getattr(builtin, args.child_scenario)()
    selected = configs[:1] if args.representatives else configs
    mm.init_worker(mm.collect_required_skills(selected))
    results = []
    for index, cfg in enumerate(selected):
        start = time.monotonic()
        row = {"name": cfg["name"], "index": index, "status": "failed", "steps": cfg["steps"]}
        try:
            mm.process_scenario(cfg, str(output), force=False, speed_up_ratio=speed)
            row.update(validate_motion(output / (cfg["name"] + "_motion.npz")))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["wall_seconds"] = round(time.monotonic() - start, 3)
        results.append(row)
        dump(output / "result.json", {
            "name": args.child_scenario, "seed": args.seed,
            "total_available_configs": len(configs), "selected_configs": len(selected),
            "passed": sum(r["status"] == "passed" for r in results),
            "failed": sum(r["status"] != "passed" for r in results),
            "configurations": results,
        })
    if any(row["status"] != "passed" for row in results):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--representatives", action="store_true")
    parser.add_argument("--skills", action="store_true")
    parser.add_argument("--scenario", action="append", help="Select registered scenario(s); default all")
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument("--jobs", type=int, default=1, help="Independent scenario/skill processes (default: 1)")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--child-scenario", help=argparse.SUPPRESS)
    parser.add_argument("--child-skill", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_scenario or args.child_skill:
        child(args)
        return
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    registry = catalog(args.seed)
    dump(output / "catalog.json", registry)
    if args.list_only:
        print(json.dumps(registry, indent=2))
        return
    selected = [row for row in registry["scenarios"] if not args.scenario or row["name"] in args.scenario]
    if args.scenario and set(args.scenario) - {row["name"] for row in selected}:
        parser.error("unknown scenario selection")
    report = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed, "scope": "one configuration per scenario" if args.representatives else "all configurations",
        "pipeline": "official motion_matching.run init_worker/process_scenario with seeded RNG",
        "rng_policy": "legacy NumPy/Python seeded; default_rng(None) uses seed; explicit builtin seeds retained",
        "physical_policy_rollout": False,
        "database_directory": os.environ.get("PHP_MOTION_DATABASE_DIR"),
        "jobs": args.jobs,
        "child_thread_environment": {key: "1" for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        "catalog": registry, "scenarios": [], "skills": [],
    }
    tasks = [("scenario", row["name"]) for row in selected]
    if args.skills:
        tasks += [("skill", row["name"]) for row in registry["skills"] if row["name"] != "locomotion"]
    if args.jobs > 1:
        # Build shared caches before concurrent readers start, avoiding partial
        # pickle reads when two skills share the same database/feature family.
        from motion_matching import run as mm
        started = time.monotonic()
        loaded = mm.init_databases()
        report["feature_cache_prime"] = {"status": "passed", "traversal_databases": len(loaded[1]),
                                         "wall_seconds": round(time.monotonic() - started, 3)}
        del loaded
        gc.collect()
        dump(output / "matrix.json", report)

    def run_task(task: tuple[str, str]) -> tuple[str, dict]:
        kind, name = task
        directory = output / ("scenarios" if kind == "scenario" else "skills") / name
        directory.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--output-dir", str(directory), "--seed", str(args.seed), f"--child-{kind}", name]
        if args.representatives:
            command.append("--representatives")
        started = time.monotonic()
        row = {"name": name, "status": "failed", "command": command, "log": str(directory / "run.log")}
        with (directory / "run.log").open("w") as log:
            try:
                env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
                process = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout_s, check=False)
                row["exit_code"] = process.returncode
                if (directory / "result.json").is_file():
                    row["result"] = json.loads((directory / "result.json").read_text())
                if process.returncode == 0 and "result" in row:
                    row["status"] = "passed"
            except subprocess.TimeoutExpired:
                row["error"] = f"timeout after {args.timeout_s} seconds"
        row["wall_seconds"] = round(time.monotonic() - started, 3)
        row["log_sha256"] = sha256(directory / "run.log")
        return kind, row

    def save_result(result: tuple[str, dict]) -> None:
        kind, row = result
        report["scenarios" if kind == "scenario" else "skills"].append(row)
        report["passed_scenarios"] = sum(r["status"] == "passed" for r in report["scenarios"])
        report["passed_skill_executors"] = sum(r["status"] == "passed" for r in report["skills"])
        report["failed"] = sum(r["status"] != "passed" for r in report["scenarios"] + report["skills"])
        dump(output / "matrix.json", report)
        print(f"{kind} {row['name']}: {row['status']} ({row['wall_seconds']} s)", flush=True)

    if args.jobs == 1:
        for task in tasks:
            save_result(run_task(task))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for future in concurrent.futures.as_completed([pool.submit(run_task, task) for task in tasks]):
                save_result(future.result())
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
