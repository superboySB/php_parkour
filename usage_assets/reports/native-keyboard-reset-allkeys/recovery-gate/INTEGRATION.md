# 显式恢复门卫的最小接入

这里只准备 `previous_recovered.py`。作者未运行、导入或测试它，也未启动 Docker、GUI、GPU、SSH、守护进程或任何既有入口。候选已按冻结的四例生产者 `run.py`（edb808…）、`subset_check.py`（ff350…）和合同（98ace…）实现；实际四例完成收据不存在时返回 waiting，不能放行。

恢复合同与旧的正常完成合同不同：原 session54334 的真实 143、旧 launch-receipt 的 running 原字节、旧观察缺口永久保留；新管理器仅证明原 Docker exec 自然 0、629 个配置的 1258 个 worker 正常退出和 629 份视频完整解码。缺失的四例须独立补验，原八个缺失历史 birth 不得用新 birth 填入。技能质量仍未证明。

`previous_recovered()` 返回 `status=recovered_previous_ready, ready=true` 才可供调用方放行；未完成返回 waiting；已存在的矛盾证据抛异常。函数只读取文件、host `/proc` 和固定本地 Docker Unix socket 的 GET 接口。它不取 GPU 锁、不检查 GPU idle、不创建或停止容器、不发信号。调用方仍须在自己的既有独占 GPU mutex 内重新核验恢复证明与 GPU idle，并维持原清理合同。

最小 GUI carrier 可完整保留 `native-keyboard-reset-allkeys-preparation-01` 的 14 件 codefreeze 和原 manifest `5c99684ef9c19f6e6e3750c810c2613b72e0a691fae2552038b4c5445289ccf2`：先核其全部 SHA，再禁写 bytecode，以临时 `sys.modules` 绑定该冻结 `common.py` 加载原完整 `host_runner.py`，最后恢复 namespace。只把加载后的模块对象的 `previous_completed` 替换为调用公共门卫并拒绝 waiting 的函数；不改原源文件、不缩减原按键/观察/退出验收。新返回证明必须附 carrier/gate/原 hostrunner/common SHA 和恢复证据指纹，明确它属于恢复合同；不能给旧 receipt 加正常 0 字段。原 GUI 的 mutex、GPU idle、own PID/CID/XID/显示隔离和 finally 均照旧执行。

原 resume 根执行器 `native-resume-root-transaction-01/run.py` 的 `tool_exit()` 与 `previous()` 都固定旧正常 0 链，不能原样执行。未来独立新副本应仅把生命周期前提改为公共恢复门卫，保留冻结 root-commands `d573aa8075fe70f9264a20d6f6db8051c121fd3270170e728d5ec2fc2fa60996` 的 18 组 argv、科学 helper/adapter/输入门卫和 wrapper+真实 Kit child birth 观察。原候选的 cleanup 信号中断缺口仍须在新副本修正为延迟信号后再使用；不得修改旧候选或掩盖原审查记录。

armed waiter 当前原源、合同、PID 和依赖均不得更改。Root 将来先核定并取消它的 exact owned PID/birth，再制作新 copy/contract 后重新 arm。除了 waiter 的 `local_ready`，其调用的 `final-student-native58-preparation/native58.py` 的 execute 中也有旧正常完成门卫，且 verify_snapshot 固定旧 receipt 路径；二者都须显式采用同一恢复合同并重 prepare/封存新控制面。不可只改 waiter 让它继续卡在第二道门卫，也不可 monkeypatch JSON 读取来伪造旧 completed/driver0。最终 60 ORT、58 cases/116 workers/116 host mappings/58 full decodes 的科学合同保持不变。

以上 carrier、新 resume copy 与新 waiter/native58 copy 尚未实现或执行；本任务不复制更多控制器、不取消现 armed 进程。Root 审查并授权之后才可进行这些接入。
