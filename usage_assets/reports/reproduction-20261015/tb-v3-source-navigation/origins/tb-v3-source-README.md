# SDK018 默认交接后的 TensorBoard 接入 v3：仅准备，尚未执行

入口保持独立：只有 cloud888 真实终态、原 watch parent actualwait0、888视频出版与完整restore、默认 SDK018 adoption 实际通过后，root 才执行此服务接入。没有训练恢复、日志重新写入或新的仿真实验。

已准备 [轻量容器内启动器](tb_launch_after_adoption_v3.py)、[只读端口/events/HTTP检查器](tb_adoption_observe_v3.py)、[实际纯/混学生末步基线](tb-final-student-baseline.json)。基线 SHA `1c4b21859ac61fc868df8fafe337dc59452aef28396ca3c91977354dd8b1f073` 来自已完整CRC核验的实际离线 scalar JSON；纯学生末步9999、混合学生末步29999。它不是未来 TensorBoard、转发或浏览器成功收据。

v2按实际远端UID1000账号工作。原v1源与5项CPU验证完整保留在 `tb-after-adoption-preparation-v1/`；新observer的15项普通CPU守卫保留在 `tb-observer-v2-preparation/`，[独立源审](tb-observer-v2-independent-static-review.json)单独保留。远端6006通过exact新CID内的只读proc probe、前后Docker top和宿主公开stat/status完成PID映射；不读取宿主root进程的fd/ns/cmdline，也不使用sudo。

## 远端6006：只在全新默认CID启动

先保存实际 adoption `result.json`、`new-container.json` 和 SHA，重新核精确新CID、StartedAt/State.Pid、镜像fdfb及原outputs bind。所有命令由 root 真实 Popen/wait 保存 argv、stdout/stderr与退出原件。不要使用可变化的默认name替代下面的精确CID。

将这两份准备源码及原样基线放入独立操作代码目录，例如远端 `/diff/dzp_is_sb/php-parkour-research/outputs/tb-sdk018-default-code-20261015/`；核 SHA 后，创建全新操作目录 `/diff/dzp_is_sb/php-parkour-research/outputs/tb-sdk018-default-20261015-01/`。目录已存在即保留并停止，不能覆盖旧观察。

远端宿主执行预读，完整记录所有原events的路径/大小/模式/SHA及6006 IPv4/IPv6 listener与所有者：

```bash
/usr/bin/python3 -B REMOTE_OBSERVER snapshot --port 6006 \
  --event-root /diff/dzp_is_sb/php-parkour-research/outputs/official-full \
  --output REMOTE_TB_DIR/events-before.json
```

此快照必须没有任何6006 listener。launcher 还会在执行时重新检查6006及原events，随后只在实际新CID内部启动：

```bash
docker exec ACTUAL_NEW_CID /opt/php/bin/train-python -B \
  /outputs/tb-sdk018-default-code-20261015/tb_launch_after_adoption_v3.py \
  --new-cid ACTUAL_NEW_CID \
  --adoption-result /outputs/ACTUAL_ADOPTION_DIR/result.json \
  --adoption-result-sha256 ACTUAL_ADOPTION_RESULT_SHA256 \
  --events-before /outputs/tb-sdk018-default-20261015-01/events-before.json \
  --events-before-sha256 ACTUAL_PRESTART_SNAPSHOT_SHA256 \
  --output /outputs/tb-sdk018-default-20261015-01/service
```

真实工作argv为 `/opt/php/bin/train-python -m tensorboard.main --logdir /outputs/official-full --host 127.0.0.1 --port 6006 --load_fast false`。只对子进程设置空 `CUDA_VISIBLE_DEVICES`，原默认容器合同不变。保留 `before-spawn.json`、`launch.json`、容器内PID/PGID/SID/出生ticks及持续的 `stdout.raw`、`stderr.raw`。启动器退出0只表示启动记录写完；live服务的 `actual_child_wait_returncode` 仍是null，不能称TensorBoard已自然退出0。启动记录失败只停止/reap其自己的服务session并保留失败原件。

TensorBoard准备就绪后，以exact新CID保存真实listener：

```bash
/usr/bin/python3 -B REMOTE_OBSERVER snapshot --port 6006 \
  --container-id ACTUAL_FULL_NEW_CID \
  --event-root /diff/dzp_is_sb/php-parkour-research/outputs/official-full \
  --output REMOTE_TB_DIR/listener-after.json
```

取规范化结果的**宿主**PID与出生ticks；容器内train-python可能由bash包装，因此不能把launcher初始容器PID直接当作HTTP listener。新observer在exact新CID内通过只读stdlib probe读取容器listener/PID1的fd与namespace，将容器PID与前后Docker top中的宿主PID按公开stat/status的NSpid/NStgid和相同出生ticks唯一对应；fresh inspect再核同一CID/镜像/StartedAt/State.Pid/Config/Mounts。实际Docker argv、注入源码、stdout/stderr与退出原件保存在独立docker-logs中。容器内 `--user 0` 只用于该已接受新CID的只读probe，不改变SSH操作者或宿主权限。

