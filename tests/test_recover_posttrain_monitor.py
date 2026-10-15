"""Recovery control tests use only synthetic files and explicit Docker doubles."""
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.research import posttrain_coverage as pc
from scripts.research import recover_posttrain_monitor as recovery
from test_posttrain_coverage import canonical, own_container


def original_container_state(*_):
    raise AssertionError("Original missing-name branch must not run")


@pytest.fixture
def partial(tmp_path, monkeypatch):
    coverage = tmp_path / "outputs" / recovery.COVERAGE_DIRECTORY
    coverage.mkdir(parents=True)
    (coverage.parent / ".posttrain-coverage.lock").touch()
    (coverage / "monitor.lock").touch()
    selection = {"input_identity": "f" * 64}
    pc.write(coverage / "selection.json", selection)
    pc.write(coverage / "monitor-status.json", {"status": "rejected", "error": "ValueError: Cannot inspect own container: Error: no such object: own-cpu\n"})
    source = tmp_path / "original.py"
    source.write_text("# Synthetic original; loading is explicitly doubled\n")
    args = SimpleNamespace(root=tmp_path, coverage_output=coverage, recovery_dir=coverage.parent / "posttrain-inspect-recovery-test",
                           action="once", poll_seconds=1)
    observation = {"status": "ready_for_cpu_verification_gpu_not_started", "selection": selection, "source": str(tmp_path / "source")}
    module = SimpleNamespace(require=pc.require, read=pc.read, write=pc.write, now=pc.now,
                             observe=lambda _: observation, docker_command=lambda _a, _s, role, _i: ("own-" + role, []),
                             container_state=original_container_state)
    monkeypatch.setattr(recovery, "load_monitor", lambda _: (module, source))
    def missing(argv, **_):
        assert argv[:3] == ["docker", "container", "inspect"]
        return SimpleNamespace(returncode=1, stdout="[]\n", stderr=f"Error: no such object: {argv[-1]}\n")
    monkeypatch.setattr(recovery.subprocess, "run", missing)
    return args, module, observation


def test_recovery_archives_before_advance_and_holds_both_locks(partial):
    args, module, _ = partial
    originals = {p.name: p.read_bytes() for p in args.coverage_output.iterdir()}
    def advance(_args, _observation):
        for name, raw in originals.items():
            assert (args.recovery_dir / "original" / name).read_bytes() == raw
        for path in (args.root / "outputs/.posttrain-coverage.lock", args.coverage_output / "monitor.lock"):
            with path.open("rb") as other:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {"status": "waiting", "blockers": ["synthetic CPU launch"]}
    module.advance = advance
    assert recovery.run(args) == 0
    receipt = pc.read(args.recovery_dir / "execution.json")
    assert receipt["host_control_changed"] and not receipt["frozen_cpu_gpu_runner_changed"]
    assert receipt["observation_status"] == "waiting"
    assert (args.coverage_output / "selection.json").read_bytes() == originals["selection.json"]


def test_readonly_recovery_preflight_writes_nothing(partial, capsys):
    args, module, _ = partial
    args.action = "dry-run"
    before = {str(p): p.read_bytes() for p in args.root.rglob("*") if p.is_file()}
    module.advance = lambda *_: pytest.fail("Dry-run advanced")
    assert recovery.run(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "recovery_preflight_passed_no_writes"
    assert before == {str(p): p.read_bytes() for p in args.root.rglob("*") if p.is_file()}
    assert not args.recovery_dir.exists()


@pytest.mark.parametrize("change", ["extra_partial", "selection", "wrong_rejection", "existing_container", "socket", "lock"])
def test_recovery_preflight_failure_preserves_originals_and_never_advances(partial, monkeypatch, change):
    args, module, observation = partial
    module.advance = lambda *_: pytest.fail("Rejected recovery advanced")
    held = None
    if change == "extra_partial": (args.coverage_output / "cpu-ready.json").write_text("{}")
    elif change == "selection": observation["selection"] = {"input_identity": "a" * 64}
    elif change == "wrong_rejection": pc.write(args.coverage_output / "monitor-status.json", {"status": "rejected", "error": "socket unavailable"})
    elif change == "existing_container":
        monkeypatch.setattr(recovery, "container_state", lambda *_: {"State": {"Running": False, "ExitCode": 0}})
    elif change == "socket":
        monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect to the Docker daemon"))
    else:
        held = (args.root / "outputs/.posttrain-coverage.lock").open("rb")
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = {p.name: p.read_bytes() for p in args.coverage_output.iterdir()}
    try:
        with pytest.raises((ValueError, BlockingIOError)):
            recovery.run(args)
    finally:
        if held: held.close()
    assert before == {p.name: p.read_bytes() for p in args.coverage_output.iterdir()}
    assert not args.recovery_dir.exists()


@pytest.mark.parametrize("change", [None, "image", "source", "network", "devices", "command"])
def test_host_replacement_preserves_existing_cpu_identity_guards(canonical, monkeypatch, change):
    args, _ = canonical
    source, key = args.root / "source" / args.source_tree, "f" * 64
    info = own_container(args, source, "cpu", key)
    if change == "image": info["Image"] = "wrong-image"
    elif change == "source": info["Mounts"][0]["Source"] = "/wrong"
    elif change == "network": info["HostConfig"]["NetworkMode"] = "host"
    elif change == "devices": info["HostConfig"]["DeviceRequests"] = [{"DeviceIDs": [args.gpu_uuid]}]
    elif change == "command": info["Config"]["Cmd"] = ["bash"]
    monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=json.dumps([info]), stderr=""))
    if change:
        with pytest.raises(ValueError): recovery.container_state(pc, args, source, "cpu", "own-container", key)
    else:
        assert recovery.container_state(pc, args, source, "cpu", "own-container", key) == info


def test_wrong_original_monitor_bytes_are_rejected_before_import(tmp_path):
    source = tmp_path / "source" / recovery.SOURCE_TREE / "scripts/research/posttrain_coverage.py"
    source.parent.mkdir(parents=True)
    source.write_text("raise RuntimeError('must never import changed monitor')\n")
    with pytest.raises(ValueError, match="exact original"):
        recovery.load_monitor(tmp_path)
