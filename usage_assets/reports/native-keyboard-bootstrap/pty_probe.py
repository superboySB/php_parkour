"""Bounded actual sshkeyboard/native listener PTY test; no GUI, DDS or simulator."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
KEYS = ["]", "w", "c", "o", "i"]


def child(mode):
    import sshkeyboard
    from holosoma_inference.inputs.impl import keyboard as native
    if mode == "patched":
        spec = importlib.util.spec_from_file_location("native_keyboard_bootstrap", HERE / "proposed/run_native_policy.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.install_keyboard_compat()
    errors = []
    def capture(args):
        errors.append({"type": args.exc_type.__name__, "message": str(args.exc_value)})
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = capture
    listener = native._KeyboardListenerThread()
    first, second = listener.subscribe(), listener.subscribe()
    active = listener.start()
    deadline = time.monotonic() + 5
    while not sshkeyboard._running and listener.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert active and sys.stdin.isatty() and sshkeyboard._running
    print("PTY_READY " + json.dumps({"mode": mode, "active": active, "stdin_isatty": sys.stdin.isatty()}), flush=True)
    listener.join(timeout=12)
    timed_out = listener.is_alive()
    if timed_out:
        sshkeyboard.stop_listening()
        listener.join(timeout=2)
    report = {"mode": mode, "active": active, "stdin_isatty": sys.stdin.isatty(),
              "first_subscriber": list(first), "second_subscriber": list(second),
              "listener_alive_after_escape": listener.is_alive(), "errors": errors,
              "timed_out": timed_out, "sshkeyboard_version": importlib.metadata.version("sshkeyboard"),
              "native_source_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
              "dependency_source_sha256": hashlib.sha256(Path(sshkeyboard.__file__).read_bytes()).hexdigest()}
    print("PTY_RESULT " + json.dumps(report, sort_keys=True), flush=True)


def run_case(mode):
    master, slave = pty.openpty()
    before_tty, before_flags = termios.tcgetattr(slave), fcntl.fcntl(slave, fcntl.F_GETFL)
    process = None
    data = b""
    def read_tag(tag, timeout):
        nonlocal data
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in data.decode(errors="replace").splitlines():
                if line.startswith(tag):
                    return json.loads(line[len(tag):])
            if select.select([process.stdout], [], [], max(0, deadline-time.monotonic()))[0]:
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                data += chunk
        raise RuntimeError(f"No {tag} from {mode}: {data.decode(errors='replace')}")
    try:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--child", mode],
                                   stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        ready = read_tag("PTY_READY ", 8)
        for key in KEYS:
            os.write(master, key.encode())
            time.sleep(0.10)
        time.sleep(0.20)
        os.write(master, b"\x1b")
        result = read_tag("PTY_RESULT ", 8)
        process.wait(timeout=3)
        data += process.stdout.read()
        result.update(child_exit_code=process.returncode, ready=ready,
                      terminal_attributes_restored=termios.tcgetattr(slave)==before_tty,
                      terminal_flags_restored=fcntl.fcntl(slave,fcntl.F_GETFL)==before_flags)
        assert result["child_exit_code"] == 0
        assert not result["listener_alive_after_escape"] and not result["timed_out"]
        assert result["first_subscriber"] == result["second_subscriber"] == KEYS
        assert result["terminal_attributes_restored"] and result["terminal_flags_restored"]
        if mode == "original":
            assert len(result["errors"]) == 1 and result["errors"][0]["type"] == "AttributeError"
            assert "'NoneType' object has no attribute 'start'" in result["errors"][0]["message"]
        else:
            assert result["errors"] == []
        result["expected_observation_passed"] = True
        return result
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        os.close(master)
        os.close(slave)
        (HERE / f"pty-{mode}.log").write_bytes(data)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        result = {"schema_version": 1, "scope": "Actual native class + installed sshkeyboard2.3.1 reading kernel PTY bytes; no GUI/key-window, GPU, SDK or DDS",
                  "cases": [run_case("original"), run_case("patched")],
                  "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "gui_controls_verified": False}
        (HERE / "pty-report.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
