#!/usr/bin/env python3
"""Recover the frozen 02bc host monitor's missing-container inspection only.

The original CPU/GPU runner, selection identity and downstream transfer API stay
frozen. This separately recorded host wrapper owns the original monitor locks;
it never changes the old source tree or retries an existing native attempt.
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import fcntl
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

SOURCE_TREE = "02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c"
MONITOR_SHA = "58b8978cb24d8a194133e6344c1fa415632413d83c92b18a21ebcc3b75ed5dfc"
COVERAGE_DIRECTORY = "coverage-official-final-ro-assets-v2"
IMAGE = "sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def container_state(pc, args, source, role, name, input_identity):
    """The sole replacement function; retain every frozen identity guard."""
    result = subprocess.run(["docker", "container", "inspect", name], text=True, capture_output=True)
    if result.returncode:
        missing = {f"error: no such object: {name}".casefold(),
                   f"error: no such container: {name}".casefold(),
                   f"error response from daemon: no such container: {name}".casefold()}
        pc.require(result.returncode == 1 and result.stdout.strip() in ("", "[]")
                   and result.stderr.strip().casefold() in missing,
                   f"Cannot inspect own container: {result.stderr}")
        return None
    info = json.loads(result.stdout)[0]
    config, host = info["Config"], info["HostConfig"]
    pc.require(config["Labels"].get("php.posttrain.identity") == input_identity
               and config["Labels"].get("php.posttrain.role") == role and info["Image"] == args.image
               and host["NetworkMode"] == "none" and config.get("WorkingDir") == "/workspace/php_parkour"
               and config.get("Entrypoint") == ["/opt/php/bin/entrypoint"], "Existing container has another identity/image/role/network/entrypoint")
    mounts = {item["Destination"]: item for item in info["Mounts"]}
    pc.require(len(mounts) == len(info["Mounts"]) == 4
               and set(mounts) == {"/workspace/php_parkour", pc.OFFICIAL, "/data/assets", pc.COVERAGE},
               "Existing container has an extra mount overriding frozen inputs")
    for destination, source_path, writable in (("/workspace/php_parkour", source, False), (pc.OFFICIAL, args.official_output, False),
                                               ("/data/assets", args.root / "assets", False), (pc.COVERAGE, args.coverage_output, True)):
        mount = mounts.get(destination, {})
        pc.require(mount.get("Source") == str(source_path) and mount.get("RW") is writable,
                   "Existing container mount/access differs from the frozen cohort")
    environment = dict(item.split("=", 1) for item in config["Env"] if "=" in item)
    pc.require(environment.get("LOGGER") == "tensorboard" and environment.get("WANDB_MODE") == "disabled"
               and environment.get("CUDA_VISIBLE_DEVICES") == ("0" if role == "gpu" else ""), "Existing container environment changed")
    requests = host.get("DeviceRequests") or []
    if role == "gpu":
        pc.require(len(requests) == 1 and requests[0].get("DeviceIDs") == [args.gpu_uuid], "Existing container has another GPU UUID")
    else:
        pc.require(not requests and environment.get("NVIDIA_VISIBLE_DEVICES") == "void", "CPU preparation container exposes GPUs")
    expected = pc.docker_command(args, source, role, input_identity)[1]
    pc.require(config["Cmd"] == expected[expected.index(args.image) + 1:], "Existing coverage entry point differs")
    return info


def load_monitor(root):
    path = root / "source" / SOURCE_TREE / "scripts/research/posttrain_coverage.py"
    require(not path.is_symlink() and path.is_file() and digest(path) == MONITOR_SHA,
            "Recovery requires the exact original 02bc monitor bytes")
    spec = importlib.util.spec_from_file_location("recovered_frozen_posttrain_monitor", path)
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    return pc, path


def original_records(args):
    expected = {"selection.json", "monitor-status.json", "monitor.lock"}
    require({path.name for path in args.coverage_output.iterdir()} == expected,
            "Recovery is only for the untouched selection/rejected/lock directory; retain other partials separately")
    records = []
    for name in sorted(expected):
        path = args.coverage_output / name
        require(stat.S_ISREG(path.lstat().st_mode), f"Original recovery input is not a regular file: {name}")
        records.append({"name": name, "bytes": path.stat().st_size, "sha256": digest(path),
                        "mode": stat.S_IMODE(path.stat().st_mode)})
    return records


def preflight(pc, args):
    records = original_records(args)
    observation = pc.observe(args)
    require(observation.get("status") == "ready_for_cpu_verification_gpu_not_started",
            "Original scientific/source/process gates are not ready")
    selection = pc.read(args.coverage_output / "selection.json")
    require(selection == observation["selection"], "Actual observe differs from the preserved original selection")
    name = pc.docker_command(args, Path(observation["source"]), "cpu", selection["input_identity"])[0]
    old = pc.read(args.coverage_output / "monitor-status.json")
    error = old.get("error", "")
    prefix = "ValueError: Cannot inspect own container: "
    missing = {f"error: no such object: {name}".casefold(), f"error: no such container: {name}".casefold(),
               f"error response from daemon: no such container: {name}".casefold()}
    require(old.get("status") == "rejected" and error.startswith(prefix)
            and error[len(prefix):].strip().casefold() in missing,
            "Original rejection is not the exact missing CPU-container diagnostic")
    for role in ("cpu", "gpu"):
        own_name = pc.docker_command(args, Path(observation["source"]), role, selection["input_identity"])[0]
        require(pc.container_state(args, Path(observation["source"]), role, own_name, selection["input_identity"]) is None,
                "An existing coverage container must not be restarted by this recovery")
    require(original_records(args) == records, "Original partials changed during read-only preflight")
    return observation, records


def archive(pc, args, original_path, records, original_function):
    args.recovery_dir.mkdir(exist_ok=False)
    saved = args.recovery_dir / "original"
    saved.mkdir()
    for item in records:
        target = saved / item["name"]
        shutil.copy2(args.coverage_output / item["name"], target)
        require(digest(target) == item["sha256"] and target.stat().st_size == item["bytes"]
                and stat.S_IMODE(target.stat().st_mode) == item["mode"], "Original archive differs in bytes or permissions")
    require(original_records(args) == records, "Original inputs changed while archiving")
    wrapper = Path(__file__).resolve()
    shutil.copy2(wrapper, args.recovery_dir / wrapper.name)
    patch = "".join(difflib.unified_diff(inspect.getsource(original_function).splitlines(True),
                                       inspect.getsource(container_state).splitlines(True),
                                       fromfile="original/container_state", tofile="host-recovery/container_state"))
    patch_path = args.recovery_dir / "host-container-inspection.diff"
    patch_path.write_text(patch)
    receipt = {"schema_version": 1, "started_utc": pc.now(), "status": "archived_before_host_recovery",
               "actual_argv": sys.argv, "original_source_tree": SOURCE_TREE,
               "original_monitor": {"path": str(original_path), "sha256": MONITOR_SHA},
               "wrapper": {"path": str(wrapper), "sha256": digest(wrapper)},
               "patch_sha256": digest(patch_path), "original_files": records,
               "coverage_output": str(args.coverage_output), "selection_identity": pc.read(saved / "selection.json")["input_identity"],
               "host_control_changed": True, "frozen_cpu_gpu_runner_changed": False,
               "locks_held": [str(args.root / "outputs/.posttrain-coverage.lock"), str(args.coverage_output / "monitor.lock")],
               "scope": "Separate host loop and only one frozen function replacement; original scientific runner/input identity retained; no success inferred"}
    pc.write(args.recovery_dir / "execution.json", receipt)
    return receipt


def run(args):
    pc, original_path = load_monitor(args.root)
    original_function = pc.container_state
    pc.container_state = lambda *values: container_state(pc, *values)
    with contextlib.ExitStack() as locks:
        for path in (args.root / "outputs/.posttrain-coverage.lock", args.coverage_output / "monitor.lock"):
            require(not path.is_symlink() and path.is_file(), f"Original lock is missing/unsafe: {path}")
            stream = locks.enter_context(path.open("rb"))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        observation, records = preflight(pc, args)
        if args.action == "dry-run":
            print(json.dumps({"status": "recovery_preflight_passed_no_writes", "selection_identity": observation["selection"]["input_identity"],
                              "original_files": records, "wrapper_sha256": digest(__file__), "original_monitor_sha256": MONITOR_SHA}, indent=2))
            return 0
        receipt = archive(pc, args, original_path, records, original_function)
        try:
            while True:
                require(digest(__file__) == receipt["wrapper"]["sha256"], "Recovery wrapper changed during execution")
                if observation["status"] == "ready_for_cpu_verification_gpu_not_started":
                    observation = pc.advance(args, observation)
                status = {"observed_utc": pc.now(), **observation, "host_recovery_execution": str(args.recovery_dir / "execution.json")}
                pc.write(args.coverage_output / "monitor-status.json", status)
                with (args.recovery_dir / "observations.jsonl").open("a") as stream:
                    stream.write(json.dumps(status, allow_nan=False) + "\n")
                print(json.dumps(status, indent=2), flush=True)
                if args.action == "once" or observation["status"] in ("completed", "execution_failed"):
                    code = int(observation["status"] == "execution_failed")
                    receipt.update(status="host_recovery_invocation_finished", finished_utc=pc.now(), returncode=code,
                                   observation_status=observation["status"])
                    pc.write(args.recovery_dir / "execution.json", receipt)
                    return code
                time.sleep(args.poll_seconds)
                observation = pc.observe(args)
        except BaseException as error:
            receipt.update(status="host_recovery_failed", finished_utc=pc.now(), error=f"{type(error).__name__}: {error}", partial_evidence_retained=True)
            pc.write(args.recovery_dir / "execution.json", receipt)
            pc.write(args.coverage_output / "monitor-status.json", {"observed_utc": pc.now(), "status": "rejected", "error": receipt["error"],
                                                                  "host_recovery_execution": str(args.recovery_dir / "execution.json"), "quality_verified": False})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dry-run", "once", "watch"))
    parser.add_argument("--root", type=Path, default=Path("/diff/dzp_is_sb/php-parkour-research"))
    parser.add_argument("--recovery-dir", type=Path, required=True, help="Fresh sibling output directory for original bytes and the separate host receipt")
    parser.add_argument("--poll-seconds", type=float, default=60)
    parsed = parser.parse_args()
    for path in (parsed.root, parsed.recovery_dir):
        require(path.is_absolute() and not any(part.is_symlink() for part in (path, *path.parents)), "Use absolute paths without symlink ancestors")
    root, recovery = parsed.root.resolve(), parsed.recovery_dir.resolve()
    require(recovery.parent == root / "outputs" and recovery.name.startswith("posttrain-inspect-recovery-")
            and not recovery.exists(), "Recovery output must be a fresh posttrain-inspect-recovery-* sibling")
    require(parsed.poll_seconds >= 1, "Poll interval must be positive")
    args = SimpleNamespace(action=parsed.action, root=root, source_tree=SOURCE_TREE, image=IMAGE,
                           gpu_uuid="GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5", training_container="php-parkour-cloud-research",
                           official_output=root / "outputs/official-full", driver_log=root / "outputs/official-full-driver.log",
                           coverage_output=root / "outputs" / COVERAGE_DIRECTORY, recovery_dir=recovery,
                           poll_seconds=parsed.poll_seconds, resume_interrupted=False)
    return run(args)


if __name__ == "__main__":
    def terminated(_signum, _frame):
        raise KeyboardInterrupt("Owned host recovery received SIGTERM")
    signal.signal(signal.SIGTERM, terminated)
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print(json.dumps({"status": "rejected", "error": f"{type(error).__name__}: {error}", "quality_verified": False}), file=sys.stderr)
        raise SystemExit(1)
