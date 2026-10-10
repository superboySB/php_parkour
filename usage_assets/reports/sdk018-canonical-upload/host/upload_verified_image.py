import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

ROOT = Path('/home/dzp/projects/php_parkour')
path = ROOT / 'scripts/research/cloud.py'
spec = importlib.util.spec_from_file_location('cloud_upload_sdk018', path)
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)
# A separate tag preserves the active official training/watch image and tags.
cloud.IMAGE = 'php-parkour:research-sdk018-canonical-candidate'
args = SimpleNamespace(host='tencent-231', remote_root='/diff/dzp_is_sb/php-parkour-research')
base = ROOT / 'outputs/research/cloud/sdk018-canonical-upload'
assert not base.exists()
base.mkdir(parents=True)
expected = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
assert cloud.image_info(cloud.IMAGE)[0] == expected
offline = ROOT / 'outputs/research/sdk018-canonical-offline-02/acceptance.json'
acceptance = json.loads(offline.read_text())
assert acceptance['status'] == 'passed' and acceptance['image_id'] == expected
receipt = {'status': 'running', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'image': cloud.IMAGE, 'local_id': expected, 'offline_acceptance_sha256': hashlib.sha256(offline.read_bytes()).hexdigest(),
           'active_cloud_container_replacement': False, 'active_cloud_source_replacement': False,
           'default_research_tag_replacement': False}
(base / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
try:
    before = json.loads(cloud.remote_output(args, ['docker', 'inspect', '--type', 'container', 'php-parkour-cloud-research']))[0]
    (base / 'active-container-before.json').write_text(json.dumps(before, indent=2) + '\n')
    record = cloud.upload_image(args)
    after = json.loads(cloud.remote_output(args, ['docker', 'inspect', '--type', 'container', 'php-parkour-cloud-research']))[0]
    assert after['Id'] == before['Id'] and after['Image'] == before['Image'] and after['Mounts'] == before['Mounts'] and after['State']['Running']
    (base / 'active-container-after.json').write_text(json.dumps(after, indent=2) + '\n')
    receipt.update(status='passed', transfer=record, active_cloud_identity_mounts_preserved=True)
except BaseException as error:
    receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
    raise
finally:
    receipt['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    (base / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
