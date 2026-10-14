#!/usr/bin/env python3
"""CPU-only consistency and media checks of preserved native evaluation artifacts."""
import argparse
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time

SKILLS = ["locomotion", "low-step", "high-step", "low-climb-76", "high-climb-76"]
LABELS = ["eval-teacher-" + x for x in SKILLS] + ["eval-student-pure"]
REGISTRIES = ["file:///data/assets/motions-" + x for x in SKILLS]
METRICS = {"motion/error_ref_pos": "m", "motion/error_ref_rot": "rad",
           "motion/error_body_pos": "m", "motion/error_joint_pos": "rad (joint-vector L2)"}
CONTRACT = Path("/control/input-contract.json")
RESULTS = Path("/results")
SCOPE = ("CPU audit of six existing official 64-environment, 3000-control-step "
         "native evaluations and all 160 preserved clips; no new rollout, model "
         "loading, training, convergence, course-completion or source-coverage claim.")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "missing/non-regular input: " + str(path))
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_json(path):
    def invalid(value):
        raise ValueError("non-finite JSON constant: " + value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def close(a, b, absolute=1e-6, relative=1e-6):
    return finite(a) and finite(b) and math.isclose(a, b, abs_tol=absolute, rel_tol=relative)


def all_finite(value):
    if isinstance(value, dict):
        return all(all_finite(x) for x in value.values())
    if isinstance(value, list):
        return all(all_finite(x) for x in value)
    return type(value) is not float or math.isfinite(value)


def guard():
    state = {"dockerenv": Path("/.dockerenv").is_file(),
             "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
             "NVIDIA_VISIBLE_DEVICES": os.environ.get("NVIDIA_VISIBLE_DEVICES"),
             "gpu_devices": sorted(glob.glob("/dev/nvidia*") + glob.glob("/dev/dri/render*")),
             "nvidia_proc": Path("/proc/driver/nvidia/gpus").exists(),
             "python": sys.executable, "python_version": sys.version}
    require(state["dockerenv"] and state["CUDA_VISIBLE_DEVICES"] == ""
            and state["NVIDIA_VISIBLE_DEVICES"] == "void" and not state["gpu_devices"]
            and not state["nvidia_proc"], "CPU Docker guard failed: " + repr(state))
    return state


MAX_EVENT_RECORD_BYTES = 64 * 1024 * 1024
TFRECORD_PROVENANCE = {'original_source': 'scripts/research/student_training_curves/extract_student_scalars.py', 'original_source_sha256': 'e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12', 'copied_functions': ['regular', 'masked_crc32c', 'verify_tfrecord'], 'copied_function_block_sha256': '1ffc01312a4d580df3997bb048c5cae108fd91387fe1c9113616890156eda5d8', 'method': 'Exact function source copied without execution; dependencies: hashlib, Path, stat, struct, require, MAX_EVENT_RECORD_BYTES; runtime CRC updater is installed TensorBoard pywrap_tensorflow.crc_update.'}


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute normalized input path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Input has a symlink component')
    require(stat.S_ISREG(path.stat().st_mode), 'Regular input required: ' + str(path))
    return path


def masked_crc32c(crc):
    crc &= 0xffffffff
    return (((crc >> 15) | ((crc << 17) & 0xffffffff)) + 0xa282ead8) & 0xffffffff


def verify_tfrecord(event_fp, crc_update):
    """Strict whole-file framing check; injectable CRC updater for CPU protocol fixtures."""
    result = {'status': 'running', 'format': 'TFRecord', 'expected_file': event_fp,
        'records': 0, 'bytes': 0, 'complete_eof': False, 'crc32c_verified': False,
        'max_record_bytes': MAX_EVENT_RECORD_BYTES, 'largest_record_bytes': 0, 'diagnostics': []}
    digest, offset, record_offset = hashlib.sha256(), 0, 0

    def problem(code, failure_offset, **details):
        result['diagnostics'].append(dict(problem=code, offset=failure_offset,
            record_index=result['records'], record_offset=record_offset, **details))
        raise ValueError(code + ' at byte ' + str(failure_offset))

    try:
        path = regular(event_fp['path'])
        before = path.stat()
        with path.open('rb') as stream:
            def take(length):
                nonlocal offset
                chunks, remaining = [], length
                while remaining:
                    chunk = stream.read(remaining)
                    if not chunk:
                        break
                    digest.update(chunk); offset += len(chunk)
                    chunks.append(chunk); remaining -= len(chunk)
                return b''.join(chunks)

            while True:
                record_offset = offset
                length_bytes = take(8)
                if not length_bytes:
                    result['complete_eof'] = True
                    break
                if len(length_bytes) != 8:
                    problem('truncated_length_header', record_offset, expected_bytes=8, actual_bytes=len(length_bytes))
                length_crc = take(4)
                if len(length_crc) != 4:
                    problem('truncated_length_crc', record_offset + 8, expected_bytes=4, actual_bytes=len(length_crc))
                stored = struct.unpack('<I', length_crc)[0]
                calculated = masked_crc32c(crc_update(0, length_bytes))
                if stored != calculated:
                    problem('length_crc_mismatch', record_offset + 8, stored_crc=stored, calculated_crc=calculated)
                length = struct.unpack('<Q', length_bytes)[0]
                if length > MAX_EVENT_RECORD_BYTES or length > event_fp['bytes']:
                    problem('record_length_exceeds_bound', record_offset, declared_length=length,
                        maximum=MAX_EVENT_RECORD_BYTES, original_file_bytes=event_fp['bytes'])
                remaining, crc = length, 0
                while remaining:
                    start = offset
                    expected = min(remaining, 1048576)
                    chunk = take(expected)
                    if len(chunk) != expected:
                        problem('truncated_payload', start, expected_bytes=expected, actual_bytes=len(chunk), declared_length=length)
                    crc = crc_update(crc, chunk)
                    remaining -= len(chunk)
                crc_offset = offset
                payload_crc = take(4)
                if len(payload_crc) != 4:
                    problem('truncated_payload_crc', crc_offset, expected_bytes=4, actual_bytes=len(payload_crc), declared_length=length)
                stored, calculated = struct.unpack('<I', payload_crc)[0], masked_crc32c(crc)
                if stored != calculated:
                    problem('payload_crc_mismatch', crc_offset, stored_crc=stored, calculated_crc=calculated, declared_length=length)
                result['records'] += 1
                result['largest_record_bytes'] = max(result['largest_record_bytes'], length)
        after = path.stat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        actual = {'path': str(path), 'bytes': offset, 'sha256': digest.hexdigest()}
        if identity(before) != identity(after) or actual != event_fp:
            problem('event_changed_or_whole_file_identity_mismatch', offset, actual_file=actual)
        if not result['records']:
            problem('no_complete_tfrecords', 0)
        result.update(status='passed', bytes=offset, sha256=digest.hexdigest(), crc32c_verified=True)
    except Exception as error:
        if not result['diagnostics']:
            result['diagnostics'].append({'problem': 'tfrecord_read_or_crc_error', 'offset': offset,
                'record_index': result['records'], 'record_offset': record_offset,
                'error': type(error).__name__ + ': ' + str(error)})
        result.update(status='failed', bytes=offset, read_sha256=digest.hexdigest(),
            error=type(error).__name__ + ': ' + str(error))
    return result


def records(stage):
    return [stage[x] for x in ("manifest", "training_manifest", "quality", "config", "log")] + stage["events"] + stage["videos"]


def validate_contract(contract):
    require(type(contract.get("schema_version")) is int and contract["schema_version"] == 1,
            "input contract schema_version must be int 1")
    stages = contract["stages"]
    require([s["label"] for s in stages] == LABELS, "stage labels/order changed")
    flat = [fp for stage in stages for fp in records(stage)]
    require(len(flat) == 196 and len({x["path"] for x in flat}) == 196, "expected 196 distinct inputs")
    for fp in flat:
        native = Path(fp["native_path"])
        require(native.is_absolute() and ".." not in native.parts
                and native.is_relative_to("/outputs/official-full/official"), "invalid native_path")
        expected = Path("/artifacts") / native.relative_to("/outputs")
        require(fp["path"] == str(expected) and expected.resolve() == expected,
                "artifact path mapping/symlink changed: " + str(expected))
        require(integer(fp["bytes"], 1) and re.fullmatch("[0-9a-f]{64}", fp["sha256"]), "invalid fingerprint")
    videos = [fp for stage in stages for fp in stage["videos"]]
    require(len(videos) == 160 and sum(x["quality_bound"] is True for x in videos) == 148,
            "expected 160 clips, exactly 148 quality-bound")
    for fp in videos:
        require(type(fp["quality_bound"]) is bool and fp["native_described"] is True
                and finite(fp["declared_duration_seconds"]) and fp["declared_duration_seconds"] > 0,
                "invalid video descriptor")
    require(sum(len(s["events"]) for s in stages) == 6, "expected six event files")
    return flat


def snapshot(flat):
    found, failures = [], []
    for fp in flat:
        try:
            actual = fingerprint(fp["path"])
            found.append(actual)
            require(actual == {k: fp[k] for k in ("path", "bytes", "sha256")}, "fingerprint mismatch")
        except Exception as exc:
            failures.append({"path": fp["path"], "error": str(exc)})
    return {"files": found, "failures": failures}


def phase(result, name, callback):
    try:
        result[name] = {"status": "passed", "value": callback()}
    except Exception as exc:
        result[name] = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}


