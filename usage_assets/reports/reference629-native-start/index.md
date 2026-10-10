# 629配置逐帧指令原生启动见证

这是 **2026-10-10 15:40:46.171069 UTC** 的固定历史见证，不随仍在运行的任务更新。当时矩阵为4配置 `completed`、1配置 `running`、0配置失败，CID `4d1e8c16558995d925ed273bc2a2568fffe51b81c229a10257bcefeaccc08a12` 仍在运行，原生矩阵 parent 的最终 wait 尚未产生。**不代表629配置、1258 worker、全部宿主映射或全片解码已经完成。**

[原始 witness](live-witness/witness.json) · [固定快照范围](snapshot-scope.json) · [原始 container inspect](live-witness/container-inspect.json) · [root-arm](root-arm/root-arm.json) · [真实 parent process-start](parent/process-start.json) · [native-running 启动 receipt](host/launch-receipt.json)

见证保存 launcher、controller、native docker-exec client、observer 四个真实宿主 PID / start-time birth。它们是控制进程身份，不是1258个原生 worker 的 `command_writer` 映射。只保留真实 process-start，未补造 pending 的 process-exit；也未将容器 Running 状态改写为已停止。

## 第一项已完成配置

原始 case ID：`random_locomotion:0000:cfg0000_stand_2.0s_left_45_1.4s_forward_2.3s_right_90_0.9s_right_45_0.6s_right_45_2.0s_left_90_0.6s_left_45_2.6s_run_right_45_1.2s_left_45_1.3s_run_right_90_1.6s_stand_2.0s`。本包复制该配置全部20个原始常规文件及独立 parent log；其中原生推理为920个完整策略 tick，两个 worker 的原始退出/进程组证据与录制 NPZ 都保留。[原始结果](first-completed-case/result.json)、[case-evidence](first-completed-case/case-evidence.json)、[worker-processes](first-completed-case/worker-processes.json)、[parent log](first-completed-case-parent.log) 可直接复核。

[原始视频](first-completed-case/video/episode_0_1791646765.mp4) · [原始 PNG](first-completed-case/video/episode_0_1791646765.png)

<video controls preload="metadata" poster="first-completed-case/video/episode_0_1791646765.png" style="width:100%;max-width:800px"><source src="first-completed-case/video/episode_0_1791646765.mp4" type="video/mp4"></video>

![第一配置原始缩略图](first-completed-case/video/episode_0_1791646765.png)

该 MP4 此时只有原核心 `ffprobe` 探测和缩略图检查记录；**全片解码待整批 CPU 后验**，此次出版没有再启动解码或仿真。第一项启发式阈值未触发也不等于障碍完成；`quality_verified=false` 与 `obstacle_course_completion_verified=false` 均保留。

## 输入与版本

原生启动 controller SHA `e25f6be50253044770bae37ba37e8b1db10098b65bf585d2d2af99d42e2e32f0`，宿主 launcher SHA `e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15`。[controller 原件](controller/reference629-native-controller-01.py)、[launcher 原件](controller/host_owned_launch.py) 与[三份真实 overlay](overlay/)保留原字节。

完整计划引用[已出版的无损 gzip](../reference629-plan/reference629-cpu-plan-01/checks/reference629-plan.json.gz)及[恢复凭据](../reference629-plan/restoration.json)，不重复复制103MB JSON。原始 whole SHA 为 `7729d5e6b4ea740e69511172c2331dd880cb7aaac3c75a07ccebb8e50d47311f`；17场景、629配置、342651个50Hz指令帧属于计划范围，而非此启动见证的已完成数量。原始冻结源/输入树与模型仍为外部复现前提，启动 receipt 的 `source_before` 保存5184个文件的原冻结校验；完整 run 后的 source-after 仍待终态，不能提前宣称。

本次只做宿主标准库复制、既有封存 SHA/bytes 核对、凭据模式扫描和链接存在检查。没有 Docker / SSH / GPU / 新原生操作，没有复制持续增长的 observer 流，也不改变 live 文件。[复制映射](copy-provenance.json)保留历史原路径；[evidence-manifest](evidence-manifest.json)绑定本目录全部文件（自身除外）。
