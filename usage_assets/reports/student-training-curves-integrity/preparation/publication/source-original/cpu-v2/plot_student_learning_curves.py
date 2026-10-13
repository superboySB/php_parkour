#!/usr/bin/env python3
"""Plot SHA-bound completed student scalar integrity reports in CPU Docker only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

TARGETS = {'pure': 10000, 'finetune': 30000}
CORE_TAGS = {
    'pure': ('Loss/behavior', 'Loss/warmup_active'),
    'finetune': ('Loss/ppo_coef', 'Loss/warmup_active', 'Loss/learning_rate',
                 'Loss/total_loss', 'Loss/surrogate_loss', 'Loss/value_loss',
                 'Loss/behavior', 'Loss/entropy_mean', 'Loss/mean_kl'),
}
FALSE_FLAGS = {key: False for key in ('quality_verified', 'convergence_verified',
    'official_schedule_complete', 'seven_PT_acceptance_verified', 'pt_onnx_numerical_parity_verified')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
        and not any(p.is_symlink() for p in (path, *path.parents))
        and stat.S_ISREG(path.stat().st_mode), 'Regular normalized input without symlinks required')
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
    require(identity(before) == identity(after), 'Input changed while reading')
    record = {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}
    return (record, b''.join(chunks)) if raw else record


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def trailing_mean(values, window):
    result, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        result.append(total / min(index + 1, window))
    require(all(math.isfinite(value) for value in result), 'Nonfinite derived moving average')
    return result


def finite_row(row):
    return (type(row.get('step')) is int and row['step'] >= 0
        and type(row.get('value')) in (int, float) and math.isfinite(row['value'])
        and type(row.get('wall_time')) in (int, float) and math.isfinite(row['wall_time']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--input-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--window', type=int, default=25)
    args = parser.parse_args()
    require(Path('/.dockerenv').is_file() and os.environ.get('CUDA_VISIBLE_DEVICES') == ''
        and os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'void'
        and not list(Path('/dev').glob('nvidia[0-9]*')), 'Use GPU-hidden CPU Docker')
    require(args.window > 0, 'Positive moving-average sample window required')
    source = fingerprint(Path(__file__).absolute())
    input_fp, raw = fingerprint(args.input, True)
    require(re.fullmatch('[0-9a-f]{64}', args.input_sha256) and input_fp['sha256'] == args.input_sha256, 'Actual extractor report SHA differs')
    payload = strict_json(raw)
    kind = payload.get('kind')
    require(kind in TARGETS and type(payload.get('schema_version')) is int and payload['schema_version'] == 1
        and payload.get('phase') == 'student_training_scalars' and payload.get('status') == 'passed'
        and payload.get('event_integrity_complete') is True
        and payload.get('training_scalar_integrity_complete') is True and payload.get('input_files_unchanged') is True
        and payload.get('stage') == 'student-' + kind and payload.get('target_iterations') == TARGETS[kind]
        and payload.get('diagnostics') == [] and all(payload.get(key) is False for key in FALSE_FLAGS), 'Actual completed student scalar integrity report required')
    target = TARGETS[kind]
    require(payload['required_core_tags'] == list(CORE_TAGS[kind]), 'Core student tags differ from native algorithm')
    inputs = payload['input_files']
    require(len(inputs) >= 3 and len({row['path'] for row in inputs}) == len(inputs)
        and inputs[0] == payload['input_contract'] and inputs[1] == payload['native_manifest'], 'Extractor input contract/manifest inventory differs')
    require(inputs[2:] == [{key: event[key] for key in ('path', 'bytes', 'sha256')} for event in payload['events']], 'Event inventory differs')
    for event in payload['events']:
        integrity = event.get('tfrecord_integrity', {})
        expected = {key: event[key] for key in ('path', 'bytes', 'sha256')}
        require(integrity.get('status') == 'passed' and integrity.get('format') == 'TFRecord'
            and integrity.get('expected_file') == expected and integrity.get('bytes') == event['bytes']
            and integrity.get('sha256') == event['sha256'] and type(integrity.get('records')) is int
            and integrity['records'] > 0 and integrity.get('complete_eof') is True
            and integrity.get('crc32c_verified') is True and integrity.get('diagnostics') == [],
            'Each whole original event must pass framing/CRC/EOF before plotting')
    for row in [*inputs, payload['extractor_source']]:
        require(fingerprint(row['path']) == row, 'Original extractor/input changed before plotting')
    scalars, coverage = payload['scalars'], payload['tag_coverage']
    for tag in CORE_TAGS[kind]:
        rows, info = scalars[tag], coverage[tag]
        require(len(rows) == target and [row['step'] for row in rows] == list(range(target))
            and all(finite_row(row) for row in rows) and info['required_core'] is True
            and info['samples'] == info['unique_steps'] == target and info['all_finite'] is True
            and info['missing_steps'] == info['duplicate_steps'] == info['out_of_range_steps'] == []
            and info['out_of_order'] is False, 'Full finite once-per-step core scalar sequence required: ' + tag)
    plotted = [*CORE_TAGS[kind], 'Train/mean_reward', 'Train/mean_episode_length']
    if kind == 'finetune':
        plotted.append('Loss/ppo_gate_mean')
    for tag in plotted:
        require(tag in coverage and all(finite_row(row) for row in scalars.get(tag, [])), 'Invalid conditional scalar report: ' + tag)
    output = args.output
    require(output.is_absolute() and '..' not in output.parts and output.is_relative_to('/validation')
        and not any(p.is_symlink() for p in (output, *output.parents)) and not output.exists(), 'Fresh /validation plot directory required')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'running', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'kind': kind, 'stage': payload['stage'], 'target_iterations': target,
        'input': input_fp, 'plot_source': source, 'input_contract': payload['input_contract'],
        'native_manifest': payload['native_manifest'], 'events': payload['events'],
        'event_integrity_complete': True, 'event_integrity_checker': payload['event_integrity_checker'],
        'input_files': [*inputs, input_fp], 'input_files_unchanged': False,
        'tags': [dict({'tag': tag}, **coverage[tag]) for tag in plotted], 'figures': [],
        'unplotted_actual_tags': sorted(set(scalars) - set(plotted)),
        'scope': 'Actual logged student training values and coverage; no rollout, convergence, skill, seven-PT or ONNX-parity acceptance.',
        'smoothing': {'method': 'trailing arithmetic mean', 'window_samples': args.window,
            'conditional_series': 'Original points retained; averages restart at missing, duplicate or decreasing steps. No missing sample is synthesized.'}, **FALSE_FLAGS}
    failure = None
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        matplotlib.rcParams['svg.hashsalt'] = input_fp['sha256']
        columns = 2 if len(plotted) <= 4 else 3
        nrows = (len(plotted) + columns - 1) // columns
        fig, axes = plt.subplots(nrows, columns, figsize=(13.5, 3.3 * nrows + 1.5), squeeze=False)
        for axis, tag in zip(axes.flat, plotted):
            rows, info = scalars.get(tag, []), coverage[tag]
            steps, values = [row['step'] for row in rows], [row['value'] for row in rows]
            if rows:
                axis.scatter(steps, values, color='#087f8c', alpha=.3, s=3, label='Original logged samples')
                segments = []
                for index, row in enumerate(rows):
                    if not segments or row['step'] != rows[index - 1]['step'] + 1:
                        segments.append([])
                    segments[-1].append(row)
                for index, segment in enumerate(segments):
                    axis.plot([row['step'] for row in segment], trailing_mean([row['value'] for row in segment], args.window),
                        color='#e28b2d', linewidth=1.0, label=f'Trailing mean ({args.window} actual samples)' if index == 0 else None)
                axis.legend(loc='best', fontsize=7, frameon=False)
            else:
                axis.text(.5, .5, 'No native samples for this conditional tag', ha='center', va='center', transform=axis.transAxes)
            axis.set_title(tag, loc='left', fontsize=10)
            axis.set_xlabel('Actual native training iteration')
            axis.set_ylabel('Logged value')
            axis.set_xlim(0, target - 1)
            axis.grid(alpha=.18)
            axis.text(.01, .02, f"{info['samples']} samples; {len(info['missing_steps'])} missing steps; {len(info['duplicate_steps'])} duplicate steps",
                fontsize=7, transform=axis.transAxes)
        for axis in list(axes.flat)[len(plotted):]:
            axis.set_visible(False)
        fig.suptitle(f'Official student-{kind} — {target} training iterations', fontsize=16, y=.99)
        fig.text(.5, .955, 'CORE SCALAR INTEGRITY VERIFIED | REWARD COVERAGE AS LOGGED | QUALITY / CONVERGENCE NOT VERIFIED', ha='center', fontsize=8, color='#9d4b24')
        fig.text(.03, .01, 'Original event/report SHA bound; missing/duplicate conditional samples are not repaired. Input SHA: ' + input_fp['sha256'][:20], fontsize=7)
        fig.tight_layout(rect=(0, .025, 1, .935))
        png, svg = output / 'learning-curves.png', output / 'learning-curves.svg'
        fig.savefig(png, dpi=160, metadata={'Description': 'Actual completed student training scalar curves; quality/convergence not verified; input SHA ' + input_fp['sha256']})
        fig.savefig(svg, metadata={'Date': None, 'Description': 'Actual student scalar curves; input SHA ' + input_fp['sha256']})
        plt.close(fig)
        for original in [*inputs, input_fp, payload['extractor_source'], source]:
            require(fingerprint(original['path']) == original, 'Input or source changed while plotting')
        report.update(status='rendered_student_training_curves', input_files_unchanged=True,
            matplotlib=matplotlib.__version__, backend=matplotlib.get_backend(), figures=[fingerprint(png), fingerprint(svg)])
    except Exception as error:
        failure = error
        report.update(status='failed', error=type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with (output / 'plot-report.json').open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    if failure is not None:
        raise SystemExit(1)
    print(json.dumps({'status': report['status'], 'stage': report['stage'], 'figures': report['figures']}))


if __name__ == '__main__':
    main()
