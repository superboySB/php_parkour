#!/usr/bin/env python3
"""Select the smallest process-free NVIDIA GPU from an nvidia-smi XML snapshot.

Uses the standard library only, on either host. Graphics processes count as
occupied. Unknown process/utilization information fails closed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def number(value: str | None) -> float | None:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:MiB|%)?\s*", value or "")
    return float(match[1]) if match else None


def inspect(xml: str, memory_limit: int = 64) -> list[dict]:
    rows = []
    for index, gpu in enumerate(ET.fromstring(xml).findall("gpu")):
        processes = gpu.find("processes")
        memory = number(gpu.findtext("fb_memory_usage/used"))
        utilization = number(gpu.findtext("utilization/gpu_util"))
        # nvidia-smi indices follow XML order, not Linux device minor numbers.
        # On the Tencent server GPU index 0 has minor 7. Docker receives a UUID
        # below so CUDA/PCI/minor enumeration cannot silently select another GPU.
        pids = [node.findtext("pid") for node in gpu.findall("processes/process_info")]
        known_processes = processes is not None and (processes.text or "").strip() in ("", "None")
        rows.append({
            "index": index, "minor_number": gpu.findtext("minor_number"),
            "uuid": gpu.findtext("uuid"),
            "name": gpu.findtext("product_name"), "memory_used_mib": memory,
            "utilization_percent": utilization, "pids": pids,
            "idle": known_processes and not pids and memory is not None
            and memory <= memory_limit and utilization == 0,
        })
    if not rows:
        raise ValueError("nvidia-smi reported no GPUs")
    return sorted(rows, key=lambda row: row["index"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin", action="store_true", help="Read nvidia-smi -q -x from stdin")
    parser.add_argument("--gpu", type=int, help="Require this specific GPU to be idle")
    parser.add_argument("--json", action="store_true", help="Print the complete audit snapshot")
    args = parser.parse_args()
    xml = sys.stdin.read() if args.stdin else subprocess.check_output(["nvidia-smi", "-q", "-x"], text=True)
    rows = inspect(xml)
    candidates = [row for row in rows if row["idle"] and (args.gpu is None or row["index"] == args.gpu)]
    selected = candidates[0] if candidates else None
    if args.json:
        print(json.dumps({"selected": selected, "gpus": rows}, indent=2))
    elif selected:
        print(selected["index"])
    if not selected:
        parser.exit(1, "No process-free GPU with <=64 MiB memory and zero utilization is available.\n")


if __name__ == "__main__":
    main()
