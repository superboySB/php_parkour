# technical_pipeline.md 独立只读复核

结论：本次没有发现新的实质事实缺口或措辞冲突，`substantive_factual_findings=[]`。没有建议改写算法公式或扩大验证结论。

重点核对了 teacher449/575、学生108+32、teacher450路由剥离；29维位置增量与PD；reward/GAE/PPO；冻结教师在线动作label；pure/mixed零label不同处理；mixed完整batch分母、10倍BC、critic不受gate缩放且value梯度不进depthCNN；residual gate采样/EMA/分位数/未来max与不恢复的统计状态。非学习链的数据IO、27维特征/L2分数、qpos/四元数布局、FK与converter边界、expertID和源片段覆盖也一致。

部署与real2sim2real节正确保留固定wireorder、default角metadata未自动应用、20184B SHM/无capturetimestamp、各控制时钟、SDK根位置零占位、IMU腰链以及真实相机/标定/真机尚未验证的边界。未用外部论文或他人评测代替本项目结果。

115项历史源码SHA全部可按原字节核验：110项直接匹配当前源码，5项匹配已发布历史source-before（原3份GUI文件，及后来更新的sim2sim监督与推理键盘入口）。这不表示115项都仍等于当前工作树。154个本地Markdown链接与源码行号均有效。详细检查和每份来源SHA见同目录JSON。

本次只读源码与文档，并用宿主stdlib做hash/链接核验；没有运行科学推理、GPU、DDS、仿真或云操作，没有修改README/技术文档/运行代码/冻结raw，也没有提交。完整官方训练、最终学生sim2sim、888源片与629物理扫描仍按各自真实证据判断，本文复核不替代这些验收。
