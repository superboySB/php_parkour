# 新独立批次的 CPU 准备

旧批次在41例后被GPU空闲检查拦住，原失败及41原片[单独保存](../native58-preserved-failed41-01/README.md)。本包是新路径的准备记录，不续写旧失败。

未修改的31ecc原prepare于2026-10-15 06:27:18 UTC实际开始，真实e238父进程退出0；两只CPU容器无GPU/runc/无网络并自然退出0。纯/混合学生共60项ORT通过，默认29关节姿态最大误差均为0；root逐项验证5241冻结文件的完整集合与SHA。

[原主审](root-review.json)保留实际模型、CPU容器/时间与父进程身份。[原件索引](raw-inventory.json)保存plan/freeze、CPU全部报告和日志、原parent/start/exit以及主审代码/原始inspect。

这是当时尚无native运行的CPU准备快照。四模型与首次回传同字节，见[模型恢复包](../student-transfer-cpu-actual-02/README.md)；完整科学源树与1887输入不在此重复归档，仅以冻结清单绑定。后续原生状态见[续做记录](../index.md)，CPU通过不表示技能成功。

```bash
python3 cloud888_report.py restore --input . --output /tmp/native58-cpu-prepare-new --manifest-sha256 <外部已审查的包SHA256>
```

标准库恢复完整原字节/权限，不执行模型或仿真。
