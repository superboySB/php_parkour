# technical_pipeline.md 独立只读审查

审查文档 SHA256：`a2933ee0c69d1dad52e9cb357f575329aeed1882b7f36c94963af2651c6ed56c`，共580行。未修改文档、源码或旧运行证据，也未启动GPU/DDS。

结论：没有发现需要纠正的算法/源码事实错误；没有将实机闭环、完整训练或629物理扫描写成已经完成。用户要求的技术主题均有具体说明。

| 主题 | 文档行号 | 结论 |
| --- | --- | --- |
| Teacher RL state/observations | 188–221 | covered; sorted term order, actor449/critic575 and six preset variants/noise are explicit |
| Actions/control/physics | 223–245 | covered; Gaussian mean29, positional residual/scale, runtime default-bias and 200Hz/50Hz timing are distinguished |
| Reward/termination/PPO loss | 247–294 | covered; nine reward terms, dt, BadTracking, GAE, clipped actor/value loss and entropy agree with native implementation |
| Student inputs/labels/BC/PPO/gate | 296–383 | covered; depth/current-state inputs, expert routing, deterministic label origin, zero-label mask differences, both objectives and noncheckpointed residual statistics are explicit |
| Nonlearning provenance/formats/labels | 44–182 | covered; upstream retarget versus this run,27D normalized L2/features,inertialization/FK/IK/terrain schemas, quaternions and units, native mapping, FPS and command sources are distinguished; neither playback nor conversion is called learned policy success |
| GUI labels and paired files | 172–180 | covered; current Tk saves paired files but still lacks vel_cmd, Viser preserves existing labels; no intent inferred from displacement |
| Deployment/real2sim2real | 385–520 | covered; two ONNX sessions, observation order/default metadata caveat, joint map/PD/DDS/frame/depth/SHM clocks, robot description differences, randomization and physical hardware limits are explicit |
| Validation/completion boundaries | 522–580 | covered; smoke versus official schedules, source clip IDs/warmup/boundaries, 17 versus629, threshold versus skill success, failed quality and unverified hardware remain explicit |

129个本地链接均存在，源码行号fragment均在文件范围内；115项旧算法审计源码SHA全部可解析验证，其中112项匹配当前文件，3项GUI旧版本匹配发布的source-before原字节。source-before manifest的7文件也全部通过。

建议后续刷新证据（不属算法错误）：第550/567行已明确14:19历史快照，因此原计数可以保留。新观察到的low_speed_step:0041原生退出故障应另附时间戳和取证链接，保留execution_failed，不将其归为技能/倾斜失败，也不写629完成。第439行0.1.6仍为本次冻结cohort实际SDK；不能把尚未在本次新运行验证的上游0.1.8修复写成已用/已验。证据见`outputs/research/sim2sim-failure-forensics/low-speed-step-0041-attempt-0001/report.json`。

第535行没有宣称YAML与PT配置逐字节相等，现有说明准确；六preset的symbolic output_dim在原生setup内被解析为29，是另有报告记录的预期运行时补全，不应称配置损坏。

边界：本审查为静态源码/已有证据审查，不替代未完成的七模型训练、Isaac reload/dynamics、真实G1/D435i/IMU标定或新SDK生命周期实测。原MoCap到每一PHP发布clip的映射缺口仍存在，文档已如实限定。
