# 两类学生的原生容量与性能 pilot

在初始统一镜像的云端物理 GPU 1（RTX PRO 5000，72 GB）顺序运行两类学生。使用五个只训练两轮的 smoke 教师，按 locomotion、low-step、high-step、low-climb-76、high-climb-76 顺序与本地五组 `file://` registry 配对。这不是正式完整训练，也不证明技能质量或最终新镜像的容量。

学生默认预处理是 **3 个变体**，教师默认才是 64。实际保留学生原生 2048 environments、96 mini-batches、2 learning epochs、24 rollout steps、save interval 500；算法配置只把默认纯 DAgger 的 10000 轮和 DAgger+PPO 的 30000 轮覆盖为 20 轮。使用单个已核对的 GPU UUID，`NGPUS=1` 是单卡运行控制；无头、输出路径和 LOGGER 也仅控制运行记录。没有降低环境数、mini-batches 或模型大小，没有修改冻结源码。

| 学生 | Native 训练耗时 | 核心迭代中位数，去前两轮 | 显存峰值 | 完成步数 |
| --- | ---: | ---: | ---: | ---: |
| pure | 130.453 s | 3.4255 s | 11,399 MiB | 983,040 |
| finetune | 181.798 s | 3.9320 s | 9,063 MiB | 983,040 |

两阶段均到达原生 checkpoint iteration 19。每个阶段的 actor/student/backbone 权重均有限且确有非零更新，最终 ONNX 双图分别通过 30 组真实 CPU checker/inference，TensorBoard loss/reward 含 step 0–19 且全部 scalar 有限。显存按约一秒一次的查询尽力采样；核心迭代时间不包含初始化、预处理与 checkpoint/ONNX 写入。未收敛专家、未来 PPO gate 和实际 episode 分布可能影响性能，不能把本次数字作为已收敛专家的吞吐或完整日程耗时保证。

运行对应初始云端镜像 `sha256:707065aebca88043d1ca4742d3112e7f3cdcf5148b09eff4333f58e0d1e967b0`、冻结源码树 `cbdb6ef45a8b19a46ee968d1c6f57d7952de983b1980829ef6847b290a3ac6d9`。独立 driver 以 SHA 命名放在 `/outputs/tools`，没有改 source snapshot。显式 `LOGGER=disabled` 与 `WANDB_MODE=disabled` 保留本地 TensorBoard，所有数据/checkpoint 都是本地路径；另设置 HF 离线 guard。两个原生训练子进程均已结束，GPU 已交还后续最终部署。

[完整汇总](training-cloud-student-capacity.json) 记录逐阶段结果及下载后 10 个重要文件的 SHA 复核；全部约 164.5 MB 原始模型和日志保存在本地 `outputs/research/student-capacity-pilot/results/`。这里入库 [实际命令与默认对照计划](student-capacity-pilot/plan.json)、[启动前 GPU/五个专家校验](student-capacity-pilot/preflight.json)、[独立工具来源](student-capacity-pilot/tool-provenance.json)，以及 [每阶段原始配置、日志、采样、权重/ONNX/TensorBoard 验证](student-capacity-pilot/)。原始 events 已保存在 [capacity-pilot 数据目录](../tensorboard/capacity-pilot/)。
