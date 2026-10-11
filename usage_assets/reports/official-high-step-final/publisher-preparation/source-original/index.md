# 第二个完整官方教师：low-step

low-step 原生官方训练已在 2026-10-11 05:16:04 UTC 自然完成20,000次迭代，最终 PT 的 `iter` 和 `iteration` 均为19999；原 driver 随后进入 high-step。此时已有 locomotion、low-step 两个教师完成训练保存，其余教师、两种学生及整条官方链仍未完成。本包记录 low-step 自身的产物与实际 CPU 验收，不证明物理 rollout 质量、收敛、越障成功或 PT/ONNX 数值一致性。

原云训练保持冻结 image631/source0093；本地验收使用现有 image2be，在独立 runc、无网络、GPU hidden 的 CPU 容器中执行，没有替换训练环境。原训练控制与产物来源见[只读 inventory 前检](transfer/inventory-before.stdout.raw)、[后检](transfer/inventory-after.stdout.raw)、[选择性传回回执](transfer/receipt.json)、[passed manifest](transfer/teacher-low-step.json)及[此前独立终态 PT 哈希观察](terminal-checkpoint-observation/stdout.raw)。

![low-step 实际完整训练曲线](cpu-01/validation/plots/learning-curves.png)

[四个 tag 的完整原始数值](cpu-01/validation/scalars.json)各有20,000个有限样本，step严格为0–19999，总计80,000点。图中保留原始数据，叠加25样本 trailing mean，负 entropy 原样显示；[SVG](cpu-01/validation/plots/learning-curves.svg)与[绘图回执](cpu-01/validation/plots/plot-report.json)绑定同一原始报告和绘图源码。

| Tag | step19999 实际值 |
|---|---:|
| Train/mean_reward | 43.75150680541992 |
| Loss/Value | 0.034325260668992996 |
| Loss/Surrogate | -0.0070761144161224365 |
| Loss/Entropy | -4.607186794281006 |

## 实际 CPU 检查

- [宿主执行回执](cpu-01/host/execution.json)与[五阶段回执](cpu-01/validation/phases.json)记录 checkpoint、scalars、ONNX、bind、plots 全部实际 wait0；命名独立的 CPU 容器自然 exit0、已停止、无 OOM，四份源码与全部输入前后 SHA 不变。限制为2 CPU/12 GB，实际 cgroup memory peak 为1,354,354,688 bytes（约1.261 GiB）。[独立只读后验](cpu-01/independent-postexecution-review.json)另核原始报告、来源与当前文件 SHA，没有重跑科学检查。
- [PT 报告](cpu-01/validation/checkpoint.json)确认 actor449→29、critic575→1、68个 checkpoint Tensor 全部有限，两个 normalizer 均为 `None`；4096环境、seed42、64 variants、24 steps/env、4 minibatches、5 epochs、save500及20,000迭代均属于实际 low-step 保存配置。原 YAML 在[这里](artifacts/holosoma_config.yaml)。
- 同一原生 run 的 iteration0 PT 到最终 PT，actor9个及 critic8个保存的 AdamW state 全部从20增至400000；actor9个、critic8个权重 Tensor 都有非零变化，最大绝对差分别为2.040323879569769和4.187479428015649。iteration0 已保存20步 Adam 更新，**不是未训练随机初始化**。baseline 的来源 SHA 与完整配置都绑定到该 low-step run。
- [ONNX 报告](cpu-01/validation/onnx.json)执行12个真实 CPU ORT case，检查有限确定性动作和参考查表。自包含图为428,920,342 bytes，输入 `obs[1,449]`、`time_step[1,1]`，动作输出 `[1,29]`。四个参考常量为 `[1643264,29]`、`[1643264,29]`、`[1643264,3]`、`[1643264,4]`，共427,248,640 bytes。参考总帧数及12次查表不等同于原56片段的物理覆盖或成功率。
- [绑定报告](cpu-01/validation/bind.json)确认 PT 与 ONNX metadata 完整配置精确一致。原 YAML 仅 `actor.output_dim=['robot_action_dim']` 与 PT `[29]` 不同；[原云端 PPO 源码](cpu-01/input/runtime-resolution-source.py)第40–43行明确执行此原地解析，只允许这一字段替换，其余完整配置必须相同。原始 YAML/PT 未被改写。

`quality_verified`、`convergence_verified`、`pt_onnx_numerical_parity_verified`、`official_schedule_complete` 均保持 false。本轮没有官方云端 eval、Isaac/DDS/MuJoCo rollout 或新的 GPU 作业。

## 原件与离线恢复

[path-map.json](path-map.json)记录原路径、公开副本路径、大小和 SHA；原 JSON 内的绝对路径保留不改写。[evidence-manifest.json](evidence-manifest.json)绑定全部发布文件。[原始准备清单](cpu-01/preparation-manifest.json)、[执行合同](cpu-01/contract.json)、源码及完整差异均保留；准备时“尚未执行”的说明是历史快照，实际结果以后续五阶段回执为准。

最终 PT 和原 YAML 在 `artifacts/`，同 run iteration0 PT 仅存于 `cpu-01/input/model_00000.pt`，原传回副本映射至同 SHA 正文。72,561,360-byte 原 TensorBoard event 采用 `mtime=0`、无 filename 的 gzip，必要时连续分块至每件≤25 MB；[event-archive.json](tensorboard/event-archive.json)记录压缩前后 SHA、大小、顺序和发布时完整流式解压核对。所有验收报告、stdout/stderr、inspect、SSH/rsync回执保留原字节。

**428,920,342-byte 最终 ONNX 不进入 Git**；[external-onnx.json](external-onnx.json)记录其原始路径、大小和 SHA `bb3d4fd4657233a7ede2a14005ee7336efa82954d115112cecc5d7cec1f5cd69`。新 checkout 如没有该原件，可显式下载到用户选择的现有目录：

```bash
rsync -a --protect-args \
  -e 'ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no' \
  tencent-231:/diff/dzp_is_sb/php-parkour-research/outputs/official-full/official/teacher-low-step/PHP-research/20261010_165257-teacher-low-step-locomotion/model_19999.onnx \
  /absolute/existing-download-directory/model_19999.onnx
```

从仓库根校验包，或在新空目录恢复原输入、重放完全相同的五个 CPU 阶段：

```bash
python3 -B usage_assets/reports/official-low-step-final/replay.py verify
python3 -B usage_assets/reports/official-low-step-final/replay.py restore \
  --onnx /absolute/path/model_19999.onnx --output /absolute/fresh-low-step-restoration
python3 -B usage_assets/reports/official-low-step-final/replay.py run \
  --onnx /absolute/path/model_19999.onnx --output /absolute/fresh-low-step-cpu-replay
```

restore 和 run 要求各自独立的新输出目录。replay 先核所有原件 SHA，再恢复事件与 baseline 的临时输入副本；run 只启动现有固定 image2be 的 runc/networknone/GPUhidden CPU 容器，输入只读、输出独立。宿主只使用标准库和已有 Docker，不安装包、不自动下载、不重试、不覆盖历史失败。这里仅提供入口；本包没有声称出版后的 replay 已实际执行。
