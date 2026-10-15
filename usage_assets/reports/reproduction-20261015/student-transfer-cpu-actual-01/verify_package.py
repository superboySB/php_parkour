#!/usr/bin/env python3
"""Verify an externally pinned package, optionally restore four ONNX files.

Only Python's standard library is required. Verification completes before a
restore directory is created. This checks retained bytes, not physical skills.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_alias(path):
    path = Path(os.path.abspath(path))
    for p in (path, *path.parents):
        require(not p.is_symlink(), 'Symlink path: ' + str(p))
    return path


def relative(value):
    p = PurePosixPath(value)
    require(isinstance(value, str) and value and not p.is_absolute()
            and all(x not in ('', '.', '..') for x in value.split('/'))
            and '\\' not in value, 'Unsafe relative path')
    return p


def verify(package, expected):
    package = no_alias(package)
    require(package.is_dir(), 'Package is not a directory')
    seal = package / 'manifest.json'
    require(seal.is_file() and not seal.is_symlink(), 'Missing manifest')
    raw = seal.read_bytes()
    require(digest(raw) == expected, 'External manifest SHA mismatch')
    doc = json.loads(raw)
    require(doc.get('schema') == 'student_transfer_retained_bytes_v1', 'Unknown schema')
    entries = doc['files']
    expected_files = set()
    expected_dirs = set()
    for entry in entries:
        p = relative(entry['path'])
        require(str(p) != 'manifest.json' and str(p) not in expected_files,
                'Duplicate/recursive manifest path')
        expected_files.add(str(p))
        expected_dirs.update(str(q) for q in p.parents if str(q) != '.')
        f = no_alias(package / str(p))
        require(f.is_file(), 'Missing file: ' + str(p))
        data = f.read_bytes()
        require(len(data) == entry['bytes'] and digest(data) == entry['sha256'],
                'Retained file bytes/SHA mismatch: ' + str(p))
        require(stat.S_IMODE(f.stat().st_mode) == entry['mode'], 'File mode changed: ' + str(p))
    actual_files = set()
    actual_dirs = set()
    for p in package.rglob('*'):
        require(not p.is_symlink(), 'Symlink in package')
        rel = p.relative_to(package).as_posix()
        if p.is_dir():
            actual_dirs.add(rel)
        else:
            require(p.is_file(), 'Nonregular package entry')
            actual_files.add(rel)
    require(actual_files == expected_files | {'manifest.json'}, 'Package file-set changed')
    require(actual_dirs == expected_dirs, 'Package directory-set changed')
    decoded = []
    targets = set()
    for model in doc.get('models', []):
        target = str(relative(model['target']))
        require(target not in targets, 'Duplicate restore target')
        targets.add(target)
        compressed = str(relative(model['gzip_path']))
        require(compressed in expected_files, 'Model is outside sealed package')
        with gzip.open(package / compressed, 'rb') as stream:
            data = stream.read(model['bytes'] + 1)
            require(len(data) == model['bytes'] and stream.read(1) == b'', 'Model size mismatch')
        require(digest(data) == model['sha256'], 'Decoded model SHA mismatch')
        decoded.append((model, data))
    if decoded:
        require(targets == {'pure/student.onnx', 'pure/depth_backbone.onnx',
                            'finetune/student.onnx', 'finetune/depth_backbone.onnx'},
                'Expected exactly two complete student/depth pairs')
        before = json.loads((package / 'original-transfer/remote-before.json').read_bytes())
        after = json.loads((package / 'original-transfer/remote-after.json').read_bytes())
        require(before['status'] == after['status'] == 'ready'
                and before['snapshot_identity'] == after['snapshot_identity']
                and before['payload'] == after['payload'], 'Transfer snapshot changed')
        originals = before['payload']['files']
        require(len(originals) == 32 and len({x['relative'] for x in originals}) == 32,
                'Expected 32 unique original transfer files')
        model_by_raw = {x['raw_relative']: x for x, _ in decoded}
        require(len(model_by_raw) == 4, 'Duplicate raw model path')
        for original in originals:
            rel = str(relative(original['relative']))
            if rel in model_by_raw:
                model = model_by_raw[rel]
                require((original['sha256'], original['bytes']) ==
                        (model['sha256'], model['bytes']), 'Model/source32 mismatch')
            else:
                f = package / 'original-transfer/raw' / rel
                require(f.relative_to(package).as_posix() in expected_files,
                        'Missing source32 metadata')
                data = f.read_bytes()
                require(len(data) == original['bytes'] and digest(data) == original['sha256'],
                        'Source32 metadata mismatch')
        for pair in before['payload']['pairs']:
            for name, origin in pair['models'].items():
                model = model_by_raw[origin['relative']]
                require(model['target'] == pair['kind'] + '/' + name
                        and model['sha256'] == origin['sha256']
                        and model['bytes'] == origin['bytes'], 'Canonical pair mismatch')
        fetch = json.loads((package / 'original-transfer/fetch-status.json').read_bytes())
        require(fetch['status'] == 'completed' and fetch['files'] == 32
                and fetch['snapshot_identity'] == before['snapshot_identity'],
                'Fetch status differs from source32')
    require(digest(seal.read_bytes()) == expected, 'Manifest changed while verifying')
    return package, doc, decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--restore-models', type=Path)
    args = parser.parse_args()
    package, doc, decoded = verify(args.package, args.manifest_sha256)
    restored = []
    if args.restore_models:
        require(len(decoded) == 4, 'Use the independent model-payload package to restore models')
        output = no_alias(args.restore_models)
        require(not output.exists(), 'Restore directory already exists')
        require(output.parent.is_dir(), 'Restore parent must already exist')
        require(output != package and package not in output.parents, 'Restore inside sealed package')
        output.mkdir(mode=0o755)
        for model, data in decoded:
            target = output / model['target']
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            os.chmod(target, 0o644)
            actual = target.read_bytes()
            require(len(actual) == model['bytes'] and digest(actual) == model['sha256'],
                    'Restored model verification failed')
            restored.append({'path': str(target), 'bytes': len(actual), 'sha256': digest(actual)})
        verify(package, args.manifest_sha256)
    print(json.dumps({'status': 'passed_retained_bytes_verification',
                      'manifest_sha256': args.manifest_sha256,
                      'files_verified': len(doc['files']), 'models_decoded': len(decoded),
                      'restored_models': restored,
                      'scope': 'CPU/export provenance and byte restoration only; physical/native validation pending.'},
                     indent=2))


if __name__ == '__main__':
    main()
