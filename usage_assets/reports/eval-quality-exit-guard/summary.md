# 评估必须产生有效报告

本轮五个非默认教师的首次实际 Isaac 重载都在 URDF 转换阶段失败，但上游 eval 捕获异常并返回了 0；没有质量报告。[原始失败证据](../teacher-presets-reload-ro-failure/summary.md) 保留这些初始化失败。

`eval_quality.py` 现在拒绝覆盖已有报告，绑定 checkpoint 初始 SHA，在原生 main 正常返回后要求新生成的 regular quality.json、schema1/completed、同一 PT 路径和 SHA、正整数环境数/控制步数、finite_actions/root 为 true。缺少报告或无效报告将抛异常并非零退出。它不把发生跌倒的实测质量记录改成通过：例如 failed_resets=900 且 quality_verified=false 的有效实测报告仍被保存。

Docker 内 **14/14 CPU 测试通过**；[原始 JUnit](raw/tests.xml) 与 [日志](raw/tests.log) 保留测试。覆盖了上游返回却没有报告、8 种无效字段、checkpoint 中途修改、拒绝覆写历史报告及正常回调清理；原来的张量指标和 atomic report 用例也通过。这是报告/退出门卫检查，实际五教师重载和长程策略质量另行验收。[应用后的精确源码](source-after/scripts/research/eval_quality.py) 和修改前字节均封存。
