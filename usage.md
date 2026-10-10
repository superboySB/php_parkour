# PHP Parkour 功能复现与验收

配置和首次启动见 [note.md](note.md)。本项目使用 Unitree G1 29 DOF，功能覆盖以 [验收定义](scripts/research/acceptance_matrix.json) 和代码注册表为准。本文件随真实运行结果更新；没有对应日志、JSON 和源文件校验记录的项目不记为通过。

先看真实结果：[17 场景参考动作播放页](usage_assets/motion_matching/playback.html)、[12 指令物理闭环视频](usage_assets/sim2sim/directions.mp4)、[逐项原始报告](usage_assets/reports/)。参考动作来自生成数组，闭环录像来自公开 ONNX 策略驱动的 MuJoCo，训练录像来自实际 Isaac checkpoint。

[![17场景参考动作离线播放页，点击打开](usage_assets/motion-gallery.png)](usage_assets/motion_matching/playback.html)

播放页的17个MP4已在已有Chrome中逐一加载、核对时长并seek解码关键帧；[浏览器验收报告](usage_assets/reports/motion-gallery.json)保留每个文件结果。

![公开深度策略的12种指令，逐项独立重置、移除吊架后录像](usage_assets/sim2sim/directions.png)

[播放这段同步视频](usage_assets/sim2sim/directions.mp4)。每项均为 8 秒仿真时间，50 Hz 原生策略控制。完整路径与转角见后文，不能把转弯绕圈时的小净位移当作没有行走。

## 1. 证据与功能边界

| 证据 | 证明的内容 |
| --- | --- |
| 资产 SHA-256 验证 | 输入与官方公开发布一致 |
| CPU 测试与配置检查 | 数据处理、导出、注册、CLI 等代码契约 |
| 全场景动作匹配 | 生成了有效的参考动作/方向指令/地形文件 |
| 参考动作视频 | 真实生成数组的运动学回放；画面带 `KINEMATIC / NO POLICY` |
| 有界训练与评估 | 实际启动、梯度更新、保存/加载 checkpoint、渲染、导出通路 |
| 默认迭代训练 | 使用记录中的默认训练量；完成迭代仍需评估策略质量 |
| MuJoCo 原生闭环录像 | 深度图、DDS 状态、ONNX 动作与物理机器人相互连接；另报告跌倒/位移 |

这几类证据分别统计。参考动作中的翻越成功不等于策略掌握该技能，吊架辅助站立不等于无辅助稳定行走，有限值 ONNX 输出不等于跑酷成功。

## 2. 公开资产

2026-10-10 已在本机完成七组资产的包及逐文件校验：682 个文件，解压文件总计 862,921,430 字节。包括 19 个数据库、32 OBJ、32 JSON、学生 ONNX 双模型以及 296 组官方动作/地形对和各组 README。完整记录为 `outputs/research/asset-verification/results.json`，输入发布清单为 [release-assets.json](release-assets.json)。

仓库内保留了可直接查看的 [逐文件验收记录](usage_assets/reports/asset-verification.json)。

```bash
python3 scripts/research/verify_assets.py
python3 scripts/research/verify_assets.py --verify-only
```

五类教师数据是 `locomotion`、`low-step`、`high-step`、`low-climb-76`、`high-climb-76`，分别为 100、56、60、40、40 对。公开发布没有原生教师 checkpoint，因此教师与自己的学生需要实际训练。

## 3. 全部动作场景与技能

全部 17 种公开场景、629 组配置来自 [builtin.py](motion_matching/motion_matching/scenarios/builtin.py)。计数由容器内实际 catalog 检查得到，含自由移动的 100 组配置：

