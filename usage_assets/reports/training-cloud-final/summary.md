# 最终统一镜像的云端 smoke 验收

最终主 pipeline **22/22 通过、退出码 0**。训练采用已有 smoke 配置：64 environments、2 iterations；七个评估各运行 1 environment、250 control steps。五教师、六教师 preset、两学生训练，以及七次评估与两次独立导出全部完成。这验证真实训练、恢复、渲染和导出路径，不是完整官方日程，也不证明技能收敛；所有报告仍记录 `quality_verified=false`。

使用最终统一镜像，local ID `sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f`，云端加载后的 ID `sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd`。两端 Config/RootFS 内容指纹相同：`2a43037e2397fac3e343e8d621dd42c41ea7c27da82602789d575fddda112482`。冻结源码是 git `3439cb7da79d199a1dad77fca17486befb9c37f6`、tree SHA `0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab`；运行后 1903 个 snapshot 文件的 SHA 和权限逐项一致，见 [源码复核](source-snapshot-after.json)。

[最终 cloud doctor](doctor.log) 已通过，完整镜像、挂载和 GPU 选择见 [deployment](deployment.json)。只使用物理 GPU 1，UUID `GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5`，容器内仅该卡、编号为 0。显式禁用 W&B，使用本地 registry/checkpoint 和 TensorBoard；HF offline guards 也已设置。约 711.748 秒完成主 pipeline（按最后日志写入时间计）；约一秒一次、截至主 pipeline 结束的 648 个显存样本中峰值为 **6664 MiB**。这只是尽力采样，可能漏掉短峰值；[交还记录](gpu-handoff.json) 确认训练/eval 进程已退出、卡上无 compute process，之后的 CPU 验证不占 GPU。

## 实际验收证据

- 五教师最终 ONNX 共 **60 组真实 ORT CPU inference**，验证图结构、参考动作输出及 checkpoint/registry/iteration provenance，见 [教师汇总](teacher-onnx/summary.json)。这不声称 PT/ONNX 数值等价或策略质量。
- 两学生从原生 PT 独立导出双图，各 **30 组 checker/实际 ORT CPU inference**，见 [纯学生](student-onnx/export-student-pure-onnx-validation-0.json)、[混合学生](student-onnx/export-student-finetune-onnx-validation-0.json)。
- 全部 **13 个训练阶段**（含六 preset）的 `model_00000` → `model_00001` 政策张量均有限、实际网络权重有非零变化，原始差异报告位于 [独立验证](independent-validation/)。
- **13 个训练 run** 的 loss 与 reward 均包含有限 step 0、1；连同评估共有 **29 份原始 TensorBoard events**，所有 scalar 有限，见 [逐 tag/value 验证](independent-validation/tensorboard.json) 与 [原始 events](../../tensorboard/final-cloud/)。
- 下载后重新计算 **140 个产物**的 SHA（26 个 PT、五教师最终 ONNX、两学生独立双图、quality JSON/视频/events 等），与云端记录一致。完整约 743.1 MB 原始输出保存在本地 `outputs/research/final-cloud-acceptance/results/`，索引在 [完整汇总](summary.json)。

## 七次新版评估

四项跟踪误差均有 250 个有限样本，质量 JSON 保存 mean、p95、max、重置事件、实际 checkpoint SHA、配置 SHA、视频 SHA 与 TensorBoard 路径。以下为 mean；关节误差是 joint-vector L2。两轮策略频繁失败重置，因此这些数值和视频仅作为执行证据。

| 评估 | 失败重置 | 参考位置 m | 参考旋转 rad | 身体位置 m | 关节 L2 rad |
| --- | ---: | ---: | ---: | ---: | ---: |
| student-finetune | 15 | 0.1774 | 0.4809 | 0.1316 | 1.6108 |
| student-pure | 16 | 0.1885 | 0.4853 | 0.1384 | 1.5777 |
| teacher-high-climb-76 | 9 | 0.1615 | 0.4587 | 0.1143 | 1.0123 |
| teacher-high-step | 8 | 0.1763 | 0.7401 | 0.1418 | 1.2293 |
| teacher-locomotion | 9 | 0.1639 | 0.5595 | 0.1277 | 1.0543 |
| teacher-low-climb-76 | 9 | 0.1899 | 0.4684 | 0.1269 | 1.1854 |
| teacher-low-step | 9 | 0.1828 | 0.5866 | 0.1395 | 1.2292 |

七份原始 [quality JSON](quality/) 均关联本次新生成、ffprobe 可读的 MP4 和评估 TensorBoard。每类挑选本次最长已记录 episode，见 [视频及原始路径/SHA 索引](media.json)；它们仍是未收敛策略的短 episode，不表示课程完成。

本地已有 TensorBoard 的根 logdir 为 `/workspace/php_parkour/usage_assets/tensorboard`，打开 `http://127.0.0.1:6006/` 即可筛选 `final-cloud/` runs。仅在该端口没有已有服务时，才运行下面的独立启动命令：

```bash
docker exec php-parkour-research train-python -m tensorboard.main \
  --logdir /workspace/php_parkour/usage_assets/tensorboard/final-cloud \
  --host 127.0.0.1 --port 6006 --load_fast false
```

浏览器打开 `http://127.0.0.1:6006/`。训练使用 `Loss/*` 与 `Train/mean_reward`；评估使用 `Evaluation/tracking_error/*`、`Evaluation/failed_resets`。整个过程无需服务器联网。

## 独立记录工具的修正

主 pipeline 真实退出码始终是 0。首次独立 driver 已成功比较 13 个训练阶段权重，但它错误地断言只有 7 个，造成工具自身的计数失败；[原始失败状态](driver-initial-status.json) 与 [初版工具](tools/driver.py) 均保留。随后 [独立 finalizer](tools/finalize.py) 根据现有产物核对 13 个权重/TB run，完成后验检查，没有重复训练、评估或 ONNX 推理，也没有修改冻结源码；[最终状态](driver-final-status.json) 通过。启动命令/环境、工具 SHA 和修正来源见 [launch](launch.json)、[finalizer metadata](tools/finalizer-tool.json)。

[全部精选证据的 bytes/SHA manifest](evidence-manifest.json) 保留结果校验信息。
