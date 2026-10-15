#!/usr/bin/env python3
"""Verify retained native matrix evidence and fully decode its videos on CPU.

Run inside the project Docker image with the original source, inputs and native
outputs mounted read-only at their recorded paths. This tool starts no physics,
DDS or GPU worker. Overall driver/host-parent exits must be verified separately.
An explicit preview validates only named completed cases of a live matrix.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fingerprint(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular retained file required: " + str(path))
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def write(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def validate_scope(plan: dict, report: dict, preview_case_ids: list[str]) -> list[int]:
    """Bind the full plan and case identities before choosing a bounded preview."""
    content = {key: value for key, value in plan.items() if key != "plan_sha256"}
    identity = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    expected, actual = plan["selections"], report["selections"]
    if (identity != plan["plan_sha256"] or plan.get("status") != "planned"
            or plan.get("schema_version") != 3 or plan.get("python_faulthandler") is not True
            or len(expected) != plan["planned_configurations"] or len(actual) != len(expected)
            or len({case["scenario"] for case in expected}) != plan["planned_scenarios"]
            or len({case["case_id"] for case in expected}) != len(expected)
            or plan.get("quality_verified") is not False or plan.get("obstacle_course_completion_verified") is not False
            or any(report.get(key) != value for key, value in plan.items() if key not in ("status", "selections"))):
        raise ValueError("Full native plan identity, scope or immutable matrix fields differ")
    if plan.get("all_configurations") and (len(expected) != 629 or plan["planned_scenarios"] != 17):
        raise ValueError("The all-configurations scope must retain all 629 cases and 17 scenes")
    for planned, case in zip(expected, actual):
        if any(case.get(key) != value for key, value in planned.items()):
            raise ValueError("Native case order or immutable input identity differs")
    if preview_case_ids:
        requested = set(preview_case_ids)
        if len(requested) != len(preview_case_ids) or not requested <= {case["case_id"] for case in expected}:
            raise ValueError("Preview requires distinct, existing exact case IDs")
        return [index for index, case in enumerate(expected) if case["case_id"] in requested]
    invocation = report["last_invocation"]
    if (report.get("status") != "completed" or report.get("configuration_coverage_complete") is not True
            or report.get("completed_configurations") != len(expected)
            or report.get("completed_scenarios") != plan["planned_scenarios"]
            or invocation["case_ids"] or invocation["case_limit"] is not None or invocation["resume"] is not False
            or invocation["requested_configurations"] != len(expected)):
        raise ValueError("Full validation requires a fresh, unfiltered, completed native matrix")
    return list(range(len(expected)))


def command_runs(codes: list[int]) -> list[dict]:
    if not codes:
        raise ValueError("Native policy must have at least one command frame")
    runs, start = [], 0
    for end in range(1, len(codes) + 1):
        if end == len(codes) or codes[end] != codes[start]:
            runs.append({"start_frame": start, "end_frame_exclusive": end, "code": codes[start],
                         "seconds": (end - start) / 50})
            start = end
    return runs


def input_fingerprints(plan: dict, selections: list[dict]) -> list[dict]:
    records = [plan["source_matrix_record"], *plan["dependencies"], *plan["models"],
               *(record for case in selections for record in case["source_files"])]
    unique = {}
    for record in records:
        if record["path"] in unique and record != unique[record["path"]]:
            raise ValueError("Conflicting retained input fingerprints")
        unique[record["path"]] = record
    actual = []
    for path, expected in sorted(unique.items()):
        value = fingerprint(Path(path))
        if value["sha256"] != expected["sha256"] or ("bytes" in expected and value["bytes"] != expected["bytes"]):
            raise ValueError("Retained input changed: " + path)
        actual.append(value)
    return actual


def validate(args) -> dict:
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("Fresh CPU validation output required; preserve previous results")
    if args.output.resolve().is_relative_to(args.matrix.resolve().parent):
        raise ValueError("Write validation outside the retained native output directory")
    # Exclusive creation prevents a second validator from replacing this receipt.
    with args.output.open("x"):
        pass
    result = {"schema_version": 1, "status": "running", "started_unix": time.time(),
              "helper": fingerprint(Path(__file__).resolve()), "cases": [],
              "preview": bool(args.preview_case_id), "completion_verified": False,
              "quality_verified": False, "obstacle_course_completion_verified": False,
              "overall_native_parent_exit_verified": False,
              "scope": "CPU retained-evidence validation and full video decoding; overall driver/host-parent exits are separate evidence"}
    write(args.output, result)
    try:
        snapshots = []
        for path in (args.plan, args.matrix):
            if path.is_symlink() or not path.is_file():
                raise ValueError("Regular retained JSON required: " + str(path))
            raw = path.read_bytes()
            snapshots.append(({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                              json.loads(raw)))
        (before_plan, plan), (before_matrix, report) = snapshots
        indices = validate_scope(plan, report, args.preview_case_id)
        saved = args.matrix.parent / "plan.json"
        if saved.read_bytes() != args.plan.read_bytes():
            raise ValueError("Native saved plan differs from the supplied frozen plan")
        scripts = Path(__file__).resolve().parent
        # inference-python removes PYTHONPATH; matrix has a direct helper import.
        if args.matrix_module is not None:
            scripts = args.matrix_module.resolve().parent
        module_path = args.matrix_module or scripts / "sim2sim_scene_matrix.py"
        if not any(record["path"] == str(module_path.resolve()) and record["sha256"] == digest(module_path)
                   for record in plan["dependencies"]):
            raise ValueError("Loaded matrix validator is not the frozen planned dependency")
        selected = [plan["selections"][index] for index in indices]
        inputs_before = input_fingerprints(plan, selected)
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(scripts))
        import importlib.util
        spec = importlib.util.spec_from_file_location("validated_native_matrix", module_path)
        matrix = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matrix)
        result.update(native_plan_sha256=plan["plan_sha256"], native_plan_file_sha256=before_plan["sha256"],
                      matrix_sha256=before_matrix["sha256"], reference_commands=bool(plan.get("reference_commands")),
                      planned_configurations=plan["planned_configurations"], planned_scenarios=plan["planned_scenarios"],
                      planned_total_policy_ticks=sum(matrix.policy_ticks(plan, case) for case in plan["selections"]),
                      selected_case_ids=[case["case_id"] for case in selected],
                      inputs=inputs_before, matrix_validator=fingerprint(module_path))
        write(args.output, result)
        workers = videos = ticks = 0
        for index, expected in zip(indices, selected):
            case = report["selections"][index]
            attempts = case["attempts"]
            if (case["status"] != "completed" or len(attempts) != 1 or attempts[0]["status"] != "completed"
                    or attempts[0]["returncode"] != 0):
                raise ValueError("Exactly one normally completed native attempt required: " + case["case_id"])
            matrix.verify_completed(attempts[0], plan, case)
            directory = Path(attempts[0]["output"])
            native = json.loads((directory / "result.json").read_text())
            evidence = json.loads(Path(attempts[0]["evidence"]["path"]).read_text())
            sealed_files = {record["path"]: record for record in evidence["files"]}
            sealed = matrix.validate_worker_receipts(directory, plan, native)
            expected_ticks = matrix.policy_ticks(plan, expected)
            if (native["inference"]["ticks"] != expected_ticks or len(native["videos"]) != 1
                    or type(native["simulation"]["fall_detected"]) is not bool
                    or native["survival_passed"] is not (not native["simulation"]["fall_detected"])):
                raise ValueError("Native frame count, video count or threshold report differs")
            decoded = []
            for relative in native["videos"]:
                source = directory / relative
                path = source.resolve()
                if Path(relative).is_absolute() or source.is_symlink() or not path.is_relative_to(directory.resolve()):
                    raise ValueError("Unsafe retained video path")
                before = fingerprint(path)
                sealed_video = sealed_files.get(str(source))
                if sealed_video is None or any(before[key] != sealed_video[key] for key in ("bytes", "sha256")):
                    raise ValueError("Video differs from its original retained evidence seal")
                argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-threads", "1",
                        "-i", str(path), "-f", "null", "-"]
                completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
                decode = {**before, "command": argv, "returncode": completed.returncode,
                          "stderr": completed.stderr, "full_decode": completed.returncode == 0}
                decoded.append(decode)
                if completed.returncode or fingerprint(path) != before:
                    result["failed_video"] = decode
                    raise ValueError("Immutable full video decode failed: " + case["case_id"])
            matrix.verify_completed(attempts[0], plan, case)
            codes = expected["reference_commands"]["codes"] if plan.get("reference_commands") else [expected["command"]] * expected_ticks
            entry = {"case_id": case["case_id"], "native_result_sha256": digest(directory / "result.json"),
                     "parent_returncode": attempts[0]["returncode"], "worker_receipts": sealed,
                     "worker_exit0_empty_groups": 2, "policy_ticks": expected_ticks,
                     "policy_seconds": expected_ticks / 50, "command_runs": command_runs(codes), "videos": decoded,
                     "reference_commands": bool(plan.get("reference_commands")),
                     "survival_heuristic_passed": native["survival_passed"], "quality_verified": False,
                     "obstacle_course_completion_verified": False}
            if plan.get("reference_commands"):
                entry["reference_motion"] = next(record for record in expected["source_files"]
                                                 if record["path"] == expected["reference_commands"]["path"])
                clip = native["inference"]["lifecycle"]["recording_toggle_and_stop_autosave"][0]
                entry["policy_recording"] = fingerprint(directory / clip["file"])
            result["cases"].append(entry)
            workers += 2
            videos += len(decoded)
            ticks += expected_ticks
            write(args.output, result)
        if fingerprint(args.plan) != before_plan or input_fingerprints(plan, selected) != inputs_before:
            raise ValueError("Frozen plan or inputs changed during CPU validation")
        if not args.preview_case_id and fingerprint(args.matrix) != before_matrix:
            raise ValueError("Completed native matrix changed during CPU validation")
        result.update(status="preview_validated" if args.preview_case_id else "passed",
                      completion_verified=not bool(args.preview_case_id), configurations=len(selected),
                      scenarios=len(Counter(case["scenario"] for case in selected)),
                      worker_exit0_empty_group_count=workers, full_decoded_mp4_count=videos,
                      total_policy_ticks=ticks, quality_verified=False, obstacle_course_completion_verified=False)
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        result["finished_unix"] = time.time()
        write(args.output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matrix-module", type=Path,
                        help="Exact frozen matrix validator path; must occur in the plan dependency closure")
    parser.add_argument("--preview-case-id", action="append", default=[],
                        help="Validate only this completed case; never produces full completion evidence")
    args = parser.parse_args()
    value = validate(args)
    print(json.dumps({key: value[key] for key in ("status", "preview", "completion_verified", "configurations",
                                                "full_decoded_mp4_count", "total_policy_ticks")}))


if __name__ == "__main__":
    main()
