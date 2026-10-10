#!/usr/bin/env python3
"""Verify offline database baking, local file:// bundles, and Viser/Tk startup.

Run with motion-python inside Docker after motion_matching_matrix.py.
All data is materialized locally and content-checked. Remote SDK imports are
blocked; no account, cloud registry, or external network is needed.
Server checks confirm HTTP and full G1/motion initialization, not browser
interaction. --interactive-gui additionally checks a real Tk display.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


class OfflineImportGuard(importlib.abc.MetaPathFinder):
    """Make accidental remote experiment SDK use fail before initialization."""

    def __init__(self):
        self.attempts = 0

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "wandb" or fullname.startswith("wandb."):
            self.attempts += 1
            raise RuntimeError("remote experiment SDK imports are disabled in this offline workflow")
        return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def server_check(command: list[str], port: int, markers: list[str], log: Path, timeout: float) -> dict:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"port {port} is already occupied; refusing to test another server")
    status = {"command": command, "port": port, "scope": "bounded HTTP/server initialization"}
    started = time.monotonic()
    with log.open("w") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic() - started < timeout:
                if process.poll() is not None:
                    raise RuntimeError(f"server exited early with code {process.returncode}")
                content = log.read_text(errors="replace")
                if "Traceback (most recent call last)" in content:
                    raise RuntimeError("server or GUI child printed a traceback")
                if all(marker in content for marker in markers):
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                            payload = response.read()
                            if response.status == 200 and b"<html" in payload.lower():
                                status.update(status="passed", http_status=200, response_bytes=len(payload), response_sha256=hashlib.sha256(payload).hexdigest())
                                break
                    except OSError:
                        pass
                time.sleep(0.25)
            else:
                raise TimeoutError(f"server did not initialize within {timeout} seconds")
        finally:
            # The Tk subprocess shares this newly-created process group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
    status["wall_seconds"] = round(time.monotonic() - started, 3)
    status["log_sha256"] = sha256(log)
    return status


def main() -> None:
    # motion-python installs the motion package; training helpers are mounted
    # alongside it and remain importable when Python starts from this script.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--registry-probe", help=argparse.SUPPRESS)
    parser.add_argument("--interactive-gui", action="store_true")
    parser.add_argument("--timeout-s", type=int, default=180)
    args = parser.parse_args()
    guard = OfflineImportGuard()
    sys.meta_path.insert(0, guard)
    if "wandb" in sys.modules:
        raise RuntimeError("remote SDK was loaded before the offline import guard")
    if args.registry_probe:
        from wbt_training.utils.registry import RegistryResolver, main as registry_main
        if registry_main(["teacher", "", args.registry_probe]) != 0:
            raise RuntimeError("local registry CLI failed")
        resolved = RegistryResolver().resolve(args.registry_probe)
        if len(resolved) != 1 or resolved[0].local_uri != args.registry_probe or guard.attempts:
            raise RuntimeError("local registry resolution used an unexpected path or remote SDK")
        print("OFFLINE_LOCAL_REGISTRY_RESOLVED; REMOTE_SDK_IMPORTS=0", file=sys.stderr)
        return
    if args.matrix is None or args.output_dir is None:
        parser.error("--matrix and --output-dir are required")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads(args.matrix.read_text())
    motions = [(row["name"], Path(row["result"]["configurations"][0]["files"][0]["path"])) for row in matrix["scenarios"] if row["status"] == "passed"]
    if not motions:
        parser.error("matrix must contain at least one passed scenario")
    from motion_matching.core.database import MotionMatchingDatabase
    from motion_matching.utils import DATABASE_DIR, ROBOT_MOTIONS_DIR
    report = {"schema_version": 1, "matrix_sha256": sha256(args.matrix), "checks": [], "data_transport": "local file:// only", "requires_external_network": False, "remote_sdk_imports_blocked": True}

    def record(name: str, function) -> None:
        item = {"name": name, "status": "failed"}
        try:
            item.update(function())
            item["status"] = "passed"
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        report["checks"].append(item)
        report["failed"] = sum(row["status"] != "passed" for row in report["checks"])
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {item['status']}", flush=True)

    def bake() -> dict:
        terrain = output / "source-terrain" / "box.obj"
        terrain.parent.mkdir()
        source_terrain = DATABASE_DIR / "terrain/climb_76_high_speed/box.obj"
        shutil.copy2(source_terrain, terrain)
        shutil.copy2(source_terrain.with_suffix(".json"), terrain.with_suffix(".json"))
        source_motion = ROBOT_MOTIONS_DIR / "climb_76_high_speed_up.npz"
        command = [sys.executable, "-m", "motion_matching.generate_database", "--motion-file", str(source_motion), "--terrain-file", str(terrain), "--fps", "30", "--output", "research_source.bin"]
        env = {**os.environ, "PHP_MOTION_DATABASE_DIR": str(output / "baked-database")}
        log = output / "bake.log"
        with log.open("w") as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout_s, check=False)
        if result.returncode:
            raise RuntimeError(f"database builder exited {result.returncode}")
        database = output / "baked-database/research_source.bin"
        db = MotionMatchingDatabase()
        db.load_from_file(str(database))
        import numpy as np
        with np.load(source_motion, allow_pickle=False) as data:
            source_frames = len(data["qpos"])
        if db.nframes() != source_frames * 4 or db.nbones() != 31 or len(db.range_starts) != 2:
            raise ValueError("unexpected source-resampling/mirror database dimensions")
        return {"command": command, "source_frames_30hz": source_frames,
                "database_frames_60hz": db.nframes(), "bones": db.nbones(), "mirrored_ranges": len(db.range_starts),
                "database": str(database), "database_sha256": sha256(database), "log_sha256": sha256(log)}

    record("source_motion_database_bake", bake)
    from wbt_training.utils.registry import bundle_pairs, validate_bundle
    from wbt_training.training_runs.motion_convert import convert
    import numpy as np

    def local_bundle(name: str, source: Path, convert_tracking: bool) -> dict:
        destination = output / "local-bundles" / name
        destination.mkdir(parents=True)
        rows = []
        pairs = bundle_pairs(source)
        for motion, terrain, obj in pairs:
            if terrain is None:
                raise ValueError(f"missing paired terrain: {motion}")
            target = destination / motion.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if convert_tracking:
                if not convert(str(motion), str(target)):
                    raise ValueError(f"motion conversion failed: {motion}")
            else:
                shutil.copy2(motion, target)
            paths = [(motion, target, convert_tracking)]
            for sidecar in (terrain, obj):
                if sidecar is not None:
                    copied = destination / sidecar.relative_to(source)
                    shutil.copy2(sidecar, copied)
                    paths.append((sidecar, copied, False))
            with np.load(target, allow_pickle=False) as native:
                if native["joint_pos"].shape[1] != 36 or native["joint_vel"].shape[1] != 35 or native["body_pos_w"].shape[1:] != (32, 3):
                    raise ValueError(f"incorrect native schema: {target}")
                for key in ("joint_pos", "joint_vel", "body_pos_w", "body_quat_w", "body_lin_vel_w", "body_ang_vel_w"):
                    if not np.isfinite(native[key]).all():
                        raise ValueError(f"nonfinite native array {key}: {target}")
            for original, copied, converted in paths:
                original_hash, copied_hash = sha256(original), sha256(copied)
                if not converted and original_hash != copied_hash:
                    raise ValueError(f"local bundle copy checksum mismatch: {copied}")
                rows.append({"source": str(original), "file": copied.relative_to(destination).as_posix(),
                             "converted_to_native": converted, "source_sha256": original_hash,
                             "sha256": copied_hash, "size": copied.stat().st_size})
        manifest = destination / "bundle-sha256.json"
        manifest.write_text(json.dumps({"schema_version": 1, "source": str(source), "files": rows}, indent=2) + "\n")
        # Re-read persisted files and the actual training registry CLI instead
        # of trusting the in-memory copy/conversion bookkeeping.
        for row in json.loads(manifest.read_text())["files"]:
            persisted = destination / row["file"]
            if persisted.stat().st_size != row["size"] or sha256(persisted) != row["sha256"]:
                raise ValueError(f"persisted bundle checksum mismatch: {persisted}")
        validate_bundle(destination)
        uri = destination.as_uri()
        command = [sys.executable, str(Path(__file__).resolve()), "--registry-probe", uri]
        log = output / ("registry-" + name + ".log")
        with log.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout_s, check=False)
        content = log.read_text()
        if result.returncode or uri not in content or "REMOTE_SDK_IMPORTS=0" not in content:
            raise RuntimeError(f"local registry CLI/resolver failed: {name}")
        return {"source_directory": str(source), "local_uri": uri, "materialized_directory": str(destination),
                "clips": len(pairs), "payload_files": len(rows), "input_format": "tracking" if convert_tracking else "native",
                "output_format": "native", "all_payload_checksums_reverified": True,
                "manifest": str(manifest), "manifest_sha256": sha256(manifest), "manifest_bytes": manifest.stat().st_size,
                "command": command, "log_sha256": sha256(log), "remote_sdk_imports": 0,
                "scope": "complete local materialization, native schema/pair validation, persisted SHA-256, actual file:// registry CLI/resolver"}

    for component in ("motions-locomotion", "motions-low-step", "motions-high-step", "motions-low-climb-76", "motions-high-climb-76"):
        record("local_native_bundle_" + component, lambda component=component: local_bundle(component, DATABASE_DIR.parent / component, False))
    for name, motion in motions:
        record("local_generated_bundle_" + name, lambda name=name, motion=motion: local_bundle(name, motion.parent, True))
    name, motion = motions[0]
    record("generated_motion_viser", lambda: server_check(
        [sys.executable, "-u", "-m", "motion_matching.motion_visualizer", "--motion-file", str(motion.parent)],
        8080, ["Loaded NPZ motion data", "Starting animation loop", "Viser server started"], output / "motion-viser.log", args.timeout_s))
    record("database_viser", lambda: server_check(
        [sys.executable, "-u", "-m", "motion_matching.play_database", "--database", "database_g1_locomotion.bin"],
        8081, ["Loaded G1 URDF for visualization"], output / "database-viser.log", args.timeout_s))
    if args.interactive_gui:
        def gui() -> dict:
            import tkinter
            window = tkinter.Tk()
            window.withdraw()
            window.update()
            window.destroy()
            result = server_check([sys.executable, "-u", "-m", "motion_matching.run", "--mode", "interactive"], 8081,
                                  ["Loaded G1 URDF for visualization", "GUI keyboard controller started"], output / "interactive-viser.log", args.timeout_s)
            result["scope"] = "real Tk window creation and bounded official interactive server startup"
            result["display"] = os.environ.get("DISPLAY")
            return result
        record("interactive_tk_viser", gui)
    else:
        report["interactive_gui"] = "not checked; rerun in GUI Docker with --interactive-gui"
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    report["remote_sdk_import_attempts"] = guard.attempts
    report["remote_sdk_loaded"] = "wandb" in sys.modules
    if guard.attempts or report["remote_sdk_loaded"]:
        report["failed"] += 1
    report["materialized_native_clips"] = sum(row.get("clips", 0) for row in report["checks"] if row["status"] == "passed")
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
