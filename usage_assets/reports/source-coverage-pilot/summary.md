# 逐原始片段验收工具：真实 Isaac pilot 与缓存修复

本次只跑了三个片段尝试：正式训练的 teacher 第500轮，以及两种只训练1轮的 smoke student。三个子进程均正常结束，策略控制、首次事件捕获、日志、配置、TensorBoard和视频保存均工作；三个片段均未完成，`quality_verified=false`。没有声称完成296源×三策略的888次尝试或完整官方训练。

| 策略 | PT迭代编号 | 源帧数 | 实际策略步 | 策略仿真时间 | 首次停止 | 原始报告 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| teacher | 500 | 920 | 158 | 3.16 s | 跟踪失败，未到边界 | [teacher/quality.json](teacher/quality.json) |
| pure | 1 | 455 | 21 | 0.42 s | 跟踪失败，未到边界 | [pure/quality.json](pure/quality.json) |
| finetune | 1 | 455 | 21 | 0.42 s | 跟踪失败，未到边界 | [finetune/quality.json](finetune/quality.json) |

两种学生都使用完整的 low-step 源，保留原始 expert 1，独立 bundle 的 native expert为0。教师使用完整的 locomotion源。没有截短源、调整终止阈值、重写参考时间或使用辅助控制。参考frame0由原生零动作预热执行，策略帧分别连续为1..158、1..21、1..21；最后一帧是边界标记。四项跟踪误差、动作和机器人根状态的实际策略样本均有限。

## 数据校验与 CPU 检查

固定原始专家顺序为 locomotion 100、low-step 56、high-step 60、low-climb-76 40、high-climb-76 40，共296对、181236帧、3624.72参考秒，全部50FPS。数组shape、名称顺序、有限值、单位四元数、one-hot命令、地形配对及发布SHA均通过。原始296个NPZ都没有存储motion_idxs/motion_ends；原生合并为独立bundle补充本地expert0和最后一帧边界，外部provenance保留原expert。

[完整inventory](teacher/inventory.json)、[来源记录示例](pure/singleton/provenance.json)。[48项CPU回归JUnit](cpu-tests/source-coverage-harness-repaired-final-tests.xml)包含15项数据工具检查和33项原生评估控制流/来源/缓存检查；CPU的physics fixture不是真实物理验收。本报告的三个GPU运行与这些CPU检查分开记录。

## 发现并修复的初始化问题

未修复时三次真实GPU尝试都在第二次原生reset_all的零动作步失败，策略步数为0。[原始teacher报告](before-cache-repair/teacher/quality.json)、[pure](before-cache-repair/pure/quality.json)、[finetune](before-cache-repair/finetune/quality.json)和当时精确源码均保留。这不是策略技能表现：WBT.reset_all清零relative body target缓存，Isaac WBT下一步先做termination/reward/log，后刷新缓存；布局XY平移把这项初始化错误放大到teacher约2.58m、students约0.82m。

独立工具现在只在两次warmup的原始env.step之前，从固定版本MotionCommand.step的AST提取同一对齐公式，刷新当前帧的两个relative缓存。没有调用command.step，也没有推进/回写参考时间、重采样、改变RNG或终止条件。每次完整缓存before/after、时钟与RNG SHA均保存在[teacher缓存记录](teacher/warmup-cache-refresh.json)及各quality.json；原公式文件SHA/AST SHA亦有记录。[诊断说明](cache-diagnosis/warmup-relative-cache-review.md)给出实际原生类与真实参考数据的CPU推导和逐位parity。

相同PT、源、seed、地形变体数和上限重跑后，teacher预热body error约0.03174m，students约0.03398m，成功进入上表的策略控制阶段。常规阶段仍使用原生评估循环；首次真正跟踪失败仍停止。运行中的云训练和子模块源码没有改动。

此外，保留文件现在按原字节复制并设为0644，解决临时OBJ的0600权限被继承、宿主无法读取的问题。保留的实际native motion NPZ、terrain OBJ和保存配置均随各策略目录提交，可逐项SHA核对。

## 录像与复跑

[新九个视频完整CPU解码记录](video-full-decode.json)和[旧九个视频解码记录](before-cache-repair/video-full-decode.json)均通过；启动和warmup原片也在计数内，录像不等于纯策略控制时长。原视频与截图在[媒体目录](../../isaac/source-coverage-pilot/)。

![teacher片段中的实际Isaac帧](../../isaac/source-coverage-pilot/teacher-midpoint.png)

运行入口见[note.md](../../../note.md)，实际命令和原始参数见各策略的plan.json、case.json、host-launch.json。重新运行时使用新输出目录；旧结果不会被覆盖。去掉source过滤可以准备全部296源；教师需按原五个expert分别提供对应PT。一次只检查1个地形变体，这不覆盖官方训练全部64/3个变体。

[机读汇总](summary.json)、[全部文件bytes/SHA清单](evidence-manifest.json)。
