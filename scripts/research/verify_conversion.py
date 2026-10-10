#!/usr/bin/env python3
"""Execute both public motion-conversion CLI modes on real generated motion."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    import numpy as np
    from wbt_training.config_values.robot_config import G1_29DOF_JOINT_NAMES, G1_32BODY_NAMES, ISAACLAB_TO_MUJOCO_DOF
    from wbt_training.training_runs.motion_convert import OUT32_TO_BM30
    from wbt_training.utils.registry import validate_bundle

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="A real BeyondMimic NPZ from the motion workflow")
    parser.add_argument("--terrain", type=Path, help="Optional paired generated terrain NPY")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use an empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    source = args.source.resolve()
    commands = []

    def run(arguments: list[str], log: str) -> None:
        command = [sys.executable, "-m", *arguments]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        (output / log).write_text(result.stdout + result.stderr)
        commands.append({"command": command, "returncode": result.returncode, "log": log})
        if result.returncode:
            raise RuntimeError(f"Conversion command failed; see {output / log}")

    converted = output / "single" / "example_motion.npz"
    run(["wbt_training.training_runs.motion_convert", str(source), str(converted)], "single.log")
    directory = output / "directory-source"
    directory.mkdir()
    shutil.copy2(source, directory / "example_motion.npz")
    run(["wbt_training.training_runs.motion_convert", str(directory), str(output / "directory-output")], "directory.log")
    with np.load(source, allow_pickle=False) as src, np.load(converted, allow_pickle=False) as dst, np.load(output / "directory-output/example_motion.npz", allow_pickle=False) as second:
        assert set(dst.files) == set(second.files)
        for key in dst.files:
            np.testing.assert_array_equal(dst[key], second[key], err_msg=f"CLI modes disagree for {key}")
        np.testing.assert_array_equal(dst["joint_pos"][:, :3], src["body_pos_w"][:, 0])
        np.testing.assert_array_equal(dst["joint_pos"][:, 3:7], src["body_quat_w"][:, 0])
        np.testing.assert_array_equal(dst["joint_pos"][:, 7:], src["joint_pos"][:, ISAACLAB_TO_MUJOCO_DOF])
        np.testing.assert_array_equal(dst["joint_vel"][:, :3], src["body_lin_vel_w"][:, 0])
        np.testing.assert_array_equal(dst["joint_vel"][:, 3:6], src["body_ang_vel_w"][:, 0])
        np.testing.assert_array_equal(dst["joint_vel"][:, 6:], src["joint_vel"][:, ISAACLAB_TO_MUJOCO_DOF])
        for key in ("body_pos_w", "body_quat_w", "body_lin_vel_w", "body_ang_vel_w"):
            np.testing.assert_array_equal(dst[key], src[key][:, OUT32_TO_BM30])
        assert dst["joint_names"].tolist() == G1_29DOF_JOINT_NAMES
        assert dst["body_names"].tolist() == G1_32BODY_NAMES
        for key in ("vel_cmd", "motion_ends", "motion_idxs"):
            if key in src:
                np.testing.assert_array_equal(dst[key], src[key])
        shapes = {key: list(dst[key].shape) for key in dst.files}
    if args.terrain:
        shutil.copy2(args.terrain, converted.with_name("example_terrain.npy"))
    validate_bundle(converted.parent)
    run(["wbt_training.training_runs.diagnose_motion", str(converted)], "diagnose.log")
    report = {"status": "passed", "source": str(source), "converted": str(converted), "commands": commands,
              "shapes": shapes, "checks": "File and directory CLI outputs are identical; all root, DOF, body and optional fields match the expected permutation; native registry validates; diagnose CLI ran", "requires_isaac_or_gpu": False}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
