#!/usr/bin/env python3
"""Target only a newly launched PHP Tk controller via existing X11 libraries.

Runs inside Docker. The parent PID owns the GUI subprocess and its state file.
X11 input goes only to the exact controller window, never global desktop keys.
"""
from __future__ import annotations
import argparse
import ctypes as C
import ctypes.util
import json
import os
from pathlib import Path
import time


class KeyEvent(C.Structure):
    _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                ("display", C.c_void_p), ("window", C.c_ulong), ("root", C.c_ulong),
                ("subwindow", C.c_ulong), ("time", C.c_ulong), ("x", C.c_int), ("y", C.c_int),
                ("x_root", C.c_int), ("y_root", C.c_int), ("state", C.c_uint),
                ("keycode", C.c_uint), ("same_screen", C.c_int)]


class Event(C.Union):
    _fields_ = [("key", KeyEvent), ("pad", C.c_long * 24)]


class X11:
    def __init__(self):
        self.x = C.CDLL(ctypes.util.find_library("X11"))
        signatures = {
            "XOpenDisplay": ([C.c_char_p], C.c_void_p),
            "XDefaultRootWindow": ([C.c_void_p], C.c_ulong),
            "XQueryTree": ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)], C.c_int),
            "XFetchName": ([C.c_void_p, C.c_ulong, C.POINTER(C.c_char_p)], C.c_int),
            "XFree": ([C.c_void_p], C.c_int),
            "XStringToKeysym": ([C.c_char_p], C.c_ulong),
            "XKeysymToKeycode": ([C.c_void_p, C.c_ulong], C.c_uint),
            "XSendEvent": ([C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)], C.c_int),
            "XSetInputFocus": ([C.c_void_p, C.c_ulong, C.c_int, C.c_ulong], C.c_int),
            "XFlush": ([C.c_void_p], C.c_int),
            "XCloseDisplay": ([C.c_void_p], C.c_int),
        }
        for name, (args, result) in signatures.items():
            getattr(self.x, name).argtypes = args
            getattr(self.x, name).restype = result
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("this Docker process has no X11 display")
        self.root = self.x.XDefaultRootWindow(self.display)

    def children(self, window):
        root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
        if not self.x.XQueryTree(self.display, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(count)):
            return []
        result = list(children[:count.value])
        if children:
            self.x.XFree(children)
        return result

    def title(self, window):
        name = C.c_char_p()
        if not self.x.XFetchName(self.display, window, C.byref(name)) or not name:
            return None
        result = name.value.decode(errors="replace")
        self.x.XFree(name)
        return result

    def windows(self):
        found = []
        for top in self.children(self.root):
            for window in [top, *self.children(top)]:
                if self.title(window) == "Motion Matching - Keyboard Controller":
                    found.append(window)
        # Xwayland may repeat the title on a compositor frame and its client.
        # Keep the client, not both entries for the same Tk window.
        found = set(found)
        return sorted(window for window in found if not found.intersection(self.children(window)))

    def key(self, window, name, pressed):
        self.x.XSetInputFocus(self.display, window, 2, 0)
        self.x.XFlush(self.display)
        time.sleep(0.1)
        event = Event()
        event.key.type = 2 if pressed else 3
        event.key.send_event = 1
        event.key.display = self.display
        event.key.window = window
        event.key.root = self.root
        event.key.same_screen = 1
        event.key.keycode = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(name.encode()))
        if not event.key.keycode:
            raise ValueError("unknown X11 key")
        mask = 1 if pressed else 2
        if not self.x.XSendEvent(self.display, window, 0, mask, C.byref(event)):
            raise RuntimeError("targeted XSendEvent failed")
        self.x.XFlush(self.display)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=int)
    parser.add_argument("--baseline", default="[]")
    parser.add_argument("--key")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--window", type=int)
    args = parser.parse_args()
    x = X11()
    try:
        if args.parent is None:
            print(json.dumps({"windows": x.windows()}))
            return
        children = Path(f"/proc/{args.parent}/task/{args.parent}/children").read_text().split()
        eligible = []
        for pid in children:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if any(value.endswith(b"/ui/gui_controller.py") for value in command):
                env = dict(value.split(b"=", 1) for value in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if b"=" in value)
                eligible.append((int(pid), Path(os.fsdecode(env[b"MOTION_MATCHING_KEYBOARD_STATE_FILE"]))))
        if len(eligible) != 1:
            raise RuntimeError("expected exactly one Tk subprocess owned by this PHP parent")
        pid, statefile = eligible[0]
        baseline = set(json.loads(args.baseline))
        windows = [window for window in x.windows() if window not in baseline]
        if len(windows) != 1:
            raise RuntimeError(f"expected exactly one newly created matching Tk window; found {windows}, baseline {sorted(baseline)}")
        wrapper = windows[0]
        chosen = args.window or wrapper
        state = json.loads(statefile.read_text())
        if args.key:
            candidates = [chosen] if args.window else [wrapper, *x.children(wrapper)]
            for candidate in candidates:
                x.key(candidate, args.key, not args.release)
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    state = json.loads(statefile.read_text())
                    if state['key_states'].get(args.key.lower()) is (not args.release):
                        chosen = candidate
                        break
                    time.sleep(0.03)
                else:
                    continue
                break
            else:
                raise RuntimeError("targeted Tk event did not reach the parent's state transport")
        print(json.dumps({"gui_pid": pid, "parent_pid": args.parent, "wrapper_window": wrapper,
                          "event_window": chosen, "state_file": str(statefile), "state": state,
                          "event": {"key": args.key, "pressed": not args.release}}))
    finally:
        x.x.XCloseDisplay(x.display)


if __name__ == "__main__":
    main()
