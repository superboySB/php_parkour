#!/usr/bin/env python3
"""Record unresolved historical hash failures alongside actual baseline parity."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    failures, classification = [], {}
    for case in ET.parse(args.junit).getroot().iter("testcase"):
        failure = case.find("failure")
        if failure is None:
            continue
        detail = failure.text or ""
        test = case.get("classname", "") + "::" + case.get("name", "")
        category = next((label for needle, label in (
            ("test_golden_generation", "end_to_end_generation"), ("test_urdf_kinematics_char", "URDF_forward_kinematics"),
            ("TestDataUtilsResample", "resampling"), ("TestQposToTracking", "MuJoCo_tracking_conversion"),
            ("TestRandomizeBox", "box_randomization")) if needle in test), "unclassified")
        classification[category] = classification.get(category, 0) + 1
        failures.append({"test": test, "classification": category,
                         "status": "failed", "message": failure.get("message"),
                         "full_hashes_in_failure": list(dict.fromkeys(re.findall(r"\b[a-f0-9]{64}\b", detail))),
                         "failure_detail": detail})
    baseline = json.loads(args.baseline_report.read_text())
    report = {"schema_version": 1, "status": "unresolved historical hash failures",
              "count": len(failures), "failures": failures,
              "classification": classification,
              "same_image_baseline_revision": baseline["baseline_revision"],
              "baseline_array_comparisons": len(baseline["arrays"]),
              "baseline_failed": baseline["failed"],
              "python310_diagnostic": json.loads(args.diagnostic.read_text()),
              "conclusion": "The research changes reproduce unmodified-source arrays exactly. The historical tests still fail; their SHA-256-only reference cannot quantify a discrepancy or establish its cause without the original mm_hs arrays/environment.",
              "sources": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in (args.junit, args.baseline_report, args.diagnostic)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Recorded {len(failures)} unresolved failures; baseline comparison failed={baseline['failed']}")


if __name__ == "__main__":
    main()
