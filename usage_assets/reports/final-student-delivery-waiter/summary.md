# 最终学生的自动回传和本地验收交接

[冻结准备源码与准确CLI](preparation/README.md)、[55项Docker CPU及冻结合同](preparation/summary.json)、[独立预启动审查](preparation/independent-review/summary.md)、[root实际启动身份](root-arm/launch.json)、[首次真实状态](root-arm/initial-state.json)、[实际启动后观察](root-arm/initial-observation.json)。准备阶段的 not_armed 描述保留原字节；实际启动由独立 root-arm 收据证明。

2026-10-10 11:03:25 UTC（北京时间19:03）root已实际启动单实例PID1121672，PGID/SID1121672、出生ticks105819944；固定合同与waiter源码SHA、真实argv及boot_id均封存。第一次真实SSH status正常exit0、transport session为空，返回waiting且16正式阶段仍阻塞。fetch/prepare/run均false，模型和native cohort目录未建；本地Docker ID集合前后不变。

此进程每600秒只读等待；真正ready后仅一次回传4ONNX+28JSON，检查SHA/来源，再等待现fresh629真实成功/停止、固定GPU mutex和GPU空闲。随后由冻结native58入口执行真实60项CPU ORT及两学生共58项native验收。通过门卫为58case/116正常worker与空组/116精确host映射/58原视频完整解码。当前这些真实最终模型步骤均未执行，不能由synthetic tests替代。

只读查看运行中的准确状态：

```bash
python3 -m json.tool outputs/research/final-student-delivery-waiter-preparation/execution/state.json
```

此批已armed，勿再次执行watch、手工fetch或另起final58。唯一singleton锁和existing execution拒绝自动重启；已开始步骤的失败、partial和所有原日志保留，不自动尝试另一目录。取消需核对launch出生身份再SIGTERM；native58拥有自己的GPU/容器finally。非合作transport会failed并留待人工核查，不承诺已回收；SIGKILL/host crash不在已测范围。准备/源码恢复前提还包括[final58包](../final-student-native58-preparation/summary.md)，本包不是独立Docker环境。

[first-poll/](first-poll/)保留第一次已退出status helper的三个原文件。root-arm的watch.stdout/stderr只封存首次观察时的字节，运行中原文件及execution/state会继续变化；本报告不把它们视为未来终态。当前活进程文件仍位于ignored outputs目录，不覆盖本报告。

[11:00 UTC两任务实际活进程](active-jobs/summary.json)确认原cloud官方driver/train与local629 wrapper/simulator仍存活；local固定快照158completed/1running/470planned。同期[TensorBoard原scalar快照](active-jobs/official-scalars.json)首教师step10315，四选定tag全部历史样本有限。仍未完成正式训练、629全量后验或最终58项验收；quality/course没有被推定通过。
