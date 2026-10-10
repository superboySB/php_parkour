#!/usr/bin/env bash
# Keep the published launcher's input resolution, activation and eval defaults.
set -euo pipefail
kind=$1
report=$2
shift 2
[[ $kind == teacher || $kind == student ]]
source "$(dirname "${BASH_SOURCE[0]}")/../../wbt_training/training_runs/setup_env.sh"
php_launcher_init
NUM_ENVS=${NUM_ENVS:-1}
MAX_EVAL_STEPS=${MAX_EVAL_STEPS:-250}
php_positive_integer NUM_ENVS "$NUM_ENVS"
php_positive_integer MAX_EVAL_STEPS "$MAX_EVAL_STEPS"
php_prepare_inputs "eval_$kind" "${CHECKPOINT:-}"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-${GPU_INDEX:-0}}
php_activate_sim
variants=1
[[ $kind != student ]] || variants=3
exec "$HSSIM_PYTHON" scripts/research/eval_quality.py "$kind" --quality-output "$report" \
    --checkpoint "$PHP_CHECKPOINTS" --training.num-envs "$NUM_ENVS" \
    --training.max-eval-steps "$MAX_EVAL_STEPS" --training.export-onnx False \
    --training.registry-name "$REGISTRY" --terrain.terrain-term.spawn.randomize-tiles True \
    "${LOGGER_ARGS[@]}" --logger.video.enabled True \
    --training.preprocess-hook-kwargs "{\"add_onpath_obstacle\": true, \"num_variants\": $variants, \"obstacle_seed\": 42}" \
    --training.seed 42 "$@"
