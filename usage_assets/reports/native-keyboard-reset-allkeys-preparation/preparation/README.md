# 原生 GUI 全方向键与 Backspace 补测准备

状态：仅准备完成，实际 GUI / Backspace / 全键派发尚未执行。没有创建 GUI cohort、X server、DDS、Robot、仿真或 GPU 任务。CPU candidate02 的 46/46 测试通过；它们使用控制面 fixtures、合成 NPZ 和一个普通 stdlib PTY 子进程，不能替代真实界面验收。

本目录复制第五次成功 EGL GUI 控制器，只在新的独立候选中补操作及只读观察。`origins.json` 与 `source-before/` 保留旧源；原第五次控制器/cohort、生产代码、运行中 629 和已 arm 的 waiter 均未改变。`codefreeze.json` 锁定 14 个 Python 文件；审查期间不再修改。两个 CPU candidate 的精确源码、XML、日志、容器 inspect 和 source before/after 均保留。

## 实际协议

- 仍使用已验 canonical 镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`、原生 PLANE、seed42、500 Hz physics / 50 Hz policy、released ONNX pair、EGL offscreen 和可见 GLFW viewer。
- 复用私有 Xephyr / authority / hostname、自建 Tk terminal 的真实 XTEST→Tk→PTY、原生 pynput hold/release、own XID / PID birth / PGID / SID、只读 host command_writer 观察。
- 自有 MuJoCo 窗口真实按 `7`→`8`，核 gantry 长度降低后恢复；`y`/`g` 各切换并恢复，核原生 camera tracking / overlay 状态并保存实际窗口截图。沿用 `8`/`9` 后释放 gantry、终端 `]`、`c`。
- LOW 模式依次真实按住并释放 `w/s/a/d/q/e`，原生 one-hot 索引应为 `1/11/2/4/3/5`；HIGH 为 `6/11/7/9/8/10`。每次激活确认后，新增实际标签控制 tick 至少 10，随后真实 release→0。原生 `=` 完成 LOW→HIGH→LOW。
- 每个模式另按住 `w`，激活后在未释放 `w` 时通过真实 PTY 点击 `z`；必须有原生 ZERO_VELOCITY 的非零→0 分发日志和至少 10 个 stand 标签，再释放 `w`。
- 原生录制只保存一个 NPZ，必须含全部部署标签 0–11，各至少 10 帧，无保留槽 12–14；格式仍为原生 SDK 的 quaternion + zero XYZ placeholders + joints，不是世界轨迹。
- 保存录制、释放全部 held keys、原生 `o` damping 后，将真实 `BackSpace` 仅派发到自有 MuJoCo 窗口。新增 observer 只在原 `MuJoCo.render()` 前后读取完整 time / qpos / qvel / ctrl / model.qpos0 / nq / nv / nu / nkey / physics_dt 和累计 physics tick，原方法调用一次。不会调用 reset、mj_forward，或改时钟、动作、策略状态。
- 必须在真实 Backspace 请求后出现恰一个新 clock drop，并有完整 qpos 改变；区分 render 内发生和两次 render 观察间发生。重置前 time≥1 s，观察后 time≤0.1 s，保存 qpos0 误差而不自行改写 reset 目标。之后 physics/time、policy tick、depth heartbeat 必须继续推进。
- 最后走原生 SIGINT 正常退出，要求两 wrapper 实际 rc0、original main returned→Python atexit 各一次、birth 核定的进程组无存活成员、两条精确 host/container/command_writer birth 映射、全部实际 MP4 的 ffmpeg 全片 decode0、无 fatal 文本/非正常清理。

这里验收输入接口和 MuJoCo 物理数据重置，不认定运动方向跟踪、技能成功、越障、真机、安全性或策略/历史/gantry/SDK 全部重置。所有失败都保留；不能通过程序调用 reset 或修改状态来补造通过结果。

## Root 后续执行

先等 `fresh629-sdk018-6cb2ae2-prepared02` 的真实完整终态：native/observer/CPU driver 均 0，1258 worker / 629 full decodes，两所属 GPU/CPU 容器均停止。`run` 会核这些原收据并实际 inspect 两个旧 CID，取得同一个 UUID 全程 mutex 后再检查 GPU idle。若 armed waiter 先持有锁，本次直接拒绝启动，不抢占任务。

准备动作仅复制既有 immutable canonical context 和本地 released pair、封存源码并 inspect 镜像，不启动 native：

```bash
python3 -B outputs/research/native-keyboard-reset-allkeys-preparation-01/host_runner.py prepare \
  --source /home/dzp/projects/php_parkour/outputs/research/sdk018-canonical-build-6cb2ae2/context \
  --project /home/dzp/projects/php_parkour \
  --destination /home/dzp/projects/php_parkour/outputs/research/native-keyboard-reset-allkeys-cohort-01 \
  --image sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f \
  --display :93
```

Root 审查新 plan、file SHA、空输出目录及 private display 后，才明确授权启动：

```bash
python3 -B outputs/research/native-keyboard-reset-allkeys-preparation-01/host_runner.py run \
  --plan /home/dzp/projects/php_parkour/outputs/research/native-keyboard-reset-allkeys-cohort-01/cohort/plan.json \
  --root-authorized-start
```

实际启动前仍会在新容器里先执行两角色 import/config parse preflight，不构造 native 对象；本轮未声称已完成这份新 cohort 的实际 preflight。禁止给上述 native 命令再套外部 `timeout`。原受控会话/操作 deadline 失败会保留证据并只清理自身资源，任何强制回收都不能算通过。禁止覆盖或重试已有 attempt；新尝试必须使用新 cohort 名称及新 plan。

CPU 复核命令仅创建新的 runc / network-none / GPU-hidden 测试容器：

```bash
python3 -B outputs/research/native-keyboard-reset-allkeys-preparation-01/run_cpu_candidate.py \
  --output outputs/research/native-keyboard-reset-allkeys-preparation-01/cpu-root-review-01
```

`cpu-candidate-01/` 保存第一次 45 项通过及当时精确源码；`cpu-candidate-02/` 为追加 main/atexit 门卫后的 46 项通过及当前精确源码。root 尚未实际 prepare/run GUI，`plan.json` 是审查用协议及 argv，不是虚构的执行收据。canonical context、旧成功 GUI、released pair、0915 host observer 和未来完成的 fresh629 终态收据是恢复运行所需的外部前提，本归档不复制大模型/整个 source tree。
