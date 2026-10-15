# 最终学生 ONNX 原件

本目录保存本轮训练的两个最终 student/depth 配对：pure 对应 iteration 9999，finetune 对应 iteration 29999。
四个模型采用无损 gzip，保留实际 32 文件回传的 before/after/status 与其余 28 个 JSON 原件。
模型 CPU 导出/运行检查通过；原生仿真和物理质量验收仍待完成。

只使用 Python 标准库。先从已审查外部记录取得本目录 manifest 的 SHA256，再验证并恢复到新的空路径：

```bash
python3 verify_package.py --package . --manifest-sha256 <已审查的模型子包SHA256> --restore-models /tmp/student-pairs-new
```

恢复路径必须不存在，父目录必须已经存在；不会覆盖工作区模型。恢复目录含 pure/ 与 finetune/ 各两个 ONNX。
