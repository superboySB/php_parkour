#!/usr/bin/env python3
"""Unmodified native629 driver with a fail-closed per-case leftover-child gate."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('/workspace/php_parkour')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attach_gate(matrix, expected_plan, own_path, expected_own_sha):
    original = matrix.verify_inputs
    def guarded(plan, selection):
        if sha(own_path) != expected_own_sha:
            raise ValueError('Frozen629 control helper changed during execution')
        if plan != expected_plan:
            raise ValueError('Native regenerated plan differs from actual CPU-preflight plan')
        live = matrix.running_children()
        if live:
            raise ValueError(f'Previous native child remains; no next DDS case: {live}')
        return original(plan, selection)
    matrix.verify_inputs = guarded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-plan', type=Path, required=True)
    parser.add_argument('--matrix-sha256', required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('native_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    native_args = args.native_args
    if native_args and native_args[0] == '--':
        native_args = native_args[1:]
    if ('--all-configs' not in native_args or any(flag in native_args for flag in
            ['--resume','--case-id','--case-limit','--plan','--plan-output'])):
        raise ValueError('Fresh unfiltered629 execution required; no resume/subset/plan mode')
    own = Path(__file__).resolve()
    source = ROOT / 'scripts/research/sim2sim_scene_matrix.py'
    if sha(own) != args.helper_sha256 or sha(source) != args.matrix_sha256:
        raise ValueError('Frozen native/control SHA differs')
    spec = importlib.util.spec_from_file_location('frozen_matrix', source)
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)
    expected = json.loads(args.expected_plan.read_text())
    if (expected['schema_version'] != 3 or expected['planned_scenarios'] != 17
            or expected['planned_configurations'] != 629 or len(expected['selections']) != 629
            or not expected['all_configurations']):
        raise ValueError('Actual CPU plan must contain exact17 scenarios/629 configurations')
    attach_gate(matrix, expected, own, args.helper_sha256)
    sys.argv = [str(source), *native_args]
    matrix.main()


if __name__ == '__main__':
    main()
