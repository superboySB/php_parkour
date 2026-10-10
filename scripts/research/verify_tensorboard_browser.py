#!/usr/bin/env python3
"""Capture real local TensorBoard curves using existing host Chrome and stdlib.

TensorBoard and event readers run in Docker. This script installs nothing,
opens a fresh browser profile, types the UI filters, and verifies the scalar
HTTP data underlying the displayed charts. A short pilot is not convergence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from viser_browser import CDP, free_port


def read_json(url: str):
    with urlopen(url, timeout=10) as stream:
        return json.load(stream)


def type_filter(cdp: CDP, placeholder: str, value: str) -> None:
    selector = f"input[placeholder={json.dumps(placeholder)}]"
    cdp.evaluate("(() => {const e=document.querySelector(" + json.dumps(selector) + ");if(!e)throw Error('filter input missing');e.focus();e.select();})()")
    cdp.call("Input.insertText", {"text": value})
    # The run filter is committed by Enter; tag filtering also responds to it.
    for kind in ("keyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:6006/")
    parser.add_argument("--pilot-run", default="pilot/teacher-locomotion")
    parser.add_argument("--pilot-iterations", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("only a local TensorBoard endpoint is accepted")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("an existing Chrome/Chromium is required")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    views = [
        {"name": "tensorboard-pilot", "run_filter": "^" + re.escape(args.pilot_run) + "$",
         "runs": [args.pilot_run], "tags": ["Loss/Surrogate", "Loss/Value", "Train/mean_reward"],
         "expected_steps": list(range(args.pilot_iterations)), "excluded_text": "smoke/"},
        {"name": "tensorboard-students", "run_filter": "^smoke/student-(pure|finetune)$",
         "runs": ["smoke/student-pure", "smoke/student-finetune"],
         "tags": ["Loss/behavior", "Loss/total_loss", "Train/mean_reward"],
         "expected_steps": [0, 1], "excluded_text": "pilot/"},
    ]
    report = {"schema_version": 1, "status": "failed", "url": args.url, "views": [],
              "scope": "real local TensorBoard UI; 4096-env 20-iteration pilot and two-iteration student smoke; no full-training or convergence claim"}
    browser = None
    cdp = None
    with tempfile.TemporaryDirectory(prefix="php-tensorboard-chrome-") as profile, (args.output_dir / "chrome.log").open("w") as log:
        try:
            tags = read_json(args.url.rstrip("/") + "/data/plugin/scalars/tags")
            report["available_runs"] = sorted(tags)
            port = free_port()
            command = [chrome, "--headless=new", "--no-first-run", "--disable-dev-shm-usage", "--window-size=1600,1100",
                       f"--remote-debugging-port={port}", f"--user-data-dir={profile}", args.url]
            browser = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            started = time.monotonic()
            while time.monotonic() - started < 45:
                try:
                    targets = read_json(f"http://127.0.0.1:{port}/json/list")
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
                if cdp.evaluate("!!document.querySelector('input[placeholder=\"Filter tags (regex)\"]')"):
                    break
                time.sleep(0.2)
            else:
                raise TimeoutError("TensorBoard filters did not appear")
            cdp.evaluate("(() => {const e=Array.from(document.querySelectorAll('input[type=checkbox]')).find(e=>e.parentElement.parentElement.innerText.includes('Ignore outliers in chart scaling'));if(e?.checked)e.click();})()")
            cdp.evaluate("(() => {const e=Array.from(document.querySelectorAll('input[type=number]')).find(e=>Number(e.value)===0.6);if(!e)throw Error('smoothing input missing');e.focus();e.select();})()")
            cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            for kind in ("keyDown", "keyUp"):
                cdp.call("Input.dispatchKeyEvent", {"type": kind, "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
            cdp.call("Input.insertText", {"text": "0"})
            for kind in ("keyDown", "keyUp"):
                cdp.call("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
            cdp.evaluate("document.activeElement.blur()")
            time.sleep(0.3)
            settings = cdp.evaluate("({smoothing: Number(Array.from(document.querySelectorAll('input[type=range]')).find(e=>Number(e.value)<1)?.value), ignore_outliers_in_chart_scaling: Array.from(document.querySelectorAll('input[type=checkbox]')).find(e=>e.parentElement.parentElement.innerText.includes('Ignore outliers in chart scaling'))?.checked})")
            if settings["smoothing"] != 0 or settings["ignore_outliers_in_chart_scaling"]:
                raise AssertionError(f"chart settings did not apply: {settings}")
            report["chart_settings"] = {**settings, "domains_fitted_to_data": True}
            cdp.evaluate("document.querySelector('button[aria-label=\"Close side pane\"]')?.click()")
            for view in views:
                item = {**view, "series": []}
                for run in view["runs"]:
                    if run not in tags:
                        raise AssertionError(f"missing run: {run}")
                    for tag in view["tags"]:
                        if tag not in tags[run]:
                            # Pure DAgger has behavior loss, without PPO total_loss.
                            if run == "smoke/student-pure" and tag == "Loss/total_loss":
                                continue
                            raise AssertionError(f"missing scalar: {run}: {tag}")
                        endpoint = args.url.rstrip("/") + "/data/plugin/scalars/scalars?" + urlencode({"run": run, "tag": tag})
                        data = read_json(endpoint)
                        if [row[1] for row in data] != view["expected_steps"] or not all(math.isfinite(row[2]) for row in data):
                            raise AssertionError(f"invalid steps or values: {run}: {tag}")
                        item["series"].append({"run": run, "tag": tag, "points": data, "steps_verified": True, "all_finite": True})
                type_filter(cdp, "Filter runs (regex)", view["run_filter"])
                type_filter(cdp, "Filter tags (regex)", "^(" + "|".join(re.escape(tag) for tag in view["tags"]) + ")$")
                started = time.monotonic()
                while time.monotonic() - started < 30:
                    text = cdp.evaluate("document.body.innerText") or ""
                    compact = re.sub(r"\s+", "", text)
                    if all(tag in compact for tag in view["tags"]) and view["excluded_text"] not in text:
                        break
                    time.sleep(0.2)
                else:
                    raise TimeoutError(f"TensorBoard filters did not produce expected cards: {view['name']}")
                time.sleep(1)
                cdp.evaluate("Array.from(document.querySelectorAll('button[aria-label=\"Fit line chart domains to data\"]')).forEach(e=>e.click())")
                time.sleep(0.5)
                canvases = cdp.evaluate("Array.from(document.querySelectorAll('canvas')).filter(e=>{let r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0}).map(e=>{const copy=document.createElement('canvas');copy.width=e.width;copy.height=e.height;const ctx=copy.getContext('2d');ctx.drawImage(e,0,0);let colored=0;if(ctx){const p=ctx.getImageData(0,0,e.width,e.height).data;for(let i=0;i<p.length;i+=4){if(p[i+3]>0&&Math.max(p[i],p[i+1],p[i+2])-Math.min(p[i],p[i+1],p[i+2])>20)colored++;}}return {width:e.width,height:e.height,colored_pixels:colored};})")
                if len(canvases) < len(view["tags"]) or any(row["colored_pixels"] < 10 for row in canvases):
                    raise AssertionError(f"charts did not render colored curves: {canvases}")
                image = args.output_dir / (view["name"] + ".png")
                image.write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})["data"]))
                item.update(status="passed", ui_text=text, location=cdp.evaluate("location.href"), visible_chart_canvases=canvases,
                            screenshot=image.name, screenshot_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
                report["views"].append(item)
            report["status"] = "passed"
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            if cdp:
                cdp.socket.close()
            if browser and browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                browser.wait(timeout=10)
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "views": len(report["views"]), "error": report.get("error")}, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
