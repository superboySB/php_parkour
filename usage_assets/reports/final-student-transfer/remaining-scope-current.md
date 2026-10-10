# 当前剩余功能范围复核

结论：除已在运行/等待的七模型正式训练、后置888、发布策略629扫描，以及已知12历史hash和真机边界外，还找到 **4项可在无物理G1条件下补验的具体工作流**。未发现新的资产/环境、离线TensorBoard或基本同步缺口。本轮只读本地源码与既有证据，不查询云端、不执行GPU/浏览器/测试，不改冻结源码、docs/raw或git。

| 优先级 | 尚缺实际证据的范围 | 最小可行动补验 |
|---|---|---|
| P1 | **5个非默认教师preset的保存后重载/eval及独立图ORT**。现22stage包含6教师preset的64env/2iter训练，但`eval-teachers`只取`teacher-SKILL`默认noscale；各preset自己的PT没有对应eval/ORT记录。 | 用已存各preset PT/YAML，在空闲GPU另开有界native eval，保留新视频/quality/TB/PT SHA；CPU按该preset实际输入维数/anchor/scale验图。当前`validate_teacher_onnx.py`固定obs449，不能直接用它判no-heightscan失败。无须为此把每个ablation×五数据集跑全日程；no-heightscan若声称默认完整复现仍应60000轮。 |
| P2 | **play_database实际播放/定位控件**。现`database_viser`仅boundedHTTP/startup，另一个motion-file viewer的播放/Save不覆盖它。 | CPU Docker+已有Chrome，用真实verified/bakedDB，实际pause/seek、min/max范围、speed后观察帧/G1位姿更新，保留浏览器与server证据。一条代表流程即可。 |
| P2 | **原生MuJoCo/推理terminal真实按键与Backspace reset**。当前自动harness使用injectedprovider/原生API，已测DDS、depth、PD、recording，未测原生inputevent派发。 | 等629释放DDS后，用自建窗口/PTY运行文档手动pair，定向验证gantry8/9、]启动、方向press/release、=切速、c录制、o阻尼、i初姿及Backspace重置；日志绑定命令/mode/reset变化。不得同时启动第二个SHM/DDS仿真。 |
| P1，最终模型后 | **自训pure/fine的PT→ONNX→本地MuJoCo衔接**。official16结束于Isaaceval/export；888是nativePT的Isaacfirstattempt；17/629绑定的是发布ONNX，不能替代新模型部署。 | 完成后回传两套最终PT/config/匹配双图/TB并核SHA；CPU检查metadata/顺序/scale/defaultangles，宜同输入比较PT与ORT；随后将各自准确pair跑原生plane方向、bundledstep和一份customOBJ，保存全部失败。只有要声称新模型全场景时才复用17scene矩阵，不改当前released629cohort。 |

具体5个非默认教师为 `g1-wbt-terrain-ref`、`g1-wbt-terrain-no-heightscan`、`g1-wbt-terrain-no-heightscan-noscale`、`g1-wbt-terrain-ref-pelvis`、`g1-wbt-terrain-no-heightscan-pelvis`。单纯训练sweep通过并非这些preset完整默认日程或重载接口已通过。

## 旧缺口已经关闭，勿重复计算

- Viser真实file/terrainvariant/rerandomize/speed/save/delete与TkStart/EndRecording均已有完整转换、file://、CPUMotionLoader证据：[GUI报告](../../../usage_assets/reports/gui-workflows/summary.md)。交互录制没有vel_cmd，已明确提示；不能自动补造监督label。
- 学生`--show-depth True`已有4env×100步、100显示帧/98种SHA和实际窗口截图：[depthGUI](../../../usage_assets/reports/depth-gui/summary.json)。不是策略收敛证明。
- 当前`experiment.DEFAULTS`的8项与acceptance8项完全对应，6teacher+2student均有训练接口smoke；17scenarios/629configs和29注册项（28独立traversal+locomotion）参考生成已覆盖。未发现漏掉注册模型/内置场景的计数。
- 正式首教师actualsavedconfig确认4096env/64variants/20000iter/24steps/4mini/5epochs/save500/seed42；学生native2048env/**3variants**/96mini/2epochs/24steps/save500及10000/30000日程已有默认审计。未来阶段需以最终实际PT/config核验，不能将计划或20itercapacitypilot写成完整日程。
- TensorBoard真实events、有限scalars、浏览器曲线和云端viewer→本地6007HTTP200已有证据；`--network none`无源码挂载的镜像训练probe也实跑。没有W&B验收要求。
- 镜像archive/config/layers、不可变源码快照、资产SHA、最小空闲GPUUUID、真实PT回传及16GiB本地评估均已完成。当前GUI源码挂载、镜像封存64ebc5f和云训3439cb7/0093不同版本是已记录的冻结边界，不应为追HEAD重建正在训练的容器。最终产物回传/质量属于上述newstudenthandoff，不是从头重做同步。

## 功能与质量的边界

四项补验均不需要实物G1；其中presetIsaac/物理部署需等待已有GPU/DDS任务空闲。仅旧真机边界仍依赖G1、D435i、IMU/外参/producer等实际硬件。原MoCap采集/OmniRetarget、可选多GPU、W&B及所有model×scenario×command×variant任意组合不是当前离线PHP工作流的额外必要验收。

没有把runtime可执行、finiteORT、参考回放、后台启动或达到迭代目标写成技能成功。已测的backward净X为正、窄step跌倒、partialclimb和sourcepilot失败属于已测失败，不能转写为缺执行，也不能称掌握技能。

主要来源：`acceptance_matrix.json`、公开554edcc原README、当前README/note/usage/technical、旧remaining-function-audit、最终22stage报告、GUI/depthGUI、officialdriver/defaults、runtimeoffline、cloudtransfer/deployment、milestone回传及scene模型SHA。完整逐文件SHA/行号、可行动项和排除边界见 [remaining-scope-current.json](remaining-scope-current.json)。features/validation已交叉确认前三项/新学生handoff没有另份已执行报告；本轮未发起新验收。
