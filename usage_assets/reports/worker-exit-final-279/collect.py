"""Read-only, text-only supplement after old cohort halt. Host stdlib only."""
from pathlib import Path
import collections
import datetime as dt
import hashlib
import json
import re
import subprocess

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
RESEARCH = ROOT / "outputs/research"
PREVIOUS = RESEARCH / "worker-exit-completed-log-audit-20261010T074622Z"
HALT = RESEARCH / "sim2sim-cohort-halt-20261010T0749"
copied, anomalies = [], []
sha = lambda data: hashlib.sha256(data).hexdigest()
utc = lambda value: dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def local(value):
    if value.startswith("/outputs/"):
        return RESEARCH / Path(value).relative_to("/outputs")
    if value.startswith("/workspace/php_parkour/"):
        return ROOT / Path(value).relative_to("/workspace/php_parkour")
    return ROOT / value


def retain(source, target):
    before = source.stat()
    data = source.read_bytes()
    destination = OUT / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    after = source.stat()
    assert sha(source.read_bytes()) == sha(data) == sha(destination.read_bytes())
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    copied.append({"path": str(destination.relative_to(OUT)), "source": str(source.relative_to(ROOT)),
                   "bytes": len(data), "sha256": sha(data), "source_mtime_utc": utc(before.st_mtime)})
    return data


previous = json.loads((PREVIOUS / "full629-matrix-snapshot.json").read_bytes())
previous_report = json.loads(retain(PREVIOUS / "report.json", "previous-275-report.original.json"))
previous_manifest = retain(PREVIOUS / "evidence-manifest.json", "previous-275-manifest.original.json")
matrix_bytes = retain(RESEARCH / "sim2sim/all-configs-final/matrix.json", "final-matrix.original.json")
matrix = json.loads(matrix_bytes)
receipt = json.loads(retain(RESEARCH / "sim2sim-all-configs-host/full-driver.json", "full-driver.original.json"))
halt = json.loads(retain(HALT / "halt-receipt.json", "halt-receipt.original.json"))
retain(HALT / "cleanup-check.json", "cleanup-check.original.json")
retain(HALT / "after-full-execution.log", "full-execution.original.log")
retain(HALT / "frozen-dependencies-manifest.json", "frozen-dependencies-manifest.original.json")
assert sha(matrix_bytes) == receipt["matrix_sha256"] == "b2d46e0fea6c2bccf77c90d15da68277dc58f678e421d51066968e3232540495"
assert receipt["returncode"] == 1 and halt["native_processes"] == []
old_completed = {x["case_id"] for x in previous["selections"] if x.get("status") == "completed"}
assert len(old_completed) == 275
completed = [x for x in matrix["selections"] if x.get("status") == "completed"]
added = [x for x in completed if x["case_id"] not in old_completed]
failures = [x for x in matrix["selections"] if x.get("status") == "execution_failed"]
known_failures = {"low_speed_step:0041:right_45_walk1.5s_step0s", "low_speed_climb_58:0022:left_90_walk2.0s_plat0s"}
new_failures = [x for x in failures if x["case_id"] not in known_failures]
assert len(completed) == 279 and len(added) == 4 and len(failures) == 5 and len(new_failures) == 3
patterns = previous_report["patterns"]
compiled = {key: re.compile(value) for key, value in patterns.items()}

kernel_command = ["journalctl", "-k", "--since", "2026-10-10 07:35:35 UTC", "--until", "2026-10-10 07:46:40 UTC",
                  "--utc", "--no-pager", "-o", "json", "--grep=segfault|traps|command_writer"]
kernel = subprocess.run(kernel_command, capture_output=True)
(OUT / "kernel-query.stdout.jsonl").write_bytes(kernel.stdout)
(OUT / "kernel-query.stderr.txt").write_bytes(kernel.stderr)
(OUT / "kernel-query-receipt.json").write_text(json.dumps({"command": kernel_command, "returncode": kernel.returncode}, indent=2) + "\n")
kernel_records = [json.loads(line) for line in kernel.stdout.splitlines() if line.strip()]
assert kernel.returncode == 0


