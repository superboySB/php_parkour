#!/usr/bin/env bash
# Full published schedules on the one GPU exposed by the Docker launcher.
# Restarting uses validated checkpoints and successful manifests.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo"
output=${1:-/outputs/official-training}
eval_steps=${PHP_OFFICIAL_EVAL_STEPS:-3000}
eval_envs=${PHP_OFFICIAL_EVAL_ENVS:-64}
mkdir -p "$output"
exec 9>"$output/official-acceptance.lock"
flock -n 9 || { echo 'An official acceptance driver already holds this output directory.' >&2; exit 1; }
pipeline=(bash scripts/research/train_pipeline.sh)
common=(--profile official --output "$output" --skip-completed)

"${pipeline[@]}" teachers "${common[@]}" --resume
train-python scripts/research/validate_teacher_exports.py --output "$output" --profile official
"${pipeline[@]}" eval-teachers "${common[@]}" --num-envs "$eval_envs" --eval-steps "$eval_steps"
for kind in pure finetune; do
    "${pipeline[@]}" "distill-$kind" "${common[@]}" --resume
    "${pipeline[@]}" eval-student "${common[@]}" --student-kind "$kind" \
        --num-envs "$eval_envs" --eval-steps "$eval_steps"
    "${pipeline[@]}" export "${common[@]}" --student-kind "$kind"
done
echo 'Official schedules and recorded evaluations/exports finished; assess quality.json before making skill claims.'