| 类别 | 场景函数 |
| --- | --- |
| 自由移动 | `random_locomotion` |
| 台阶 | `low_speed_step`、`high_speed_step` |
| 攀爬 58 | `low_speed_climb_58`、`high_speed_climb_58` |
| 攀爬 76 | `low_speed_climb_76`、`high_speed_climb_76` |
| 攀爬 94 | `low_speed_climb_94`、`high_speed_climb_94` |
| 翻滚 | `low_speed_roll_78`、`low_speed_roll_90`、`high_speed_roll_134` |
| 跨栏与腾跃 | `high_speed_hurdle`、`high_speed_dash_vault`、`high_speed_speed_vault`、`high_speed_cat_vault` |
| 跳跃 | `high_speed_jump_35` |

技能注册表共 29 项，包含 locomotion 与 28 个方向/速度/动作技能。完整验收遍历每个场景的全部配置，再单独执行 28 个 traversal skill。仅用 `--representatives` 的首配置检查会在报告中单独标识，不能作为全配置覆盖。

```bash
bash scripts/research/docker.sh motion scripts/research/motion_matching_matrix.py \
  --skills --seed 42 --jobs 4 --output-dir /outputs/motion-matching
bash scripts/research/docker.sh motion scripts/research/render_motion_evidence.py \
  --matrix /outputs/motion-matching/matrix.json --output-dir /outputs/motion-videos
```

每个动作 NPZ 检查动作匹配导出的 tracking 字段、50 FPS、29 关节、有限值、四元数和 15 维 one-hot 方向指令，并检查配对地形 NPY 与 OBJ。该导出需要转换为 Holosoma native 格式后用于训练；不能与296组已发布native数据混称。生成数据实际使用指令索引0–11，12–14为保留维。四任务并发时每个子进程将OpenBLAS/OMP/MKL线程数设为1。参考录像默认使用CPU OSMesa，不需要DISPLAY。录像清单记录源数组和地形 SHA-256、源帧采样位置、编码参数及产物 SHA-256。所有生成结果保留在忽略目录，图片/视频验收后选取证据保存到本仓库。

实际结果是 **629/629 配置、28/28 独立 traversal 技能通过**，seed 42。每种场景各保存一个完整配置的 MP4、GIF 与 PNG，共 17 组；视频范围为每场景一个配置，数组验收范围为全部配置。自由移动视频选择含 5 个障碍的 clutter 配置，所有 50 个 clutter 配置实际含 5–15 个障碍。[全部场景计数和技能清单](usage_assets/reports/motion-summary.md)、[逐配置 JSON](usage_assets/reports/motion-matching.json)、[视频来源与哈希](usage_assets/motion_matching/manifest.json)。

| 参考轨迹示例 | 预览 | 完整视频 |
| --- | --- | --- |
| 低速台阶 | ![低速台阶参考轨迹](usage_assets/motion_matching/low_speed_step.gif) | [MP4](usage_assets/motion_matching/low_speed_step.mp4) |
| 高速攀爬 76 cm | ![高速攀爬参考轨迹](usage_assets/motion_matching/high_speed_climb_76.gif) | [MP4](usage_assets/motion_matching/high_speed_climb_76.mp4) |
| 翻滚 78 cm | ![翻滚参考轨迹](usage_assets/motion_matching/low_speed_roll_78.gif) | [MP4](usage_assets/motion_matching/low_speed_roll_78.mp4) |
| Cat vault | ![Cat vault参考轨迹](usage_assets/motion_matching/high_speed_cat_vault.gif) | [MP4](usage_assets/motion_matching/high_speed_cat_vault.mp4) |

这些画面标注 `KINEMATIC / NO POLICY`；[离线播放页](usage_assets/motion_matching/playback.html) 包含全部 17 场景，支持播放、暂停与拖动。

## 4. 数据库、浏览器与键盘交互

本次离线工作流使用`generate_database`、`play_database`、交互`run`、批量`run --mode generate`、`motion_visualizer`和本地`file://`数据解析。数据库生成必须使用G1 qpos格式及正确FPS。Viser页面提供播放、逐帧、速度、文件切换、关节/根位姿、地形可见性与地形变体控制；Tk键盘输入依赖GUI会话。

