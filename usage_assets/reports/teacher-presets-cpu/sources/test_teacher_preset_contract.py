"""Reject plausible but incorrect preset/export associations without a GPU."""
import copy

import pytest

from scripts.research.validate_teacher_presets import inspect_config


@pytest.fixture
def config():
    return {"observation": {"groups": {"actor_obs": {"terms": {"dof_pos": {"scale": 1.0}}}}},
            "command": {"setup_terms": {"motion_command": {"params": {"motion_config": {"body_name_ref": ["pelvis"]}}}}},
            "training": {"name": "teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion",
                         "registry_name": "file:///data/assets/motions-locomotion"},
            "robot": {"control": {"action_scale": .25, "action_scales_by_effort_limit_over_p_gain": True}},
            "algo": {"config": {"empirical_normalization": False, "module_dict": {"actor": {
                "type": "MLP", "input_dim": ["actor_obs"], "output_dim": [29],
                "layer_config": {"hidden_dims": [512, 256, 128], "activation": "ELU", "dropout_prob": 0., "use_layer_norm": False}}}}}}


def test_no_height_pelvis_has_its_own_contract(config):
    result = inspect_config("g1-wbt-terrain-no-heightscan-pelvis", config, 160)
    assert result["anchor"] == ["pelvis"] and result["height_scan"] is False


@pytest.mark.parametrize("fault", ["wrong_dimension", "oracle_added", "torso_anchor", "noscale_weights", "registry", "normalized_actor", "different_activation"])
def test_misassociated_or_unsupported_export_is_rejected(config, fault):
    value = copy.deepcopy(config)
    dim = 160
    if fault == "wrong_dimension": dim = 449
    elif fault == "oracle_added": value["observation"]["groups"]["actor_obs"]["terms"]["height_scan"] = {"scale": 1.}
    elif fault == "torso_anchor": value["command"]["setup_terms"]["motion_command"]["params"]["motion_config"]["body_name_ref"] = ["torso_link"]
    elif fault == "noscale_weights": value["robot"]["control"]["action_scale"] = 1.
    elif fault == "registry": value["training"]["registry_name"] = "file:///data/assets/motions-low-step"
    elif fault == "normalized_actor": value["algo"]["config"]["empirical_normalization"] = True
    else: value["algo"]["config"]["module_dict"]["actor"]["layer_config"]["activation"] = "ReLU"
    with pytest.raises(ValueError, match="Saved preset identity"):
        inspect_config("g1-wbt-terrain-no-heightscan-pelvis", value, dim)
