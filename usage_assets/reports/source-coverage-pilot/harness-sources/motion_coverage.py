#!/usr/bin/env python3
"""Validate released source motions and copy one immutable, offline eval bundle.

Run with train-python inside the research Docker. This module performs CPU data
checks only; it does not import a simulator, restore a policy, or allocate a GPU.
Source file IDs, source boundaries, training expert IDs and the singleton's local
expert ID are deliberately recorded separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from wbt_training.config_values.robot_config import G1_29DOF_JOINT_NAMES, G1_32BODY_NAMES
from wbt_training.utils.registry import bundle_pairs, validate_bundle

# This is the ordered five-expert student input, not alphabetical skill order.
REGISTRIES = (
    ("locomotion", 100),
    ("low-step", 56),
    ("high-step", 60),
    ("low-climb-76", 40),
    ("high-climb-76", 40),
)
SCHEMA_VERSION = 1


def sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _numeric(array: np.ndarray, shape: tuple[int, ...], label: str) -> None:
    _require(array.shape == shape, f"{label}: expected shape {shape}, got {array.shape}")
    _require(array.dtype.kind in "fiu", f"{label}: expected real numeric dtype")
    _require(bool(np.isfinite(array).all()), f"{label}: contains NaN or infinity")


def _quaternion_error(array: np.ndarray, label: str) -> float:
    error = float(np.max(np.abs(np.linalg.norm(array, axis=-1) - 1))) if array.size else 0.0
    _require(error <= 1e-5, f"{label}: wxyz quaternion norm error {error} exceeds 1e-5")
    return error


def inspect_motion(path: Path | str) -> dict:
    """Strict native G1 schema check; return actual source metadata, never rewrite it."""
    path = Path(path)
    with np.load(path, allow_pickle=False) as data:
        fields = {
            "fps", "joint_pos", "joint_vel", "body_pos_w", "body_quat_w",
            "body_lin_vel_w", "body_ang_vel_w", "joint_names", "body_names", "vel_cmd",
        }
        _require(fields <= set(data.files), f"{path}: missing fields {sorted(fields - set(data.files))}")
        fps_value = data["fps"]
        _require(fps_value.size == 1 and fps_value.dtype.kind in "fiu", f"{path}: fps must be one numeric value")
        fps = float(fps_value.item())
        _require(bool(np.isfinite(fps)) and fps > 0, f"{path}: fps must be finite and positive")
        joint_pos = data["joint_pos"]
        _require(joint_pos.ndim == 2 and len(joint_pos) >= 2, f"{path}: need at least two motion frames")
        frames = len(joint_pos)
        shapes = {
            "joint_pos": (frames, 36), "joint_vel": (frames, 35),
            "body_pos_w": (frames, 32, 3), "body_quat_w": (frames, 32, 4),
            "body_lin_vel_w": (frames, 32, 3), "body_ang_vel_w": (frames, 32, 3),
            "vel_cmd": (frames, 15),
        }
        arrays = {key: data[key] for key in shapes}
        for key, shape in shapes.items():
            _numeric(arrays[key], shape, f"{path}:{key}")
        for key, expected in (("joint_names", G1_29DOF_JOINT_NAMES), ("body_names", G1_32BODY_NAMES)):
            names = data[key]
            _require(names.shape == (len(expected),) and names.dtype.kind in "SU", f"{path}:{key}: invalid names array")
            actual = [item.decode() if isinstance(item, bytes) else str(item) for item in names.tolist()]
            _require(actual == expected, f"{path}:{key}: differs from native MuJoCo G1 ordering")
        body_quaternion_error = _quaternion_error(arrays["body_quat_w"], f"{path}:body_quat_w")
        root_quaternion_error = _quaternion_error(joint_pos[:, 3:7], f"{path}:root quaternion")
        command = arrays["vel_cmd"]
        _require(bool(np.logical_or(command == 0, command == 1).all()), f"{path}:vel_cmd must be one-hot")
        _require(bool((command.sum(axis=1) == 1).all()), f"{path}:vel_cmd requires one active index per frame")
        _require(bool((command[:, 12:] == 0).all()), f"{path}:vel_cmd uses undefined indices 12..14")
        if "motion_ends" in data.files:
            ends = data["motion_ends"]
            _require(ends.shape == (frames,) and ends.dtype.kind in "biu", f"{path}: invalid motion_ends shape/dtype")
            _require(bool(np.logical_or(ends == 0, ends == 1).all()), f"{path}:motion_ends must be boolean")
            end_indices = np.flatnonzero(ends).tolist()
            _require(bool(end_indices) and end_indices[-1] == frames - 1, f"{path}:motion_ends must close the final frame")
        else:
            end_indices = [frames - 1]
        starts = [0] + [index + 1 for index in end_indices[:-1]]
        native_ids = {"present": "motion_idxs" in data.files, "unique_values": None}
        if native_ids["present"]:
            ids = data["motion_idxs"]
            _require(ids.shape == (frames,) and ids.dtype.kind in "iu", f"{path}: invalid motion_idxs shape/dtype")
            _require(bool((ids >= 0).all()), f"{path}:motion_idxs must be nonnegative")
            native_ids["unique_values"] = np.unique(ids).tolist()
        return {
            "frames": frames, "fps": fps, "duration_seconds": frames / fps,
            "last_frame_time_seconds": (frames - 1) / fps,
            "end_indices_inclusive": end_indices,
            "source_bounds": [{"start_inclusive": start, "end_inclusive": end} for start, end in zip(starts, end_indices)],
            "source_motion_ends_present": "motion_ends" in data.files,
            "source_motion_idxs": native_ids,
            "boundary_interpretation": "explicit source motion_ends" if "motion_ends" in data.files else "entire source file; final boundary supplied by native concatenation",
            "arrays": {key: {"shape": list(value.shape), "dtype": str(value.dtype)} for key, value in arrays.items()},
            "extra_keys": sorted(set(data.files) - fields),
            "command_active_indices": np.flatnonzero(np.any(command != 0, axis=0)).tolist(),
            "body_quaternion_max_norm_error": body_quaternion_error,
            "root_quaternion_max_norm_error": root_quaternion_error,
            "joint_order": "G1_29DOF_JOINT_NAMES (MuJoCo)",
            "body_order": "G1_32BODY_NAMES", "quaternion_order": "wxyz",
        }


def inspect_terrain(path: Path | str) -> dict:
    path = Path(path)
    terrain = np.load(path, allow_pickle=False)
    _require(isinstance(terrain, np.ndarray), f"{path}: terrain must be NPY, not NPZ")
    _require(terrain.ndim == 3 and terrain.shape[1] >= 1 and terrain.shape[2] == 10, f"{path}: expected (boxes, variants, 10)")
    _numeric(terrain, terrain.shape, str(path))
    _require(bool((terrain[:, :, 7:] > 0).all()), f"{path}: box sizes must be positive")
    return {
        "shape": list(terrain.shape), "dtype": str(terrain.dtype),
        "box_count": int(terrain.shape[0]), "variant_count": int(terrain.shape[1]),
        "quaternion_max_norm_error": _quaternion_error(terrain[:, :, 3:7], str(path)),
        "layout": "world XYZ, wxyz quaternion, full XYZ size",
    }


def _identity(record: dict) -> dict:
    return {key: record[key] for key in (
        "source_clip_id", "global_ordinal", "expert_ordinal", "source_ordinal",
        "source_motion_sha256", "source_terrain_sha256", "source_obj_sha256",
        "frames", "fps", "source_bounds",
    )}


def validate_inventory(data: dict) -> None:
    """Reject changed source/expert labels before consuming a saved inventory.

    This validates manifest consistency, not a cryptographic signature. The
    actual data bytes are checked against release-assets.json by inventory(),
    and checked again against the recorded SHA when materializing a source.
    """
    _require(data.get("schema_version") == SCHEMA_VERSION, "Unsupported inventory schema")
    records = data.get("records")
    count = sum(count for _, count in REGISTRIES)
    _require(isinstance(records, list) and len(records) == count and data.get("total_files") == count, f"Inventory must contain the ordered {count} released sources")
    _require(data.get("registry_order") == ["motions-" + skill for skill, _ in REGISTRIES], "Inventory registry order mismatch")
    root = Path(data["asset_root"])
    global_ordinal = 0
    for expert, (skill, count) in enumerate(REGISTRIES):
        component = "motions-" + skill
        group = records[global_ordinal:global_ordinal + count]
        relative_paths = [record["relative_motion"] for record in group]
        _require(relative_paths == sorted(set(relative_paths)), f"{component}: source paths must be unique and sorted")
        for ordinal, record in enumerate(group):
            for key, expected in (("global_ordinal", global_ordinal + ordinal), ("expert_ordinal", expert), ("source_ordinal", ordinal)):
                _require(type(record.get(key)) is int and record[key] == expected, f"Inventory {key} mismatch")
            _require(record["registry_component"] == component and record["skill"] == skill, "Inventory expert/skill label mismatch")
            _require(record["source_registry_uri"] == (root / component).as_uri(), "Inventory registry URI mismatch")
            _require(record["source_clip_id"] == component + "/" + record["relative_motion"], "Inventory source_clip_id mismatch")
            for role in ("motion", "terrain", "obj"):
                relative = record["relative_" + role]
                source = record["source_" + role]
                digest = record["source_" + role + "_sha256"]
                if relative is None:
                    _require(role == "obj" and source is None and digest is None, "Inventory missing required pair member")
                    continue
                path = Path(relative)
                _require(not path.is_absolute() and ".." not in path.parts, "Inventory unsafe relative source path")
                _require(source == str(root / component / path), "Inventory source path mismatch")
                _require(isinstance(digest, str) and len(digest) == 64 and all(char in "0123456789abcdef" for char in digest), "Inventory invalid source SHA256")
            expected_terrain = "terrain".join(record["relative_motion"].rsplit("motion", 1))
            _require(record["relative_terrain"] == str(Path(expected_terrain).with_suffix(".npy")), "Inventory motion/terrain stem mismatch")
            if record["relative_obj"] is not None:
                _require(record["relative_obj"] == str(Path(record["relative_terrain"]).with_suffix(".obj")), "Inventory terrain/OBJ stem mismatch")
            _require(type(record["frames"]) is int and record["frames"] >= 2 and record["fps"] == 50, "Inventory released frame count/FPS mismatch")
            ends = record["end_indices_inclusive"]
            _require(isinstance(ends, list) and ends and all(type(end) is int and 0 <= end < record["frames"] for end in ends) and ends == sorted(set(ends)) and ends[-1] == record["frames"] - 1, "Inventory invalid source boundaries")
            starts = [0] + [end + 1 for end in ends[:-1]]
            _require(record["source_bounds"] == [{"start_inclusive": start, "end_inclusive": end} for start, end in zip(starts, ends)], "Inventory source bounds mismatch")
        global_ordinal += count
    _require(data.get("total_frames") == sum(record["frames"] for record in records), "Inventory total frame count mismatch")
    _require(abs(data["total_reference_seconds"] - sum(record["frames"] / record["fps"] for record in records)) < 1e-8, "Inventory reference duration mismatch")
    identities = [_identity(record) for record in records]
    expected_hash = hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _require(data.get("inventory_sha256") == expected_hash, "Inventory identity SHA256 mismatch; source/expert metadata changed")


def inventory(root: Path | str, *, release_manifest: Path | str | None = REPO / "release-assets.json") -> dict:
    """Inventory the fixed five released registries in original expert order.

    Relative motion paths determine source_ordinal, matching bundle_pairs and
    native preprocessing. source_clip_id is component/relative-motion-path;
    SHA256 values bind that stable path identity to the exact input bytes.
    """
    root = Path(root).expanduser().resolve()
    release = json.loads(Path(release_manifest).read_text()) if release_manifest is not None else None
    records, summary = [], []
    for expert, (skill, count) in enumerate(REGISTRIES):
        component = "motions-" + skill
        directory = root / component
        pairs = bundle_pairs(directory)
        _require(len(pairs) == count, f"{component}: expected {count} motions, found {len(pairs)}")
        _require(all(terrain is not None for _, terrain, _ in pairs), f"{component}: every released motion needs its matching terrain NPY")
        expected_files = {entry["path"]: entry for entry in release["components"][component]["files"]} if release else None
        if expected_files is not None:
            expected_data = {name for name in expected_files if Path(name).suffix in (".npz", ".npy", ".obj")}
            actual_data = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".npz", ".npy", ".obj")}
            _require(actual_data == expected_data, f"{component}: data paths differ from release manifest")
        paired_data = {path for pair in pairs for path in pair if path is not None}
        _require(paired_data == {path for path in directory.rglob("*") if path.is_file() and path.suffix in (".npz", ".npy", ".obj")}, f"{component}: unpaired data file")
        first = len(records)
        for ordinal, (motion, terrain, obj) in enumerate(pairs):
            relative = motion.relative_to(directory).as_posix()
            record = {
                "source_clip_id": component + "/" + relative,
                "global_ordinal": len(records), "expert_ordinal": expert,
                "skill": skill, "registry_component": component, "source_ordinal": ordinal,
                "source_registry_uri": directory.as_uri(), "relative_motion": relative,
            }
            for role, path in (("motion", motion), ("terrain", terrain), ("obj", obj)):
                digest = sha256(path) if path else None
                record["source_" + role] = str(path) if path else None
                record["source_" + role + "_sha256"] = digest
                record["relative_" + role] = path.relative_to(directory).as_posix() if path else None
                if expected_files is not None and path is not None:
                    entry = expected_files[path.relative_to(directory).as_posix()]
                    _require(digest == entry["sha256"] and path.stat().st_size == entry["size"], f"{path}: release checksum/size mismatch")
            record.update(inspect_motion(motion))
            record["terrain"] = inspect_terrain(terrain)
            record["release_checksum_verified"] = expected_files is not None
            _require(record["fps"] == 50, f"{motion}: released coverage requires 50 Hz; no automatic resampling")
            records.append(record)
        group = records[first:]
        summary.append({
            "expert_ordinal": expert, "skill": skill, "registry_component": component,
            "files": len(group), "frames": sum(item["frames"] for item in group),
            "reference_seconds": sum(item["duration_seconds"] for item in group),
            "source_boundary_count": sum(len(item["source_bounds"]) for item in group),
            "global_ordinal_start": first, "global_ordinal_end_inclusive": len(records) - 1,
        })
    identities = [_identity(record) for record in records]
    result = {
        "schema_version": SCHEMA_VERSION, "status": "cpu_inventory_verified",
        "scope": "Released native source files and terrain pairs only; no simulation, policy inference, or claim of source-clip skill success.",
        "asset_root": str(root), "registry_order": ["motions-" + skill for skill, _ in REGISTRIES],
        "ordering": "fixed original five-expert registry order, then relative POSIX motion path (bundle_pairs)",
        "release_manifest_sha256": sha256(release_manifest) if release_manifest is not None else None,
        "inventory_sha256": hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "records": records, "summary": summary, "total_files": len(records),
        "total_frames": sum(record["frames"] for record in records),
        "total_reference_seconds": sum(record["duration_seconds"] for record in records),
        "fps_set": sorted({record["fps"] for record in records}),
        "native_source_motion_idxs_present_count": sum(record["source_motion_idxs"]["present"] for record in records),
        "native_source_motion_ends_present_count": sum(record["source_motion_ends_present"] for record in records),
        "simulation_started": False,
    }
    validate_inventory(result)
    return result


def materialize(record: dict, destination: Path | str) -> dict:
    """Copy a verified source pair byte-for-byte, retaining external provenance.

    The file:// bundle contains one source, with native local expert ID 0 after
    native preprocessing. The original training expert ID is retained outside
    the native NPZ in provenance.json. Existing nonempty destinations are refused.
    """
    destination = Path(destination).expanduser().resolve()
    _require(not destination.exists() or (destination.is_dir() and not any(destination.iterdir())), f"Refusing nonempty destination: {destination}")
    _require(type(record.get("expert_ordinal")) is int and 0 <= record["expert_ordinal"] < len(REGISTRIES), "record expert_ordinal must be a nonnegative integer in the fixed registry order")
    _require(record["registry_component"] == "motions-" + REGISTRIES[record["expert_ordinal"]][0], "record expert/registry order mismatch")
    _require(record["source_clip_id"] == record["registry_component"] + "/" + record["relative_motion"], "record source_clip_id mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=destination.name + ".partial-", dir=destination.parent))
    try:
        # Docker runs as root; published public-source evidence must remain readable
        # by the host user rather than retaining mkdtemp's private 0700 directory.
        stage.chmod(0o755)
        bundle = stage / "bundle"
        bundle.mkdir()
        files = []
        for role in ("motion", "terrain", "obj"):
            source = record["source_" + role]
            if source is None:
                _require(role == "obj", f"Missing required source {role}")
                continue
            relative = Path(record["relative_" + role])
            _require(not relative.is_absolute() and ".." not in relative.parts, f"Unsafe relative {role} path")
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            digest = sha256(target)
            _require(digest == record["source_" + role + "_sha256"], f"Source {role} changed since inventory")
            files.append({"role": role, "source": source, "relative_path": relative.as_posix(), "path": str(destination / "bundle" / relative), "sha256": digest, "bytes": target.stat().st_size})
        validate_bundle(bundle)
        copied = inspect_motion(bundle / record["relative_motion"])
        for key in ("frames", "fps", "end_indices_inclusive", "source_bounds", "source_motion_idxs", "source_motion_ends_present"):
            _require(copied[key] == record[key], f"Source metadata differs from inventory: {key}")
        _require(copied["source_motion_idxs"]["unique_values"] in (None, [0]), "Source has nonzero native expert IDs; byte-preserving singleton cannot relabel them")
        _require(inspect_terrain(bundle / record["relative_terrain"]) == record["terrain"], "Source terrain metadata differs from inventory")
        result = {
            "schema_version": SCHEMA_VERSION, "status": "cpu_singleton_materialized_verified",
            "registry_uri": (destination / "bundle").as_uri(),
            "provenance_path": str(destination / "provenance.json"),
            "source_clip_id": record["source_clip_id"], "original_expert_ordinal": record["expert_ordinal"],
            "singleton_native_expert_ordinal": 0,
            "native_id_note": "Source bytes are unchanged; absent motion_idxs is not a stored zero array. Native preprocessing assigns local expert 0 to this sole registry. Original training expert remains external provenance.",
            "record": record, "files": files, "simulation_started": False,
        }
        (stage / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
        stage.rename(destination)
        return result
    except BaseException:
        shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    scan = subparsers.add_parser("inventory", help="Strict offline inventory of all 296 released source files")
    scan.add_argument("--root", type=Path, default=Path("/data/assets"))
    scan.add_argument("--release-manifest", type=Path, default=REPO / "release-assets.json")
    scan.add_argument("--output", type=Path, required=True)
    single = subparsers.add_parser("materialize", help="Copy one source pair identified in a verified inventory")
    single.add_argument("--inventory", type=Path, required=True)
    single.add_argument("--source-clip-id", required=True)
    single.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "inventory":
        _require(not args.output.exists(), f"Refusing to overwrite existing inventory: {args.output}")
        result = inventory(args.root, release_manifest=args.release_manifest)
        result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({key: result[key] for key in ("status", "inventory_sha256", "total_files", "total_frames", "total_reference_seconds", "fps_set")}, indent=2))
    else:
        data = json.loads(args.inventory.read_text())
        validate_inventory(data)
        matches = [record for record in data["records"] if record["source_clip_id"] == args.source_clip_id]
        _require(len(matches) == 1, "Expected exactly one matching source_clip_id")
        result = materialize(matches[0], args.destination)
        print(json.dumps({key: result[key] for key in ("status", "source_clip_id", "registry_uri", "provenance_path")}, indent=2))


if __name__ == "__main__":
    main()
