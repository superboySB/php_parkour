#!/usr/bin/env python3
"""Synchronize and deploy the same PHP Docker image and source to Tencent.

Only existing Docker, SSH, rsync, gzip and Python standard libraries are used
on hosts. Passwords and private keys are never copied. Run from any directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_idle_gpu import inspect

SSH = ["ssh", "-p", "22", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
       "-o", "StrictHostKeyChecking=accept-new", "-o", "ControlMaster=auto",
       "-o", "ControlPersist=10m", "-o", "ControlPath=~/.ssh/php-parkour-%C"]
CONTAINER = "php-parkour-cloud-research"
IMAGE = "php-parkour:research"


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def output(argv):
    return subprocess.check_output(argv, text=True).strip()


def ssh(args, argv, **kwargs):
    return run([*SSH, args.host, shlex.join(argv)], **kwargs)


def remote_output(args, argv):
    return ssh(args, argv, capture_output=True, text=True).stdout.strip()


def transfer(args, source, destination, *options):
    run(["rsync", "-a", "--partial", "--protect-args", *options,
         "-e", shlex.join(SSH), str(source), str(destination)])


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_files():
    files = []
    # The pinned submodule is materialized, without its Git credentials/metadata.
    for directory, prefix in [(ROOT, ""), (ROOT / "thirdparty/holosoma", "thirdparty/holosoma/")]:
        names = subprocess.check_output(["git", "-C", str(directory), "ls-files", "-z",
                                         "--cached", "--others", "--exclude-standard"]).decode().split("\0")
        for name in names:
            path = directory / name
            if any(part in {".git", ".ssh", ".aws", ".azure", ".netrc", ".pypirc"}
                   or part.startswith((".env", "id_rsa", "id_ed25519", "id_dsa", "id_ecdsa"))
                   or part.lower().endswith((".pem", ".key")) for part in Path(name).parts):
                continue
            if name and (path.is_file() or path.is_symlink()):
                if path.is_symlink():
                    digest = hashlib.sha256(os.readlink(path).encode()).hexdigest()
                else:
                    digest = sha(path)
                files.append({"path": prefix + name, "sha256": digest,
                              "symlink": path.is_symlink(), "mode": path.lstat().st_mode & 0o777})
    return sorted(files, key=lambda item: item["path"])


def stage_source(staged: Path) -> list[dict]:
    """Freeze a verified local snapshot before slow network transfer.

    Other collaborators may edit the checkout during rsync. Those edits belong
    to the next snapshot and must never modify this deployment's content.
    """
    for attempt in range(3):
        files = source_files()
        try:
            for item in files:
                source, target = ROOT / item["path"], staged / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.unlink(missing_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
                digest = hashlib.sha256(os.readlink(target).encode()).hexdigest() if item["symlink"] else sha(target)
                if digest != item["sha256"] or target.lstat().st_mode & 0o777 != item["mode"]:
                    raise ValueError("Source changed while freezing snapshot: " + item["path"])
            return files
        except (OSError, ValueError):
            if attempt == 2:
                raise
    raise RuntimeError("Failed to freeze source snapshot")


def sync(args):
    with tempfile.TemporaryDirectory(prefix="php-source-") as scratch:
        staged = Path(scratch) / "source"
        files = stage_source(staged)
        tree = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        destination = args.remote_root + "/source/" + tree
        ssh(args, ["mkdir", "-p", destination, args.remote_root + "/assets",
                   args.remote_root + "/outputs", args.remote_root + "/logs",
                   args.remote_root + "/cache", args.remote_root + "/images"])
        listing = Path(scratch) / "files"
        listing.write_bytes(b"\0".join(item["path"].encode() for item in files) + b"\0")
        transfer(args, str(staged) + "/", args.host + ":" + destination + "/",
                 "--from0", "--files-from=" + str(listing), "--checksum")
        manifest = Path(scratch) / "source-manifest.json"
        manifest.write_text(json.dumps({"source_tree_sha256": tree,
                                        "git_head": output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
                                        "files": files}, indent=2) + "\n")
        transfer(args, manifest, args.host + ":" + destination + "/source-manifest.json")
    verify_code = """import hashlib,json,os,sys
from pathlib import Path
root=Path(sys.argv[1]); data=json.loads((root/'source-manifest.json').read_text())
for item in data['files']:
 p=root/item['path']; h=hashlib.sha256()
 if item['symlink']: h.update(os.readlink(p).encode())
 else:
  with p.open('rb') as f:
   for block in iter(lambda:f.read(8388608),b''): h.update(block)
 if h.hexdigest()!=item['sha256']: raise SystemExit('Source changed during sync: '+item['path'])
 if p.lstat().st_mode & 0o777 != item['mode']: raise SystemExit('Source mode differs: '+item['path'])
