# 正式两学生629：资源等待控制源码与CPU协议

本包只保存已独立审查的源码准备、有限普通CPU控制和只读status/help收据。它不包含正式1258原生结果、影片、实际合同或CPU计划，不证明正在进行的科学批次已经完成；最新运行状态见仓库note/usage。

[preparation03](sources/preparation03/HOST-RESOURCE-V3.md) 封85个文件（9f32）；原35中33份逐字节保持，另两份只改宿主parent reader和GPU创建前资源准入。[publication03](sources/publication03/HOST-RESOURCE-V3.md) 封206个文件（255c）；原kind/worker/map/CPUdecoder/科学检查与publisher/restore原字节保持，新增只读hostresource收据门卫。
唯一629helper名称为reference629_gpu_resource_wait.py，与58控制模块分开；实际nvidia查询busy才等待，同原UUID flock FD/inode/owner，真实1800秒预算/5秒间隔/15秒query，原物理计时与worker timeout不变。超时/取消只清理本次自有readonly query，不干预其他任务。晚观察即使实际rc0仍拒绝准入；无科学自动重试。

独立源码审查：[prep85](reference629-resource-wait-preparation-independent-static-review-02.json)、[pub206](reference629-resource-publication-independent-static-review-02.json)、[629宿主资源控制](reference629-resource-wait-host-independent-static-review-03.json)、[58宿主reader](native58-resource-wait-postreview-independent-static-review.json)、[真实parent launcher源码](formal629-resource-wait-root-launcher-independent-static-review-02.json)。

18项普通CPU子进程协议、10项合成admission、16项只读/合成publication协议真实退出0；GPU查询在协议测试中由明确标注的Python子进程或离线数据模拟，不是任何科学GPU结果。合法源码缺实际前提时status仍waiting/help0，错误seal退出1。旧49e/17CPU与新880/18CPU完整候选字节、失败/取消/晚query收据均保留，不追认旧源审为新源通过。

全部原路径、bytes、SHA256和完整mode无损归档在raw-inventory.json。另提供可读85/206source副本；原代码的绝对workspace约束仍在，不应从这些副本隐式启动作业。真正执行/出版必须另有同32fetch/实际58终态与独立review/新CPU合同与独立review/实际完整1258以及原parent0。已启动合同永不resume或重试。
[准确CLI依赖模板](cli-dependencies.json) 用大写标记实际必需证据，不发现newest、不填未来SHA。四最终ONNX和原32transfer/60ORT已另封在[模型与CPU原件包](../reproduction-20261015/student-transfer-cpu-actual-02/README.md)；本包不重复PT、完整5184源码、资产或科学runtime树。

仅标准库恢复到全新独立目录；先从外部已审记录取得本包seal：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/reference629-resource-sources-new --manifest-sha256 <外部已审报告包SHA256>
```

Git只保存executable bit，restore按原inventory恢复完整mode。真实Git权限归一化恢复证明见[独立恢复旁包](../final-student-reference629-resource-wait-source-restore/README.md)。恢复不运行科学作业；本包仅复用原236f archive/verify_package/restore字节协议。
