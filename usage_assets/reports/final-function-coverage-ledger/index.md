# 最终功能覆盖：29项只读ledger

本包原字节封存 `b5095ba390c654f0cc0ef42e5a8e35f8972eb202` 审计时点的[ledger](ledger.json)、[摘要](summary.md)，以及其SHA绑定的[根README](declarations/README.md)、[动作README](declarations/motion_matching/README.md)、[训练README](declarations/wbt_training/README.md)、[部署指南](declarations/wbt_training/DEPLOY.md)、[note](declarations/note.md)、[usage](declarations/usage.md)。[出版清单](publication-manifest.json)绑定全部9个依赖的bytes/SHA及源路径；原ignored报告和六份原文没有修改。

新增缺口是两组：①指南命名方向键的真实派发与MuJoCo Backspace reset；②teacher/pure/finetune原生从PT继续训练的收据。root已分派runtime/validation只读准备短协议，实际native执行须等待现629正常终态及固定GPU锁释放，不改现official任务。

official16、cloud888、fresh629、最终58项、云默认SDK018接入仍等待实际终态/前置；12历史golden缺私人baseline，实体G1/D435i无硬件验证。生成、CPU fixture、smoke、正常退出和quality=false均不能替代正式训练或技能/课程成功。当前高层自主长程越障质量尚未成立。

六份 `declarations/` 文件是历史原文证据，保留内部原仓库相对路径；本包没有复制它们的整个依赖树，不能把该子目录当独立运行checkout。链接目标按manifest记录的原source路径解释。实际运行指南仍是当前仓库[note](../../../note.md)与[usage](../../../usage.md)。原摘要位于同样三层深度，已检查其发布后本地链接存在。

本次仅复制与校验六份声明原文、两份报告和出版wrapper，检查本地链接；没有重新验证全部历史源码/媒体SHA，也没有执行入口、测试、SSH、Docker、GPU、native、daemon或Git操作。ledger中的动态计数是当时本地文件观察，原动态JSON未另存，不代表将来终态。
