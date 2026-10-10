"""Deployment boundaries: corrupted transfers and active jobs must fail closed."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/research/cloud.py"
    spec = importlib.util.spec_from_file_location("php_cloud_transfer_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


@pytest.fixture
def args():
    return argparse.Namespace(host="test-host", remote_root="/diff/dzp_is_sb/test", gpu=None)


def cached_image(cloud):
    info = {"Id": "sha256:local", "Config": {"Env": ["PHP_DOCKER=1"]},
            "RootFS": {"Type": "layers", "Layers": ["sha256:expected-layer"]}}
    digest = hashlib.sha256(json.dumps({"Config": info["Config"], "RootFS": info["RootFS"]},
                                      sort_keys=True).encode()).hexdigest()
    directory = cloud.ROOT / "outputs/research/cloud/images"
    directory.mkdir(parents=True)
    archive = directory / "local.tar.gz"
    archive.write_bytes(b"test archive bytes")
    return info, digest, archive


def test_corrupt_remote_archive_is_rejected_before_docker_load(cloud, args, monkeypatch):
    info, fingerprint, archive = cached_image(cloud)
    monkeypatch.setattr(cloud, "image_info", lambda image: (info["Id"], fingerprint))
    commands = []
    monkeypatch.setattr(cloud, "ssh", lambda args, argv, **kwargs: commands.append(argv))
    monkeypatch.setattr(cloud, "transfer", lambda *args, **kwargs: None)

    def remote(args, command):
        if command[:3] == ["docker", "image", "inspect"]:
            raise subprocess.CalledProcessError(1, command)
        assert command[0] == "sha256sum"
        return "0" * 64 + "  archive.tar.gz"

    monkeypatch.setattr(cloud, "remote_output", remote)
    with pytest.raises(RuntimeError, match="checksum differs"):
        cloud.upload_image(args)
    assert not any(command[:2] == ["docker", "load"] for command in commands)
    assert archive.read_bytes() == b"test archive bytes"


def test_changed_loaded_layers_are_rejected_after_verified_transfer(cloud, args, monkeypatch):
    info, fingerprint, archive = cached_image(cloud)
    monkeypatch.setattr(cloud, "image_info", lambda image: (info["Id"], fingerprint))
    commands = []
    monkeypatch.setattr(cloud, "ssh", lambda args, argv, **kwargs: commands.append(argv))
    monkeypatch.setattr(cloud, "transfer", lambda *args, **kwargs: None)
    inspections = 0

    def remote(args, command):
        nonlocal inspections
        if command[0] == "sha256sum":
            return cloud.sha(archive) + "  archive.tar.gz"
        inspections += 1
        if inspections == 1:
            raise subprocess.CalledProcessError(1, command)
        changed = dict(info, RootFS={"Type": "layers", "Layers": ["sha256:wrong-layer"]})
        return json.dumps([changed])

    monkeypatch.setattr(cloud, "remote_output", remote)
    with pytest.raises(RuntimeError, match="configuration/layers differ"):
        cloud.upload_image(args)
    assert sum(command[:2] == ["docker", "load"] for command in commands) == 1


def test_existing_container_is_retained_before_transfer(cloud, args, monkeypatch):
    monkeypatch.setattr(cloud, "image_info", lambda image: ("sha256:local", "fingerprint"))
    monkeypatch.setattr(cloud, "gpu_snapshot", lambda args: ({"index": 1}, []))
    monkeypatch.setattr(cloud, "remote_output", lambda args, command: "existing-job-container")

    def no_transfer(*args, **kwargs):
        pytest.fail("An existing container must be rejected before source/image transfer")

    monkeypatch.setattr(cloud, "sync", no_transfer)
    monkeypatch.setattr(cloud, "upload_image", no_transfer)
    monkeypatch.setattr(cloud, "ssh", no_transfer)
    with pytest.raises(RuntimeError, match="already exists"):
        cloud.deploy(args)


def test_deploy_uses_post_transfer_uuid_and_private_shared_memory(cloud, args, monkeypatch):
    (cloud.ROOT / "outputs/research/cloud").mkdir(parents=True)
    monkeypatch.setattr(cloud, "image_info", lambda image: ("sha256:local", "fingerprint"))
    snapshots = iter([
        ({"index": 1, "uuid": "GPU-before-transfer"}, []),
        ({"index": 2, "uuid": "GPU-still-idle"}, []),
    ])
    monkeypatch.setattr(cloud, "gpu_snapshot", lambda args: next(snapshots))
    monkeypatch.setattr(cloud, "remote_output", lambda args, command: "")
    source = args.remote_root + "/source/frozen-tree"
    monkeypatch.setattr(cloud, "sync", lambda args: (source, "frozen-tree"))
    monkeypatch.setattr(cloud, "upload_image", lambda args: {"image": cloud.IMAGE, "remote_id": "sha256:verified-remote"})
    commands = []
    monkeypatch.setattr(cloud, "ssh", lambda args, argv, **kwargs: commands.append(argv))
    monkeypatch.setattr(cloud, "transfer", lambda *args, **kwargs: None)
    cloud.deploy(args)
    run = next(command for command in commands if command[:2] == ["docker", "run"])
    assert run[run.index("--gpus") + 1] == "device=GPU-still-idle"
    assert "CUDA_VISIBLE_DEVICES=0" in run
    assert source + ":/workspace/php_parkour" in run
    assert args.remote_root + "/assets:/data/assets" in run
    assert args.remote_root + "/outputs:/outputs" in run
    assert "--ipc=host" not in run and "--privileged" not in run
    assert "--shm-size" in run
    assert run[-3:] == ["sha256:verified-remote", "sleep", "infinity"]
    assert not any(command[:2] in (["docker", "rm"], ["docker", "stop"]) for command in commands)


def test_source_manifest_omits_host_authentication_files(cloud, monkeypatch):
    files = ["safe.py", ".netrc", ".aws/credentials", "keys/id_rsa_backup", ".env.local"]
    for name in files:
        path = cloud.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test fixture\n")
    holo = cloud.ROOT / "thirdparty/holosoma"
    holo.mkdir(parents=True)

    def listing(command):
        return ("\0".join(files) + "\0").encode() if command[2] == str(cloud.ROOT) else b""

    monkeypatch.setattr(cloud.subprocess, "check_output", listing)
    assert [item["path"] for item in cloud.source_files()] == ["safe.py"]


def test_export_freezes_initial_image_and_retags_only_verified_loaded_id(cloud, args, monkeypatch):
    initial = {"Id": "sha256:initial-id", "Config": {"Env": ["PHP_DOCKER=1"]},
               "RootFS": {"Type": "layers", "Layers": ["sha256:original-layer"]}}
    fingerprint = hashlib.sha256(json.dumps(
        {"Config": initial["Config"], "RootFS": initial["RootFS"]},
        sort_keys=True).encode()).hexdigest()
    transfer_tag = "php-parkour:transfer-initial-id"
    # Loading can change a manifest ID while retaining the actual contents.
    loaded = dict(initial, Id="sha256:verified-remote-manifest")
    local_commands, remote_commands, exports = [], [], []
    mutable_image_id = initial["Id"]

    def identify(image):
        assert image == cloud.IMAGE
        return mutable_image_id, fingerprint

    def local(command, **kwargs):
        nonlocal mutable_image_id
        local_commands.append(command)
        if command[:2] == ["docker", "tag"]:
            # A concurrent build replaces the public tag after initial inspect.
            mutable_image_id = "sha256:concurrently-built-image"

    class Process:
        def __init__(self, command, **kwargs):
            self.stdout = io.BytesIO(b"saved image")
            if command[:2] == ["docker", "save"]:
                exports.append(command)
                assert mutable_image_id != initial["Id"]
                assert command[2] == transfer_tag
            elif command == ["gzip", "-1"]:
                kwargs["stdout"].write(b"compressed frozen image")
            else:
                pytest.fail("Unexpected subprocess: " + repr(command))

        def wait(self):
            return 0

    inspections = 0

    def remote(args, command):
        nonlocal inspections
        if command[0] == "sha256sum":
            archive = cloud.ROOT / "outputs/research/cloud/images/initial-id.tar.gz"
            return cloud.sha(archive) + "  image.tar.gz"
        inspections += 1
        if inspections == 1:
            raise subprocess.CalledProcessError(1, command)
        assert command == ["docker", "image", "inspect", transfer_tag]
        return json.dumps([loaded])

    monkeypatch.setattr(cloud, "image_info", identify)
    monkeypatch.setattr(cloud, "run", local)
    monkeypatch.setattr(cloud.subprocess, "Popen", Process)
    monkeypatch.setattr(cloud, "remote_output", remote)
    monkeypatch.setattr(cloud, "ssh", lambda args, argv, **kwargs: remote_commands.append(argv))
    monkeypatch.setattr(cloud, "transfer", lambda *args, **kwargs: None)
    result = cloud.upload_image(args)
    assert local_commands[0] == ["docker", "tag", initial["Id"], transfer_tag]
    assert exports == [["docker", "save", transfer_tag]]
    assert remote_commands[-1] == ["docker", "tag", loaded["Id"], cloud.IMAGE]
    assert result["local_id"] == initial["Id"]
    assert result["remote_id"] == loaded["Id"]
