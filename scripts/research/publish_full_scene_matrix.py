#!/usr/bin/env python3
"""Publish verified full629 physical evidence, or an explicitly partial preview.

Host standard library only. This tool never starts simulation or edits input
evidence. Full publication requires the frozen plan, successful terminal driver
receipt, all 629 completed cases and every retained input/artifact checksum.
Video, thumbnails and logs are copied byte for byte; plots use measured CSVs.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.sim2sim_scene_matrix import validate_worker_receipts

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_NAMESPACE = None
CHUNK_LIMIT = 25_000_000
SCENARIO_COUNTS = dict(zip((
    "random_locomotion", "low_speed_step", "high_speed_step", "low_speed_climb_58", "high_speed_climb_58",
    "low_speed_climb_76", "high_speed_climb_76", "low_speed_climb_94", "high_speed_climb_94",
    "low_speed_roll_78", "low_speed_roll_90", "high_speed_roll_134", "high_speed_hurdle",
    "high_speed_dash_vault", "high_speed_speed_vault", "high_speed_cat_vault", "high_speed_jump_35"),
    (100, 56, 60, 40, 40, 40, 40, 20, 15, 1, 3, 40, 51, 51, 20, 51, 1)))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_bytes(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"Nonfinite JSON literal: {value}")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def host_path(value: str) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("Parent traversal in retained path")
    if REFERENCE_NAMESPACE is not None:
        for prefix, target in REFERENCE_NAMESPACE:
            if path.is_relative_to(prefix):
                return target / path.relative_to(prefix)
        return path if path.is_absolute() else ROOT / path
    for prefix, target in ((Path("/workspace/php_parkour"), ROOT), (Path("/outputs"), ROOT / "outputs/research"),
                           (Path("/data/assets"), ROOT / "outputs/research/assets")):
        if path.is_relative_to(prefix):
            return target / path.relative_to(prefix)
    return path if path.is_absolute() else ROOT / path


def check_record(record: dict) -> Path:
    path = host_path(record["path"])
    size = record.get("bytes", record.get("size"))
    if not path.is_file() or path.is_symlink() or (size is not None and path.stat().st_size != size) or digest(path) != record["sha256"]:
        raise ValueError(f"Missing or changed retained file: {record['path']}")
    return path


def safe_child(directory: Path, relative: str) -> Path:
    path = (directory / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError(f"Unsafe or missing artifact path: {relative}")
    return path


def option(command: list, flag: str) -> str:
    if command.count(flag) != 1:
        raise ValueError(f"Expected one {flag} in retained argv")
    return command[command.index(flag) + 1]


def validate_parent_exit(start: dict, end: dict | None, helper: Path) -> None:
    """Require the independent launcher's actual wait, never an inferred exit."""
    if (start.get("helper_sha256") != digest(helper)
            or start.get("argv", [])[:3] != ["/usr/bin/python3", "-B", str(helper.resolve())]
            or end is None or end.get("actual_wait_returncode") != 0
            or not end.get("finished_utc") or end.get("pending_signals")
            or any(end.get(key) != value for key, value in start.items())):
        raise ValueError("Independent actual parent exit0 or helper identity missing/changed")


def command_runs(codes: list[int]) -> list[dict]:
    runs, start = [], 0
    for end in range(1, len(codes) + 1):
        if end == len(codes) or codes[end] != codes[start]:
            runs.append({"start_frame": start, "end_frame_exclusive": end,
                         "code": codes[start], "seconds": (end - start) / 50})
            start = end
    return runs


def reference_info(row: dict) -> dict:
    reference = row["reference_commands"]
    frames, codes, commands = reference["frames"], reference["codes"], reference["commands"]
    motion = [item for item in row["source_files"] if item["path"].endswith("_motion.npz")]
    if (type(frames) is not int or frames < 1 or reference["fps"] != 50
            or len(codes) != frames or len(commands) != frames or len(motion) != 1
            or reference["path"] != motion[0]["path"] or reference["sha256"] != motion[0]["sha256"]
            or reference["bytes"] != motion[0].get("bytes", motion[0].get("size"))
            or reference["unique_codes"] != sorted(set(codes))
            or reference["root_body"] != "pelvis" or reference["root_body_index"] != 0
            or reference["quaternion_order"] != "wxyz"):
        raise ValueError("Reference motion identity, 50 FPS or frame metadata mismatch")
    for code, vector in zip(codes, commands):
        if (type(code) is not int or not 0 <= code <= 11 or len(vector) != 15
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
                or vector != [float(index == code) for index in range(15)]):
            raise ValueError("Reference commands must retain exact finite onehot codes 0..11")
    duration = frames / 50
    if row["policy_seconds"] != duration or row["reference_clip_seconds"] != duration:
        raise ValueError("Reference duration must equal frames / 50 without resampling")
    launch = row["launch"]
    if (option(launch, "--reference-motion") != reference["path"]
            or launch.count("--reference-spawn") != 1 or launch.count("--record-policy") != 1
            or "--commands" in launch or "--seconds-per-command" in launch):
        raise ValueError("Reference launch must replay source labels, spawn and record")
    return {"reference_commands": True, "reference_frames": frames, "reference_fps": 50,
            "reference_motion": motion[0], "command_runs": command_runs(codes), "duration": duration}


def validate_plan(plan: dict, matrix: dict, expected_plan: str, expected_harness: str, preview: bool) -> None:
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in (expected_plan, expected_harness)):
        raise ValueError("Explicit expected plan and harness SHA256 are required")
    content = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if identity(content) != plan.get("plan_sha256") or plan.get("plan_sha256") != expected_plan:
        raise ValueError("Frozen plan identity changed")
    expected_total = sum(SCENARIO_COUNTS.values())
    reference = plan.get("reference_commands") is True
    if ("reference_commands" in plan and type(plan["reference_commands"]) is not bool
            or reference and plan.get("schema_version") != 3
            or (plan.get("schema_version") != 3 and not (preview and plan.get("schema_version") == 2)) or plan.get("status") != "planned" or plan.get("all_configurations") is not True
            or plan.get("planned_configurations") != expected_total or plan.get("planned_scenarios") != len(SCENARIO_COUNTS)
            or plan.get("seed") != 42 or plan.get("seconds_per_configuration") != (None if reference else 10)
            or plan.get("quality_verified") is not False or plan.get("obstacle_course_completion_verified") is not False
            or len(plan["selections"]) != expected_total):
        raise ValueError("Expected the fixed 17-scenario/629-configuration, seed42 constant or reference plan")
    if any(matrix.get(k) != v for k, v in plan.items() if k not in ("status", "selections")) or len(matrix["selections"]) != expected_total:
        raise ValueError("Matrix immutable fields differ from the frozen plan")
    if not any(Path(r["path"]).name == "sim2sim_scene_matrix.py" and r["sha256"] == expected_harness for r in plan["dependencies"]):
        raise ValueError("Frozen production harness missing from plan dependencies")
    seen = set()
    ordinal = 0
    for scenario, count in SCENARIO_COUNTS.items():
        for index in range(count):
            p, row = plan["selections"][ordinal], matrix["selections"][ordinal]
            if (p["scenario"] != scenario or p["configuration_index"] != index or p["available_configurations"] != count
                    or p["case_id"] in seen or any(row.get(k) != v for k, v in p.items())):
                raise ValueError("Case order, source index or immutable case identity changed")
            if (len(p["source_files"]) != 3 or {Path(r["path"]).suffix for r in p["source_files"]} != {".npz", ".npy", ".obj"}
                    or not any(r["path"] == p["mesh"] and r["sha256"] == p["mesh_sha256"] for r in p["source_files"])):
                raise ValueError("Invalid motion/terrain/OBJ source triple")
            seen.add(p["case_id"])
            if reference:
                reference_info(p)
            ordinal += 1
    if reference and (plan.get("seconds_per_scenario") is not None
                      or not math.isclose(plan["total_policy_seconds"], sum(row["reference_commands"]["frames"] / 50 for row in plan["selections"]), abs_tol=1e-8)):
        raise ValueError("Reference total duration mismatch")


