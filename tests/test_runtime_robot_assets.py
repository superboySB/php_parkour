"""Filesystem and native parser regressions for the writable conversion root.

No Robot, simulator, CUDA context, or DDS listener is constructed here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.research import runtime_robot_assets as assets


@pytest.fixture
def sealed(tmp_path):
    source = tmp_path / "source"
    urdf = source / assets.PRIMARY_URDF
    urdf.parent.mkdir(parents=True)
    urdf.write_text('<robot name="fixture"><link name="body"><visual><geometry>'
                    '<mesh filename="meshes/a.STL"/></geometry></visual><collision><geometry>'
                    '<mesh filename="meshes/a.STL"/></geometry></collision></link></robot>')
    (urdf.parent / "meshes").mkdir()
    (urdf.parent / "meshes/a.STL").write_bytes(b"mesh fixture bytes\x00\x01")
    value = assets.contract(source, tmp_path / "cohort/runtime-robot-assets/robots")
    return value


def test_copy_preserves_original_bytes_deduplicates_mesh_and_seals_once(sealed):
    assert len(sealed["files"]) == 2
    before = {row["relative_path"]: (Path(sealed["source_root"]) / row["relative_path"]).read_bytes() for row in sealed["files"]}
    assets.prepare(sealed)
    original_manifest = Path(sealed["manifest"]["path"]).read_bytes()
    for name, raw in before.items():
        assert (Path(sealed["runtime_root"]) / name).read_bytes() == raw
        assert (Path(sealed["source_root"]) / name).read_bytes() == raw
    assets.prepare(sealed)
    assert Path(sealed["manifest"]["path"]).read_bytes() == original_manifest


@pytest.mark.parametrize("location", ("source_root", "runtime_root"))
def test_changed_original_or_copy_is_rejected_without_recopied_repair(sealed, location):
    assets.prepare(sealed)
    path = Path(sealed[location]) / sealed["files"][0]["relative_path"]
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        assets.prepare(sealed)
    assert path.read_bytes() == b"tampered"


def test_partial_first_copy_is_retained_and_not_overwritten(sealed):
    root = Path(sealed["runtime_root"])
    root.mkdir(parents=True)
    (root / "partial.txt").write_bytes(b"retain")
    with pytest.raises(OSError):
        assets.prepare(sealed)
    assert (root / "partial.txt").read_bytes() == b"retain"


def test_native_converter_outputs_may_accumulate_but_original_hashes_stay_fixed(sealed):
    assets.prepare(sealed)
    root = Path(sealed["runtime_root"])
    for pid in (17, 239):
        directory = root / f"converted_rank0_pid{pid}"
        (directory / "configuration").mkdir(parents=True)
        for relative in ("robot.usd", "configuration/robot_physics.usd", "config.yaml", ".asset_hash"):
            (directory / relative).write_bytes(b"native converter output placeholder; no physics claimed")
    assets.verify(sealed)


@pytest.mark.parametrize("name", ("g1/rogue.usd", "converted_rankx_pid1/robot.usd", "converted_rank0_pid2/code.py",
                                  "converted_rank0_pid2/subdir/config.yaml"))
def test_unrelated_or_executable_additions_rejected(sealed, name):
    assets.prepare(sealed)
    path = Path(sealed["runtime_root"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unapproved addition")
    with pytest.raises(ValueError):
        assets.verify(sealed)


@pytest.mark.parametrize("reference", ("../../escape.STL", "/tmp/absolute.STL", "package://robot/mesh.STL"))
def test_urdf_external_or_parent_references_rejected(sealed, reference):
    path = Path(sealed["source_root"]) / sealed["urdf_file"]
    path.write_text(f'<robot><mesh filename="{reference}"/></robot>')
    with pytest.raises(ValueError):
        assets.closure(sealed["source_root"])


def test_generated_symlink_is_rejected(sealed, tmp_path):
    assets.prepare(sealed)
    directory = Path(sealed["runtime_root"]) / "converted_rank0_pid19"
    directory.mkdir()
    (directory / "robot.usd").symlink_to(Path(sealed["source_root"]) / sealed["urdf_file"])
    with pytest.raises(ValueError, match="symlink"):
        assets.verify(sealed)


def test_source_parent_symlink_is_rejected(sealed, tmp_path):
    source = Path(sealed["source_root"])
    alias = tmp_path / "source-link"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        assets.contract(alias, Path(sealed["runtime_root"]))


def test_manifest_and_config_mismatch_rejected(sealed):
    assets.prepare(sealed)
    config = SimpleNamespace(robot=SimpleNamespace(asset=SimpleNamespace(
        asset_root=sealed["runtime_root"], urdf_file=sealed["urdf_file"], usd_file=None)))
    assert assets.validate_config(config, sealed)["original_files"] == 2
    config.robot.asset.asset_root = sealed["source_root"]
    with pytest.raises(ValueError, match="Parsed robot"):
        assets.validate_config(config, sealed)
    Path(sealed["manifest"]["path"]).write_bytes(b"changed manifest")
    with pytest.raises(ValueError, match="manifest changed"):
        assets.verify(sealed)


def test_host_path_translation_does_not_rewrite_manifest(sealed, tmp_path):
    assets.prepare(sealed)
    raw = Path(sealed["manifest"]["path"]).read_bytes()
    # Manifest is deliberately path independent; case/selection fingerprints
    # bind the actual roots, which the host translates only in memory.
    assert "source_root" not in json.loads(raw) and "runtime_root" not in json.loads(raw)
    translated = copy.deepcopy(sealed)
    translated["source_root"] = str(tmp_path / "translated-source")
    translated["runtime_root"] = str(tmp_path / "translated/runtime-robot-assets/robots")
    import shutil
    shutil.copytree(sealed["source_root"], translated["source_root"])
    shutil.copytree(Path(sealed["runtime_root"]).parent, Path(translated["runtime_root"]).parent)
    translated["manifest"]["path"] = str(Path(translated["runtime_root"]).parent / "manifest.json")
    assets.verify(translated)
    assert Path(translated["manifest"]["path"]).read_bytes() == raw
    assert Path(sealed["manifest"]["path"]).read_bytes() == raw


def test_real_g1_closure_is_exact_35_with_referenced_half_sphere():
    root = Path(__file__).resolve().parents[1]
    rows = assets.closure(root / assets.SOURCE_RELATIVE)
    assert len(rows) == 35
    assert any(row["relative_path"] == "g1/meshes/half_sphere.obj" for row in rows)
    urdf = next(row for row in rows if row["relative_path"] == assets.PRIMARY_URDF)
    assert urdf["source_sha256"] == "0ce8a53a9bd2751d890a037aa9cc4cde3677832bbe779ff5de92349ff9af648d"


def test_actual_native_parser_public_override_changes_only_asset_root(sealed):
    from dataclasses import asdict
    from wbt_training.config_values.experiment import g1_wbt_terrain_ref_noscale
    from wbt_training.utils.checkpoint import parse_saved_config_overrides
    assets.prepare(sealed)
    original = g1_wbt_terrain_ref_noscale.get_eval_config()
    parsed = parse_saved_config_overrides(original, ["--robot.asset.asset-root", sealed["runtime_root"]])
    actual, expected = asdict(parsed), asdict(original)
    expected["robot"]["asset"]["asset_root"] = sealed["runtime_root"]
    assert actual == expected
    assert assets.validate_config(parsed, sealed)["asset_root"] == sealed["runtime_root"]
