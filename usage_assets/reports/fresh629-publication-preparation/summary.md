# Fresh629 专用发布工具：冻结准备与真实等待

最终80/80项Docker CPU控制面测试和独立审查通过；11:44:05–06 UTC，root针对真实运行中的fresh629分别调用status、prepare、publish，均exit0/waiting，没有生成出版目录或.partial stage、没有启动额外进程，Docker ID集合及原生容器出生身份前后不变。此包没有完成或发布629物理结果。

- [冻结适配器设计及恢复前提](adapter/summary.md)、[准确计划](adapter/plan.json)、[源码冻结](adapter/code-freeze.json)、[原始30项清单](adapter/manifest.json)。原清单不包含自身；本包另保留它的完整字节。
- [最终80项JUnit](adapter/cpu-tests-final/tests.xml)、[启动/源文件前后SHA/退出回执](adapter/cpu-tests-final/launch.json)。候选73、80项各自原始源码和日志保留，不把多轮测试相加。
- [独立只读审查](review/summary.md)、[审查JSON](review/review.json)。三个预审问题——bytecode写入、验证后改变原件被接受、导入活主树模块——均已修正并有对应回归。
- [真实三个waiting调用及原始stdout](actual-waiting/root-attempt-02/summary.json)、[准确argv](actual-waiting/root-attempt-02/calls.json)、[前](actual-waiting/root-attempt-02/before.json)/[后](actual-waiting/root-attempt-02/after.json)容器身份。
- [root初次汇总失败](actual-waiting/root-attempt-01/root-summary-error.json)及[原汇总源码](actual-waiting/root-attempt-01/root-helper-source-before-fix.py)保留。该次三个接口和容器检查已成功，最后统计误用未开始行的status字段而KeyError；修正为默认planned后以新目录完成第二次核验，没有改原接口收据或控制器。
- [11:44:49实际本地/云端Docker top与身份](active-jobs/summary.json)：本地279 completed/1 running/349 planned；[11:34:36教师scalar原快照](active-jobs/scalars-20261010T113436Z.json)：首教师step11255，所选奖励/loss历史值有限。这些是历史进度摘要，动态matrix本体未另存，不能用于证明完整629终态。

适配器逐字节复用固定旧publisher中的纯校验/页面函数，并从固定cohort/source加载原生validator；不构造旧driver成功收据，不修改运行中的cohort、原官方训练、已armed final-student waiter或生产脚本。完整publish须实际host/CPU零退出和两容器停止、629/17未过滤一次执行、1258 worker正常退出/空组、1258精确hostwriter出生映射、629原视频既有完整解码、5206冻结文件及2266输入绑定全部通过。80项fixture含mock scientific gate，不能冒充真实物理后验。

完整发布逐字节保存原视频/PNG/CSV/JSON/日志；大host观察日志按不超过25,000,000字节连续分块，记录offset/长度/各SHA及原文件wholeSHA，可无损重组。失败.partial目录保留，完整成功后才原子改名；质量与越障成功标记始终false，跌倒仍显示。原始host树和计划在验证开始时绑定，复制前后再次核验。Git的chunk-*.bin属性禁行尾转换。

本包位于adapter/的原summary记录其准备时尚未调用真实接口，属于原始历史边界；root后续实际调用另列于actual-waiting/。恢复仍需要原绝对cohort、canonical context、1887生成输入、released ONNX和原生结果，不能仅凭本包补造629证据。复制本包不能运行新的训练或重启原任务；历史root helper源码按原字节留存，不应在归档目录直接重新运行。[外层字节清单](evidence-manifest.json)覆盖本包全部文件。
