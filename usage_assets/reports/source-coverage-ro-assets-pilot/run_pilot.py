#!/usr/bin/env python3
"""Root-operated once-only one-source Isaac pilot; this file does not run at import."""
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

BASE = Path(__file__).resolve().parent
ROOT = Path('/home/dzp/projects/php_parkour')
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
NAME = 'php-source-coverage-ro-assets-pilot-01'
NATIVE_PLAN = '/outputs/teacher/plan.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(argv, timeout=45):
    return subprocess.check_output(argv, text=True, timeout=timeout)


def verify_prepared():
    ready = json.loads((BASE / 'readiness.json').read_text())
    if ready['status'] != 'cpu_preflight_passed_gpu_not_run' or ready['image_id'] != IMAGE or ready['gpu_uuid'] != GPU:
        raise ValueError('Pilot CPU readiness/image/GPU identity mismatch')
    for row in ready['sealed_inputs']:
        p = Path(row['path'])
        if not p.is_file() or p.is_symlink() or digest(p) != row['sha256'] or p.stat().st_size != row['bytes']:
            raise ValueError(f'Prepared input changed: {p}')
    if digest(__file__) != ready['runner_sha256']:
        raise ValueError('Root-only runner changed after readiness')
    for name in ('native-first-attempt-summary.json',):
        if (BASE / 'run-output/teacher' / name).exists():
            raise ValueError('An actual native attempt already exists; preserve it and prepare a new cohort')
    return ready


