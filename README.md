# [RSS 2026] Perceptive Humanoid Parkour: Chaining Dynamic Human Skills via Motion Matching

Research Docker workflow: [配置与运行手册](note.md) · [功能复现与图像/视频证据](usage.md).
The `research` branch uses one image for local simulation and cloud training,
local TensorBoard events and file registries; project packages are installed inside Docker.

Research reproduction (2026-10-15): all 16 official training/evaluation/export
stages have finished. See the [current audit](usage_assets/reports/reproduction-20261015/index.md),
[full finetune learning curves](usage_assets/reports/official-student-finetune-training-curves/index.md),
and [simulation video gallery](usage_assets/reproduction-20261015/media/playback.html).
The final students' [complete 58-case gallery](usage_assets/reports/final-student-native58-resource-wait-04/playback.html)
has passed independent CPU checks, lossless restoration and browser playback.
The [completed flat-ground preview](usage_assets/reports/reproduction-20261015/source888-first-boundary-preview/playback.html)
and [low-step preview](usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-preview/playback.html)
show final teachers reaching their source boundaries; the complete cohort is still running.
Policy and obstacle-course success remain separate from execution checks.
For local playback and seeking, run `python3 scripts/research/serve_evidence.py` and open `http://127.0.0.1:8088/usage_assets/reproduction-20261015/media/playback.html`.

Zhen Wu\*, Xiaoyu Huang\*, Lujie Yang\*, Yuanhang Zhang, Xi Chen,
Pieter Abbeel†, Rocky Duan†, Angjoo Kanazawa†, Carmelo Sferrazza†, Guanya Shi†, C. Karen Liu†

[Project page](https://php-parkour.github.io/) ·
[arXiv](https://arxiv.org/abs/2602.15827) ·
[Video](https://youtu.be/IjeBnbm9sto)

<p align="center">
  <img src="assets/teaser-480p.gif" width="800" alt="Parkour Demo">
</p>

## Overview

PHP (Perceptive Humanoid Parkour) enables humanoid robots to autonomously
perform long-horizon, vision-based parkour across challenging obstacle courses.
The framework has three steps:

1. **Motion matching.** Compose retargeted atomic human skills into long-horizon
   trajectories offline using motion matching.
2. **Teacher training.** Train RL experts to track the trajectories with privileged
   state and terrain observations.
3. **Student training.** Distill the experts into a depth-based, multi-skill policy
   using DAgger + RL.

## Get started

Start with [note.md](note.md) to build the unified Docker image, verify assets,
and configure local simulation or offline cloud training. Actual results and
known failures are recorded in [usage.md](usage.md).

For motion matching and training, clone PHP with its pinned Holosoma submodule:

```bash
git clone --branch research --recurse-submodules https://github.com/superboySB/php_parkour.git
cd php_parkour
```

Choose a guide below for environment setup and commands. For training, use the
[prepared example datasets](wbt_training/README.md#example-motionterrain-datasets) or generate your own
with motion matching. If you already have an exported ONNX pair, go directly to sim2sim.

| Guide | Workflow | Requirements |
|---|---|---|
| [Motion matching](motion_matching/README.md) | Generate and inspect motion/terrain datasets; prepare local bundles or add skills | Unified Docker, `motion-python` |
| [Training and evaluation](wbt_training/README.md) | Train teachers, distill students, evaluate checkpoints, and export ONNX | Unified Docker, `train-python`; offline TensorBoard |
| [Sim2sim](wbt_training/DEPLOY.md) | Run the exported depth policy in MuJoCo | Same Docker image, native DDS and depth shared memory |

## 🏃 Try the demo

<p align="center">
  <img src="assets/php-demo-480p.gif" width="800" alt="PHP depth locomotion demo in MuJoCo">
</p>

To try the example student policy in MuJoCo, download the validated ONNX pair
from the [student release](https://github.com/amazon-far/php_parkour/releases/tag/student-assets-v1).
Run from the PHP checkout root:

```bash
python3 scripts/research/verify_assets.py
```

The release contains sanitized `depth_backbone.onnx` and `student.onnx` files,
without raw `.pt` or teacher checkpoints. The research verifier stores all seven asset groups in
`outputs/research/assets/`; the student pair is mounted as `/data/assets/student`
in Docker. It verifies each archive and extracted file against
[release-assets.json](release-assets.json).

Follow the [sim2sim guide](wbt_training/DEPLOY.md) to run the policy. You can
also use the [automatically exported ONNX pair](wbt_training/README.md#export-to-onnx)
from your own student training run.

## Citation

```bibtex
@article{wu2026perceptive,
  title={Perceptive humanoid parkour: Chaining dynamic human skills via motion matching},
  author={Wu, Zhen and Huang, Xiaoyu and Yang, Lujie and Zhang, Yuanhang and Chen, Xi and Abbeel, Pieter and Duan, Rocky and Kanazawa, Angjoo and Sferrazza, Carmelo and Shi, Guanya and others},
  journal={arXiv preprint arXiv:2602.15827},
  year={2026}
}
```

Related: [OmniRetarget](https://omniretarget.github.io/).
