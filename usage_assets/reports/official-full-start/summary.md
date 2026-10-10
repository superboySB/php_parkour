# 正式完整训练的启动证据

**状态：运行中，尚未完成，也未验证最终策略质量。** 北京时间 2026-10-10 12:20:56 启动单 GPU 官方日程。12:29:25 的实时 TensorBoard 记录首教师 step 0–114，所检查的 Value / Surrogate / Entropy loss 与 mean reward 均有限，见 [原始标量快照](initial-live-scalars.json)。这份报告只记录启动时点；最新进度需读取远端日志、manifest 和 TensorBoard。

使用最终统一镜像，Config/RootFS 指纹 `2a43037e2397fac3e343e8d621dd42c41ea7c27da82602789d575fddda112482`；挂载冻结源码 git `3439cb7`、树 SHA `0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab`。实际镜像、driver/pipeline SHA、资产清单 SHA 和日程见 [启动记录](launch.json)。此前已用相同镜像和源码完成 [最终 22 项 smoke](../training-cloud-final/summary.md)。

启动前物理 GPU 0 有其他作业；GPU 1 为最低编号空闲卡，2 MiB、0% 利用率、无计算或图形进程。按照 UUID `GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5` 仅向容器暴露这一张卡，见 [全卡检查](gpu-before-start.json)。主机与云端均未安装项目依赖；训练、TensorBoard 和评估解释器都位于 Docker。

首教师实际保存配置核对：4096 环境、64 variants、seed 42、obstacle_seed 42、20000 总迭代、24 steps/env、4 minibatches、5 epochs、每 500 轮保存。见 [配置核验及 SHA](actual-initial-configuration.json)、[初始阶段 manifest](teacher-locomotion-start.json)、[进程命令](processes.txt)和[日志快照](current-progress.log)。

后续自动依次运行其余四教师，每教师 20000 轮；校验五教师最终 ONNX、执行每教师 64 环境 × 3000 步质量评估；再运行 2048 环境的纯 DAgger 10000 轮和 DAgger+PPO 30000 轮，各自评估及独立导出。沿用原生训练配置，不以 smoke 产物替代完整教师。阶段失败时 driver 停止；相同输出目录重新执行 driver 会按已校验 checkpoint 恢复。

```bash
python3 scripts/research/cloud.py exec tail -n 50 /outputs/official-full-driver.log
python3 scripts/research/cloud.py exec cat /outputs/official-full/official/manifests/teacher-locomotion.json
```

远端持久输出目录为 `/diff/dzp_is_sb/php-parkour-research/outputs/official-full`。官方 locomotion 容量 pilot 测得单教师 20000 轮核心计算约 12.89 小时，不含初始化、保存和评估；完整七模型日程预计需多天，不能据此保证其他模型耗时。训练结束后还需回传模型、检查长 rollout 和本地部署质量，才可更新验收结论。

离线 TensorBoard 已监听云端 `127.0.0.1:6006`，logdir `/outputs/official-full`。本机已建立密钥 SSH 转发，打开 `http://127.0.0.1:6007/` 即可查看，无需在线账号。云端和本地转发均实测 HTTP 200，见 [云端 HTTP](tensorboard-http.json)与[本机 HTTP](local-tensorboard-http.json)。已有服务无需重复启动；转发断开后只需重新运行：

```bash
ssh -p 22 -N -L 127.0.0.1:6007:127.0.0.1:6006 tencent-231
```

[初始精选证据清单](evidence-manifest.json)记录原始文件 bytes 与 SHA；训练中的源快照保持不变，之后的文档同步会创建独立快照。
