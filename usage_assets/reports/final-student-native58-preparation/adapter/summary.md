# 最终两学生本地 58 例验收入口

独立入口 `native58.py` 已实现 status / prepare / run，仅位于 ignored outputs；生产 core、当前 629 cohort 和云端训练未改。**当前仅完成 47 项 Docker CPU 控制面测试及真实 missing-fetch waiting 分支；最终模型实际 ORT/导入/仿真均未执行。**

未来必须显式传入真实 completed fetch attempt：严格核四个最终 ONNX、二十八个 JSON、remote-before/after、materialized models 与来源 SHA。没有 fetch 时 status / prepare 返回 waiting，实际验证均 exit0，未创建 cohort。不会 SSH/fetch 或从目录时间猜模型。

prepare 真正拿到完整模型后才复制 canonical 3297 源文件与1887生成输入、原模型字节和 helper。每个学生在新 runc/network-none/noGPU 短进程内生成实际默认17计划、核两环境 SDK/selected entrypoint/config、CPU ORT30及模型默认姿态匹配；通过后才创建 host-plan.json 和全文件 freeze manifest。当前 plan.json 仅是带未解析最终模型 SHA 的设计索引，不能作为 run 输入。

run 需要 root 明确启动参数，绑定固定本地 UUID、实际宿主 runner/common SHA、共享 GPU mutex 和现 fresh629 的成功/释放收据。mutex 覆盖四个顺序 phase 和 CPU 后验：pure12方向 / pure17场景 / finetune12方向 / finetune17场景。方向保留原8秒/400tick/defaultwall373；场景保留10秒/500tick/defaultwall413，均seed42/startup180且不加wall override。

每 phase 使用新独立私有容器和 own-fullCID 清理，原 commands executor、supervisor、matrix core/receiptvalidator、hostwriter observer 字节不变；只有17scene薄引导适配原629控制门卫。总通过门卫为58例、116正常worker exit0/emptygroups、116 exacthostwriter PID/birth映射和58原视频全片CPU decode。生存启发式失败作为原始质量结果保留，正常运行通过不等于越障或技能成功。

初次CPU测试33pass/1fail为测试断言 Symlink 大小写错误，原XML/log保留；candidate02为41pass。之后补 canonical lock/receipt、actualhostsource 与 pair substitution 门卫，最终47/47pass。终态清理fault tests覆盖marker写失败、observer异常、ownCID停止失败及CLI等待异常，均保留失败并继续后续自身清理。实际新入口尚无最终模型和完整 native 运行实证，此限制不能由 fixtures 替代。

准确CLI模板与58条 case identity 见 plan.json；代码指纹见 code-freeze.json；真实缺模型分支见 actual-missing-fetch.json。
