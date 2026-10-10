#!/usr/bin/env python3
"""Check the published physical scene gallery in existing host Chrome.

Uses stdlib and a fresh browser profile. Loads every actual MP4, checks its
dimensions/duration against the publication manifest, decodes a keyframe,
verifies the result/search filters, and checks one video advances in playback.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from viser_browser import CDP, free_port


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery", type=Path, default=Path("usage_assets/sim2sim/scenarios/playback.html"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("an existing Chrome/Chromium is required; nothing is installed")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")
    manifest_path = args.gallery.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    clips = [video for row in manifest["scenarios"] for video in row["videos"]]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "failed", "scope": "offline physical-rollout media loading and UI only; no additional policy rollout",
              "gallery": str(args.gallery.resolve()), "gallery_sha256": hashlib.sha256(args.gallery.read_bytes()).hexdigest(),
              "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "recorded_outcome_counts": manifest["counts"]}
    cdp = None
    with tempfile.TemporaryDirectory(prefix="php-scene-gallery-chrome-") as profile, (args.output_dir / "chrome.log").open("w") as log:
        port = free_port()
        command = [chrome, "--headless=new", "--no-first-run", "--disable-dev-shm-usage", "--window-size=1600,1100",
                   "--autoplay-policy=no-user-gesture-required", f"--remote-debugging-port={port}", f"--user-data-dir={profile}", args.gallery.resolve().as_uri()]
        browser = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            started = time.monotonic()
            while time.monotonic() - started < 45:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as stream:
                        targets = json.load(stream)
                    target = next(row for row in targets if row.get("type") == "page")
                    cdp = CDP(target["webSocketDebuggerUrl"])
                    break
                except (OSError, StopIteration):
                    time.sleep(0.2)
            if cdp is None:
                raise TimeoutError("Chrome did not initialize")
            cdp.call("Page.enable")
            started = time.monotonic()
            videos = []
            while time.monotonic() - started < 45:
                videos = cdp.evaluate("Array.from(document.querySelectorAll('video')).map(v=>({file:v.getAttribute('src'),width:v.videoWidth,height:v.videoHeight,duration:v.duration,readyState:v.readyState,controls:v.controls,error:v.error?{code:v.error.code,message:v.error.message}:null}))")
                if len(videos) == len(clips) and all(v["readyState"] >= 1 or v["error"] for v in videos):
                    break
                time.sleep(0.2)
            if len(videos) != len(clips):
                raise AssertionError("gallery and manifest video counts differ")
            for video, clip in zip(videos, clips):
                if video["file"] != clip["path"] or video["error"] or not video["controls"]:
                    raise AssertionError(f"video failed to load with native controls: {video}")
                if (video["width"], video["height"]) != (clip["width"], clip["height"]) or abs(video["duration"] - clip["duration_seconds"]) > 0.05:
                    raise AssertionError(f"video metadata differs: {video}")
            report["videos"] = videos
            report["decoded_keyframes"] = cdp.evaluate("Promise.all(Array.from(document.querySelectorAll('video')).map(v=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('seek timeout: '+v.getAttribute('src'))),10000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve({file:v.getAttribute('src'),time:v.currentTime,readyState:v.readyState})},{once:true});v.currentTime=v.duration/2;})))")
            if not all(row["readyState"] >= 2 for row in report["decoded_keyframes"]):
                raise AssertionError("one or more video keyframes did not decode")
            states = {"all": 17, "threshold": manifest["counts"]["threshold_triggered"],
                      "unflagged": manifest["counts"]["unflagged"], "execution_failed": manifest["counts"]["execution_failed"]}
            report["filters"] = []
            for value, expected in states.items():
                actual = cdp.evaluate("(() => {const e=document.getElementById('state');e.value=" + json.dumps(value) + ";e.dispatchEvent(new Event('change',{bubbles:true}));return [...document.querySelectorAll('article')].filter(x=>!x.hidden).length;})()")
                if actual != expected:
                    raise AssertionError(f"outcome filter {value}: {actual} != {expected}")
                report["filters"].append({"state": value, "visible": actual, "expected": expected})
            report["search"] = cdp.evaluate("(() => {const e=document.getElementById('state');e.value='all';e.dispatchEvent(new Event('change'));const s=document.getElementById('search');s.value='random_locomotion';s.dispatchEvent(new Event('input'));const found=[...document.querySelectorAll('article')].filter(x=>!x.hidden).map(x=>x.id);s.value='';s.dispatchEvent(new Event('input'));return found;})()")
            if report["search"] != ["random_locomotion"]:
                raise AssertionError("scenario search did not isolate the requested result")
            if videos:
                before = cdp.evaluate("(() => {const v=document.querySelector('video');v.currentTime=1;return v.play().then(()=>v.currentTime);})()")
                time.sleep(0.7)
                after = cdp.evaluate("(() => {const v=document.querySelector('video');v.pause();return v.currentTime;})()")
                if after <= before + 0.2:
                    raise AssertionError("video did not advance during playback")
                report["playback"] = {"file": videos[0]["file"], "before_seconds": before, "after_seconds": after}
                cdp.evaluate("document.querySelector('video').currentTime=document.querySelector('video').duration/2")
            time.sleep(0.5)
            screenshot = args.output_dir / "scene-gallery.png"
            screenshot.write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
            report.update(status="passed", checked_videos=len(videos), checked_scenarios=cdp.evaluate("document.querySelectorAll('article').length"),
                          screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest())
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            if cdp:
                cdp.socket.close()
            if browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                browser.wait(timeout=10)
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checked_videos": report.get("checked_videos"), "error": report.get("error")}, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
