"""Use real CPU tensors to verify the probe reads flags BEFORE reset clears them."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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
