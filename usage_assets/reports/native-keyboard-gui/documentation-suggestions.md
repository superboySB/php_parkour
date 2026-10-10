# 主文档建议（仅建议，尚未编辑主文档）

- usage：链接 `usage_assets/reports/native-keyboard-gui/{summary.md,playback.html,independent-review.json}`；明确五次真实尝试、四次失败原样保留、第五次平地接口完成。两NPZ169/196帧，manual c与STOP o autosave；低/高方向依据原生keys/state/one-hot1/6，不以相机空图证明高速步态。
- note：生产GUI compose仅MUJOCO_GL改egl并已docker compose config解析。可见passive viewer仍使用GLFW，离屏depth/video走EGL。保留真实终端TTY/窗口焦点、LoDDS与独占SHM约束；不要称一次EGL成功根除所有heap问题。
- 技术边界：退出用出生身份绑定的原生Python SIGINT，原handler/main/atexit以及实际wrapper0、组空均已观察；Esc仅listener不停止policy。Interface完整与策略质量/实机分开，本次是一个G1平地接口，非629/障碍/训练收敛。
- 图：优先attempts/05-egl-completed/outputs/initial-stiff.png与policy-terminal.png及原始video；initial机器人只有部分在画面，forward-6因Camera tracking OFF只有地板必须标明，不作高速步态视觉证据。

全部本地HTML链接已检查，独立CPU headless Chrome（GPU禁用）实际加载6张PNG、640×360原片metadata与中点解码，播放时间实际前进；浏览器自有组已回收。原MP4另有DockerCPU ffmpeg完整解码报告。
