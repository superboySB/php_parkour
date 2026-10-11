#!/usr/bin/env python3
"""One selective read-only transfer; retain all failures and never retry."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import shlex
import subprocess

BASE = Path(__file__).resolve().parent
HOST = 'tencent-231'
SSH = ['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
       '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
       '-o', 'ControlMaster=no']


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fp(path):
    path = Path(path).absolute()
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Regular nonsymlink file required: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('Local file changed: ' + str(path))
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def process(label, argv, stdin=None):
    out, err = BASE / (label + '.stdout.raw'), BASE / (label + '.stderr.raw')
    record = {'argv': argv, 'started_utc': now(), 'stdout': str(out), 'stderr': str(err)}
    save(BASE / (label + '.launch.json'), record)
    with out.open('xb') as stdout, err.open('xb') as stderr:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr, start_new_session=True)
        record['pid'] = child.pid
        fields = (Path('/proc') / str(child.pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        record.update(start_time_clock_ticks=int(fields[19]), pgid=int(fields[2]), sid=int(fields[3]))
        save(BASE / (label + '.launch.json'), record)
        if stdin is not None:
            child.stdin.write(stdin); child.stdin.close()
        record['actual_wait_returncode'] = child.wait()
    record.update(finished_utc=now(), stdout_fingerprint=fp(out), stderr_fingerprint=fp(err))
    save(BASE / (label + '.exit.json'), record)
    if record['actual_wait_returncode']:
        raise RuntimeError(label + ' failed: ' + str(record['actual_wait_returncode']))
    return record


def inventory(label):
    script = BASE / 'inventory_remote.py'
    receipt = process(label, SSH + [HOST, 'python3 -'], script.read_bytes())
    data = json.loads(Path(receipt['stdout']).read_bytes())
    if data['status'] != 'passed':
        raise ValueError('Remote read-only inventory not passed')
    return data


def main():
    receipt_path = BASE / 'receipt.json'
    with receipt_path.open('x'):
        pass
    record = {'schema_version': 1, 'status': 'running', 'started_utc': now(),
              'remote_read_only': True, 'remote_files_modified': False,
              'native_or_gpu_started': False, 'automatic_retries': 0,
              'sources_before': [fp(__file__), fp(BASE / 'inventory_remote.py')]}
    save(receipt_path, record)
    try:
        before = inventory('inventory-before')
        record['inventory_before'] = fp(BASE / 'inventory-before.stdout.raw')
        artifacts = before['artifacts']
        run = before['run_directory']
        names = [Path(row['path']).name for row in artifacts]
        if len(names) != len(set(names)) or any(str(Path(row['path']).parent) != run for row in artifacts):
            raise ValueError('Ambiguous artifact selection')
        allowed = {'model_19999.pt', 'model_19999.onnx', 'holosoma_config.yaml', 'model_00000.pt', *before['event_file_names']}
        if set(names) != allowed - (set() if before['initial_checkpoint_exists'] else {'model_00000.pt'}):
            raise ValueError('Only final PT/ONNX/YAML/TensorBoard and native baseline may be transferred')
        record['initial_checkpoint_exists'] = before['initial_checkpoint_exists']
        (BASE / 'teacher-low-step.json').write_bytes(before['manifest_before']['raw'].encode())
        (BASE / 'runtime-resolution-source.py').write_bytes(before['runtime_resolution_source']['raw'].encode())
        record['remote_artifacts_before'] = artifacts
        target = BASE / 'artifacts'; target.mkdir(exist_ok=False)
        file_list = BASE / 'rsync-files.txt'
        file_list.write_text(''.join(name + '\n' for name in names))
        record['rsync'] = process('rsync', ['rsync', '-a', '--no-owner', '--no-group', '--protect-args',
            '--info=progress2', '--partial-dir=.rsync-partial', '--files-from', str(file_list),
            '-e', shlex.join(SSH), HOST + ':' + run + '/', str(target) + '/'])
        local = [fp(target / name) for name in names]
        if {p.name for p in target.iterdir()} != set(names):
            raise ValueError('Unexpected local or partial file remains')
        for expected, actual in zip(artifacts, local):
            if any(expected[key] != actual[key] for key in ('bytes', 'sha256')):
                raise ValueError('Local artifact differs: ' + actual['path'])
        record['local_artifacts'] = local
        record['artifact_mapping'] = [{'remote': expected, 'local': actual} for expected, actual in zip(artifacts, local)]
        after = inventory('inventory-after')
        record['inventory_after'] = fp(BASE / 'inventory-after.stdout.raw')
        for field in ('artifacts', 'manifest_before', 'manifest_after', 'runtime_resolution_source', 'event_file_names', 'run_directory'):
            if before[field] != after[field]:
                raise ValueError('Remote source changed during transfer: ' + field)
        for key in ('boot_id', 'container_id', 'image', 'started_at', 'running', 'init_host_pid'):
            if before['identity_before'][key] != after['identity_after'][key]:
                raise ValueError('Original remote identity changed during transfer: ' + key)
        record['remote_artifacts_after'] = after['artifacts']
        record['sources_after'] = [fp(__file__), fp(BASE / 'inventory_remote.py')]
        if record['sources_after'] != record['sources_before']:
            raise ValueError('Transfer helpers changed during actual execution')
        record.update(status='completed', verified_artifact_count=len(local),
                      verified_artifact_bytes=sum(row['bytes'] for row in local),
                      remote_source_unchanged=True, source_helpers_unchanged=True,
                      cpu_acceptance_executed=False, quality_verified=False)
    except BaseException as error:
        record.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        record['finished_utc'] = now()
        save(receipt_path, record)
    print(json.dumps({key: record[key] for key in ('status', 'verified_artifact_count', 'verified_artifact_bytes', 'initial_checkpoint_exists')}))


if __name__ == '__main__':
    main()
