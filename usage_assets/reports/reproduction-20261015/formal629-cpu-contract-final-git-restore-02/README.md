# 实际两629 CPU合同：Git权限恢复实测

主包 seal `99a37fe0752cc7a92d4b8b1d14d961238b3bc76f715e97bc18b01e03e9dc9e60`。71份发布文件先按Git的0644/0755权限归一化，原236f标准库restore经原e238父进程实际执行。原父child.wait退出0，外层真实Popen/wait退出0；两层process-start/process-exit及stdout.raw/stderr.raw全部保留。

85份原件逐一SHA256、bytes、完整原mode和精确file-set与原封包source-snapshot相同。包含两份完整629参考计划，不缩减物理指令或时序；主包seal与文件均未改变。本次仅标准库恢复CPU验收证据，不运行仿真，也不证明正在进行的1258物理测试完成。

[CPU合同主包](../formal629-cpu-contract-actual-02/README.md) · [逐件恢复核验](exact-restoration-review.json) · [原e238父退出](original-parent/process-exit.json) · [外层退出](outer/process-exit.json)
