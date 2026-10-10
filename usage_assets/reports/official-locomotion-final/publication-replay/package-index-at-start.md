# 首个完整官方教师：locomotion

截至 2026-10-10 17:08 UTC，五个官方教师中已有 **1/5 完成**。locomotion 原生训练实际退出 0，完成 20,000 次迭代，最终 PT 的 `iter` 和 `iteration` 均为 19999；原 driver 随后自动进入 low-step 教师。其余四个教师、两种学生及完整训练链尚未完成。本页的 CPU 检查不证明收敛、物理 rollout 质量、越障成功或 PT/ONNX 数值一致性。

[原终态 observation](terminal-observation.json)、[云端实际控制与下一阶段记录](cloud-control/control.json)、[四件下载回执](transfer/receipt.json)均保留原始字节。训练使用云端旧冻结镜像 `631d9e53…`、源码树 `0093aa40…`；本地独立 CPU 验收使用统一镜像 `2be18521…`，没有替换正在运行的训练环境。

完整训练参数为 4096 环境、seed 42、64 个地形变体、20,000 迭代、24 steps/env、4 minibatches、5 epochs、save interval 500。终态耗时 45,112.345 秒（约 12.53 小时，含初始化与保存等），20,000 个 collection+learning 样本的中位数为 1.978 秒；不能把该核心时间当完整链日程。精确配置见 [原 YAML](artifacts/holosoma_config.yaml) 和 [CPU checkpoint 报告](cpu-02/validation/checkpoint.json)。

![真实 0–19999 迭代的训练曲线](cpu-02/validation/plots/learning-curves.png)

曲线来自完整原始 TensorBoard events。[四个 tag 的全部数值](cpu-02/validation/scalars.json)各包含 20,000 个有限样本，step 严格为 0–19999；图中保留原始曲线并叠加 trailing 25-sample 均值，详见 [绘图回执](cpu-02/validation/plots/plot-report.json)。曲线趋势不替代策略质量验收。

## 实际验收与保留的失败

- [第一次 CPU 验收](cpu-01/validation/phases.json)真实退出 1，原 stdout/stderr、源码及 Docker inspect 全部保留。它发现 YAML 的 `actor.output_dim=['robot_action_dim']` 与 PT 的 `[29]` 不相等，没有改写原 YAML 或 PT。
- [逐字段诊断](config-diagnostic/config-diff.json)只发现这一个符号解析差异。[原云端冻结源码](runtime-resolution-source/ppo_modules.py)的 `PPOActor._process_module_config` 第 40–43 行实际执行该解析；[来源回执](runtime-resolution-source/receipt.json)把原文件 SHA 绑定到云端冻结源树。第二次验收仅允许这一项明确替换，仍要求所有其它配置字段完全相同。
- [第二次 CPU 验收](cpu-02/host/execution.json)的 checkpoint、scalars、ONNX、bind、plots 五阶段均实际退出 0，容器最终退出 0、stopped，四件验收源码前后 SHA 不变。实际执行使用 runc、无网络、GPU hidden、2 CPU、12 GB 内存及只读输入挂载；memory peak 为 3,616,792,576 bytes。
- [PT 检查](cpu-02/validation/checkpoint.json)核实 actor 449→29、critic 575→1、68 个 checkpoint Tensor 全部有限，两 normalizer 均为 `None`；原 iteration-0 PT 到最终 PT 的 actor/critic 权重实际变化，所有保存的 AdamW step 从 20 增至 400000。
- [ONNX 检查](cpu-02/validation/onnx.json)实际执行 12 个 CPU ORT case，核实有限动作、参考索引及自包含图。[绑定报告](cpu-02/validation/bind.json)确认最终 PT、ONNX metadata、单项解析后的 YAML、完整 events 属于同一迭代和配置；它明确保留 `pt_onnx_numerical_parity_verified=false`、`skills_verified=false`。

## 原件与恢复

[path-map.json](path-map.json)记录每个原路径到本包副本的映射及 SHA；原 JSON 内部路径保持原样。[evidence-manifest.json](evidence-manifest.json)覆盖全部发布文件。最终 PT 和原 YAML 在 `artifacts/`；iteration-0 PT 在 `cpu-02/input/model_00000.pt`。第一次使用的 baseline 与该副本完全同 SHA，只存一份。

72,561,360-byte 原 TensorBoard event 无损压缩为 17,169,905 bytes，gzip `mtime=0`、不含原 filename，单文件小于 25 MB。发布时已实际流式解压全部内容，恢复 SHA 为 `503cd5a80058818ef3bdbe7f2634f3f109169eeb8c9c72f07c6ca84756bbe00a`，大小完全相同；详见 [event-archive.json](tensorboard/event-archive.json)。恢复合同支持按 offset 拼接分块，本轮压缩后只需一件。所有原始日志和验收报告均未压缩改写。

**1,183,810,764-byte 最终 ONNX 不进入 Git**。[external-onnx.json](external-onnx.json)保留本地与云端原路径、大小和 SHA `7255943ae7cdfae4a8371659865a0774709e6898c3d052ea6ceda5f89c9056c7`。若本地原件仍存在，可直接把它传给 replay；否则先显式下载到用户选定目录：

```bash
rsync -a --protect-args \
  -e 'ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no -o ControlMaster=auto -o ControlPersist=10m -o ControlPath=~/.ssh/php-parkour-%C' \
  tencent-231:/diff/dzp_is_sb/php-parkour-research/outputs/official-full/official/teacher-locomotion/PHP-research/20261010_042104-teacher-locomotion-locomotion/model_19999.onnx \
  /absolute/existing-download-directory/model_19999.onnx
```

从仓库根目录校验包；`restore` 恢复原 events 和四件最终输入，`run` 在全新输出目录恢复输入并调用与第二次验收完全相同的五阶段源码及原容器内部 argv：

```bash
python3 -B usage_assets/reports/official-locomotion-final/replay.py verify
python3 -B usage_assets/reports/official-locomotion-final/replay.py restore \
  --onnx /absolute/path/model_19999.onnx --output /absolute/fresh-restoration
python3 -B usage_assets/reports/official-locomotion-final/replay.py run \
  --onnx /absolute/path/model_19999.onnx --output /absolute/fresh-five-phase-replay
```

`restore` 与 `run` 各要求独立的新目录，不能使用同一个已存在目录。ONNX 必须先匹配精确大小和 SHA，随后才能创建任何 Docker 容器；需要本地已有上面的完整统一镜像。挂载仍为 `/code`、`/control`、`/artifacts` 只读以及新 `/validation` 可写。脚本只使用宿主 Python 标准库和现有 Docker，不安装包、不启动 Isaac/DDS/GPU、不下载模型、不重试失败，保留自己的 argv、真实 wait、inspect 和日志。此发布时 `replay.py` 仅完成静态语法检查，尚未执行新的五阶段；上文实际通过证据属于原 CPU02。
