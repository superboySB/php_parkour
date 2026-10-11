# 正式学生全629参考指令：准备记录

这是可恢复的源码准备与只读状态记录，**不是正式学生的物理验收结果**。两种正式学生仍需在真实最终产物齐备后各执行629配置：合计1258例、2516个worker、2516份宿主writer出生映射和1258段视频全片解码。公开ONNX已经完成的扫描不能代替这两种自训模型。

原58计划每模型包含12个平地方向与17个代表场景，覆盖全部17场景名称，却只选17/629配置；每模型另有612配置未选。其中12个平地方向项每项8秒；只有17个代表场景项使用固定前进10秒，9个所选原参考片段长于10秒；两个low-speed roll参考还含backward code11。新增范围保持原58不变，另按每份原NPZ完整15维、50Hz逐帧指令执行全629，而非运动学回放。[实际源码范围报告](proofs/formal-student-reference629-coverage-gap-01.json)与[root核对](proofs/formal-student-reference629-coverage-gap-root-verification-01.json)保留具体17行和来源。

已封存35份冻结依赖（1,802,261字节）、[原内层manifest](preparation/preparation-manifest.json)、[root源码审查](preparation/root-review.json)、[独立源码审查](preparation/independent-review.json)与完整diff。不可变科学文件是原reference core/helper/matrix，未来模型SHA、CPU计划SHA和合同尚未绑定。[原计划](preparation/plan.json)、[原CLI与门槛说明](preparation/README.md)和[恢复映射](restore-map.json)说明如何继续。原README/manifest的“未调用”描述的是生成准备包时点，以下实际status是之后发生的有限操作。

2026-10-11 19:50:26 UTC，仅缺少显式前提的`status`分支实际退出0、返回`waiting`；缺少transfer、native58_base、真实58父wait及独立后验等6项参数，未获取锁、未创建cohort、未启动Docker/native/GPU。保存[真实执行回执](preparation/actual-status-check-01/execution.json)、[原stdout](preparation/actual-status-check-01/stdout.raw)、[原stderr](preparation/actual-status-check-01/stderr.raw)、[独立核对](preparation/actual-status-check-01/independent-review.json)及[root准备完成记录](proofs/formal-student-reference629-future-preparation-review-completion.json)。AST语法检查与源码审查不是科学测试；此处未声称实际CPU计划生成、ORT或原生执行通过。

继续前必须有真实完成的4ONNX+28JSON选择性回传，以及同一模型pair的58例实际终态、60ORT、部署姿态/镜像/源码绑定、唯一`logs/run-*.json`真实child.wait0、空session和原日志SHA。`state.json`完成标记不能代替父wait。另需独立58实际后验；未来`prepare`生成的新两套629 CPU计划、控制源码、模型和合同必须再经root及独立审查，之后才由root显式执行。用户已有授权；root flag是内部操作门槛，不是新增用户审批。

恢复时，把`preparation/`原字节映射回原`outputs/research/final-student-reference629-preparation-01/`；仅可在目标不存在时复制，或核对已存在文件完全一致，不覆盖活等待器、原58控制、partial或历史证据。5184文件大源码、原629输入/模型、Docker层和真实未来收据没有复制，准确依赖见[restore-map](restore-map.json)。旧公开模型及旧7729计划不能充当正式模型输入。当前包不自动衔接任何任务。

原CLI中的`status`只读；真实`prepare`会创建隔离CPU容器，`execute`才调用GPU/native并持有原UUID锁。首次失败保留，不自动重试；所有阈值与失败均须保存，完成执行也不证明技能、课程、收敛或实机成功。`quality_verified=false`、`obstacle_course_completion_verified=false`。

全部包内依赖由[外层publication-manifest](publication-manifest.json)绑定。原始manifest及所有raw报告未改写。本包制作仅使用宿主标准库复制、哈希与本地链接检查，没有运行任何控制入口或科学任务。
