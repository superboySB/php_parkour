# SDK 0.1.8 统一镜像：实际断网验收

镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f` 由干净根提交 `6cb2ae2` 与 Holosoma `4a0bf04` 的完整冻结上下文构建。3297 个输入文件的字节清单与实际 Docker build 日志保存在 [build/](build/)。没有把宿主机的 outputs、Git 凭据或科学 Python 环境放进构建上下文。

第二次独立容器 [acceptance.json](offline-02/acceptance.json) **passed**：网络关闭、私有 PID/IPC、8 GiB SHM、唯一固定 GPU，只挂只读资产和独立输出/缓存，**不挂宿主源码**。三个运行环境 doctor 与 265 个约束版本全部核对；train/inference 的 SDK 都实际为 0.1.8，两份原生扩展 SHA 可查。真实 Isaac 训练使用 16 环境 × 2 迭代 × 24 步，共 768 transitions，原生阶段 15.756 秒；两轮 checkpoint 的有限、非零权重更新通过。教师 ONNX 的 12 个真实 CPU 推理用例通过；52 个 TensorBoard scalar tag、步骤 0/1 的全部值有限。模型迭代为 1，不能称收敛策略或完整官方训练。

motion/inference 的 pip check 返回 0；train 仍返回 1，保留原有三条上游元数据冲突（两条 usd-core 声明及 dex-retargeting/lxml），没有伪装为全部依赖无冲突。第一次 [失败原回执](offline-01/acceptance.json) 是验收 helper 把 Isaac Python wrapper 的非零提示误计为第四条包冲突；没有启动训练，容器已停止。修正只识别精确 wrapper 提示后新开第二次目录，未改任何原日志。

主 Dockerfile 与两份 SDK 约束已改为 0.1.8。Holosoma 的 unitree extra 硬钉 0.1.6，因此 recipe 用原 booster extra 加显式 SDK 0.1.8；[实际 CPU 包元数据与解析证据](recipe/summary.md) 保留正向安装计划和冲突的负向对照。runtime-locks 记录先行候选镜像的实际 freeze 来源；此处单独保留新构建的实际 freeze，不声称来自未来构建的字节。源码版本说明也区分了之后独立绑定的 eval 报告门卫与本镜像烘焙的 6cb2ae2 版本。

原来的 0.1.6 镜像、正在云端进行的官方训练容器及其源码挂载均保留原状态。新镜像上传另有独立校验回执；本页不凭启动上传就声称远端已经完成。

[原始训练阶段 manifest](offline-02/training/smoke/manifests/teacher-locomotion.json)、[权重差异](offline-02/weight-update.json)、[ONNX contract 与 SHA](offline-02/teacher-onnx.json)、[TensorBoard scalar 清单](offline-02/tensorboard.json) 和原始 event 文件都保留。较大的 PT/ONNX、镜像归档、缓存和 654MB 上下文未重复进入 Git；对应原路径与 SHA 在收据和 publication.json 中说明。
