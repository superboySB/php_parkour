# 单 source boundary 实测预览

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

后续实测媒体终态见 [postpublication-media-review.json](postpublication-media-review.json)：CPU/GIF完整解码、三原片精确 Range、Chrome 实际播放/拖动/图片解码、31 原件完整 SHA/bytes/mode/file-set 恢复均通过。原当时 pending 记录保持不变。

自动 HTTP 再核验依赖原工作区的 Chrome/CDP/serve_evidence 文件；独立标准库 restore 不依赖原绝对工作区。浏览器核验候选 seal 与最终包新增的收据、终态审查由本包最终 evidence-manifest 全部封存。
