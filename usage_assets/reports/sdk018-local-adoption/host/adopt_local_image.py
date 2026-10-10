import datetime as dt
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/dzp/projects/php_parkour')
BASE = ROOT / 'outputs/research/sdk018-local-adoption-01'
assert not BASE.exists()
BASE.mkdir()
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
record = {'status': 'starting', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'commands': [],
          'scope': 'Adopt fully verified SDK018 image for idle local default container; preserve cloud/independent native containers'}


def write():
    (BASE / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')


def command(argv, name, timeout=60):
    r = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    (BASE / name).write_text(r.stdout)
    record['commands'].append({'argv': argv, 'returncode': r.returncode, 'log': name})
    write()
    r.check_returncode()
    return r.stdout


def containers():
    names = subprocess.check_output(['docker', 'ps', '-aq'], text=True).split()
    return json.loads(subprocess.check_output(['docker', 'inspect', '--type', 'container', *names], text=True))


write()
try:
    before = containers()
    old = [c for c in before if c['Name'] == '/php-parkour-research']
    assert len(old) == 1 and old[0]['State']['Running']
    old = old[0]
    (BASE / 'container-before.json').write_text(json.dumps(old, indent=2) + '\n')
    top = command(['docker', 'top', old['Id'], '-eo', 'pid,ppid,args'], 'before-processes.log')
    lines = top.splitlines()[1:]
    assert len(lines) == 4
    assert all('sleep infinity' in s or 'tensorboard.main' in s for s in lines)
    others = {c['Id']: (c['Image'], c['State']['StartedAt'], c['State']['Running']) for c in before if c['Id'] != old['Id']}
    command(['docker', 'tag', old['Image'], 'php-parkour:research-sdk016-retained'], 'retain-old-tag.log')
    command(['docker', 'tag', IMAGE, 'php-parkour:research'], 'adopt-new-tag.log')
    command(['docker', 'compose', '-f', 'docker/compose.yml', 'up', '-d', '--no-build', '--force-recreate'], 'compose.log', 120)
    after = json.loads(subprocess.check_output(['docker', 'inspect', '--type', 'container', 'php-parkour-research'], text=True))[0]
    (BASE / 'container-after.json').write_text(json.dumps(after, indent=2) + '\n')
    assert after['Id'] != old['Id'] and after['Image'] == IMAGE and after['State']['Running']
    assert after['HostConfig']['IpcMode'] == 'private'
    current = {c['Id']: (c['Image'], c['State']['StartedAt'], c['State']['Running']) for c in containers() if c['Id'] != after['Id']}
    assert current == others
    command(['docker', 'exec', after['Id'], '/opt/php/bin/train-python', 'scripts/research/verify_runtime.py',
             '--require-gpu', '--output', '/outputs/sdk018-local-adoption-01/runtime.json'], 'doctor.log', 60)
    command(['docker', 'exec', '-d', after['Id'], '/opt/php/bin/train-python', '-m', 'tensorboard.main',
             '--logdir', '/workspace/php_parkour/usage_assets/tensorboard', '--host', '127.0.0.1', '--port', '6006',
             '--load_fast', 'false'], 'restart-local-tensorboard.log')
    record.update(status='passed', old_image_id=old['Image'], old_container_id=old['Id'],
                  image_id=IMAGE, new_container_id=after['Id'], other_local_container_identities_preserved=True,
                  original_local_tensorboard_restart_requested=True, cloud_mutations=False)
except BaseException as e:
    record.update(status='failed', error=f'{type(e).__name__}: {e}')
    raise
finally:
    record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    write()
print(json.dumps(record))
