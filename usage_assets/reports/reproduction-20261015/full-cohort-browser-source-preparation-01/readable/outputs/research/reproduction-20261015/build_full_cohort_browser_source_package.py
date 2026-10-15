#!/usr/bin/env python3
"""Archive reviewed browser sources and existing CPU receipts, never run them."""
from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
PUBLIC = ROOT / 'usage_assets/reports/reproduction-20261015/full-cohort-browser-source-preparation-01'
STAGE = WORK / 'full-cohort-browser-source-publication-build-01'
HELPER = WORK / 'cloud888-publication-preparation-01/cloud888_report.py'
HELPER_SHA = '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
PREPARATIONS = {
    'formal629-http-browser-preparation-02': 'b444791746c01c6b1fdc5827aaa10d4eaa62a66632190674cd72b7c849c580c4',
    'formal629-http-browser-preparation-03': 'b2f10900cf082c3de0fae2723c3b8aa71c9d78ed07b9ae2a5592be46492a5edc',
    'formal629-http-browser-preparation-04': '2a57da852ade47c54448a42135685ced2a3cf5607d3968e09ca61f92f54077cb',
    'formal629-http-browser-preparation-05': '25bf670ca626e33ec815aa13490a95d4894f7b0851c1698ec2cce6c5eef748ed',
    'cloud888-full-browser-preparation-01': '58c47a6dd00cdec9048b042386e22241a552244f72e18491c37b1c0c334305fd',
    'cloud888-full-browser-preparation-02': '727cf6f60bdd34ad2c6cc3b370b24f3b14c3b42f8634e1e4a46a0d761708c401',
}
REVIEWS = {
    'shared-http-browser-core-independent-static-review-01.json': 'b0242ec7398b885f22b92d20f8f2483cc3ac8650af2caf34ea982b63b79cced0',
    'shared-http-browser-core-second-independent-static-review-01.json': 'af1c1131a7e3d6044d6ec287ec15fc177ab26f89ac0ab111e3090e48c64be00f',
    'formal629-http-browser-independent-static-review-02.json': 'cbda9d0c1cc250d91f97a4cc785d331363f7191e9927f123a4118afa4e0bae9e',
    'formal629-http-browser-independent-static-review-04.json': '29d0d15bd7e81ff080276b459914d3e553c79ae2d61c1e6e31aad507f3ab3e2d',
    'formal629-http-browser-independent-static-review-05.json': 'c56f04d004c2887cd4d60b35fbb093fe67a5b1c48421137f6d247f9af8f6b131',
    'cloud888-http-browser-independent-static-review-01.json': 'a37583ada3b004e89816fb518bf3f53eb4b8a7b8ee5180fc1b31ef250f5cd0a8',
    'cloud888-http-browser-independent-static-review-02.json': 'a33d67d521875382b67c62fd0caf8b481a58f10ca6f6cd2b5e0b98d6596b745c',
}


def fp(path):
    path = Path(path)
    assert not any(p.is_symlink() for p in (path, *path.parents))
    a = path.stat(); raw = path.read_bytes(); b = path.stat()
    assert stat.S_ISREG(a.st_mode)
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
    assert signature(a) == signature(b) and len(raw) == b.st_size
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def files(base):
    entries = list(base.rglob('*'))
    assert not any(p.is_symlink() for p in (base, *base.parents, *entries))
    assert all(p.is_dir() or p.is_file() for p in entries)
    return {p for p in entries if p.is_file()}


def load_helper():
    raw = HELPER.read_bytes(); assert hashlib.sha256(raw).hexdigest() == HELPER_SHA
    module = ModuleType('_original236_browser_source_archive'); module.__file__ = str(HELPER)
    exec(compile(raw, str(HELPER), 'exec'), module.__dict__)
    return module


