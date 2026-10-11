#!/usr/bin/env python3
"""Verify this publication, restore original events, or replay the five CPU phases.

Host dependencies are Python's standard library and an existing Docker. The
exact external ONNX and existing unified image are required; no package install,
GPU, network, training, simulator or policy rollout is started by replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import zlib

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
CHUNK = 8 * 1024 * 1024


def regular(path):
    if not path.is_file() or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Regular nonsymlink file required: ' + str(path))
    return path


def fp(path):
    regular(path)
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(CHUNK), b''):
            sha.update(data)
    return {'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}


def read(path):
    return json.loads(regular(path).read_bytes())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def verify_package():
    manifest = read(BASE / 'evidence-manifest.json')
    expected = set()
    for record in manifest['files']:
        relative = Path(record['path'])
        if relative.is_absolute() or '..' in relative.parts or str(relative) in expected:
            raise ValueError('Unsafe or duplicate publication path')
        expected.add(str(relative))
        if fp(BASE / relative) != {key: record[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Publication bytes changed: ' + str(relative))
    actual = {str(path.relative_to(BASE)) for path in BASE.rglob('*') if path.is_file()}
    if actual != expected | {'evidence-manifest.json'} or any(path.is_symlink() for path in BASE.rglob('*')):
        raise ValueError('Publication file set differs')
    return manifest


def copy(source, target, expected):
    if fp(source) != expected:
        raise ValueError('Input does not match the archived original: ' + str(source))
    with source.open('rb') as old, target.open('xb') as new:
        shutil.copyfileobj(old, new, length=CHUNK)
    if fp(source) != expected or fp(target) != expected:
        raise ValueError('Input changed while restoring: ' + str(source))


def restore_event(target):
    archive = read(BASE / 'tensorboard/event-archive.json')
    if (archive['encoding'] != 'gzip' or archive['gzip_mtime'] != 0
            or Path(archive['restore_name']).name != archive['restore_name']):
        raise ValueError('Unexpected original event contract')
    compressed_sha, restored_sha = hashlib.sha256(), hashlib.sha256()
    compressed_bytes = restored_bytes = 0
    decoder = zlib.decompressobj(wbits=31)
    destination = target / archive['restore_name']
    with destination.open('xb') as output:
        for record in archive['chunks']:
            relative = Path(record['path'])
            if relative.is_absolute() or '..' in relative.parts or record['offset'] != compressed_bytes:
                raise ValueError('Unsafe or noncontinuous compressed event chunk')
            path = BASE / relative
            expected = {key: record[key] for key in ('bytes', 'sha256')}
            if fp(path) != expected:
                raise ValueError('Compressed event chunk changed')
            with path.open('rb') as stream:
                for data in iter(lambda: stream.read(CHUNK), b''):
                    compressed_sha.update(data)
                    compressed_bytes += len(data)
                    restored = decoder.decompress(data)
                    output.write(restored)
                    restored_sha.update(restored)
                    restored_bytes += len(restored)
            if fp(path) != expected:
                raise ValueError('Compressed event chunk changed during restoration')
        restored = decoder.flush()
        output.write(restored)
        restored_sha.update(restored)
        restored_bytes += len(restored)
    if (not decoder.eof or decoder.unused_data
            or {'bytes': compressed_bytes, 'sha256': compressed_sha.hexdigest()} != archive['compressed']
            or {'bytes': restored_bytes, 'sha256': restored_sha.hexdigest()} != archive['original']
            or fp(destination) != archive['original']):
        raise ValueError('Original TensorBoard event restoration failed')
    return {'file': str(destination), **fp(destination)}


def inputs(artifacts):
    manifest = read(BASE / 'cpu-02/input/input-manifest.json')
    mapping = {'/control': BASE / 'cpu-02/input', '/artifacts': artifacts}
    result = []
    for record in manifest['records']:
        source = Path(record['path'])
        if source.parent.as_posix() not in mapping:
            raise ValueError('Unexpected original input namespace: ' + record['path'])
        path = mapping[source.parent.as_posix()] / source.name
        if fp(path) != {key: record[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Reconstructed input differs: ' + record['path'])
        result.append({'native_path': record['path'], 'host_path': str(path), **fp(path)})
    return result


def restore(output, onnx):
    verify_package()
    output = output.absolute()
    if ('..' in output.parts or output.is_relative_to(BASE) or output.exists()
            or any(path.is_symlink() for path in (output, *output.parents))):
        raise ValueError('Use a fresh nonsymlink output outside this publication')
    external = read(BASE / 'external-onnx.json')
    expected_onnx = {key: external[key] for key in ('bytes', 'sha256')}
    if fp(onnx.absolute()) != expected_onnx:
        raise ValueError('Download the exact original final ONNX before replay')
    output.mkdir(exist_ok=False)
    artifacts = output / 'artifacts'
    artifacts.mkdir()
    transfer = read(BASE / 'transfer/receipt.json')
    originals = {Path(row['path']).name: {key: row[key] for key in ('bytes', 'sha256')}
                 for row in transfer['expected_artifacts']}
    for name in ('model_19999.pt', 'holosoma_config.yaml'):
        copy(BASE / 'artifacts' / name, artifacts / name, originals[name])
    copy(onnx.absolute(), artifacts / 'model_19999.onnx', expected_onnx)
    event = restore_event(artifacts)
    restored = inputs(artifacts)
    save(output / 'restoration.json', {'status': 'original_inputs_restored_and_verified', 'event': event,
                                      'inputs': restored, 'science_executed': False})
    verify_package()
    return output, artifacts, restored


def inspect(cid):
    value = json.loads(subprocess.check_output(['docker', 'inspect', cid]))
    if len(value) != 1 or value[0]['Id'] != cid or value[0]['Image'] != IMAGE:
        raise ValueError('Own CPU container identity differs')
    return value[0]


def run(output, onnx):
    output, artifacts, before = restore(output, onnx)
    host, validation = output / 'host', output / 'validation'
    host.mkdir()
    validation.mkdir()
    name = 'php-official-locomotion-replay-' + uuid.uuid4().hex[:12]
    argv = ['docker', 'create', '--name', name, '--runtime', 'runc', '--init', '--network', 'none',
            '--cpus', '2', '--memory', '12g', '--label', 'php.research.owner=official-locomotion-replay',
            '-e', 'CUDA_VISIBLE_DEVICES=', '-e', 'NVIDIA_VISIBLE_DEVICES=void',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'OMP_NUM_THREADS=1', '-e', 'OPENBLAS_NUM_THREADS=1',
            '-e', 'MKL_NUM_THREADS=1', '-e', 'ACCEPT_EULA=Y', '-e', 'OMNI_KIT_ACCEPT_EULA=YES']
    for source, destination, readonly in ((BASE / 'cpu-02/source', '/code', True),
        (BASE / 'cpu-02/input', '/control', True), (artifacts, '/artifacts', True), (validation, '/validation', False)):
        argv.extend(['--mount', f'type=bind,src={source},dst={destination}' + (',readonly' if readonly else '')])
    argv.extend([IMAGE, '/usr/bin/python3', '-B', '/code/run_cpu_phases.py'])
    report = {'status': 'starting', 'create_argv': argv, 'image_id': IMAGE,
              'quality_verified': False, 'official_schedule_complete': False, 'inputs_before': before}
    created = subprocess.run(argv, capture_output=True)
    (host / 'create.stdout.raw').write_bytes(created.stdout)
    (host / 'create.stderr.raw').write_bytes(created.stderr)
    report['create_returncode'] = created.returncode
    if created.returncode:
        save(host / 'execution.json', {**report, 'status': 'failed'})
        raise ValueError('CPU container creation failed')
    cid = created.stdout.decode().strip()
    if not re.fullmatch('[0-9a-f]{64}', cid):
        raise ValueError('Invalid own container ID')
    report['container_id'] = cid
    child = None
    try:
        initial = inspect(cid)
        if initial['Name'] != '/' + name or initial['HostConfig']['Runtime'] != 'runc' or initial['HostConfig']['NetworkMode'] != 'none':
            raise ValueError('CPU container isolation differs')
        save(host / 'inspect-before.json', initial)
        with (host / 'start.stdout.raw').open('xb') as stdout, (host / 'start.stderr.raw').open('xb') as stderr:
            child = subprocess.Popen(['docker', 'start', '--attach', cid], stdout=stdout, stderr=stderr)
            report['actual_attached_wait_returncode'] = child.wait()
        final = inspect(cid)
        report['actual_container_exit_code'] = final['State']['ExitCode']
        if report['actual_attached_wait_returncode'] or final['State']['Running'] or final['State']['ExitCode']:
            raise ValueError('Original CPU phases did not normally exit zero')
        phases = read(validation / 'phases.json')
        if phases['status'] != 'passed' or [row['actual_wait_returncode'] for row in phases['phases']] != [0] * 5:
            raise ValueError('All five original CPU phases must pass')
        report['inputs_after'] = inputs(artifacts)
        if report['inputs_after'] != before:
            raise ValueError('Reconstructed inputs changed')
        verify_package()
        report.update(status='passed', actual_phase_exits=[0] * 5)
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        # Only this freshly created full CID can be stopped. Inputs and outputs
        # remain for review; no Docker rm, retries or foreign-process signals.
        final = inspect(cid)
        if final['Name'] != '/' + name:
            raise ValueError('Own CPU container name differs during cleanup')
        if final['State']['Running']:
            stopped = subprocess.run(['docker', 'stop', '--time', '20', cid], capture_output=True)
            (host / 'stop.stdout.raw').write_bytes(stopped.stdout)
            (host / 'stop.stderr.raw').write_bytes(stopped.stderr)
            report['owned_cleanup_returncode'] = stopped.returncode
            final = inspect(cid)
        if child is not None and child.poll() is None:
            report['actual_attached_cleanup_wait_returncode'] = child.wait()
        save(host / 'inspect-after.json', final)
        report['container_running_after_cleanup'] = final['State']['Running']
        save(host / 'execution.json', report)
        if final['State']['Running']:
            raise ValueError('Own CPU container remains running; evidence retained')
    return {'status': report['status'], 'output': str(output), 'phase_exits': report['actual_phase_exits']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('verify')
    for command in ('restore', 'run'):
        item = sub.add_parser(command)
        item.add_argument('--output', type=Path, required=True)
        item.add_argument('--onnx', type=Path, required=True,
                          help='Exact externally downloaded model_19999.onnx, checked before any Docker action')
    args = parser.parse_args()
    if args.command == 'verify':
        value = {'status': 'publication_verified', 'files': len(verify_package()['files']), 'science_executed': False}
    elif args.command == 'restore':
        output, _, restored = restore(args.output, args.onnx)
        value = {'status': 'original_inputs_restored_and_verified', 'output': str(output), 'inputs': len(restored), 'science_executed': False}
    else:
        value = run(args.output, args.onnx)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
