# 正式 reference629 跨 boot 控制源码准备

本包只保存已审查的源码准备与实际有限 CPU 协议记录，不含未来 native58 终态、正式629合同、CPU计划、原生结果、影片或发布成功收据。

新 [preparation v2](sources/preparation-v2/HOST-CONTROL-V2.md) 封48个依赖：原35中34份逐字节不变，只适配真实跨 boot native58 parent 的宿主 schema；新 [publication v2](sources/publication-v2/HOST-CONTROL-V2.md) 封106个依赖，原52中51份逐字节不变，只更新上游路径、seal 与精确依赖数。原 adapter/cpu_prepare/native_runner/support/frozen科学源、模型绑定及 publisher/restore 科学语义保持。旧 v1 包仍保留。

独立审查：[preparation](reference629-crossboot-preparation-independent-static-review-01.json)、[publication](reference629-crossboot-publication-independent-static-review-01.json)、[共享58宿主控制](native58-crossboot-postreview-independent-static-review.json)。
真实记录包含10个合成 admission控制、12个 shared parent守卫、8个合成/只读 publication控制；合法源码的缺前提 status 明确 waiting/help退出0，错误seal退出1。首次测试的错误消息regex断言失败原件，以及被新direct-parent门卫替代的 aa456/f221初版，均如实保留。

原 e238 parent 的真实 argv 与 actual_wait_returncode 不会被改写为旧 waiter 收据。新58 review仍必须核同fetch模型/60ORT/pose/全部58case/116worker/116hostmap/58原片；正式两个学生各629必须另有真实合同、父进程、CPU/native及2516 worker/hostmap、1258完整解码后才能执行出版门卫。上述未来阶段尚未由本包证明。

四最终 ONNX 与实际回传/CPU预检另见[模型与CPU原件](../reproduction-20261015/student-transfer-cpu-actual-02/README.md)。未来准确CLI依赖及明确未解决参数见[future-cli-dependencies.json](future-cli-dependencies.json)；固定源的原绝对工作区仍有约束，恢复本包不会自动运行科学作业，也不替代完整5184源码、资产、模型、旧历史运行或新物理验收。

所有已列新源、初版与实际控制/审查原件按工作区相对路径无损归档，raw-inventory.json 保留原 bytes/SHA/完整mode。Git只保留executable bit；标准库restore会恢复原完整权限。

```bash
python3 cloud888_report.py restore --input . --output /tmp/reference629-sources-new --manifest-sha256 <外部已审查的本包sealSHA256>
```

使用全新目录，不覆盖现有源或模型。封包后的Git权限归一化副本实际恢复证明见[独立恢复旁包](../final-student-reference629-crossboot-source-restore/README.md)。
