# 正式最终学生 ONNX → 本地 MuJoCo：待执行方案

这是只读设计，当前正式 pure/fine 最终模型尚不存在；未传输文件、未启动仿真或训练、未修改 tracked 源码及正在执行的依赖。2026-10-10 06:58 UTC 独立观察仍是第一教师 step3872/20000。公共 release 学生的 629 次场景任务与本方案的自训模型是不同来源，不能互相计数。

最短完整闭环为两个最终 pair 各 **12 个独立平地指令 + 17 个代表场景 = 58 次物理运行**。全部 seed42，每次 10 个仿真秒；平地每指令 fresh simulator/policy，场景每类仅一个合法完整几何。它覆盖公开部署指令与场景类别，但不等于 629 个几何配置均已用于自训策略、不等于逐参考动作跟踪，也不自动证明障碍通关。

## 1. 云端选择门卫与来源

使用 `/outputs/official-full` 的正式 16 阶段终态与已部署 posttrain monitor 的 CPU 门卫。没有必要等待云端 888 次物理尝试结束：**CPU `cpu-ready.json` 成功后，两最终 ONNX 可只读回传，本地任务可与云端 888 并行**，机器/GPU/DDS 均独立；本地仍须等待现有 629 任务结束。

必须核验：

- 16 个 manifest 均 `profile=official,status=passed,returncode=0,finished_utc` 非空；官方 driver 原生进程结束、原官方锁已交接、日志末尾 marker 存在。原 shell 没有持久化最终退出码，沿用显式 `driver_exit_status:null`，不能把 detached launch 0 当完成。
- 五 teacher 最终 `checkpoint_iteration=19999`，resolved command 4096 环境，target20000；pure 最终9999/target10000、fine 最终29999/target30000，均2048环境。默认 `settings.num_envs` 可是 null，实际环境数以 command 与恢复出的 native saved config 为准。
- 顺序固定 locomotion / low-step / high-step / low-climb-76 / high-climb-76，全部 file:// 本地 registry；两学生 `settings.source_checkpoints` 是五个最终 teacher 的有序 path+SHA，FINETUNE 分别0/1。不能只认文件名 `model_09999.pt`。
- monitor 的 `selection.json` 自身 identity、16 manifest SHA、7 PT path/SHA 与 `cpu-ready.json.input_identity` 一致；CPU ready 七项实际 `torch.load(map_location=cpu)` 核验了 `iter` 与 `iteration`、finite policy、恢复的 native typed config、4096/2048、64/3 variants、seed42/save500/24steps、teacher mini4/epoch5、student mini96/epoch2，以及五冻结 actor+normalizer 张量与最终教师 bitwise 相等。该现成门卫是“实际 PT”的证据，无需把 PT 拉回本地再加载。
- 对每个 `export-student-{pure,finetune}.json`，`settings.source_checkpoints` 恰为对应最终学生 PT path/SHA，原生 command 的 `--training.checkpoint` 与 registry-name 也必须相符。**export 的 settings.registries 在实际 schema 中为 null**，应读 command，而非误拒 null。
- 只从 export manifest 的 `onnx_validation_reports=[{bundle,report}]` 选择 pair，校验所有 `artifact_fingerprints`、模型/report 字节数与 SHA。若多个 bundle，按最终 checkpoint 及完整被验证的 bundle identity 选取；无法唯一判定则拒绝，不按最新 mtime 猜测，也不从 training periodic `onnx_bundle_directories` 取模型。
- 对应云 ORT report 须 passed、30 cases（15 onehot×2 depth）、两个模型 SHA 与 export fingerprints 一致，所有输出 finite/repeat deterministic；其 schema 检查是合成输入合同检查，不能称 PT/ONNX 数值 parity 或技能质量。学生 metadata **没有 iteration、PT SHA 或 experiment_config**；最终迭代来源靠 export command + final PT manifest + CPU 科学回执绑定，不能凭 ONNX 文件自己推断。

