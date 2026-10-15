#!/usr/bin/env python3
"""Verify an externally pinned native58 media side package using only stdlib."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(package, expected, restore_modes=False):
    package = package.absolute()
    require(package.resolve() == package, 'Normalized package without symlinks required')
    seal = package / 'evidence-manifest.json'
    require(not seal.is_symlink() and hashlib.sha256(seal.read_bytes()).hexdigest() == expected, 'External seal SHA differs')
    manifest = json.loads(seal.read_bytes())
    require(manifest['status'] == 'sealed_actual_native58_derived_media_side_package', 'Unexpected package schema')
    rows = manifest['files']; names = [r['path'] for r in rows]
    require(len(names) == len(set(names)), 'Duplicate manifest paths')
    actual = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlink package member rejected')
        if path.is_file() and path != seal:
            actual.add(path.relative_to(package).as_posix())
    require(actual == set(names), 'Exact payload file set differs')
    paths = []
    for row in rows:
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix() == row['path'], 'Unsafe manifest member')
        path = package / relative; require(path.is_file() and path.resolve() == path, 'Regular payload required')
        data = path.read_bytes()
        require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'Payload bytes differ: ' + row['path'])
        require(isinstance(row['mode'], int) and 0 <= row['mode'] <= 0o777, 'Plain permission mode required')
        paths.append((path, row))
    # Git records executability, not all permission bits. Restore only modes after
    # the external seal and every payload byte/file-set have passed verification.
    if restore_modes:
        for path, row in paths:
            path.chmod(row['mode'])
    require(all(stat.S_IMODE(p.stat().st_mode) == r['mode'] for p, r in paths), 'Payload permission mode differs; use --restore-modes after a Git checkout')
    return {'status': 'passed_external_seal_bytes_exact_file_set_and_modes', 'payload_files': len(rows),
            'payload_bytes': sum(r['bytes'] for r in rows), 'external_seal_sha256': expected,
            'mode_restoration_requested': restore_modes,
            'scope': 'Derived package only. Original full58 MP4s and historical/source/model dependencies remain in separately linked packages; no new simulation or success claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--restore-modes', action='store_true')
    parser.add_argument('--restore-to', type=Path, help='Copy the verified whole package to a fresh separate directory, preserving modes, then verify it')
    args = parser.parse_args()
    result = verify(args.package, args.manifest_sha256, args.restore_modes)
    if args.restore_to is not None:
        package, target = args.package.absolute(), args.restore_to.absolute()
        require(not target.exists() and target.parent.resolve() == target.parent, 'Fresh normalized restore target required')
        require(not target.is_relative_to(package) and not package.is_relative_to(target), 'Separate restore target required')
        shutil.copytree(package, target)
        restored = verify(target, args.manifest_sha256)
        verify(package, args.manifest_sha256)
        result['restore'] = {'target': str(target), 'result': restored, 'source_reverified_after_copy': True}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
