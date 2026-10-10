"""CPU guards for immutable source provenance and offline singleton inputs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def coverage():
    source = Path(__file__).resolve().parents[1] / "scripts/research/motion_coverage.py"
    spec = importlib.util.spec_from_file_location("research_motion_coverage", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_source(coverage, root, component="motions-low-step", stem="a"):
    directory = root / component
    directory.mkdir(parents=True, exist_ok=True)
    frames = 3
    pos = np.zeros((frames, 36))
    pos[:, 3] = 1
    quat = np.zeros((frames, 32, 4))
    quat[:, :, 0] = 1
    command = np.zeros((frames, 15), dtype=np.float32)
    command[:, 1] = 1
    data = dict(
        fps=np.array([50]), joint_pos=pos, joint_vel=np.zeros((frames, 35)),
        body_pos_w=np.zeros((frames, 32, 3)), body_quat_w=quat,
        body_lin_vel_w=np.zeros((frames, 32, 3)), body_ang_vel_w=np.zeros((frames, 32, 3)),
        joint_names=np.array(coverage.G1_29DOF_JOINT_NAMES),
        body_names=np.array(coverage.G1_32BODY_NAMES), vel_cmd=command,
    )
    motion = directory / (stem + "_motion.npz")
    np.savez(motion, **data)
    terrain = np.zeros((1, 2, 10))
    terrain[:, :, 3] = 1
    terrain[:, :, 7:] = 1
    np.save(directory / (stem + "_terrain.npy"), terrain)
    return motion, data


def test_order_and_original_expert_survive_byte_exact_singleton(coverage, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "REGISTRIES", (("locomotion", 1), ("low-step", 2)))
    write_source(coverage, tmp_path / "assets", "motions-locomotion", "z")
    write_source(coverage, tmp_path / "assets", stem="b")
    write_source(coverage, tmp_path / "assets", stem="a")
    inventory = coverage.inventory(tmp_path / "assets", release_manifest=None)
    records = inventory["records"]
    assert [(r["expert_ordinal"], r["relative_motion"]) for r in records] == [(0, "z_motion.npz"), (1, "a_motion.npz"), (1, "b_motion.npz")]
    record = records[1]
    assert record["source_motion_idxs"] == {"present": False, "unique_values": None}
    assert record["source_bounds"] == [{"start_inclusive": 0, "end_inclusive": 2}]
    result = coverage.materialize(record, tmp_path / "singleton")
    assert (tmp_path / "singleton").stat().st_mode & 0o777 == 0o755
    assert result["source_clip_id"] == "motions-low-step/a_motion.npz"
    assert result["original_expert_ordinal"] == 1 and result["singleton_native_expert_ordinal"] == 0
    assert result["record"] == record
    assert result["registry_uri"] == (tmp_path / "singleton/bundle").as_uri()
    for file in result["files"]:
        assert not Path(file["path"]).is_symlink()
        assert Path(file["path"]).read_bytes() == Path(file["source"]).read_bytes()
    assert json.loads(Path(result["provenance_path"]).read_text()) == result
    with pytest.raises(ValueError, match="nonempty"):
        coverage.materialize(record, tmp_path / "singleton")


@pytest.mark.parametrize("mutation,pattern", [("nan", "NaN"), ("shape", "expected shape"), ("names", "ordering"), ("command", "one active")])
def test_reject_malformed_native_inputs(coverage, tmp_path, mutation, pattern):
    motion, data = write_source(coverage, tmp_path)
    if mutation == "nan":
        data["body_ang_vel_w"][1, 0, 0] = np.nan
    elif mutation == "shape":
        data["joint_vel"] = data["joint_vel"][:, :-1]
    elif mutation == "names":
        data["joint_names"] = data["joint_names"][::-1]
    else:
        data["vel_cmd"][0, 0] = 1
    np.savez(motion, **data)
    with pytest.raises(ValueError, match=pattern):
        coverage.inspect_motion(motion)


def test_reject_orphan_pair_and_stale_source_hash(coverage, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    motion, data = write_source(coverage, tmp_path / "assets")
    record = coverage.inventory(tmp_path / "assets", release_manifest=None)["records"][0]
    orphan = motion.with_name("orphan_terrain.npy")
    np.save(orphan, np.zeros((0, 1, 10)))
    with pytest.raises(ValueError, match="pair"):
        coverage.inventory(tmp_path / "assets", release_manifest=None)
    orphan.unlink()
    data["joint_pos"][0, 0] = 1
    np.savez(motion, **data)
    with pytest.raises(ValueError, match="changed since inventory"):
        coverage.materialize(record, tmp_path / "stale")
    assert not (tmp_path / "stale").exists()


def test_reject_nonzero_native_id_without_silent_relabel(coverage, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    motion, data = write_source(coverage, tmp_path / "assets")
    data["motion_idxs"] = np.ones(3, dtype=np.int64)
    data["motion_ends"] = np.array([False, False, True])
    np.savez(motion, **data)
    record = coverage.inventory(tmp_path / "assets", release_manifest=None)["records"][0]
    with pytest.raises(ValueError, match="nonzero native expert IDs"):
        coverage.materialize(record, tmp_path / "invalid-singleton")
    assert not (tmp_path / "invalid-singleton").exists()


def test_release_checksum_required(coverage, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    motion, _ = write_source(coverage, tmp_path / "assets")
    files = [{"path": p.name, "size": p.stat().st_size, "sha256": coverage.sha256(p)} for p in motion.parent.iterdir()]
    files[0]["sha256"] = "0" * 64
    release = tmp_path / "release.json"
    release.write_text(json.dumps({"components": {"motions-low-step": {"files": files}}}))
    with pytest.raises(ValueError, match="checksum/size mismatch"):
        coverage.inventory(tmp_path / "assets", release_manifest=release)


@pytest.mark.parametrize("field,value,pattern", [
    ("expert_ordinal", 1, "expert_ordinal mismatch"),
    ("source_ordinal", 1, "source_ordinal mismatch"),
    ("source_motion_sha256", "0" * 64, "identity SHA256 mismatch"),
])
def test_saved_inventory_rejects_changed_source_labels(coverage, monkeypatch, tmp_path, field, value, pattern):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    write_source(coverage, tmp_path / "assets")
    inventory = coverage.inventory(tmp_path / "assets", release_manifest=None)
    inventory["records"][0][field] = value
    with pytest.raises(ValueError, match=pattern):
        coverage.validate_inventory(inventory)


@pytest.mark.parametrize("expert", [-1, True, 5])
def test_singleton_rejects_negative_boolean_or_out_of_range_expert(coverage, monkeypatch, tmp_path, expert):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    write_source(coverage, tmp_path / "assets")
    record = coverage.inventory(tmp_path / "assets", release_manifest=None)["records"][0]
    record["expert_ordinal"] = expert
    with pytest.raises(ValueError, match="nonnegative integer"):
        coverage.materialize(record, tmp_path / "bad-expert")


def test_singleton_checks_source_boundary_field_presence(coverage, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "REGISTRIES", (("low-step", 1),))
    write_source(coverage, tmp_path / "assets")
    record = coverage.inventory(tmp_path / "assets", release_manifest=None)["records"][0]
    record["source_motion_ends_present"] = True
    with pytest.raises(ValueError, match="source_motion_ends_present"):
        coverage.materialize(record, tmp_path / "bad-field-presence")
