# Motion matching 复现证据

2026-10-10 在统一 `php-parkour:research` Docker 中运行，G1 单机器人。seed 42，四个场景任务并发；每个任务设置 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`。参考数据生成与录像使用 CPU；录像通过 MuJoCo `mj_forward` 重放 NPZ，**没有调用控制策略或物理步进**，不能作为技能闭环成功率。

17 个场景的 **629/629 配置**（总342,651帧）全部实际生成，通过 50 FPS、有限数值、数组形状、15 维 one-hot 指令（生成数据实际出现索引0–11；12–14保留维不作为已使用命令）、单位四元数、正尺寸 box 和可解析 OBJ 校验。29 个注册技能中，locomotion 在随机行走/其他场景及键盘轨迹中运行，其余 **28/28** 独立技能执行器通过有限轨迹检查。原始逐配置报告见 [motion-matching.json](motion-matching.json)，完整注册信息见 [motion-catalog.json](motion-catalog.json)。

所有场景各保留一段完整参考轨迹录像（随机locomotion选cfg0001显示offpath障碍；该族50个有clutter配置各有5–15个box，另50个为空地）；[离线播放页](../motion_matching/playback.html)支持播放、暂停和拖动，GIF 只作小尺寸预览。已有Chrome实际加载17/17个MP4的尺寸/时长/解码元数据均通过，且17/17都实际seek解码关键帧，见 [播放页截图](../motion-gallery.png) 与 [验收报告](motion-gallery.json)。视频覆盖一配置，生成验收覆盖全部629配置，二者范围有别。来源清单记录源 NPZ/terrain SHA-256、MP4/PNG/GIF SHA-256、逐视频帧的源帧索引、GIF采样位置和末帧停留时间。

| 场景 | 实际配置数 | 场景调用的技能 | 结果 |
| --- | ---: | --- | --- |
| `high_speed_cat_vault` | 51 | `cat_vault` | 通过 |
| `high_speed_climb_58` | 40 | `climb_58_down`, `climb_58_up` | 通过 |
| `high_speed_climb_76` | 40 | `climb_76_high_speed_down`, `climb_76_high_speed_up` | 通过 |
| `high_speed_climb_94` | 15 | `climb_94_high_speed_down`, `climb_94_high_speed_up` | 通过 |
| `high_speed_dash_vault` | 51 | `dash_vault` | 通过 |
| `high_speed_hurdle` | 51 | `hurdle` | 通过 |
| `high_speed_jump_35` | 1 | `jump_35`, `step_high_speed_down`, `step_high_speed_up` | 通过 |
| `high_speed_roll_134` | 40 | `climb_134_up`, `roll_136` | 通过 |
| `high_speed_speed_vault` | 20 | `speed_vault` | 通过 |
| `high_speed_step` | 60 | `step_high_speed`, `step_high_speed_down`, `step_high_speed_up` | 通过 |
| `low_speed_climb_58` | 40 | `climb_58_down`, `climb_58_up` | 通过 |
| `low_speed_climb_76` | 40 | `climb_76_down`, `climb_76_up` | 通过 |
| `low_speed_climb_94` | 20 | `climb_94_down`, `climb_94_up` | 通过 |
| `low_speed_roll_78` | 1 | `climb_76_up`, `roll_78` | 通过 |
| `low_speed_roll_90` | 3 | `climb_94_up`, `roll_90` | 通过 |
| `low_speed_step` | 56 | `step`, `step_down`, `step_up` | 通过 |
| `random_locomotion` | 100 | locomotion | 通过 |

29个注册技能：`locomotion`、`step`、`step_up`、`step_down`、`step_high_speed`、`step_high_speed_up`、`step_high_speed_down`、`climb_58`、`climb_58_up`、`climb_58_down`、`climb_76`、`climb_76_up`、`climb_76_down`、`climb_76_high_speed_up`、`climb_76_high_speed_down`、`climb_94_up`、`climb_94_down`、`climb_94_high_speed_up`、`climb_94_high_speed_down`、`climb_134_up`、`roll_78`、`roll_90`、`roll_136`、`hurdle`、`dash_vault`、`speed_vault`、`cat_vault`、`jump_35`、`drop_92`. `drop_92` 等仅单技能执行器覆盖的项目，在矩阵里单独标明；公开student的5个训练技能组只有 locomotion、低/高速step、低/高速climb_76，不能把vault/roll参考动画说成student已学会。

当前工作流完全离线，26/26项通过：数据库烘焙、5个完整发布native bundle、17个生成场景的本地物化/校验，以及3个Viser/Tk入口。5个发布bundle共296组动作；17场景全部629组tracking动作均转换为native并复制地形，逐文件校验持久内容SHA-256、数组形状和有限值，随后实际调用`file://` registry CLI及Resolver。共925组native动作。服务器使用本地数据和TensorBoard，验收脚本阻断远端实验SDK导入，motion与registry验收进程的导入次数均为0。22份逐文件内容记录保存在[local-bundles](local-bundles/)。数据库烘焙由真实190帧30Hz源动作生成760帧60Hz数据库（包含镜像、31骨骼、2段）。完整结果见 [motion-workflows.json](motion-workflows.json)。

