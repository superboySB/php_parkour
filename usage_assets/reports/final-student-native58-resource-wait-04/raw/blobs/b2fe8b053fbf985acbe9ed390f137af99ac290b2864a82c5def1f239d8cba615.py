#!/usr/bin/env python3
"""Own the real e238 parent for the separately reviewed cross-boot native58 run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
CONTROL = ROOT / 'outputs/research/final-student-native58-crossboot-control-01'
PINS = {
    'manifest.json': 'e1845f7c53efdbf9348ef876c945017b616077d58069d51f7f90ac1a6ded70fd',
    'crossboot_gate.py': '842726d3b6c671c0f863094c17f36262e772f7eb7acda6c4642a03ef419e7ec6',
    'run_native58.py': '119a374c80d986ab24c1f6516bccccdd8fbd52338ec08b57a3be400b3421266f',
}
PROTOCOL = ROOT / 'outputs/research/reproduction-20261015/run_formal_reference629.py'
PROTOCOL_SHA = '0efbd749b57bf198f7d1d9a33e3cbf97c22a8c1a7a49fc836fcc1100ec8dc1e9'
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'


def load(path, digest, name):
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Reviewed source pin differs: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--control-output', required=True, type=Path)
    parser.add_argument('--admission-wait-seconds', type=float, default=86400)
    parser.add_argument('--poll-seconds', type=float, default=5)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    if not args.root_authorized_start or not math.isfinite(args.admission_wait_seconds) or not math.isfinite(args.poll_seconds):
        raise ValueError('Explicit start and finite waiting limits required')
    if not 0 <= args.admission_wait_seconds <= 7 * 86400 or not .1 <= args.poll_seconds <= 60:
        raise ValueError('Waiting/poll outside reviewed bounds')
    protocol = load(PROTOCOL, PROTOCOL_SHA, 'original_reviewed_parent_protocol')
    gate = load(CONTROL / 'crossboot_gate.py', PINS['crossboot_gate.py'], 'reviewed_crossboot_admission')
    output = protocol.safe(args.output)
    control_output = protocol.safe(args.control_output)
    protocol.require(not output.exists() and not control_output.exists(), 'Fresh receipt outputs required')
    protocol.require(not output.is_relative_to(control_output) and not control_output.is_relative_to(output), 'Receipt outputs overlap')

    def recheck():
        data, contract_fp, preparation, plan = gate.contract(args.contract, args.contract_sha256)
        protocol.require(data['preparation']['sha256'] == PINS['manifest.json'], 'Root-reviewed preparation changed')
        rows = [protocol.fp(__file__), protocol.fp(PROTOCOL), protocol.fp(LAUNCHER)]
        protocol.require(rows[1]['sha256'] == PROTOCOL_SHA and rows[2]['sha256'] == LAUNCHER_SHA, 'Original protocol/parent changed')
        rows += [gate.fingerprint(CONTROL / name) for name in PINS]
        protocol.require(all(row['sha256'] == PINS[Path(row['path']).name] for row in rows[3:]), 'Crossboot source changed')
        return rows + [contract_fp] + [data[name] for name in ('source_review', 'plan', 'cpu_prepare_review', 'resource_audit', 'unix_endpoint_observation')]

    sources = recheck()
    data, _, _, _ = gate.contract(args.contract, args.contract_sha256)
    base = Path(data['plan']['path']).parent
    protocol.require(not (base / 'host/launch-receipt.json').exists() and not any((base / 'phases').iterdir()), 'Started native attempts are never retried')
    for path in (output, control_output):
        protocol.require(not path.is_relative_to(base) and not base.is_relative_to(path), 'Receipts overlap frozen native base')
        protocol.require(not path.is_relative_to(CONTROL) and not CONTROL.is_relative_to(path), 'Receipts overlap preparation')
    adapter = ['/usr/bin/python3', '-B', str(CONTROL / 'run_native58.py'), 'run',
               '--contract', str(args.contract), '--contract-sha256', args.contract_sha256,
               '--output', str(control_output), '--admission-wait-seconds', str(args.admission_wait_seconds),
               '--poll-seconds', str(args.poll_seconds), '--root-authorized-start']
    launcher = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(CONTROL / 'run_native58.py'),
                '--sha256', PINS['run_native58.py'], '--output', str(output / 'original-parent'), '--', *adapter]
    return protocol.run_owned(launcher, adapter, output, sources, recheck,
        science_scope='final_student_native58_explicit_crossboot_host_control_v1')


if __name__ == '__main__':
    raise SystemExit(main())
