# PHP training and evaluation

[Project overview](../README.md) · [Docker setup and complete workflow](../note.md) · [Recorded results and limits](../usage.md)

Train G1 terrain teachers and distill them into a RealSense D435i depth student.
Isaac Sim training, evaluation and export use the unified research Docker image.
Datasets are local `file://` bundles, checkpoints are native `.pt` files, and
metrics are recorded in TensorBoard. The cloud server runs the transferred image
and local assets without external network access.
For the exported ONNX pair in MuJoCo, see the [sim2sim guide](DEPLOY.md).

## Setup

Follow [note.md](../note.md) to build the pinned image, verify the local runtime,
download assets on the local machine, and transfer the image/data to the server.
Dependencies belong to the image; this workflow requires no host or server Python
package installation.

From a **host terminal** at the PHP checkout root, enter the existing local container:

```bash
bash scripts/research/docker.sh shell
```

**All remaining training, evaluation, export and TensorBoard commands below run
inside Docker, from `/workspace/php_parkour`.** Commands specifically marked
“local host” are the exceptions. For cloud execution and GPU selection, use the
`cloud.py exec` instructions in [note.md](../note.md).

The image provides `train-python`, the pinned Holosoma/Isaac Sim interpreter.
Launchers and Python presets default to local TensorBoard logging.
`LOGGER=tensorboard` selects Holosoma's local SummaryWriter; its internal
`logger:disabled` preset still writes TensorBoard events. No experiment account
or login is required. Checkpoints, events and videos are stored under the chosen
`--logger.base-dir`; the research pipeline uses `/outputs/training/`.

## Example motion/terrain datasets

These prepared native datasets let you skip motion matching and start teacher
training. They contain the motion/terrain pairs for the five-teacher setup:
locomotion, low- and high-speed step, and low- and high-speed climb-76.

