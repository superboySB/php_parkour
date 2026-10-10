# 最终两学生本地58例验收的准备证据

[冻结入口及准确CLI](adapter/summary.md)、[机器设计索引](adapter/plan.json)、[47项CPU测试与真实缺模型分支](adapter/report.json)、[源码冻结](adapter/code-freeze.json)、[独立只读审查](independent-summary.md)。

当前仅完成控制器实现、47/47 Docker CPU控制面测试与真实missing-fetch waiting分支，尚未回传正式模型，真实模型prepare、60项ORT和58次native验收均未执行；实际prepare缺fetch分支也只返回waiting。缺fetch时没有cohort/Docker/native/GPU/daemon。33pass/1fail与中间41pass原件保留；仅最终47项有精确源码freeze，不能给旧candidate虚构源码身份。

实际未来模型准备成功后，四个顺序phase要求58case、116worker exit0/empty groups、116精确hostwriter出生映射及58原MP4完整解码；原8/10仿真秒、wall373/413、startup180、seed42不变，发布模型629运行不能替代这项自训模型验收。正常退出不等于课程成功。

`adapter/`是原ignored准备目录的逐字节副本，含26件原manifest依赖与原manifest；部署准备位置为`outputs/research/final-student-native58-preparation/`。运行需要现有已验证的canonical image/context、1887生成输入及真正completed selective fetch，不能拿本包的设计索引代替真实host-plan或最终模型。

恢复时还须保留原方向baseline两JSON及五个原helper路径；本包已按原字节归档两份baseline，[restore-map](prerequisites/restore-map.json)将它们与已复制helper映射回准确原路径。此包不是独立运行环境：canonical context/source-manifest、motion-matching matrix及1887生成文件、指定镜像、真实completed fetch和现fresh629成功/释放收据仍是外部前提；当前本机这些既有输入路径均存在，最终模型与629终态仍在等待。不要覆盖运行中控制文件。
