# 新完整58例的独立只读CPU后验

实际新批次完整58例结束后，通过原e238父进程执行独立验收。验收与父进程真实退出0，must_fix为空；核对58case、116worker及宿主映射、60ORT/默认姿态/原四模型与冻结输入。

独立容器runc/network-none/noGPU，仅整个repo一个RO挂载；实际重新完整解码全部58原MP4，各有正视频帧和progress=end。每次Docker exec真实wait0、完整stdout/stderr保留，检查前后容器身份未变。资源控制04的原9次GPU检查及全部查询/API日记、旧41失败释放与历史root143/八缺口分开核验。

[机器摘要](report.json)保存实际完整review和父进程SHA；原7.1MB完整JSON、116解码raw、全部父进程日志、严格CPU观察与31文件源码准备均无损归档。原58影片/worker/model完整数据另由最终58结果包负责，旧41不混入本次58。

外部核验evidence-manifest SHA后，可标准库恢复全部原件：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/native58-independent-review-originals-new --manifest-sha256 <外部已审SHA>
```

本后验仅证明执行与媒体/证据链完整，不宣称课程成功率。[新控制与启动](../../native58-resource-wait-control-preparation-04/README.md)；[当前进展](../index.md)。
