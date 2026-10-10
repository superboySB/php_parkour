# 训练完成后的逐源片段覆盖：CPU 验证记录

独立 `posttrain_coverage.py` 已实现并冻结，尚未部署；本报告没有启动 GPU、修改云端或恢复训练。正式训练使用的 `0093aa40…` 只读源码绑定保持原样。未来后置任务必须使用另一个经哈希验证的新源码快照。

最终生产文件 SHA256：`00b7ad8d215f04d603ae696cafa613d15cd1287066a1387ddde376ba7203dff0`；测试文件：`91150cb9dbb81126df446fbe004c8531a3ff16e11ab582afd2f0a86e8fc383a7`。原字节位于 [harness-sources](harness-sources/)。

- Docker CPU 验证 109/109：61 项后置门卫/调度/恢复测试，48 项已有源片段覆盖工具测试。Root 和 runtime 各对最终版本独立复跑 61/61。独立执行的数量不相加。
- 实际七份烟测 PT 在 CPU 上读取，两个学生分别与有序五教师逐张量核对 55 项：每教师 8 个 actor 张量与 3 个观测归一化缓冲，全部 bitwise 相等。PPO 的 `std` 是采样分布参数，不属于冻结教师均值网络。CUDA 未初始化。这证明实际保存格式兼容，不能替代七份正式最终 PT 的核验。
- 独立只读审计无未决阻塞；三个已有 teacher/pure/finetune 实测 native 报告通过宿主内存路径翻译后仍可严格校验，原对象和文件 SHA 未变。这是既有报告校验，未运行新的物理尝试。
- 最终文件对运行中官方 manifest 的原字节副本执行 stdlib `dry-run`：返回 `waiting`，16 项未完成阻塞，文件 SHA 集合未变、没有创建覆盖输出或启动容器。此处没有重新查询云端。
- 早一候选新增回归漏掉 Docker-inspection 测试替身，在故意不包含 Docker CLI 的容器内出现 1 项失败。生产 SHA 没变；修正测试替身后全部通过。原失败 XML、stdout/stderr、启动记录均保留于 evidence，未安装 Docker CLI。

## 触发门卫

只有全部 16 阶段通过、对应文件及质量/ONNX 报告 SHA 完整、原 driver 进程消失、原日志末行结束 marker 存在、原官方锁可获，才进入 CPU 准备。检查训练容器镜像、旧源码内容和真实输出挂载，避免读到另一套旧结果。原 detached shell 未持久化最终退出码，因此记录 `driver_exit_status: null`；结束 marker、进程、锁和产物核验是分别观察的事实。

五教师要求最终迭代 19999、4096 环境、64 地形变体；pure 学生 9999、finetune 学生 29999，均为 2048 环境、3 变体。实际 PT 的 embedded config、seed42、每 rollout 24 步、save500、教师 mini4/epoch5、学生 mini96/epoch2，以及学生有序五个最终教师路径/SHA、完整冻结 actor/normalizer 参数都会核验。七份官方质量报告须对应最终 PT、64×3000 控制步、每项指标 192000 个 finite 样本，并保留新视频、TensorBoard 与所有文件指纹。教师最终原生 ONNX、两个学生导出及真实 CPU 推理报告也须完整。

科学核验与 native saved-config 解析、预处理、MotionLoader 校验仅在已有镜像的无 GPU、断网 CPU 容器运行。随后为 teacher/pure/finetune 各生成全部 296 源片段的计划、执行完整 CPU preflight；没有筛选器。每源保留原始帧数、SHA、专家顺序与 singleton 的外部身份。

GPU 子容器仅在 CPU 全部通过、固定物理 UUID 无程序且空闲后启动。Docker 请求 UUID 与容器实际 `nvidia-smi`、Torch 单卡 UUID 均须一致。新源码与 official-full 为只读挂载，资产只读，覆盖输出独立可写；精确核对四个挂载、cwd、entrypoint、镜像、网络和容器身份。全局 monitor 锁与原官方锁防止重复启动和与原生 driver 并行。工具没有训练启动或恢复命令。

## 888 次尝试及恢复边界

296 个公开源片段按 100/56/60/40/40 专家顺序，分别用于对应教师、pure、finetune，共 888 次首次尝试。seed42、每源一个变体、完整原文件不裁切，上限为原始帧数，遇实际 failed、timeout 或原生 reference boundary 即停止。初始化 warmup A 与尝试 warmup B 分开；正常首个 policy target 为 frame1，末帧是边界 sentinel，不能称首末每帧都由策略作用。eval-only 相对身体缓存修复保留源码与 before/after，既不改时钟也不放宽 termination。

技能失败可为执行通过，原样保留质量 JSON、实际 config、轨迹、视频与 TensorBoard。最终 summary 始终 `quality_verified: false`，不能据一次边界到达宣称所有技能可靠。运行中的任务会被同身份 watch 接管；已完成及失败尝试均不重跑。进程中断留下的 started/log/部分视频是不可重复首次尝试证据，保留并标执行失败，再继续未尝试部分。GPU 容器异常退出后需明确 `--resume-interrupted` 才能继续；CPU 准备失败需人工审查后选择新覆盖目录，新的 host 输出路径会进入 cohort 身份并产生新容器名，旧目录与容器保留。

目前没有七份正式最终 PT，没有执行全量 CPU 888 预检、后置 GPU UUID 真实验收或 888 次物理尝试。CPU fixture 中的模拟控制平面文件不是仿真证据；真实烟测权重核对也不是正式训练收敛证明。原生训练恢复不保存完整 curriculum/RNG 状态，本工具不恢复训练。官方 ONNX 被删除或篡改会拒绝触发，不自动再导出；未声称 PT/ONNX 数值等价或学生 ONNX metadata 具有原生不存在的 PT iteration。

所有命令模板见 [watch-commands.md](watch-commands.md)。部署回执由 root 单独发布；本证据目录的文件 SHA 见 [evidence-manifest.json](evidence-manifest.json)。
