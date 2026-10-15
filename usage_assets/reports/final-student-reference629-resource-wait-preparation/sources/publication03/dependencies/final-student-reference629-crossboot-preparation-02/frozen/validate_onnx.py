#!/usr/bin/env python3
"""Check the released/exported PHP ONNX pair using real CPU inference.

Run inside the research Docker with inference-python. This checks the model
contract; synthetic observations do not measure parkour or policy quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path


COMMANDS = [
    "stand", "low_forward", "low_left_45", "low_left_90", "low_right_45",
    "low_right_90", "high_forward", "high_left_45", "high_left_90",
    "high_right_45", "high_right_90", "back", "reserved_12", "reserved_13",
    "reserved_14",
]


def validate(backbone: Path, student: Path, seed: int) -> dict:
    import numpy as np
    import onnx
    import onnxruntime as ort

    sessions = []
    models = []
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    for path in (backbone, student):
        model = onnx.load(path)
        onnx.checker.check_model(model, full_check=True)
        session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        sessions.append(session)
        models.append({
            "path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "inputs": [{"name": x.name, "shape": x.shape, "dtype": x.type} for x in session.get_inputs()],
            "outputs": [{"name": x.name, "shape": x.shape, "dtype": x.type} for x in session.get_outputs()],
            "metadata": {p.key: p.value for p in model.metadata_props},
        })
    b_session, s_session = sessions
    b_input = b_session.get_inputs()[0]
    depth_shape = tuple(b_input.shape)
    if depth_shape not in ((1, 58, 87), (1, 1, 58, 87)):
        raise ValueError(f"D435i depth shape is not 58 x 87: {depth_shape}")
    metadata = models[1]["metadata"]
    joints = metadata.get("joint_names", "").split(",")
    if len(joints) != 29 or len(set(joints)) != 29:
        raise ValueError("Student metadata must contain 29 unique joint_names")
    for key in ("action_scale", "default_joint_pos"):
        values = np.fromstring(metadata.get(key, ""), sep=",")
        if len(values) not in ((1, 29) if key == "action_scale" else (29,)) or not np.isfinite(values).all():
            raise ValueError(f"Student metadata {key} is absent or malformed")
    student_inputs = {x.name: x for x in s_session.get_inputs()}
    if "obs" not in student_inputs or student_inputs["obs"].shape != [1, 140]:
        raise ValueError(f"Expected PHP student obs [1, 140], got {student_inputs}")
    rng = np.random.default_rng(seed)
    cases = []
    for kind in ("zero_depth", "random_normalized_depth"):
        depth = np.zeros(depth_shape, np.float32) if kind == "zero_depth" else rng.uniform(-0.5, 0.5, depth_shape).astype(np.float32)
        latent = b_session.run(None, {b_input.name: depth})[0]
        if latent.shape != (1, 32) or not np.isfinite(latent).all():
            raise ValueError(f"Non-finite or incorrect backbone latent: {latent.shape}")
        for code, name in enumerate(COMMANDS):
            obs = np.zeros((1, 140), np.float32)
            obs[0, 92] = -1.0  # actor observation gravity z
            obs[0, 93 + code] = 1.0
            obs[:, 108:] = latent
            feed = {"obs": obs}
            if "time_step" in student_inputs:
                feed["time_step"] = np.zeros((1, 1), np.float32)
            started = time.perf_counter()
            outputs = s_session.run(None, feed)
            elapsed = time.perf_counter() - started
            repeated = s_session.run(None, feed)
            if not all(np.isfinite(x).all() for x in outputs):
                raise ValueError(f"Non-finite student output in {kind}/{name}")
            if outputs[0].shape != (1, 29):
                raise ValueError(f"Expected action [1, 29], got {outputs[0].shape}")
            if not all(np.array_equal(a, b) for a, b in zip(outputs, repeated)):
                raise ValueError(f"Non-deterministic CPU inference in {kind}/{name}")
            cases.append({"depth_case": kind, "command_index": code, "command": name,
                          "deployed_command": code < 12, "seconds": elapsed,
                          "action_min": float(outputs[0].min()), "action_max": float(outputs[0].max()),
                          "action_l2": float(np.linalg.norm(outputs[0])), "output_shapes": [list(x.shape) for x in outputs]})
    return {"status": "passed", "scope": "ONNX structure, metadata and synthetic inference; not locomotion quality",
            "seed": seed, "python": platform.python_version(), "numpy": np.__version__,
            "onnx": onnx.__version__, "onnxruntime": ort.__version__, "models": models, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = validate(args.models / "depth_backbone.onnx", args.models / "student.onnx", args.seed)
    except Exception as error:
        args.output.write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"ONNX pair passed {len(result['cases'])} synthetic cases: {args.output}")


if __name__ == "__main__":
    main()
