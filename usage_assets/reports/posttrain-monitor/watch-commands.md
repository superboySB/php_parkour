# 待部署命令模板（本报告未执行）

`PHP_COVERAGE_SOURCE_SHA` 必须是随后 commit/sync 得到的新冻结快照，内含本次 monitor 的精确字节；不得替换正在训练的 `0093aa40…` 源码绑定，也不能使用尚未包含 monitor 的旧快照。先执行只读 dry-run，人工审核其回执，再使用同组参数 watch。

```bash
PHP_CLOUD_ROOT=/diff/dzp_is_sb/php-parkour-research
PHP_COVERAGE_SOURCE_SHA='REPLACE_WITH_NEW_VERIFIED_64_HEX_SOURCE_TREE'
python3 "$PHP_CLOUD_ROOT/source/$PHP_COVERAGE_SOURCE_SHA/scripts/research/posttrain_coverage.py" dry-run \
  --root "$PHP_CLOUD_ROOT" \
  --source-tree "$PHP_COVERAGE_SOURCE_SHA" \
  --image sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd \
  --gpu-uuid GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5 \
  --training-container php-parkour-cloud-research \
  --official-output "$PHP_CLOUD_ROOT/outputs/official-full" \
  --driver-log "$PHP_CLOUD_ROOT/outputs/official-full-driver.log" \
  --coverage-output "$PHP_CLOUD_ROOT/outputs/coverage-official-final"
```

未完成训练时仅返回 waiting，不进行 Docker/GPU 启动。通过预先源码检查后，部署 watch：

```bash
nohup python3 "$PHP_CLOUD_ROOT/source/$PHP_COVERAGE_SOURCE_SHA/scripts/research/posttrain_coverage.py" watch \
  --root "$PHP_CLOUD_ROOT" \
  --source-tree "$PHP_COVERAGE_SOURCE_SHA" \
  --image sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd \
  --gpu-uuid GPU-27eb1141-ab74-ebdd-42c2-6549fb7253e5 \
  --training-container php-parkour-cloud-research \
  --official-output "$PHP_CLOUD_ROOT/outputs/official-full" \
  --driver-log "$PHP_CLOUD_ROOT/outputs/official-full-driver.log" \
  --coverage-output "$PHP_CLOUD_ROOT/outputs/coverage-official-final" \
  --poll-seconds 60 \
  > "$PHP_CLOUD_ROOT/outputs/posttrain-monitor.log" 2>&1 &
```

宿主仅使用 stdlib 与现有 Docker/NVIDIA 命令，不安装 Python 包。镜像内部执行已有 train-python；两个新子容器均断网，TensorBoard 写本地文件、WANDB_MODE=disabled。

同参数再次启动 watch 将核对输入身份并接管自己仍运行的容器，不重复任务。不要同时改 source-tree、权重或覆盖目录后声称是同一次恢复。CPU 准备失败后保留原目录/容器，审查失败后选择全新 `--coverage-output`，会产生不同 cohort/container 身份。GPU 容器异常退出后，审查证据再为同组参数增加 `--resume-interrupted`；它只继续未尝试源，已中断的首次尝试保留为执行失败，不会重跑美化结果。正常技能 failed/timeout 不需要这个参数。

真实完成需检查新输出 `summary.json`、888 项唯一 case 及各 native 报告/视频/TB/源 SHA，不能只看监控进程退出。`completed` 表示 888 次执行和证据结构通过；其 `quality_verified` 仍为 false。原官方 driver 没有持久化 terminal exit code，回执会明确保留 null，不将 detached launch 成功解释为多日任务成功。
