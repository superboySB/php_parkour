# 低台阶单 source 实测预览

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

媒体终态见 [postpublication-media-review.json](postpublication-media-review.json)：三原片独立 CPU 全解码、派生 GIF 全解码、精确非零 Range、Chrome 自身三原片206/播放/拖动/图片解码和31原件真实恢复均已通过。原当时 pending 字段与首次宿主列表顺序检查失败均原样保留。

自动HTTP再检查依赖原工作区Chrome/CDP/serve_evidence；独立标准库restore不依赖原绝对工作区。浏览器候选seal保留在evidence内，最终seal另封新增的实际收据。
