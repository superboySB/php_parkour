#!/usr/bin/env python3
"""Actually restore the source archive via original236f/e238 with Git modes."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
PACKAGE = ROOT / 'usage_assets/reports/reproduction-20261015/full-cohort-browser-source-preparation-01'
SNAPSHOT = WORK / 'full-cohort-browser-source-publication-build-01/source-snapshot'
OUT = WORK / 'local-checks/full-cohort-browser-source-git-restore-01'
PUBLIC = ROOT / 'usage_assets/reports/reproduction-20261015/full-cohort-browser-source-git-restore-01'
HELPER_SHA = '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fp(path):
    path = Path(path); assert not any(p.is_symlink() for p in (path, *path.parents))
    a = path.stat(); raw = path.read_bytes(); b = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
    assert signature(a) == signature(b) and stat.S_ISREG(b.st_mode)
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def files(base):
    entries = list(base.rglob('*')); assert not any(p.is_symlink() for p in (base, *base.parents, *entries))
    assert all(p.is_file() or p.is_dir() for p in entries)
    return {p.relative_to(base).as_posix(): p for p in entries if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args(); seal = args.manifest_sha256
    assert len(seal) == 64 and all(x in '0123456789abcdef' for x in seal)
    assert not OUT.exists() and not PUBLIC.exists()
    assert fp(PACKAGE / 'evidence-manifest.json')['sha256'] == seal
    assert fp(PACKAGE / 'cloud888_report.py')['sha256'] == HELPER_SHA
    assert fp(LAUNCHER)['sha256'] == LAUNCHER_SHA
    before = {rel: fp(p) for rel, p in files(PACKAGE).items()}
    manifest = json.loads((PACKAGE / 'evidence-manifest.json').read_bytes())
    expected = {r['path']: r for r in manifest['files']}; assert len(expected) == len(manifest['files'])
    assert set(before) == set(expected) | {'evidence-manifest.json'}
    for rel, row in expected.items():
        assert all(before[rel][k] == row[k] for k in ('bytes', 'sha256'))
    inventory = json.loads((PACKAGE / 'raw-inventory.json').read_bytes())
    origin = {Path(r['path']).relative_to(ROOT).as_posix(): r for r in json.loads((PACKAGE / 'report.json').read_bytes())['source_fingerprints']}
    assert len(inventory) == len(origin) and set(files(SNAPSHOT)) == set(origin) == {r['path'] for r in inventory}
    OUT.mkdir(); clone = OUT / 'git-permission-normalized'; shutil.copytree(PACKAGE, clone)
    for path in [clone, *clone.rglob('*')]:
        path.chmod((0o755 if path.stat().st_mode & 0o111 else 0o644) if path.is_file() else 0o755)
    assert set(files(clone)) == set(before)
    for rel, original in before.items():
        actual = fp(clone / rel); assert all(actual[k] == original[k] for k in ('bytes', 'sha256'))
        assert stat.S_IMODE((clone / rel).stat().st_mode) in (0o644, 0o755)
    restored = OUT / 'restored-originals'; helper = clone / 'cloud888_report.py'
    command = ['/usr/bin/python3', '-B', str(helper), 'restore', '--input', str(clone),
               '--output', str(restored), '--manifest-sha256', seal]
    argv = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(helper), '--sha256', HELPER_SHA,
            '--output', str(OUT / 'original-parent'), '--', *command]
    outer = OUT / 'outer'; outer.mkdir()
    start = {'argv': argv, 'started_utc': now(), 'source': fp(Path(__file__)), 'launcher': fp(LAUNCHER),
             'input_package_sha256': seal, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'parent_pid': os.getpid(), 'parent_stat': Path('/proc/self/stat').read_text()}
    with (outer / 'stdout.raw').open('xb') as stdout, (outer / 'stderr.raw').open('xb') as stderr:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 start_new_session=True, close_fds=True)
        start.update(pid=child.pid, stat=Path(f'/proc/{child.pid}/stat').read_text())
        save(outer / 'process-start.json', start); code = child.wait()
    save(outer / 'process-exit.json', dict(start, actual_wait_returncode=code, finished_utc=now(),
         stdout=fp(outer / 'stdout.raw'), stderr=fp(outer / 'stderr.raw')))
    assert code == 0, (outer / 'stderr.raw').read_text()
    ps = json.loads((OUT / 'original-parent/process-start.json').read_bytes())
    pe = json.loads((OUT / 'original-parent/process-exit.json').read_bytes())
    assert ps['argv'] == pe['argv'] == command and pe['actual_wait_returncode'] == 0 and pe['pending_signals'] == []
    assert pe['parent_pid'] == ps['parent_pid'] == child.pid and pe['helper_sha256'] == HELPER_SHA and pe['launcher_sha256'] == LAUNCHER_SHA
    assert set(files(restored)) == set(origin)
    rows = []
    for row in inventory:
        rel = row['path']; actual = fp(restored / rel)
        for original in (SNAPSHOT / rel, ROOT / rel):
            observed = fp(original)
            assert actual['bytes'] == row['bytes'] == observed['bytes'] == origin[rel]['bytes']
            assert actual['sha256'] == row['sha256'] == observed['sha256'] == origin[rel]['sha256']
            assert stat.S_IMODE((restored / rel).stat().st_mode) == row['mode'] == stat.S_IMODE(original.stat().st_mode) == origin[rel]['mode']
        rows.append({'relative': rel, 'bytes': actual['bytes'], 'sha256': actual['sha256'], 'mode': row['mode']})
    assert before == {rel: fp(p) for rel, p in files(PACKAGE).items()}
    assert not list(PACKAGE.rglob('*.pyc')) and not list(clone.rglob('*.pyc')) and not list(restored.rglob('*.pyc'))
    review = {'status': 'passed_actual_browser_source_git_mode_restore', 'input_package_sha256': seal,
              'publication_files_including_manifest': len(before), 'original_files': len(rows),
              'original_e238_parent_actual_wait_returncode': 0, 'outer_actual_wait_returncode': code,
              'exact_original_SHA_bytes_full_modes_and_file_set': True,
              'comparison_targets': ['sealed build source-snapshot', 'current original frozen source/control files', 'raw-inventory', 'source fingerprint report'],
              'main_package_unchanged': True, 'no_bytecode_generated': True,
              'controls_rerun': False, 'HTTP_or_Chrome_executed': False, 'scientific_jobs_started': False,
              'future_full888_or1258_browser_acceptance_asserted': False, 'restored': rows}
    save(OUT / 'exact-restoration-review.json', review)
    snap = OUT / 'receipt-snapshot'; snap.mkdir()
    for name in ('outer', 'original-parent'):
        shutil.copytree(OUT / name, snap / name)
    for path in (OUT / 'exact-restoration-review.json', Path(__file__), LAUNCHER):
        shutil.copyfile(path, snap / path.name); (snap / path.name).chmod(stat.S_IMODE(path.stat().st_mode))
    raw = helper.read_bytes(); assert hashlib.sha256(raw).hexdigest() == HELPER_SHA
    module = ModuleType('_original236_browser_restore_receipts'); module.__file__ = str(helper)
    exec(compile(raw, str(helper), 'exec'), module.__dict__)
    PUBLIC.mkdir(); original_receipts = module.archive(snap, PUBLIC); shutil.copytree(snap, PUBLIC / 'readable')
    shutil.copyfile(helper, PUBLIC / 'cloud888_report.py')
    (PUBLIC / 'README.md').write_text('# 全批次浏览器源码：Git权限真实恢复\n\n'
        '[源码主包](../full-cohort-browser-source-preparation-01/README.md) seal `' + seal + '`。'
        '全部' + str(len(before)) + '份发布文件先按Git的0644/0755权限归一化；原236f标准库restore经原e238父真实Popen/child.wait退出0，外层真实Popen/wait退出0。'
        '全部' + str(len(rows)) + '份源码/CPU协议原件的精确集合、bytes、SHA256及完整原mode与构建快照、当前冻结原件和inventory逐项相同。\n\n'
        '本旁包完整保留[原父出生](readable/original-parent/process-start.json)、[原父真实退出](readable/original-parent/process-exit.json)、'
        '[外层出生](readable/outer/process-start.json)、[外层退出](readable/outer/process-exit.json)，两层stdout.raw/stderr.raw及[逐原件核验](readable/exact-restoration-review.json)。'
        '这些只是本次真实标准库恢复收据；没有重跑CPU控制或启动HTTP/Chrome/仿真，也不证明未来完整888/1258实际验收。原主包seal与全部字节保持。\n\n'
        '旁包11份原收据/恢复源的完整mode同样保留在[raw-inventory](raw-inventory.json)；可用附带原236f标准库restore和外部本旁包seal恢复到全新目录。\n')
    payload = [dict(fp(p), path=rel) for rel, p in sorted(files(PUBLIC).items())]
    save(PUBLIC / 'evidence-manifest.json', {'schema_version': 1, 'source_input_files': len(original_receipts),
         'input_package_sha256': seal, 'files': payload,
         'scope': 'Actual original236f/e238/outer Git-mode restore receipts only; not a future888/1258 browser or scientific result.'})
    module.verify_package(PUBLIC)
    print(json.dumps({'main_package_sha256': seal, 'original_files': len(rows),
                      'original_e238_parent_actual_wait_returncode': 0, 'outer_actual_wait_returncode': code,
                      'companion_manifest': fp(PUBLIC / 'evidence-manifest.json'),
                      'companion_original_receipts': len(original_receipts), 'companion_payload_files': len(payload),
                      'original_parent_exit': fp(PUBLIC / 'readable/original-parent/process-exit.json'),
                      'outer_exit': fp(PUBLIC / 'readable/outer/process-exit.json')}, indent=2))


if __name__ == '__main__':
    main()
