#!/usr/bin/env python3
"""Run the project's complete CPU test suites inside the unified Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=os.environ.get("PHP_CONTAINER", "php-parkour-research"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/research/cpu-tests"))
    parser.add_argument("--timeout-s", type=int, default=1800)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output_dir.resolve()
    try:
        relative = output.relative_to(repo)
    except ValueError:
        parser.error("output directory must be inside the checkout mounted in Docker")
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    container_output = Path("/workspace/php_parkour") / relative
    groups = [
        ("root-training", "/workspace/php_parkour", "train-python", ["tests", "wbt_training/tests"]),
        ("motion-matching", "/workspace/php_parkour/motion_matching", "motion-python", ["tests"]),
    ]
    report = {"schema_version": 1, "container": args.container, "groups": []}
    for name, cwd, python, tests in groups:
        xml = output / (name + ".xml")
        command = ["docker", "exec", "-e", "CUDA_VISIBLE_DEVICES=", "-e", "PHP_DOCKER=0", "-w", cwd, args.container,
                   "/opt/php/bin/" + python, "-m", "pytest", "-q", *tests,
                   "--junitxml=" + str(container_output / xml.name)]
        started = time.monotonic()
        row = {"name": name, "status": "failed", "command": command}
        log = output / (name + ".log")
        with log.open("w") as stream:
            try:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout_s, check=False)
                row["exit_code"] = result.returncode
                if xml.is_file():
                    root = ET.parse(xml).getroot()
                    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
                    for key in ("tests", "errors", "failures", "skipped"):
                        row[key] = sum(int(suite.get(key, 0)) for suite in suites)
                    row["passed"] = row["tests"] - row["errors"] - row["failures"] - row["skipped"]
                    if result.returncode == 0 and row["errors"] + row["failures"] == 0:
                        row["status"] = "passed"
            except subprocess.TimeoutExpired:
                row["error"] = f"timeout after {args.timeout_s} seconds"
        row["wall_seconds"] = round(time.monotonic() - started, 3)
        row["log"] = str(log)
        row["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        report["groups"].append(row)
        report["failed_groups"] = sum(item["status"] != "passed" for item in report["groups"])
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {row['status']}; {row.get('passed', 0)} passed, {row.get('failures', 0)} failed, {row.get('skipped', 0)} skipped", flush=True)
    if report["failed_groups"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
