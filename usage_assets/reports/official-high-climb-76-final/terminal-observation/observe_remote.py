#!/usr/bin/env python3
"""One bounded, read-only observation; never starts or stops any remote job."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import subprocess

CID = 'f1f079422c8a6927a11a9e4d681ac50bc3abe7db03f2e3ccdbe7e6a07d9702db'
IMAGE = 'sha256:631d9e53768a3cc65372b394d0aa266a34ee92004141a9817824001ade30e3bd'
STARTED = '2026-10-10T04:01:22.880471283Z'
ROOT = Path('/diff/dzp_is_sb/php-parkour-research')
OUT = ROOT / 'outputs/official-full'


def process(pid, expected=None):
    path = Path('/proc') / str(pid)
    result = {'pid': pid, 'expected_start_ticks': expected}
    try:
        before = (path / 'stat').read_bytes()
        fields = before.decode().rsplit(')', 1)[1].split()
        command = (path / 'cmdline').read_bytes()
        after = (path / 'stat').read_bytes()
        after_fields = after.decode().rsplit(')', 1)[1].split()
        result.update(state=fields[0], ppid=int(fields[1]), pgid=int(fields[2]), sid=int(fields[3]),
                      start_ticks=int(fields[19]), cmdline=command.decode(errors='replace').replace('\x00', ' ').strip(),
                      stable_birth=int(fields[19]) == int(after_fields[19]), exists=True)
        result['expected_birth_matches'] = expected is None or result['start_ticks'] == expected
    except FileNotFoundError:
        result.update(exists=False, expected_birth_matches=False)
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    return result


def file_record(path, tail=None):
    if path.is_symlink() or not path.is_file():
        return {'path': str(path), 'exists': False}
    size = path.stat().st_size
    with path.open('rb') as stream:
        if tail is not None:
            stream.seek(max(0, size - tail))
        raw = stream.read()
    return {'path': str(path), 'exists': True, 'bytes_at_read': size, 'read_offset': max(0, size - tail) if tail else 0,
            'read_bytes': len(raw), 'read_sha256': hashlib.sha256(raw).hexdigest(), 'raw': raw.decode(errors='replace')}


def main():
    result = {'observed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'read_only': True, 'remote_files_modified': False,
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    check = subprocess.run(['docker', 'inspect', CID], capture_output=True, timeout=30)
    result['inspect'] = {'argv': ['docker', 'inspect', CID], 'returncode': check.returncode,
                         'stdout_raw': check.stdout.decode(), 'stderr_raw': check.stderr.decode()}
    if check.returncode:
        print(json.dumps(result)); raise SystemExit(1)
    info = json.loads(check.stdout)[0]
    identity = (info['Id'] == CID and info['Image'] == IMAGE and info['State']['StartedAt'] == STARTED)
    result['container'] = {'id': info['Id'], 'image': info['Image'], 'started_at': info['State']['StartedAt'],
                           'running': info['State']['Running'], 'exit_code': info['State']['ExitCode'],
                           'identity_matches': identity}
    if not identity:
        print(json.dumps(result)); raise SystemExit(1)
    result['original_processes'] = [process(3836907, 700458612), process(4074213, 702550493), process(816842, 713715179)]
    top = subprocess.run(['docker', 'top', CID, '-eo', 'pid,ppid,pgid,sid,args'], capture_output=True, timeout=30)
    result['top'] = {'argv': ['docker', 'top', CID, '-eo', 'pid,ppid,pgid,sid,args'], 'returncode': top.returncode,
                     'stdout_raw': top.stdout.decode(), 'stderr_raw': top.stderr.decode()}
    current = []
    for line in top.stdout.decode().splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) == 5 and '-m wbt_training.train_agent' in parts[4]:
            row = process(int(parts[0]))
            row['docker_top_row'] = line
            current.append(row)
    result['actual_native_training_processes'] = current
    manifests = []
    for label in ('locomotion', 'low-step', 'high-step', 'low-climb-76', 'high-climb-76'):
        record = file_record(OUT / 'official/manifests' / ('teacher-' + label + '.json'))
        if record['exists']:
            record['value'] = json.loads(record['raw'])
            manifests.append(record)
    result['teacher_manifests'] = manifests
    requested = next((record for record in manifests if record['value'].get('label') == 'teacher-low-climb-76'), None)
    labels = {'teacher-low-climb-76', 'teacher-high-climb-76'}
    for row in current:
        words = row.get('cmdline', '').split()
        if '--training.name' in words:
            index = words.index('--training.name')
            if index + 1 < len(words): labels.add(words[index + 1])
    logs = []
    for record in manifests:
        value = record['value']
        if value.get('label') not in labels:
            continue
        native_log = value.get('log')
        if native_log:
            native_path = Path(native_log)
            if not native_path.is_relative_to('/outputs'):
                raise ValueError('Unexpected manifest log path')
            path = ROOT / str(native_path).lstrip('/')
        else:
            matches = sorted((OUT / 'official').glob(value['label'] + '-*.log'), key=lambda path: path.stat().st_mtime_ns)
            path = matches[-1] if matches else None
        if path is not None:
            row = file_record(path, 65536)
            row['label'] = value['label']
            logs.append(row)
    result['stage_log_tails'] = logs
    result['driver_tail'] = file_record(ROOT / 'outputs/official-full-driver.log', 65536)
    result['requested_low_climb_76_status'] = requested['value'].get('status') if requested else 'manifest_not_found'
    result['all_official_teachers_terminal'] = len(manifests) == 5 and all(record['value'].get('status') == 'passed' for record in manifests)
    result['observation_completed_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
