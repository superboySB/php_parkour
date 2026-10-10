# 原生 resume 科学协议独立源码审查

审查结论：主要协议与当前源码一致；有 **1 项未来验收门卫需要收紧**，不需要修改原生学习算法。此次仅静态读取冻结计划、引用源码及已有 checkpoint schema JSON，未读取正在编写的 preparation controls，未运行任何入口、测试、Docker、SSH、原生仿真或 GPU，也未载入 PT。

[review.json](review.json) 逐项记录路径、SHA、行号。冻结 `report.json`、`summary.md`、`plan.json` 的 SHA 分别为 `f3532a2898bb0975a2911075776584cc6f84764b6c99f365a235ccfebf2cd6be`、`6e5add785250b916fe994a89a4f5eb6bc3f3f6d78220ad36e3e0959ab33db5f1`、`6d9e5495bdc253b93600db09f8638e78e0b4561e30f55f59ce48b25361ab92a9`；report 引用的 26 个文件大小及 SHA 全部匹配当前字节。

## 必要收紧

混合学生本次 `distillation_warmup_steps=0`，所有编号均走完整 loss 分支。`std` 属于第 3 组 AdamW 参数（`distillation_ppo.py:245`），通过 Normal/log_prob/entropy 仍在计算图中（`student_teacher_modules.py:278`，`distillation_ppo.py:623`），乘以零系数不会删除计算图，随后每个 minibatch 都调用 optimizer.step（`:596`、`:689`）。因此本协议的 std state 应要求 **16 → 24 → 40**、组 LR 为 0、有限 std 权重保持不变。原报告的 “when present / 若缺少仅报告” 不能据以宣称该组连续性已验证。若真实 CPU PT 不符合，应失败或明确缩小已验证范围并保留差异。纯学生 std、冻结教师参数则确实不属于 optimizer。

已将这一点发给 root/validation，等待其实际 CPU PT schema 与后续控制面门卫核验；本审查没有读取新控制器，所以不判定其是否已落实。

## 确认事项

- `train_pipeline.py:484` 将 iter1、target4 转为 remaining3；三个 native learn 从当前编号开始，所以实际编号为 1、2、3，结束 iter3。跨两进程共 5 次 learner iteration，最后重复 save 不增加梯度更新。
- 同一 generator 每 epoch 4 个 minibatch（`data_utils.py:105`）；教师 5 epochs、学生 2 epochs。因此教师 actor/critic 每适用参数 step 为 **40 → 60 → 100**，学生 student/depth（混合另含 critic/std）为 **16 → 24 → 40**。两个学生 storage 继承该 generator，没有覆盖。
- 混合 critic 的 value loss 没有乘 PPO gate（`distillation_ppo.py:691`）。真实系数公式为 `min(it / 10000, 0.9)`（`:369`），恢复编号 1/2/3 对应 0.0001/0.0002/0.0003；std LR 为 0，早期 adaptive KL 分支不运行。
- 两学生 load 对 optimizer 异常仅 warning 后继续（`distillation.py:414`、`distillation_ppo.py:881`）。原生退出 0、iter3 或权重变化均不够；逐参数完整 state/key/group/step 门卫能够拒绝新的 optimizer 只得到 final24（教师 final60）。
- PT 的 `experiment_config` 是顶层字典，同时有 `iteration` 和 legacy `iter`，二者应相等（`base_algo.py:63`）；学生 `num_teachers`、`teacher_loaded` 是 PT 顶层字段，不能要求它们必然出现在 YAML。既有真实 smoke schema JSON 与 save 源码吻合。
- 教师 2→4 完成后固定 iter3 teacher SHA，再运行两学生各自 baseline/resume，顺序正确。原生完整 load 之后仅重新载入 frozen teachers（`train_agent.py:382`）；pipeline 自己的 resume PT 不进入 ordered teacher provenance。
- 本地 PT load 返回原路径（`eval_utils.py:288`）；新日志目录只有秒级 UTC 时间戳（`experiment_paths.py:14`），native 的 `mkdir(exist_ok=True)` 不保护碰撞。因此 baseline 原字节归档、原 PT SHA 前后不变、不同 run parent 及碰撞拒绝都必须由新控制面落实。
- HSSIM adapter 仅增加 public asset-root flag 的方案可行。launcher 在 activation 之前构建 TRAIN_COMMAND，后续 activation 重设 HSSIM 环境变量不会重写数组；不需要 patch learn/load/save。真实 CPU parse/35 文件资产合同及 source/control/image SHA 仍是未执行的前提。
- TensorBoard 的 global_step 就是原生 it（`logging_utils.py:339`）；baseline0/1、独立恢复 run1/2/3 应分别保留。Loss 与 Train/num_samples 可要求有限；reward/episode 标签受 episode buffer 是否非空影响，不应仅因缺少它们判 resume 失败。
- 教师现有 12-case 验证器绑定 PT/graph SHA、metadata iteration 和 registry；smoke 阈值只是 >=1，外层还须要求 exact3。学生 autosave 在 PT 完成后导出 pair，失败仅 warning（`student_teacher.py:121`）；必须绑定新 `model_00003`、PT3/native log/两 graph SHA 和各 30 ORT cases，不能借旧 iter1 或虚构 iteration metadata。现有 ORT 工具不证明 PT 数值 parity 或技能质量。

BaseTask 的 environment checkpoint 为空（`:217`），新进程重新 seed、reset；RNG、物理状态、采样/课程/gate/rollout 历史并未完整恢复。此短协议只能证明原生 model/optimizer/index 的继续训练，不证明不中断训练的逐位等价、收敛、官方五专家或完整日程。
