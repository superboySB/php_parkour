"""Reference labels must survive loading exactly and follow physics ticks."""
import hashlib
import json
import math

import numpy as np
import pytest

from scripts.research.reference_commands import load_reference_commands, reference_frame_for_step


def reference_arrays():
    commands = np.zeros((12, 15), dtype=np.float32)
    commands[np.arange(12), np.arange(12)] = 1
    positions = np.zeros((12, 30, 3), dtype=np.float32)
    positions[:, 0] = [1.25, -2.5, 0.8]
    quaternions = np.zeros((12, 30, 4), dtype=np.float32)
    quaternions[..., 0] = 1
    quaternions[:, 0] = [math.sqrt(0.5), 0, 0, math.sqrt(0.5)]
    return {"fps": np.array([50]), "vel_cmd": commands, "body_pos_w": positions, "body_quat_w": quaternions}


def test_exact_labels_file_identity_and_wxyz_root(tmp_path):
    path = tmp_path / "reference.npz"
    arrays = reference_arrays()
    np.savez(path, **arrays)
    result = load_reference_commands(path)
    assert result["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["frames"] == 12 and result["fps"] == 50
    assert result["codes"] == result["unique_codes"] == list(range(12))
    assert result["commands"] == arrays["vel_cmd"].tolist()
    assert result["root_xy"] == [1.25, -2.5]
    assert result["root_yaw"] == pytest.approx(math.pi / 2, abs=1e-6)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("fault", ["zero", "two_ones", "fractional", "nan", "unsupported_code", "wrong_width"])
def test_invalid_labels_are_rejected_without_argmax(tmp_path, fault):
    arrays = reference_arrays()
    if fault == "zero": arrays["vel_cmd"][0] = 0
    elif fault == "two_ones": arrays["vel_cmd"][0, 1] = 1
    elif fault == "fractional": arrays["vel_cmd"][0, :2] = [0.5, 0.5]
    elif fault == "nan": arrays["vel_cmd"][0, 0] = np.nan
    elif fault == "unsupported_code": arrays["vel_cmd"][0, [0, 12]] = [0, 1]
    else: arrays["vel_cmd"] = arrays["vel_cmd"][:, :14]
    path = tmp_path / "invalid.npz"
    np.savez(path, **arrays)
    with pytest.raises(ValueError, match="vel_cmd"):
        load_reference_commands(path)


@pytest.mark.parametrize("fault", ["fps", "missing_pose", "pose_frames", "zero_quaternion", "wrong_root_name"])
def test_reference_clock_and_root_contract_are_required(tmp_path, fault):
    arrays = reference_arrays()
    if fault == "fps": arrays["fps"] = np.array([50.1])
    elif fault == "missing_pose": del arrays["body_quat_w"]
    elif fault == "pose_frames": arrays["body_pos_w"] = arrays["body_pos_w"][:-1]
    elif fault == "zero_quaternion": arrays["body_quat_w"][0, 0] = 0
    else: arrays["body_names"] = np.array(["world"] + ["body"] * 29)
    path = tmp_path / "invalid.npz"
    np.savez(path, **arrays)
    with pytest.raises(ValueError):
        load_reference_commands(path)


def test_integer_clock_anchor_decimation_and_end():
    assert [reference_frame_for_step(step, 1003, 10, 3) for step in (1003, 1013, 1023, 1033, 1043)] == [0, 1, 2, 3, 3]
    assert reference_frame_for_step(10**20 + 20, 10**20, 10, 3) == 2
    for values in [(-1, 0, 10, 3), (0, -1, 10, 3), (0, 0, 0, 3), (0, 0, 10, 0),
                   (999, 1000, 10, 3), (1001, 1000, 10, 3), (0.0, 0, 10, 3), (False, 0, 10, 3)]:
        with pytest.raises(ValueError):
            reference_frame_for_step(*values)
