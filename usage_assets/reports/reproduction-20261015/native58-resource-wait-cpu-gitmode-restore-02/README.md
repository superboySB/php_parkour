# 新一轮 CPU 准备包的恢复验证

将[CPU 准备包](../native58-resource-wait-cpu-prepare-02/README.md)的权限先规范为 Git 可表达的 0644/0755，再通过原 e238 父进程实际执行标准库 restore。真实父进程和外层等待均为 0；42 个原始文件的集合、字节、SHA256 和完整权限全部一致。此验证没有启动原生仿真。

[执行原件](execution.json)；[原父进程退出](original-parent/process-exit.json)。
