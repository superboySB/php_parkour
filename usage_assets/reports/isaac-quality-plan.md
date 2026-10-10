# Isaac 质量评估入口与后续正式评估设置

独立 `scripts/research/eval_quality.py` / `.sh` 已实现并真实运行，pipeline 的 teacher / student 评估已改经该入口。它保留原生载入、环境、策略、动作与 reset 行为，没有编辑 native eval 模块或云端冻结源。退出 0 / 写出视频仍不足以证明跟踪质量。

当前最小实现捕获下表中的仿真时长、失败/超时、首次失败、episode 长度、观察到的顶层 loader/expert ID、边界完成事件数、四个主误差的 overall/按 expert 统计、有限性、视频 SHA / ffprobe，并写入报告旁的离线 TensorBoard `Evaluation/*`。原始源片段覆盖、`expert-lost fraction` 与完整逐事件序列属于后续扩展，当前 JSON 不宣称已实现这些建议项。

真实基线为 [16 env ×100 step 质量报告](isaac-local-quality.json)：2 秒仿真/env、32 env-seconds，49 次失败 reset、0 timeout，reference-position p95=0.44015 m、tracked-body-position p95=0.25293 m。每个误差有 1600 个有限样本，动作与 root state 均有限；所有视频都有本次 SHA、正时长，17 个 TensorBoard scalar tag 通过真实 EventAccumulator 读取。模型仅训练到 iter1，说明执行通路和质量记录生效，**不说明训练收敛**。100 条 locomotion 源动作被合并为一个 NPZ 后加载；报告的 `available_clip_count=1`、`observed_clip_ids=[0]` 是顶层 loader ID，不表示只加载了一条源动作，也不证明这些源动作被实际遍历。

[教师失败视频（0.70 秒原片）](../isaac/local-teacher-quality.mp4)；[预览](../isaac/local-teacher-quality.png)。第一次配置错误的两份日志保留在 `outputs/research/local-isaac/quality-100/run.log`（实例配置需要属性对象）与 `quality-100-v3/run.log`（Isaac root state 为 proxy，需要 `[:]` 取 tensor）；成功结果使用全新 `quality-100-v4` 目录。回归还覆盖 `reset_all()` 内部的额外 warmup step，确保 100 步没有被误算为 101 步。[23 项目标测试 JUnit](research-quality-training.xml)。

## 合并动作与覆盖字段

`combine_motions()` 将源 NPZ 串接，并用 `motion_ends` 保留各源片段边界；单文件 `MotionLoader.num_motions` 固定为 1，起点为 0、终点为整个合并缓冲长度。当前质量入口从 `motion_ids` 收集 `observed_clip_ids`，从顶层 `motion_end_idx` 数量得到 `available_clip_count`，所以这些字段不能作为源文件数量或源片段覆盖率。`motion_idxs` 标识有序 registry 对应的 expert，也不能替代源片段 ID。[真实 loader 检查与字段解释](official-pilot-quality/coverage-interpretation.json) 同时记录了本地旧基线与新的 teacher pilot；后者合并文件有 100 个源边界，顶层 ID 仍只有 0。

要测源片段覆盖，应在 reset 清除状态前保留每个环境的实际 reference `time_steps`，按本次预处理后 `motion_ends` 的区间定位片段，再关联源文件顺序、registry/expert 与地形变体映射。应分别统计被访问片段、访问帧范围、到达边界及失败/超时，不能把“载入全部文件”“观察到 expert”或一个边界事件数写成完整原片段覆盖。当前 JSON 没有保存足以完成该还原的逐步 reference 时间索引，因此尚未测量原始源片段覆盖。

## 可复用的原生入口

`eval_teacher.py::run_eval` 与 `eval_student.py::run_eval` 都先恢复 checkpoint 的配置、重建地形，再构建 algo；二者都将 `EvalCallbacksConfig.collect_active_callbacks()` 结果写进 `algo.config.eval_callbacks`，随后调用 `algo.evaluate_policy(...)`。PPO、pure Distillation、DistillationPPO 都有相同的 pre / post eval callback 生命周期。