def validate_driver(receipt: dict, launch: dict, wrapper: Path, plan: dict, matrix: dict, matrix_sha: str, preview: bool, expected_harness: str) -> None:
    if (digest(wrapper) != launch["launcher_sha256"] or launch.get("launch_exit_code") != 0
            or receipt.get("image_id") != plan["image_id"] or launch.get("image_id") != plan["image_id"]
            or receipt.get("harness_sha256") != expected_harness or receipt.get("quality_verified") is not False):
        raise ValueError("Driver wrapper, image or frozen harness identity mismatch")
    command = receipt["command"]
    if ("--all-configs" not in command
            or option(command, "--matrix") != plan["source_matrix"]
            or option(command, "--models") != str(Path(plan["models"][0]["path"]).parent)
            or option(command, "--image-id") != plan["image_id"] or float(option(command, "--seconds")) != 10
            or host_path(option(command, "--output")).resolve() != host_path(plan["selections"][0]["output"]).parent.parent.resolve()
            or not any(Path(arg).name == "sim2sim_scene_matrix.py" for arg in command)):
        raise ValueError("Driver argv is not bound to this fixed full629 plan")
    if preview:
        return
    total = sum(SCENARIO_COUNTS.values())
    if (receipt.get("status") != "completed" or receipt.get("returncode") != 0 or receipt.get("completion_verified") is not True
            or receipt.get("completed_configurations") != total or receipt.get("matrix_sha256") != matrix_sha
            or not receipt.get("finished_utc") or matrix.get("status") != "completed"
            or matrix.get("completed_configurations") != total or matrix.get("completed_scenarios") != len(SCENARIO_COUNTS)
            or matrix.get("configuration_coverage_complete") is not True or not matrix.get("finished_unix")):
        raise ValueError("Full publication requires actual terminal driver exit0 and completed629 matrix/hash/coverage")


def validate_cpu_case(case: dict | None, plan: dict, row: dict, result: dict, evidence: dict, directory: Path) -> None:
    """Bind the CPU container's scientific checks to these exact original bytes."""
    if case is None:
        raise ValueError("Reference publication requires actual CPU per-case validation")
    info = reference_info(row)
    if (case["case_id"] != row["case_id"] or case["native_result_sha256"] != evidence["result_sha256"]
            or case["parent_returncode"] != 0 or case["worker_exit0_empty_groups"] != 2
            or case["policy_ticks"] != info["reference_frames"] or case["policy_seconds"] != info["duration"]
            or case["reference_commands"] is not True or case["command_runs"] != info["command_runs"]
            or case["reference_motion"] != info["reference_motion"]
            or case["quality_verified"] is not False or case["obstacle_course_completion_verified"] is not False):
        raise ValueError("CPU reference case, original labels or result binding mismatch")
    sealed = evidence.get("worker_receipts", [])
    if len(sealed) != 3 or case["worker_receipts"] != sealed or any(record not in evidence["files"] for record in sealed):
        raise ValueError("CPU worker receipt SHA binding mismatch")
    for record in sealed:
        check_record(record)
    workers = load_bytes((directory / "worker-processes.json").read_bytes())
    final = workers["events"][-1]
    if (workers["schema_version"] != 2 or workers["harness_sha256"] != plan["worker_harness_record"]["sha256"]
            or final["event"] != "finally_wait_complete" or final["cleanup_errors"] or final["unreaped_roles"]
            or len(final["workers"]) != 2 or {worker["role"] for worker in final["workers"]} != {"simulator", "inference"}):
        raise ValueError("Reference worker final receipt mismatch")
    for worker in final["workers"]:
        group = worker["process_group"]
        if (worker["returncode"] != 0 or group["live_members"] or group["ownership_state"] != "retired_empty"
                or group["ownership_verified"] is not True or group["ownership_lost"]):
            raise ValueError("Reference native worker did not exit0 with empty owned group")
    clips = result["inference"]["lifecycle"]["recording_toggle_and_stop_autosave"]
    if (len(clips) != 1 or clips[0]["frames"] != info["reference_frames"] or clips[0]["fps"] != 50
            or clips[0]["qpos_shape"] != [info["reference_frames"], 36]
            or clips[0]["vel_cmd_shape"] != [info["reference_frames"], 15]
            or host_path(case["policy_recording"]["path"]).resolve() != safe_child(directory, clips[0]["file"])):
        raise ValueError("CPU reference recording binding mismatch")
    check_record(case["policy_recording"])
    videos = case["videos"]
    if len(videos) != len(result["videos"]) or len(videos) != 1:
        raise ValueError("Full CPU reference video decode required")
    for decoded, relative in zip(videos, result["videos"]):
        path = safe_child(directory, relative)
        argv = decoded["command"]
        if (check_record(decoded).resolve() != path or decoded["returncode"] != 0 or decoded["full_decode"] is not True
                or not argv or Path(argv[0]).name != "ffmpeg" or "-xerror" not in argv
                or option(argv, "-i") != decoded["path"] or argv[-3:] != ["-f", "null", "-"]):
            raise ValueError("CPU full MP4 decode or immutable video binding mismatch")


def validate_case(plan: dict, row: dict, cpu_case: dict | None = None) -> dict:
    if row.get("status") != "completed" or row.get("returncode") != 0 or not row.get("attempts"):
        raise ValueError(f"Case has no successful terminal execution: {row['case_id']}")
    attempt = row["attempts"][-1]
    if attempt.get("status") != "completed" or attempt.get("returncode") != 0:
        raise ValueError("Last attempt is not completed exit0")
    evidence_path = check_record(attempt["evidence"])
    evidence = load_bytes(evidence_path.read_bytes())
    directory = host_path(attempt["output"]).resolve()
    expected_launch = list(row["launch"])
    expected_launch[expected_launch.index("--output") + 1] = attempt["output"]
    expected_input = {k: plan[k] for k in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
        "case_id": row["case_id"], "source_files": row["source_files"], "launch": row["launch"]}
    reference = reference_info(row) if plan.get("reference_commands") is True else None
    ticks = reference["reference_frames"] if reference else 500
    seconds = ticks / 50
    if (evidence_path.resolve() != directory / "case-evidence.json" or evidence["case_input"] != expected_input
            or attempt["launch"] != expected_launch or evidence["execution"] != {
                "output": attempt["output"], "launch": expected_launch, "log": attempt["log"], "returncode": 0}
            or evidence.get("expected_policy_ticks") != ticks):
        raise ValueError("Retained evidence input/attempt/argv/provenance mismatch")
    check_record(attempt["log"])
    retained = set()
    for record in evidence["files"]:
        path = check_record(record).resolve()
        if not path.is_relative_to(directory) or path in retained:
            raise ValueError("Unsafe or duplicate retained artifact")
        retained.add(path)
    result_path = directory / "result.json"
    if row.get("result_report") != str(Path(attempt["output"]) / "result.json") or digest(result_path) != evidence["result_sha256"]:
        raise ValueError("Result report path/checksum mismatch")
    result = load_bytes(result_path.read_bytes())
    if result != row["result"]:
        raise ValueError("Embedded and independent native results differ")
    if plan.get("schema_version") == 3 and not reference:
        receipts = validate_worker_receipts(directory, plan, result, translate=host_path)
        expected_receipts = {host_path(record["path"]).resolve(): record for record in evidence.get("worker_receipts", [])}
        if (len(expected_receipts) != 3 or any(record["sha256"] != expected_receipts.get(Path(record["path"]), {}).get("sha256")
                or record["bytes"] != expected_receipts.get(Path(record["path"]), {}).get("bytes") for record in receipts)):
            raise ValueError("Worker process receipt fingerprints differ from retained evidence")
        required = {directory / name for name in ("worker-processes.json", "simulator-process-start.json", "inference-process-start.json")}
        if not required.issubset(retained):
            raise ValueError("Worker process receipts absent from retained evidence")
    cfg, sim, inference = result["config"], result["simulation"], result["inference"]
    if (any(item.get("status") != "completed" for item in (result, sim, inference)) or cfg["model_sha256"] != plan["model_sha256"]
            or cfg["mesh"] != row["mesh"] or cfg["mesh_sha256"] != row["mesh_sha256"]
            or cfg["models"] != str(Path(plan["models"][0]["path"]).parent)
            or cfg["commands"] != (row["reference_commands"]["codes"] if reference else [row["command"]])
            or cfg["seed"] != plan["seed"] or cfg["gl"] != option(row["launch"], "--gl")
            or cfg["duration"] != seconds or cfg["record_policy"] is not bool(reference) or cfg["course_guide"]
            or inference["ticks"] != ticks or inference["control_period_simulation_seconds"] != .02
            or not inference["lifecycle"]["damping_mode_active"] or not inference["lifecycle"]["policy_action_disabled"]
            or sim["gantry_disabled_during_policy"] is not True or not seconds <= sim["policy_simulation_seconds"] < seconds + .1
            or result.get("quality_verified") is not False or result.get("obstacle_course_completion_verified") is not False
            or type(sim["fall_detected"]) is not bool or result["survival_passed"] is not (not sim["fall_detected"])):
        raise ValueError("Native config/policy ticks/unsupported policy lifecycle or heuristic mismatch")
    if reference:
        if (cfg.get("reference_spawn") is not True
                or cfg.get("reference_motion") != {key: value for key, value in row["reference_commands"].items() if key != "commands"}):
            raise ValueError("Reference spawn or original motion metadata changed")
        validate_cpu_case(cpu_case, plan, row, result, evidence, directory)
    trajectory_path = directory / "trajectory.csv"
    trajectory = list(csv.DictReader(io.StringIO(trajectory_path.read_text())))
    if not trajectory or any(not math.isfinite(float(v)) for r in trajectory for v in r.values()):
        raise ValueError("Missing or nonfinite measured trajectory")
    active = [r for r in trajectory if float(r["policy_seconds"]) >= 0]
    if len(active) < ticks or any(float(r["gantry_enabled"]) != 0 for r in active):
        raise ValueError("Insufficient unsupported trajectory samples")
    checks = result["video_checks"]
    if not checks or len(checks) != len(result["videos"]) or {c["video"] for c in checks} != set(result["videos"]):
        raise ValueError("Missing/duplicate native video checks")
    mandatory = {result_path, trajectory_path}
    for check in checks:
        video, png = (safe_child(directory, check[k]) for k in ("video", "thumbnail"))
        probe = check["probe"]; stream = probe["streams"][0]
        duration = float(probe["format"]["duration"])
        header = png.read_bytes()[:24]
        if (not math.isfinite(duration) or duration <= 0 or min(stream["width"], stream["height"]) <= 0
                or header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (stream["width"], stream["height"])):
            raise ValueError("Invalid video metadata or PNG dimensions")
        mandatory.update((video, png))
    if not mandatory <= retained:
        raise ValueError("Result/trajectory/media absent from retained checksummed evidence")
    # Reject unrecorded additions to completed evidence instead of silently dropping them.
    actual = {p.resolve() for p in directory.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob("*")) or actual != retained | {evidence_path.resolve()}:
        raise ValueError("Completed output file set changed after retention")
    return {"row": row, "directory": directory, "evidence": evidence, "trajectory": active, "result": result}


