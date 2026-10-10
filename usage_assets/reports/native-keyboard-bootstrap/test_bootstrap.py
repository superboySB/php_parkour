"""CPU-only tests; native listener IO is separately exercised with a private PTY."""
from collections import deque
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import sshkeyboard
from holosoma_inference.inputs.impl import keyboard as native

HERE = Path(__file__).resolve().parent


@pytest.fixture
def context(monkeypatch):
    name = "php_keyboard_bootstrap_under_test"
    spec = importlib.util.spec_from_file_location(name, HERE / "proposed/run_native_policy.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    # Register every class mutation for restoration; no listener is started.
    monkeypatch.setattr(native._KeyboardListenerThread, "run", native._KeyboardListenerThread.run)
    monkeypatch.setattr(native, "_listener", None)
    return helper, monkeypatch


def test_install_changes_only_run_and_is_idempotent(context):
    helper, _ = context
    cls = native._KeyboardListenerThread
    before = dict(cls.__dict__)
    command_mapping = dict(native.KEYBOARD_COMMANDS)
    receipt = helper.install_keyboard_compat()
    assert {k for k in set(before) | set(cls.__dict__) if before.get(k) is not cls.__dict__.get(k)} == {"run"}
    assert cls.run.__wrapped__ is before["run"]
    assert native.KEYBOARD_COMMANDS == command_mapping
    installed = cls.run
    assert helper.install_keyboard_compat() == receipt
    assert cls.run is installed


@pytest.mark.parametrize("behavior", ["normal", "oserror", "fallback", "unexpected", "fallback_oserror", "fallback_typeerror"])
def test_blocking_return_callback_delays_and_exceptions(context, behavior):
    helper, monkeypatch = context
    helper.install_keyboard_compat()
    calls = []
    def blocking(**kwargs):
        calls.append(kwargs)
        if behavior in ("fallback", "fallback_oserror", "fallback_typeerror") and len(calls) == 1:
            raise TypeError("synthetic unsupported delay kwarg")
        if behavior in ("oserror", "fallback_oserror"):
            raise OSError("synthetic terminal error")
        if behavior == "fallback_typeerror":
            raise TypeError("synthetic fallback failure")
        if behavior == "unexpected":
            raise RuntimeError("synthetic unexpected error")
        for key in ["]", "w", "c", "o", "i"]:
            kwargs["on_press"](key)
        return None
    monkeypatch.setattr(native, "listen_keyboard", blocking)
    listener = native._KeyboardListenerThread()
    first, second = listener.subscribe(), listener.subscribe()
    expected = {"unexpected": RuntimeError, "fallback_oserror": OSError, "fallback_typeerror": TypeError}.get(behavior)
    if expected:
        with pytest.raises(expected):
            listener.run()
    else:
        listener.run()
    assert calls[0]["delay_second_char"] == 0.15
    assert calls[0]["delay_other_chars"] == 0.05
    assert len(calls) == (2 if behavior.startswith("fallback") else 1)
    if len(calls) == 2:
        assert set(calls[1]) == {"on_press"}
    assert list(first) == list(second) == (["]", "w", "c", "o", "i"] if behavior in ("normal", "fallback") else [])


def test_no_tty_start_behavior_is_unchanged(context):
    helper, monkeypatch = context
    start = native._KeyboardListenerThread.start
    helper.install_keyboard_compat()
    monkeypatch.setattr(native.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    listener = native._KeyboardListenerThread()
    assert listener.start() is False
    assert listener.start() is False
    assert native._KeyboardListenerThread.start is start


@pytest.mark.parametrize("field", ["distribution_version", "module_version", "native_source", "dependency_source", "alias", "delay", "active_listener", "live_run"])
def test_dependency_and_live_source_guards_fail_before_mutation(context, tmp_path, field):
    helper, monkeypatch = context
    original = native._KeyboardListenerThread.run
    if field == "distribution_version":
        monkeypatch.setattr(helper.importlib.metadata, "version", lambda _: "99.0")
    elif field == "module_version":
        monkeypatch.setattr(sshkeyboard, "__version__", "99.0")
    elif field in ("native_source", "dependency_source"):
        target = native if field == "native_source" else sshkeyboard
        bad = tmp_path / "changed.py"
        bad.write_bytes(Path(target.__file__).read_bytes() + b"\n# changed\n")
        monkeypatch.setattr(target, "__file__", str(bad))
    elif field == "alias":
        monkeypatch.setattr(native, "listen_keyboard", lambda **_: None)
    elif field == "delay":
        monkeypatch.setattr(native, "REPEAT_DELAY_FIRST", 0.3)
    elif field == "active_listener":
        monkeypatch.setattr(native, "_listener", SimpleNamespace(is_alive=lambda: True))
    else:
        original = lambda _: None
        monkeypatch.setattr(native._KeyboardListenerThread, "run", original)
    with pytest.raises(RuntimeError, match="compatibility guard failed"):
        helper.install_keyboard_compat()
    assert native._KeyboardListenerThread.run is original


def test_different_bootstrap_cannot_replace_existing_patch(context, tmp_path):
    helper, monkeypatch = context
    helper.install_keyboard_compat()
    before = native._KeyboardListenerThread.run
    other = tmp_path / "other_bootstrap.py"
    other.write_text("# different bootstrap\n")
    monkeypatch.setattr(helper, "__file__", str(other))
    with pytest.raises(RuntimeError, match="different bootstrap"):
        helper.install_keyboard_compat()
    assert native._KeyboardListenerThread.run is before


@pytest.mark.parametrize("outcome", ["normal", "system_exit", "unexpected"])
def test_runpy_preserves_native_argv_and_propagates_exit(context, outcome):
    helper, monkeypatch = context
    entry = Path(native.__file__).resolve().parents[2] / "run_policy.py"
    before_argv, before_path = sys.argv, list(sys.path)
    forwarded = ["inference:g1-wbt-distillation-d435i", "--task.model-path", "['file with space.onnx','student.onnx']", "--task.depth-shm.no-required"]
    def execute(filename, *, run_name):
        assert filename == str(entry) and run_name == "__main__"
        assert sys.argv == [str(entry), *forwarded]
        assert sys.path[0] == str(entry.parent)
        if outcome == "system_exit":
            raise SystemExit(7)
        if outcome == "unexpected":
            raise ValueError("native failure")
        return {"native": True}
    monkeypatch.setattr(helper.runpy, "run_path", execute)
    if outcome == "normal":
        assert helper.launch(entry, forwarded) == {"native": True}
    else:
        with pytest.raises(SystemExit if outcome == "system_exit" else ValueError) as error:
            helper.launch(entry, forwarded)
        if outcome == "system_exit":
            assert error.value.code == 7
    assert sys.argv is before_argv
    assert sys.path == before_path


@pytest.mark.parametrize("kind", ["wrong_path", "changed_source"])
def test_entry_guard_rejects_before_keyboard_patch(context, tmp_path, kind):
    helper, monkeypatch = context
    entry = Path(native.__file__).resolve().parents[2] / "run_policy.py"
    original = native._KeyboardListenerThread.run
    if kind == "wrong_path":
        other = tmp_path / "run_policy.py"
        other.write_bytes(entry.read_bytes())
        entry = other
    else:
        monkeypatch.setattr(helper, "EXPECTED_RUNNER_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="compatibility guard failed"):
        helper.launch(entry, [])
    assert native._KeyboardListenerThread.run is original


def test_main_requires_native_entry(context):
    helper, _ = context
    with pytest.raises(SystemExit, match="usage"):
        helper.main([])
