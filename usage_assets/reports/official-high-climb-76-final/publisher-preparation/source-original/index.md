# 高攀爬教师最终证据：仅源准备，尚未出版

本页是未来第五位 `teacher-high-climb-76` 完整官方教师证据的待绑定模板。目前只完成 publisher/replay 源适配；未运行出版器、事件压缩还原或 public replay，未创建公开证据目录。原生终态、最终模型 SHA、TensorBoard 标量和曲线、CPU 五阶段及 root/独立后验结果均未由此准备验证。不能使用前四位教师的结果替代第五位教师本阶段。

未来允许出版前，root 必须从实际 `passed` / 整数返回码 0 / checkpoint iteration 19999 的本阶段 manifest 和稳定选择性 transfer 绑定五个同次训练原件（基线 PT、最终 PT、ONNX、YAML、唯一实际 event）。还必须绑定实际生成的 CPU contract/source proof、root/独立后验报告、五阶段回执、input-binding/scalars 报告、真实曲线图，以及本阶段新的 terminal Q 和单个 root terminal report。未知路径、字节数、SHA 和结果目前保持 null/false；绑定后需要新的完整源/输入复核，不能直接把本模板当已出版结论。

完成未来绑定时，本页也须用本阶段真实报告更新并重新封存。CPU 数值检查不等于策略技能、物理稳定性、收敛或 PT↔ONNX 数值 parity，不能推出整个官方日程完成。

原始 JSON 和日志保持原路径/字节；event 将以 gzip(mtime=0)保存，需要时连续切为 <=25,000,000 字节文件，并实际流式还原核 whole SHA/bytes。ONNX 不入 Git，external-onnx 合同必须记录本阶段实际 bytes/SHA/下载命令；没有预测模型大小或 event 名称。

未来发布时，最终 `artifacts/model_19999.pt` 和同次训练 `cpu-01/input/model_00000.pt` 必须显式 `git add -f`，再从 fresh Git archive 对照完整 evidence-manifest 核验，避免 *.pt 被忽略。

未来 replay 保留已有隔离合同：统一镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`，runc/无网/GPUhidden、2 CPU/12 GiB、三个只读输入挂载和一个全新可写 validation 挂载，完全相同的五阶段 CPU 源码。实际调用前先核完整公开包、还原同字节 event/模型输入并核外部 ONNX SHA；本准备未执行这些动作。
