#!/usr/bin/env python3
"""One CPU-only generation of the real reference629 plan; no native rollout."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import time
import uuid

ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
BASE = Path(__file__).resolve().parent
PREP = ROOT / 'outputs/research/reference629-preparation-01'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
PINS = {
    'sim2sim.py': '023fed0f9f31f79b506b370a96013c18e8b1c94239e0504eca4bcea6076c3f4d',
    'reference_commands.py': '1af208fc1f57bac61d37256a4bdbb20fa45b05817291c3372c92b5a8c3807d57',
    'sim2sim_scene_matrix.py': '599c75df14c5ac902d57f88bfd3d752317e332abce5751153bef8d20d8d0bb70',
}
MATRIX_SHA = 'ed413845f4b82156964e11ad6ee3faca30e3c0b10dbfdc295a8284f9ee3308ed'


def fp(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected regular input: ' + str(path))
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    raw = json.dumps(value, indent=2, allow_nan=False) + '\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(raw)
    temporary.replace(path)


def command(label, argv):
    before = time.time()
    with (BASE / (label + '.stdout')).open('xb') as out, (BASE / (label + '.stderr')).open('xb') as err:
        child = subprocess.Popen(argv, stdout=out, stderr=err)
        rc = child.wait()
    record = {'argv': argv, 'actual_wait_returncode': rc, 'started_unix': before,
              'finished_unix': time.time(), 'launcher_child_pid': child.pid,
              'stdout': fp(BASE / (label + '.stdout')), 'stderr': fp(BASE / (label + '.stderr'))}
    save(BASE / (label + '.json'), record)
    if rc:
        raise RuntimeError(label + ' returned ' + str(rc))
    return (BASE / (label + '.stdout')).read_text()


def sources():
    records = {name: fp(ROOT / 'scripts/research' / name) for name in PINS}
    for name, record in records.items():
        if record['sha256'] != PINS[name]:
            raise ValueError('Frozen source changed: ' + name)
    record = fp(OLD / 'inputs/matrix.json')
    if record['sha256'] != MATRIX_SHA:
        raise ValueError('Frozen matrix changed')
    return {'sources': records, 'source_matrix': record, 'old_freeze_manifest': fp(OLD / 'freeze-manifest.json')}


def main():
    token = uuid.uuid4().hex
    name = 'php-reference629-cpu-plan-' + token[:12]
    receipt = {'schema_version': 1, 'scope': 'CPU plan only; no native workers or GPU',
               'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'image_id': IMAGE, 'container_name': name, 'owner_token': token,
               'native_started': False, 'gpu_requested': False, 'status': 'preparing'}
    cid = None
    checks = BASE / 'checks'
    checks.mkdir()
    (PREP / 'overlay').mkdir(parents=True)
    receipt['inputs_before'] = sources()
    for filename in PINS:
        destination = PREP / 'overlay' / filename
        with destination.open('xb') as stream:
            stream.write((ROOT / 'scripts/research' / filename).read_bytes())
        if fp(destination)['sha256'] != PINS[filename]:
            raise ValueError('Overlay copy changed: ' + filename)
    receipt['overlay_before'] = {name: fp(PREP / 'overlay' / name) for name in PINS}
    save(BASE / 'launch-receipt.json', receipt)
    try:
        argv = ['docker', 'create', '--name', name, '--label', 'php.reference629.cpu-owner=' + token,
                '--runtime', 'runc', '--network', 'none', '--ipc', 'private', '--init', '--shm-size', '1g',
                '--workdir', '/workspace/php_parkour', '--entrypoint', '/opt/php/bin/inference-python']
        for key, value in {'NVIDIA_VISIBLE_DEVICES': 'void', 'CUDA_VISIBLE_DEVICES': '',
                           'PYTHONDONTWRITEBYTECODE': '1', 'PHP_DOCKER': '1', 'WANDB_MODE': 'disabled',
                           'WANDB_DISABLED': 'true', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}.items():
            argv += ['--env', key + '=' + value]
        for host, container, mode in [(OLD / 'source', '/workspace/php_parkour', 'ro'),
                                      (PREP / 'overlay', '/workspace/php_parkour/scripts/research', 'ro'),
                                      (OLD / 'inputs', '/data', 'ro'), (checks, '/checks', 'rw')]:
            argv += ['--mount', 'type=bind,src=' + str(host) + ',dst=' + container + (',readonly' if mode == 'ro' else '')]
        argv += [IMAGE, '-B', '/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py',
                 '--matrix', '/data/matrix.json', '--models', '/data/assets/student',
                 '--output', '/outputs/reference629', '--all-configs', '--reference-commands', '--plan',
                 '--plan-output', '/checks/reference629-plan.json', '--image-id', IMAGE, '--gl', 'egl']
        cid = command('create', argv).strip()
        if len(cid) != 64 or any(character not in '0123456789abcdef' for character in cid):
            raise ValueError('Docker did not return a full container ID')
        receipt['container_id'] = cid
        before = json.loads(command('inspect-created', ['docker', 'inspect', cid]))[0]
        if (before['Image'] != IMAGE or before['HostConfig']['Runtime'] != 'runc'
                or before['HostConfig']['NetworkMode'] != 'none' or before['HostConfig'].get('DeviceRequests')
                or before['Config']['Labels'].get('php.reference629.cpu-owner') != token):
            raise ValueError('Unexpected CPU container identity/runtime')
        receipt['created_identity'] = {'id': before['Id'], 'image': before['Image'], 'name': before['Name'],
                                       'created': before['Created'], 'owner_token': token}
        save(BASE / 'launch-receipt.json', receipt)
        command('start-attached', ['docker', 'start', '-a', cid])
        wait = command('wait', ['docker', 'wait', cid]).strip()
        terminal = json.loads(command('inspect-terminal', ['docker', 'inspect', cid]))[0]
        if wait != '0' or terminal['State']['Running'] or terminal['State']['ExitCode'] != 0:
            raise ValueError('Actual CPU container did not finish with zero exit')
        receipt['container_exit_code'] = terminal['State']['ExitCode']
        receipt['plan'] = fp(checks / 'reference629-plan.json')
        receipt['status'] = 'cpu_reference_plan_completed'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if cid:
            current = json.loads(command('inspect-cleanup', ['docker', 'inspect', cid]))[0]
            if (current['Id'] != cid or current['Image'] != IMAGE
                    or current['Config']['Labels'].get('php.reference629.cpu-owner') != token):
                raise ValueError('Refuse cleanup of non-owned container')
            if current['State']['Running']:
                command('stop-owned', ['docker', 'stop', '--time', '10', cid])
                current = json.loads(command('inspect-stopped', ['docker', 'inspect', cid]))[0]
            if current['State']['Running']:
                raise ValueError('Own CPU container still running')
            receipt['owned_container_running_after_stop'] = False
            command('remove-owned', ['docker', 'rm', cid])
            receipt['owned_container_removed'] = True
        receipt['inputs_after'] = sources()
        receipt['overlay_after'] = {name: fp(PREP / 'overlay' / name) for name in PINS}
        if (receipt['inputs_after'] != receipt['inputs_before']
                or receipt['overlay_after'] != receipt['overlay_before']):
            receipt['status'] = 'failed'
            receipt['error'] = 'RO input or overlay changed'
        receipt['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(BASE / 'launch-receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'plan': receipt.get('plan'), 'native_started': False}))


if __name__ == '__main__':
    main()