def owned_attempt_files(directory: Path, all_directories: list[Path]) -> list[Path]:
    """Separate recorded retries; refuse an otherwise silently skipped retry."""
    nested = [p for p in all_directories if p != directory and p.is_relative_to(directory)]
    if not directory.exists():
        return []
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in retained attempt output")
        if any(path == p or path.is_relative_to(p) for p in nested):
            continue
        if path.is_dir() and path.name.startswith("attempt-"):
            raise ValueError("Unrecorded attempt directory would be omitted")
        if path.is_file():
            files.append(path)
    return files


def validate_attempt_archive(plan: dict, row: dict, attempt: dict, all_directories: list[Path]) -> dict:
    directory = host_path(attempt["output"]).resolve()
    files = owned_attempt_files(directory, all_directories)
    expected_launch = list(row["launch"])
    expected_launch[expected_launch.index("--output") + 1] = attempt["output"]
    if attempt["launch"] != expected_launch:
        raise ValueError("Historical attempt launch changed")
    if attempt.get("log"):
        check_record(attempt["log"])
    sealed = bool(attempt.get("evidence"))
    if sealed:
        evidence_path = check_record(attempt["evidence"]).resolve()
        evidence = load_bytes(evidence_path.read_bytes())
        expected_input = {k: plan[k] for k in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
            "case_id": row["case_id"], "source_files": row["source_files"], "launch": row["launch"]}
        if (evidence_path != directory / "case-evidence.json" or evidence["case_input"] != expected_input
                or evidence["execution"] != {"output": attempt["output"], "launch": expected_launch,
                    "log": attempt.get("log"), "returncode": attempt.get("returncode")}):
            raise ValueError("Historical sealed attempt identity/execution changed")
        retained = set()
        for r in evidence["files"]:
            path = check_record(r).resolve()
            if not path.is_relative_to(directory) or path in retained:
                raise ValueError("Unsafe or duplicate historical artifact")
            retained.add(path)
        if retained | {evidence_path} != set(files):
            raise ValueError("Historical sealed artifact set changed")
        if evidence.get("result_sha256") and digest(directory / "result.json") != evidence["result_sha256"]:
            raise ValueError("Historical sealed result checksum changed")
        # Keep the original seal's expectations through copying. Rehashing here
        # would accept a file changed after check_record verified the seal.
        fingerprints = [{**record, "path": str(host_path(record["path"]).resolve())}
                        for record in [*evidence["files"], attempt["evidence"]]]
    else:
        fingerprints = [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]
    # No seal means only the current original bytes can be fingerprinted. This
    # is preserved failed-attempt history, never retroactively verified physics.
    return {"sealed": sealed, "integrity_scope": "retained seal and files verified" if sealed else "unsealed history: current original byte fingerprints only",
            "files": fingerprints}


def reference_namespace(base: Path, receipt: dict) -> list[tuple[Path, Path]]:
    base = base.resolve()
    created = receipt["created_inspect"]
    mounts = created["Mounts"]
    by_destination = {item["Destination"]: item for item in mounts}
    expected = {"/workspace/php_parkour", "/workspace/php_parkour/scripts/research", "/data", "/data/cache", "/checks", "/outputs"}
    if len(mounts) != len(expected) or set(by_destination) != expected:
        raise ValueError("Reference cohort requires the exact six private mount destinations")
    for destination, item in by_destination.items():
        source = Path(item["Source"])
        readonly = destination in {"/workspace/php_parkour", "/workspace/php_parkour/scripts/research", "/data"}
        if item["Type"] != "bind" or item["RW"] is readonly or not source.is_dir() or source.is_symlink():
            raise ValueError("Reference mount type, access or source differs")
        local = {"/workspace/php_parkour/scripts/research": "overlay", "/data/cache": "cache", "/checks": "checks", "/outputs": "outputs"}
        if destination in local and source.resolve() != base / local[destination]:
            raise ValueError("Reference writable/overlay mount is outside its own cohort")
    return [(Path(destination), Path(by_destination[destination]["Source"]).resolve()) for destination in
            ("/workspace/php_parkour/scripts/research", "/workspace/php_parkour", "/outputs", "/data")]


