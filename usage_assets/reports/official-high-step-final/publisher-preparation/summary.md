# 高台阶 publication 源准备（尚未执行）

本目录只封存和适配源码。最初准备时，真实高台阶 transfer 及生成的 CPU 合同已绑定，CPU 后验三份报告当时保持 null；该初始快照现保留在 binding-history。随后实际五阶段 CPU 验收及独立复核完成，三报告已由 root 绑定。出版器仍须经新的 root/独立源码复核后执行。本准备代理没有运行 replay、Docker、科学脚本或下载，也未创建 usage_assets 目标。

source-original/ 是低台阶 publication-preparation 的十一份原字节文件；diffs/ 完整记录两 helper 的变更。binding-originals/ 是本次实际高输入的源/元数据小副本，模型和 event 只记录真实 transfer SHA，未复制进 preparation。publication-plan.json 精确列出这些依赖和待绑定报告。

原件 Q171218 + P170036 的单个 root-terminal-transition-verification.json 是本次终态来源，不复制整个 P 的 handoff/history。CPU 生成目录的实际 pins 在 preparation.json/contract.json，未链接不存在的 preparation-manifest.json。

未来原始 event 将 gzip(mtime=0)并在需要时按 <=25,000,000 字节分块，publisher 会实际流式还原核 whole bytes/SHA；ONNX 保留外部下载合同，public replay 先核 exact SHA 再在无网 GPUhidden runc 内复用五 phase。此准备没有声称上述动作已执行或技能/收敛已通过。

发布后 root 必须显式 force-add `artifacts/model_19999.pt` 与 `cpu-01/input/model_00000.pt`，再从 fresh Git archive 核完整包/manifest；工作区存在和 SHA 正确不足以证明 PT 已进入 Git。

真实 CPU 后验于本次绑定：五阶段及容器实际退出0，root/independent报告均存在且SHA绑定；原未绑定plan/index/manifest/summary保留在binding-history。publisher/replay尚未执行，仍须完成新root与独立出版源审查。
