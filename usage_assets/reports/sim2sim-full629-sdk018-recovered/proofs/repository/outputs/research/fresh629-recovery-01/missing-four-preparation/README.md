# 四例观察缺口的补验准备

这里只静态整理合同；没有运行入口、Docker、SSH、native/GPU、测试或 daemon。原 audit01 与原629目录保持原字节。

四例是 `high_speed_speed_vault` 的 `0004 run_left_45_0.3s`、`0005 0.5s`、`0006 0.9s`、`0007 1.2s`。原模拟/推理 entry 已封存，缺的是各自真实 host command_writer 出生时间映射，共8条；缺观察不等于技能失败。补验必须是独立的新尝试，不能改写原143或合成旧observer终态。

[contract.json](contract.json) 给出精确原生 argv、四个case_id、原模型/几何/三文件SHA、freeze5206及挂载。复用原目录的完整 `source` 5184文件（3297源码+1887生成输入）、`inputs`5文件、`control`4文件，均只读；输出与cache使用全新独立目录。固定2be镜像/物理GPU UUID、privateIPC/PID、networknone、init和8GBSHM。

原生 `sim2sim_scene_matrix.py --all-configs --case-id ...` 接受此四例；没有 `--resume` 或 `--case-limit`。它仍生成629项计划，实际只执行4项，真实终态应为 **completed_subset / completed_configurations4 / configuration_coverage_complete=false**。不能要求或伪称新matrix为completed629。原 `run_frozen_matrix.py` 禁止subset；原 `finalize_fresh629.py`只接受完整629，两者保持不动，也不假装可直接用于本补验。

Root实际执行前须完整恢复管理器daemon0+原native driver0+CPU629/1258cleanworkers/629全片解码，显式保留原8条观察缺口；核精确旧GPU/CPU CID均停止，无原生残留，再取得全局UUIDmutex并核GPU空闲。新observer必须先于新workers启动，最终8条精确hostwriter映射、8worker正常退出且组空、4MP4原文件完整解码，所有输入SHA前后相同才闭合这4例的新尝试。此处不改变当前cohort、armed waiter或任何旧门卫。

当前原session54334真实143，因此旧正常退出门卫仍未满足。本合同不授权绕过它；恢复终态须由Root另行真实观察和显式新合同记录。
