#!/usr/bin/env python3
"""Read-only, standard-library inventory of one completed low-step teacher."""
from pathlib import Path, PurePosixPath
import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
import sys

ROOT = Path('/diff/dzp_is_sb/php-parkour-research')
RUN = ROOT / 'outputs/official-full/official/teacher-low-step/PHP-research/20261010_165257-teacher-low-step-locomotion'
MANIFEST = ROOT / 'outputs/official-full/official/manifests/teacher-low-step.json'
SOURCE = ROOT / 'source/0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab'
PPO_MODULE = SOURCE / 'thirdparty/holosoma/src/holosoma/holosoma/agents/modules/ppo_modules.py'
CID = 'f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
IMAGE = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
STARTED = '2026-10-10T04:01:22.880471283Z'
BOOT = 'f17c5b43-57e8-451f-a9e1-b57b29860227'
FINAL_SHA = 'ff6912286a5b2a4d8d048dca5471b53935baecca4d06c3407af7201ef09153e6'
EXPECTED = ((3836907, 700458612, 'official_driver'), (4074213, 702550493, 'posttrain_monitor'),
            (471066, 709429584, 'high_step_wrapper'), (471154, 709429651, 'high_step_kit'))


def require(value, message):
    if not value:
        raise ValueError(message)


def meta(s):
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
            'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}


def regular(path):
    for parent in reversed(path.parents):
        require(not stat.S_ISLNK(parent.lstat().st_mode), 'Symlink ancestor: ' + str(parent))
    state = path.lstat()
    require(stat.S_ISREG(state.st_mode), 'Regular source required: ' + str(path))
    return meta(state)


def file_record(path, raw=False):
    before = regular(path)
    h = hashlib.sha256()
    data = [] if raw else None
    count = 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require(meta(os.fstat(stream.fileno())) == before, 'Path changed before read: ' + str(path))
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block); count += len(block)
            if raw:
                data.append(block)
        fd_after = meta(os.fstat(stream.fileno()))
    after = regular(path)
    require(before == fd_after == after and count == before['bytes'], 'Source changed while reading: ' + str(path))
    result = {'path': str(path), 'bytes': count, 'sha256': h.hexdigest(),
              'stat_before': before, 'fd_stat_after': fd_after, 'stat_after': after}
    if raw:
        result['raw'] = b''.join(data).decode('utf-8')
    return result


def process(pid, birth, role):
    root = Path('/proc') / str(pid)
    before = (root / 'stat').read_bytes().decode().rsplit(')', 1)[1].split()
    command = (root / 'cmdline').read_bytes().decode(errors='replace').replace('\0', ' ').strip()
    after = (root / 'stat').read_bytes().decode().rsplit(')', 1)[1].split()
    require(int(before[19]) == int(after[19]) == birth and before[0] != 'Z' and after[0] != 'Z', 'Process birth/state differs: ' + role)
    return {'role': role, 'pid': pid, 'start_time_clock_ticks': birth, 'state': after[0],
            'ppid': int(after[1]), 'pgid': int(after[2]), 'sid': int(after[3]), 'cmdline': command,
            'stable_birth': True}


def identity():
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(boot == BOOT, 'Boot changed')
    child = subprocess.run(['docker', 'inspect', CID], capture_output=True, timeout=30)
    require(child.returncode == 0, 'Original container inspect failed')
    value = json.loads(child.stdout)[0]
    require((value['Id'], value['Image'], value['State']['StartedAt'], value['State']['Running']) == (CID, IMAGE, STARTED, True), 'Original container identity differs')
    mount = [row for row in value['Mounts'] if row['Destination'] == '/workspace/php_parkour']
    require(len(mount) == 1 and mount[0]['Source'] == str(SOURCE), 'Original source mount differs')
    return {'boot_id': boot, 'container_id': value['Id'], 'image': value['Image'],
            'started_at': value['State']['StartedAt'], 'running': value['State']['Running'],
            'init_host_pid': value['State']['Pid'], 'mounts': value['Mounts'],
            'inspect_returncode': child.returncode, 'inspect_stdout_raw': child.stdout.decode(),
            'inspect_stderr_raw': child.stderr.decode(), 'processes': [process(*row) for row in EXPECTED]}


record = {'schema_version': 1, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'remote_read_only': True, 'remote_files_modified': False, 'scientific_imports': False,
          'native_or_gpu_started': False, 'errors': []}
try:
    record['identity_before'] = identity()
    record['manifest_before'] = file_record(MANIFEST, raw=True)
    manifest = json.loads(record['manifest_before']['raw'])
    require((manifest['label'], manifest['profile'], manifest['status'], manifest['returncode'], manifest['checkpoint_iteration'], manifest['checkpoint_sha256']) ==
            ('teacher-low-step', 'official', 'passed', 0, 19999, FINAL_SHA), 'Final passed manifest differs')
    require(ROOT / str(PurePosixPath(manifest['checkpoint'])).lstrip('/') == RUN / 'model_19999.pt', 'Unexpected run directory')
    names = sorted(path.name for path in RUN.iterdir())
    record['run_directory'] = str(RUN)
    record['event_file_names'] = [name for name in names if name.startswith('events.out.tfevents.')]
    record['final_model_related_names'] = [name for name in names if name.startswith('model_19999')]
    require(record['event_file_names'], 'No TensorBoard event file')
    require(record['final_model_related_names'] == ['model_19999.onnx', 'model_19999.pt'], 'Final ONNX external/extra filenames need review')
    selected = ['model_19999.pt', 'model_19999.onnx', 'holosoma_config.yaml', *record['event_file_names']]
    record['initial_checkpoint_exists'] = 'model_00000.pt' in names
    if record['initial_checkpoint_exists']:
        selected.append('model_00000.pt')
    record['artifacts'] = [file_record(RUN / name) for name in selected]
    final = next(row for row in record['artifacts'] if row['path'].endswith('/model_19999.pt'))
    require(final['sha256'] == FINAL_SHA, 'Final checkpoint differs from passed manifest')
    record['runtime_resolution_source'] = file_record(PPO_MODULE, raw=True)
    record['manifest_after'] = file_record(MANIFEST, raw=True)
    require(record['manifest_after'] == record['manifest_before'], 'Manifest changed during inventory')
    record['identity_after'] = identity()
    for key in ('boot_id', 'container_id', 'image', 'started_at', 'running', 'init_host_pid'):
        require(record['identity_before'][key] == record['identity_after'][key], 'Original identity changed: ' + key)
    for before, after in zip(record['identity_before']['processes'], record['identity_after']['processes']):
        require((before['pid'], before['start_time_clock_ticks']) == (after['pid'], after['start_time_clock_ticks']), 'Original process changed')
    record['status'] = 'passed'
except Exception as exc:
    record['status'] = 'failed'
    record['errors'].append(type(exc).__name__ + ': ' + str(exc))
record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
print(json.dumps(record, ensure_ascii=False, indent=2))
sys.exit(record['status'] != 'passed')
