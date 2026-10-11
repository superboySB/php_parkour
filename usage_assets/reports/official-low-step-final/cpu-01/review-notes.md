# Low-step 最终产物 CPU 验收准备（尚未执行）

本目录仅完成实际产物传回后的源码复制、教师专用合同适配、输入接线和标准库 AST 语法检查。没有创建 CPU 容器，没有导入 Torch、ONNX、TensorBoard 或 Matplotlib，没有启动训练、物理评估或 GPU 作业。官方 high-step 训练与现有 waiter 不变。

## 已实际完成的传输

来源为同一已完成的原生 low-step run：

`/diff/dzp_is_sb/php-parkour-research/outputs/official-full/official/teacher-low-step/PHP-research/20261010_165257-teacher-low-step-locomotion/`

末尾 `-locomotion` 是真实原生目录名，不代表改接首教师。五件产物共 522,202,692 bytes；`../teacher-low-step-final-01/receipt.json` 记录 SSH inventory-before、rsync、SSH inventory-after 三次实际 wait0 及各自原始 stdout/stderr。所有产物远端前后 stat/SHA 与本地 bytes/SHA 相同。passed manifest 和 PPO 配置解析源码从同次只读观察返回，小文件也保留原始字节。

| 文件 | Bytes | SHA256 |
|---|---:|---|
| model_19999.pt | 10345023 | ff6912286a5b2a4d8d048dca5471b53935baecca4d06c3407af7201ef09153e6 |
| model_19999.onnx | 428920342 | bb3d4fd4657233a7ede2a14005ee7336efa82954d115112cecc5d7cec1f5cd69 |
| holosoma_config.yaml | 30944 | d9ee3170421d7561cb9e52ebd06850e396fb7dbbe5385a1e73c2d0d610053bfd |
| events.out.tfevents.1791651217.pro5000-6.71862.0 | 72561360 | 85ed6bec3d6737dc8705c6191bd9e11da5908eb35e803345d2cc590f7b436203 |
| model_00000.pt | 10345023 | 0eeeecfc7c7bc71ef8ee6b1a6a5cd1ffe61362598c2af38e146b5926df05f8dc |

`model_00000.pt` 是保存的 iteration0 状态，可能已经完成第一轮优化；它不是“未训练随机初始化”。计划比较的是 iteration0→19999。

两次只读观察均核实原 CID、image631、StartedAt、boot、source0093挂载，以及原 driver3836907/700458612、monitor4074213/702550493、high-step wrapper471066/709429584、Kit471154/709429651 的出生身份。完整 raw inspect 和 `/proc` 双读记录在传输目录的两个 inventory stdout 中。

## 适配与尚未执行的检查

`source-original/` 保留首教师 CPU02 原始五份脚本；`diffs/` 保存各份完整 unified diff，包括两份零差异文件。`source/run_cpu_phases.py` 和 `source/validate_teacher_onnx.py` 与首教师副本逐字节相同。

`accept_teacher.py` 仅换入实际 low-step 的五件 SHA、事件名、教师/registry/报告名称，并加强 baseline SHA 与同 run 全部 `experiment_config` 一致性检查。实际 YAML 文本显示4096环境、seed42、64 variants、add_onpath_obstacle=true、obstacle_seed42、noscale action_scale1.0，与沿用的检查合同一致；PT449/575维度与这些配置的数值核验仍须未来 CPU 实测，当前未声称通过。

YAML 的 `robot_action_dim`→PT29 仅允许原 CPU02 已由原生源码证明的单字段解析；其他完整配置必须相等。若真实 low-step 发现任何其他差异，保留失败并先诊断，不放宽检查。

图脚本改为第二个 low-step 教师，仍保留全部真实四个 tag、20000点及25样本 trailing mean。原始负 entropy 不截断。最终 ONNX 是否 self-contained、真实参考帧数、12次 ORT 推理、全部 checkpoint Tensor/Adam finite、更新量和四个 TB tag 完整性均未在本轮运行。

## Root 审阅后唯一执行入口

在仓库根运行以下命令。它只创建命名独立的 runc、networknone、GPUhidden CPU 容器；三个输入目录只读，一个全新 validation 目录可写。固定镜像、挂载、环境与所有源码 SHA 在 `contract.json`；实际返回码/inspect/内存峰值将在新的 `host/` 与 `validation/` 中保存。

```bash
python3 -B outputs/research/official-full/teacher-low-step-final-cpu-01/run_cpu.py
```

当前 `host/` 与 `validation/` 均不存在。入口拒绝重用这些目录；失败保留原件，不自动重试。

预期五阶段为 checkpoint、scalars、ONNX、bind、plot。所有阶段实际通过后，也仅证明本教师保存产物和 CPU 接口有效；质量、收敛、PT/ONNX 数值等价、官方物理 eval、完整七模型训练完成仍为 false。
