# 云端训练与 TensorBoard 验收

同一份统一镜像在云端物理 GPU 1（RTX PRO 5000，72 GB）运行，UUID 为 `GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5`；容器内仅有该卡，编号为 0。首次镜像在两端的 manifest ID 表现不同，实际 `Config`/`RootFS` 内容指纹一致，见 [镜像传输记录](runtime-cloud-image-transfer.json)。所有训练使用本地 `file://` 数据与 checkpoint，LOGGER 的底层配置为 `disabled`，TensorBoard SummaryWriter 仍开启；这些运行没有启用 W&B logger。

## 22 项完整 smoke

| 项目 | 实际配置 | 结果 |
| --- | --- | --- |
| 五类教师：locomotion / low-step / high-step / low-climb-76 / high-climb-76 | 各 64 environments、2 iterations、seed 42 | 5/5 通过，保存原生 checkpoint |
| 六种教师 preset：ref / no-heightscan 及两者的 noscale、pelvis 变体 | locomotion，64 environments、2 iterations | 6/6 通过 |
| 五类教师 checkpoint 评估 | 各 1 environment、250 steps，原生渲染 | 5/5 通过，均有本次新生成且可读的 MP4 |
| 纯 DAgger 与 DAgger+PPO 学生 | 五个教师与五个 registry 按顺序配对，各 64 environments、2 iterations | 2/2 通过 |
| 两类学生 checkpoint 评估 | 各 1 environment、250 steps | 2/2 通过，均有本次新生成且可读的 MP4 |
| 两类学生独立 ONNX 导出 | 从原生 PT 恢复，重新创建环境和双 ONNX 图 | 2/2 通过，分别通过 30 组 checker/真实 CPU 推理 |

整体 driver 返回 0，耗时 683.109 秒。完整约 706 MB 产物保存在本地 `outputs/research/cloud/results/training-acceptance/`；下载后的 13 个 checkpoint 与 4 个导出模型均重新计算 SHA-256，与运行记录一致。[完整汇总](training-cloud-acceptance.json) 与 [各阶段原始 manifest、权重差异及 ONNX 报告](training-cloud/) 可供审查。

独立 CPU 验证比较五类教师、两类学生的 `model_00000.pt` 和 `model_00001.pt`：政策浮点张量均为有限值，策略网络权重确有非零变化。验证工具以 SHA 命名放在 `/outputs/tools/`，没有修改冻结的云端源码。[工具来源](training-cloud-weight-verifier-tool.json) 和 [源码复核](training-cloud-source-verified.json) 记录了该事实；训练后原快照内 1537 个 manifest 文件逐项哈希/权限复核全部一致。

GPU 显存以每秒一次的 nvidia-smi 样本作尽力记录，从教师评估阶段开始观察到的峰值为 6554 MiB，未测量更早教师/preset 的峰值，见 [采样报告](training-cloud-gpu-peak.json)。[64 环境教师逐迭代耗时](training-cloud-teacher-performance.json) 仅用于 smoke 诊断，不用于外推 4096 环境的正式训练。

这些结果验证真实训练更新、加载、物理步进、渲染、蒸馏和导出路径，不代表机器人已经学会障碍技能。两轮策略频繁提前终止；[七类实际评估短视频与截图索引](training-cloud-media.json) 选择了各阶段最长的已记录 episode，仍只能作为执行证据。

## 正式 4096 环境的 20 轮 pilot

完成 smoke 后，仅运行以下额外 pilot，未自动续到 20000 轮：

```bash
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh \
  teachers --profile official --skills locomotion --iterations 20 \
  --output /outputs/official-training
```

未覆盖 num-envs 或预处理参数，实际使用 4096 environments 与完整默认预处理。20 轮成功完成，最后 checkpoint 的 iteration 为 19，driver 总耗时 194.766 秒。每秒显存采样峰值 20479 MiB。去掉前两轮，18 个核心迭代耗时的中位数为 2.321 秒，范围 2.231–2.468 秒。

同一 locomotion 配置的 20000 轮 collection+learning 核心时间据此估计约 12.89 小时；该数值不包含启动、预处理、checkpoint 序列化、评估，也不估计其他教师或学生。完整实测样本、checkpoint SHA 与范围限制见 [pilot 报告](training-cloud-official-pilot.json)。这次运行是 20 轮覆盖的性能 pilot，尚未完成正式训练日程。

## 离线 TensorBoard

13 个 smoke 训练阶段的原始 events 总计 91,938 字节：全部 scalar 有限，loss 与 `Train/mean_reward` 均含真实 step 0、1。[13 阶段验证报告](training-cloud-tensorboard.json) 保留各 run、tag、值及原文件 SHA。另保存了 71,324 字节的 pilot events，其中 loss、reward、训练耗时均含完整 step 0–19，见 [pilot events 验证](training-cloud-pilot-tensorboard.json)。所有原始文件位于 [TensorBoard 数据目录](../tensorboard/)，无需服务器联网。

在统一本地容器中查看这些已入库的原始曲线：

```bash
docker exec php-parkour-research train-python -m tensorboard.main \
  --logdir /workspace/php_parkour/usage_assets/tensorboard \
  --host 127.0.0.1 --port 6006 --load_fast false
```

打开 `http://127.0.0.1:6006/`。教师查看 `Loss/Value`，纯 DAgger 查看 `Loss/behavior`，DAgger+PPO 查看 `Loss/total_loss`；奖励使用 `Train/mean_reward`。`smoke/` 的 13 个 run 只有两轮，`pilot/teacher-locomotion` 有 20 轮。HTTP 数据端已核对真实曲线值，[HTTP 验证记录](training-cloud-tensorboard-http.json) 对应最初 13 个 run；监听检查确认服务仅绑定 127.0.0.1。[真实 Chrome 浏览器验收](tensorboard-browser.json) 另验证 8 条实际曲线、UI 筛选和 canvas 渲染；[20 步教师截图](../tensorboard-pilot.png) 与 [两学生截图](../tensorboard-students.png) 使用 Smoothing=0，完整显示已记录端点。

教师自动 ONNX 的完整动作库占用、官方每 500 轮产物周期、五类教师约 124 GB 的容量估算，以及最终 pilot ONNX 的 12 组实际 CPU 验收，见 [教师产物与最终导出](training-cloud-teacher-artifacts.md)。

另在初始镜像执行了两个学生的原生 2048 环境、3 variants、20 轮容量/性能 pilot；使用未收敛专家，不代表正式训练，见 [学生容量与性能](training-cloud-student-capacity.md)。
