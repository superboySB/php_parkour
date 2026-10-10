"""Local bundle ordering and terrain regeneration without simulator services."""

import dataclasses
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from holosoma.utils.eval_utils import CheckpointConfig

from wbt_training.config_values.experiment import g1_wbt_terrain_warp_distill_finetune
from wbt_training.utils import multi_motion_helpers
from wbt_training.utils.checkpoint import (
    apply_preprocess_hook,
    load_saved_experiment_config,
)


def write_bundle(root, label, motion_values):
    bundle = root / label
    bundle.mkdir()
    # Create files out of lexical order to exercise stable discovery.
    for name, value in reversed(list(motion_values.items())):
        data = {
            "fps": np.array(50),
            "joint_pos": np.full((3, 2), value, dtype=np.float32),
            "joint_vel": np.zeros((3, 2), dtype=np.float32),
            "body_pos_w": np.array(
                [[[0, 0, 0.7]], [[1, 0, 0.7]], [[2, 0, 0.7]]], dtype=np.float32
            ),
            "body_quat_w": np.tile([1, 0, 0, 0], (3, 1, 1)).astype(np.float32),
            "body_lin_vel_w": np.zeros((3, 1, 3), dtype=np.float32),
            "body_ang_vel_w": np.zeros((3, 1, 3), dtype=np.float32),
            "vel_cmd": np.tile(np.eye(15, dtype=np.float32)[value % 15], (3, 1)),
            "joint_names": np.array(["left", "right"]),
            "body_names": np.array(["pelvis"]),
        }
        np.savez(bundle / f"motion_{name}.npz", **data)
        obstacles = np.array(
            [[[value, 0, 0.3, 1, 0, 0, 0, 0.6, 0.8, 0.6]]], dtype=np.float32
        )
        np.save(bundle / f"terrain_{name}.npy", obstacles)
    return bundle


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    path = tmp_path / "combined"
    path.mkdir()
    monkeypatch.setattr(multi_motion_helpers, "_TMP_DIR", path)
    return path


def test_import_does_not_allocate_scratch(monkeypatch):
    monkeypatch.setattr(
        multi_motion_helpers.tempfile,
        "mkdtemp",
        lambda **_: pytest.fail("Import allocated scratch"),
    )
    importlib.reload(multi_motion_helpers)
    assert multi_motion_helpers._TMP_DIR is None


def test_local_bundle_order_and_pair_boundaries(tmp_path, scratch, monkeypatch):
    import wandb

    monkeypatch.setattr(
        wandb, "Api", lambda **_: pytest.fail("Local bundles requested W&B")
    )
    first = write_bundle(tmp_path, "z_first", {"02": 2, "01": 1})
    second = write_bundle(tmp_path, "a_second", {"01": 8})
    counts, motion_file, terrain_file, obj_files = (
        multi_motion_helpers.pull_paired_from_wandb_registry(
            f"file://{first},file://{second}"
        )
    )
    assert counts == [2, 1]
    assert obj_files == []
    with np.load(motion_file) as motion:
        np.testing.assert_array_equal(
            motion["joint_pos"][:, 0], [1] * 3 + [2] * 3 + [8] * 3
        )
        np.testing.assert_array_equal(motion["motion_idxs"], [0] * 6 + [1] * 3)
        np.testing.assert_array_equal(motion["motion_ends"], [False, False, True] * 3)
        np.testing.assert_array_equal(motion["joint_names"], ["left", "right"])
    with np.load(terrain_file) as terrain:
        np.testing.assert_array_equal(terrain["obj_count_list"], [0, 1, 2, 3])
        np.testing.assert_array_equal(terrain["obj_list"][:, 0, 0], [1, 2, 8])


