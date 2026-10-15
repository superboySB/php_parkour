# 新一轮58例的宿主资源等待控制04

原科学源码、四模型、CPU准备计划和时序保持不变。仅在内存明确替换 `recovered_previous` 与 `gpu_idle` 两个宿主函数：精确原busy状态可有限等待，原query错误仍失败；每次默认1800秒、最多3600秒，实际等待计入原43200秒总wall上限。仅清理自身尚未reap的只读查询客户端，不触碰其他GPU任务。

原38项资源协议CPU控制、03的42项完整门卫控制及04的5项变动控制和原e238真实0/7/130协议均保留。完整Mounts行仅按唯一Destination排序；任何行内容或其他inspect字段差异仍拒绝。实际API/CLI/GPU查询原件及收到的HTTP不完整响应字节在验证前保存。[源码独审](source-review.json)和[真实父进程入口独审](launcher-source-review.json)通过。

实际只读gate于2026-10-15 15:20:07北京时间退出0；boot、互斥锁、账号、socket/daemon、GPU空闲与旧失败批次释放均通过。随后15:20:31真实e238parent1096507启动wrapper1096508。此包仅保存源码、只读gate和不可变启动原件，运行中的stdout和未来终态不在快照内，不作完整58验收。

旧控制02及其真实gate1已[独立保留](../reproduction-20261015/native58-resource-wait-control02-preserved-01/README.md)，旧首批41例/parent1/三个sleep容器stop143见[完整失败包](../reproduction-20261015/native58-preserved-failed41-01/README.md)。新批次全部58例重新执行，不续写旧41。历史root143与八个观察缺口也不改写。

原件路径、字节SHA与完整mode见raw-inventory.json。恢复只需标准库与外部已审manifest SHA：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/native58-control04-originals-new --manifest-sha256 <外部已审SHA>
```

此包不恢复整棵冻结科学源树、模型和旧629依赖；不能单独执行仿真。[新CPU准备](../reproduction-20261015/native58-resource-wait-cpu-prepare-02/README.md)、[四ONNX无损包](../reproduction-20261015/student-transfer-cpu-actual-02/README.md)及[当前实际进展](../reproduction-20261015/index.md)分别公开。
