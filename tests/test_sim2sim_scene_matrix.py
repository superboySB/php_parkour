"""CPU selection/resume/provenance checks; native child output is a fixture."""
from __future__ import annotations

import copy
import csv
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.research import sim2sim_scene_matrix as matrix

REAL_RUNNING_CHILDREN = matrix.running_children


def catalog():
    scenarios = []
    for name in matrix.SCENARIOS:
        rows = []
        for index in range(matrix.CONFIG_COUNTS[name]):
            stem = f"forward-{index}"
            rows.append({"name": stem, "index": index, "status": "passed", "duration_seconds": 10.,
                "steps": [{"vel_cmd_idx": 6}], "terrain_vertices": 8 if index == 0 else 80,
                "files": [{"path": f"/fixture/{name}/{stem}{suffix}", "sha256": "fixture"} for suffix in
                          ("_motion.npz", "_terrain.npy", "_terrain.obj")]})
        scenarios.append({"name": name, "status": "passed", "result": {
            "total_available_configs": len(rows), "configurations": rows}})
    return {"scenarios": scenarios}


def test_default_seventeen_contract_and_explicit_all_629():
    source = catalog()
    default = matrix.select(source)
    all_cases = matrix.select(source, all_configs=True)
    assert len(default) == 17 and len(all_cases) == 629
    assert [item["scenario"] for item in default] == list(matrix.SCENARIOS)
    assert default[0]["configuration_index"] == 1  # Original clutter-forward representative rule.
    assert all_cases[0]["configuration_index"] == 0  # Full coverage also includes plain ground.
    assert len({item["case_id"] for item in all_cases}) == 629
    assert all(item["command"] == (1 if item["scenario"].startswith("low_speed_") else 6) for item in all_cases)


@pytest.mark.parametrize("fault", ("missing", "failed", "duplicate_index", "duplicate_name", "missing_pair", "duplicate_scenario"))
def test_all_configs_refuses_incomplete_or_ambiguous_source(fault):
    source = catalog()
    group = source["scenarios"][0]["result"]["configurations"]
    if fault == "missing":
        group.pop()
    elif fault == "failed":
        group[0]["status"] = "failed"
    elif fault == "duplicate_index":
        group[1]["index"] = group[0]["index"]
    elif fault == "duplicate_name":
        group[1]["name"] = group[0]["name"]
    elif fault == "missing_pair":
        group[0]["files"].pop(0)
    else:
        source["scenarios"].append(copy.deepcopy(source["scenarios"][0]))
    with pytest.raises(ValueError):
        matrix.select(source, all_configs=True)


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    for name in ("depth_backbone.onnx", "student.onnx"):
        (models / name).write_bytes(name.encode())
    helper = tmp_path / "native-helper.py"
    helper.write_text("# Frozen native dependency fixture\n")
    source = tmp_path / "source.json"
    source.write_text("{}")
    selections = []
    for index, name in enumerate(("random_locomotion", "low_speed_step")):
        files = []
        for suffix in ("_motion.npz", "_terrain.npy", "_terrain.obj"):
            path = tmp_path / (name + suffix)
            path.write_bytes((name + suffix).encode())
            files.append(matrix.fingerprint(path))
        selections.append({"scenario": name, "configuration": "forward:" + "a" * 205,
            "configuration_index": index, "case_id": f"{name}:{index}:fixture", "source_files": files,
            "mesh": files[2]["path"], "mesh_sha256": files[2]["sha256"], "command": 6 if index == 0 else 1})
    monkeypatch.setattr(matrix, "select", lambda source, all_configs=False: copy.deepcopy(selections))
    monkeypatch.setattr(matrix, "dependencies", lambda: [matrix.fingerprint(helper)])
    monkeypatch.setattr(matrix, "GLOBAL_LOCK", tmp_path / "matrix-global.lock")
    # Fixture rollouts neither participate in nor inspect real container DDS
    # jobs. Dedicated /proc tests below use a real, PID-scoped CPU process.
    monkeypatch.setattr(matrix, "running_children", lambda base=None: [])
    args = SimpleNamespace(matrix=source, models=models, output=tmp_path / "output", seconds=10., seed=42,
        gl="egl", sim_python="/opt/php/bin/train-python", inference_python="/opt/php/bin/inference-python",
        image_id="sha256:" + "a" * 64, all_configs=True, resume=False, case_id=[], case_limit=None)
    plan = matrix.make_plan(args)
    return args, plan, helper


