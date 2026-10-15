#!/usr/bin/env python3
"""Own the genuine original parent for the explicitly versioned formal629 cohort."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
PREPARATION = ROOT / 'outputs/research/final-student-reference629-crossboot-preparation-02'
PREPARATION_SHA = '9f32c251bcb25c3ed1fbe999bd49c8081a712ce0d6985a99f8ed6820c661af2b'
ADAPTER_SHA = 'ce216a06b36b06b21aa1c110b50f33483a036e17c64f309827ca8480166bbe53'
PROTOCOL = WORK / 'run_formal_reference629.py'
PROTOCOL_SHA = '0efbd749b57bf198f7d1d9a33e3cbf97c22a8c1a7a49fc836fcc1100ec8dc1e9'
LAUNCHER = ROOT / 'outputs/research/host_owned_launch.py'
LAUNCHER_SHA = 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--contract-review', type=Path, required=True)
    parser.add_argument('--contract-review-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root-authorized-start', action='store_true')
    args = parser.parse_args()
    import hashlib
    if PROTOCOL.is_symlink() or hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise ValueError('Original reviewed actual-parent protocol changed')
    spec = importlib.util.spec_from_file_location('frozen_actual_parent_protocol', PROTOCOL)
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    protocol.require(args.root_authorized_start, 'Explicit separately reviewed start required')
    contract_path, review_path, output = map(protocol.safe, (args.contract, args.contract_review, args.output))
    protocol.require(str(contract_path) == str(args.contract) and str(review_path) == str(args.contract_review), 'Canonical absolute contract/review paths required')
    adapter = PREPARATION / 'adapter.py'

    def recheck():
        sources = [protocol.fp(__file__), protocol.fp(PROTOCOL), protocol.fp(LAUNCHER),
                   protocol.fp(adapter), protocol.fp(PREPARATION / 'preparation-manifest.json'),
                   protocol.fp(contract_path), protocol.fp(review_path)]
        expected = (PROTOCOL_SHA, LAUNCHER_SHA, ADAPTER_SHA, PREPARATION_SHA,
                    args.contract_sha256, args.contract_review_sha256)
        protocol.require(all(row['sha256'] == sha for row, sha in zip(sources[1:], expected)), 'Reviewed source/preparation/actual contract/review SHA differs')
        manifest = protocol.read(PREPARATION / 'preparation-manifest.json')
        protocol.require(len(manifest['files']) == 85, 'Exact reviewed85 preparation required')
        names = set()
        for row in manifest['files']:
            relative = Path(row['path'])
            protocol.require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in names, 'Unsafe/duplicate preparation source')
            names.add(str(relative))
            actual = protocol.fp(PREPARATION / relative)
            protocol.require((actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256']), 'Preparation dependency changed')
            sources.append(actual)
        contract, review = protocol.read(contract_path), protocol.read(review_path)
        protocol.require(contract['schema_version'] == 1 and contract['status'] == 'prepared_for_separate_review'
                         and contract['native_started'] is False and contract['gpu_started'] is False
                         and contract['contract_identity'] == protocol.identity({k: v for k, v in contract.items() if k != 'contract_identity'})
                         and contract['expected'] == {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}
                         and contract['kind_order'] == ['pure', 'finetune'] and contract['preparation_manifest'] == sources[4]
                         and Path(contract['base']) / 'contract.json' == contract_path, 'Actual prepared formal629 contract identity/scope differs')
        protocol.require(review['status'] == 'passed_readonly_formal_reference629_resource_wait_contract_review'
                         and review['must_fix'] == [] and review['contract'] == sources[5]
                         and review['preparation_manifest'] == sources[4]
                         and review['native_started'] is False, 'Actual independent CPU contract review missing or refers to another cohort')
        return sources

    sources = recheck()
    contract = protocol.read(contract_path)
    base = protocol.safe(contract['base'])
    protocol.require(not (base / 'runs').exists(), 'An already-started scientific attempt is never retried')
    protocol.require(not output.exists() and not output.is_relative_to(base) and not base.is_relative_to(output), 'Fresh independent original-parent output required')
    protocol.require(not output.is_relative_to(PREPARATION) and not PREPARATION.is_relative_to(output), 'Receipt output overlaps sealed preparation')
    adapter_argv = ['/usr/bin/python3', '-B', str(adapter), 'execute', '--preparation-sha256', PREPARATION_SHA,
                    '--contract', str(contract_path), '--contract-sha256', args.contract_sha256, '--root-authorized-start']
    launcher_argv = ['/usr/bin/python3', '-B', str(LAUNCHER), '--helper', str(adapter), '--sha256', ADAPTER_SHA,
                     '--output', str(output / 'original-parent'), '--', *adapter_argv]
    return protocol.run_owned(launcher_argv, adapter_argv, output, sources, recheck,
                              science_scope='official_two_students_full_reference629_resource_wait_host_admission_v3')


if __name__ == '__main__':
    raise SystemExit(main())