def passed_manifest(value, label):
    require(value["label"] == label and value["profile"] == "official"
            and value["settings"]["profile"] == "official" and value["status"] == "passed"
            and type(value["returncode"]) is int and value["returncode"] == 0
            and value["quality_verified"] is False, "invalid official native manifest: " + label)


def flag(argv, key):
    require(argv.count(key) == 1, "missing/duplicated native argument: " + key)
    return argv[argv.index(key) + 1]


def provenance(stages):
    teachers, identities = [], {}
    for stage in stages:
        label = stage["label"].removeprefix("eval-")
        value = read_json(stage["training_manifest"]["path"])
        passed_manifest(value, label)
        student = label == "student-pure"
        target, envs = (10000, 2048) if student else (20000, 4096)
        s, env = value["settings"], value["environment"]
        require(s["skills"] == SKILLS and s["iterations_target"] == target
                and s["num_envs"] in (None, envs) and value["checkpoint_iteration"] == target - 1
                and type(value["checkpoint_iteration"]) is int
                and flag(value["command"], "--algo.config.num-learning-iterations") == str(target)
                and flag(value["command"], "--training.num-envs") == str(envs)
                and flag(value["command"], "--training.seed") == "42", "final training schedule changed")
        checkpoint = {"path": value["checkpoint"], "sha256": value["checkpoint_sha256"]}
        require(Path(checkpoint["path"]).is_relative_to("/outputs/official-full/official/" + label)
                and Path(checkpoint["path"]).name == ("model_09999.pt" if student else "model_19999.pt")
                and re.fullmatch("[0-9a-f]{64}", checkpoint["sha256"]), "non-final checkpoint identity")
        registries = REGISTRIES if student else [REGISTRIES[SKILLS.index(label.removeprefix("teacher-"))]]
        require(s["registries"] == env["REGISTRY"] == ",".join(registries), "training registry order changed")
        if student:
            require(s["source_checkpoints"] == teachers and s["finetune"] == env["FINETUNE"] == "0"
                    and env["TEACHER_CHECKPOINT"] == ",".join(x["path"] for x in teachers), "pure student provenance changed")
        else:
            require(s["source_checkpoints"] == [] and s["finetune"] is None, "teacher provenance changed")
            teachers.append(checkpoint)
        identities[stage["label"]] = {**checkpoint, "iteration": target - 1, "registries": registries}
    return identities


