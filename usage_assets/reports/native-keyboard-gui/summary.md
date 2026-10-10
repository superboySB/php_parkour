# 原生 MuJoCo 窗口与终端键盘验收

第五次实际运行通过平地接口验收：真实私有 MuJoCo 窗口中的8/9、独占终端窗口中经Tk→PTY传递的 `] / c / = / o / i`，以及 XTEST `w` 按住/松开的低速command1、高速command6均有原生状态回执。两段原生录制分别169/196帧（fps50）；手动c保存，STOP/o自动保存。双方原生main/atexit返回、实际外层wrapper均0、出生身份绑定的进程组为空，未使用TERM/KILL兜底。宿主观察器实际关联了容器/宿主PID、出生时间与command_writer线程。

[逐次结果](attempts.json)、[独立验收](independent-review.json)、[离线原片与截图](playback.html)、[完整发布SHA清单](manifest.json)。四次失败的原始日志、退出码、计划与原始manifest全部保留在attempts/；这些失败没有改成成功。CPU后验独立确认NPZ有限值、one-hot标签、原始MP4完整解码，以及每次原始manifest的所有文件哈希。

第四次运行在所有接口完成、视频保存及atexit之后发生 `free(): invalid next size (fast)` / native abort，外层wrapper1，整体失败。第五次只将离屏渲染环境 `MUJOCO_GL=glfw` 改为 `egl`；安装版官方源码显示depth/video Renderer走所选GLContext，而visible passive viewer显式使用GLFW。生产compose仅同样修改该项，并保存了解析后的配置及前后源文件。一次对照成功不证明所有原生内存问题已根除；未加入os._exit、忽略退出码或native算法/动作/清理补丁。

主图只使用初始窗口与终端日志。forward6原始截图因为相机跟随关闭、机器人移出视野而只有地板，保留原图但不作为高速步态可视化证明。命令1/6验收依据真实键事件、状态与NPZ标签；记录的rootXYZ为SDK占位零，不能当作世界轨迹。原始视频可完整播放。

本次证明单个G1平地接口流程，不证明障碍通关、629配置策略覆盖、训练收敛、实时性能或实机运行。NPZ为原生推理录制：wxyz四元数 + XYZ占位 +29关节及15维命令；不是配对terrain的训练native bundle。
