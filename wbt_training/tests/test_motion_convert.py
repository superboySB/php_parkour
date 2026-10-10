"""Real converter regressions; requires only NumPy and the standard library."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from wbt_training.training_runs.motion_convert import convert


def source(path: Path, frames: int = 3, dofs: int = 29) -> None:
    np.savez(path, fps=np.array([50]), joint_pos=np.zeros((frames, dofs)), joint_vel=np.zeros((frames, dofs)),
             body_pos_w=np.zeros((frames, 30, 3)), body_quat_w=np.tile([1.0, 0.0, 0.0, 0.0], (frames, 30, 1)),
             body_lin_vel_w=np.zeros((frames, 30, 3)), body_ang_vel_w=np.zeros((frames, 30, 3)))


def test_native_input_is_rejected_without_overwriting_output(tmp_path):
    input_file, output = tmp_path / "already-native.npz", tmp_path / "output.npz"
    source(input_file, dofs=36)
    with pytest.raises(ValueError, match="already converted"):
        convert(str(input_file), str(output))
    assert not output.exists()


def test_single_frame_cli_does_not_claim_success(tmp_path):
    input_file, output = tmp_path / "short.npz", tmp_path / "output.npz"
    source(input_file, frames=1)
    result = subprocess.run([sys.executable, "-m", "wbt_training.training_runs.motion_convert", str(input_file), str(output)],
                            text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "at least two frames" in result.stderr
    assert "Converted" not in result.stdout
    assert not output.exists()


def test_nonfinite_source_is_rejected(tmp_path):
    input_file, output = tmp_path / "invalid.npz", tmp_path / "output.npz"
    source(input_file)
    with np.load(input_file) as data:
        values = {key: data[key] for key in data.files}
    values["body_pos_w"][1, 0, 0] = np.nan
    np.savez(input_file, **values)
    with pytest.raises(ValueError, match="finite"):
        convert(str(input_file), str(output))
    assert not output.exists()
