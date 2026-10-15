#!/usr/bin/env python3
"""Check the preserved-media gallery with an already installed CPU Chrome."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
HELPERS = ROOT / "usage_assets/reports/official-evaluations-six/browser-reproduce"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HELPERS))
from verify_gallery import connect_cdp
from viser_browser import CDP, free_port


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fp(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Fresh browser output directory required")
    args.output.mkdir(parents=True)
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / "manifest.json").read_text())
    paths = [package / name for name in ["sources.json", "manifest.json", "playback.html", "build_media.py", "verify_browser.py"]]
    paths += [HELPERS / name for name in ["verify_gallery.py", "viser_browser.py"]]
    for clip in manifest["clips"] + manifest["kinematic_references"]:
        paths += [ROOT / clip[key] for key in ["source_video", "source_poster"]]
        paths += [package / clip["gif"]["path"]] if "gif" in clip else [ROOT / clip["existing_gif"]]
    report = {"status": "failed", "scope": "25 original-video metadata and midpoint seeks, 25 GIF/PNG decodes, category filters and playback; no new rollout.", "input_before": [fp(p) for p in paths], "quality_verified": False}
    browser = cdp = None
    try:
        chrome = shutil.which("google-chrome") or shutil.which("chromium")
        require(chrome, "Existing Chrome required; installs nothing")
        with tempfile.TemporaryDirectory(prefix="php-media-browser-") as profile, (args.output / "chrome.stdout.log").open("wb") as stdout, (args.output / "chrome.stderr.log").open("wb") as stderr:
            port = free_port()
            command = [chrome, "--headless=new", "--disable-gpu", "--disable-background-networking", "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage", "--allow-file-access-from-files", "--autoplay-policy=no-user-gesture-required", "--window-size=1440,1200", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=" + str(port), "--user-data-dir=" + profile, "about:blank"]
            if os.geteuid() == 0:
                command.insert(1, "--no-sandbox")
            report["command"] = command
            browser = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    require(browser.poll() is None, "Chrome exited before connection")
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                            target = next(t for t in json.load(response) if t.get("type") == "page")
                        cdp = connect_cdp(CDP, target["webSocketDebuggerUrl"])
                        cdp.socket.settimeout(40)
                        break
                    except (OSError, StopIteration):
                        time.sleep(.1)
                require(cdp is not None, "Chrome connection timeout")
                cdp.call("Page.enable")
                cdp.call("Page.navigate", {"url": (package / "playback.html").as_uri()})
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if cdp.evaluate("document.querySelectorAll('article').length") == 25:
                        break
                    time.sleep(.1)
                require(cdp.evaluate("document.querySelectorAll('article').length") == 25, "25 cards required")
                metadata = cdp.evaluate("""(async()=>{const rows=[];for(const v of document.querySelectorAll('video')){v.preload='auto';await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('metadata timeout')),12000);v.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve();},{once:true});v.addEventListener('error',()=>reject(Error(v.error.message)),{once:true});v.load();});rows.push({src:v.getAttribute('src'),width:v.videoWidth,height:v.videoHeight,duration:v.duration,error:v.error?.message});}return rows;})()""")
                report["metadata"] = metadata
                clips = manifest["clips"] + manifest["kinematic_references"]
                require(len(metadata) == 25, "25 loaded videos required")
                for actual, clip in zip(metadata, clips):
                    stream = clip["source_metadata"]["streams"][0]
                    require(actual["src"] == "../../../" + clip["source_video"] and actual["width"] == stream["width"] and actual["height"] == stream["height"] and not actual.get("error") and abs(actual["duration"] - float(clip["source_metadata"]["format"]["duration"])) < .05, "Video metadata differs")
                report["seeks"] = cdp.evaluate("""(async()=>{const rows=[];for(const v of document.querySelectorAll('video')){const target=v.duration/2;await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('seek timeout')),12000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve();},{once:true});v.currentTime=target;});rows.push({target,time:v.currentTime,ready:v.readyState,error:v.error?.message});}return rows;})()""")
                require(all(x["ready"] >= 2 and abs(x["time"] - x["target"]) < .05 and not x.get("error") for x in report["seeks"]), "Midpoint decode failed")
                report["images"] = cdp.evaluate("""(async()=>{const srcs=[...document.querySelectorAll('video')].map(v=>v.poster).concat([...document.querySelectorAll('article img')].map(i=>i.src));return await Promise.all(srcs.map(src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve({src,width:i.naturalWidth,height:i.naturalHeight});i.onerror=()=>reject(Error(src));i.src=src;})));})()""")
                require(len(report["images"]) == 50 and all(min(x["width"], x["height"]) > 0 for x in report["images"]), "50 poster/GIF decodes required")
                report["filters"] = cdp.evaluate("""[...document.querySelectorAll('button[data-filter]')].map(b=>{b.click();return {category:b.dataset.filter,count:document.querySelectorAll('article:not([hidden])').length,text:document.querySelector('#count').textContent};})""")
                require([x["count"] for x in report["filters"]] == [25, 1, 4, 2, 1, 17], "Category filters differ")
                cdp.evaluate("document.querySelector('button[data-filter=all]').click();true")
                report["playback"] = cdp.evaluate("""(async()=>{const vs=[...document.querySelectorAll('video')];const before=await Promise.all(vs.map(async v=>{v.muted=true;v.currentTime=0;await v.play();return v.currentTime;}));await new Promise(r=>setTimeout(r,900));const rows=vs.map((v,i)=>({before:before[i],after:v.currentTime,paused:v.paused,error:v.error?.message}));vs.forEach(v=>v.pause());return rows;})()""")
                require(all(not x["paused"] and x["after"] - x["before"] > .2 and not x.get("error") for x in report["playback"]), "Playback did not advance")
                screenshot = cdp.call("Page.captureScreenshot", {"format": "png"})
                (args.output / "playback.png").write_bytes(base64.b64decode(screenshot["data"]))
                report["status"] = "passed"
            finally:
                if cdp:
                    try:
                        cdp.call("Browser.close")
                    except Exception as error:
                        report["close_response"] = str(error)
                    cdp.socket.close()
                try:
                    report["browser_returncode"] = browser.wait(timeout=15)
                    report["cleanup"] = "natural_wait"
                except subprocess.TimeoutExpired:
                    browser.terminate()
                    report["browser_returncode"] = browser.wait(timeout=5)
                    report["cleanup"] = "owned_browser_terminate"
        require(report["browser_returncode"] == 0 and report["cleanup"] == "natural_wait", "Chrome did not exit naturally with0")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        report["input_after"] = [fp(p) for p in paths]
        report["inputs_unchanged"] = report["input_before"] == report["input_after"]
        if not report["inputs_unchanged"]:
            report["status"] = "failed"
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["status", "inputs_unchanged"]} | ({"error": report["error"]} if "error" in report else {})))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
