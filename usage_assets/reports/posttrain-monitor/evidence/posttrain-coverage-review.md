# Post-training coverage final independent review

结论：最终冻结版本未发现未解决的实质阻塞。生产源码 SHA `00b7ad8d215f04d603ae696cafa613d15cd1287066a1387ddde376ba7203dff0`，测试 SHA `91150cb9dbb81126df446fbe004c8531a3ff16e11ab582afd2f0a86e8fc383a7`；独立 CPU **61/61 通过**，测试前后两份源码哈希均未变化。完整官方训练完成及其后的 **296 sources × 3 policies = 888 次 GPU first attempt 尚未由本审阅执行**。

## 已核实的门卫

- `observe:351`：16 个 canonical stage 未全部通过即 waiting，不查询 GPU、不启动容器；dry-run 在目录和锁写入前返回。selection identity 包含绝对宿主机 coverage 输出路径，fresh cohort 的容器名及挂载身份同步改变。
- `process_gate:231` / `verify_frozen_source:264`：官方 manifest/log 绑定旧训练容器实际挂载；旧官方源与新独立评估源各自核对 manifest 全部文件 SHA。不会替换原训练源、停止原训练容器或写入官方产物。
- `container_state:319`：精确绑定镜像、role、entrypoint、cwd、完整四挂载及 RO/RW、无网络、命令和唯一 GPU UUID；拒绝额外嵌套挂载。
- `scientific_check:432` / `compare_frozen_experts:485`：七个最终 PT 检查迭代、env、variants、seed、save、rollout、minibatches、epochs、有限策略权重和有序五专家；deterministic actor 完整 keys 与原生 normalizer buffers 逐 tensor 比较，PPO action std 单独排除。
- `verify_gpu_mapping:625`：CPU 预检通过且持有官方锁后核验 NVIDIA 实际可见 UUID 和唯一 cuda:0；本次 CPU 审阅未执行真实 GPU 门卫。
- `attempt_case:560`：既有通过/失败 receipt 原样保留；中断或歧义 first attempt 记录 execution_failed，不自动再试。resume 仅推进未尝试 case。
- `verify_finished_batch:382`：888 个唯一 case、三个 296-source plan、原 receipt、保留产物 SHA、最终计数及容器退出状态须一致。

## 两个重点确认

直接提取最终生产 `translate` AST，对三份已有真实 repaired singleton（teacher/pure/finetune）报告执行 host stdlib `validate_native_report`，全部通过。函数递归构造新 dict/list，只在内存映射路径；原对象、原 case/quality JSON 文件及 SHA 前后不变。此处使用已有三份报告，不代表未来 888 cohort 已执行。

watch 的全局 monitor 锁与 official 锁没有循环依赖。host 启动 child 后释放短期 official 锁，child 最多等待 60 秒接手同一 inode，并在整个 CPU/GPU 阶段持有；child 不等待 monitor 锁。watch 在 own child 运行期间暂时 waiting，child 退出释放后下一轮继续。

## 证据与限制

- `posttrain-independent-frozen-tests.xml/log` 及 `posttrain-independent-frozen-tests-provenance.json`：最终独立 61 项 CPU 测试和前后源码 SHA。
- `posttrain-host-translation-proof-frozen.json`：最终源码 AST、三份真实报告验证及原文件 SHA 不变证明。
- `posttrain-frozen-expert-schema-proof.json`：此前真实 smoke PT 的两学生 expert0 八个 MLP tensor（398365 元素）与 teacher 同 key、bitwise 相等；CUDA 未初始化。本证明不覆盖未来官方最终 PT。
- `posttrain-independent-identity-tests.xml/log`：保留旧候选测试漏 mock Docker inspect 导致的 60 pass / 1 fail。仅测试 fixture 已修复，最终 61 项独立通过；没有安装 Docker CLI 或宿主包。

原生官方 shell 没有退出回执，工具如实保留 `driver_exit_status=null`，用 16 个通过 manifest、最后 marker、无活动旧子进程和官方锁已释放共同判断。完整官方日程及 888 次 GPU 覆盖仍待真实执行；本审阅未 SSH、未占 GPU、未改云端或冻结源、未提交代码。