def collect_case(selection, kind):
    attempt = selection["attempts"][-1]
    original = local(attempt["output"])
    prefix = Path(kind) / selection["scenario"] / f"config-{selection['configuration_index']:04d}"
    (OUT / prefix).mkdir(parents=True, exist_ok=True)
    (OUT / prefix / "selection.snapshot.json").write_text(json.dumps(selection, indent=2) + "\n")
    snapshots = []
    for source in sorted(original.rglob("*")):
        if source.is_file() and (source.suffix in {".json", ".log", ".csv", ".txt"} or source.name == "stop"):
            data = retain(source, prefix / source.relative_to(original))
            snapshots.append({"name": str(source.relative_to(original)), "bytes": len(data), "sha256": sha(data),
                              "mtime_utc": utc(source.stat().st_mtime), "mtime_unix": source.stat().st_mtime})
    parent_log = local(attempt["log"]["path"])
    parent_data = retain(parent_log, prefix / "parent-attempt.original.log")
    if sha(parent_data) != attempt["log"]["sha256"]:
        anomalies.append({"case_id": selection["case_id"], "error": "parent log SHA differs"})
    evidence = json.loads((original / "case-evidence.json").read_text()) if (original / "case-evidence.json").exists() else None
    sealed = {item["path"]: item for item in evidence["files"]} if evidence else {}
    if evidence and sha((original / "case-evidence.json").read_bytes()) != attempt["evidence"]["sha256"]:
        anomalies.append({"case_id": selection["case_id"], "error": "case evidence SHA differs"})
    record = {"case_id": selection["case_id"], "scenario": selection["scenario"], "configuration_index": selection["configuration_index"],
              "configuration": selection["configuration"], "status": selection["status"], "command": selection["command"],
              "matching_released_training_bundle_available": selection["matching_released_training_bundle_available"],
              "attempt_number": attempt["number"], "parent_returncode": attempt["returncode"], "started_utc": utc(attempt["started_unix"]),
              "finished_utc": utc(attempt["finished_unix"]), "raw_directory": str(prefix), "output": attempt["output"],
              "source_files": selection["source_files"], "mesh_sha256": selection["mesh_sha256"], "logs": [], "ready_pids": {},
              "text_snapshots": snapshots, "timeline": []}
    for role, ready in [("simulator", "sim-ready.json"), ("inference", "policy-ready.json")]:
        ready_path = original / ready
        record["ready_pids"][role] = json.loads(ready_path.read_text()).get("pid") if ready_path.exists() else None
        path = original / f"{role}.log"
        data = path.read_bytes()
        expected = sealed.get(str(Path(attempt["output"]) / path.name))
        matches = []
        lines = data.decode(errors="replace").splitlines()
        for number, line in enumerate(lines, 1):
            for label, pattern in compiled.items():
                if pattern.search(line):
                    matches.append({"kind": label, "line_number": number, "line": line,
                                    "context": lines[max(0, number - 3):min(len(lines), number + 2)]})
        valid = expected["sha256"] == sha(data) if expected else None
        if evidence and valid is not True:
            anomalies.append({"case_id": selection["case_id"], "role": role, "error": "sealed log SHA differs/missing"})
        record["logs"].append({"role": role, "bytes": len(data), "sha256": sha(data), "line_count": len(lines),
                               "sealed_log_sha_matches": valid, "resource_tracker_warning": "resource_tracker" in data.decode(errors="replace"), "matches": matches})
    record["timeline"].append({"event": "parent_attempt_started", "unix": attempt["started_unix"], "utc": utc(attempt["started_unix"]), "clock": "matrix recorded wall clock"})
    for name in ["inference.json", "error.json", "simulation.json"]:
        path = original / name
        if path.exists():
            value = path.stat().st_mtime
            record["timeline"].append({"event": name + " file mtime", "unix": value, "utc": utc(value), "clock": "filesystem mtime; not an exit code"})
    candidates = [item for item in kernel_records if attempt["started_unix"] <= int(item["__REALTIME_TIMESTAMP"]) / 1e6 <= attempt["finished_unix"]]
    record["kernel_time_correlated_records"] = candidates
    for item in candidates:
        value = int(item["__REALTIME_TIMESTAMP"]) / 1e6
        record["timeline"].append({"event": "kernel fault (time-correlated, host TID mapping unavailable)", "unix": value, "utc": utc(value), "message": item["MESSAGE"], "clock": "journal __REALTIME_TIMESTAMP"})
    record["timeline"].append({"event": "parent_attempt_finished", "unix": attempt["finished_unix"], "utc": utc(attempt["finished_unix"]), "returncode": attempt["returncode"], "clock": "matrix recorded wall clock"})
    record["timeline"].sort(key=lambda item: item["unix"])
    if kind == "new-failures":
        record["inference"] = {k: v for k, v in json.loads((original / "inference.json").read_text()).items() if k != "samples"}
        record["simulation"] = json.loads((original / "simulation.json").read_text())
        record["absent_artifacts"] = [name for name in ["result.json", "case-evidence.json", "worker-processes.json", "simulator-process-start.json", "inference-process-start.json"] if not (original / name).exists()]
        record["conclusion"] = "Both body-level JSON reports completed, but parent returned 1. Logs contain no requested fatal/traceback string. Kernel fault occurs shortly after inference JSON; host TID to worker PID mapping and final worker return codes were not recorded. Do not infer skill failure or successful shutdown."
    return record


