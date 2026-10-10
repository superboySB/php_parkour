"""CPU fixtures only: every subprocess.Popen/run in main is replaced.

These tests never import Holosoma, DDS, ONNX, MuJoCo or Isaac. Dummy model/video
bytes are not physics/media evidence. These regressions exercise the applied supervisor source.
"""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("worker_exit_candidate", Path(__file__).resolve().parents[1] / "scripts/research/sim2sim.py")
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)


class Process:
    def __init__(self, pid, wait_plan=(), terminate_exits=True, kill_exits=True):
        self.pid = pid
        self.returncode = None
        self.wait_plan = list(wait_plan)
        self.terminate_exits = terminate_exits
        self.kill_exits = kill_exits
        self.actions = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.actions.append(("wait", timeout))
        item = self.wait_plan.pop(0) if self.wait_plan else 0
        if item == "timeout":
            raise subprocess.TimeoutExpired(["fixture"], timeout)
        self.returncode = item if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self):
        self.actions.append(("terminate", None))
        if self.terminate_exits:
            self.returncode = -15

    def kill(self):
        self.actions.append(("kill", None))
        if self.kill_exits:
            self.returncode = -9


class Harness:
    def __init__(self, root, mode="success", process_options=None, child_error=False,
                 child_term_exits=True, child_kill_exits=True):
        self.root = root
        self.output = root / "out"
        self.models = root / "models"
        self.models.mkdir()
        for name in ["student.onnx", "depth_backbone.onnx"]:
            (self.models / name).write_bytes(b"synthetic CPU fixture, not ONNX")
        self.mode = mode
        self.process_options = process_options or {}
        self.child_error = child_error
        self.processes = []
        self.environments = []
        self.logs = []
        self.group_signals = []
        self.child_live = mode == "wrapper_exit_child_live"
        self.child_term_exits = child_term_exits
        self.child_kill_exits = child_kill_exits
        self.clock = 0.0
        self.spawn_receipt_before_second_launch = None

    def popen(self, argv, **kwargs):
        assert kwargs["start_new_session"] is True
        self.logs.append(kwargs["stdout"])
        role = argv[argv.index("--worker") + 1]
        if role == "inference":
            self.spawn_receipt_before_second_launch = json.loads((self.output / "worker-processes.json").read_text())
            if self.child_error:
                raise OSError("fixture second launch failed")
        process = Process(91001 + len(self.processes), **self.process_options.get(role, {}))
        self.processes.append(process)
        self.environments.append(dict(kwargs["env"]))
        native_pid = 92001 + len(self.processes) - 1
        (self.output / f"{role}-process-start.json").write_text(json.dumps({"schema_version": 1, "role": role,
            "argv": argv, "process": {"pid": native_pid, "process_group_id": process.pid,
            "session_id": process.pid, "start_time_clock_ticks": process.pid + 101}, "python_faulthandler": None}))
        if role == "simulator":
            if self.mode not in ["startup_timeout", "startup_exit"]:
                (self.output / "sim-ready.json").write_text('{"ready": true, "pid": 92001}')
            if self.mode == "startup_exit":
                process.returncode = 7
            (self.output / "simulation.json").write_text('{"status":"completed","fall_detected":false}')
            video = self.output / "video" / "fixture.mp4"
            video.parent.mkdir()
            video.write_bytes(b"synthetic CPU fixture, not MP4")
        else:
            (self.output / "inference.json").write_text('{"status":"completed","ticks":500,"samples":[]}')
            if self.mode == "both_already_failed":
                self.processes[0].returncode = 1
                process.returncode = -11
        return process

    def group_members(self, pgid, sid):
        assert pgid == sid
        members = []
        for process in self.processes:
            if process.pid == pgid and process.returncode is None:
                members.append({"pid": process.pid, "process_group_id": pgid, "session_id": sid, "state": "S",
                                "start_time_clock_ticks": process.pid + 100})
                members.append({"pid": 92001 + self.processes.index(process), "process_group_id": pgid,
                                "session_id": sid, "state": "S", "start_time_clock_ticks": process.pid + 101})
        if self.processes and pgid == self.processes[0].pid and self.child_live:
            members.append({"pid": 93001, "process_group_id": pgid, "session_id": sid, "state": "S",
                            "start_time_clock_ticks": 94001})
        return members

    def killpg(self, pgid, number):
        self.group_signals.append((pgid, number))
        process = next(process for process in self.processes if process.pid == pgid)
        if number == 15:
            if process.returncode is None:
                process.terminate()
            if self.child_term_exits:
                self.child_live = False
        elif number == 9:
            if process.returncode is None:
                process.kill()
            if self.child_kill_exits:
                self.child_live = False
        else:
            raise AssertionError("Unexpected group signal")

    def sleep(self, duration):
        self.clock += duration
        if self.mode in ["success", "postprocess_failure", "wrapper_exit_child_live"]:
            for process in self.processes:
                process.returncode = 0
        elif self.mode == "policy_crash":
            self.processes[1].returncode = -11
        elif self.mode == "interrupt":
            raise KeyboardInterrupt("fixture interrupt")

    def run(self, argv, **kwargs):
        if self.mode == "postprocess_failure":
            raise subprocess.CalledProcessError(9, argv)
        if argv[0] == "ffprobe":
            return subprocess.CompletedProcess(argv, 0, stdout='{"format":{"duration":"1"},"streams":[]}')
        if argv[0] == "ffmpeg":
            Path(argv[-1]).write_bytes(b"synthetic PNG fixture")
            return subprocess.CompletedProcess(argv, 0)
        raise AssertionError("Unexpected subprocess.run escaped fixture: " + repr(argv))

    def main(self, extra=()):
        argv = ["sim2sim.py", "--models", str(self.models), "--output", str(self.output),
                "--startup-timeout", "0.1", "--wall-timeout", "0.1", *extra]
        original_identity = CANDIDATE.process_identity
        def identity(pid):
            value = original_identity(pid)
            if 91001 <= pid <= 91002:
                value = {"pid": pid, "process_group_id": pid, "session_id": pid,
                         "start_time_clock_ticks": pid + 100, "fixture": "synthetic CPU identity"}
            return value
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {"PHP_DOCKER": "1"}), \
             mock.patch.object(CANDIDATE, "process_identity", side_effect=identity), \
             mock.patch.object(CANDIDATE.subprocess, "Popen", side_effect=self.popen), \
             mock.patch.object(CANDIDATE.subprocess, "run", side_effect=self.run), \
             mock.patch.object(CANDIDATE, "process_group_members", side_effect=self.group_members), \
             mock.patch.object(CANDIDATE.os, "killpg", side_effect=self.killpg), \
             mock.patch.object(CANDIDATE.time, "monotonic", side_effect=lambda: self.clock), \
             mock.patch.object(CANDIDATE.time, "sleep", side_effect=self.sleep), \
             mock.patch("builtins.print"):
            CANDIDATE.main()

    def events(self):
        return json.loads((self.output / "worker-processes.json").read_text())["events"]


