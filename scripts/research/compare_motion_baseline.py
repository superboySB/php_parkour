#!/usr/bin/env python3
"""Compare motion numerics with an unmodified Git revision in the same Docker.

Historical tests contain only SHA-256 values, so they cannot establish the
magnitude of a numeric mismatch. This independently exports the pre-research
source and compares actual arrays, preserving those historical failures.
No golden hash is changed, skipped, or accepted by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import importlib.metadata
import json
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path


def capture(output: Path) -> None:
    import numpy as np
    import trimesh
    from motion_matching import run as mm
    from motion_matching.scenarios import builtin
    from motion_matching.kinematics.g1_setup import init_g1_kinematics
    from motion_matching.utils import data_utils as data
    from motion_matching.utils.tracking_format import qpos_to_tracking

    output.mkdir(parents=True)
    arrays = {}
    rng = np.random.default_rng(1)
    qpos = rng.standard_normal((40, 36))
    qpos[:, :4] /= np.linalg.norm(qpos[:, :4], axis=1, keepdims=True)
    arrays["resample_data"] = data.resample_data(qpos, 50, 60)
    arrays["adjust_data_speed"] = data.adjust_data_speed(qpos, 1.3)
    rng = np.random.default_rng(5)
    qpos = rng.standard_normal((12, 36))
    qpos[:, :4] /= np.linalg.norm(qpos[:, :4], axis=1, keepdims=True)
    for key, value in qpos_to_tracking(qpos.astype(np.float32), 50).items():
        arrays["tracking_" + key] = value
    params = {"pos": [1.0, 2.0, 0.5], "quat": [1.0, 0.0, 0.0, 0.0], "size": [0.4, 0.6, 0.3]}
    arrays["randomize_box"] = data.randomize_box_x_numpy(params, num_variants=10, rng=np.random.default_rng(0))
    kin, _axes = init_g1_kinematics()
    for name, function in (("global", kin.compute_global_poses), ("joint", kin.compute_joint_poses)):
        pos, quat = function(np.array([0.1, 0.2, 0.5]), np.array([1.0, 0.0, 0.0, 0.0]), np.zeros(kin.num_joints))
        arrays[name + "_position"] = pos
        arrays[name + "_quaternion"] = quat
    original_rng = np.random.default_rng
    np.random.seed(0)
    np.random.default_rng = lambda *_a, **_k: original_rng(0)
    original_db_path = mm.db_path
    cache = output / "features"
    cache.mkdir()
    mm.db_path = lambda relative: str(cache / relative) if relative.endswith(".pkl") else original_db_path(relative)
    for name, function in (("roll_78", builtin.low_speed_roll_78), ("climb_76", builtin.low_speed_climb_76)):
        configs, ratio = function()
        config = configs[0]
        directory = output / name
        directory.mkdir()
        mm.init_worker(required_skills=mm.collect_required_skills([config]))
        mm.process_scenario(config, str(directory), force=True, speed_up_ratio=ratio)
        base = directory / config["name"]
        with np.load(base.with_name(base.name + "_motion.npz"), allow_pickle=False) as generated:
            for key in generated.files:
                arrays[name + "_" + key] = generated[key]
        arrays[name + "_terrain_variants"] = np.load(base.with_name(base.name + "_terrain.npy"), allow_pickle=False)
        mesh = trimesh.load(base.with_name(base.name + "_terrain.obj"), process=False)
        arrays[name + "_terrain_vertices"] = np.asarray(mesh.vertices)
        arrays[name + "_terrain_faces"] = np.asarray(mesh.faces)
    np.savez(output / "arrays.npz", **arrays)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="554edcc")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--compare-only", action="store_true", help="recheck existing captured arrays without regenerating them")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if args.capture:
        capture(output)
        return
    if output.exists() and any(output.iterdir()) and not args.compare_only:
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[2]
    git = ["git", "-c", "safe.directory=" + str(repo)]
    revision = subprocess.check_output([*git, "rev-parse", args.base_ref], cwd=repo, text=True).strip()
    source = output / "baseline-source"
    if not args.compare_only:
        archive = subprocess.check_output([*git, "archive", revision, "motion_matching"], cwd=repo)
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(source, filter="data")
    commands = []
    for name, package in (("baseline", source / "motion_matching"), ("research", repo / "motion_matching")):
        command = [sys.executable, str(Path(__file__).resolve()), "--capture", "--output-dir", str(output / name)]
        commands.append(command)
        if args.compare_only:
            continue
        env = {**os.environ, "PYTHONPATH": str(package), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        with (output / (name + ".log")).open("w") as stream:
            subprocess.run(command, cwd=output, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    import numpy as np
    rows, invariants = [], []
    with np.load(output / "baseline/arrays.npz", allow_pickle=False) as before, np.load(output / "research/arrays.npz", allow_pickle=False) as after:
        if set(before.files) != set(after.files):
            raise AssertionError("baseline/research keys differ")
        for name in sorted(before.files):
            left, right = before[name], after[name]
            same_schema = left.dtype == right.dtype and left.shape == right.shape
            finite = bool(np.isfinite(left).all() and np.isfinite(right).all())
            max_difference = float(np.max(np.abs(left.astype(float) - right.astype(float)))) if left.size and same_schema else None
            # This is an exact baseline parity check, not a tolerance-based
            # replacement for the missing historical numeric reference.
            equal = same_schema and finite and np.array_equal(left, right)
            rows.append({"name": name, "status": "passed" if equal else "failed", "shape": list(right.shape),
                         "dtype": str(right.dtype), "finite": finite, "byte_equal": same_schema and left.tobytes() == right.tobytes(),
                         "max_abs_difference": max_difference, "sha256": hashlib.sha256(right.tobytes()).hexdigest()})
        for name, expected_shape in (("resample_data", (33, 36)), ("adjust_data_speed", (30, 36))):
            actual = after[name]
            error = float(np.max(np.abs(np.linalg.norm(actual[:, :4], axis=1) - 1)))
            # Production quat.normalize divides by norm + 1e-8. Preserve
            # that intentional regularization rather than demanding exact 1.
            invariants.append({"name": name + "_shape_and_unit_quaternion", "status": "passed" if actual.shape == expected_shape and error < 2e-8 else "failed", "quaternion_norm_max_error": error, "tolerance": 2e-8, "reason": "quat.normalize uses a 1e-8 denominator regularizer"})
        for name in ("tracking_body_quat_w", "roll_78_body_quat_w", "climb_76_body_quat_w"):
            error = float(np.max(np.abs(np.linalg.norm(after[name], axis=-1) - 1)))
            invariants.append({"name": name + "_unit_quaternion", "status": "passed" if error < 2e-7 else "failed", "max_error": error})
        for name in ("roll_78", "climb_76"):
            velocity_commands = after[name + "_vel_cmd"]
            variants = after[name + "_terrain_variants"]
            valid = velocity_commands.ndim == 2 and velocity_commands.shape[1] == 15 and np.all(np.isin(velocity_commands, [0, 1])) and np.all(velocity_commands.sum(axis=1) == 1)
            valid = valid and variants.ndim == 3 and variants.shape[1:] == (10, 10) and bool(np.all(variants[..., 7:10] > 0))
            invariants.append({"name": name + "_one_hot_commands_and_positive_box_sizes", "status": "passed" if valid else "failed"})
        # Independently accumulate zero-angle URDF joint origins, avoiding
        # yourdfpy's scene graph and the production FK implementation.
        from scipy.spatial.transform import Rotation
        from motion_matching.utils import G1_URDF
        urdf = ET.parse(G1_URDF).getroot()
        links = [link.get("name") for link in urdf.findall("link")]
        joints = urdf.findall("joint")
        children = {joint.find("child").get("link") for joint in joints}
        transforms = {next(name for name in links if name not in children): np.eye(4)}
        pending = list(joints)
        while pending:
            ready = [joint for joint in pending if joint.find("parent").get("link") in transforms]
            if not ready:
                raise AssertionError("URDF joint hierarchy is disconnected")
            for joint in ready:
                origin = joint.find("origin")
                xyz = [float(v) for v in origin.get("xyz", "0 0 0").split()] if origin is not None else [0, 0, 0]
                rpy = [float(v) for v in origin.get("rpy", "0 0 0").split()] if origin is not None else [0, 0, 0]
                local = np.eye(4)
                local[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()
                local[:3, 3] = xyz
                transforms[joint.find("child").get("link")] = transforms[joint.find("parent").get("link")] @ local
                pending.remove(joint)
        for kind, names in (("global", links), ("joint", [joint.find("child").get("link") for joint in joints if joint.get("type") not in ("fixed", "floating")])):
            expected_positions = np.asarray([transforms[name][:3, 3] for name in names]) + [0.1, 0.2, 0.5]
            expected_rotations = np.asarray([transforms[name][:3, :3] for name in names])
            quaternions = after[kind + "_quaternion"]
            actual_rotations = Rotation.from_quat(quaternions[:, [1, 2, 3, 0]]).as_matrix()
            error = max(float(np.max(np.abs(after[kind + "_position"] - expected_positions))), float(np.max(np.abs(actual_rotations - expected_rotations))))
            invariants.append({"name": kind + "_independent_urdf_zero_angle_fk", "status": "passed" if error < 1e-12 else "failed", "max_abs_error": error, "tolerance": 1e-12})
    report = {"schema_version": 1, "baseline_revision": revision, "scope": "same-image unmodified Git source versus research source",
              "python": sys.version, "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "mujoco", "trimesh", "yourdfpy")},
              "thread_environment": {name: "1" for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
              "historical_goldens": "unchanged; historical mm_hs reference arrays/environment unavailable, so legacy hash mismatches remain failures",
              "commands": commands, "arrays": rows, "invariants": invariants,
              "capture_logs": [{"path": str(output / (name + ".log")), "sha256": hashlib.sha256((output / (name + ".log")).read_bytes()).hexdigest()} for name in ("baseline", "research")],
              "failed": sum(row["status"] != "passed" for row in rows + invariants)}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Baseline parity: {sum(row['status'] == 'passed' for row in rows)}/{len(rows)} arrays identical; {sum(row['status'] == 'passed' for row in invariants)}/{len(invariants)} functional invariants; revision {revision}")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
