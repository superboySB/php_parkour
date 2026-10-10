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


def test_dependency_closure_includes_dynamic_bridges_and_every_parent_initializer():
    records = matrix.dependencies()
    by_path = {Path(item["path"]): item for item in records}
    package_roots = [matrix.ROOT / path for path in (
        "thirdparty/holosoma/src/holosoma/holosoma",
        "thirdparty/holosoma/src/holosoma_inference/holosoma_inference", "wbt_training")]
    bridge = package_roots[0] / "bridge"
    dynamic = bridge / "unitree/unitree_sdk2py_bridge.py"
    assert dynamic in by_path
    assert by_path[dynamic] == matrix.fingerprint(dynamic)
    assert set(bridge.rglob("*.py")).issubset(by_path)
    for path in by_path:
        for package_root in package_roots:
            if not path.is_relative_to(package_root):
                continue
            parent = path.parent
            while parent.is_relative_to(package_root):
                initializer = parent / "__init__.py"
                if initializer.is_file():
                    assert initializer in by_path
                    assert by_path[initializer] == matrix.fingerprint(initializer)
                if parent == package_root:
                    break
                parent = parent.parent


def test_dependency_parent_initializer_side_effect_imports_are_recursively_scanned(tmp_path, monkeypatch):
    holosoma = tmp_path / "thirdparty/holosoma/src/holosoma/holosoma"
    sources = {
        "scripts/research/sim2sim.py": "import holosoma.hidden.deep.leaf\n",
        "docker/bin/train-python": "fixture", "docker/bin/inference-python": "fixture", "docker/bin/activate": "fixture",
        "thirdparty/holosoma/src/holosoma/holosoma/__init__.py": "import wbt_training.root_side_effect\n",
        "thirdparty/holosoma/src/holosoma/holosoma/bridge/__init__.py": "from . import bridge_side_effect\n",
        "thirdparty/holosoma/src/holosoma/holosoma/bridge/bridge_side_effect.py": "from wbt_training.nested import leaf\n",
        "thirdparty/holosoma/src/holosoma/holosoma/bridge/unitree/__init__.py": "from . import unitree_sdk2py_bridge\n",
        "thirdparty/holosoma/src/holosoma/holosoma/bridge/unitree/unitree_sdk2py_bridge.py": "# only dynamic entry point names this leaf\n",
        "thirdparty/holosoma/src/holosoma/holosoma/hidden/__init__.py": "from . import parent_side_effect\n",
        "thirdparty/holosoma/src/holosoma/holosoma/hidden/parent_side_effect.py": "from wbt_training import root_side_effect\n",
        "thirdparty/holosoma/src/holosoma/holosoma/hidden/deep/__init__.py": "# deep package\n",
        "thirdparty/holosoma/src/holosoma/holosoma/hidden/deep/leaf.py": "# AST discovered leaf\n",
        "wbt_training/__init__.py": "from . import root_side_effect\n",
        "wbt_training/root_side_effect.py": "# root initializer side effect\n",
        "wbt_training/nested/__init__.py": "from . import initializer_only\n",
        "wbt_training/nested/leaf.py": "# imported via bridge parent initializer\n",
        "wbt_training/nested/initializer_only.py": "# no leaf import points here\n",
    }
    for relative, content in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    records = {Path(item["path"]): item for item in matrix.dependencies()}
    assert all(tmp_path / relative in records for relative in sources)
    assert records[holosoma / "bridge/unitree/unitree_sdk2py_bridge.py"] == matrix.fingerprint(holosoma / "bridge/unitree/unitree_sdk2py_bridge.py")


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
    helper = tmp_path / "scripts/research/sim2sim.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# Frozen native dependency fixture\n")
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
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


