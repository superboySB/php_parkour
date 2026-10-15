#!/usr/bin/env python3
"""Verify and restore the retained document evidence only; no scientific job."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat


def require(value, message):
    if not value:
        raise ValueError(message)


def relative(name):
    path = Path(name)
    require(isinstance(name, str) and bool(name) and path.parts and not path.is_absolute()
            and '..' not in path.parts and path.as_posix() == name, 'Normalized safe relative path required')
    return path


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink/traversal rejected')
    return path


def fingerprint(path):
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular file required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Bytes changed while hashing')
    return {'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def stored(package, record, sealed):
    storage = record['storage']
    name = relative(storage['path']).as_posix()
    require(name in sealed, 'Original storage missing from seal')
    if storage['kind'] == 'file':
        require(fingerprint(package / name) == {key: record[key] for key in ('bytes', 'sha256')}, 'Original copy differs')
        return [package / name]
    require(storage['kind'] == 'chunks', 'Unknown original storage kind')
    description = read(package / name)
    require(description['bytes'] == record['bytes'] and description['sha256'] == record['sha256'], 'Chunk descriptor identity differs')
    offset, whole, chunks = 0, hashlib.sha256(), []
    for chunk in description['chunks']:
        member = relative(chunk['path']).as_posix()
        require(member in sealed and chunk['offset'] == offset and 0 < chunk['bytes'] <= 25_000_000,
                'Chunk offset/length/seal differs')
        path = package / member
        require(fingerprint(path) == {key: chunk[key] for key in ('bytes', 'sha256')}, 'Chunk bytes differ')
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                whole.update(block)
        chunks.append(path)
        offset += chunk['bytes']
    require(offset == record['bytes'] and whole.hexdigest() == record['sha256'], 'Reconstructed original differs')
    return chunks


def verify(package, expected_manifest_sha256):
    package = safe(package)
    require(isinstance(expected_manifest_sha256, str)
            and fingerprint(package / 'evidence-manifest.json')['sha256'] == expected_manifest_sha256,
            'Explicit reviewed manifest SHA differs')
    seal = read(package / 'evidence-manifest.json')
    require(seal['schema_version'] == 1 and seal['status'] == 'sealed_document_publication', 'Terminal document seal required')
    expected = {}
    for row in seal['files']:
        name = relative(row['path']).as_posix()
        require(name != 'evidence-manifest.json' and name not in expected and 0 <= row['bytes'] < 100_000_000,
                'Duplicate, self-referential or Git-oversize sealed file')
        expected[name] = row
    actual = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlink in sealed package')
        require(path.is_dir() or stat.S_ISREG(path.stat().st_mode), 'Nonregular package member')
        member = path.relative_to(package).as_posix()
        if path.is_file() and member != 'evidence-manifest.json':
            actual.add(member)
    require(actual == set(expected), 'Package file set changed')
    for name, row in expected.items():
        require(fingerprint(package / name) == {key: row[key] for key in ('bytes', 'sha256')}, 'Sealed bytes differ: ' + name)
    mapping = read(package / 'restore-map.json')
    require(mapping['schema_version'] == 1, 'Restore map schema differs')
    seen = set()
    for record in mapping['retained']:
        destination = relative(record['workspace_relative']).as_posix()
        require(destination not in seen and type(record['mode']) is int and 0 <= record['mode'] <= 0o777,
                'Duplicate original destination or unsafe original mode')
        seen.add(destination)
        stored(package, record, expected)
    return {'status': 'document_evidence_bytes_verified', 'files': len(expected),
            'retained_originals': len(seen), 'excluded_bound_files': len(mapping['excluded_bindings']),
            'model_source_restore_supported': False, 'historical_tree_restore_supported': False,
            'historical_binding_only_roots': mapping.get('historical_binding_only_roots', []),
            'native_started': False, 'gpu_started': False}


def restore(package, output, expected_manifest_sha256):
    package, output = safe(package), safe(output)
    require(not output.exists() and not output.is_relative_to(package) and not package.is_relative_to(output),
            'Fresh separate restore directory required')
    before = fingerprint(package / 'evidence-manifest.json')
    report = verify(package, expected_manifest_sha256)
    seal = {row['path']: row for row in read(package / 'evidence-manifest.json')['files']}
    mapping = read(package / 'restore-map.json')
    output.mkdir(parents=True)
    for record in mapping['retained']:
        target = safe(output / relative(record['workspace_relative']))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as destination:
            for chunk in stored(package, record, seal):
                with chunk.open('rb') as source:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        require(fingerprint(target) == {key: record[key] for key in ('bytes', 'sha256')}, 'Restored original differs')
        target.chmod(record['mode'])
        require(stat.S_IMODE(target.stat().st_mode) == record['mode'], 'Restored original mode differs')
    verify(package, expected_manifest_sha256)
    require(fingerprint(package / 'evidence-manifest.json') == before, 'Seal changed during restore')
    return dict(report, status='retained_document_evidence_restored', output=str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'restore'))
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(args.action != 'restore' or args.output, 'Explicit fresh output required')
    value = verify(args.package, args.manifest_sha256) if args.action == 'verify' else restore(args.package, args.output, args.manifest_sha256)
    print(json.dumps(value, allow_nan=False))


if __name__ == '__main__':
    main()
