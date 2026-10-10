# Five nondefault preset checkpoint reload plan

Status: planned only. These are the completed 64-environment, two-iteration smoke checkpoints; this plan does not claim converged skills or reproduce six full ablation schedules. Root separately performs CPU ONNX inference/parity. GPU eval waits until the 629-configuration job releases the GPU.

The launcher restores each checkpoint experiment configuration. Its explicit evaluation overrides are 16 environments, 100 policy steps, deterministic one-variant terrain preprocessing with obstacle seed 42, headless video and disabled remote logging/TensorBoard. Each output must be fresh; preserve failed attempts. These evaluation overrides do not change training learning parameters.

## teacher-preset-g1-wbt-terrain-no-heightscan-locomotion

Actor input: **160**. Verified directly from PT actor first layer and existing ONNX graph; all five graphs have `time_step (1,1)` and action output `(1,29)`.

PT: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-locomotion/PHP-research/20261010_040852-teacher-preset-g1-wbt-terrain-no-heightscan-locomotion-locomotion/model_00001.pt`

ONNX: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-locomotion/PHP-research/20261010_040852-teacher-preset-g1-wbt-terrain-no-heightscan-locomotion-locomotion/model_00001.onnx`

Saved config: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-locomotion/PHP-research/20261010_040852-teacher-preset-g1-wbt-terrain-no-heightscan-locomotion-locomotion/holosoma_config.yaml`

```bash
docker exec -e CHECKPOINT=/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-locomotion/PHP-research/20261010_040852-teacher-preset-g1-wbt-terrain-no-heightscan-locomotion-locomotion/model_00001.pt -e REGISTRY=file:///data/assets/motions-locomotion -e LOGGER=tensorboard -e WANDB_MODE=disabled -e NUM_ENVS=16 -e MAX_EVAL_STEPS=100 php-parkour-research bash scripts/research/eval_quality.sh teacher /outputs/preset-reload/teacher-preset-g1-wbt-terrain-no-heightscan-locomotion/quality.json --training.headless True --logger.video.interval 1 --logger.video.upload-to-wandb False
```

## teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion

Actor input: **160**. Verified directly from PT actor first layer and existing ONNX graph; all five graphs have `time_step (1,1)` and action output `(1,29)`.

PT: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion/PHP-research/20261010_040933-teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion-locomotion/model_00001.pt`

ONNX: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion/PHP-research/20261010_040933-teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion-locomotion/model_00001.onnx`

Saved config: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion/PHP-research/20261010_040933-teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion-locomotion/holosoma_config.yaml`

```bash
docker exec -e CHECKPOINT=/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion/PHP-research/20261010_040933-teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion-locomotion/model_00001.pt -e REGISTRY=file:///data/assets/motions-locomotion -e LOGGER=tensorboard -e WANDB_MODE=disabled -e NUM_ENVS=16 -e MAX_EVAL_STEPS=100 php-parkour-research bash scripts/research/eval_quality.sh teacher /outputs/preset-reload/teacher-preset-g1-wbt-terrain-no-heightscan-noscale-locomotion/quality.json --training.headless True --logger.video.interval 1 --logger.video.upload-to-wandb False
```

## teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion

Actor input: **160**. Verified directly from PT actor first layer and existing ONNX graph; all five graphs have `time_step (1,1)` and action output `(1,29)`.

PT: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion/PHP-research/20261010_041014-teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion-locomotion/model_00001.pt`

ONNX: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion/PHP-research/20261010_041014-teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion-locomotion/model_00001.onnx`

Saved config: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion/PHP-research/20261010_041014-teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion-locomotion/holosoma_config.yaml`

```bash
docker exec -e CHECKPOINT=/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion/PHP-research/20261010_041014-teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion-locomotion/model_00001.pt -e REGISTRY=file:///data/assets/motions-locomotion -e LOGGER=tensorboard -e WANDB_MODE=disabled -e NUM_ENVS=16 -e MAX_EVAL_STEPS=100 php-parkour-research bash scripts/research/eval_quality.sh teacher /outputs/preset-reload/teacher-preset-g1-wbt-terrain-no-heightscan-pelvis-locomotion/quality.json --training.headless True --logger.video.interval 1 --logger.video.upload-to-wandb False
```

## teacher-preset-g1-wbt-terrain-ref-locomotion

Actor input: **449**. Verified directly from PT actor first layer and existing ONNX graph; all five graphs have `time_step (1,1)` and action output `(1,29)`.

PT: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-locomotion/PHP-research/20261010_040831-teacher-preset-g1-wbt-terrain-ref-locomotion-locomotion/model_00001.pt`

ONNX: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-locomotion/PHP-research/20261010_040831-teacher-preset-g1-wbt-terrain-ref-locomotion-locomotion/model_00001.onnx`

Saved config: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-locomotion/PHP-research/20261010_040831-teacher-preset-g1-wbt-terrain-ref-locomotion-locomotion/holosoma_config.yaml`

```bash
docker exec -e CHECKPOINT=/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-locomotion/PHP-research/20261010_040831-teacher-preset-g1-wbt-terrain-ref-locomotion-locomotion/model_00001.pt -e REGISTRY=file:///data/assets/motions-locomotion -e LOGGER=tensorboard -e WANDB_MODE=disabled -e NUM_ENVS=16 -e MAX_EVAL_STEPS=100 php-parkour-research bash scripts/research/eval_quality.sh teacher /outputs/preset-reload/teacher-preset-g1-wbt-terrain-ref-locomotion/quality.json --training.headless True --logger.video.interval 1 --logger.video.upload-to-wandb False
```

## teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion

Actor input: **449**. Verified directly from PT actor first layer and existing ONNX graph; all five graphs have `time_step (1,1)` and action output `(1,29)`.

PT: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion/PHP-research/20261010_040954-teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion-locomotion/model_00001.pt`

ONNX: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion/PHP-research/20261010_040954-teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion-locomotion/model_00001.onnx`

Saved config: `/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion/PHP-research/20261010_040954-teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion-locomotion/holosoma_config.yaml`

```bash
docker exec -e CHECKPOINT=/outputs/final-cloud-acceptance/results/smoke/teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion/PHP-research/20261010_040954-teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion-locomotion/model_00001.pt -e REGISTRY=file:///data/assets/motions-locomotion -e LOGGER=tensorboard -e WANDB_MODE=disabled -e NUM_ENVS=16 -e MAX_EVAL_STEPS=100 php-parkour-research bash scripts/research/eval_quality.sh teacher /outputs/preset-reload/teacher-preset-g1-wbt-terrain-ref-pelvis-locomotion/quality.json --training.headless True --logger.video.interval 1 --logger.video.upload-to-wandb False
```

Acceptance: native process exit 0; quality JSON binds the correct checkpoint SHA and its actual saved preset; four finite tracking metrics and nonempty sample count; new nonempty MP4 fully decodes and has a nonzero duration; TensorBoard events are readable. Record failures without replacing the previous run. `quality_verified` remains false for smoke checkpoints.

No command in this plan has been executed by this task.