def native_worker_receipt_fixture(output, plan):
    """Synthetic wrapper/native-child receipts, never real worker execution."""
    workers = []
    entries = []
    for role, pid, native_pid in (("simulator",1101,1101),("inference",2201,2202)):
        launch = [plan["worker_interpreters"][role],plan["worker_harness_record"]["path"],"--worker",role,"--output",str(output)]
        born = pid*10
        identity = {"pid":pid,"process_group_id":pid,"session_id":pid,"start_time_clock_ticks":born}
        members = [dict(identity,state="S")]
        leader = {"pid":pid,"start_time_clock_ticks":born}
        worker = {"role":role,"launch":launch,"identity_at_spawn":identity,
            "process_group":{"process_group_id":pid,"session_id":pid,"live_members":members,
                "leader_identity":leader,"known_members":[dict(leader)],"retired":False,"ownership_lost":False,
                "ownership_state":"owned","ownership_reason":None,"ownership_verified":True},
            "returncode":None,"exit_code":None,"signal_number":None,"signal_name":None,"status":"running"}
        workers.append(worker)
        native = {"pid":native_pid,"process_group_id":pid,"session_id":pid,"start_time_clock_ticks":born+(native_pid!=pid)}
        entries.append({"schema_version":1,"role":role,"argv":launch[1:],"process":native,"python_faulthandler":"1"})
    for entry in entries:
        matrix.write(output/f"{entry['role']}-process-start.json",entry)
    events = [{"event":"orchestrator_started","elapsed_seconds":0.,"workers":[]},
        {"event":"worker_spawned","role":"simulator","elapsed_seconds":.1,"workers":copy.deepcopy(workers[:1])},
        {"event":"worker_spawned","role":"inference","elapsed_seconds":.2,"workers":copy.deepcopy(workers)}]
    workers[1]["process_group"]["live_members"].append(dict(entries[1]["process"],state="S"))
    workers[1]["process_group"]["known_members"].append({key:entries[1]["process"][key] for key in ("pid","start_time_clock_ticks")})
    for index,entry in enumerate(entries):
        events.append({"event":"worker_entry_observed","role":entry["role"],"elapsed_seconds":.3+index*.1,
            "entry_sha256":matrix.digest(output/f"{entry['role']}-process-start.json"),
            "entry_process":copy.deepcopy(entry["process"]),"workers":copy.deepcopy(workers)})
    for worker in workers:
        worker.update(returncode=0,exit_code=0,status="exited")
        worker["process_group"].update(live_members=[],retired=True,ownership_state="retired_empty")
    completion = {"event":"workers_loop_complete","elapsed_seconds":10.,"workers":copy.deepcopy(workers)}
    events += [completion, {"event":"finally_enter","elapsed_seconds":10.1,"workers":copy.deepcopy(workers)},
        {"event":"finally_wait_complete","elapsed_seconds":10.2,"workers":copy.deepcopy(workers),"unreaped_roles":[],"cleanup_errors":[]}]
    receipt = {"schema_version":2,"harness_sha256":plan["worker_harness_record"]["sha256"],"python_faulthandler":"1","events":events}
    matrix.write(output/"worker-processes.json",receipt)
    return copy.deepcopy(completion)


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
            "seed": plan["seed"], "duration": 10., "gl": "egl", "record_policy": False, "course_guide": False,"python_faulthandler":True},
        "simulation": {"status": "completed", "gantry_disabled_during_policy": True, "policy_simulation_seconds": 10.014},
        "inference": {"status": "completed", "ticks": ticks, "control_period_simulation_seconds": .02,
            "lifecycle": {"damping_mode_active": True, "policy_action_disabled": True}},
        "videos": ["video/rollout.mp4"], "video_checks": [{"video": "video/rollout.mp4", "thumbnail": "video/rollout.png",
            "probe": {"format": {"duration": "14.0"}}}], "survival_passed": False}
    result.update(worker_status_report="worker-processes.json",worker_status_at_completion=native_worker_receipt_fixture(output,plan))
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


@pytest.mark.parametrize("artifact", ("video/rollout.mp4", "trajectory.csv", "result.json", "case-evidence.json",
                                    "worker-processes.json","simulator-process-start.json","inference-process-start.json"))
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


def test_schema3_plan_binds_harness_and_every_case_faulthandler(run_fixture):
    args, plan, helper = run_fixture
    assert plan["schema_version"] == 3 and plan["python_faulthandler"] is True
    assert plan["worker_harness_record"] == matrix.fingerprint(helper)
    assert plan["worker_harness_record"] in plan["dependencies"]
    assert all("--python-faulthandler" in item["launch"] for item in plan["selections"])


