# 三类原生续训真实验收

本包是16环境、teacher/Pure DAgger/DAgger+PPO各baseline target2→resume target4的实际接口/优化器状态连续性验收。真实训练共6次，宿主实际观察到6个wrapper和6个不同的Kit Python子进程出生/namespace/祖先链；每次原生训练返回0并回到仅init/sleep的独占容器空闲状态。历史已完成3步 + 新continuation15步组成原18步，3类各原生resume、ONNX CPU检查、达目标skip均通过。既有33个CPU准备测试仍属于单独[准备包](../native-resume-acceptance-preparation/index.md)，不计作这6次真实训练。

教师optimizer严格40→60→100，两个学生严格16→24→40；原生恢复从保存iter1继续，首份新checkpoint仍为iter1，最终iter3。故不能把同名model_00001误当原baseline字节，也不能称只新增两轮。原科学读取同时检查PT迭代/配置、optimizer参数及moment形状/步数、非零有限权重变化、教师冻结、学生mixed std原语义、真实TB更新以及auto-export ONNX和不启动native的skip。它不证明bitwise继续、训练收敛、正式7模型完成或策略质量。

两次失败原件永久保留：最早教师baseline/archive/resume三步真实0后，第4 CPU读日志过度要求close之后的`Training shutdown complete.`而失败，原父wait1/自有容器已停止。原Isaac `simulation_app.close()`可能直接终止Python，所以新adapter仅修改原科学模块对象的native_load_log：精确原生checkpoint加载 + shutdown-begin + 真实native0/Kit已退出。教师有optimizer成功INFO；学生源码成功时没有该句，仍用原严格optimizer实质计数。sidecar明确close()返回未证明，不伪造缺失日志，不覆盖失败报告。

第一次continuation仅在GPU空闲门卫退出1，未建容器/未建actual/admission/未训练；当时占用原因未知，未保留同期compute PID快照。Root随后另存真实UUID空闲查询，显式第二次启动同冻结helper，actual-parent-02最终wait0，两个父回执都保留。第二次续跑复用教师已0前三步，从第4步开始执行15步，没有重训或覆盖老师。原session54334=143、原629观察缺口及四例补验恢复合同仍原样保留。

[独立验收](independent-review.json) · [实际continuation收据](continuation/actual/receipt.json) · [最终真实父wait0](continuation/actual-parent-02/process-exit.json) · [第一次GPU预检父wait1](continuation/actual-parent-01/process-exit.json) · [原教师失败父wait1](failed-teacher-attempt/actual-parent-01/process-exit.json) · [实际TB标量](tensorboard-scalars.json) · [分块还原映射](large-file-restoration.json) · [SHA清单](publication-manifest.json)。三类独立报告链接见independent-review的labels；原始TB events、训练/导出/skip日志、18step stdout/stderr与进程流、native exec receipts、baseline归档、固定输入/源清单均保存。

PT/ONNX仅保存原科学报告与baseline归档所需的闭包，不复制3298源码全树、35个机器人mesh、缓存或其它未使用中间checkpoint。大于25,000,000字节的原PT/进程流按连续offset分块，原wholeSHA与每块SHA完整保留，无压缩/重编码；重复大文件只共用相同wholeSHA的块。运行 `python3 -B restore_large_files.py --package . --destination /绝对路径/新还原目录` 可重建大文件到restore_relative，对已存在文件拒绝覆盖。原报告的容器绝对路径不重写；需按actual-output与原source/inputs/controls映射恢复环境，不能在活cohort上覆盖。原prepared状态和CPU-only措辞是历史准备代理范围，不表示需要再向用户申请训练授权。
