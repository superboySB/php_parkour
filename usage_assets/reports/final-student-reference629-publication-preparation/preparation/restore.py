#!/usr/bin/env python3
"""Restore an actual sealed formal-pair publication into one fresh workspace.

Source-only preparation: this file has only been AST parsed, never imported or
invoked. No actual package currently exists. The future CLI verifies the entire
package before creating output; it restores bytes and file modes, never uid/gid,
containers, training, simulation or model quality. It does not overwrite/retry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys

CHUNK_LIMIT = 25_000_000
GIT_BLOB_LIMIT = 100_000_000
ORIGINAL_WORKSPACE = '/home/dzp/projects/php_parkour'
COUNTS = {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}
RESERVED = {'restoration-receipt.json', 'restoration-receipt.pending.json',
            'restoration-failed.json', '.restore-incomplete.json'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Invalid explicit SHA256')
    return value


def number(value):
    require(type(value) is int and value >= 0, 'Nonnegative integer bytes required')
    return value


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value and '\x00' not in value,
            'Canonical relative POSIX path required')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == value and value != '.',
            'Absolute, traversing or noncanonical relative path')
    return path


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            'Symlink/traversing filesystem path rejected')
    return path


def fingerprint(path):
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular package/restored file required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode), 'File changed while hashing')
    return {'bytes': after.st_size, 'sha256': digest.hexdigest()}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def bound_json(path, expected=None):
    """Parse the very bytes checked by the binding, never a second file read."""
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size < GIT_BLOB_LIMIT,
            'Regular JSON below100MB required')
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode)
            and len(raw) == after.st_size, 'JSON changed while reading')
    record = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        require(record == {key: expected[key] for key in ('bytes', 'sha256')}, 'Parsed JSON bytes/SHA differ')
    return strict_json(raw), record


def table(rows, key):
    require(isinstance(rows, list) and rows, 'Nonempty evidence list required')
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get(key), str) and row[key] not in result,
                'Duplicate or invalid evidence path')
        number(row['bytes']); sha(row['sha256'])
        result[row[key]] = row
    return result


def match(path, row):
    require(fingerprint(path) == {key: row[key] for key in ('bytes', 'sha256')}, 'Package/whole bytes or SHA differ')


def package_files(package):
    names = set()
    for path in package.rglob('*'):
        require(not path.is_symlink(), 'Symlink in package tree')
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.stat().st_mode), 'Nonregular package evidence')
        names.add(path.relative_to(package).as_posix())
    return names


def validate_chunks(package, stored, row, files, originals):
    path = relative(stored['path']).as_posix()
    require(path in files, 'Chunk descriptor is not sealed by manifest')
    descriptor, _ = bound_json(package / path, files[path])
    restored = relative(stored['restored_relative']).as_posix()
    number(descriptor['bytes']); sha(descriptor['sha256'])
    require(type(descriptor['schema_version']) is int and descriptor['schema_version'] == 1
            and descriptor['original_relative'] == restored and path == restored + '.chunks.json'
            and descriptor['bytes'] == row['bytes'] and descriptor['sha256'] == row['sha256']
            and row['bytes'] > CHUNK_LIMIT and restored not in files,
            'Chunk descriptor identity/whole binding differs')
    origin = originals.get(descriptor['source'])
    require(origin is not None and origin['bytes'] == row['bytes'] and origin['sha256'] == row['sha256'],
            'Descriptor source is not an actual same-byte original alias')
    parts = descriptor['chunks']
    require(isinstance(parts, list) and parts, 'Nonempty chunk list required')
    offset, whole = 0, hashlib.sha256()
    for ordinal, part in enumerate(parts):
        name = relative(part['path']).as_posix()
        size = number(part['bytes']); sha(part['sha256'])
        require(type(part['offset']) is int and part['offset'] == offset and 0 < size <= CHUNK_LIMIT
                and (ordinal == len(parts) - 1 or size == CHUNK_LIMIT)
                and name == restored + f'.parts/{ordinal:06d}.bin' and name in files
                and files[name]['bytes'] == size and files[name]['sha256'] == part['sha256'],
                'Missing/reordered/noncontiguous/oversized or relabeled chunk')
        actual_part, actual_size = hashlib.sha256(), 0
        with (package / name).open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                whole.update(block); actual_part.update(block); actual_size += len(block)
        require(actual_size == size and actual_part.hexdigest() == part['sha256'], 'Chunk actual bytes/SHA differ')
        offset += size
    require(offset == row['bytes'] and whole.hexdigest() == row['sha256'], 'Reassembled original whole bytes/SHA differ')
    return descriptor


def preflight(package, manifest_sha, output):
    package, output = safe(package), safe(output)
    require(package.is_dir(), 'Existing actual publication directory required')
    require(not output.exists() and output.parent.is_dir(), 'A fresh output under an existing parent is required')
    require(not output.is_relative_to(package) and not package.is_relative_to(output), 'Package/output trees may not overlap')
    manifest_path = package / 'evidence-manifest.json'
    manifest, manifest_record = bound_json(manifest_path)
    require(manifest_record['sha256'] == sha(manifest_sha), 'Manifest differs from independently supplied SHA')
    require(manifest_record['bytes'] < GIT_BLOB_LIMIT, 'Manifest reaches100MB')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1
            and manifest['status'] == 'complete_formal_pair_publication'
            and set(manifest['counts']) == set(COUNTS)
            and all(type(manifest['counts'][key]) is int and manifest['counts'][key] == value for key, value in COUNTS.items())
            and manifest['all_original_bytes_retained'] is True
            and manifest['quality_verified'] is manifest['obstacle_course_completion_verified'] is False,
            'Only complete1258/2516/2516/1258 actual publication manifests are accepted')
    files = table(manifest['files'], 'path')
    require('restore-map.json' in files and 'evidence-manifest.json' not in files,
            'Sealed restore-map required; manifest must not include itself')
    for name, row in files.items():
        relative(name)
        require(row['bytes'] < GIT_BLOB_LIMIT, 'Actual package blob reaches100MB')
        match(package / name, row)
    require(package_files(package) == set(files) | {'evidence-manifest.json'}, 'Package file-set differs from complete manifest')
    require(type(manifest['bytes_excluding_manifest']) is int
            and manifest['bytes_excluding_manifest'] == sum(row['bytes'] for row in files.values()), 'Manifest byte total differs')
    mapping, _ = bound_json(package / 'restore-map.json', files['restore-map.json'])
    require(type(mapping['schema_version']) is int and mapping['schema_version'] == 1
            and mapping['original_workspace'] == ORIGINAL_WORKSPACE
            and mapping['external_file_dependencies'] == [] and mapping['all_inventory_files_retained'] is True,
            'Self-contained original workspace restore-map required')
    originals = table(manifest['original_inventory'], 'path')
    rows = table(mapping['files'], 'original_path')
    require(set(rows) == set(originals), 'Restore mapping omits/adds an original inventory file')
    targets, descriptors = set(), {}
    for name, row in rows.items():
        target = relative(row['workspace_relative']).as_posix()
        require(name == ORIGINAL_WORKSPACE + '/' + target and target not in targets
                and not any(target == reserved or target.startswith(reserved + '/') for reserved in RESERVED),
                'Conflicting or invalid workspace mapping')
        targets.add(target)
        require(row['bytes'] == originals[name]['bytes'] and row['sha256'] == originals[name]['sha256'],
                'Restore entry is not the sealed original fingerprint')
        mode = row['mode']
        require(type(mode) is int and 0 <= mode <= 0o7777 and row['mode_octal'] == oct(mode)
                and 'uid' not in row and 'gid' not in row, 'Only actual file mode is restored, never uid/gid')
        stored = row['storage']; storage_path = relative(stored['path']).as_posix()
        require(storage_path in files, 'Mapped storage not sealed by manifest')
        if stored['kind'] == 'file':
            require(files[storage_path]['bytes'] == row['bytes'] and files[storage_path]['sha256'] == row['sha256'],
                    'Direct storage has different original bytes/SHA')
        elif stored['kind'] == 'chunks':
            if storage_path not in descriptors:
                descriptors[storage_path] = validate_chunks(package, stored, row, files, originals)
            descriptor = descriptors[storage_path]
            require(descriptor['bytes'] == row['bytes'] and descriptor['sha256'] == row['sha256']
                    and descriptor['original_relative'] == stored['restored_relative'], 'Shared chunk alias differs')
        else:
            raise ValueError('Unsupported storage kind')
    for target in targets:
        require(not any(parent.as_posix() in targets for parent in PurePosixPath(target).parents),
                'A file mapping conflicts with another file directory')
    require({name for name in files if name.endswith('.chunks.json')} == set(descriptors),
            'Package includes a chunk descriptor not validated by the restore-map')
    for name, row in files.items():
        match(package / name, row)
    match(manifest_path, manifest_record)
    require(package_files(package) == set(files) | {'evidence-manifest.json'}, 'Package changed during preflight')
    return {'package': package, 'output': output, 'manifest': manifest_record, 'files': files,
            'rows': list(rows.values()), 'descriptors': descriptors}


def restore(context):
    package, output = context['package'], context['output']
    safe(output)
    require(not output.exists() and not output.is_symlink(), 'Output appeared after preflight; never overwrite')
    output.mkdir(exist_ok=False)
    pending = output / '.restore-incomplete.json'
    completed = []
    try:
        output.chmod(0o755)
        with pending.open('x') as stream:
            stream.write(json.dumps({'status': 'restoring_data_files_not_complete'}) + '\n')
        pending.chmod(0o644)
        for row in context['rows']:
            target = output / row['workspace_relative']
            require(target.is_relative_to(output) and not any(p.is_symlink() for p in (target, *target.parents)),
                    'Destination tree changed or traverses a symlink')
            target.parent.mkdir(parents=True, exist_ok=True)
            stored = row['storage']
            sources = [stored['path']] if stored['kind'] == 'file' else [
                part['path'] for part in context['descriptors'][stored['path']]['chunks']]
            with target.open('xb') as destination:
                for source in sources:
                    match(package / source, context['files'][source])
                    with (package / source).open('rb') as original:
                        for block in iter(lambda: original.read(8 * 1024 * 1024), b''):
                            destination.write(block)
                    match(package / source, context['files'][source])
            match(target, row)  # Verify readable fresh bytes before final mode can restrict reads.
            target.chmod(row['mode'])
            require(stat.S_IMODE(target.stat().st_mode) == row['mode'], 'Restored original mode differs')
            completed.append({key: row[key] for key in ('workspace_relative', 'bytes', 'sha256', 'mode')})
        for name, row in context['files'].items():
            match(package / name, row)
        match(package / 'evidence-manifest.json', context['manifest'])
        require(package_files(package) == set(context['files']) | {'evidence-manifest.json'}, 'Package changed during restore')
        for path in output.rglob('*'):
            require(not path.is_symlink(), 'Symlink appeared in restored tree')
            if path.is_dir():
                path.chmod(0o755)
        actual_files = {path.relative_to(output).as_posix() for path in output.rglob('*') if path.is_file()}
        require(actual_files == {row['workspace_relative'] for row in context['rows']} | {pending.name},
                'Unexpected/missing restored files before success receipt')
        for row in context['rows']:
            target = safe(output / row['workspace_relative'])
            require(stat.S_ISREG(target.stat().st_mode) and stat.S_IMODE(target.stat().st_mode) == row['mode'],
                    'Restored original file mode changed before completion')
        receipt = {'schema_version': 1, 'status': 'restored_original_workspace_files',
                   'package': str(package), 'manifest': context['manifest'], 'output': str(output),
                   'restored_file_count': len(completed), 'restored_bytes': sum(row['bytes'] for row in completed),
                   'files': completed, 'bytes_verified_before_final_chmod': True, 'file_modes_verified': True,
                   'uid_gid_restored': False, 'hardlinks_created': False, 'science_executed': False,
                   'native_started': False, 'gpu_started': False, 'quality_verified': False,
                   'scope': 'File recovery only; no training, simulator, model acceptance, hardware or independent parent-returncode proof.',
                   'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        temporary = output / 'restoration-receipt.pending.json'
        with temporary.open('x') as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
        temporary.chmod(0o644)
        pending.unlink()
        temporary.replace(output / 'restoration-receipt.json')  # Final success marker; no later filesystem operation.
        return {'status': receipt['status'], 'output': str(output), 'restored_file_count': len(completed),
                'receipt': str(output / 'restoration-receipt.json'), 'science_executed': False}
    except BaseException as error:
        try:
            success = output / 'restoration-receipt.json'
            if success.exists():
                success.unlink()
            with (output / 'restoration-failed.json').open('x') as stream:
                json.dump({'status': 'failed_partial_restore', 'error': type(error).__name__ + ': ' + str(error),
                           'completed_file_count': len(completed), 'success_receipt_created': False,
                           'automatic_retry': False}, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        except BaseException as diagnostic_error:
            print('Partial restore diagnostic IO failed; preserve output and original error: ' + str(diagnostic_error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    context = preflight(args.package, args.manifest_sha256, args.output)
    print(json.dumps(restore(context), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
