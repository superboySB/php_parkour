"""CPU-only publication gates; native artifacts below are explicitly fixtures."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from scripts.research import publish_full_scene_matrix as pub
from scripts.research import sim2sim_scene_matrix as worker_contract


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def record(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": pub.digest(path)}


def worker_receipts(directory, plan):
    """Synthetic shutdown observations, never native simulation evidence."""
    workers = []
    events = [{"event":"orchestrator_started", "elapsed_seconds":0., "workers":[]}]
    for ordinal, role in enumerate(("simulator", "inference"), 1):
        pid = ordinal * 101
        ident = {"pid":pid, "process_group_id":pid, "session_id":pid, "start_time_clock_ticks":pid * 10}
        launch = [plan["worker_interpreters"][role], plan["worker_harness_record"]["path"], "--worker", role, "--output", str(directory)]
        workers.append({"role":role, "launch":launch, "identity_at_spawn":ident,
            "process_group":{"process_group_id":pid, "session_id":pid, "live_members":[dict(ident,state="S")],
                "leader_identity":{"pid":pid,"start_time_clock_ticks":pid * 10},
                "known_members":[{"pid":pid,"start_time_clock_ticks":pid * 10}],
                "ownership_verified":True,"ownership_state":"owned","ownership_lost":False,"retired":False,"ownership_reason":None},
            "returncode":None, "exit_code":None, "signal_number":None, "signal_name":None, "status":"running"})
        events.append({"event":"worker_spawned", "role":role, "elapsed_seconds":ordinal / 10, "workers":copy.deepcopy(workers)})
        write(directory / f"{role}-process-start.json", {"schema_version":1, "role":role, "argv":launch[1:], "process":ident, "python_faulthandler":"1"})
    for ordinal, role in enumerate(("simulator", "inference")):
        path = directory / f"{role}-process-start.json"
        entry = json.loads(path.read_text())
        events.append({"event":"worker_entry_observed", "role":role, "elapsed_seconds":.3 + ordinal / 10,
            "entry_sha256":pub.digest(path), "entry_process":entry["process"], "workers":copy.deepcopy(workers)})
    for worker in workers:
        worker["process_group"].update(retired=True,ownership_state="retired_empty")
        worker.update(returncode=0, exit_code=0, status="exited")
        worker["process_group"]["live_members"] = []
    completion = {"event":"workers_loop_complete", "elapsed_seconds":10., "workers":copy.deepcopy(workers)}
    events += [completion, {"event":"finally_wait_complete", "elapsed_seconds":10.1, "workers":copy.deepcopy(workers), "cleanup_errors":[], "unreaped_roles":[]}]
    write(directory / "worker-processes.json", {"schema_version":2, "harness_sha256":plan["worker_harness_record"]["sha256"], "python_faulthandler":"1", "events":events})
    return copy.deepcopy(completion)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    """Small contract fixture, never evidence of a real physical rollout."""
    monkeypatch.setattr(pub, "ROOT", tmp_path)
    monkeypatch.setattr(worker_contract, "ROOT", tmp_path)
    monkeypatch.setattr(pub, "SCENARIO_COUNTS", {"random_locomotion": 1, "low_speed_step": 1})
    raw = tmp_path / "raw"
    source = tmp_path / "source.json"; write(source, {"fixture": True})
    models = []
    for name in ("depth_backbone.onnx", "student.onnx"):
        path = tmp_path / "models" / name; path.parent.mkdir(exist_ok=True); path.write_bytes(b"CPU fixture, not an ONNX model")
        models.append(record(path))
    harness = tmp_path / "sim2sim_scene_matrix.py"; harness.write_text("# CPU fixture, never simulation\n")
    worker_harness = tmp_path / "scripts/research/sim2sim.py"; worker_harness.parent.mkdir(parents=True); worker_harness.write_text("# Synthetic worker source fixture\n")
    rows = []
    for i, scenario in enumerate(pub.SCENARIO_COUNTS):
        files = []
        for suffix in ("motion.npz", "terrain.npy", "terrain.obj"):
            path = tmp_path / "inputs" / (scenario + "_" + suffix); path.parent.mkdir(exist_ok=True); path.write_bytes(b"Fixture input " + suffix.encode()); files.append(record(path))
        output = raw / scenario / "config-0000"
        command = 6 if i == 0 else 1
        rows.append({"scenario": scenario, "configuration": "fixture-only", "configuration_index": 0, "available_configurations": 1,
                     "case_id": scenario + ":0000:fixture", "source_files": files, "mesh": files[2]["path"], "mesh_sha256": files[2]["sha256"],
                     "command": command, "output": str(output), "launch": ["fixture-python", "sim2sim.py", "--gl", "egl", "--output", str(output)]})
    plan = {"schema_version": 3, "status": "planned", "python_faulthandler": True,
            "worker_harness_record": record(worker_harness), "worker_interpreters": {"simulator":"fixture-train", "inference":"fixture-inference"}, "all_configurations": True, "planned_configurations": 2, "planned_scenarios": 2,
            "seed": 42, "seconds_per_configuration": 10, "image_id": "sha256:" + "a" * 64, "source_matrix": str(source),
            "source_matrix_sha256": pub.digest(source), "source_matrix_record": record(source), "dependencies": [record(harness), record(worker_harness)], "models": models,
            "model_sha256": {Path(r["path"]).name: r["sha256"] for r in models}, "selections": rows,
            "quality_verified": False, "obstacle_course_completion_verified": False}
    plan["plan_sha256"] = pub.identity(plan)
    matrix = copy.deepcopy(plan)
    for i, row in enumerate(matrix["selections"]):
        directory = Path(row["output"]); directory.mkdir(parents=True)
        result = {"status": "completed", "quality_verified": False, "obstacle_course_completion_verified": False,
                  "config": {"model_sha256": plan["model_sha256"], "mesh_sha256": row["mesh_sha256"], "mesh": row["mesh"],
                             "models": str(tmp_path / "models"), "commands": [row["command"]], "seed": 42, "gl": "egl", "duration": 10,
                             "record_policy": False, "course_guide": False, "python_faulthandler": True},
                  "simulation": {"status": "completed", "gantry_disabled_during_policy": True, "policy_simulation_seconds": 10.01,
                                 "fall_detected": bool(i), "minimum_pelvis_height_m": .1 if i else .7, "minimum_base_up_z": -.2 if i else 1,
                                 "final_base_up_z": 1, "path_length_xy_m": 1, "final_position_xyz_m": [1, 0, .7]},
                  "inference": {"status": "completed", "ticks": 500, "control_period_simulation_seconds": .02,
                                "lifecycle": {"damping_mode_active": True, "policy_action_disabled": True}},
                  "survival_passed": not bool(i), "videos": ["video/fixture.mp4"],
                  "video_checks": [{"video": "video/fixture.mp4", "thumbnail": "video/fixture.png",
                                    "probe": {"format": {"duration": "13"}, "streams": [{"width": 2, "height": 2}]}}]}
        result.update(worker_status_report="worker-processes.json", worker_status_at_completion=worker_receipts(directory, plan))
        write(directory / "result.json", result)
        with (directory / "trajectory.csv").open("w", newline="") as stream:
            writer = csv.writer(stream); writer.writerow(["policy_seconds", "x_m", "y_m", "pelvis_z_m", "base_up_z", "gantry_enabled", "base_yaw_rad"])
            writer.writerows((n * .02, n / 500, 0, .7, 1, 0, 0) for n in range(501))
        video = directory / "video"; video.mkdir(); (video / "fixture.mp4").write_bytes(b"CPU fixture video bytes: not playable and never physical evidence")
        (video / "fixture.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + (2).to_bytes(4, "big") * 2)
        log = raw / "logs" / (row["scenario"] + ".log"); log.parent.mkdir(exist_ok=True); log.write_text("CPU native-output fixture\n")
        case_input = {k: plan[k] for k in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
            "case_id": row["case_id"], "source_files": row["source_files"], "launch": row["launch"]}
        evidence = {"case_input": case_input, "files": [record(p) for p in sorted(directory.rglob("*")) if p.is_file()],
                    "execution": {"output": str(directory), "launch": row["launch"], "log": record(log), "returncode": 0},
                    "result_sha256": pub.digest(directory / "result.json"), "expected_policy_ticks": 500,
                    "worker_receipts": [record(directory / name) for name in ("worker-processes.json", "simulator-process-start.json", "inference-process-start.json")]}
        write(directory / "case-evidence.json", evidence)
        row.update(status="completed", returncode=0, result=result, result_report=str(directory / "result.json"), attempts=[{
            "number": 1, "status": "completed", "returncode": 0, "output": str(directory), "launch": row["launch"], "log": record(log),
            "evidence": record(directory / "case-evidence.json")}])
    matrix.update(status="completed", completed_configurations=2, completed_scenarios=2, configuration_coverage_complete=True, finished_unix=123)
    wrapper = tmp_path / "driver.py"; wrapper.write_text("# CPU receipt fixture\n")
    launch = {"launcher_sha256": pub.digest(wrapper), "launch_exit_code": 0, "image_id": plan["image_id"]}
    receipt = {"status": "completed", "returncode": 0, "completion_verified": True, "completed_configurations": 2, "finished_utc": "fixture-terminal",
               "quality_verified": False, "image_id": plan["image_id"], "harness_sha256": pub.digest(harness),
               "command": ["fixture-python", str(harness), "--all-configs", "--resume", "--matrix", str(source), "--models", str(tmp_path / "models"),
                           "--image-id", plan["image_id"], "--seconds", "10", "--output", str(raw)]}
    args = SimpleNamespace(plan=raw / "plan.json", matrix=raw / "matrix.json", driver_receipt=tmp_path / "host/receipt.json",
                           driver_launch=tmp_path / "host/launch.json", driver_wrapper=wrapper, output=tmp_path / "publication", preview_case_count=0, expected_plan_sha256=plan["plan_sha256"], expected_harness_sha256=pub.digest(harness))
    def save():
        write(args.plan, plan); write(args.matrix, matrix); receipt["matrix_sha256"] = pub.digest(args.matrix)
        write(args.driver_receipt, receipt); write(args.driver_launch, launch)
    save()
    return SimpleNamespace(plan=plan, matrix=matrix, receipt=receipt, launch=launch, args=args, save=save)


def validate(f):
    return pub.validate_all(f.plan, f.matrix, f.receipt, f.launch, f.args.driver_wrapper, pub.digest(f.args.matrix), expected_plan=f.args.expected_plan_sha256, expected_harness=f.args.expected_harness_sha256)


def reseal(f, index=0):
    row = f.matrix["selections"][index]; directory = Path(row["output"])
    write(directory / "result.json", row["result"])
    evidence_path = directory / "case-evidence.json"; evidence = json.loads(evidence_path.read_text())
    evidence["files"] = [record(p) for p in sorted(directory.rglob("*")) if p.is_file() and p != evidence_path]
    evidence["result_sha256"] = pub.digest(directory / "result.json"); write(evidence_path, evidence)
    row["attempts"][-1]["evidence"] = record(evidence_path); f.save()


def test_valid_terminal_fixture_retains_flagged_case_and_all_manifest_bytes(fixture):
    f = fixture; summary = pub.publish(f.args)
    assert summary["configurations"] == 2 and summary["threshold_events"] == 1
    assert summary["configuration_coverage_complete"] is True and summary["quality_verified"] is False
    manifest = json.loads((f.args.output / "evidence-manifest.json").read_text())
    assert all(pub.digest(f.args.output / r["path"]) == r["sha256"] for r in manifest["files"])
    assert all((f.args.output / r["path"]).read_bytes() == Path(r["source"]).read_bytes() for r in manifest["byte_copies"])
    rows = json.loads((f.args.output / "cases.json").read_text()); assert rows[1]["threshold_event"] is True


@pytest.mark.parametrize("field,value", [("status", "running"), ("returncode", 1), ("completion_verified", False), ("completed_configurations", 1), ("matrix_sha256", "0" * 64)])
def test_full_rejects_nonterminal_failed_or_unbound_driver(fixture, field, value):
    fixture.receipt[field] = value
    with pytest.raises(ValueError, match="terminal driver"): validate(fixture)


@pytest.mark.parametrize("field,value", [("status", "running"), ("completed_configurations", 1), ("configuration_coverage_complete", False)])
def test_full_rejects_running_or_partial_matrix_even_exit0(fixture, field, value):
    fixture.matrix[field] = value
    with pytest.raises(ValueError, match="terminal driver"): validate(fixture)


def test_plan_identity_and_order_cannot_be_relabelled(fixture):
    fixture.plan["selections"][0]["configuration_index"] = 9
    with pytest.raises(ValueError, match="plan identity"): validate(fixture)


def test_changed_source_file_blocks_publication(fixture):
    Path(fixture.plan["selections"][0]["mesh"]).write_bytes(b"Changed source")
    with pytest.raises(ValueError, match="changed retained file"): validate(fixture)


@pytest.mark.parametrize("fault", ["ticks", "gantry", "model", "label", "nonfinite_trajectory"])
def test_resealed_native_failure_cannot_bypass_semantic_gates(fixture, fault):
    row = fixture.matrix["selections"][0]
    if fault == "ticks": row["result"]["inference"]["ticks"] = 499
    elif fault == "gantry": row["result"]["simulation"]["gantry_disabled_during_policy"] = False
    elif fault == "model": row["result"]["config"]["model_sha256"] = {"student.onnx": "wrong"}
    elif fault == "label": row["result"]["survival_passed"] = False
    else:
        path = Path(row["output"]) / "trajectory.csv"; path.write_text(path.read_text().replace("0.7", "nan", 1))
    reseal(fixture)
    with pytest.raises(ValueError, match="Native config|nonfinite"): validate(fixture)


def test_tampered_video_and_missing_retained_artifact_are_refused(fixture):
    path = Path(fixture.matrix["selections"][0]["output"]) / "video/fixture.mp4"; path.write_bytes(b"Tampered")
    with pytest.raises(ValueError, match="changed retained file"): validate(fixture)


def test_omitting_video_from_resealed_evidence_is_refused(fixture):
    row = fixture.matrix["selections"][0]; path = Path(row["attempts"][-1]["evidence"]["path"])
    d = json.loads(path.read_text()); d["files"] = [r for r in d["files"] if not r["path"].endswith(".mp4")]; write(path, d)
    row["attempts"][-1]["evidence"] = record(path)
    with pytest.raises(ValueError, match="absent from retained"): validate(fixture)


def test_preview_is_explicit_partial_and_restricted_to_ignored_output(fixture):
    f = fixture; f.receipt.update(status="running", completion_verified=False); f.matrix["status"] = "running"; f.save()
    f.args.preview_case_count = 2
    with pytest.raises(ValueError, match="ignored outputs"): pub.publish(f.args)
    f.args.output = pub.ROOT / "outputs/research/preview"
    summary = pub.publish(f.args)
    assert summary["status"] == "preview" and summary["configuration_coverage_complete"] is False
    assert "PREVIEW" in (f.args.output / "playback.html").read_text()


def test_existing_evidence_is_never_overwritten(fixture):
    fixture.args.output.mkdir(); (fixture.args.output / "keep").write_bytes(b"Original")
    with pytest.raises(ValueError, match="empty output"): pub.publish(fixture.args)
    assert (fixture.args.output / "keep").read_bytes() == b"Original"


def test_duplicate_and_nonfinite_json_rejected():
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
        with pytest.raises(ValueError): pub.load_bytes(raw)


def add_historical_attempt(f, sealed=True):
    row = f.matrix["selections"][0]; base = Path(row["output"])
    new = base / "attempt-0002"
    original = copy.deepcopy(row["attempts"][0])
    # Copy first, then nest the successful retry without recursive copytree.
    temporary = base.with_name("retry-temporary")
    shutil.copytree(base, temporary); temporary.rename(new)
    latest = copy.deepcopy(original); latest.update(number=2, output=str(new))
    latest["launch"][-1] = str(new)
    evidence_path = new / "case-evidence.json"; evidence = json.loads(evidence_path.read_text())
    row["result"]["worker_status_at_completion"] = worker_receipts(new, f.plan)
    write(new / "result.json", row["result"])
    evidence["files"] = [record(p) for p in sorted(new.rglob("*")) if p.is_file() and p != evidence_path]
    evidence["result_sha256"] = pub.digest(new / "result.json")
    evidence["worker_receipts"] = [record(new / name) for name in
        ("worker-processes.json", "simulator-process-start.json", "inference-process-start.json")]
    evidence["execution"].update(output=str(new), launch=latest["launch"])
    write(evidence_path, evidence); latest["evidence"] = record(evidence_path)
    original["status"] = "execution_failed"  # e.g. an interrupted verification receipt; its seal is still checked.
    if not sealed:
        original.pop("evidence"); (base / "case-evidence.json").unlink()
    row.update(attempts=[original, latest], result_report=str(new / "result.json")); f.save()
    return base


def test_historical_sealed_artifact_tamper_is_not_silently_copied(fixture):
    base = add_historical_attempt(fixture)
    assert len(validate(fixture)) == 2
    (base / "video/fixture.mp4").write_bytes(b"Tampered historical bytes")
    with pytest.raises(ValueError, match="changed retained file"): validate(fixture)


def test_unsealed_failed_history_is_retained_and_marked_without_quality_claim(fixture):
    base = add_historical_attempt(fixture, sealed=False)
    pub.publish(fixture.args)
    rows = json.loads((fixture.args.output / "cases.json").read_text())
    previous = rows[0]["attempts"][0]
    assert previous["sealed"] is False and "unsealed history" in previous["integrity_scope"]
    video = next(p for p in previous["files"] if p.endswith("fixture.mp4"))
    assert (fixture.args.output / video).read_bytes() == (base / "video/fixture.mp4").read_bytes()


def test_unrecorded_retry_directory_is_refused(fixture):
    base = add_historical_attempt(fixture)
    unknown = base / "attempt-0099"; unknown.mkdir(); (unknown / "keep.log").write_text("Unlisted history")
    with pytest.raises(ValueError, match="Unrecorded attempt"): validate(fixture)


@pytest.mark.parametrize('fault', ['nonzero','unknown_group','cleanup','entry','missing_fingerprint','forged_fingerprint'])
def test_resealed_worker_exit_or_receipt_failure_cannot_publish(fixture, fault):
    row = fixture.matrix['selections'][0]; directory = Path(row['output'])
    path = directory / 'worker-processes.json'; receipt = json.loads(path.read_text())
    if fault == 'nonzero': receipt['events'][-1]['workers'][0]['returncode'] = 1
    elif fault == 'unknown_group': receipt['events'][-1]['workers'][0]['process_group']['live_members'] = None
    elif fault == 'cleanup': receipt['events'][-1]['cleanup_errors'] = [{'error':'synthetic cleanup failure'}]
    elif fault == 'entry':
        entry_path = directory / 'inference-process-start.json'; entry = json.loads(entry_path.read_text())
        entry['process']['start_time_clock_ticks'] += 1; write(entry_path, entry)
    write(path, receipt)
    reseal(fixture)
    seal_path = Path(row['attempts'][-1]['evidence']['path']); seal = json.loads(seal_path.read_text())
    seal['worker_receipts'] = [record(directory / name) for name in
        ('worker-processes.json','simulator-process-start.json','inference-process-start.json')]
    if fault == 'missing_fingerprint': seal['worker_receipts'] = []
    elif fault == 'forged_fingerprint': seal['worker_receipts'][0]['sha256'] = '0' * 64
    write(seal_path, seal); row['attempts'][-1]['evidence'] = record(seal_path); fixture.save()
    with pytest.raises(ValueError, match='worker receipts|Worker process receipt'):
        validate(fixture)


@pytest.mark.parametrize('field', ['expected_plan_sha256','expected_harness_sha256'])
def test_explicit_unexpected_cohort_hash_refuses_publication(fixture, field):
    setattr(fixture.args, field, '0' * 64)
    with pytest.raises(ValueError, match='plan identity|harness'):
        pub.publish(fixture.args)
    assert not fixture.args.output.exists()


def test_legacy_plan_can_only_produce_explicit_unverified_history_preview(fixture):
    fixture.plan['schema_version'] = 2
    fixture.plan.pop('plan_sha256'); fixture.plan['plan_sha256'] = pub.identity(fixture.plan)
    fixture.args.expected_plan_sha256 = fixture.plan['plan_sha256']
    fixture.matrix['schema_version'] = 2; fixture.matrix['plan_sha256'] = fixture.plan['plan_sha256']
    for row in fixture.matrix['selections']:
        path = Path(row['attempts'][0]['evidence']['path']); evidence = json.loads(path.read_text())
        evidence['case_input']['plan_sha256'] = fixture.plan['plan_sha256']; write(path, evidence)
        row['attempts'][0]['evidence'] = record(path)
    fixture.save()
    with pytest.raises(ValueError, match='fixed 17-scenario'):
        pub.publish(fixture.args)
    fixture.args.preview_case_count = 2; fixture.args.output = pub.ROOT / 'outputs/research/legacy-preview'
    result = pub.publish(fixture.args)
    assert result['legacy_normal_exit_unverified'] is True and result['configuration_coverage_complete'] is False
    assert '不能作为通过验收' in (fixture.args.output / 'playback.html').read_text()


def test_file_changed_after_seal_verification_is_rejected_at_copy(fixture, monkeypatch):
    base = add_historical_attempt(fixture)
    target = base / 'video/fixture.mp4'
    original = pub.check_record
    injected = []
    def check_then_mutate(record_value):
        path = original(record_value)
        if path == target and not injected:
            injected.append(True)
            target.write_bytes(b'Changed after verified seal: synthetic CPU fixture only')
        return path
    monkeypatch.setattr(pub, 'check_record', check_then_mutate)
    with pytest.raises(ValueError, match='changed before copy'):
        pub.publish(fixture.args)
    assert injected and not fixture.args.output.exists()
