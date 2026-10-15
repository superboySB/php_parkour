# 首次 native58 批次：保留失败与已完成 41 例

原批次完成纯学生12方向、17代表场景及混合学生12方向，共 **41例、82个正常worker/空组与82份宿主映射**。原三阶段CPU后验已完整解码41段原片；本次独立只读审计核验这些原件，不重新仿真或另做媒体解码。

第四阶段开始前，原 GPU 空闲门卫拒绝。原 native、控制 wrapper 与真实父进程均保留退出 **1**；拦截瞬间的 GPU 查询输出没有保存，因此不能判定是外部任务或上一阶段短暂残留。最后17个场景尚未启动。这不是完整58验收。

三个 GPU 容器只承载 sleep infinity，原cleanup停止后实际状态均为 ExitCode **143**；科学driver、observer、worker和CPU finalizer的正常退出 **0** 分别记录，不混淆两者。

[独立部分审查](independent-partial-audit.json) · [归档范围](report.json) · [所有原件索引](raw-inventory.json) · [后续实际状态](../index.md)

归档包含旧cohort全部host/phases输出、observer/driver/CPU原始日志、41原MP4、控制/真实父进程与外层监督、只读审计及其实际执行原件。源树、1887输入和四模型只绑定身份，不在此重复保存；模型见[独立模型包](../student-transfer-cpu-actual-02/README.md)。不覆盖原失败，也不把已有41例补写为完整58终态。

标准库无损恢复需要外部已审查的 evidence-manifest.json SHA256：

```bash
python3 cloud888_report.py restore --input . --output /tmp/native58-failed41-new --manifest-sha256 <已审查的包SHA256>
```

恢复仅复制原始字节/权限，不运行科学任务；当前续做采用新的独立批次，原模型、科学函数和物理时序保持不变。
