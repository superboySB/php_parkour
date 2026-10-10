#!/usr/bin/env python3
"""Capture the real Viser browser UI with existing host Chrome (stdlib only).

The browser uses a new temporary profile and CPU SwiftShader. The project
server runs in Docker. No Python packages or browsers are installed on host.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


class CDP:
    def __init__(self, url: str):
        parsed = urlparse(url)
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        request = f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        self.socket.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError("Chrome rejected CDP WebSocket")
        self.counter = 0

    def read(self, count: int) -> bytes:
        result = b""
        while len(result) < count:
            piece = self.socket.recv(count - len(result))
            if not piece:
                raise EOFError("CDP socket closed")
            result += piece
        return result

    def message(self) -> dict:
        fragments = b""
        while True:
            first, second = self.read(2)
            length = second & 127
            if length == 126:
                length = struct.unpack("!H", self.read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self.read(8))[0]
            mask = self.read(4) if second & 128 else None
            payload = self.read(length)
            if mask:
                payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            opcode = first & 15
            if opcode == 8:
                raise EOFError("Chrome closed CDP")
            if opcode in (0, 1):
                fragments += payload
                if first & 128:
                    return json.loads(fragments)

    def call(self, method: str, params: dict | None = None) -> dict:
        self.counter += 1
        payload = json.dumps({"id": self.counter, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        if len(payload) < 126:
            header = bytes([129, 128 | len(payload)])
        elif len(payload) < 65536:
            header = bytes([129, 254]) + struct.pack("!H", len(payload))
        else:
            header = bytes([129, 255]) + struct.pack("!Q", len(payload))
        self.socket.sendall(header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(payload)))
        while True:
            response = self.message()
            if response.get("id") == self.counter:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response.get("result", {})

    def evaluate(self, expression: str):
        response = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in response:
            raise RuntimeError(response["exceptionDetails"])
        return response.get("result", {}).get("value")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="php-parkour-research")
    parser.add_argument("--motion-file", required=True, help="Motion file/directory as seen inside Docker")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        parser.error("an existing Chrome/Chromium is required; this script installs nothing")
    repo = Path(__file__).resolve().parents[2]
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    try:
        relative = output.relative_to(repo)
    except ValueError:
        parser.error("output directory must be inside the mounted checkout")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8080)) == 0:
            parser.error("port 8080 is occupied; refusing to capture an unrelated server")
    output.mkdir(parents=True, exist_ok=True)
    pidfile = Path("/workspace/php_parkour") / relative / "server.pid"
    server_shell = "echo $$ > " + shlex.quote(str(pidfile)) + "; exec /opt/php/bin/motion-python -u -m motion_matching.motion_visualizer --motion-file " + shlex.quote(args.motion_file)
    server_command = ["docker", "exec", args.container, "bash", "-c", server_shell]
    report = {"schema_version": 1, "status": "failed", "server_command": server_command,
              "scope": "real Viser UI in fresh Chrome profile with CPU SwiftShader; reference playback"}
    browser = None
    cdp = None
    with tempfile.TemporaryDirectory(prefix="php-viser-chrome-") as profile, (output / "server.log").open("w") as server_log, (output / "chrome.log").open("w") as browser_log:
        server = subprocess.Popen(server_command, stdout=server_log, stderr=subprocess.STDOUT)
        try:
            started = time.monotonic()
            while time.monotonic() - started < 180:
                if server.poll() is not None:
                    raise RuntimeError("Viser process exited before initialization")
                if "Starting animation loop" in (output / "server.log").read_text(errors="replace"):
                    break
                time.sleep(0.25)
            else:
                raise TimeoutError("Viser did not initialize")
            debug_port = free_port()
            browser_command = [chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                               "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                               "--window-size=1440,960", f"--remote-debugging-port={debug_port}",
                               f"--user-data-dir={profile}", "http://127.0.0.1:8080"]
            report["browser_command"] = browser_command
            browser = subprocess.Popen(browser_command, stdout=browser_log, stderr=subprocess.STDOUT, start_new_session=True)
            started = time.monotonic()
            while time.monotonic() - started < 45:
                try:
                    with urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=2) as stream:
                        targets = json.load(stream)
                    target = next(row for row in targets if row.get("type") == "page")
                    cdp = CDP(target["webSocketDebuggerUrl"])
                    break
                except (OSError, StopIteration):
                    time.sleep(0.25)
            else:
                raise TimeoutError("Chrome CDP did not initialize")
            cdp.call("Page.enable")
            started = time.monotonic()
            while time.monotonic() - started < 60:
                text = cdp.evaluate("document.body.innerText") or ""
                if "Play Animation" in text and "Animation Controls" in text:
                    break
                time.sleep(0.25)
            else:
                raise TimeoutError("Viser GUI controls did not appear in browser")
            time.sleep(2)
            report["initial_ui_text"] = text
            report["dom_controls"] = cdp.evaluate("Array.from(document.querySelectorAll('input,button,select,[role=slider]')).map(e=>({tag:e.tagName,type:e.type,role:e.getAttribute('role'),ariaLabel:e.getAttribute('aria-label'),text:e.innerText,value:e.value,checked:e.checked}))")
            frame_expression = "(() => {let e=Array.from(document.querySelectorAll('label')).find(e=>e.textContent.trim()==='Frame');for(let i=0;e&&i<6;i++,e=e.parentElement){let s=e.querySelector('[role=slider]');if(s)return {value:Number(s.getAttribute('aria-valuenow')),min:Number(s.getAttribute('aria-valuemin')),max:Number(s.getAttribute('aria-valuemax'))};}return null;})()"
            report["frame_before_play"] = cdp.evaluate(frame_expression)
            result = cdp.evaluate("(() => {let label=Array.from(document.querySelectorAll('label')).find(e=>e.innerText.includes('Play Animation'));if(!label)return {clicked:false};let box=label.querySelector('input') || document.getElementById(label.htmlFor);if(!box)return {clicked:false};box.click();return {clicked:true,checked:box.checked};})()")
            report["play_checkbox"] = result
            if not result.get("clicked") or not result.get("checked"):
                raise RuntimeError("could not enable the actual Play Animation checkbox")
            time.sleep(2)
            report["frame_after_play"] = cdp.evaluate(frame_expression)
            before, after = report["frame_before_play"], report["frame_after_play"]
            if before is None or after is None or before["value"] == after["value"]:
                raise RuntimeError("animation frame did not advance after Play")
            snapshot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            (output / "viser-playback.png").write_bytes(base64.b64decode(snapshot["data"]))
            report["active_ui_text"] = cdp.evaluate("document.body.innerText")
            report["canvas_count"] = cdp.evaluate("document.querySelectorAll('canvas').length")
            if report["canvas_count"] < 1:
                raise RuntimeError("browser has no WebGL canvas")
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if cdp:
                cdp.socket.close()
            if browser and browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                browser.wait(timeout=10)
            if (output / "server.pid").is_file():
                pid = (output / "server.pid").read_text().strip()
                if pid.isdigit():
                    subprocess.run(["docker", "exec", args.container, "kill", "-TERM", pid], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=5)
    report["artifacts"] = [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}
                           for path in sorted(output.iterdir()) if path.is_file() and path.name != "results.json"]
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