added_records = [collect_case(x, "added-completed") for x in added]
failure_records = [collect_case(x, "new-failures") for x in new_failures]
summary = {"final_selection_counts": dict(collections.Counter(x.get("status", "planned") for x in matrix["selections"])),
           "matrix_top_level_status": matrix["status"], "stale_top_level_completed_configurations": matrix["completed_configurations"],
           "wrapper_terminal_returncode": receipt["returncode"], "actual_native_cleanup_receipt_empty": halt["native_processes"] == [],
           "previous_completed_audited": 275, "new_completed_cases": len(added_records), "new_completed_logs": sum(len(x["logs"]) for x in added_records),
           "new_completed_fatal_cases": sum(any(m["kind"] == "native_crash" for log in x["logs"] for m in log["matches"]) for x in added_records),
           "new_completed_traceback_cases": sum(any(m["kind"] == "python_traceback" for log in x["logs"] for m in log["matches"]) for x in added_records),
           "cumulative_completed_fatal_cases": previous_report["summary"]["current629_completed_snapshot"]["cases_with_matches"],
           "new_execution_failed_cases": len(failure_records), "all_execution_failed_cases": len(failures)}
summary["cumulative_completed_fatal_cases"] += summary["new_completed_fatal_cases"]
limits = ["Only new four completed cases and three additional execution_failed cases were reread; previous 275/old17/old12 findings are carried forward by original report SHA.",
          "Media were neither read, hashed, decoded nor copied; only JSON/log/CSV/text and zero-byte stop markers were retained. Source NPZ/NPY/OBJ and 340 frozen dependencies were not rescanned.",
          "A parent-zero/artifact-sealed old attempt is not proof that its workers returned zero. Even a log without a fatal string cannot establish worker return codes.",
          "Kernel timestamps correlate with cases; without historical host/container thread mapping or native backtrace, do not treat temporal correlation as exact PID attribution or definitive SDK causality.",
          "Simulation height/tilt events are a separate quality heuristic, not an explanation for process shutdown failures and not obstacle-course completion.",
          "Stopped matrix deliberately retains running/planned labels and stale top-level counts; selection counts plus halt/terminal wrapper receipts describe its actual incomplete state."]
report = {"schema_version": 1, "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "scope": "Final read-only text supplement after old 571dfb cohort halt",
          "matrix_sha256": sha(matrix_bytes), "plan_identity": matrix["plan_sha256"], "patterns": patterns,
          "previous_report": {"path": str(PREVIOUS.relative_to(ROOT) / "report.json"), "sha256": sha((PREVIOUS / "report.json").read_bytes())},
          "summary": summary, "added_completed": added_records, "new_execution_failed": failure_records, "anomalies": anomalies, "limits": limits}
