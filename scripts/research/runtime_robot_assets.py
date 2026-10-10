#!/usr/bin/env python3
"""Seal and verify a writable URDF conversion root without writable Python source.

Only the exact source URDF and its local mesh/texture dependencies are copied.
The immutable manifest uses relative paths so host-side evidence verification
can translate mount paths in memory without rewriting the original manifest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import xml.etree.ElementTree as ET

PRIMARY_URDF = "g1/main_mesh_arm_collision_halfspherehand.urdf"
SOURCE_RELATIVE = "thirdparty/holosoma/src/holosoma/holosoma/data/robots"
GENERATED_DIRECTORY = r"converted_rank[0-9]+_pid[0-9]+"
GENERATED_FILES = "USD (.usd/.usda/.usdc), root config.yaml/.asset_hash, optional configuration directory"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def relative(value):
    path = PurePosixPath(value)
    require(isinstance(value, str) and path.parts and not path.is_absolute()
            and ".." not in path.parts and path.as_posix() == value and ":" not in value,
            "Unsafe robot asset relative path")
    return path


def regular(root, name):
    """Reject links in every component, even when their resolved target is local."""
    root = Path(root)
    require(root.is_absolute(), "Robot asset root must be absolute")
    for parent in [root, *root.parents]:
        require(not parent.is_symlink(), "Robot asset root has a symlink component")
    path = root
    for part in relative(name).parts:
        path = path / part
        require(not path.is_symlink(), "Robot asset path has a symlink component")
    require(stat.S_ISREG(path.stat().st_mode), "Robot asset must be a regular file")
    return path


def closure(source_root, urdf_file=PRIMARY_URDF):
    urdf = regular(source_root, urdf_file)
    names = {relative(urdf_file).as_posix()}
    try:
        tree = ET.parse(urdf)
    except ET.ParseError as error:
        raise ValueError("Original robot URDF is malformed or changed") from error
    for node in tree.iter():
        if node.tag in ("mesh", "texture") and node.get("filename"):
            reference = relative(node.get("filename"))
            name = (relative(urdf_file).parent / reference).as_posix()
            regular(source_root, name)
            names.add(name)
    return [{"relative_path": name, "bytes": regular(source_root, name).stat().st_size,
             "source_sha256": digest(regular(source_root, name)),
             "copy_sha256": digest(regular(source_root, name))} for name in sorted(names)]


def contract(source_root, runtime_root, *, source_path=None, urdf_file=PRIMARY_URDF):
    """Read-only preparation: expected copy hashes are sealed before any copy."""
    payload = {"schema_version": 1, "urdf_file": urdf_file,
               "generated_directory_pattern": GENERATED_DIRECTORY, "generated_file_policy": GENERATED_FILES,
               "files": closure(source_root, urdf_file)}
    raw = encoded(payload)
    target = Path(runtime_root)
    require(target.is_absolute() and target.name == "robots" and target.parent.name == "runtime-robot-assets",
            "Use the independent cohort runtime-robot-assets/robots directory")
    return {**payload, "source_root": str(Path(source_path or source_root)), "runtime_root": str(target),
            "manifest": {"path": str(target.parent / "manifest.json"), "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()}}


def payload(value):
    require(value.get("schema_version") == 1 and value.get("generated_directory_pattern") == GENERATED_DIRECTORY,
            "Unsupported runtime robot asset contract")
    require(value.get("generated_file_policy") == GENERATED_FILES, "Unsupported converter output policy")
    rows = value["files"]
    names = [relative(row["relative_path"]).as_posix() for row in rows]
    require(names and names == sorted(set(names)) and value["urdf_file"] in names,
            "Robot asset contract must contain unique sorted dependencies and its URDF")
    for row in rows:
        require(type(row["bytes"]) is int and row["bytes"] > 0
                and re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
                and row["source_sha256"] == row["copy_sha256"], "Robot source/copy identity differs")
    return {key: value[key] for key in ("schema_version", "urdf_file", "generated_directory_pattern", "generated_file_policy", "files")}


def verify(value, *, copied=True):
    expected = payload(value)
    raw = encoded(expected)
    root = Path(value["runtime_root"])
    require(root.is_absolute() and root.name == "robots" and root.parent.name == "runtime-robot-assets",
            "Runtime robot root escaped the dedicated cohort directory")
    manifest = value["manifest"]
    require(Path(manifest["path"]) == root.parent / "manifest.json"
            and manifest["bytes"] == len(raw) and manifest["sha256"] == hashlib.sha256(raw).hexdigest(),
            "Runtime robot asset manifest identity differs")
    require(closure(value["source_root"], value["urdf_file"]) == expected["files"],
            "Original robot URDF dependency closure changed")
    if not copied:
        return value
    path = regular(root.parent, "manifest.json")
    require(path.read_bytes() == raw, "Runtime robot asset manifest changed")
    originals = {row["relative_path"] for row in expected["files"]}
    for row in expected["files"]:
        path = regular(root, row["relative_path"])
        require(path.stat().st_size == row["bytes"] and digest(path) == row["copy_sha256"],
                "Copied robot asset changed")
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        require(not path.is_symlink(), "Runtime conversion tree contains a symlink")
        mode = path.stat().st_mode
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), "Runtime conversion tree contains a special file")
        if stat.S_ISDIR(mode):
            require(any(original.startswith(name + "/") for original in originals)
                    or re.fullmatch(GENERATED_DIRECTORY, path.relative_to(root).parts[0]),
                    "Unexpected directory outside generated conversion outputs")
        else:
            generated = path.relative_to(root).parts
            allowed_output = (re.fullmatch(GENERATED_DIRECTORY, generated[0]) and len(generated) >= 2
                              and (path.suffix.lower() in (".usd", ".usda", ".usdc")
                                   or (len(generated) == 2 and path.name in ("config.yaml", ".asset_hash"))))
            require(name in originals or allowed_output,
                    "Unexpected file outside generated conversion outputs")
    return value


def prepare(value):
    """First CPU preparation copies once; subsequent entry only verifies bytes."""
    verify(value, copied=False)
    root = Path(value["runtime_root"])
    if root.parent.exists():
        return verify(value)
    root.mkdir(parents=True, exist_ok=False)
    for row in value["files"]:
        target = root / row["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regular(value["source_root"], row["relative_path"]), target)
        target.chmod(0o644)
    with (root.parent / "manifest.json").open("xb") as stream:
        stream.write(encoded(payload(value)))
    return verify(value)


def validate_config(config, value):
    """Check the public override after actual native saved-config parsing."""
    verify(value)
    asset = config.robot.asset
    require(asset.asset_root == value["runtime_root"] and asset.urdf_file == value["urdf_file"]
            and asset.usd_file is None, "Parsed robot asset configuration differs from the sealed URDF contract")
    return {"asset_root": asset.asset_root, "urdf_file": asset.urdf_file, "usd_file": asset.usd_file,
            "manifest_sha256": value["manifest"]["sha256"], "original_files": len(value["files"])}
