# 正式学生训练曲线归档 v2：仅源码准备

本目录只编写并静态解析源码。没有调用 CLI、读取 TensorBoard event 内容、启动科学阶段、Docker、SSH、浏览器或 GPU；没有实际接受合同、正式学生曲线包、恢复成功收据。原训练、32 文件选择性 fetch、armed waiter、58/629 门卫均未修改。两类学生的未来实际产物必须分别独立验收、分别出版。

本v2只修补v1的日志归属绑定、inspect状态与接受合同自身引用闭包；v1静态独审指出这些must-fix，未获得执行准入，完整原字节保存在`source-original/v1/`。

`student_curves_archive.py` 仅使用宿主 Python 标准库，没有子进程或联网入口。科学提取及 Matplotlib 绘图在统一 Docker 内执行。旧 `cpu/` v1 不能准入：EventAccumulator 可能吞掉截断事件；出版依赖将绑定相邻 `cpu-v2/` 的严格 TFRecord 长度/CRC32C/完整 EOF 验证源码，已冻结版本：

- `extract_student_scalars.py`：19,320 B，SHA `e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12`。
- `plot_student_learning_curves.py`：12,268 B，SHA `6a14cfa86df96199e575384c48466d44046b1a2fad8ce76c1427b7d5add7abd0`。
- v2 `source-manifest.json`：4,141 B，SHA `0a652313753768928296cc34632698f794548fb718a33f51e9b8848a9dd0daf8`。只按字节核对，不改动冻结目录。

沿用教师归档的原字节保护、`gzip(mtime=0)`、连续分块和 whole SHA 思路；这是新学生报告 schema 的实现，不导入旧 publisher，也不把教师的四个 loss 或任意 `status=passed` 当作学生验收。

## 未来实际接受合同

Root 在真实 extract/plot 两阶段及独立后验均完成后才生成接受合同，并向出版 CLI 显式提供其经审核 SHA。现在不生成占位合同或假成功报告。

合同是 JSON，必须有 `schema_version=1`、`status=reviewed_actual_student_learning_curves_cpu_acceptance`、`kind=pure|finetune`。`files` 必须恰好有下列 13 个 role；每项均为实际宿主绝对 `path`、真实整数 `bytes` 和完整 `sha256`：

| Role | 实际文件和校验 |
| --- | --- |
| `input_contract` | 已由 extractor 接受的同 run 事件合同；不是本出版接受合同 |
| `scalars` | 原始 `scalars.json`，含所有 tag、逐样本来源、完整核心步数及 conditional coverage |
| `plot_report` | 原始 `plot-report.json`，绑定相同输入合同、事件、标量和 PNG/SVG |
| `extract_source`, `plot_source` | 实际 Docker `/code` 两源码的宿主提供者，必须等于上述冻结版本 |
| `cpu_execution` | 原始 host execution，真实 create0、attached child wait0、自然 container0、停止状态、source before=after |
| `cpu_phases` | 原始两阶段报告：按序 `extract`、`plot`，各真实整数 wait0，完整输入 before=after/unchanged |
| `created_inspect`, `running_inspect`, `final_inspect` | 相同 full CID/image/name 的实际 created/live/exited JSON，可为单对象或一元素 inspect 数组 |
| `root_review`, `independent_review` | 实际后验全文，`must_fix=[]`、通过状态及 `evidence_fingerprints`；自身全部 fingerprint 引用逐项核验 |
| `publication_source` | 实际调用的本归档源码自身，绝对路径与 `__file__` 相同、SHA 精确匹配 |

另有 `figures`，键恰为 `png`、`svg`，各绑定真实原件 fingerprint。必填`cpu_raw_logs`键恰为`create_stdout/create_stderr/attached_stdout/attached_stderr/extract_stdout/extract_stderr/plot_stdout/plot_stderr`，各是实际原始日志fingerprint（空stderr也按实际0B/SHA绑定并保留）；两review均须覆盖全部八份原件。八个canonical原日志path必须各不相同，空stderr可有同一SHA。host `execution.cpu_raw_logs`键恰为create/attached四项，每个phase有实际`stdout`、`stderr` fingerprint；各经实际provider映射后的canonical path及whole bytes/SHA必须逐项等于合同8项。`create_stdout`原字节经stat/wholeSHA核对后`.strip()`必须恰好为同一full container ID。两个 review 的通过状态只接受 `passed`、`passed_readonly_postexecution_review` 或 `passed_student_learning_curves_postexecution_review`；这不是孤立门卫。两份 review 的 evidence 必须至少覆盖实际输入合同、scalars、plot report、host execution、phase report、两源码和两图，所有自身引用都核 current SHA。两review还必须覆盖三inspect、本publisher源码、原native manifest和实际CRC模块hostcopy。Root 工具会话/父 wait 的实际证据也应由 review 纳入；本工具不会把用户填入的工具编号伪称 OS 观测。

