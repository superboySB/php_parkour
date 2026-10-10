#!/usr/bin/env python3
"""Bounded real-Tk key events -> file controller -> motion matching test.

Only sends events to the Tk window created by this process. Saves a cropped
image of that window and an actual 3-second generated reference trajectory.
Run inside the GUI-enabled Docker with motion-python. No physical policy
tracking or browser interaction is claimed.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
import traceback
from pathlib import Path

import numpy as np
from PIL import Image

from motion_matching import run as mm
from motion_matching.core.features import forward_kinematics
from motion_matching.io import build_combined_terrain_mesh, save_motion_npz
from motion_matching.metadata.constants import G1_JOINT_AXES
from motion_matching.ui.gui_controller import FileKeyboardController, GUIKeyboardController, KEYBOARD_STATE_ENV
from motion_matching.utils import math_utils


def capture_window(window) -> Image.Image:
    """Capture this X11 drawable, including its children, without desktop crops.

    The desktop may use a Wayland compositor: X11 root screenshots then show
    wallpaper even though Tk's Xwayland window has rendered successfully.
    Read the explicitly targeted drawable via the existing system libX11.
    """
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
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("XOpenDisplay failed for the Tk screenshot")
    image = None
    try:
        image = x11.XGetImage(display, window.winfo_id(), 0, 0,
                              window.winfo_width(), window.winfo_height(), ctypes.c_ulong(-1).value, 2)
        if not image:
            raise RuntimeError("XGetImage failed for the targeted Tk window")
        raw = image.contents
        if raw.bits_per_pixel != 32:
            raise RuntimeError(f"unsupported X11 pixel format: {raw.bits_per_pixel}")
        pixels = np.frombuffer(ctypes.string_at(raw.data, raw.bytes_per_line * raw.height),
                               dtype="<u4" if raw.byte_order == 0 else ">u4").reshape(raw.height, -1)[:, :raw.width]
        channels = []
        for mask in (raw.red_mask, raw.green_mask, raw.blue_mask):
            shift = (mask & -mask).bit_length() - 1
            maximum = mask >> shift
            channels.append((((pixels & mask) >> shift) * 255 // maximum).astype(np.uint8))
        result = Image.fromarray(np.stack(channels, axis=-1))
        if len(np.unique(np.asarray(result).reshape(-1, 3), axis=0)) < 20:
            raise AssertionError("targeted Tk screenshot is blank or unpainted")
        return result
    finally:
        if image:
            x11.XDestroyImage(image)
        x11.XCloseDisplay(display)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    os.environ[KEYBOARD_STATE_ENV] = str(output / "keyboard-state.json")
    report = {"schema_version": 1, "status": "failed", "display": os.environ.get("DISPLAY"),
              "scope": "real Tk-generated events, JSON transport, 180 motion-matching kinematic steps; no physical tracking"}
    system = mm.MotionMatchingSystem(required_skills=set())
    reader = FileKeyboardController()
    reader.stop()
    reader.running = True
    reader.state_file = os.environ[KEYBOARD_STATE_ENV]

    class Probe(GUIKeyboardController):
        def _setup_ui(self) -> None:
            super()._setup_ui()
            self.root.after(250, self.press)

        def press(self) -> None:
            try:
                self.root.focus_force()
                self.root.event_generate("<KeyPress>", keysym="i")
                self.root.event_generate("<KeyPress>", keysym="Tab")
                self.root.after(100, self.inspect)
            except Exception:
                self.fail()

        def inspect(self) -> None:
            try:
                self._save_state()
                reader.update()
                if not reader.is_key_pressed("i") or not reader.is_key_pressed("tab"):
                    raise AssertionError("Tk key press did not reach file controller")
                if self.status_labels["tab"].cget("text") != "High":
                    raise AssertionError("Tab did not toggle the GUI speed display")
                report["press_state"] = reader.get_key_status()
                self.root.update_idletasks()
                x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
                width, height = self.root.winfo_width(), self.root.winfo_height()
                screenshot = capture_window(self.root)
                screenshot.save(output / "keyboard-controller.png")
                self.root.event_generate("<KeyRelease>", keysym="Tab")
                self._save_state()
                qposes = []
                commands = []
                for _ in range(180):
                    reader.update()
                    bones, rotations = system.step(1 / 60, {
                        "stick_direction": reader.get_desired_velocity(), "trigger_skill": None,
                        "camera_azimuth": 0.0, "desired_strafe": False, "target_speed": mm.LOCOMOTION_HIGH_SPEED,
                    })
                    positions, world_rotations = forward_kinematics(bones, rotations, system.db.bone_parents, return_rotations=True)
                    dof = np.sum(math_utils.quat_to_scaled_angle_axis(rotations[-29:]) * G1_JOINT_AXES, axis=-1)
                    qposes.append(np.concatenate([world_rotations[1], positions[1], dof]))
                    commands.append(np.eye(15)[6])
                qposes = np.asarray(qposes, dtype=np.float32)
                displacement = float(np.linalg.norm(qposes[-1, 4:6] - qposes[0, 4:6]))
                if displacement < 0.5 or not np.isfinite(qposes).all():
                    raise AssertionError(f"forward command produced insufficient finite motion: {displacement} m")
                save_motion_npz(qposes, str(output / "keyboard_motion.npz"), target_fps=50, source_fps=60, vel_cmd=np.asarray(commands)[np.floor(np.linspace(0, 179, 150)).astype(int)])
                # Flat locomotion has no obstacles; keep a paired ground preview.
                build_combined_terrain_mesh([]).export(output / "keyboard_terrain.obj")
                np.save(output / "keyboard_terrain.npy", np.zeros((0, 10, 10), dtype=np.float32))
                self.root.event_generate("<KeyRelease>", keysym="i")
                self._save_state()
                reader.update()
                if reader.is_key_pressed("i"):
                    raise AssertionError("Tk key release did not reach file controller")
                report.update(status="passed", steps=180, simulation_frequency_hz=60,
                              target_speed_m_s=mm.LOCOMOTION_HIGH_SPEED, root_displacement_xy_m=displacement,
                              release_state=reader.get_key_status(), screenshot_bbox=[x, y, width, height])
                report["screenshot_capture"] = "XGetImage of this Tk drawable; blank-image check passed"
                self._quit_program()
                reader.update()
                if reader.running:
                    raise AssertionError("GUI Quit did not stop the file controller")
                report["quit_published_stop"] = True
            except Exception:
                self.fail()

        def fail(self) -> None:
            report["status"] = "failed"
            report["error"] = traceback.format_exc()
            self.running = False
            self.root.quit()

    gui = Probe()
    try:
        gui.start()
        gui.save_thread.join(timeout=2)
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
    finally:
        if gui.root is not None:
            gui.root.destroy()
    report["artifacts"] = [{"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
                           for p in sorted(output.iterdir()) if p.is_file() and p.name != "results.json"]
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
