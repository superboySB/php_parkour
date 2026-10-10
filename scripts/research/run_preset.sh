#!/usr/bin/env bash
# Shared official launcher validation/activation with an explicit PHP preset.
set -euo pipefail
research_preset=${1:?Expected exp:g1-wbt-terrain-* preset}
shift
source "$(dirname "$0")/../../wbt_training/training_runs/setup_env.sh"
php_launcher_init
NGPUS="${NGPUS:-1}"
php_positive_integer NGPUS "$NGPUS"
php_prepare_inputs teacher ''
php_training_command
php_select_training_gpu
php_activate_sim
exec "${TRAIN_COMMAND[@]}" -m wbt_training.train_agent \
    "$research_preset" simulator:isaacsim --training.registry-name "$REGISTRY" \
    "${LOGGER_ARGS[@]}" --logger.video.enabled False "$@"
