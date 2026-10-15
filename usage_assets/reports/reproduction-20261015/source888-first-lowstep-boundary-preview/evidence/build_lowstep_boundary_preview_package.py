#!/usr/bin/env python3
"""One actual low-step source archive; never invoke full888 publication."""
import datetime
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour')
REPRO=ROOT/'outputs/research/reproduction-20261015'
RAW=REPRO/'cloud888-first-lowstep-boundary-preview-raw-01'
OUT=ROOT/'usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-preview'
HELPER=REPRO/'cloud888_report.py'
HELPER_SHA='236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert sha(HELPER)==HELPER_SHA and not OUT.exists()
    spec=importlib.util.spec_from_file_location('lowstep_original_archive',HELPER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cpu_root=REPRO/'local-checks/first-lowstep-boundary-cpu-02';cpu=json.loads((cpu_root/'report.json').read_bytes())
    host=json.loads((REPRO/'local-checks/first-lowstep-boundary-cpu-host-02/execution.json').read_bytes())
    quality=json.loads((RAW/'raw-case/quality.json').read_bytes())
    trajectory=[json.loads(line) for line in (RAW/'raw-case/trajectory.jsonl').read_bytes().splitlines()]
    completed=module.completion(quality,trajectory)
    assert len(trajectory)==505 and completed['source_boundary_completed'] and completed['policy_steps']==503
    assert cpu['total_decoded_frames']==506 and cpu['all31_source_files_before_after_equal']
    assert host['actual_wait_returncode']==0 and host['container_before_after_equal']
    assert all(r['actual_wait_returncode']==0 for r in cpu['commands'])
    OUT.mkdir();inventory=module.archive(RAW,OUT);assert len(inventory)==31
    evidence=OUT/'evidence'
    for name in ['first-lowstep-boundary-inspection-01','first-lowstep-boundary-cpu-01','first-lowstep-boundary-cpu-host-01','first-lowstep-boundary-cpu-02','first-lowstep-boundary-cpu-host-02']:
        shutil.copytree(REPRO/'local-checks'/name,evidence/name)
    for name in ['lowstep_boundary_media_cpu.py','run_lowstep_media_cpu.py','verify_boundary_preview_http.py']:
        shutil.copyfile(REPRO/name,evidence/name)
    shutil.copyfile(Path(__file__),evidence/Path(__file__).name);shutil.copyfile(HELPER,OUT/'cloud888_report.py')
    for name in ['poster.png','contact-sheet.png','obstacle-window.png']:
        shutil.copyfile(REPRO/'local-checks/first-lowstep-boundary-inspection-01'/name,OUT/name)
    shutil.copyfile(cpu_root/'source-lowstep-boundary-preview.gif',OUT/'preview.gif')
    videos=[r for r in inventory.values() if r['storage']=='original'];assert len(videos)==3
    cards=[]
    for row in sorted(videos,key=lambda r:r['sha256']!=cpu['chosen']['sha256']):
        primary=row['sha256']==cpu['chosen']['sha256']
        cards.append('<article><h2>'+('完整低台阶动作原片 10.08s' if primary else '原始单帧片段 0.02s')+'</h2><video controls muted playsinline preload="auto" '+('data-primary poster="poster.png" ' if primary else '')+'src="'+html.escape(row['stored'])+'"></video><p><a href="'+html.escape(row['stored'])+'">原 MP4 下载</a> · SHA256 <code>'+row['sha256']+'</code></p></article>')
    (OUT/'playback.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>低台阶单 source 实测预览</title><style>body{font:16px/1.6 sans-serif;max-width:1000px;margin:2em auto;padding:0 1em;color:#222}video,img{max-width:100%;height:auto}article{border-top:1px solid #ddd;margin-top:2em}code{overflow-wrap:anywhere}figure{margin:1em 0}</style><h1>低台阶单 source 实测预览</h1><p>teacher low-step，seed42，单 source / 单 terrain variant / first attempt。原 trajectory 505 帧、503 个连续 policy steps，failed reset 0、timeout reset 0；原轨迹到达 native boundary。</p><p>画面可见抬腿经过黑色台阶、继续行走后停稳；跟随视角存在遮挡，接触和完整越障不单独宣称。完整 888 队列与障碍课程质量仍待终态验收。本包不给出完整队列比例。</p><p>原叠字 Commands: Not available 保留；source 完成判定来自原始 trajectory。</p><figure><img src="preview.gif" alt="低台阶原视频2.06至10.06秒的480x270 8FPS派生GIF"><figcaption>派生 GIF：[2.06,10.06)，480×270 / 8 FPS；原 MP4 字节保留。</figcaption></figure><figure><img src="poster.png" alt="低台阶动作原视频6秒帧"></figure><figure><img src="obstacle-window.png" alt="原视频3至7秒的16帧接触图"></figure>'''+''.join(cards)+'<p><a href="README.md">核验与原件说明</a> · <a href="contact-sheet.png">全程接触图</a></p></html>')
    (OUT/'README.md').write_text('''# 低台阶单 source 实测预览

teacher low-step、seed42、单 source、单 terrain variant、first attempt：原轨迹 **505 帧**，连续 **503 个 policy steps**，failed resets **0**、timeout resets **0**；到达 native boundary。
画面可见抬腿经过黑色台阶、继续行走后停稳；跟随视角存在遮挡，接触和完整越障不单独宣称。完整 888 队列与障碍课程质量仍待终态验收，本包不给出完整队列比例。

[浏览播放与下载原 MP4](playback.html) · [派生 GIF](preview.gif) · [3–7 秒的16帧接触图](obstacle-window.png) · [全程接触图](contact-sheet.png)

三段原 MP4 独立 CPU 完整解码，共 **506** 视频帧（1+1+504）；505 是原 trajectory 行数，503 是扣除 warmup 与 boundary sentinel 后连续 policy steps，口径不同。
派生 GIF 取最长10.08秒原片的 **[2.06,10.06)** 秒，480×270、8 FPS、64帧。原 `Commands: Not available` 叠字保留；完成依据原始轨迹。

实际回传目录的31文件（24 case + 7 acquisition）全部保留。MP4 保持原字节，其他文件无损 gzip 去重；raw-inventory.json 记录原路径、SHA256、bytes、完整 mode。
原 completion-review.json 的当时 CPU/visual pending 字段原样保留，后续媒体终态另存。初次 CPU 宿主 helper 仅因 Docker Mounts 列表顺序断言失败，原源码与raw完整保留；02按Destination排序比较全部字段后实际重新解码，Docker exec真实wait0。
出版权限按 Git executable bit 理解；restore按原inventory恢复完整mode（含0666），不要求克隆后保留Git不保存的0644以外普通mode。

先从外部已审记录取得包的 evidence-manifest.json SHA256；仅需 Python 标准库、恢复到全新独立目录：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/lowstep-source-restored-new --manifest-sha256 <外部已审报告包SHA256>
```

仅复用236f原helper的archive/verify_package/restore字节协议，未调用正式888 build/publish入口，不运行科学作业。
''')
    for row in inventory.values():
        p=RAW/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    module.save(OUT/'evidence-manifest.json',{'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_input_files':31,'files':[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file()],'scope':'Single low-step source media preview candidate; not888 terminal or obstacle-course success.'})
    module.verify_package(OUT)
    print(json.dumps({'package':str(OUT),'candidate_manifest_sha256':sha(OUT/'evidence-manifest.json')},indent=2))
if __name__=='__main__':main()