独立 driver 在调用原生 `main()` 前，为本进程的 `collect_active_callbacks()` 追加一个 research callback，无需修改这两个模块。callback 在 `on_pre_evaluate_policy()` 安装 env 实例探针，在 `on_post_evaluate_policy()` 恢复探针、完成本次最后一段视频编码并原子写最终 JSON。该钩子位于 `close_simulation_app()` **之前**，可以避免 Isaac shutdown 提前退出导致结尾报告丢失。

## 采样位置决定结果是否可靠

普通 `on_post_eval_env_step` 收到的 robot state 可能已经 reset；`termination_manager.terminated` 与 `time_outs` 也会在 reset 中清零。直接在这个时刻读它们会漏掉失败，读末态还可能把“刚摔倒但已经重置到站立”的环境算成成功。

WBT 的 `env._update_log_dict()` 恰好在 termination / reward 之后、`reset_envs_idx()` **之前**执行。独立探针包装该实例方法，先执行原方法，再只读复制：

- `termination_manager.terminated`、`termination_manager.time_outs`、`episode_length_buf`；分别累积失败和超时，不把 timeout 当成功。
- `env.log_dict` 中的 `motion/error_*` 张量；原方法已经调用 `motion_command.update_metrics()`，不重复执行 termination 或改变 sampler。
- `motion_command.motion_ids` 与 `motion.motion_idxs[time_steps]`；当前保存观察到的顶层 motion ID 与 expert ID，供按 expert 分组统计。`time_steps` 用于定位 expert，但没有作为逐步 reference 索引持久化；合并缓冲内的源片段覆盖需另行记录并通过 `motion_ends` 还原。
- simulator root/body state 的有限性和实际高度；action 有限性在 post callback 从 `actor_state['actions']` 读取。

到达源片段边界不一定产生 episode termination：`MotionCommand.step()` 检查 `motion_ends`，以 `motion_end_reset` 标记重采样和 robot state 重置。当前 post callback 将该标记累计为 `clip_completions_excluding_failed_timeout_steps`，排除同一步的 failure/timeout。它是边界完成事件计数，没有保存每个事件的原始源片段身份；顶层 motion/expert ID 也不足以还原该身份。不能把它当作完整课程完成、独立源片段覆盖或未结束片段的成功；超时也不等于边界完成。

## 最小 JSON 指标

| 字段 | 原生来源 / 定义 |
| --- | --- |
| checkpoint SHA、iteration、seed、config/registry SHA、expert 顺序 | 输入与 exact saved config |
| physics/control dt、控制步数、每环境仿真秒、总 env-seconds、墙钟秒 | `env.sim_dt`、`env.dt`、实际 callback 计数；仿真秒=steps×dt |
| failed / timeout resets，首次失败时间，各环境存活时间 | pre-reset manager flags；分开记录同时触发 |
| 边界完成事件数、观察到的顶层 motion IDs / expert IDs | pre-reset IDs + post `motion_end_reset`；不等于源片段覆盖。原片段 ID、访问帧范围与 censored 状态需扩展采样 |
| reference position error mean/p95/max (m) | `motion/error_ref_pos` |
| reference rotation error mean/p95/max (rad) | `motion/error_ref_rot` |
| tracked-body position error mean/p95/max (m) | `motion/error_body_pos`，原生已对 tracked bodies 求均值 |
| joint position L2 error mean/p95/max (rad) | `motion/error_joint_pos` 是 29 维向量范数，不能误叫逐关节 RMSE |
| expert-lost fraction（学生） | `which_motion<0` 的原生阈值判定；阈值随 exact config 一并保存 |
| finite action/state、最大 action magnitude、最小 pelvis、视频 SHA / ffprobe | 真实张量与本次新 MP4 |

`motion/error_ref_lin_vel`、`error_ref_ang_vel`、`error_body_rot`、`error_joint_vel` 可同时保存，但前四项位置/姿态/关节误差足以组成最小评估集。所有主指标应有按 expert ID 分组统计，避免 locomotion 数量掩盖 climb / step 失败。长评估用在线均值/分位数汇总或有界 CPU 缓冲，禁止逐步打印海量日志。

