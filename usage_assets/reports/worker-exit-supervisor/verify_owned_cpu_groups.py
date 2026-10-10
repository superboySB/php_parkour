"""Actual, owned plain-Python process groups only; no DDS or simulator imports."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owned_group_candidate", HERE / "sim2sim.py")
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def birth_group(process):
    identity = CANDIDATE.process_identity(process.pid)
    assert identity["process_group_id"] == identity["session_id"] == process.pid
    birth = {"pid": process.pid, "start_time_clock_ticks": identity["start_time_clock_ticks"]}
    return {"process_group_id": process.pid, "session_id": process.pid, "leader_identity": birth,
            "known_members": [dict(birth)], "retired": False, "ownership_lost": False}, identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    assert os.environ.get("PHP_DOCKER") == "1", "Run this actual CPU process test in Docker only"
    owned = []
    logs = []
    cases = []
    fallback = []

    def spawn(name, code, *extra):
        log = (output / f"{name}.log").open("w")
        logs.append(log)
        argv = [sys.executable, "-u", "-c", code, *map(str, extra)]
        process = subprocess.Popen(argv, start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
        group, identity = birth_group(process)
        owned.append((process, group))
        save(output / f"{name}-launch.json", {"argv": argv, "start_new_session": True, "identity": identity})
        return process, group

    try:
        direct, direct_group = spawn("direct-term", "import time; time.sleep(60)")
        before = CANDIDATE.worker_group_status(direct_group)
        assert before["ownership_verified"] and before["live_members"]
        assert CANDIDATE.signal_worker_group(direct_group, signal.SIGTERM)
        assert CANDIDATE.wait_worker_shutdown(direct, direct_group, 2)
        direct_final = CANDIDATE.worker_group_status(direct_group)
        assert direct.returncode == -signal.SIGTERM and direct_final["live_members"] == []
        cases.append({"case": "actual_direct_group_term", "status": "passed", "before": before,
                      "direct_status": CANDIDATE.process_return_status(direct), "final": direct_final})

        child_code = """import json,os,pathlib,signal,sys,time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'sid':os.getsid(0)}))
time.sleep(60)
"""
        launcher_code = """import pathlib,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-u','-c',sys.argv[1],sys.argv[2]])
while not pathlib.Path(sys.argv[2]).exists():time.sleep(.01)
while not pathlib.Path(sys.argv[3]).exists():time.sleep(.01)
"""
        child_ready = output / "orphan-child-ready.json"
        release = output / "release-wrapper"
        wrapper, group = spawn("wrapper-with-child", launcher_code, child_code, child_ready, release)
        deadline = time.monotonic() + 5
        while not child_ready.exists():
            assert wrapper.poll() is None and time.monotonic() < deadline
            time.sleep(.01)
        child = json.loads(child_ready.read_text())
        assert child["pgid"] == child["sid"] == wrapper.pid
        initial = CANDIDATE.worker_group_status(group)
        child_identity = CANDIDATE.process_identity(child["pid"])
        owned_child = {"pid": child["pid"], "start_time_clock_ticks": child_identity["start_time_clock_ticks"]}
        assert owned_child in group["known_members"]
        release.touch()
        assert wrapper.wait(timeout=3) == 0
        orphan = CANDIDATE.worker_group_status(group)
        assert orphan["ownership_verified"] and any(m["pid"] == child["pid"] for m in orphan["live_members"])
        assert not CANDIDATE.wait_worker_shutdown(wrapper, group, .15)
        assert CANDIDATE.signal_worker_group(group, signal.SIGTERM)
        assert not CANDIDATE.wait_worker_shutdown(wrapper, group, .15), "Owned child explicitly ignores TERM"
        after_term = CANDIDATE.worker_group_status(group)
        assert CANDIDATE.signal_worker_group(group, signal.SIGKILL)
        assert CANDIDATE.wait_worker_shutdown(wrapper, group, 3)
        final = CANDIDATE.worker_group_status(group)
        assert final["ownership_verified"] and final["retired"] and final["live_members"] == []
        cases.append({"case": "actual_zero_wrapper_owned_orphan_term_then_kill", "status": "passed",
                      "initial": initial, "child_identity": child_identity, "wrapper_status": CANDIDATE.process_return_status(wrapper),
                      "after_wrapper_zero": orphan, "after_term": after_term, "final": final})

        foreign, foreign_group = spawn("different-owned-group", "import time; time.sleep(60)")
        incorrect_group = copy.deepcopy(group)
        incorrect_group.update(process_group_id=foreign.pid, session_id=foreign.pid)
        refused = False
        try:
            CANDIDATE.signal_worker_group(incorrect_group, signal.SIGTERM)
        except RuntimeError as error:
            refused = True
            refusal = str(error)
        assert refused and foreign.poll() is None
        assert CANDIDATE.signal_worker_group(foreign_group, signal.SIGTERM)
        assert CANDIDATE.wait_worker_shutdown(foreign, foreign_group, 2)
        cases.append({"case": "different_group_not_owned_by_old_identity_is_refused", "status": "passed",
                      "refusal": refusal, "still_alive_before_its_own_authorized_cleanup": True,
                      "final_after_own_cleanup": CANDIDATE.worker_group_status(foreign_group)})
    finally:
        for process, group in owned:
            try:
                if not CANDIDATE.wait_worker_shutdown(process, group, .2):
                    fallback.append({"pid": process.pid, "action": "candidate group KILL cleanup"})
                    CANDIDATE.signal_worker_group(group, signal.SIGKILL)
                    assert CANDIDATE.wait_worker_shutdown(process, group, 3)
            except BaseException as error:
                fallback.append({"pid": process.pid, "error": str(error)})
        for log in logs:
            log.close()
        report = {"schema_version": 1, "status": "passed" if len(cases) == 3 and not fallback else "failed",
                  "candidate_sha256": hashlib.sha256((HERE / "sim2sim.py").read_bytes()).hexdigest(),
                  "scope": "Actual owned ordinary CPU Python groups in Docker. No SDK, DDS, MuJoCo, Isaac, ONNX or GPU.",
                  "actual_group_signals": True, "cases": cases, "cleanup_fallback": fallback,
                  "limits": ["This does not verify actual SDK018, native shell launchers or simulator cleanup.",
                             "Orphan zombies may remain pending system-init reaping; only non-Z live members are gated."]}
        save(output / "result.json", report)
    assert report["status"] == "passed", report
    print(json.dumps({"status": report["status"], "cases": len(cases), "cleanup_fallback": fallback,
                      "candidate_sha256": report["candidate_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
