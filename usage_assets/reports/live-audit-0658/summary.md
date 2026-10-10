# 三个真实运行句柄的独立只读核验

本次核验结果为 `verified_wait`，没有发现运行或文件完整性异常。没有启动 GPU/DDS 作业、重启任何进程、安装包、替换 bind 或修改现有原始结果。科学读取均在已有 Docker 中以空 CUDA 可见设备执行。

云端实际观察为 2026-10-10 06:58:02–06:58:05 UTC。原生 teacher Python PID **3836987**、外层 shell PID **3836908** 均存活，命令保持 4096 环境、locomotion、20000 迭代。镜像 `631d9e…`、源码绑定 `0093aa40…` 未变。TensorBoard 的 Value/Surrogate/Entropy/mean_reward 各读取 **3873** 个样本（step0–3872），全部 finite；最新 mean_reward 为 24.9086。这仅证明持续训练进度，不能证明技能收敛。

后置 watch 的实际 `/proc/3940821` 命令与独立 `8d9ee8a4…` 快照一致，monitor 文件 SHA 为 `00b7ad8d…`。最新 poll 为 **06:57:54.814682 UTC**，观察时仅过去 7.4 秒；日志已有 19 次 waiting，状态为 16 个未完成阻塞、`gpu_started=false`。覆盖目录只有 monitor 锁及状态文件，没有准备好的 selection 或 GPU 任务。该状态与早先部署回执相比已持续更新。

本地在约 **06:56:21 UTC** 捕获一次原字节 matrix，再对同一快照完成 CPU 验证。实际 driver shell PID **18565** → Python PID **18570** 存活，同时观察到 native sim2sim 父进程、simulator 与 inference 子进程。镜像为 `88254ac0…`，源码为宿主工作区挂载；driver SHA `284e3eab…` 与原启动回执一致。固定 plan identity 为 `571dfb1e…`。

该快照中 **128 completed / 1 running / 500 planned**。128 个 completed 全部逐一通过原生 `verify_completed`：case 身份、launch、parent log、case-evidence、全部留存文件 SHA、独立 result 与 embedded result 一致、finite 轨迹、500 policy ticks、10 秒仿真及原视频/缩略图证据检查。340 个源码/机器人依赖与 1887 个 motion/terrain 输入条目未变化；加 source matrix 和两模型共 2230 个唯一文件逐 SHA 与 size 核验通过。新 publisher 不属于这条运行依赖闭包。

真实阶段统计：random_locomotion 的 100 个全部已执行，其中 88 个未触发阈值、12 个触发；low_speed_step 已执行 28 个，其中 20 个未触发、8 个触发。共 **108 个 heuristic survival、20 个阈值事件**（14 个低骨盆事件，20 个倾斜/fall 事件，存在重叠）。这些是原始完整录像对应的启发式高度/倾斜指标，使用固定前进指令；不证明参考动作复现或障碍通关，也不代表全 629 项已通过。

两个审计自身边界如实保留：SSH 用户不能读取 root native 进程的 cwd symlink，仍以实际 `/proc` cmdline/status/stat 和 Docker top 确认身份，未提权；最初审计 helper 把 source 的 `size` 与 fingerprint 的 `bytes` 字段名直接比较，尽管 SHA/大小相同却报不同，修正只读比较后全部核验通过，旧诊断保留。运行中 matrix 顶层 derived count=2/finished_unix 是此前两例 pilot 的残留；driver 在整轮结束时才刷新这些字段，当前进度必须数 `selections`，不视其为新任务已结束。

详见 [summary.json](summary.json)、[remote-report.json](remote-report.json)、[local-report.json](local-report.json)、[quality-stage.json](quality-stage.json)。全部核验针对捕获时点，后续任务继续运行。官方全程、后置 888 次尝试与新正式学生 ONNX 的 MuJoCo 闭环均未由本次审计完成。
