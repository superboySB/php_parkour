# fresh629 启动与首两个样本的独立 CPU 后验

固定快照为 **2026-10-10 10:10:23.951343 UTC**。当时整批状态为 `running`：21 项完成、1 项运行、607 项待跑。**本报告仅验收计划最前面的 2 个 random_locomotion 配置，不能作为 629 项完成或全部场景技能成功的证据。**

[独立报告](cpu-review.json)、[固定矩阵快照](snapshot/outputs/all-configs/matrix.json)、[原始启动收据](snapshot/host/launch-receipt.json)、[原生计划](snapshot/inputs/native-plan.json)、[完整冻结文件清单](snapshot/freeze-manifest.json)。本包保留原始字节，不覆盖 live 原件；计划内路径保留当时的容器路径。

- 原生容器：`2d09d396cf6936c28334e3798a03db87eeceac6562bbc280ab0586e99253a8e1`；镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`。固定 GPU UUID、network none、私有 IPC/PID、source/inputs/control 只读在启动与快照身份中一致。
- 5206 个冻结文件共 1,314,912,939 B 的 SHA256 全部匹配：3297 个完整源码文件、1887 个生成 motion/terrain 输入、22 个控制/元数据文件。其中 Python 依赖集合为 **376** 文件。原始 released student/depth ONNX 对和这两例实际 OBJ 哈希同时由原生输入 validator 验证。
- 两例均只有一次 attempt，parent rc0；4 个 worker 的原始 `worker-processes.json` 均以 `finally_wait_complete` 收尾，角色 rc0/exited、所有组 retired_empty/ownership intact、live_members/cleanup_errors/unreaped_roles 全空。两个角色的原生 PID/出生时刻、启动 argv、SHA 与 spawn/completion/final 收据通过原生 schema3 validator，并已纳入 case-evidence 哈希。
- 4 个 command_writer 线程均与原始 host `/proc` 观察中的进程 PID/出生时刻、TID/出生时刻、NSpid/NStgid 对应。[派生映射](snapshot/host/observer/selected-mappings.json) 与[原始采样行](snapshot/host/observer/selected-snapshots.jsonl)经[独立再连接校验](host-mapping-source-proof.json)一致。这是首两例的历史观测，不是整批 observer 完成收据。
- 每例 500 推理 tick，控制周期 .02 仿真秒；轨迹含 501 个有效采样，相邻间隔 .02 s，首末跨度恰为 10 s。首采样有 .016/.008 s 启动偏移，因此末采样为 10.016/10.008 s。它们不是 wall 秒；实际模拟循环 wall 为 16.319/16.339 s。
- 两段原生 MP4 均非空、duration 为 14.24/14.14 s（含初始化/释放阶段），`ffmpeg -xerror` 全片解码 rc0，前后 SHA 不变。下方 PNG 来自真实原片解码；第二例取视频 12 s 展示实际跌倒。

| 配置 | 执行/500 ticks/退出收据 | 生存阈值结果 | 原片与截图 |
|---|---|---|---|
| random_locomotion cfg0000（无 clutter） | 通过 | 未触发高度/倾斜阈值；最低 pelvis .6280 m、up_z .8752 | [视频](../../sim2sim/fresh629-start-first-two/random-locomotion-cfg0000.mp4) · [截图](../../sim2sim/fresh629-start-first-two/random-locomotion-cfg0000.png) |
| random_locomotion cfg0001（含 clutter） | 通过 | **触发跌倒阈值**；最低 pelvis .06163 m、up_z −.66519，倾斜阈值采样累计 8.0 s | [视频](../../sim2sim/fresh629-start-first-two/random-locomotion-cfg0001.mp4) · [跌倒截图](../../sim2sim/fresh629-start-first-two/random-locomotion-cfg0001.png) |

这两例运行的是官方发布 ONNX 对，seed42、实际生成 OBJ、固定指令 6（高速前进）、gantry 在 policy 阶段关闭。生成 motion 的动作序列属于输入场景来源信息；本次没有逐帧重放该参考动作，也没有验证自主导航或障碍课程完成。`quality_verified=false`、`obstacle_course_completion_verified=false` 保留；1/2 未触发生存阈值不能被改写为技能成功率，更不能计入最终自训学生的验收。

独立验证在新 runc/network-none/无 NVIDIA device 的 CPU 容器中执行；未 exec 活跃 GPU 容器、未启动 simulator/inference/DDS/GPU、未更改 live raw。首次 checker 错把轨迹起点假定为 0，留下原始失败收据与源码于 [initial-clock-assumption-review](initial-clock-assumption-review/correction.json)；依据实际 ACK 偏移改为检查首末 10 s 跨度后复验通过，原生数据未改。未复制完整源树、模型或全部 629 输出；完整冻结清单和哈希供复核。
