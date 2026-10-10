#!/usr/bin/env python3
"""Real ONNX closed-loop rollouts on generated PHP scenario geometries.

Uses deterministic, predeclared configurations, retaining falls and failures.
Default: one geometry per scenario (17). --all-configs explicitly selects all
629 configurations. Commands remain constant forward by default. Explicit
--reference-commands replays every generated 50 Hz label through the physical
policy, with root XY/yaw alignment and deployment startup stance preserved.
Run only inside the research Docker; execution is sequential.
Matrix drivers share a container-wide DDS lock. Manual sim2sim invocations must
also run sequentially, after all matrix drivers and native workers have exited.
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import re
import math
import importlib.util

if __package__:
    from .reference_commands import load_reference_commands
else:
    from reference_commands import load_reference_commands

ROOT = Path(__file__).resolve().parents[2]
GLOBAL_LOCK = Path("/tmp/php-parkour-sim2sim-matrix.lock")
SCENARIOS = ("random_locomotion", "low_speed_step", "high_speed_step",
             "low_speed_climb_58", "high_speed_climb_58", "low_speed_climb_76", "high_speed_climb_76",
             "low_speed_climb_94", "high_speed_climb_94", "low_speed_roll_78", "low_speed_roll_90",
             "high_speed_roll_134", "high_speed_hurdle", "high_speed_dash_vault", "high_speed_speed_vault",
             "high_speed_cat_vault", "high_speed_jump_35")
RELEASED_TRAINING_DATA = {"random_locomotion", "low_speed_step", "high_speed_step", "low_speed_climb_76", "high_speed_climb_76"}
CONFIG_COUNTS = dict(zip(SCENARIOS, (100, 56, 60, 40, 40, 40, 40, 20, 15, 1, 3, 40, 51, 51, 20, 51, 1)))


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fingerprint(path: Path) -> dict:
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def select(source: dict, all_configs: bool = False) -> list[dict]:
    by_name = {entry["name"]: entry for entry in source["scenarios"]}
    if len(source["scenarios"]) != len(SCENARIOS) or set(by_name) != set(SCENARIOS):
        raise ValueError("Motion-matching matrix must contain all exact 17 PHP scenarios")
    selected = []
    for name in SCENARIOS:
        entry = by_name[name]
        if entry["status"] != "passed":
            raise ValueError(f"Motion-matching scenario did not pass: {name}")
        candidates = sorted((config for config in entry["result"]["configurations"] if config["status"] == "passed"), key=lambda config: config["index"])
        if all_configs:
            configs = entry["result"]["configurations"]
            if (len(candidates) != CONFIG_COUNTS[name] or len(configs) != len(candidates)
                    or entry["result"]["total_available_configs"] != CONFIG_COUNTS[name]
                    or [config["index"] for config in candidates] != list(range(CONFIG_COUNTS[name]))
                    or len({config["name"] for config in candidates}) != len(candidates)):
                raise ValueError(f"Incomplete or duplicate all-configuration input: {name}")
        elif name == "random_locomotion":
            # Ground plane alone has 8 OBJ vertices. Choose the first actual
            # clutter mesh with a simple high-forward reference sequence.
            candidates = [config for config in candidates if config["terrain_vertices"] > 8
                          and {step.get("vel_cmd_idx", 0) for step in config["steps"] if step.get("vel_cmd_idx", 0)} == {6}]
        elif len(candidates) > 1:
            forward = [config for config in candidates if "forward" in config["name"]]
            candidates = forward or candidates
        if not candidates:
            raise ValueError(f"No deterministic complete configuration available: {name}")
        for config in candidates if all_configs else candidates[:1]:
            if (len(config["files"]) != 3 or len({item["path"] for item in config["files"]}) != 3
                    or {Path(item["path"]).suffix for item in config["files"]} != {".npz", ".npy", ".obj"}):
                raise ValueError(f"Expected the generated motion/terrain/OBJ triple: {name}/{config['name']}")
            meshes = [item for item in config["files"] if item["path"].endswith("_terrain.obj")]
            if len(meshes) != 1:
                raise ValueError(f"Expected one generated OBJ: {name}/{config['name']}")
            mesh = meshes[0]
            selected.append({"scenario": name, "configuration": config["name"], "configuration_index": config["index"],
                         "case_id": f"{name}:{config['index']:04d}:{config['name']}",
                         "available_configurations": entry["result"]["total_available_configs"],
                         "reference_clip_seconds": config["duration_seconds"], "reference_steps": config["steps"],
                         "terrain_vertices": config["terrain_vertices"], "mesh": mesh["path"], "mesh_sha256": mesh["sha256"],
                         "source_files": config["files"],
                         "command": 1 if name.startswith("low_speed_") else 6,
                         "matching_released_training_bundle_available": name in RELEASED_TRAINING_DATA,
                         "quality_verified": False, "obstacle_course_completion_verified": False})
    return selected


def dependencies() -> list[dict]:
    """Local import closure plus dynamically registered presets/runtime targets.

    Unrelated motion-matching GUI, docs, tests and training agent source are not
    included merely because they share this checkout. Installed native libraries
    are bound by the externally verified immutable Docker image ID.
    """
    files = {Path(__file__).resolve(), ROOT / "scripts/research/sim2sim.py",
             ROOT / "scripts/research/reference_commands.py"}
    packages = {name: ROOT / relative for name, relative in (
        ("holosoma", "thirdparty/holosoma/src/holosoma/holosoma"),
        ("holosoma_inference", "thirdparty/holosoma/src/holosoma_inference/holosoma_inference"),
        ("wbt_training", "wbt_training"))}
    # Native registry discovery imports these preset modules, and selected
    # simulator/plugin/interface targets are loaded through string names.
    for name, directory in packages.items():
        values = directory / ("config/config_values" if name == "holosoma_inference" else "config_values")
        files.update(path for path in values.rglob("*.py") if "tests" not in path.parts)
    for relative in ("simulator/mujoco", "simulator/base_simulator", "simulator/shared", "simulator/plugins", "managers/terrain"):
        files.update(path for path in (packages["holosoma"] / relative).rglob("*.py") if "tests" not in path.parts)
    # SDK bridges are selected through installed entry-point metadata, so no
    # Python import statement necessarily names their implementation module.
    files.update((packages["holosoma"] / "bridge").rglob("*.py"))
    files.update((packages["holosoma_inference"] / "sdk/unitree").glob("*.py"))
    files.update(ROOT / "docker/bin" / name for name in ("train-python", "inference-python", "activate"))
    assets = packages["holosoma"] / "data/robots/g1"
    files.update(path for path in assets.rglob("*") if path.is_file() and "__pycache__" not in path.parts)

    def resolve(module):
        root, _, tail = module.partition(".")
        if root not in packages:
            return None
        base = packages[root].joinpath(*tail.split(".")) if tail else packages[root]
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None

    seeds, files, pending, checked = files, set(), [], set()

    def include(path):
        candidates = [path]
        # Importing a leaf executes every regular parent package __init__.
        # Those initializers can import other leaves as a side effect, and
        # must themselves enter the AST work queue, including for seed files.
        for directory in packages.values():
            if path.is_relative_to(directory):
                parent = path.parent
                while parent.is_relative_to(directory):
                    initializer = parent / "__init__.py"
                    if initializer.is_file():
                        candidates.append(initializer)
                    if parent == directory:
                        break
                    parent = parent.parent
                break
        for candidate in candidates:
            if candidate not in files:
                files.add(candidate)
                pending.append(candidate)

    for path in seeds:
        include(path)
    while pending:
        path = pending.pop()
        if path in checked or path.suffix != ".py":
            continue
        checked.add(path)
        package = next((name + "." + ".".join(path.relative_to(directory).with_suffix("").parts)
                        for name, directory in packages.items() if path.is_relative_to(directory)), "")
        package = package.removesuffix(".__init__") if path.name == "__init__.py" else package.rpartition(".")[0]
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    if not package:
                        continue
                    module = importlib.util.resolve_name("." * node.level + module, package)
                names = [module, *(module + "." + alias.name for alias in node.names)]
            for name in names:
                candidate = resolve(name)
                if candidate is not None:
                    include(candidate)
    return [fingerprint(path) for path in sorted(files)]


def verify_inputs(plan: dict, selection: dict) -> None:
    if plan.get("schema_version") != 3:
        raise ValueError("New native acceptance requires schema3 worker exit receipts; preserve legacy raw evidence")
    for item in [plan["source_matrix_record"], *plan["dependencies"], *plan["models"], *selection["source_files"]]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Planned input changed; use a fresh plan: {item['path']}")


def case_input(plan: dict, selection: dict) -> dict:
    return {key: plan[key] for key in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
        "case_id": selection["case_id"], "source_files": selection["source_files"], "launch": selection["launch"]}


def attempt_launch(selection: dict, output: Path) -> list[str]:
    launch = list(selection["launch"])
    launch[launch.index("--output") + 1] = str(output)
    return launch


def running_children(base: Path | None = None) -> list[int]:
    """An interrupted driver must not start beside its surviving native child."""
    found = []
    script = str(ROOT / "scripts/research/sim2sim.py")
    for process in Path("/proc").glob("[0-9]*"):
        try:
            command = (process / "cmdline").read_bytes().decode().split("\0")
            if script not in command or "--output" not in command:
                continue
            output = Path(command[command.index("--output") + 1]).resolve()
            if base is None or output.is_relative_to(base.resolve()):
                found.append(int(process.name))
        except (OSError, UnicodeError, IndexError):
            # A process may exit between directory enumeration and this read.
            continue
    return found


def make_plan(args) -> dict:
    source = json.loads(args.matrix.read_text())
    selections = select(source, args.all_configs)
    models = [fingerprint(args.models / name) for name in ("depth_backbone.onnx", "student.onnx")]
    if args.all_configs and not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id):
        raise ValueError("--all-configs requires the externally verified Docker --image-id sha256:...")
    for selection in selections:
        for item in selection["source_files"]:
            if digest(Path(item["path"])) != item["sha256"]:
                raise ValueError(f"Missing or changed generated source: {item['path']}")
        output = args.output.resolve() / selection["scenario"]
        if args.all_configs:
            slug = re.sub(r"[^A-Za-z0-9_.-]", "_", selection["configuration"])[:80]
            name_hash = hashlib.sha256(selection["configuration"].encode()).hexdigest()[:12]
            output /= f"config-{selection['configuration_index']:04d}-{slug}-{name_hash}"
        selection["output"] = str(output)
        command_args = ["--commands", str(selection["command"]), "--seconds-per-command", str(args.seconds)]
        if getattr(args, "reference_commands", False):
            motions = [item for item in selection["source_files"] if item["path"].endswith("_motion.npz")]
            if len(motions) != 1:
                raise ValueError("Reference replay requires exactly one generated _motion.npz")
            reference = load_reference_commands(motions[0]["path"])
            if reference["sha256"] != motions[0]["sha256"]:
                raise ValueError("Reference labels differ from the source matrix NPZ")
            if not math.isclose(reference["frames"] / reference["fps"], selection["reference_clip_seconds"], abs_tol=1e-9):
                raise ValueError("Reference frame duration differs from the source matrix")
            selection["reference_commands"] = reference
            selection["policy_seconds"] = reference["frames"] / reference["fps"]
            command_args = ["--reference-motion", reference["path"], "--reference-spawn", "--record-policy"]
        selection["launch"] = [sys.executable, str(ROOT / "scripts/research/sim2sim.py"), "--models", str(args.models.resolve()),
                               "--terrain", "custom", "--mesh", selection["mesh"], *command_args,
                               "--seed", str(args.seed), "--gl", args.gl,
                               "--python-faulthandler",
                               "--sim-python", args.sim_python, "--inference-python", args.inference_python, "--output", str(output)]
    closure = dependencies()
    harness = [item for item in closure if item["path"] == str(ROOT / "scripts/research/sim2sim.py")]
    if len(harness) != 1:
        raise ValueError("Native harness must be an explicit unique frozen dependency")
    plan = {"schema_version": 3, "status": "planned", "seed": args.seed, "image_id": args.image_id,
            "source_matrix": str(args.matrix.resolve()), "source_matrix_sha256": digest(args.matrix),
            "source_matrix_record": fingerprint(args.matrix), "models": models,
            "model_sha256": {Path(item["path"]).name: item["sha256"] for item in models},
            "dependencies": closure, "worker_harness_record": harness[0],
            "worker_interpreters": {"simulator": args.sim_python, "inference": args.inference_python},
            "python_faulthandler": True, "all_configurations": args.all_configs,
            "runtime_environment": {"MUJOCO_EGL_DEVICE_ID": os.environ.get("MUJOCO_EGL_DEVICE_ID", "0")},
            "container_matrix_lock": str(GLOBAL_LOCK),
            "concurrency_scope": "One matrix driver per container; all manual native sim2sim jobs must also be serialized",
            "scope": ("17 scenarios, all 629 generated configurations; constant forward command; not reference-motion replay or verified obstacle-course completion"
                      if args.all_configs else "17 scenarios, exactly one complete generated geometry per scenario; constant forward command; not 629 policy rollouts or reference-motion replay"),
            "seconds_per_scenario": args.seconds, "seconds_per_configuration": args.seconds,
            "planned_scenarios": len(SCENARIOS), "planned_configurations": len(selections), "selections": selections,
            "selection_rule": ("Every passing source configuration, fixed scenario order then complete contiguous source index"
                               if args.all_configs else "First passing forward-named configuration by source index, else first passing configuration; random_locomotion first clutter (>8 vertices) configuration with only high-forward moving segments"),
            "estimated_egl_wall_minutes": [240, 300] if args.all_configs else [8, 12],
            "quality_verified": False, "obstacle_course_completion_verified": False}
    if getattr(args, "reference_commands", False):
        plan.update(reference_commands=True, seconds_per_scenario=None, seconds_per_configuration=None,
                    total_policy_seconds=sum(item["policy_seconds"] for item in selections),
                    estimated_egl_wall_minutes=None,
                    scope=f"17 scenarios, {len(selections)} generated configurations; full per-frame reference command replay through the physical policy; root XY/yaw alignment with deployment stance; skill/course success unverified")
    plan["plan_sha256"] = identity(plan)
    return plan


def validate_worker_receipts(directory: Path, plan: dict, result: dict, translate=lambda value: value) -> list[dict]:
    """Validate immutable native shutdown evidence; optional host path mapping.

    `directory` is the actual evidence directory in the observer namespace.
    translate maps retained native absolute paths to that namespace without
    rewriting the original JSON. Returns the three mandatory fingerprints.
    """
    def require(condition, message):
        if not condition:
            raise ValueError("Native worker receipts: " + message)

    require(plan.get("schema_version") == 3 and plan.get("python_faulthandler") is True,
            "schema3 and fatal-signal diagnostics are required")
    harness = plan["worker_harness_record"]
    require(harness in plan["dependencies"] and re.fullmatch(r"[0-9a-f]{64}", harness["sha256"])
            and Path(translate(harness["path"])).resolve() == (ROOT / "scripts/research/sim2sim.py").resolve()
            and sum(item["path"] == harness["path"] for item in plan["dependencies"]) == 1,
            "harness SHA is not bound to the frozen dependency closure")
    require(set(plan["worker_interpreters"]) == {"simulator", "inference"}, "two native interpreters required")
    directory = Path(directory).resolve()
    paths = [directory / name for name in ("worker-processes.json", "simulator-process-start.json", "inference-process-start.json")]
    require(all(path.is_file() and not path.is_symlink() and path.stat().st_size > 0 for path in paths),
            "three fresh regular receipt files required")
    receipt = json.loads(paths[0].read_text())
    require(receipt.get("schema_version") == 2 and receipt.get("harness_sha256") == harness["sha256"]
            and receipt.get("python_faulthandler") == "1", "supervisor source/diagnostic contract differs")
    events = receipt["events"]
    require(events and events[-1].get("event") == "finally_wait_complete"
            and sum(event.get("event") == "finally_wait_complete" for event in events) == 1,
            "final waited cleanup event must exist exactly once and be last")
    require(not any(event.get("event") in ("error_detected", "terminate_requested", "kill_requested") for event in events),
            "failed/terminated attempts cannot be sealed as normal completion")
    require(all(isinstance(event.get("elapsed_seconds"), (int, float))
                and math.isfinite(event["elapsed_seconds"]) and event["elapsed_seconds"] >= 0 for event in events)
            and [e["elapsed_seconds"] for e in events] == sorted(e["elapsed_seconds"] for e in events),
            "event chronology is missing or nonmonotonic")
    final = events[-1]
    require(final.get("unreaped_roles") == [] and final.get("cleanup_errors") == [], "cleanup is incomplete or failed")
    completion = [event for event in events if event.get("event") == "workers_loop_complete"]
    require(len(completion) == 1 and result.get("worker_status_report") == "worker-processes.json"
            and result.get("worker_status_at_completion") == completion[0], "result is not bound to the observed terminal workers")
    roles = ("simulator", "inference")

    def by_role(event):
        workers = event["workers"]
        require([item.get("role") for item in workers] == list(roles), "two ordered workers required")
        return {item["role"]: item for item in workers}

    def clean(worker):
        require(type(worker.get("returncode")) is int and type(worker.get("exit_code")) is int
                and worker["returncode"] == worker["exit_code"] == 0 and worker.get("status") == "exited"
                and "signal_number" in worker and "signal_name" in worker
                and worker["signal_number"] is None and worker["signal_name"] is None
                and worker["process_group"].get("live_members") == []
                and worker["process_group"].get("ownership_verified") is True
                and worker["process_group"].get("ownership_state") == "retired_empty"
                and worker["process_group"].get("retired") is True
                and worker["process_group"].get("ownership_lost") is False
                and not worker["process_group"].get("observation_error"), "worker is nonzero, alive or unobservable")

    last, completed = by_role(final), by_role(completion[0])
    for role, path in zip(roles, paths[1:]):
        spawn_events = [event for event in events if event.get("event") == "worker_spawned" and event.get("role") == role]
        require(len(spawn_events) == 1, "missing/duplicate spawn event: " + role)
        spawned = [worker for worker in spawn_events[0]["workers"] if worker.get("role") == role]
        require(len(spawned) == 1, "spawn worker identity missing: " + role)
        spawn = spawned[0]
        identity_at_spawn = spawn["identity_at_spawn"]
        pid, birth = identity_at_spawn["pid"], identity_at_spawn["start_time_clock_ticks"]
        require(type(pid) is int and pid > 1 and type(birth) is int and birth > 0
                and identity_at_spawn["process_group_id"] == identity_at_spawn["session_id"] == pid,
                "spawn is not an observed private session leader")
        launch = spawn["launch"]
        require(len(launch) == 6 and launch[:4] == [plan["worker_interpreters"][role], harness["path"], "--worker", role]
                and launch[4] == "--output" and Path(translate(launch[5])).resolve() == directory,
                "worker launch/interpreter/output differs from the native plan")
        for worker in (completed[role], last[role]):
            clean(worker)
            require(worker["launch"] == launch and worker["identity_at_spawn"] == identity_at_spawn
                    and worker["process_group"]["process_group_id"] == worker["process_group"]["session_id"] == pid
                    and worker["process_group"].get("leader_identity") == {"pid": pid, "start_time_clock_ticks": birth},
                    "worker identity changed between spawn, completion and cleanup")
        entry = json.loads(path.read_text())
        require(entry.get("schema_version") == 1 and entry.get("role") == role and entry.get("argv") == launch[1:]
                and entry.get("python_faulthandler") == "1", "native entry argv/role/diagnostics differ")
        native = entry["process"]
        native_pid, native_birth = native["pid"], native["start_time_clock_ticks"]
        require(type(native_pid) is int and native_pid > 1 and type(native_birth) is int and native_birth >= birth
                and native["process_group_id"] == native["session_id"] == pid, "native entry is outside the observed private session")
        entry_events = [event for event in events if event.get("event") == "worker_entry_observed" and event.get("role") == role]
        require(len(entry_events) == 1 and entry_events[0].get("entry_sha256") == digest(path)
                and entry_events[0].get("entry_process") == native
                and events.index(spawn_events[0]) < events.index(entry_events[0]) < events.index(completion[0]),
                "native entry was not uniquely observed and SHA-bound before completion")
        native_identity = {"pid": native_pid, "start_time_clock_ticks": native_birth}
        require(all(native_identity in worker["process_group"].get("known_members", [])
                    for worker in (completed[role], last[role])),
                "native entry birth is absent from terminal ownership history")
        if native_pid == pid:
            require(native_birth == birth, "native leader PID was reused")
        else:
            observed = [member for event in events for worker in event.get("workers", []) if worker.get("role") == role
                        for member in worker.get("process_group", {}).get("live_members", []) or []]
            require(any(type(member.get("pid")) is int and type(member.get("start_time_clock_ticks")) is int
                        and member["pid"] == native_pid and member["start_time_clock_ticks"] == native_birth
                        and member.get("process_group_id") == member.get("session_id") == pid for member in observed),
                    "native child PID/birth was never independently observed in its worker group")
    return [fingerprint(path) for path in paths]


def policy_ticks(plan: dict, selection: dict) -> int:
    return selection["reference_commands"]["frames"] if plan.get("reference_commands") else round(plan["seconds_per_configuration"] / .02)


def validate_reference_replay(directory: Path, selection: dict, cfg: dict, inference: dict) -> None:
    import numpy as np

    reference = selection["reference_commands"]
    metadata = {key: value for key, value in reference.items() if key != "commands"}
    raw_inference = json.loads((directory / "inference.json").read_text())
    if inference != {key: value for key, value in raw_inference.items() if key != "samples"}:
        raise ValueError("Reference inference summary differs from the raw native report")
    inference = raw_inference
    replay, lifecycle = inference["reference_replay"], inference["lifecycle"]
    released = json.loads((directory / "released.json").read_text())
    anchor, decimation = replay["anchor_physics_step"], replay["physics_steps_per_policy_tick"]
    if (cfg.get("reference_motion") != metadata or cfg.get("reference_spawn") is not True
            or cfg != json.loads((directory / "run.json").read_text())
            or replay["sha256"] != reference["sha256"] or replay["frames"] != reference["frames"] or replay["fps"] != 50
            or replay["all_frames_applied"] is not True or replay["reference_qpos_drives_simulation"] is not False
            or replay["spatial_alignment"] != "root XY/yaw only" or type(anchor) is not int or decimation != 10
            or anchor % decimation or not 0 <= anchor - released["physics_step"] < decimation
            or released["physics_steps_per_policy_tick"] != decimation
            or released["reference_motion_sha256"] != reference["sha256"] or released["reference_full_pose_applied"] is not False
            or len(inference["commands"]) != reference["frames"] or len(inference["samples"]) != reference["frames"]):
        raise ValueError("Reference replay metadata, raw reports or control clock mismatch")
    for index, (command, sample) in enumerate(zip(inference["commands"], inference["samples"])):
        step = anchor + index * decimation
        seconds = (step - released["physics_step"]) / 500
        if (command["reference_frame"] != index or command["code"] != reference["codes"][index]
                or command["physics_step"] != step or not math.isclose(command["seconds"], seconds, abs_tol=1e-9)
                or sample["reference_frame"] != index or sample["physics_step"] != step
                or sample["reference_seconds"] != index / 50 or sample["command"] != reference["codes"][index]
                or not math.isclose(sample["simulation_seconds"], seconds, abs_tol=1e-9)
                or sample["velocity_command"] != reference["commands"][index]
                or sample["policy_action_enabled"] is not True or sample["get_ready_state"] is not False
                or any(not math.isfinite(float(sample[key])) for key in ("wall_seconds", "target_min", "target_max", "action_l2"))):
            raise ValueError("Reference replay skipped, repeated or changed a policy frame/label")
    clips = lifecycle["recording_toggle_and_stop_autosave"]
    if (lifecycle.get("damping_command_sent") is not True or lifecycle["damping_kp_max"] != 0
            or not math.isfinite(lifecycle["damping_kd_min"]) or lifecycle["damping_kd_min"] <= 0 or len(clips) != 1):
        raise ValueError("Reference replay requires native recording and damping delivery")
    clip, frames = clips[0], reference["frames"]
    recording_path = directory / clip["file"]
    recording = recording_path.resolve()
    if (not recording.is_relative_to(directory.resolve()) or recording_path.is_symlink() or not recording.is_file()
            or clip["frames"] != frames or clip["fps"] != 50 or clip["qpos_shape"] != [frames, 36]
            or clip["vel_cmd_shape"] != [frames, 15]):
        raise ValueError("Reference recording identity or schema mismatch")
    with np.load(recording, allow_pickle=False) as archive:
        qpos, labels, fps = archive["qpos"], archive["vel_cmd"], archive["fps"]
        if (qpos.shape != (frames, 36) or not np.isfinite(qpos).all()
                or not np.allclose(np.linalg.norm(qpos[:, :4], axis=1), 1, atol=1e-3)
                or fps.size != 1 or float(fps.reshape(-1)[0]) != 50
                or labels.shape != (frames, 15) or not np.array_equal(labels, reference["commands"])):
            raise ValueError("Reference recording actual frames or labels mismatch")


def validate_result(path: Path, plan: dict, selection: dict) -> dict:
    result = json.loads(path.read_text())
    cfg, sim, inference = result["config"], result["simulation"], result["inference"]
    reference = selection.get("reference_commands") if plan.get("reference_commands") else None
    expected_ticks = policy_ticks(plan, selection)
    duration = expected_ticks / 50 if reference else plan["seconds_per_configuration"]
    if (result.get("status") != "completed" or sim.get("status") != "completed" or inference.get("status") != "completed"
            or cfg["model_sha256"] != plan["model_sha256"] or cfg["mesh_sha256"] != selection["mesh_sha256"]
            or cfg["mesh"] != selection["mesh"] or cfg["models"] != str(Path(plan["models"][0]["path"]).parent)
            or cfg["commands"] != (reference["codes"] if reference else [selection["command"]]) or cfg["seed"] != plan["seed"]
            or cfg["gl"] != selection["launch"][selection["launch"].index("--gl") + 1]
            or cfg["duration"] != duration or cfg["record_policy"] is not bool(reference) or cfg["course_guide"]
            or cfg.get("python_faulthandler") is not True or "--python-faulthandler" not in selection["launch"]
            or inference["ticks"] != expected_ticks or inference["control_period_simulation_seconds"] != .02
            or not inference["lifecycle"]["damping_mode_active"] or not inference["lifecycle"]["policy_action_disabled"]
            or not sim["gantry_disabled_during_policy"] or sim["policy_simulation_seconds"] < cfg["duration"]
            or result.get("quality_verified") is not False or result.get("obstacle_course_completion_verified") is not False):
        raise ValueError("Native closed-loop result identity, duration, ticks or lifecycle mismatch")
    if reference:
        validate_reference_replay(path.parent, selection, cfg, inference)
    validate_worker_receipts(path.parent, plan, result)
    rows = list(csv.DictReader((path.parent / "trajectory.csv").open()))
    if not rows or any(not math.isfinite(float(value)) for row in rows for value in row.values()):
        raise ValueError("Missing or nonfinite native trajectory")
    active = [row for row in rows if float(row["policy_seconds"]) >= 0]
    if len(active) < expected_ticks or any(float(row["gantry_enabled"]) != 0 for row in active):
        raise ValueError("Insufficient unsupported policy trajectory")
    checks = result["video_checks"]
    if not result["videos"] or {item["video"] for item in checks} != set(result["videos"]):
        raise ValueError("Fresh native video checks are required")
    for check in checks:
        duration = float(check["probe"]["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Native video has no duration")
        for relative in (check["video"], check["thumbnail"]):
            candidate = (path.parent / relative).resolve()
            if not candidate.is_relative_to(path.parent.resolve()) or not candidate.is_file() or not candidate.stat().st_size:
                raise ValueError("Missing or unsafe video evidence path")
    return result


def retain_evidence(directory: Path, plan: dict, selection: dict, launch: list[str], log_path: Path) -> dict:
    result = validate_result(directory / "result.json", plan, selection)
    files = [fingerprint(path) for path in sorted(directory.rglob("*")) if path.is_file()]
    evidence = {"schema_version": 1, "case_input": case_input(plan, selection), "files": files,
                "worker_receipts": validate_worker_receipts(directory, plan, result),
                "execution": {"output": str(directory), "launch": launch, "log": fingerprint(log_path), "returncode": 0},
                "result_sha256": digest(directory / "result.json"), "expected_policy_ticks": policy_ticks(plan, selection),
                "scope": "Native closed-loop execution evidence; survival is heuristic and course completion unverified"}
    target = directory / "case-evidence.json"
    write(target, evidence)
    return {"evidence": fingerprint(target), "result": result}


def verify_completed(attempt: dict, plan: dict, selection: dict) -> None:
    item = attempt["evidence"]
    if digest(Path(item["path"])) != item["sha256"]:
        raise ValueError("Completed case evidence changed; preserve it and use a fresh output")
    evidence = json.loads(Path(item["path"]).read_text())
    if evidence["case_input"] != case_input(plan, selection):
        raise ValueError("Completed case inputs/launch changed")
    if evidence["expected_policy_ticks"] != policy_ticks(plan, selection):
        raise ValueError("Completed case expected policy ticks changed")
    expected_execution = {"output": attempt["output"], "launch": attempt_launch(selection, Path(attempt["output"])),
                          "log": attempt["log"], "returncode": 0}
    if (evidence["execution"] != expected_execution or attempt["launch"] != expected_execution["launch"]
            or attempt["returncode"] != 0):
        raise ValueError("Completed attempt output/launch/log changed")
    if fingerprint(Path(attempt["log"]["path"])) != attempt["log"]:
        raise ValueError("Completed parent log changed")
    for artifact in evidence["files"]:
        if digest(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError(f"Completed artifact changed: {artifact['path']}")
    result_path = Path(attempt["output"]) / "result.json"
    result = validate_result(result_path, plan, selection)
    if evidence.get("worker_receipts") != validate_worker_receipts(result_path.parent, plan, result):
        raise ValueError("Completed native worker receipts changed or were not sealed")
    if not all(item in evidence["files"] for item in evidence["worker_receipts"]):
        raise ValueError("Mandatory native worker receipts are absent from retained hashes")
    if selection.get("result") != result or selection.get("result_report") != str(result_path):
        raise ValueError("Completed matrix result summary changed")


def execute(args, plan: dict) -> dict:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # The lock lives outside child output paths, which native sim2sim requires empty.
    lock_path = args.output.with_name(args.output.name + ".lock")
    with GLOBAL_LOCK.open("a") as global_lock, lock_path.open("a") as lock:
        try:
            fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another matrix driver holds the container-wide DDS lock") from error
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another matrix driver holds this output lock") from error
        return execute_locked(args, plan)


def execute_locked(args, plan: dict) -> dict:
    # Check all native children, including cases excluded by a pilot filter and
    # surviving jobs from a different output. Matrix locks alone cannot survive
    # a killed parent or govern a separately launched manual native harness.
    live = running_children()
    if live:
        raise ValueError(f"Native child still running in this container; do not overlap DDS jobs: {live}")
    target, saved_plan = args.output / "matrix.json", args.output / "plan.json"
    if args.resume:
        if not saved_plan.is_file() or json.loads(saved_plan.read_text()) != plan:
            raise ValueError("Resume requires identical source/model/mesh/dependency/launch/image plan")
        report = json.loads(target.read_text())
        if (any(report.get(key) != value for key, value in plan.items() if key not in ("status", "selections"))
                or len(report["selections"]) != len(plan["selections"])):
            raise ValueError("Resume matrix does not match its immutable plan")
        for expected, existing in zip(plan["selections"], report["selections"]):
            if any(existing.get(key) != value for key, value in expected.items()):
                raise ValueError("Resume case identity changed")
        # No native children remain. Preserve unfinished outputs and close their
        # old receipts before selecting a subset or creating a fresh attempt.
        for selection in report["selections"]:
            for attempt in selection.get("attempts", []):
                if attempt["status"] == "running":
                    attempt.update(status="interrupted", finished_unix=time.time(),
                                   error="Previous matrix driver ended; no live native child remains; raw output retained")
                    selection["status"] = "interrupted"
    else:
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("Use a new empty output directory, or --resume with identical inputs")
        args.output.mkdir(parents=True, exist_ok=True)
        write(saved_plan, plan)
        report = copy.deepcopy(plan)
        report["started_unix"] = time.time()
    selected = [item for item in report["selections"] if not args.case_id or item["case_id"] in set(args.case_id)]
    if args.case_id and len(selected) != len(set(args.case_id)):
        raise ValueError("Unknown --case-id")
    if args.case_limit:
        selected = selected[:args.case_limit]
    report.update(status="running", last_invocation={"case_ids": args.case_id, "case_limit": args.case_limit,
                  "requested_configurations": len(selected), "resume": args.resume, "started_unix": time.time()})
    write(target, report)
    for selection in selected:
        attempts = selection.setdefault("attempts", [])
        completed = bool(attempts and attempts[-1]["status"] == "completed")
        try:
            verify_inputs(plan, selection)
            if completed:
                verify_completed(attempts[-1], plan, selection)
            else:
                live = running_children(Path(selection["output"]))
                if live:
                    raise ValueError(f"Native child still running for this case; do not overlap DDS jobs: {live}")
        except (ValueError, OSError, KeyError, TypeError) as error:
            report.update(status="execution_failed", finished_unix=time.time(),
                          integrity_error={"case_id": selection["case_id"], "error": f"{type(error).__name__}: {error}"})
            write(target, report)
            raise
        if completed:
            print(f"Verified completed case; skipping {selection['case_id']}", flush=True)
            continue
        base = Path(selection["output"])
        number = len(attempts) + 1
        output = base if number == 1 and not base.exists() else base / f"attempt-{number:04d}"
        while output.exists():
            number += 1
            output = base / f"attempt-{number:04d}"
        launch = attempt_launch(selection, output)
        log_path = args.output / (f"{selection['scenario']}.log" if not args.all_configs and not attempts else
                   f"logs/{selection['scenario']}/config-{selection['configuration_index']:04d}/attempt-{number:04d}.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        attempt = {"number": number, "output": str(output), "launch": launch, "status": "running", "started_unix": time.time()}
        attempts.append(attempt)
        selection["status"] = "running"
        write(target, report)
        started = time.monotonic()
        print(f"Starting {selection['case_id']}, attempt {number}", flush=True)
        try:
            with log_path.open("x") as log:
                process = subprocess.run(launch, cwd=ROOT, env=os.environ | plan["runtime_environment"],
                                         stdout=log, stderr=subprocess.STDOUT, check=False)
            attempt["returncode"] = process.returncode
            if process.returncode:
                raise RuntimeError(f"Native child returned {process.returncode}")
            # Catch changes during this case as well as between long-running cases.
            verify_inputs(plan, selection)
            retained = retain_evidence(output, plan, selection, launch, log_path)
            attempt.update(status="completed", evidence=retained["evidence"])
            selection.update(status="completed", result_report=str(output / "result.json"), result=retained["result"],
                             returncode=process.returncode, wall_seconds=time.monotonic() - started)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
            attempt.update(status="execution_failed", error=f"{type(error).__name__}: {error}")
            selection["status"] = "execution_failed"
        finally:
            attempt.update(wall_seconds=time.monotonic() - started, finished_unix=time.time(),
                           log=fingerprint(log_path) if log_path.exists() else None)
            write(target, report)
        print(f"Finished {selection['case_id']}: {selection['status']}", flush=True)
    complete = sum(item.get("status") == "completed" for item in report["selections"])
    failed = any(item.get("status") != "completed" for item in selected)
    covered_scenarios = {item["scenario"] for item in report["selections"] if item.get("status") == "completed"}
    report.update(status="execution_failed" if failed else ("completed" if complete == len(plan["selections"]) else "completed_subset"),
                  finished_unix=time.time(), completed_configurations=complete, completed_scenarios=len(covered_scenarios),
                  configuration_coverage_complete=complete == len(plan["selections"]),
                  heuristic_survival_configurations=sum(bool(item.get("result", {}).get("survival_passed")) for item in report["selections"]),
                  heuristic_survival_scenarios=len({item["scenario"] for item in report["selections"] if item.get("result", {}).get("survival_passed")}))
    write(target, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("/outputs/motion-matching/matrix.json"))
    parser.add_argument("--models", type=Path, default=Path("/data/assets/student"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gl", choices=("egl", "osmesa"), default="egl")
    parser.add_argument("--sim-python", default=os.environ.get("HSSIM_PYTHON", "/opt/php/bin/train-python"))
    parser.add_argument("--inference-python", default=os.environ.get("PHP_INFERENCE_PYTHON", "/opt/php/bin/inference-python"))
    parser.add_argument("--image-id", default=os.environ.get("PHP_RESEARCH_IMAGE_ID", "unrecorded; record Docker image ID externally"))
    parser.add_argument("--plan", action="store_true", help="Verify exact input hashes and write the plan without simulator/inference")
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--all-configs", action="store_true", help="Explicitly select all 629 configurations across 17 scenarios")
    parser.add_argument("--reference-commands", action="store_true", help="Replay every generated NPZ command frame with root XY/yaw alignment and native policy recording; duration comes from each NPZ")
    parser.add_argument("--resume", action="store_true", help="Verify completed case evidence and retain failed/interrupted attempts")
    parser.add_argument("--case-id", action="append", default=[], help="Run an explicit subset by exact plan case_id")
    parser.add_argument("--case-limit", type=int, help="Run only the first N selected cases; recorded as partial coverage")
    args = parser.parse_args()
    if not args.reference_commands and not 8 <= args.seconds <= 12:
        parser.error("Use 8–12 simulated seconds per selected scenario")
    if args.case_limit is not None and args.case_limit < 1:
        parser.error("--case-limit must be positive")
    if args.plan and args.resume:
        parser.error("--plan cannot overwrite an existing --resume run")
    args.output = args.output.resolve()
    report = make_plan(args)
    if args.plan:
        target = args.plan_output or args.output.with_name(args.output.name + "-plan.json")
        if target.exists():
            parser.error("Plan output already exists; preserve it and choose a fresh path")
        write(target, report)
        print(f"Verified {report['planned_scenarios']} scenarios / {report['planned_configurations']} configurations. Plan: {target}", flush=True)
        return
    if not (Path("/.dockerenv").exists() or os.environ.get("PHP_DOCKER") == "1"):
        parser.error("Physical rollout must run inside the research Docker")
    report = execute(args, report)
    if report["status"] == "execution_failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
