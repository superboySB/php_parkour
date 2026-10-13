# 学生曲线两阶段 CPU 执行器（仅源码准备）

`run_phases.py` 尚未执行。它只以真实子进程运行已审查的 extract、plot，不导入模型或训练代码，不代表学生曲线或完整系统已经通过。

Root 的独立宿主执行器应使用现有固定 2be 镜像，`runc`、`--network none`、2 CPU、12 GiB，`CUDA_VISIBLE_DEVICES=`、`NVIDIA_VISIBLE_DEVICES=void`，不授予 GPU、额外设备或 privileged。仅四个绑定：代码到 `/code:ro`、真实输入合同目录到 `/control:ro`、真实产物目录到 `/artifacts:ro`、全新空输出目录到 `/validation:rw`。容器内脚本检查这四个挂载的访问属性并拒绝其下额外子挂载；镜像/CID/网络/CPU/内存及完整挂载来源由 Root 的真实 create/start/inspect 收据核实。

`/code` 中应为本脚本与 source-manifest 中固定 SHA 的 `extract_student_scalars.py`、`plot_student_learning_curves.py`。唯一调用为：

```sh
/opt/php/bin/train-python -B /code/run_phases.py --contract-sha256 <真实/control/input-contract.json的64位SHA>
```

合同使用已审查 extractor schema1，`kind` 为 `pure` 或 `finetune`。所有嵌套 `{path,bytes,sha256}` 文件指纹必须实际落在 `/control` 或 `/artifacts`；因此可选保存 YAML 也绑定到完整 before/after 清单。`native_path` 只是原始来源名，不替换原文件或伪造合同。原始事件与同 run 的真实终态 manifest 仍由 extractor 的现有严格门卫验证。

阶段 argv 保持原 extractor/plot 接口；各自独立保留 `/validation/{extract,plot}.{stdout,stderr}` 完整字节与指纹。extract 真实退出 0 且报告通过后，原 installed CRC 模块字节复制为 `/validation/runtime-sources/pywrap_tensorflow.py`，记录 `runtime_source_copies=[{original:<fp>,retained:<fp>}]`，供出版合同显式映射。plot 输入绑定 extract 报告真实 SHA；两个图及报告必须真实存在且源/输入匹配。最后写 `/validation/phases.json`，失败保留已有文件，停止后续阶段，不重试、不覆盖。报告保留 quality/convergence/full-schedule/seven-PT/parity 为 false。

本目录清单只冻结作者的源码与说明，不包含 Root 后续宿主执行器、未来输入合同或实际运行产物。此阶段仅 AST 解析和文件指纹检查，未运行入口、容器或科学任务。
