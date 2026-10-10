"""One fresh runc import/config preflight, no native objects or GPU."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/dzp/projects/php_parkour')
BASE = ROOT / 'outputs/research/native-keyboard-reset-allkeys-cohort-01'
COHORT = BASE / 'cohort'
OUTPUT = BASE / 'host/root-cpu-preflight-01'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(argv):
    return subprocess.check_output(argv, text=True).strip()


def main():
    plan = json.loads((COHORT / 'plan.json').read_text())
    assert plan['plan_sha256'] == '422ac089d4208477f0b3822ddbc7aa03268ee2a6e5395868d6dd1473355e2bc8'
    assert plan['image_id'] == IMAGE and plan['status'] == 'prepared_not_executed'
    OUTPUT.mkdir(exist_ok=False)
    (OUTPUT / 'outputs').mkdir()
    (OUTPUT / 'cache').mkdir()
    cid = None
    name = 'php-allkeys-root-cpu-' + plan['token'][:12]
    record = {'status': 'starting', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'Exact prepared source imports and CLI parsing only; no native object, listener, GUI, DDS or GPU',
              'helper_sha256': sha(__file__), 'plan_sha256': sha(COHORT / 'plan.json'), 'native_started': False}
    expected = {'/workspace/php_parkour': (str(COHORT / 'source'), False),
                '/data/assets': (str(COHORT / 'assets'), False),
                '/outputs': (str(OUTPUT / 'outputs'), True), '/data/cache': (str(OUTPUT / 'cache'), True)}

    def save():
        (OUTPUT / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    def inspect_owned():
        obj = json.loads(capture(['docker', 'inspect', cid]))[0]
        assert obj['Id'] == cid and obj['Image'] == IMAGE and obj['Name'] == '/' + name
        h = obj['HostConfig']
        assert h['Runtime'] == 'runc' and h['NetworkMode'] == 'none' and h['IpcMode'] == 'private'
        assert not h.get('DeviceRequests') and not h.get('PidMode')
        assert {m['Destination']: (m['Source'], m['RW']) for m in obj['Mounts']} == expected
        return {k: obj[k] for k in ('Id', 'Name', 'Image', 'State', 'HostConfig', 'Mounts')}

    def verify_files():
        for row in plan['files']:
            p = COHORT / row['relative']
            assert p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], p

    try:
        verify_files()
        argv = ['docker', 'create', '--name', name, '--runtime', 'runc', '--network', 'none',
                '--ipc', 'private', '--init', '--shm-size', '1g', '--entrypoint', '/bin/bash',
                '-w', '/workspace/php_parkour']
        for key, value in {'CUDA_VISIBLE_DEVICES': '', 'NVIDIA_VISIBLE_DEVICES': 'void',
                           'PYTHONDONTWRITEBYTECODE': '1', 'WANDB_MODE': 'disabled', 'WANDB_DISABLED': 'true',
                           'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                           'PHP_GUI_TOKEN': plan['token'], 'MUJOCO_GL': 'egl'}.items():
            argv += ['--env', key + '=' + value]
        for target, (source, rw) in expected.items():
            argv += ['--mount', 'type=bind,src=' + source + ',dst=' + target + ('' if rw else ',readonly')]
        argv += [IMAGE, '-lc', 'exec sleep infinity']
        record['create_argv'] = argv; save()
        cid = capture(argv); record['container_id'] = cid; save()
        capture(['docker', 'start', cid])
        (OUTPUT / 'running-inspect.json').write_text(json.dumps(inspect_owned(), indent=2) + '\n')
        record['roles'] = []
        for role, python in [('simulator', '/opt/php/bin/train-python'), ('inference', '/opt/php/bin/inference-python')]:
            argv = ['docker', 'exec', cid, python,
                    '/workspace/php_parkour/scripts/research/gui_audit/cpu_preflight.py', '--role', role]
            with (OUTPUT / (role + '.log')).open('x') as log:
                result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
            row = {'role': role, 'argv': argv, 'returncode': result.returncode, 'log_sha256': sha(OUTPUT / (role + '.log'))}
            record['roles'].append(row); save()
            assert result.returncode == 0, role
            report = OUTPUT / 'outputs' / (role + '-cpu-preflight.json')
            payload = json.loads(report.read_text())
            assert payload['status'] == 'passed' and payload['native_objects_constructed'] is False
            row['report_sha256'] = sha(report)
        verify_files()
        record['sealed_files_verified_before_after'] = len(plan['files'])
        record['status'] = 'passed_import_and_config_only'
    except BaseException as error:
        record.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        if cid is not None:
            inspect_owned()
            capture(['docker', 'stop', '--time', '20', cid])
            after = inspect_owned()
            assert not after['State']['Running']
            (OUTPUT / 'stopped-inspect.json').write_text(json.dumps(after, indent=2) + '\n')
            record['running_after_stop'] = False
            capture(['docker', 'rm', cid]); record['own_container_removed'] = True
        record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
    print(json.dumps({k: record.get(k) for k in ('status', 'sealed_files_verified_before_after', 'native_started', 'own_container_removed')}))


if __name__ == '__main__':
    main()
