# 资源等待控制02与实际启动前拒绝

此包保存新独立58批次的宿主控制02（32依赖、38普通CPU控制、原e238真实0/7/130协议）、独立源码/父进程入口审查及真实合同。原科学源码、CPU计划和模型保持不变。

实际只读gate于2026-10-15 15:05:56北京时间退出1，stderr为 `Failed41 stopped143 current inspect changed during recheck`。原生任务尚未开始。最后重核直接比较完整Mounts列表，Docker返回顺序可能变化；后续修订必须规范完整行顺序，挂载内容和其他容器字段继续严格核验。本包不修改该失败或封存源码。失败调用的原API响应没有在旧入口独立保存，不补造瞬间raw。

原32依赖、80个CPU协议原件和真实gate stdout/stderr/实际wait均以工作区原路径归档；完整模式见raw-inventory.json。source-only与失败门卫不构成完整58或技能成功。四模型与新CPU准备见[独立包](../native58-resource-wait-cpu-prepare-02/README.md)。

外部核验evidence-manifest.json的SHA后，可用标准库无损恢复到新目录：

```bash
python3 -B cloud888_report.py restore --input . --output /tmp/native58-control02-originals-new --manifest-sha256 <外部已审SHA>
```
