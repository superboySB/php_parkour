"""Owned CPU fixtures only: no SSH, Docker operation, native loop or signal."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

BASE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def remote():
    return load('upgrade_waiting_watch_remote')


def record(remote):
    return {'pid': remote.OLD_PID, 'start_ticks': remote.OLD_START, 'pgid': remote.OLD_PID,
            'sid': remote.OLD_PID, 'cmdline': list(remote.OLD_COMMAND), 'state': 'S',
            'boot_id': '12345678-1234-1234-1234-123456789abc'}


@pytest.mark.parametrize('field,value', [('pid', 1), ('start_ticks', 42), ('pgid', 1), ('sid', 1),
    ('cmdline', ['python3', 'someone_else.py']), ('state', 'Z'), ('state', 'X'),
    ('boot_id', '87654321-1234-1234-1234-123456789abc')])
def test_foreign_reused_or_dead_old_process_is_rejected(remote, field, value):
    value_record = record(remote)
    value_record[field] = value
    with pytest.raises(ValueError):
        remote.old_identity(value_record, record(remote)['boot_id'])


def proc_stat(pid, birth, pgid=None, sid=None):
    tail = ['S', '1', str(pgid or pid), str(sid or pid)] + ['0'] * 15 + [str(birth), '0']
    return str(pid) + ' (name with ) parenthesis) ' + ' '.join(tail)


def test_process_fields_bind_first_birth_before_cmdline_read(remote, tmp_path, monkeypatch):
    proc = tmp_path / 'proc'
    p = proc / '31'
    p.mkdir(parents=True)
    boot = proc / 'sys/kernel/random/boot_id'
    boot.parent.mkdir(parents=True)
    boot.write_text(record(remote)['boot_id'])
    (p / 'stat').write_text(proc_stat(31, 111))
    (p / 'cmdline').write_bytes(b'python3\0watch.py\0')
    assert remote.process(31, proc)['start_ticks'] == 111
    original = Path.read_bytes
    def reused(path):
        if path == p / 'cmdline':
            (p / 'stat').write_text(proc_stat(31, 222))
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', reused)
    with pytest.raises(ValueError, match='birth'):
        remote.process(31, proc)


def test_pidfd_rechecks_birth_after_open_before_the_only_signal(remote, monkeypatch):
    opened, signals, closed = [], [], []
    values = [record(remote), {**record(remote), 'start_ticks': 999}]
    monkeypatch.setattr(remote, 'process', lambda *_: values.pop(0))
    monkeypatch.setattr(remote.os, 'pidfd_open', lambda pid, flags: opened.append((pid, flags)) or 87, raising=False)
    monkeypatch.setattr(remote.signal, 'pidfd_send_signal', lambda *args: signals.append(args), raising=False)
    monkeypatch.setattr(remote.os, 'close', lambda fd: closed.append(fd))
    with pytest.raises(ValueError, match='exact archived'):
        remote.terminate_exact_old(record(remote))
    assert opened == [(remote.OLD_PID, 0)] and closed == [87] and not signals


def test_exact_old_signal_uses_pidfd_sigterm_once_without_group_or_escalation(remote, monkeypatch):
    signals, polls, closed = [], [], []
    calls = iter([record(remote), record(remote), FileNotFoundError()])
    def process(*_):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(remote, 'process', process)
    monkeypatch.setattr(remote.os, 'pidfd_open', lambda pid, flags: 90 if pid == remote.OLD_PID else pytest.fail('Foreign PID'), raising=False)
    monkeypatch.setattr(remote.signal, 'pidfd_send_signal', lambda *args: signals.append(args), raising=False)
    monkeypatch.setattr(remote.os, 'close', lambda fd: closed.append(fd))
    monkeypatch.setattr(remote.os, 'kill', lambda *_: pytest.fail('PID-only signal'))
    monkeypatch.setattr(remote.os, 'killpg', lambda *_: pytest.fail('Group signal'))
    monkeypatch.setattr(remote.select, 'poll', lambda: SimpleNamespace(register=lambda *args: polls.append(args), poll=lambda _: [(90, 1)]))
    result = remote.terminate_exact_old(record(remote))
    assert signals == [(90, remote.signal.SIGTERM, None, 0)] and closed == [90]
    assert result['exit_observed'] and len(polls) == 1


def test_pidfd_timeout_does_not_send_kill_or_another_signal(remote, monkeypatch):
    signals = []
    monkeypatch.setattr(remote, 'process', lambda *_: record(remote))
    monkeypatch.setattr(remote.os, 'pidfd_open', lambda *_: 90, raising=False)
    monkeypatch.setattr(remote.signal, 'pidfd_send_signal', lambda *args: signals.append(args), raising=False)
    monkeypatch.setattr(remote.os, 'close', lambda *_: None)
    monkeypatch.setattr(remote.select, 'poll', lambda: SimpleNamespace(register=lambda *_: None, poll=lambda _: []))
    with pytest.raises(ValueError, match='no escalation'):
        remote.terminate_exact_old(record(remote))
    assert len(signals) == 1 and signals[0][1] == remote.signal.SIGTERM


def test_no_pidfd_means_no_pid_only_fallback(remote, monkeypatch):
    monkeypatch.delattr(remote.os, 'pidfd_open', raising=False)
    monkeypatch.setattr(remote.os, 'kill', lambda *_: pytest.fail('Unsafe fallback was used'))
    with pytest.raises(ValueError, match='unavailable'):
        remote.terminate_exact_old(record(remote))


@pytest.mark.parametrize('change', ('running', 'gpu_started', 'stale'))
def test_status_must_be_fresh_waiting_without_gpu(remote, tmp_path, change):
    value = {'status': 'waiting', 'gpu_started': False, 'observed_utc': remote.now()}
    if change == 'running': value['status'] = 'running'
    if change == 'gpu_started': value['gpu_started'] = True
    if change == 'stale': value['observed_utc'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=3)).isoformat()
    path = tmp_path / 'status.json'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError): remote.waiting_status(path)


def test_archive_keeps_exact_raw_and_rejects_links(remote, tmp_path):
    original = tmp_path / 'old.log'
    raw = b'line with trailing spaces  \r\n\x00old raw bytes\n'
    original.write_bytes(raw)
    target = tmp_path / 'retained.log'
    result = remote.retain_regular(original, target)
    assert target.read_bytes() == original.read_bytes() == raw and result['sha256'] == remote.sha(raw)
    link = tmp_path / 'link'
    link.symlink_to(original)
    with pytest.raises(ValueError): remote.retain_regular(link, tmp_path / 'not-created')
    assert not (tmp_path / 'not-created').exists()


def test_global_lock_must_really_be_released(remote, tmp_path, monkeypatch):
    monkeypatch.setattr(remote, 'ROOT', tmp_path)
    path = tmp_path / 'outputs/.posttrain-coverage.lock'
    path.parent.mkdir()
    path.touch()
    with path.open('r+') as held:
        remote.fcntl.flock(held, remote.fcntl.LOCK_EX | remote.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): remote.global_lock_free()
    assert remote.global_lock_free()['available'] is True


@pytest.fixture
def operation(remote, tmp_path, monkeypatch):
    root = tmp_path / 'remote-root'
    outputs = root / 'outputs'
    outputs.mkdir(parents=True)
    old = outputs / 'coverage-official-final'
    old.mkdir()
    (old / 'monitor-status.json').write_bytes(b'{"old":"status bytes"}\n')
    (outputs / 'posttrain-monitor.log').write_bytes(b'old log  \r\n')
    (outputs / 'posttrain-monitor-launch.json').write_bytes(b'{"old":"launch bytes"}\n')
    monkeypatch.setattr(remote, 'ROOT', root)
    monkeypatch.setattr(remote, 'OLD_COVERAGE', old)
    monkeypatch.setattr(remote, 'NEW_COVERAGE', outputs / 'coverage-official-final-ro-assets-v2')
    monkeypatch.setattr(remote, 'NEW_LOG', outputs / 'posttrain-monitor-ro-assets-v2.log')
    system = {'official': {'Id': 'fixed', 'Image': remote.IMAGE, 'Pid': 5, 'StartedAt': 'fixed', 'Mounts': ['frozen']},
              'native_training': [{'pid': 4, 'start_ticks': 8}], 'docker_ids': ['fixed']}
    monkeypatch.setattr(remote, 'system_snapshot', lambda: copy.deepcopy(system))
    monkeypatch.setattr(remote, 'old_guard', lambda *_: {'process': record(remote), 'waiting': {'status': 'waiting', 'gpu_started': False}})
    monkeypatch.setattr(remote, 'verify_new_source', lambda _: {'source': 'fixed', 'dry_run': {'status': 'waiting', 'gpu_started': False}})
    return remote, root, system


def test_audit_writes_only_new_receipts_without_signal_or_new_watch(operation, monkeypatch):
    remote, root, _ = operation
    monkeypatch.setattr(remote, 'terminate_exact_old', lambda *_: pytest.fail('Audit signalled a watcher'))
    monkeypatch.setattr(remote.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Audit launched anything'))
    original = {str(p): p.read_bytes() for p in (root / 'outputs').rglob('*') if p.is_file()}
    result = remote.run(remote.APPROVED_TREE, 'audit', 'fixture-audit', 'a' * 64)
    assert result['status'] == 'passed' and not result['signals'] and not remote.NEW_COVERAGE.exists()
    assert all(Path(name).read_bytes() == value for name, value in original.items())
    assert len(result['archived_originals']) == 3


@pytest.mark.parametrize('change', ('docker_ids', 'official', 'native_training'))
def test_upgrade_rejects_changed_official_fingerprint_before_any_signal(operation, monkeypatch, change):
    remote, root, system = operation
    remote.run(remote.APPROVED_TREE, 'audit', 'fixture-upgrade', 'a' * 64)
    system[change] = ['different']
    monkeypatch.setattr(remote, 'terminate_exact_old', lambda *_: pytest.fail('Changed training task was touched'))
    monkeypatch.setattr(remote.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Changed task launched watch'))
    with pytest.raises(ValueError, match='fingerprint'):
        remote.run(remote.APPROVED_TREE, 'upgrade', 'fixture-upgrade', 'a' * 64)
    result = json.loads((root / 'outputs/posttrain-monitor-upgrade-v2/fixture-upgrade/upgrade/report.json').read_text())
    assert result['status'] == 'failed' and not result['signals'] and not remote.NEW_COVERAGE.exists()


def test_upgrade_starts_only_fresh_watch_after_old_exit_and_actual_lock_release(operation, monkeypatch):
    remote, root, system = operation
    remote.run(remote.APPROVED_TREE, 'audit', 'fixture-upgrade-ok', 'a' * 64)
    events = []
    def terminate(_, receipt=None):
        events.append('old-exit')
        receipt.update(signal_sent=True, exit_observed=True)
        return receipt
    monkeypatch.setattr(remote, 'terminate_exact_old', terminate)
    monkeypatch.setattr(remote, 'global_lock_free', lambda: events.append('lock-free') or {'available': True})
    def start(argv, **kwargs):
        assert events == ['old-exit', 'lock-free']
        events.append('new-watch')
        assert argv == remote.command(remote.APPROVED_TREE, 'watch') and kwargs['start_new_session']
        remote.write(remote.NEW_COVERAGE / 'monitor-status.json', {'status': 'waiting', 'gpu_started': False, 'observed_utc': remote.now()})
        (remote.NEW_COVERAGE / 'monitor.lock').touch()
        return SimpleNamespace(pid=77, poll=lambda: None)
    monkeypatch.setattr(remote.subprocess, 'Popen', start)
    monkeypatch.setattr(remote.time, 'sleep', lambda _: None)
    monkeypatch.setattr(remote, 'process', lambda _: {'pid': 77, 'start_ticks': 88, 'pgid': 77, 'sid': 77,
        'state': 'S', 'boot_id': record(remote)['boot_id'], 'cmdline': remote.command(remote.APPROVED_TREE, 'watch')})
    result = remote.run(remote.APPROVED_TREE, 'upgrade', 'fixture-upgrade-ok', 'a' * 64)
    assert result['status'] == 'passed' and result['official_native_and_docker_unchanged']
    assert events == ['old-exit', 'lock-free', 'new-watch']
    launch = root / 'outputs/posttrain-monitor-upgrade-v2/fixture-upgrade-ok/upgrade/new-launch.json'
    assert json.loads(launch.read_text())['process']['start_ticks'] == 88


def test_default_host_preview_never_connects_or_writes(monkeypatch, tmp_path, capsys):
    host = load('upgrade_waiting_watch')
    monkeypatch.setattr(host.subprocess, 'run', lambda *_a, **_k: pytest.fail('Preview contacted SSH'))
    import sys
    monkeypatch.setattr(sys, 'argv', ['helper', '--attempt', 'future-root-approved', '--receipt-dir', str(tmp_path / 'not-created')])
    assert host.main() == 0
    value = json.loads(capsys.readouterr().out)
    assert value['status'] == 'preview_only_no_ssh' and not (tmp_path / 'not-created').exists()
    assert 'ControlMaster=auto' in value['command'] and host.APPROVED_TREE in value['command'][-1]


def test_helper_source_has_no_docker_mutation_or_group_signal():
    source = (BASE / 'upgrade_waiting_watch_remote.py').read_text()
    assert 'os.kill(' not in source and 'os.killpg(' not in source
    for action in ('run', 'start', 'stop', 'restart', 'kill', 'rm', 'exec'):
        assert "['docker', '" + action + "'" not in source
