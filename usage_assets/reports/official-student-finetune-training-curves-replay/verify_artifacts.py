#!/usr/bin/env python3
"""Verify the sealed replay files and optionally restore two large originals."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    package = Path(__file__).absolute().parent
    helper = package / "student_curves_archive.py"
    if hashlib.sha256(helper.read_bytes()).hexdigest() != "068c13d5e8e61a7e7a4b80b2813a96ac617efee408674e9fe1f65a498b50dcc2":
        raise ValueError("Reviewed archive helper SHA differs")
    spec = importlib.util.spec_from_file_location("archive_helpers", helper)
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    manifest = package / "evidence-manifest.json"
    archive.require(archive.fingerprint(manifest)["sha256"] == args.manifest_sha256,
                    "Explicit replay manifest SHA differs")
    value = archive.load(manifest)
    archive.require(value["status"] == "completed_finetune_curves_replay_publication",
                    "Completed replay evidence required")
    expected = set()
    for row in value["files"]:
        relative = archive.relative(row["path"])
        archive.require(str(relative) not in expected, "Duplicate publication path")
        expected.add(str(relative))
        actual = archive.fingerprint(package.joinpath(*relative.parts))
        archive.require(archive.body(actual) == archive.body(row) and actual["bytes"] <= archive.LIMIT,
                        "Sealed publication file differs")
    actual_paths = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
    archive.require(actual_paths == expected | {"evidence-manifest.json"}, "Publication file set differs")
    mapping = archive.load(package / "compressed-artifacts.json")
    archive.require(mapping["status"] == "lossless_replay_artifacts" and len(mapping["records"]) == 2,
                    "Both original replay artifacts required")
    for row in mapping["records"]:
        archive.decode_record(package, row)
    if args.output:
        output = archive.fresh(args.output, [package])
        output.mkdir(parents=True)
        for row in mapping["records"]:
            target = output.joinpath(*archive.relative(row["logical_path"]).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                archive.decode_record(package, row, stream)
            target.chmod(row["mode"])
            archive.require(archive.body(archive.fingerprint(target)) == archive.body(row),
                            "Restored original differs")
    print(json.dumps({"status": "verified_finetune_curve_replay_package",
                      "files": len(expected), "originals": 2,
                      "restored": str(args.output.absolute()) if args.output else None}))


if __name__ == "__main__":
    main()
