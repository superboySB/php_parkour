# allkeys / Backspace 冻结候选独立只读审查

结论：未发现阻塞性的静态代码问题；真实 GUI 验收仍未执行，不关闭真实全键和 Backspace 缺口。

审查对象为 `native-keyboard-reset-allkeys-preparation-01` 的14个 Python 文件。它们与 codefreeze、candidate02 两份前后指纹及保留源码完全一致；14份AST均可解析。76项 preparation manifest 共755,781B逐项匹配；旧v5的11份源文件和 source-before 均保持原字节。

保留 CPU 原件为 candidate01 45/45、candidate02 46/46；检查了 XML、准确源码副本、runc/network-none/GPU-hidden容器创建/运行/停止身份和实际退出0、删除收据。本审查没有运行任何测试、helper/controller、Docker、SSH、native/DDS/GPU或daemon。

原 render 仅调用一次，新增观察只读完整物理状态。真实 BackSpace 请求后必须观察单次time下降、qpos变化及后续physics/time/control/depth推进；qpos0误差和nkey被保留。该门卫支持当前明确限定的物理数据变化，不证明qvel/ctrl为零、完整默认/keyframe相等，或策略历史/SDK/gantry重置。Backspace之前已进入o damping，因此后续tick推进不得称主动策略成功恢复。

六方向LOW/HIGH的真实XTEST按住/释放、各≥10原生one-hot控制tick、release→0与held-w期间独立z非零→0 dispatch均有实际执行门卫；7/8/y/g/Backspace只发向私有自有窗口。录制要求全部0–11标签各≥10帧且无保留槽，仍是原生带XYZ占位的记录，不是世界轨迹/训练bundle。

启动受真实完整fresh629 driver/observer/CPU0、1258worker/629完整解码、两actualCID停止、固定UUID独占flock、GPU compute idle和root flag限制；两原生进程需真实SIGINT后main/atexit各一次、wrapper0/组空、精确host birth映射、全部MP4全片decode0。任何真实失败都应保留并拒绝通过，不改变旧v5、运行中629或waiter。

详细行号、14源前后SHA与证据哈希见 [review.json](review.json)。must-fix：无。下一步仅由root在前置条件真正满足后授权新的独立实际cohort。
