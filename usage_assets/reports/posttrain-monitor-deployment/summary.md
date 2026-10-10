# 后置验收等待进程：实际云端部署

北京时间2026-10-10 **14:39:54** 已启动，host PID **3940821**。独立复查实际 `/proc` 参数，状态从 `2026-10-10T06:39:54.224775+00:00` 更新到 `2026-10-10T06:40:54.251774+00:00`，间隔60秒；目前为 **waiting**，16个正式阶段尚未完成。没有启动后置GPU作业，没有执行888次尝试。

- [冻结source manifest](frozen-source-manifest.json)：2452文件，Git `afb196b`，源码树 `8d9ee8a4dea5cccb8bac5664fb779fe8f5a102d6fd38104649ab28bd33010772`。远端逐文件内容/mode和镜像Config/RootFS内容指纹独立检查通过；monitor源码SHA `00b7ad8d215f04d603ae696cafa613d15cd1287066a1387ddde376ba7203dff0`。实际同步日志见[source-sync.log](source-sync.log)。
- [实际远端只读检查](audit-stdout.json)与[退出回执](audit-exit.json)：dry-run退出0、waiting，未创建coverage目录，也未新增Docker。原训练进程仍存活，源码挂载仍为`0093aa40…`。该原挂载为可写，本次没有修改或替换。
- [后台启动](launch-stdout.json)与[退出回执](launch-exit.json)：启动两秒后实际进程存活、首个monitor-status为waiting。它不是整个官方driver或888次尝试的最终退出码。
- [持续轮询及真实进程参数](status-stdout.json)与[退出回执](status-exit.json)：SSH已退出后，进程仍存活且再次更新时间；coverage目录只有monitor锁/状态文件，Docker容器集合不变。全局monitor锁还在独立输出父目录。
- [离线TensorBoard进度](training-progress.json)：14:38观测首教师到step3362，所检查Value/Surrogate/Entropy/reward从step0起全部有限，PT保存到iteration3000。它仍是第一教师，不是七模型完成或收敛证明。

[精确部署操作脚本](operator-deploy.py)及各phase的`*-remote.py`、stdout/stderr/exit保留原字节。宿主使用现有SSH、Docker和Python标准库；没有安装包或Conda。后续科学核验与仿真仅在同一镜像的新离线容器执行。CPU门卫与真实smoke模型的检查见[独立CPU报告](../posttrain-monitor/summary.md)。

状态位于服务器 `/diff/dzp_is_sb/php-parkour-research/outputs/coverage-official-final/monitor-status.json`，日志为`outputs/posttrain-monitor.log`。它等待七模型的训练、评估、导出和进程/锁结束，再准备三套296源CPU预检，固定物理GPU 1的UUID空闲后才进行888次首次尝试。当前没有创建selection、CPU或GPU验收容器；不把等待进程的启动视为完成这些步骤。七份正式最终PT、完整预检、后置GPU实际UUID映射与888次原片段执行仍待真实完成。

[机读摘要](summary.json) · [逐文件SHA/bytes](evidence-manifest.json)。
