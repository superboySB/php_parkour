"""CPU finalizer contracts using the existing synthetic native matrix fixtures.

Videos are explicit byte-string fixtures and ffmpeg is a test double. These
tests verify rejection/receipt behavior, not physical rollouts or real decoding.
Root separately decodes the retained native videos in the project Docker.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.research import sim2sim_scene_matrix as matrix
from scripts.research import validate_scene_matrix as finalizer
from test_sim2sim_scene_matrix import (
    catalog, native_output_fixture, reference_fixture, reference_output_fixture,
    run_fixture,
)


def reidentify(plan):
    plan["plan_sha256"] = matrix.identity({key: value for key, value in plan.items() if key != "plan_sha256"})


@pytest.fixture
def full_scope():
    """Only a 629-case identity/scope fixture; no 629 physical results exist."""
    plan = {"schema_version": 3, "status": "planned", "python_faulthandler": True,
            "all_configurations": True, "planned_configurations": 629, "planned_scenarios": 17,
            "quality_verified": False, "obstacle_course_completion_verified": False,
            "selections": matrix.select(catalog(), all_configs=True)}
    reidentify(plan)
    report = copy.deepcopy(plan)
    report.update(status="completed", configuration_coverage_complete=True, completed_configurations=629,
                  completed_scenarios=17, last_invocation={"case_ids": [], "case_limit": None,
                  "resume": False, "requested_configurations": 629})
    return plan, report


def test_full_629_scope_and_live_exact_preview_are_distinct(full_scope):
    plan, report = full_scope
    assert finalizer.validate_scope(plan, report, []) == list(range(629))
    report.update(status="running", completed_configurations=1, configuration_coverage_complete=False)
    assert finalizer.validate_scope(plan, report, [plan["selections"][0]["case_id"]]) == [0]
    with pytest.raises(ValueError, match="Full validation"):
        finalizer.validate_scope(plan, report, [])


@pytest.mark.parametrize("fault", ("identity", "order", "case_input", "count", "scenario_count", "duplicate"))
def test_plan_and_case_identity_tampering_is_rejected_even_for_preview(full_scope, fault):
    plan, report = full_scope
    if fault == "identity": plan["plan_sha256"] = "f" * 64
    elif fault == "order": report["selections"][:2] = reversed(report["selections"][:2])
    elif fault == "case_input": report["selections"][0]["mesh_sha256"] = "f" * 64
    else:
        if fault == "count": plan["planned_configurations"] = 1
        elif fault == "scenario_count": plan["planned_scenarios"] = 1
        else: plan["selections"][1] = copy.deepcopy(plan["selections"][0])
        reidentify(plan)
        report.update(copy.deepcopy(plan))
    with pytest.raises(ValueError):
        finalizer.validate_scope(plan, report, [plan["selections"][0]["case_id"]])


@pytest.mark.parametrize("fault", ("status", "coverage", "count", "scene_count", "case_ids", "limit", "resume", "requested"))
def test_full_completion_refuses_partial_filtered_or_resumed_invocations(full_scope, fault):
    plan, report = full_scope
    if fault == "status": report["status"] = "completed_subset"
    elif fault == "coverage": report["configuration_coverage_complete"] = False
    elif fault == "count": report["completed_configurations"] = 628
    elif fault == "scene_count": report["completed_scenarios"] = 16
    elif fault == "case_ids": report["last_invocation"]["case_ids"] = [plan["selections"][0]["case_id"]]
    elif fault == "limit": report["last_invocation"]["case_limit"] = 629
    elif fault == "resume": report["last_invocation"]["resume"] = True
    else: report["last_invocation"]["requested_configurations"] = 628
    with pytest.raises(ValueError, match="Full validation"):
        finalizer.validate_scope(plan, report, [])


@pytest.mark.parametrize("preview", (("missing-case",), ("duplicate", "duplicate")))
def test_preview_refuses_unknown_or_duplicate_case_ids(full_scope, preview):
    plan, report = full_scope
    ids = [plan["selections"][0]["case_id"]] * 2 if preview[0] == "duplicate" else list(preview)
    with pytest.raises(ValueError, match="distinct, existing"):
        finalizer.validate_scope(plan, report, ids)


@pytest.fixture(params=("constant", "reference"))
def retained(request, monkeypatch):
    """Reuse real matrix validators with two synthetic, sealed native attempts."""
    args, original, helper = request.getfixturevalue("reference_fixture" if request.param == "reference" else "run_fixture")
    plan = copy.deepcopy(original)
    scripts = helper.parent
    module = scripts / "sim2sim_scene_matrix.py"
    module.write_bytes(Path(matrix.__file__).read_bytes())
    reader = scripts / "reference_commands.py"
    reader.write_bytes((Path(matrix.__file__).parent / "reference_commands.py").read_bytes())
    plan["dependencies"].extend(matrix.fingerprint(path) for path in (module, reader))
    # The fixture validates a bounded two-case plan, never claims all 629.
    plan.update(all_configurations=False, planned_scenarios=2)
    reidentify(plan)
    report = copy.deepcopy(plan)
    args.output.mkdir()
    for case in report["selections"]:
        directory = Path(case["output"])
        if plan.get("reference_commands"):
            native = reference_output_fixture(directory, plan, case)
        else:
            native_output_fixture(directory, plan, case)
            native = json.loads((directory / "result.json").read_text())
        native["simulation"]["fall_detected"] = True
        matrix.write(directory / "result.json", native)
        log = args.output / f"fixture-{case['configuration_index']}.log"
        log.write_text("Synthetic native fixture; no physical worker was run.\n")
        sealed = matrix.retain_evidence(directory, plan, case, case["launch"], log)
        attempt = {"number": 1, "status": "completed", "returncode": 0, "output": str(directory),
                   "launch": case["launch"], "log": matrix.fingerprint(log), "evidence": sealed["evidence"]}
        case.update(status="completed", attempts=[attempt], result=sealed["result"], result_report=str(directory / "result.json"))
    report.update(status="completed", configuration_coverage_complete=True, completed_configurations=2,
                  completed_scenarios=2, last_invocation={"case_ids": [], "case_limit": None,
                  "resume": False, "requested_configurations": 2})
    matrix.write(args.output / "plan.json", plan)
    matrix.write(args.output / "matrix.json", report)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    return SimpleNamespace(plan=args.output / "plan.json", matrix=args.output / "matrix.json",
        output=args.output.parent / "validation.json", matrix_module=module, preview_case_id=[]), plan, report


@pytest.fixture
def decoder(monkeypatch):
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv[:7] == ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-threads", "1"]
        assert argv[-3:] == ["-f", "null", "-"] and kwargs["timeout"] == 120
        return SimpleNamespace(returncode=0, stderr="", stdout="")
    monkeypatch.setattr(finalizer.subprocess, "run", run)
    return calls


def failed_receipt(args):
    value = json.loads(args.output.read_text())
    assert value["status"] == "failed" and value["completion_verified"] is False
    assert value["quality_verified"] is value["obstacle_course_completion_verified"] is False
    return value


def test_bounded_validation_keeps_real_scope_and_variable_policy_ticks(retained, decoder):
    args, plan, _ = retained
    scripts_before = {path.relative_to(args.matrix_module.parent) for path in args.matrix_module.parent.rglob("*")}
    value = finalizer.validate(args)
    assert value["status"] == "passed" and value["configurations"] == value["planned_configurations"] == 2
    assert value["completion_verified"] is True and value["overall_native_parent_exit_verified"] is False
    assert value["worker_exit0_empty_group_count"] == 4 and value["full_decoded_mp4_count"] == len(decoder) == 2
    expected = [matrix.policy_ticks(plan, case) for case in plan["selections"]]
    assert [case["policy_ticks"] for case in value["cases"]] == expected
    assert value["total_policy_ticks"] == sum(expected) == (554 if plan.get("reference_commands") else 1000)
    assert value["quality_verified"] is value["obstacle_course_completion_verified"] is False
    assert scripts_before == {path.relative_to(args.matrix_module.parent) for path in args.matrix_module.parent.rglob("*")}


def test_live_preview_never_becomes_full_completion_and_allows_live_matrix_updates(retained, decoder, monkeypatch):
    args, plan, report = retained
    report.update(status="running", configuration_coverage_complete=False, completed_configurations=1)
    matrix.write(args.matrix, report)
    args.preview_case_id = [plan["selections"][0]["case_id"]]
    original = finalizer.subprocess.run
    def live_update(argv, **kwargs):
        report["live_updated_unix"] = 1234.5
        matrix.write(args.matrix, report)
        return original(argv, **kwargs)
    monkeypatch.setattr(finalizer.subprocess, "run", live_update)
    value = finalizer.validate(args)
    assert value["status"] == "preview_validated" and value["preview"] is True
    assert value["completion_verified"] is False and value["configurations"] == 1
    assert value["planned_configurations"] == 2 and len(value["cases"]) == len(decoder) == 1


@pytest.mark.parametrize("fault", ("failed_case", "failed_attempt", "nonzero", "retry"))
def test_failed_or_retried_attempt_is_refused_even_in_preview(retained, decoder, fault):
    args, plan, report = retained
    case = report["selections"][0]
    if fault == "failed_case": case["status"] = "execution_failed"
    elif fault == "failed_attempt": case["attempts"][0]["status"] = "execution_failed"
    elif fault == "nonzero": case["attempts"][0]["returncode"] = 1
    else: case["attempts"].append(copy.deepcopy(case["attempts"][0]))
    matrix.write(args.matrix, report)
    args.preview_case_id = [case["case_id"]]
    with pytest.raises(ValueError, match="Exactly one"):
        finalizer.validate(args)
    assert not decoder
    failed_receipt(args)


@pytest.mark.parametrize("kind", ("source_matrix", "model", "dependency", "motion", "mesh"))
def test_changed_input_is_rejected_before_video_decoding(retained, decoder, kind):
    args, plan, _ = retained
    targets = {"source_matrix": plan["source_matrix_record"], "model": plan["models"][0],
               "dependency": plan["dependencies"][0], "motion": plan["selections"][0]["source_files"][0],
               "mesh": plan["selections"][0]["source_files"][2]}
    Path(targets[kind]["path"]).write_bytes(b"changed input")
    with pytest.raises(ValueError, match="input changed"):
        finalizer.validate(args)
    assert not decoder
    failed_receipt(args)


def test_changed_validator_source_is_rejected_before_executing_it(retained, decoder):
    args, _, _ = retained
    sentinel = args.output.with_name("untrusted-module-executed")
    args.matrix_module.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
    with pytest.raises(ValueError, match="frozen planned dependency"):
        finalizer.validate(args)
    assert not sentinel.exists() and not decoder
    failed_receipt(args)


@pytest.mark.parametrize("fault", ("corrupt_before", "ffmpeg_nonzero", "timeout", "change_during_decode", "change_before_fingerprint"))
def test_original_video_integrity_and_full_decoder_failures_are_preserved(retained, decoder, monkeypatch, fault):
    args, _, report = retained
    directory = Path(report["selections"][0]["attempts"][0]["output"])
    video = directory / "video/rollout.mp4"
    if fault == "corrupt_before": video.write_bytes(b"damaged original video")
    elif fault == "change_before_fingerprint":
        original = finalizer.fingerprint
        changed = False
        def replace_after_seal_check(path):
            nonlocal changed
            if Path(path) == video and not changed:
                video.write_bytes(b"different stable video after original seal validation")
                changed = True
            return original(path)
        monkeypatch.setattr(finalizer, "fingerprint", replace_after_seal_check)
    else:
        original = finalizer.subprocess.run
        def fail_decode(argv, **kwargs):
            value = original(argv, **kwargs)
            if fault == "ffmpeg_nonzero": return SimpleNamespace(returncode=1, stderr="corrupt video fixture", stdout="")
            if fault == "timeout": raise subprocess.TimeoutExpired(argv, 120)
            video.write_bytes(b"video changed during decoding")
            return value
        monkeypatch.setattr(finalizer.subprocess, "run", fail_decode)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        finalizer.validate(args)
    value = failed_receipt(args)
    if fault == "ffmpeg_nonzero":
        assert value["failed_video"]["returncode"] == 1 and value["failed_video"]["full_decode"] is False
        assert "corrupt video fixture" in value["failed_video"]["stderr"]
    if fault in ("corrupt_before", "change_before_fingerprint"):
        assert not decoder


@pytest.mark.parametrize("target", ("model", "plan", "matrix", "native_result"))
def test_changes_during_decoding_cannot_produce_full_completion(retained, decoder, monkeypatch, target):
    args, plan, report = retained
    original = finalizer.subprocess.run
    changed = False
    def mutate(argv, **kwargs):
        nonlocal changed
        value = original(argv, **kwargs)
        if not changed:
            path = {"model": Path(plan["models"][0]["path"]), "plan": args.plan, "matrix": args.matrix,
                    "native_result": Path(report["selections"][0]["attempts"][0]["output"]) / "result.json"}[target]
            path.write_bytes(path.read_bytes() + b"\n")
            changed = True
        return value
    monkeypatch.setattr(finalizer.subprocess, "run", mutate)
    with pytest.raises(ValueError):
        finalizer.validate(args)
    failed_receipt(args)


@pytest.mark.parametrize("location", ("existing", "inside_native"))
def test_validation_never_overwrites_or_writes_inside_native_evidence(retained, decoder, location):
    args, _, _ = retained
    if location == "existing":
        args.output.write_bytes(b"previous failure retained verbatim")
        before = args.output.read_bytes()
    else:
        args.output = args.matrix.parent / "invalid-new-output.json"
    with pytest.raises(ValueError, match="Fresh|outside"):
        finalizer.validate(args)
    if location == "existing": assert args.output.read_bytes() == before
    else: assert not args.output.exists()
    assert not decoder