def validate_reference_driver(receipt: dict, start: dict, exit_receipt: dict | None, wrapper: Path,
                              plan: dict, matrix: dict, matrix_sha: str, preview: bool) -> None:
    wrapper_sha = digest(wrapper)
    helper = check_record(receipt["helper"])
    process = receipt["host_process"]
    fields = start["stat"][start["stat"].rfind(")") + 2:].split()
    if (helper.resolve() != wrapper.resolve() or start["helper_sha256"] != wrapper_sha
            or start["argv"] != ["/usr/bin/python3", "-B", str(wrapper.resolve()), "--root-authorized-start"]
            or start["pid"] != process["pid"] or int(fields[19]) != process["start_time_clock_ticks"]
            or start["boot_id"] != receipt["boot_id"] or receipt["image_id"] != plan["image_id"]
            or receipt["quality_verified"] is not False or receipt["obstacle_course_completion_verified"] is not False):
        raise ValueError("Reference controller source or actual parent start identity mismatch")
    cid = receipt["container_id"]
    command = receipt["native"]["argv"]
    if (not re.fullmatch("[0-9a-f]{64}", cid) or command[:5] != ["docker", "exec", cid, "/opt/php/bin/inference-python", "-B"]
            or Path(command[5]).name != "sim2sim_scene_matrix.py" or command.count("--all-configs") != 1
            or command.count("--reference-commands") != 1
            or any(flag in command for flag in ("--resume", "--plan", "--case-id", "--case-limit", "--seconds"))
            or option(command, "--matrix") != plan["source_matrix"] or option(command, "--image-id") != plan["image_id"]
            or option(command, "--models") != str(Path(plan["models"][0]["path"]).parent)
            or Path(option(command, "--output")) != Path(plan["selections"][0]["output"]).parent.parent):
        raise ValueError("Reference controller native argv differs from the full frozen plan")
    created, running = receipt["created_inspect"], receipt["running_inspect"]
    for inspect in (created, running):
        if (inspect["Id"] != cid or inspect["Image"] != plan["image_id"]
                or inspect["Name"] != "/" + receipt["container_name"]
                or inspect["Config"]["Labels"].get("php.reference629.owner") != receipt["ownership_token"]):
            raise ValueError("Reference exact own container identity mismatch")
    source = receipt["source_before"]
    for name in ("freeze_manifest", "source_matrix", "cpu_reference_plan", "observer"):
        check_record(source[name])
    for name, item in receipt["overlay"].items():
        for kind in ("source", "copy"):
            check_record(item[kind])
        if not any(record["sha256"] == item["copy"]["sha256"] and Path(record["path"]).name == name for record in plan["dependencies"]):
            raise ValueError("Reference overlay is not bound to planned dependencies")
    if digest(check_record(receipt["prelaunch_plan"])) != source["cpu_reference_plan"]["sha256"]:
        raise ValueError("Reference prelaunch plan differs from actual CPU plan")
    if preview:
        return
    validate_parent_exit(start, exit_receipt, wrapper)
    if (receipt["status"] != "native_reference629_completed_worker1258_hostwriter1258"
            or receipt["errors"] or receipt["cleanup_errors"] or receipt.get("pending_signals")
            or receipt["native"].get("actual_wait_returncode") != 0 or receipt["observer"].get("actual_wait_returncode") != 0
            or receipt["completed_configurations"] != len(plan["selections"])
            or receipt["completed_scenarios"] != len(SCENARIO_COUNTS)
            or receipt["native_workers_exit0"] != 2 * len(plan["selections"])
            or receipt["source_before"] != receipt["source_after"]
            or matrix["status"] != "completed" or matrix["configuration_coverage_complete"] is not True
            or matrix["completed_configurations"] != len(plan["selections"])):
        raise ValueError("Reference full publication requires real parent/native/observer exit0 and complete629")
    for name in ("native_plan", "native_matrix", "observer_summary"):
        check_record(receipt[name])
    if (receipt["native_plan"]["sha256"] != source["cpu_reference_plan"]["sha256"]
            or receipt["native_matrix"]["sha256"] != matrix_sha):
        raise ValueError("Reference terminal plan/matrix differs from the controller proof")
    stop = receipt["owned_container_stop"]
    if (stop["container_id"] != cid or stop["running_after_stop"] is not False
            or stop["after"]["State"]["Running"] is not False
            or any(stop["after"][key] != running[key] for key in ("Id", "Image", "Name"))
            or stop["after"]["State"]["StartedAt"] != running["State"]["StartedAt"]):
        raise ValueError("Reference exact own GPU container stop is unverified")
    observed = load_bytes(check_record(receipt["observer_summary"]).read_bytes())
    if observed["mapping_scope_complete"] is not True or observed["errors"] or observed["stop_reason"] != "stop_file":
        raise ValueError("Reference observer did not complete its actual mapping scope")
    retained = receipt["host_native_mappings"]
    expected = {(row["case_id"], role): row for row in matrix["selections"] for role in ("simulator", "inference")}
    if len(retained) != len(expected) or len({(item["case_id"], item["role"]) for item in retained}) != len(expected):
        raise ValueError("Reference full1258 host writer coverage missing or duplicate")
    identities = set()
    for item in retained:
        row = expected[(item["case_id"], item["role"])]
        entry_path = check_record(item["entry"])
        if entry_path.resolve() != host_path(row["output"]) / (item["role"] + "-process-start.json"):
            raise ValueError("Reference host mapping entry belongs to another case")
        entry = load_bytes(entry_path.read_bytes())["process"]
        matches = [mapping for mapping in observed["command_writer_mappings"] if mapping["role"] == item["role"]
                   and mapping["worker_output"] == row["output"] and mapping["container_tgid"] == entry["pid"]
                   and mapping["owner_start_time_clock_ticks"] == entry["start_time_clock_ticks"]]
        if len(matches) != 1 or matches[0] != item["mapping"]:
            raise ValueError("Reference host writer is missing, ambiguous or has another birth")
        key = (item["mapping"]["host_tid"], item["mapping"]["start_time_clock_ticks"])
        if key in identities:
            raise ValueError("Reference host writer identity reused between workers")
        identities.add(key)


def validate_cpu_report(report: dict, plan: dict, matrix_sha: str, plan_file_sha: str,
                        preview: bool, rows: list[dict]) -> dict[str, dict]:
    ticks = sum(row["reference_commands"]["frames"] for row in rows)
    if (report["status"] != ("preview_validated" if preview else "passed")
            or report["preview"] is not preview or report["completion_verified"] is not (not preview)
            or report["reference_commands"] is not True or report["native_plan_sha256"] != plan["plan_sha256"]
            or report["native_plan_file_sha256"] != plan_file_sha
            or (not preview and report["matrix_sha256"] != matrix_sha)
            or report["planned_configurations"] != len(plan["selections"])
            or report["planned_scenarios"] != len(SCENARIO_COUNTS)
            or report["planned_total_policy_ticks"] != sum(row["reference_commands"]["frames"] for row in plan["selections"])
            or report["configurations"] != len(rows) or report["scenarios"] != len({row["scenario"] for row in rows})
            or report["worker_exit0_empty_group_count"] != 2 * len(rows)
            or report["full_decoded_mp4_count"] != len(rows) or report["total_policy_ticks"] != ticks
            or report["quality_verified"] is not False or report["obstacle_course_completion_verified"] is not False):
        raise ValueError("Reference CPU validation is incomplete, stale or has another scope")
    cases = {case["case_id"]: case for case in report["cases"]}
    if (len(cases) != len(rows) or len(report["cases"]) != len(rows) or set(cases) != {row["case_id"] for row in rows}
            or set(report["selected_case_ids"]) != set(cases) or len(report["selected_case_ids"]) != len(rows)):
        raise ValueError("Reference CPU cases omitted, duplicated or relabeled")
    planned = [plan["source_matrix_record"], *plan["dependencies"], *plan["models"],
               *(record for row in rows for record in row["source_files"])]
    normalize = lambda record: (record["path"], record.get("bytes", record.get("size")), record["sha256"])
    if {normalize(record) for record in report["inputs"]} != {normalize(record) for record in planned}:
        raise ValueError("Reference CPU inputs differ from the complete selected dependency closure")
    if not any(report["matrix_validator"] == record for record in plan["dependencies"]):
        raise ValueError("Reference CPU validator is not the frozen planned matrix")
    return cases


def validate_cpu_execution(context: dict, plan: dict, receipt: dict, preview: bool) -> None:
    execution, report = context["cpu_execution"], context["cpu_validation"]
    start, end = context["cpu_parent_start"], context["cpu_parent_exit"]
    runner = check_record(execution["helper"])
    validator = check_record(execution["validation_helper"])
    validate_parent_exit(start, end, runner)
    if (execution["status"] != "completed" or execution["preview"] is not preview
            or execution["actual_wait_returncode"] != 0 or execution["image_id"] != plan["image_id"]
            or execution["errors"] or execution["cleanup_errors"]
            or execution["source_before"] != execution["source_after"]
            or execution["source_before"] != receipt["source_before"]
            or check_record(execution["validation_report"]).resolve() != context["cpu_validation_path"].resolve()
            or report["helper"]["sha256"] != digest(validator)
            or report["helper"]["bytes"] != validator.stat().st_size
            or start["helper_sha256"] != digest(runner)):
        raise ValueError("Reference CPU report lacks its actual independent parent exit0 execution")
    cid = execution["container_id"]
    created, running = execution["created_inspect"], execution["running_inspect"]
    stop = execution["owned_container_stop"]
    hc = created["HostConfig"]
    if (created["Id"] != cid or created["Image"] != plan["image_id"] or hc["Runtime"] != "runc"
            or hc.get("DeviceRequests") or hc.get("Devices") or hc["NetworkMode"] != "none"
            or hc["IpcMode"] != "private" or hc.get("PidMode") or hc["Privileged"] or hc["Init"] is not True
            or stop["container_id"] != cid or stop["running_after_stop"] is not False
            or stop["after"]["State"]["Running"] is not False
            or any(stop["after"][key] != running[key] or running[key] != created[key] for key in ("Id", "Image", "Name"))
            or stop["after"]["State"]["StartedAt"] != running["State"]["StartedAt"]):
        raise ValueError("Reference CPU own container isolation or actual stopped identity mismatch")
    command = execution["command"]
    if (command[:6] != ["docker", "exec", cid, "/opt/php/bin/inference-python", "-B", "/control/validate_scene_matrix.py"]
            or option(command, "--matrix") != "/outputs/reference629/matrix.json"
            or option(command, "--matrix-module") != "/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py"
            or option(command, "--plan") != "/plan.json" or option(command, "--output") != "/validation/validation.json"
            or (not preview and "--preview-case-id" in command)):
        raise ValueError("Reference CPU actual argv differs from the complete validation scope")
    selected = [command[index + 1] for index, flag in enumerate(command) if flag == "--preview-case-id"]
    if selected != (report["selected_case_ids"] if preview else []):
        raise ValueError("Reference CPU actual preview selection differs from its validated cases")
    if not preview:
        gate = execution["native_terminal_gate"]
        for name in ("controller_receipt", "parent_start", "parent_exit"):
            if check_record(gate[name]).resolve() != context[name + "_path"].resolve():
                raise ValueError("Reference CPU terminal admission is bound to another native parent")
        if (gate["native_workers_exit0"] != 2 * len(plan["selections"])
                or gate["host_writer_mappings"] != 2 * len(plan["selections"])
                or gate["stopped_native_container"]["Id"] != receipt["container_id"]
                or gate["stopped_native_container"]["State"]["Running"] is not False
                or gate["stopped_native_container"]["State"]["StartedAt"] != receipt["running_inspect"]["State"]["StartedAt"]):
            raise ValueError("Reference CPU native terminal admission is incomplete")


