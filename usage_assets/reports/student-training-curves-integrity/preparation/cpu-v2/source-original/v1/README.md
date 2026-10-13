本目录仅为正式学生完整训练标量/曲线提供可审查 CPU 源码。没有实际事件、终态绑定、提取报告、图片、容器或通过结论；只做 AST 解析，未 import/执行两入口或科学包。future actual 路径和 SHA 在 source-interface.json 中为 null/类型说明，不能充作实际 input-contract。

extract_student_scalars.py 接受 --contract /control/input-contract.json --contract-sha256 <实际SHA> --output /validation/scalars.json。contract 精确字段见 source-interface.json：kind、原 native_manifest 指纹、native_run_directory、CPU run_directory 和 events 各原路径/bytes/SHA。native manifest 必须是该学生官方 passed / integer0 / 最终 iteration9999或29999，checkpoint.parent 与全部原 event basename 绑定同run。run_directory 必须是只读 /artifacts 映射，全部 events.out.tfevents.* 的实际集合必须与合同完全一致，不能漏掉第二个事件或把其它run混入。input-contract/native manifest/events/源码逐字节核验并在后验重核；Root未来另保存远端真实出处/稳定性及实际Docker执行证据，本文不代替这些证明。

逐文件 EventAccumulator(size_guidance={'scalars':0}, purge_orphaned_data=False) 保留原重启/重复记录。纯学生要求 Loss/behavior、Loss/warmup_active 实际精确0..9999；fine要求两update分支共同输出的九个Loss标签实际精确0..29999（完整列表在源码/接口）。任何核心缺步、重复、越界、顺序异常、非finite不能passed。所有实际scalar tags及原row来源保留，不重命名，不去重，不补步。非finite写null和原repr+定位diagnostics，failed报告仍是allow_nan=False合法JSON；原events仍为权威原件。

Train/mean_reward、Train/mean_episode_length 条件写入，Loss/ppo_gate_mean仅PPO update分支输出；都记录真实覆盖、缺失、重复及顺序，缺样本不补齐。其它实际tags同样完整保留。任何tag的实际非finite仍拒绝通过。报告逐row保留source_event/event_sample_index，多文件按合同声明顺序读取；若核心原序列不能精确达到0..target-1则保留原问题并failed，不能重排/删旧event来获得passed。

plot_student_learning_curves.py 接受 --input /validation/scalars.json --input-sha256 <实际提取报告SHA> --output /validation/plots [--window 25]，再次核精确核心序列、所有绑定输入/源码，输出 learning-curves.png、learning-curves.svg、plot-report.json。原采样点全部保留；均值线在缺步/重复/倒序处分段，绝不插值或跨缺失平滑。图包含核心loss、reward/episode及fine条件PPO gate；其余实际tags保留在完整scalars.json并以unplotted_actual_tags明示。

future Root执行器需另提供两phase实际wait0、正确image/runc/networknone/GPUhidden、原始start/finalinspect及自然stop0、源/输入前后相同、独立后验。两脚本在CPU Docker guard之后才导入TensorBoard/Matplotlib，不依赖host科学包。提取器只验标量完整性，绘图器只可视化这些实际值；quality/convergence/whole schedule/7PT/ONNX parity全部false。图或loss下降不能代替学生技能、58/1258物理case或全部官方流程验收。

source-original保留已完成教师五阶段验收的直接原始accept_teacher.py与plot_learning_curves.py；minimal-delta保存两份完整unified diff及full.diff。新源删除教师PT/单ONNX/PPO配置验收功能，只保留并加强学生事件和曲线所需逻辑；native算法/模型/训练不改。原teacher文件、armed paired gate、H、项目docs/README/Git及正在运行的任务均不动。无科学重跑、网络或Docker操作。实际报告可较大，未来publication需将大JSON和event一同保真分块，不能丢原rows。
