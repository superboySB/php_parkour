# 教师 ONNX 产物与最终导出验收

实际 4096 环境 pilot 配置的 `save_interval=500`，默认预处理保留 64 个变体。官方 `PPO.learn()` 在 iteration 0、500、… 定期同时保存 PT 与 ONNX，退出训练时再保存最终版本。`training.export_onnx` 没有参与该训练判断；它只控制 `eval_teacher.py` 的评估前导出。因此 20000 次迭代会保留 40 个周期导出和 iteration 19999 的最终导出，共 41 份，不能把 `--training.export-onnx False` 当成训练产物开关。

pilot 的最终 ONNX 为 1,183,810,736 字节，嵌入 4,546,688 帧 `joint_pos` / `joint_vel` / reference position / quaternion。四张 float32 参考表占 1,182,138,880 字节，策略、图与 metadata 约 1.67 MB。官方导出过程先写外部常量，随后 `attach_onnx_metadata` 用默认 `onnx.load` 加载常量并 `onnx.save` 内嵌；实际最终图的 external tensor 数为 0。旁边约一个图大小的 `_Constant_*` 与权重文件已不被该图引用。这次没有删除官方产物。

| 教师 | 原始帧数 | 64 变体预计帧数 | 单份 ONNX，十进制 GB | 41 份预计 GB |
| --- | ---: | ---: | ---: | ---: |
| high-climb-76 | 25,191 | 1,612,224 | 0.421 | 17.255 |
| high-step | 26,513 | 1,696,832 | 0.443 | 18.157 |
| locomotion | 71,042 | 4,546,688 | 1.184 | 48.536 |
| low-climb-76 | 32,814 | 2,100,096 | 0.548 | 22.456 |
| low-step | 25,676 | 1,643,264 | 0.429 | 17.586 |

五教师的 ONNX 合计约 124 GB，另预计约 3 GB 当前 run 的遗留常量和约 2.1 GB 全部 PT；日志与视频另计。其余四组是按真实 NPZ 帧数及相同导出器推算，没有冒充实际长训练产物。现有可用容量足够，保留官方周期 500 和最终导出，不改核心算法或学习参数。[机器可读估算](training-cloud-teacher-artifacts.json) 保留所有数字与假设。

最终 pilot 的 `model_00019.onnx` 已在无网络的独立 CPU 容器实跑：完整 ONNX checker、29 关节 metadata、两类观测 × 六种时间索引的 12 组有限且确定的 ONNXRuntime 推理全部通过。参考输出逐元素精确匹配图中的第一帧、中间帧、末帧，以及越界上限 clamp 和小数转整数的行为。[实际验收报告](training-cloud-teacher-final-onnx.json) 记录模型 SHA、runtime 版本和每组结果。这验证可执行导出与参考查表，不验证策略质量，也没有声称 PT/ONNX 数值等价。

正式训练结束后，对 manifest 指向的最终 `.onnx` 重复同一命令；PT 和 ONNX 的 iteration 应同时为 19999。`MODEL` 和 `REPORT` 使用真实容器内路径：

```bash
inference-python scripts/research/validate_teacher_onnx.py \
  --model "$MODEL" --output "$REPORT"
```

只需控制空间时，可以在完整 SHA 校验后选择下载最终 ONNX、PT、配置、events 与日志，或归档旧周期 ONNX；需要评估 checkpoint 时使用官方 `eval_teacher.py` 的 `--training.export-onnx True` 可重新导出，避免用长训练验证导出路径。当前验收保留所有原始产物，未启用筛选或清理。
