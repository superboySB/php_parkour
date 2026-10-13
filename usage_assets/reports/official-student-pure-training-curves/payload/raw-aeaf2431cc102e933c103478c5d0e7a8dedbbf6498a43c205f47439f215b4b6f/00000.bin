#!/usr/bin/env python3
"""Run the two reviewed student-scalar phases inside an isolated CPU container."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

CODE = Path('/code')
CONTROL = Path('/control/input-contract.json')
OUTPUT = Path('/validation')
PYTHON = '/opt/php/bin/train-python'
SOURCES = {
    'extract': (CODE / 'extract_student_scalars.py', 'e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12'),
    'plot': (CODE / 'plot_student_learning_curves.py', '6a14cfa86df96199e575384c48466d44046b1a2fad8ce76c1427b7d5add7abd0'),
}
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


def safe_path(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute normalized path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path component: ' + str(path))
    return path


def signature(path):
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def fingerprint(path, raw=False):
    path = safe_path(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Regular file required: ' + str(path))
    before = signature(path)
    digest, chunks = hashlib.sha256(), []
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            digest.update(chunk)
            if raw:
                chunks.append(chunk)
    require(signature(path) == before, 'File changed while hashing: ' + str(path))
    pin = {'path': str(path), 'bytes': before[2], 'sha256': digest.hexdigest()}
    return (pin, b''.join(chunks)) if raw else pin


def body(record):
    require(isinstance(record, dict) and {'path', 'bytes', 'sha256'} <= record.keys(), 'File fingerprint required')
    require(isinstance(record['path'], str) and type(record['bytes']) is int and record['bytes'] > 0
        and isinstance(record['sha256'], str) and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'Invalid input fingerprint')
    return {key: record[key] for key in ('path', 'bytes', 'sha256')}


def cpu_only():
    require(Path('/.dockerenv').is_file() and os.environ.get('CUDA_VISIBLE_DEVICES') == ''
        and os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'void', 'GPU-hidden Docker required')
    require(not list(Path('/dev').glob('nvidia*')) and not list(Path('/dev').glob('dri/renderD*')),
        'CPU container exposes accelerator devices')
    mounts = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split(' - ', 1)[0].split()
        path = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), fields[4])
        mounts.append((Path(path), fields[5].split(',')))
    expected = {'/code': 'ro', '/control': 'ro', '/artifacts': 'ro', '/validation': 'rw'}
    for target, mode in expected.items():
        root = safe_path(target)
        require(root.is_dir(), 'Required mount directory missing: ' + target)
        exact = [options for path, options in mounts if path == root]
        require(len(exact) == 1 and mode in exact[0]
            and ('rw' if mode == 'ro' else 'ro') not in exact[0], 'Mount access differs: ' + target)
        require(not any(path != root and path.is_relative_to(root) for path, _ in mounts),
            'Unexpected nested mount: ' + target)
    return expected


def sources():
    own = safe_path(Path(__file__).absolute())
    require(own == CODE / 'run_phases.py', 'Execute the fixed /code/run_phases.py')
    records = [fingerprint(own)]
    for path, sha in SOURCES.values():
        pin, raw = fingerprint(path, True)
        require(pin['sha256'] == sha and len(raw) == pin['bytes']
            and hashlib.sha256(raw).hexdigest() == sha, 'Reviewed source bytes differ: ' + str(path))
        records.append(pin)
    return records


def collect_inputs(expected_sha):
    pin, raw = fingerprint(CONTROL, True)
    require(re.fullmatch('[0-9a-f]{64}', expected_sha) and pin['sha256'] == expected_sha,
        'Explicit actual input contract SHA differs')
    contract = strict_json(raw)
    require(type(contract.get('schema_version')) is int and contract['schema_version'] == 1
        and contract.get('kind') in ('pure', 'finetune'), 'Actual pure/finetune input contract required')
    require(isinstance(contract.get('native_manifest'), dict)
        and isinstance(contract.get('events'), list) and contract['events'], 'Native manifest and events required')
    records = {pin['path']: pin}

    def add(record):
        record = body(record)
        path = safe_path(record['path'])
        require(path.is_relative_to('/control') or path.is_relative_to('/artifacts'),
            'Contract file lies outside the read-only input mounts: ' + str(path))
        require(fingerprint(path) == record, 'Actual input bytes differ: ' + str(path))
        require(str(path) not in records or records[str(path)] == record, 'Conflicting repeated fingerprint')
        records[str(path)] = record

    add(contract['native_manifest'])
    for event in contract['events']:
        add(event)

    def visit(value):
        if isinstance(value, dict):
            if {'path', 'bytes', 'sha256'} <= value.keys():
                add(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(contract)  # Includes any saved-config fingerprint carried by the real contract.
    require(len(records) >= 3, 'Nonempty complete native/event input inventory required')
    return contract, list(records.values())


def run_phase(name, argv, report):
    stdout, stderr = OUTPUT / (name + '.stdout'), OUTPUT / (name + '.stderr')
    row = {'phase': name, 'argv': argv, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'actual_wait_returncode': None}
    report['phases'].append(row)
    try:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            completed = subprocess.run(argv, stdout=out, stderr=err, check=False)
            row['actual_wait_returncode'] = completed.returncode
    finally:
        row['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if stdout.exists():
            row['stdout'] = fingerprint(stdout)
        if stderr.exists():
            row['stderr'] = fingerprint(stderr)
    require(type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0,
        'Actual ' + name + ' subprocess failed; original logs retained')


def retain_crc_source(scalars, report):
    require(scalars.get('status') == 'passed' and scalars.get('event_integrity_complete') is True
        and scalars.get('training_scalar_integrity_complete') is True, 'Actual successful extractor report required')
    original = body(scalars['event_integrity_checker']['crc_update_source'])
    path = safe_path(original['path'])
    require(str(path).endswith('/tensorboard/compat/tensorflow_stub/pywrap_tensorflow.py'),
        'Unexpected installed CRC source path')
    before, raw = fingerprint(path, True)
    require(before == original and hashlib.sha256(raw).hexdigest() == original['sha256']
        and len(raw) == original['bytes'], 'Actual CRC module bytes differ from extractor')
    target = OUTPUT / 'runtime-sources' / 'pywrap_tensorflow.py'
    target.parent.mkdir()
    with target.open('xb') as stream:
        stream.write(raw)
    retained = fingerprint(target)
    require(retained['bytes'] == original['bytes'] and retained['sha256'] == original['sha256']
        and fingerprint(path) == before, 'CRC source copy or original changed')
    report['runtime_source_copies'].append({'original': original, 'retained': retained})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract-sha256', required=True)
    args = parser.parse_args()
    mount_contract = cpu_only()
    require(not any(OUTPUT.iterdir()), 'Fresh empty /validation required; prior output is never reused')
    report = {'schema_version': 1, 'status': 'running',
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'phases': [],
        'inputs_before': [], 'inputs_after': [], 'inputs_unchanged': False,
        'source_before': [], 'source_after': [], 'sources_unchanged': False,
        'runtime_source_copies': [], 'mount_access': mount_contract, 'errors': [],
        'scope': 'Two actual CPU scalar extraction and plotting subprocesses only; no training, PT parsing or rollout.',
        **FALSE_FLAGS}
    failed = False
    try:
        report['source_before'] = sources()
        contract, report['inputs_before'] = collect_inputs(args.contract_sha256)
        report['kind'] = contract['kind']
        extract_argv = [PYTHON, '-B', str(SOURCES['extract'][0]), '--contract', str(CONTROL),
            '--contract-sha256', args.contract_sha256, '--output', str(OUTPUT / 'scalars.json')]
        run_phase('extract', extract_argv, report)
        scalar_fp, raw = fingerprint(OUTPUT / 'scalars.json', True)
        scalars = strict_json(raw)
        require(scalars['extractor_source'] == report['source_before'][1]
            and scalars['input_contract'] == report['inputs_before'][0]
            and scalars['kind'] == contract['kind'], 'Actual extractor source/input/kind differs')
        retain_crc_source(scalars, report)
        require(sources() == report['source_before'], 'Sources changed before plot')
        plot_argv = [PYTHON, '-B', str(SOURCES['plot'][0]), '--input', scalar_fp['path'],
            '--input-sha256', scalar_fp['sha256'], '--output', str(OUTPUT / 'plots')]
        run_phase('plot', plot_argv, report)
        plot_fp, raw = fingerprint(OUTPUT / 'plots' / 'plot-report.json', True)
        plotted = strict_json(raw)
        require(plotted.get('status') == 'rendered_student_training_curves'
            and plotted.get('input_files_unchanged') is True
            and plotted.get('plot_source') == report['source_before'][2]
            and plotted.get('input') == scalar_fp and plotted.get('kind') == contract['kind']
            and all(plotted.get(key) is False for key in FALSE_FLAGS), 'Actual plot source/input/report differs')
        require(isinstance(plotted.get('figures'), list) and len(plotted['figures']) == 2,
            'Both original plot figures required')
        for figure in plotted['figures']:
            require(Path(figure['path']).parent == OUTPUT / 'plots'
                and fingerprint(figure['path']) == body(figure), 'Original plot figure bytes differ')
        require(fingerprint(OUTPUT / 'scalars.json') == scalar_fp, 'Extractor report changed during plot')
        report['outputs'] = [scalar_fp, plot_fp, *[body(figure) for figure in plotted['figures']]]
    except Exception as error:
        failed = True
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        try:
            report['inputs_after'] = [fingerprint(row['path']) for row in report['inputs_before']]
            report['inputs_unchanged'] = bool(report['inputs_before']) and report['inputs_after'] == report['inputs_before']
            report['source_after'] = sources()
            report['sources_unchanged'] = bool(report['source_before']) and report['source_after'] == report['source_before']
            require(report['inputs_unchanged'] and report['sources_unchanged'], 'Source/input before-after comparison failed')
            require([row['phase'] for row in report['phases']] == ['extract', 'plot']
                and all(type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0
                    for row in report['phases']), 'Both ordered actual phases must exit zero')
        except Exception as error:
            failed = True
            report['errors'].append(type(error).__name__ + ': ' + str(error))
        report['status'] = 'failed' if failed else 'passed'
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with (OUTPUT / 'phases.json').open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
    print(json.dumps({'status': report['status'], 'kind': report.get('kind'),
        'actual_phase_waits': [row['actual_wait_returncode'] for row in report['phases']]}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
