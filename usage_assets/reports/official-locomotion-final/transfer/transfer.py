#!/usr/bin/env python3
"""Download only the four observed final teacher artifacts; never alter remote files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
OBSERVATION = BASE.parent / "first-teacher-terminal-observation-20261010T165258Z.json"
HOST = "tencent-231"
REMOTE = "/diff/dzp_is_sb/php-parkour-research/outputs/official-full/official/teacher-locomotion/PHP-research/20261010_042104-teacher-locomotion-locomotion"
SSH = ["ssh", "-p", "22", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
       "-o", "StrictHostKeyChecking=accept-new", "-o", "ControlMaster=auto",
       "-o", "ControlPersist=10m", "-o", "ControlPath=~/.ssh/php-parkour-%C"]
REMOTE_HASH = r'''import hashlib,json,os,stat,sys
result=[]
for name in sys.argv[1:]:
    before=os.lstat(name)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Regular observed artifact required: "+name)
    h=hashlib.sha256()
    with open(name,"rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    after=os.lstat(name)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode)
    if identity(before)!=identity(after):
        raise ValueError("Source changed while hashing: "+name)
    result.append({"path":name,"bytes":after.st_size,"sha256":h.hexdigest()})
print(json.dumps(result,sort_keys=True))
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular file required: " + str(path))
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": value.hexdigest()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def process(label, argv, stdin=None):
    record = {"argv": argv, "started_utc": now(), "stdout": str(BASE / (label + ".stdout.raw")),
              "stderr": str(BASE / (label + ".stderr.raw"))}
    save(BASE / (label + ".launch.json"), record)
    with Path(record["stdout"]).open("xb") as out, Path(record["stderr"]).open("xb") as err:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err)
        record["pid"] = child.pid
        save(BASE / (label + ".launch.json"), record)
        if stdin is not None:
            child.stdin.write(stdin)
            child.stdin.close()
        record["returncode"] = child.wait()
    record["finished_utc"] = now()
    record["stdout_fingerprint"] = fingerprint(Path(record["stdout"]))
    record["stderr_fingerprint"] = fingerprint(Path(record["stderr"]))
    save(BASE / (label + ".exit.json"), record)
    if record["returncode"] != 0:
        raise RuntimeError(label + " exited " + str(record["returncode"]))
    return record


def remote_hash(label, records):
    argv = SSH + [HOST, shlex.join(["python3", "-", *[record["path"] for record in records]])]
    receipt = process(label, argv, REMOTE_HASH.encode())
    actual = json.loads(Path(receipt["stdout"]).read_bytes())
    if actual != records:
        save(BASE / (label + ".mismatch.json"), {"expected": records, "actual": actual})
        raise ValueError(label + " differs from the observed source bytes/SHA")
    return actual


def main():
    with (BASE / "receipt.json").open("x"):
        pass
    receipt = {"schema_version": 1, "status": "running", "started_utc": now(),
               "helper": fingerprint(Path(__file__).resolve()), "remote_read_only": True,
               "training_or_inference_started": False, "remote_files_modified": False}
    save(BASE / "receipt.json", receipt)
    try:
        raw = OBSERVATION.read_bytes()
        observation = json.loads(raw)
        manifest = observation["manifest"]
        if (manifest["label"] != "teacher-locomotion" or manifest["profile"] != "official"
                or manifest["status"] != "passed" or manifest["returncode"] != 0
                or manifest["checkpoint_iteration"] != 19999):
            raise ValueError("Expected terminal official locomotion teacher observation")
        artifacts = observation["artifacts"]
        expected_names = {"model_19999.pt", "model_19999.onnx", "holosoma_config.yaml",
                          "events.out.tfevents.1791606211.pro5000-6.47700.0"}
        if (len(artifacts) != 4 or {Path(item["path"]).name for item in artifacts} != expected_names
                or any(str(Path(item["path"]).parent) != REMOTE for item in artifacts)
                or any(type(item["bytes"]) is not int or item["bytes"] <= 0
                       or len(item["sha256"]) != 64 for item in artifacts)):
            raise ValueError("Exactly the four observed artifacts under the fixed source directory required")
        checkpoint = next(item for item in artifacts if item["path"].endswith(".pt"))
        if checkpoint["sha256"] != manifest["checkpoint_sha256"]:
            raise ValueError("Observed checkpoint hash differs from terminal manifest")
        (BASE / "observation.json").write_bytes(raw)
        receipt["observation"] = fingerprint(BASE / "observation.json")
        receipt["expected_artifacts"] = artifacts
        remote_script = BASE / "remote_hash.py"
        remote_script.write_text(REMOTE_HASH)
        receipt["remote_hash_helper"] = fingerprint(remote_script)
        target = BASE / "artifacts"
        target.mkdir(exist_ok=False)
        receipt["remote_before"] = remote_hash("source-before", artifacts)
        file_list = BASE / "rsync-files.txt"
        file_list.write_text("".join(Path(item["path"]).name + "\n" for item in artifacts))
        argv = ["rsync", "-a", "--no-owner", "--no-group", "--protect-args", "--info=progress2",
                "--partial-dir=.rsync-partial", "--files-from", str(file_list), "-e", shlex.join(SSH),
                HOST + ":" + REMOTE + "/", str(target) + "/"]
        receipt["rsync"] = process("rsync", argv)
        local = [fingerprint(target / Path(item["path"]).name) for item in artifacts]
        for expected, actual in zip(artifacts, local):
            if any(actual[key] != expected[key] for key in ("bytes", "sha256")):
                raise ValueError("Downloaded artifact differs: " + actual["path"])
        if {path.name for path in target.iterdir()} != expected_names:
            raise ValueError("Unexpected or partial artifact files retained; inspect before any reuse")
        receipt["local_artifacts"] = local
        receipt["artifact_mapping"] = [{"source": expected, "local": actual}
                                       for expected, actual in zip(artifacts, local)]
        receipt["remote_after"] = remote_hash("source-after", artifacts)
        if fingerprint(OBSERVATION)["sha256"] != receipt["observation"]["sha256"]:
            raise ValueError("Original terminal observation changed during transfer")
        if fingerprint(Path(__file__).resolve()) != receipt["helper"]:
            raise ValueError("Transfer helper changed during execution")
        receipt.update(status="completed", verified_artifact_count=4,
                       verified_artifact_bytes=sum(item["bytes"] for item in artifacts),
                       original_observation=fingerprint(OBSERVATION))
    except BaseException as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        receipt["finished_utc"] = now()
        save(BASE / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "verified_artifact_count", "verified_artifact_bytes")}))


if __name__ == "__main__":
    main()