def main():
    assert not PUBLIC.exists() and not STAGE.exists()
    originals = set(); closure_records = []
    for name, sha in PREPARATIONS.items():
        base = WORK / name; manifest = base / 'manifest.json'
        assert fp(manifest)['sha256'] == sha
        data = json.loads(manifest.read_bytes()); actual = files(base)
        if 'files' in data:
            assert {p.relative_to(base).as_posix() for p in actual} == {x['path'] for x in data['files']} | {'manifest.json'}
            for row in data['files']:
                assert fp(base / row['path']) == dict(row, path=str(base / row['path']))
        else:
            assert {p.name for p in actual} == {'README.md', 'manifest.json', 'verify_cloud888_http.py', 'test_adapter.py'}
        originals |= actual
        for row in data['dependencies']:
            assert fp(row['path']) == row
            originals.add(Path(row['path']))
        closure_records.append({'name': name, 'manifest': fp(manifest), 'payload_files': len(actual) - 1,
                                'dependencies': len(data['dependencies']), 'historical': name not in (
                                    'formal629-http-browser-preparation-05', 'cloud888-full-browser-preparation-02')})
    for name, sha in REVIEWS.items():
        path = WORK / name; assert fp(path)['sha256'] == sha; originals.add(path)
    for name in ('local-checks/formal629-http-browser-controls-01', 'local-checks/formal629-http-browser-controls-03',
                 'local-checks/formal629-http-browser-controls-04', 'local-checks/formal629-http-browser-controls-05',
                 'cloud888-full-browser-source-controls-01', 'cloud888-full-browser-source-controls-02'):
        originals |= files(WORK / name)
    for name in ('verify_formal629_http.py', 'verify_formal629_http03.py', 'verify_formal629_http04.py',
                 'verify_formal629_http05.py', 'test_formal629_http_browser.py', 'test_formal629_http_browser03.py',
                 'test_formal629_http_browser04.py', 'test_formal629_http_browser05.py',
                 'formal629-browser03-actual-completed-case-schema-readback.json',
                 'formal629-browser05-actual-completed-case-schema-readback.json',
                 'formal629-browser04-source-preservation.json',
                 'formal629-resource-publication-command-preparation-02.json',
                 'formal629-resource-publication-command-preparation-browser05.json',
                 'verify_full_cohort_browser_source_git_restore.py'):
        originals.add(WORK / name)
    originals |= {HELPER, ROOT / 'outputs/research/host_owned_launch.py', Path(__file__)}
    assert fp(WORK / 'formal629-resource-publication-command-preparation-02.json')['sha256'] == '2f800262dde6546f52dc08b5d57bb01612087ea45112d1abfe3a5213e84006fa'
    assert fp(WORK / 'formal629-resource-publication-command-preparation-browser05.json')['sha256'] == 'faed8cfdf6646c464f80a90fbc169bb3a0f3ed94ab5fb44853410f0ab7b26f65'
    assert fp(WORK / 'evidence_http_browser.py')['sha256'] == '5c7a0041d4090954b4d69da59d4f488d9d32ba0af8efef3b57f83d2e9a3deed6'
    external = ROOT / 'usage_assets/reports/final-student-reference629-resource-wait-preparation'
    assert fp(external / 'evidence-manifest.json')['sha256'] == 'e37fc402f854500447f87e196da31d965fc124c3296d2376d40d2bb6327ad64a'
    before = [dict(fp(p), mode=stat.S_IMODE(p.stat().st_mode)) for p in sorted(originals)]
    STAGE.mkdir(); snapshot = STAGE / 'source-snapshot'; snapshot.mkdir()
    for path in sorted(originals):
        assert path.is_relative_to(ROOT)
        target = snapshot / path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target); target.chmod(stat.S_IMODE(path.stat().st_mode))
    PUBLIC.mkdir(); helper = load_helper(); inventory = helper.archive(snapshot, PUBLIC)
    assert len(inventory) == len(originals)
    shutil.copyfile(HELPER, PUBLIC / 'cloud888_report.py')
    shutil.copytree(snapshot, PUBLIC / 'readable')
    save(PUBLIC / 'report.json', {
        'status': 'source_only_full_cohort_browser_preparation',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'preparations': closure_records, 'independent_reviews': [fp(WORK / name) for name in REVIEWS],
        'archived_original_files': len(originals), 'source_fingerprints': before,
        'ordinary_CPU_controls': {'formal_historical02': 15, 'formal_historical03': 18,
                                  'formal_historical04': 20, 'formal_final05': 22,
                                  'cloud_historical01': 13, 'cloud_final02': 20,
                                  'scope': 'Existing raw receipts only, synthetic schemas/mock Range and owned ordinary Python children. Shared tests overlap across versions; not a count of distinct scientific experiments. No controls rerun for packaging.'},
        'actual_full888_or1258_browser_executed': False, 'actual_full_cohort_publication_included': False,
        'scientific_jobs_started': False,
        'scope': 'Reviewed browser sources, historical rejected/superseded versions and existing ordinaryCPU receipts only. Existing limited three-case raw-schema reports do not assert a future publication or full cohort result.',
        'external_prerequisites': [{'public_path': 'usage_assets/reports/final-student-reference629-resource-wait-preparation',
                                    'evidence_manifest_sha256': 'e37fc402f854500447f87e196da31d965fc124c3296d2376d40d2bb6327ad64a',
                                    'scope': 'Original85/206 scientific source closure and its source/control prerequisites, not duplicated here.'},
                                   {'scope': 'Future complete actual888 publication, actual restored coverage and external seal; future complete actual1258 publication and external seal; existing Chrome/Chromium and original workspace paths. These actual artifacts are not supplied or inferred by this source-only package.'}]})
    save(PUBLIC / 'future-cli-templates.json', {
        'scope': 'Exact source-version templates only. Uppercase tokens require real separately reviewed future artifacts. Not executed by this package.',
        'formal05': ['/usr/bin/python3', '-B', str(WORK / 'verify_formal629_http05.py'),
                     '--package', 'ACTUAL_COMPLETE_FORMAL1258_PUBLICATION', '--manifest-sha256', 'ACTUAL_EXTERNAL_PUBLICATION_SHA256',
                     '--preparation-sha256', PREPARATIONS['formal629-http-browser-preparation-05'],
                     '--output', str(WORK / 'FRESH_FORMAL1258_BROWSER_OUTPUT')],
        'cloud02': ['/usr/bin/python3', '-B', str(WORK / 'cloud888-full-browser-preparation-02/verify_cloud888_http.py'),
                    '--package', 'ACTUAL_COMPLETE_CLOUD888_PUBLICATION', '--manifest-sha256', 'ACTUAL_EXTERNAL_PUBLICATION_SHA256',
                    '--preparation-sha256', PREPARATIONS['cloud888-full-browser-preparation-02'],
                    '--restored-coverage', 'ACTUAL_COMPLETE_236F_RESTORED_COVERAGE',
                    '--output', str(WORK / 'FRESH_CLOUD888_BROWSER_OUTPUT')],
        'additional_root_publication_templates': [fp(WORK / 'formal629-resource-publication-command-preparation-02.json'),
                                                   fp(WORK / 'formal629-resource-publication-command-preparation-browser05.json')]})
    prefix = 'readable/outputs/research/reproduction-20261015/'
    (PUBLIC / 'README.md').write_text('''# 全批次浏览器检查器：源码准备与CPU协议

本包只保存浏览器检查器源码、独立源码审查、已有普通CPU协议收据及历史修订。**完整888/1258批次的实际HTTP/Chrome验收尚未由本包执行或证明**；不包含未来完整出版结果、模型、PT、科学运行数据，也不承诺仅凭本包重建仿真或训练。

当前已审版本：

- [formal05准备说明](PREFIXformal629-http-browser-preparation-05/README.md)：准备seal `25bf670c…`、入口 `6effeb36…`，22项普通CPU控制与help真实退出0。1258个案例视频访问、2516个图像访问、54页，允许原归档共享同字节存储。
- [cloud02准备说明](PREFIXcloud888-full-browser-preparation-02/README.md)：准备seal `727cf6f6…`、入口 `11abc63e…`，20项合成普通CPU控制与help经原e238父真实退出0；缺包和不安全输出路径真实退出1。完整888行、74页及全部唯一MP4（含孤立、短片）需未来实际核验。
- [共享Range/CDP/自有Chrome核心](PREFIXevidence_http_browser.py)：`5c7a0041…`。显式Range逐字节核原片，另按Chrome真实UA核206；只清理自有Popen，真实wait与空session后才能删除profile。

独立源码审查：[formal05](PREFIXformal629-http-browser-independent-static-review-05.json)、[cloud02](PREFIXcloud888-http-browser-independent-static-review-02.json)、[共享核心初审](PREFIXshared-http-browser-core-independent-static-review-01.json)、[共享核心复审](PREFIXshared-http-browser-core-second-independent-static-review-01.json)。

formal02/03/04、cloud01及其原源码/manifest/普通CPU原始stdout、stderr和等待收据按原字节完整保留。formal02合法媒体别名/模型绑定缺口、formal04轨迹图与案例关联缺口、cloud01原案例媒体绑定与输出隔离缺口的requires-correction报告也保留；这些是明确历史记录，不是当前版本通过或未来实际结果。各版本测试重叠，不相加为科学实验次数。三个已completed案例的有限原始schema读回只使用内存storage resolver/预期SVG路径，不生成或验收未来图库。

[完整收录清单与范围](report.json) · [未来CLI模板](future-cli-templates.json) · [原路径/完整mode恢复清单](raw-inventory.json) · [全部发布SHA](evidence-manifest.json)。另收入原 `2f800…` 及最新 `faed8…` 操作模板，保留未来placeholder，不把模板当作实际执行。

大科学闭包作为明确外部前提：[已公开85/206源码准备包](../../final-student-reference629-resource-wait-preparation/README.md)，seal `e37fc402f854500447f87e196da31d965fc124c3296d2376d40d2bb6327ad64a`。这里仅直接保存浏览器所需原脚本/manifest依赖，不递归重复206/85的整个科学closure。实际完整888/1258出版包、其外部seal、云888原236f恢复树、模型/runtime及已有Chrome仍是分别审查的实际前提。原脚本绝对workspace约束保持，readable副本供审查，不从副本隐式启动作业。

仅标准库恢复源码及已有收据到全新目录，不执行任何CPU控制、HTTP、浏览器或科学任务。先从外部已审记录取得本包完整seal：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/full-cohort-browser-sources-new --manifest-sha256 <外部已审包SHA256>
```

Git只保存executable bit；发布文件可按0644/0755检出，原完整mode保留在inventory并由原236f恢复。真实Git权限归一化、原e238父和外层Popen/wait0及逐原件恢复核验见[恢复旁包](../full-cohort-browser-source-git-restore-01/README.md)。恢复只证明本源码/CPU证据字节闭包，不代表完整批次或机器人技能成功。
'''.replace('PREFIX', prefix))
    assert before == [dict(fp(p), mode=stat.S_IMODE(p.stat().st_mode)) for p in sorted(originals)]
    payload = sorted(files(PUBLIC)); assert all(p.stat().st_size < 50_000_000 for p in payload)
    save(PUBLIC / 'evidence-manifest.json', {'schema_version': 1, 'status': 'source_only_browser_preparation_archive',
         'source_input_files': len(originals), 'files': [dict(fp(p), path=p.relative_to(PUBLIC).as_posix()) for p in payload],
         'scope': 'Only reviewed browser source/control evidence and explicitly historical revisions; no future actual888/1258 publication, browser pass, model or scientific result.'})
    helper.verify_package(PUBLIC)
    print(json.dumps({'package': str(PUBLIC), 'manifest': fp(PUBLIC / 'evidence-manifest.json'),
                      'original_files': len(originals), 'payload_files': len(payload),
                      'payload_bytes': sum(p.stat().st_size for p in payload),
                      'max_file_bytes': max(p.stat().st_size for p in payload)}, indent=2))


if __name__ == '__main__':
    main()
