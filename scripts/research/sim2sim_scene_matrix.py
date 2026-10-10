#!/usr/bin/env python3
"""One real ONNX closed-loop rollout per generated PHP scenario (17 meshes).

Uses deterministic, predeclared configurations, retaining falls and failures.
This covers one geometry per scenario, not all 629 configurations or the
reference clip's skills/command sequence. Run only inside the research Docker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("random_locomotion", "low_speed_step", "high_speed_step",
             "low_speed_climb_58", "high_speed_climb_58", "low_speed_climb_76", "high_speed_climb_76",
             "low_speed_climb_94", "high_speed_climb_94", "low_speed_roll_78", "low_speed_roll_90",
             "high_speed_roll_134", "high_speed_hurdle", "high_speed_dash_vault", "high_speed_speed_vault",
             "high_speed_cat_vault", "high_speed_jump_35")
RELEASED_TRAINING_DATA = {"random_locomotion", "low_speed_step", "high_speed_step", "low_speed_climb_76", "high_speed_climb_76"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def select(source: dict) -> list[dict]:
    by_name = {entry["name"]: entry for entry in source["scenarios"]}
    if set(by_name) != set(SCENARIOS):
        raise ValueError("Motion-matching matrix must contain all exact 17 PHP scenarios")
    selected = []
    for name in SCENARIOS:
        entry = by_name[name]
        if entry["status"] != "passed":
            raise ValueError(f"Motion-matching scenario did not pass: {name}")
        candidates = sorted((config for config in entry["result"]["configurations"] if config["status"] == "passed"), key=lambda config: config["index"])
        if name == "random_locomotion":
            # Ground plane alone has 8 OBJ vertices. Choose the first actual
            # clutter mesh with a simple high-forward reference sequence.
            candidates = [config for config in candidates if config["terrain_vertices"] > 8
                          and {step.get("vel_cmd_idx", 0) for step in config["steps"] if step.get("vel_cmd_idx", 0)} == {6}]
        elif len(candidates) > 1:
            forward = [config for config in candidates if "forward" in config["name"]]
            candidates = forward or candidates
        if not candidates:
            raise ValueError(f"No deterministic complete configuration available: {name}")
        config = candidates[0]
        mesh = next(item for item in config["files"] if item["path"].endswith("_terrain.obj"))
        selected.append({"scenario": name, "configuration": config["name"], "configuration_index": config["index"],
                         "available_configurations": entry["result"]["total_available_configs"],
                         "reference_clip_seconds": config["duration_seconds"], "reference_steps": config["steps"],
                         "terrain_vertices": config["terrain_vertices"], "mesh": mesh["path"], "mesh_sha256": mesh["sha256"],
                         "command": 1 if name.startswith("low_speed_") else 6,
                         "matching_released_training_bundle_available": name in RELEASED_TRAINING_DATA,
                         "quality_verified": False, "obstacle_course_completion_verified": False})
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("/outputs/motion-matching/matrix.json"))
    parser.add_argument("--models", type=Path, default=Path("/data/assets/student"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gl", choices=("egl", "osmesa"), default="egl")
    parser.add_argument("--image-id", default=os.environ.get("PHP_RESEARCH_IMAGE_ID", "unrecorded; record Docker image ID externally"))
    parser.add_argument("--plan", action="store_true", help="Verify exact input hashes and write the plan without simulator/inference")
    parser.add_argument("--plan-output", type=Path)
    args = parser.parse_args()
    if not 8 <= args.seconds <= 12:
        parser.error("Use 8–12 simulated seconds per selected scenario")
    source = json.loads(args.matrix.read_text())
    selections = select(source)
    model_hashes = {name: digest(args.models / name) for name in ("depth_backbone.onnx", "student.onnx")}
    for selection in selections:
        mesh = Path(selection["mesh"])
        if not mesh.is_file() or digest(mesh) != selection["mesh_sha256"]:
            parser.error(f"Missing or changed generated mesh: {mesh}")
        output = args.output.resolve() / selection["scenario"]
        selection["output"] = str(output)
        selection["launch"] = [sys.executable, str(ROOT / "scripts/research/sim2sim.py"), "--models", str(args.models.resolve()),
                               "--terrain", "custom", "--mesh", str(mesh), "--commands", str(selection["command"]),
                               "--seconds-per-command", str(args.seconds), "--seed", str(args.seed), "--gl", args.gl, "--output", str(output)]
    report = {"schema_version": 1, "status": "planned", "seed": args.seed, "image_id": args.image_id,
              "source_matrix": str(args.matrix.resolve()), "source_matrix_sha256": digest(args.matrix), "model_sha256": model_hashes,
              "scope": "17 scenarios, exactly one complete generated geometry per scenario; constant forward command; not 629 policy rollouts or reference-motion replay",
              "seconds_per_scenario": args.seconds, "planned_scenarios": len(selections), "selections": selections,
              "selection_rule": "First passing forward-named configuration by source index, else first passing configuration; random_locomotion first clutter (>8 vertices) configuration with only high-forward moving segments",
              "estimated_egl_wall_minutes": [8, 12], "quality_verified": False, "obstacle_course_completion_verified": False}
    if args.plan:
        target = args.plan_output or args.output.with_name(args.output.name + "-plan.json")
        write(target, report)
        print(f"Verified {len(selections)} scenario geometries. Plan: {target}", flush=True)
        return
    if not (Path("/.dockerenv").exists() or os.environ.get("PHP_DOCKER") == "1"):
        parser.error("Physical rollout must run inside the research Docker")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a new empty output directory; preserve all previous runs")
    args.output.mkdir(parents=True, exist_ok=True)
    report.update(status="running", started_unix=time.time())
    target = args.output / "matrix.json"
    write(target, report)
    for selection in selections:
        name = selection["scenario"]
        print(f"Starting {name}: {selection['configuration']} / command {selection['command']}", flush=True)
        started = time.monotonic()
        with (args.output / f"{name}.log").open("w") as log:
            process = subprocess.run(selection["launch"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        result_path = Path(selection["output"]) / "result.json"
        result = json.loads(result_path.read_text()) if result_path.is_file() else None
        selection.update(returncode=process.returncode, wall_seconds=time.monotonic() - started,
                         status="completed" if process.returncode == 0 and result else "execution_failed",
                         result_report=str(result_path), result=result)
        write(target, report)
        print(f"Finished {name}: {selection['status']}, heuristic survival={result.get('survival_passed') if result else None}", flush=True)
    report.update(status="completed" if all(item["status"] == "completed" for item in selections) else "execution_failed",
                  finished_unix=time.time(), completed_scenarios=sum(item["status"] == "completed" for item in selections),
                  heuristic_survival_scenarios=sum(bool(item.get("result", {}).get("survival_passed")) for item in selections if item.get("result")))
    write(target, report)
    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
