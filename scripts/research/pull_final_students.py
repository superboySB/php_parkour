#!/usr/bin/env python3
"""Read-only final-student status, or explicit SHA-bound selective fetch.

Host and remote probe use stdlib, existing SSH/rsync and read-only Docker
inspection. Actual PT science must already have passed in the frozen monitor's
CPU-only container. This never starts containers, training, simulation or DDS.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2] if __file__ != "<stdin>" else Path.cwd()
REMOTE_ROOT = "/diff/dzp_is_sb/php-parkour-research"
TREE = "02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c"
MONITOR_SHA = "58b8978cb24d8a194133e6344c1fa415632413d83c92b18a21ebcc3b75ed5dfc"
COVERAGE_DIRECTORY = "coverage-official-final-ro-assets-v2"
IMAGE = "sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd"
PAIR = ("student.onnx", "depth_backbone.onnx")
KINDS = ("pure", "finetune")
SKILLS = ("locomotion", "low-step", "high-step", "low-climb-76", "high-climb-76")
LABELS = (*[f"teacher-{s}" for s in SKILLS], *[f"eval-teacher-{s}" for s in SKILLS],
          "student-pure", "eval-student-pure", "export-student-pure", "student-finetune", "eval-student-finetune", "export-student-finetune")
JSON_LIMIT = 16 * 1024 * 1024


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""): value.update(block)
    return value.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path): return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.chmod(0o644)
    temporary.replace(path)


def relative_path(value):
    require(isinstance(value, str), "Relative path must be text")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.parts
            and ".." not in path.parts and not any(ord(x) < 32 for x in value)
            and str(path) == value, f"Unsafe relative path: {value}")
    return path


def coverage_directory(value):
    """One explicit coverage child of remote_root/outputs, never an arbitrary path."""
    path = relative_path(value)
    require(len(path.parts) == 1 and re.fullmatch(r"coverage-[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value),
            "Coverage output must be one safe coverage-* directory relative to remote_root/outputs")
    return value


def regular_file(root, relative):
    path = Path(root)
    for part in relative_path(relative).parts:
        path /= part
        require(not path.is_symlink(), f"Symlink is not an immutable transfer source: {path}")
    require(stat.S_ISREG(path.stat().st_mode), f"Not a regular file: {path}")
    require(path.resolve().is_relative_to(Path(root).resolve()), f"File escapes root: {path}")
    return path


def load_monitor(root, tree):
    require(re.fullmatch(r"[0-9a-f]{64}", tree), "Invalid frozen source tree")
    source = Path(root) / "source" / tree
    path = regular_file(source, "scripts/research/posttrain_coverage.py")
    require(sha(path) == MONITOR_SHA, "Frozen monitor revision differs from the reviewed API")
    spec = importlib.util.spec_from_file_location("final_student_frozen_monitor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_cpu_receipt(cpu, selection, pc):
    require(cpu.get("status") == "cpu_scientific_checks_passed" and cpu.get("input_identity") == selection["input_identity"]
            and cpu.get("simulation_started") is False and cpu.get("quality_verified") is False
            and cpu.get("total_sources") == 296 and cpu.get("finished_utc")
            and re.fullmatch(r"[0-9a-f]{64}", cpu.get("inventory_sha256", "")), "Incomplete CPU scientific receipt")
    require(selection.get("schema_version") == 2
            and cpu.get("runtime_robot_assets") == selection["runtime_robot_assets"],
            "CPU receipt does not bind the schema2 shared runtime robot assets")
    reports = cpu.get("checkpoints", [])
    require(len(reports) == 7 and [x["label"] for x in reports] == list(pc.TRAINING), "CPU receipt lacks ordered seven final PTs")
    targets = {"teacher": "holosoma.agents.ppo.ppo.PPO", "pure": "wbt_training.utils.student_teacher.PhpDistillation",
               "finetune": "wbt_training.utils.student_teacher.PhpDistillationPPO"}
    for report in reports:
        label = report["label"]
        expected = selection["checkpoints"][label]
        kind = "teacher" if label.startswith("teacher-") else label.removeprefix("student-")
        registry = f"file:///data/assets/motions-{label.removeprefix('teacher-')}" if kind == "teacher" else ",".join(f"file:///data/assets/motions-{s}" for s in pc.SKILLS)
        require(all(report.get(k) == v for k, v in expected.items()) and report.get("embedded_config_verified") is True
                and report.get("algorithm") == targets[kind] and report.get("registry") == registry,
                f"CPU final PT/config provenance differs: {label}")
        counts = report.get("tensor_counts", [])
        require(len(counts) == (2 if kind == "teacher" else 1)
                and all(type(x) is int and x > 0 for x in counts), f"CPU receipt has no policy tensor evidence: {label}")
        experts = report.get("frozen_experts", [])
        if kind == "teacher": require(experts == [], "Unexpected teacher expert receipt")
        else:
            require(len(experts) == 5 and [x["original_expert_ordinal"] for x in experts] == list(range(5)), "Incomplete ordered frozen experts")
            for item in experts:
                require(item.get("bitwise_equal_to_final_teacher") is True and item.get("actor_tensors") == 8
                        and set(item.get("actor_tensor_keys", [])) == {f"{i}.{name}" for i in (0,2,4,6) for name in ("weight","bias")}
                        and item.get("normalizer_tensors") == 3
                        and set(item.get("normalizer_tensor_keys", [])) == {"mean", "std", "eps"}, "Incomplete frozen actor/normalizer proof")
    plans = cpu.get("plans", [])
    require(len(plans) == 3 and [x["policy"] for x in plans] == list(pc.POLICIES)
            and all(x.get("sources") == 296 and re.fullmatch(r"[0-9a-f]{64}", x.get("sha256", "")) for x in plans), "Incomplete three full-source CPU plans")


def remote_probe(root, tree, pc, coverage_output=COVERAGE_DIRECTORY):
    """Pure read-only gate. pc is the exact reviewed frozen monitor module."""
    root = Path(root)
    coverage_output = coverage_directory(coverage_output)
    official, coverage = root / "outputs/official-full", root / "outputs" / coverage_output
    # Reject manifest aliases before the native gate reads them.
    for label in pc.LABELS:
        relative = f"official/manifests/{label}.json"
        if (official / relative).exists() or (official / relative).is_symlink(): regular_file(official, relative)
    stages, blockers = pc.stage_status(official)
    cpu_present = (coverage / "cpu-ready.json").is_file()
    waiting = {"status": "waiting", "observed_utc": now(), "canonical_stage_count": 16,
               "remote_root": str(root), "source_tree": tree, "monitor_sha256": MONITOR_SHA,
               "coverage_output": coverage_output, "host_coverage_output": str(coverage),
               "stage_blockers": blockers, "cpu_ready_present": cpu_present, "gpu_started": False,
               "transfer_started": False, "quality_verified": False}
    if blockers: return waiting
    if not cpu_present or not (coverage / "selection.json").is_file():
        waiting["blockers"] = ["Posttrain selection/CPU-ready not yet available"]
        return waiting
    selection = read(regular_file(coverage, "selection.json"))
    cpu = read(regular_file(coverage, "cpu-ready.json"))
    require(selection["input_identity"] == identity({k:v for k,v in selection.items() if k != "input_identity"}), "Selection identity changed")
    require(selection["coverage_source_tree"] == tree and selection["training_source_tree"] == pc.TRAIN_TREE
            and selection["image"] == IMAGE and selection["image_contents_sha256"] == pc.IMAGE_CONTENTS
            and selection["official_output"] == pc.OFFICIAL and selection["coverage_output"] == pc.COVERAGE
            and selection["host_coverage_output"] == str(coverage)
            and selection["driver_completion"]["status"] == "driver_quiescent"
            and selection["driver_log_sha256"] == sha(regular_file(root / "outputs", "official-full-driver.log")),
            "Selection source/image/driver provenance differs")
    args = SimpleNamespace(root=root, source_tree=tree, image=IMAGE, gpu_uuid=selection["gpu_uuid"],
                           official_output=official, coverage_output=coverage)
    source = pc.verify_snapshot(args)  # Source hashes + existing image inspect only.
    actual = pc.inspect_artifacts(official, stages)  # No torch/GPU; hashes all official outputs.
    require(all(selection.get(key) == value for key,value in actual.items()), "Final official manifests/PT/output hashes changed since CPU selection")
    verify_cpu_receipt(cpu, selection, pc)
    name = pc.docker_command(args, source, "cpu", selection["input_identity"])[0]
    state = pc.container_state(args, source, "cpu", name, selection["input_identity"])
    require(state is not None and state["State"]["Running"] is False and state["State"]["ExitCode"] == 0,
            "Actual isolated CPU preparation container did not finish successfully")
    for item in cpu["plans"]:
        path = PurePosixPath(item["path"])
        require(path == PurePosixPath(pc.COVERAGE) / item["policy"] / "plan.json", "CPU plan path changed")
        actual_plan = regular_file(coverage, str(path.relative_to(pc.COVERAGE)))
        data = read(actual_plan)
        require(sha(actual_plan) == item["sha256"] and data.get("schema_version") == 2
                and data.get("runtime_robot_assets") == selection["runtime_robot_assets"] and data.get("policy") == item["policy"]
                and data.get("selected_sources") == data.get("inventory_total_sources") == len(data["cases"]) == 296,
                "CPU complete-source plan changed")
    files, pairs = {}, []
    def add(relative):
        relative_path(relative)
        path = regular_file(root / "outputs", relative)
        require(path.suffix == ".json" or path.name in PAIR and relative.startswith("official-full/official/export-student-"), "Transfer whitelist contains forbidden payload")
        if path.suffix == ".json":
            require(path.stat().st_size <= JSON_LIMIT, "Provenance JSON is unexpectedly large")
            read(path)
        files[relative] = {"relative":relative, "sha256":sha(path), "bytes":path.stat().st_size}
    for label in pc.LABELS: add(f"official-full/official/manifests/{label}.json")
    for filename in ("selection.json", "cpu-ready.json"): add(f"{coverage_output}/{filename}")
    add("official-full/official/teacher-onnx-validation/summary.json")
    for item in selection["teacher_reports"]: add(str(PurePosixPath(item["path"]).relative_to("/outputs")))
    for kind in KINDS:
        stage = stages[f"export-student-{kind}"]
        entries = stage["onnx_validation_reports"]
        require(len(entries) == 1, f"Ambiguous independently validated final {kind} bundles")
        entry = entries[0]
        bundle = PurePosixPath(entry["bundle"])
        require(bundle.is_relative_to(f"/outputs/official-full/official/export-student-{kind}") and ".." not in bundle.parts,
                "Final bundle escapes its explicit export stage")
        model_records = {}
        for filename in PAIR:
            relative = str((bundle / filename).relative_to("/outputs"))
            add(relative)
            model_records[filename] = files[relative]
        report_path = PurePosixPath(entry["report"])
        require(report_path.is_relative_to(f"/outputs/official-full/official/export-student-{kind}")
                and report_path.suffix == ".json" and ".." not in report_path.parts,
                "Final ORT report escapes its explicit export stage")
        report = str(report_path.relative_to("/outputs")); add(report)
        add(str(PurePosixPath(stages[f"eval-student-{kind}"]["evaluation_quality_report"]).relative_to("/outputs")))
        pairs.append({"kind":kind, "checkpoint":selection["checkpoints"][f"student-{kind}"],
                      "bundle":entry["bundle"], "report":report, "models":model_records})
    payload = {"schema_version":2, "remote_root":str(root), "source_tree":tree, "monitor_sha256":MONITOR_SHA,
               "coverage_output":coverage_output, "host_coverage_output":str(coverage),
               "image":IMAGE, "selection_identity":selection["input_identity"], "checkpoints":selection["checkpoints"],
               "cpu_container":name, "cpu_container_exit_code":0, "pairs":pairs,
               "files":sorted(files.values(),key=lambda x:x["relative"]), "quality_verified":False}
    return {"status":"ready", "observed_utc":now(), "snapshot_identity":identity(payload), "payload":payload,
            "cohort":f"final-{selection['input_identity'][:12]}-{pairs[0]['checkpoint']['sha256'][:12]}-{pairs[1]['checkpoint']['sha256'][:12]}"}


def validate_receipt(receipt):
    require(receipt.get("status") == "ready" and receipt["snapshot_identity"] == identity(receipt["payload"]), "Remote immutable receipt identity differs")
    payload = receipt["payload"]
    require(payload["schema_version"] == 2 and payload["monitor_sha256"] == MONITOR_SHA and payload["image"] == IMAGE,
            "Remote receipt uses another source/image contract")
    coverage_output = coverage_directory(payload["coverage_output"])
    remote_root = PurePosixPath(payload["remote_root"])
    require(remote_root.is_absolute() and ".." not in remote_root.parts
            and payload["host_coverage_output"] == str(remote_root / "outputs" / coverage_output)
            and re.fullmatch(r"[0-9a-f]{64}", payload["source_tree"]),
            "Remote receipt coverage path/source identity differs")
    require([x["kind"] for x in payload["pairs"]] == list(KINDS) and len(payload["pairs"]) == 2, "Expected two ordered final pairs")
    require(set(payload["checkpoints"]) == {f"teacher-{s}" for s in SKILLS} | {f"student-{k}" for k in KINDS}, "Receipt lacks seven canonical checkpoints")
    for skill in SKILLS:
        checkpoint = payload["checkpoints"][f"teacher-{skill}"]
        require((checkpoint["iteration"], checkpoint["num_envs"], checkpoint["num_variants"]) == (19999,4096,64), "Wrong final teacher PT provenance")
    files = payload["files"]
    require(len({x["relative"] for x in files}) == len(files), "Duplicate transfer paths")
    expected_models = set()
    for pair in payload["pairs"]:
        kind = pair["kind"]
        bundle = PurePosixPath(pair["bundle"])
        require(bundle.is_absolute() and bundle.is_relative_to(f"/outputs/official-full/official/export-student-{kind}")
                and ".." not in bundle.parts, "Final model bundle is outside its absolute export stage")
        report_path = relative_path(pair["report"])
        require(report_path.suffix == ".json" and report_path.is_relative_to(f"official-full/official/export-student-{kind}"), "Final ORT report is outside its export stage")
        checkpoint = payload["checkpoints"][f"student-{kind}"]
        require(pair["checkpoint"] == checkpoint and checkpoint["iteration"] == (9999 if kind == "pure" else 29999)
                and checkpoint["num_envs"] == 2048 and checkpoint["num_variants"] == 3, "Wrong final student PT provenance")
        require(set(pair["models"]) == set(PAIR), "Incomplete final model pair")
        for name,record in pair["models"].items():
            require(record["relative"] == str((bundle / name).relative_to("/outputs"))
                    and record in files, "Model path/hash is not bound to its explicit bundle")
            expected_models.add(record["relative"])
    expected_json = {f"official-full/official/manifests/{label}.json" for label in LABELS}
    expected_json |= {f"{coverage_output}/selection.json", f"{coverage_output}/cpu-ready.json",
                      "official-full/official/teacher-onnx-validation/summary.json"}
    expected_json |= {f"official-full/official/teacher-onnx-validation/{skill}.json" for skill in SKILLS}
    expected_json |= {f"official-full/official/eval-student-{kind}/quality.json" for kind in KINDS}
    expected_json |= {pair["report"] for pair in payload["pairs"]}
    json_total = 0
    actual_models = set()
    for item in files:
        path = relative_path(item["relative"])
        require(type(item["bytes"]) is int and item["bytes"] > 0 and re.fullmatch(r"[0-9a-f]{64}",item["sha256"]), "Invalid file fingerprint")
        if path.suffix == ".onnx":
            actual_models.add(str(path))
            require(path.name in PAIR and any(path.is_relative_to(f"official-full/official/export-student-{k}") for k in KINDS), "Teacher/other ONNX is forbidden")
        else:
            allowed = path.suffix == ".json" and str(path) in expected_json
            require(allowed and item["bytes"] <= JSON_LIMIT, "Non-whitelisted or oversized JSON payload")
            json_total += item["bytes"]
    require(actual_models == expected_models and len(actual_models) == 4 and json_total <= 64*1024*1024
            and {x["relative"] for x in files if x["relative"].endswith(".json")} == expected_json,
            "Transfer is not exactly four ONNX plus bound small JSON")
    require(receipt["cohort"] == f"final-{payload['selection_identity'][:12]}-{payload['pairs'][0]['checkpoint']['sha256'][:12]}-{payload['pairs'][1]['checkpoint']['sha256'][:12]}", "Immutable cohort is not derived from its final input identity")
    return files


def observe_remote(args):
    command = ["ssh", "-p", "22", "-o", "BatchMode=yes", args.host, "python3", "-B", "-", "probe",
               "--remote-root", args.remote_root, "--source-tree", args.source_tree,
               "--coverage-output", coverage_directory(args.coverage_output)]
    result = subprocess.run(command, input=Path(__file__).read_bytes(), capture_output=True, check=True)
    receipt = json.loads(result.stdout)
    if receipt.get("status") == "ready":
        validate_receipt(receipt)
        observed = receipt["payload"]
    else:
        require(receipt.get("status") == "waiting", "Unknown remote observation status")
        observed = receipt
    require(observed["remote_root"] == args.remote_root and observed["source_tree"] == args.source_tree
            and observed["coverage_output"] == args.coverage_output
            and observed["host_coverage_output"] == str(PurePosixPath(args.remote_root) / "outputs" / args.coverage_output)
            and observed["monitor_sha256"] == MONITOR_SHA,
            "SSH receipt belongs to another requested remote root/source/coverage directory")
    return receipt


def verify_download(raw, files):
    expected = {x["relative"] for x in files}
    actual = {str(p.relative_to(raw)) for p in raw.rglob("*") if p.is_file() or p.is_symlink()}
    require(actual == expected, "Downloaded file set differs from the explicit whitelist")
    for item in files:
        path = regular_file(raw,item["relative"])
        require(path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], f"Downloaded bytes/SHA changed: {item['relative']}")


def fetch(args, before):
    if before["status"] == "waiting": return before
    tool_sha = sha(__file__)
    files = validate_receipt(before)
    require(before["payload"]["remote_root"] == args.remote_root and before["payload"]["source_tree"] == args.source_tree
            and before["payload"]["coverage_output"] == coverage_directory(args.coverage_output),
            "Fetch receipt belongs to another requested remote root/source/coverage directory")
    require(re.fullmatch(r"final-[0-9a-f]{12}-[0-9a-f]{12}-[0-9a-f]{12}",before["cohort"]), "Invalid immutable cohort name")
    destination = args.output_root / before["cohort"] / args.attempt
    require(not any(path.is_symlink() for path in [destination,*destination.parents]), "Transfer destination has a symlink ancestor")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.mkdir(exist_ok=False)
    raw = destination / "raw"; raw.mkdir()
    write(destination / "remote-before.json", before)
    listing = destination / "files-from.nul"
    listing.write_bytes(b"\0".join(x["relative"].encode() for x in files)+b"\0")
    command = ["rsync", "-a", "--relative", "--partial", "--protect-args", "--from0", "--files-from",str(listing),
               "-e", "ssh -p 22 -o BatchMode=yes", f"{args.host}:{args.remote_root}/outputs/", str(raw)+"/"]
    report = {"status":"running","started_utc":now(),"snapshot_identity":before["snapshot_identity"],
              "destination":str(destination),"command":command,"transfer_tool_sha256":tool_sha,"quality_verified":False}
    write(destination / "fetch-status.json",report)
    try:
        with (destination / "rsync.stdout.log").open("xb") as stdout, (destination / "rsync.stderr.log").open("xb") as stderr:
            subprocess.run(command,stdout=stdout,stderr=stderr,check=True)
        verify_download(raw, files)
        after = observe_remote(args)
        write(destination / "remote-after.json",after)
        require(after.get("snapshot_identity") == before["snapshot_identity"] and after.get("payload") == before["payload"],
                "Remote final source changed during transfer; partial evidence retained")
        require(sha(__file__) == tool_sha, "Transfer helper changed while copying; partial evidence retained")
        verify_download(raw, files)
        materialized=[]
        for pair in before["payload"]["pairs"]:
            directory=destination / "models" / pair["kind"]; directory.mkdir(parents=True)
            for name,item in pair["models"].items():
                target=directory/name; shutil.copyfile(regular_file(raw,item["relative"]),target);target.chmod(0o644)
                require(sha(target)==item["sha256"],"Materialized final model SHA changed")
                materialized.append({"kind":pair["kind"],"source_relative":item["relative"],"path":str(target),"sha256":item["sha256"],"bytes":target.stat().st_size})
        report.update(status="completed",finished_utc=now(),files=len(files),total_bytes=sum(x["bytes"] for x in files),models=materialized,
                      scope="Four SHA-bound final ONNX files and provenance transferred; local ORT and MuJoCo remain unexecuted")
        write(destination / "fetch-status.json",report)
        return report
    except BaseException as error:
        report.update(status="failed",finished_utc=now(),error=f"{type(error).__name__}: {error}",partial_evidence_retained=True)
        write(destination / "fetch-status.json",report)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("status","dry-run","fetch","probe"))
    parser.add_argument("--host",default="tencent-231")
    parser.add_argument("--remote-root",default=REMOTE_ROOT)
    parser.add_argument("--source-tree",default=TREE)
    parser.add_argument("--coverage-output",default=COVERAGE_DIRECTORY,
                        help="One safe coverage-* directory relative to remote-root/outputs; must match selection.json")
    parser.add_argument("--output-root",type=Path,default=REPO/"outputs/research/final-student-transfer")
    parser.add_argument("--attempt",default="initial",help="Fresh immutable attempt name; choose a new name after reviewing a retained partial failure")
    args=parser.parse_args()
    coverage_directory(args.coverage_output)
    require(re.fullmatch(r"[A-Za-z0-9_@.][A-Za-z0-9_@.-]*",args.host) and re.fullmatch(r"/diff/dzp_is_sb/[A-Za-z0-9_./-]+",args.remote_root)
            and ".." not in PurePosixPath(args.remote_root).parts, "Unsafe SSH host/remote root")
    require(re.fullmatch(r"[0-9a-f]{64}",args.source_tree) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}",args.attempt), "Invalid source tree/attempt name")
    if args.action=="probe":
        result=remote_probe(Path(args.remote_root),args.source_tree,load_monitor(args.remote_root,args.source_tree),args.coverage_output)
    else:
        require(not any(path.is_symlink() for path in [args.output_root,*args.output_root.parents]), "Output tree has a symlink ancestor")
        args.output_root=args.output_root.resolve()
        require(args.output_root.is_relative_to((REPO/"outputs/research/final-student-transfer").resolve()), "Use the dedicated final-student-transfer output tree")
        result=observe_remote(args)
        if args.action=="fetch": result=fetch(args,result)
    print(json.dumps(result,indent=2,allow_nan=False))
    return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({"status":"rejected","error":f"{type(error).__name__}: {error}","quality_verified":False}),file=sys.stderr)
        raise SystemExit(1)