print('Verified source snapshot: '+data['source_tree_sha256'])
"""
    ssh(args, ["python3", "-c", verify_code, destination])
    assets = ROOT / "outputs/research/assets"
    if assets.is_dir():
        transfer(args, str(assets) + "/", args.host + ":" + args.remote_root + "/assets/", "--checksum")
    return destination, tree


def image_info(image):
    info = json.loads(output(["docker", "image", "inspect", image]))[0]
    # Docker's image store can change the manifest ID on load; verify its actual
    # configuration and layer digests as well.
    contents = {"Config": info["Config"], "RootFS": info["RootFS"]}
    return info["Id"], hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()


def upload_image(args):
    image_id, fingerprint = image_info(IMAGE)
    transfer_tag = "php-parkour:transfer-" + image_id.removeprefix("sha256:")
    local = ROOT / "outputs/research/cloud/images"
    local.mkdir(parents=True, exist_ok=True)
    archive = local / (image_id.removeprefix("sha256:") + ".tar.gz")
    ssh(args, ["mkdir", "-p", args.remote_root + "/images"])
    try:
        loaded = json.loads(remote_output(args, ["docker", "image", "inspect", IMAGE]))[0]
        remote_fingerprint = hashlib.sha256(json.dumps(
            {"Config": loaded["Config"], "RootFS": loaded["RootFS"]}, sort_keys=True).encode()).hexdigest()
        if remote_fingerprint == fingerprint:
            return {"image": IMAGE, "local_id": image_id, "remote_id": loaded["Id"],
                    "contents_sha256": fingerprint, "already_present": True}
    except subprocess.CalledProcessError:
        pass
    if not archive.is_file():
        # Freeze the tag from its immutable ID before export. A concurrent build
        # may replace IMAGE but must not change the contents of this archive.
        run(["docker", "tag", image_id, transfer_tag])
        partial = archive.with_suffix(".gz.partial")
        print("Exporting the complete Docker image:", archive, flush=True)
        with partial.open("wb") as stream:
            save = subprocess.Popen(["docker", "save", transfer_tag], stdout=subprocess.PIPE)
            compress = subprocess.Popen(["gzip", "-1"], stdin=save.stdout, stdout=stream)
            save.stdout.close()
            compressed = compress.wait()
            saved = save.wait()
        if compressed or saved:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"docker save/gzip failed: {saved}/{compressed}")
        run(["gzip", "-t", str(partial)])
        partial.replace(archive)
    archive_sha = sha(archive)
    remote_archive = args.remote_root + "/images/" + archive.name
    print(f"Transferring {archive.stat().st_size} bytes; archive SHA-256 {archive_sha}", flush=True)
    transfer(args, archive, args.host + ":" + remote_archive)
    remote_sha = remote_output(args, ["sha256sum", remote_archive]).split()[0]
    if remote_sha != archive_sha:
        raise RuntimeError("Remote Docker archive checksum differs")
    print("Remote archive SHA-256 verified; loading the complete image", flush=True)
    ssh(args, ["docker", "load", "--input", remote_archive])
    verified = None
    # The IMAGE fallback also accepts archives exported by the first research
    # revision, but neither tag is trusted until its layers/config match.
    for candidate in (transfer_tag, IMAGE):
        try:
            loaded = json.loads(remote_output(args, ["docker", "image", "inspect", candidate]))[0]
        except subprocess.CalledProcessError:
            continue
        remote_fingerprint = hashlib.sha256(json.dumps(
            {"Config": loaded["Config"], "RootFS": loaded["RootFS"]}, sort_keys=True).encode()).hexdigest()
        if remote_fingerprint == fingerprint:
            verified = loaded
            break
    if verified is None:
        raise RuntimeError("Remote image configuration/layers differ from the local image")
    ssh(args, ["docker", "tag", verified["Id"], IMAGE])
    return {"image": IMAGE, "local_id": image_id, "remote_id": verified["Id"],
            "contents_sha256": fingerprint, "archive_sha256": archive_sha,
            "archive_bytes": archive.stat().st_size}


def gpu_snapshot(args):
    xml = remote_output(args, ["nvidia-smi", "-q", "-x"])
    rows = inspect(xml)
    candidates = [row for row in rows if row["idle"] and (args.gpu is None or row["index"] == args.gpu)]
    if not candidates:
        raise RuntimeError("No idle GPU: requires no graphics/compute processes, <=64MiB and 0% utilization")
    return candidates[0], rows


def deploy(args):
    # Check keys, permissions, availability and local image before a large upload.
    image_info(IMAGE)
    gpu_snapshot(args)
    existing = remote_output(args, ["docker", "ps", "-aq", "--filter", "name=^/" + CONTAINER + "$"])
    if existing:
        raise RuntimeError(f"{CONTAINER} already exists; retain its job, or stop/remove your container before redeploying")
    source, tree = sync(args)
    ssh(args, ["python3", source + "/scripts/research/verify_assets.py", "--verify-only",
               "--destination", args.remote_root + "/assets", "--report",
               args.remote_root + "/outputs/asset-verification/results.json"])
    image = upload_image(args)
    # Re-evaluate after transfer, which can take a long time.
    gpu, rows = gpu_snapshot(args)
    command = ["docker", "run", "-d", "--name", CONTAINER, "--init", "--network", "host",
               "--shm-size", "16g", "--gpus", "device=" + gpu["uuid"],
               "--label", "php.research.owner=php-parkour", "--label", "php.research.source=" + tree,
               "-e", "ACCEPT_EULA=Y", "-e", "OMNI_KIT_ACCEPT_EULA=YES",
               "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "CUDA_VISIBLE_DEVICES=0",
               "-e", "LOGGER=tensorboard", "-e", "WANDB_MODE=disabled",
               "-e", "PHP_DOCKER=1", "-e", "PHP_MOTION_DATABASE_DIR=/data/assets/databases",
               "-v", source + ":/workspace/php_parkour",
               "-v", args.remote_root + "/outputs:/outputs",
               "-v", args.remote_root + "/outputs:/workspace/php_parkour/outputs/research",
               "-v", args.remote_root + "/logs:/workspace/php_parkour/logs",
               "-v", args.remote_root + "/assets:/data/assets",
               "-v", args.remote_root + "/cache:/data/cache", image["remote_id"], "sleep", "infinity"]
    ssh(args, command)
    record = {"created_utc": datetime.now(timezone.utc).isoformat(), "host": args.host,
              "container": CONTAINER, "source": source, "source_tree_sha256": tree,
              "gpu": gpu, "gpu_snapshot": rows, **image}
    path = ROOT / "outputs/research/cloud/deployment.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    transfer(args, path, args.host + ":" + args.remote_root + "/deployment.json")
    print(json.dumps(record, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="tencent-231")
    parser.add_argument("--remote-root", default="/diff/dzp_is_sb/php-parkour-research")
    parser.add_argument("--gpu", type=int, help="Require this idle GPU, otherwise use smallest idle ID")
    parser.add_argument("--detach", action="store_true", help="Run exec asynchronously inside Docker; redirect logs in your command")
    parser.add_argument("action", choices=["status", "sync", "upload-image", "deploy", "pull", "exec"])
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after exec (no shell expansion)")
    args = parser.parse_args()
    path = PurePosixPath(args.remote_root)
    if (not re.fullmatch(r"[A-Za-z0-9_@.][A-Za-z0-9_@.-]*", args.host)
            or not path.is_relative_to("/diff/dzp_is_sb") or ".." in path.parts):
        parser.error("Use an SSH host alias and a destination below /diff/dzp_is_sb")
    try:
        if args.action == "status":
            gpu, rows = gpu_snapshot(args)
            print(json.dumps({"selected": gpu, "gpus": rows}, indent=2))
        elif args.action == "sync":
            source, tree = sync(args)
            print(json.dumps({"source": source, "source_tree_sha256": tree}, indent=2))
        elif args.action == "deploy":
            deploy(args)
        elif args.action == "upload-image":
            record = upload_image(args)
            (ROOT / "outputs/research/cloud/image-transfer.json").write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(record, indent=2))
        elif args.action == "pull":
            (ROOT / "outputs/research/cloud/results").mkdir(parents=True, exist_ok=True)
            transfer(args, args.host + ":" + args.remote_root + "/outputs/",
                     str(ROOT / "outputs/research/cloud/results") + "/")
            transfer(args, args.host + ":" + args.remote_root + "/logs/", str(ROOT / "logs") + "/")
        elif args.action == "exec":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("exec requires a command")
            ssh(args, ["docker", "exec", *(["-d"] if args.detach else []), CONTAINER, *command])
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Cloud operation failed: {exc}\n")


if __name__ == "__main__":
    main()
