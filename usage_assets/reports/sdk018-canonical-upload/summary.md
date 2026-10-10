# SDK0.1.8 完整统一镜像上传

实际完整 Docker 归档 **10,897,464,145 字节**，SHA-256 `03fbce4defd450f365e7654de7fef6308d390301df520562f5b0fb9e1d1f9280`，已传输到 `/diff/dzp_is_sb/php-parkour-research/images/` 并在服务器加载；独立复核再次读完本地包并核对远端 SHA。两端 Config/RootFS 指纹为 `9dc4e5696747951769505625a96dddc5bfd3240e3ff504db7dbef4526b2d8395`。本地 image ID 为 `2be18521…`，远端 Docker 存储转换后为 `fdfb7221…`。[完整核验回执](independent-upload-verification.json)。

新 tag 是 `php-parkour:research-sdk018-canonical-candidate`。云端原 `php-parkour:research` tag、正在训练的原 container ID/image/PID/StartedAt 及全部挂载内容均未改变，没有额外 GPU 任务，也没有重建训练容器。

上传 helper 的首次后验因 Docker inspect 挂载数组返回顺序改变而误报失败；[原失败 receipt](receipt.json) 和原日志保留。独立核验按 Destination 排序逐字段比较，确认内容相同；镜像与包校验也重新完成，既未重传或重启训练，也未把失败原记录改成 passed。新镜像已通过[实际断网 Isaac 小训练验收](../sdk018-canonical-offline/summary.md)，这次上传不代表官方长训练完成。
