# 原生 GUI 全方向键与 Backspace 补验：准备归档

本包只记录准备完成，不关闭真实按键/Backspace 缺口。实际新 GUI、XTEST/pynput 按键、物理 reset、录制和正常退出尚未执行，也不证明方向跟踪、越障、最终学生质量或实体 G1 成功。

[原候选说明与实际 native CLI](preparation/README.md)、[14 源冻结](preparation/codefreeze.json)、[原内层清单](preparation/manifest.json)、[独立只读审查](review/review.json)及[审查摘要](review/summary.md)保持原字节。candidate01 [45/45 XML](preparation/cpu-candidate-01/tests/tests.xml)和candidate02 [46/46 XML](preparation/cpu-candidate-02/tests/tests.xml)来自 runc / network-none / GPU-hidden CPU fixtures、合成 NPZ 与普通 stdlib PTY 子进程，不能替代真实 GUI。

原候选历史 `gui_cohort_created=false` 是当时事实。之后 root 已 prepare 新 cohort：见[真实冻结计划](root-prepared/cohort/plan.json)、[原 source-before](root-prepared/host/source-before.json)、[原 source-after](root-prepared/host/source-after.json)。计划内部 identity 是 `422ac089d4208477f0b3822ddbc7aa03268ee2a6e5395868d6dd1473355e2bc8`；该 JSON 原字节 SHA 是 `c7380ca2cd625df98486c0f090baef22c3ea7af52238f37ea1be649dd93c7402`。Root prepare 的 stdout 仅在工具 session14855 观察，未另存原件；本包不补造 stdout 或 prepare 进程退出码文件。

Root 随后在独立 runc / network-none / GPU-hidden 容器做了真实 import/config parse，见[实际收据](root-preflight/receipt.json)、[模拟端报告](root-preflight/outputs/simulator-cpu-preflight.json)、[推理端报告](root-preflight/outputs/inference-cpu-preflight.json)、[两日志之一](root-preflight/simulator.log)、[另一日志](root-preflight/inference.log)、[running inspect](root-preflight/running-inspect.json)、[stopped inspect](root-preflight/stopped-inspect.json)及[精确 helper](root-preflight/helper/preflight_allkeys_root_cpu.py)。两角色返回0、未构造 native 对象；收据记录3313个封存文件前后SHA核对、所属CPU容器停止并移除。收据的 `plan_sha256` 字段绑定上述 JSON 原字节 SHA，不是内部 identity。容器的 sleep 主进程停止后实际 ExitCode143保留，不能冒称原生 worker 退出0。

恢复时还需要外部原件：canonical 镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`；`outputs/research/sdk018-canonical-build-6cb2ae2/context` 的完整 source；`outputs/research/sdk018-native-pilot-20261010T0915/host/observe_container_pids.py`；`outputs/research/assets/student/{depth_backbone.onnx,student.onnx}` released pair。原canonical `source-manifest.json` 的3297条历史基线正确。本次 prepare 的 source-before3298=该3297条+1个已存在生成文件 `scripts/research/__pycache__/sim2sim_scene_matrix.cpython-312.pyc`；其mtime为2026-10-10T09:14:15.712032Z，早于本次prepare。新cohort复制了这份extra，所以source-after3311、加两个ONNX后冻结计划3313均按实际raw成立。大source、模型、cache、真实Xauthority和活跃任务输出均未复制。

精确恢复当前root plan还需这份[原字节extra（仅改归档扩展名）](external-context-extra/sim2sim_scene_matrix.cpython-312.pyc.bin)，60332B、SHA `d25d606fba156a1662869c7ee9e4fbdffbdf02b995c865abe06feb77c2d3ae64`。它映射回 `outputs/research/sdk018-canonical-build-6cb2ae2/context/scripts/research/__pycache__/sim2sim_scene_matrix.cpython-312.pyc`，并对应新cohort封存source下相同相对路径。只有目标不存在才恢复，已有目标须字节完全相同；不得覆盖canonical或任何alive任务依赖。本次只复制该文件原字节，没有生成/执行/修改bytecode。此额外文件是当前冻结身份恢复所需，不把历史canonical清单改称3298。

恢复 controls 时只将 `preparation/` 中原76项依赖及内层manifest映射回 `outputs/research/native-keyboard-reset-allkeys-preparation-01/`：目标不存在才创建，已存在则逐字节/SHA完全相同才接受；任何不同都应停止，不覆盖。上述新 plan 的绝对路径仍指向 `outputs/research/native-keyboard-reset-allkeys-cohort-01/cohort`，须先恢复全部真实外部 source/model 并按其3313项清单核对，不能仅凭这份小包直接运行。如果需要重新 prepare，依原README使用全新cohort路径/新plan，不覆盖现存attempt或伪造相同identity。

实际 `run` 只由 root 在原README门卫满足后授权：现有 `fresh629-sdk018-6cb2ae2-prepared02` 真正629完整、native/observer/CPU最终均0、1258 worker与629视频完整decode；原root session54334确认最终exit0；两actual GPU/CPU CID均停止；固定GPU UUID共享mutex空闲、GPU compute idle。controller会在同一独占flock下复核原terminal收据与实际CID。若 armed waiter 先获得锁，应拒绝启动，不能抢占。旧v5、正在跑的629、official训练和waiter均不改动。

Backspace仅验真实自有窗口键后的单次物理time下降、qpos改变与后续physics/control/depth推进；不宣称策略历史/SDK/gantry全部重置。新协议在o damping后reset，后续tick推进也不等于主动策略成功恢复。全部原字节复制与来源关系见[外层发布清单](publication-manifest.json)。
