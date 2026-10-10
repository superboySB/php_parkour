#!/usr/bin/env python3
"""CPU checks for the six saved teacher smoke presets, including PT/ONNX means.

Run with train-python in Docker. No Isaac startup, CUDA, or model training.
These are saved two-iteration smoke models, not trained parkour experts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

if __package__:
    from .validate_teacher_onnx import validate
else:
    from validate_teacher_onnx import validate

PRESETS = ("g1-wbt-terrain-ref", "g1-wbt-terrain-no-heightscan", "g1-wbt-terrain-ref-noscale",
           "g1-wbt-terrain-no-heightscan-noscale", "g1-wbt-terrain-ref-pelvis", "g1-wbt-terrain-no-heightscan-pelvis")


def fingerprint(path):
    path = Path(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def inspect_config(preset, config, observation_dim):
    expected_dim = 160 if "no-heightscan" in preset else 449
    terms = config["observation"]["groups"]["actor_obs"]["terms"]
    anchor = config["command"]["setup_terms"]["motion_command"]["params"]["motion_config"]["body_name_ref"]
    actor = config["algo"]["config"]["module_dict"]["actor"]
    layer = actor["layer_config"]
    if (preset not in PRESETS or observation_dim != expected_dim or ("height_scan" in terms) != (expected_dim == 449)
            or anchor != (["pelvis"] if preset.endswith("pelvis") else ["torso_link"])
            or config["training"]["name"] != f"teacher-preset-{preset}-locomotion"
            or config["training"]["registry_name"] != "file:///data/assets/motions-locomotion"
            or config["algo"]["config"]["empirical_normalization"] is not False
            or actor["type"] != "MLP" or actor["input_dim"] != ["actor_obs"] or actor["output_dim"] != [29]
            or layer["hidden_dims"] != [512, 256, 128] or layer["activation"] != "ELU"
            or layer["dropout_prob"] != 0 or layer["use_layer_norm"]):
        raise ValueError("Saved preset identity, anchor, dimensions or native MLP contract differs")
    return {"observation_dim": expected_dim, "anchor": anchor, "height_scan": "height_scan" in terms,
            "observation_scales": {name: term["scale"] for name, term in terms.items()}}


def check(preset, root, output, seed):
    import numpy as np
    import torch
    import onnxruntime as ort

    stage = f"teacher-preset-{preset}-locomotion"
    manifest_path = root / "manifests" / f"{stage}.json"
    manifest = json.loads(manifest_path.read_text())
    candidates = sorted((root / stage).rglob("model_00001.pt"))
    if (len(candidates) != 1 or manifest.get("status") != "passed" or manifest.get("returncode") != 0
            or manifest.get("profile") != "smoke" or manifest.get("checkpoint_iteration") != 1
            or manifest["settings"]["iterations_target"] != 2):
        raise ValueError(f"Missing successful two-iteration preset stage: {preset}")
    checkpoint = candidates[0]
    before = [fingerprint(p) for p in (manifest_path, checkpoint, checkpoint.with_suffix(".onnx"), checkpoint.parent / "holosoma_config.yaml")]
    if before[1]["sha256"] != manifest["checkpoint_sha256"]:
        raise ValueError("PT differs from the original native stage manifest")
    loaded = torch.load(checkpoint, map_location="cpu", weights_only=False)
    config = loaded["experiment_config"]
    if loaded["iter"] != 1 or loaded["actor_obs_normalizer_state_dict"] is not None:
        raise ValueError("Unexpected checkpoint iteration or actor normalizer")
    state = loaded["actor_model_state_dict"]
    dim = state["actor_module.module.0.weight"].shape[1]
    contract = inspect_config(preset, config, dim)
    expected = {"std", *(f"actor_module.module.{i}.{part}" for i in (0, 2, 4, 6) for part in ("weight", "bias"))}
    if set(state) != expected or any(not torch.isfinite(v).all().item() for v in state.values()):
        raise ValueError("Incomplete or nonfinite native actor tensors")
    native_report = validate(checkpoint.with_suffix(".onnx"), seed, dim)
    if (json.loads(native_report["metadata"]["experiment_config"]) != json.loads(json.dumps(config))
            or json.loads(native_report["metadata"]["iteration"]) != loaded["iter"]):
        raise ValueError("ONNX saved configuration/iteration differs from PT")
    options = ort.SessionOptions(); options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(checkpoint.with_suffix(".onnx")), options, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(seed)
    parity = []
    with torch.inference_mode():
        for index in range(10):
            obs = np.zeros((1, dim), np.float32) if index == 0 else rng.normal(0, .1, (1, dim)).astype(np.float32)
            actual = session.run(["actions"], {"obs": obs, "time_step": np.zeros((1, 1), np.float32)})[0]
            mean = torch.from_numpy(obs)
            for layer in (0, 2, 4, 6):
                mean = torch.nn.functional.linear(mean, state[f"actor_module.module.{layer}.weight"], state[f"actor_module.module.{layer}.bias"])
                if layer != 6:
                    mean = torch.nn.functional.elu(mean)
            expected_mean = mean.numpy()
            np.testing.assert_allclose(actual, expected_mean, rtol=1e-5, atol=1e-6)
            parity.append({"case": index, "max_absolute_error": float(np.max(np.abs(actual - expected_mean)))})
    if torch.cuda.is_initialized() or before != [fingerprint(Path(item["path"])) for item in before]:
        raise ValueError("CUDA initialized or saved inputs changed during CPU verification")
    native_path = output / f"{preset}-onnx.json"
    native_path.write_text(json.dumps(native_report, indent=2, allow_nan=False) + "\n")
    report = {"preset": preset, "status": "passed", "scope": "Two-iteration smoke export execution, embedded reference and PT mean parity; no Isaac reload or policy quality claim",
              "contract": contract, "inputs": before, "checkpoint_iteration": loaded["iter"], "onnx_report": fingerprint(native_path),
              "reference_cases": len(native_report["cases"]), "pt_mean_parity_cases": parity,
              "parity_tolerance": {"rtol": 1e-5, "atol": 1e-6}, "torch": torch.__version__,
              "onnxruntime": ort.__version__, "cuda_initialized": False, "quality_verified": False}
    (output / f"{preset}-parity.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Existing smoke root containing manifests and teacher-preset-* stages")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a fresh empty evidence directory")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for preset in PRESETS:
            results.append(check(preset, args.root, args.output, args.seed))
        summary = {"status": "passed", "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "presets": results,
                   "total_reference_cases": sum(r["reference_cases"] for r in results), "total_pt_parity_cases": 10 * len(results),
                   "isaac_reload_verified": False, "quality_verified": False,
                   "sources": [fingerprint(Path(__file__)), fingerprint(Path(__file__).with_name("validate_teacher_onnx.py"))]}
    except Exception as error:
        (args.output / "failure.json").write_text(json.dumps({"status": "failed", "completed_presets": len(results), "error": f"{type(error).__name__}: {error}"}, indent=2) + "\n")
        raise
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: summary[k] for k in ("status", "total_reference_cases", "total_pt_parity_cases", "isaac_reload_verified", "quality_verified")}))


if __name__ == "__main__":
    main()
