#!/usr/bin/env python3
"""Guarded keyboard compatibility bootstrap for the pinned native policy runner.

sshkeyboard 2.3.1 blocks in listen_keyboard() and returns None. The pinned
Holosoma listener incorrectly calls start()/join() on that return value after
listening ends. Only its run method is replaced in memory. No submodule file,
key mapping, input selection, callback, repeat setting or policy is changed.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import runpy
import sys


EXPECTED_KEYBOARD_SHA256 = "99706aaadf8057e61a501dd96bd1d9dc34ef82fd82b66342d496ff639a704039"
EXPECTED_RUN_SHA256 = "2fcd4f42001bae3a9f1ef84f2f1494c55c1e3da713a1905180d42d3f74ff5106"
EXPECTED_RUNNER_SHA256 = "59890b843f5854f5b10632b74afcb1434795a72a6f9e8e17bd7be35ac76ab966"
EXPECTED_SSHKEYBOARD_VERSION = "2.3.1"
EXPECTED_SSHKEYBOARD_SHA256 = "d23f6bc9b156e650436290504709ee4d69e692434f5118d2e28584d981cf3dc8"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guard(condition: bool, detail: str) -> None:
    if not condition:
        raise RuntimeError("Native keyboard compatibility guard failed: " + detail)


def install_keyboard_compat() -> dict:
    import sshkeyboard
    from holosoma_inference.inputs.impl import keyboard as native

    keyboard_path = Path(native.__file__).resolve()
    dependency_path = Path(sshkeyboard.__file__).resolve()
    _guard(sha256(keyboard_path) == EXPECTED_KEYBOARD_SHA256, "keyboard.py source changed; review before applying")
    _guard(importlib.metadata.version("sshkeyboard") == EXPECTED_SSHKEYBOARD_VERSION,
           "sshkeyboard distribution version changed")
    _guard(sshkeyboard.__version__ == EXPECTED_SSHKEYBOARD_VERSION, "sshkeyboard module version changed")
    _guard(sha256(dependency_path) == EXPECTED_SSHKEYBOARD_SHA256, "sshkeyboard source changed")
    _guard(native.listen_keyboard is sshkeyboard.listen_keyboard, "native listen_keyboard alias was already replaced")
    _guard(native.REPEAT_DELAY_FIRST == 0.15 and native.REPEAT_DELAY_REST == 0.05, "native delay constants changed")

    cls = native._KeyboardListenerThread
    original = cls.run
    marker = getattr(original, "_php_keyboard_compat_receipt", None)
    own_sha = sha256(Path(__file__).resolve())
    if marker is not None:
        _guard(marker.get("bootstrap_sha256") == own_sha, "a different bootstrap already replaced run")
        return dict(marker)
    _guard(native._listener is None or not native._listener.is_alive(), "listener is already running")
    _guard(Path(original.__code__.co_filename).resolve() == keyboard_path, "run was already replaced")
    _guard(hashlib.sha256(inspect.getsource(original).encode()).hexdigest() == EXPECTED_RUN_SHA256,
           "live native run method changed")

    def blocking_run(self) -> None:
        def on_press(keycode):
            for queue in self._subscribers:
                queue.append(keycode)

        try:
            native.listen_keyboard(
                on_press=on_press,
                delay_second_char=native.REPEAT_DELAY_FIRST,
                delay_other_chars=native.REPEAT_DELAY_REST,
            )
        except OSError:
            pass
        except TypeError:
            # Preserve the original older-API fallback and exception boundaries.
            native.listen_keyboard(on_press=on_press)

    receipt = {
        "schema_version": 1,
        "fix": "sshkeyboard synchronous return; remove invalid return.start/return.join only",
        "bootstrap_sha256": own_sha,
        "native_keyboard_sha256": EXPECTED_KEYBOARD_SHA256,
        "native_original_run_sha256": EXPECTED_RUN_SHA256,
        "sshkeyboard_version": EXPECTED_SSHKEYBOARD_VERSION,
        "sshkeyboard_source_sha256": EXPECTED_SSHKEYBOARD_SHA256,
        "only_class_method_replaced": "_KeyboardListenerThread.run",
    }
    blocking_run.__wrapped__ = original
    blocking_run._php_keyboard_compat_receipt = receipt
    cls.run = blocking_run
    return dict(receipt)


def launch(native_script: Path, policy_args: list[str]):
    from holosoma_inference.inputs.impl import keyboard as native

    entry = native_script.resolve(strict=True)
    expected = Path(native.__file__).resolve().parents[2] / "run_policy.py"
    _guard(entry == expected, "entry must be the installed native run_policy.py")
    _guard(sha256(entry) == EXPECTED_RUNNER_SHA256, "native run_policy.py source changed")
    receipt = install_keyboard_compat()
    print("PHP_NATIVE_KEYBOARD_COMPAT " + json.dumps(receipt, sort_keys=True), file=sys.stderr, flush=True)

    previous_argv, previous_path = sys.argv, list(sys.path)
    sys.argv = [str(entry), *policy_args]
    # Match Python's direct-script import path while executing the native entry.
    if sys.path:
        sys.path[0] = str(entry.parent)
    else:
        sys.path.append(str(entry.parent))
    try:
        return runpy.run_path(str(entry), run_name="__main__")
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path


def main(argv: list[str] | None = None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: run_native_policy.py /path/to/native/run_policy.py [native arguments...]")
    return launch(Path(args[0]), args[1:])


if __name__ == "__main__":
    main()
