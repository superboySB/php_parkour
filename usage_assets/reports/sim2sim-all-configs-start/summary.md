# 全629配置物理闭环：两例预检与后台启动快照

截至 **2026-10-10T06:19:44.570322+00:00**，固定629配置计划的逐case记录中实际完成 **16/629**，状态分布 `{'completed': 16, 'running': 1, 'planned': 612}`。后台任务仍在运行；不声称629完成、课程通过或策略质量通过。这里是精简启动证据，后续完整结果应另行发布。

[完整计划](plan.json)保存17场景629配置、340依赖与1887输入SHA，seed42，每配置10模拟秒；使用真实released ONNX、原生DDS/深度共享内存、PD/MuJoCo物理。每例恒定forward命令，不按原reference轨迹回放。计划identity为 `571dfb1e11c1cb862f8b6e8a3b8760b5cb899e039a5bfeb3b1012213d0b59158`。

两例实际预检exit0、wall **43.006016s**，各500策略ticks，gantry在策略阶段均已关闭。

| 原配置index | Policy ticks | 策略模拟秒 | 高度/倾斜阈值事件 | 原始证据 |
|---|---:|---:|---|---|
| 0 | 500 | 10.010 | 未触发 | [JSON](pilot/case-0000/result.json) · [MP4](pilot/case-0000/video/episode_0_1791612781.mp4) · [PNG](pilot/case-0000/video/episode_0_1791612781.png) |
| 1 | 500 | 10.010 | 触发 | [JSON](pilot/case-0001/result.json) · [MP4](pilot/case-0001/video/episode_0_1791612802.mp4) · [PNG](pilot/case-0001/video/episode_0_1791612802.png) |

两段MP4均用容器内ffmpeg `-hwaccel none -threads 1` **完整解码**，分别719/712帧，与原ffprobe相同，exit0、progress=end、stderr为空。见[解码报告](video-full-decode.json)。解码仅用CPU，没有启动仿真、GPU作业或获取全局sim锁。

完整后台任务于 **2026-10-10T06:14:54.250576+00:00** 启动。[detached launch](host/full-launch.json)只是启动回执；[driver回执快照](host/full-driver-snapshot.json)、[实际live PID树](live-processes.json)、[执行日志快照](host/full-execution-snapshot.log)共同证明已开始运行。[driver wrapper](host/full_driver.py)和[冻结harness](sources/sim2sim_scene_matrix.py)也保留。

[原子matrix快照](matrix-snapshot.json) SHA为 `2e279dba421abf672d41d5d60a654f4678d2dcd4c1c82a5e599cc047997742d4`。该文件按原子replace读到完整bytes并原样发布。运行中的顶层completed_configurations目前仍是前次pilot的2，finished_unix也沿用pilot；**本页16是从selections中completed+exit0+完整result+500ticks+gantryoff逐条核得**，不是用旧顶层计数。完整629运行以resume保留两例预检，没有重复计数。

首次28项CPU测试与真实native子进程并行，16个fixture被/proc门卫拒绝重叠，原[失败JUnit](cpu-tests/root-first-parallel.xml)完整保留。待native空闲后，同28项[重跑JUnit](cpu-tests/root-idle-rerun.xml)和[日志](host/root-tests-idle.log)证明28/28通过。该结果只证明CPU控制流，不冒充真实物理验收。

随后仅修复CPU测试fixture隔离：普通fixture使用自己的临时锁并忽略无关真实native进程，专门的/proc测试仍读取真实/proc，但限定到本测试创建的CPU子进程。测试可与正在运行的真实扫描共存，新增[隔离后JUnit](cpu-tests/root-isolated-concurrent.xml)及[原始日志](cpu-tests/root-isolated-concurrent.log)证明28/28通过（0失败、0错误、0跳过）。生产harness SHA保持不变；以上首次16失败及空闲28通过原件均未覆盖。这仍是CPU控制流证据，不新增物理case，也不更新本页06:19UTC运行快照。

case1的阈值事件如实保留；高度/倾斜阈值本身不是课程完成判据，也不能普遍等同永久跌倒。`quality_verified=false`、`obstacle_course_completion_verified=false`。原17代表场景gallery保持不变。

[完整发布摘要与快照时间/SHA](summary.json) · [发布manifest](evidence-manifest.json)