assert anomalies == []
(OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
pilot = [{"case_id": x["case_id"], "scenario": x["scenario"], "configuration_index": x["configuration_index"], "configuration": x["configuration"],
          "command": x["command"], "mesh": x["mesh"], "mesh_sha256": x["mesh_sha256"], "source_files": x["source_files"],
          "original_parent_returncode": x["attempts"][-1]["returncode"], "original_output": x["attempts"][-1]["output"],
          "scope": "Historical failed case identity only; not an executed new SDK pilot"} for x in failures]
(OUT / "sdk-pilot-failed-case-identities.json").write_text(json.dumps({"source_plan": matrix["plan_sha256"], "cases": pilot}, indent=2) + "\n")
lines = ["# Final stopped-cohort text audit supplement", "", "The old driver is terminal with exit 1. Selection records retain 279 completed, 5 execution_failed, 1 running and 344 planned; no complete-coverage claim is valid. The stale top-level completed count is 2. The halt receipt records no live native process.", "", "The last four completed cases (high_speed_climb_58 configs 24–27) add eight SHA-matching sealed worker logs. None contains the requested fatal/traceback strings. Carried forward with the preserved 275-case report, 10 of 279 parent-zero completed cases have explicit simulator SIGSEGV logs. Absence of a fatal line does not prove a worker-zero exit.", "", "Three additional failures are retained below. All have parent exit 1 and body JSON reporting 500 inference ticks and completed simulation. No role log has a fatal/traceback match. A kernel command_writer fault is time-correlated shortly after inference JSON; historic host-TID to worker-PID mapping is unavailable.", "", "| Case | Ready simulator / inference PID | Inference JSON UTC | Kernel fault UTC | Parent error mtime UTC | Simulation JSON UTC | Parent exit UTC | Height/tilt threshold |", "|---|---|---|---|---|---|---|---|"]
for record in failure_records:
    timeline = {x["event"]: x for x in record["timeline"]}
    faults = record["kernel_time_correlated_records"]
    kernel_time = utc(int(faults[0]["__REALTIME_TIMESTAMP"]) / 1e6) if faults else "none observed"
    lines.append("| " + " | ".join([record["case_id"], str(record["ready_pids"]["simulator"]) + " / " + str(record["ready_pids"]["inference"]), timeline["inference.json file mtime"]["utc"], kernel_time, timeline["error.json file mtime"]["utc"], timeline["simulation.json file mtime"]["utc"], record["finished_utc"], str(record["simulation"]["fall_detected"])]) + " |")
lines += ["", "For each failure the inference body report precedes the kernel fault, then the parent records an error, then the simulator saves its body JSON, and finally the parent exits 1. A body report is not interpreter-shutdown completion. Low/high climb58 fall outside the five released training bundles; do not turn this process-failure audit into skill-completion claims.", "", "`sdk-pilot-failed-case-identities.json` lists all five original failure identities for future explicitly planned tests; it does not represent new execution. `report.json` gives exact original bytes/SHA, sealed-log comparisons, kernel messages, clocks, and limits. `evidence-manifest.json` hashes the retained text snapshots.", "", *["- " + text for text in limits], ""]
(OUT / "report.md").write_text("\n".join(lines))
entries = []
for path in sorted(OUT.rglob("*")):
    if path.is_file() and path.name != "evidence-manifest.json":
        entries.append({"path": str(path.relative_to(OUT)), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())})
manifest = {"schema_version": 1, "scope": "Original-byte text-only audit supplement; no source/run/media mutation", "files": entries, "original_copies": copied, "total_bytes": sum(x["bytes"] for x in entries)}
(OUT / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
assert sha((PREVIOUS / "evidence-manifest.json").read_bytes()) == sha(previous_manifest)
print(json.dumps({"summary": summary, "report_sha256": sha((OUT / "report.json").read_bytes()), "manifest_sha256": sha((OUT / "evidence-manifest.json").read_bytes()), "files": len(entries), "total_bytes_excluding_manifest": manifest["total_bytes"]}, indent=2))
