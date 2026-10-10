# SDK0.1.8 全629配置：CPU准备证据（尚未启动仿真）

固定 canonical 镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`，源码 commit `6cb2ae2492ef7bf66da7c5a72da87d6f60f0636f`。这是新的独立cohort，不恢复旧629目录，也不使用5例pilot输出。

- 629个配置、17类场景、1887份生成输入、580个不同OBJ内容；released模型保持原SHA。
- 完整3297份canonical源码与输入/控制器/CPU报告共5206文件，全部SHA独立复核通过。此小归档只含manifest、计划、CPU报告和控制源码，不含完整源码树、资产、ONNX或录像。
- 实际CPU容器使用runc、network none、private PID/IPC、无GPU请求；原生all-configs计划、17场景配置/Unitree动态entrypoint、DepthPolicy/SHM等两角色imports三命令均exit0。SDK两环境均0.1.8，未构造Robot/DDS、未初始化CUDA；CPU容器已停止。
- 外层控制器19项CPU测试通过。validation独立5206 SHA复核通过。每例原生verify_inputs前额外检查全容器native残留并重验控制器自身SHA；该门卫是外层新增控制，不改6cb原生core/actor/CLI。
- 原生case argv不传startup/wall override。由冻结sim2sim.py:436、512默认计算：startup180秒、10秒单命令wall413秒；**这只是启动前推导**，未来每例实际run.json必须逐项核对。无隐含120秒watchdog。
- 宿主native driver上限43200秒，observer上限43500秒；native结束后先停止自己的GPU容器，再CPU全量验收。observer若异常未及时结束仍为只读进程且受自身上限约束。
- 未来完整验收要求真实driver0、629例各500ticks、1258个worker exactexit0/空且身份连续的processgroup、1258个精确host command_writer映射和629个MP4完整decode。当前未产生这些运行结果。

host-plan身份：`44d6e71e8ef1d12c5b479d8e3bcb411c39e8d7daa1c3bac109d6edd7417502d0`；native计划身份：`1e3483f7b35dd7592d9e5e0b02c13143a44e4f17a5cd0ba24def25c0229a6e6f`。

准备第一版曾在所有CPU预检通过后因宿主chmod容器root-owned报告失败；[原始失败日志](independent/preparation-01.log)保留，第二版取消无必要chmod并加入回归，使用新目录完成。第一版没有启动native/GPU。

后续启动必须由root单独授权，并持有共享GPU宿主锁。所有结果仅验收真实执行和退出完整性；constant-forward不等于参考轨迹重放，存活启发式不等于越障成功或SDK因果结论。
