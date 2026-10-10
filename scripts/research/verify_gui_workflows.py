#!/usr/bin/env python3
"""Drive real Viser controls in CPU Chrome; run project Python only in Docker.

Every run uses a fresh owned output directory and temporary copies of motions.
No physical policy, inferred command labels, or GPU rendering is used.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from viser_browser import CDP, free_port


def wait_for(predicate, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.15)
    raise TimeoutError("GUI condition did not become true")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="php-parkour-research")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["viewer", "interactive"], default="viewer")
    parser.add_argument("--expect-paired", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    relative = output.relative_to(repo)
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    docker_output = Path("/workspace/php_parkour") / relative
    port = 8080 if args.mode == "viewer" else 8081
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            parser.error(f"port {port} occupied; refusing to affect another server")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("requires existing Chrome; installs no host packages")
    fixture = output / "fixture"
    fixture.mkdir()
    originals = []
    if args.mode == "viewer":
        source = repo / "outputs/research/motion-matching/scenarios/low_speed_step"
        for base in ["forward_walk0.5s_step0.5s", "forward_walk0.8s_step0.5s"]:
            for suffix in ["_motion.npz", "_terrain.npy", "_terrain.obj"]:
                path = source / (base + suffix)
                shutil.copyfile(path, fixture / path.name)
                originals.append({"path": str(path.relative_to(repo)), "sha256": digest(path)})
        module = "motion_matching.motion_visualizer"
        extra = ["--motion-file", str(docker_output / "fixture")]
    else:
        module = "motion_matching.run"
        extra = ["--mode", "interactive"]
    report = {"schema_version": 1, "status": "failed", "mode": args.mode,
              "scope": "actual reference GUI controls only; CPU browser; no physical policy evaluation",
              "original_files": originals, "actions": [],
              "source_fingerprints": [{"path": p, "sha256": digest(repo / p)} for p in
                  ["motion_matching/motion_matching/run.py", "motion_matching/motion_matching/motion_visualizer.py",
                   "motion_matching/motion_matching/io/motion_io.py", "scripts/research/verify_gui_workflows.py",
                   "scripts/research/gui_tk_probe.py"]]}
    tk_command = ["docker", "exec", args.container, "/opt/php/bin/motion-python",
                  "/workspace/php_parkour/scripts/research/gui_tk_probe.py"]
    if args.mode == "interactive":
        baseline = json.loads(subprocess.check_output(tk_command, text=True))["windows"]
        report["x11_baseline_windows"] = baseline
    launch = ("import os,runpy,sys;from pathlib import Path;"
              "assert os.getpgid(0)==os.getpid(),'Docker exec must have an isolated process group';"
              "Path(sys.argv[1]).write_text(str(os.getpid()));os.chdir(sys.argv[2]);"
              "module=sys.argv[3];sys.argv=[module,*sys.argv[4:]];runpy.run_module(module,run_name='__main__')")
    command = ["docker", "exec", "-e", "OMP_NUM_THREADS=1", "-e", "OPENBLAS_NUM_THREADS=1",
               "-e", "MKL_NUM_THREADS=1", args.container, "/opt/php/bin/motion-python", "-u", "-c",
               launch, str(docker_output / "server.pid"), str(docker_output), module, *extra]
    report["server_command"] = command
    server = browser = cdp = None
    try:
        with tempfile.TemporaryDirectory(prefix="php-gui-browser-") as profile, (output / "server.log").open("w") as server_log, (output / "chrome.log").open("w") as chrome_log:
            server = subprocess.Popen(command, stdout=server_log, stderr=subprocess.STDOUT)
            def initialized():
                if server.poll() is not None:
                    raise RuntimeError("project GUI exited; inspect server.log")
                log = (output / "server.log").read_text(errors="replace")
                if "Traceback (most recent call last)" in log:
                    raise RuntimeError("project GUI traceback; inspect server.log")
                return ("Starting animation loop" if args.mode == "viewer" else "GUI keyboard controller started") in log
            wait_for(initialized, 180)
            debug = free_port()
            browser_command = [chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                               "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader",
                               "--enable-unsafe-swiftshader", "--window-size=1440,1100",
                               f"--remote-debugging-port={debug}", f"--user-data-dir={profile}",
                               f"http://127.0.0.1:{port}"]
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
            marker = "Save Motion" if args.mode == "viewer" else "Start Recording"
            wait_for(lambda: marker in (cdp.evaluate("document.body.innerText") or ""))
            cdp.evaluate("""window.controlGroup = function(name) {
                let label=Array.from(document.querySelectorAll('label')).find(e=>e.textContent.trim()===name);
                for(let e=label,i=0;e&&i<7;i++,e=e.parentElement){
                    if(e.querySelector('input,button,[role=slider]')) return e;
                } throw Error('control absent: '+name);
            }; window.controlValue = function(name) {let g=controlGroup(name),s=g.querySelector('[role=slider]');
                return s ? Number(s.getAttribute('aria-valuenow')) : g.querySelector('input').value;};""")
            def screenshot(name):
                data = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (output / name).write_bytes(base64.b64decode(data["data"]))
            def button(name):
                value = cdp.evaluate("(()=>{let e=Array.from(document.querySelectorAll('button')).find(e=>e.innerText.trim()===" + json.dumps(name) + ");if(!e)throw Error('button absent');e.click();return e.innerText;})()")
                report["actions"].append({"action": "click_button", "name": name, "result": value})
                time.sleep(0.3)
            def select(name, value):
                cdp.evaluate("controlGroup(" + json.dumps(name) + ").querySelector('input').click()")
                wait_for(lambda: cdp.evaluate("Array.from(document.querySelectorAll('[role=option]')).some(e=>e.innerText.trim()===" + json.dumps(value) + ")"), 10)
                cdp.evaluate("Array.from(document.querySelectorAll('[role=option]')).find(e=>e.innerText.trim()===" + json.dumps(value) + ").click()")
                wait_for(lambda: cdp.evaluate("controlValue(" + json.dumps(name) + ")") == value, 10)
                report["actions"].append({"action": "select", "name": name, "value": value})
                time.sleep(0.5)
            screenshot("initial.png")
            if args.mode == "viewer":
                chosen = "forward_walk0.8s_step0.5s_motion.npz"
                select("Motion File", chosen)
                before_variant = cdp.evaluate("controlValue('Variant')")
                select("Variant", "0" if before_variant != "0" else "1")
                before_random = cdp.evaluate("controlValue('Variant')")
                button("Re-randomize Terrain")
                after_random = wait_for(lambda: (v if (v := cdp.evaluate("controlValue('Variant')")) != before_random else None), 10)
                report["terrain_change"] = {"before": before_variant, "before_rerandomize": before_random, "after_rerandomize": after_random}
                report["speed_control_html"] = cdp.evaluate("controlGroup('Speed').outerHTML")
                cdp.evaluate("(()=>{let e=controlGroup('Speed').querySelector('input[type=text]');e.focus();e.select();})()")
                cdp.call("Input.insertText", {"text": "2"})
                for key, code in [("Enter", 13), ("Tab", 9)]:
                    for kind in ["keyDown", "keyUp"]:
                        cdp.call("Input.dispatchKeyEvent", {"type": kind, "key": key, "code": key, "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code})
                wait_for(lambda: cdp.evaluate("controlValue('Speed')") == 2, 10)
                time.sleep(1)
                report["actions"].append({"action": "keyboard_slider", "name": "Speed", "value": 2.0})
                button("Save Motion")
                saved = fixture / (Path(chosen).stem + "_speed_2.npz")
                wait_for(saved.is_file, 15)
                terrain_stem = saved.stem.replace("_motion", "_terrain")
                paired = {ext: (saved.parent / (terrain_stem + ext)).is_file() for ext in [".npy", ".obj"]}
                report["saved_motion"] = str(saved.relative_to(output))
                report["saved_terrain_pair"] = paired
                screenshot("edited-saved.png")
                if args.expect_paired and not all(paired.values()):
                    raise AssertionError("actual Save Motion did not produce its paired terrain NPY/OBJ")
                button("Delete Current File")
                wait_for(lambda: not (fixture / chosen).exists(), 10)
                chosen_terrain_stem = Path(chosen).stem.replace("_motion", "_terrain")
                remaining_deleted = [p.name for p in [fixture / chosen,
                    fixture / (chosen_terrain_stem + ".npy"), fixture / (chosen_terrain_stem + ".obj")] if p.exists()]
                report["delete_remaining_files"] = remaining_deleted
                if remaining_deleted:
                    raise AssertionError("Delete Current File left its associated terrain file")
            else:
                parent = int((output / "server.pid").read_text())
                event_window = None
                def tk_key(key, release=False):
                    nonlocal event_window
                    command = [*tk_command, "--parent", str(parent), "--baseline", json.dumps(baseline), "--key", key]
                    if release:
                        command.append("--release")
                    if event_window:
                        command += ["--window", str(event_window)]
                    result = subprocess.run(command, capture_output=True, text=True)
                    if result.returncode:
                        raise RuntimeError("targeted Tk probe failed: " + result.stderr)
                    data = json.loads(result.stdout)
                    event_window = data["event_window"]
                    report["actions"].append({"action": "real_tk_key", "result": data})
                tk_key("i")
                button("Start Recording")
                time.sleep(2)
                tk_key("i", release=True)
                tk_key("j")
                time.sleep(1)
                tk_key("j", release=True)
                button("End Recording")
                recordings = wait_for(lambda: list((output / "motion_matching_results").rglob("*.npz")), 20)
                saved = recordings[0]
                terrain_stem = saved.stem.replace("_motion", "_terrain")
                paired = {ext: (saved.parent / (terrain_stem + ext)).is_file() for ext in [".npy", ".obj"]}
                report["saved_motion"] = str(saved.relative_to(output))
                report["saved_terrain_pair"] = paired
                screenshot("interactive-recorded.png")
                if args.expect_paired and not all(paired.values()):
                    raise AssertionError("actual Start/End Recording did not produce paired terrain NPY/OBJ")
            if args.expect_paired:
                docker_saved = docker_output / saved.relative_to(output)
                docker_terrain = docker_saved.with_name(saved.stem.replace("_motion", "_terrain") + ".npy")
                conversion = ["docker", "exec", args.container, "/opt/php/bin/train-python",
                              "/workspace/php_parkour/scripts/research/verify_conversion.py", "--source", str(docker_saved),
                              "--terrain", str(docker_terrain), "--output", str(docker_output / "conversion")]
                result = subprocess.run(conversion, capture_output=True, text=True)
                (output / "conversion.log").write_text(result.stdout + result.stderr)
                report["conversion_command"] = conversion
                if result.returncode:
                    raise RuntimeError("saved GUI output failed real conversion/registry/diagnose; inspect conversion.log")
                native_path = docker_output / "conversion/single/example_motion.npz"
                inspect = """
