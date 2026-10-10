#!/usr/bin/env python3
"""Check a full teacher ONNX, including its embedded motion-table contract.

Run with inference-python inside the research image. Synthetic observations
verify export execution and reference lookup, not locomotion quality.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
from pathlib import Path


def validate(path: Path, seed: int, expected_observation_dim: int = 449) -> dict:
    import numpy as np
    import onnx
    import onnxruntime as ort

    onnx.checker.check_model(str(path), full_check=True)
    model = onnx.load(path, load_external_data=False)
    tensors = {t.name: t for t in model.graph.initializer}
    for node in model.graph.node:
        if node.op_type == "Constant":
            for attr in node.attribute:
                if attr.type == onnx.AttributeProto.TENSOR:
                    tensors[node.output[0]] = attr.t
    external = [t for t in tensors.values() if t.data_location == onnx.TensorProto.EXTERNAL]
    if external:
        raise ValueError("Expected the official metadata-rewritten, self-contained teacher graph")
    metadata = {p.key: p.value for p in model.metadata_props}
    joint_names = json.loads(metadata["dof_names"])
    if len(joint_names) != 29 or len(set(joint_names)) != 29:
        raise ValueError("Teacher must describe 29 unique joints")
    gathers = {n.output[0]: n for n in model.graph.node if n.op_type == "Gather"}
    names = ("joint_pos", "joint_vel", "ref_pos_xyz", "ref_quat_xyzw")
    table = tensors[gathers["joint_pos"].input[0]]
    frames = table.dims[0]
    steps = (0.0, 1.0, float(frames // 2), float(frames - 1), float(frames + 100), 1.75)
    indices = [min(int(np.float32(s)), frames - 1) for s in steps]
    expected = {}
    for name in names:
        tensor = tensors[gathers[name].input[0]]
        if tensor.data_type != onnx.TensorProto.FLOAT or tensor.dims[0] != frames:
            raise ValueError(f"Unexpected reference tensor: {name}")
        array = np.frombuffer(tensor.raw_data, dtype=np.float32).reshape(tensor.dims)
        expected[name] = array[indices].copy()
        del array
    constants = [{"name": t.name, "shape": list(t.dims), "bytes": len(t.raw_data)}
                 for t in tensors.values() if len(t.dims) == 2 and t.dims[0] == frames]
    del model, tensors, table, tensor
    gc.collect()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    inputs = {x.name: x for x in session.get_inputs()}
    if expected_observation_dim not in (160, 449):
        raise ValueError("Published terrain teachers use 160 or 449 actor observations")
    config = json.loads(metadata["experiment_config"])
    actor_terms = config["observation"]["groups"]["actor_obs"]["terms"]
    if ("height_scan" in actor_terms) != (expected_observation_dim == 449):
        raise ValueError("Expected observation size disagrees with saved height-scan configuration")
    if inputs["obs"].shape != [1, expected_observation_dim] or inputs["time_step"].shape != [1, 1]:
        raise ValueError(f"Unexpected teacher inputs: {inputs}")
    rng = np.random.default_rng(seed)
    cases = []
    for kind in ("zeros", "random_normal"):
        shape = (1, expected_observation_dim)
        obs = np.zeros(shape, np.float32) if kind == "zeros" else rng.normal(0, 0.1, shape).astype(np.float32)
        first_action = None
        for i, step in enumerate(steps):
            feed = {"obs": obs, "time_step": np.array([[step]], np.float32)}
            values = dict(zip([o.name for o in session.get_outputs()], session.run(None, feed), strict=True))
            repeated = session.run(None, feed)
            if not all(np.isfinite(v).all() for v in values.values()):
                raise ValueError(f"Non-finite output: {kind}/{step}")
            if not all(np.array_equal(a, b) for a, b in zip(values.values(), repeated, strict=True)):
                raise ValueError("CPU execution is not deterministic")
            if values["actions"].shape != (1, 29):
                raise ValueError("Wrong action shape")
            for name in names:
                np.testing.assert_array_equal(values[name], expected[name][i:i + 1])
            if first_action is not None:
                np.testing.assert_array_equal(values["actions"], first_action)
            first_action = values["actions"].copy()
            cases.append({"observations": kind, "time_step": step, "reference_index": indices[i],
                          "action_min": float(first_action.min()), "action_max": float(first_action.max())})
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {"status": "passed", "scope": "Teacher ONNX structure, metadata, deterministic CPU inference and exact embedded reference lookup; not policy quality or PT/ONNX numerical parity",
            "path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest.hexdigest(),
            "seed": seed, "expected_observation_dim": expected_observation_dim,
            "python": platform.python_version(), "onnx": onnx.__version__,
            "onnxruntime": ort.__version__, "self_contained": True, "motion_frames": frames,
            "reference_constants": constants, "metadata": metadata,
            "inputs": [{"name": x.name, "shape": x.shape, "type": x.type} for x in session.get_inputs()],
            "outputs": [{"name": x.name, "shape": x.shape, "type": x.type} for x in session.get_outputs()],
            "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--expected-observation-dim", type=int, choices=(160, 449), default=449)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = validate(args.model, args.seed, args.expected_observation_dim)
    except Exception as error:
        args.output.write_text(json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n")
        raise
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Teacher ONNX passed {len(result['cases'])} CPU cases: {args.output}")


if __name__ == "__main__":
    main()
