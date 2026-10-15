#!/usr/bin/env python3
"""Actually restore the sealed source archive after Git mode normalization."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
sys.dont_write_bytecode = True

ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
PACKAGE = ROOT / 'usage_assets/reports/final-student-reference629-resource-wait-preparation'
SEAL = 'e37fc402f854500447f87e196da31d965fc124c3296d2376d40d2bb6327ad64a'
OUT = WORK / 'local-checks/reference629-resource-source-final-git-restore-01'
PUBLIC = ROOT / 'usage_assets/reports/final-student-reference629-resource-wait-source-restore'
SNAPSHOT = WORK / 'reference629-resource-source-publication-build-01/source-snapshot'
PREPARATIONS = [
    ('outputs/research/final-student-reference629-crossboot-preparation-02',
     '9f32c251bcb25c3ed1fbe999bd49c8081a712ce0d6985a99f8ed6820c661af2b', 85),
    ('outputs/research/final-student-reference629-crossboot-publication-preparation-02',
     '255c2a87cc97945ca5cb923ec343264b952c371c1b43bed1efacf6afd96fa412', 206),
]

def fp(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

def regular_files(base):
    assert not base.is_symlink()
    entries = list(base.rglob('*'))
    assert not any(p.is_symlink() for p in entries)
    assert all(p.is_file() or p.is_dir() for p in entries)
    return {p.relative_to(base).as_posix(): p for p in entries if p.is_file()}

def check_preparation(base, expected_sha, count):
    manifest = base / 'preparation-manifest.json'
    assert fp(manifest)['sha256'] == expected_sha
    rows = json.loads(manifest.read_bytes())['files']
    assert len(rows) == count
    expected = {row['path'] for row in rows} | {'preparation-manifest.json'}
    assert set(regular_files(base)) == expected
    for row in rows:
        actual = fp(base / row['path'])
        assert actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256']
    return {'restored_directory': str(base), 'manifest_sha256': expected_sha,
            'payload_files': count, 'exact_file_set_and_sha_bytes': True}

def main():
    assert not OUT.exists() and not PUBLIC.exists()
    assert fp(PACKAGE / 'evidence-manifest.json')['sha256'] == SEAL
    package_before = {rel: fp(p) for rel, p in regular_files(PACKAGE).items()}
    inventory = json.loads((PACKAGE / 'raw-inventory.json').read_bytes())
    source_rows = json.loads((PACKAGE / 'report.json').read_bytes())['source_fingerprints']
    assert len(inventory) == len(source_rows) == 861
    source_by_relative = {Path(row['path']).relative_to(ROOT).as_posix(): row for row in source_rows}
    assert len(source_by_relative) == 861
    assert set(source_by_relative) == {row['path'] for row in inventory}
    OUT.mkdir()
    clone = OUT / 'git-permission-normalized'
    shutil.copytree(PACKAGE, clone)
    for p in [clone, *clone.rglob('*')]:
        assert not p.is_symlink()
        p.chmod((0o755 if p.stat().st_mode & 0o111 else 0o644) if p.is_file() else 0o755)
    clone_files = regular_files(clone)
    manifest = json.loads((clone / 'evidence-manifest.json').read_bytes())
    expected = {row['path']: row for row in manifest['files']}
    assert len(expected) == len(manifest['files']) == 525
    assert set(clone_files) == set(expected) | {'evidence-manifest.json'}
    assert fp(clone / 'evidence-manifest.json')['sha256'] == SEAL
    for rel, row in expected.items():
        actual = fp(clone / rel)
        assert actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes']
        assert stat.S_IMODE((clone / rel).stat().st_mode) in (0o644, 0o755)
    restored = OUT / 'restored-originals'
    argv = [sys.executable, '-B', str(clone / 'cloud888_report.py'), 'restore',
            '--input', str(clone), '--output', str(restored), '--manifest-sha256', SEAL]
    with (OUT / 'stdout.raw').open('xb') as stdout, (OUT / 'stderr.raw').open('xb') as stderr:
        child = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
        birth = Path(f'/proc/{child.pid}/stat').read_text()
        save(OUT / 'process-start.json', {'argv': argv, 'pid': child.pid, 'birth_stat': birth,
                                        'parent_pid': __import__('os').getpid(), 'source': fp(Path(__file__))})
        code = child.wait()
    execution = {'scope': 'Actual source archive restore only, after Git0644/0755 normalization; no scientific execution.',
                 'argv': argv, 'pid': child.pid, 'birth_stat': birth, 'actual_wait_returncode': code,
                 'input_package_sha256': SEAL, 'stdout': fp(OUT / 'stdout.raw'), 'stderr': fp(OUT / 'stderr.raw'),
                 'source': fp(Path(__file__))}
    save(OUT / 'execution.json', execution)
    assert code == 0, (OUT / 'stderr.raw').read_text()
    actual_restored = regular_files(restored)
    assert set(actual_restored) == {row['path'] for row in inventory}
    rows = []
    for row in inventory:
        rel = row['path']
        current = fp(restored / rel)
        for original in (SNAPSHOT / rel, ROOT / rel):
            original_fp = fp(original)
            assert current['sha256'] == row['sha256'] == source_by_relative[rel]['sha256'] == original_fp['sha256']
            assert current['bytes'] == row['bytes'] == source_by_relative[rel]['bytes'] == original_fp['bytes']
            assert stat.S_IMODE((restored / rel).stat().st_mode) == row['mode'] == stat.S_IMODE(original.stat().st_mode)
        rows.append({'relative': rel, 'bytes': current['bytes'], 'sha256': current['sha256'], 'mode': row['mode']})
    closures = [check_preparation(restored / rel, sha, count) for rel, sha, count in PREPARATIONS]
    assert package_before == {rel: fp(p) for rel, p in regular_files(PACKAGE).items()}
    assert not list(clone.rglob('*.pyc')) and not list(PACKAGE.rglob('*.pyc'))
    review = {'status': 'passed_actual_reference629_resource_source_git_mode_restore',
              'input_package_sha256': SEAL, 'publication_files_including_manifest': len(clone_files),
              'original_files': len(rows), 'actual_wait_returncode': code,
              'exact_sha_bytes_full_original_modes_file_set': True,
              'comparison_targets': ['original sealed build snapshot', 'current original source/control files', 'raw-inventory', 'source fingerprint report'],
              'restored_preparation_closures': closures, 'publication_source_unchanged': True,
              'no_bytecode_generated': True, 'scientific_jobs_started': False, 'actual_native1258_results_asserted': False,
              'restored': rows}
    save(OUT / 'exact-restoration-review.json', review)
    PUBLIC.mkdir()
    for name in ['process-start.json', 'execution.json', 'stdout.raw', 'stderr.raw', 'exact-restoration-review.json']:
        shutil.copyfile(OUT / name, PUBLIC / name)
    shutil.copyfile(Path(__file__), PUBLIC / Path(__file__).name)
    (PUBLIC / 'README.md').write_text('# 正式629资源等待源码：Git权限恢复实测\n\n'
        '源码准备包 seal `' + SEAL + '`。526份发布文件先全部按Git的0644/0755权限归一化；标准库restore真实退出0。'
        '861份原件逐一SHA256、bytes、完整原mode与精确file-set同时匹配原构建快照、当前原源码/控制收据与封存inventory。'
        '恢复出的85份preparation和206份publication源码再次通过各自外部seal及完整file-set核验。\n\n'
        '原件在[源码准备包](../final-student-reference629-resource-wait-preparation/README.md)。'
        '本旁包保存真实命令、出生记录、actualwait、stdout/stderr及逐文件核验，不改原包seal。'
        '此次仅恢复源码及普通CPU协议证据，没有启动科学作业，也不声明正在进行的1258批次完成。\n')
    payload = [{'path': rel, 'bytes': fp(p)['bytes'], 'sha256': fp(p)['sha256']}
               for rel, p in sorted(regular_files(PUBLIC).items())]
    save(PUBLIC / 'manifest.json', {'schema_version': 1, 'input_package_sha256': SEAL,
        'scope': 'Actual Git-mode-normalized861 original source/control file restore only; no native1258 result.', 'files': payload})
    print(json.dumps({'actual_wait_returncode': code, 'original_files': len(rows), 'publication_files': len(clone_files),
          'restored_source_closures': [85, 206], 'proof_manifest_sha256': fp(PUBLIC / 'manifest.json')['sha256'],
          'execution_sha256': fp(OUT / 'execution.json')['sha256']}, indent=2))

if __name__ == '__main__':
    main()