import importlib.abc,json,numpy as np,sys
from pathlib import Path
class OfflineGuard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='wandb' or fullname.startswith('wandb.'): raise AssertionError('unexpected remote SDK import')
sys.meta_path.insert(0,OfflineGuard())
from wbt_training.config_values.robot_config import G1_29DOF_JOINT_NAMES,G1_32BODY_NAMES
from wbt_training.utils.registry import RegistryResolver
from holosoma.managers.command.terms.wbt import MotionLoader
p=Path(sys.argv[1]);r=RegistryResolver().resolve(p.parent.as_uri());assert len(r)==1
loader=MotionLoader(str(p),G1_32BODY_NAMES,G1_29DOF_JOINT_NAMES,device='cpu')
with np.load(p,allow_pickle=False) as data:
 report={'status':'passed','registry_uri':p.parent.as_uri(),'native_frames':loader.time_step_total,'fps':float(data['fps'].item()),'shapes':{k:list(data[k].shape) for k in data.files},'vel_cmd_present':'vel_cmd' in data.files,'device':'cpu','physical_policy_evaluation':False}
 assert report['fps']==50 and loader.time_step_total>=2
 if 'vel_cmd' in data.files:
  v=data['vel_cmd'];assert v.shape==(loader.time_step_total,15) and np.isfinite(v).all();assert np.all(v.sum(axis=1)==1) and np.all((v==0)|(v==1))
Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\\n')
"""
                inspect_command = ["docker", "exec", "-e", "OMP_NUM_THREADS=1", args.container,
                                   "/opt/php/bin/train-python", "-c", inspect, str(native_path), str(docker_output / "native-load.json")]
                result = subprocess.run(inspect_command, capture_output=True, text=True)
                (output / "native-load.log").write_text(result.stdout + result.stderr)
                report["native_load_command"] = inspect_command
                if result.returncode:
                    raise RuntimeError("native CPU MotionLoader rejected saved GUI output; inspect native-load.log")
                report["native_load"] = json.loads((output / "native-load.json").read_text())
            report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if cdp:
            report["failure_dom"] = cdp.evaluate("document.body.innerText")
    finally:
        if cdp:
            cdp.socket.close()
        if browser and browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
            browser.wait(timeout=10)
        pidfile = output / "server.pid"
        if pidfile.is_file():
            pid = int(pidfile.read_text())
            stop = "import os,signal,sys;os.killpg(int(sys.argv[1]),signal.SIGTERM)"
            subprocess.run(["docker", "exec", args.container, "/opt/php/bin/motion-python", "-c", stop, str(pid)], capture_output=True)
        if server:
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=5)
    report["artifacts"] = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size, "sha256": digest(p)}
                           for p in sorted(output.rglob("*")) if p.is_file() and p.name != "results.json"]
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "error": report.get("error"), "report": str(output / "results.json")}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
