# 只替换等待中的逐源验收监视器

2026-10-10 10:09 UTC 已实际完成升级。新watch PID4074213、出生ticks702550493，使用已提交并完整同步校验的源码快照 `02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c`，独立输出 `outputs/coverage-official-final-ro-assets-v2`，状态waiting、gpu_started=false。它等待七个正式模型和全部16阶段完成后，才启动独立CPU验收，再等待固定GPU1空闲执行888次first attempt。启动监视器不等于完成训练或源覆盖。

升级前后两次只读核验原watch PID3940821、出生ticks701292491、命令/源码/PGID/SID/bootID及新鲜waiting状态，无selection或CPU/GPU验收子容器。保留其status/log/launch原字节后，仅对该进程经pidfd发送一次SIGTERM，观察退出并确认全局锁释放；没有PID-only/group信号或强制升级。旧目录和日志仍保留。

正式训练的container ID、镜像、宿主PID、StartedAt、全部mounts、训练进程出生身份以及全部Docker container ID集合在audit/upgrade前后完全一致。正式训练仍用原0093源码和631镜像；没有Docker stop/start/exec操作，没有重启训练。helper的25项目标CPU门卫通过，初轮20通过/5失败的原XML也保留。

本目录包含两阶段原始远端stdout/exit、实际新watch身份、远端原始归档的按字节回传、完整操作helper及CPU测试证据。该升级只衔接RO源码资产修复；技能质量仍需正式产物与实际rollout验收。

- [升级实际完整回执](upgrade/stdout.json)
- [只读升级前核对](audit/stdout.json)
- [旧watch原始字节归档](remote-originals/)
- [CPU门卫与操作源码](helper-cpu/report.json)
