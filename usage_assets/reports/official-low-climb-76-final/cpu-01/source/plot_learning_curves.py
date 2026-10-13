#!/usr/bin/env python3
"""Plot all 20000 logged iterations of the fourth low-climb-76 teacher; CPU Docker only."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import stat

TAGS = ('Train/mean_reward', 'Loss/Value', 'Loss/Surrogate', 'Loss/Entropy')
LABELS = ('Mean episode reward (logged)', 'Value loss (logged)',
          'Surrogate loss (logged)', 'Entropy term (logged)')


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('A regular source file without symlink components is required')
    return path


def fingerprint(path):
    path = regular(path)
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def trailing_mean(values, window):
    result = []
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i-window]
        result.append(total/min(i+1, window))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--window', type=int, default=25)
    args = parser.parse_args()
    if args.window < 1:
        raise ValueError('Moving-average window must be positive')
    source = fingerprint(args.input)
    script = fingerprint(__file__)
    payload = json.loads(args.input.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if (payload.get('status') != 'passed' or payload.get('phase') != 'scalars'
            or payload.get('stage') != 'teacher-low-climb-76' or payload.get('stage_complete') is not True
            or payload.get('samples_per_tag') != 20000 or payload.get('official_schedule_complete') is not False
            or payload.get('quality_verified') is not False):
        raise ValueError('The actual completed fourth-teacher scalars report is required')
    mapping = payload['scalars']
    if not isinstance(mapping, dict):
        raise ValueError('Expected a tag-to-scalar-list mapping')
    data = []
    for tag in TAGS:
        rows = mapping[tag]
        if not isinstance(rows, list) or not rows:
            raise ValueError('Missing actual samples: '+tag)
        steps, values = [], []
        for row in rows:
            step, value = row['step'], row['value']
            if type(step) is not int or step < 0 or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Invalid actual iteration/scalar: '+tag)
            if 'wall_time' in row and (not isinstance(row['wall_time'], (int, float)) or not math.isfinite(row['wall_time'])):
                raise ValueError('Nonfinite TensorBoard wall time: '+tag)
            steps.append(step); values.append(value)
        if len(steps) != 20000 or steps != list(range(20000)):
            raise ValueError('Every actual source iteration 0..19999 must be retained: '+tag)
        data.append((tag, steps, values))

    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('Output must not contain symlink components')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('A fresh empty output directory is required; retain previous evidence')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams['svg.hashsalt'] = source['sha256']
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.7))
    colors = ('#087f8c', '#e28b2d', '#4d728f', '#8a5c99')
    for axis, (tag, steps, values), ylabel, color in zip(axes.flat, data, LABELS, colors):
        axis.plot(steps, values, color=color, alpha=.28, linewidth=.7, label='Raw TensorBoard samples')
        axis.plot(steps, trailing_mean(values, args.window), color=color, linewidth=1.6,
                  label=f'Trailing mean: {args.window} samples')
        axis.set_title(tag, fontsize=12, loc='left')
        axis.set_xlabel('Actual training iteration')
        axis.set_ylabel(ylabel)
        axis.grid(alpha=.18)
        axis.legend(loc='best', fontsize=8, frameon=False)
    fig.suptitle('Official low-climb-76 teacher — fourth 20000-iteration stage completed', fontsize=18, y=.98)
    fig.text(.5, .933, 'FOURTH TEACHER COMPLETED  |  WHOLE SCHEDULE UNFINISHED  |  QUALITY NOT VERIFIED',
             ha='center', fontsize=10, color='#9d4b24')
    fig.text(.04, .018, f'All actual samples retained. Trailing window counts samples; early means use available samples. Source SHA256: {source["sha256"][:20]}…',
             fontsize=8, color='#555555')
    fig.tight_layout(rect=(0, .04, 1, .905))
    png, svg = output/'learning-curves.png', output/'learning-curves.svg'
    fig.savefig(png, dpi=160, metadata={'Description': 'Completed fourth low-climb-76 teacher; whole official schedule unfinished; quality not verified; source SHA256 '+source['sha256']})
    fig.savefig(svg, metadata={'Date': None, 'Description': 'Completed fourth low-climb-76 teacher; whole official schedule unfinished; quality not verified; source SHA256 '+source['sha256']})
    plt.close(fig)
    if fingerprint(args.input) != source or fingerprint(__file__) != script:
        raise ValueError('Input or plotting source changed during rendering')
    report = {'schema_version': 1, 'status': 'rendered_completed_fourth_teacher_curves',
              'rendered_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'training_status': 'completed_20000_iterations', 'stage_complete': True, 'official_schedule_complete': False,
              'quality_verified': False, 'convergence_verified': False,
              'scope': 'All 20000 iterations of the fourth official low-climb-76 teacher, from the actual full scalars report; whole official schedule unfinished; not rollout or parkour quality acceptance.',
              'input': source, 'plot_source': script, 'matplotlib': matplotlib.__version__,
              'backend': matplotlib.get_backend(),
              'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
              'nvidia_visible_devices': os.environ.get('NVIDIA_VISIBLE_DEVICES'),
              'smoothing': {'method': 'trailing arithmetic mean', 'window_samples': args.window,
                            'early_window': 'all available samples', 'raw_samples_plotted': True},
              'tags': [{'tag': tag, 'samples': len(steps), 'min_iteration': min(steps), 'max_iteration': max(steps),
                        'min_value': min(values), 'max_value': max(values)} for tag, steps, values in data],
              'figures': [fingerprint(png), fingerprint(svg)]}
    with (output/'plot-report.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    for path in output.iterdir():
        path.chmod(0o644)
    print(json.dumps({'status': report['status'], 'quality_verified': False,
                      'samples': {row['tag']: row['samples'] for row in report['tags']}}, allow_nan=False))


if __name__ == '__main__':
    main()
