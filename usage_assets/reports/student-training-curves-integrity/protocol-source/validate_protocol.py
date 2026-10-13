#!/usr/bin/env python3
"""CPU-only TFRecord protocol fixtures and one original teacher event; no student acceptance."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import types

EXTRACTOR_SHA = 'e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12'
REAL_EVENT_NAME = 'events.out.tfevents.1791793401.pro5000-6.135317.0'
REAL_EVENT_BYTES = 72561360
REAL_EVENT_SHA = 'ca8621a8c9919f27c3bfd0e397ba4d425f3eb5904ed0f797e5eed5b6b6cd0478'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
        and not any(p.is_symlink() for p in (path, *path.parents))
        and stat.S_ISREG(path.stat().st_mode), 'Regular normalized source without symlinks required')
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
    require(identity(before) == identity(after), 'Source changed during fingerprint')
    record = {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}
    return (record, b''.join(chunks)) if raw else record


def copy_runtime_source(path, directory):
    original, raw = fingerprint(path, True)
    target = directory / Path(path).name
    with target.open('xb') as stream:
        stream.write(raw)
    copied = fingerprint(target)
    require(copied['bytes'] == original['bytes'] and copied['sha256'] == original['sha256'], 'Runtime source copy differs')
    return {'original': original, 'retained': copied}


def record_bytes(writer_type, payloads):
    output = io.BytesIO()
    writer = writer_type(output)
    for payload in payloads:
        writer.write(payload)
    writer.flush()
    return output.getvalue()


def mutate(raw, index):
    changed = bytearray(raw)
    changed[index] ^= 1
    return bytes(changed)


def synthetic_cases(module, crc_module, writer_type, directory):
    payload = b'synthetic_protocol_fixture_payload'
    valid = record_bytes(writer_type, [payload])
    two = record_bytes(writer_type, [b'first', b'second', b''])
    oversized_header = struct.pack('<Q', module.MAX_EVENT_RECORD_BYTES + 1)
    oversized = oversized_header + struct.pack('<I', crc_module.masked_crc32c(oversized_header))
    remaining_header = struct.pack('<Q', 100)
    exceeds_file = remaining_header + struct.pack('<I', crc_module.masked_crc32c(remaining_header))
    specs = [
        ('valid_single_record', valid, None, None, 1, None),
        ('valid_multiple_including_empty_payload', two, None, None, 3, None),
        ('valid_multichunk_payload', record_bytes(writer_type, [b'x' * (1048576 + 17)]), None, None, 1, None),
        ('truncated_header_1_byte', valid[:1], 'truncated_length_header', 0, 0, None),
        ('truncated_header_7_bytes', valid[:7], 'truncated_length_header', 0, 0, None),
        ('truncated_length_crc', valid[:10], 'truncated_length_crc', 8, 0, None),
        ('truncated_body', valid[:12 + len(payload) - 1], 'truncated_payload', 12, 0, None),
        ('truncated_body_crc', valid[:-1], 'truncated_payload_crc', 12 + len(payload), 0, None),
        ('flipped_length_crc', mutate(valid, 8), 'length_crc_mismatch', 8, 0, None),
        ('flipped_body_crc', mutate(valid, len(valid) - 1), 'payload_crc_mismatch', 12 + len(payload), 0, None),
        ('flipped_body_byte', mutate(valid, 12), 'payload_crc_mismatch', 12 + len(payload), 0, None),
        ('valid_prefix_then_1_byte_bad_tail', valid + b'x', 'truncated_length_header', len(valid), 1, None),
        ('valid_prefix_then_7_byte_bad_tail', valid + b'x' * 7, 'truncated_length_header', len(valid), 1, None),
        ('valid_prefix_then_bad_record_length_crc', valid + mutate(valid, 8), 'length_crc_mismatch', len(valid) + 8, 1, None),
        ('valid_prefix_then_bad_record_body_crc', valid + mutate(valid, len(valid) - 1), 'payload_crc_mismatch', len(valid) + 12 + len(payload), 1, None),
        ('declared_length_above_64MiB', oversized, 'record_length_exceeds_bound', 0, 0, None),
        ('declared_length_exceeds_original_file', exceeds_file, 'record_length_exceeds_bound', 0, 0, None),
        ('whole_file_sha_mismatch', valid, 'event_changed_or_whole_file_identity_mismatch', len(valid), 1, {'sha256': '0' * 64}),
        ('whole_file_size_mismatch', valid, 'event_changed_or_whole_file_identity_mismatch', len(valid), 1, {'bytes': len(valid) + 1}),
        ('empty_file', b'', 'no_complete_tfrecords', 0, 0, None),
    ]
    outcomes = []
    for name, raw, problem, offset, records, change in specs:
        path = directory / (name + '.tfrecord')
        with path.open('xb') as stream:
            stream.write(raw)
        actual = fingerprint(path)
        supplied = actual | (change or {})
        result = module.verify_tfrecord(supplied, crc_module.crc_update)
        expected_status = 'failed' if problem else 'passed'
        if problem:
            matched = (result['status'] == 'failed' and result['records'] == records
                and result['crc32c_verified'] is False
                and any(row.get('problem') == problem and row.get('offset') == offset
                        for row in result['diagnostics']))
        else:
            matched = (result['status'] == 'passed' and result['records'] == records
                and result['complete_eof'] is True and result['crc32c_verified'] is True
                and result['bytes'] == actual['bytes'] and result['sha256'] == actual['sha256']
                and result['diagnostics'] == [])
        unchanged = fingerprint(path) == actual
        outcomes.append({'name': 'synthetic_protocol_fixture/' + name, 'scope': 'Synthetic raw TFRecord protocol only; payloads are not student scalars or native manifests',
            'fixture_file': actual, 'supplied_fingerprint': supplied, 'expected_status': expected_status,
            'expected_problem': problem, 'expected_offset': offset, 'expected_records': records,
            'outcome_matches_expected': bool(matched and unchanged), 'fixture_unchanged': unchanged, 'result': result})
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extractor', type=Path, required=True)
    parser.add_argument('--extractor-sha256', required=True)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--event-bytes', type=int, required=True)
    parser.add_argument('--event-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').is_file() and os.environ.get('CUDA_VISIBLE_DEVICES') == ''
        and os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'void'
        and not list(Path('/dev').glob('nvidia[0-9]*')), 'GPU-hidden CPU Docker required')
    require(args.extractor.is_relative_to('/code') and args.extractor_sha256 == EXTRACTOR_SHA,
        'Exact frozen v2 extractor mapped read-only to /code required')
    extractor, raw = fingerprint(args.extractor, True)
    require(extractor['sha256'] == args.extractor_sha256, 'Extractor original source SHA differs')
    require(args.event == Path('/artifacts') / REAL_EVENT_NAME and args.event_bytes == REAL_EVENT_BYTES
        and args.event_sha256 == REAL_EVENT_SHA and re.fullmatch('[0-9a-f]{64}', args.event_sha256), 'Exact root-provided original teacher event required')
    event = fingerprint(args.event)
    require(event['bytes'] == args.event_bytes and event['sha256'] == args.event_sha256, 'Original teacher event bytes/SHA differ')
    output = args.output
    require(output.is_absolute() and '..' not in output.parts and output.is_relative_to('/validation')
        and not any(path.is_symlink() for path in (output, *output.parents)) and not output.exists(), 'Fresh /validation report required')
    require(output.parent.is_dir() and not any(output.parent.iterdir()), 'Fresh empty validation mount required')
    source = fingerprint(Path(__file__).absolute())
    sys.dont_write_bytecode = True
    module = types.ModuleType('frozen_student_scalar_protocol_only')
    module.__file__ = extractor['path']
    exec(compile(raw, extractor['path'], 'exec'), module.__dict__)
    require(callable(module.verify_tfrecord) and module.MAX_EVENT_RECORD_BYTES == 67108864, 'Frozen strict protocol API differs')
    output.parent.mkdir(parents=True, exist_ok=True)
    runtime_sources = output.parent / 'runtime-sources'; runtime_sources.mkdir(exist_ok=False)
    fixtures = output.parent / 'synthetic_protocol_fixture'; fixtures.mkdir(exist_ok=False)
    report = {'schema_version': 1, 'phase': 'tfrecord_protocol_validation', 'status': 'running',
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'harness_source': source,
        'extractor_source': extractor, 'original_teacher_event': event,
        'scope': 'One CPU protocol phase: synthetic framing/CRC failure fixtures plus one genuine existing completed teacher event. No protobuf/scalar extraction, model loading or student completion evidence.',
        'quality_verified': False, 'convergence_verified': False, 'student_training_scalars_verified': False,
        'student_training_completed': False, 'official_schedule_complete': False,
        'input_sources_unchanged': False, 'input_sources_before': [source, extractor, event],
        'input_sources_after': None, 'known_vectors': [], 'synthetic_protocol_fixture_cases': [],
        'real_teacher_event': None, 'runtime_sources': []}
    failure = None
    try:
        from tensorboard.compat.tensorflow_stub import pywrap_tensorflow
        from tensorboard.summary.writer import record_writer
        for native_source in (pywrap_tensorflow.__file__, record_writer.__file__):
            report['runtime_sources'].append(copy_runtime_source(Path(native_source).absolute(), runtime_sources))
        report['input_sources_before'] += [row['original'] for row in report['runtime_sources']]
        whole = pywrap_tensorflow.crc_update(0, b'123456789')
        incremental = pywrap_tensorflow.crc_update(pywrap_tensorflow.crc_update(0, b'1234'), b'56789')
        masked_empty = pywrap_tensorflow.masked_crc32c(b'')
        report['known_vectors'] = [
            {'name': 'CRC32C_123456789', 'expected': 0xe3069283, 'actual': whole, 'matched': whole == 0xe3069283},
            {'name': 'CRC32C_incremental_1234_56789', 'expected': 0xe3069283, 'actual': incremental, 'matched': incremental == 0xe3069283},
            {'name': 'masked_CRC32C_empty', 'expected': 0xa282ead8, 'actual': masked_empty, 'matched': masked_empty == 0xa282ead8}]
        report['synthetic_protocol_fixture_cases'] = synthetic_cases(module, pywrap_tensorflow, record_writer.RecordWriter, fixtures)
        real = module.verify_tfrecord(event, pywrap_tensorflow.crc_update)
        report['real_teacher_event'] = {'scope': 'Original teacher-high-climb-76 complete event framing/CRC/whole-file only; no student/core-loss claims', 'input': event, 'result': real}
        require(all(row['matched'] for row in report['known_vectors']), 'CRC32C known-vector mismatch')
        require(all(row['outcome_matches_expected'] for row in report['synthetic_protocol_fixture_cases']), 'Synthetic protocol fixture mismatch; original outcomes retained')
        require(real['status'] == 'passed' and real['complete_eof'] is True and real['crc32c_verified'] is True
            and real['bytes'] == event['bytes'] and real['sha256'] == event['sha256'] and real['records'] > 0
            and real['diagnostics'] == [], 'Original teacher event protocol check failed')
        report['input_sources_after'] = [fingerprint(original['path']) for original in report['input_sources_before']]
        require(report['input_sources_after'] == report['input_sources_before'], 'Source or original input changed during protocol validation')
        for row in report['runtime_sources']:
            require(fingerprint(row['retained']['path']) == row['retained'], 'Retained installed package source changed')
        report.update(status='passed_protocol_validation', input_sources_unchanged=True)
    except Exception as error:
        failure = error
        report.update(status='failed_protocol_validation', error=type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with output.open('x') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    if failure is not None:
        raise SystemExit(1)
    print(json.dumps({'status': report['status'], 'phase': report['phase'],
        'synthetic_protocol_fixture_cases': len(report['synthetic_protocol_fixture_cases']),
        'real_teacher_event_records': report['real_teacher_event']['result']['records']}))


if __name__ == '__main__':
    main()
