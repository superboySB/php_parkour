#!/usr/bin/env python3
"""Record the three image runtimes; no simulator or training process starts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


PROBES = {
    "train": """
import importlib.metadata as md, json, sys
from pathlib import Path
import holosoma, wbt_training, mujoco, numpy, torch, unitree_interface
print(json.dumps(dict(python=sys.version, executable=sys.executable,
    numpy=numpy.__version__, torch=torch.__version__, mujoco=mujoco.__version__,
    isaaclab=Path('/workspace/isaaclab/VERSION').read_text().strip(),
    isaaclab_package=md.version('isaaclab'), isaacsim=Path('/isaac-sim/VERSION').read_text().strip(),
    torch_cuda=torch.version.cuda, cuda_available=torch.cuda.is_available(),
    cuda_devices=torch.cuda.device_count(), holosoma=holosoma.__file__,
    gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    php=wbt_training.__file__, unitree_sdk=unitree_interface.__file__)))
""",
    "motion": """
import json, sys, numpy, scipy, mujoco, motion_matching, tkinter
print(json.dumps(dict(python=sys.version, executable=sys.executable,
    numpy=numpy.__version__, scipy=scipy.__version__, mujoco=mujoco.__version__,
    motion_matching=motion_matching.__file__, tkinter=tkinter.TkVersion)))
""",
    "inference": """
import json, sys, numpy, onnxruntime, pinocchio, holosoma_inference, unitree_interface
from holosoma_inference.policies.depth_distillation import DepthDistillationPolicy
print(json.dumps(dict(python=sys.version, executable=sys.executable,
    numpy=numpy.__version__, pinocchio=pinocchio.__version__,
    onnxruntime=onnxruntime.__version__, providers=onnxruntime.get_available_providers(),
    inference=holosoma_inference.__file__, unitree_sdk=unitree_interface.__file__)))
""",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/outputs/docker/runtime.json"))
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()
    report = {}
    for name, program in PROBES.items():
        proc = subprocess.run(
            [f"/opt/php/bin/{name}-python", "-c", program],
            text=True, capture_output=True, check=False,
        )
        result = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        if proc.returncode == 0:
            try:
                result["versions"] = json.loads(proc.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError) as exc:
                result["parse_error"] = str(exc)
        report[name] = result
    report["passed"] = all(item["returncode"] == 0 and "versions" in item for item in report.values())
    if args.require_gpu:
        report["passed"] &= report["train"].get("versions", {}).get("cuda_available", False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
