# 官方首个教师的真实训练曲线（进行中快照）

![首个 locomotion 教师的四条真实训练曲线](learning-curves-plot-01/figures/learning-curves.png)

这是首个 **locomotion teacher** 尚未完成的官方训练快照，目标为 **20,000 次迭代**；本次记录只覆盖真实 iteration **0–14,340**。四个 TensorBoard tag（`Train/mean_reward`、`Loss/Value`、`Loss/Surrogate`、`Loss/Entropy`）各有 **14,341 个有限样本**。所有原始点均保留；深色线是 **25 样本的后向算术均值**，开头不足 25 点时使用已有样本。负 surrogate/entropy 值原样展示。

本发布是 `partial/running` 历史快照，`official_schedule_complete=false`、`quality_verified=false`、`convergence_verified=false`。它只展示首个教师的日志，没有证明训练收敛、技能质量或其余教师与学生已完成。

[PNG](learning-curves-plot-01/figures/learning-curves.png) · [SVG](learning-curves-plot-01/figures/learning-curves.svg) · [原始 scalars JSON](learning-curves-snapshot-01/scalars.json) · [绘图报告](learning-curves-plot-01/figures/plot-report.json)

[官方容器导出收据](learning-curves-snapshot-01/export-receipt.json)保留导出前后容器身份、完整原始 stdout/stderr 的 SHA 和实际退出码。[CPU 绘图启动与清理收据](learning-curves-plot-01/launch.json)、[容器前检](learning-curves-plot-01/container-before.json)、[最终状态](learning-curves-plot-01/container-final.json)与[实际命令](learning-curves-plot-01/executed-commands.txt)记录绘图在独立 `runc`、断网、GPU 隐藏容器中 exit 0，自己的容器已停止。原始数据 SHA256 为 `5f165225fa2ad0bbb120783654591acefa4ae54b037be0b509219d32c33b8afd`。

两个 sibling 目录保持原始目录结构与全部文件字节，包括导出脚本、绘图脚本、stdout/stderr、inspect、图像和原始 inner manifest。[原始说明](learning-curves-plot-01/summary.md)的 `../learning-curves-snapshot-01` 仍对应相邻目录；历史 JSON 中的绝对路径保留原样，仅表示当时执行环境。[外层 publication manifest](publication-manifest.json)逐一绑定本仓库内的发布文件，供新 checkout 核验。

## 从发布数据离线重绘

在新 checkout 的仓库根目录执行以下命令。Docker 本地须已有已验证的完整镜像 `sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f`（可事先从离线归档 `docker load`）；`--pull never` 禁止拉取。宿主机只执行 shell 与 Docker，Matplotlib 在容器中运行。命令将只读发布目录挂到原脚本期望的 `/data`，写入全新空目录；不会覆盖本发布。

```bash
curve_publication="$PWD/usage_assets/reports/official-teacher-learning-curves"
mkdir -p "$PWD/outputs/research"
curve_output=$(mktemp -d "$PWD/outputs/research/official-teacher-curves-replot.XXXXXXXX")
docker run --pull never --rm \
  --name "php-curves-$(basename "$curve_output")" \
  --runtime runc --network none --ipc private --init \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e MPLBACKEND=Agg -e MPLCONFIGDIR=/tmp/matplotlib \
  -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$curve_publication/learning-curves-snapshot-01,dst=/data,readonly" \
  --mount "type=bind,src=$curve_output,dst=/figures" \
  --entrypoint /opt/php/bin/train-python \
  sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f \
  /data/plot_learning_curves.py --input /data/scalars.json --output /figures --window 25
printf '%s\n' "$curve_output"
```

新输出含 `learning-curves.png`、`learning-curves.svg` 和新的 `plot-report.json`。这是可复制的离线命令；本次出版只复制并核对既有证据，没有再次运行绘图、容器或导出。
