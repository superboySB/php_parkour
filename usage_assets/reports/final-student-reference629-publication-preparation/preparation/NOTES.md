# 正式两学生全参考配置：发布与恢复工具准备

这是经静态审阅的源码准备包。Root已用禁用site-packages的Python实际运行发布器与恢复器的 `--help`，均正常退出；实际状态入口的验证另以Root执行收据为准。`admission` 正文、实际正式模型、两模型各629配置的仿真与CPU后验、发布和完整恢复仍待真实完成。既有公开学生ONNX结果不能代替正式自训学生结果。缺先决条件时 `status` 返回 `waiting`/0，只说明等待分支正常，不是发布成功。

三个工具使用宿主已有标准库 Python：`python3 -S -B`。它们不启动 Docker、SSH、GPU、训练或仿真，不在宿主安装科学包。训练、ONNX推理、原生仿真和完整视频解码仍由原统一Docker流程执行，保存真实收据后才能进入发布门卫。

## 固定依赖与恢复来源

下表副本由Root按原字节封存在本目录 `dependencies/`，须与本准备包的独立审核清单一并校验。副本是恢复来源；当前工具仍核验并使用右列原路径，没有改成从这些副本运行。恢复前须验证副本SHA，目标不存在或已完全相同才能恢复；不得覆盖活动任务、部分结果或历史原件。

| 本目录内封存副本 | 固定SHA256 | 原执行/读取位置（相对项目根目录） |
| --- | --- | --- |
| `dependencies/final-student-reference629-preparation-01/`（35依赖及原manifest） | manifest `481d54ee84d4b2d9c439580fe83d00927a44bfc8e2a11101b58862b536d49ce0`；依赖逐项以原manifest为准 | `outputs/research/final-student-reference629-preparation-01/` |
| `dependencies/publish_full_scene_matrix.py` | `35432cb8fb8cc46391dc855f51065aaa3ca017ee9ad57a808ded567be29b19ca` | `scripts/research/publish_full_scene_matrix.py` |
| `dependencies/pull_final_students.py` | `a88f9731f23e3f1469d6d46f54cce5410ee2f5a40c0055523194e6f8ce0912bb` | `scripts/research/pull_final_students.py` |
| `dependencies/host_owned_launch.py` | `e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15` | `outputs/research/host_owned_launch.py` |

原项目根路径固定为 `/home/dzp/projects/php_parkour`。35依赖中的冻结科学源码、控制器、observer与CPU后验合同保持原判据；本工具复用旧发布器的纯标准库验证/渲染接口，没有合成旧单控制器或旧CPU执行收据。

## 命令入口

以下所有尖括号内容都是必须由Root审阅实际文件后替换的显式占位值。不得猜测未来SHA、使用示例哈希、把缺失文件补成成功收据，或把工具自己计算出的未审核SHA当批准值。本准备manifest须与独立审核记录一并校验；没有它时不能运行下面的等待分支。

仅检查缺少未来实际输入的等待状态，不创建结果目录：

```bash
python3 -S -B outputs/research/final-student-reference629-publication-preparation-01/publisher.py status \
  --preparation-sha256 '<REVIEWED_PREPARATION_MANIFEST_SHA256>'
```

实际合同与独立外部父进程收据齐备后，完整只读预检：

```bash
python3 -S -B outputs/research/final-student-reference629-publication-preparation-01/publisher.py status \
  --preparation-sha256 '<REVIEWED_PREPARATION_MANIFEST_SHA256>' \
  --contract '<ACTUAL_CONTRACT_PATH>' \
  --contract-sha256 '<REVIEWED_ACTUAL_CONTRACT_SHA256>' \
  --parent-start '<ACTUAL_OUTER_PROCESS_START_PATH>' \
  --parent-start-sha256 '<REVIEWED_ACTUAL_OUTER_PROCESS_START_SHA256>' \
  --parent-exit '<ACTUAL_OUTER_PROCESS_EXIT_PATH>' \
  --parent-exit-sha256 '<REVIEWED_ACTUAL_OUTER_PROCESS_EXIT_SHA256>'
```

真正发布沿用上述全部实际参数，将子命令改为 `publish`，并追加 `--output '<ABSENT_PUBLICATION_DIRECTORY>' --root-authorized-publish`。输出目录必须全新，其父目录必须已存在。该标志是内部operator门卫，不是新用户审批；缺证据仍拒绝。失败保留首个partial目录，不自动重试，不留下完整成功manifest。

完整发布后，从经审核的实际包恢复到另一个全新workspace：

```bash
python3 -S -B outputs/research/final-student-reference629-publication-preparation-01/restore.py \
  --package '<ACTUAL_COMPLETE_PUBLICATION_DIRECTORY>' \
  --manifest-sha256 '<REVIEWED_ACTUAL_PUBLICATION_EVIDENCE_MANIFEST_SHA256>' \
  --output '<ABSENT_RESTORED_WORKSPACE>'
```

恢复工具只有这三个参数；不调用发布器、科学模块或容器。它必须先验证实际完整manifest及整个包，才独占创建输出根。成功时最后生成 `restoration-receipt.json` 并向stdout说明恢复数量；失败保留partial和可写出的失败诊断，不生成成功回执。该文件是实际恢复函数的文件证据，不是独立父进程退出证明。此说明不代表恢复已经执行。

## 完整发布的真实门槛

- 实际最终模型与JSON来自原严格选择性transfer，绑定正式pure/finetune pair、前置58例验收/60项CPU ORT、实际冻结配置与输入；不能用公开ONNX、源码准备或CPU fixture替代。
- 明确审核的实际合同与 `host_owned_launch.py` 外层start/exit收据，实际父进程wait0；两kind原生执行共享这个真实outer身份，不伪造两份独立父收据。
- 两kind各629完整逐帧参考配置、17命名场景，完整15维50Hz指令及实际参考帧数，原生parent0、各1258 worker正常退出/组空与1258唯一宿主writer出生映射；合计1258配置、2516 worker与2516映射。
- 两kind各自新CPU `create/start/wait` 实际0、own CID身份匹配且已停止，各629原MP4完整解码；合计1258全片解码。接收原新CPU schema，不虚构旧 `docker exec` 或独立CPU父进程证明。
- 原source/overlay/input/model/plan/receipt/seal/记录NPZ与raw/media全部哈希、精确file-set和初次绑定期望在复制前后仍一致；首attempt、所有阈值及原日志完整保留，不失败后自动择优重试。

即使全部门槛通过，`quality_verified=false`、`obstacle_course_completion_verified=false`；1258是两模型配置次数，不是1258独立几何或成功技能，亦不证明收敛、PT↔ONNX parity或实体G1/D435i成功。

## 自包含字节与恢复边界

实际发布包按内容保存全部已验inventory正文，不以原宿主绝对路径+SHA替代可取得的文件；同字节可共享存储，`restore-map.json` 保留每条原路径、合法workspace相对路径及各自mode。大raw按连续offset拆为每块不超过25,000,000字节，保留每块与whole SHA；原视频/图片保持可播放原字节，不重新编码，媒体达到100,000,000字节会明确拒绝，所有发布Git blob均须小于100MB。

恢复逐路径独立创建文件、核原字节后逐项chmod，不hardlink不同mode文件，不恢复uid/gid，不覆盖任何existing/partial/history。恢复不重写JSON/脚本中的内部绝对路径；若workspace位置不同，文件恢复成功并不代表这些固定路径控制器可直接运行。未来执行前必须按原合同恢复原路径并重新审核真实输入与依赖。Docker镜像层、驱动、GPU设备和硬件不属于该文件包，仍按项目统一Docker配置另行恢复。
