# 技术文档三处新增内容复查

文档SHA256：`f08944c34dce63b1e25a37c4f2fb3f5bf60de2b8f1dee34d4ced8cc043fb4979`，584行。旧审查JSON/MD按原bytes复制到history，旧文件仍未更改。

- 第550行：15:12历史快照计数合计629，保留执行失败且未写完成，准确。
- 第561行：选择性回传输入/输出、57项fixture CPU通过、实际waiting及尚未执行的最终模型ORT/物理验证边界准确。
- 第571行：故障时间线已准确区分parent发现异常、simulator收尾、parent最终exit1。

本地链接132个，缺失0个，越界源码行号0个。115源码SHA结果从上一份审查明确继承，本轮没有重读115源或2230输入/媒体。

仅计数/PID观察：2026-10-10T07:33:10.398587+00:00，{'completed': 237, 'execution_failed': 2, 'running': 1, 'planned': 389}；wrapper18564、driver18565及其后代PID记录于scan-counts-pids.json。顶层completed_configurations=2是运行中旧pilot派生字段，不能代替逐selection计数。没有启动GPU/DDS、仿真或云端操作。