实际浏览器中加载了G1/地形/关节控件并点击 `Play Animation`，画布与播放状态检查通过，Frame滑块实际从0推进到94，见 [浏览器截图](../viser-playback.png) 与 [结果](viser-browser.json)。该检查使用本机已有Chrome及CPU SwiftShader，宿主没有安装Python包。Tk只对本次窗口定向发送I/Tab和释放事件，JSON文件控制器驱动180步60Hz参考运动，XY位移5.2125m；Quit同步发布停止状态，见 [键盘窗口](../keyboard-controller.png) 与 [结果](keyboard-gui.json)。这不是机器人硬件控制测试。

公开资产7/7包、682/682文件SHA-256核验通过，源manifest约束的内容共862,921,430字节；验收后重新核验仍全部通过，见 [asset-verification.json](asset-verification.json)。

最终完整CPU测试：root+training **247 passed**，之后新增5项训练状态门卫均通过、关联13项复查通过（独立增量，见 [训练/launcher JUnit](research-training-launchers.xml)）；motion **213 passed，12 failed，0 skipped**。12项都是研究分支修改前的历史字节hash门禁：重采样2、tracking转换1、随机box1、URDF FK2、端到端NPZ/OBJ/NPY6。历史mm_hs环境/原始参考数组未发布，且引用的0424c06c不在该仓库历史，不能从SHA-256反推差异或归因浮点误差。没有更新golden或跳过失败。独立Python3.10诊断复查6个characterization/FK hash测试，仍得到相同失败；同一Docker中导出未修改554edcc源码与research代码，**36/36真实数组bytes完全相同**，9/9功能不变量通过，独立URDF零位FK误差最大2.30e-16。详见 [CPU结果](cpu-tests-final.json)、[12项失败详情](legacy-goldens.json) 与 [原版数值对照](motion-baseline-parity.json)。这证明本次修改保持原版数值，不能证明缺失的旧mm_hs参考已经重现。

从仓库根目录复跑（输出目录须为空，每轮使用新的目录名）：

```bash
python3 scripts/research/verify_assets.py --verify-only
bash scripts/research/docker.sh motion scripts/research/motion_matching_matrix.py --output-dir outputs/research/my-motion --skills --jobs 4
bash scripts/research/docker.sh motion scripts/research/verify_motion_workflows.py --matrix outputs/research/my-motion/matrix.json --output-dir outputs/research/my-workflows --interactive-gui
bash scripts/research/docker.sh motion scripts/research/verify_keyboard_gui.py --output-dir outputs/research/my-keyboard
python3 scripts/research/viser_browser.py --motion-file /workspace/php_parkour/outputs/research/my-motion/scenarios/low_speed_step --output-dir outputs/research/my-browser
docker exec -e MUJOCO_GL=osmesa -w /workspace/php_parkour php-parkour-research /opt/php/bin/motion-python scripts/research/render_motion_evidence.py --matrix outputs/research/my-motion/matrix.json --output-dir outputs/research/my-videos
bash scripts/research/docker.sh motion scripts/research/publish_motion_evidence.py --source outputs/research/my-videos --output-dir outputs/research/my-publication
python3 scripts/research/cpu_tests.py --output-dir outputs/research/my-cpu
bash scripts/research/docker.sh motion scripts/research/compare_motion_baseline.py --output-dir outputs/research/my-parity
```

Tk检查需要按note.md以GUI方式启动统一容器，`DISPLAY`/Xauthority匹配当前桌面；浏览器验收需要已有Chrome/Chromium，服务器8080/8081端口须空闲。CPU测试保留12项历史失败，进程退出码1属于该实际记录；不要写成全绿。重生成数据的seed/图像renderer/源数据hash均见报告。

官方公共Git历史也已仅在本机镜像检查：5个发布ref覆盖16个commit，未含`0424c06c`；官方commit API返回422 “No commit found”。历史树没有`mm_hs`完整环境锁或golden输出数组，唯一NPZ是源动作输入。原参考仍不可恢复，12个失败继续保留。[公共上游调查](legacy-upstream-audit.json)记录refs、历史、源文件快照及HTTP结果；不据此推断未发布的私有历史。
