# 官方长训练驱动最终审计

审计镜像 `sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f`，内置源码 commit `64ebc5f125958ac1a9ab4891858b80a2ece5dd57`；挂载源码的 pipeline SHA256 为 `5f85596f40b796b8626e05058d54824d93ba97e3788129e1763ba5c461284adb`。仅检查源码、读取真实 typed 配置、运行无 GPU 的 `--plan` 和 CPU 回归；没有在本审计启动训练或仿真 GPU 作业。[源码 SHA](source-fingerprints.json) 区分镜像内源码与后续挂载修复，原镜像的断网执行证据仍独立有效。

默认官方驱动按顺序完成五教师训练、最终教师 ONNX 检查、五教师质量评估、pure 学生训练/评估/独立导出、finetune 学生训练/评估/独立导出。五教师与数据顺序为 locomotion、low-step、high-step、low-climb-76、high-climb-76。正式任务使用全新 `/outputs/official-full`；驱动用 flock 防止同一输出目录并发。

| 阶段 | 环境数 | 迭代数 | 地形变体参数 | mini-batches | epochs | rollout steps | 保存间隔 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 每类 ref-noscale 教师 | 4096 | 20000 | 64 | 4 | 5 | 24 | 500 |
| pure DAgger 学生 | 2048 | 10000 | 3 | 96 | 2 | 24 | 500 |
| DAgger+PPO 学生 | 2048 | 30000 | 3 | 96 | 2 | 24 | 500 |

这些值来自实际导入的 [默认配置](defaults.json)，不是按 smoke 参数推断。两种学生 action_scale 均为 1、depth latent32；pure 隐层 [512,256,128]，finetune 为 [2048,1024,512,256,128]。无 height-scan 的其他教师 preset 默认60000轮，完整官方驱动选择的是有 height-scan 的 ref-noscale，不把60000改成20000。

学生 official 入口逐一要求本次选中的教师已成功保存 iter≥19999；完整驱动使用全部五个。它按上述顺序传递 teacher PT 与 file:// registry，避免专家和数据错配。generic `--skills` 允许显式子集；子集不能称全五专家复现。[8 个计划调用 / 16 个 pipeline 阶段](plan.json) 中尖括号 checkpoint 是计划占位符，不能直接当可执行路径。

## 已修复的恢复输入漏洞

镜像内64ebc5f源码在已达目标时，会先早退，尚未比较旧训练输入。挂载修复现在在恢复或早退之前比较**实际环境数、当前阶段 registry及顺序、FINETUNE、教师权重 SHA及顺序**；不一致明确拒绝。默认4096与显式4096等价，改变总目标20→20000合法。缺少可验证旧settings但已有PT的legacy记录拒绝恢复；没有保存过PT的未开始阶段仍可从0启动。

学生自己的 `--training.checkpoint` 是恢复状态，不属于教师来源；即使调用者遗留 `CHECKPOINT=selfPT` 环境变量，也不会被塞入有序teacher source。pure和finetune两种自身2→4恢复、目标延长、已达目标、配置变化拒绝、双教师换序拒绝均有回归。

[最终相关组45/45通过](resume-provenance.xml)，0失败、0错误，2.50秒。测试用真实torch PT验证bookkeeping，子进程为替身；不把它冒充GPU训练或ONNX数值验收，也不与先前重叠测试计数相加。

## 原生恢复语义和限制

官方核心load恢复0-based `iter`，learn执行 `range(current_iter,current_iter+N)`，末次保存最后索引。20轮pilot保存iter19；续到默认目标19999传入N=19981。恢复会重做已保存索引对应的一步，不是逐比特无缝继续。模型、优化器与迭代恢复；**WBT继承BaseTask的空environment checkpoint state，没有保存WBT curriculum、采样历史、RNG或完整模拟器状态**，不声称精确复现不中断的随机轨迹。

manifest原子写入，失败和未完成阶段不当成功使用；PT递归检查policy浮点/complex tensor有限值并核SHA。当前恢复输入比较绑定registry URI，尚未逐数据文件绑定字节；应保持已经独立checksum核验的资产不变，修改同一路径的数据时使用新输出目录。

## 训练后的质量和导出

官方eval为64环境×3000控制步，dt0.02时每环境60仿真秒；teacher重建1个变体，student3个变体。预reset记录failed与timeout、四个tracking error、observed clip/expert ID，并把本次视频、checkpoint/config SHA和TensorBoard关联到JSON。WBT没有按env/variant尺寸保存环境状态，因此4096→64环境和64→1变体不会因恢复此类状态造成shape冲突。该评估没有穷尽全部参考片段或全部64训练地形布局；以observed IDs判断实际覆盖。

quality验收要求step/env/source SHA一致、action/root有限、每指标恰好steps×env个有限样本、新的可读视频及TensorBoard events。skip前复核产物SHA和结构，删除/篡改后重跑。**有限值和文件完成不等于策略质量通过**；失败计数与误差目前没有自动质量阈值，学生前的教师评估也不阻断质量差但有限的教师。

教师最终ONNX需要与PT同名、metadata.iteration匹配、metadata.registry匹配，并执行12组真实CPU图/参考查表验收。事后删除或损坏教师图时驱动fail closed，已完成teacher PT不会自动重训重建该图；这项限制经root确认保留。正常native保存/导出失败会使训练阶段failed，之后可resume。不要用1variant eval导出冒充64variant训练原图。

学生独立export从PT恢复确切pure/finetune配置，推断五teacher slots，完整load后生成fresh backbone/student pair，检查29关节/默认姿态/缩放metadata及30组真实CPU推理；源PT SHA与两个ONNX SHA保存在manifest。它不要求另外读取远程teacher文件，不依赖W&B账户；实际file://注册表、TensorBoard和disabled online logger均在同一镜像环境。尚未把这些合同检查提升成PT/ONNX数值parity或物理技能质量证明。

[机器可读审计](audit.json)。除已修复的恢复输入漏洞外，未发现必然导致全新目录、完整默认配置在末尾失败的源码路径；实际长任务仍以各阶段退出码、manifest、质量报告和原始日志为准。本审计不宣称140000累计训练迭代已执行或策略已收敛。