@pytest.mark.parametrize("fault", ["legacy","missing_supervisor","missing_entry","nonzero","running","signal",
    "live_group","unknown_group","cleanup","unreaped","missing_final","duplicate_final","extra_after_final",
    "completion_snapshot","harness","faulthandler","entry_role","entry_argv","entry_pid","entry_birth",
    "entry_group","spawn_birth","spawn_launch","child_unobserved","reordered_roles","symlink",
    "boolean_returncode","missing_signal","duplicate_harness","supervisor_schema","entry_schema",
    "ownership_false","ownership_unknown","not_retired","ownership_lost","leader_birth","known_native_missing",
    "entry_sha","entry_snapshot","missing_sim_entry_event","duplicate_entry_event","wrong_harness_path"])
def test_worker_receipt_gate_rejects_adversarial_shutdown_evidence(run_fixture,fault):
    args,plan,_ = run_fixture
    output=args.output/"single"
    selection=plan["selections"][0]
    native_output_fixture(output,plan,selection)
    result=matrix.json.loads((output/"result.json").read_text())
    receipt=matrix.json.loads((output/"worker-processes.json").read_text())
    entry=matrix.json.loads((output/"inference-process-start.json").read_text())
    final=receipt["events"][-1]
    worker=final["workers"][0]
    if fault == "legacy": plan["schema_version"] = 2
    elif fault == "missing_supervisor": (output/"worker-processes.json").unlink()
    elif fault == "missing_entry": (output/"inference-process-start.json").unlink()
    elif fault == "nonzero": worker["returncode"] = 1
    elif fault == "running": worker["status"] = "running"
    elif fault == "signal": worker["signal_number"] = 11
    elif fault == "live_group": worker["process_group"]["live_members"] = [{"pid":999}]
    elif fault == "unknown_group": worker["process_group"]["live_members"] = None
    elif fault == "cleanup": final["cleanup_errors"] = [{"error":"log-close failed"}]
    elif fault == "unreaped": final["unreaped_roles"] = ["simulator"]
    elif fault == "missing_final": receipt["events"].pop()
    elif fault == "duplicate_final": receipt["events"].append(copy.deepcopy(final))
    elif fault == "extra_after_final": receipt["events"].append({"event":"unexpected","elapsed_seconds":11.})
    elif fault == "completion_snapshot": result["worker_status_at_completion"]["workers"][0]["exit_code"] = 9
    elif fault == "harness": receipt["harness_sha256"] = "f"*64
    elif fault == "faulthandler": entry["python_faulthandler"] = None
    elif fault == "entry_role": entry["role"] = "simulator"
    elif fault == "entry_argv": entry["argv"][-1] = "/different/output"
    elif fault == "entry_pid": entry["process"]["pid"] = 9999
    elif fault == "entry_birth": entry["process"]["start_time_clock_ticks"] += 1
    elif fault == "entry_group": entry["process"]["session_id"] = 7
    elif fault == "spawn_birth": worker["identity_at_spawn"]["start_time_clock_ticks"] += 1
    elif fault == "spawn_launch": worker["launch"][0] = "/different/python"
    elif fault == "child_unobserved": receipt["events"] = [e for e in receipt["events"] if e["event"] != "worker_entry_observed"]
    elif fault == "reordered_roles": final["workers"].reverse()
    elif fault == "boolean_returncode": worker["returncode"] = False
    elif fault == "missing_signal": worker.pop("signal_number")
    elif fault == "duplicate_harness": plan["dependencies"].append(copy.deepcopy(plan["worker_harness_record"]))
    elif fault == "supervisor_schema": receipt["schema_version"] = 1
    elif fault == "entry_schema": entry["schema_version"] = 2
    elif fault == "ownership_false": worker["process_group"]["ownership_verified"] = False
    elif fault == "ownership_unknown": worker["process_group"]["ownership_state"] = "unknown"
    elif fault == "not_retired": worker["process_group"]["retired"] = False
    elif fault == "ownership_lost": worker["process_group"]["ownership_lost"] = True
    elif fault == "leader_birth": worker["process_group"]["leader_identity"]["start_time_clock_ticks"] += 1
    elif fault == "known_native_missing": final["workers"][1]["process_group"]["known_members"] = []
    elif fault == "entry_sha": next(e for e in receipt["events"] if e["event"] == "worker_entry_observed")["entry_sha256"] = "f"*64
    elif fault == "entry_snapshot": next(e for e in receipt["events"] if e["event"] == "worker_entry_observed")["entry_process"]["pid"] += 1
    elif fault == "missing_sim_entry_event": receipt["events"] = [e for e in receipt["events"] if not(e["event"] == "worker_entry_observed" and e["role"] == "simulator")]
    elif fault == "duplicate_entry_event": receipt["events"].insert(4,copy.deepcopy(receipt["events"][3]))
    elif fault == "wrong_harness_path": plan["worker_harness_record"]["path"] = "/other/scripts/research/sim2sim.py"
    else:
        path=output/"inference-process-start.json";target=output/"alias.json";path.rename(target);path.symlink_to(target)
    if fault != "missing_supervisor": matrix.write(output/"worker-processes.json",receipt)
    if fault not in ("missing_entry","symlink"): matrix.write(output/"inference-process-start.json",entry)
    with pytest.raises((ValueError,KeyError)):
        matrix.validate_worker_receipts(output,plan,result)