出处：`scripts/research/train_pipeline.py:149,241,251,350,376,452,481`；`scripts/research/posttrain_coverage.py:109,231,432,485,516,644`；`wbt_training/training_runs/export_distill_onnx.py:106,159`；`wbt_training/utils/exporter.py:222`。

## 2. 精确白名单回传，避免全部 checkpoint 树

现有 `cloud.py pull` 会递归拉整个 remote `/outputs/` 及 logs；**本方案不得调用该命令**（`scripts/research/cloud.py:289`）。云端原始 PT/periodic ONNX 树可能很大。仅拉两个 explicit final export bundles 的 `student.onnx`、`depth_backbone.onnx` 四个文件，以及小型 provenance JSON。

建议本地不可混淆目录：

```text
outputs/research/final-student-transfer/<cohort>/
  remote-receipt.json                 # 原绝对路径、selection identity、来源SHA、实际字节数
  files-from.nul                     # 经门卫生成的明确白名单；不是glob
  raw/official-full/official/manifests/*.json  # 16份，小型来源快照
  raw/coverage-official-final/{selection,cpu-ready}.json
  raw/official-full/official/export-student-*/.../{student,depth_backbone}.onnx
  raw/official-full/official/export-student-*/onnx-validation-*.json
  raw/official-full/official/eval-student-*/quality.json  # 只JSON，非全部视频
  models/pure/{student,depth_backbone}.onnx
  models/finetune/{student,depth_backbone}.onnx
  cpu/{pure,finetune}-onnx-local.json
  cpu/deployment-contract.json
```

`<cohort>` 建议为 monitor input_identity 前12位+两个最终 PT SHA 前12位，完整 SHA 全部写 receipt，且目标目录不存在或为空。保存完整的 cloud 原路径；本地 `models/` 是 SHA 校验后的字节复制，记录原路径→本地路径映射，不修改 raw manifest/report。不要覆盖 `/data/assets/student` 或 release 629 原模型。

receipt 至少包含：schema、UTC、官方 training source0093/new posttrain snapshot、两镜像ID及相同 config/layer fingerprint、selection identity/SHA、cpu-ready SHA、16 manifests path/SHA、7最终PT path/SHA/iteration、两 export command、bundle/report/model path/SHA/bytes、最终 actor合同检查结果、文件白名单、总字节数。remote CPU 科学回执只读提取，不生成新 PT、不复制优化器树。可加 7个 eval quality JSON及teacher ONNX validation小报告作完整官方验收索引，但不要取 teacher ONNX 约GB级常量图或所有电影。

白名单生成器应宿主 stdlib：拒绝 `..`、绝对输入、symlink逃出 remote outputs、未在 manifest 中绑定的路径；明确拒绝 `.pt`、teacher `.onnx` 和目录 glob。执行前记录全部 remote SHA/size，复制后再核 remote/local SHA；源期间变化即拒绝。本次只设计这些步骤，尚未实现/运行 transfer runner。

未来实际 rsync 命令（白名单相对 remote outputs，NUL分隔）：

```bash
rsync -a --relative --partial --protect-args --from0 \
  --files-from=outputs/research/final-student-transfer/COHORT/files-from.nul \
  -e 'ssh -p 22 -o BatchMode=yes' \
  tencent-231:/diff/dzp_is_sb/php-parkour-research/outputs/ \
  outputs/research/final-student-transfer/COHORT/raw/
```

失败/中断保留 partial 与原 receipt；重传同一不可变 cohort 可补同一白名单缺文件，不能换权重或让坏文件静默通过。完成 SHA 验收后才 materialize `models/{pure,finetune}`。任何科学读取、ONNX/NumPy/PT 处理均 Docker 内，宿主只 stdlib/现成SSH/rsync。

## 3. CPU 可提前核，原生部署合同不能跳过

模型回传后可在本地 629 仍运行时，以 `CUDA_VISIBLE_DEVICES=''`、inference-python 执行两个 local ORT30case；读取模型而非依赖云 report 的 passed 字符串。模型 SHA、IO/metadata 应与原云 report 完全一致（路径允许仅按 receipt 平移）。