def validate_all(plan: dict, matrix: dict, receipt: dict, launch: dict, wrapper: Path, matrix_sha: str, preview_count=0, *, expected_plan=None, expected_harness=None, reference_context=None) -> list[dict]:
    validate_plan(plan, matrix, expected_plan, expected_harness, bool(preview_count))
    reference = plan.get("reference_commands") is True
    if reference:
        if reference_context is None:
            raise ValueError("Reference publication requires its explicit actual controller/CPU context")
        validate_reference_driver(receipt, reference_context["parent_start"], reference_context.get("parent_exit"),
                                  wrapper, plan, matrix, matrix_sha, bool(preview_count))
        validate_cpu_execution(reference_context, plan, receipt, bool(preview_count))
    else:
        validate_driver(receipt, launch, wrapper, plan, matrix, matrix_sha, bool(preview_count), expected_harness)
    for record in [plan["source_matrix_record"], *plan["dependencies"], *plan["models"],
                   *(record for row in plan["selections"] for record in row["source_files"])]:
        check_record(record)
    rows = matrix["selections"]
    if preview_count:
        if type(preview_count) is not int or not 1 <= preview_count <= 2:
            raise ValueError("Preview is restricted to one or two actual completed cases")
        requested = set(reference_context["cpu_validation"]["selected_case_ids"]) if reference else None
        rows = [r for r in rows if r.get("status") == "completed" and (requested is None or r["case_id"] in requested)][:preview_count]
        if len(rows) != preview_count:
            raise ValueError("Preview lacks requested completed real cases")
    cpu_cases = validate_cpu_report(reference_context["cpu_validation"], plan, matrix_sha,
                                   reference_context["plan_file_sha256"], bool(preview_count), rows) if reference else {}
    verified = []
    for row in rows:
        item = validate_case(plan, row, cpu_cases.get(row["case_id"]))
        directories = [host_path(a["output"]).resolve() for a in row["attempts"]]
        if len(set(directories)) != len(directories) or len({a["number"] for a in row["attempts"]}) != len(directories):
            raise ValueError("Duplicate retained attempt directory or number")
        item["attempt_archives"] = [validate_attempt_archive(plan, row, a, directories) for a in row["attempts"]]
        verified.append(item)
    return verified


def trajectory_svg(rows: list[dict]) -> str:
    points = [(float(r["x_m"]), float(r["y_m"])) for r in rows]
    xs, ys = zip(*points); lowx, highx, lowy, highy = min(xs), max(xs), min(ys), max(ys)
    scale = min(570 / max(highx - lowx, .1), 300 / max(highy - lowy, .1))
    def xy(x, y): return 45 + (x - lowx) * scale, 340 - (y - lowy) * scale
    path = " ".join(f"{px:.2f},{py:.2f}" for px, py in (xy(x, y) for x, y in points))
    start, end = xy(*points[0]), xy(*points[-1])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 390" role="img" aria-label="Measured world XY trajectory">'
            '<rect width="660" height="390" fill="#142334"/><g fill="#cbd8e8" font-family="sans-serif" font-size="14">'
            f'<text x="24" y="25">Measured world XY (m), policy stage; +Y upward</text><text x="24" y="373">'
            f'X [{lowx:.3f}, {highx:.3f}], Y [{lowy:.3f}, {highy:.3f}] — start circle, end cross</text></g>'
            f'<polyline points="{path}" fill="none" stroke="#80c7ff" stroke-width="2"/>'
            f'<circle cx="{start[0]:.2f}" cy="{start[1]:.2f}" r="5" fill="#74e5ab"/>'
            f'<path d="M{end[0]-5:.2f},{end[1]-5:.2f}l10,10m0,-10l-10,10" stroke="#ffc48a" stroke-width="3"/></svg>')


