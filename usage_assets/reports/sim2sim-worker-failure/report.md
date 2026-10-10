# low_speed_step配置41：保留执行失败的只读调查

该attempt仍为`execution_failed`，parent exit1。虽然原生推理保存500ticks、模拟器保存10.002策略秒/501无吊架有限样本，缺少成功的原生父进程终态、result.json、PNG与case-evidence，因此不能改记completed，也不能由两个body JSON推断整个进程成功。

原字节保留：14个attempt文件（含MP4/trajectory/worker logs/JSON）、parent traceback、固定plan、当时matrix完整快照与失败selection；每份均有SHA，复制前后校验一致。没有重编码媒体或修改原运行目录。

| 事件 | 实际UTC | 证据 |
|---|---|---|
| 推理body完成JSON | 07:00:49.690954 | 原文件mtime_ns、500ticks/STOP lifecycle |
| 内核native thread段错误 | 07:00:49.743842 | journal原JSON：`command_writer[394853]: segfault` |
| parent发现worker非0 | 07:00:50.119261 | error.json文件mtime、A worker failed |
| 模拟器保存原MP4 | 07:00:51.392426 | 原文件mtime、simulator.log save成功 |
| 模拟器body完成JSON | 07:00:51.460990 | 原文件mtime、10.002s/finite/gantryoff |

这一顺序强烈指向推理完成后native线程/退出阶段异常；它不是策略摔倒证据（本次body轨迹未触发高度/倾斜阈值）。但旧harness不记录每worker具体returncode/信号及宿主PID映射，因此不能确赋崩溃进程、C++函数或析构竞态。内核PID394853是thread ID，不直接等于容器policy PID45120。

源码说明这一证据组合可能出现：sim2sim.py先写inference.json，再进入finally/解释器退出；worker的PythonBaseException handler抓不到native信号；parent只写笼统A worker failed，随后finally等待另一个worker，后者仍可完成视频和simulation.json。当前policy Python UnitreeInterface/BaseInterface无显式close，SDK C++析构具体顺序仍由runtime独立审阅。

SHM resource_tracker警告在邻接成功case40与42同样存在，不能单凭警告认定根因。只读journal能读到segfault；当前窗口无systemd-coredump记录，coredumpctl未安装，dmesg权限不足；没有sudo或安装工具。

最小后续：保持当前629扫描继续，等其终态且所有DDS worker退出，再保留本attempt并以fresh独立尝试/observer显式记录每worker容器与hostPID、returncode/信号、faulthandler/退出日志；只有正常终态和原生完整证据门卫通过后才能另记成功。不要补造result.json、覆盖失败历史或修改活跃冻结harness。

[完整来源、SHA、时间与代码行号](report.json) · [原字节manifest](evidence-manifest.json) · [内核journal原JSON](host-query-00.stdout.log)