```bash
docker exec -w /workspace/php_parkour -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=1 \
  php-parkour-research /opt/php/bin/inference-python scripts/research/validate_onnx.py \
  --models /outputs/final-student-transfer/COHORT/models/pure \
  --seed 42 --output /outputs/final-student-transfer/COHORT/cpu/pure-onnx-local.json
# 对finetune同样执行，使用独立目录/报告名。
```

需要额外 CPU 合同回执（当前 final 不存在，尚未运行）：backbone [1,58,87]→[1,32]；student obs[1,140]、time_step[1,1]、actions[1,29]；93 proprio +15 command +32 depth，完整名字/顺序/scale/history 吻合。29 joint_names 集合必须等于部署 G1 joints，记录真实 real↔model permutation 与 action_scale 向量对应重排；默认角按 joint_names重排后，与最终训练 canonical default、metadata default_joint_pos、部署 preset default_dof_angles 比较（CSV metadata 仅3位小数，容差须解释为rounding，不能掩盖真实偏差）。

重要纠正：**当前 inference 并不按 `observation_names` metadata 重新排序**。BasePolicy 读 ObservationConfig，当前 distill preset 已固定实际训练 sorted wire order：actions29/base_ang_vel3/dof_pos29/dof_vel29/projected_gravity3，再加command15/depth32。旧 released metadata 的声明顺序误导；新 exporter 已写真实sorted名称，`robot_anchor_projected_gravity` 是部署 projected_gravity 的语义对应。不能因旧metadata不同就重排 observation blocks，也不能声称新导出可自动修正任意obs合同。

default_joint_pos metadata **不会自动替换**部署默认角；motor_kp/kd 以显式部署 preset 优先于 metadata（已知几百分比差异须记录实际使用值，不能称 bitwise同PD）。最新烟测两学生默认29角与当前preset相符，但正式 final 仍要重新核。action_scale与joint_names由native policy读取，obs默认角/排序来自config。不得实例化完整DDS policy作为“CPU检查”去启动新DDS通道。

出处：`scripts/research/validate_onnx.py:32,51,63,79`；`wbt_training/utils/exporter.py:69,259,355`；`holosoma_inference/policies/base.py:70,116,130,587,743`；`holosoma_inference/policies/depth_distillation.py:257,328,483`；`holosoma_inference/config/config_values/observation.py:154`；`.../robot.py:238,291`。

还可 CPU 预生成两个17场景plan（`--plan` 不启动sim/inference），每个使用本地新pair与原motion矩阵；plan必须在最终执行前重新核image/model/dependency/geometrySHA。plan是计划文件，不计成功运行。

## 4. GPU/DDS 启动门卫

本地当前629必须真正结束：`full-driver.json` 是 terminal、真实returncode已收；matrix全部629项有终态attempt；driver18565/18570与所有原生simulator/inference子进程消失；container-wide `/tmp/php-parkour-sim2sim-matrix.lock` 可获得。若driver提前执行失败仍有未尝试配置，须先解决629原任务，不能借terminal失败绕过“完成”。保留其原始失败及publication，不重跑挑结果。

记录 Docker inspect image88254…、当前可复核source/dependency closure、两个finalpairSHA、host与container实际GPU UUID、nvidia-smi进程/内存快照；未知其他compute/DDS任务出现则等待，不停止任何别人的进程。桌面graphics占用与compute任务应分别记录，不把云端“零进程≤64MiB”规则直接套到本地桌面GPU。要求本地计算任务已空闲且显存余量足够；原16G迁移证明不能替代新pair实测。

DDS 必须逐任务串行；同一容器同loopback/domain不并行两个policy。scene matrix 自带global flock与存活native child检查；直接 sim2sim.py 的plane入口**没有该锁**，未来外层应在同一global flock持有期间先检查 `running_children()==[]`，再启动整个12-isolated组。manual native作业也须遵循串行约定，不能靠不同output目录躲过DDS冲突。后一个policy开始前要求前一个子进程完整退出，禁止随意unlink全局SHM，只使用容器私有清理行为。

