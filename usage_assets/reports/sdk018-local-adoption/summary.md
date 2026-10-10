# 本地默认容器已采用SDK0.1.8统一镜像

2026-10-10北京时间17:30，实际先核对原默认容器只剩sleep与本项目离线TensorBoard，没有原生仿真/训练进程，再将原image保留为`php-parkour:research-sdk016-retained`，把已通过实际断网验收的`2be18521…`标记为`php-parkour:research`，按原compose重建本地默认容器。新CID为`8e66b49c…`，实际image为2be18521，私有IPC，三个环境doctor通过。

当时其它本地容器的ID、image、StartedAt和running状态全部保持相同；本轮不包含云端命令，没有中断官方训练。原离线TensorBoard6006已在新默认容器重新启动，独立HTTP检查返回200。默认容器日常绑定工作区源码；镜像烘焙的是6cb2ae2，后续实际源码版本应结合单独快照判断，不能仅凭tag认定完全一致。[实际receipt](receipt.json)、[doctor](runtime.json)、[HTTP复核](tensorboard-http-check.json)。
