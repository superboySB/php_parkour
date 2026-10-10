#!/usr/bin/env python3
"""CPU-only plan/evidence checks for four independent native attempts.

Passed as exact frozen stdin bytes to a private runc/noGPU container. It does
not construct a simulator, SDK robot, policy or DDS object. Written, not run.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
SOURCE = Path('/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py')
SOURCE_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
OLD_PLAN = Path('/data/native-plan.json')
OLD_PLAN_SHA = 'dc8a2994f246a221d2b745a355dd8512964434397db9e47b9ed6131bbb06f287'
CASES = ['high_speed_speed_vault:0004:run_left_45_0.3s',
         'high_speed_speed_vault:0005:run_left_45_0.5s',
         'high_speed_speed_vault:0006:run_left_45_0.9s',
         'high_speed_speed_vault:0007:run_left_45_1.2s']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def relocate(value):
    if isinstance(value, str):
        prefix = '/outputs/all-configs'
        return '/outputs/missing-four' + value[len(prefix):] if value == prefix or value.startswith(prefix + '/') else value
    if isinstance(value, dict):
        return {key: relocate(child) for key, child in value.items()}
    if isinstance(value, list):
        return [relocate(child) for child in value]
    return value


def plan_check(matrix, args):
    require(args.case_id == CASES, 'Exact four ordered case IDs required')
    require(args.plan == Path('/outputs/missing-four-plan.json')
            and args.matrix == Path('/outputs/missing-four/matrix.json'), 'Fixed new namespace required')
    require(sha(OLD_PLAN) == OLD_PLAN_SHA, 'Frozen old complete plan changed')
    old = read(OLD_PLAN)
    expected = relocate(copy.deepcopy(old))
    expected.pop('plan_sha256')
    expected['plan_sha256'] = matrix.identity(expected)
    actual = read(args.plan)
    require(actual == expected, 'New actual CLI plan must differ only by independent output namespace and derived identity')
    require(actual['schema_version'] == 3 and actual['planned_configurations'] == 629
            and actual['planned_scenarios'] == 17 and actual['all_configurations'] is True
            and actual['seconds_per_configuration'] == 10.0 and actual['seed'] == 42
            and len(actual['dependencies']) == 376, 'Complete fixed input/clock/closure contract differs')
    chosen = [selection for selection in actual['selections'] if selection['case_id'] in CASES]
    require([row['case_id'] for row in chosen] == CASES, 'Exact ordered subset unavailable')
    for selection in chosen:
        matrix.verify_inputs(actual, selection)
    return actual, chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'final'])
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case-id', action='append', default=[])
    args = parser.parse_args()
    require(args.output == Path('/outputs/' + ('plan-validation.json' if args.mode == 'plan' else 'full-validation.json'))
            and not args.output.exists(), 'Fresh fixed CPU report required')
    require(sha(SOURCE) == SOURCE_SHA, 'Frozen native validator source changed')
    spec = importlib.util.spec_from_file_location('_missing_four_frozen_matrix', SOURCE)
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)
    result = {'schema_version': 1, 'status': 'running', 'mode': args.mode, 'started_unix': time.time(),
              'scope': 'CPU-only original schema3 native evidence checks and full MP4 decode; independent four-case attempts',
              'original_session54334_exit_code': 143, 'historical_host_observer_gap_preserved': True,
              'source_sha256': SOURCE_SHA, 'cases': [], 'quality_verified': False,
              'obstacle_course_completion_verified': False}
    write(args.output, result)
    try:
        plan_before = sha(args.plan)
        plan, chosen = plan_check(matrix, args)
        result.update(native_plan_sha256=plan['plan_sha256'], native_plan_file_sha256=plan_before,
                      planned_configurations=629, selected_case_ids=CASES,
                      dependency_count=len(plan['dependencies']), configurations=4)
        if args.mode == 'final':
            matrix_before = sha(args.matrix)
            report = read(args.matrix)
            require(read(args.matrix.parent / 'plan.json') == plan, 'Executed immutable plan differs')
            require(report['status'] == 'completed_subset' and report['completed_configurations'] == 4
                    and report['completed_scenarios'] == 1 and report['configuration_coverage_complete'] is False
                    and len(report['selections']) == 629, 'Real four-case subset terminal required')
            require(all(report.get(key) == value for key, value in plan.items() if key not in ('status', 'selections')),
                    'Executed full-plan immutable metadata differs')
            invocation = report['last_invocation']
            require(invocation['case_ids'] == CASES and invocation['case_limit'] is None
                    and invocation['resume'] is False and invocation['requested_configurations'] == 4,
                    'Actual execution invocation is not exact fresh four-case subset')
            for expected, case in zip(plan['selections'], report['selections']):
                require(all(case.get(key) == value for key, value in expected.items()), 'Case original input identity differs')
                if case['case_id'] not in CASES:
                    require(not case.get('attempts') and 'status' not in case, 'Unselected configuration was attempted')
                    continue
                require(case['status'] == 'completed' and len(case['attempts']) == 1
                        and case['attempts'][0]['status'] == 'completed' and case['attempts'][0]['returncode'] == 0,
                        'Fresh once-only native parent0 required')
                attempt = case['attempts'][0]
                matrix.verify_inputs(plan, expected)
                matrix.verify_completed(attempt, plan, case)
                directory = Path(attempt['output'])
                native_path = directory / 'result.json'
                native = read(native_path)
                sealed = matrix.validate_worker_receipts(directory, plan, native)
                require(native['inference']['ticks'] == 500 and len(native['videos']) == 1, '500ticks/onevideo required')
                decoded = []
                for relative in native['videos']:
                    raw_path = directory / relative
                    path = raw_path.resolve()
                    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts
                            and not raw_path.is_symlink() and path.is_relative_to(directory.resolve()), 'Unsafe native video')
                    before = sha(path)
                    argv = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads', '1', '-i', str(path), '-f', 'null', '-']
                    completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
                    row = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': before, 'command': argv,
                           'returncode': completed.returncode, 'stderr': completed.stderr,
                           'full_decode': completed.returncode == 0}
                    decoded.append(row)
                    result['current_video_check'] = row
                    write(args.output, result)
                    require(completed.returncode == 0 and sha(path) == before, 'Original full video decode/hash failed')
                result['cases'].append({'case_id': case['case_id'], 'native_result_sha256': sha(native_path),
                    'parent_returncode': 0, 'worker_receipts': sealed, 'worker_exit0_empty_groups': 2,
                    'policy_ticks': 500, 'videos': decoded, 'survival_heuristic_passed': native['survival_passed'],
                    'quality_verified': False, 'obstacle_course_completion_verified': False})
                write(args.output, result)
            require([row['case_id'] for row in result['cases']] == CASES and sha(args.matrix) == matrix_before,
                    'Actual final cases or immutable matrix changed')
            result.update(matrix_sha256=matrix_before, worker_exit0_empty_group_count=8, full_decoded_mp4_count=4)
        require(sha(args.plan) == plan_before and sha(SOURCE) == SOURCE_SHA, 'Plan/validator changed')
        result['status'] = 'passed'
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        result['finished_unix'] = time.time()
        write(args.output, result)


if __name__ == '__main__':
    main()
