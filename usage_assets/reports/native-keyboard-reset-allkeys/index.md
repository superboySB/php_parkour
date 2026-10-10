# 原生 GUI 全方向键与 Backspace 补验

2026-10-10 14:14:52–14:15:32 UTC 的独立原生运行通过：真实父进程 wait0、双方原生 main/atexit 正常返回、两个 wrapper0、出生身份绑定进程组为空、观察器0、独占容器和 Xephyr 已停止。原14份 GUI 源码及既有3313项计划保持不变；新 carrier 只以明确恢复门卫替换旧生命周期前提，原 session54334=143 和八个历史观察缺口仍保留。

低/高速两模式各实际派发 `w/s/a/d/q/e` 并按住至少10个策略 tick，松开回到 command0；两次按住w再发z均观察到原生 ZERO_VELOCITY 事件。`7/8/9/y/g`、模式切换及原生窗口 Backspace 都有真实 XTEST/TTY/状态记录。此次只有 **1份录制、1段视频**：424帧，fps50，qpos424×36、命令424×15，0–11标签全部出现（非零标签最少12帧）。原生录制的 rootXYZ 是零占位，不能当世界轨迹或配对 terrain 训练数据。

Backspace 在原 render 的单次调用前后使 MuJoCo time11.57→0，nkey0、qpos等于model.qpos0、qvel/ctrl为零，随后物理时间继续推进。它证明物理 data reset；没有声称 policy history、gantry 或 SDK 全部 reset。视频已有原始 ffmpeg -xerror 全片解码0，本出版不重解码、不重编码。动作按键和物理重置成功不代表平地策略质量、障碍通关、训练收敛或真实 G1/D435i 验证。

[离线原片与截图](playback.html) · [独立验收](independent-review.json) · [原生summary](raw/outputs/summary.json) · [按键原始事件](raw/outputs/operator-events.jsonl) · [Backspace完整状态](raw/outputs/backspace-reset.json) · [原始host退出](raw/host/launch-receipt.json) · [真实父进程wait](carrier/actual-parent-01/process-exit.json) · [恢复门卫真实0](recovery-gate/root-actual-gate-02.receipt.json) · [SHA清单](publication-manifest.json)。[原CPU准备包](../native-keyboard-reset-allkeys-preparation/index.md)与[旧五次GUI原件](../native-keyboard-gui/summary.md)保持独立，旧双录制不算本次新增数量。

本包保存本次全部host/outputs原始字节、两角色PTY/状态/观察流、NPZ、原MP4/截图、原完整plan/manifest、精确GUI overlays与原14代码、carrier/父wait/两次门卫调用（01失败、02真实通过）。不复制3313源码全树、模型、缓存或Xauth cookie；恢复大依赖请按原plan/manifest及准备包的精确映射，恢复门卫内629+四例证明引用仍属于外部真实cohort，不能修改或补写旧收据。包内原manifest保持原字节，其未复制的大源码条目明确属于外部依赖。
