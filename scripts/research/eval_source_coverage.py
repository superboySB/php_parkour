#!/usr/bin/env python3
"""Prepare and run isolated first-attempt evaluations of released source clips.

Use train-python inside the research Docker. `plan` and `preflight` are CPU-only;
`run` explicitly starts native Isaac evaluation, one fresh process per source.
For one teacher clip, use --policy teacher --checkpoint LOCAL_PT and one exact
--source-clip-id from the inventory. For all teachers, use five repeated
--teacher-checkpoint SKILL=LOCAL_PT arguments. For pure/finetune students,
--checkpoint is that student's own PT. Without a source filter all 296 are used.
No online registry, W&B login, host installation, or training change is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.eval_quality import atomic_json, sha256
from scripts.research.runtime_robot_assets import (SOURCE_RELATIVE, contract as robot_contract,
    prepare as prepare_robot_assets, verify as verify_robot_assets)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def file_record(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Expected an existing local file: {path}")
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def prepare(args):
    from scripts.research.motion_coverage import REGISTRIES, inventory, materialize
    from scripts.research.source_coverage_probe import native_arguments, recover_config
    if args.output.exists():
        raise ValueError("Use a new output directory; existing evidence is never overwritten")
    data = inventory(args.assets_root)
    records = data["records"]
    if args.source_clip_id:
        selected = set(args.source_clip_id)
        records = [record for record in records if record["source_clip_id"] in selected]
        if len(records) != len(selected):
            raise ValueError("Unknown source_clip_id; use the inventory's exact stable IDs")
    teacher_paths = {}
    for item in args.teacher_checkpoint:
        skill, path = item.split("=", 1)
        if skill not in dict(REGISTRIES) or skill in teacher_paths:
            raise ValueError("Teacher keys must be unique skills from the original five-expert order")
        teacher_paths[skill] = file_record(path)
    if args.policy == "teacher":
        if args.checkpoint:
            if teacher_paths or len({record["skill"] for record in records}) != 1:
                raise ValueError("A single teacher --checkpoint requires sources from exactly one expert")
            teacher_paths[records[0]["skill"]] = file_record(args.checkpoint)
        if any(record["skill"] not in teacher_paths for record in records):
            raise ValueError("Every selected original expert requires its own --teacher-checkpoint skill=PT")
    elif teacher_paths or not args.checkpoint:
        raise ValueError("Student evaluation requires its own local --checkpoint, without teacher checkpoints")
    student = file_record(args.checkpoint) if args.policy != "teacher" else None
    args.output.mkdir(parents=True)
    if args.runtime_robot_assets_contract:
        robot_assets = json.loads(args.runtime_robot_assets_contract.read_text())
        verify_robot_assets(robot_assets)
    else:
        robot_assets = robot_contract(ROOT / SOURCE_RELATIVE, args.output.resolve() / "runtime-robot-assets/robots")
        prepare_robot_assets(robot_assets)
    data["created_at_utc"] = now()
    atomic_json(args.output / "inventory.json", data)
    source_inventory = file_record(args.output / "inventory.json")
    harness_sources = [file_record(ROOT / "scripts/research" / name) for name in
                       ("eval_source_coverage.py", "source_coverage_probe.py", "motion_coverage.py", "eval_quality.py", "runtime_robot_assets.py")]
    cases = []
    for record in records:
        case_id = f"{args.policy}-e{record['expert_ordinal']}-{record['source_ordinal']:03d}-{record['source_motion_sha256'][:12]}"
        directory = args.output / "cases" / case_id
        directory.mkdir(parents=True)
        singleton = materialize(record, directory / "singleton")
        checkpoint = teacher_paths[record["skill"]] if args.policy == "teacher" else student
        case = {"schema_version": 2, "case_id": case_id, "policy": args.policy,
                "output": str(directory.resolve()), "source": record,
                "inventory_sha256": data["inventory_sha256"], "checkpoint": checkpoint["path"],
                "source_inventory": source_inventory, "harness_sources": harness_sources,
                "runtime_robot_assets": robot_assets,
                "checkpoint_sha256": checkpoint["sha256"], "registry_uri": singleton["registry_uri"],
                "singleton_provenance": singleton["provenance_path"],
                "singleton_provenance_sha256": sha256(singleton["provenance_path"]),
                "max_steps": args.max_steps if args.max_steps is not None else record["frames"],
                "original_expert_ordinal": record["expert_ordinal"], "singleton_native_expert_ordinal": 0}
        if case["max_steps"] < 1:
            raise ValueError("max_steps must be positive")
        # Actual saved-config parsing checks the model type and every native
        # override before any GPU request. Preprocessing is the next stage.
        saved, _ = recover_config(case)
        if args.policy == "teacher":
            registry = saved.training.registry_name.rstrip("/").split("/")[-1]
            if registry != record["registry_component"]:
                raise ValueError(f"Teacher saved registry {saved.training.registry_name!r} does not match {record['skill']}")
        case["saved_algorithm_target"] = saved.algo._target_
        case["saved_training_registry"] = saved.training.registry_name
        case["native_argv"] = ["--checkpoint", checkpoint["path"], *native_arguments(case)]
        path = directory / "case.json"
        atomic_json(path, case)
        cases.append({"case_id": case_id, "case": file_record(path), "source_clip_id": record["source_clip_id"],
                      "original_expert_ordinal": record["expert_ordinal"], "checkpoint": checkpoint})
    plan = {"schema_version": 2, "status": "prepared_gpu_not_run", "created_at_utc": now(), "policy": args.policy,
            "scope": "Each selected original source is attempted independently on one generated terrain variant, seed42. Execution and skill quality are separate. No GPU run by plan/preflight.",
            "source_inventory": file_record(args.output / "inventory.json"), "inventory_sha256": data["inventory_sha256"],
            "inventory_total_sources": data["total_files"], "selected_sources": len(cases),
            "stop_rules": ["first native failed", "first native timeout", "first native motion boundary", "max policy steps"],
            "native_warmup_semantics": "reset_all A initializes; reset_all B is first attempt zero-action warmup at frame0; first policy frame1, last potential frameT-2; boundaryT-1 is sentinel",
            "harness_sources": harness_sources,
            "runtime_robot_assets": robot_assets,
            "cases": cases, "quality_verified": False, "simulation_started": False}
    atomic_json(args.output / "plan.json", plan)
    return {key: plan[key] for key in ("status", "inventory_total_sources", "selected_sources", "inventory_sha256")}


def verify_plan(path):
    from scripts.research.motion_coverage import validate_inventory
    from scripts.research.source_coverage_probe import native_arguments, verify_case
    plan = json.loads(path.read_text())
    if (plan.get("schema_version") != 2 or plan.get("policy") not in ("teacher", "pure", "finetune")
            or not plan.get("cases") or len(plan["cases"]) != plan.get("selected_sources")
            or len({item["case_id"] for item in plan["cases"]}) != len(plan["cases"])
            or len({item["source_clip_id"] for item in plan["cases"]}) != len(plan["cases"])):
        raise ValueError("Invalid plan schema, policy, counts or duplicate case/source identity")
    verify_robot_assets(plan["runtime_robot_assets"])
    expected_harness = [file_record(ROOT / "scripts/research" / name) for name in
                        ("eval_source_coverage.py", "source_coverage_probe.py", "motion_coverage.py", "eval_quality.py", "runtime_robot_assets.py")]
    if plan["harness_sources"] != expected_harness:
        raise ValueError("Plan does not bind the complete current five-source harness")
    for item in [plan["source_inventory"], *plan["harness_sources"]]:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError(f"Planned input changed: {item['path']}; prepare a fresh plan")
    inventory = json.loads(Path(plan["source_inventory"]["path"]).read_text())
    validate_inventory(inventory)
    if inventory["inventory_sha256"] != plan["inventory_sha256"]:
        raise ValueError("Plan inventory identity mismatch")
    records = {record["source_clip_id"]: record for record in inventory["records"]}
    for item in plan["cases"]:
        for artifact in (item["case"], item["checkpoint"]):
            if sha256(artifact["path"]) != artifact["sha256"]:
                raise ValueError(f"Planned case/checkpoint changed: {artifact['path']}")
        case = json.loads(Path(item["case"]["path"]).read_text())
        if (case.get("schema_version") != 2 or case["runtime_robot_assets"] != plan["runtime_robot_assets"]
                or case["source"] != records[item["source_clip_id"]] or case["inventory_sha256"] != plan["inventory_sha256"]
                or case["case_id"] != item["case_id"] or case["checkpoint_sha256"] != item["checkpoint"]["sha256"]
                or case["checkpoint"] != item["checkpoint"]["path"] or case["policy"] != plan["policy"]
                or case["source_inventory"] != plan["source_inventory"] or case["harness_sources"] != plan["harness_sources"]
                or case["native_argv"] != ["--checkpoint", case["checkpoint"], *native_arguments(case)]):
            raise ValueError("Case identity does not match source inventory and plan")
        verify_case(case)  # Checks retained singleton bytes, source identity and current helper SHA.
    return plan


def validate_native_report(quality, case):
    """Execution evidence is mandatory even when the first attempt failed."""
    if (quality.get("status") != "completed" or quality.get("case_id") != case["case_id"]
            or quality.get("source") != case["source"] or quality.get("quality_verified") is not False
            or quality.get("checkpoint", {}).get("sha256") != case["checkpoint_sha256"]
            or quality["checkpoint"].get("path") != case["checkpoint"]
            or quality.get("policy") != case.get("policy")
            or quality.get("singleton_provenance_sha256") != case.get("singleton_provenance_sha256")
            or quality.get("inventory_identity_sha256") != case["inventory_sha256"]
            or quality.get("source_inventory") != case.get("source_inventory")
            or quality.get("harness_sources") != case.get("harness_sources")
            or quality.get("runtime_robot_assets") != case["runtime_robot_assets"]
            or quality.get("native_argv") != case["native_argv"]):
        raise ValueError("Native quality identity/status does not match this case")
    verify_robot_assets(case["runtime_robot_assets"])
    runtime = quality["actual_native"]
    validate_robot_report(runtime.get("robot_asset_config"), case["runtime_robot_assets"])
    if runtime.get("source_table_verification", {}).get("status") != "matched_selected_source":
        raise ValueError("Actual reference table was not checked against the selected source")
    retained = [quality["trajectory"]]
    for name in ("motion", "terrain_obj", "saved_eval_config"):
        retained.append(runtime[name]["retained"])
    events, videos = quality["tensorboard_events"], quality["videos"]
    if not events or not videos or not any(video["duration_seconds"] > 0 for video in videos):
        raise ValueError("Fresh TensorBoard events and a decodable native video are required")
    retained.extend(events + videos)
    for item in retained:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError(f"Native retained evidence changed: {item['path']}")
    if set(quality["metrics"]) != {"motion/error_ref_pos", "motion/error_ref_rot", "motion/error_body_pos", "motion/error_joint_pos"}:
        raise ValueError("Four native policy tracking metrics are required")
    for metric in quality["metrics"].values():
        steps = quality["control_steps"]
        if metric["samples"] != steps or metric["finite"] is not (True if steps else None):
            raise ValueError("Invalid finite-policy metric scope; zero steps is not an observed finite rollout")


def validate_cpu_report(report, case):
    if (report.get("status") != "cpu_preflight_passed_gpu_not_run" or report.get("simulation_started") is not False
            or report.get("case_id") != case["case_id"] or report.get("source") != case["source"]
            or report.get("checkpoint", {}).get("path") != case["checkpoint"]
            or report["checkpoint"].get("sha256") != case["checkpoint_sha256"]
            or report.get("registry_uri") != case["registry_uri"]
            or report.get("policy") != case["policy"]
            or report.get("singleton_provenance_sha256") != case["singleton_provenance_sha256"]
            or report.get("inventory_identity_sha256") != case["inventory_sha256"]
            or report.get("harness_sources") != case["harness_sources"]):
        raise ValueError("CPU report identity does not match this planned case")
    if report.get("runtime_robot_assets") != case["runtime_robot_assets"]:
        raise ValueError("CPU report robot asset contract differs")
    verify_robot_assets(case["runtime_robot_assets"])
    validate_robot_report(report.get("robot_asset_config"), case["runtime_robot_assets"])
    if (report.get("num_envs") != 1 or report.get("actual_frames") != case["source"]["frames"]
            or report.get("actual_boundary_indices_inclusive") != [case["source"]["frames"] - 1]
            or report.get("actual_native_expert_ids") != [0] or report.get("expert_balancing_active") is not False
            or report.get("original_expert_ordinal") != case["original_expert_ordinal"]
            or report.get("source_table_verification", {}).get("status") != "matched_selected_source"):
        raise ValueError("CPU native singleton metadata does not match the source")
    artifacts = report["artifacts"]
    if {Path(item["path"]).name for item in artifacts} != {"holosoma_config.yaml", "motion.npz", "terrain.obj"}:
        raise ValueError("CPU preflight native config, reference and terrain are required")
    for item in artifacts:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("CPU preflight retained asset changed")


def validate_robot_report(actual, expected):
    if actual != {"asset_root": expected["runtime_root"], "urdf_file": expected["urdf_file"], "usd_file": None,
                  "manifest_sha256": expected["manifest"]["sha256"], "original_files": len(expected["files"])}:
        raise ValueError("Reported parsed robot asset configuration differs from the sealed contract")


def execute(args):
    plan = verify_plan(args.plan)
    selected = [item for item in plan["cases"] if not args.case_id or item["case_id"] in args.case_id]
    if args.case_id and len(selected) != len(set(args.case_id)):
        raise ValueError("Unknown case_id")
    directory = args.plan.parent
    stage = "cpu-preflight" if args.action == "preflight" else "native-first-attempt"
    summary_path = directory / f"{stage}-summary.json"
    if summary_path.exists():
        raise ValueError("A summary already exists; preserve it and prepare a new plan for another run")
    summary = {"schema_version": 1, "status": "running", "stage": stage, "started_at_utc": now(),
               "plan": file_record(args.plan), "simulation_started": args.action == "run", "quality_verified": False,
               "cases": [], "scope": "CPU preflight only" if args.action == "preflight" else "Native first attempts, not convergence or every terrain variant"}
    atomic_json(summary_path, summary)
    failed = False
    for item in selected:
        case = json.loads(Path(item["case"]["path"]).read_text())
        output = Path(case["output"])
        log = output / f"{stage}.log"
        if log.exists() or (args.action == "run" and (output / "quality.json").exists()):
            raise ValueError("Refusing to overwrite case execution evidence")
        command = [sys.executable, str(ROOT / "scripts/research/source_coverage_probe.py"), "--case", item["case"]["path"]]
        env = {**os.environ, "LOGGER": "tensorboard", "WANDB_MODE": "disabled", "PYTHONUNBUFFERED": "1"}
        if args.action == "preflight":
            command.append("--cpu-preflight")
            env["CUDA_VISIBLE_DEVICES"] = ""
        started = time.monotonic()
        process_error, return_code = None, None
        try:
            with log.open("x") as stream:
                completed = subprocess.run(command, env=env, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                return_code = completed.returncode
        except (OSError, subprocess.SubprocessError) as error:
            process_error = f"{type(error).__name__}: {error}"
            if log.exists():
                with log.open("a") as stream:
                    stream.write(f"\nChild launch/wait failed: {process_error}\n")
        report_path = output / "cpu-preflight/report.json" if args.action == "preflight" else output / "quality.json"
        result = {"case_id": case["case_id"], "source_clip_id": case["source"]["source_clip_id"],
                  "command": command, "return_code": return_code, "wall_seconds": time.monotonic() - started,
                  "log": file_record(log) if log.exists() else None, "status": "execution_failed", "quality_verified": False}
        try:
            if report_path.exists():
                result["report"] = file_record(report_path)
                quality = json.loads(report_path.read_text())
                if args.action == "preflight":
                    validate_cpu_report(quality, case)
                    result["status"] = "cpu_preflight_passed_gpu_not_run" if return_code == 0 else "execution_failed"
                else:
                    result.update({"stop_reason": quality.get("stop_reason"),
                                   "reference_boundary_reached": quality.get("first_attempt_reference_boundary_reached", False),
                                   "policy_steps": quality.get("control_steps", 0)})
                    validate_native_report(quality, case)
                    if return_code == 0:
                        result["status"] = "execution_passed"
                    else:
                        result["evidence_error"] = "Native worker returned a nonzero exit code"
            else:
                result["evidence_error"] = "Worker did not produce its required quality/preflight JSON"
        except (ValueError, KeyError, OSError, TypeError) as error:
            result["status"] = "execution_failed"
            result["evidence_error"] = f"{type(error).__name__}: {error}"
        if process_error:
            result["status"], result["evidence_error"] = "execution_failed", process_error
        failed |= result["status"] == "execution_failed"
        summary["cases"].append(result)
        atomic_json(summary_path, summary)
    summary.update(status="execution_failed" if failed else "completed", finished_at_utc=now(),
                   execution_passed=sum(case["status"] != "execution_failed" for case in summary["cases"]),
                   execution_failed=sum(case["status"] == "execution_failed" for case in summary["cases"]))
    atomic_json(summary_path, summary)
    return {"summary": str(summary_path), "status": summary["status"], "cases": len(summary["cases"]), "quality_verified": False}, int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    plan = commands.add_parser("plan", help="Inventory all 296 inputs and prepare selected singleton cases; CPU only")
    plan.add_argument("--policy", choices=("teacher", "pure", "finetune"), required=True)
    plan.add_argument("--checkpoint", type=Path)
    plan.add_argument("--teacher-checkpoint", action="append", default=[], metavar="SKILL=LOCAL_PT")
    plan.add_argument("--assets-root", type=Path, default=Path("/data/assets"))
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--runtime-robot-assets-contract", type=Path,
                      help="Use a shared previously CPU-prepared contract; default copies into this new plan output")
    plan.add_argument("--source-clip-id", action="append", default=[])
    plan.add_argument("--max-steps", type=int, help="Override policy-step cap; default is source frame count")
    for action in ("preflight", "run"):
        command = commands.add_parser(action, help="CPU native loader checks" if action == "preflight" else "Start GPU evaluation; GPU scheduling required")
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Run with /opt/php/bin/train-python inside the research Docker")
    if args.action == "plan":
        result, code = prepare(args), 0
    else:
        result, code = execute(args)
    print(json.dumps(result, indent=2), flush=True)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