def check_metrics(metrics, samples):
    require(set(metrics) == set(METRICS), "tracking metric set changed")
    for key, metric in metrics.items():
        require(metric["unit"] == METRICS[key] and type(metric["samples"]) is int
                and metric["samples"] == samples and metric["finite"] is True,
                "invalid finite metric samples: " + key)
        require(all(finite(metric[k]) and metric[k] >= 0 for k in ("mean", "p95", "max"))
                and metric["mean"] <= metric["max"] and metric["p95"] <= metric["max"], "invalid metric aggregates")


def check_quality(stage, identity):
    m, q = read_json(stage["manifest"]["path"]), read_json(stage["quality"]["path"])
    passed_manifest(m, stage["label"])
    s, env = m["settings"], m["environment"]
    require(s["skills"] == SKILLS and type(s["num_envs"]) is int and s["num_envs"] == 64
            and type(s["eval_steps"]) is int and s["eval_steps"] == 3000
            and type(s["eval_quality_schema"]) is int and s["eval_quality_schema"] == 1
            and type(m["overrides"]["num_envs"]) is int and m["overrides"]["num_envs"] == 64,
            "official evaluation dimensions changed")
    checkpoint = {k: identity[k] for k in ("path", "sha256")}
    require(s["source_checkpoints"] == [checkpoint] and env["CHECKPOINT"] == identity["path"]
            and s["registries"] == env["REGISTRY"] == ",".join(identity["registries"]), "evaluation source identity changed")
    require(m["evaluation_quality_report"] == stage["quality"]["native_path"]
            and m["evaluation_quality_sha256"] == stage["quality"]["sha256"]
            and m["log"] == stage["log"]["native_path"], "native report/log binding changed")
    require(q["schema_version"] == 1 and type(q["schema_version"]) is int
            and q["status"] == "completed" and q["quality_verified"] is False and all_finite(q)
            and q["checkpoint"] == identity["path"] and q["checkpoint_sha256"] == identity["sha256"]
            and type(q["checkpoint_iteration"]) is int and q["checkpoint_iteration"] == identity["iteration"], "quality schema/identity changed")
    require(type(q["num_envs"]) is int and q["num_envs"] == 64 and type(q["control_steps"]) is int
            and q["control_steps"] == 3000 and close(q["control_dt_seconds"], .02)
            and close(q["sim_seconds_per_env"], 60) and close(q["total_env_seconds"], 3840)
            and type(q["seed"]) is int and q["seed"] == 42 and q["registry_order"] == identity["registries"], "quality dimensions/registry/seed changed")
    require(q["finite_actions"] is True and q["finite_root_states"] is True
            and finite(q["max_abs_action"]) and q["max_abs_action"] >= 0
            and finite(q["minimum_root_height_m"]) and finite(q["wall_seconds"]) and q["wall_seconds"] > 0
            and q["capture_phase"] == "after native _update_log_dict, before reset_envs_idx", "invalid finite fields/capture phase")
    for key, array in (("failed_resets", "failed_resets_by_env"), ("timeout_resets", "timeout_resets_by_env")):
        require(integer(q[key]) and len(q[array]) == 64 and all(integer(x) and x <= 3000 for x in q[array])
                and sum(q[array]) == q[key], "per-environment reset sum changed: " + key)
    first = q["first_failure_sim_seconds_by_env"]
    require(len(first) == 64 and all((x is None and n == 0) or
            (n > 0 and finite(x) and .02 <= x <= 60 and close(x / .02, round(x / .02)))
            for x, n in zip(first, q["failed_resets_by_env"])), "first failure times invalid")
    require(integer(q["clip_completions_excluding_failed_timeout_steps"])
            and all(integer(x, 1) and x <= 3000 for x in q["ended_episode_lengths_steps"]), "invalid completion/episode counters")
    require(integer(q["available_clip_count"], 1) and q["observed_clip_ids"]
            and q["observed_clip_ids"] == sorted(set(q["observed_clip_ids"]))
            and all(integer(x) for x in q["observed_clip_ids"]), "invalid native command motion IDs")
    experts = q["observed_expert_ids"]
    require(experts and experts == sorted(set(experts)) and all(integer(x) and x < len(identity["registries"]) for x in experts), "invalid expert IDs")
    keys = {str(x) for x in experts}
    require(set(q["metrics_by_expert"]) == set(q["resets_by_expert"]) == keys, "expert key mapping inconsistent")
    check_metrics(q["metrics"], 192000)
    for key in keys:
        reset = q["resets_by_expert"][key]
        require(all(integer(reset[k]) for k in ("env_steps", "failed_resets", "timeout_resets"))
                and reset["env_steps"] > 0 and reset["failed_resets"] <= reset["env_steps"]
                and reset["timeout_resets"] <= reset["env_steps"], "invalid expert reset counters")
        check_metrics(q["metrics_by_expert"][key], reset["env_steps"])
    for counter, field in (("env_steps", "control_steps"), ("failed_resets", "failed_resets"), ("timeout_resets", "timeout_resets")):
        expected = 192000 if counter == "env_steps" else q[field]
        require(sum(x[counter] for x in q["resets_by_expert"].values()) == expected, "expert counter sum changed")
    for metric in METRICS:
        parts = [q["metrics_by_expert"][key][metric] for key in keys]
        require(close(sum(x["mean"] * x["samples"] for x in parts) / 192000, q["metrics"][metric]["mean"])
                and close(max(x["max"] for x in parts), q["metrics"][metric]["max"]), "expert/global aggregate mismatch")
    require(flag(q["native_argv"], "--checkpoint") == identity["path"]
            and flag(q["native_argv"], "--training.num-envs") == "64"
            and flag(q["native_argv"], "--training.max-eval-steps") == "3000"
            and flag(q["native_argv"], "--training.seed") == "42"
            and flag(q["native_argv"], "--training.registry-name") == ",".join(identity["registries"]), "quality native argv changed")
    require(q["saved_eval_config"] == stage["config"]["native_path"]
            and q["saved_eval_config_sha256"] == stage["config"]["sha256"], "saved YAML binding changed")
    bound = {x["path"]: x for x in m["artifact_fingerprints"]}
    native_bound = {x["native_path"]: x for x in [stage["quality"]] + stage["events"] + stage["videos"] if x.get("quality_bound", True)}
    require(set(bound) == set(native_bound), "native quality-bound artifact set changed")
    for path, fp in native_bound.items():
        require(bound[path]["sha256"] == fp["sha256"] and bound[path]["bytes"] == fp["bytes"], "native artifact fingerprint changed")
    quality_videos = {x["path"]: x for x in q["videos"]}
    native_videos = {x["path"]: x for x in m["evaluation_videos"]}
    require(len(quality_videos) == len(q["videos"]) and len(native_videos) == len(m["evaluation_videos"])
            and set(native_videos) == {x["native_path"] for x in stage["videos"]}
            and set(quality_videos) == {x["native_path"] for x in stage["videos"] if x["quality_bound"]}, "quality/native video distinction changed")
    for fp in stage["videos"]:
        path = fp["native_path"]
        require(close(native_videos[path]["duration_seconds"], fp["declared_duration_seconds"]), "native video duration changed")
        if fp["quality_bound"]:
            require(quality_videos[path]["sha256"] == fp["sha256"]
                    and close(quality_videos[path]["duration_seconds"], fp["declared_duration_seconds"]), "quality video binding changed")
    require(m["evaluation_tensorboard_events"] == q["tensorboard_events"] == [x["native_path"] for x in stage["events"]], "event paths changed")
    return {"metrics": q["metrics"], "failed_resets": q["failed_resets"], "timeout_resets": q["timeout_resets"],
            "observed_clip_ids": q["observed_clip_ids"], "available_clip_count": q["available_clip_count"],
            "observed_clip_id_scope": "Native command.motion_ids; expert-balanced single-bundle sampling assigns expert IDs, so these are not bounded by motion_end_idx.numel() and do not establish source-motion coverage.",
            "expert_registry_mapping": {str(x): identity["registries"][x] for x in experts},
            "metrics_by_expert": q["metrics_by_expert"], "resets_by_expert": q["resets_by_expert"],
            "quality_bound_videos": len(quality_videos), "native_described_only_videos": len(native_videos) - len(quality_videos)}


