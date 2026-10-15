# TensorBoard v3：源码与验证材料导航

这是独立阅读导航，补齐旧封存 README 中指向其他目录的四处链接。原 v3 seal `1dd8f052750c0584b3da7db1c01f0545aecdd37c6d5efeee8750d563fcdb1b2e` 与原文均未改动；下面链接指向逐字节相同的公开阅读副本。

- [容器内轻量启动器](sources/tb_launch_after_adoption_v3.py)
- [只读端口、事件与 HTTP 检查器](sources/tb_adoption_observe_v3.py)
- [已完成训练的离线末步基线](sources/tb-final-student-baseline.json)
- [v2 observer 独立源码审查](reviews/tb-observer-v2-independent-static-review.json)
- [正式学生浏览器检查器](sources/tb_final_students_browser_v3.py)
- [v3 独立源码审查](reviews/tb-v3-independent-static-review.json)
- [SDK v4 独立源码审查](reviews/sdk018-mount-order-v4-independent-static-review.json)
- [已有普通 CPU 协议结果与命令收据](cpu-controls/report.json)

v3 只将 Docker Mounts 的完整行按唯一 Destination 排序，保持其他身份字段及 Docker 原始 stdout；browser 和 launcher 的函数 AST 与原版相同，仅引用新 observer。原 CPU 记录为 18 项 observer 守卫、3 项浏览器拒绝及3个 help，全部真实退出0，属于源码与合成/普通 CPU 协议验证。

这些文件没有证明默认 SDK adoption、TensorBoard、SSH 转发、HTTP 或浏览器已经实际通过。离线基线的纯学生9999、混合学生29999末步也不代表课程成功率。实际接入仍需真实 SDK v4 adoption 结果、新 CID 与出生、同源 events 前后 SHA、6006 listener、原自有6007 SSH 以及真实 HTTP/browser 收据。

[原封存操作说明副本](origins/tb-v3-source-README.md) 保留了当时的全部文字和相对路径；阅读时请使用本页导航。源码中的原绝对 workspace 与外部依赖约束仍在，本页不是独立执行环境。副本来源、SHA 和范围见 [provenance.json](provenance.json)，原封印依赖见 [v3 manifest](origins/tb-v3-source-manifest.json) 与 [SDK v4 manifest](origins/sdk018-v4-source-manifest.json)。
