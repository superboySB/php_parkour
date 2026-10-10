"""Read-only, CPU-only validation of a captured live matrix and its completed set."""
from pathlib import Path
from collections import Counter
import datetime as dt
import hashlib
import json
import sys

sys.path.insert(0, "/workspace/php_parkour")
from scripts.research import sim2sim_scene_matrix as native

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def process(pid):
    directory = Path("/proc") / str(pid)
    return {"pid": pid, "cmdline": (directory / "cmdline").read_bytes().decode().split("\0"),
            "status": (directory / "status").read_text(), "cwd": str((directory / "cwd").resolve()),
            "stat": (directory / "stat").read_text()}

base = Path("/outputs/live-audit-0653")
live = Path("/outputs/sim2sim/all-configs-final")
plan_bytes = (base / "captured-plan.json").read_bytes() if (base / "captured-plan.json").exists() else (live / "plan.json").read_bytes()
matrix_bytes = (base / "captured-matrix.json").read_bytes() if (base / "captured-matrix.json").exists() else (live / "matrix.json").read_bytes()
plan, matrix = json.loads(plan_bytes), json.loads(matrix_bytes)
(base / "captured-plan.json").write_bytes(plan_bytes)
(base / "captured-matrix.json").write_bytes(matrix_bytes)
errors = []
def check(condition, message):
    if not condition: errors.append(message)
check(native.identity({k:v for k,v in plan.items() if k != "plan_sha256"}) == plan["plan_sha256"], "Immutable plan identity mismatch")
check(len(plan["dependencies"]) == 340, "Expected 340 dependency files")
check(sum(len(x["source_files"]) for x in plan["selections"]) == 1887, "Expected 1887 generated inputs")
check(len(plan["selections"]) == len(matrix["selections"]) == 629, "Expected complete 629 planned configurations")
check(plan["plan_sha256"] == matrix["plan_sha256"], "Matrix belongs to another plan")
check(native.dependencies() == plan["dependencies"], "Computed runtime dependency closure changed")
inputs = [plan["source_matrix_record"], *plan["dependencies"], *plan["models"],
          *(f for selection in plan["selections"] for f in selection["source_files"])]
unique = {}
for item in inputs:
    previous = unique.setdefault(item["path"], item)
    check(previous == item, f"Conflicting input fingerprint: {item['path']}")
input_records = []
for path, expected in unique.items():
    actual = native.fingerprint(Path(path))
    valid = actual["path"] == expected["path"] and actual["sha256"] == expected["sha256"] and actual["bytes"] == expected.get("bytes",expected.get("size"))
    check(valid, f"Input bytes/SHA changed: {path}")
    input_records.append({"path":path,"sha256":actual["sha256"],"bytes":actual["bytes"],"verified":valid})
completed = []
scenarios = {}
for expected, current in zip(plan["selections"], matrix["selections"]):
    check(all(current.get(key) == value for key,value in expected.items()), f"Planned case fields changed: {expected['case_id']}")
    if current.get("status") != "completed": continue
    try:
        native.verify_completed(current["attempts"][-1], plan, current)
        evidence = json.loads(Path(current["attempts"][-1]["evidence"]["path"]).read_text())
        result = current["result"]
        completed.append({"case_id":current["case_id"],"scenario":current["scenario"],"configuration_index":current["configuration_index"],
                          "evidence_sha256":current["attempts"][-1]["evidence"]["sha256"],"retained_files":len(evidence["files"]),
                          "inference_ticks":result["inference"]["ticks"],"survival_passed":result["survival_passed"],
                          "survival_metrics":{k:v for k,v in result.items() if "survival" in k or "fall" in k or "threshold" in k},"quality_verified":result["quality_verified"],
                          "obstacle_course_completion_verified":result["obstacle_course_completion_verified"],"verified":True})
    except (OSError,ValueError,KeyError,TypeError) as error:
        errors.append(f"{current['case_id']}: {type(error).__name__}: {error}")
    bucket = scenarios.setdefault(current["scenario"], {"completed":0,"heuristic_survival":0,"threshold_event":0})
    bucket["completed"] += 1
    bucket["heuristic_survival"] += bool(current["result"].get("survival_passed"))
    bucket["threshold_event"] += not bool(current["result"].get("survival_passed"))
processes=[]
for entry in Path("/proc").glob("[0-9]*"):
    try:
        command=(entry/"cmdline").read_bytes().decode().split("\0")
        if str(native.ROOT/"scripts/research/sim2sim_scene_matrix.py") in command or str(native.ROOT/"scripts/research/sim2sim.py") in command:
            processes.append(process(int(entry.name)))
        elif any("holosoma_inference" in value or "holosoma.sim2sim" in value for value in command):
            processes.append(process(int(entry.name)))
    except (OSError, UnicodeError): pass
driver = process(18565)
check(str(native.ROOT/"scripts/research/sim2sim_scene_matrix.py") in driver["cmdline"], "Expected live driver PID18565 command")
states=Counter(x.get("status","planned") for x in matrix["selections"])
report={"observed_utc":now(),"status":"verified_wait" if not errors else "anomaly", "matrix_status":matrix["status"],
        "captured_matrix_sha256":sha(base/"captured-matrix.json"),"captured_plan_sha256":sha(base/"captured-plan.json"),
        "plan_identity":plan["plan_sha256"],"image_id":plan["image_id"],"driver_source_sha256":sha(native.__file__),
        "driver":driver,"related_processes":processes,"case_states":dict(states),"completed_evidence_verified":len(completed),
        "completed_policy_ticks_500":sum(x["inference_ticks"]==500 for x in completed),
        "heuristic_survival":sum(bool(x["survival_passed"]) for x in completed),
        "threshold_events":sum(not bool(x["survival_passed"]) for x in completed),"scenarios":scenarios,
        "planned_dependencies":len(plan["dependencies"]),"generated_input_entries":1887,"unique_input_files_verified":len(input_records),
        "input_records":input_records,"completed":completed,"errors":errors,
        "top_level_derived_counts_may_be_previous_invocation":{key:matrix.get(key) for key in ("completed_configurations","completed_scenarios","finished_unix")},
        "scope":"One captured running matrix; completed evidence only, not all629 passed or verified course completion",
        "gpu_job_started_by_audit":False,"quality_verified":False}
(base/"local-report.json").write_text(json.dumps(report,indent=2)+"\n")
for path in base.glob("*.json"): path.chmod(0o644)
print(json.dumps({key:report[key] for key in ("observed_utc","status","case_states","completed_evidence_verified","heuristic_survival","threshold_events","planned_dependencies","generated_input_entries","unique_input_files_verified","errors")},indent=2))
