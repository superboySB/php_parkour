#!/usr/bin/env bash
set -euo pipefail
/opt/php/bin/inference-python -m pytest -q /proposal/test_bootstrap.py --junitxml=/proposal/tests.xml > /proposal/tests.log 2>&1
/opt/php/bin/inference-python /proposal/pty_probe.py > /proposal/pty-driver.log 2>&1
bash /proposal/wrapper-fixture/run_php_inference.sh --help > /proposal/native-help.log 2>&1
