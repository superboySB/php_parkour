"""Actual seven smoke PT payloads, CPU only; no canonical schedule assertion."""
import json
from pathlib import Path
import sys
sys.path.insert(0, "/workspace/php_parkour")
import torch
from scripts.research.posttrain_coverage import SKILLS, compare_frozen_experts, digest

root = Path("/outputs/final-cloud-acceptance/results/smoke")
def load(label):
    manifest = json.loads((root / "manifests" / f"{label}.json").read_text())
    path = Path(manifest["checkpoint"].replace("/outputs/final-training-acceptance/smoke", str(root), 1))
    assert digest(path) == manifest["checkpoint_sha256"]
    data = torch.load(path, map_location="cpu", weights_only=False)
    return data, {"path": str(path), "sha256": digest(path), "iteration": data["iter"]}
teachers, inputs = [], []
for skill in SKILLS:
    data, record = load(f"teacher-{skill}")
    teachers.append(data)
    inputs.append(record)
results = []
for kind in ("pure", "finetune"):
    data, record = load(f"student-{kind}")
    report = compare_frozen_experts(data, teachers, torch)
    assert [entry["actor_tensors"] for entry in report] == [8] * 5
    assert [entry["normalizer_tensors"] for entry in report] == [3] * 5
    results.append({"kind": kind, "checkpoint": record, "experts": report, "total_verified_frozen_tensors": 55})
assert not torch.cuda.is_initialized()
output = {"status": "passed", "scope": "Actual final bounded-smoke PT naming, all five ordered frozen actor tensors and normalizer buffers; not official iterations or policy quality",
          "cuda_initialized": False, "teachers": inputs, "students": results,
          "teacher_actor_state_keys": sorted(teachers[0]["actor_model_state_dict"]),
          "omitted_distribution_parameter": "std", "runner_sha256": digest("/workspace/php_parkour/scripts/research/posttrain_coverage.py"), "quality_verified": False}
path = Path("/outputs/posttrain-coverage-audit/real-expert-schema.json")
path.write_text(json.dumps(output, indent=2) + "\n")
path.chmod(0o644)
print(json.dumps({"status": output["status"], "students": [item["total_verified_frozen_tensors"] for item in results], "cuda_initialized": False}))
