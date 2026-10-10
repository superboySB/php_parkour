# 学生原生深度窗口验收

使用已发布 smoke 运行的纯学生 iteration 1 PT（SHA `959b6685…`），在同一 research Docker 的真实 X11 会话调用 `eval_student.main()`，传入 `--show-depth True`。没有改学生网络、深度处理、OpenCV 窗口或评估器。

4 个 Isaac 环境、100 个评估步，原生 `imshow` 实际显示 100 帧（float32、464×696 的 2×2 拼图），98 个不同数组 SHA，全部有限。原生 `waitKey` 绘制后，从精确标题的窗口直接读取 X11 drawable，两张 PNG 的颜色数分别为 220/223，已实际目检。Docker 进程 exit=0，耗时 17.168 秒；输入 PT 与观察脚本/原生评估源码 SHA 在运行前后相同。

![实际延迟深度窗口](../../depth-gui/depth-frame-0030.png)

[最终原始观察报告](real-student-04/report.json)、[完整启动 argv](launch-04.json)、[原始 Isaac 日志](execution-04.log)、[真实保存配置](actual-eval-config.yaml)、[逐文件 SHA 清单](evidence-manifest.json)。观察包装只记录原生 imshow 数组并截图，不合成传感器帧；它调用的仍是原生学生评估入口。

前三次失败全部保留。验收脚本的启动参数曾写错日志目录名，以及给离线 disabled logger 传入仅 W&B logger 支持的 project/name；修正 argv 后通过，没有修改项目评估/训练代码。第一次进程在 viewer 建立前退出，原报告状态仍为 running，须结合其真实 exit=1 和 failure-01 注释判断，不代表后台仍在执行。

本次没有产出 MP4：100步没有达到默认录像间隔；上述两张图片是实际 GUI 窗口，不是从旧机器人影片抽帧。它仅验证深度显示选项、实际帧更新和退出，不证明 smoke 学生技能成功、正式训练完成或真机相机可用。

复跑时先按 note.md 以 GUI 模式启动 Docker，使用自己的有效学生 PT 与新输出目录。命令参数以 launch-04.json 为准；其中 `/outputs/final-cloud-acceptance/...` 是本次真实 PT 位置，需要替换为本机现有 PT。`logger:disabled` 仍写本地 TensorBoard，勿加入 `--logger.project`/`--logger.name`。
