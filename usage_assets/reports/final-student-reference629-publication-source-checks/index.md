# 发布工具源码：检查记录

[源码包与恢复步骤](../final-student-reference629-publication-preparation/index.md)仅为源码准备，正式两学生1258例与完整结果发布/恢复尚未执行。

源码包经过[初审](release-review/01.json)、[外部目录说明修正](release-review/02.json)与[Git权限兼容修正](release-review/03.json)。

Root随后实际执行包内标准库复制示例：68份公开文件模拟Git下载权限（66项权限变化），在工作区之外的临时兄弟目录恢复92个源码路径，逐项校验bytes/SHA/mode及独立文件，真实child.wait=0；临时目录已删除。[执行记录](source-copy/receipt.json)、[原stdout](source-copy/stdout.raw)、[独立核对](source-copy/independent-review.json)保留范围。该操作没有覆盖原固定工作区，也没有启动Docker、训练或仿真；不是完整结果恢复。

`quality_verified=false`、`obstacle_course_completion_verified=false`。
