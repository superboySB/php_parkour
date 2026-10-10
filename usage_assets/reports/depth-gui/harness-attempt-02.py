#!/usr/bin/env python3
"""Observe the real student's --show-depth GUI inside the research Docker.

The native evaluation entry point and OpenCV rendering run unchanged. Wrappers
record the arrays actually supplied to imshow and capture only this evaluation's
named X11 window after the native waitKey paints it. No desktop is captured.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time

TITLE = "eval_student depth (delayed)"


def capture_depth_window(path: Path) -> dict:
    import numpy as np
    from PIL import Image

    class XImage(ctypes.Structure):
        _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                    ("xoffset", ctypes.c_int), ("format", ctypes.c_int),
                    ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                    ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                    ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
                    ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                    ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong),
                    ("blue_mask", ctypes.c_ulong)]

    x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                              ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                              ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)), ctypes.POINTER(ctypes.c_uint)]
    x11.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
    x11.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                             ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("XOpenDisplay failed")
    image = None
    try:
        def find(window, depth=0):
            title = ctypes.c_void_p()
            if x11.XFetchName(display, window, ctypes.byref(title)) and title:
                name = ctypes.string_at(title).decode(errors="replace")
                x11.XFree(title)
                if name == TITLE:
                    return window
            if depth >= 5:
                return None
            root, parent = ctypes.c_ulong(), ctypes.c_ulong()
            children, count = ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
            if not x11.XQueryTree(display, window, ctypes.byref(root), ctypes.byref(parent),
                                  ctypes.byref(children), ctypes.byref(count)):
                return None
            ids = [children[i] for i in range(count.value)]
            if children:
                x11.XFree(children)
            for child in ids:
                found = find(child, depth + 1)
                if found:
                    return found
            return None

        window = find(x11.XDefaultRootWindow(display))
        if window is None:
            raise RuntimeError("Native OpenCV depth window was not found")
        root, x, y = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        width, height, border, depth = (ctypes.c_uint() for _ in range(4))
        if not x11.XGetGeometry(display, window, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y),
                                ctypes.byref(width), ctypes.byref(height), ctypes.byref(border), ctypes.byref(depth)):
            raise RuntimeError("Could not read depth window geometry")
        image = x11.XGetImage(display, window, 0, 0, width, height, ctypes.c_ulong(-1).value, 2)
        if not image or image.contents.bits_per_pixel != 32:
            raise RuntimeError("Unsupported or unavailable X11 window pixels")
        raw = image.contents
        pixels = np.frombuffer(ctypes.string_at(raw.data, raw.bytes_per_line * raw.height),
                               dtype="<u4" if raw.byte_order == 0 else ">u4").reshape(raw.height, -1)[:, :raw.width]
        channels = []
        for mask in (raw.red_mask, raw.green_mask, raw.blue_mask):
            shift = (mask & -mask).bit_length() - 1
            maximum = mask >> shift
            channels.append((((pixels & mask) >> shift) * 255 // maximum).astype(np.uint8))
        rgb = np.stack(channels, axis=-1)
        unique = len(np.unique(rgb.reshape(-1, 3), axis=0))
        if unique < 20:
            raise AssertionError("Depth window capture is blank or unpainted")
        Image.fromarray(rgb).save(path)
        return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size, "width": raw.width, "height": raw.height,
                "unique_colors": unique, "capture": "XGetImage of exact native OpenCV window title"}
    finally:
        if image:
            x11.XDestroyImage(image)
        x11.XCloseDisplay(display)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args, native = parser.parse_known_args()
    if native and native[0] == "--":
        native.pop(0)
    if not Path("/.dockerenv").exists() or not os.environ.get("DISPLAY"):
        parser.error("Run in the GUI-enabled research Docker with a reachable DISPLAY")
    if "--show-depth" not in native or native[native.index("--show-depth") + 1] != "True":
        parser.error("Pass the native --show-depth True option after --")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use an empty output directory; previous evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    import cv2
    import numpy as np

    report = {"schema_version": 1, "status": "running", "display": os.environ["DISPLAY"],
              "native_argv": native, "started_unix": time.time(), "frames": [], "captures": [],
              "scope": "Actual native student --show-depth GUI; smoke checkpoint, no skill quality claim",
              "quality_verified": False, "errors": []}
    source_root = Path(__file__).resolve().parents[2]
    tracked_inputs = [Path(__file__).resolve(),
                      source_root / "wbt_training/training_runs/eval_student.py",
                      source_root / "wbt_training/utils/checkpoint.py"]
    if "--checkpoint" in native:
        tracked_inputs.append(Path(native[native.index("--checkpoint") + 1]).resolve())
    report["input_fingerprints"] = [{"path": str(path), "bytes": path.stat().st_size,
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                    for path in tracked_inputs]
    target = output / "report.json"

    def save():
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        temporary.replace(target)

    originals = cv2.imshow, cv2.waitKey, cv2.destroyAllWindows

    def show(title, value):
        result = originals[0](title, value)
        if title == TITLE:
            report["frames"].append({"index": len(report["frames"]), "shape": list(value.shape),
                                     "dtype": str(value.dtype), "finite": bool(np.isfinite(value).all()),
                                     "minimum": float(value.min()), "maximum": float(value.max()),
                                     "sha256": hashlib.sha256(value.tobytes()).hexdigest()})
        return result

    def pump(delay):
        result = originals[1](delay)
        count = len(report["frames"])
        if count in (3, 30):
            try:
                report["captures"].append(capture_depth_window(output / f"depth-frame-{count:04}.png"))
            except Exception as error:
                report["errors"].append(str(error))
            save()
        return result

    def close():
        frames = report["frames"]
        report.update(finished_unix=time.time(), shown_frames=len(frames),
                      unique_depth_frames=len({frame["sha256"] for frame in frames}),
                      all_frames_finite=all(frame["finite"] for frame in frames))
        report["status"] = "passed" if (len(frames) >= 30 and report["unique_depth_frames"] > 1
                                               and report["all_frames_finite"] and len(report["captures"]) == 2
                                               and not report["errors"]) else "failed"
        report["inputs_unchanged"] = all(
            hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
            for item in report["input_fingerprints"])
        if not report["inputs_unchanged"]:
            report["status"] = "failed"
        save()  # Isaac may terminate the process during subsequent app.close().
        return originals[2]()

    cv2.imshow, cv2.waitKey, cv2.destroyAllWindows = show, pump, close
    save()
    sys.argv = ["wbt_training.training_runs.eval_student", *native]
    try:
        runpy.run_module("wbt_training.training_runs.eval_student", run_name="__main__")
    except BaseException as error:
        if not isinstance(error, SystemExit) or error.code not in (None, 0):
            report.update(status="failed", finished_unix=time.time())
            report["errors"].append(f"{type(error).__name__}: {error}")
            save()
        raise
    finally:
        cv2.imshow, cv2.waitKey, cv2.destroyAllWindows = originals
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