CPU inspect 固定为已验统一镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`，runc、network none、无 GPU DeviceRequests/Devices、`Privileged=false`、GPU hidden、2 CPU/12 GiB；三inspect都要求`State.OOMKilled=false`、`State.Error=""`。四个实际 bind 为 `/code`、`/control`、`/artifacts` 只读以及 `/validation` 可写；根据这些真实 Mounts 翻译原报告中的容器路径，不重写原报告。Root/独审的 fingerprint 引用须有实际本地字节提供者，远端历史位置可作为纯 `native_path` 来源字符串保留，不能冒充本地可读取的文件。

实际 `source_before/source_after` 是非空fingerprint数组，至少覆盖两producer；`inputs_before/inputs_after`是非空fingerprint数组，至少覆盖输入合同、native manifest和全部原events。两份前后数组逐项相等且全部实际字节重新核SHA。实际 phase argv必须从 `/opt/php/bin/train-python -B` 开始，第三参数就是相应受审源码；其后仅接受约定输入、输入SHA、输出参数，plot可在末尾另给正整数`--window`。提取报告必须有实际原生 `official/passed/int0` manifest 和 final checkpoint iteration 9999（pure）或29999（finetune），全部事件属于同一实际 run。该 manifest 只是曲线来源身份门卫，不扩大为本工具独立证明的训练/模型质量。

纯学生核心 tag 是 `Loss/behavior`、`Loss/warmup_active`，各按序恰好0..9999；混合学生九个核心 loss 按序恰好0..29999，详见源码 `CORE`。缺步、重复、越界、乱序或任何非有限 scalar 均拒绝。顶层 `event_integrity_complete=true` 且每件原 event 的 TFRecord 验证须有同一 whole bytes/SHA、正 record 数、长度/CRC32C 和完整 EOF，同时核`expected_file`、空diagnostics、67,108,864 B记录上限和实际largest_record_bytes。通过记录不能由 EventAccumulator 成功读取替代。所有scalar row逐条核严格整数step/index、finite值、原event/tag、逐event连续sample index，coverage从原rows复算；core原rows本身必须按序恰好全range，不能只提交一个passed摘要。plot必须原样绑定相同`event_integrity_checker`、完整events、plotted tags和unplotted实际tags。奖励/episode、PPO gate 等 conditional tag 的真实缺步/重复等诊断不被补齐；全部实际 tag 和逐样本 JSON 保留。两种图的输入/figure/source SHA 都必须与实际报告一致。

## 未来 CLI

以下变量只能填写未来实际生成并审核的文件及 SHA；不是可现在执行的成功案例。

```bash
PUB=outputs/research/official-full/student-final-learning-curves-source-preparation-01/publication-v2/student_curves_archive.py
python3 -S -B "$PUB" publish \
  --contract "$ACTUAL_ACCEPTANCE_CONTRACT" \
  --contract-sha256 "$REVIEWED_ACCEPTANCE_SHA256" \
  --output "$FRESH_PUBLIC_PACKAGE"
```

全部原件/真实退出/接受报告校验通过后才独占创建输出。异常保留 partial 和失败描述，不重试、不删除原件；成功 manifest 最后写入。正式包里有相同原字节的 `student_curves_archive.py`，以后无需原宿主或科学包即可校验和恢复：

```bash
python3 -S -B "$PACKAGE/student_curves_archive.py" verify \
  --package "$PACKAGE" --manifest-sha256 "$REVIEWED_PACKAGE_MANIFEST_SHA256"
python3 -S -B "$PACKAGE/student_curves_archive.py" restore \
  --package "$PACKAGE" --manifest-sha256 "$REVIEWED_PACKAGE_MANIFEST_SHA256" \
  --output "$FRESH_RESTORED_DIRECTORY"
