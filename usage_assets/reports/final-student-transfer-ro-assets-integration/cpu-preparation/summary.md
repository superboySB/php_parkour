# 学生模型回传入口与新 watcher 路径集成

默认源树改为 `02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c`，默认覆盖目录改为 `coverage-official-final-ro-assets-v2`，对应已审核的 `posttrain_coverage.py` SHA `58b8978cb24d8a194133e6344c1fa415632413d83c92b18a21ebcc3b75ed5dfc`。原云镜像 `631d9e...` 与正式训练源树合同保持原值。

新增 `--coverage-output` 只接受远端 `root/outputs/` 下一个安全的 `coverage-*` 相对目录，并校验 selection 的绝对目录。等待与就绪回执均绑定请求的源树、monitor SHA、相对和绝对目录；旧目录的 CPU-ready 不能替代新目录。就绪回执升为 schema2，并要求 selection、CPU 科学回执和三份逐源片计划使用同一共享机器人资产合同。回传仍严格限于两个学生的四个 ONNX 和二十八个 JSON。

现有 Docker 的 CUDA-disabled CPU 测试 **77/77 通过**，原 57 项与新增 20 项全部保留，0 failure/error/skip。`tests-initial.xml`/`.log` 是首次实际运行原件，未改名为后续运行；文件名中的 initial 不表示存在未记录的失败。测试使用合成控制面 fixture，SSH/rsync/Docker 检查为测试替身，不代表正式日程已结束或最终模型已回传。

本次 agent 未执行 SSH/status/fetch，未启动 GPU/DDS。Root 可按 report.json 的 `root_next_read_only_status_argv` 做真实只读状态检查。修改前后源码和最小补丁完整保留；旧 helper/history/watch/raw 不改。
