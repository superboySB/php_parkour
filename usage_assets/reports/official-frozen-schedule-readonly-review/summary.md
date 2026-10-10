# 官方冻结日程的独立只读审计

**未发现最近本地 RO 资产、eval 退出门卫或 retry 修复缺席会必然阻断当前官方日程的证据。应继续保留正在运行的原 driver。** 本审计不声明正式训练、16 阶段或最终技能质量已完成。

实际 SSH 采样时间：**2026-10-10 10:23:03 UTC**。仅使用服务器现有 Python 标准库读取既有文件、`docker inspect/top`；没有 `docker exec` 进入活跃 GPU 容器，没有安装、重启、信号、写服务器文件、改变 bind、启动 GPU/DDS/仿真。[原始 SSH stdout](remote-stdout.json)、[stderr](remote-stderr.log)、[调用收据](remote-launch.json)、[采样 helper](collect_remote.py)、[机器报告](report.json)。

**身份保持一致。** 与已有 10:09 升级后观测逐字段比较，官方容器 CID `f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db`、镜像 `sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd`、init PID3760878、StartedAt `2026-10-10T04:01:22.880471283Z`、全部挂载，以及 native PID3836908/3836987 的出生时刻/PGID/SID/argv 均一致。[逐字段比较](identity-comparison.json)、[先前原始观测](prior-observation-1009.json)。这是两次实际观测的一致性，没有宣称持续监控覆盖了其间每一时刻。

正式源仍为 `0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab`，pipeline SHA `5f85596f40b796b8626e05058d54824d93ba97e3788129e1763ba5c461284adb`，旧 eval helper SHA `87a6bb555cf2260b74f878d98c9eb743b8484dff3686478508d01e61a9869d80`；新 helper `5cbb7f…` 与 retry archive 逻辑没有进入此活跃源。原部署清单中的 **1903 个文件 SHA256 全部仍匹配**。[1903 SHA 报告](source-1903-sha256-verification.json)。只校验原清单，不把新增转换缓存算作源码清单修改，也不声称整个目录树只读或没有额外文件。

采样时唯一阶段 manifest 为 `teacher-locomotion: running`；现有日志最后完整迭代行为 9308/20000。实际训练 argv 为4096环境、20000迭代、seed42；这只是日志进度，不是新增 PT/科学质量验收。新 watch 的既有状态为 `waiting`、`gpu_started=false`，其余15阶段 manifest 尚不存在；审计没有触发 watch 或传输模型。

## 为什么本地 RO 缓存失败不能直接套用

实际官方 Docker 的 `/workspace/php_parkour`、`/data/assets`、`/data/cache`、`/outputs`、日志与 outputs 别名挂载均为 **RW**；原 cloud deploy 也未给 source bind 添加 `:ro`。保存配置为 `robot.asset.asset_root=@holosoma/data/robots`、`urdf_file=g1/main_mesh_arm_collision_halfspherehand.urdf`、`usd_file=null`。Isaac 原源码在该根下创建独立 `converted_rank<rank>_pid<pid>`，强制转换。

SSH 实际观察到此资产根已有 **24 个转换目录、120 个 USD 文件**，原机器人源文件仍包含在1903 SHA匹配清单内。因此本次没有“converter向只读源目录写入”的同一触发条件。[保存配置](saved-configs/holosoma_config.yaml)、[原转换源码296–358行](original-source/thirdparty/holosoma/src/holosoma/holosoma/simulator/isaacsim/isaacsim.py)、[本地首次RO失败原报告](../teacher-presets-reload-ro-failure/summary.md)。后置888使用另外冻结 RO source/RW35资产合同，与这次历史 RW 部署分别记录。

## 原生返回0之后，旧 pipeline 仍怎样判断

[旧 helper187–208行](original-source/scripts/research/eval_quality.py)没有本地新加的最终 CLI 门卫。但它由[旧 pipeline380–418行](original-source/scripts/research/train_pipeline.py)调用后，pipeline会独立要求：

- 新的非空 MP4，ffprobe duration>0；quality.json 的 mtime 属于本次执行，schema/status/PT SHA一致。
- 64环境×3000控制步；action/root finite；四个 tracking 指标各192000 finite样本，mean/p95/max有限。
- 质量报告的视频属于本次新视频；视频 SHA 与非空 TensorBoard events 可对应，产物写入 manifest fingerprints。

子进程即使返回0，缺失或不匹配的产物仍让 `status=failed`，pipeline以非零退出。**manifest 的 `returncode` 字段记录原生子进程的0，可能与 pipeline 最终退出1同时存在；不可只读该字段判断通过。** 原 shell 有 `set -e`，会停止后续阶段；watch 要求所有阶段 `passed`，还复核实际文件、来源与最后 marker/进程/锁/GPU状态，不会仅凭 child rc0 放行。

这与五 preset 的直接 helper 曾返回0但没有报告是不同调用链。旧官方 pipeline 已有[20迭代官方PT真实缩小评估](../official-pilot-quality/summary.md)及[两学生最终smoke](../training-cloud-final/manifests/eval-student-pure.json)作为其接口执行证据；均不是最终官方质量通过。

## 后续真实顺序与边界

[原 shell16–24行](original-source/scripts/research/run_official_acceptance.sh)依次执行：五教师各20000轮 → 五个最终训练 ONNX 的 CPU检查 → 五教师各64×3000评估 → pure学生10000轮/评估/独立导出 → finetune学生30000轮/评估/独立导出。学生训练默认2048环境，三个地形变体，按固定五专家顺序读取已完成的教师；保存间隔500。

教师图必须与最终 PT 同名，iteration/registry metadata 匹配；teacher eval 明确 `export-onnx=False`，其1variant不会替换训练64variant图。学生 eval不代替export；独立export从自己的PT恢复纯/混合配置、五teacher slots和迭代，构建环境后生成 fresh pair，再运行30组 ONNX checker/ORT检查。[教师validator](original-source/scripts/research/validate_teacher_exports.py)、[学生export110–168行](original-source/wbt_training/training_runs/export_distill_onnx.py)。这一顺序没有被最近本地修改替换。

真实边界是：原 shell 没有自动 retry；任何未来 eval/export/教师图检查失败会停止下游，而 watch只观察、不修复。坏质量但数据有限不自动成为执行失败；`quality_verified=false`与failed reset计数仍需人工/后续覆盖评估解释。最终训练图缺失或损坏时不能拿1variant eval图代替原64variant图。这些是源码已明确的恢复/质量边界，**当前没有观察到此类后期失败**。

## 保持训练不动的最小恢复原则

现在不改、不重启原 driver。如果以后实际某阶段失败，只在原 shell/native进程结束、官方锁释放、固定UUID GPU空闲后，保留原日志、manifest、quality/TB及失败输出的字节和SHA，再准备独立冻结的“缺失阶段续接”收据；不重新训练已完成教师，不缩短默认日程，也不将不同专家来源混入旧输出。

旧 pipeline仅归档旧manifest，重新评估会写固定quality.json/TB目录；后续确需重试时应先保留旧quality/TB。若选择新的 RO容器，须采用已审资产合同和明确支持asset override的入口；不要盲用没有asset-root选项的原pipeline。要让watch最终放行，必须真实满足16阶段、7个canonical最终PT及相关ONNX/质量产物、进程/锁/GPU条件；不能补一个“passed”manifest或单独追加终点marker来绕过等待。替代 completion receipt/续接方案应交root审核后再实施，本审计未部署任何恢复任务。
