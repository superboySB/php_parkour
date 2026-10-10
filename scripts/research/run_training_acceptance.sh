#!/usr/bin/env bash
# Bounded execution acceptance only. Does not replace official training.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
output=${PHP_ACCEPTANCE_OUTPUT:-/outputs/training-acceptance}
pipeline=(bash scripts/research/train_pipeline.sh)
common=(--profile smoke --output "$output" --skip-completed)
"${pipeline[@]}" teachers "${common[@]}"
"${pipeline[@]}" teacher-presets "${common[@]}" --skills locomotion
"${pipeline[@]}" eval-teachers "${common[@]}" --eval-steps 250
for kind in pure finetune; do
    "${pipeline[@]}" "distill-$kind" "${common[@]}"
    "${pipeline[@]}" eval-student "${common[@]}" --student-kind "$kind" --eval-steps 250
    "${pipeline[@]}" export "${common[@]}" --student-kind "$kind"
done
