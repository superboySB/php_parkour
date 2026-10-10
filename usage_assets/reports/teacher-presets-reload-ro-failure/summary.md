# 五教师首次重载：保留只读资产目录失败

新统一镜像中的五个非默认原始教师 PT 均完成 CPU 解析，随后五次 Isaac 原生进程都返回 0。然而逐日志核验发现每例一个 `OSError: Read-only file system`：URDF converter 向只读源码资产目录创建 converted_rank0_pid*。**五次均未产生 quality.json，也没有实测 rollout、metrics、视频或 TensorBoard 评估结果，验收失败。** 这属于初始化失败，不能据此评价技能。

[独立原审查](review.json) 绑定五份原始日志、容器/driver/CPU 回执及 20 份未改变的原始 PT/YAML/ONNX/训练 manifest SHA；[原始英文审查说明](retained-original-summary.md) 也保持字节不变。之后将 35 份原始 G1 URDF/mesh 复制至独立可写数据目录，以公有 `--robot.asset.asset-root` 参数重试，Python 源码仍只读。新尝试使用新输出目录，不覆盖本轮失败。

原始报告保留在本页相邻文件及 retained/；大模型本身不重复复制。修复报告缺失时父进程仍成功的问题见 [退出门卫](../eval-quality-exit-guard/summary.md)。