```bash
/usr/bin/python3 -B REMOTE_OBSERVER check --url http://127.0.0.1:6006 \
  --baseline REMOTE_BASELINE --baseline-sha256 1c4b21859ac61fc868df8fafe337dc59452aef28396ca3c91977354dd8b1f073 \
  --adoption-result REMOTE_ADOPTION_RESULT --adoption-result-sha256 ACTUAL_RESULT_SHA256 \
  --adoption-container-inspect REMOTE_ADOPTION_NEW_CONTAINER_JSON \
  --adoption-container-inspect-sha256 ACTUAL_ADOPTION_CONTAINER_INSPECT_SHA256 \
  --event-root /diff/dzp_is_sb/php-parkour-research/outputs/official-full \
  --events-before REMOTE_TB_DIR/events-before.json --events-before-sha256 ACTUAL_PRESTART_SNAPSHOT_SHA256 \
  --expected-pid ACTUAL_HOST_TB_LISTENER_PID --expected-start-ticks ACTUAL_HOST_TB_LISTENER_TICKS \
  --output REMOTE_TB_DIR/remote-http-01
```

保存根页面、`/data/runs`、`/data/plugin/scalars/tags`及每个core tag/Train mean reward的实际HTTP200原件。pure/fine实际长run名逐字匹配；检查所有返回点finite且step递增，末步/末值与原离线基线一致。HTTP允许TensorBoard下采样，返回点数不被称为完整训练样本数。检查前后所有原events SHA/模式/文件集合一致，listener的固定出生/argv/socket inode/namespace/boot一致；动态status计数仅保留，不作为身份字段。

服务日志仍在增长。HTTP核验时另保存一次日志字节快照及SHA/观察UTC，不把live日志快照称作最终关闭日志。若服务尚未载入完整runs/tags，保留本次失败观察，待实际ready再用新目录只读复核，不重启服务或覆盖失败。

## 本地6007：核实端口与自有SSH出生

先用同一checker的 `snapshot --port 6007 --output FRESH_LOCAL_BEFORE_JSON` 记录IPv4/IPv6端口与现有进程。如果已有listener，先保留原件：正确的原有自有forward可由root另审复用；确实需要新tunnel时，只处理root新读确认出生的原自有SSH。未知listener不能被顶替。

端口全新空闲时，root通过实际Popen启动并记录出生、独立session和stdout/stderr，不用 `ssh -f`：

```text
["ssh","-p","22","-o","BatchMode=yes","-o","PasswordAuthentication=no",
 "-o","ControlMaster=no","-o","ControlPath=none","-o","ExitOnForwardFailure=yes",
 "-N","-L","127.0.0.1:6007:127.0.0.1:6006","tencent-231"]
```

保留该live tunnel的实际PID/出生ticks，之后从真实socket owner再次核对。复制远端6006完整HTTP观察原件、adoption结果和SHA到全新本地目录，再执行：

```bash
/usr/bin/python3 -B outputs/research/reproduction-20261015/tb_adoption_observe_v3.py check \
  --url http://127.0.0.1:6007 \
  --baseline outputs/research/reproduction-20261015/tb-final-student-baseline.json \
  --baseline-sha256 1c4b21859ac61fc868df8fafe337dc59452aef28396ca3c91977354dd8b1f073 \
  --adoption-result ACTUAL_COPIED_ADOPTION_RESULT --adoption-result-sha256 ACTUAL_RESULT_SHA256 \
  --remote-check ACTUAL_COPIED_REMOTE_HTTP_REPORT --remote-check-sha256 ACTUAL_REMOTE_HTTP_REPORT_SHA256 \
  --expected-pid ACTUAL_LOCAL_SSH_LISTENER_PID --expected-start-ticks ACTUAL_LOCAL_SSH_LISTENER_TICKS \
  --output outputs/research/reproduction-20261015/tb-local-http-01
```

本地checker要求远端报告属于同一实际adoption结果/newCID、6006 URL、原events前后无变、init namespace与boot，并再次从6007读取相同真实runs/tags/scalars和HTTP200，核自有SSH固定出生前后一致。

## 真实浏览器画面

媒体agent另备轻量 `tb_final_students_browser_v3.py`，要求显式基线SHA与上述本地实际HTTP报告SHA；尚未产生任何未来截图。仅真实Chrome/CDP，精确过滤pure/fine两个run，smoothing0、无outlier隐藏；纯显示 `Loss/behavior`、`Train/mean_reward`，混合再显示 `Loss/total_loss`。保存真实canvas/DOM/CDP/Chrome日志、截图及Browser.close后实际wait0。旧 `verify_tensorboard_browser.py` 固定pilot/smoke范围，不能直接当作正式学生的末步验收。

这些步骤只证明已有原events的真实服务/转发/显示。课程成功率仍需各实验自己的实际终止原因与轨迹，不能从TensorBoard末步或reward作推断。


新增v3仅解决完整Mounts数组随机排序的宿主验收误拒；observer同时在adoption当前inspect与listener前后container_identity中按uniqueDestination规范完整行，其他字段严格，原Docker stdout原字节均保留。原v2源码/61文件seal f6a282保持。运行时observer/launcher/browser没有fa7/b538或control_revision2硬pin，真实SDKv4 result沿用相同passed/newCID/image/birth原schema，可兼容；active操作流程须先使用已审SDKv4新named入口，不能执行旧v2/v3 SDKadopter。此包精确绑定SDKv4 source seal546313和独审9111a6作为来源，不表示未来实际adoption/TB/tunnel/HTTP/browser已通过。浏览器所有科学tag/run/末步/图形和UID1000只读映射逻辑保持，browser与launcher仅引用新observer文件名。新canonical源码位于reproduction-20261015根；仅source-only准备、普通CPU协议，不启动任何服务。
