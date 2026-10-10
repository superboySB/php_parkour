# RO 源码 + 独立 RW robot assets：单源真实 Isaac 验收

初始化与评估接口通过，技能质量失败。Root 使用统一 SDK0.1.8 镜像运行原 teacher iteration500，对原 locomotion cfg0000 的完整920帧 source 做一次 first attempt：实际158个策略步（3.16仿真秒）后首次跟踪终止，failed resets=1、timeouts=0、reference boundary=false、`quality_verified=false`。没有完成920帧 source，更没有完成296源/888次覆盖。

原PT SHA `d38d7c626fab4750e40eacfc05bc8178a56141055a569f9abca9f71c7584e87a`，原source NPZ SHA `fef9f7ce29d01c8e1441ab7f99a142bf13a76a26cc7598361d927626d96c3ecc`。1环境、1地形变体、seed42、cap920；没有裁剪原source、修改关节/方向标签或放宽失败阈值。实际四项tracking指标各158有限样本，逐行误差均值/最大值/p95与quality JSON一致，实际动作与root状态全部有限。原模型仍是未收敛的中间检查点。

新schema2 plan/case绑定五个harness源SHA。readonly挂载的完整3298文件源码＝canonical6cb2ae2构建的3297文件＋六个显式runtime集成overlay（新asset helper增加一个文件）；镜像内原源码和新挂载源码身份分别记录，不能把它称为重建后的新镜像。镜像精确ID为`sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`。

35个原始URDF/mesh按SHA复制到本cohort的`/outputs/teacher/runtime-robot-assets/robots`，公有asset_root override经真实原生配置解析及保存YAML再次核对；USD实际生成于该独立RW目录的converted_rank0_pid45中，原Python源码仍RO。运行前后3356个封存输入（含3298源码、原PT/source、35份复制资产、CPU原始证据）SHA全部不变。新生成USD只保留SHA，不将23MB模型副本或大PT/NPZ拷入Git。

A/B两次原生零动作warmup与policy分列。两个缓存刷新均使用原生MotionCommand.step同一AST公式`155892b6ef1326d34b9bed8adcee2320681efc38df55dcb03b955088cca864ea`；clock、motion/expertID、boundary及Python/NumPy/Torch CPU/CUDA RNG前后都未改变。初始化与attempt warmup从reference0推进1；真正策略帧为1..158，完整可作用区间1..918，末919为边界sentinel，不能声称frame0及末标记受策略控制。

Root唯一实际GPU容器`8114edab64443cf1c9b74ef42534b1dffb47c682137e4221edfb6b00f60b0def`已正常停止；driver返回0，后验另外使用runc/networknone/无GPU的独立CPU容器完成。3段实际原生MP4（.02/.02/3.18秒）全部全片解码；两份TB events均可读取，其中Coverage日志13个scalar全部有限，原生评估日志无scalar，未把空日志称作有限数据。

[最长实际原片](../../isaac/source-coverage-ro-assets-pilot/teacher-iter500-source000.mp4)（3.18秒，包含原生录像时间边界，与3.16秒policy时间分别记录）及[中点实际截图](../../isaac/source-coverage-ro-assets-pilot/teacher-iter500-source000.png)。截图可见G1仿真与原生teacher叠字`Commands: Not available`；不是实体机器人或学生方向控制证据。

原始quality、轨迹、实际YAML、native日志、plan/case、资产manifest、源码overlay、CPU/host启动与停止回执按原字节保留，manifest逐件绑定。旧GPU三例、旧raw、云端长训与watch冻结树均未改动。本次只证明新的RO源码/RW资产合同可完成这一个真实评估接口，不替代正式模型训练、全部源覆盖或实机验收。
