"""Operator-run acceptance of a full baked image; no host scientific imports."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/dzp/projects/php_parkour')
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', args.image_id)
    assert re.fullmatch(r'[0-9a-f]{40}', args.revision)
    base = args.output.resolve()
    assert not base.exists()
    base.mkdir(parents=True)
    (base / 'cache').mkdir()
    report = {'status': 'starting', 'observed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'image_id': args.image_id, 'revision': args.revision, 'gpu_uuid': GPU,
              'no_source_bind': True, 'network_mode': 'none', 'quality_verified': False,
              'scope': 'Baked image imports, pinned environments, actual16env2iter Isaac training, weights, teacher ONNX CPU and TensorBoard; no convergence or full schedule',
              'commands': []}
    cid = None

    def write():
        (base / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')

    def command(argv, name, timeout=120, accepted=(0,)):
        row = {'argv': argv, 'started_unix': time.time(), 'log': name}
        report['commands'].append(row)
        write()
        with (base / name).open('x') as stream:
            process = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        row.update(returncode=process.returncode, finished_unix=time.time(), log_sha256=sha(base / name))
        write()
        assert process.returncode in accepted, (name, process.returncode)

    def capture(argv):
        return subprocess.check_output(argv, text=True, timeout=40)

    def inspect():
        obj = json.loads(capture(['docker', 'inspect', '--type', 'container', cid]))[0]
        assert obj['Id'] == cid and obj['Image'] == args.image_id
        host = obj['HostConfig']
        assert host['NetworkMode'] == 'none' and host['IpcMode'] == 'private' and host.get('PidMode', '') == ''
        assert host['Init'] is True and host['ShmSize'] == 8 * 1024**3 and not host['Privileged']
        assert len(host['DeviceRequests']) == 1 and host['DeviceRequests'][0]['DeviceIDs'] == [GPU]
        mounts = {m['Destination']: m for m in obj['Mounts']}
        assert set(mounts) == {'/data/assets', '/data/cache', '/outputs'}
        assert mounts['/data/assets']['RW'] is False
        assert mounts['/outputs']['Source'] == str(base) and mounts['/outputs']['RW'] is True
        return obj

    write()
    try:
        image = json.loads(capture(['docker', 'image', 'inspect', args.image_id]))[0]
        assert image['Config']['Labels']['org.opencontainers.image.revision'] == args.revision
        assert image['Config']['Labels']['org.php-parkour.source-dirty'] == 'false'
        (base / 'image-inspect.json').write_text(json.dumps(image, indent=2) + '\n')
        active = capture(['nvidia-smi', '-i', GPU, '--query-compute-apps=pid', '--format=csv,noheader']).strip()
        assert not active, 'Local GPU compute process active; do not start acceptance'
        name = 'php-sdk018-offline-' + hashlib.sha256(str(base).encode()).hexdigest()[:14]
        create = ['docker', 'create', '--name', name, '--gpus', 'device=' + GPU,
                  '--network', 'none', '--ipc', 'private', '--init', '--shm-size', '8g',
                  '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'HF_HUB_OFFLINE=1', '-e', 'WANDB_MODE=disabled',
                  '-e', 'OMP_NUM_THREADS=4', '-e', 'LOGGER=tensorboard',
                  '--mount', 'type=bind,src=' + str(ROOT / 'outputs/research/assets') + ',dst=/data/assets,readonly',
                  '--mount', 'type=bind,src=' + str(base / 'cache') + ',dst=/data/cache',
                  '--mount', 'type=bind,src=' + str(base) + ',dst=/outputs',
                  '-w', '/workspace/php_parkour', '--entrypoint', '/bin/bash', args.image_id,
                  '-lc', 'exec sleep infinity']
        report['create_argv'] = create
        write()
        cid = capture(create).strip()
        assert re.fullmatch(r'[0-9a-f]{64}', cid)
        report['container_id'] = cid
        command(['docker', 'start', cid], 'container-start.log')
        (base / 'container-inspect.json').write_text(json.dumps(inspect(), indent=2) + '\n')
        command(['docker', 'exec', cid, '/opt/php/bin/train-python', 'scripts/research/verify_runtime.py',
                 '--require-gpu', '--output', '/outputs/runtime.json'], 'doctor.log')
        runtime = json.loads((base / 'runtime.json').read_text())
        assert runtime['passed'] and all(runtime[r]['versions']['unitree_sdk_version'] == '0.1.8' for r in ('train', 'inference'))
        sdk_code = "import hashlib,importlib.metadata as md,json,pathlib,unitree_interface; p=list(pathlib.Path(unitree_interface.__file__).parent.glob('unitree_interface.cpython-*.so'));assert len(p)==1;print(json.dumps({'version':md.version('far-unitree-sdk'),'extension':str(p[0]),'sha256':hashlib.sha256(p[0].read_bytes()).hexdigest()}))"
        sdk = {}
        for runtime_name, expected in [('train', '9304320e194ca6fb0bc4f85699a533bcc3051f577bd823914903aedc9b1b0926'), ('inference', 'fdedc667b19b8257c4a2e2cc70d8a99c65e9425d29366426f73a75ac1d5664d4')]:
            command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid, '/opt/php/bin/' + runtime_name + '-python', '-c', sdk_code], runtime_name + '-sdk.json')
            row = json.loads((base / (runtime_name + '-sdk.json')).read_text().strip().splitlines()[-1])
            assert row['version'] == '0.1.8' and row['sha256'] == expected
            sdk[runtime_name] = row
        report['sdk'] = sdk
        for runtime_name in ('train', 'motion', 'inference'):
            command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid,
                     '/opt/php/bin/' + runtime_name + '-python', '-m', 'pip', 'freeze'], runtime_name + '.freeze.txt')
            command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid,
                     '/opt/php/bin/' + runtime_name + '-python', '-m', 'pip', 'check'], runtime_name + '-pip-check.log', accepted=(1,) if runtime_name == 'train' else (0,))
        conflicts = (base / 'train-pip-check.log').read_text().splitlines()
        assert len(conflicts) == 3 and all(any(line.startswith(prefix) for prefix in ('nvidia-srl-usd ', 'nvidia-srl-usd-to-urdf ', 'dex-retargeting ')) for line in conflicts)
        report['pip_check'] = {'motion': 0, 'inference': 0, 'train': 1, 'train_known_metadata_conflicts': conflicts}
        code = '''import hashlib,importlib.metadata as md,json,pathlib,re
root=pathlib.Path('/workspace/php_parkour'); forbidden=[str(p) for p in [root/'.git',root/'outputs',root/'.env.local',root/'thirdparty/holosoma/.git'] if p.exists()]; assert not forbidden
out={}
for name in ('train-added','motion','inference'):
 p=pathlib.Path('/opt/php-build/constraints.'+name+'.txt'); items={}
 for line in p.read_text().splitlines():
  line=line.split('#',1)[0].strip()
  if line: a,b=line.split('==');items[re.sub(r'[-_.]+','-',a).lower()]=b
 out[name]={'count':len(items),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pins':items}
pathlib.Path('/outputs/baked-source-and-pins.json').write_text(json.dumps({'forbidden_paths':forbidden,'constraints':out},indent=2)+'\\n')
'''
        command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid, '/opt/php/bin/train-python', '-c', code], 'baked-source-and-pins.log')
        pins = json.loads((base / 'baked-source-and-pins.json').read_text())['constraints']
        for runtime_name in ('train', 'motion', 'inference'):
            actual = {}
            for line in (base / (runtime_name + '.freeze.txt')).read_text().splitlines():
                if '==' in line:
                    key, value = line.split('==', 1)
                    actual[re.sub(r'[-_.]+', '-', key).lower()] = value
            expected = pins['train-added' if runtime_name == 'train' else runtime_name]['pins']
            assert all(actual.get(key) == value for key, value in expected.items()), runtime_name
        report['matched_dependency_pins'] = {k: v['count'] for k, v in pins.items()}
        command(['docker', 'exec', cid, '/opt/php/bin/train-python', 'scripts/research/train_pipeline.py',
                 'teachers', '--profile', 'smoke', '--skills', 'locomotion', '--num-envs', '16',
                 '--iterations', '2', '--output', '/outputs/training'], 'train-driver.log', timeout=600)
        stage = json.loads((base / 'training/smoke/manifests/teacher-locomotion.json').read_text())
        assert stage['status'] == 'passed' and stage['returncode'] == 0 and stage['checkpoint_iteration'] == 1
        native = Path(stage['checkpoint'])
        command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid, '/opt/php/bin/train-python',
                 'scripts/research/verify_weight_update.py', '--before', str(native.with_name('model_00000.pt')),
                 '--after', str(native), '--output', '/outputs/weight-update.json'], 'weight-update.log')
        command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid, '/opt/php/bin/inference-python',
                 'scripts/research/validate_teacher_onnx.py', '--model', str(native.with_suffix('.onnx')),
                 '--output', '/outputs/teacher-onnx.json'], 'teacher-onnx.log')
        code = '''import json,math,pathlib
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
p=next(pathlib.Path('/outputs/training').rglob('events.out.tfevents.*'));e=EventAccumulator(str(p),size_guidance={'scalars':0});e.Reload();tags=e.Tags()['scalars'];assert tags
rows={t:{'samples':len(e.Scalars(t)),'steps':[s.step for s in e.Scalars(t)],'all_finite':all(math.isfinite(s.value) for s in e.Scalars(t))} for t in tags};assert all(r['all_finite'] for r in rows.values());assert all(t in rows for t in ('Loss/Value','Loss/Surrogate','Loss/Entropy','Train/mean_reward'))
pathlib.Path('/outputs/tensorboard.json').write_text(json.dumps({'status':'passed','event':str(p),'tags':rows},indent=2)+'\\n')
'''
        command(['docker', 'exec', '-e', 'CUDA_VISIBLE_DEVICES=', cid, '/opt/php/bin/train-python', '-c', code], 'tensorboard.log')
        report.update(status='passed', native_training=stage, finite_weight_update_verified=True,
                      teacher_onnx_cpu_passed=True, tensorboard_finite_passed=True)
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if cid is not None:
            try:
                inspect()
                report['owned_container_stop'] = capture(['docker', 'stop', '--time', '20', cid]).strip()
                info = inspect()
                report['owned_container_running_after_stop'] = info['State']['Running']
                assert not info['State']['Running']
                (base / 'container-final-inspect.json').write_text(json.dumps(info, indent=2) + '\n')
            except BaseException as error:
                report.update(status='failed', cleanup_error=f'{type(error).__name__}: {error}')
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write()
    print(json.dumps({k: report[k] for k in ('status', 'image_id', 'container_id', 'quality_verified')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
