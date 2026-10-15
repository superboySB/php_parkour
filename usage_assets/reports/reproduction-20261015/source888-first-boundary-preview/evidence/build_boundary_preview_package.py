#!/usr/bin/env python3
"""Prepare one actual source preview; never call the 888 publication builder."""
import datetime
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path('/home/dzp/projects/php_parkour')
REPRO = ROOT / 'outputs/research/reproduction-20261015'
RAW = REPRO / 'cloud888-first-boundary-preview-raw-01'
OUT = ROOT / 'usage_assets/reports/reproduction-20261015/source888-first-boundary-preview'
HELPER = REPRO / 'cloud888_report.py'
HELPER_SHA = '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert sha(HELPER) == HELPER_SHA and not OUT.exists()
    spec = importlib.util.spec_from_file_location('boundary_byte_archive', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    OUT.mkdir()
    # Only byte archival is reused, never build()/terminal selection semantics.
    inventory = module.archive(RAW, OUT)
    assert len(inventory) == 31
    inspection_root = REPRO / 'local-checks/first-boundary-inspection-01'
    inspection = json.loads((inspection_root / 'inspection.json').read_bytes())
    assert inspection['completion']['source_boundary_completed'] is True
    assert inspection['completion']['policy_steps'] == 488
    assert sum(v['decoded_frames'] for v in inspection['videos']) == 491
    assert all(row['actual_wait_returncode'] == 0 for row in inspection['commands'])
    evidence = OUT / 'evidence'
    for name in ['first-boundary-inspection-01', 'first-boundary-gif-01', 'first-boundary-gif-host-01']:
        shutil.copytree(REPRO / 'local-checks' / name, evidence / name)
    for name in ['inspect_boundary_preview_cpu.py', 'derive_boundary_preview_cpu.py', 'verify_boundary_preview_http.py']:
        shutil.copyfile(REPRO / name, evidence / name)
    shutil.copyfile(HELPER, OUT / 'cloud888_report.py')
    shutil.copyfile(Path(__file__), evidence / 'build_boundary_preview_package.py')
    shutil.copyfile(inspection_root / 'poster.png', OUT / 'poster.png')
    shutil.copyfile(inspection_root / 'contact-sheet.png', OUT / 'contact-sheet.png')
    shutil.copyfile(REPRO / 'local-checks/first-boundary-gif-01/source-boundary-preview.gif', OUT / 'preview.gif')
    longest = inspection['chosen']['sha256']
    mp4s = [r for r in inventory.values() if r['storage'] == 'original']
    assert len(mp4s) == 3
    cards = []
    for row in sorted(mp4s, key=lambda r: r['sha256'] != longest):
        primary = row['sha256'] == longest
        cards.append('<article><h2>' + ('完整运动片段 9.78s' if primary else '原始单帧片段 0.02s')
                     + '</h2><video controls muted playsinline preload="auto" '
                     + ('data-primary poster="poster.png" ' if primary else '')
                     + 'src="' + html.escape(row['stored']) + '"></video><p><a href="'
                     + html.escape(row['stored']) + '">原 MP4 下载</a> · SHA256 <code>'
                     + row['sha256'] + '</code></p></article>')
    (OUT / 'playback.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>单 source boundary 实测预览</title><style>body{font:16px/1.6 sans-serif;max-width:1000px;margin:2em auto;padding:0 1em;color:#222}video,img{max-width:100%;height:auto}article{border-top:1px solid #ddd;margin-top:2em}code{overflow-wrap:anywhere}figure{margin:1em 0}</style><h1>单 source boundary 实测预览</h1><p>teacher locomotion，seed42，单 source / 单 terrain variant / first attempt。原 source 490 帧、488 个连续 policy steps，failed reset 0、timeout reset 0；原轨迹到达 native boundary。</p><p>这是平地动作参考片段；完整 888 队列与障碍课程质量仍待终态验收。画面原叠字 Commands: Not available 保留，完成判定来自原始 trajectory。</p><figure><img src="preview.gif" alt="原视频1.76至9.76秒的480x270 8FPS派生GIF"><figcaption>派生 GIF：[1.76,9.76)，480×270 / 8 FPS；原 MP4 字节保留。</figcaption></figure><figure><img src="poster.png" alt="5秒原始视频帧"></figure><figure><img src="contact-sheet.png" alt="完整原视频每秒采样的接触图"></figure>'''
        + ''.join(cards) + '<p><a href="README.md">核验与原件说明</a></p></html>')
    (OUT / 'README.md').write_text('''# 单 source boundary 实测预览

teacher locomotion、seed42、单 source、单 terrain variant、first attempt：原 source **490 帧**，连续 **488 个 policy steps**，failed resets **0**、timeout resets **0**；原轨迹达到 native boundary。
该片段在平地站立、前进、转向后停稳。完整 888 队列与障碍课程质量仍待终态验收，本包不给出完整队列比例。

[浏览播放与下载原 MP4](playback.html) · [派生 GIF](preview.gif) · [原视频接触图](contact-sheet.png)

三段原 MP4 全部 CPU 完整解码，共 491 个视频帧（1+1+489）；source 490 帧是原轨迹长度，二者口径不同。
派生 GIF 为最长原片的 [1.76,9.76) 秒、480×270、8 FPS、64 帧。原叠字 `Commands: Not available` 保留；source 完成由原轨迹证明。

整个实际回传目录的 31 文件（24 case + 7 acquisition）均保留：MP4 保持原字节，其余文件无损 gzip 去重，原路径、SHA256、bytes、完整 mode 存在 raw-inventory.json。
原 completion-review.json 的当时 CPU/visual pending 字段原样保留在 archive；后续 CPU/browser/visual 结论单独记录。
出版文件权限按 Git 保存的 executable bit 理解；restore 会按原件 inventory 恢复完整 mode（包括 0666）。

核验与恢复仅需 Python 标准库，先从外部已审查记录取得 evidence-manifest.json 的 SHA256：

```bash
python3 cloud888_report.py restore --input . --output /tmp/source-boundary-restored-new --manifest-sha256 <已审查的报告包SHA256>
```

恢复到全新独立目录，不运行任何科学作业。这里仅复用 236f 原 helper 的 archive/verify_package/restore 字节协议，未调用它的正式 888 publish 入口。
''')
    for row in inventory.values():
        f = RAW / row['path']
        assert f.stat().st_size == row['bytes'] and sha(f) == row['sha256']
    module.save(OUT / 'evidence-manifest.json', {'schema_version': 1,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_input_files': len(inventory),
        'files': [{'path': p.relative_to(OUT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                  for p in sorted(OUT.rglob('*')) if p.is_file()],
        'scope': 'Single-source preview candidate; original byte archive only, not888 terminal.'})
    module.verify_package(OUT)
    print(json.dumps({'package': str(OUT), 'candidate_manifest_sha256': sha(OUT / 'evidence-manifest.json')}, indent=2))


if __name__ == '__main__':
    main()