def main():
    ready = verify_prepared()
    out = BASE / 'gpu-host-01'
    out.mkdir(exist_ok=False)
    record = {'schema_version': 1, 'status': 'starting', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'image_id': IMAGE, 'gpu_uuid': GPU, 'readiness_sha256': digest(BASE / 'readiness.json'),
              'scope': 'One exact source, original iter500 teacher,1env/1variant/seed42/fullsource cap. Skill quality remains false.',
              'quality_verified': False, 'commands': []}
    cid = None
    stop_sampling = threading.Event()
    sampler = None

    def write():
        (out / 'launch.json').write_text(json.dumps(record, indent=2) + '\n')

    expected = {
        '/workspace/php_parkour': (str(BASE / 'source'), False),
        '/data/assets': (str(ROOT / 'outputs/research/assets'), False),
        '/data/pilot-checkpoint': (ready['checkpoint_directory'], False),
        '/outputs': (str(BASE / 'run-output'), True),
        '/data/cache': (str(BASE / 'cache'), True),
    }

    def inspect_owned():
        obj = json.loads(capture(['docker', 'inspect', '--type', 'container', cid]))[0]
        if (obj['Id'] != cid or obj['Image'] != IMAGE or obj['Name'] != '/' + NAME
                or obj['Config']['WorkingDir'] != '/workspace/php_parkour'
                or obj['Config']['Entrypoint'] != ['/bin/bash']
                or obj['HostConfig']['NetworkMode'] != 'none' or obj['HostConfig']['IpcMode'] != 'private'
                or obj['HostConfig'].get('PidMode', '') != ''
                or [x['DeviceIDs'] for x in obj['HostConfig']['DeviceRequests']] != [[GPU]]):
            raise ValueError('Owned container identity/namespace/device contract changed')
        if {m['Destination']: (m['Source'], m['RW']) for m in obj['Mounts']} != expected:
            raise ValueError('Owned container RO-source/RO-input/RW-output mount contract changed')
        return obj

    def sample_memory():
        with (out / 'gpu-memory.jsonl').open('x') as stream:
            while not stop_sampling.is_set():
                row = {'utc': dt.datetime.now(dt.timezone.utc).isoformat()}
                try:
                    row['gpu'] = capture(['nvidia-smi', '-i', GPU, '--query-gpu=uuid,memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'], 10).strip()
                    row['compute'] = capture(['nvidia-smi', '-i', GPU, '--query-compute-apps=pid,process_name,used_memory', '--format=csv,noheader,nounits'], 10).strip()
                except Exception as error:
                    row['sampling_error'] = f'{type(error).__name__}: {error}'
                stream.write(json.dumps(row) + '\n'); stream.flush()
                stop_sampling.wait(1)

    write()
    with (ROOT / ('outputs/research/.local-native-' + GPU + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            verify_prepared()
            if capture(['nvidia-smi', '-i', GPU, '--query-compute-apps=pid', '--format=csv,noheader']).strip():
                raise ValueError('The selected GPU has an active compute process; no native pilot was started')
            command = ['docker', 'create', '--name', NAME, '--gpus', 'device=' + GPU,
                       '--network', 'none', '--ipc', 'private', '--init', '--shm-size', '8g',
                       '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'HF_HUB_OFFLINE=1', '-e', 'WANDB_MODE=disabled',
                       '-e', 'LOGGER=tensorboard', '-e', 'OMP_NUM_THREADS=4', '-e', 'PYTHONUNBUFFERED=1']
            for target, (source, rw) in expected.items():
                command += ['--mount', 'type=bind,src=' + source + ',dst=' + target + ('' if rw else ',readonly')]
            command += ['-w', '/workspace/php_parkour', '--entrypoint', '/bin/bash', IMAGE, '-lc', 'exec sleep infinity']
            record['create_argv'] = command; write()
            cid = capture(command).strip(); record['container_id'] = cid; write()
            capture(['docker', 'start', cid])
            (out / 'container-inspect.json').write_text(json.dumps(inspect_owned(), indent=2) + '\n')
            visible = capture(['docker', 'exec', cid, 'nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader']).splitlines()
            if visible != [GPU]:
                raise ValueError('Actual visible GPU UUID differs')
            record['actual_gpu_uuids'] = visible
            code = "from pathlib import Path; import json; from scripts.research.eval_source_coverage import verify_plan,validate_cpu_report; p=verify_plan(Path('/outputs/teacher/plan.json')); c=json.loads(Path(p['cases'][0]['case']['path']).read_text()); validate_cpu_report(json.loads((Path(c['output'])/'cpu-preflight/report.json').read_text()),c); print('Actual CPU plan/report/source/asset contract verified; no native object instantiated')"
            record['same_container_cpu_gate'] = capture(['docker', 'exec', cid, '/opt/php/bin/train-python', '-c', code], 120)
            sampler = threading.Thread(target=sample_memory, daemon=True); sampler.start()
            argv = ['docker', 'exec', '-w', '/workspace/php_parkour', cid, '/opt/php/bin/train-python', 'scripts/research/eval_source_coverage.py', 'run', '--plan', NATIVE_PLAN]
            record['commands'].append({'argv': argv, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat()}); write()
            with (out / 'native-driver.log').open('x') as stream:
                completed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
            record['commands'][-1].update(returncode=completed.returncode, log_sha256=digest(out / 'native-driver.log'))
            summary_path = BASE / 'run-output/teacher/native-first-attempt-summary.json'
            record['native_summary_sha256'] = digest(summary_path) if summary_path.is_file() else None
            if completed.returncode != 0:
                raise RuntimeError('Native first-attempt driver failed; all partial evidence retained')
            summary = json.loads(summary_path.read_text())
            if summary['status'] != 'completed' or summary['execution_passed'] != 1 or len(summary['cases']) != 1:
                raise ValueError('Expected one real completed execution, independently of tracking quality')
            record['native_case'] = summary['cases'][0]
            for row in ready['sealed_inputs']:
                if digest(row['path']) != row['sha256']:
                    raise ValueError('A sealed source/input changed during the native attempt')
            record['source_and_input_bytes_unchanged'] = True
            record['status'] = 'native_execution_completed_pending_independent_evidence_validation'
        except BaseException as error:
            record.update(status='execution_failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            stop_sampling.set()
            if sampler is not None:
                sampler.join(timeout=25)
            if cid is not None:
                try:
                    inspect_owned()
                    record['owned_container_stop'] = capture(['docker', 'stop', '--time', '20', cid], 65).strip()
                    obj = inspect_owned()
                    if obj['State']['Running']:
                        raise ValueError('Owned container still running')
                    record['owned_container_running_after_stop'] = False
                    (out / 'container-final-inspect.json').write_text(json.dumps(obj, indent=2) + '\n')
                except BaseException as error:
                    record.update(status='execution_failed', cleanup_error=f'{type(error).__name__}: {error}')
            record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat(); write()
    print(json.dumps({key: record.get(key) for key in ('status', 'container_id', 'quality_verified')}))
    return 0 if record['status'].startswith('native_execution_completed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
