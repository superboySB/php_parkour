# 最终功能覆盖 ledger（只读）

从用户原目标、当前四份README/DEPLOY及note/usage提取29项要求；逐项声明行号、实际证据路径/scope、缺口和下一动作见[ledger.json](ledger.json)。机器清单同时列出8个preset、5组有序数据、17场景及29技能，不以已成功项缩小范围。

新增可行动缺口只有两组，已获root确认并分派准备：

| 缺口 | 已有证据及不足 | 最小补验 |
|---|---|---|
| **P05/P06：完整命名键派发与Backspace reset** | [v5真实GUI](../../../usage_assets/reports/native-keyboard-gui/independent-review.json)仅有8/9、]c=o i和w低/高速；[12方向闭环](../../../usage_assets/reports/sdk018-directions/independent/report.json)使用API，不能替代`s/a/d/q/e/z`的真实键事件。DEPLOY:91明确Backspace，但无实际reset回执。 | runtime复用v5私有Xephyr/PTY准备一个短批，逐键down/up、切速、返回stand、目标viewer Backspace前后真实state/time/depth及正常退出；无需场景×按键组合。 |
| **T08：原生训练从PT继续学习** | [45项恢复合同](../../../usage_assets/reports/official-driver-audit/audit.md)明确child是替身；真实eval/export加载PT不能证明optimizer/iter续训。[22-stage smoke](../../../usage_assets/reports/training-cloud-final/summary.json)未提供该独立收据。root/runtime确认暂无可引用记录。 | validation只读准备teacher/pure/finetune三类baseline2→target4，独立新output记录PT/iter/optimizer恢复、续训有限非零更新及新TB步，再核合法skip；不要求轨迹逐比特恢复。 |

两组实际native/GPU执行均须等现629正常终态及固定UUID锁释放。只读协议准备可现在推进；不启动第二份官方训练，不改活控制器或旧raw。

此前明确缺口已关闭：[数据库全部11控件/27动作](../../../usage_assets/reports/database-gui/summary.md)、[Viser配对保存与Tk Start/End](../../../usage_assets/reports/gui-workflows/summary.md)、[show-depth真实100帧](../../../usage_assets/reports/depth-gui/summary.md)、[五非默认preset原生重载](../../../usage_assets/reports/teacher-preset-reload-sdk018-v3/summary.md)。本轮未发现其它已查实且独立于现任务的新命名入口遗漏。

剩余主体仍是原有范围：

- **official16**：五教师4096×20000、两学生2048×10000/30000及评估/最终导出；smoke不是正式训练。
- **cloud888**：最终三策略各296source首次尝试；三个pilot均失败，不能当全覆盖。
- **fresh629**：629真实终态、1258正常worker/hostwriter、629全片decode、5206冻结/2266输入和全部失败/阈值原字节发布。固定计划只有580不同OBJ SHA，不能写629独立几何或技能成功。
- **final58**：真正fetch最终4ONNX+28JSON后60ORT及两学生58native/116worker/116hostmaps/58decode；准备CPU/waiting不是完成。
- **云默认SDK018**：candidate上传/load已完成，默认训练环境仍016；只能待official/888/watch安全结束后接入。
- **12历史golden**：原私人mm_hs数组/环境不可得；保持失败，不刷新SHA。
- **实体G1/D435i**：没有实际传感器/标定/动力学/硬件运动验收，仿真深度和SDK占位XYZ不得伪称实机数据。

此外，高层“自主长程多技能越障成功”目前**未成立**：已有reset/跌倒/课程失败是已测失败，不是尚未测试；必须用最终质量及原片判断。正式迭代、正常退出、生成或参考动画均不能自动证明成功。五训练技能组也不能推出学生已学会全部29参考技能。

本轮单次本地文件观察：fresh629 `{'completed': 349, 'running': 1, 'planned': 279}` / running；waiter poll `7` / waiting，fetch/prepare/run均false，保存的remote status仍16阶段阻塞。时点/SHA见ledger；动态原JSON未另存，没有重验case或查询远端。

未扩张的范围：G1项目不增加飞机；用户排除W&B；不新增原始mocap采集、完整OmniRetarget、额外全量多GPU、任意全组合或上游Holosoma其它机器人/ROS功能。

本轮只读文档/源码/本地报告；未运行入口、测试、SSH、Docker、GPU、DDS或daemon，未改主文档、源码、Git。HEAD与本地origin/research同为`b5095ba390c6`；这不是本轮联网确认。既有报告按自身版本/scope引用，没有重验全部旧SHA。
