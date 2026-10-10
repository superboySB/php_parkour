"""Use real CPU tensors to verify the probe reads flags BEFORE reset clears them."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

torch = pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eval_quality_test", ROOT / "scripts/research/eval_quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


def test_pre_reset_failed_timeout_are_separate_and_report_is_atomic(tmp_path, monkeypatch):
    from holosoma.utils.helpers import instantiate
    from holosoma.simulator.isaacsim.proxy_utils import RootStatesProxy
    flags = SimpleNamespace(terminated=torch.tensor([True, False, True]), time_outs=torch.tensor([False, True, True]))
    cmd = SimpleNamespace(motion_ids=torch.tensor([0, 1, 2]), time_steps=torch.tensor([0, 1, 2]),
                          motion=SimpleNamespace(motion_idxs=torch.tensor([0, 1, 1]), motion_end_idx=torch.arange(3)),
                          motion_end_reset=torch.tensor([False, True, True]))
    native_calls = []
    metrics = {key: torch.tensor([0.1, 0.2, 0.3]) for key in quality.METRICS}
    env = SimpleNamespace(num_envs=3, dt=0.02, termination_manager=flags, episode_length_buf=torch.tensor([5, 10, 20]),
                          command_manager=SimpleNamespace(get_state=lambda name: cmd), log_dict=metrics,
                          simulator=SimpleNamespace(robot_root_states=RootStatesProxy(torch.tensor([[0., 0., .7, 1., 0., 0., 0.]] * 3))),
                          _update_log_dict=lambda: native_calls.append("native log"),
                          training_config=SimpleNamespace(seed=42, registry_name="file:///first,file:///second"))
    checkpoint = tmp_path / "model.pt"
    torch.save({"iter": 1}, checkpoint)
    log_dir = tmp_path / "native-eval"
    log_dir.mkdir()
    (log_dir / "holosoma_config.yaml").write_text("seed: 42\n")
    loop = SimpleNamespace(env=env, log_dir=str(log_dir), current_learning_iteration=1)
    report = tmp_path / "quality.json"
    # Holosoma instantiate requires attribute configs (plain dict is rejected).
    module_name = "eval_quality_test"
    import sys
    monkeypatch.setitem(sys.modules, module_name, quality)
    callback = instantiate(SimpleNamespace(_target_=f"{module_name}.QualityProbe", config={"output": str(report), "checkpoint": str(checkpoint), "argv": []}), training_loop=loop)
    callback.on_pre_evaluate_policy()
    original = callback.original_log
    env._update_log_dict()  # Native reset_all warmup must not count as rollout.
    callback.on_pre_eval_env_step({"step": 0})
    env._update_log_dict()
    flags.terminated.zero_()
    flags.time_outs.zero_()
    metrics["motion/error_ref_pos"].zero_()  # In-place reset must not change captured errors.
    callback.on_post_eval_env_step({"actions": torch.ones(3, 29)})
    callback.on_post_evaluate_policy()
    data = json.loads(report.read_text())
    assert native_calls == ["native log", "native log"]
    assert env._update_log_dict is original
    assert data["failed_resets"] == 2 and data["timeout_resets"] == 2
    assert data["first_failure_sim_seconds_by_env"] == [0.02, None, 0.02]
    assert data["clip_completions_excluding_failed_timeout_steps"] == 0
    assert data["metrics"]["motion/error_ref_pos"]["mean"] == pytest.approx(.2)
    assert data["resets_by_expert"]["1"] == {"failed_resets": 1, "timeout_resets": 2, "env_steps": 2}
    assert data["registry_order"] == ["file:///first", "file:///second"]
    assert data["sim_seconds_per_env"] == .02 and data["total_env_seconds"] == .06
    assert data["quality_verified"] is False
    assert data["tensorboard_events"] and all(Path(path).is_file() for path in data["tensorboard_events"])
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_report_rejects_nonfinite_json(tmp_path):
    report = tmp_path / "quality.json"
    quality.atomic_json(report, {"status": "old-complete"})
    with pytest.raises(ValueError):
        quality.atomic_json(report, {"error": float("nan")})
    assert json.loads(report.read_text()) == {"status": "old-complete"}


def prepare_native_main(tmp_path, monkeypatch, native):
    from holosoma.config_types.eval_callback import EvalCallbacksConfig
    checkpoint = tmp_path / "original.pt"
    checkpoint.write_bytes(b"opaque checkpoint; no mock physics or model load")
    report = tmp_path / "quality.json"
    argv = ["eval_quality", "teacher", "--quality-output", str(report), "--checkpoint", str(checkpoint)]
    monkeypatch.setattr(sys, "argv", argv)
    original = EvalCallbacksConfig.collect_active_callbacks
    monkeypatch.setattr(quality.importlib, "import_module", lambda name: SimpleNamespace(main=lambda: native(checkpoint, report)))
    return checkpoint, report, argv, EvalCallbacksConfig, original


def valid_main_report(checkpoint):
    return {"schema_version": 1, "status": "completed", "checkpoint": str(checkpoint),
            "checkpoint_sha256": quality.sha256(checkpoint), "control_steps": 100, "num_envs": 16,
            "finite_actions": True, "finite_root_states": True}


def test_native_return_without_rollout_report_is_nonzero_failure(tmp_path, monkeypatch):
    _, report, argv, callbacks, original = prepare_native_main(tmp_path, monkeypatch, lambda *_: None)
    with pytest.raises(RuntimeError, match="without a fresh quality report"):
        quality.main()
    assert not report.exists()
    assert callbacks.collect_active_callbacks is original and sys.argv is argv


def test_existing_quality_report_is_preserved_and_never_reused(tmp_path, monkeypatch):
    calls = []
    _, report, _, callbacks, original = prepare_native_main(tmp_path, monkeypatch, lambda *_: calls.append(1))
    report.write_bytes(b"historical raw evidence\n")
    with pytest.raises(SystemExit) as error:
        quality.main()
    assert error.value.code == 2 and not calls
    assert report.read_bytes() == b"historical raw evidence\n" and callbacks.collect_active_callbacks is original


@pytest.mark.parametrize("field,value", [("checkpoint_sha256", "0" * 64), ("control_steps", 0),
    ("control_steps", True), ("num_envs", 0), ("finite_actions", False), ("finite_root_states", False),
    ("checkpoint", "/different/model.pt"), ("status", "running")])
def test_fresh_but_invalid_rollout_report_does_not_pass(tmp_path, monkeypatch, field, value):
    def native(checkpoint, report):
        data = valid_main_report(checkpoint)
        data[field] = value
        report.write_text(json.dumps(data))
    _, report, argv, callbacks, original = prepare_native_main(tmp_path, monkeypatch, native)
    with pytest.raises(RuntimeError, match="does not prove a finite rollout"):
        quality.main()
    assert report.is_file() and callbacks.collect_active_callbacks is original and sys.argv is argv


def test_checkpoint_mutation_after_native_return_is_rejected(tmp_path, monkeypatch):
    def native(checkpoint, report):
        report.write_text(json.dumps(valid_main_report(checkpoint)))
        checkpoint.write_bytes(b"changed checkpoint")
    prepare_native_main(tmp_path, monkeypatch, native)
    with pytest.raises(RuntimeError, match="does not prove a finite rollout"):
        quality.main()


def test_fresh_finite_rollout_accepts_failed_resets_without_claiming_skill_quality(tmp_path, monkeypatch):
    def native(checkpoint, report):
        data = valid_main_report(checkpoint)
        data.update(failed_resets=900, quality_verified=False)
        report.write_text(json.dumps(data))
    _, report, argv, callbacks, original = prepare_native_main(tmp_path, monkeypatch, native)
    quality.main()
    assert callbacks.collect_active_callbacks is original and sys.argv is argv
    assert json.loads(report.read_text())["quality_verified"] is False
