#!/usr/bin/env python3
"""Validate the final native ONNX paired with each recorded teacher checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

SKILLS = ("locomotion", "low-step", "high-step", "low-climb-76", "high-climb-76")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/outputs/official-training"))
    parser.add_argument("--profile", choices=("official", "smoke"), default="official")
    parser.add_argument("--skills", nargs="+", choices=SKILLS, default=list(SKILLS))
    parser.add_argument("--inference-python", default="/opt/php/bin/inference-python")
    args = parser.parse_args()
    run_root = args.output.resolve() / args.profile
    report_root = run_root / "teacher-onnx-validation"
    report_root.mkdir(parents=True, exist_ok=True)
    summary = {"status": "running", "profile": args.profile, "teachers": [],
               "scope": "Final native teacher graph execution/reference contract and checkpoint provenance; not PT/ONNX parity or policy quality"}
    try:
        for skill in args.skills:
            manifest = json.loads((run_root / "manifests" / f"teacher-{skill}.json").read_text())
            checkpoint = Path(manifest["checkpoint"])
            if (manifest.get("status") != "passed" or manifest.get("profile") != args.profile
                    or manifest.get("label") != f"teacher-{skill}"
                    or sha(checkpoint) != manifest.get("checkpoint_sha256")
                    or manifest.get("checkpoint_iteration", -1) < (19999 if args.profile == "official" else 1)):
                raise ValueError(f"Teacher checkpoint provenance/iteration is incomplete: {skill}")
            graph = checkpoint.with_suffix(".onnx")
            result_path = report_root / f"{skill}.json"
            subprocess.run([args.inference_python, str(Path(__file__).with_name("validate_teacher_onnx.py")),
                            "--model", str(graph), "--output", str(result_path)], check=True)
            result = json.loads(result_path.read_text())
            if result.get("status") != "passed" or result.get("sha256") != sha(graph):
                raise ValueError(f"Teacher graph changed during validation: {skill}")
            if json.loads(result["metadata"]["iteration"]) != manifest["checkpoint_iteration"]:
                raise ValueError(f"Teacher graph iteration differs from its checkpoint: {skill}")
            graph_config = json.loads(result["metadata"]["experiment_config"])
            if graph_config["training"]["registry_name"] != manifest["environment"]["REGISTRY"]:
                raise ValueError(f"Teacher graph registry differs from its training inputs: {skill}")
            summary["teachers"].append({"skill": skill, "checkpoint": str(checkpoint),
                                        "checkpoint_sha256": manifest["checkpoint_sha256"],
                                        "onnx": str(graph), "onnx_sha256": result["sha256"],
                                        "cpu_cases": len(result["cases"]), "report": str(result_path)})
        summary["status"] = "passed"
    except Exception as error:
        summary.update(status="failed", error=str(error))
        raise
    finally:
        (report_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Validated final native teacher graphs: {len(summary['teachers'])}")


if __name__ == "__main__":
    main()
