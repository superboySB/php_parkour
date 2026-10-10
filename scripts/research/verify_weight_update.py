#!/usr/bin/env python3
"""Compare two real native checkpoints without starting a simulator or GPU job.

This is evidence of changed network weights, not proof of convergence or a
replacement for rollout quality metrics. It is intentionally separate from the
official save schedule: use model_00000/model_00001 from a two-step smoke run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    import torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def read(path: Path):
        data = torch.load(path, map_location="cpu", weights_only=False)
        if not isinstance(data, dict) or not isinstance(data.get("iter"), int):
            raise ValueError(f"Invalid native checkpoint: {path}")
        tensors = {}
        def visit(value, name):
            if isinstance(value, torch.Tensor):
                if (value.is_floating_point() or value.is_complex()) and not torch.isfinite(value).all().item():
                    raise ValueError(f"Non-finite tensor {name} in {path}")
                tensors[name] = value
            elif isinstance(value, dict):
                for key, item in value.items():
                    visit(item, f"{name}.{key}" if name else str(key))
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    visit(item, f"{name}[{index}]")
        if isinstance(data.get("model_state_dict"), dict):
            visit(data["model_state_dict"], "policy")
        else:
            for section in ("actor_model_state_dict", "critic_model_state_dict"):
                if not isinstance(data.get(section), dict):
                    raise ValueError(f"Missing policy state {section} in {path}")
                visit(data[section], "actor" if section.startswith("actor") else "critic")
        if not tensors:
            raise ValueError(f"No native policy tensors: {path}")
        return data["iter"], tensors

    iteration0, before = read(args.before)
    iteration1, after = read(args.after)
    if iteration1 <= iteration0 or before.keys() != after.keys():
        raise ValueError("Compare increasing iterations from the same native policy architecture")
    groups = {}
    for name, previous in before.items():
        current = after[name]
        if previous.shape != current.shape or previous.dtype != current.dtype:
            raise ValueError(f"Policy tensor schema changed: {name}")
        if not (previous.is_floating_point() or previous.is_complex()):
            continue
        group = name.split(".")[0] if name.startswith(("actor.", "critic.")) else name.split(".")[1]
        summary = groups.setdefault(group, {"tensors": 0, "changed_tensors": 0, "elements": 0, "changed_elements": 0, "max_abs_difference": 0.0, "changed_network_weights": []})
        difference = (current - previous).abs()
        changed = int(torch.count_nonzero(difference).item())
        summary["tensors"] += 1
        summary["changed_tensors"] += int(changed > 0)
        summary["elements"] += previous.numel()
        summary["changed_elements"] += changed
        summary["max_abs_difference"] = max(summary["max_abs_difference"], float(difference.max().item()) if difference.numel() else 0)
        if changed and name.endswith((".weight", ".bias")):
            summary["changed_network_weights"].append(name)
    updated = any(value["changed_network_weights"] for name, value in groups.items() if name in ("actor", "student", "depth_backbone"))
    report = {"status": "passed" if updated else "failed", "scope": "Real policy tensor difference between saved iterations; not proof of locomotion quality or convergence",
              "before": {"path": str(args.before.resolve()), "iteration": iteration0, "sha256": hashlib.sha256(args.before.read_bytes()).hexdigest()},
              "after": {"path": str(args.after.resolve()), "iteration": iteration1, "sha256": hashlib.sha256(args.after.read_bytes()).hexdigest()},
              "groups": groups, "nontrivial_policy_weight_change_verified": updated, "quality_verified": False}
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not updated:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
