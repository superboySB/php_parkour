#!/usr/bin/env python3
"""Observe completed official training, then attempt all 296 sources per policy.

Host entry points use only Python's standard library. Scientific checks and
native workers run in the existing Docker image. This never starts training or
changes the training container/source mount. `dry-run` performs no writes and
does not start a container. Deployment remains an explicit operator action.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import uuid

SKILLS = ("locomotion", "low-step", "high-step", "low-climb-76", "high-climb-76")
POLICIES = ("teacher", "pure", "finetune")
TRAINING = {**{f"teacher-{skill}": (20000, 4096, 64) for skill in SKILLS},
            "student-pure": (10000, 2048, 3), "student-finetune": (30000, 2048, 3)}
LABELS = (*[f"teacher-{s}" for s in SKILLS], *[f"eval-teacher-{s}" for s in SKILLS],
          "student-pure", "eval-student-pure", "export-student-pure",
          "student-finetune", "eval-student-finetune", "export-student-finetune")
MARKER = "Official schedules and recorded evaluations/exports finished; assess quality.json before making skill claims."
OFFICIAL = "/outputs/official-full"
COVERAGE = "/outputs/posttrain-coverage"
TRAIN_TREE = "0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab"
IMAGE_CONTENTS = "2a43037e2397fac3e343e8d621dd42c41ea7c27da82602789d575fddda112482"
ACTIVE_TOKENS = ("run_official_acceptance.sh", "train_pipeline.py", "wbt_training.train_agent",
                 "wbt_training.training_runs.eval_", "export_distill_onnx", "validate_teacher_exports.py", "torchrun")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.chmod(0o644)
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def flag(command, name):
    require(command.count(name) == 1, f"Missing/duplicate native flag {name}")
    return command[command.index(name) + 1]


def host_path(official, recorded):
    path = PurePosixPath(recorded)
    require(path.is_absolute() and ".." not in path.parts and path.is_relative_to(OFFICIAL),
            f"Artifact escapes the read-only official output: {recorded}")
    resolved = (official / path.relative_to(OFFICIAL)).resolve()
    require(resolved.is_relative_to(official.resolve()), f"Artifact symlink escapes official output: {recorded}")
    return resolved


def check_file(official, record):
    path = host_path(official, record["path"])
    require(path.is_file() and digest(path) == record["sha256"], f"Artifact missing/changed: {record['path']}")
    if "bytes" in record:
        require(path.stat().st_size == record["bytes"], f"Artifact size changed: {record['path']}")


def stage_status(official):
    stages, blockers = {}, []
    for label in LABELS:
        path = official / "official/manifests" / f"{label}.json"
        if not path.exists():
            blockers.append(f"{label}: missing manifest")
            continue
        stage = read(path)
        if stage.get("status") != "passed":
            blockers.append(f"{label}: {stage.get('status', 'unknown')}")
        stages[label] = stage
    return stages, blockers


def inspect_artifacts(official, stages):
    """Standard-library provenance/hash gate, used only after all stages passed."""
    registries = [f"file:///data/assets/motions-{skill}" for skill in SKILLS]
    teachers, checkpoints, manifest_hashes = [], {}, {}
    for label in LABELS:
        stage = stages[label]
        settings, env = stage["settings"], stage["environment"]
        require(stage.get("label") == label and stage.get("profile") == "official"
                and stage.get("status") == "passed" and stage.get("returncode") == 0
                and stage.get("finished_utc"), f"Nonterminal/nonofficial manifest: {label}")
        require(settings["profile"] == "official" and settings["skills"] == list(SKILLS)
                and settings["assets"] == "/data/assets", f"Official input order/assets changed: {label}")
        require(env.get("LOGGER") == "tensorboard" and str(env.get("NGPUS")) == "1", f"Unexpected logger/GPU count: {label}")
        manifest_hashes[label] = digest(official / "official/manifests" / f"{label}.json")
        if label in TRAINING:
            target, num_envs, variants = TRAINING[label]
            require(settings["iterations_target"] == target and settings["num_envs"] in (None, num_envs)
                    and int(flag(stage["command"], "--training.num-envs")) == num_envs
                    and flag(stage["command"], "--training.seed") == "42", f"Shortened/changed official schedule: {label}")
            require(stage["checkpoint_iteration"] == target - 1, f"Not the final canonical iteration: {label}")
            checkpoint = {"path": stage["checkpoint"], "sha256": stage["checkpoint_sha256"]}
            require(PurePosixPath(checkpoint["path"]).is_relative_to(f"{OFFICIAL}/official/{label}"), f"Wrong checkpoint stage: {label}")
            check_file(official, checkpoint)
            if label.startswith("teacher-"):
                skill = label.removeprefix("teacher-")
                require(settings["registries"] == registries[SKILLS.index(skill)] == env.get("REGISTRY")
                        and settings["source_checkpoints"] == [] and settings["finetune"] is None,
                        f"Wrong teacher registry/provenance: {label}")
                teachers.append(checkpoint)
            else:
                require(settings["registries"] == ",".join(registries) == env.get("REGISTRY")
                        and settings["source_checkpoints"] == teachers
                        and env.get("TEACHER_CHECKPOINT") == ",".join(item["path"] for item in teachers)
                        and settings["finetune"] == env.get("FINETUNE") == ("0" if label.endswith("pure") else "1"),
                        f"Student ordered final experts/registries changed: {label}")
            checkpoints[label] = {**checkpoint, "iteration": target - 1, "num_envs": num_envs, "num_variants": variants}
        else:
            artifacts = stage.get("artifact_fingerprints", [])
            require(artifacts, f"No artifact fingerprints: {label}")
            for artifact in artifacts:
                check_file(official, artifact)
            source = checkpoints[label.removeprefix("eval-").removeprefix("export-")]
            source_record = {key: source[key] for key in ("path", "sha256")}
            require(settings["source_checkpoints"] == [source_record], f"Evaluation/export uses another PT: {label}")
            if label.startswith("eval-"):
                expected_registry = registries[SKILLS.index(label.removeprefix("eval-teacher-"))] if label.startswith("eval-teacher-") else ",".join(registries)
                require(settings["num_envs"] == 64 and settings["eval_steps"] == 3000
                        and settings["eval_quality_schema"] == 1 and env.get("CHECKPOINT") == source["path"]
                        and settings["registries"] == env.get("REGISTRY") == expected_registry,
                        f"Official eval dimensions/source changed: {label}")
                quality = read(host_path(official, stage["evaluation_quality_report"]))
                require(digest(host_path(official, stage["evaluation_quality_report"])) == stage["evaluation_quality_sha256"], f"Quality SHA changed: {label}")
                require(quality.get("schema_version") == 1 and quality.get("status") == "completed"
                        and quality.get("num_envs") == 64 and quality.get("control_steps") == 3000
                        and quality.get("checkpoint_sha256") == source["sha256"]
                        and quality.get("finite_actions") is True and quality.get("finite_root_states") is True,
                        f"Incomplete official quality report: {label}")
                metrics = quality["metrics"]
                require(set(metrics) == {f"motion/error_{key}" for key in ("ref_pos", "ref_rot", "body_pos", "joint_pos")}, f"Missing quality metrics: {label}")
                for metric in metrics.values():
                    require(metric["samples"] == 192000 and metric["finite"] is True
                            and all(math.isfinite(metric[k]) for k in ("mean", "p95", "max")), f"Invalid tracking samples: {label}")
                require(quality.get("videos") and quality.get("tensorboard_events"), f"Missing quality media/TB: {label}")
                bound = {item["path"]: item["sha256"] for item in artifacts}
                require(bound.get(stage["evaluation_quality_report"]) == stage["evaluation_quality_sha256"], f"Unbound quality JSON: {label}")
                for video in quality["videos"]:
                    require(video["duration_seconds"] > 0 and bound.get(video["path"]) == video["sha256"], f"Unbound video: {label}")
                require(all(path in bound for path in quality["tensorboard_events"]), f"Unbound TB event: {label}")
            else:
                require(flag(stage["command"], "--training.checkpoint") == source["path"]
                        and flag(stage["command"], "--training.registry-name") == ",".join(registries), f"Wrong export inputs: {label}")
                require(stage.get("onnx_validation_reports"), f"Missing ONNX inference validation: {label}")
                bound = {item["path"]: item["sha256"] for item in artifacts}
                for item in stage["onnx_validation_reports"]:
                    report = read(host_path(official, item["report"]))
                    require(item["report"] in bound and report["status"] == "passed" and len(report["cases"]) == 30, f"Invalid student ONNX report: {label}")
                    models = {PurePosixPath(model["path"]).name: model for model in report["models"]}
                    for name in ("student.onnx", "depth_backbone.onnx"):
                        require(models[name]["path"] == f"{item['bundle']}/{name}"
                                and bound.get(models[name]["path"]) == models[name]["sha256"], f"Changed student ONNX: {label}")
    teacher_summary = read(official / "official/teacher-onnx-validation/summary.json")
    require(teacher_summary["status"] == "passed" and teacher_summary["profile"] == "official"
            and [item["skill"] for item in teacher_summary["teachers"]] == list(SKILLS), "Incomplete final teacher ONNX coverage")
    teacher_reports = []
    for item, checkpoint in zip(teacher_summary["teachers"], teachers):
        require(item["checkpoint"] == checkpoint["path"] and item["checkpoint_sha256"] == checkpoint["sha256"]
                and item["onnx"] == str(PurePosixPath(checkpoint["path"]).with_suffix(".onnx")), "Teacher ONNX/PT provenance changed")
        check_file(official, {"path": item["onnx"], "sha256": item["onnx_sha256"]})
        report = read(host_path(official, item["report"]))
        require(report["status"] == "passed" and report["sha256"] == item["onnx_sha256"]
                and len(report["cases"]) == item["cpu_cases"] > 0, "Invalid teacher ONNX inference report")
        require(json.loads(report["metadata"]["iteration"]) == 19999, "Teacher ONNX iteration differs from final PT")
        config = json.loads(report["metadata"]["experiment_config"])
        require(config["training"]["registry_name"] == registries[SKILLS.index(item["skill"])], "Wrong teacher ONNX registry metadata")
        teacher_reports.append({"path": item["report"], "sha256": digest(host_path(official, item["report"]))})
    return {"manifests_sha256": manifest_hashes, "checkpoints": checkpoints, "teacher_reports": teacher_reports,
            "teacher_summary_sha256": digest(official / "official/teacher-onnx-validation/summary.json")}


def capture(argv):
    return subprocess.check_output(argv, text=True).strip()


@contextlib.contextmanager
def official_lock(official, wait_seconds=0):
    # O_RDONLY avoids truncating or creating the native driver's lock file.
    with (official / "official-acceptance.lock").open("rb") as stream:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def process_gate(args):
    info = json.loads(capture(["docker", "inspect", args.training_container]))[0]
    mounts = {item["Destination"]: item["Source"] for item in info["Mounts"]}
    require(mounts.get("/workspace/php_parkour") == str(args.root / "source" / TRAIN_TREE), "Active training source mount changed")
    require(info["Image"] == args.image, "Training image ID changed")
    def mounted_path(container_path):
        path = PurePosixPath(container_path)
        candidates = [PurePosixPath(destination) for destination in mounts if path.is_relative_to(destination)]
        require(candidates, f"Training output has no actual Docker mount: {container_path}")
        destination = max(candidates, key=lambda candidate: len(candidate.parts))
        return (Path(mounts[str(destination)]) / path.relative_to(destination)).resolve()
    require(mounted_path(OFFICIAL) == args.official_output.resolve()
            and mounted_path("/outputs/official-full-driver.log") == args.driver_log.resolve(),
            "Observed manifests/log are not the training container's actual official output")
    if info["State"]["Running"]:
        top = capture(["docker", "top", args.training_container, "-eo", "pid,args"])
        if any(token in top for token in ACTIVE_TOKENS):
            return {"status": "waiting", "blockers": ["Official driver/training/evaluation/export process still alive"]}
    with args.driver_log.open("rb") as stream:
        stream.seek(max(0, args.driver_log.stat().st_size - 65536))
        lines = stream.read().decode(errors="replace").splitlines()
    if not lines or next((line.strip() for line in reversed(lines) if line.strip()), "") != MARKER:
        return {"status": "waiting", "blockers": ["Canonical driver final marker is not the last nonempty log line"]}
    try:
        with official_lock(args.official_output):
            pass
    except (OSError, BlockingIOError):
        return {"status": "waiting", "blockers": ["Official driver's lock unavailable"]}
    verify_frozen_source(args.root / "source" / TRAIN_TREE, TRAIN_TREE)
    return {"status": "driver_quiescent", "driver_exit_status": None,
            "scope": "Native shell exit status was not persisted; final marker, absent child processes and released lock are observed instead"}


def verify_frozen_source(source, tree):
    manifest = read(source / "source-manifest.json")
    require(manifest["source_tree_sha256"] == tree
            and hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest() == tree
            and len({item["path"] for item in manifest["files"]}) == len(manifest["files"]),
            "Source manifest tree identity changed")
    for item in manifest["files"]:
        rel = PurePosixPath(item["path"])
        require(not rel.is_absolute() and ".." not in rel.parts, "Invalid source manifest path")
        path = source / rel
        actual = hashlib.sha256(os.readlink(path).encode()).hexdigest() if item["symlink"] else digest(path)
        require(actual == item["sha256"] and path.lstat().st_mode & 0o777 == item["mode"], f"Changed frozen source file: {rel}")


def verify_snapshot(args):
    source = args.root / "source" / args.source_tree
    verify_frozen_source(source, args.source_tree)
    require(digest(source / "scripts/research/posttrain_coverage.py") == digest(__file__), "Monitor and frozen CPU/GPU runner are different revisions")
    require(args.source_tree != TRAIN_TREE, "Coverage must use its own frozen research snapshot")
    image = json.loads(capture(["docker", "image", "inspect", args.image]))[0]
    actual = hashlib.sha256(json.dumps({"Config": image["Config"], "RootFS": image["RootFS"]}, sort_keys=True).encode()).hexdigest()
    require(actual == IMAGE_CONTENTS, "Docker configuration/layers differ from the accepted image")
    return source


def idle_gpu(uuid):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from select_idle_gpu import inspect
    xml = capture(["nvidia-smi", "-q", "-x"])
    rows = inspect(xml)
    selected = [row for row in rows if row["uuid"] == uuid]
    require(len(selected) == 1, "Configured GPU UUID is absent/ambiguous")
    return selected[0], rows, xml


def docker_command(args, source, role, input_identity):
    name = f"php-parkour-posttrain-{role}-{input_identity[:12]}"
    command = ["docker", "run", "-d", "--name", name, "--init", "--network", "none", "--shm-size", "16g",
               "--label", f"php.posttrain.identity={input_identity}", "--label", f"php.posttrain.role={role}",
               "-e", "ACCEPT_EULA=Y", "-e", "OMNI_KIT_ACCEPT_EULA=YES", "-e", "PHP_DOCKER=1",
               "-e", "LOGGER=tensorboard", "-e", "WANDB_MODE=disabled", "-e", "PYTHONUNBUFFERED=1",
               "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-w", "/workspace/php_parkour",
               "-v", f"{source}:/workspace/php_parkour:ro",
               "-v", f"{args.official_output}:{OFFICIAL}:ro",
               "-v", f"{args.root / 'assets'}:/data/assets:ro",
               "-v", f"{args.coverage_output}:{COVERAGE}"]
    if role == "gpu":
        command += ["--gpus", f"device={args.gpu_uuid}", "-e", "CUDA_VISIBLE_DEVICES=0"]
    else:
        command += ["-e", "NVIDIA_VISIBLE_DEVICES=void", "-e", "CUDA_VISIBLE_DEVICES="]
    command += [args.image, "/opt/php/bin/train-python", "scripts/research/posttrain_coverage.py",
                "cpu-prepare" if role == "cpu" else "batch", "--selection", f"{COVERAGE}/selection.json"]
    return name, command


def container_state(args, source, role, name, input_identity):
    result = subprocess.run(["docker", "inspect", name], text=True, capture_output=True)
    if result.returncode:
        require("No such" in result.stderr, f"Cannot inspect own container: {result.stderr}")
        return None
    info = json.loads(result.stdout)[0]
    config, host = info["Config"], info["HostConfig"]
    require(config["Labels"].get("php.posttrain.identity") == input_identity
            and config["Labels"].get("php.posttrain.role") == role and info["Image"] == args.image
            and host["NetworkMode"] == "none" and config.get("WorkingDir") == "/workspace/php_parkour"
            and config.get("Entrypoint") == ["/opt/php/bin/entrypoint"], "Existing container has another identity/image/role/network/entrypoint")
    mounts = {item["Destination"]: item for item in info["Mounts"]}
    require(len(mounts) == len(info["Mounts"]) == 4
            and set(mounts) == {"/workspace/php_parkour", OFFICIAL, "/data/assets", COVERAGE},
            "Existing container has an extra mount overriding frozen inputs")
    for destination, source_path, writable in (("/workspace/php_parkour", source, False), (OFFICIAL, args.official_output, False),
                                              ("/data/assets", args.root / "assets", False), (COVERAGE, args.coverage_output, True)):
        mount = mounts.get(destination, {})
        require(mount.get("Source") == str(source_path) and mount.get("RW") is writable, "Existing container mount/access differs from the frozen cohort")
    environment = dict(item.split("=", 1) for item in config["Env"] if "=" in item)
    require(environment.get("LOGGER") == "tensorboard" and environment.get("WANDB_MODE") == "disabled"
            and environment.get("CUDA_VISIBLE_DEVICES") == ("0" if role == "gpu" else ""), "Existing container environment changed")
    requests = host.get("DeviceRequests") or []
    if role == "gpu":
        require(len(requests) == 1 and requests[0].get("DeviceIDs") == [args.gpu_uuid], "Existing container has another GPU UUID")
    else:
        require(not requests and environment.get("NVIDIA_VISIBLE_DEVICES") == "void", "CPU preparation container exposes GPUs")
    expected = docker_command(args, source, role, input_identity)[1]
    require(config["Cmd"] == expected[expected.index(args.image) + 1:], "Existing coverage entry point differs")
    return info


def observe(args):
    stages, blockers = stage_status(args.official_output)
    if blockers:
        return {"status": "waiting", "blockers": blockers, "gpu_started": False}
    process = process_gate(args)
    if process["status"] != "driver_quiescent":
        return process
    artifacts = inspect_artifacts(args.official_output, stages)
    source = verify_snapshot(args)
    selection = {"schema_version": 1, "training_source_tree": TRAIN_TREE, "coverage_source_tree": args.source_tree,
                 "image": args.image, "image_contents_sha256": IMAGE_CONTENTS, "gpu_uuid": args.gpu_uuid,
                 "official_output": OFFICIAL, "coverage_output": COVERAGE,
                 "host_coverage_output": str(args.coverage_output), "driver_log_sha256": digest(args.driver_log),
                 "driver_completion": process, **artifacts}
    selection["input_identity"] = identity(selection)
    return {"status": "ready_for_cpu_verification_gpu_not_started", "selection": selection, "source": str(source),
            "cpu_command": docker_command(args, source, "cpu", selection["input_identity"])[1],
            "gpu_command_requires_cpu_and_idle_gates": docker_command(args, source, "gpu", selection["input_identity"])[1]}


def tensor_finite(value, torch):
    if isinstance(value, torch.Tensor):
        require(not (value.is_floating_point() or value.is_complex()) or torch.isfinite(value).all().item(), "Nonfinite checkpoint policy tensor")
        return 1
    if isinstance(value, dict):
        return sum(tensor_finite(item, torch) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(tensor_finite(item, torch) for item in value)
    return 0


def verify_finished_batch(args, selection, summary):
    """Host standard-library check of all immutable per-case native evidence."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.research.eval_source_coverage import validate_native_report
    require(summary["input_identity"] == selection["input_identity"] and len(summary["cases"]) == 888,
            "Incomplete final batch accounting")
    source = args.root / "source" / args.source_tree
    mappings = ((COVERAGE, args.coverage_output), (OFFICIAL, args.official_output),
                ("/data/assets", args.root / "assets"), ("/workspace/php_parkour", source))
    def translate(value):
        if isinstance(value, dict):
            return {key: translate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [translate(item) for item in value]
        if isinstance(value, str) and value.startswith("/"):
            path = PurePosixPath(value)
            for prefix, destination in mappings:
                if path.is_relative_to(prefix):
                    return str(destination / path.relative_to(prefix))
        return value
    ready = read(args.coverage_output / "cpu-ready.json")
    require(ready["input_identity"] == selection["input_identity"] and len(ready["plans"]) == 3, "CPU cohort changed after execution")
    results = {(item["policy"], item["case_id"]): item for item in summary["cases"]}
    require(len(results) == 888, "Duplicate final attempt IDs")
    for policy, plan_record in zip(POLICIES, ready["plans"]):
        plan_path = args.coverage_output / policy / "plan.json"
        require(plan_record["policy"] == policy and digest(plan_path) == plan_record["sha256"], "Final source plan changed")
        plan = read(plan_path)
        require(plan["selected_sources"] == plan["inventory_total_sources"] == len(plan["cases"]) == 296, "Filtered final source coverage")
        for item in plan["cases"]:
            case_path = Path(translate(item["case"]["path"]))
            require(digest(case_path) == item["case"]["sha256"], "Final case identity changed")
            case = read(case_path)
            result = results[(policy, case["case_id"])]
            record_path = Path(translate(case["output"])) / "posttrain-attempt.json"
            require(read(record_path) == result and result["input_identity"] == selection["input_identity"]
                    and result["case_sha256"] == item["case"]["sha256"] and result["source_clip_id"] == case["source"]["source_clip_id"], "Final summary differs from original attempt")
            for artifact in result["artifacts"]:
                require(digest(translate(artifact["path"])) == artifact["sha256"], "Final attempt evidence missing/changed")
            if result["status"] == "execution_passed":
                quality = read(Path(translate(case["output"])) / "quality.json")
                validate_native_report(translate(quality), translate(case))
            else:
                require(result["status"] == "execution_failed", "Nonterminal first attempt")
    failures = sum(item["status"] == "execution_failed" for item in results.values())
    require(summary["execution_failed"] == failures and summary["execution_passed"] == 888 - failures
            and summary["status"] == ("execution_failed" if failures else "completed")
            and summary["quality_verified"] is False, "Final summary counts/quality status changed")


def scientific_check(selection):
    """Docker CPU only: native exact config recovery, tensor provenance, inventory."""
    require(Path("/.dockerenv").exists() and os.environ.get("CUDA_VISIBLE_DEVICES") == "", "Scientific checks require the Docker CPU-only entry point")
    import torch
    from holosoma.utils.eval_utils import CheckpointConfig
    from wbt_training.utils.checkpoint import load_saved_experiment_config
    from scripts.research.motion_coverage import inventory
    require(not torch.cuda.is_initialized(), "CPU gate unexpectedly initialized CUDA")
    targets = {"teacher": "holosoma.agents.ppo.ppo.PPO", "pure": "wbt_training.utils.student_teacher.PhpDistillation",
               "finetune": "wbt_training.utils.student_teacher.PhpDistillationPPO"}
    teachers, reports = [], []
    require(set(selection["checkpoints"]) == set(TRAINING), "CPU gate requires all seven canonical checkpoints")
    for label in TRAINING:
        expected = selection["checkpoints"][label]
        target, envs, variants = TRAINING[label]
        require((expected["iteration"], expected["num_envs"], expected["num_variants"]) == (target - 1, envs, variants),
                f"CPU selection is not the canonical final schedule: {label}")
        require(digest(expected["path"]) == expected["sha256"], "PT changed before CPU validation")
        loaded = torch.load(expected["path"], map_location="cpu", weights_only=False)
        require(loaded.get("iter") == loaded.get("iteration") == expected["iteration"], f"Embedded PT iteration mismatch: {label}")
        require(isinstance(loaded.get("experiment_config"), dict), f"Final PT lacks embedded config: {label}")
        saved, _ = load_saved_experiment_config(CheckpointConfig(checkpoint=expected["path"]))
        policy = "teacher" if label.startswith("teacher-") else label.removeprefix("student-")
        registry = f"file:///data/assets/motions-{label.removeprefix('teacher-')}" if policy == "teacher" else ",".join(f"file:///data/assets/motions-{s}" for s in SKILLS)
        kwargs = json.loads(saved.training.preprocess_hook_kwargs)
        require(saved.algo._target_ == targets[policy] and saved.training.num_envs == expected["num_envs"]
                and saved.training.seed == 42 and saved.training.registry_name == registry
                and kwargs.get("num_variants") == expected["num_variants"] and kwargs.get("add_onpath_obstacle") is True
                and kwargs.get("obstacle_seed") == 42 and saved.algo.config.save_interval == 500
                and saved.algo.config.num_steps_per_env == 24
                and saved.algo.config.num_mini_batches == (4 if policy == "teacher" else 96)
                and saved.algo.config.num_learning_epochs == (5 if policy == "teacher" else 2),
                f"Embedded canonical training config mismatch: {label}")
        states = [loaded["actor_model_state_dict"], loaded["critic_model_state_dict"]] if policy == "teacher" else [loaded["model_state_dict"]]
        counts = [tensor_finite(state, torch) for state in states]
        require(all(counts), f"Empty policy weights: {label}")
        expert_report = []
        if policy == "teacher":
            teachers.append(loaded)
        else:
            ordered = [selection["checkpoints"][f"teacher-{s}"]["path"] for s in SKILLS]
            require(saved.training.teacher_checkpoint == ",".join(ordered) and loaded.get("num_teachers") == 5
                    and loaded.get("teacher_loaded") == [True] * 5, f"Embedded ordered experts missing: {label}")
            expert_report = compare_frozen_experts(loaded, teachers, torch)
        reports.append({"label": label, **expected, "algorithm": saved.algo._target_, "registry": registry,
                        "tensor_counts": counts, "embedded_config_verified": True, "frozen_experts": expert_report})
    data = inventory("/data/assets")
    require(data["total_files"] == 296 and [sum(record["expert_ordinal"] == i for record in data["records"]) for i in range(5)] == [100, 56, 60, 40, 40], "Inventory is not the canonical 296 sources")
    require(not torch.cuda.is_initialized(), "Scientific validation initialized CUDA")
    return {"status": "cpu_scientific_checks_passed", "simulation_started": False, "checkpoints": reports,
            "inventory_sha256": data["inventory_sha256"], "total_sources": 296, "quality_verified": False}


def compare_frozen_experts(student, teachers, torch):
    """Use native PPO-to-MLP naming and native observation-normalizer loading."""
    from holosoma.agents.modules.student_teacher_modules import TeacherObsNormalizer
    require(len(teachers) == 5 and student.get("num_teachers") == 5 and student.get("teacher_loaded") == [True] * 5,
            "Five complete frozen experts are required")
    report = []
    for index, teacher in enumerate(teachers):
        prefix = f"teachers.{index}."
        actual = {key.removeprefix(prefix): value for key, value in student["model_state_dict"].items() if key.startswith(prefix)}
        renamed = {}
        for key, value in teacher["actor_model_state_dict"].items():
            for actor_prefix in ("actor_module.module.", "actor_module.", "actor."):
                if key.startswith(actor_prefix):
                    key = key.removeprefix(actor_prefix)
                    break
            if key != "std":  # Frozen teacher outputs the PPO mean, not sampled std.
                renamed[key] = value
        require(actual and set(actual) == set(renamed) and all(torch.equal(value, renamed[key]) for key, value in actual.items()),
                f"Frozen expert {index} parameters differ from the complete final teacher actor")
        prefix = f"teacher_obs_normalizers.{index}."
        buffers = {key.removeprefix(prefix): value for key, value in student["model_state_dict"].items() if key.startswith(prefix)}
        require(set(buffers) == {"mean", "std", "eps"}, f"Frozen expert {index} observation-normalizer buffers are incomplete")
        normalizer = TeacherObsNormalizer(buffers["mean"].shape[-1])
        normalizer.load_ppo_state_dict(teacher.get("actor_obs_normalizer_state_dict"))
        require(all(torch.equal(value, normalizer.state_dict()[key]) for key, value in buffers.items()),
                f"Frozen expert {index} observation normalizer differs from final teacher")
        report.append({"original_expert_ordinal": index, "actor_tensor_keys": sorted(actual), "actor_tensors": len(actual),
                       "normalizer_tensor_keys": sorted(buffers), "normalizer_tensors": len(buffers), "bitwise_equal_to_final_teacher": True})
    return report


def cpu_prepare(selection_path):
    selection = read(selection_path)
    base = Path(selection_path).parent
    report = scientific_check(selection)
    script = "scripts/research/eval_source_coverage.py"
    for policy in POLICIES:
        command = [sys.executable, script, "plan", "--policy", policy, "--output", f"{COVERAGE}/{policy}"]
        if policy == "teacher":
            for skill in SKILLS:
                command += ["--teacher-checkpoint", f"{skill}={selection['checkpoints'][f'teacher-{skill}']['path']}"]
        else:
            command += ["--checkpoint", selection["checkpoints"][f"student-{policy}"]["path"]]
        subprocess.run(command, check=True)
        subprocess.run([sys.executable, script, "preflight", "--plan", f"{COVERAGE}/{policy}/plan.json"], check=True)
    reports = verify_prepared_plans(selection)
    write(base / "cpu-ready.json", {**report, "input_identity": selection["input_identity"], "finished_utc": now(), "plans": reports})


def verify_prepared_plans(selection):
    from scripts.research.eval_source_coverage import verify_plan, validate_cpu_report
    reports = []
    source_ids = None
    for policy in POLICIES:
        path = Path(COVERAGE) / policy / "plan.json"
        plan = verify_plan(path)
        require(plan["policy"] == policy and plan["selected_sources"] == plan["inventory_total_sources"] == 296, "A post-train plan filtered source coverage")
        inventory = read(plan["source_inventory"]["path"])
        ids = [item["source_clip_id"] for item in plan["cases"]]
        require(ids == [item["source_clip_id"] for item in inventory["records"]] and (source_ids is None or source_ids == ids), "Missing/reordered post-train sources")
        source_ids = ids
        summary = read(path.parent / "cpu-preflight-summary.json")
        require(summary["status"] == "completed" and len(summary["cases"]) == 296
                and all(item["status"] == "cpu_preflight_passed_gpu_not_run" for item in summary["cases"]), "Incomplete full-source CPU preflight")
        for item in plan["cases"]:
            case = read(item["case"]["path"])
            label = f"teacher-{case['source']['skill']}" if policy == "teacher" else f"student-{policy}"
            expected = selection["checkpoints"][label]
            require(case["checkpoint"] == expected["path"] and case["checkpoint_sha256"] == expected["sha256"]
                    and case["max_steps"] == case["source"]["frames"], "Case PT or complete-source cap changed")
            validate_cpu_report(read(Path(case["output"]) / "cpu-preflight/report.json"), case)
        reports.append({"policy": policy, "path": str(path), "sha256": digest(path), "sources": 296})
    return reports


def attempt_case(selection, policy, item, validate_native_report):
    case = read(item["case"]["path"])
    output = Path(case["output"])
    record_path, started_path, log = output / "posttrain-attempt.json", output / "posttrain-started.json", output / "posttrain-native.log"
    if record_path.exists():
        result = read(record_path)
        require(result["input_identity"] == selection["input_identity"] and result["case_sha256"] == item["case"]["sha256"]
                and result["policy"] == policy and result["case_id"] == case["case_id"]
                and result["source_clip_id"] == case["source"]["source_clip_id"]
                and result["status"] in ("execution_passed", "execution_failed"), "Existing attempt belongs to another cohort")
        for artifact in result["artifacts"]:
            require(digest(artifact["path"]) == artifact["sha256"], "Existing attempt evidence changed")
        if result["status"] == "execution_passed":
            validate_native_report(read(output / "quality.json"), case)
        return result
    result = {"policy": policy, "case_id": case["case_id"], "source_clip_id": case["source"]["source_clip_id"],
              "input_identity": selection["input_identity"], "case_sha256": item["case"]["sha256"], "quality_verified": False,
              "status": "execution_failed", "returncode": None, "artifacts": []}
    if started_path.exists() or log.exists() or any((output / name).exists() for name in ("quality.json", "native", "runtime-assets", "trajectory.jsonl")):
        result["error"] = "Interrupted/ambiguous first attempt retained; never automatically rerun"
    else:
        write(started_path, {"input_identity": selection["input_identity"], "case_sha256": item["case"]["sha256"], "started_utc": now()})
        try:
            with log.open("x") as stream:
                completed = subprocess.run([sys.executable, "scripts/research/source_coverage_probe.py", "--case", item["case"]["path"]],
                                           stdout=stream, stderr=subprocess.STDOUT, env={**os.environ, "LOGGER": "tensorboard", "WANDB_MODE": "disabled"})
            result["returncode"] = completed.returncode
            quality = read(output / "quality.json")
            validate_native_report(quality, case)
            require(completed.returncode == 0, "Native worker returned nonzero")
            result.update(status="execution_passed", stop_reason=quality["stop_reason"], policy_steps=quality["control_steps"], reference_boundary_reached=quality["first_attempt_reference_boundary_reached"])
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
            result["error"] = f"{type(error).__name__}: {error}"
    for path in (started_path, log, output / "quality.json"):
        if path.is_file():
            result["artifacts"].append({"path": str(path), "sha256": digest(path)})
    result["finished_utc"] = now()
    write(record_path, result)
    return result


def batch(selection_path):
    """Continue unattempted cases; failed skills and interrupted attempts persist."""
    require(Path("/.dockerenv").exists(), "Native batch runs only inside Docker")
    from scripts.research.eval_source_coverage import verify_plan, validate_native_report
    selection = read(selection_path)
    base = Path(selection_path).parent
    ready = read(base / "cpu-ready.json")
    require(ready["status"] == "cpu_scientific_checks_passed" and ready["input_identity"] == selection["input_identity"]
            and ready["plans"] == verify_prepared_plans(selection), "CPU preparation/input identity changed")
    write(base / f"actual-gpu-{time.time_ns()}.json", verify_gpu_mapping(selection))
    summary = {"schema_version": 1, "input_identity": selection["input_identity"], "status": "running", "scope": "296 original sources per teacher/pure/finetune; one variant/seed42/first attempt, not skill success", "quality_verified": False, "cases": []}
    for policy in POLICIES:
        plan = verify_plan(Path(COVERAGE) / policy / "plan.json")
        for item in plan["cases"]:
            summary["cases"].append(attempt_case(selection, policy, item, validate_native_report))
            write(base / "summary.json", summary)
    require(len(summary["cases"]) == 888, "Final coverage accounting must contain all 888 sources/policies")
    failures = sum(item["status"] == "execution_failed" for item in summary["cases"])
    summary.update(status="execution_failed" if failures else "completed", execution_failed=failures,
                   execution_passed=888 - failures, finished_utc=now())
    write(base / "summary.json", summary)
    return int(bool(failures))


def verify_gpu_mapping(selection):
    """Actual container visibility, after CPU preparation and before workers."""
    import torch
    uuids = capture(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"]).splitlines()
    require([value.strip() for value in uuids] == [selection["gpu_uuid"]], "Actual container NVIDIA UUID visibility differs from the fixed GPU")
    require(os.environ.get("CUDA_VISIBLE_DEVICES") == "0" and torch.cuda.device_count() == 1,
            "Actual Torch device mapping is not exactly one cuda:0")
    properties = torch.cuda.get_device_properties(0)
    actual_uuid = getattr(properties, "uuid", None)
    if actual_uuid is not None:
        raw = getattr(actual_uuid, "bytes", None)
        normalized = f"GPU-{uuid.UUID(bytes=bytes(raw))}" if raw is not None else "GPU-" + str(uuid.UUID(str(actual_uuid).removeprefix("GPU-")))
        require(normalized == selection["gpu_uuid"], "Torch cuda:0 maps to another physical UUID")
    return {"observed_utc": now(), "nvidia_visible_uuids": uuids, "torch_device_count": 1, "torch_device": "cuda:0",
            "torch_uuid": str(actual_uuid) if actual_uuid is not None else None,
            "device_name": properties.name, "total_memory_bytes": properties.total_memory,
            "scope": "GPU mapping only; no policy/skill success inferred"}


def advance(args, observation):
    """Only called in explicit once/watch modes while holding the monitor lock."""
    selection = observation["selection"]
    path = args.coverage_output / "selection.json"
    if path.exists():
        require(read(path) == selection, "Existing coverage output has another immutable input identity; preserve it and choose a fresh output")
    else:
        write(path, selection)
    source = Path(observation["source"])
    with official_lock(args.official_output):
        for role in ("cpu", "gpu"):
            name, command = docker_command(args, source, role, selection["input_identity"])
            info = container_state(args, source, role, name, selection["input_identity"])
            if info is not None and info["State"]["Running"]:
                return {"status": "waiting", "blockers": [f"Own {role} coverage container is running"], "container": name}
            if role == "cpu" and info is not None:
                require(info["State"]["ExitCode"] == 0 and (args.coverage_output / "cpu-ready.json").is_file(), "CPU preparation failed/interrupted; preserve output and use a fresh cohort after review")
                ready = read(args.coverage_output / "cpu-ready.json")
                require(ready["status"] == "cpu_scientific_checks_passed" and ready["input_identity"] == selection["input_identity"]
                        and ready["total_sources"] == 296 and len(ready["checkpoints"]) == 7, "CPU report identity/coverage changed")
                continue
            if role == "gpu" and info is not None:
                summary_path = args.coverage_output / "summary.json"
                if summary_path.exists() and read(summary_path).get("status") in ("completed", "execution_failed"):
                    summary = read(summary_path)
                    verify_finished_batch(args, selection, summary)
                    require(info["State"]["ExitCode"] == (0 if summary["status"] == "completed" else 1), "Contradictory final batch exit status")
                    return {"status": summary["status"], "container": name, "container_exit_code": info["State"]["ExitCode"], "quality_verified": False}
                require(args.resume_interrupted, "Own GPU batch was interrupted; use --resume-interrupted to continue unattempted cases, retaining the interrupted case as execution_failed")
            if role == "gpu":
                gpu, rows, xml = idle_gpu(args.gpu_uuid)
                if not gpu["idle"]:
                    return {"status": "waiting", "blockers": ["Configured fixed GPU UUID is occupied"], "gpu": gpu}
                write(args.coverage_output / "gpu-before-start.json", {"observed_utc": now(), "selected": gpu, "gpus": rows})
                (args.coverage_output / "gpu-before-start.xml").write_text(xml)
            if info is None:
                container_id = capture(command)
            else:
                container_id = capture(["docker", "start", name])
            return {"status": "waiting", "blockers": [f"Started isolated {role} coverage container"], "container": name, "id": container_id}
    raise RuntimeError("Unexpected post-train state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dry-run", "once", "watch", "cpu-prepare", "batch"))
    parser.add_argument("--root", type=Path, default=Path("/diff/dzp_is_sb/php-parkour-research"))
    parser.add_argument("--source-tree")
    parser.add_argument("--image", default="sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd")
    parser.add_argument("--gpu-uuid", default="GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5")
    parser.add_argument("--training-container", default="php-parkour-cloud-research")
    parser.add_argument("--official-output", type=Path)
    parser.add_argument("--driver-log", type=Path)
    parser.add_argument("--coverage-output", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--resume-interrupted", action="store_true")
    args = parser.parse_args()
    if args.action in ("cpu-prepare", "batch"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        require(args.selection is not None, "--selection is required inside Docker")
        selection = read(args.selection)
        require(selection["input_identity"] == identity({key: value for key, value in selection.items() if key != "input_identity"}), "Selection identity changed")
        # Host releases its launch-time lock after docker run returns. The
        # child then holds the same native lock throughout CPU or GPU work.
        with official_lock(Path(OFFICIAL), wait_seconds=60):
            return cpu_prepare(args.selection) if args.action == "cpu-prepare" else batch(args.selection)
    args.root = args.root.resolve()
    args.official_output = (args.official_output or args.root / "outputs/official-full").resolve()
    args.driver_log = (args.driver_log or args.root / "outputs/official-full-driver.log").resolve()
    args.coverage_output = (args.coverage_output or args.root / "outputs/coverage-official-final").resolve()
    require(args.source_tree is not None and len(args.source_tree) == 64 and all(c in "0123456789abcdef" for c in args.source_tree), "Specify the independently frozen coverage --source-tree SHA")
    require(not args.coverage_output.is_relative_to(args.official_output) and not args.official_output.is_relative_to(args.coverage_output), "Coverage and official outputs must be separate")
    require(args.poll_seconds >= 1, "Poll interval must be positive")
    if args.action == "dry-run":
        print(json.dumps(observe(args), indent=2))
        return 0
    (args.root / "outputs").mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as locks:
        global_lock = locks.enter_context((args.root / "outputs/.posttrain-coverage.lock").open("a"))
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        args.coverage_output.mkdir(parents=True, exist_ok=True)
        monitor_lock = locks.enter_context((args.coverage_output / "monitor.lock").open("a"))
        fcntl.flock(monitor_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                observation = observe(args)
                if observation["status"] == "ready_for_cpu_verification_gpu_not_started":
                    observation = advance(args, observation)
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                write(args.coverage_output / "monitor-status.json", {"observed_utc": now(), "status": "rejected",
                      "error": f"{type(error).__name__}: {error}", "quality_verified": False})
                raise
            write(args.coverage_output / "monitor-status.json", {"observed_utc": now(), **observation})
            print(json.dumps(observation, indent=2), flush=True)
            if args.action == "once" or observation["status"] in ("completed", "execution_failed"):
                return int(observation["status"] == "execution_failed")
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "rejected", "error": f"{type(error).__name__}: {error}", "quality_verified": False}), file=sys.stderr)
        raise SystemExit(1)