native BadTracking 的本配置位置判据均为完整三维 L2 误差：reference anchor position 误差 >0.5m，或两 ankle roll / 两 wrist yaw 指定 body 中任一的 reference-relative position 误差 >0.5m；这些位置判据不是仅比较 z。只有姿态判据比较参考与机器人 projected gravity 的 z 分量差绝对值 >0.8，这不是四元数角度 0.8rad。[原生 BadTracking 实现](../../thirdparty/holosoma/src/holosoma/holosoma/managers/termination/terms/wbt.py#L80)。报告应记录实际 target 类型与阈值；不同 pelvis / no-heightscan 配方不能套用同一套虚构的成功阈值。直接报告原生失败率与跟踪误差，然后比较同一配置的 smoke baseline 与正式 checkpoint。

## 建议正式评估设置

每类 teacher 先 64 env ×3000 control steps（dt=0.02 时每环境 60 仿真秒），seed42；student 对五类有序 bundle 同样设置，分别评估 pure / PPO checkpoint。若显存或视频成本要求更小，可用 16 env 增加评估步数，保持总 env-seconds，并明确记录设置变化。

这只是起始窗口，**不能预先宣称覆盖全部 296 条源动作**。已确认的单 loader teacher 路径在每次 native eval reset 时将 phase 置 0，因而回到合并缓冲起点；顶层只有一个 motion ID 时，不能理解为在其中 100 条源动作间均匀随机选择。频繁失败会使评估反复访问开头，增加环境数或更换 seed 也不自动解决源片段覆盖。多 expert 学生另有 `PhpMotionCommand` 均衡抽帧分支，应按实际采样器和保存的 reference 索引解释，不能套用 teacher 的 phase-zero 结论，更不能假设源片段均匀采样。完整覆盖需要显式的源片段调度/逐片段评估及边界与时间索引证据，并清楚标注与原生评估的差异。250-step smoke 每环境只有 5 仿真秒，证明可执行，不证明完整技能或收敛。

基线与正式模型使用相同 registry 顺序、地形预处理 seed、环境数、采样/初态设置及仿真时长，输出并排的失败次数/1000 env-seconds、reference/body p95 error、边界完成事件数与已观察到的 expert IDs。源片段覆盖率只有在补齐上述边界映射和 reference 索引后才报告。只有完整日程、finite checkpoint、真实权重更新、长 rollout 与新视频共同成立后，才讨论训练质量；loss 下降尤其不能替代这些指标。

## 已确认的源码位置

- [teacher native eval](../../wbt_training/training_runs/eval_teacher.py)、[student native eval](../../wbt_training/training_runs/eval_student.py)：配置恢复和 callback 注入位置。
- [PPO eval loop](../../thirdparty/holosoma/src/holosoma/holosoma/agents/ppo/ppo.py)：`evaluate_policy` / callback 顺序。
- [BaseTask](../../thirdparty/holosoma/src/holosoma/holosoma/envs/base_task/base_task.py)：`_post_physics_step` 在 `_update_log_dict` 后才 reset。
- [WBT manager](../../thirdparty/holosoma/src/holosoma/holosoma/envs/wbt/wbt_manager.py)：`_update_log_dict` 在 reset 前生成原生跟踪指标。
- [MotionCommand](../../thirdparty/holosoma/src/holosoma/holosoma/managers/command/terms/wbt.py)：`update_metrics`、eval phase=0、`motion_end_reset`。
- [合并动作预处理](../../wbt_training/utils/multi_motion_helpers.py)：`combine_motions`、`motion_ends` 与按 registry 添加 expert `motion_idxs`。
- [PHP 学生采样器](../../wbt_training/config_values/motion_command.py)：`_sample_expert_balanced` / `reset`，多 expert 分支与单 loader teacher 评估的区别。
- [当前质量指标采样](../../scripts/research/eval_quality.py)：顶层 `motion_ids`、expert ID 与边界事件计数的实际保存范围。
- [TerminationManager](../../thirdparty/holosoma/src/holosoma/holosoma/managers/termination/manager.py)：failed/timeouts 聚合及 reset 清零。
- [原生 eval recording callback](../../thirdparty/holosoma/src/holosoma/holosoma/agents/callbacks/recording.py)：Isaac 真 root/body NPZ 录制，与部署 SDK 的 zero-root 录制格式不同。

不建议只解析 stdout 的 reward 平均值推测质量，也不建议关闭原生 termination 后以“不 reset”为成功标准。
