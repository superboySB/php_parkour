# 第二次原生退出失败：low_speed_climb_58配置22

本attempt保留`execution_failed`和parent exit1。14个原文件（594612bytes）、固定plan、失败selection、当时matrix、parentlog及kernel原JSON已逐字节保全；没有写result/PNG/case-evidence、重试或修改冻结cohort。

| 事件 | UTC |
| --- | --- |
| inference_body_json | 2026-10-10T07:33:00.232871+00:00 |
| first_kernel_command_writer_segfault | 2026-10-10T07:33:00.290878+00:00 |
| parent_detects_worker_nonzero_error_json | 2026-10-10T07:33:00.660859+00:00 |
| simulator_mp4_saved | 2026-10-10T07:33:01.205862+00:00 |
| simulator_body_json | 2026-10-10T07:33:01.266617+00:00 |
| second_kernel_command_writer_segfault | 2026-10-10T07:33:01.889877+00:00 |
| parent_attempt_final_exit1_receipt | 2026-10-10T07:33:02.086655+00:00 |

第一条kernel `command_writer[464076]`段错误发生在inference JSON后58.007433ms。第二条`command_writer[464044]`在simulation JSON后623.259632ms。父进程先检测异常，模拟器继续保存原视频/轨迹/JSON，父进程收尾后最终exit1。

这次新增直接证据：`sim-ready.json`的simulator PID为63669，`simulator.log`明确记录`/isaac-sim/python.sh: line73:63669 Segmentation fault(core dumped)`，因此可归属simulator Python段错误退出。policy-ready为63702；没有旧hostPID映射/逐worker返回码，不能把两个kernel线程分别精确映射或仅凭数量断言两worker各崩一次。当前对应container PID和host TID均已退出。

worker body保存500policyticks，10.0sim秒、501无吊架active样本；704行完整CSV全部finite，minimum pelvis=0.7299898267m、minimum up=0.9802942518，没有高度/倾斜阈值事件。这不代表完成climb技能，也不弥补父进程失败。

与第一例相同：原生命令线程在inference body完成之后很快崩溃；相同parent traceback SHA/exit1；simulator仍能保存body文件；最终成功证据缺失。两例轨迹均未触发高度/倾斜门槛，退出故障与技能质量分开。邻接成功case21/23同样有SHM resource_tracker警告，故警告不足归因。

不同：第一例low-step41只有一条kernel command_writer崩溃且无simulator shell段错误文本；第二例climb58-22有两条kernel崩溃和可明确归属的simulator段错误。前者在发布训练技能范围，后者climb58不在五bundle名称中；这项范围差异不能解释native析构故障。10个相同Python/launcher/cleanup源码SHA均与第一例一致。

当前simulator的CPython3.11与inference的3.12只读metadata都仍为SDK0.1.6。runtime已保存的上游0.1.8源码在析构中新增`Wait()`后reset，与本次时序相容，属于最小修复候选；没有本例backtrace/core证明根因，也没有在此cohort应用修复。保存的两份CPP仅为参考，不是本次镜像版本变更。

最小后续：让冻结扫描继续，终态且DDS空闲后再审阅独立新cohort的workerPID/返回码/信号原始记录补丁。保留两次failedattempt，只有新尝试正常终态及全部原生门卫通过才能另记成功；不可补造旧result或覆盖失败。

[完整字段、SHA及比较](report.json) · [原字节清单](evidence-manifest.json) · [内核journal](host-query-00.stdout.log) · [PID证据](pid-observation.json)。
