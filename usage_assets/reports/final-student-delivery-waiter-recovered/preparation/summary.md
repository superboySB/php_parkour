# 最终学生交付 waiter：恢复生命周期接入准备

这份包仅替换本地主机的前置生命周期门卫。原 session54334 的真实退出码仍为 **143**；原 629 配置由已接管的 Docker exec 自然退出 0，并完成 629 配置、1258 个 worker 正常退出和 629 段录像全解码。原 observer 仅有 1250 个唯一 host writer 映射，8 个历史缺口保持原样；另外四例补验提供独立的 8 个映射与 4 段完整录像。门卫使用原字节 `previous_recovered_02.py`，SHA 为 `dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525`，不把原失败改写成正常退出。

新 waiter、合同和 native58 只完成源码准备与静态审阅。本轮没有执行、导入或测试这些新入口，没有取消旧 waiter，没有 fetch、CPU 模型准备或 native/GPU 运行。旧版 55/47 项测试属于旧源码；本包不将它们算作新版实测。

新代码继续要求官方 16 阶段、7 个 PT 和 CPU-ready 来源通过，再单次回传 4 个 ONNX 与 28 个 JSON。未来本地验收仍为两对模型 60 个 CPU ORT case，以及每个学生 12 个方向和 17 个代表场景，共 58 个 native case、116 个正常退出 worker、116 个精确 host writer 映射和 58 段完整解码录像。8 个科学与复用 helper 逐字节等于旧版；学习参数、原生命令、模型与几何校验、失败保留及禁止自动重试的行为未变。执行完成也不代表越障技能成功。

Root 应先核旧 PID 1121672 的完整出生身份与等待状态，再结束该旧进程。新旧 waiter 共用原 `waiter.lock` 的非阻塞独占锁；新入口若误在旧进程仍持锁时启动，会在 status/fetch 前拒绝。包内不包含自动取消或 arm 脚本。

准确的手动 arm argv 与全部 SHA 位于 [root-arm-command.json](waiter/root-arm-command.json)。新状态和日志写入 `final-student-delivery-waiter-recovered-preparation-01/execution`；新回传目标为 `final-student-transfer/waiter-delivery-recovered-01`，新 native 目标为 `final-student-native58-delivery-recovered-01`。旧目录及其原始状态不复用、不覆盖。

本包是源码归档，不是独立可运行镜像。恢复代码时应按 [restore-map.json](restore-map.json) 放回精确的原绝对路径；还需要现存 canonical context、1887 个生成输入、既有方向 baseline、五个 helper 的原位置、严格 pull 入口，以及恢复链的原始 629/四例证据和已停止容器。上述外部前提未复制进本包。`source-before` 仅用于比较，不应覆盖仍在运行或已冻结的旧文件。
