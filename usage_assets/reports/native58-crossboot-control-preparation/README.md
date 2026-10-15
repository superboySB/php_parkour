# 跨重启续跑的宿主控制准备

这是明确的新宿主控制版本：保留旧 boot、旧等待器失败、原 root 退出 143 和八个历史观察缺口；只适配跨重启的 PID 身份与当前容器不存在事实。原 native58 科学源码、模型、计划和 CPU60 准备不变。

[独立源码审查](source-review.json)与[父进程启动器审查](launcher-source-review.json)均通过。24 项普通 CPU 单测、原 e238 父进程的真实 0/7/130 等待及两次精确 pidfd TERM 检查通过。真实只读门卫退出 2，记录 [GPU 忙时的 waiting](actual-readonly-gate.json)。它们不构成原生 58 例或技能成功验收。

可直接阅读 [门卫](sources/crossboot_gate.py)、[显式控制入口](sources/run_native58.py)和[真实父进程外层监督](sources/launch_native58_crossboot.py)。归档包括全部 26 个准备依赖、CPU 原始输出、审查、实际合同/只读观察，以及当时不可变的启动记录。运行中的 stdout 与未来退出记录不在此快照内。

无损恢复只需 Python 标准库，先取得外部已审查的 evidence-manifest.json SHA256：

```bash
python3 cloud888_report.py restore --input . --output /tmp/crossboot-sources-new --manifest-sha256 <已审查的包SHA256>
```

原工作区相对路径、字节 SHA、完整原权限保存在 raw-inventory.json；Git 不保留的完整权限由 restore 恢复。恢复不会运行任何训练或仿真。固定源码中的原绝对工作区仍须按原合同理解；本包不恢复整棵科学源树、模型或历史629全部依赖，不能单独执行原生任务。模型与 CPU 原件见[独立模型包](../reproduction-20261015/student-transfer-cpu-actual-02/README.md)，历史629见[原验收归档](../sim2sim-full629-sdk018-recovered/index.md)，当前真实终态见[续做记录](../reproduction-20261015/index.md)。
