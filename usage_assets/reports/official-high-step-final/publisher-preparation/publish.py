#!/usr/bin/env python3
"""Archive already completed evidence; this program runs no scientific phase."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'release-assets.json').is_file() and (parent / 'scripts/research').is_dir())
BASE = ROOT / 'usage_assets/reports/official-high-step-final'
PREPARATION = ROOT / 'outputs/research/official-full/teacher-high-step-final-publication-preparation-01'
SOURCE = ROOT / 'outputs/research/official-full'
LIMIT = 25_000_000
CONTRACT_SHA256 = '00694ca7dcb3c6198bbac166a6adaefc772f0d48d15e8c189ae5028e2d8ded3f'
Q = SOURCE / 'verified-cloud-waits/20261011T171218931711Z'
TRANSITION = SOURCE / 'bounded-verified-wait-20261011T170036Z/root-terminal-transition-verification.json'


def fp(path):
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_file():
        raise ValueError('Regular nonsymlink file required: ' + str(path))
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha.update(data)
    return {'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    if BASE.exists() or BASE.is_symlink():
        raise ValueError('Use the fresh dedicated high-step publication; preserve all previous evidence')
    plan = json.loads((PREPARATION / 'publication-plan.json').read_bytes())
    binding = plan['reviewed_cpu_postexecution_binding']
    if not binding or binding['status'] != 'root_and_independent_reviewed_actual_high_step_cpu':
        raise ValueError('Bind actual high-step CPU terminal reports and obtain new review before publication')
    for row in plan['actual_input_fingerprints'] + binding['files']:
        if fp(Path(row['path'])) != {key: row[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Pinned actual high-step input changed: ' + row['path'])
    cohort = SOURCE / 'teacher-high-step-final-cpu-01'
    required_reports = {str(cohort / name) for name in ('independent-postexecution-review.json', 'validation/phases.json', 'host/execution.json')}
    if {row['path'] for row in binding['files']} != required_reports:
        raise ValueError('Bind exactly the actual independent review, five-phase receipt and CPU execution receipt')
    if fp(cohort / 'contract.json')['sha256'] != CONTRACT_SHA256:
        raise ValueError('Generated actual high-step CPU contract differs')
    transfer = SOURCE / 'teacher-high-step-final-01'
    terminal = json.loads((transfer / 'inventory-before.stdout.raw').read_bytes())
    after = json.loads((transfer / 'inventory-after.stdout.raw').read_bytes())
    transferred = json.loads((transfer / 'receipt.json').read_bytes())
    native = json.loads((transfer / 'teacher-high-step.json').read_bytes())
    if (native['status'] != 'passed' or type(native['returncode']) is not int or native['returncode'] != 0
            or type(native['checkpoint_iteration']) is not int or native['checkpoint_iteration'] != 19999
            or native['environment']['REGISTRY'] != 'file:///data/assets/motions-high-step'
            or not native['checkpoint'].startswith('/outputs/official-full/official/teacher-high-step/')
            or Path(native['checkpoint']).name != 'model_19999.pt'
            or terminal['status'] != 'passed' or after['status'] != 'passed'
            or terminal['artifacts'] != after['artifacts']
            or transferred['status'] != 'completed' or not transferred['remote_source_unchanged']
            or not transferred['source_helpers_unchanged'] or transferred['verified_artifact_count'] != 5):
        raise ValueError('Require actual high-step passed0/19999 and stable completed five-artifact transfer')
    events = terminal['event_file_names']
    if len(events) != 1 or Path(events[0]).name != events[0]:
        raise ValueError('Require the single actual high-step TensorBoard event')
    EVENT = events[0]
    expected_names = {'model_00000.pt', 'model_19999.pt', 'model_19999.onnx', 'holosoma_config.yaml', EVENT}
    artifact_rows = plan['actual_artifacts']
    if ({Path(row['path']).name for row in artifact_rows} != expected_names or len(artifact_rows) != 5
            or {path.name for path in (transfer / 'artifacts').iterdir()} != expected_names):
        raise ValueError('Exact actual high-step artifact set differs')
    for row in artifact_rows:
        if Path(row['path']).parent != transfer / 'artifacts' or fp(Path(row['path'])) != {key: row[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Actual high-step artifact body changed')
    if next(row['sha256'] for row in artifact_rows if Path(row['path']).name == 'model_19999.pt') != native['checkpoint_sha256']:
        raise ValueError('Native high-step final checkpoint SHA differs')
    review = json.loads((cohort / 'independent-postexecution-review.json').read_bytes())
    phases = json.loads((cohort / 'validation/phases.json').read_bytes())
    execution = json.loads((cohort / 'host/execution.json').read_bytes())
    if (review['status'] != 'passed_readonly_postexecution_review' or review['must_fix']
            or phases['status'] != 'passed' or [row['actual_wait_returncode'] for row in phases['phases']] != [0] * 5
            or any(type(row['actual_wait_returncode']) is not int for row in phases['phases'])
            or execution['actual_start_attached_wait_returncode'] != 0 or execution['actual_container_exit_code'] != 0
            or execution['container_running'] or not execution['source_unchanged']):
        raise ValueError('Require the actual high-step CPU terminal evidence')
    for row in review['evidence_fingerprints']:
        if fp(Path(row['path'])) != {key: row[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Actual reviewed report changed: ' + row['path'])
    preparation = json.loads((PREPARATION / 'preparation-manifest.json').read_bytes())
    expected_files = plan['actual_input_fingerprints'] + binding['files'] + artifact_rows + review['evidence_fingerprints']
    expected_files += [{'path': str(PREPARATION / row['path']), 'bytes': row['bytes'], 'sha256': row['sha256']}
                       for row in preparation['files']]
    pinned = {}
    for row in expected_files:
        path = Path(row['path'])
        expected = {key: row[key] for key in ('bytes', 'sha256')}
        if path in pinned and pinned[path] != expected:
            raise ValueError('Conflicting original fingerprints: ' + str(path))
        if fp(path) != expected:
            raise ValueError('Reviewed source/input differs before publication: ' + str(path))
        pinned[path] = expected
    BASE.mkdir(exist_ok=False)
    mapping = []
    def copy(source, relative):
        target = BASE / relative
        expected = pinned.get(source, fp(source))
        if fp(source) != expected:
            raise ValueError('Reviewed copy source changed: ' + str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as old, target.open('xb') as new:
            shutil.copyfileobj(old, new, length=8 * 1024 * 1024)
        if fp(target) != expected or fp(source) != expected:
            raise ValueError('Copy changed original evidence: ' + str(source))
        mapping.append({'source': str(source), 'published': relative, **expected, 'encoding': 'original_bytes'})
    def tree(source, relative, exclude=()):
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Source symlink rejected: ' + str(path))
            if path.is_file() and path.name not in exclude:
                copy(path, str(Path(relative) / path.relative_to(source)))
    cohort = SOURCE / 'teacher-high-step-final-cpu-01'
    for kind in ('source', 'source-original', 'diffs', 'host', 'validation', 'input'):
        tree(cohort / kind, 'cpu-01/' + kind)
    for path in sorted(cohort.iterdir()):
        if path.is_file():
            copy(path, 'cpu-01/' + path.name)
    transfer = SOURCE / 'teacher-high-step-final-01'
    excluded = ('model_19999.pt', 'model_19999.onnx', 'holosoma_config.yaml', EVENT, 'model_00000.pt')
    tree(transfer, 'transfer', excluded)
    for name in ('model_19999.pt', 'holosoma_config.yaml'):
        copy(transfer / 'artifacts' / name, 'artifacts/' + name)
    if fp(transfer / 'artifacts/model_00000.pt') != fp(BASE / 'cpu-01/input/model_00000.pt'):
        raise ValueError('Same-run baseline copy differs')
    mapping.append({'source': str(transfer / 'artifacts/model_00000.pt'),
                    'published': 'cpu-01/input/model_00000.pt',
                    **fp(BASE / 'cpu-01/input/model_00000.pt'), 'encoding': 'original_bytes_shared_identical_copy'})
    tree(Q, 'terminal-observation')
    copy(TRANSITION, 'terminal-observation/root-terminal-transition-verification.json')
    tree(PREPARATION, 'publisher-preparation')
    copy(PREPARATION / 'replay.py', 'replay.py')
    copy(PREPARATION / 'index.md', 'index.md')
    original = transfer / 'artifacts' / EVENT
    expected = fp(original)
    event_dir = BASE / 'tensorboard'
    event_dir.mkdir(exist_ok=False)
    compressed = event_dir / (EVENT + '.gz')
    with original.open('rb') as old, compressed.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=9, mtime=0) as stream:
            shutil.copyfileobj(old, stream, length=8 * 1024 * 1024)
    compressed_expected = fp(compressed)
    chunks = []
    if compressed_expected['bytes'] <= LIMIT:
        chunks.append({'path': str(compressed.relative_to(BASE)), 'offset': 0, **compressed_expected})
    else:
        with compressed.open('rb') as stream:
            offset, number = 0, 0
            while data := stream.read(LIMIT):
                path = compressed.with_name(compressed.name + f'.part-{number:03d}')
                with path.open('xb') as output:
                    output.write(data)
                chunks.append({'path': str(path.relative_to(BASE)), 'offset': offset, **fp(path)})
                offset += len(data)
                number += 1
        compressed.unlink()
    # Actual sequential decompression verifies every original event byte, without
    # retaining a >25 MB uncompressed file inside this Git publication.
    import zlib
    decoder = zlib.decompressobj(wbits=31)
    restored_sha, compressed_sha = hashlib.sha256(), hashlib.sha256()
    restored_bytes, compressed_bytes = 0, 0
    for chunk in chunks:
        path = BASE / chunk['path']
        if fp(path) != {key: chunk[key] for key in ('bytes', 'sha256')} or chunk['offset'] != compressed_bytes:
            raise ValueError('Compressed event chunk identity differs')
        with path.open('rb') as stream:
            for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                compressed_sha.update(data)
                compressed_bytes += len(data)
                output = decoder.decompress(data)
                restored_sha.update(output)
                restored_bytes += len(output)
    output = decoder.flush()
    restored_sha.update(output)
    restored_bytes += len(output)
    restored = {'bytes': restored_bytes, 'sha256': restored_sha.hexdigest()}
    if (not decoder.eof or decoder.unused_data or restored != expected or fp(original) != expected
            or compressed_bytes != compressed_expected['bytes'] or compressed_sha.hexdigest() != compressed_expected['sha256']):
        raise ValueError('Lossless event restoration failed')
    event_manifest = {'schema_version': 1, 'encoding': 'gzip', 'gzip_mtime': 0, 'gzip_original_filename': '',
                      'source': str(original), 'restore_name': EVENT, 'original': expected,
                      'compressed': compressed_expected, 'chunks': chunks,
                      'actual_streaming_restoration': {'status': 'passed', **restored},
                      'note': 'Concatenate chunks by offset then gunzip; streaming verification consumed all original bytes.'}
    save(event_dir / 'event-archive.json', event_manifest)
    mapping.append({'source': str(original), 'published': 'tensorboard/event-archive.json',
                    **expected, 'encoding': 'lossless_gzip_chunk_contract'})
    onnx = transfer / 'artifacts/model_19999.onnx'
    terminal = json.loads((BASE / 'transfer/inventory-before.stdout.raw').read_bytes())
    onnx_record = next(row for row in terminal['artifacts'] if row['path'].endswith('.onnx'))
    if fp(onnx) != {key: onnx_record[key] for key in ('bytes', 'sha256')}:
        raise ValueError('External ONNX differs from original terminal observation')
    save(BASE / 'external-onnx.json', {'schema_version': 1, 'included_in_git': False,
        'local_original': str(onnx), 'remote_original': onnx_record['path'],
        'bytes': onnx_record['bytes'], 'sha256': onnx_record['sha256'],
        'reason': 'The exact self-contained high-step final ONNX remains an external replay prerequisite.',
        'download': {'ssh_alias': 'tencent-231', 'port': 22, 'remote_path': onnx_record['path'],
                     'argv_template': ['rsync', '-av', '--partial', '-e', 'ssh -p 22 -o BatchMode=yes -o PasswordAuthentication=no',
                                       'tencent-231:' + onnx_record['path'], '<fresh-local-onnx-path>']}})
    save(BASE / 'path-map.json', {'schema_version': 1, 'raw_json_rewritten': False, 'records': mapping,
         'docker_namespace': {'/code': 'cpu-01/source', '/control': 'cpu-01/input',
                              '/artifacts': 'Fresh replay directory with restored event, PT/config and verified external ONNX',
                              '/validation': 'Fresh replay output directory'},
         'excluded_external_artifact': 'external-onnx.json'})
    for path, expected in pinned.items():
        if fp(path) != expected:
            raise ValueError('Actual high-step input changed while archiving: ' + str(path))
    oversized = [str(path.relative_to(BASE)) for path in BASE.rglob('*') if path.is_file() and path.stat().st_size > LIMIT]
    if oversized:
        raise ValueError('Publication file exceeds 25 MB: ' + repr(oversized))
    files = [{'path': str(path.relative_to(BASE)), **fp(path)} for path in sorted(BASE.rglob('*')) if path.is_file()]
    save(BASE / 'evidence-manifest.json', {'schema_version': 1, 'files': files,
        'raw_json_rewritten': False, 'quality_verified': False, 'official_schedule_complete': False})
    print(json.dumps({'status': 'raw_archive_populated', 'original_copies': len(mapping),
                      'event_compressed': compressed_expected, 'event_chunks': len(chunks),
                      'actual_restored': restored, 'science_executed': False}))


if __name__ == '__main__':
    main()
