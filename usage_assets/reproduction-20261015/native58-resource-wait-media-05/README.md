这三段GIF来自已独立审查、实际完成的最终学生原生仿真58项，只展示指定原片时间区间的行为：纯学生前进跌倒、混合学生前进、混合学生在低横梁附近腾起后继续跑动。

001/030截取原片[3.90,11.90)秒，057截取[4.00,12.00)秒；480×270、fps=8、64帧，CPU完整解码均实际退出0。GIF百分之一秒时基使ffprobe编码时长为8.01秒；选取的原片区间仍为8秒。057处于低横梁端部附近和跟随视角，不能据此确认正向跨过整道横梁或课程；没有逐帧MP4 PTS到policy时钟映射，不推定精确offset。未触发阈值及survival启发式不等于技能／课程成功。

[播放页](playback.html)含3GIF及完整原MP4链接。[manifest.json](manifest.json)绑定原case、真实指标、CSV、release/clock、原58公开seal、实际独立review、6组全片8帧联系图／海报、057[4,8)秒16张原始帧、CPU argv／出生／actualwait及原始日志。root实际目检原件见[evidence/root-visual-review.json](evidence/root-visual-review.json)，另有[三张GIF联系图的root复核消息](evidence/root-derived-contact-review.json)。完整MP4留在[原58公开包](../../reports/final-student-native58-resource-wait-04/playback.html)，本侧包没有复制完整MP4、模型、科学源或历史科学依赖。

[browser/report.json](browser/report.json)保存实际HTTP三个GIF原字节200读回，以及Chrome三个GIF／十六张PNG decode和尺寸检查；包含HTTP请求、raw CDP／Chrome日志与截图。Chrome收到Browser.close后自然实际wait0，再删除profile。浏览器验收仅证明HTTP加载／图像解码，64帧完整解码由单独CPU原件证明。该HTTP回执覆盖浏览器调用时的派生文件快照；其后仅收集回执、补入root复核消息与离线验证器、更新本说明，不改变GIF、PNG或播放页。原58seal及原片前后不变。[browser-parent/process-exit.json](browser-parent/process-exit.json)保留真实e238父调用、argv、helper SHA与actualwait0。

本侧包evidence-manifest.json逐文件记录bytes、SHA256、mode及精确文件集合。取得独立公布的seal SHA后，可使用标准库离线核验；Git仅保存可执行位，必要时追加--restore-modes，在所有内容通过后恢复原权限。验证器本身也在seal文件表中；可追加--restore-to /绝对路径/新目录完成整包标准库复制、权限恢复与末端校验：

```bash
python3 -B reproduce/verify_media_seal.py --package . --manifest-sha256 ACTUAL_EXTERNAL_SEAL_SHA --restore-modes
```

从仓库根运行`python3 scripts/research/serve_evidence.py`，再打开`http://127.0.0.1:8088/usage_assets/reproduction-20261015/native58-resource-wait-media-05/playback.html`。reproduce内制作脚本记录实际历史b4只读CPU调用；重做媒体需同SHA完整原片及等价CPU ffmpeg。自动HTTP verifier额外依赖原工作区中固定的Range／CDP／main-restore源码和原58公开包；侧包离线字节验证不需要这些执行依赖，不构成新的科学runner。