def check_yaml(stage, identity):
    import yaml
    config = yaml.safe_load(Path(stage["config"]["path"]).read_text())
    training = config["training"]
    require(type(training["num_envs"]) is int and training["num_envs"] == 64
            and type(training["seed"]) is int and training["seed"] == 42
            and training["registry_name"] == ",".join(identity["registries"]), "saved YAML dimensions/seed/registry changed")
    require(type(training["max_eval_steps"]) is int and training["max_eval_steps"] == 3000
            and training["checkpoint"] is None and training["export_onnx"] is False,
            "saved YAML actual eval/source fields changed")
    source_manifest = read_json(stage["training_manifest"]["path"])
    expected_teachers = source_manifest["environment"].get("TEACHER_CHECKPOINT")
    require(training["teacher_checkpoint"] == expected_teachers, "saved YAML ordered teacher sources changed")
    checked = {key: training[key] for key in ("num_envs", "seed", "registry_name", "max_eval_steps",
                                             "checkpoint", "teacher_checkpoint", "export_onnx")}
    return {"training": checked, "yaml_version": yaml.__version__, "top_level_keys": sorted(config)}


def check_tensorboard(stage):
    from tensorboard.compat.tensorflow_stub import pywrap_tensorflow
    import tensorboard
    integrity = {"checker_provenance": TFRECORD_PROVENANCE,
                 "crc_update_source": fingerprint(Path(pywrap_tensorflow.__file__).absolute()),
                 "events": []}
    integrity_path = RESULTS / stage["label"] / "tensorboard-integrity.json"
    for fp in stage["events"]:
        event_fp = {key: fp[key] for key in ("path", "bytes", "sha256")}
        integrity["events"].append(verify_tfrecord(event_fp, pywrap_tensorflow.crc_update))
        save(integrity_path, integrity)
    require(integrity["events"] and all(x["status"] == "passed" and x["complete_eof"] is True
            and x["crc32c_verified"] is True for x in integrity["events"]), "strict whole-original TensorBoard TFRecord gate failed; see tensorboard-integrity.json")
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    q = read_json(stage["quality"]["path"])
    expected = {"Evaluation/failed_resets": q["failed_resets"], "Evaluation/timeouts": q["timeout_resets"],
                "Evaluation/control_steps": q["control_steps"], "Evaluation/sim_seconds_per_env": q["sim_seconds_per_env"],
                "Evaluation/clip_completions": q["clip_completions_excluding_failed_timeout_steps"]}
    for metric, value in q["metrics"].items():
        for aggregate in ("mean", "p95", "max"):
            expected["Evaluation/tracking_error/" + metric.removeprefix("motion/") + "/" + aggregate] = value[aggregate]
    found = {}
    for fp in stage["events"]:
        accumulator = EventAccumulator(fp["path"], size_guidance={"scalars": 0}, purge_orphaned_data=False).Reload()
        for tag in accumulator.Tags()["scalars"]:
            if tag.startswith("Evaluation/"):
                require(tag not in found, "duplicated Evaluation tag across event files")
                found[tag] = [{"step": x.step, "value": x.value, "wall_time": x.wall_time} for x in accumulator.Scalars(tag)]
    save(RESULTS / stage["label"] / "tensorboard-scalars.json", {"expected": expected, "observed": found})
    require(set(found) == set(expected) and len(found) == 17, "actual Evaluation scalar tag set differs")
    for tag, values in found.items():
        require(len(values) == 1 and values[0]["step"] == 3000 and finite(values[0]["wall_time"])
                and close(values[0]["value"], expected[tag], absolute=1e-6, relative=1e-6), "TensorBoard scalar/step mismatch: " + tag)
    require(fingerprint(Path(pywrap_tensorflow.__file__).absolute()) == integrity["crc_update_source"], "installed CRC updater source changed")
    return {"tensorboard_version": tensorboard.__version__, "matched_tags": sorted(found),
            "event_integrity_complete": True, "event_integrity": integrity,
            "absolute_tolerance": 1e-6, "relative_tolerance": 1e-6, "reason": "SummaryWriter scalar encoding uses float32"}


