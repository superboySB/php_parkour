#!/usr/bin/env bash
# Run only inside the research Docker; select a profile explicitly.
set -euo pipefail
exec "${HSSIM_PYTHON:-/opt/php/bin/train-python}" "$(dirname "$0")/train_pipeline.py" "$@"
