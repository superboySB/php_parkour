# recovered629 出版 adapter（仅准备，未执行）

Root 审阅后执行的唯一入口：

```bash
python3 -B /home/dzp/projects/php_parkour/outputs/research/fresh629-recovery-01/publisher-preparation/publish_recovered.py \
  --root-authorized-publish \
  --expected-contract-sha256 076053b2f59791f8403863fe509c64bf3c57b5c9e3acf0b26778b13b3325e3b7
```

固定目标 `usage_assets/reports/sim2sim-full629-sdk018-recovered/` 必须不存在；尚未ready时只返回waiting，不创建目标或staging。执行中失败保留独立`.partial-*`目录与publication-error.json，不覆盖既有出版、raw、严格publisher或gate。

首次和封存前实际调用冻结02 gate `dbc64d32...6525`，要求真实ready且返回完全一致；该gate只读Docker GET与既有证明，不启动任何资源。旧64dd的真实code1与stderr/stdout及修正版Root实际调用原件均从controller-adapter目录收入证据，不把旧143变为0。另要求四例process-exit.json实际wait0。

仅复用不变的strict publisher `5b0d967f...79a7a` 的validate_plan/validate_case/validate_attempt_archive与renderer。按已验证的私有sys.modules绑定加载冻结5e90 native validator，ROOT锚定原ROsource。adapter只提供原/新namespace映射；不会调用接受旧正常host事务的validate_driver，也不会制造它所需的success receipt。

629主画廊始终使用原629结果；四例补验保留独立cohort、原attempt number1、不同出生身份与单独视频页。633是实际attempt数，629是唯一配置数。原1250host映射/8历史缺失与补验8新映射分别保留；quality=false，阈值计数按原629与独立4分别列出。17代表固定每场景原config0，不选较好结果。

所有633次native output、sealed receipts、parent logs、reports、controls/source proof和三段observer raw stream的正文均保留；原两大流连续分块，每块≤25,000,000B，whole bytes/SHA和offset顺序入index。629全部视频均原字节复制，17代表只引用其中17段，不额外复制。大型模型/完整5206冻结树按Root明确范围不重复复制，保留原plan/freeze精确SHA和reproduction-inputs-external.json；**self-contained仅指验收raw证据，不代表独立还原GB级输入树**。

本次仅写adapter和静态读取既有源码/字段并记录冻结SHA，没有import/编译/测试/执行adapter或gate，没有启动CPU容器、Docker、SSH、native/GPU，也尚未创建目标出版目录。Root仍需实际执行及浏览器验证后才能宣称出版通过。
