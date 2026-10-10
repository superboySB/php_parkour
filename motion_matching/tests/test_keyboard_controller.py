"""GUI file transport must keep a Docker controller alive on partial writes."""

import json
from types import SimpleNamespace

import numpy as np

from motion_matching.ui.gui_controller import FileKeyboardController, GUIKeyboardController, KEYBOARD_STATE_ENV


def test_partial_gui_state_keeps_last_command_without_terminal_fallback(tmp_path, monkeypatch):
    controller = FileKeyboardController()
    controller.stop()
    controller.running = True
    controller.state_file = str(tmp_path / "state.json")
    controller.key_states["i"] = True
    (tmp_path / "state.json").write_text('{"key_states":')

    def no_terminal():
        raise AssertionError("A transient GUI write must not read Docker stdin")

    monkeypatch.setattr(controller, "_handle_terminal_input", no_terminal)
    controller.update()
    assert controller.running
    np.testing.assert_array_equal(controller.get_desired_velocity(), [1, 0, 0])
    (tmp_path / "state.json").write_text(json.dumps({"running": False, "key_states": {"i": False}}))
    controller.update()
    assert not controller.running
    np.testing.assert_array_equal(controller.get_desired_velocity(), [0, 0, 0])


def test_gui_transport_round_trip_needs_no_display(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setenv(KEYBOARD_STATE_ENV, str(path))
    gui = GUIKeyboardController()
    gui.key_states["j"] = True
    gui._save_state()
    controller = FileKeyboardController()
    controller.stop()
    controller.state_file = str(path)
    controller.running = True
    controller.update()
    np.testing.assert_array_equal(controller.get_desired_velocity(), [0, 1, 0])
    gui.running = False
    gui._save_state()
    controller.update()
    assert not controller.running
    assert not list(tmp_path.glob(".motion_matching_state_*"))


def test_quit_publishes_stop_before_periodic_writer_exits(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setenv(KEYBOARD_STATE_ENV, str(path))
    gui = GUIKeyboardController()
    gui._save_state()
    quit_calls = []
    gui.root = SimpleNamespace(quit=lambda: quit_calls.append(True))
    gui._quit_program()
    assert json.loads(path.read_text())["running"] is False
    assert quit_calls == [True]