def child(command, prefix, timeout=300):
    started = time.monotonic()
    out, err, code, failure = b"", b"", None, None
    try:
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        out, err, code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as exc:
        out, err, failure = exc.stdout or b"", exc.stderr or b"", "timeout"
    except Exception as exc:
        failure = type(exc).__name__ + ": " + str(exc)
    Path(str(prefix) + ".stdout.raw").write_bytes(out)
    Path(str(prefix) + ".stderr.raw").write_bytes(err)
    result = {"command": command, "returncode": code, "failure": failure,
              "elapsed_seconds": time.monotonic() - started}
    save(str(prefix) + ".execution.json", result)
    return result, out


def video(stage, fp, index):
    folder = RESULTS / stage["label"] / "videos"
    folder.mkdir(exist_ok=True)
    prefix = folder / (str(index).zfill(3) + "-" + Path(fp["path"]).stem)
    result = {**fp, "status": "failed"}
    probe, raw = child(["ffprobe", "-v", "error", "-threads", "1", "-count_frames", "-select_streams", "v:0",
                        "-show_streams", "-show_format", "-of", "json", fp["path"]], str(prefix) + ".ffprobe")
    decode, progress = child(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-threads", "1",
                              "-filter_threads", "1", "-i", fp["path"], "-map", "0:v:0", "-threads", "1",
                              "-vsync", "0", "-progress", "pipe:1", "-nostats", "-f", "null", "-"], str(prefix) + ".ffmpeg")
    result["ffprobe"], result["ffmpeg"] = probe, decode
    try:
        require(probe["returncode"] == decode["returncode"] == 0
                and probe["failure"] is None and decode["failure"] is None, "ffprobe/full ffmpeg decode failed")
        metadata = json.loads(raw)
        stream = metadata["streams"][0]
        duration = float(metadata["format"]["duration"])
        frames = int(stream["nb_read_frames"])
        pairs = [line.split("=", 1) for line in progress.decode().splitlines() if "=" in line]
        last = dict(pairs)
        decoded = int(last.get("frame", "0"))
        result.update({"metadata": metadata, "duration_seconds": duration, "probed_frames": frames,
                       "decoded_frames": decoded, "progress_end": last.get("progress") == "end"})
        require(finite(duration) and duration > 0 and close(duration, fp["declared_duration_seconds"])
                and frames == decoded and decoded > 0 and last.get("progress") == "end"
                and int(stream["width"]) > 0 and int(stream["height"]) > 0, "video metadata/frame count/duration/progress mismatch")
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    save(str(prefix) + ".result.json", result)
    return result


