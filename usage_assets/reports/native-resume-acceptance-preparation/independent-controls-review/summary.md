# Native resume 控制面最终只读审查

**最终冻结版通过只读审查，未决 must-fix 为 0。** 此结论仅覆盖控制与 CPU 准备合同；6 次真实 native baseline/resume 尚未执行，不能记为 resume 已验收。

[review.json](review.json) 保留逐路径/行号、冻结 SHA、全部核对结果及草稿问题的发现和修复。最终 `resume_evidence.py` 为 `41133f5be5900ebd3ffc291af670c1a89ff26889ad5d4de07106b167cf9df6a0`，adapter 为 `1e062cbd585681fd28febf3d302370428c60b697cd861460c1edf8c6b8045f45`；contract 为 `ab7d1cfd5618ed53d13078a85fe1f52ad0cbd2115b8901e2d393964e8435b593`，root-commands 为 `d573aa8075fe70f9264a20d6f6db8051c121fd3270170e728d5ec2fc2fa60996`，readiness 为 `e9f9f66516b64ebf4eb2630e043b222497dc159fc98f618332beee53344054f2`。

本次独立使用 stdlib 只读解析/哈希，核对了 3298 个 source 文件及实际 regular file-set、380 个执行源、201 个 registry 输入、35 个 robot 源/副本文件。72 件 preparation-manifest 记录逐大小/SHA 匹配。contract.host_output、root mount/create argv、实际 CPU launch 及 readiness 全部统一为 `run-output-final-frozen`。记录的 CPU XML 为 33/33、0 failure/error/skip，三 preset 真实 CPU 预检显示仅 public asset-root 改变，未启动 CUDA/native；本审查没有重新执行这些测试。

草稿发现的两个真实阻塞均已修正并保留历史说明：native activation 后 HSSIM 环境必须核 canonical train-python，父 pipeline 才核 adapter；INFO 级载入/正常 shutdown 标记改读原生 `train.log` DEBUG sink，baseline 也归档该日志。最终新增 CPU 回归与冻结源码一致。

科学门卫落实：全部 optimizer 参数必须有 state，教师40→60→100，学生16→24→40；mixed std 无豁免，必须 LR0、三 PT 的 std 权重同值。frozen teacher/normalizer 在 baseline、resumed1、final3 逐 tensor 同值。PT 顶层 iter/iteration、嵌入 config、exact target、原始 resume PT SHA、唯一固定教师 SHA、新 run parent、有限 loss/TB 步数、final12/30/30 ORT、skip 不启动 native/不修改输出均有相应拒绝条件。

**GPU mutex 与 Docker 生命周期仍由 root 人工执行，不由这两 helper 或 JSON 自动实施。** root 的18条结构化命令为6 native+12 CPU，必须全程持同一 UUID mutex；先核 fresh629 完整正常 CPU 终态、其 GPU/CPU 两个 own containers 已停且无 native 残留、GPU 空闲；只创建独立新 CID并核 image/mount/UUID，逐次保留真实 Docker exec rc、stdout/stderr、inspect/top 和 namespace→host birth，异常也仅停自己的 CID，最终无子进程/容器已停后才解锁。adapter 收据中的 PID 属于 pre-exec wrapper，不能自动当作随后 Kit Python 子进程 birth。

此次未运行入口、测试、项目 import、PT 加载、Docker、SSH、原生仿真、GPU或 daemon；未修改冻结源码、历史 raw、正式训练、当前629、waiter、项目文档或 Git。结果不证明收敛、五专家完整日程、RNG/物理连续逐位等价或真机技能。
