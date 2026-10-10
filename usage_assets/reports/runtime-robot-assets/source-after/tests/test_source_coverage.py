"""Exercise the actual three native CPU eval loops and callback instantiation.

The small environment is a control-flow fixture, with no physical simulator.
BaseTask.reset_all and BaseTask.step are real, so both warmup calls and action
interfaces come from upstream; these tests do not establish skill success.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
from holosoma.agents.ppo.ppo import PPO
from holosoma.agents.distillation.distillation import Distillation
from holosoma.agents.distillation_ppo.distillation_ppo import DistillationPPO
from holosoma.envs.base_task.base_task import BaseTask
from scripts.research import source_coverage_probe as coverage
from scripts.research import runtime_robot_assets as robot_assets


def asset_fixture(tmp_path):
    source = tmp_path / "robot-source"
    urdf = source / robot_assets.PRIMARY_URDF
    urdf.parent.mkdir(parents=True, exist_ok=True)
    urdf.write_text('<robot name="fixture"><link name="body"/></robot>')
    value = robot_assets.contract(source, tmp_path / "runtime-robot-assets/robots")
    robot_assets.prepare(value)
    return value


class CPUEnv:
    reset_all = BaseTask.reset_all
    step = BaseTask.step
    num_envs, dim_actions, device, dt = 1, 29, "cpu", .02

    def __init__(self, outcome, frames=4):
        self.outcome, self.physical_steps, self.reset_calls, self.log_calls = outcome, 0, 0, 0
        self.command = SimpleNamespace(time_steps=torch.zeros(1, dtype=torch.long), motion_ids=torch.zeros(1, dtype=torch.long),
            motion_end_reset=torch.zeros(1, dtype=torch.bool), motion=SimpleNamespace(
                num_motions=1, time_step_total=frames, motion_ends=torch.tensor([False] * (frames - 1) + [True]),
                motion_idxs=torch.zeros(frames, dtype=torch.long)), motion_cfg=SimpleNamespace(
                freeze_at_timestep_zero_prob=0., resample_on_motion_end=True, enable_default_pose_prepend=False,
                enable_default_pose_append=False, default_pose_transition_strategy="none", body_names_to_track=["body"]))
        self.command._env = self
        self.command.robot_root_pos_w = self.command.robot_ref_pos_w = self.command.ref_pos_w = torch.tensor([[0.,0.,.7]])
        self.command.robot_root_quat_w = self.command.robot_ref_quat_w = self.command.ref_quat_w = torch.tensor([[0.,0.,0.,1.]])
        self.command.body_pos_w = torch.tensor([[[0.,0.,.7]]])
        self.command.body_quat_w = torch.tensor([[[0.,0.,0.,1.]]])
        self.command.body_pos_relative_w = torch.zeros(1,1,3)
        self.command.body_quat_relative_w = torch.zeros(1,1,4)
        self.command_manager = SimpleNamespace(get_state=lambda name: self.command)
        self.termination_manager = SimpleNamespace(terminated=torch.zeros(1, dtype=torch.bool), time_outs=torch.zeros(1, dtype=torch.bool))
        self.episode_length_buf = torch.zeros(1, dtype=torch.long)
        self.simulator = SimpleNamespace(robot_root_states=torch.tensor([[0., 0., .7, 0., 0., 0., 1.]]), dof_state=torch.zeros(1,29,2),
            set_actor_root_state_tensor_robots=lambda *args: None, set_dof_state_tensor_robots=lambda *args: None)
        self.obs_buf_dict = {"actor_obs": torch.zeros(1,108), "critic_obs": torch.zeros(1,575),
                             "teacher_obs": torch.zeros(1,450), "depth_camera": {"depth_cam": torch.zeros(1,58,87)}}
        self.rew_buf, self.reset_buf, self.extras = torch.zeros(1), torch.zeros(1,dtype=torch.bool), {}
        self.log_dict = {key: torch.ones(1) * .1 for key in coverage.METRICS}

    def set_is_evaluating(self):
        self.is_evaluating = True

    def reset_envs_idx(self, env_ids):
        self.reset_calls += 1
        self.command.time_steps.zero_()
        self.episode_length_buf.zero_()
        self.termination_manager.terminated.zero_()
        self.termination_manager.time_outs.zero_()

    def _pre_physics_step(self, actions):
        self.last_actions = actions.clone()

    def _physics_step(self):
        self.physical_steps += 1
        if self.outcome == "initial_exception" and self.physical_steps == 1:
            raise RuntimeError("deliberate CPU physics fixture error")

    def _update_log_dict(self):
        self.log_calls += 1

    def _post_physics_step(self):
        self.episode_length_buf += 1
        failed = (self.outcome in ("warmup_failed", "warmup_both") and self.physical_steps == 2) or (self.outcome == "failed_boundary" and self.physical_steps == 3)
        timeout = (self.outcome in ("warmup_timeout", "warmup_both") and self.physical_steps == 2) or (self.outcome == "policy_timeout" and self.physical_steps == 3)
        self.termination_manager.terminated.fill_(failed)
        self.termination_manager.time_outs.fill_(timeout)
        if self.outcome == "nonfinite" and self.physical_steps == 3:
            self.log_dict["motion/error_ref_pos"].fill_(float("nan"))
        self._update_log_dict()  # Actual probe must copy flags/errors here.
        if failed or timeout:
            self.reset_envs_idx(torch.tensor([0]))
        self.command.time_steps += 1
        boundary = self.command.time_steps.item() == self.command.motion.time_step_total - 1
        self.command.motion_end_reset.fill_(boundary or (self.outcome == "failed_boundary" and failed))
        if boundary:
            self.command.time_steps.zero_()


def native_fixture(tmp_path, cls, outcome="boundary", frames=4):
    checkpoint = tmp_path / "model.pt"
    torch.save({"iter": 500}, checkpoint)
    value = asset_fixture(tmp_path)
    case = {"schema_version": 2, "runtime_robot_assets": value,
            "output": str(tmp_path), "source": {"frames": frames, "fps": 50, "expert_ordinal": 2},
            "case_id": "cpu-test", "inventory_sha256": "inventory", "checkpoint": str(checkpoint), "native_argv": []}
    env = CPUEnv(outcome, frames)
    env.robot_config = SimpleNamespace(asset=SimpleNamespace(asset_root=value["runtime_root"],
        urdf_file=value["urdf_file"], usd_file=None))
    loop = SimpleNamespace(device="cpu", num_act=29, env=env, actor_obs_keys=["actor_obs"], critic_obs_keys=["critic_obs"],
                           eval_callbacks=[], log_dir=str(tmp_path / "unused-log"), current_learning_iteration=500,
                           config=SimpleNamespace(eval_callbacks={"coverage": SimpleNamespace(
                               _target_="scripts.research.source_coverage_probe.SourceCoverageProbe", config={"case": case})}))
    for name in ("_create_eval_callbacks", "_pre_evaluate_policy", "_post_evaluate_policy", "_pre_eval_env_step", "_post_eval_env_step", "env_step"):
        setattr(loop, name, MethodType(getattr(cls, name), loop))
    if cls is PPO:
        loop._create_actor_state = MethodType(cls._create_actor_state, loop)
    else:
        loop._extract_groups = MethodType(cls._extract_groups, loop)
    loop._eval_mode = lambda: None
    loop.get_inference_policy = lambda: lambda obs: torch.ones(1,29) * .2
    return loop


@pytest.mark.parametrize("cls", (PPO, Distillation, DistillationPPO))
@pytest.mark.parametrize("outcome,reason,steps", (("boundary", "native_boundary", 2),
    ("warmup_failed", "failed_during_native_warmup", 0), ("warmup_timeout", "timeout_during_native_warmup", 0),
    ("warmup_both", "failed_during_native_warmup", 0), ("failed_boundary", "failed", 1), ("policy_timeout", "timeout", 1)))
def test_real_native_loop_stops_first_attempt_and_restores_hooks(tmp_path, cls, outcome, reason, steps):
    loop = native_fixture(tmp_path, cls, outcome)
    original_step, original_log = loop.env.step, loop.env._update_log_dict
    coverage.guarded_evaluate(loop, cls.evaluate_policy, 99)
    report = json.loads((tmp_path / "quality.json").read_text())
    assert report["status"] == "completed" and report["stop_reason"] == reason
    assert report["control_steps"] == steps
    assert loop.env.physical_steps == steps + 2
    assert loop.eval_callbacks[0].finalized
    assert loop.env.step == original_step and loop.env._update_log_dict == original_log
    assert report["initialization_steps"] == 1 and report["attempt_warmup_steps"] == 1
    assert report["attempt_warmup_events"][0]["reference_frame"] == 0
    assert report["policy_reference_frames"] == list(range(1, steps + 1))
    assert report["first_attempt_reference_boundary_reached"] is (outcome == "boundary")
    assert all(metric["samples"] == steps and metric["finite"] is (True if steps else None) for metric in report["metrics"].values())
    assert report["quality_verified"] is False
    assert report["warmup_cache_repair"]["enabled"] is True
    assert len(report["warmup_cache_repair"]["events"]) == 2
    assert all(event["clock_unchanged"] and event["rng_unchanged"] for event in report["warmup_cache_repair"]["events"])
    if outcome == "warmup_both":
        assert report["failed_resets"] == report["timeout_resets"] == 1
    if outcome == "failed_boundary":
        assert report["first_event"]["failed"] and report["first_event"]["motion_end_reset"]


@pytest.mark.parametrize("cls", (PPO, Distillation, DistillationPPO))
def test_actual_max_step_bound_is_partial_coverage(tmp_path, cls):
    loop = native_fixture(tmp_path, cls, frames=10)
    coverage.guarded_evaluate(loop, cls.evaluate_policy, 2)
    report = json.loads((tmp_path / "quality.json").read_text())
    assert report["stop_reason"] == "max_steps" and report["control_steps"] == 2
    assert report["policy_reference_frames"] == [1,2]
    assert report["missing_policy_reference_frames"] == list(range(3,9))
    assert report["first_attempt_reference_boundary_reached"] is False


@pytest.mark.parametrize("outcome", ("initial_exception", "nonfinite"))
def test_unexpected_native_error_keeps_partial_report_and_propagates(tmp_path, outcome):
    loop = native_fixture(tmp_path, PPO, outcome)
    original_step = loop.env.step
    with pytest.raises((RuntimeError, ValueError)):
        coverage.guarded_evaluate(loop, PPO.evaluate_policy, 99)
    report = json.loads((tmp_path / "quality.json").read_text())
    assert report["status"] == "execution_failed" and report["execution_error"]
    assert loop.env.step == original_step and loop.eval_callbacks[0].finalized
    if outcome == "initial_exception":
        assert report["control_steps"] == 0
        assert report["trajectory"]["bytes"] == 0
        assert report["finite_actions"] is None
    else:
        assert report["metrics"]["motion/error_ref_pos"]["finite"] is False


def test_case_identity_and_byte_changes_are_refused(tmp_path):
    checkpoint, asset = tmp_path / "model.pt", tmp_path / "source.npz"
    checkpoint.write_bytes(b"checkpoint")
    asset.write_bytes(b"asset")
    provenance = {"record": {"source_clip_id": "source", "expert_ordinal": 1}, "registry_uri": (tmp_path / "bundle").as_uri(),
                  "original_expert_ordinal": 1, "singleton_native_expert_ordinal": 0,
                  "files": [{"path": str(asset), "sha256": coverage.sha256(asset)}]}
    path = tmp_path / "provenance.json"
    coverage.atomic_json(path, provenance)
    case = {"schema_version": 2, "runtime_robot_assets": asset_fixture(tmp_path),
            "checkpoint": str(checkpoint), "checkpoint_sha256": coverage.sha256(checkpoint),
            "singleton_provenance": str(path), "singleton_provenance_sha256": coverage.sha256(path),
            "source": provenance["record"], "registry_uri": provenance["registry_uri"],
            "original_expert_ordinal": 1, "singleton_native_expert_ordinal": 0}
    coverage.verify_case(case)
    for field, value in (("source", {"source_clip_id": "other", "expert_ordinal": 1}), ("registry_uri", "file:///other"), ("original_expert_ordinal", 0)):
        altered = copy.deepcopy(case)
        altered[field] = value
        with pytest.raises(ValueError, match="identity"):
            coverage.verify_case(altered)
    asset.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="asset changed"):
        coverage.verify_case(case)
    coverage.atomic_json(path, {**provenance, "original_expert_ordinal": 3})
    with pytest.raises(ValueError, match="provenance changed"):
        coverage.verify_case(case)


def test_wrong_control_frequency_fails_before_installing_hooks(tmp_path):
    loop = native_fixture(tmp_path, PPO)
    loop.env.dt = .01
    original_step = loop.env.step
    with pytest.raises(ValueError, match="FPS"):
        PPO._create_eval_callbacks(loop)
    assert loop.env.step == original_step


@pytest.mark.parametrize("change", ("missing_tensorboard", "missing_yaml", "changed_motion", "wrong_robot_config", "wrong_robot_contract"))
def test_report_validation_requires_retained_native_evidence(tmp_path, change):
    from scripts.research.eval_source_coverage import validate_native_report
    loop = native_fixture(tmp_path, PPO)
    coverage.guarded_evaluate(loop, PPO.evaluate_policy, 99)
    report = json.loads((tmp_path / "quality.json").read_text())
    case = loop.eval_callbacks[0].case
    case["checkpoint_sha256"] = coverage.sha256(case["checkpoint"])
    report["actual_native"]["source_table_verification"] = {"status": "matched_selected_source"}
    for name in ("motion", "terrain_obj", "saved_eval_config"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        report["actual_native"][name] = {"retained": coverage.fingerprint(path)}
    video = tmp_path / "video-evidence-placeholder.mp4"
    video.write_bytes(b"This test verifies evidence hashes only, not video decoding.")
    report["videos"] = [{**coverage.fingerprint(video), "duration_seconds": 1.0}]
    validate_native_report(report, case)
    if change == "missing_tensorboard":
        report["tensorboard_events"] = []
    elif change == "missing_yaml":
        Path(report["actual_native"]["saved_eval_config"]["retained"]["path"]).unlink()
    elif change == "wrong_robot_config":
        report["actual_native"]["robot_asset_config"]["asset_root"] = case["runtime_robot_assets"]["source_root"]
    elif change == "wrong_robot_contract":
        report["runtime_robot_assets"] = {**report["runtime_robot_assets"], "runtime_root": "/wrong/runtime-robot-assets/robots"}
    else:
        Path(report["actual_native"]["motion"]["retained"]["path"]).write_bytes(b"changed")
    with pytest.raises((ValueError, OSError)):
        validate_native_report(report, case)


def test_malformed_child_report_records_terminal_failure(tmp_path, monkeypatch):
    # Fault injection into orchestration only; native callback APIs are
    # exercised without mocking in the 25 loop tests above.
    from scripts.research import eval_source_coverage as orchestrator
    case = {"case_id": "case", "output": str(tmp_path), "source": {"source_clip_id": "source"}}
    case_path = tmp_path / "case.json"
    coverage.atomic_json(case_path, case)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    (tmp_path / "quality.json").write_text("{broken JSON")
    # Remove the input quality just before the evidence-overwrite gate, then
    # have the fake child create malformed output. No simulator is requested.
    (tmp_path / "quality.json").unlink()
    monkeypatch.setattr(orchestrator, "verify_plan", lambda path: {"cases": [{"case_id": "case", "case": {"path": str(case_path)}}]})
    def child(*args, **kwargs):
        (tmp_path / "quality.json").write_text("{broken JSON")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(orchestrator.subprocess, "run", child)
    result, code = orchestrator.execute(SimpleNamespace(plan=plan_path, case_id=[], action="run"))
    summary = json.loads((tmp_path / "native-first-attempt-summary.json").read_text())
    assert code == 1 and result["status"] == summary["status"] == "execution_failed"
    assert summary["cases"][0]["evidence_error"].startswith("JSONDecodeError")


def test_retained_private_tempfile_keeps_bytes_and_is_host_readable(tmp_path):
    source, retained = tmp_path / "private-terrain.obj", tmp_path / "retained-terrain.obj"
    source.write_bytes(b"temporary mesh bytes")
    source.chmod(0o600)
    coverage.retain_file(source, retained)
    assert coverage.sha256(retained) == coverage.sha256(source)
    assert retained.stat().st_mode & 0o777 == 0o644
    assert source.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("shift", ((0.,0.), (10.,-20.), (-100.,100.)))
def test_real_motion_command_alignment_parity_without_advancing_clock_or_rng(shift):
    from holosoma.managers.command.terms.wbt import MotionCommand
    from holosoma.managers.termination.terms.wbt import BadTracking
    command = object.__new__(MotionCommand)
    bodies = torch.tensor([[[0.,2.48,.7], [0.,2.48,.8], [.1,2.48,.2]]] * 5)
    bodies[:, :, :2] += torch.tensor(shift)
    bodies[:, :, 0] += torch.arange(5).float()[:,None] * .01
    quats = torch.tensor([[[0.,0.,0.,1.]] * 3] * 5)
    roots = torch.zeros(1,13)
    roots[:, :3], roots[:, 3:7] = bodies[0,0], quats[0,0]
    command._env = SimpleNamespace(episode_length_buf=torch.zeros(1,dtype=torch.long), is_evaluating=True,
        simulator=SimpleNamespace(scene=SimpleNamespace(env_origins=torch.zeros(1,3)), robot_root_states=roots,
                                  _rigid_body_pos=bodies[0:1].clone(), _rigid_body_rot=quats[0:1].clone()))
    command.num_envs, command.device = 1, "cpu"
    command.motion_cfg = SimpleNamespace(body_names_to_track=["root","ref","foot"], use_adaptive_timesteps_sampler=False,
                                        freeze_at_timestep_zero_prob=0., resample_on_motion_end=True)
    command.motion = SimpleNamespace(_body_pos_w=bodies, _body_quat_w=quats,
        motion_ends=torch.tensor([False,False,False,False,True]), time_step_total=5, motion_start_idx=torch.tensor([0]))
    command._tracked_body_indexes_in_motion = command.tracked_body_indexes = torch.arange(3)
    command._ref_body_index_in_motion = command.ref_body_index = 1
    command._root_body_index_in_motion = 0
    command.init_buffers()
    termination = object.__new__(BadTracking)
    termination.bad_motion_body_pos_body_indexes = torch.arange(3)
    termination.bad_motion_body_pos_threshold = .5
    assert termination.bad_motion_body_pos(command).item()
    event = coverage.refresh_relative_targets(command)
    assert not termination.bad_motion_body_pos(command).item()
    assert event["clock_before"] == event["clock_after"]
    assert event["rng_sha256_before"] == event["rng_sha256_after"]
    assert command.time_steps.item() == 0
    command.step()  # Actual upstream advances naturally to reference1.
    assert command.time_steps.item() == 1
    expected_pos, expected_quat = command.body_pos_relative_w.clone(), command.body_quat_relative_w.clone()
    command.body_pos_relative_w.zero_()
    command.body_quat_relative_w.zero_()
    coverage.refresh_relative_targets(command)  # Never rewind the source clock.
    assert command.time_steps.item() == 1
    assert torch.equal(command.body_pos_relative_w, expected_pos)
    assert torch.equal(command.body_quat_relative_w, expected_quat)