def thumbnail(stage, videos):
    candidates = [x for x in videos if x["quality_bound"]]
    require(candidates, "no quality-bound video for representative thumbnail")
    chosen = max(candidates, key=lambda x: x["declared_duration_seconds"])
    require(chosen["status"] == "passed", "longest quality-bound original did not fully decode")
    output = RESULTS / stage["label"] / "representative.png"
    result, _ = child(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-threads", "1",
                       "-filter_threads", "1", "-ss", str(chosen["duration_seconds"] / 2), "-i", chosen["path"],
                       "-map", "0:v:0", "-threads", "1", "-frames:v", "1", "-y", str(output)],
                      RESULTS / stage["label"] / "thumbnail.ffmpeg")
    require(result["returncode"] == 0 and result["failure"] is None and output.is_file()
            and output.stat().st_size > 0, "representative thumbnail failed")
    return {"source_native_path": chosen["native_path"], "source_sha256": chosen["sha256"],
            "source_duration_seconds": chosen["duration_seconds"], "seek_seconds": chosen["duration_seconds"] / 2,
            "thumbnail": fingerprint(output), "execution": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    state = guard()  # Must precede third-party imports and every child process.
    require(RESULTS.is_dir() and not list(RESULTS.iterdir()), "results directory must exist and be empty")
    report = {"schema_version": 1, "status": "failed", "quality_verified": False, "full": False,
              "scope": SCOPE, "guard": state, "stages": [], "errors": []}
    flat = []
    try:
        source = Path(__file__).resolve()
        report["source_before"] = fingerprint(source)
        report["contract_before"] = fingerprint(CONTRACT)
        require(report["source_before"]["sha256"] == args.source_sha256, "source admission SHA mismatch")
        require(report["contract_before"]["sha256"] == args.contract_sha256, "contract admission SHA mismatch")
        contract = read_json(CONTRACT)
        flat = validate_contract(contract)
        report["input_before"] = snapshot(flat)
        save(RESULTS / "input-before.json", report["input_before"])
        require(not report["input_before"]["failures"], "input fingerprints failed before audit")
        identities = provenance(contract["stages"])
        report["checkpoint_identities_without_loading_pt"] = identities
        for program in ("ffmpeg", "ffprobe"):
            version, _ = child([program, "-version"], RESULTS / (program + "-version"))
            require(version["returncode"] == 0, program + " unavailable")
        for stage in contract["stages"]:
            (RESULTS / stage["label"]).mkdir()
            result = {"label": stage["label"]}
            phase(result, "native_quality", lambda: check_quality(stage, identities[stage["label"]]))
            phase(result, "saved_yaml", lambda: check_yaml(stage, identities[stage["label"]]))
            phase(result, "tensorboard", lambda: check_tensorboard(stage))
            result["videos"] = [video(stage, fp, i) for i, fp in enumerate(stage["videos"])]
            phase(result, "representative_thumbnail", lambda: thumbnail(stage, result["videos"]))
            result["status"] = "passed" if all(result[x]["status"] == "passed" for x in
                ("native_quality", "saved_yaml", "tensorboard", "representative_thumbnail")) and all(x["status"] == "passed" for x in result["videos"]) else "failed"
            report["stages"].append(result)
            save(RESULTS / stage["label"] / "stage-result.json", result)
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        if flat:
            report["input_after"] = snapshot(flat)
            save(RESULTS / "input-after.json", report["input_after"])
            if report["input_after"] != report.get("input_before") or report["input_after"]["failures"]:
                report["errors"].append("original input bytes changed or became unreadable")
        for name, path in (("source", Path(__file__).resolve()), ("contract", CONTRACT)):
            try:
                report[name + "_after"] = fingerprint(path)
                if report[name + "_after"] != report.get(name + "_before"):
                    report["errors"].append(name + " changed during audit")
            except Exception as exc:
                report["errors"].append(name + " after hash failed: " + str(exc))
        if not report["errors"] and len(report["stages"]) == 6 and all(x["status"] == "passed" for x in report["stages"]):
            report["status"] = "passed"
        report["counts"] = {"stages": len(report["stages"]), "videos_attempted": sum(len(x["videos"]) for x in report["stages"]),
                            "videos_passed": sum(v["status"] == "passed" for x in report["stages"] for v in x["videos"])}
        save(RESULTS / "report.json", report)
    print(json.dumps({"status": report["status"], "quality_verified": False, "full": False,
                      "counts": report["counts"], "errors": report["errors"]}, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