def test_saved_config_regenerates_local_terrain_and_depth_assets(
    tmp_path, scratch, monkeypatch
):
    import wandb

    monkeypatch.setattr(
        wandb, "Api", lambda **_: pytest.fail("Local preprocessing requested W&B")
    )
    first = write_bundle(tmp_path, "z_first", {"01": 1})
    second = write_bundle(tmp_path, "a_second", {"01": 8})
    preset = g1_wbt_terrain_warp_distill_finetune
    saved_dict = preset.to_serializable_dict()
    saved_dict["terrain"]["terrain_term"]["obj_file_path"] = "/missing/training.obj"
    depth_terms = saved_dict["observation"]["groups"]["depth_camera"]["terms"]
    for term in depth_terms.values():
        term["params"]["terrain_mesh_vertices"] = "/missing/training_depth.npz"
        term["params"]["terrain_mesh_faces"] = "/missing/training_depth.npz"
    checkpoint_path = tmp_path / "model_12345.pt"
    torch.save({"experiment_config": saved_dict}, checkpoint_path)
    saved, _ = load_saved_experiment_config(
        CheckpointConfig(checkpoint=str(checkpoint_path))
    )
    config = dataclasses.replace(
        saved,
        training=dataclasses.replace(
            saved.training,
            registry_name=f"file://{first},file://{second}",
            num_envs=2,
            preprocess_hook_kwargs=json.dumps(
                {"add_onpath_obstacle": True, "num_variants": 2, "obstacle_seed": 7}
            ),
        ),
    )
    processed = apply_preprocess_hook(config)
    terrain_path = Path(processed.terrain.terrain_term.obj_file_path)
    assert terrain_path.is_file()
    assert processed.scene.env_spacing == 0.0
    motion_cfg = processed.command.setup_terms["motion_command"].params["motion_config"]
    motion_path = (
        motion_cfg["motion_file"]
        if isinstance(motion_cfg, dict)
        else motion_cfg.motion_file
    )
    with np.load(motion_path) as motion:
        # Every variant retains the ordered teacher-to-bundle assignment.
        np.testing.assert_array_equal(motion["motion_idxs"], ([0] * 3 + [1] * 3) * 2)
        np.testing.assert_array_equal(
            motion["joint_pos"][:, 0], ([1] * 3 + [8] * 3) * 2
        )
        assert motion["body_pos_w"].shape == (12, 1, 3)
    mesh_paths = set()
    for term in processed.observation.groups["depth_camera"].terms.values():
        mesh_path = Path(term.params["terrain_mesh_vertices"])
        mesh_paths.add(mesh_path)
        assert str(mesh_path) == term.params["terrain_mesh_faces"]
        with np.load(mesh_path) as mesh:
            assert mesh["vertices"].shape[1] == mesh["faces"].shape[1] == 3
            assert len(mesh["faces"]) > 0
    assert saved.terrain.terrain_term.obj_file_path == "/missing/training.obj"
    for term in saved.observation.groups["depth_camera"].terms.values():
        assert term.params["terrain_mesh_vertices"] == "/missing/training_depth.npz"
    # The config hook creates named scratch files; remove only this test's outputs.
    terrain_path.unlink()
    for path in mesh_paths:
        path.unlink()


@pytest.mark.parametrize("explicit_seed", [None, 7])
def test_obstacle_generation_honors_recorded_seed_despite_global_rng_state(
    tmp_path, scratch, explicit_seed
):
    from wbt_training.config_values.experiment import g1_wbt_terrain_ref_noscale

    bundle = write_bundle(tmp_path, "seeded", {"01": 1, "02": 2})
    kwargs = {"add_onpath_obstacle": True, "num_variants": 2}
    if explicit_seed is not None:
        kwargs["obstacle_seed"] = explicit_seed
    config = dataclasses.replace(
        g1_wbt_terrain_ref_noscale,
        training=dataclasses.replace(
            g1_wbt_terrain_ref_noscale.training, seed=19,
            registry_name=bundle.as_uri(), num_envs=2,
            preprocess_hook_kwargs=json.dumps(kwargs),
        ),
    )
    outputs = []
    for global_seed in (100, 200):
        np.random.seed(global_seed)
        torch.manual_seed(global_seed)
        processed = apply_preprocess_hook(config)
        effective = json.loads(processed.training.preprocess_hook_kwargs)["obstacle_seed"]
        assert effective == (19 if explicit_seed is None else explicit_seed)
        path = Path(processed.terrain.terrain_term.obj_file_path)
        motion_config = processed.command.setup_terms["motion_command"].params["motion_config"]
        with np.load(motion_config["motion_file"] if isinstance(motion_config, dict) else motion_config.motion_file) as motion:
            arrays = {key: motion[key].copy() for key in motion.files}
        outputs.append((path.read_bytes(), arrays))
        path.unlink()
    assert outputs[0][0] == outputs[1][0]
    assert outputs[0][1].keys() == outputs[1][1].keys()
    for key in outputs[0][1]:
        np.testing.assert_array_equal(outputs[0][1][key], outputs[1][1][key])


def test_explicit_hook_seed_preserves_single_gpu_training_geometry(tmp_path, scratch):
    import shutil
    from wbt_training.utils.obstacle_helpers import add_onpath_obstacle_standalone

    bundle = write_bundle(tmp_path, "legacy-seed", {"01": 1, "02": 2})
    _, source, terrain, _ = multi_motion_helpers.pull_paired_from_wandb_registry(bundle.as_uri())
    copies = [tmp_path / "implicit.npz", tmp_path / "explicit.npz"]
    for path in copies:
        shutil.copyfile(source, path)
    outputs = []
    for path, seed in zip(copies, (None, 42), strict=True):
        # Holosoma's single-GPU training entry already seeds these before
        # preprocessing. Explicit seeding must preserve that sampled geometry.
        np.random.seed(42)
        torch.manual_seed(42)
        _, motion_path, mesh, _ = add_onpath_obstacle_standalone(2, str(path), str(terrain), seed)
        with np.load(motion_path) as archive:
            arrays = {key: archive[key].copy() for key in archive.files}
        outputs.append((mesh.vertices.copy(), mesh.faces.copy(), arrays))
    np.testing.assert_array_equal(outputs[0][0], outputs[1][0])
    np.testing.assert_array_equal(outputs[0][1], outputs[1][1])
    for key in outputs[0][2]:
        np.testing.assert_array_equal(outputs[0][2][key], outputs[1][2][key])