def make_page(summary: dict, cases: list[dict]) -> str:
    data = json.dumps(cases, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    title = "PREVIEW · 2-case interface check" if summary["preview"] else "G1 · all 629 configuration rollouts"
    if summary["preview"]:
        title = f'PREVIEW · {len(cases)} cases · full629 not certified'
        if summary.get("legacy_normal_exit_unverified"):
            title += ' · historical status, worker exits unverified'
    reference = summary.get("reference_commands", False)
    coverage_text = ("固定计划的629配置按各自生成NPZ的50Hz完整意图标签运行物理策略；帧数/时长依原片段，保留部署起始站姿，仅对齐root XY/yaw。"
                     if reference else "固定计划的629个配置均完成10秒物理rollout及500策略ticks。")
    mode_text = ("输入是逐帧15维onehot reference代码序列；本页逐段列出实际验证过的代码、帧范围和时长。"
                 if reference else "恒定forward输入；不是reference replay。")
    raw_links = summary.get("raw_links", {})
    scene_options = ''.join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in SCENARIO_COUNTS)
    scene_rows = ''.join(f'<tr><td>{html.escape(r["scenario"])}</td><td>{r["configurations"]}</td><td>{r["threshold_events"]}</td><td>{r["no_threshold_events"]}</td></tr>' for r in summary["scenarios"])
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + html.escape(title) + '''</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#101a27;color:#edf4fc;font:15px/1.6 system-ui;margin:0;padding:24px}header,.toolbar,.pager,main,footer{max-width:1500px;margin:0 auto 22px}h1{font-size:29px;margin:0}a{color:#92c9ff}p{color:#c0d0e0}.warning{padding:14px;background:#503627;border:1px solid #bc8357;border-radius:8px}.toolbar,.pager{display:flex;gap:10px;flex-wrap:wrap;align-items:center}input,select,button{font:inherit;color:inherit;background:#23374d;border:1px solid #647c95;border-radius:6px;padding:8px}input{min-width:240px;flex:1}button{cursor:pointer}button:disabled{opacity:.4}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:20px}article{background:#1d2e43;padding:17px;border-radius:10px;min-width:0}h2{font-size:19px;margin:0}.name,code{overflow-wrap:anywhere}.small{font-size:12px}.badge{display:inline-block;border-radius:20px;padding:3px 10px;background:#285542}.threshold{background:#713c2c}video,img{display:block;width:100%;background:#101923;border-radius:5px}video{aspect-ratio:16/9}.facts{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px}.facts span{padding:4px;background:#142338}details{margin:12px 0}summary{cursor:pointer}table{border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #41536a;padding:5px 14px;text-align:left}.preview{color:#ffc27f}footer{font-size:13px;color:#a8bed4}
</style></head><body><header><h1>''' + html.escape(title) + '''</h1><p class="warning">''' + (
        ('本页仅为两例以内的历史reported completed身体数据预览；旧监督未证明全部worker正常退出，不能作为通过验收。'
         if summary.get('legacy_normal_exit_unverified') else
         '本页仅为两例以内的实际结果预览，测试离线页面与媒体；完整629扫描尚未通过发布门卫。') if summary['preview'] else
        coverage_text + '629是配置数量，不代表629种独立几何，更不代表629种技能成功。') + '''
使用发布学生ONNX、原生DDS/深度SHM、MuJoCo/PD，''' + mode_text + '''所有高度/倾斜阈值事件与历史失败attempt原样保留。未触发阈值不等于课程完成；正常攀爬也可能触发倾斜阈值。quality_verified=false。</p>
<p><a href="summary.json">机器汇总</a> · <a href="cases.json">逐配置JSON</a> · <a href="cases.csv">逐配置CSV</a> · <a href="''' + html.escape(raw_links.get("matrix.json", "matrix.json")) + '''">原始matrix/分块描述</a> · <a href="''' + html.escape(raw_links.get("plan.json", "plan.json")) + '''">固定plan/分块描述</a> · <a href="evidence-manifest.json">完整SHA清单</a></p>
<details><summary>17场景统计（阈值不是技能成功率）</summary><table><thead><tr><th>场景</th><th>本页配置</th><th>高度/倾斜事件</th><th>未触发</th></tr></thead><tbody>''' + scene_rows + '''</tbody></table></details></header>
<div class="toolbar"><input id="search" type="search" placeholder="搜索场景、配置、case ID、mesh SHA" aria-label="搜索配置"><select id="scene" aria-label="场景"><option value="all">全部场景</option>''' + scene_options + '''</select><select id="state" aria-label="阈值"><option value="all">全部结果</option><option value="threshold">触发高度/倾斜阈值</option><option value="unflagged">未触发阈值</option></select><span id="visible"></span></div>
<div class="pager"><button id="previous">上一页</button><span id="page"></span><button id="next">下一页</button></div><main id="cards"></main><footer>视频、PNG、JSON、CSV和日志均从原证据逐字节复制。世界XY图只绘制CSV中的policy阶段实际位置，未平滑或改写轨迹。媒体按页加载；file://或标准库HTTP服务均可离线使用。</footer>
<script id="case-data" type="application/json">''' + data + '''</script><script>
const cases=JSON.parse(document.getElementById('case-data').textContent),search=document.getElementById('search'),scene=document.getElementById('scene'),state=document.getElementById('state');let page=0,selected=cases;const pageSize=24;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v).toFixed(3);
function render(){const pages=Math.max(1,Math.ceil(selected.length/pageSize));page=Math.min(page,pages-1);document.getElementById('visible').textContent=selected.length+' / '+cases.length+' 配置';document.getElementById('page').textContent=(page+1)+' / '+pages;document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page===pages-1;
document.getElementById('cards').innerHTML=selected.slice(page*pageSize,(page+1)*pageSize).map(r=>`<article data-case="${esc(r.case_id)}" data-state="${r.threshold_event?'threshold':'unflagged'}"><h2>${esc(r.scenario)} · ${r.configuration_index}</h2><span class="badge ${r.threshold_event?'threshold':''}">${r.threshold_event?'触发高度/倾斜阈值':'本次未触发阈值'}</span><p class="name small">${esc(r.configuration)}</p>${r.videos.map(v=>`<video controls preload="none" poster="${esc(v.thumbnail)}" src="${esc(v.path)}"></video><p class="small"><a href="${esc(v.path)}">原始MP4</a> · ${num(v.duration_seconds)}s · ${v.width}×${v.height}</p>`).join('')}<div class="facts"><span>${r.policy_ticks} ticks · ${num(r.policy_seconds)}s</span><span>${r.reference_commands?'reference 50 Hz · '+r.reference_frames+' frames':'command '+r.command} · seed42</span><span>最低pelvis ${num(r.minimum_pelvis_height_m)}m</span><span>最低up ${num(r.minimum_base_up_z)}</span><span>XY路径 ${num(r.path_length_xy_m)}m</span><span>末态up ${num(r.final_base_up_z)}</span></div>${r.reference_commands?`<details class="commands"><summary>50Hz reference逐段代码序列 (${r.command_runs.length}段)</summary><p class="small">source NPZ SHA ${esc(r.reference_motion.sha256)}；frame区间为[start,end)，时间从policy anchor开始，未重采样。</p><table><thead><tr><th>代码</th><th>帧[start,end)</th><th>起止秒</th><th>时长</th></tr></thead><tbody>${r.command_runs.map(run=>`<tr><td>${run.code}</td><td>[${run.start_frame}, ${run.end_frame_exclusive})</td><td>${num(run.start_frame/50)}–${num(run.end_frame_exclusive/50)}</td><td>${num(run.seconds)}s</td></tr>`).join('')}</tbody></table><a href="${esc(r.policy_recording)}">原生SDK策略录制NPZ（root XYZ为占位零，物理位置见CSV）</a></details>`:''}<details class="trajectory"><summary>实际世界XY轨迹与截图</summary><img loading="lazy" src="${esc(r.trajectory_svg)}" alt="Measured world XY trajectory">${r.videos.map(v=>`<a href="${esc(v.thumbnail)}"><img loading="lazy" src="${esc(v.thumbnail)}" alt="Original decoded thumbnail"></a>`).join('')}<a href="${esc(r.trajectory_csv)}">原始world XYZ/倾斜CSV</a></details><details><summary>SHA、原始结果和全部attempt</summary><p class="small">OBJ SHA ${esc(r.mesh_sha256)}。${r.attempts.length} 次attempt；失败记录未删除。${r.reference_commands?'按原生成reference代码逐帧控制；技能成功仍未验定。':'没有按reference技能序列控制。'}</p><p><a href="${esc(r.result_json)}">result JSON</a> · <a href="${esc(r.case_evidence)}">case-evidence</a> · <a href="${esc(r.attempts_json)}">全部attempt原始文件链接</a></p></details></article>`).join('');}
function filter(){const q=search.value.toLowerCase();selected=cases.filter(r=>(r.case_id+' '+r.configuration+' '+r.mesh_sha256).toLowerCase().includes(q)&&(scene.value==='all'||r.scenario===scene.value)&&(state.value==='all'||(r.threshold_event?'threshold':'unflagged')===state.value));page=0;render();}search.addEventListener('input',filter);scene.addEventListener('change',filter);state.addEventListener('change',filter);document.getElementById('previous').onclick=()=>{page--;render();};document.getElementById('next').onclick=()=>{page++;render();};filter();
</script></body></html>'''


def publish(args) -> dict:
    """The explicit cohort namespace is scoped to this one publication call."""
    global REFERENCE_NAMESPACE
    previous = REFERENCE_NAMESPACE
    inputs = None
    if getattr(args, "reference_cohort", None) is not None:
        paths = {"plan.json": args.plan, "matrix.json": args.matrix, "driver-receipt.json": args.driver_receipt,
                 "parent-start.json": args.parent_start, "cpu-validation.json": args.cpu_validation,
                 "cpu-execution.json": args.cpu_execution_receipt,
                 "cpu-parent-start.json": args.cpu_parent_start, "cpu-parent-exit.json": args.cpu_parent_exit}
        if getattr(args, "parent_exit", None) is not None:
            paths["parent-exit.json"] = args.parent_exit
        if any(path is None for path in paths.values()):
            raise ValueError("Reference publication requires actual native and CPU execution/parent evidence")
        inputs = {name: path.read_bytes() for name, path in paths.items()}
        REFERENCE_NAMESPACE = reference_namespace(args.reference_cohort, load_bytes(inputs["driver-receipt.json"]))
    try:
        return _publish(args, inputs)
    finally:
        REFERENCE_NAMESPACE = previous


