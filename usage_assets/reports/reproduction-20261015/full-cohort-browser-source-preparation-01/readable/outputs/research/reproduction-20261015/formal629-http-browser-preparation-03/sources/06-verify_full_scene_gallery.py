#!/usr/bin/env python3
"""Verify offline full629/preview gallery media and controls in existing Chrome.

Host stdlib only; CPU software browser/media decoding, never simulation. Pages
hold at most 24 cards; at most four videos load/seek concurrently. A full report
only passes after every published video, thumbnail and world-XY SVG is checked.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from urllib.request import urlopen

from viser_browser import CDP, free_port


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome: parser.error("Existing Chrome/Chromium required; this tool installs nothing")
    if args.output.exists() and any(args.output.iterdir()): parser.error("Use an empty browser report directory")
    args.output.mkdir(parents=True, exist_ok=True)
    root = args.gallery.resolve().parent
    summary = json.loads((root / "summary.json").read_text()); cases = json.loads((root / "cases.json").read_text())
    manifest = json.loads((root / "evidence-manifest.json").read_text())
    report = {"schema_version": 1, "status": "failed", "scope": "Offline browser, original media and controls only; no policy/simulation run",
              "preview": summary["preview"], "gallery_sha256": sha(args.gallery), "manifest_sha256": sha(root / "evidence-manifest.json"),
              "published_cases": len(cases), "metadata_and_seek": [], "images": [], "filters": [],
              "browser_mode": "headless --disable-gpu; CPU video/image decode; max24 cards/page, max4 video checks concurrently"}
    cdp = None
    with tempfile.TemporaryDirectory(prefix="php-full-scene-browser-") as profile, (args.output / "chrome.log").open("w") as log:
        port = free_port()
        command = [chrome, "--headless=new", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run", "--window-size=1600,1200",
                   "--disable-features=VaapiVideoDecoder,AcceleratedVideoDecodeLinuxGL", "--autoplay-policy=no-user-gesture-required",
                   f"--remote-debugging-port={port}", f"--user-data-dir={profile}", args.gallery.resolve().as_uri()]
        browser = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            for record in manifest["files"]:
                p = root / record["path"]
                if not p.resolve().is_relative_to(root) or not p.is_file() or p.stat().st_size != record["bytes"] or sha(p) != record["sha256"]:
                    raise ValueError(f"Published manifest mismatch: {record['path']}")
            report["manifest_files_checked"] = len(manifest["files"])
            started = time.monotonic()
            while time.monotonic() - started < 40:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as stream: targets = json.load(stream)
                    target = next(t for t in targets if t.get("type") == "page")
                    cdp = CDP(target["webSocketDebuggerUrl"]); cdp.call("Page.enable")
                    if cdp.evaluate("!!document.getElementById('case-data')"): break
                    cdp.socket.close(); cdp = None
                except (OSError, StopIteration): time.sleep(.2)
            if cdp is None: raise TimeoutError("Chrome/gallery did not initialize")
            if cdp.evaluate("JSON.parse(document.getElementById('case-data').textContent)") != cases:
                raise AssertionError("Page case data differs from published JSON")
            if summary["preview"] and "PREVIEW" not in cdp.evaluate("document.title"):
                raise AssertionError("Partial preview lacks an explicit title")
            for state, expected in (("threshold", summary["threshold_events"]), ("unflagged", summary["no_threshold_events"]), ("all", len(cases))):
                shown = cdp.evaluate("(() => {const e=document.getElementById('state');e.value=" + json.dumps(state) + ";e.dispatchEvent(new Event('change'));return Number(document.getElementById('visible').textContent.split(' / ')[0]);})()")
                if shown != expected: raise AssertionError(f"Outcome filter {state}: {shown} != {expected}")
                report["filters"].append({"state": state, "matched": shown})
            first_scene = cases[0]["scenario"]
            shown = cdp.evaluate("(() => {const e=document.getElementById('scene');e.value=" + json.dumps(first_scene) + ";e.dispatchEvent(new Event('change'));return Number(document.getElementById('visible').textContent.split(' / ')[0]);})()")
            if shown != sum(r["scenario"] == first_scene for r in cases): raise AssertionError("Scene filter mismatch")
            cdp.evaluate("document.getElementById('scene').value='all';document.getElementById('scene').dispatchEvent(new Event('change'))")
            result = cdp.evaluate("(() => {const s=document.getElementById('search');s.value=" + json.dumps(cases[0]["case_id"]) + ";s.dispatchEvent(new Event('input'));return [...document.querySelectorAll('article')].map(r=>r.dataset.case);})()")
            if result != [cases[0]["case_id"]]: raise AssertionError("Case-ID search did not isolate exactly one case")
            report["search_case_id"] = result[0]
            cdp.evaluate("document.getElementById('search').value='';document.getElementById('search').dispatchEvent(new Event('input'))")
            pages = math.ceil(len(cases) / 24)
            for page in range(pages):
                page_cases = cases[page * 24:(page + 1) * 24]
                ids = cdp.evaluate("[...document.querySelectorAll('article')].map(r=>r.dataset.case)")
                if ids != [r["case_id"] for r in page_cases] or len(ids) > 24: raise AssertionError("Pagination identity/count mismatch")
                expected_videos = [v for r in page_cases for v in r["videos"]]
                for offset in range(0, len(expected_videos), 4):
                    js = '''Promise.all([...document.querySelectorAll('video')].slice(OFFSET,END).map(v=>new Promise((resolve,reject)=>{
const timer=setTimeout(()=>reject(Error('media timeout: '+v.getAttribute('src'))),10000);const fail=()=>{clearTimeout(timer);reject(Error('media error: '+v.getAttribute('src')));};v.addEventListener('error',fail,{once:true});
v.addEventListener('loadedmetadata',()=>{const width=v.videoWidth,height=v.videoHeight,duration=v.duration;v.addEventListener('seeked',()=>{clearTimeout(timer);resolve({file:v.getAttribute('src'),width,height,duration,seek_seconds:v.currentTime,readyState:v.readyState,controls:v.controls});},{once:true});v.currentTime=duration/2;},{once:true});v.preload='auto';v.load();})))'''.replace('OFFSET', str(offset)).replace('END', str(offset + 4))
                    checked = cdp.evaluate(js)
                    for actual, expected in zip(checked, expected_videos[offset:offset + 4]):
                        if (actual["file"] != expected["path"] or actual["width"] != expected["width"] or actual["height"] != expected["height"]
                                or abs(actual["duration"] - expected["duration_seconds"]) > .05 or actual["readyState"] < 2 or not actual["controls"]):
                            raise AssertionError(f"Metadata/decoded seek mismatch: {actual}")
                    report["metadata_and_seek"].extend(checked)
                images = cdp.evaluate('''Promise.all([...document.querySelectorAll('img')].map(img=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('image timeout: '+img.getAttribute('src'))),10000);const done=()=>{clearTimeout(timer);if(!img.naturalWidth)reject(Error('image decode failed'));else resolve({file:img.getAttribute('src'),width:img.naturalWidth,height:img.naturalHeight});};img.loading='eager';if(img.complete)done();else{img.addEventListener('load',done,{once:true});img.addEventListener('error',()=>reject(Error('image error')),{once:true});}})))''')
                expected_images = [path for row in page_cases for path in [row["trajectory_svg"], *(v["thumbnail"] for v in row["videos"])]]
                if [r["file"] for r in images] != expected_images: raise AssertionError("World-XY/thumbnail image set mismatch")
                report["images"].extend(images)
                if page == 0:
                    before = cdp.evaluate("(() => {const v=document.querySelector('video');v.currentTime=1;return v.play().then(()=>v.currentTime);})()")
                    time.sleep(.6)
                    after = cdp.evaluate("(() => {const v=document.querySelector('video');v.pause();return v.currentTime;})()")
                    if after <= before + .15: raise AssertionError("Actual video playback did not advance")
                    report["playback"] = {"before_seconds": before, "after_seconds": after}
                    cdp.evaluate("document.querySelector('details.trajectory').open=true")
                    time.sleep(.3)
                    screenshot = args.output / "gallery.png"
                    screenshot.write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
                    report["screenshot_sha256"] = sha(screenshot)
                    cdp.evaluate("document.querySelector('details.trajectory').scrollIntoView({block:'start'})")
                    trajectory_shot = args.output / "gallery-world-trajectory.png"
                    trajectory_shot.write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
                    report["world_trajectory_screenshot_sha256"] = sha(trajectory_shot)
                if page + 1 < pages: cdp.evaluate("document.getElementById('next').click()")
            expected_count = sum(len(r["videos"]) for r in cases)
            if len(report["metadata_and_seek"]) != expected_count: raise AssertionError("Not every published video was checked")
            report.update(status="passed", checked_cases=len(cases), checked_videos=expected_count, checked_pages=pages,
                          all_published_media_checked=True, configuration_coverage_complete=summary["configuration_coverage_complete"])
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            if cdp: cdp.socket.close()
            if browser.poll() is None: os.killpg(browser.pid, signal.SIGTERM); browser.wait(timeout=10)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: report.get(k) for k in ("status", "preview", "checked_cases", "checked_videos", "error")}, ensure_ascii=False))
    if report["status"] != "passed": raise SystemExit(1)


if __name__ == "__main__":
    main()