本分支将 GUI 到动作匹配的 JSON 文件传输改为同目录原子替换，读入异常时保留上一份有效指令，避免后台线程写文件中途导致交互主循环停止。回归测试为 [test_keyboard_controller.py](motion_matching/tests/test_keyboard_controller.py)。实际 GUI 和可视化结果按独立报告记录。

离线验收 **26/26 项通过**：数据库烘焙、五组完整发布native bundle与17场景的本地物化/校验，以及三个Viser/Tk入口。发布数据296组与生成数据629组共925组native动作；每个生成场景先将tracking动作转换并复制配对地形，再复核所有持久文件SHA-256、字段尺寸、有限值及实际`file://` registry CLI/Resolver。训练与曲线使用本地数据和TensorBoard；验收脚本阻断远端实验SDK导入，motion与registry验收进程的导入次数均为0。[工作流报告](usage_assets/reports/motion-workflows.json)保留命令和输出，[22份逐文件校验清单](usage_assets/reports/local-bundles/)保留源文件与物化文件哈希。

另按note.md的官方CLI在新的`/outputs`工作目录实际生成40组`high_speed_climb_76`，目录转换40/40个NPZ并复制40个同名terrain NPY后，Holosoma native bundle校验通过；[文档命令复查报告](usage_assets/reports/documented-motion-commands.json)记录实际字段尺寸和日志hash。参考录像脚本在空DISPLAY下默认OSMesa重录2个pilot也通过，见[默认渲染检查](usage_assets/reports/reference-render-default.json)。

真实浏览器点击播放后，Frame 从 0 推进到 94；Tk 定向按下 I/Tab、释放和退出后，JSON 指令驱动 180 步、3 秒参考运动，XY 位移 5.2125 m。截图来自本次窗口和页面，宿主使用已有 Chrome，无新增 Python 包。

按note.md切换GUI容器后，在仓库根目录复跑下列有界检查。各输出目录应为空；先结束已有Viser服务，使8080/8081空闲。输入沿用第3节生成的`/outputs/motion-matching`：

```bash
bash scripts/research/docker.sh motion scripts/research/verify_motion_workflows.py \
  --matrix /outputs/motion-matching/matrix.json --output-dir /outputs/motion-workflows-new --interactive-gui
bash scripts/research/docker.sh motion scripts/research/verify_keyboard_gui.py \
  --output-dir /outputs/keyboard-gui-new
python3 scripts/research/viser_browser.py \
  --motion-file /outputs/motion-matching/scenarios/low_speed_step \
  --output-dir outputs/research/viser-browser-new
```

最后一项使用宿主已有的Chrome/Chromium；生成服务与全部Python依赖仍在Docker。该浏览器自动检查验证播放按钮及帧推进，其他编辑控件的存在与数据格式回归不等于逐控件浏览器操作验收。

![Viser真实播放页面](usage_assets/viser-playback.png)

[浏览器结果](usage_assets/reports/viser-browser.json)；[键盘窗口截图](usage_assets/keyboard-controller.png) 与 [键盘结果](usage_assets/reports/keyboard-gui.json)。另外修复了从仓库根目录启动时资源路径定位错误、Quit 未同步写停止状态，以及窗口裁掉技能/退出控件的问题。

真实 low-step BeyondMimic 数据的单文件/目录转换、诊断 CLI 和原生 registry 加载已通过：364 帧，native 位置 `[364,36]`、速度 `[364,35]`、32 body 与 15 维命令，逐数组映射精确核验。[转换报告](usage_assets/reports/motion-conversion.json)。转换器现会拒绝单帧、非有限值和错误格式，并返回失败状态。

## 5. 训练、Isaac Sim 评估与导出

默认流程是五个 height-scan 教师，每个 4096 环境、20000 迭代；学生有纯 DAgger（2048 环境、10000 迭代）与 DAgger + PPO（2048 环境、30000 迭代）两种。全部六个教师配置和两个学生配置见 [acceptance_matrix.json](scripts/research/acceptance_matrix.json)。

