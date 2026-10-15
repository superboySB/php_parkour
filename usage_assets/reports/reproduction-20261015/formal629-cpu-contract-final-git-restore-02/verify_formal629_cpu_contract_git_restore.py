#!/usr/bin/env python3
"""Restore actual CPU evidence with Git modes via the original owned parent."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
sys.dont_write_bytecode = True

ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
PACKAGE = ROOT / 'usage_assets/reports/reproduction-20261015/formal629-cpu-contract-actual-02'
SNAPSHOT = WORK / 'formal629-cpu-contract-publication-build-02/source-snapshot'
SEAL = '99a37fe0752cc7a92d4b8b1d14d961238b3bc76f715e97bc18b01e03e9dc9e60'
HELPER_SHA = '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
OUT = WORK / 'local-checks/formal629-cpu-contract-final-git-restore-02'
PUBLIC = ROOT / 'usage_assets/reports/reproduction-20261015/formal629-cpu-contract-final-git-restore-02'

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def fp(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}

def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

def files(base):
    entries = list(base.rglob('*'))
    assert not base.is_symlink() and not any(p.is_symlink() for p in entries)
    assert all(p.is_file() or p.is_dir() for p in entries)
    return {p.relative_to(base).as_posix(): p for p in entries if p.is_file()}

def main():
    assert not OUT.exists() and not PUBLIC.exists()
    assert fp(LAUNCHER)['sha256'] == LAUNCHER_SHA
    assert fp(PACKAGE / 'evidence-manifest.json')['sha256'] == SEAL
    assert fp(PACKAGE / 'cloud888_report.py')['sha256'] == HELPER_SHA
    before = {rel: fp(p) for rel, p in files(PACKAGE).items()}
    manifest = json.loads((PACKAGE / 'evidence-manifest.json').read_bytes())
    expected = {row['path']: row for row in manifest['files']}
    assert len(expected) == len(manifest['files']) == 70
    assert set(before) == set(expected) | {'evidence-manifest.json'}
    for rel, row in expected.items():
        assert before[rel]['bytes'] == row['bytes'] and before[rel]['sha256'] == row['sha256']
    inventory = json.loads((PACKAGE / 'raw-inventory.json').read_bytes())
    assert len(inventory) == 85 and len({row['path'] for row in inventory}) == 85
    assert set(files(SNAPSHOT)) == {row['path'] for row in inventory}
    OUT.mkdir()
    clone = OUT / 'git-permission-normalized'
    shutil.copytree(PACKAGE, clone)
    for p in [clone, *clone.rglob('*')]:
        p.chmod((0o755 if p.stat().st_mode & 0o111 else 0o644) if p.is_file() else 0o755)
    assert set(files(clone)) == set(before)
    for rel in before:
        actual = fp(clone / rel)
        assert actual['bytes'] == before[rel]['bytes'] and actual['sha256'] == before[rel]['sha256']
        assert stat.S_IMODE((clone / rel).stat().st_mode) in (0o644, 0o755)
    restored = OUT / 'restored-originals'
    helper = clone / 'cloud888_report.py'
    helper_argv = ['/usr/bin/python3', '-B', str(helper), 'restore', '--input', str(clone),
                   '--output', str(restored), '--manifest-sha256', SEAL]
    argv = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(helper), '--sha256', HELPER_SHA,
            '--output', str(OUT / 'original-parent'), '--', *helper_argv]
    outer = OUT / 'outer'
    outer.mkdir()
    start = {'argv': argv, 'started_utc': now(), 'source': fp(Path(__file__)), 'launcher': fp(LAUNCHER),
             'input_package_sha256': SEAL, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'parent_pid': os.getpid(), 'parent_stat': Path('/proc/self/stat').read_text()}
    with (outer / 'stdout.raw').open('xb') as stdout, (outer / 'stderr.raw').open('xb') as stderr:
        child = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True,
                                 stdin=subprocess.DEVNULL, close_fds=True)
        start.update(pid=child.pid, stat=Path(f'/proc/{child.pid}/stat').read_text())
        save(outer / 'process-start.json', start)
        code = child.wait()
    exit_receipt = dict(start, actual_wait_returncode=code, finished_utc=now(),
                        stdout=fp(outer / 'stdout.raw'), stderr=fp(outer / 'stderr.raw'))
    save(outer / 'process-exit.json', exit_receipt)
    assert code == 0, (outer / 'stderr.raw').read_text()
    parent_start = json.loads((OUT / 'original-parent/process-start.json').read_bytes())
    parent_exit = json.loads((OUT / 'original-parent/process-exit.json').read_bytes())
    assert parent_start['argv'] == parent_exit['argv'] == helper_argv
    assert parent_exit['actual_wait_returncode'] == 0 and parent_exit['pending_signals'] == []
    assert parent_start['parent_pid'] == parent_exit['parent_pid'] == child.pid
    assert parent_exit['helper_sha256'] == HELPER_SHA and parent_exit['launcher_sha256'] == LAUNCHER_SHA
    assert set(files(restored)) == {row['path'] for row in inventory}
    rows = []
    for row in inventory:
        actual = fp(restored / row['path'])
        original = fp(SNAPSHOT / row['path'])
        assert actual['bytes'] == row['bytes'] == original['bytes']
        assert actual['sha256'] == row['sha256'] == original['sha256']
        assert stat.S_IMODE((restored / row['path']).stat().st_mode) == row['mode'] == stat.S_IMODE((SNAPSHOT / row['path']).stat().st_mode)
        rows.append({'relative': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256'], 'mode': row['mode']})
    assert before == {rel: fp(p) for rel, p in files(PACKAGE).items()}
    assert not list(PACKAGE.rglob('*.pyc')) and not list(clone.rglob('*.pyc'))
    review = {'status': 'passed_actual_formal629_cpu_contract_git_mode_restore', 'input_package_sha256': SEAL,
              'publication_files_including_manifest': 71, 'original_files': 85,
              'original_e238_parent_actual_wait_returncode': 0, 'outer_actual_wait_returncode': code,
              'exact_original_sha_bytes_full_modes_file_set': True, 'comparison_target': str(SNAPSHOT),
              'original_package_unchanged': True, 'no_bytecode_generated': True,
              'scientific_job_started': False, 'native1258_completion_asserted': False, 'restored': rows}
    save(OUT / 'exact-restoration-review.json', review)
    PUBLIC.mkdir()
    for name in ['outer', 'original-parent']:
        shutil.copytree(OUT / name, PUBLIC / name)
    shutil.copyfile(OUT / 'exact-restoration-review.json', PUBLIC / 'exact-restoration-review.json')
    shutil.copyfile(Path(__file__), PUBLIC / Path(__file__).name)
    shutil.copyfile(LAUNCHER, PUBLIC / 'original-host-owned-launch.py')
    (PUBLIC / 'README.md').write_text('# 实际两629 CPU合同：Git权限恢复实测\n\n'
        '主包 seal `' + SEAL + '`。71份发布文件先按Git的0644/0755权限归一化，原236f标准库restore经原e238父进程实际执行。'
        '原父child.wait退出0，外层真实Popen/wait退出0；两层process-start/process-exit及stdout.raw/stderr.raw全部保留。\n\n'
        '85份原件逐一SHA256、bytes、完整原mode和精确file-set与原封包source-snapshot相同。'
        '包含两份完整629参考计划，不缩减物理指令或时序；主包seal与文件均未改变。'
        '本次仅标准库恢复CPU验收证据，不运行仿真，也不证明正在进行的1258物理测试完成。\n\n'
        '[CPU合同主包](../formal629-cpu-contract-actual-02/README.md) · '
        '[逐件恢复核验](exact-restoration-review.json) · '
        '[原e238父退出](original-parent/process-exit.json) · [外层退出](outer/process-exit.json)\n')
    payload = [{'path': rel, 'bytes': fp(p)['bytes'], 'sha256': fp(p)['sha256']}
               for rel, p in sorted(files(PUBLIC).items())]
    save(PUBLIC / 'manifest.json', {'schema_version': 1, 'input_package_sha256': SEAL,
         'scope': 'Actual Git-mode-normalized85 CPU contract originals restored by original236f/e238; no native run or future completion claim.', 'files': payload})
    print(json.dumps({'original_e238_parent_actual_wait_returncode': 0, 'outer_actual_wait_returncode': code,
        'original_files': 85, 'proof_manifest': fp(PUBLIC / 'manifest.json'),
        'parent_exit': fp(PUBLIC / 'original-parent/process-exit.json'),
        'outer_exit': fp(PUBLIC / 'outer/process-exit.json')}, indent=2))

if __name__ == '__main__':
    main()