```

恢复先核完整包/清单/路径/分块/解码 whole SHA，全部通过后才创建全新输出。目标与 package 不得互为祖先；不覆盖 existing 或旧 partial。失败留下 partial，没有成功 `restoration.json`。不同 mode 的记录分别写文件，不 hardlink；只恢复原文件 mode，不恢复 uid/gid，不修改原 JSON 内部绝对路径。恢复收据仅在成功之后真实生成并由 stdout 返回，不自称已经执行过。

原始 events，以及任何超过25MB的 JSON/SVG/PNG/其他证据，都以 `gzip(mtime=0)` 保存；所有归档体使用连续 ≤25,000,000 B 的块，每块独立 SHA、offset、整件编码 SHA和原始 SHA。普通 PNG/SVG 另有直接可读的原字节预览；大图仍完整归档，index 明确提示先无损恢复查看，不丢弃、不重编码或伪造替代图。相同内容可共享字节块，恢复仍按每条路径自己的 mode。manifest 每条依赖都≤25MB，可避免 Git 100MB blob 上限；Git 不保留完整读写权限，因此包校验按 bytes/SHA，mode 只由 restore-map 重建。

Root/独审、CPU原始stdout/stderr、输入/source及其他 review fingerprint 引用闭包一并原字节归档。出版acceptance contract自身（含额外嵌套实际fingerprints）、所有已加载输入合同/inspect/报告及每份被fingerprint引用的`.json`继续扫描嵌套引用，至传递闭包结束；每个引用核真实whole bytes/SHA，循环只共享同一实际pin，不跳过后代依赖。原文档中相对清单path默认按该文档原目录解析；遇到repo-relative出处等不同命名空间时，只能由未来接受合同可选`relative_file_copies`数组精确指定`document_path`、`relative_path`、`host_copy`，核同一whole bytes/SHA且必须真正使用，不能猜基目录。JSON schema中用于说明的`bytes/sha256`描述字符串不是实际fingerprint，不能替代任一强制门卫的真实pin。对非`.json`原始stdout/raw/源码只归档原字节，不猜其中语义。需要的原始 events 若尚未取得，出版会拒绝并不创建结果目录；应由独立只读 transfer 提供准确 native path、whole SHA/bytes 原件，本工具不下载、不猜事件名、不制造替代 event。完整出版成功后，events 可从 Git 包离线无损恢复。

本包只证明已接受的 scalar 完整性、实际曲线及归档恢复合同。`quality/convergence/official_schedule_complete/seven_PT_acceptance/PT_ONNX_parity` 始终为 false；图形走势不是收敛或技能验收。

## v2 installed CRC模块与原路径

接受合同新增必填`native_file_copies`数组。每项是`native_path`（真实容器/历史原绝对路径）和`host_copy`（实际宿主绝对`path`、整数`bytes`、`sha256`）。`scalars.event_integrity_checker.crc_update_source`必须在该数组有精确映射；其原path/bytes/SHA不能删掉或替换为hostcopy。hostcopy必须是未来实际CPU中installed `tensorboard/compat/tensorflow_stub/pywrap_tensorflow.py`原字节的只读取得副本，不是网上下载的新版本。核原fingerprint==hostcopy whole bytes/SHA之后才解析引用；两review都必须覆盖该源。所有映射必须实际使用，禁止重复native_path或覆盖四个真实bind。示意字段只在`source-interface.json`中作为schema描述，不生成实际合同。

## 直接源码与概念出处

`source-original/v1/`保留本v2的直接冻结v1源码、NOTES、接口、清单、全部出处和独审原件，SHA/bytes见`source-interface.json`。`minimal-delta/`保存对该直接草稿的完整源码与NOTES差异；`full.diff`是全部两文件差异的串接，没有省略。新接口/清单/静态检查资料是新增文件，详见source-only manifest。

教师概念祖先是`outputs/research/official-full/teacher-high-climb-76-final-publication-binding-01/publish.py`和`replay.py`，本目录只冻结其原字节到`source-original/v1/source-original/teacher-conceptual-ancestor/`供来源审阅。借鉴原件SHA、mtime0 gzip、连续chunk与wholeSHA无损恢复思路，没有import、调用其Docker replay入口；学生合同、13roles、二phase、三inspect、core/conditional coverage和独立verify/restore是新的实现，不能把差异描述成只换label。CPU-v2最终五份源码/接口/清单/README原件也保存在`source-original/v1/source-original/cpu-v2/`，只作字节出处。

## 当前验证边界

当前只做AST、stdlib import白名单/禁止调用的静态核对、原件和diff字节核对。`publish/verify/restore`均未运行；因此没有实际package manifest、运行通过或restore成功声明。需要Root与独立静态审阅后，未来真实学生结束、CPU二phase/三inspect/完整EOF CRC及双方后验完成，再生成actual acceptance-contract并执行。任何缺文件、缺pin或gate失败都拒绝准入；fresh输出父目录需已存在，不能与输入原件目录互为祖先。gzip头和wholeSHA离线核验不证明科学收敛或模型质量。

## v1 → v2 最小修订范围

本v2的完整差异仅覆盖四个现行文件（publisher源码、NOTES、接口、静态记录）；`minimal-delta/full.diff`按文件串接全部差异。`source-original/v1/`完整保留v1当时所有文件，包含被独审指出must-fix的报告。未改v1或冻结CPU-v2，不增加运行器、科学阶段或通用监控行为。当前独立protocol单phase与正式学生extract/plot两phase出版无关，不在本工具中伪称正式输入或actual acceptance。
