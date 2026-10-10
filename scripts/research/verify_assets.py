#!/usr/bin/env python3
"""Download all public bundles and record checksum verification (stdlib only)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("outputs/research/assets"))
    parser.add_argument("--report", type=Path, default=Path("outputs/research/asset-verification/results.json"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "download_assets.py"
    spec = importlib.util.spec_from_file_location("php_download_assets", source)
    downloader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(downloader)
    manifest = json.loads(downloader.MANIFEST.read_text())
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": downloader.sha256(downloader.MANIFEST),
        "destination": str(args.destination.resolve()),
        "components": [],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    for name in manifest["components"]:
        started = time.monotonic()
        item = {"name": name, "status": "failed"}
        try:
            component = downloader.read_component(downloader.MANIFEST, name)
            destination = args.destination / name
            changed = False if args.verify_only else downloader.fetch(component, destination)
            problems = downloader.verify(component, destination)
            if problems:
                raise ValueError("; ".join(problems))
            item.update(
                status="passed", downloaded=changed,
                file_count=len(component["files"]),
                total_file_bytes=sum(entry["size"] for entry in component["files"]),
                archive=component["archive"],
                files=component["files"],
            )
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        item["wall_seconds"] = round(time.monotonic() - started, 3)
        report["components"].append(item)
        report["passed"] = sum(row["status"] == "passed" for row in report["components"])
        report["failed"] = sum(row["status"] != "passed" for row in report["components"])
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {item['status']} ({item['wall_seconds']} s)", flush=True)
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
