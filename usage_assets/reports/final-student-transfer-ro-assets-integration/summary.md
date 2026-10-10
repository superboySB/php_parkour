# 学生模型回传入口与新 watcher 路径集成

默认源树为 `02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c`，默认覆盖目录为 `coverage-official-final-ro-assets-v2`，对应已审核的 `posttrain_coverage.py` SHA `58b8978cb24d8a194133e6344c1fa415632413d83c92b18a21ebcc3b75ed5dfc`。原云镜像 `631d9e...` 与正式训练源树合同保持原值。

新增 `--coverage-output` 只接受远端 `root/outputs/` 下一个安全的 `coverage-*` 相对目录，并校验 selection 的绝对目录。等待与就绪回执均绑定请求的源树、monitor SHA、相对和绝对目录；旧目录的 CPU-ready 不能替代新目录。就绪回执升为 schema2，并要求 selection、CPU 科学回执和三份逐源片计划使用同一共享机器人资产合同。回传仍严格限于两个学生的四个 ONNX 和二十八个 JSON。

现有 Docker 的 CUDA-disabled CPU 测试 **77/77 通过**，原 57 项与新增 20 项全部保留，0 failure/error/skip。[JUnit](tests-initial.xml) 和[日志](tests-initial.log)是首次实际运行原件。测试中的 SSH/rsync/Docker 检查使用合成控制面 fixture，不代表正式日程已结束或最终模型已回传。[修改前后源码与最小补丁](minimal.patch)供独立核对。

Root 于 **2026-10-10 10:19:48 UTC** 实际执行只读 `status`，exit **0**；[原始 JSON](root-readonly-status.json)与[空 stderr](root-readonly-status.stderr)逐字节保留。独立核对源树、monitor SHA、相对目录、绝对目录与上述新合同全部一致。实际状态为 **waiting**：16 个阶段阻塞，首项 `teacher-locomotion: running`，CPU-ready 尚不存在；`gpu_started`、`transfer_started`、`quality_verified` 均为 false。该状态说明正式训练仍在进行，不表示模型已就绪或回传已完成。

[详细报告](report.json)记录核对字段、命令与 SHA；[总清单](manifest.json)封存全部文件。原冻结 CPU 报告、摘要与清单分别原样保留于 [cpu-preparation](cpu-preparation/report.json)，源文件、补丁与测试原件保持原字节。未修改正式训练、watcher、源码/tests、主文档或旧证据。