def _publish(args, reference_raw=None) -> dict:
    output = args.output.resolve()
    preview = bool(args.preview_case_count)
    if preview and not output.is_relative_to((ROOT / "outputs/research").resolve()):
        raise ValueError("Preview output must remain in ignored outputs/research, never published usage_assets")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory; existing evidence is preserved")
    if output.is_relative_to(args.matrix.resolve().parent) or output.is_relative_to(args.driver_receipt.resolve().parent):
        raise ValueError("Publication cannot modify the running/raw evidence directory")
    if reference_raw is None and getattr(args, "driver_launch", None) is None:
        raise ValueError("Constant mode requires its original --driver-launch receipt")
    raw = reference_raw or {name: path.read_bytes() for name, path in (("plan.json", args.plan), ("matrix.json", args.matrix),
           ("driver-receipt.json", args.driver_receipt), ("driver-launch.json", args.driver_launch))}
    plan, matrix, receipt = (load_bytes(raw[name]) for name in ("plan.json", "matrix.json", "driver-receipt.json"))
    reference = plan.get("reference_commands") is True
    if reference is not bool(reference_raw):
        raise ValueError("Reference plans require --reference-cohort; constant plans use the original driver contract")
    launch = load_bytes(raw["driver-launch.json"]) if not reference else {}
    context = None
    if reference:
        context = {"parent_start": load_bytes(raw["parent-start.json"]),
                   "parent_exit": load_bytes(raw["parent-exit.json"]) if "parent-exit.json" in raw else None,
                   "cpu_validation": load_bytes(raw["cpu-validation.json"]),
                   "cpu_execution": load_bytes(raw["cpu-execution.json"]),
                   "cpu_parent_start": load_bytes(raw["cpu-parent-start.json"]),
                   "cpu_parent_exit": load_bytes(raw["cpu-parent-exit.json"]),
                   "plan_file_sha256": hashlib.sha256(raw["plan.json"]).hexdigest(),
                   "cpu_validation_path": args.cpu_validation, "controller_receipt_path": args.driver_receipt,
                   "parent_start_path": args.parent_start, "parent_exit_path": args.parent_exit}
    verified = validate_all(plan, matrix, receipt, launch, args.driver_wrapper, hashlib.sha256(raw["matrix.json"]).hexdigest(), args.preview_case_count,
                            expected_plan=args.expected_plan_sha256, expected_harness=args.expected_harness_sha256,
                            reference_context=context)
    expected_copy_hashes = {host_path(r["path"]).resolve(): r["sha256"] for item in verified for r in item["evidence"]["files"]}
    for item in verified:
        for archive in item["attempt_archives"]:
            for record in archive["files"]:
                expected_copy_hashes[Path(record["path"]).resolve()] = record["sha256"]
    for item in verified:
        for attempt in item["row"]["attempts"]:
            for key in ("evidence", "log"):
                if attempt.get(key): expected_copy_hashes[host_path(attempt[key]["path"]).resolve()] = attempt[key]["sha256"]
    expected_copy_hashes[args.driver_wrapper.resolve()] = receipt["helper"]["sha256"] if reference else launch["launcher_sha256"]
    extra_sources = {}
    terminal_trees = []
    if reference:
        execution = context["cpu_execution"]
        for name, record in (("cpu-runner.py", execution["helper"]), ("validate_scene_matrix.py", execution["validation_helper"]),
                             ("original-frozen-manifest.json", receipt["source_before"]["freeze_manifest"]),
                             ("observe_container_pids.py", receipt["source_before"]["observer"])):
            path = check_record(record)
            expected_copy_hashes[path.resolve()] = record["sha256"]
            extra_sources["sources/" + name] = path
        for name, item in receipt["overlay"].items():
            path = check_record(item["copy"])
            expected_copy_hashes[path.resolve()] = item["copy"]["sha256"]
            extra_sources["sources/native-overlay/" + name] = path
        # Only terminal host trees are frozen wholesale. A live preview retains
        # its explicit JSON snapshot and completed cases, never races active logs.
        if not preview:
            for directory, prefix in ((args.driver_receipt.parent, "host/native"), (args.parent_start.parent, "host/native-parent"),
                                      (args.cpu_execution_receipt.parent, "host/cpu"), (args.cpu_parent_start.parent, "host/cpu-parent")):
                files = set()
                for path in sorted(directory.rglob("*")):
                    if path.is_symlink():
                        raise ValueError("Symlink in terminal reference host evidence")
                    if path.is_file():
                        files.add(path.resolve())
                        expected_copy_hashes.setdefault(path.resolve(), digest(path))
                        extra_sources[prefix + "/" + path.relative_to(directory).as_posix()] = path
                terminal_trees.append((directory, files))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".publishing-", dir=output.parent))
    copied = []
    def copy(src: Path, rel: str) -> str:
        target = staging / rel; target.parent.mkdir(parents=True, exist_ok=True)
        source_sha = digest(src)
        if src.resolve() in expected_copy_hashes and source_sha != expected_copy_hashes[src.resolve()]:
            raise ValueError(f"Verified artifact changed before copy: {src}")
        shutil.copyfile(src, target)
        if digest(src) != source_sha or digest(target) != source_sha:
            raise ValueError(f"Source changed during byte copy: {src}")
        copied.append({"path": rel, "source": str(src), "sha256": source_sha, "bytes": target.stat().st_size})
        return rel
    def archive(src: Path, rel: str, content=None, snapshot=False) -> str:
        content = src.read_bytes() if content is None else content
        whole_sha = hashlib.sha256(content).hexdigest()
        if not snapshot and (digest(src) != whole_sha or (src.resolve() in expected_copy_hashes and expected_copy_hashes[src.resolve()] != whole_sha)):
            raise ValueError("Verified archive changed before copy: " + str(src))
        if not snapshot:
            expected_copy_hashes.setdefault(src.resolve(), whole_sha)
        if len(content) <= CHUNK_LIMIT:
            if snapshot:
                target = staging / rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
                return rel
            return copy(src, rel)
        chunks = []
        for ordinal, offset in enumerate(range(0, len(content), CHUNK_LIMIT)):
            value = content[offset:offset + CHUNK_LIMIT]
            name = rel + f".parts/{ordinal:06d}.bin"
            target = staging / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
            record = {"path": name, "offset": offset, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            chunks.append(record); copied.append(record | {"source": str(src), "snapshot": snapshot})
        descriptor = {"schema_version": 1, "original_relative": rel, "source": str(src), "bytes": len(content),
                      "sha256": whole_sha, "chunks": chunks, "reconstruction": "Concatenate chunks by offset, then verify bytes and whole SHA256"}
        link = rel + ".chunks.json"
        (staging / link).write_text(json.dumps(descriptor, indent=2) + "\n")
        if not snapshot and digest(src) != whole_sha:
            raise ValueError("Source changed during chunk copy: " + str(src))
        return link
    try:
        links = {}
        raw_paths = {"plan.json": args.plan, "matrix.json": args.matrix, "driver-receipt.json": args.driver_receipt,
                     "parent-start.json": getattr(args, "parent_start", None), "parent-exit.json": getattr(args, "parent_exit", None),
                     "cpu-validation.json": getattr(args, "cpu_validation", None), "cpu-execution.json": getattr(args, "cpu_execution_receipt", None),
                     "cpu-parent-start.json": getattr(args, "cpu_parent_start", None), "cpu-parent-exit.json": getattr(args, "cpu_parent_exit", None)}
        for name, content in raw.items():
            if reference:
                links[name] = archive(raw_paths[name], name, content, snapshot=preview)
            else:
                (staging / name).write_bytes(content)
                links[name] = name
        copy(args.driver_wrapper, "sources/full_driver.py")
        copy(Path(__file__), "sources/publish_full_scene_matrix.py")
        for name, source in extra_sources.items():
            archive(source, name)
        cases = []
        for ordinal, item in enumerate(verified):
            row, result = item["row"], item["result"]; sim = result["simulation"]
            prefix = f'cases/{row["scenario"]}/config-{row["configuration_index"]:04d}'
            attempts = []
            for attempt, archive in zip(row["attempts"], item["attempt_archives"]):
                directory = host_path(attempt["output"]).resolve(); folder = f'{prefix}/attempt-{attempt["number"]:04d}'
                files = []
                for record in archive["files"]:
                    src = Path(record["path"])
                    files.append(copy(src, folder + "/" + src.relative_to(directory).as_posix()))
                parent_log = copy(check_record(attempt["log"]), folder + "/parent-execution.log") if attempt.get("log") else None
                attempts.append({"number": attempt["number"], "status": attempt["status"], "returncode": attempt.get("returncode"),
                                 "files": files, "parent_log": parent_log, "original_receipt": attempt,
                                 "sealed": archive["sealed"], "integrity_scope": archive["integrity_scope"]})
            current = f'{prefix}/attempt-{row["attempts"][-1]["number"]:04d}'
            (staging / (prefix + "/attempts.json")).write_text(json.dumps(attempts, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
            svg = prefix + "/world-xy.svg"; (staging / svg).write_text(trajectory_svg(item["trajectory"]))
            videos = []
            for check in result["video_checks"]:
                stream = check["probe"]["streams"][0]
                videos.append({"path": current + "/" + check["video"], "thumbnail": current + "/" + check["thumbnail"],
                               "duration_seconds": float(check["probe"]["format"]["duration"]), "width": stream["width"], "height": stream["height"]})
            cases.append({"ordinal": ordinal, **{k: row[k] for k in ("case_id", "scenario", "configuration", "configuration_index", "command", "mesh_sha256")},
                          "status": "completed", "policy_ticks": result["inference"]["ticks"], "policy_seconds": sim["policy_simulation_seconds"],
                          "threshold_event": sim["fall_detected"], **{k: sim[k] for k in ("minimum_pelvis_height_m", "minimum_base_up_z", "final_base_up_z", "path_length_xy_m", "final_position_xyz_m")},
                          "videos": videos, "trajectory_svg": svg, "trajectory_csv": current + "/trajectory.csv", "result_json": current + "/result.json",
                          "case_evidence": current + "/case-evidence.json", "attempts_json": prefix + "/attempts.json", "attempts": attempts,
                          "quality_verified": False, "obstacle_course_completion_verified": False})
            if reference:
                info = reference_info(row)
                cases[-1].update({key: info[key] for key in ("reference_commands", "reference_frames", "reference_fps", "reference_motion", "command_runs")})
                cases[-1].update(command=None, reference_policy_seconds=info["duration"],
                                 reference_motion_sha256=info["reference_motion"]["sha256"], reference_motion_path=info["reference_motion"]["path"],
                                 policy_recording=current + "/" + result["inference"]["lifecycle"]["recording_toggle_and_stop_autosave"][0]["file"])
        scenes = []
        for name in SCENARIO_COUNTS:
            rows = [r for r in cases if r["scenario"] == name]; flags = sum(r["threshold_event"] for r in rows)
            scenes.append({"scenario": name, "planned_configurations": SCENARIO_COUNTS[name], "configurations": len(rows), "threshold_events": flags,
                           "no_threshold_events": len(rows) - flags, "historical_noncompleted_attempts": sum(a["status"] != "completed" for r in rows for a in r["attempts"])})
            if reference:
                scenes[-1].update(reference_frames=sum(row["reference_frames"] for row in rows),
                                  reference_policy_seconds=sum(row["reference_frames"] for row in rows) / 50)
        summary = {"schema_version": 1, "status": "preview" if preview else "completed_publication", "preview": preview,
                   "legacy_normal_exit_unverified": plan.get("schema_version") == 2,
                   "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "plan_sha256": plan["plan_sha256"], "image_id": plan["image_id"],
                   "matrix_sha256": hashlib.sha256(raw["matrix.json"]).hexdigest(), "model_sha256": plan["model_sha256"], "configurations": len(cases),
                   "planned_configurations": sum(SCENARIO_COUNTS.values()), "policy_ticks": sum(r["policy_ticks"] for r in cases),
                   "policy_seconds": sum(r["policy_seconds"] for r in cases), "threshold_events": sum(r["threshold_event"] for r in cases),
                   "no_threshold_events": sum(not r["threshold_event"] for r in cases), "scenarios": scenes,
                   "scope": ("Configuration coverage of full 50Hz source-reference command sequences through native ONNX physics; deployment stance with root XY/yaw alignment. Not 629 independent geometries or successful skills. All threshold events retained."
                             if reference else "Configuration coverage of constant-forward native ONNX physical rollouts; not 629 independent geometries or successful skills. All threshold events and historical attempts retained."),
                   "configuration_coverage_complete": not preview, "quality_verified": False, "obstacle_course_completion_verified": False,
                   "media_policy": "Original video/PNG/log/JSON/CSV bytes, no transcoding or trajectory smoothing; derived world XY SVG from measured policy trajectory only",
                   "publisher_sha256": digest(Path(__file__))}
        if reference:
            summary.update(reference_commands=True, reference_fps=50, reference_frames=sum(row["reference_frames"] for row in cases),
                           reference_policy_seconds=sum(row["reference_frames"] for row in cases) / 50,
                           cpu_validation_matrix_sha256=context["cpu_validation"]["matrix_sha256"],
                           cpu_matrix_progress_difference_allowed=preview,
                           full_video_decode_verified=True, raw_links=links,
                           native_parent_exit_verified=not preview, host_writer_coverage_verified=not preview,
                           cpu_parent_exit_verified=True, host_mappings_verified=0 if preview else 2 * len(cases),
                           evidence_scope="preview only" if preview else "native parent0, workers0/empty, host births, independent CPU parent0 and full MP4 decode")
        for name, obj in (("summary.json", summary), ("cases.json", cases), ("scenarios.json", scenes)):
            (staging / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        fields = ["ordinal", "case_id", "scenario", "configuration_index", "configuration", "command", "mesh_sha256", "policy_ticks", "policy_seconds", "threshold_event",
                  "minimum_pelvis_height_m", "minimum_base_up_z", "final_base_up_z", "path_length_xy_m", "result_json", "trajectory_csv"]
        if reference:
            fields += ["reference_frames", "reference_fps", "reference_policy_seconds", "reference_motion_sha256", "reference_motion_path", "command_runs", "policy_recording"]
        with (staging / "cases.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
            writer.writerows([{**case, "command_runs": json.dumps(case["command_runs"], separators=(",", ":"))} for case in cases] if reference else cases)
        (staging / "playback.html").write_text(make_page(summary, cases))
        records = [{"path": p.relative_to(staging).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(staging.rglob("*")) if p.is_file()]
        manifest = {"schema_version": 1, "preview": preview, "source_matrix_sha256": summary["matrix_sha256"], "plan_sha256": plan["plan_sha256"],
                    "files": records, "byte_copies": copied, "bytes_excluding_manifest": sum(r["bytes"] for r in records)}
        (staging / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        if args.plan.read_bytes() != raw["plan.json"]:
            raise ValueError("Plan changed during publication")
        if not preview and (args.matrix.read_bytes() != raw["matrix.json"] or args.driver_receipt.read_bytes() != raw["driver-receipt.json"]):
            raise ValueError("Terminal matrix/driver receipt changed during publication")
        if reference:
            for name, source in raw_paths.items():
                if name in raw and (not preview or name not in {"matrix.json", "driver-receipt.json"}) and source.read_bytes() != raw[name]:
                    raise ValueError("Reference execution evidence changed during publication: " + name)
            for directory, files in terminal_trees:
                current = list(directory.rglob("*"))
                if any(path.is_symlink() for path in current) or {path.resolve() for path in current if path.is_file()} != files:
                    raise ValueError("Reference terminal host evidence file set changed during publication")
        if output.exists(): output.rmdir()
        staging.rename(output)
        return summary
    except BaseException as error:
        if reference:
            (staging / "publication-failed.json").write_text(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}",
                                                                         "scope": "Incomplete stage retained; not a published result"}, indent=2) + "\n")
        else:
            shutil.rmtree(staging)
        raise


def restore_chunks(package: Path, output: Path) -> dict:
    package, output = package.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(package):
        raise ValueError("Restore into a new directory outside the immutable publication")
    descriptors = sorted(package.rglob("*.chunks.json"))
    output.mkdir(parents=True)
    restored = []
    for descriptor_path in descriptors:
        descriptor = load_bytes(descriptor_path.read_bytes())
        relative = Path(descriptor["original_relative"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe reconstructed path")
        target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
        offset = 0
        with target.open("xb") as stream:
            for record in descriptor["chunks"]:
                part = safe_child(package, record["path"])
                if (part.is_symlink() or record["offset"] != offset or not 0 < record["bytes"] <= CHUNK_LIMIT
                        or part.stat().st_size != record["bytes"] or digest(part) != record["sha256"]):
                    raise ValueError("Noncontiguous, oversized or changed archive chunk")
                stream.write(part.read_bytes()); offset += record["bytes"]
        if offset != descriptor["bytes"] or digest(target) != descriptor["sha256"]:
            raise ValueError("Reconstructed whole-file bytes or SHA mismatch")
        restored.append({"path": str(target), "bytes": offset, "sha256": descriptor["sha256"]})
    return {"status": "restored_original_bytes", "files": restored}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "restore-chunks":
        parser = argparse.ArgumentParser(description="Restore original raw files from verified, contiguous byte chunks into a fresh directory")
        parser.add_argument("--package", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args(sys.argv[2:])
        print(json.dumps(restore_chunks(args.package, args.output), indent=2))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True,
                        help="Identity from the independently frozen cohort plan")
    parser.add_argument("--expected-harness-sha256", required=True,
                        help="SHA256 of that cohort sim2sim_scene_matrix.py source")
    for name in ("plan", "matrix", "driver-receipt", "driver-wrapper", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--driver-launch", type=Path, help="Original constant-mode wrapper launch receipt")
    parser.add_argument("--reference-cohort", type=Path, help="Explicit reference controller cohort with its exact six mount namespaces")
    for name in ("parent-start", "parent-exit", "cpu-validation", "cpu-execution-receipt", "cpu-parent-start", "cpu-parent-exit"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--preview-case-count", type=int, choices=(1, 2), default=0,
                        help="Only actual completed cases; output restricted to ignored outputs/research, never a full publication")
    args = parser.parse_args()
    try:
        summary = publish(args)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        parser.error(str(error))
    print(json.dumps({k: summary[k] for k in ("status", "configurations", "threshold_events", "configuration_coverage_complete")}, indent=2))


if __name__ == "__main__":
    main()
