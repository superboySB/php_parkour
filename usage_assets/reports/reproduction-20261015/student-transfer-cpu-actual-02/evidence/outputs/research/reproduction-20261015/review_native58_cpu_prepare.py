#!/usr/bin/env python3
"""Read the actual original CPU-prepared58 cohort; never run a simulation."""
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/dzp/projects/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
BASE = ROOT / 'outputs/research/final-student-native58-delivery-recovered-01'
PREP = ROOT / 'outputs/research/final-student-native58-recovered-preparation-01'
OUT = WORK / 'native58-cpu-prepare-root-review-01'


def require(value, message):
    if not value:
        raise ValueError(message)


def fp(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Missing/aliased input')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    OUT.mkdir(exist_ok=False)
    sys.path.insert(0, str(PREP))
    import native58
    require(fp(PREP / 'native58.py')['sha256'] == '31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43', 'Original adapter differs')
    plan = read(BASE / 'host-plan.json')
    require(not (BASE / 'host/launch-receipt.json').exists() and not list((BASE / 'phases').iterdir()), 'Native attempt already exists')
    count = native58.verify_snapshot(BASE, plan)
    freeze = read(BASE / 'freeze-manifest.json')['files']
    actual = {p.relative_to(BASE).as_posix() for group in ('source', 'inputs', 'control', 'host') for p in (BASE / group).rglob('*') if p.is_file()}
    require(actual == {row['relative'] for row in freeze} and len(actual) == count, 'Complete frozen file set differs')
    before = [fp(BASE / row['relative']) for row in freeze]
    parent_path = WORK / 'student-native58-cpu-prepare-host-01/original-parent/process-exit.json'
    parent = read(parent_path)
    require(parent['actual_wait_returncode'] == 0 and parent['pending_signals'] == [] and parent['helper_sha256'] == fp(PREP / 'native58.py')['sha256'], 'Actual original CPU parent wait failed')
    require(parent['argv'][:4] == ['/usr/bin/python3', '-B', str(PREP / 'native58.py'), 'prepare'] and parent['argv'][-2:] == ['--output', str(BASE)], 'Actual original prepare argv differs')
    require(parent['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'CPU preparation boot changed')
    phases = []
    for kind in ('pure', 'finetune'):
        where = BASE / 'host' / ('cpu-' + kind)
        launch, summary, ort = [read(where / name) for name in ('launch.json', 'summary.json', 'onnx.json')]
        require(launch['status'] == 'passed' and launch['returncode'] == launch['container_exit_code'] == 0 and launch['owned_container_stop']['running_after_stop'] is False, 'Original CPU exit/stopped receipt failed')
        require(summary['status'] == ort['status'] == 'passed' and summary['ort_cases'] == len(ort['cases']) == 30 and summary['directions_cases'] == 12 and summary['scene_cases'] == 17 and not summary['native_started'] and not summary['gpu_started'], 'Actual CPU counts/scope failed')
        require(all(math.isfinite(row[key]) for row in ort['cases'] for key in ('action_min', 'action_max', 'action_l2')) and all(row['output_shapes'][0] == [1, 29] for row in ort['cases']), 'Actual ONNX samples nonfinite/wrong shape')
        models = {Path(row['path']).name: (row['bytes'], row['sha256']) for row in plan['origin_transfer']['models'] if row['kind'] == kind}
        require({Path(row['path']).name: (row['bytes'], row['sha256']) for row in ort['models']} == models, 'CPU model differs from completed fetch')
        pose = ort['native_default_pose_compatibility']
        require(pose['status'] == 'passed' and len(pose['native_joint_names']) == 29 and len(pose['model_joint_names']) == 29 and math.isfinite(pose['max_default_pose_absolute_error']) and pose['max_default_pose_absolute_error'] <= .000501, 'Default deployment pose mismatch')
        cid = launch['container_id']
        argv = ['docker', 'container', 'inspect', cid]
        proc = subprocess.run(argv, capture_output=True)
        (OUT / (kind + '.inspect.stdout.raw')).write_bytes(proc.stdout)
        (OUT / (kind + '.inspect.stderr.raw')).write_bytes(proc.stderr)
        require(proc.returncode == 0, 'Fresh exact CPU inspect failed')
        info = json.loads(proc.stdout)[0]
        require(info['Id'] == cid and info['Image'] == plan['image_id'] and not info['State']['Running'] and info['State']['ExitCode'] == 0 and not info['State']['OOMKilled'] and not info['State']['Error'], 'Fresh CPU state differs')
        require(info['HostConfig']['Runtime'] == 'runc' and info['HostConfig']['NetworkMode'] == 'none' and not info['HostConfig'].get('DeviceRequests') and not info['HostConfig'].get('Devices'), 'CPU isolation differs')
        require(all(not row['RW'] or row['Destination'] == '/preflight' for row in info['Mounts']), 'Unexpected CPU writable mount')
        require(info['State']['StartedAt'] == read(where / 'container-inspect.json')['State']['StartedAt'], 'CPU birth differs')
        phases.append({'kind': kind, 'ort_cases': 30, 'models': ort['models'], 'pose': pose, 'container_id': cid, 'started_at': info['State']['StartedAt'], 'state': info['State'], 'fresh_inspect_argv': argv, 'actual_inspect_wait_returncode': proc.returncode, 'fresh_inspect_stdout': fp(OUT / (kind + '.inspect.stdout.raw'))})
    require([fp(BASE / row['relative']) for row in freeze] == before, 'Frozen inputs changed during actual review')
    save(OUT / 'review.json', {'status': 'passed_readonly_native58_cpu_preparation_review', 'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'reviewer_source': fp(__file__), 'must_fix': [], 'plan': fp(BASE / 'host-plan.json'), 'freeze': fp(BASE / 'freeze-manifest.json'), 'frozen_files': count, 'actual_parent_wait': fp(parent_path), 'phases': phases, 'cpu_ort_cases': 60, 'native_started': False, 'gpu_started': False, 'scope': 'Actual original CPU preparation only. Failed old delivery and historical boot mismatch retained. New host crossboot gate/actual native execution still required.'})
    print(json.dumps({'status': 'passed_readonly_native58_cpu_preparation_review', 'frozen_files': count, 'cpu_ort_cases': 60, 'review': fp(OUT / 'review.json')}))


if __name__ == '__main__':
    main()
