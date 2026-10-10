#!/usr/bin/env python3
"""Future CPU stdin adapter; only substitutes the frozen native_load_log gate.

Writing this file does not execute or import the original scientific verifier.
Actual parent/native zero, observed Kit ancestry and idle proofs are external
host observations, supplied with an explicit SHA by the Root-owned continuation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
MODULE = Path('/control/resume_evidence.py')
MODULE_SHA = '41133f5be5900ebd3ffc291af670c1a89ff26889ad5d4de07106b167cf9df6a0'
HOST_OUTPUT = Path('/home/dzp/projects/php_parkour/outputs/research/native-resume-acceptance-preparation-01/run-output-final-frozen')
LABELS = ('teacher-locomotion', 'student-pure', 'student-finetune')


def require(value, message):
    if not value:
        raise ValueError(message)


def fingerprint(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in [path, *path.parents]), 'Regular immutable CPU input required')
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Input changed during read')
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def checked(row):
    path = Path(row['path'])
    require(path.is_relative_to(HOST_OUTPUT), 'Native receipt must be in the exact original output')
    path = Path('/outputs') / path.relative_to(HOST_OUTPUT)
    actual = fingerprint(path)
    require(all(actual[k] == row[k] for k in ['bytes', 'sha256']), 'Observed native receipt changed')
    return path, actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify-resume'])
    parser.add_argument('--label', choices=LABELS, required=True)
    parser.add_argument('--native-exit-proof', type=Path, required=True)
    parser.add_argument('--native-exit-proof-sha256', required=True)
    args = parser.parse_args()
    expected_path = Path('/outputs/continuation-admission') / (args.label + '-native.json')
    require(args.native_exit_proof == expected_path and re.fullmatch('[0-9a-f]{64}', args.native_exit_proof_sha256), 'Explicit exact admission path and SHA required')
    proof_fp = fingerprint(expected_path)
    require(proof_fp['sha256'] == args.native_exit_proof_sha256, 'Host admission SHA differs')
    proof = json.loads(expected_path.read_bytes())
    require(proof['schema_version'] == 1 and proof['status'] == 'native_completed_zero_and_container_idle'
            and proof['label'] == args.label and proof['stage'] == args.label + '-resume-target4'
            and re.fullmatch('[0-9a-f]{64}', proof['container_id']), 'Host admission identity differs')
    stage = proof['native_stage']
    require(stage['stage'] == proof['stage'] and stage['kind'] == 'actual_native_training_future_only'
            and stage['returncode'] == 0, 'Actual native parent result is not zero')
    native_path, native_fp = checked(stage['native_exec_receipt'])
    native = json.loads(native_path.read_bytes())
    wrapper, kit = stage['wrapper_mapping'], stage['kit_mapping']
    require(wrapper['host_pid'] != kit['host_pid'] and wrapper['container_pid'] == native['pid']
            and str(wrapper['start_time_clock_ticks']) == str(native['start_time_clock_ticks'])
            and native['stage'] == stage['stage'] and kit['argv'][0] == '/isaac-sim/kit/python/bin/python3'
            and kit['argv'][1:] == native['actual_exec_argv'][1:], 'Actual wrapper/Kit identity or argv differs')
    ancestry = stage['ancestry']
    require(ancestry[0] == kit and ancestry[-1] == wrapper and len({r['host_pid'] for r in ancestry}) == len(ancestry)
            and all(a['ppid'] == b['host_pid'] for a, b in zip(ancestry, ancestry[1:])), 'Observed native ancestry differs')
    for process in ancestry:
        require(process['state'] != 'Z' and int(process['start_time_clock_ticks']) > 0
                and process['nspid'] == [process['host_pid'], process['container_pid']]
                and process['nstgid'] == process['nspid'] and proof['container_id'] in process['cgroup']
                and process['boot_id'] == kit['boot_id'], 'Observed native namespace/birth ownership differs')
    live = [p for p in stage['idle_after']['processes'] if p['state'] != 'Z']
    require(len(live) == 2 and sum(p['container_pid'] == 1 for p in live) == 1
            and sum(p['argv'] == ['sleep', 'infinity'] for p in live) == 1
            and all(proof['container_id'] in p['cgroup'] for p in live)
            and not {(p['host_pid'], str(p['start_time_clock_ticks'])) for p in live}
                & {(p['host_pid'], str(p['start_time_clock_ticks'])) for p in ancestry}, 'Native wrapper/Kit not observed gone into idle')
    module_fp = fingerprint(MODULE)
    require(module_fp['sha256'] == MODULE_SHA, 'Original scientific verifier changed')
    spec = importlib.util.spec_from_file_location('_resume_original_cpu_science', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sidecar = {}
    def native_load_log(run_directory, input_checkpoint):
        require(str(input_checkpoint) == proof['expected_resume_checkpoint'], 'Host admission checkpoint differs')
        actual = native['actual_exec_argv']
        require(actual.count('--training.checkpoint') == 1
                and actual[actual.index('--training.checkpoint') + 1] == str(input_checkpoint), 'Native actual checkpoint argv differs')
        path = module.regular(Path(run_directory) / 'train.log')
        raw = path.read_text()
        prefix = {'teacher-locomotion': 'Loading checkpoint from ',
                  'student-pure': 'Loading Distillation checkpoint from ',
                  'student-finetune': 'Loading DistillationPPO checkpoint from '}[args.label]
        require(any(line.endswith(prefix + str(input_checkpoint)) for line in raw.splitlines()), 'Exact native checkpoint load line missing')
        require('Shutting down simulation app...' in raw, 'Native shutdown beginning missing')
        require(not re.search(r'Could not load optimizer state|Exception occurred during training|Traceback \(most recent call last\)|Fatal Python error|Segmentation fault|core dumped|free\(\):', raw), 'Native restore/training/fatal error')
        if args.label.startswith('teacher'):
            require('Optimizer loaded from checkpoint' in raw, 'PPO explicit optimizer load missing')
        sidecar.update(schema_version=1, status='actual_native_zero_kit_gone_and_shutdown_begin_verified',
            label=args.label, original_module=module_fp, host_admission=proof_fp, native_receipt=native_fp,
            actual_native_parent_returncode=0, real_kit_birth_observed=True, observed_native_children_gone=True,
            native_load_shutdown_log=module.fingerprint(path), shutdown_begin_present=True,
            post_close_training_shutdown_complete_present='Training shutdown complete.' in raw,
            post_close_simulation_app_closed_present='Simulation app closed.' in raw,
            simulation_app_close_return_verified=False,
            scope='Only log admission changed: shutdown beginning plus actual native zero and observed Kit exit. Legacy native_load_shutdown_log field does not assert close() returned. Original optimizer/weight/TB/ONNX/skip science remains unchanged.')
        return path
    module.native_load_log = native_load_log
    sys.argv = [str(MODULE), 'verify-resume', '--label', args.label]
    module.main()
    require(sidecar and fingerprint(MODULE) == module_fp and fingerprint(expected_path) == proof_fp
            and fingerprint(native_path) == native_fp, 'CPU adapter inputs changed')
    module.write_new(Path('/outputs/continuation-admission') / (args.label + '-shutdown-log-validation.json'), sidecar)
    print(json.dumps({'status': sidecar['status'], 'label': args.label, 'original_scientific_module_unchanged': True}))


if __name__ == '__main__':
    main()
