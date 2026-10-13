本目录是 student-final learning curves 的 CPU v2 源准备，尚待 Root/独立静态审查及未来真实 CPU 协议验证，未执行、未 import 新helper或科学包，未解析事件。cpu/ 原 v1 两源码及其全部历史原件保持不变；v1 初始审查结论因 EA 可吞掉坏尾部 DataLossError 的缺口已撤回未来执行批准，撤回addendum原字节保存在source-original/v1/。不能称v1已批准或v2运行通过。

v2只增加完整 TFRecord framing/CRC/EOF 门卫和plot对应门卫，原kind/target/core tags、无purge多event提取、nonfinite合法JSON诊断、conditional reward/PPO-gate真覆盖与未来CLI均保持：

```text
/opt/php/bin/train-python -B /code/extract_student_scalars.py --contract /control/input-contract.json --contract-sha256 <实际SHA> --output /validation/scalars.json
/opt/php/bin/train-python -B /code/plot_student_learning_curves.py --input /validation/scalars.json --input-sha256 <实际提取报告SHA> --output /validation/plots
```

每原event先由 verify_tfrecord(event_fp, crc_update) 严格读到完整EOF：header为little-endian uint64 length，紧随4-byte masked CRC32C；然后读取完整body和4-byte masked body CRC32C。payload每次最多1MiB，逐块增量CRC/SHA，不把声明的大长度一次读入RAM；单record payload上限64MiB，声明长度也不能大于原文件bytes。任一短header/短CRC/短body、错误CRC、长度越界、额外坏尾、I/O错误、整文件SHA/bytes或stat变化均failed并保留准确byte offset/record_index/record_offset诊断；不会只采纳已经齐全的core前缀或EA warning。EOF必须正好落在完整record边界且至少有一条完整记录。

CRC updater取自已有TensorBoard compat包，import发生在CPU Docker guard之后；mask公式由本源显式给出。未来实际报告记录安装模块文件指纹（event_integrity_checker.crc_update_source），该模块是固定Docker镜像的运行依赖，不是捏造的本次host安装验证。协议依据：[TensorFlow TFRecord格式](https://www.tensorflow.org/tutorials/load_data/tfrecord)、[TensorBoard compat CRC源码](https://raw.githubusercontent.com/tensorflow/tensorboard/master/tensorboard/compat/tensorflow_stub/pywrap_tensorflow.py)。这些upstream master引用只说明协议/故障语义，没有冒充已固定运行镜像版本或实际坏样本测试。

只有event完整性通过才逐file EventAccumulator(size_guidance={'scalars':0}, purge_orphaned_data=False)；不purge、不去重、不补步。纯核心Loss/behavior、Loss/warmup_active要求精确0..9999；fine九个共同核心Loss要求精确0..29999。所有实际scalar tags原row和来源保留，核心重复/缺步/越界/乱序及任一tag非finite不能passed。nonfinite原值写null+原repr+定位diagnostics，allow_nan=False合法failed报告。reward/episode、分支条件ppo_gate_mean仅报告真实覆盖/缺失/重复，不能硬补成target条数或称技能质量。

scalars.json新增顶层event_integrity_complete和event_integrity_checker；每events[].tfrecord_integrity必须是passed/TFRecord、原expected_file、整bytes/SHA一致、正records、complete_eof=true、crc32c_verified=true、diagnostics=[]。失败事件保留已检查bytes/read_sha256及准确offset诊断，不称整体SHA完整通过。plotter逐event核这些字段后才写图；plot报告同时保留完整性结果。PNG/SVG、report路径及其它API见source-interface.json，未来真实inputcontract/events/CPU/Root/独立审查均null。

source-original/v1是先前v1目录的逐原件快照（包括当时审查与撤回原件）；minimal-delta包含v1→v2两个源码、README及source-interface的完整unified diff，full.diff不包含自引用manifest生成差异。source-manifest逐bytes/SHA覆盖本目录静态依赖。这里只AST解析/字节核对，无协议fixture、无真实event解析、无Docker/SSH/训练/模型/GPU/科学重跑/H/Git/文档更改；Root未来会在隔离CPU容器实际验证协议和既有event，这不能假称正式学生训练/交付已经完成。

所有图表/报告仍仅是训练标量完整性和可视化；convergence、policy quality、完整官方流程、7PT、ONNX parity均false。armed paired学生交付门卫完全不动。
