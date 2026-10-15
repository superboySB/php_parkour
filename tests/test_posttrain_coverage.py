"""Control-plane tests use synthetic files, never a simulator or GPU.

Native saved-config/preprocessing and first-attempt interfaces have their own
real CPU regressions in test_source_coverage.py. These tests check scheduling,
provenance, locking and evidence retention, without pretending JSON is physics.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.research import posttrain_coverage as pc


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pc.write(path, value)


@pytest.fixture
def canonical(tmp_path, monkeypatch):
    official = tmp_path / "outputs/official-full"
    stages, teachers = {}, []
    registries = [f"file:///data/assets/motions-{s}" for s in pc.SKILLS]

    def artifact(relative, value=b"synthetic-control-plane-artifact"):
        path = official / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return {"path": f"{pc.OFFICIAL}/{relative}", "sha256": pc.digest(path), "bytes": len(value)}

    def json_artifact(relative, value):
        return artifact(relative, (json.dumps(value) + "\n").encode())

    for label in pc.LABELS:
        training = label in pc.TRAINING
        teacher_label = label.removeprefix("eval-")
        registry = registries[pc.SKILLS.index(teacher_label.removeprefix("teacher-"))] if teacher_label.startswith("teacher-") else ",".join(registries)
        sources = []
        if label.startswith("student-"):
            sources = copy.deepcopy(teachers)
        elif not training:
            source_label = label.removeprefix("eval-").removeprefix("export-")
            sources = [{"path": stages[source_label]["checkpoint"], "sha256": stages[source_label]["checkpoint_sha256"]}]
        stage = {"label": label, "profile": "official", "status": "passed", "returncode": 0, "finished_utc": "2026-10-10T10:00:00+00:00",
                 "command": [], "settings": {"profile": "official", "skills": list(pc.SKILLS), "assets": "/data/assets", "num_envs": None,
                    "iterations_target": None, "registries": registry, "source_checkpoints": sources, "finetune": None},
                 "environment": {"LOGGER": "tensorboard", "NGPUS": "1", "REGISTRY": registry}}
        if training:
            target, envs, _ = pc.TRAINING[label]
            stage["command"] = ["--training.num-envs", str(envs), "--training.seed", "42"]
            stage["settings"]["iterations_target"] = target
            record = artifact(f"official/{label}/run/model_{target - 1:05d}.pt")
            stage.update(checkpoint=record["path"], checkpoint_sha256=record["sha256"], checkpoint_iteration=target - 1)
            if label.startswith("teacher-"):
                teachers.append({key: record[key] for key in ("path", "sha256")})
            else:
                stage["settings"]["finetune"] = stage["environment"]["FINETUNE"] = "0" if label.endswith("pure") else "1"
                stage["environment"]["TEACHER_CHECKPOINT"] = ",".join(item["path"] for item in teachers)
        elif label.startswith("eval-"):
            stage["settings"].update(num_envs=64, eval_steps=3000, eval_quality_schema=1)
            stage["environment"]["CHECKPOINT"] = sources[0]["path"]
            video = artifact(f"official/{label}/episode.mp4")
            event = artifact(f"official/{label}/events.out.tfevents.synthetic")
            quality = {"schema_version": 1, "status": "completed", "num_envs": 64, "control_steps": 3000,
                       "checkpoint_sha256": sources[0]["sha256"], "finite_actions": True, "finite_root_states": True,
                       "metrics": {f"motion/error_{key}": {"samples": 192000, "finite": True, "mean": 0., "p95": 0., "max": 0.} for key in ("ref_pos", "ref_rot", "body_pos", "joint_pos")},
                       "videos": [{**video, "duration_seconds": .02}], "tensorboard_events": [event["path"]]}
            report = json_artifact(f"official/{label}/quality.json", quality)
            stage.update(evaluation_quality_report=report["path"], evaluation_quality_sha256=report["sha256"], artifact_fingerprints=[report, video, event])
        else:
            bundle = f"{pc.OFFICIAL}/official/{label}/model"
            models = [artifact(f"official/{label}/model/{name}") for name in ("student.onnx", "depth_backbone.onnx")]
            report = json_artifact(f"official/{label}/onnx.json", {"status": "passed", "cases": [{}] * 30, "models": models})
            stage["command"] = ["--training.checkpoint", sources[0]["path"], "--training.registry-name", ",".join(registries)]
            stage.update(onnx_validation_reports=[{"bundle": bundle, "report": report["path"]}], artifact_fingerprints=[*models, report])
        stages[label] = stage
        save(official / "official/manifests" / f"{label}.json", stage)
    entries = []
    for index, skill in enumerate(pc.SKILLS):
        teacher = teachers[index]
        graph_path = str(Path(teacher["path"]).with_suffix(".onnx"))
        graph = artifact(str(Path(graph_path).relative_to(pc.OFFICIAL)))
        report = json_artifact(f"official/teacher-onnx-validation/{skill}.json", {"status": "passed", "sha256": graph["sha256"], "cases": [{}],
                              "metadata": {"iteration": "19999", "experiment_config": json.dumps({"training": {"registry_name": registries[index]}})}})
        entries.append({"skill": skill, "checkpoint": teacher["path"], "checkpoint_sha256": teacher["sha256"], "onnx": graph["path"], "onnx_sha256": graph["sha256"], "cpu_cases": 1, "report": report["path"]})
    save(official / "official/teacher-onnx-validation/summary.json", {"status": "passed", "profile": "official", "teachers": entries})
    (official / "official-acceptance.lock").touch()
    frozen_files = [{"path": "native.py", "sha256": hashlib.sha256(b"synthetic native source\n").hexdigest(), "symlink": False, "mode": 0o644}]
    tree = hashlib.sha256(json.dumps(frozen_files, sort_keys=True).encode()).hexdigest()
    monkeypatch.setattr(pc, "TRAIN_TREE", tree)
    source = tmp_path / "source" / tree
    source.mkdir(parents=True)
    (source / "native.py").write_bytes(b"synthetic native source\n")
    (source / "native.py").chmod(0o644)
    save(source / "source-manifest.json", {"source_tree_sha256": tree, "files": frozen_files})
    log = tmp_path / "outputs/official-full-driver.log"
    log.write_text(pc.MARKER + "\n")
    args = SimpleNamespace(root=tmp_path, official_output=official, driver_log=log, coverage_output=tmp_path / "outputs/coverage",
                           source_tree="b" * 64, image="sha256:accepted", gpu_uuid="GPU-fixed", training_container="training", resume_interrupted=False)
    # These scheduling fixtures do not represent scientific asset preparation.
    # Exact filesystem/closure validation has real-file tests of its own.
    monkeypatch.setattr(pc, "robot_contract", lambda *_a, **_k: {"files": [{}] * 35})
    return args, stages


def training_inspect(args, running=True):
    return [{"Image": args.image, "State": {"Running": running}, "Mounts": [
        {"Destination": "/workspace/php_parkour", "Source": str(args.root / "source" / pc.TRAIN_TREE)},
        {"Destination": "/outputs", "Source": str(args.root / "outputs")}]}]


def test_complete_synthetic_control_plane_selects_seven_final_pts(canonical):
    args, stages = canonical
    result = pc.inspect_artifacts(args.official_output, stages)
    assert len(result["checkpoints"]) == 7
    assert [result["checkpoints"][f"teacher-{s}"]["iteration"] for s in pc.SKILLS] == [19999] * 5
    assert result["checkpoints"]["student-pure"]["iteration"] == 9999
    assert result["checkpoints"]["student-finetune"]["iteration"] == 29999


def test_unfinished_dry_observation_has_no_subprocess_or_mutation(canonical, monkeypatch):
    args, stages = canonical
    stages["teacher-locomotion"]["status"] = "running"
    save(args.official_output / "official/manifests/teacher-locomotion.json", stages["teacher-locomotion"])
    before = {str(path): pc.digest(path) for path in args.root.rglob("*") if path.is_file()}
    monkeypatch.setattr(pc, "capture", lambda *_: pytest.fail("Docker/GPU inspection before manifests complete"))
    observation = pc.observe(args)
    after = {str(path): pc.digest(path) for path in args.root.rglob("*") if path.is_file()}
    assert observation["status"] == "waiting" and before == after
    assert not args.coverage_output.exists()


@pytest.mark.parametrize("change", ["profile", "iteration", "envs", "seed", "registry", "experts", "finetune", "stage_source"])
def test_changed_canonical_inputs_rejected(canonical, change):
    args, stages = canonical
    teacher = stages["teacher-locomotion"]
    student = stages["student-pure"]
    if change == "profile": teacher["profile"] = "smoke"
    elif change == "iteration": teacher["checkpoint_iteration"] = 19
    elif change == "envs": teacher["command"][1] = "64"
    elif change == "seed": teacher["command"][3] = "43"
    elif change == "registry": teacher["settings"]["registries"] = "file:///data/assets/motions-low-step"
    elif change == "experts": student["settings"]["source_checkpoints"].reverse()
    elif change == "finetune": student["settings"]["finetune"] = "1"
    else: stages["eval-teacher-locomotion"]["settings"]["source_checkpoints"] = student["settings"]["source_checkpoints"]
    with pytest.raises(ValueError): pc.inspect_artifacts(args.official_output, stages)


@pytest.mark.parametrize("artifact_name", ["episode.mp4", "events.out.tfevents.synthetic", "quality.json"])
def test_removed_rollout_artifact_rejected(canonical, artifact_name):
    args, stages = canonical
    (args.official_output / "official/eval-teacher-locomotion" / artifact_name).unlink()
    with pytest.raises(ValueError): pc.inspect_artifacts(args.official_output, stages)


def test_teacher_onnx_tampering_rejected(canonical):
    args, stages = canonical
    path = pc.host_path(args.official_output, stages["teacher-locomotion"]["checkpoint"]).with_suffix(".onnx")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError): pc.inspect_artifacts(args.official_output, stages)


def test_artifact_cannot_escape_official_mount(canonical):
    args, _ = canonical
    with pytest.raises(ValueError): pc.host_path(args.official_output, "/outputs/official-full/../other/file.pt")


@pytest.mark.parametrize("token", ["run_official_acceptance.sh", "wbt_training.train_agent", "export_distill_onnx"])
def test_live_official_children_block_completion(canonical, monkeypatch, token):
    args, _ = canonical
    monkeypatch.setattr(pc, "capture", lambda argv: json.dumps(training_inspect(args)) if argv[1] == "inspect" else f"PID COMMAND\n100 python {token}")
    assert pc.process_gate(args)["status"] == "waiting"


def test_detach_success_and_old_marker_do_not_prove_completion(canonical, monkeypatch):
    args, _ = canonical
    args.driver_log.write_text(pc.MARKER + "\nnew failed restart\n")
    monkeypatch.setattr(pc, "capture", lambda argv: json.dumps(training_inspect(args, False)))
    assert pc.process_gate(args)["status"] == "waiting"


def test_native_driver_lock_blocks_posttrain(canonical, monkeypatch):
    args, _ = canonical
    monkeypatch.setattr(pc, "capture", lambda argv: json.dumps(training_inspect(args, False)))
    with pc.official_lock(args.official_output):
        assert pc.process_gate(args)["status"] == "waiting"
    assert pc.process_gate(args)["status"] == "driver_quiescent"


def test_original_training_bind_must_remain_unchanged(canonical, monkeypatch):
    args, _ = canonical
    info = training_inspect(args, False)
    info[0]["Mounts"][0]["Source"] = "/new/source"
    monkeypatch.setattr(pc, "capture", lambda argv: json.dumps(info))
    with pytest.raises(ValueError): pc.process_gate(args)


def test_cpu_and_gpu_commands_isolate_sources_outputs_and_uuid(canonical):
    args, _ = canonical
    source = args.root / "source" / args.source_tree
    _, cpu = pc.docker_command(args, source, "cpu", "f" * 64)
    _, gpu = pc.docker_command(args, source, "gpu", "f" * 64)
    assert "--gpus" not in cpu and "NVIDIA_VISIBLE_DEVICES=void" in cpu and "CUDA_VISIBLE_DEVICES=" in cpu
    assert gpu[gpu.index("--gpus") + 1] == "device=GPU-fixed"
    for command in (cpu, gpu):
        assert command[command.index("--network") + 1] == "none"
        assert f"{source}:/workspace/php_parkour:ro" in command
        assert f"{args.official_output}:{pc.OFFICIAL}:ro" in command
        assert args.training_container not in command and "sleep" not in command


def test_occupied_fixed_uuid_never_selects_other_idle_gpu(monkeypatch):
    xml = '<nvidia_smi_log><gpu><uuid>GPU-other</uuid><fb_memory_usage><used>0 MiB</used></fb_memory_usage><utilization><gpu_util>0 %</gpu_util></utilization><processes/></gpu><gpu><uuid>GPU-fixed</uuid><fb_memory_usage><used>100 MiB</used></fb_memory_usage><utilization><gpu_util>0 %</gpu_util></utilization><processes><process_info><pid>123</pid></process_info></processes></gpu></nvidia_smi_log>'
    monkeypatch.setattr(pc, "capture", lambda *_: xml)
    gpu, _, _ = pc.idle_gpu("GPU-fixed")
    assert gpu["uuid"] == "GPU-fixed" and not gpu["idle"]


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    path = tmp_path / "case.json"
    case = {"case_id": "pure-e1-000-source", "output": str(tmp_path), "source": {"source_clip_id": "motions-low-step/source_motion.npz"},
            "runtime_robot_assets": {"fixture": "scheduling only"}}
    save(path, case)
    monkeypatch.setattr(pc, "verify_selection_robot_assets", lambda *_a, **_k: None)
    return {"input_identity": "f" * 64, "runtime_robot_assets": case["runtime_robot_assets"]}, {"case": {"path": str(path), "sha256": pc.digest(path)}}, case


def test_interrupted_attempt_is_retained_without_rerunning(attempt, monkeypatch):
    selection, item, case = attempt
    directory = Path(case["output"])
    save(directory / "posttrain-started.json", {"started": "earlier"})
    (directory / "trajectory.jsonl").write_text('{"partial":true}\n')
    monkeypatch.setattr(pc.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Interrupted first attempt was repeated"))
    result = pc.attempt_case(selection, "pure", item, lambda *_: None)
    assert result["status"] == "execution_failed" and "Interrupted" in result["error"]
    assert (directory / "trajectory.jsonl").read_text() == '{"partial":true}\n'


def test_skill_failure_is_execution_passed_and_never_repeated(attempt, monkeypatch):
    selection, item, case = attempt
    directory = Path(case["output"])
    calls = []
    def worker(*args, **kwargs):
        calls.append(args)
        save(directory / "quality.json", {"stop_reason": "failed", "control_steps": 21, "first_attempt_reference_boundary_reached": False})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(pc.subprocess, "run", worker)
    result = pc.attempt_case(selection, "pure", item, lambda *_: None)
    assert result["status"] == "execution_passed" and result["stop_reason"] == "failed" and not result["reference_boundary_reached"]
    assert pc.attempt_case(selection, "pure", item, lambda *_: None) == result and len(calls) == 1
    (directory / "quality.json").write_text("tampered")
    with pytest.raises(ValueError): pc.attempt_case(selection, "pure", item, lambda *_: None)


def test_worker_launch_failure_records_terminal_execution_failure(attempt, monkeypatch):
    selection, item, case = attempt
    def fail(*args, **kwargs): raise OSError("cannot start child")
    monkeypatch.setattr(pc.subprocess, "run", fail)
    result = pc.attempt_case(selection, "pure", item, lambda *_: None)
    assert result["status"] == "execution_failed" and result["returncode"] is None
    assert pc.read(Path(case["output"]) / "posttrain-attempt.json") == result


def test_stale_attempt_identity_rejected(attempt):
    selection, item, case = attempt
    save(Path(case["output"]) / "posttrain-attempt.json", {"input_identity": "another", "case_sha256": item["case"]["sha256"]})
    with pytest.raises(ValueError): pc.attempt_case(selection, "pure", item, lambda *_: None)


def test_attempt_changed_robot_contract_rejected_before_worker(attempt, monkeypatch):
    selection, item, case = attempt
    case["runtime_robot_assets"] = {"changed": "another cohort"}
    save(Path(item["case"]["path"]), case)
    monkeypatch.setattr(pc.subprocess, "run", lambda *_a, **_k: pytest.fail("Changed asset contract started a worker"))
    with pytest.raises(ValueError, match="shared robot assets"):
        pc.attempt_case(selection, "pure", item, lambda *_: None)


def test_cpu_prepare_passes_one_sealed_contract_to_all_three_plans(tmp_path, monkeypatch):
    asset = {"fixture": "preparation forwarding only"}
    selection = {"input_identity": "f" * 64, "runtime_robot_assets": asset,
                 "checkpoints": {key: {"path": key + ".pt"} for key in pc.TRAINING}}
    path = tmp_path / "selection.json"
    save(path, selection)
    monkeypatch.setattr(pc, "scientific_check", lambda _: {"status": "cpu_scientific_checks_passed"})
    def prepare(value):
        assert value == asset
        (tmp_path / "runtime-robot-assets").mkdir()
    monkeypatch.setattr(pc, "prepare_robot_assets", prepare)
    monkeypatch.setattr(pc, "verify_prepared_plans", lambda _: [{"fixture": "three CPU plans"}])
    calls = []
    monkeypatch.setattr(pc.subprocess, "run", lambda argv, **_: calls.append(argv))
    pc.cpu_prepare(path)
    plans = [argv for argv in calls if "plan" in argv]
    assert len(plans) == 3
    contract_path = str(tmp_path / "runtime-robot-assets/contract.json")
    assert all(argv[argv.index("--runtime-robot-assets-contract") + 1] == contract_path for argv in plans)
    assert pc.read(contract_path) == asset
    assert pc.read(tmp_path / "cpu-ready.json")["runtime_robot_assets"] == asset


def test_existing_monitor_lock_cannot_be_acquired_twice(tmp_path):
    import fcntl
    path = tmp_path / "monitor.lock"
    with path.open("a") as first, path.open("a") as second:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)


def own_container(args, source, role, key):
    command = pc.docker_command(args, source, role, key)[1]
    return {"Image": args.image, "State": {"Running": False, "ExitCode": 0},
            "Config": {"Labels": {"php.posttrain.identity": key, "php.posttrain.role": role},
                       "WorkingDir": "/workspace/php_parkour", "Entrypoint": ["/opt/php/bin/entrypoint"],
                       "Env": ["LOGGER=tensorboard", "WANDB_MODE=disabled", f"CUDA_VISIBLE_DEVICES={'0' if role == 'gpu' else ''}", "NVIDIA_VISIBLE_DEVICES=void"],
                       "Cmd": command[command.index(args.image) + 1:]},
            "HostConfig": {"NetworkMode": "none", "DeviceRequests": [{"DeviceIDs": [args.gpu_uuid]}] if role == "gpu" else []},
            "Mounts": [{"Destination": dest, "Source": str(src), "RW": rw} for dest, src, rw in
                       [("/workspace/php_parkour", source, False), (pc.OFFICIAL, args.official_output, False),
                        ("/data/assets", args.root / "assets", False), (pc.COVERAGE, args.coverage_output, True)]]}


@pytest.mark.parametrize("change", [None, "image", "gpu", "writeable_official", "source", "command", "network", "online", "extra_mount", "cwd", "entrypoint"])
def test_existing_container_identity_and_gpu_mount_guards(canonical, monkeypatch, change):
    args, _ = canonical
    source, key = args.root / "source" / args.source_tree, "f" * 64
    info = own_container(args, source, "gpu", key)
    if change == "image": info["Image"] = "wrong-image"
    elif change == "gpu": info["HostConfig"]["DeviceRequests"][0]["DeviceIDs"] = ["GPU-other"]
    elif change == "writeable_official": info["Mounts"][1]["RW"] = True
    elif change == "source": info["Mounts"][0]["Source"] = "/different/source"
    elif change == "command": info["Config"]["Cmd"] = ["bash", "run_training.sh"]
    elif change == "network": info["HostConfig"]["NetworkMode"] = "host"
    elif change == "online": info["Config"]["Env"][1] = "WANDB_MODE=online"
    elif change == "extra_mount": info["Mounts"].append({"Destination": pc.OFFICIAL + "/official", "Source": "/wrong", "RW": True})
    elif change == "cwd": info["Config"]["WorkingDir"] = "/another/repo"
    elif change == "entrypoint": info["Config"]["Entrypoint"] = ["bash", "another-script.sh"]
    monkeypatch.setattr(pc.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=json.dumps([info])))
    if change:
        with pytest.raises(ValueError): pc.container_state(args, source, "gpu", "own-container", key)
    else:
        assert pc.container_state(args, source, "gpu", "own-container", key) == info


def test_existing_cpu_container_must_have_no_device_requests(canonical, monkeypatch):
    args, _ = canonical
    source, key = args.root / "source" / args.source_tree, "f" * 64
    info = own_container(args, source, "cpu", key)
    info["HostConfig"]["DeviceRequests"] = [{"DeviceIDs": [args.gpu_uuid]}]
    monkeypatch.setattr(pc.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=json.dumps([info])))
    with pytest.raises(ValueError): pc.container_state(args, source, "cpu", "own-container", key)


@pytest.mark.parametrize("stderr", [
    "Error: no such object: own-container\n",
    "Error: No such object: own-container\n",
    "Error: No such container: own-container\n",
    "Error response from daemon: No such container: own-container\n",
])
@pytest.mark.parametrize("stdout", ["", "[]\n"])
def test_exact_missing_container_is_absent_across_docker_versions(canonical, monkeypatch, stderr, stdout):
    args, _ = canonical
    calls = []
    def inspect(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=1, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(pc.subprocess, "run", inspect)
    assert pc.container_state(args, args.root / "source" / args.source_tree, "cpu", "own-container", "f" * 64) is None
    assert calls == [(["docker", "container", "inspect", "own-container"], {"text": True, "capture_output": True})]


@pytest.mark.parametrize("returncode,stdout,stderr", [
    (1, "", "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n"),
    (1, "", "permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock\n"),
    (1, "[]\n", "Error: no such object: another-container\n"),
    (1, "[]\n", "Error response from daemon: No such container: own-container\nCannot connect to the Docker daemon\n"),
    (1, '[{"Id":"unexpected"}]', "Error: no such object: own-container\n"),
    (125, "[]\n", "Error: no such object: own-container\n"),
])
def test_failed_container_inspection_cannot_authorize_a_launch(canonical, monkeypatch, returncode, stdout, stderr):
    args, _ = canonical
    monkeypatch.setattr(pc.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr))
    with pytest.raises(ValueError, match="Cannot inspect own container"):
        pc.container_state(args, args.root / "source" / args.source_tree, "cpu", "own-container", "f" * 64)


def test_actual_missing_name_diagnostic_launches_only_cpu_phase(canonical, monkeypatch):
    args, _ = canonical
    args.coverage_output.mkdir()
    key = "f" * 64
    source = args.root / "source" / args.source_tree
    observation = {"selection": {"input_identity": key}, "source": str(source)}
    name, expected = pc.docker_command(args, source, "cpu", key)
    def inspect(argv, **_):
        assert argv == ["docker", "container", "inspect", name]
        return SimpleNamespace(returncode=1, stdout="[]\n", stderr=f"Error: no such object: {name}\n")
    monkeypatch.setattr(pc.subprocess, "run", inspect)
    monkeypatch.setattr(pc, "idle_gpu", lambda *_: pytest.fail("Fresh CPU preparation reached GPU selection"))
    launched = []
    monkeypatch.setattr(pc, "capture", lambda argv: launched.append(argv) or "synthetic-cpu-container-id")
    result = pc.advance(args, observation)
    assert launched == [expected]
    assert result["container"] == name and result["blockers"] == ["Started isolated cpu coverage container"]
    assert not (args.coverage_output / "cpu-ready.json").exists()


def test_socket_failure_stops_before_any_coverage_launch(canonical, monkeypatch):
    args, _ = canonical
    args.coverage_output.mkdir()
    observation = {"selection": {"input_identity": "f" * 64}, "source": str(args.root / "source" / args.source_tree)}
    monkeypatch.setattr(pc.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=1, stdout="", stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock\n"))
    monkeypatch.setattr(pc, "capture", lambda *_: pytest.fail("Socket failure launched a container"))
    monkeypatch.setattr(pc, "idle_gpu", lambda *_: pytest.fail("Socket failure reached GPU selection"))
    with pytest.raises(ValueError, match="Cannot inspect own container"):
        pc.advance(args, observation)
    assert (args.coverage_output / "selection.json").is_file()
    assert not (args.coverage_output / "cpu-ready.json").exists()


def test_cpu_failure_blocks_gpu_phase(canonical, monkeypatch):
    args, _ = canonical
    args.coverage_output.mkdir()
    observation = {"selection": {"input_identity": "f" * 64}, "source": str(args.root / "source" / args.source_tree)}
    monkeypatch.setattr(pc, "container_state", lambda *_: {"State": {"Running": False, "ExitCode": 1}})
    monkeypatch.setattr(pc, "idle_gpu", lambda *_: pytest.fail("CPU failure reached GPU selection"))
    with pytest.raises(ValueError): pc.advance(args, observation)


def test_gpu_phase_waits_for_fixed_uuid_after_cpu_success(canonical, monkeypatch):
    args, _ = canonical
    args.coverage_output.mkdir()
    key = "f" * 64
    save(args.coverage_output / "cpu-ready.json", {"status": "cpu_scientific_checks_passed", "input_identity": key, "total_sources": 296, "checkpoints": [{}] * 7})
    observation = {"selection": {"input_identity": key}, "source": str(args.root / "source" / args.source_tree)}
    monkeypatch.setattr(pc, "container_state", lambda _args, _src, role, *_: {"State": {"Running": False, "ExitCode": 0}} if role == "cpu" else None)
    monkeypatch.setattr(pc, "idle_gpu", lambda *_: ({"uuid": args.gpu_uuid, "idle": False}, [], "xml"))
    monkeypatch.setattr(pc, "capture", lambda *_: pytest.fail("Occupied GPU launched Docker"))
    assert pc.advance(args, observation)["status"] == "waiting"


def test_interrupted_gpu_container_requires_explicit_resume(canonical, monkeypatch):
    args, _ = canonical
    args.coverage_output.mkdir()
    key = "f" * 64
    save(args.coverage_output / "cpu-ready.json", {"status": "cpu_scientific_checks_passed", "input_identity": key, "total_sources": 296, "checkpoints": [{}] * 7})
    observation = {"selection": {"input_identity": key}, "source": str(args.root / "source" / args.source_tree)}
    monkeypatch.setattr(pc, "container_state", lambda *_: {"State": {"Running": False, "ExitCode": 137}})
    # CPU container succeeded; GPU container was interrupted.
    monkeypatch.setattr(pc, "container_state", lambda _args, _src, role, *_: {"State": {"Running": False, "ExitCode": 0 if role == 'cpu' else 137}})
    monkeypatch.setattr(pc, "idle_gpu", lambda *_: pytest.fail("Implicit interrupted GPU restart"))
    with pytest.raises(ValueError, match="resume-interrupted"): pc.advance(args, observation)


@pytest.fixture
def frozen_payloads():
    import torch
    from holosoma.agents.modules.student_teacher_modules import TeacherObsNormalizer
    teachers = [{"actor_model_state_dict": {"std": torch.ones(29), "actor_module.module.0.weight": torch.full((2, 3), float(i)),
                                             "actor_module.module.0.bias": torch.full((2,), float(i))}, "actor_obs_normalizer_state_dict": None} for i in range(5)]
    state = {}
    for i, teacher in enumerate(teachers):
        for key, value in teacher["actor_model_state_dict"].items():
            if key != "std": state[f"teachers.{i}." + key.removeprefix("actor_module.module.")] = value.clone()
        for key, value in TeacherObsNormalizer(3).state_dict().items():
            state[f"teacher_obs_normalizers.{i}.{key}"] = value
    return torch, teachers, {"model_state_dict": state, "num_teachers": 5, "teacher_loaded": [True] * 5}


@pytest.mark.parametrize("change", [None, "missing_actor", "swapped_experts", "missing_normalizer", "wrong_normalizer"])
def test_frozen_expert_complete_keyset_and_native_normalizer_loading(frozen_payloads, change):
    torch, teachers, student = frozen_payloads
    if change == "missing_actor": del student["model_state_dict"]["teachers.0.0.bias"]
    elif change == "swapped_experts": teachers[0], teachers[1] = teachers[1], teachers[0]
    elif change == "missing_normalizer": del student["model_state_dict"]["teacher_obs_normalizers.0.eps"]
    elif change == "wrong_normalizer": student["model_state_dict"]["teacher_obs_normalizers.0.mean"].fill_(1)
    if change:
        with pytest.raises(ValueError): pc.compare_frozen_experts(student, teachers, torch)
    else:
        assert len(pc.compare_frozen_experts(student, teachers, torch)) == 5
        assert not torch.cuda.is_initialized()


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_nested_nonfinite_model_tensor_is_rejected(number):
    import torch
    with pytest.raises(ValueError): pc.tensor_finite({"actor": [torch.tensor([number])]}, torch)
    assert not torch.cuda.is_initialized()


@pytest.mark.parametrize("change", [None, "visible_uuids", "torch_count", "torch_uuid"])
def test_actual_gpu_mapping_is_checked_before_any_worker(monkeypatch, change):
    import torch
    import uuid
    expected = "GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5"
    actual = expected if change != "torch_uuid" else "GPU-37eb1141-ab74-ebdd-42c2-6549fb7253e5"
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(pc, "capture", lambda *_: expected + ("\nGPU-other" if change == "visible_uuids" else ""))
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 2 if change == "torch_count" else 1)
    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda _: SimpleNamespace(name="synthetic-device", total_memory=1,
                        uuid=SimpleNamespace(bytes=uuid.UUID(actual.removeprefix("GPU-")).bytes)))
    if change:
        with pytest.raises(ValueError): pc.verify_gpu_mapping({"gpu_uuid": expected})
    else:
        assert pc.verify_gpu_mapping({"gpu_uuid": expected})["torch_device_count"] == 1
    assert not torch.cuda.is_initialized()


def test_child_holds_native_official_lock_throughout_work(tmp_path, monkeypatch):
    import fcntl
    official = tmp_path / "official"
    official.mkdir()
    (official / "official-acceptance.lock").touch()
    selection = {"schema_version": 1}
    selection["input_identity"] = pc.identity(selection)
    path = tmp_path / "selection.json"
    save(path, selection)
    monkeypatch.setattr(pc, "OFFICIAL", str(official))
    monkeypatch.setattr(pc.sys, "argv", ["posttrain_coverage.py", "cpu-prepare", "--selection", str(path)])
    def cpu(_):
        with (official / "official-acceptance.lock").open("rb") as other:
            with pytest.raises(BlockingIOError): fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return 0
    monkeypatch.setattr(pc, "cpu_prepare", cpu)
    assert pc.main() == 0


def test_inner_blocking_error_is_not_retried_as_lock_acquisition(tmp_path):
    (tmp_path / "official-acceptance.lock").touch()
    with pytest.raises(BlockingIOError, match="worker failure"):
        with pc.official_lock(tmp_path, wait_seconds=1):
            raise BlockingIOError("worker failure")


def test_training_output_mount_must_match_observed_manifests(canonical, monkeypatch):
    args, _ = canonical
    info = training_inspect(args, False)
    info[0]["Mounts"][1]["Source"] = "/another/passed-output"
    monkeypatch.setattr(pc, "capture", lambda *_: json.dumps(info))
    with pytest.raises(ValueError, match="actual official output"): pc.process_gate(args)


def test_original_frozen_source_content_drift_is_rejected(canonical, monkeypatch):
    args, _ = canonical
    (args.root / "source" / pc.TRAIN_TREE / "native.py").write_text("changed under same path")
    monkeypatch.setattr(pc, "capture", lambda *_: json.dumps(training_inspect(args, False)))
    with pytest.raises(ValueError, match="Changed frozen source"): pc.process_gate(args)


def test_monitor_global_lock_blocks_a_different_output_directory(tmp_path, monkeypatch):
    root = tmp_path / "research"
    root.mkdir()
    argv = ["posttrain_coverage.py", "once", "--root", str(root), "--source-tree", "a" * 64]
    monkeypatch.setattr(pc.sys, "argv", argv)
    def observe(_):
        with monkeypatch.context() as other:
            other.setattr(pc.sys, "argv", [*argv, "--coverage-output", str(root / "outputs/another-cohort")])
            with pytest.raises(BlockingIOError): pc.main()
        return {"status": "waiting", "blockers": ["unfinished official training"]}
    monkeypatch.setattr(pc, "observe", observe)
    assert pc.main() == 0
    assert (root / "outputs/.posttrain-coverage.lock").exists()
    assert not (root / "outputs/another-cohort").exists()


def test_fresh_host_cohort_has_new_identity_and_container_names(canonical, monkeypatch):
    args, _ = canonical
    source = args.root / "source" / args.source_tree
    monkeypatch.setattr(pc, "verify_snapshot", lambda _: source)
    monkeypatch.setattr(pc, "capture", lambda *_: json.dumps(training_inspect(args, False)))
    before = pc.observe(args)
    args.coverage_output = args.root / "outputs/fresh-cohort-after-reviewed-cpu-failure"
    after = pc.observe(args)
    assert before["selection"]["input_identity"] != after["selection"]["input_identity"]
    assert before["selection"]["manifests_sha256"] == after["selection"]["manifests_sha256"]
    for role in ("cpu", "gpu"):
        assert pc.docker_command(args, source, role, before["selection"]["input_identity"])[0] != pc.docker_command(args, source, role, after["selection"]["input_identity"])[0]
    assert not args.coverage_output.exists()
