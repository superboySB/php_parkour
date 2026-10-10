# Fresh629 独立发布入口：准备与CPU控制面证据

当前仅完成独立控制器与最终80/80 CPU fixture测试；没有调用真实cohort的status/prepare/publish，没有运行真实全量后验或创建实际出版目录。候选01的73项、候选02的80项和最终80项原日志/XML/启动参数/各自精确三源码均保留。最终还保留了实际runc容器before/after inspect、source-before/after与own容器移除收据。

入口只读取固定fresh629 cohort，既不连接Docker daemon/SSH，也不启动子进程、仿真、GPU、daemon或修改旧cohort/云端训练/已armed waiter。status、prepare、publish在真实host launch仍starting/running/native_completed时均返回waiting/exit0，不建stage或出版目录。真实host failed会拒绝；只有completed才能继续完整校验。prepare执行完整只读校验并打印结果，仍不生成出版目录。

完整publish必须核实际host/CPU终态及GPU+CPU容器停止收据，629配置/17scenarios，1258 worker direct exit0+空且已退休的私有processgroup，1258精确hostwriter PID/TID出生映射，629原MP4的既有CPU全片decode及每份result/workerreceipt/video SHA。还核5206冻结文件（source5184/control4/host13/inputs5），source/control/inputs实际regular文件集无增删，2266 native source/model/dependency记录全部绑定冻结SHA/大小。host原snapshots全部逐行复算summary映射，保留原first-status/lastseen语义。不是重新运行ffmpeg或重新生成物理证据。

复用publisher_source.py是现生产publisher的原字节SHA固定副本；仅重用validate_plan/case/attempt_archive及原interactive页面/真实轨迹SVG渲染。先核原生matrix源码SHA，再私有加载cohort/source中的validator，使ROOT匹配冻结namespace；临时绑定并恢复三个module cache项，避免执行live主树模块。程序本身禁bytecode写入。没有构造旧driver receipt或修改任何原始JSON。

出版先保留唯一.partial-* stage，失败保留stage/诊断和已复制原字节，不覆盖既有出版。验证起始时锁定的host全树和plan/matrix SHA直接传递给copy，验证后变化会拒绝；copy不接受重新计算的新期望。逐case全部原视频、PNG、CSV、JSON与日志保留，不压制跌倒/阈值。完整host树原字节保留；超过25,000,000字节的文件以连续chunk保存，chunked-originals.json记录每块offset/bytes/SHA及原文件wholeSHA/长度，按列表顺序拼接即可重组。最后复核原host字节/文件集、计划/矩阵和完整freeze，再原子rename成功目录。

准确命令见[plan.json](plan.json)：

```bash
python3 -B outputs/research/fresh629-publication-preparation/publish_fresh629.py status
python3 -B outputs/research/fresh629-publication-preparation/publish_fresh629.py prepare
python3 -B outputs/research/fresh629-publication-preparation/publish_fresh629.py publish --output /home/dzp/projects/php_parkour/usage_assets/reports/sim2sim-full629-sdk018
```

第三条仅供root在真实完整终态及独立审查后执行，当前并未调用。没有preview或伪造终态通道；真实出版路径须fresh且位于workspace的usage_assets或ignored outputs/research。默认cohort/绝对workspace/host plan/native plan/固定image provenance不可替换。正常闭环运行与没有触发生存启发式阈值都不等于越障/技能成功，quality_verified和obstacle_course_completion_verified始终false。

恢复前提：本准备包不是629物理证据或完整资产包。必须保留原绝对路径outputs/research/fresh629-sdk018-6cb2ae2-prepared02内5206冻结文件、完整outputs/all-configs逐case原件、全部host动态日志与终态收据；不能仅凭本包的设计plan重建结果。canonical source context outputs/research/sdk018-canonical-build-6cb2ae2/context及source-manifest.json（3297源码）、1887生成输入、released ONNX pair、canonical image2be185与原native运行环境是重新准备/重跑cohort的外部前提；出版校验只读取已完整保留的cohort，不要求启动该image。本包不复制大source树或ONNX。

冻结清单[manifest.json](manifest.json)明确排除未来root-execution/、__pycache__/及.pyc/.pyo；root后续真实waiting/raw应另行出版，不能混入本次CPU完成范围。