```bash
# 每条命令都在选卡后的云端统一 Docker 中执行
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh teachers --profile smoke
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh teacher-presets --profile smoke --skills locomotion
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh eval-teachers --profile smoke --eval-steps 250
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh distill-pure --profile smoke
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh distill-finetune --profile smoke
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh eval-student --profile smoke --student-kind finetune
python3 scripts/research/cloud.py exec bash scripts/research/train_pipeline.sh export --profile smoke --student-kind finetune
```

smoke 采用显式缩小的并行环境、布局和迭代数，检查实际梯度更新与 checkpoint/ONNX 生成。正式训练用 `--profile official`，并记录所有显式 override。恢复按 checkpoint 中的真实迭代计算剩余量；成功记录需与 checkpoint 内容和 SHA-256 一致。Isaac Sim 评估与手动导出需要 `.pt`，不能用公开 ONNX 文件冒充。

本地 16 GiB 卡已完成 locomotion 教师实际训练：16 环境、2 迭代、768 timesteps，23.376 秒，随后真实加载 checkpoint、完成 100 步评估与 6 段原生录像。未收敛的教师频繁终止，最长片段只有 0.70 秒。[训练与评估报告](usage_assets/reports/runtime-summary.md#本地实际-isaac-smoke)、[示例 MP4](usage_assets/videos/runtime-isaac-smoke.mp4)。这是加载/渲染通路验收，不是成功的跑酷策略演示。

云端已完成 **22/22 项 smoke**：五类教师、六种教师 preset、五类教师评估、两种学生训练、两种学生评估与两种独立导出。每次训练均实际更新权重；两类学生导出的双 ONNX 各通过 30 组真实推理。全部阶段耗时 683.109 秒，13 个训练 run 的 TensorBoard loss/reward 都是有限值。[云端汇总及原始报告](usage_assets/reports/training-cloud-summary.md)保留 checkpoint、源代码快照和模型哈希；两轮训练的录像不能作为技能成功证据。

另按官方 locomotion 默认并行量和完整预处理运行 **4096 环境、20 迭代 pilot**，保存 iteration 19 的原生 checkpoint。显存采样峰值为 20479 MiB，18 个稳定核心迭代的中位耗时为 2.321 秒；对应 20000 轮的 collection+learning 估算约 12.89 小时，不包括初始化、保存和评估。其他教师和学生的耗时需要分别测量。完整官方日程尚未完成，见[pilot 实测与限制](usage_assets/reports/training-cloud-official-pilot.json)。

独立质量入口还真实复跑本地未收敛教师：16 环境 × 100 control steps，共 32 env-seconds，49 次失败 reset、0 次超时；四项跟踪误差各记录 1600 个有限样本。它在 reset 清除状态前采样，关联 checkpoint SHA、实际录像和 17 个 `Evaluation/*` TensorBoard 标量。[质量 JSON](usage_assets/reports/isaac-local-quality.json)、[测试记录](usage_assets/reports/research-quality-training.xml)、[真实失败短片](usage_assets/isaac/local-teacher-quality.mp4)。该运行仅观察到一个动作片段，没有声称覆盖全部 locomotion 数据。

![本地未收敛教师的实际评估帧](usage_assets/isaac/local-teacher-quality.png)

所有实验数据均为本地 `file://` 注册表，曲线使用离线 TensorBoard。在统一容器中运行以下命令，浏览器打开 `http://127.0.0.1:6006/`，即可查看入库的原始训练与评估 events：

```bash
docker exec php-parkour-research train-python -m tensorboard.main \
  --logdir /workspace/php_parkour/usage_assets/tensorboard \
  --host 127.0.0.1 --port 6006 --load_fast false
```

[TensorBoard 原始事件及 HTTP 验证](usage_assets/reports/training-cloud-summary.md#离线-tensorboard)记录了真实 loss/reward，服务器不需要外网或在线账号。

![真实TensorBoard官方配置20轮pilot曲线](usage_assets/tensorboard-pilot.png)

![真实TensorBoard两种学生的两轮训练曲线](usage_assets/tensorboard-students.png)

两张图均由本地 TensorBoard 页面实际筛选、绘制与截图，平滑为 0；浏览器显示的 8 条 series 已与 HTTP 原始标量逐项核对。[浏览器验收记录](usage_assets/reports/tensorboard-browser.json)。复查命令为 `python3 scripts/research/verify_tensorboard_browser.py --output-dir outputs/research/tensorboard-browser-new`，使用宿主已有 Chrome，无新增包。

## 6. ONNX 与全部部署指令

```bash
bash scripts/research/docker.sh inference scripts/research/validate_onnx.py \
  --models /data/assets/student --output /outputs/onnx/released.json
```

检查 depth backbone 和 student 两个模型的 ONNX checker、SDK 所需关节/默认姿态/动作缩放元数据、32 维深度 latent、140 维学生输入和 29 维输出。在零深度和随机归一化深度下逐一检查 15 个方向槽位，共 30 组真实 ONNX Runtime 推理。

公开模型实际 **30/30 通过**，模型 SHA-256、张量形状和每项结果见 [ONNX 报告](usage_assets/reports/onnx-released.json)。

部署指令为 0..11：站立，低速前进/左右 45°/左右 90°，高速前进/左右 45°/左右 90°，后退；12..14 为保留槽位，只做合约检查。合成输入结果只证明模型接口工作，策略表现由下面的物理闭环单独测量。

## 7. MuJoCo 场景与物理闭环

PHP 原生部署包括平面、随 Holosoma 捆绑的阶梯障碍场，以及用户 OBJ 网格覆盖。统一容器内部由训练环境运行 MuJoCo，推理环境运行原生 `DepthDistillationPolicy`；通过原生 Unitree SDK DDS（`lo`）和 D435i 58 × 87 深度共享内存连接。自动输入替代键盘事件，实际物理与网络没有替换为假接口。

```bash
bash scripts/research/docker.sh sim scripts/research/sim2sim.py \
  --models /data/assets/student --terrain plane --commands all --isolate-commands --gl egl \
  --seed 42 --seconds-per-command 8 --output /outputs/sim2sim/plane
bash scripts/research/docker.sh sim scripts/research/sim2sim.py \
  --models /data/assets/student --terrain step --commands all --isolate-commands --gl egl \
  --seed 42 --seconds-per-command 8 --output /outputs/sim2sim/step
```

每个指令独立启动，按仿真时钟运行。报告包含实际物理步数、策略 ticks、命令、无吊架轨迹、位移、最低骨盆高度、基座朝上余弦和跌倒判据。视频经过 ffprobe 时长检查及实际解码，保存中间帧 PNG。跌倒判据是移除吊架后骨盆低于 0.4 m 或朝上余弦低于 0.35；这不是论文中的完整课程成功率指标。

平地 12/12 指令各独立运行 8 秒，均未触发该阈值。[逐指令报告](usage_assets/reports/sim2sim-plane-matrix.json) 与下面的实测轨迹显示，持续发送 45°/90° 转向指令会继续转身绕行；路径长度与末端净位移分别统计。

![12种指令的实际物理轨迹与累计转角](usage_assets/sim2sim/trajectories.png)

后退索引 11 的输入通路工作，但本次末端 X 位移为 +1.05 m，不能称后退跟踪成功。阶梯与自定义地形的实际结果如下，均保留原片与失败结果：

| 地形与输入 | 实际结果 | 视频 |
| --- | --- | --- |
| 官方阶梯，高速前进 20 秒 | 末态站在 0.76 m 块上；攀爬时触发倾斜阈值 | [原片](usage_assets/sim2sim/step-forward.mp4) |
| 官方阶梯，高速前进 36 秒 | 后半程偏离障碍列，没有完整课程穿越结论 | [原片](usage_assets/sim2sim/step-course-36s.mp4) |
| 生成的 high-climb-76 OBJ，高速 12 秒 | 越过区域后继续行走，有倾斜事件与偏航 | [原片](usage_assets/sim2sim/custom-high-climb-76.mp4) |
| 生成的窄 low-step OBJ，低/高速各 12 秒 | 两次均实际跌倒 | [低速](usage_assets/sim2sim/custom-low-step.mp4)、[高速](usage_assets/sim2sim/custom-high-step.mp4) |
| 官方阶梯，外部航向按键引导 44 秒 | 第 2 块附近失败；引导使用仿真真值，属于辅助输入 | [失败原片](usage_assets/sim2sim/step-course-guided-44s.mp4) |

![公开策略攀爬0.76m阶梯的实际帧](usage_assets/sim2sim/step-76cm-climb.png)

![自定义窄台阶上的实际跌倒](usage_assets/sim2sim/custom-low-step-failure.png)

[详细数值、引导算法与逐条复跑命令](usage_assets/reports/deployment-summary.md)。所有这些试验都未声明完整课程成功率，单次没有阈值事件也不能推广为任意地形泛化。

`--record-policy` 已真实验证录制开关、STOP 自动保存和阻尼发送，Kp=0、Kd≥3。原生 Unitree 状态把 root xyz 填为零，所以录制 NPZ 只包含 SDK wxyz 四元数、零 xyz 占位、29 关节和指令；不能直接当作世界轨迹或训练 bundle。真实机器人位移记录在 simulator 的 `trajectory.csv`。

## 8. 全量测试、同步与结果来源

```bash
python3 scripts/research/cpu_tests.py --output-dir outputs/research/cpu-tests
python3 scripts/research/cloud.py status
python3 scripts/research/cloud.py sync
python3 scripts/research/cloud.py pull
```

CPU 测试统一在 Docker 中运行，分别保留根目录/训练和 motion matching 的 JUnit、日志、计数及日志 SHA-256。`PHP_DOCKER=0` 只用于隔离原生安装路径的 subprocess double 测试，解释器仍在容器内；真实容器路径由 doctor、训练和闭环运行验证。

动作测试目前 **213 passed、12 failed、0 skipped**。12 项均为修改前已有的历史字节 hash：未修改基线`554edcc`与research的36组数组逐字节一致，9项独立功能不变量通过，URDF零位FK的独立误差最大2.30e-16；另外用Python3.10复查6个characterization/FK hash测试，仍出现相同失败。历史`mm_hs`原始数组/环境不可得，[本机限定路径与文件名检查](usage_assets/reports/legacy-local-reference-search.json)也未找到；不能从SHA反推差异，也没有刷新golden或跳过失败。[12项原始详情](usage_assets/reports/legacy-goldens.json)、[原版数值对照](usage_assets/reports/motion-baseline-parity.json)。因此完整CPU命令保留退出码1，不能称为全绿。

云端镜像核对压缩包 SHA-256、镜像配置和层内容，源码快照逐文件复核 SHA-256。选卡检查包含图形与计算进程，Docker 根据 GPU UUID 映射，保存物理 nvidia-smi 编号。远端容器不在本体安装任何项目包。当前运行中的结果均写入 `outputs/research/` 或远端项目持久目录，未完成项目不会在此文件中记作通过。

首次完整镜像归档 **12,014,827,234 字节**，包 SHA-256 `332e292e5b0f542c2dfec6bf1b4c007d623f6acef313c3b37b03ba1d2eaccb83`，两端 Config/RootFS 指纹相同。部署时物理 GPU 1 没有任何进程、显存 1 MiB、利用率 0%，对应 UUID `GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5`；容器内只见这张卡。[传输记录](usage_assets/reports/cloud-image-transfer.json)、[部署记录](usage_assets/reports/cloud-deployment.json)、[仅公钥登录验证](usage_assets/reports/cloud-ssh-key-check.json)。最终重建的镜像将另行记录，不与首次镜像混记。
