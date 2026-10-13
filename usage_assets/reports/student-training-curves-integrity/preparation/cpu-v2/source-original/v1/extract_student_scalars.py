#!/usr/bin/env python3
"""Read SHA-bound completed student TensorBoard events in CPU Docker only."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

TARGETS = {'pure': 10000, 'finetune': 30000}
CORE_TAGS = {
    'pure': ('Loss/behavior', 'Loss/warmup_active'),
    'finetune': ('Loss/ppo_coef', 'Loss/warmup_active', 'Loss/learning_rate',
                 'Loss/total_loss', 'Loss/surrogate_loss', 'Loss/value_loss',
                 'Loss/behavior', 'Loss/entropy_mean', 'Loss/mean_kl'),
}
CONDITIONAL_TAGS = ('Train/mean_reward', 'Train/mean_episode_length', 'Loss/ppo_gate_mean')
FALSE_FLAGS = {key: False for key in ('quality_verified', 'convergence_verified',
    'official_schedule_complete', 'seven_PT_acceptance_verified', 'pt_onnx_numerical_parity_verified')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute normalized input path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Input has a symlink component')
    require(stat.S_ISREG(path.stat().st_mode), 'Regular input required: ' + str(path))
    return path


def fingerprint(path, raw=False):
    path = regular(path)
    before = path.stat()
    digest, chunks = hashlib.sha256(), []
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            digest.update(chunk)
            if raw:
                chunks.append(chunk)
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after), 'Input changed while reading: ' + str(path))
    record = {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}
    return (record, b''.join(chunks)) if raw else record


def bound(record, raw=False):
    require(isinstance(record, dict) and {'path', 'bytes', 'sha256'} <= set(record), 'Missing file fingerprint')
    require(type(record['bytes']) is int and record['bytes'] > 0
        and isinstance(record['sha256'], str) and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'Invalid input fingerprint')
    actual = fingerprint(record['path'], raw)
    fp = actual[0] if raw else actual
    require(fp == {key: record[key] for key in ('path', 'bytes', 'sha256')}, 'Input bytes/SHA mismatch: ' + record['path'])
    return actual


def cpu_only():
    require(Path('/.dockerenv').is_file() and os.environ.get('CUDA_VISIBLE_DEVICES') == ''
        and os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'void', 'Use the isolated GPU-hidden CPU Docker entry point')
    require(not list(Path('/dev').glob('nvidia[0-9]*')), 'CPU container exposes a GPU device')


def event_file_set(directory):
    directory = Path(directory)
    require(directory.is_absolute() and '..' not in directory.parts
        and not any(p.is_symlink() for p in (directory, *directory.parents)) and directory.is_dir(), 'Unsafe run directory')
    paths = sorted(directory.glob('events.out.tfevents.*'))
    for path in paths:
        regular(path)
    return [str(path) for path in paths]


def admission(contract_path, expected_sha):
    fp, raw = fingerprint(contract_path, True)
    require(re.fullmatch('[0-9a-f]{64}', expected_sha) and fp['sha256'] == expected_sha, 'Input contract SHA differs')
    contract = strict_json(raw)
    require(type(contract.get('schema_version')) is int and contract['schema_version'] == 1
        and contract.get('kind') in TARGETS, 'Unknown student contract')
    kind, target = contract['kind'], TARGETS[contract['kind']]
    manifest_fp, manifest_raw = bound(contract['native_manifest'], True)
    manifest = strict_json(manifest_raw)
    stage = 'student-' + kind
    require(manifest.get('label') == stage and manifest.get('profile') == 'official'
        and manifest.get('status') == 'passed' and type(manifest.get('returncode')) is int
        and manifest['returncode'] == 0 and type(manifest.get('checkpoint_iteration')) is int
        and manifest['checkpoint_iteration'] == target - 1 and manifest.get('finished_utc'), 'Actual final official native manifest required')
    checkpoint = PurePosixPath(manifest['checkpoint'])
    prefix = PurePosixPath('/outputs/official-full/official') / stage / 'PHP-research'
    require(checkpoint.is_absolute() and '..' not in checkpoint.parts and checkpoint.is_relative_to(prefix)
        and len(checkpoint.relative_to(prefix).parts) == 2 and str(checkpoint) == manifest['checkpoint']
        and checkpoint.name == f'model_{target - 1:05d}.pt'
        and re.fullmatch('[0-9a-f]{64}', manifest.get('checkpoint_sha256', '')), 'Native final checkpoint identity/path differs')
    require(contract['native_run_directory'] == str(checkpoint.parent), 'Events are not bound to the final checkpoint run')
    run = Path(contract['run_directory'])
    require(run.is_absolute() and '..' not in run.parts and run.is_relative_to('/artifacts'), 'Run must be a read-only /artifacts mapping')
    events = contract.get('events')
    require(isinstance(events, list) and events, 'At least one actual event file required')
    local_paths, native_paths, inputs = [], [], [fp, manifest_fp]
    for event in events:
        native = PurePosixPath(event['native_path'])
        local = Path(event['path'])
        require(native.parent == checkpoint.parent and '..' not in native.parts
            and native.name.startswith('events.out.tfevents.') and str(native) == event['native_path']
            and local == run / native.name, 'Event is not the original same-run basename/path')
        inputs.append(bound(event))
        local_paths.append(str(local)); native_paths.append(str(native))
    require(len(set(local_paths)) == len(events) == len(set(native_paths)), 'Duplicate input event paths')
    require(sorted(local_paths) == event_file_set(run), 'Actual run event file-set differs from the exact contract')
    return contract, manifest, inputs


def coverage(rows, target, required):
    steps = [row['step'] for row in rows]
    counts = Counter(steps)
    finite = all(row['value'] is not None and row['wall_time'] is not None for row in rows)
    return {'samples': len(rows), 'unique_steps': len(counts),
        'first_step': min(steps) if steps else None, 'last_step': max(steps) if steps else None,
        'missing_steps': [step for step in range(target) if step not in counts],
        'duplicate_steps': [{'step': step, 'count': count} for step, count in sorted(counts.items()) if count > 1],
        'out_of_range_steps': sorted(step for step in counts if step < 0 or step >= target),
        'out_of_order': any(right < left for left, right in zip(steps, steps[1:])),
        'all_finite': finite, 'required_core': required}


def extract(report, contract, manifest, inputs):
    kind, target = contract['kind'], TARGETS[contract['kind']]
    report.update(kind=kind, stage='student-' + kind, target_iterations=target,
        input_contract=inputs[0], native_manifest=inputs[1], input_files=inputs,
        native_terminal={key: manifest[key] for key in ('label', 'profile', 'status', 'returncode',
            'checkpoint', 'checkpoint_iteration', 'checkpoint_sha256', 'finished_utc')},
        run_directory=contract['run_directory'], native_run_directory=contract['native_run_directory'],
        required_core_tags=list(CORE_TAGS[kind]), events=[], scalars={}, tag_coverage={})
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    for event, event_fp in zip(contract['events'], inputs[2:]):
        record = dict(event_fp, native_path=event['native_path'], scalar_tags=[], parsed_scalar_samples=0)
        report['events'].append(record)
        try:
            # Per-file loading plus disabled restart purge preserves original duplicates.
            accumulator = EventAccumulator(event['path'], size_guidance={'scalars': 0}, purge_orphaned_data=False)
            accumulator.Reload()
            record['scalar_tags'] = list(accumulator.Tags()['scalars'])
            for tag in record['scalar_tags']:
                output = report['scalars'].setdefault(tag, [])
                for index, item in enumerate(accumulator.Scalars(tag)):
                    require(type(item.step) is int, 'Noninteger TensorBoard step')
                    row = {'step': item.step, 'wall_time': float(item.wall_time), 'value': float(item.value),
                        'source_event': event['path'], 'event_sample_index': index}
                    for field in ('wall_time', 'value'):
                        if not math.isfinite(row[field]):
                            row[field + '_nonfinite_original'] = repr(row[field]); row[field] = None
                            report['diagnostics'].append({'problem': 'nonfinite_scalar', 'tag': tag,
                                'source_event': event['path'], 'event_sample_index': index, 'step': item.step, 'field': field})
                    output.append(row); record['parsed_scalar_samples'] += 1
        except Exception as error:
            record['parse_error'] = type(error).__name__ + ': ' + str(error)
            report['diagnostics'].append({'problem': 'event_parse_failed', 'path': event['path'], 'error': record['parse_error']})
    tags = sorted(set(report['scalars']) | set(CORE_TAGS[kind]) | set(CONDITIONAL_TAGS))
    for tag in tags:
        rows = report['scalars'].get(tag, [])
        info = coverage(rows, target, tag in CORE_TAGS[kind])
        report['tag_coverage'][tag] = info
        if tag in CORE_TAGS[kind] and (not info['all_finite'] or info['missing_steps']
                or info['duplicate_steps'] or info['out_of_range_steps'] or [row['step'] for row in rows] != list(range(target))):
            report['diagnostics'].append({'problem': 'core_steps_not_exact_finite_once_0_to_target_minus_1', 'tag': tag})
    for original in inputs:
        require(fingerprint(original['path']) == original, 'Original input changed during extraction')
    require(event_file_set(contract['run_directory']) == sorted(event['path'] for event in contract['events']), 'Event file-set changed during extraction')
    report['input_files_unchanged'] = True
    report['training_scalar_integrity_complete'] = not report['diagnostics']
    report['conditional_tag_scope'] = 'Reward/episode tags are conditional; ppo_gate_mean is emitted only by the PPO update branch. Actual coverage/duplicates remain unmodified.'
    report['raw_numeric_encoding'] = 'Nonfinite values are recorded as null plus their original repr and diagnostics; original event bytes remain the authoritative source.'
    require(report['training_scalar_integrity_complete'], 'Scalar integrity failed; original rows and diagnostics retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cpu_only()
    require(args.output.is_absolute() and '..' not in args.output.parts and args.output.is_relative_to('/validation')
        and not any(p.is_symlink() for p in (args.output, *args.output.parents)) and not args.output.exists(), 'Fresh /validation report path required')
    source = fingerprint(Path(__file__).absolute())
    report = {'schema_version': 1, 'phase': 'student_training_scalars', 'status': 'running',
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'extractor_source': source,
        'diagnostics': [], 'training_scalar_integrity_complete': False,
        'scope': 'Original completed official student training scalar integrity only; no policy rollout, convergence, seven-PT acceptance or ONNX parity.', **FALSE_FLAGS}
    failure = None
    try:
        contract, manifest, inputs = admission(args.contract, args.contract_sha256)
        extract(report, contract, manifest, inputs)
        require(fingerprint(Path(__file__).absolute()) == source, 'Extractor source changed')
        report['status'] = 'passed'
    except Exception as error:
        failure = error
        report.update(status='failed', training_scalar_integrity_complete=False,
            error=type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    if failure is not None:
        raise SystemExit(1)
    print(json.dumps({'status': report['status'], 'stage': report['stage'], 'target_iterations': report['target_iterations']}))


if __name__ == '__main__':
    main()