出处：`scripts/research/sim2sim_scene_matrix.py:190,319,335`；`scripts/research/sim2sim.py:345`；原真实629launcher `outputs/research/sim2sim-all-configs-host/full_driver.py`。

## 5. 实际闭环命令及证据名（当前未执行）

以下 `COHORT` 替换为已核验不可变cohort，输出必须fresh。在门卫通过后，pure/fine依次执行；不要沿用 release `scene-matrix-final`、`all-configs-final` 或 `/data/assets/student` 目录。

Plane每pair12个指令，fresh reset互不污染；外层在global flock下核无存活nativechild：

```bash
docker exec -w /workspace/php_parkour -e LOGGER=tensorboard -e WANDB_MODE=disabled \
  -e OMP_NUM_THREADS=2 php-parkour-research \
  flock -n /tmp/php-parkour-sim2sim-matrix.lock bash -c '
    /opt/php/bin/train-python -c "from scripts.research.sim2sim_scene_matrix import running_children; p=running_children(); assert not p, p" &&
    exec /opt/php/bin/train-python scripts/research/sim2sim.py \
      --models /outputs/final-student-transfer/COHORT/models/pure \
      --output /outputs/final-student-mujoco/COHORT/pure/plane-12-isolated \
      --terrain plane --commands all --isolate-commands \
      --seconds-per-command 10 --seed 42 --gl egl
  '
```

17代表场景每pair一组（省略 `--all-configs`），实际OBJ、常量low/high-forward、seed42、10sim秒；其中random_locomotion按现有确定性selector选有clutter且前进方向配置。先CPU plan、后物理；plan为输出兄弟文件，不污染要求empty的运行目录：

```bash
docker exec -w /workspace/php_parkour -e CUDA_VISIBLE_DEVICES= php-parkour-research \
  /opt/php/bin/train-python scripts/research/sim2sim_scene_matrix.py \
  --matrix /outputs/motion-matching/matrix.json \
  --models /outputs/final-student-transfer/COHORT/models/pure \
  --output /outputs/final-student-mujoco/COHORT/pure/17-scenes-representative \
  --image-id sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f \
  --seconds 10 --seed 42 --gl egl --plan \
  --plan-output /outputs/final-student-mujoco/COHORT/pure/17-scenes-plan.json
# GPU/DDS门卫通过后，同参数去掉 --plan/--plan-output 两项及CUDA_VISIBLE_DEVICES空覆盖，才会实际运行。
# 再对finetune替换全部pure模型与证据路径，独立执行同一组计划/闭环。
```

每条宿主启动命令另存 argv/UTC/image/source/model/provenanceSHA及实际returncode，stdout/stderr写输出兄弟 `plane-driver.log` / `scene-driver.log`，不能把detach exit0当完成。Plane要求12个独立result、各500tick和新视频；scene用原生`verify_completed`逐17核case-evidence/全部文件SHA，别仅看matrix.status。每pair29条+两pair总58条均应有不可变模型来源映射。

保留所有原始MP4/PNG、run/result/trajectory、simulation/inference/log与失败error，完整解码/seek检查录像；sim秒与wall秒分开。阈值统一 pelvis<0.4m 或 base_up_cosine<0.35，gantry释放后无支撑；记录生存、位移/朝向/时长，失败不选参数重试美化。Plane grouped启动有失败时仍保留12项，返回非零；修复后用新reviewedattempt/cohort保留旧目录，不能覆写。scene `--resume`会完整验证旧成功项SHA，并保留旧失败attempt后建新attempt，若使用必须报告全部尝试，不能只选最后成功。

所有汇总始终 `quality_verified:false,obstacle_course_completion_verified:false`；接口执行/合成ORT/58代表运行通过与技能质量分别统计。888源片段首次尝试、公共629几何、自训58代表闭环各有自己的模型来源与分母，互不替代。
