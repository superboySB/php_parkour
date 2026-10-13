# 正式学生曲线：原始记录完整性检查

2026-10-13 的补验发现：现有最终学生选择性回传只有4份ONNX和28份JSON，不含正式训练原始TensorBoard事件。此前两轮学生的截图不能替代纯DAgger的10,000轮和DAgger+PPO的30,000轮曲线。新工具单独补齐这项交付，原16阶段、7份PT、888次逐源尝试及最终模型验收门槛保持不变。

## 已实际完成的检查

同一统一镜像 `2be18521…` 的独立CPU容器实际执行了一次日志协议补验：runc、断网、GPU隐藏、2 CPU/12 GiB，两份只读输入和全新可写输出。create、attached wait和容器自然退出均为0，原始来源文件前后SHA一致。

| 输入 | 实际结果 |
| --- | --- |
| 3个CRC32C标准向量 | 全部匹配 |
| 3个正常合成TFRecord案例 | 接受，包含多记录、空payload及跨1MiB payload |
| 17个损坏/身份不符的合成案例 | 按预期明确拒绝；包括完整前缀后的坏尾、两种CRC、截断、长度越界及whole SHA错误 |
| 原high-climb-76教师事件 | 72,561,360 B，1,040,001条完整记录，最大payload85 B；CRC、EOF及whole SHA全部通过 |

真实教师事件SHA为 `ca8621a8c9919f27c3bfd0e397ba4d425f3eb5904ed0f797e5eed5b6b6cd0478`，已在[原教师事件归档](../official-high-climb-76-final/tensorboard/event-archive.json)按原字节保存。上述合成案例仅测试文件协议，不是训练数据或学生验收。没有重新运行教师训练。

[实际protocol完整报告](protocol-actual/validation/protocol.json) · [create/attach/inspect原回执](protocol-actual/execution.json) · [Root后验](protocol-actual/root-review.json) · [独立后验](protocol-actual/independent-review.json) · [实际安装的CRC/RecordWriter原始源码](protocol-actual/validation/runtime-sources/)

无损归档的字节协议也已实际通过[6个正常与7个拒绝案例](byte-archive-actual/protocol.json)：25,001,024 B不可压缩输入形成25,008,672 B gzip和两个连续块，恢复whole SHA与权限一致；错位、丢块、字节损坏、SHA错误及截断/追加gzip均被拒绝。该试验明确使用合成字节，不生成学生接受合同。[实际调用及Root复核](byte-archive-actual/root-review.json)与[固定源码](preparation/check_archive_bytes_v2.py)保留。

## 新工具的输入、输出和门槛

[extract_student_scalars.py](../../../scripts/research/student_training_curves/extract_student_scalars.py)只在CPU Docker内读取显式SHA绑定的输入合同。合同必须指向真实完成的official原生manifest、最终同run checkpoint身份及该run的全部原始事件；它不加载模型。pure核心tag为 `Loss/behavior`、`Loss/warmup_active`；finetune核心包含PPO系数、学习率、total/surrogate/value/behavior loss、entropy和KL等9项。核心step必须分别完整覆盖0..9999或0..29999，按原顺序每步一次，数值有限。

读取标量前，先逐记录核对长度、header/payload的masked CRC32C、完整EOF与文件whole SHA；记录payload上限64MiB，分1MiB读取。不能依靠TensorBoard对损坏尾部的宽容处理。保留所有实际tag和样本来源；奖励等条件tag缺失、重复和范围均如实报告，任何实际非有限值使验收失败，不补点、不去重。

[plot_student_learning_curves.py](../../../scripts/research/student_training_curves/plot_student_learning_curves.py)以完整标量JSON及其SHA为输入，输出PNG、SVG及来源报告。原始点全部保留，后向均值窗口默认25个样本；出现缺步或乱序时断开平滑线。未绘制tag仍保留在原始标量JSON。

[student_curves_archive.py](../../../scripts/research/student_training_curves/student_curves_archive.py)以真实CPU两阶段、创建/运行/终态inspect、8份原始stdout/stderr及双方后验共同绑定的接受合同为输入。它逐项核对日志角色和真实来源，重新检查完整scalar rows和coverage，并归档原事件、原JSON、图像、源码及引用闭包。所有大于25,000,000 B的原件和所有事件均以mtime=0的gzip连续分块，恢复时核对原whole SHA及权限；原JSON内部绝对路径不改写。`verify`先检查完整包，`restore`仅向全新目录写原字节。安装CRC模块需提供原路径对应的准确host copy。

这些工具的准确CPU挂载、命令行和合同字段见[CPU接口](preparation/cpu-v2/source-interface.json)及[归档接口](preparation/publication-v2/source-interface.json)。其中占位说明是未来真实输入的schema，不是已经通过的接受合同。初版拒绝意见与修正差异也按原字节保留。

纯学生原生训练及真实最终事件取回、CPU提取/绘图、公开包校验和全新目录恢复现已完成，结果见[正式纯学生曲线包](../official-student-pure-training-curves/index.md)。43个tag、430,000条标量均有限且每项覆盖0..9999；完整标量JSON为102,766,974 B，已按原字节压缩归档，不因Git单文件限制删减tag或样本。混合学生仍在训练。文件完整、loss有限与正常退出不能证明策略收敛、越障成功、PT/ONNX数值一致或真机效果。

[公开包完整CPU重放](../official-student-pure-training-curves-replay/index.md)随后实际通过：重新恢复和组织原合同、事件、配置及四份冻结代码，在新容器执行两阶段，完整430,000行及来源/coverage均相等。页面提供实际跑通的单命令入口。