def native_output_fixture(output, plan, selection, ticks=500):
    output.mkdir(parents=True)
    (output / "video").mkdir()
    (output / "video/rollout.mp4").write_bytes(b"Fixture video bytes; tests do not decode video or simulate physics")
    (output / "video/rollout.png").write_bytes(b"Fixture thumbnail")
    with (output / "trajectory.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(("policy_seconds", "x_m", "y_m", "pelvis_z_m", "base_up_z", "gantry_enabled", "base_yaw_rad"))
        for index in range(501):
            writer.writerow((index * .02, 0, 0, .7, 1, 0, 0))
    result = {"status": "completed", "quality_verified": False, "obstacle_course_completion_verified": False,
        "config": {"models": str(Path(plan["models"][0]["path"]).parent), "model_sha256": plan["model_sha256"],
            "mesh": selection["mesh"], "mesh_sha256": selection["mesh_sha256"], "commands": [selection["command"]],
            "seed": plan["seed"], "duration": 10., "gl": "egl", "record_policy": False, "course_guide": False},
        "simulation": {"status": "completed", "gantry_disabled_during_policy": True, "policy_simulation_seconds": 10.014},
        "inference": {"status": "completed", "ticks": ticks, "control_period_simulation_seconds": .02,
            "lifecycle": {"damping_mode_active": True, "policy_action_disabled": True}},
        "videos": ["video/rollout.mp4"], "video_checks": [{"video": "video/rollout.mp4", "thumbnail": "video/rollout.png",
            "probe": {"format": {"duration": "14.0"}}}], "survival_passed": False}
    matrix.write(output / "result.json", result)


def fake_child(monkeypatch, plan, *, code=0, ticks=500):
    calls = []
    def run(launch, **kwargs):
        output = Path(launch[launch.index("--output") + 1])
        selection = next(item for item in plan["selections"] if item["mesh"] == launch[launch.index("--mesh") + 1])
        calls.append(output)
        kwargs["stdout"].write("CPU-only native output fixture\n")
        if code == 0:
            native_output_fixture(output, plan, selection, ticks)
        else:
            output.mkdir(parents=True)
            (output / "error.json").write_text('{"fixture_failure": true}')
        return SimpleNamespace(returncode=code)
    monkeypatch.setattr(matrix.subprocess, "run", run)
    return calls


def test_resume_skips_only_verified_complete_case_then_finishes_subset(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    calls = fake_child(monkeypatch, plan)
    args.case_limit = 1
    first = matrix.execute(args, plan)
    assert first["status"] == "completed_subset" and first["completed_configurations"] == 1
    assert first["configuration_coverage_complete"] is False
    assert len(calls) == 1 and len(calls[0].name) < 120
    args.resume, args.case_limit = True, None
    final = matrix.execute(args, plan)
    assert final["status"] == "completed" and final["completed_configurations"] == 2
    assert len(calls) == 2 and len(final["selections"][0]["attempts"]) == 1
    assert final["quality_verified"] is False and final["heuristic_survival_configurations"] == 0


@pytest.mark.parametrize("artifact", ("video/rollout.mp4", "trajectory.csv", "result.json", "case-evidence.json"))
def test_resume_refuses_changed_complete_evidence(run_fixture, monkeypatch, artifact):
    args, plan, helper = run_fixture
    fake_child(monkeypatch, plan)
    args.case_limit = 1
    report = matrix.execute(args, plan)
    output = Path(report["selections"][0]["attempts"][0]["output"])
    (output / artifact).write_bytes(b"changed")
    args.resume = True
    with pytest.raises(ValueError, match="changed"):
        matrix.execute(args, plan)
    assert json.loads((args.output / "matrix.json").read_text())["status"] == "execution_failed"


@pytest.mark.parametrize("input_kind", ("helper", "source", "model", "mesh"))
def test_per_case_input_change_blocks_resume(run_fixture, monkeypatch, input_kind):
    args, plan, helper = run_fixture
    fake_child(monkeypatch, plan)
    args.case_limit = 1
    matrix.execute(args, plan)
    target = {"helper": helper, "source": args.matrix, "model": args.models / "student.onnx",
              "mesh": Path(plan["selections"][0]["mesh"])}[input_kind]
    target.write_bytes(b"changed")
    args.resume = True
    with pytest.raises(ValueError, match="input changed"):
        matrix.execute(args, plan)


@pytest.mark.parametrize("fault", ("launch", "parent_log", "result_summary"))
def test_resume_binds_actual_launch_and_parent_log(run_fixture, monkeypatch, fault):
    args, plan, helper = run_fixture
    fake_child(monkeypatch, plan)
    args.case_limit = 1
    report = matrix.execute(args, plan)
    attempt = report["selections"][0]["attempts"][0]
    if fault == "launch":
        attempt["launch"][attempt["launch"].index("--seed") + 1] = "999"
        matrix.write(args.output / "matrix.json", report)
    elif fault == "parent_log":
        Path(attempt["log"]["path"]).write_text("Changed parent log\n")
    else:
        report["selections"][0]["result"]["survival_passed"] = True
        matrix.write(args.output / "matrix.json", report)
    args.resume = True
    with pytest.raises(ValueError, match="changed"):
        matrix.execute(args, plan)


def test_resume_refuses_changed_plan_fields_in_mutable_matrix(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    fake_child(monkeypatch, plan)
    args.case_limit = 1
    report = matrix.execute(args, plan)
    report["planned_configurations"] = 999
    matrix.write(args.output / "matrix.json", report)
    args.resume = True
    with pytest.raises(ValueError, match="immutable plan"):
        matrix.execute(args, plan)


def test_surviving_native_child_blocks_interrupted_attempt_resume(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    args.case_limit = 1
    fake_child(monkeypatch, plan, code=7)
    report = matrix.execute(args, plan)
    output = Path(report["selections"][0]["attempts"][0]["output"])
    process = isolated_native_argv_process(monkeypatch, output)
    args.resume = True
    try:
        assert process.pid in matrix.running_children(output)
        with pytest.raises(ValueError, match="still running"):
            matrix.execute(args, plan)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_failed_attempt_is_preserved_and_rerun_in_new_directory(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    args.case_limit = 1
    failed_calls = fake_child(monkeypatch, plan, code=7)
    first = matrix.execute(args, plan)
    assert first["status"] == "execution_failed"
    original = failed_calls[0]
    assert (original / "error.json").exists()
    new_calls = fake_child(monkeypatch, plan)
    args.resume = True
    second = matrix.execute(args, plan)
    attempts = second["selections"][0]["attempts"]
    assert [attempt["status"] for attempt in attempts] == ["execution_failed", "completed"]
    assert new_calls[0] == original / "attempt-0002"
    assert (original / "error.json").exists()


def test_wrong_policy_ticks_cannot_be_marked_completed(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    args.case_limit = 1
    fake_child(monkeypatch, plan, ticks=499)
    report = matrix.execute(args, plan)
    assert report["status"] == "execution_failed" and report["completed_configurations"] == 0


def test_output_lock_prevents_concurrent_driver(run_fixture):
    args, plan, helper = run_fixture
    lock = args.output.with_name(args.output.name + ".lock")
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="lock"):
            matrix.execute(args, plan)


def test_container_lock_prevents_different_output_driver(run_fixture):
    args, plan, helper = run_fixture
    args.output = args.output.with_name("different-output")
    with matrix.GLOBAL_LOCK.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="container-wide"):
            matrix.execute(args, plan)


def harmless_native_argv_process(output):
    # This process runs only stdlib sleep, while exposing the exact argv markers
    # used by /proc liveness checks. It never imports MuJoCo, SDK or GPU code.
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)",
                             str(matrix.ROOT / "scripts/research/sim2sim.py"), "--output", str(output)])


def isolated_native_argv_process(monkeypatch, output):
    process = harmless_native_argv_process(output)
    # Exercise the actual /proc parser, while only this test owns the selected
    # PID. An independent real rollout may be running in another output.
    monkeypatch.setattr(matrix, "running_children", lambda base=None:
                        [pid for pid in REAL_RUNNING_CHILDREN(base) if pid == process.pid])
    return process


def test_live_excluded_case_blocks_resume_then_receipt_becomes_interrupted(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    args.case_limit = 1
    fake_child(monkeypatch, plan, code=7)
    report = matrix.execute(args, plan)
    first = report["selections"][0]
    original = Path(first["attempts"][0]["output"])
    first["attempts"][0]["status"] = first["status"] = report["status"] = "running"
    matrix.write(args.output / "matrix.json", report)
    args.resume, args.case_limit, args.case_id = True, None, [plan["selections"][1]["case_id"]]
    process = isolated_native_argv_process(monkeypatch, original)
    try:
        assert process.pid in matrix.running_children(args.output)
        with pytest.raises(ValueError, match="still running"):
            matrix.execute(args, plan)
        assert json.loads((args.output / "matrix.json").read_text())["selections"][0]["attempts"][0]["status"] == "running"
    finally:
        process.terminate()
        process.wait(timeout=5)
    fake_child(monkeypatch, plan)
    resumed = matrix.execute(args, plan)
    assert resumed["selections"][0]["attempts"][0]["status"] == "interrupted"
    assert (original / "error.json").exists()
    args.case_id = [plan["selections"][0]["case_id"]]
    final = matrix.execute(args, plan)
    assert [item["status"] for item in final["selections"][0]["attempts"]] == ["interrupted", "completed"]
    assert final["selections"][0]["attempts"][1]["output"] == str(original / "attempt-0002")


def test_live_native_child_from_other_output_blocks_new_matrix(run_fixture, monkeypatch):
    args, plan, helper = run_fixture
    other_output = args.output.with_name("other-output") / "old-case"
    process = isolated_native_argv_process(monkeypatch, other_output)
    try:
        assert process.pid in matrix.running_children(other_output)
        with pytest.raises(ValueError, match="still running"):
            matrix.execute(args, plan)
        assert not args.output.exists()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_dependency_list_excludes_motion_gui_and_includes_native_execution():
    paths = {item["path"] for item in matrix.dependencies()}
    assert str(matrix.ROOT / "scripts/research/sim2sim.py") in paths
    assert str(matrix.ROOT / "scripts/research/sim2sim_scene_matrix.py") in paths
    assert any(path.endswith("simulator/mujoco/mujoco.py") for path in paths)
    assert any(path.endswith("policies/depth_distillation.py") for path in paths)
    assert not any("/motion_matching/" in path or path.endswith("README.md") for path in paths)
