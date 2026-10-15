# 全批次浏览器检查器：源码准备与CPU协议

本包只保存浏览器检查器源码、独立源码审查、已有普通CPU协议收据及历史修订。**完整888/1258批次的实际HTTP/Chrome验收尚未由本包执行或证明**；不包含未来完整出版结果、模型、PT、科学运行数据，也不承诺仅凭本包重建仿真或训练。

当前已审版本：

- [formal05准备说明](readable/outputs/research/reproduction-20261015/formal629-http-browser-preparation-05/README.md)：准备seal `25bf670c…`、入口 `6effeb36…`，22项普通CPU控制与help真实退出0。1258个案例视频访问、2516个图像访问、54页，允许原归档共享同字节存储。
- [cloud02准备说明](readable/outputs/research/reproduction-20261015/cloud888-full-browser-preparation-02/README.md)：准备seal `727cf6f6…`、入口 `11abc63e…`，20项合成普通CPU控制与help经原e238父真实退出0；缺包和不安全输出路径真实退出1。完整888行、74页及全部唯一MP4（含孤立、短片）需未来实际核验。
- [共享Range/CDP/自有Chrome核心](readable/outputs/research/reproduction-20261015/evidence_http_browser.py)：`5c7a0041…`。显式Range逐字节核原片，另按Chrome真实UA核206；只清理自有Popen，真实wait与空session后才能删除profile。

独立源码审查：[formal05](readable/outputs/research/reproduction-20261015/formal629-http-browser-independent-static-review-05.json)、[cloud02](readable/outputs/research/reproduction-20261015/cloud888-http-browser-independent-static-review-02.json)、[共享核心初审](readable/outputs/research/reproduction-20261015/shared-http-browser-core-independent-static-review-01.json)、[共享核心复审](readable/outputs/research/reproduction-20261015/shared-http-browser-core-second-independent-static-review-01.json)。

formal02/03/04、cloud01及其原源码/manifest/普通CPU原始stdout、stderr和等待收据按原字节完整保留。formal02合法媒体别名/模型绑定缺口、formal04轨迹图与案例关联缺口、cloud01原案例媒体绑定与输出隔离缺口的requires-correction报告也保留；这些是明确历史记录，不是当前版本通过或未来实际结果。各版本测试重叠，不相加为科学实验次数。三个已completed案例的有限原始schema读回只使用内存storage resolver/预期SVG路径，不生成或验收未来图库。

[完整收录清单与范围](report.json) · [未来CLI模板](future-cli-templates.json) · [原路径/完整mode恢复清单](raw-inventory.json) · [全部发布SHA](evidence-manifest.json)。另收入原 `2f800…` 及最新 `faed8…` 操作模板，保留未来placeholder，不把模板当作实际执行。

大科学闭包作为明确外部前提：[已公开85/206源码准备包](../../final-student-reference629-resource-wait-preparation/README.md)，seal `e37fc402f854500447f87e196da31d965fc124c3296d2376d40d2bb6327ad64a`。这里仅直接保存浏览器所需原脚本/manifest依赖，不递归重复206/85的整个科学closure。实际完整888/1258出版包、其外部seal、云888原236f恢复树、模型/runtime及已有Chrome仍是分别审查的实际前提。原脚本绝对workspace约束保持，readable副本供审查，不从副本隐式启动作业。

仅标准库恢复源码及已有收据到全新目录，不执行任何CPU控制、HTTP、浏览器或科学任务。先从外部已审记录取得本包完整seal：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/full-cohort-browser-sources-new --manifest-sha256 <外部已审包SHA256>
```

Git只保存executable bit；发布文件可按0644/0755检出，原完整mode保留在inventory并由原236f恢复。真实Git权限归一化、原e238父和外层Popen/wait0及逐原件恢复核验见[恢复旁包](../full-cohort-browser-source-git-restore-01/README.md)。恢复只证明本源码/CPU证据字节闭包，不代表完整批次或机器人技能成功。
