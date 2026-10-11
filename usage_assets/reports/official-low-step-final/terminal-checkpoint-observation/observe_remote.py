#!/usr/bin/env python3
"""Read-only final low-step checkpoint identity and streaming SHA verification."""
from pathlib import Path, PurePosixPath
import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
import sys

ROOT = Path('/diff/dzp_is_sb/php-parkour-research')
MANIFEST = ROOT / 'outputs/official-full/official/manifests/teacher-low-step.json'
CID = 'f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
IMAGE = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
STARTED = '2026-10-10T04:01:22.880471283Z'
BOOT = 'f17c5b43-57e8-451f-a9e1-b57b29860227'
record = {'schema': 1, 'observed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'read_only': True, 'remote_files_modified': False, 'errors': []}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def metadata(s):
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
            'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}


def regular_path(path):
    for parent in reversed(path.parents):
        require(not stat.S_ISLNK(parent.lstat().st_mode), 'symlink ancestor: ' + str(parent))
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode), 'not a regular file: ' + str(path))
    return metadata(s)


def snapshot_manifest():
    before = regular_path(MANIFEST)
    with os.fdopen(os.open(MANIFEST, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require(metadata(os.fstat(stream.fileno())) == before, 'manifest identity changed before read')
        raw = stream.read()
        require(metadata(os.fstat(stream.fileno())) == before, 'manifest changed while reading')
    after = regular_path(MANIFEST)
    require(after == before, 'manifest path changed while reading')
    return {'path': str(MANIFEST), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'stat_before': before, 'stat_after': after, 'raw': raw.decode('utf-8')}


def inspect_container():
    template = '{"Id":{{json .Id}},"Image":{{json .Image}},"StartedAt":{{json .State.StartedAt}},"Running":{{json .State.Running}},"Pid":{{json .State.Pid}}}'
    argv = ['docker', 'inspect', '--format', template, CID]
    child = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    result = {'argv': argv, 'returncode': child.returncode, 'stdout': child.stdout, 'stderr': child.stderr}
    require(child.returncode == 0, 'container inspect failed')
    value = json.loads(child.stdout)
    result['value'] = value
    require((value['Id'], value['Image'], value['StartedAt']) == (CID, IMAGE, STARTED), 'container identity mismatch')
    require(value['Running'] is True, 'original container is not running')
    return result


try:
    record['boot_before'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(record['boot_before'] == BOOT, 'remote boot identity mismatch')
    record['container_before'] = inspect_container()
    record['manifest_before'] = snapshot_manifest()
    manifest = json.loads(record['manifest_before']['raw'])
    record['manifest_fields'] = {key: manifest.get(key) for key in (
        'label', 'profile', 'status', 'returncode', 'finished_utc', 'checkpoint',
        'checkpoint_iteration', 'checkpoint_sha256', 'quality_verified')}
    require(manifest['label'] == 'teacher-low-step' and manifest['profile'] == 'official', 'wrong teacher manifest')
    require(manifest['status'] == 'passed' and manifest['returncode'] == 0, 'teacher not successfully terminal')
    require(manifest['checkpoint_iteration'] == 19999, 'unexpected final checkpoint iteration')
    native = PurePosixPath(manifest['checkpoint'])
    prefix = PurePosixPath('/outputs/official-full/official/teacher-low-step')
    require(native.is_absolute() and '..' not in native.parts and prefix in native.parents, 'checkpoint outside allowed teacher subtree')
    path = ROOT.joinpath(*native.parts[1:])
    before = regular_path(path)
    digest = hashlib.sha256()
    count = 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require(metadata(os.fstat(stream.fileno())) == before, 'checkpoint identity changed before hash')
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            count += len(chunk)
        fd_after = metadata(os.fstat(stream.fileno()))
    after = regular_path(path)
    record['checkpoint'] = {'native_path': str(native), 'remote_path': str(path),
                            'bytes': count, 'sha256': digest.hexdigest(),
                            'stat_before': before, 'fd_stat_after': fd_after, 'stat_after': after}
    require(before == fd_after == after and count == before['bytes'], 'checkpoint changed during streaming hash')
    require(digest.hexdigest() == manifest['checkpoint_sha256'], 'checkpoint SHA differs from passed manifest')
    record['manifest_after'] = snapshot_manifest()
    require(record['manifest_before'] == record['manifest_after'], 'manifest bytes or identity changed during checkpoint hash')
    record['container_after'] = inspect_container()
    require(record['container_after']['value'] == record['container_before']['value'], 'original container identity changed during verification')
    record['boot_after'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(record['boot_after'] == record['boot_before'], 'boot changed during verification')
    record['status'] = 'passed'
except Exception as exc:
    record['status'] = 'failed'
    record['errors'].append(type(exc).__name__ + ': ' + str(exc))
record['completed_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
print(json.dumps(record, ensure_ascii=False, indent=2))
sys.exit(record['status'] != 'passed')
