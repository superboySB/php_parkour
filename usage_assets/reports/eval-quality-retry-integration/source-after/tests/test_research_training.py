"""Protect long training jobs from unsafe resume/skip bookkeeping.

No simulator starts: the fake process writes a real torch checkpoint in the
same schema that Holosoma saves. Run with train-python in the research Docker.
"""
from __future__ import annotations

import importlib.util
import json
import hashlib
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[1]


def test_actual_rich_wrapped_training_log_timing():
    spec = importlib.util.spec_from_file_location("research_timing", ROOT / "scripts/research/train_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_log = (ROOT / "tests/fixtures/holosoma_rich_timing.log").read_text()
    assert module.iteration_timings(real_log) == pytest.approx([1.384, 1.254])


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("research_train_pipeline", ROOT / "scripts/research/train_pipeline.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []

    class FakeProcess:
        def __init__(self, command, **kwargs):
            commands.append(command)
            output = Path(command[command.index("--logger.base-dir") + 1]) / f"native-run-{len(commands)}"
            output.mkdir(parents=True, exist_ok=True)
            restored = 0
            if "--training.checkpoint" in command:
                restored = torch.load(command[command.index("--training.checkpoint") + 1], weights_only=False)["iter"]
            iterations = int(command[command.index("--algo.config.num-learning-iterations") + 1]) if "--algo.config.num-learning-iterations" in command else 20000
            last = restored + iterations - 1
            checkpoint = {"iter": last, "actor_model_state_dict": {"weight": torch.zeros(1)}, "critic_model_state_dict": {"weight": torch.zeros(1)}}
            torch.save(checkpoint, output / f"model_{last:05d}.pt")
            if any("eval_quality.sh" in value for value in command):
                (output / "evaluation.mp4").write_bytes(b"mock video checked by the stub probe")
                launcher_index = next(i for i, value in enumerate(command) if Path(value).name == "eval_quality.sh")
                report_path = Path(command[launcher_index + 2])
                assert report_path.is_absolute() and report_path.name == "quality.json"
                assert report_path.is_relative_to(tmp_path), "The mock must never write into the project root"
                assert not report_path.exists(), "The real quality CLI requires a fresh report target"
                source = Path(kwargs["env"]["CHECKPOINT"])
                event = report_path.parent / "tensorboard" / f"events.out.tfevents.test-{len(commands)}"
                event.parent.mkdir(exist_ok=True)
                event.write_bytes(b"mock event artifact; real TensorBoard parsing is tested separately")
                steps, num_envs = int(kwargs["env"]["MAX_EVAL_STEPS"]), int(kwargs["env"]["NUM_ENVS"])
                report_path.write_text(json.dumps({"schema_version": 1, "status": "completed", "control_steps": steps, "num_envs": num_envs,
                    "checkpoint_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "finite_actions": True, "finite_root_states": True,
                    "videos": [{"path": str(output / "evaluation.mp4"), "sha256": hashlib.sha256((output / "evaluation.mp4").read_bytes()).hexdigest(), "duration_seconds": 1.0}],
                    "tensorboard_events": [str(event)],
                    "metrics": {name: {"finite": True, "samples": steps * num_envs, "mean": .1, "p95": .2, "max": .3} for name in module.QUALITY_METRICS}}))
            if any("export_distill_onnx" in value for value in command) and os.environ.get("RESEARCH_FAKE_EXPORT") == "1":
                for name in ("depth_backbone.onnx", "student.onnx"):
                    (output / name).write_bytes(f"mock {name} model bytes".encode())
            self.stdout = iter(["Computation: 100 steps/s (Collection: 1.000s, Learning 0.500s)\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    def fake_run(command, **kwargs):
        if any("validate_onnx.py" in value for value in command):
            bundle = Path(command[command.index("--models") + 1])
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps({"status": "passed", "cases": [{}] * 30, "models": [module.fingerprint(bundle / name) for name in ("depth_backbone.onnx", "student.onnx")]}))
        return SimpleNamespace(returncode=0, stdout='{"format":{"duration":"1.0"}}', stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("PHP_DOCKER", "1")

    def run(*extra, action="teachers"):
        monkeypatch.setattr(sys, "argv", ["train_pipeline.py", action, "--profile", "official", "--skills", "locomotion", "--output", str(tmp_path), *extra])
        module.main()
        label = ("teacher-locomotion" if action == "teachers" else
                 f"student-{action.removeprefix('distill-')}" if action.startswith("distill-") else
                 "eval-student-finetune" if action == "eval-student" else "export-student-finetune")
        return json.loads((tmp_path / "official/manifests" / f"{label}.json").read_text())

    run.pipeline_module = module
    return run, commands, tmp_path


def test_resume_starts_unstarted_stage_from_iteration_zero(pipeline):
    run, commands, _ = pipeline
    completed = run("--iterations", "20", "--resume")
    assert completed["checkpoint_iteration"] == 19
    assert "--training.checkpoint" not in commands[-1]


def test_resume_continues_past_completed_teacher_to_unstarted_next_teacher(pipeline):
    run, commands, directory = pipeline
    run("--iterations", "20")
    run("--iterations", "20", "--resume", "--skills", "locomotion", "low-step")
    assert len(commands) == 2
    assert "--training.checkpoint" not in commands[-1]
    next_manifest = json.loads((directory / "official/manifests/teacher-low-step.json").read_text())
    assert next_manifest["checkpoint_iteration"] == 19 and next_manifest["status"] == "passed"


def test_resume_restarts_failed_stage_without_any_checkpoint(pipeline):
    run, commands, directory = pipeline
    manifests = directory / "official/manifests"
    manifests.mkdir(parents=True)
    (manifests / "teacher-locomotion.json").write_text(json.dumps({"profile": "official", "label": "teacher-locomotion", "status": "failed"}))
    completed = run("--iterations", "2", "--resume")
    assert completed["checkpoint_iteration"] == 1
    assert "--training.checkpoint" not in commands[-1]


def test_resume_targets_total_iterations_and_accepts_native_ppo_schema(pipeline):
    run, commands, _ = pipeline
    pilot = run("--iterations", "20")
    assert pilot["checkpoint_iteration"] == 19
    assert pilot["overrides"]["iterations_target"] == 20
    assert "explicit overrides" in pilot["scope"]
    finished = run("--resume")
    command = commands[-1]
    assert command[command.index("--algo.config.num-learning-iterations") + 1] == "19981"
    assert finished["checkpoint_iteration"] == 19999
    assert finished["status"] == "passed"
    assert finished["quality_verified"] is False


def test_skip_requires_success_matching_settings_and_unchanged_checkpoint(pipeline):
    run, commands, _ = pipeline
    result = run("--iterations", "20")
    run("--iterations", "20", "--skip-completed")
    assert len(commands) == 1
    Path(result["checkpoint"]).write_bytes(b"interrupted checkpoint bytes")
    with pytest.raises(Exception):
        run("--iterations", "20", "--skip-completed")
    assert len(commands) == 1


def test_resume_does_not_repeat_training_when_target_is_already_met(pipeline):
    run, commands, _ = pipeline
    pilot = run("--iterations", "20")
    finished = run("--iterations", "20", "--resume")
    assert len(commands) == 1
    assert finished["checkpoint_sha256"] == pilot["checkpoint_sha256"]
    assert finished["checkpoint_iteration"] == 19


@pytest.mark.parametrize("target", ["20", "20000"])
def test_resume_rejects_changed_environment_count_even_when_target_is_met(pipeline, target):
    run, commands, _ = pipeline
    run("--iterations", "20", "--num-envs", "64")
    with pytest.raises(ValueError, match="Resume provenance mismatch.*num_envs"):
        run("--iterations", target, "--resume")
    assert len(commands) == 1


def test_resume_accepts_explicit_default_environment_count(pipeline):
    run, commands, _ = pipeline
    run("--iterations", "20")
    result = run("--iterations", "20", "--num-envs", "4096", "--resume")
    assert result["checkpoint_iteration"] == 19 and len(commands) == 1


def test_resume_rejects_changed_registry_before_reusing_completed_weights(pipeline):
    run, commands, directory = pipeline
    run("--iterations", "20")
    with pytest.raises(ValueError, match="Resume provenance mismatch.*registries"):
        run("--iterations", "20", "--assets", str(directory / "different-assets"), "--resume")
    assert len(commands) == 1


def test_resume_rejects_changed_finetune_mode(pipeline):
    run, commands, directory = pipeline
    run("--iterations", "20000")
    result = run("--iterations", "2", action="distill-finetune")
    result["settings"]["finetune"] = "0"
    manifest = directory / "official/manifests/student-finetune.json"
    manifest.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Resume provenance mismatch.*finetune"):
        run("--iterations", "2", "--resume", action="distill-finetune")
    assert len(commands) == 2


def test_resume_rejects_changed_ordered_teacher_weights(pipeline):
    run, commands, directory = pipeline
    teacher = run("--iterations", "20000")
    run("--iterations", "2", action="distill-pure")
    checkpoint = Path(teacher["checkpoint"])
    state = torch.load(checkpoint, weights_only=False)
    state["actor_model_state_dict"]["weight"] += 1
    torch.save(state, checkpoint)
    # Simulate a new successful teacher revision with valid native tensors and
    # updated provenance. The old student must not silently keep its experts.
    teacher["checkpoint_sha256"] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (directory / "official/manifests/teacher-locomotion.json").write_text(json.dumps(teacher))
    with pytest.raises(ValueError, match="Resume provenance mismatch.*teacher_checkpoint_sha256"):
        run("--iterations", "2", "--resume", action="distill-pure")
    assert len(commands) == 2


def test_student_resume_rejects_reordered_teacher_registry_pairs(pipeline):
    run, commands, directory = pipeline
    run("--iterations", "20000", "--skills", "locomotion", "low-step")
    # Give the second valid expert different weights so source order has an
    # observable identity, rather than comparing two identical fake policies.
    manifest_path = directory / "official/manifests/teacher-low-step.json"
    teacher = json.loads(manifest_path.read_text())
    checkpoint = Path(teacher["checkpoint"])
    state = torch.load(checkpoint, weights_only=False)
    state["actor_model_state_dict"]["weight"] += 1
    torch.save(state, checkpoint)
    teacher["checkpoint_sha256"] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(teacher))
    run("--iterations", "2", "--skills", "locomotion", "low-step", action="distill-pure")
    with pytest.raises(ValueError, match="Resume provenance mismatch.*registries.*teacher_checkpoint_sha256"):
        run("--iterations", "2", "--skills", "low-step", "locomotion", "--resume", action="distill-pure")
    assert len(commands) == 3


@pytest.mark.parametrize("kind", ["pure", "finetune"])
def test_student_resume_extends_target_without_treating_own_checkpoint_as_expert(pipeline, monkeypatch, kind):
    run, commands, _ = pipeline
    teacher = run("--iterations", "20000")
    pilot = run("--iterations", "2", action=f"distill-{kind}")
    # CHECKPOINT belongs to eval launchers. Even if a caller leaves its own
    # student PT in the environment, only TEACHER_CHECKPOINT supplies experts.
    monkeypatch.setenv("CHECKPOINT", pilot["checkpoint"])
    result = run("--iterations", "4", "--resume", action=f"distill-{kind}")
    assert len(commands) == 3 and result["checkpoint_iteration"] == 3
    command = commands[-1]
    assert command[command.index("--training.checkpoint") + 1] == pilot["checkpoint"]
    assert command[command.index("--algo.config.num-learning-iterations") + 1] == "3"
    assert result["settings"]["source_checkpoints"] == [{"path": teacher["checkpoint"], "sha256": teacher["checkpoint_sha256"]}]


def test_resume_rejects_checkpoint_with_unverifiable_legacy_training_settings(pipeline):
    run, commands, directory = pipeline
    result = run("--iterations", "20")
    del result["settings"]
    (directory / "official/manifests/teacher-locomotion.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="insufficient to verify safe resume provenance"):
        run("--iterations", "20", "--resume")
    assert len(commands) == 1


@pytest.mark.parametrize("old_status", ["failed", "running"])
def test_resume_retries_unfinished_stage_even_with_target_checkpoint(pipeline, old_status):
    run, commands, directory = pipeline
    result = run("--iterations", "20")
    manifest = directory / "official/manifests/teacher-locomotion.json"
    result["status"] = old_status
    manifest.write_text(json.dumps(result))
    completed = run("--iterations", "20", "--resume")
    assert len(commands) == 2
    assert completed["status"] == "passed"
    assert completed["checkpoint_iteration"] == 19


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("schema", ["ppo", "student"])
def test_nonfinite_native_policy_tensors_are_rejected(pipeline, bad_value, schema):
    run, commands, _ = pipeline
    result = run("--iterations", "2")
    path = Path(result["checkpoint"])
    data = torch.load(path, weights_only=False)
    if schema == "ppo":
        data["critic_model_state_dict"]["weight"][0] = bad_value
    else:
        data["model_state_dict"] = {"nested": {"weights": [torch.tensor([bad_value])]}}
    torch.save(data, path)
    with pytest.raises(ValueError, match="Non-finite policy tensor"):
        run("--iterations", "2", "--skip-completed")
    assert len(commands) == 1


def test_nonempty_policy_dictionary_without_tensors_is_rejected(pipeline):
    run, _, _ = pipeline
    result = run("--iterations", "2")
    path = Path(result["checkpoint"])
    data = torch.load(path, weights_only=False)
    data["actor_model_state_dict"] = {"metadata": "no parameters were saved"}
    torch.save(data, path)
    with pytest.raises(ValueError, match="No policy tensors"):
        run("--iterations", "2", "--skip-completed")


def test_evaluation_skip_is_bound_to_source_weights_and_duration(pipeline):
    run, commands, directory = pipeline
    teacher = run("--iterations", "2")
    source = directory / "student.pt"
    source.write_bytes(Path(teacher["checkpoint"]).read_bytes())
    first = run("--checkpoint", str(source), "--eval-steps", "100", action="eval-student")
    run("--checkpoint", str(source), "--eval-steps", "100", "--skip-completed", action="eval-student")
    assert len(commands) == 2
    longer = run("--checkpoint", str(source), "--eval-steps", "250", "--skip-completed", action="eval-student")
    assert len(commands) == 3
    checkpoint = torch.load(source, weights_only=False)
    checkpoint["actor_model_state_dict"]["weight"] += 1
    torch.save(checkpoint, source)
    changed = run("--checkpoint", str(source), "--eval-steps", "250", "--skip-completed", action="eval-student")
    assert len(commands) == 4
    assert first["settings"]["eval_steps"] == 100
    assert longer["settings"]["eval_steps"] == 250
    assert changed["settings"]["source_checkpoints"] != longer["settings"]["source_checkpoints"]


def test_successful_export_without_new_bundle_is_failed(pipeline):
    run, _, directory = pipeline
    teacher = run("--iterations", "2")
    with pytest.raises(SystemExit) as stopped:
        run("--checkpoint", teacher["checkpoint"], action="export")
    assert stopped.value.code == 1
    manifest = json.loads((directory / "official/manifests/export-student-finetune.json").read_text())
    assert manifest["status"] == "failed"
    assert "bundle" in manifest["error"]


@pytest.mark.parametrize("kind", ["video", "quality", "tensorboard"])
@pytest.mark.parametrize("operation", ["delete", "tamper"])
def test_eval_skip_rechecks_output_artifacts(pipeline, kind, operation):
    run, commands, _ = pipeline
    teacher = run("--iterations", "2")
    result = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert len(commands) == 2
    path = Path(result["evaluation_quality_report"] if kind == "quality" else result["evaluation_videos"][0]["path"] if kind == "video" else result["evaluation_tensorboard_events"][0])
    path.unlink() if operation == "delete" else path.write_bytes(b"changed output bytes")
    rerun = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert len(commands) == 3 and rerun["status"] == "passed"


def test_legacy_eval_manifest_without_artifact_hashes_is_rerun(pipeline):
    run, commands, directory = pipeline
    teacher = run("--iterations", "2")
    result = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    del result["artifact_fingerprints"]
    (directory / "official/manifests/eval-student-finetune.json").write_text(json.dumps(result))
    run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert len(commands) == 3


@pytest.mark.parametrize("name", ["depth_backbone.onnx", "student.onnx", "onnx-validation-0.json"])
@pytest.mark.parametrize("operation", ["delete", "tamper"])
def test_export_skip_rechecks_models_and_inference_report(pipeline, monkeypatch, name, operation):
    monkeypatch.setenv("RESEARCH_FAKE_EXPORT", "1")
    run, commands, _ = pipeline
    teacher = run("--iterations", "2")
    result = run("--checkpoint", teacher["checkpoint"], action="export")
    run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="export")
    assert len(commands) == 2
    artifact = next(item for item in result["artifact_fingerprints"] if Path(item["path"]).name == name)
    path = Path(artifact["path"])
    path.unlink() if operation == "delete" else path.write_bytes(b"changed model/report bytes")
    rerun = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="export")
    assert len(commands) == 3 and rerun["status"] == "passed"


def test_quality_report_rejects_structure_changes_even_if_hash_is_refreshed(pipeline):
    run, commands, directory = pipeline
    teacher = run("--iterations", "2")
    result = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    path = Path(result["evaluation_quality_report"])
    quality = json.loads(path.read_text())
    quality["metrics"]["motion/error_ref_pos"]["samples"] -= 1
    path.write_text(json.dumps(quality))
    result["evaluation_quality_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    artifact = next(item for item in result["artifact_fingerprints"] if item["path"] == str(path))
    artifact.update(sha256=result["evaluation_quality_sha256"], bytes=path.stat().st_size)
    (directory / "official/manifests/eval-student-finetune.json").write_text(json.dumps(result))
    run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert len(commands) == 3


def test_valid_evaluation_skip_does_not_archive_or_mutate(pipeline):
    run, commands, _ = pipeline
    teacher = run("--iterations", "2")
    first = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    quality = Path(first["evaluation_quality_report"])
    original = quality.read_bytes()
    event = Path(first["evaluation_tensorboard_events"][0])
    event_bytes = event.read_bytes()
    skipped = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert len(commands) == 2 and skipped == first
    assert quality.read_bytes() == original and event.read_bytes() == event_bytes
    assert not (quality.parent / "quality-history").exists()


def test_actual_eval_retry_archives_quality_and_tensorboard_bytes(pipeline):
    run, _, directory = pipeline
    teacher = run("--iterations", "2")
    first = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    old_manifest = (directory / "official/manifests/eval-student-finetune.json").read_bytes()
    quality = Path(first["evaluation_quality_report"])
    event = Path(first["evaluation_tensorboard_events"][0])
    originals = {str(path): path.read_bytes() for path in (quality, event)}
    Path(first["evaluation_videos"][0]["path"]).write_bytes(b"deleted or changed video evidence")
    retry = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert retry["status"] == "passed" and retry["evaluation_quality_report"] == first["evaluation_quality_report"]
    retained = retry["previous_evaluation_evidence"]
    receipt = Path(retained["receipt"]["path"])
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == retained["receipt"]["sha256"]
    for mapping in retained["files"]:
        assert Path(mapping["retained"]["path"]).read_bytes() == originals[mapping["original"]["path"]]
        assert mapping["original"]["sha256"] == mapping["retained"]["sha256"]
    assert set(originals) == {mapping["original"]["path"] for mapping in retained["files"]}
    assert not event.exists() and first["evaluation_tensorboard_events"][0] not in retry["evaluation_tensorboard_events"]
    assert any(path.read_bytes() == old_manifest for path in (directory / "official/manifests/history").glob("*.json"))


def test_malformed_old_quality_is_retained_without_parsing(pipeline):
    run, _, _ = pipeline
    teacher = run("--iterations", "2")
    first = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    quality = Path(first["evaluation_quality_report"])
    quality.write_bytes(b"malformed previous report; preserve these exact bytes")
    retry = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    previous = next(item for item in retry["previous_evaluation_evidence"]["files"] if item["original"]["path"] == str(quality))
    assert Path(previous["retained"]["path"]).read_bytes() == b"malformed previous report; preserve these exact bytes"
    assert retry["status"] == "passed"


def test_failed_attempt_with_report_can_retry_without_overwriting_history(pipeline):
    run, _, directory = pipeline
    teacher = run("--iterations", "2")
    first = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    first["status"] = "failed"
    manifest = directory / "official/manifests/eval-student-finetune.json"
    manifest.write_text(json.dumps(first))
    retry = run("--checkpoint", teacher["checkpoint"], "--skip-completed", action="eval-student")
    assert retry["status"] == "passed" and retry["previous_evaluation_evidence"]["files"]


def test_failed_retry_keeps_prior_history_and_new_failed_manifest(pipeline, monkeypatch):
    run, _, directory = pipeline
    teacher = run("--iterations", "2")
    first = run("--checkpoint", teacher["checkpoint"], action="eval-student")
    original = Path(first["evaluation_quality_report"]).read_bytes()
    successful_process = run.pipeline_module.subprocess.Popen

    class FailedProcess(successful_process):
        def wait(self):
            return 7

    monkeypatch.setattr(run.pipeline_module.subprocess, "Popen", FailedProcess)
    with pytest.raises(SystemExit) as failure:
        run("--checkpoint", teacher["checkpoint"], action="eval-student")
    assert failure.value.code == 7
    result = json.loads((directory / "official/manifests/eval-student-finetune.json").read_text())
    assert result["status"] == "failed" and result["returncode"] == 7
    old_quality = next(item for item in result["previous_evaluation_evidence"]["files"] if Path(item["original"]["path"]).name == "quality.json")
    assert Path(old_quality["retained"]["path"]).read_bytes() == original
    assert Path(result["evaluation_quality_report"]).is_file()


@pytest.fixture
def archive_module():
    spec = importlib.util.spec_from_file_location("evaluation_archive", ROOT / "scripts/research/train_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fault", ["quality_symlink", "quality_directory", "quality_fifo", "tb_symlink", "tb_file", "tb_nested_symlink", "tb_fifo", "history_symlink", "history_file"])
def test_archive_refuses_unsafe_evidence_before_moving_bytes(archive_module, tmp_path, fault):
    stage = tmp_path / "eval"
    stage.mkdir()
    quality, tensorboard = stage / "quality.json", stage / "tensorboard"
    quality.write_bytes(b"previous raw report")
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"must remain untouched")
    if fault == "quality_symlink":
        quality.unlink(); quality.symlink_to(foreign)
    elif fault == "quality_directory":
        quality.unlink(); quality.mkdir()
    elif fault == "quality_fifo":
        quality.unlink(); os.mkfifo(quality)
    elif fault == "tb_symlink":
        tensorboard.symlink_to(tmp_path)
    elif fault == "tb_file":
        tensorboard.write_bytes(b"not a directory")
    elif fault in ("tb_nested_symlink", "tb_fifo"):
        tensorboard.mkdir()
        if fault == "tb_nested_symlink":
            (tensorboard / "event").symlink_to(foreign)
        else:
            os.mkfifo(tensorboard / "event")
    elif fault == "history_symlink":
        (stage / "quality-history").symlink_to(tmp_path)
    else:
        (stage / "quality-history").write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="unsafe type"):
        archive_module.archive_evaluation_evidence(stage)
    assert foreign.read_bytes() == b"must remain untouched"
    if fault not in ("quality_symlink", "quality_directory", "quality_fifo"):
        assert quality.read_bytes() == b"previous raw report"


def test_archive_retains_partial_bytes_if_second_move_fails(archive_module, tmp_path, monkeypatch):
    stage = tmp_path / "eval"
    stage.mkdir()
    quality = stage / "quality.json"
    quality.write_bytes(b"original quality bytes")
    tensorboard = stage / "tensorboard"
    tensorboard.mkdir()
    (tensorboard / "event").write_bytes(b"original tensorboard bytes")
    original_rename = Path.rename

    def fail_second_move(source, destination):
        if source == tensorboard:
            raise OSError("simulated second move failure")
        return original_rename(source, destination)

    monkeypatch.setattr(Path, "rename", fail_second_move)
    with pytest.raises(OSError, match="second move failure"):
        archive_module.archive_evaluation_evidence(stage)
    retained = next((stage / "quality-history").iterdir())
    receipt = json.loads((retained / "archive.json").read_text())
    assert receipt["status"] == "failed"
    assert (retained / "quality.json").read_bytes() == b"original quality bytes"
    assert (tensorboard / "event").read_bytes() == b"original tensorboard bytes"
    assert not quality.exists()


def test_successful_exit_without_target_checkpoint_is_not_success(pipeline, monkeypatch):
    run, _, directory = pipeline
    result = run("--iterations", "2")
    checkpoint = Path(result["checkpoint"])
    data = torch.load(checkpoint, weights_only=False)
    data["iter"] = 0
    torch.save(data, checkpoint)

    class NoSaveProcess:
        stdout = iter([])
        def __init__(self, *args, **kwargs):
            pass
        def wait(self):
            return 0

    # Replace the module's shared subprocess factory used by the fixture.
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", NoSaveProcess)
    with pytest.raises(SystemExit) as stopped:
        run("--iterations", "20")
    assert stopped.value.code == 1
    manifest = json.loads((directory / "official/manifests/teacher-locomotion.json").read_text())
    assert manifest["status"] == "failed"
    assert "target iteration" in manifest["error"]
