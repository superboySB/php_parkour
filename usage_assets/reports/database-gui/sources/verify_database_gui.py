#!/usr/bin/env python3
"""Exercise the original database player in a real CPU Chrome browser.

Project imports run only in the existing Docker motion environment. The native
observer reads main-loop locals after rendering; it never writes GUI, scene,
database, playback clock, or camera state. Controls are changed through browser
clicks and keyboard events. A fresh output directory is required for every run.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.request import urlopen

from viser_browser import CDP, free_port


CONTROLS = {
    "Auto Play": "auto_play", "Speed": "speed", "Min Frame": "min_frame_slider",
    "Max Frame": "max_frame_slider", "Frame": "frame_slider",
    "Follow Character": "camera_follow", "Camera Offset X": "camera_offset_x",
    "Camera Offset Y": "camera_offset_y", "Camera Offset Z": "camera_offset_z",
    "Camera Smoothness": "camera_smoothness", "Contact (L/R)": "contact_label_text",
    "Show Contact Markers": "show_contact_markers",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError("database GUI condition did not become true")


def native_observer(output, database):
    """Read native main-loop state using Python tracing; retain silent errors."""
    import motion_matching.play_database as player

    output = output.resolve()
    assert os.getpid() == os.getpgid(0), "Docker exec requires its own process group"
    (output / "server.pid").write_text(str(os.getpid()))
    os.chdir(output)  # Native debug-file cleanup is confined to this run.
    source = Path(player.__file__).resolve()
    tree = ast.parse(source.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    loop = next(node for node in main.body if isinstance(node, ast.While))
    sample_line = next(node.lineno for node in reversed(loop.body)
                       if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "previous_time"
                                                              for t in node.targets))
    info = {"pid": os.getpid(), "pgid": os.getpgid(0), "source": str(source),
            "source_sha256": digest(source), "database": str(database),
            "database_sha256": digest(database), "sample_line": sample_line,
            "observer": "read-only native main-loop locals after render and sleep",
            "cpu_environment": {key: os.environ.get(key) for key in
                                ["CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]}}
    (output / "native-info.json").write_text(json.dumps(info, indent=2) + "\n")
    last = 0.0
    sequence = 0
    seek_frames = None
    with (output / "native-states.jsonl").open("w", buffering=1) as states, (output / "native-exceptions.jsonl").open("w", buffering=1) as errors:
        def trace(frame, event, arg):
            nonlocal last, sequence, seek_frames
            if frame.f_code.co_filename != str(source) or frame.f_code.co_name != "main":
                return None
            if event == "exception":
                errors.write(json.dumps({"time": time.time(), "line": frame.f_lineno,
                                         "type": arg[0].__name__, "message": str(arg[1])}) + "\n")
            now = time.monotonic()
            if event == "line" and frame.f_lineno == sample_line and now - last >= 0.05:
                local = frame.f_locals
                if "global_positions" not in local:
                    return trace
                sequence += 1
                if seek_frames is None:
                    base = min(100, local["db"].nframes() - 1)
                    rotations = local["db"].bone_rotations
                    different = player.np.flatnonzero(player.np.max(player.np.abs(rotations - rotations[base]), axis=(1, 2)) > 0.01)
                    assert len(different), "database contains no distinct pose for seek acceptance"
                    seek_frames = [base, int(different[min(100, len(different) - 1)])]
                values = {label: local[name].value for label, name in CONTROLS.items()}
                scene = local["server"].scene
                clients = {str(cid): {"position": client.camera.position.tolist(),
                                     "look_at": client.camera.look_at.tolist(),
                                     "up_direction": client.camera.up_direction.tolist()}
                           for cid, client in local["server"].get_clients().items()}
                markers = {name: handle.position.tolist() for name, handle in scene._handle_from_node_name.items()
                           if name.startswith("/contact_marker/")}
                row = {"sequence": sequence, "time": time.time(), "monotonic": now,
                       "controls": values, "frame": int(local["next_frame"]),
                       "current_frame": float(local["current_frame"]), "nframes": local["db"].nframes(),
                       "recommended_seek_frames": seek_frames,
                       "root_position": local["root_frame"].position.tolist(),
                       "root_wxyz": local["root_frame"].wxyz.tolist(), "joint_positions": local["dof"].tolist(),
                       "source_contacts": local["db"].contact_states[local["next_frame"]].astype(int).tolist(),
                       "contact_markers": markers, "clients": clients}
                states.write(json.dumps(row) + "\n")
                temporary = output / "native-state.tmp"
                temporary.write_text(json.dumps(row))
                temporary.replace(output / "native-state.json")
                last = now
            return trace
        sys.argv = [str(source), "--database", str(database)]
        sys.settrace(trace)
        try:
            player.main()
        finally:
            sys.settrace(None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="php-parkour-research")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--database", default="/data/assets/databases/database_g1_locomotion.bin", type=Path)
    parser.add_argument("--native-observer", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.native_observer:
        native_observer(args.output, args.database)
        return
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    relative = output.relative_to(repo)
    if output.exists() and any(output.iterdir()):
        parser.error("output must be fresh; existing evidence is never overwritten")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8081)) == 0:
            parser.error("port 8081 occupied; refusing to affect another server")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("requires existing Chrome; installs no packages")
    output.mkdir(parents=True, exist_ok=True)
    docker_output = Path("/workspace/php_parkour") / relative
    source_paths = ["scripts/research/verify_database_gui.py", "scripts/research/viser_browser.py",
                    "motion_matching/motion_matching/play_database.py",
                    "motion_matching/motion_matching/core/database.py",
                    "motion_matching/motion_matching/core/features.py",
                    "motion_matching/motion_matching/viz/scene.py"]
    fingerprints = [{"path": p, "sha256": digest(repo / p)} for p in source_paths]
    report = {"schema_version": 1, "status": "failed", "actions": [],
              "scope": "Real browser controls and native reference database playback; CPU SwiftShader; no policy or locomotion success claim",
              "not_applicable": {"motion_or_variant_selector": "Native player selects one database via --database and has no motion/variant dropdown"},
              "source_fingerprints": fingerprints,
              "image_id": subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", args.container], text=True).strip()}
    command = ["docker", "exec", "-e", "CUDA_VISIBLE_DEVICES=", "-e", "OMP_NUM_THREADS=1",
               "-e", "OPENBLAS_NUM_THREADS=1", "-e", "MKL_NUM_THREADS=1", args.container,
               "/opt/php/bin/motion-python", "-u", "/workspace/php_parkour/scripts/research/verify_database_gui.py",
               "--native-observer", "--output", str(docker_output), "--database", str(args.database)]
    report["server_command"] = command
    server = browser = cdp = None
    try:
        with tempfile.TemporaryDirectory(prefix="php-database-browser-") as profile, (output / "server.log").open("w") as log, (output / "chrome.log").open("w") as chrome_log:
            server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            def state():
                if server.poll() is not None:
                    raise RuntimeError("native database player exited; inspect server.log")
                p = output / "native-state.json"
                return json.loads(p.read_text()) if p.is_file() else None
            wait_for(state, 180)
            debug = free_port()
            browser_command = [chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                               "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader",
                               "--enable-unsafe-swiftshader", "--window-size=1440,1100",
                               f"--remote-debugging-port={debug}", f"--user-data-dir={profile}",
                               "http://127.0.0.1:8081"]
            report["browser_command"] = browser_command
            browser = subprocess.Popen(browser_command, stdout=chrome_log, stderr=subprocess.STDOUT, start_new_session=True)
            def target():
                try:
                    with urlopen(f"http://127.0.0.1:{debug}/json/list", timeout=2) as stream:
                        return next((row for row in json.load(stream) if row.get("type") == "page"), None)
                except OSError:
                    return None
            cdp = CDP(wait_for(target, 45)["webSocketDebuggerUrl"])
            cdp.call("Page.enable")
            wait_for(lambda: "Show Contact Markers" in (cdp.evaluate("document.body.innerText") or ""))
            cdp.evaluate("""window.controlGroup = function(name) {
                let label=Array.from(document.querySelectorAll('label')).find(e=>e.textContent.trim()===name);
                for(let e=label,i=0;e&&i<7;i++,e=e.parentElement) {
                    if(e.querySelector('input,button,[role=slider]')) return e;
                } throw Error('control absent: '+name);
            }; window.controlValue = function(name) {
                let g=controlGroup(name), s=g.querySelector('[role=slider]'), i=g.querySelector('input');
                return s ? Number(s.getAttribute('aria-valuenow')) : (i.type==='checkbox' ? i.checked : i.value);
            };""")
            def gui_values():
                return {name: cdp.evaluate("controlValue(" + json.dumps(name) + ")") for name in CONTROLS}
            def screenshot(name):
                snapshot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (output / name).write_bytes(base64.b64decode(snapshot["data"]))
            def checkbox(name, desired):
                before = state()
                if cdp.evaluate("controlValue(" + json.dumps(name) + ")") != desired:
                    cdp.evaluate("(()=>{let g=controlGroup(" + json.dumps(name) + ");g.querySelector('input[type=checkbox]').click();})()")
                after = wait_for(lambda: (s if (s := state())["controls"][name] == desired else None), 15)
                # Browser callbacks run in another thread. Observe a later full
                # native loop, so a newly changed handle cannot be mistaken for
                # the previous loop's already-rendered scene.
                after = wait_for(lambda: (s if (s := state())["sequence"] >= after["sequence"] + 2
                                         and s["controls"][name] == desired else None), 15)
                wait_for(lambda: cdp.evaluate("controlValue(" + json.dumps(name) + ")") == desired, 15)
                if name == "Auto Play" and not desired:
                    # Wait for the last server-generated playback frame to
                    # reach Chrome before the next manual seek. This is also
                    # how a human can confirm that playback has paused.
                    wait_for(lambda: cdp.evaluate("controlValue('Frame')") == state()["frame"], 15)
                report["actions"].append({"action": "browser_checkbox", "name": name, "value": desired,
                                          "before": before, "after": after})
                return after
            def slider(name, value):
                before = state()
                browser_before = cdp.evaluate("controlValue(" + json.dumps(name) + ")")
                cdp.evaluate("(()=>{let e=controlGroup(" + json.dumps(name) + ").querySelector('input[type=text]');e.focus();e.select();})()")
                cdp.call("Input.insertText", {"text": str(value)})
                # Let React commit the typed value before Enter/blur, rather
                # than sending both keys in the same render cycle.
                time.sleep(0.2)
                for key, code in [("Enter", 13), ("Tab", 9)]:
                    for kind in ["keyDown", "keyUp"]:
                        cdp.call("Input.dispatchKeyEvent", {"type": kind, "key": key, "code": key,
                                                             "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code})
                    time.sleep(0.2)
                after = wait_for(lambda: (s if abs((s := state())["controls"][name] - value) < 1e-6 else None), 15)
                after = wait_for(lambda: (s if (s := state())["sequence"] >= after["sequence"] + 2
                                         and abs(s["controls"][name] - value) < 1e-6
                                         and (name != "Frame" or s["frame"] == int(value)) else None), 15)
                wait_for(lambda: abs(cdp.evaluate("controlValue(" + json.dumps(name) + ")") - value) < 1e-6, 15)
                report["actions"].append({"action": "browser_keyboard_slider", "name": name, "value": value,
                                          "browser_before": browser_before,
                                          "browser_after": cdp.evaluate("controlValue(" + json.dumps(name) + ")"),
                                          "before": before, "after": after})
                return after
            time.sleep(1)
            report["initial_gui"] = gui_values()
            report["control_html"] = {name: cdp.evaluate("controlGroup(" + json.dumps(name) + ").outerHTML") for name in CONTROLS}
            first = state()
            time.sleep(0.6)
            second = state()
            assert second["frame"] > first["frame"], "default Auto Play failed to advance"
            report["default_autoplay"] = {"before": first, "after": second}
            screenshot("initial-autoplay.png")
            checkbox("Auto Play", False)
            paused = state()
            time.sleep(0.6)
            stable = state()
            assert paused["frame"] == stable["frame"], "pause failed to hold native frame"
            report["pause"] = {"before": paused, "after": stable}
            frame_a, frame_b = first["recommended_seek_frames"]
            seek_a = slider("Frame", frame_a)
            seek_b = slider("Frame", frame_b)
            assert seek_a["frame"] == frame_a and seek_b["frame"] == frame_b
            assert any(seek_a[key] != seek_b[key] for key in ["joint_positions", "root_position", "root_wxyz"]), "seek did not change actual rendered pose"
            report["seek_rendered_scene"] = {"first": seek_a, "second": seek_b,
                                              "selection": "two actual database frames with different bone rotations"}
            screenshot("paused-seek.png")
            report["speed_trials"] = []
            for value in [0.5, 2.0]:
                slider("Speed", value)
                slider("Frame", 100)
                checkbox("Auto Play", True)
                start = state()
                time.sleep(1.2)
                end = state()
                checkbox("Auto Play", False)
                rate = (end["current_frame"] - start["current_frame"]) / (end["monotonic"] - start["monotonic"])
                report["speed_trials"].append({"speed": value, "start": start, "end": end, "frames_per_wall_second": rate})
            assert report["speed_trials"][1]["frames_per_wall_second"] > 2 * report["speed_trials"][0]["frames_per_wall_second"], "speed control did not change native playback rate"
            slider("Frame", 100)
            slider("Min Frame", 200)
            lower = wait_for(lambda: (s if (s := state())["frame"] == 200 else None), 10)
            slider("Max Frame", 210)
            checkbox("Auto Play", True)
            upper = wait_for(lambda: (s if (s := state())["frame"] == 210 else None), 10)
            time.sleep(0.5)
            held = state()
            assert held["frame"] == 210, "native range upper boundary did not clamp"
            report["range_clamp"] = {"lower": lower, "upper": upper, "held": held,
                                     "native_semantics": "Auto Play clamps at the upper bound; it does not loop"}
            checkbox("Auto Play", False)
            # Seek a frame with source contact before checking actual marker removal.
            slider("Max Frame", min(first["nframes"] - 1, 2000))
            slider("Min Frame", 0)
            contact = None
            for frame in [100, 200, 300, 0, 400, 500]:
                candidate = slider("Frame", frame)
                if any(candidate["source_contacts"]):
                    contact = candidate
                    break
            assert contact is not None, "selected database frames contain no contact marker case"
            label = f"L: {contact['source_contacts'][0]}  R: {contact['source_contacts'][1]}"
            assert contact["controls"]["Contact (L/R)"] == label
            wait_for(lambda: cdp.evaluate("controlValue('Contact (L/R)')") == label, 10)
            expected_markers = {"/contact_marker/" + side for side, active in zip(["left", "right"], contact["source_contacts"]) if active}
            assert set(contact["contact_markers"]) == expected_markers
            checkbox("Show Contact Markers", False)
            hidden = wait_for(lambda: (s if not (s := state())["contact_markers"] else None), 10)
            checkbox("Show Contact Markers", True)
            visible = wait_for(lambda: (s if set((s := state())["contact_markers"]) == expected_markers else None), 10)
            report["contact_readout_and_markers"] = {"label": label, "source_contacts": contact["source_contacts"],
                                                      "hidden": hidden, "visible": visible}
            slider("Camera Offset X", -1.5)
            slider("Camera Offset Y", 0.5)
            slider("Camera Offset Z", 1.5)
            slider("Camera Smoothness", 0.3)
            followed = checkbox("Follow Character", True)
            def camera_at_target():
                s = state()
                target = [a + b for a, b in zip(s["root_position"], [-1.5, 0.5, 1.5])]
                if not s["clients"]:
                    return None
                look_at = [s["root_position"][0], s["root_position"][1] + 1, s["root_position"][2]]
                return s if all(max(abs(a - b) for a, b in zip(client["position"], target)) < 0.02
                                and max(abs(a - b) for a, b in zip(client["look_at"], look_at)) < 1e-6
                                and max(abs(a - b) for a, b in zip(client["up_direction"], [0, 0, 1])) < 1e-6
                                for client in s["clients"].values()) else None
            camera = wait_for(camera_at_target, 20)
            for client in camera["clients"].values():
                assert max(abs(a - b) for a, b in zip(client["look_at"],
                           [camera["root_position"][0], camera["root_position"][1] + 1, camera["root_position"][2]])) < 1e-6
                assert max(abs(a - b) for a, b in zip(client["up_direction"], [0, 0, 1])) < 1e-6
            report["follow_camera"] = {"enabled": followed, "converged": camera,
                                       "position_tolerance_m": 0.02, "look_at_and_up_tolerance": 1e-6}
            screenshot("paused-follow-contact.png")
            checkbox("Follow Character", False)
            report["final_gui"] = gui_values()
            report["canvas_count"] = cdp.evaluate("document.querySelectorAll('canvas').length")
            assert report["canvas_count"] >= 1
            errors = [json.loads(line) for line in (output / "native-exceptions.jsonl").read_text().splitlines()]
            report["native_exceptions"] = errors
            assert not errors, "native player swallowed an exception; inspect native-exceptions.jsonl"
            assert all(digest(repo / item["path"]) == item["sha256"] for item in fingerprints), "execution sources changed during acceptance"
            report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        if cdp:
            try:
                report["failure_dom"] = cdp.evaluate("document.body.innerText")
                shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (output / "failure.png").write_bytes(base64.b64decode(shot["data"]))
            except Exception:
                pass
    finally:
        if cdp:
            cdp.socket.close()
        if browser and browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
            browser.wait(timeout=10)
        pidfile = output / "server.pid"
        if pidfile.is_file():
            pid = int(pidfile.read_text())
            cleanup = """import os,signal,sys
p=int(sys.argv[1]); command=open('/proc/%d/cmdline'%p,'rb').read()
assert b'verify_database_gui.py' in command and b'--native-observer' in command
assert os.getpgid(p)==p
os.killpg(p,signal.SIGTERM)
"""
            stopped = subprocess.run(["docker", "exec", args.container, "/opt/php/bin/motion-python", "-c", cleanup, str(pid)], capture_output=True, text=True)
            report["native_cleanup"] = {"pid": pid, "exit_code": stopped.returncode, "stderr": stopped.stderr}
        if server:
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=5)
    report["native_info"] = json.loads((output / "native-info.json").read_text()) if (output / "native-info.json").is_file() else None
    report["artifacts"] = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size, "sha256": digest(p)}
                           for p in sorted(output.rglob("*")) if p.is_file() and p.name != "results.json"]
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "error": report.get("error"), "report": str(output / "results.json")}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