class WorkerExitTests(unittest.TestCase):
    @staticmethod
    def group(pgid=91001, birth=100):
        leader = {"pid": pgid, "start_time_clock_ticks": birth} if birth is not None else None
        return {"process_group_id": pgid, "session_id": pgid, "leader_identity": leader,
                "known_members": [dict(leader)] if leader else [], "retired": False, "ownership_lost": False}

    @staticmethod
    def member(pid=91001, birth=100):
        return {"pid": pid, "start_time_clock_ticks": birth, "process_group_id": 91001, "session_id": 91001, "state": "S"}

    def fixture(self, mode="success", **kwargs):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Harness(Path(directory.name), mode, **kwargs)

    def test_status_preserves_signed_codes_and_does_not_infer_wrapper_signal(self):
        process = Process(1)
        for code, number, name in [(None, None, None), (0, None, None), (1, None, None), (-11, 11, "SIGSEGV"),
                                   (-15, 15, "SIGTERM"), (-9, 9, "SIGKILL"), (-999, 999, "UNKNOWN")]:
            with self.subTest(code=code):
                process.returncode = code
                report = CANDIDATE.process_return_status(process)
                self.assertEqual((report["returncode"], report["signal_number"], report["signal_name"]), (code, number, name))

    def test_current_process_identity_records_namespace_and_start_time(self):
        report = CANDIDATE.process_identity(os.getpid())
        self.assertEqual(report["pid"], os.getpid())
        self.assertEqual(int(report["proc_status"]["Pid"]), os.getpid())
        self.assertGreater(report["start_time_clock_ticks"], 0)

    def test_exited_identity_is_explicitly_unavailable(self):
        report = CANDIDATE.process_identity(99999999)
        self.assertEqual(report["pid"], 99999999)
        self.assertIn("proc_unavailable", report)

    def test_normal_completion_and_final_wait_record_both_zero(self):
        harness = self.fixture()
        harness.main()
        self.assertTrue((harness.output / "result.json").exists())
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [0, 0])
        self.assertEqual(harness.events()[-1]["event"], "finally_wait_complete")

    def test_spawn_pid_is_persisted_before_second_worker_launch(self):
        harness = self.fixture()
        harness.main()
        entry = harness.spawn_receipt_before_second_launch["events"][-1]
        self.assertEqual(entry["event"], "worker_spawned")
        self.assertEqual(entry["workers"][0]["identity_at_spawn"]["pid"], 91001)
        self.assertEqual(entry["workers"][0]["role"], "simulator")

    def test_native_entry_receipt_is_hashed_and_bound_to_observed_birth(self):
        harness = self.fixture()
        harness.main()
        entries = [event for event in harness.events() if event["event"] == "worker_entry_observed"]
        self.assertEqual({event["role"] for event in entries}, {"simulator", "inference"})
        for event in entries:
            worker = next(value for value in event["workers"] if value["role"] == event["role"])
            entry = event["entry_process"]
            self.assertNotEqual(entry["pid"], worker["identity_at_spawn"]["pid"])
            self.assertIn({"pid": entry["pid"], "start_time_clock_ticks": entry["start_time_clock_ticks"]},
                          worker["process_group"]["known_members"])
            data = (harness.output / f"{event['role']}-process-start.json").read_bytes()
            self.assertEqual(event["entry_sha256"], hashlib.sha256(data).hexdigest())

    def test_both_workers_already_nonzero_cannot_skip_terminal_gate(self):
        harness = self.fixture("both_already_failed")
        with self.assertRaisesRegex(RuntimeError, "Workers ended with nonzero"):
            harness.main()
        self.assertFalse((harness.output / "result.json").exists())
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [1, -11])

    def test_policy_crash_error_snapshot_precedes_survivor_final_wait(self):
        harness = self.fixture("policy_crash")
        with self.assertRaisesRegex(RuntimeError, "A worker failed"):
            harness.main()
        error = json.loads((harness.output / "error.json").read_text())
        self.assertEqual([w["returncode"] for w in error["worker_status_at_error"]["workers"]], [None, -11])
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [0, -11])

    def test_premature_startup_exit_is_retained(self):
        harness = self.fixture("startup_exit")
        with self.assertRaisesRegex(RuntimeError, "before initialization"):
            harness.main()
        self.assertEqual(harness.events()[-1]["workers"][0]["returncode"], 7)

    def test_startup_timeout_retains_pending_and_final_status(self):
        harness = self.fixture("startup_timeout")
        with self.assertRaisesRegex(TimeoutError, "initialization timeout"):
            harness.main()
        detected = next(e for e in harness.events() if e["event"] == "error_detected")
        self.assertIsNone(detected["workers"][0]["returncode"])
        self.assertEqual(harness.events()[-1]["workers"][0]["returncode"], 0)

    def test_rollout_timeout_records_both_pending_then_waited(self):
        harness = self.fixture("wall_timeout")
        with self.assertRaisesRegex(TimeoutError, "time bound"):
            harness.main()
        detected = next(e for e in harness.events() if e["event"] == "error_detected")
        self.assertEqual([w["returncode"] for w in detected["workers"]], [None, None])
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [0, 0])

    def test_cleanup_terminate_receipt_preserves_sigterm(self):
        harness = self.fixture("policy_crash", process_options={"simulator": {"wait_plan": ["timeout"]}})
        with self.assertRaises(RuntimeError):
            harness.main()
        self.assertIn("terminate_requested", [e["event"] for e in harness.events()])
        self.assertEqual(harness.events()[-1]["workers"][0]["signal_name"], "SIGTERM")

    def test_cleanup_kill_is_waited_and_preserves_sigkill(self):
        harness = self.fixture("policy_crash", process_options={"simulator": {"wait_plan": ["timeout", "timeout"], "terminate_exits": False}})
        with self.assertRaises(RuntimeError):
            harness.main()
        self.assertIn("kill_requested", [e["event"] for e in harness.events()])
        self.assertEqual(harness.events()[-1]["workers"][0]["signal_name"], "SIGKILL")
        self.assertEqual(harness.processes[0].actions[-1], ("wait", 5))

    def test_unreaped_after_kill_remains_pending_not_success(self):
        harness = self.fixture("policy_crash", process_options={"simulator": {"wait_plan": ["timeout", "timeout", "timeout"], "terminate_exits": False, "kill_exits": False}})
        with self.assertRaises(RuntimeError):
            harness.main()
        self.assertEqual(harness.events()[-1]["unreaped_roles"], ["simulator"])
        self.assertIsNone(harness.events()[-1]["workers"][0]["returncode"])
        self.assertFalse((harness.output / "result.json").exists())

    def test_wrapper_zero_with_live_child_cannot_be_completed(self):
        harness = self.fixture("wrapper_exit_child_live")
        with self.assertRaisesRegex(RuntimeError, "groups remain live"):
            harness.main()
        self.assertFalse((harness.output / "result.json").exists())
        self.assertEqual(harness.group_signals, [(91001, 15)])
        self.assertFalse(harness.child_live)
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [0, 0])
        self.assertEqual(harness.events()[-1]["workers"][0]["process_group"]["live_members"], [])

    def test_orphan_child_receives_group_term_then_kill_even_with_zero_wrapper(self):
        harness = self.fixture("wrapper_exit_child_live", child_term_exits=False)
        with self.assertRaisesRegex(RuntimeError, "groups remain live"):
            harness.main()
        self.assertEqual(harness.group_signals, [(91001, 15), (91001, 9)])
        self.assertFalse(harness.child_live)
        self.assertTrue(all(log.closed for log in harness.logs))

    def test_still_live_group_after_kill_is_final_failure(self):
        harness = self.fixture("wrapper_exit_child_live", child_term_exits=False, child_kill_exits=False)
        with self.assertRaisesRegex(RuntimeError, "remain unreaped"):
            harness.main()
        final = harness.events()[-1]
        self.assertEqual(final["unreaped_roles"], ["simulator"])
        self.assertEqual(final["workers"][0]["returncode"], 0)
        self.assertEqual(final["workers"][0]["process_group"]["live_members"][0]["pid"], 93001)
        self.assertFalse((harness.output / "result.json").exists())

    def test_process_group_scan_filters_session_other_groups_and_zombies(self):
        with tempfile.TemporaryDirectory() as directory:
            proc_root = Path(directory)
            for pid, state, pgid, sid in [(100, "S", 100, 100), (101, "R", 100, 100),
                                          (102, "Z", 100, 100), (103, "S", 100, 900), (104, "S", 500, 500)]:
                child = proc_root / str(pid)
                child.mkdir()
                fields = [state, "1", str(pgid), str(sid)] + ["0"] * 15 + ["12345"]
                (child / "stat").write_text(str(pid) + " (fixture with space) " + " ".join(fields))
            with mock.patch.object(CANDIDATE, "Path", return_value=proc_root):
                members = CANDIDATE.process_group_members(100, 100)
            self.assertEqual([item["pid"] for item in members], [100, 101])
            self.assertTrue(all(item["start_time_clock_ticks"] == 12345 for item in members))

    def test_signal_never_targets_parent_unisolated_or_empty_foreign_group(self):
        with mock.patch.object(CANDIDATE.os, "getpgrp", return_value=100), \
             mock.patch.object(CANDIDATE.os, "killpg") as kill, \
             mock.patch.object(CANDIDATE, "process_group_members", return_value=[]):
            for pgid, sid in [(1, 1), (100, 100), (200, 300)]:
                with self.subTest(pgid=pgid, sid=sid), self.assertRaises(RuntimeError):
                    CANDIDATE.signal_worker_group({"process_group_id": pgid, "session_id": sid}, 9)
            self.assertFalse(CANDIDATE.signal_worker_group(self.group(200), 9))
            kill.assert_not_called()

    def test_reused_leader_birth_is_not_signalled_even_with_old_orphan_anchor(self):
        group = self.group()
        group["known_members"].append({"pid": 91002, "start_time_clock_ticks": 101})
        for members in [[self.member(birth=999)], [self.member(birth=999), self.member(91002, 101)]]:
            with self.subTest(members=members), mock.patch.object(CANDIDATE, "process_group_members", return_value=members), \
                 mock.patch.object(CANDIDATE.os, "killpg") as kill, self.assertRaisesRegex(RuntimeError, "unknown worker group"):
                CANDIDATE.signal_worker_group(group, 15)
            kill.assert_not_called()

    def test_only_unknown_orphan_is_not_signalled_or_absorbed(self):
        group = self.group()
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member(92002, 102)]), \
             mock.patch.object(CANDIDATE.os, "killpg") as kill, self.assertRaisesRegex(RuntimeError, "unknown worker group"):
            CANDIDATE.signal_worker_group(group, 15)
        kill.assert_not_called()
        self.assertEqual(group["known_members"], [{"pid": 91001, "start_time_clock_ticks": 100}])

    def test_known_orphan_can_anchor_group_after_leader_exit(self):
        group = self.group()
        group["known_members"].append({"pid": 91002, "start_time_clock_ticks": 101})
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member(91002, 101), self.member(92002, 102)]), \
             mock.patch.object(CANDIDATE.os, "killpg") as kill:
            self.assertTrue(CANDIDATE.signal_worker_group(group, 15))
        kill.assert_called_once_with(91001, 15)
        self.assertIn({"pid": 92002, "start_time_clock_ticks": 102}, group["known_members"])

    def test_empty_retired_group_never_revives_by_numeric_or_old_identity_match(self):
        for member in [self.member(birth=999), self.member()]:
            group = self.group()
            with mock.patch.object(CANDIDATE, "process_group_members", return_value=[]):
                self.assertTrue(CANDIDATE.worker_group_status(group)["ownership_verified"])
            self.assertTrue(group["retired"])
            with self.subTest(member=member), mock.patch.object(CANDIDATE, "process_group_members", return_value=[member]), \
                 mock.patch.object(CANDIDATE.os, "killpg") as kill, self.assertRaisesRegex(RuntimeError, "unknown worker group"):
                CANDIDATE.signal_worker_group(group, 9)
            kill.assert_not_called()

    def test_unavailable_spawn_birth_never_trusts_or_signals_new_members(self):
        group = self.group(birth=None)
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member()]), \
             mock.patch.object(CANDIDATE.os, "killpg") as kill, self.assertRaisesRegex(RuntimeError, "unknown worker group"):
            CANDIDATE.signal_worker_group(group, 9)
        kill.assert_not_called()

    def test_event_group_snapshots_do_not_mutate_when_members_are_absorbed(self):
        group = self.group()
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member()]):
            before = CANDIDATE.worker_group_status(group)
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member(), self.member(92002, 102)]):
            after = CANDIDATE.worker_group_status(group)
        self.assertEqual(len(before["known_members"]), 1)
        self.assertEqual(len(after["known_members"]), 2)

    def test_proc_observation_loss_is_sticky_and_prevents_later_signals(self):
        group = self.group()
        with mock.patch.object(CANDIDATE, "process_group_members", side_effect=PermissionError("fixture denied")):
            self.assertFalse(CANDIDATE.worker_group_status(group)["ownership_verified"])
        with mock.patch.object(CANDIDATE, "process_group_members", return_value=[self.member()]), \
             mock.patch.object(CANDIDATE.os, "killpg") as kill, self.assertRaisesRegex(RuntimeError, "unknown worker group"):
            CANDIDATE.signal_worker_group(group, 9)
        kill.assert_not_called()

    def test_group_scan_error_is_explicit_unknown_and_cannot_pass(self):
        with mock.patch.object(CANDIDATE, "process_group_members", side_effect=PermissionError("fixture denied")):
            report = CANDIDATE.worker_group_status({"process_group_id": 100, "session_id": 100})
        self.assertIsNone(report["live_members"])
        self.assertIn("fixture denied", report["observation_error"])

    def test_receipt_write_failures_still_reap_group_close_logs_and_fail(self):
        original = CANDIDATE.save
        for event in ["worker_spawned", "finally_enter", "terminate_requested", "kill_requested", "finally_wait_complete"]:
            with self.subTest(event=event):
                harness = self.fixture("wrapper_exit_child_live", child_term_exits=False)
                failed = []
                def save(path, value):
                    events = value.get("events", [])
                    if path.name == "worker-processes.json" and events[-1]["event"] == event and not failed:
                        failed.append(True)
                        raise OSError("fixture receipt write failed: " + event)
                    return original(path, value)
                with mock.patch.object(CANDIDATE, "save", side_effect=save), \
                     self.assertRaisesRegex(OSError, "fixture receipt write failed"):
                    harness.main()
                self.assertTrue(failed)
                self.assertFalse(harness.child_live)
                self.assertTrue(all(log.closed for log in harness.logs))
                self.assertEqual(harness.group_signals, [(91001, 15), (91001, 9)])

    def test_stop_marker_io_failure_still_reaps_group_and_closes_logs(self):
        harness = self.fixture("wrapper_exit_child_live", child_term_exits=False)
        original = Path.touch
        def touch(path, *args, **kwargs):
            if path == harness.output / "stop":
                raise OSError("fixture stop marker failed")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "touch", new=touch), self.assertRaisesRegex(OSError, "stop marker failed"):
            harness.main()
        self.assertFalse(harness.child_live)
        self.assertTrue(all(log.closed for log in harness.logs))

    def test_spawn_identity_failure_is_unknown_and_never_blindly_signalled(self):
        harness = self.fixture("wrapper_exit_child_live", child_term_exits=False)
        original = CANDIDATE.process_identity
        def identity(pid):
            if pid == 91001:
                raise OSError("fixture identity read failed")
            return original(pid)
        with mock.patch.object(CANDIDATE, "process_identity", side_effect=identity), \
             self.assertRaisesRegex(RuntimeError, "ownership unknown"):
            harness.main()
        self.assertTrue(harness.child_live)
        self.assertEqual(harness.group_signals, [])
        self.assertTrue(all(log.closed for log in harness.logs))
        self.assertEqual(harness.events()[-1]["workers"][0]["identity_at_spawn"]["pid"], 91001)
        self.assertEqual(harness.events()[-1]["unreaped_roles"], ["simulator"])

    def test_partial_spawn_failure_retains_first_pid_and_final_status(self):
        harness = self.fixture(child_error=True)
        with self.assertRaisesRegex(OSError, "second launch"):
            harness.main()
        self.assertEqual(len(harness.events()[-1]["workers"]), 1)
        self.assertEqual(harness.events()[-1]["workers"][0]["identity_at_spawn"]["pid"], 91001)
        self.assertEqual(harness.events()[-1]["workers"][0]["returncode"], 0)

    def test_postprocess_failure_keeps_zero_worker_codes_and_failed_parent(self):
        harness = self.fixture("postprocess_failure")
        with self.assertRaises(subprocess.CalledProcessError):
            harness.main()
        self.assertFalse((harness.output / "result.json").exists())
        self.assertEqual([w["returncode"] for w in harness.events()[-1]["workers"]], [0, 0])

    def test_keyboard_interrupt_still_writes_final_receipt(self):
        harness = self.fixture("interrupt")
        with self.assertRaises(KeyboardInterrupt):
            harness.main()
        detected = next(e for e in harness.events() if e["event"] == "error_detected")
        self.assertEqual(detected["error_type"], "KeyboardInterrupt")
        self.assertEqual(harness.events()[-1]["event"], "finally_wait_complete")

    def test_faulthandler_is_explicitly_propagated_to_workers(self):
        harness = self.fixture()
        harness.main(["--python-faulthandler"])
        self.assertTrue(json.loads((harness.output / "run.json").read_text())["python_faulthandler"])
        self.assertTrue(all(env["PYTHONFAULTHANDLER"] == "1" for env in harness.environments))

    def test_worker_self_pid_is_written_before_function_and_no_exit_claim(self):
        harness = self.fixture()
        harness.output.mkdir()
        (harness.output / "run.json").write_text("{}")
        observed = []
        def body(config, output):
            observed.append(json.loads((output / "simulator-process-start.json").read_text()))
        with mock.patch.object(sys, "argv", ["sim2sim.py", "--worker", "simulator", "--output", str(harness.output)]), \
             mock.patch.object(CANDIDATE, "simulator", side_effect=body), \
             mock.patch.object(CANDIDATE.subprocess, "Popen", side_effect=AssertionError("forbidden child")):
            CANDIDATE.main()
        self.assertEqual(observed[0]["process"]["pid"], os.getpid())
        self.assertNotIn("returncode", observed[0])

    def test_worker_python_exception_preserves_start_pid_and_error_json(self):
        harness = self.fixture()
        harness.output.mkdir()
        (harness.output / "run.json").write_text("{}")
        with mock.patch.object(sys, "argv", ["sim2sim.py", "--worker", "inference", "--output", str(harness.output)]), \
             mock.patch.object(CANDIDATE, "inference", side_effect=ValueError("fixture body error")), \
             mock.patch.object(CANDIDATE.subprocess, "Popen", side_effect=AssertionError("forbidden child")):
            with self.assertRaisesRegex(ValueError, "fixture body error"):
                CANDIDATE.main()
        self.assertTrue((harness.output / "inference-process-start.json").exists())
        self.assertEqual(json.loads((harness.output / "inference-error.json").read_text())["error"], "fixture body error")

    def test_isolated_command_wrapper_propagates_faulthandler(self):
        harness = self.fixture()
        args = ["sim2sim.py", "--models", str(harness.models), "--output", str(harness.output),
                "--commands", "0,1", "--isolate-commands", "--python-faulthandler"]
        with mock.patch.object(sys, "argv", args), mock.patch.dict(os.environ, {"PHP_DOCKER": "1"}), \
             mock.patch.object(CANDIDATE.subprocess, "Popen", side_effect=AssertionError("forbidden child")), \
             mock.patch.object(CANDIDATE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            CANDIDATE.main()
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all("--python-faulthandler" in call.args[0] for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main(verbosity=2)
