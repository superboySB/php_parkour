# 恢复版最终学生交付 waiter：已启动，等待官方产物

2026-10-10 **14:37 UTC（北京时间 22:37）**，Root 完成旧 waiter 的受控取消，启动恢复版 waiter。首次真实 SSH status 返回 `waiting`，`polls=1`；该固定快照中 fetch、CPU prepare 和 native run 均未开始。最终两学生的 60 个 ORT case、58 个 native case、116 个正常退出 worker、116 个 host writer 映射和 58 段完整录像仍是后续验收要求，**尚未执行完成**。

旧进程 PID `1121672`、birth `105819944` 的命令与源码 SHA 核对后，仅向该 leader 发送 SIGTERM。旧状态在 22 次轮询后记录 `failed / KeyboardInterrupt: ... signal 15`，这是本次受控取消的原始记录；该进程不是取消器的子进程，`actual_old_OS_wait_returncode=null`，不推断其 OS wait code。取消后原 singleton lock 已释放，inode `88220918` 保持不变。[原始取消收据](actual-replacement/old-cancellation.json)

新 launcher PID `2146112`，waiter PID `2146113`、birth `107103856`。14:37:50 UTC 的固定活性收据记录其已启动并等待官方产物，原 singleton lock inode 相同。父进程仍等待，没有 `process-exit.json`，不报告终态退出码。[首次等待状态](actual-replacement/new-first-waiting/execution/state.json)、[固定活性收据](actual-replacement/new-first-waiting/liveness.json)、[父进程启动收据](actual-replacement/actual-parent/process-start.json)

本次仅接入诚实的本地恢复生命周期：原 session54334 的退出码 **143**、原始 8 个历史 host writer 观测缺口永久保留。新门卫分别验证已恢复原 629 配置的 daemon/CPU 正常完成、1250 个原始唯一映射，以及另外四例补验的 8 个新映射；不把新 birth 填进旧缺口。其余官方 16 阶段、7 个 PT、CPU-ready 来源、单次回传 4 个 ONNX 与 28 个 JSON、几何和源码 SHA、GPU mutex 与空闲检查、失败保留和禁止自动重试判据保持不变。8 个科学与复用 helper 逐字节未变。

恢复版 waiter SHA：`872381be0fada94d3b4558ee0a0581ea18261b03159d5a9ac3661a531e5f7893`；合同 SHA：`d5226f24a6e5efeee7c1505644266e172647a70a62d13992fcf0dbe8228303fd`。准确 arm argv 保留在 [准备包命令记录](preparation/waiter/root-arm-command.json)，实际启动 argv 位于 [launcher 原始记录](actual-replacement/launcher-start.json)。现有 waiter 已启动，本记录不是再次手动启动的要求。

包内保留准备阶段的全部原字节，以及本次取消与首次等待的 146 个原始文件，包括旧 22 次轮询日志；另保留实际 host launcher 源码。只复制 Root 提供的固定 `new-first-waiting` 快照，没有复制或修改之后继续变化的新 live execution。准备阶段原 [summary](preparation/summary.md) 的“未启动”描述对应当时状态，本页记录随后实际启动事实。恢复前提和精确路径见 [restore-map](preparation/restore-map.json)。本包没有最终学生模型或最终技能成功证据。
