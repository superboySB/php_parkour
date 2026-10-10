#!/usr/bin/env python3
"""Auditable PHP teacher/student pipeline using the official launchers.

The smoke profile proves execution only. The official profile preserves the
published iteration counts; completing those counts alone is not convergence.
No host packages or W&B credentials are needed. Run in the research Docker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ("locomotion", "low-step", "high-step", "low-climb-76", "high-climb-76")
TEACHER_PRESETS = ("g1-wbt-terrain-ref", "g1-wbt-terrain-no-heightscan", "g1-wbt-terrain-ref-noscale",
                   "g1-wbt-terrain-no-heightscan-noscale", "g1-wbt-terrain-ref-pelvis", "g1-wbt-terrain-no-heightscan-pelvis")
QUALITY_METRICS = {"motion/error_ref_pos", "motion/error_ref_rot", "motion/error_body_pos", "motion/error_joint_pos"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def iteration_timings(log: str) -> list[float]:
    # Rich wraps long computation rows over multiple bordered lines.
    clean = log.replace("│", " ")
    return [float(collection) + float(learning) for collection, learning in
            re.findall(r"Collection:\s*([0-9.]+)s,\s*Learning\s+([0-9.]+)s", clean)]


def write_manifest(path: Path, evidence: dict) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def resume_provenance(settings: dict, command: list[str]) -> dict:
    """Compare the training inputs while allowing a larger iteration target.

    Pre-existing manifests recorded the requested environment override (None
    for defaults); the actual native command records its resolved value.
    A teacher stage may be resumed while extending the multi-skill driver, so
    only that stage's registry and ordered expert hashes belong in this key.
    """
    required = {"profile", "num_envs", "registries", "finetune", "source_checkpoints"}
    if not isinstance(settings, dict) or not required <= settings.keys():
        raise ValueError("Recorded training settings are insufficient to verify safe resume provenance")
    if "--training.num-envs" not in command:
        raise ValueError("Recorded training command has no resolved environment count")
    return {"profile": settings["profile"],
            "num_envs": int(command[command.index("--training.num-envs") + 1]),
            "registries": settings["registries"], "finetune": settings["finetune"],
            "teacher_checkpoint_sha256": [source["sha256"] for source in settings["source_checkpoints"]]}


def load_quality_report(path: Path, source_sha: str, steps: int, num_envs: int) -> dict:
    quality = json.loads(path.read_text())
    if not isinstance(quality, dict) or not (quality.get("schema_version") == 1 and quality.get("status") == "completed"
            and quality.get("control_steps") == steps and quality.get("num_envs") == num_envs
            and quality.get("checkpoint_sha256") == source_sha
            and quality.get("finite_actions") is True and quality.get("finite_root_states") is True):
        raise ValueError("Missing or inconsistent rollout metadata")
    metrics = quality.get("metrics", {})
    if not isinstance(metrics, dict) or set(metrics) != QUALITY_METRICS:
        raise ValueError("Incomplete native tracking metrics")
    for metric in metrics.values():
        if not (metric.get("finite") is True and metric.get("samples") == steps * num_envs
                and all(isinstance(metric.get(key), (int, float)) and math.isfinite(metric[key]) for key in ("mean", "p95", "max"))):
            raise ValueError("Invalid native tracking samples/statistics")
    videos, events = quality.get("videos"), quality.get("tensorboard_events")
    if not videos or not events:
        raise ValueError("Quality report requires associated video and TensorBoard events")
    for video in videos:
        actual = fingerprint(Path(video["path"]))
        if actual["sha256"] != video.get("sha256") or not video.get("duration_seconds", 0) > 0:
            raise ValueError("Quality video changed or has no duration")
    for event in events:
        if not Path(event).is_file() or not Path(event).stat().st_size:
            raise ValueError("Missing TensorBoard event artifact")
    return quality


def validate_export_report(path: Path, bundle: Path) -> None:
    validation = json.loads(path.read_text())
    if validation.get("status") != "passed" or len(validation.get("cases", [])) != 30:
        raise ValueError("Incomplete ONNX inference validation report")
    models = {Path(model["path"]).name: model for model in validation.get("models", [])}
    for name in ("depth_backbone.onnx", "student.onnx"):
        if name not in models or fingerprint(bundle / name)["sha256"] != models[name].get("sha256"):
            raise ValueError("Exported ONNX differs from the inference-validated model")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "teachers", "teacher-presets", "distill-pure", "distill-finetune", "eval-teachers", "eval-student", "export"))
    parser.add_argument("--profile", choices=("smoke", "official"), required=True)
    parser.add_argument("--assets", type=Path, default=Path(os.environ.get("PHP_ASSET_ROOT", "/data/assets")))
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("PHP_OUTPUT_ROOT", "/outputs")) / "training")
    parser.add_argument("--skills", nargs="+", choices=SKILLS, default=list(SKILLS))
    parser.add_argument("--num-envs", type=int)
    parser.add_argument("--iterations", type=int, help="Target total iterations, including any restored checkpoint; recorded as an override")
    parser.add_argument("--student-kind", choices=("pure", "finetune"), default="finetune")
    parser.add_argument("--checkpoint", type=Path, help="Explicit checkpoint for eval-student/export")
    parser.add_argument("--eval-steps", type=int, default=250)
    parser.add_argument("--inference-python", default=os.environ.get("PHP_INFERENCE_PYTHON", "/opt/php/bin/inference-python"))
    parser.add_argument("--resume", action="store_true", help="Resume the checkpoint saved by this pipeline")
    parser.add_argument("--skip-completed", action="store_true", help="Skip verified successful stages with the same settings and sufficient iterations")
    parser.add_argument("--plan", action="store_true", help="Print commands and exit without simulator or download")
    args = parser.parse_args()
    if args.action == "teacher-presets" and args.profile != "smoke":
        parser.error("teacher-presets is a bounded smoke sweep; official five-skill training uses the published noscale launcher")
    if not (Path("/.dockerenv").exists() or os.environ.get("PHP_DOCKER") == "1") and not args.plan:
        parser.error("This pipeline must run inside Docker")
    if args.num_envs is not None and args.num_envs < 1 or args.iterations is not None and args.iterations < 1 or args.eval_steps < 1:
        parser.error("Environment, iteration and evaluation step counts must be positive")
    run_root = args.output.resolve() / args.profile
    manifests = run_root / "manifests"
    if not args.plan:
        manifests.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(LOGGER="tensorboard", WANDB_MODE="disabled", NGPUS=env.get("NGPUS", "1"), OMNI_KIT_ACCEPT_EULA="YES", PYTHONUNBUFFERED="1")
    env.setdefault("HSSIM_PYTHON", sys.executable)
    # One selected physical GPU is chosen by the outer Docker/cloud launcher.
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    verified_checkpoints: dict[str, tuple[str, int, str]] = {}
    resume_points: dict[str, tuple[str, int, str] | None] = {}

    def registry(skill: str) -> str:
        return (args.assets.resolve() / f"motions-{skill}").as_uri()

    def verify_checkpoint(path: Path) -> tuple[str, int, str]:
        import torch
        loaded = torch.load(path, map_location="cpu", weights_only=False)
        if not isinstance(loaded, dict):
            raise ValueError(f"Incomplete native training checkpoint: {path}")
        # Core PPO saves separate actor/critic dictionaries; distillation saves
        # the composite policy under model_state_dict.
        model = loaded.get("model_state_dict")
        actor, critic = loaded.get("actor_model_state_dict"), loaded.get("critic_model_state_dict")
        if not (isinstance(model, dict) and model or isinstance(actor, dict) and actor and isinstance(critic, dict) and critic):
            raise ValueError(f"Incomplete native policy tensors in checkpoint: {path}")
        sections = {"model_state_dict": model} if isinstance(model, dict) and model else {"actor_model_state_dict": actor, "critic_model_state_dict": critic}
        for section, state in sections.items():
            tensor_count = 0
            def inspect(value, name: str) -> None:
                nonlocal tensor_count
                if isinstance(value, torch.Tensor):
                    tensor_count += 1
                    if (value.is_floating_point() or value.is_complex()) and not torch.isfinite(value).all().item():
                        raise ValueError(f"Non-finite policy tensor {name} in checkpoint: {path}")
                elif isinstance(value, dict):
                    for key, item in value.items():
                        inspect(item, f"{name}.{key}")
                elif isinstance(value, (list, tuple)):
                    for index, item in enumerate(value):
                        inspect(item, f"{name}[{index}]")
            inspect(state, section)
            if tensor_count == 0:
                raise ValueError(f"No policy tensors in {section} of checkpoint: {path}")
        iteration = loaded.get("iter")
        if not isinstance(iteration, int) or iteration < 0:
            raise ValueError(f"Invalid iteration in native checkpoint: {path}")
        del loaded
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return str(path.resolve()), iteration, digest.hexdigest()

    def checkpoint_info(label: str, for_resume: bool = False) -> tuple[str, int, str]:
        cache_key = f"{label}:{for_resume}"
        if cache_key in verified_checkpoints:
            return verified_checkpoints[cache_key]
        path = manifests / f"{label}.json"
        if path.exists():
            evidence = json.loads(path.read_text())
            if evidence.get("profile") != args.profile or evidence.get("label") != label:
                raise ValueError(f"Checkpoint manifest has inconsistent provenance: {path}")
            saved = evidence.get("checkpoint")
            if not for_resume and evidence.get("status") != "passed":
                raise ValueError(f"Stage {label} did not finish successfully; resume it before using its checkpoint")
            if saved and Path(saved).is_file():
                verified = verify_checkpoint(Path(saved))
                if evidence.get("checkpoint_sha256") and evidence["checkpoint_sha256"] != verified[2]:
                    raise ValueError(f"Checkpoint bytes changed since the recorded run: {saved}")
                verified_checkpoints[cache_key] = verified
                return verified
            if for_resume:
                # Interrupted stages can leave a complete save before their
                # manifest was finalized. Validate it structurally, never infer
                # readiness from a filename or a partial log line.
                candidates = sorted((run_root / label).glob("**/model_*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
                for candidate in candidates:
                    try:
                        verified = verify_checkpoint(candidate)
                    except Exception:
                        continue
                    verified_checkpoints[cache_key] = verified
                    return verified
        if args.plan:
            return f"<{label}-checkpoint>", 0, ""
        raise FileNotFoundError(f"No checkpoint recorded for {label}: run the matching training stage first")

    def checkpoint(label: str, for_resume: bool = False) -> str:
        return checkpoint_info(label, for_resume)[0]

    def resume_point(label: str) -> tuple[str, int, str] | None:
        if label not in resume_points:
            try:
                resume_points[label] = checkpoint_info(label, for_resume=True)
            except FileNotFoundError:
                # A sequential multi-stage run may stop before later stages
                # start, or before a failed stage's first completed save.
                print(f"No completed checkpoint for {label}; starting this stage from iteration zero", flush=True)
                resume_points[label] = None
        return resume_points[label]

    def execute(label: str, command: list[str], extra_env: dict[str, str] | None = None) -> None:
        child_env = env | (extra_env or {})
        print(json.dumps({"label": label, "command": command, "environment": {k: child_env[k] for k in ("LOGGER", "NGPUS", "CUDA_VISIBLE_DEVICES", "REGISTRY", "TEACHER_CHECKPOINT", "CHECKPOINT", "FINETUNE") if k in child_env}}, ensure_ascii=False), flush=True)
        if args.plan:
            return
        target = (args.iterations or (2 if args.profile == "smoke" else (20000 if label.startswith("teacher-") else 10000 if label == "student-pure" else 30000))) if label.startswith(("teacher-", "student-")) else None
        # A student's own resume PT is state to restore, not another expert.
        # CHECKPOINT is an eval-launcher input; an inherited value must not
        # contaminate the ordered teacher provenance of a training stage.
        source_paths = ([value.strip() for value in child_env.get("TEACHER_CHECKPOINT", "").split(",") if value.strip()]
                        if label.startswith("student-") else [])
        if label.startswith("eval-") and child_env.get("CHECKPOINT"):
            source_paths.append(child_env["CHECKPOINT"])
        if label.startswith("export-") and "--training.checkpoint" in command:
            source_paths.append(command[command.index("--training.checkpoint") + 1])
        sources = [{"path": value, "sha256": verify_checkpoint(Path(value))[2]} for value in source_paths]
        settings = {"profile": args.profile, "skills": args.skills, "assets": str(args.assets.resolve()),
                    "num_envs": args.num_envs, "iterations_target": target,
                    "registries": child_env.get("REGISTRY"), "finetune": child_env.get("FINETUNE"),
                    "source_checkpoints": sources, "eval_steps": args.eval_steps if label.startswith("eval-") else None,
                    "eval_quality_schema": 1 if label.startswith("eval-") else None}
        manifest = manifests / f"{label}.json"
        if args.resume and target is not None:
            restored = resume_point(label)
            old = json.loads(manifest.read_text()) if manifest.exists() else {}
            if restored is not None:
                previous = resume_provenance(old.get("settings"), old.get("command", []))
                requested = resume_provenance(settings, command)
                differences = [key for key in requested if previous[key] != requested[key]]
                if differences:
                    raise ValueError(f"Resume provenance mismatch for {label}: {', '.join(differences)}. "
                                     "Use a new output directory for different training inputs.")
            previously_passed = old.get("status") == "passed"
            if previously_passed and restored is not None and restored[1] >= target - 1:
                print(f"Verified checkpoint already reaches target {target}; no additional training for {label}", flush=True)
                return
        if args.skip_completed and manifest.exists():
            old = json.loads(manifest.read_text())
            if old.get("status") == "passed" and old.get("settings") == settings:
                artifacts_valid = True
                if label.startswith(("eval-", "export-")):
                    try:
                        artifacts = old.get("artifact_fingerprints", [])
                        if not artifacts or any(fingerprint(Path(item["path"])) != item for item in artifacts):
                            raise ValueError("Missing or changed output artifacts")
                        if label.startswith("eval-"):
                            quality_path = Path(old["evaluation_quality_report"])
                            load_quality_report(quality_path, sources[0]["sha256"], args.eval_steps, int(child_env["NUM_ENVS"]))
                            if fingerprint(quality_path)["sha256"] != old["evaluation_quality_sha256"]:
                                raise ValueError("Quality report changed")
                        else:
                            if not old.get("onnx_validation_reports"):
                                raise ValueError("Missing ONNX inference report")
                            for item in old["onnx_validation_reports"]:
                                validate_export_report(Path(item["report"]), Path(item["bundle"]))
                    except (OSError, ValueError, KeyError, TypeError, AttributeError):
                        artifacts_valid = False
                        print(f"Output artifacts are missing or changed; rerunning {label}", flush=True)
                if artifacts_valid and (target is None or checkpoint_info(label)[1] >= target - 1):
                    print(f"Verified completed stage, skipping {label}", flush=True)
                    return
        started = time.monotonic()
        started_unix = time.time()
        evidence = {"label": label, "profile": args.profile, "started_utc": now(), "command": command,
                    "environment": {key: child_env[key] for key in ("LOGGER", "NGPUS", "CUDA_VISIBLE_DEVICES", "HSSIM_PYTHON", "REGISTRY", "TEACHER_CHECKPOINT", "CHECKPOINT", "FINETUNE") if key in child_env},
                    "settings": settings, "overrides": {"num_envs": args.num_envs, "iterations_target": args.iterations},
                    "quality_verified": False, "scope": "execution smoke only" if args.profile == "smoke" else
                    "official preset with explicit overrides; quality requires rollout evaluation" if args.num_envs is not None or args.iterations is not None else
                    "official default training schedule; quality requires rollout evaluation"}
        if "--training.checkpoint" in command:
            restored = command[command.index("--training.checkpoint") + 1]
            evidence["resume_checkpoint"] = restored
        if manifest.exists():
            history = manifests / "history"
            history.mkdir(exist_ok=True)
            (history / f"{label}-{time.time_ns()}.json").write_bytes(manifest.read_bytes())
        evidence["status"] = "running"
        write_manifest(manifest, evidence)
        log_path = run_root / f"{label}-{time.time_ns()}.log"
        current_log = run_root / f"{label}.log"
        if current_log.is_symlink() or current_log.exists():
            current_log.unlink()
        current_log.symlink_to(log_path.name)
        with log_path.open("w") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            returncode = process.wait()
        evidence.update(status="passed" if returncode == 0 else "failed", returncode=returncode,
                        finished_utc=now(), elapsed_seconds=time.monotonic() - started, log=str(log_path))
        timing = iteration_timings(log_path.read_text())
        if timing:
            stable = timing[2:] if len(timing) > 4 else timing
            median = statistics.median(stable)
            measured_envs = int(command[command.index("--training.num-envs") + 1]) if "--training.num-envs" in command else None
            evidence["performance"] = {"iteration_samples": len(timing), "median_collection_plus_learning_seconds": median,
                "measured_num_envs": measured_envs,
                "estimate_scope": "Measured collection+learning only; excludes simulator initialization, exports/checkpoint writes and evaluation. No scaling to another environment count."}
            default_envs = 4096 if label.startswith("teacher-") else 2048
            if args.profile == "official" and measured_envs == default_envs:
                evidence["performance"]["estimated_default_schedule_core_hours"] = median * (20000 if label.startswith("teacher-") else 10000 if label == "student-pure" else 30000) / 3600
        candidates = list((run_root / label).glob("**/model_*.pt"))
        if candidates:
            for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    verified = verify_checkpoint(candidate)
                except Exception:
                    continue
                evidence.update(checkpoint=verified[0], checkpoint_iteration=verified[1], checkpoint_sha256=verified[2])
                break
        bundles = sorted({str(path.parent.resolve()) for path in (run_root / label).glob("**/student.onnx")
                          if (path.parent / "depth_backbone.onnx").is_file()
                          and (not label.startswith("export-") or min(path.stat().st_mtime, (path.parent / "depth_backbone.onnx").stat().st_mtime) >= started_unix)})
        if bundles:
            evidence["onnx_bundle_directories"] = bundles
        if label.startswith("export-") and returncode == 0 and not bundles:
            evidence.update(status="failed", error="Export exited without the requested depth_backbone.onnx/student.onnx bundle")
            returncode = 1
        if label.startswith("export-") and returncode == 0:
            validations = []
            for index, bundle in enumerate(bundles):
                report = run_root / label / f"onnx-validation-{index}.json"
                result = subprocess.run([args.inference_python, str(ROOT / "scripts/research/validate_onnx.py"), "--models", bundle, "--output", str(report)],
                                        cwd=ROOT, env=child_env, text=True, capture_output=True)
                with log_path.open("a") as log:
                    log.write(result.stdout + result.stderr)
                if result.returncode or not report.is_file():
                    evidence.update(status="failed", error="Exported bundle failed real ONNX checker/Runtime inference validation")
                    returncode = 1
                    break
                try:
                    validate_export_report(report, Path(bundle))
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    evidence.update(status="failed", error=f"Invalid ONNX validation evidence: {error}")
                    returncode = 1
                    break
                validations.append({"bundle": bundle, "report": str(report.resolve())})
            evidence["onnx_validation_reports"] = validations
            if returncode == 0:
                evidence["artifact_fingerprints"] = [fingerprint(path) for item in validations
                    for path in (Path(item["bundle"]) / "depth_backbone.onnx", Path(item["bundle"]) / "student.onnx", Path(item["report"]))]
        if label.startswith("eval-"):
            videos = []
            for path in sorted((run_root / label).glob("**/*.mp4")):
                if path.stat().st_mtime < started_unix:
                    continue
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], text=True, capture_output=True)
                try:
                    duration = float(json.loads(probe.stdout)["format"]["duration"])
                except (ValueError, KeyError, TypeError):
                    continue
                if probe.returncode == 0 and duration > 0:
                    videos.append({"path": str(path.resolve()), "duration_seconds": duration})
            evidence["evaluation_videos"] = videos
            if returncode == 0 and not videos:
                evidence.update(status="failed", error="Evaluation exited without a new readable nonempty MP4")
                returncode = 1
            quality_path = run_root / label / "quality.json"
            try:
                if quality_path.stat().st_mtime < started_unix:
                    raise ValueError("Stale rollout quality report")
                quality = load_quality_report(quality_path, sources[0]["sha256"], args.eval_steps, int(child_env["NUM_ENVS"]))
                fresh_paths = {video["path"] for video in videos}
                if any(video["path"] not in fresh_paths for video in quality["videos"]):
                    raise ValueError("Quality report references video outside this evaluation")
                evidence["evaluation_quality_report"] = str(quality_path.resolve())
                evidence["evaluation_quality_sha256"] = fingerprint(quality_path)["sha256"]
                evidence["evaluation_tensorboard_events"] = quality["tensorboard_events"]
                evidence["artifact_fingerprints"] = [fingerprint(path) for path in
                    {quality_path, *(Path(video["path"]) for video in quality["videos"]), *(Path(event) for event in quality["tensorboard_events"])}]
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                if returncode == 0:
                    evidence.update(status="failed", error=f"Evaluation quality report validation failed: {error}")
                    returncode = 1
        if target is not None and returncode == 0 and evidence.get("checkpoint_iteration", -1) < target - 1:
            evidence.update(status="failed", error="Process exited without a valid checkpoint at the requested target iteration")
            returncode = 1
        write_manifest(manifest, evidence)
        if returncode:
            raise SystemExit(returncode)

    def train_flags(label: str, official_envs: int) -> list[str]:
        num_envs = args.num_envs or (64 if args.profile == "smoke" else official_envs)
        flags = ["--training.headless", "True", "--training.num-envs", str(num_envs),
                 "--training.name", label, "--training.project", "PHP-research", "--logger.base-dir", str(run_root / label),
                 "--training.seed", "42"]
        default_iterations = 20000 if label.startswith("teacher-") else 10000 if label == "student-pure" else 30000
        target = args.iterations if args.iterations is not None else (2 if args.profile == "smoke" else default_iterations)
        restored = resume_point(label) if args.resume else None
        restored_iteration = restored[1] if restored is not None else 0
        remaining = max(1, target - restored_iteration)
        if args.iterations is not None or args.profile == "smoke" or args.resume:
            flags += ["--algo.config.num-learning-iterations", str(remaining)]
        if args.profile == "smoke":
            flags += ["--algo.config.save-interval", "1", "--algo.config.num-mini-batches", "4",
                      "--training.preprocess-hook-kwargs", '{"add_onpath_obstacle": true, "num_variants": 1, "obstacle_seed": 42}']
        if restored is not None:
            flags += ["--training.checkpoint", restored[0]]
        return flags

    launch = ROOT / "wbt_training/training_runs"
    if args.action == "download":
        for skill in args.skills:
            execute(f"download-{skill}", [sys.executable, str(ROOT / "scripts/download_assets.py"), f"motions-{skill}", "--destination", str(args.assets.resolve() / f"motions-{skill}")])
    elif args.action == "teachers":
        for skill in args.skills:
            label = f"teacher-{skill}"
            execute(label, ["bash", str(launch / "run_terrain_teacher.sh"), *train_flags(label, 4096)], {"REGISTRY": registry(skill)})
    elif args.action == "teacher-presets":
        for preset in TEACHER_PRESETS:
            for skill in args.skills:
                label = f"teacher-preset-{preset}-{skill}"
                execute(label, ["bash", str(ROOT / "scripts/research/run_preset.sh"), f"exp:{preset}", *train_flags(label, 4096)], {"REGISTRY": registry(skill)})
    elif args.action.startswith("distill-"):
        kind = args.action.removeprefix("distill-")
        label = f"student-{kind}"
        if args.profile == "official" and not args.plan:
            for skill in args.skills:
                if checkpoint_info(f"teacher-{skill}")[1] < 19999:
                    raise ValueError(f"Teacher {skill} has not completed the default 20000-iteration schedule. Use --profile smoke to test untrained experts.")
        teachers = ",".join(checkpoint(f"teacher-{skill}") for skill in args.skills)
        execute(label, ["bash", str(launch / "run_terrain_warp_distill.sh"), *train_flags(label, 2048)],
                {"TEACHER_CHECKPOINT": teachers, "REGISTRY": ",".join(registry(skill) for skill in args.skills), "FINETUNE": "1" if kind == "finetune" else "0"})
    elif args.action == "eval-teachers":
        for skill in args.skills:
            label = f"eval-teacher-{skill}"
            execute(label, ["bash", str(ROOT / "scripts/research/eval_quality.sh"), "teacher", str(run_root / label / "quality.json"), "--training.headless", "True", "--logger.base-dir", str(run_root / label),
                            "--logger.video.interval", "1", "--logger.video.upload-to-wandb", "False"],
                    {"CHECKPOINT": checkpoint(f"teacher-{skill}"), "REGISTRY": registry(skill), "MAX_EVAL_STEPS": str(args.eval_steps), "NUM_ENVS": str(args.num_envs or 1)})
    else:
        label = f"student-{args.student_kind}"
        student_path = str(args.checkpoint.resolve()) if args.checkpoint else checkpoint(label)
        registries = ",".join(registry(skill) for skill in args.skills)
        if args.action == "eval-student":
            execute(f"eval-{label}", ["bash", str(ROOT / "scripts/research/eval_quality.sh"), "student", str(run_root / f"eval-{label}" / "quality.json"), "--training.headless", "True", "--logger.base-dir", str(run_root / f"eval-{label}"),
                                      "--logger.video.interval", "1", "--logger.video.upload-to-wandb", "False"],
                    {"CHECKPOINT": student_path, "REGISTRY": registries, "MAX_EVAL_STEPS": str(args.eval_steps), "NUM_ENVS": str(args.num_envs or 1)})
        else:
            execute(f"export-{label}", [sys.executable, "-m", "wbt_training.training_runs.export_distill_onnx", "--training.checkpoint", student_path,
                                       "--training.registry-name", registries, "--training.num-envs", "1", "logger:disabled", "--logger.base-dir", str(run_root / f"export-{label}")])


if __name__ == "__main__":
    main()