The original bundles are in the
[training-motion-examples-v1 release](https://github.com/amazon-far/php_parkour/releases/tag/training-motion-examples-v1).

| Dataset | Download component | Motion/terrain pairs | Archive |
| --- | --- | ---: | ---: |
| Locomotion | `motions-locomotion` | 100 | [118.3 MB](https://github.com/amazon-far/php_parkour/releases/download/training-motion-examples-v1/php-motions-locomotion-v1.tar.gz) |
| Low-speed step | `motions-low-step` | 56 | [41.8 MB](https://github.com/amazon-far/php_parkour/releases/download/training-motion-examples-v1/php-motions-low-step-v1.tar.gz) |
| High-speed step | `motions-high-step` | 60 | [44.8 MB](https://github.com/amazon-far/php_parkour/releases/download/training-motion-examples-v1/php-motions-high-step-v1.tar.gz) |
| Low-speed climb-76 | `motions-low-climb-76` | 40 | [57.4 MB](https://github.com/amazon-far/php_parkour/releases/download/training-motion-examples-v1/php-motions-low-climb-76-v1.tar.gz) |
| High-speed climb-76 | `motions-high-climb-76` | 40 | [44.4 MB](https://github.com/amazon-far/php_parkour/releases/download/training-motion-examples-v1/php-motions-high-climb-76-v1.tar.gz) |

Download and verify all release assets on the **local host**, from the checkout
root, before cloud deployment. This downloader uses only the standard library:

```bash
python3 scripts/research/verify_assets.py
python3 scripts/research/verify_assets.py --verify-only
```

The host directory `outputs/research/assets/` is mounted as `/data/assets/`.
The downloader checks archives and extracted files against
[release-assets.json](../release-assets.json); cloud deployment transfers these
verified directories. Do not run an asset download on the offline server.
To verify one already extracted bundle **inside Docker**, without downloading:

```bash
train-python scripts/download_assets.py motions-locomotion \
  --destination /data/assets/motions-locomotion --verify
```

These are training data, without pretrained teacher `.pt` files. Train a teacher
for each desired dataset, then [distill the teachers](#distill-a-student).
For your own motions, follow [note.md](../note.md) for motion matching, conversion
to native Holosoma fields, and terrain pairing. A bundle contains `*motion*.npz`
and matching `*terrain*.npy`; use its absolute container path in `file://`.

## Train a teacher

The research pipeline trains the five teachers sequentially on the selected GPU,
with explicit local registries and a manifest for every checkpoint:

```bash
NGPUS=1 bash scripts/research/train_pipeline.sh teachers --profile official
```

The five-teacher order is `locomotion`, `low-step`, `high-step`,
`low-climb-76`, `high-climb-76`. Standard height-scan teachers use **4096
environments and 20000 iterations each**. For a bounded execution check, use
`--profile smoke`; its smaller environment/layout/iteration settings are recorded
and do not establish policy quality.

As an alternative, launch one teacher directly, also **inside Docker**:

```bash
REGISTRY='file:///data/assets/motions-locomotion' \
LOGGER=tensorboard NGPUS=1 \
bash wbt_training/training_runs/run_terrain_teacher.sh \
  --training.headless True --training.num-envs 4096 \
  --algo.config.num-learning-iterations 20000 \
  --training.name example-locomotion-teacher \
  --logger.base-dir /outputs/training/manual-teacher
```

Choose another bundle from the table to train another skill. For custom native
data use `REGISTRY=file:///outputs/your-bundle`. All registry paths refer to
container-visible directories. Avoid launching the pipeline and direct example
concurrently on the same GPU.

## Distill a student

After all five pipeline teachers complete, run either student stage or both
sequentially. The pipeline reads the actual local checkpoints from its manifests
and supplies one explicit `file://` registry per teacher in the order above:

```bash
NGPUS=1 bash scripts/research/train_pipeline.sh distill-pure --profile official
NGPUS=1 bash scripts/research/train_pipeline.sh distill-finetune --profile official
```

| Student | Setting | Environments | Iterations |
| --- | --- | ---: | ---: |
| Pure DAgger | `FINETUNE=0` | 2048 | 10000 |
| DAgger + PPO | `FINETUNE=1` | 2048 | 30000 |

For a direct launcher alternative, recover the five `.pt` paths from the completed
teacher manifests and explicitly retain the matching dataset order:

```bash
TEACHER_CHECKPOINT="$(train-python - <<'PY'
import json
from pathlib import Path
names = ('locomotion', 'low-step', 'high-step', 'low-climb-76', 'high-climb-76')
root = Path('/outputs/training/official/manifests')
paths = []
for name in names:
    manifest = json.loads((root / f'teacher-{name}.json').read_text())
    if manifest['status'] != 'passed':
        raise RuntimeError(f'Teacher stage has not completed: {name}')
    paths.append(manifest['checkpoint'])
print(','.join(paths))
PY
)"
REGISTRY='file:///data/assets/motions-locomotion,file:///data/assets/motions-low-step,file:///data/assets/motions-high-step,file:///data/assets/motions-low-climb-76,file:///data/assets/motions-high-climb-76'
export TEACHER_CHECKPOINT REGISTRY
FINETUNE=0 LOGGER=tensorboard NGPUS=1 \
bash wbt_training/training_runs/run_terrain_warp_distill.sh \
  --training.headless True --training.num-envs 2048 \
  --algo.config.num-learning-iterations 10000 \
  --training.name manual-student-pure \
  --logger.base-dir /outputs/training/manual-student-pure
```

For direct DAgger + PPO, use the same ordered inputs with `FINETUNE=1`,
`--algo.config.num-learning-iterations 30000`, and a separate output/name.
These direct student runs are alternatives to the pipeline student stages;
subsequent pipeline commands use checkpoints from their own manifests.

The offline workflow always supplies registries explicitly. Native `.pt` files
save the experiment configuration, which evaluation/export can recover.
The shell launchers' legacy `REGISTRY=auto` discovery requires remote run
references and does not currently recover registries from local `.pt` inputs;
it is not an offline prerequisite.

## Launch options

| Setting | Purpose |
| --- | --- |
| `NGPUS=1` | One training process on the GPU selected outside Docker |
| `CUDA_VISIBLE_DEVICES=0` | The selected cloud GPU appears as device 0 inside Docker |
| `--training.num-envs` | Total parallel environments across training processes |
| `--training.name` / `--logger.base-dir` | Local run name and persistent output root |
| `LOGGER=tensorboard` | Local TensorBoard scalar/event logging |

The native launchers support multiple GPUs, but this research run validates
single-GPU execution. Multiple processes require an intentional container GPU
mapping and have not been validated here. The direct student launcher otherwise
defaults to two processes, so all examples explicitly set `NGPUS=1`.
See [note.md](../note.md) for cloud GPU reservation, detached jobs, checkpoint
recovery with `--resume`, and verification with `--skip-completed`.

## Evaluate and export your checkpoints

### Evaluate in IsaacSim

Evaluate the checkpoint manifests created by the pipeline with the same ordered
local datasets. These examples perform a bounded 250-step evaluation:

```bash
bash scripts/research/train_pipeline.sh eval-teachers --profile official --eval-steps 250
bash scripts/research/train_pipeline.sh eval-student --profile official --student-kind pure --eval-steps 250
bash scripts/research/train_pipeline.sh eval-student --profile official --student-kind finetune --eval-steps 250
```

The pipeline passes explicit checkpoint paths and `file://` registries, records
checkpoint/video SHA-256, tracking metrics, resets and TensorBoard `Evaluation/*`
scalars in each `quality.json`. A bounded evaluation does not imply that every
motion clip was encountered or that a course was completed.

For direct evaluation of a pipeline teacher, read its actual native checkpoint:

```bash
CHECKPOINT="$(train-python -c 'import json; print(json.load(open("/outputs/training/official/manifests/teacher-locomotion.json"))["checkpoint"])')"
REGISTRY='file:///data/assets/motions-locomotion' \
LOGGER=tensorboard NUM_ENVS=1 MAX_EVAL_STEPS=250 \
CHECKPOINT="$CHECKPOINT" bash wbt_training/training_runs/eval_teacher.sh \
  --training.headless True --logger.base-dir /outputs/training/manual-eval-teacher \
  --logger.video.upload-to-wandb False
```

Direct student evaluation takes one native `.pt` path and all five ordered
registries. Run this block independently; it sets the registry list explicitly:

```bash
CHECKPOINT="$(train-python -c 'import json; print(json.load(open("/outputs/training/official/manifests/student-finetune.json"))["checkpoint"])')"
REGISTRY='file:///data/assets/motions-locomotion,file:///data/assets/motions-low-step,file:///data/assets/motions-high-step,file:///data/assets/motions-low-climb-76,file:///data/assets/motions-high-climb-76' \
LOGGER=tensorboard NUM_ENVS=1 MAX_EVAL_STEPS=250 \
CHECKPOINT="$CHECKPOINT" bash wbt_training/training_runs/eval_student.sh \
  --training.headless True --logger.base-dir /outputs/training/manual-eval-student \
  --logger.video.upload-to-wandb False
```

For a directly trained checkpoint, replace `CHECKPOINT` with its actual saved
`.pt` path and provide the datasets used to train it, in the same order.
Evaluation defaults to one environment; `NUM_ENVS`, `GPU_INDEX` and
`MAX_EVAL_STEPS` are available. Add `--show-depth True` to student evaluation
for the camera view in a GUI container.

### Export to ONNX

Student saves export `depth_backbone.onnx` and `student.onnx` together into a
local `model_<iteration>/` directory. Both files belong to the same checkpoint.
The pipeline also performs an independent export and validates both graphs
with real ONNX Runtime inference:

```bash
bash scripts/research/train_pipeline.sh export --profile official --student-kind pure
bash scripts/research/train_pipeline.sh export --profile official --student-kind finetune
```

For direct manual export, supply a local native `.pt` and explicit ordered
registries, **inside Docker**:

```bash
STUDENT_CHECKPOINT="$(train-python -c 'import json; print(json.load(open("/outputs/training/official/manifests/student-finetune.json"))["checkpoint"])')"
PHP_ORDERED_REGISTRIES='file:///data/assets/motions-locomotion,file:///data/assets/motions-low-step,file:///data/assets/motions-high-step,file:///data/assets/motions-low-climb-76,file:///data/assets/motions-high-climb-76'
train-python -m wbt_training.training_runs.export_distill_onnx \
  --training.checkpoint "$STUDENT_CHECKPOINT" \
  --training.registry-name "$PHP_ORDERED_REGISTRIES" \
  --training.num-envs 1 logger:disabled \
  --logger.base-dir /outputs/training/manual-export
```

Export recovers the saved model configuration and reports the actual output
bundle directory. An existing ONNX pair cannot substitute for this native `.pt`
input. Follow the [sim2sim guide](DEPLOY.md) to run the exported pair in MuJoCo.

To view local pipeline training/evaluation curves, open another container shell
and run:

```bash
train-python -m tensorboard.main --logdir /outputs/training \
  --host 127.0.0.1 --port 6006 --load_fast false
```

Open `http://127.0.0.1:6006/` on the local machine. For cloud curves, use the
SSH port-forwarding instructions in [note.md](../note.md).
