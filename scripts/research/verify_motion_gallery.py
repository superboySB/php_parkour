#!/usr/bin/env python3
"""Verify every published offline video loads and capture its real gallery."""
from __future__ import annotations

import argparse
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
    parser.add_argument("--gallery", type=Path, default=Path("usage_assets/motion_matching/playback.html"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("an existing Chrome/Chromium is required")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "failed", "gallery": str(args.gallery.resolve()),
              "gallery_sha256": hashlib.sha256(args.gallery.read_bytes()).hexdigest(), "scope": "offline browser media loading, no policy evaluation"}
    with tempfile.TemporaryDirectory(prefix="php-gallery-chrome-") as profile, (args.output_dir / "chrome.log").open("w") as stream:
        port = free_port()
        command = [chrome, "--headless=new", "--no-first-run", "--disable-dev-shm-usage", "--window-size=1440,960",
                   f"--remote-debugging-port={port}", f"--user-data-dir={profile}", args.gallery.resolve().as_uri()]
        browser = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        cdp = None
        try:
            started = time.monotonic()
            while time.monotonic() - started < 45:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                        targets = json.load(response)
                    target = next(row for row in targets if row.get("type") == "page")
                    cdp = CDP(target["webSocketDebuggerUrl"])
                    break
                except (OSError, StopIteration):
                    time.sleep(0.2)
            if cdp is None:
                raise TimeoutError("Chrome did not initialize")
            cdp.call("Page.enable")
            started = time.monotonic()
            while time.monotonic() - started < 45:
                videos = cdp.evaluate("Array.from(document.querySelectorAll('video')).map(v=>({file:v.getAttribute('src'),width:v.videoWidth,height:v.videoHeight,duration:v.duration,readyState:v.readyState,error:v.error?{code:v.error.code,message:v.error.message}:null}))")
                if videos and all(row["readyState"] >= 1 or row["error"] is not None for row in videos):
                    break
                time.sleep(0.25)
            manifest = json.loads((args.gallery.parent / "manifest.json").read_text())
            if len(videos) != len(manifest["clips"]):
                raise AssertionError("gallery video count does not match the manifest")
            for video, clip in zip(videos, manifest["clips"]):
                if video["error"] or min(video["width"], video["height"]) <= 0:
                    raise AssertionError(f"video failed to load: {video}")
                if abs(video["duration"] - clip["video_frames"] / clip["video_fps"]) > 0.1:
                    raise AssertionError(f"unexpected video duration: {video}")
            times = [min(clip["png_source_frame"] / clip["source_fps"], clip["video_frames"] / clip["video_fps"] - 0.05) for clip in manifest["clips"]]
            seeked = cdp.evaluate("Promise.all(Array.from(document.querySelectorAll('video')).map((v,i)=>new Promise((resolve,reject)=>{let timer=setTimeout(()=>reject(new Error('video seek timeout: '+v.getAttribute('src'))),10000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve({file:v.getAttribute('src'),time:v.currentTime,readyState:v.readyState})},{once:true});v.currentTime=" + json.dumps(times) + "[i];})))")
            time.sleep(1)
            report.update(status="passed", videos=videos, checked=len(videos), decoded_keyframes=seeked)
            screenshot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            import base64
            (args.output_dir / "gallery.png").write_bytes(base64.b64decode(screenshot["data"]))
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            if cdp:
                cdp.socket.close()
            if browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                browser.wait(timeout=10)
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
