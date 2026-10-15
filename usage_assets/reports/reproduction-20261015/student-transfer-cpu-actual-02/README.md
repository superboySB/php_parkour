# 学生回传与 CPU 实测归档

实际回传 **32/32 文件**，两个最终 student/depth 配对共通过 **60 个 ORT 用例**，两组默认关节姿态最大绝对误差均为 **0**。
原始 prepare 的真实宿主父进程 wait 为 **0**；两只无 GPU、runc、无网络 CPU 容器均已退出 **0**。
根审查逐项验证了 **5241 个冻结文件**；本包保留冻结清单、审查源码、审查原件、CPU 输出与宿主日志，不重复归档整棵源树。

旧等待器在成功 fetch 后实际退出 **1**，错误为 `ValueError: Host boot differs from actual recovery`，阶段为 `local_resource_release`。
失败的 state、宿主 process-start/process-exit、完整 stdout/stderr 与成功 fetch 收据原样保留。后续直接调用未修改的原 prepare，仅完成 CPU 准备。
本快照时原生学生仿真尚未开始，物理质量与技能成功验收 **pending**。

四个最终 ONNX 位于独立 [model-payload](model-payload/README.md) 无损压缩子包（不含大 PT）。已实际恢复到全新路径并逐一核对原 SHA256，恢复 CPU 子进程真实退出 0。
该子包的 manifest SHA256：`785c1b60755723fd39193ee63c1e45b73c8569997ceab71a593b868780b99ef7`。

本包完整性核验需要从外部已审查记录取得本包 manifest SHA256：

```bash
python3 verify_package.py --package . --manifest-sha256 <已审查的报告包SHA256>
```

原件索引见 [origin-inventory.json](origin-inventory.json)，结论见 [report.json](report.json)，实际恢复日志见 [model-restore-execution.json](model-restore-execution.json)。
所有 Git 单文件小于 50 MB。完整回传的 28 个 JSON 与 4 个 ONNX 的原字节身份通过模型子包的同一 32-file 清单闭合。

本 v2 修订保留 v1 历史包不变，修正出版完整权限与 Git 克隆权限不一致的问题。
出版核验只检查 Git 保存的 executable bit；完整原件权限保留在 origin-inventory.json，恢复模型使用明确的 0644 权限。
