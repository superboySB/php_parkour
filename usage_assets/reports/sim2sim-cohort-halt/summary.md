# 旧629扫描有序中断，不能作为完整验收

2026-10-10 07:48:27 UTC（北京时间15:48），停止了本任务自己启动的本地扫描。先验证真实driver PID及starttime、暂停发起新case的Python，再给当前case写stop marker；确认native子进程全部退出后，向已核验driver发送SIGINT并恢复，让外层wrapper保存实际exit1。未操作云端训练或其它程序。

原matrix逐项状态为279 reported completed、5 execution_failed、1 running、344 planned；running是本次有意中断的未封存attempt，不能补记completed。顶层completed_configurations=2仍为旧pilot派生计数。所有原状态、视频、日志和attempt都保留；两把原锁已实测空闲，无原native/driver存活。

停止原因是已实证的SDK退出段错误及父监督缺少最终worker退出码门卫；部分reported completed也有崩溃日志。因此这一批次不会被当作正常退出的629结果发布，需修复后新建源码、镜像、计划与输出批次，不能resume伪装旧cohort完成。

[实际终态与清理](halt-receipt.json) · [原外层退出回执](after-full-driver.json) · [中断后完整matrix快照](after-matrix.json) · [340依赖Git来源复核](git-frozen-source-proof.json)

340项原依赖共76,769,793字节已在ignored原目录按SHA完整归档，并逐项证明与本报告记录的Git提交一致。小型source-before保留关键监督/启动脚本；原镜像88254ac0仍保留。输出目录名all-configs-final是历史名字，不代表最终验收完成。