def test_retention_requires_three_worker_receipt_hashes(run_fixture,monkeypatch):
    args,plan,_=run_fixture
    fake_child(monkeypatch,plan)
    args.case_limit=1
    report=matrix.execute(args,plan)
    attempt=report["selections"][0]["attempts"][0]
    evidence=matrix.json.loads(Path(attempt["evidence"]["path"]).read_text())
    assert {Path(item["path"]).name for item in evidence["worker_receipts"]} == {
        "worker-processes.json","simulator-process-start.json","inference-process-start.json"}
    assert all(item in evidence["files"] for item in evidence["worker_receipts"])
    evidence["worker_receipts"] = []
    matrix.write(Path(attempt["evidence"]["path"]),evidence)
    attempt["evidence"] = matrix.fingerprint(Path(attempt["evidence"]["path"]))
    with pytest.raises(ValueError,match="worker receipts"):
        matrix.verify_completed(attempt,plan,report["selections"][0])


def test_worker_receipts_validate_host_mapping_without_rewriting_raw(run_fixture):
    args,plan,helper=run_fixture
    native_dir=Path("/outputs/native/one-case")
    native_harness="/workspace/php_parkour/scripts/research/sim2sim.py"
    host_dir=args.output/"host-case"
    native_output_fixture(host_dir,plan,plan["selections"][0])
    # Model a retained native report accessed through an independent host mount.
    receipt=json.loads((host_dir/"worker-processes.json").read_text())
    plan["worker_harness_record"]["path"]=native_harness
    for event in receipt["events"]:
        for worker in event.get("workers",[]):
            worker["launch"][-1]=str(native_dir)
            worker["launch"][1]=native_harness
    for role in ("simulator","inference"):
        path=host_dir/f"{role}-process-start.json";entry=json.loads(path.read_text());entry["argv"][-1]=str(native_dir);entry["argv"][0]=native_harness;matrix.write(path,entry)
        next(e for e in receipt["events"] if e["event"] == "worker_entry_observed" and e["role"] == role)["entry_sha256"] = matrix.digest(path)
    result=json.loads((host_dir/"result.json").read_text())
    result["worker_status_at_completion"]=copy.deepcopy(next(e for e in receipt["events"] if e["event"]=="workers_loop_complete"))
    matrix.write(host_dir/"worker-processes.json",receipt)
    before={p.name:p.read_bytes() for p in host_dir.glob("*.json")}
    mapped={str(native_dir):host_dir,native_harness:helper}
    records=matrix.validate_worker_receipts(host_dir,plan,result,translate=lambda p: mapped.get(p,p))
    assert len(records)==3 and before=={p.name:p.read_bytes() for p in host_dir.glob("*.json")}
