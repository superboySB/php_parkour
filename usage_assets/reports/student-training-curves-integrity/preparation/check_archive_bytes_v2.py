#!/usr/bin/env python3
"""Exercise reviewed byte archive primitives with explicitly synthetic fixtures."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import types

SOURCE_SHA = '068c13d5e8e61a7e7a4b80b2813a96ac617efee408674e9fe1f65a498b50dcc2'

def fp(path):
    path = Path(path).absolute()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8388608), b''):
            digest.update(data)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source = args.source.absolute(); bound = fp(source)
    assert bound['sha256'] == SOURCE_SHA, 'Exact reviewed publication-v2 source required'
    output = args.output.absolute()
    assert not output.exists() and '..' not in output.parts
    assert not any(x.is_symlink() for x in (source, *source.parents, output, *output.parents))
    output.mkdir(parents=True)
    module = types.ModuleType('synthetic_archive_protocol_only'); module.__file__ = str(source)
    raw_source = source.read_bytes()
    assert len(raw_source) == bound['bytes'] and hashlib.sha256(raw_source).hexdigest() == SOURCE_SHA
    exec(compile(raw_source, str(source), 'exec'), module.__dict__)
    assert module.LIMIT == 25000000
    package = output / 'synthetic_archive_fixture'; package.mkdir()
    originals = output / 'originals'; originals.mkdir()
    restored = output / 'restored'; restored.mkdir()
    report = {'status': 'running', 'scope': 'Synthetic byte archive protocol only. No student acceptance contract, native manifest, scalar data, publish/verify/restore CLI or scientific execution.',
        'source': bound, 'positives': [], 'negatives': [], 'student_training_completed': False,
        'student_training_scalars_verified': False, 'official_schedule_complete': False,
        'quality_verified': False, 'convergence_verified': False}
    failure = None
    try:
        rng = random.Random(42)
        fixtures = [('empty', b'', False), ('small_raw', b'clearly synthetic archive fixture\n', False),
            ('exact_raw_limit', b'r' * module.LIMIT, False),
            ('event_gzip', b'clearly synthetic event-byte fixture\n', True),
            ('large_incompressible', rng.randbytes(module.LIMIT + 1024), False),
            ('large_compressible', b'c' * (module.LIMIT + 1024), False)]
        shared, accepted = {}, {}
        for name, raw, event in fixtures:
            original = originals / name; original.write_bytes(raw); original.chmod(0o640)
            original_fp = fp(original)
            record = module.archive_record(package, name, original_fp, event, shared)
            target = restored / name
            with target.open('xb') as stream:
                module.decode_record(package, record, stream)
            target.chmod(record['mode'])
            result = fp(target)
            assert result['bytes'] == original_fp['bytes'] and result['sha256'] == original_fp['sha256']
            assert (target.stat().st_mode & 0o777) == 0o640 and fp(original) == original_fp
            if name == 'large_incompressible':
                assert len(record['chunks']) > 1 and record['encoded']['bytes'] > module.LIMIT
            if name == 'exact_raw_limit':
                assert record['encoding'] == 'raw' and len(record['chunks']) == 1
            assert all(x['bytes'] <= module.LIMIT for x in record['chunks'])
            accepted[name] = record
            report['positives'].append({'name': 'synthetic_archive_fixture/' + name, 'original': original_fp,
                'restored': result, 'record': record, 'mode': record['mode'], 'matched': True})
        def negative(name, record, provider=package):
            try:
                module.decode_record(provider, record)
            except (ValueError, OSError) as error:
                report['negatives'].append({'name': 'synthetic_archive_fixture/' + name,
                    'rejected_as_expected': True, 'error': type(error).__name__ + ': ' + str(error)})
            else:
                raise AssertionError('Invalid synthetic archive was accepted: ' + name)
        changed = copy.deepcopy(accepted['large_incompressible']); changed['chunks'][1]['offset'] += 1
        negative('noncontinuous_offset', changed)
        changed = copy.deepcopy(accepted['large_incompressible']); changed['chunks'].pop()
        negative('missing_final_chunk', changed)
        changed = copy.deepcopy(accepted['large_incompressible']); changed['sha256'] = '0' * 64
        negative('decoded_whole_sha_mismatch', changed)
        changed = copy.deepcopy(accepted['large_incompressible']); changed['encoded']['sha256'] = '0' * 64
        negative('encoded_whole_sha_mismatch', changed)
        # Corruption uses a separate owned fixture copy; accepted chunks stay intact.
        corrupt = output / 'corrupt_fixture'; shutil.copytree(package, corrupt)
        changed = copy.deepcopy(accepted['large_incompressible'])
        first = corrupt / changed['chunks'][0]['path']
        with first.open('r+b') as stream:
            value = stream.read(1); stream.seek(0); stream.write(bytes([value[0] ^ 1]))
        negative('chunk_byte_corruption', changed, corrupt)
        for name, edit in [('truncated_gzip', lambda data: data[:-1]),
                           ('trailing_gzip', lambda data: data + b'x')]:
            provider = output / name; provider.mkdir()
            changed = copy.deepcopy(accepted['event_gzip'])
            first = package / changed['chunks'][0]['path']
            target = provider / changed['chunks'][0]['path']; target.parent.mkdir(parents=True)
            target.write_bytes(edit(first.read_bytes()))
            actual = fp(target)
            changed['chunks'][0].update(bytes=actual['bytes'], sha256=actual['sha256'])
            changed['encoded'] = {key: actual[key] for key in ('bytes', 'sha256')}
            negative(name, changed, provider)
        for row in report['positives']:
            assert fp(row['original']['path']) == row['original']
            module.decode_record(package, row['record'])
        assert fp(source) == bound
        report.update(status='passed_synthetic_byte_archive_protocol', source_after=fp(source),
            original_fixtures_unchanged=True, positive_count=len(report['positives']), negative_count=len(report['negatives']))
    except Exception as error:
        failure = error
        report.update(status='failed_synthetic_byte_archive_protocol', error=type(error).__name__ + ': ' + str(error))
    with (output / 'protocol.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'status': report['status'], 'positives': len(report['positives']), 'negatives': len(report['negatives'])}))
    return 1 if failure else 0

if __name__ == '__main__':
    raise SystemExit(main())
