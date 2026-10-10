import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/dzp/projects/php_parkour')
BASE = ROOT / 'outputs/research/cloud/sdk018-canonical-upload'
TAG = 'php-parkour:research-sdk018-canonical-candidate'
EXPECTED = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
ARCHIVE = ROOT / 'outputs/research/cloud/images' / (EXPECTED.removeprefix('sha256:') + '.tar.gz')
REMOTE_ARCHIVE = '/diff/dzp_is_sb/php-parkour-research/images/' + ARCHIVE.name
TARGET = BASE / 'independent-upload-verification.json'
assert not TARGET.exists()


def remote(command):
    return subprocess.check_output(['ssh', '-p', '22', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
                                    'tencent-231', command], text=True, timeout=120)


def fingerprint(info):
    return hashlib.sha256(json.dumps({'Config': info['Config'], 'RootFS': info['RootFS']}, sort_keys=True).encode()).hexdigest()


local = json.loads(subprocess.check_output(['docker', 'image', 'inspect', EXPECTED], text=True))[0]
remote_image = json.loads(remote('docker image inspect ' + TAG))[0]
(BASE / 'remote-new-image-inspect.json').write_text(json.dumps(remote_image, indent=2) + '\n')
assert local['Id'] == EXPECTED and fingerprint(local) == fingerprint(remote_image)
h = hashlib.sha256()
with ARCHIVE.open('rb') as f:
    for block in iter(lambda: f.read(8388608), b''):
        h.update(block)
remote_sha = remote('sha256sum ' + REMOTE_ARCHIVE).split()[0]
assert h.hexdigest() == remote_sha == '03fbce4defd450f365e7654de7fef6308d390301df520562f5b0fb9e1d1f9280'
before = json.loads((BASE / 'active-container-before.json').read_text())
after = json.loads(remote('docker inspect --type container php-parkour-cloud-research'))[0]
(BASE / 'active-container-after-verified.json').write_text(json.dumps(after, indent=2) + '\n')
assert before['Id'] == after['Id'] and before['Image'] == after['Image']
assert before['State']['StartedAt'] == after['State']['StartedAt'] and before['State']['Pid'] == after['State']['Pid']
assert after['State']['Running']
mount_key = lambda m: m['Destination']
assert sorted(before['Mounts'], key=mount_key) == sorted(after['Mounts'], key=mount_key)
old_tag = json.loads(remote('docker image inspect php-parkour:research'))[0]
assert old_tag['Id'] == before['Image']
record = {
    'status': 'passed', 'observed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    'image_tag': TAG, 'local_id': EXPECTED, 'remote_id': remote_image['Id'],
    'contents_sha256': fingerprint(local), 'archive_bytes': ARCHIVE.stat().st_size,
    'archive_sha256': h.hexdigest(), 'remote_archive_sha256': remote_sha,
    'active_cloud_container_id_image_pid_startedat_mounts_preserved': True,
    'original_cloud_research_tag_preserved': True,
    'prior_operator_result': 'failed: Docker inspect mount array order changed; sorted mount records, container identity and state all match',
    'prior_operator_receipt_sha256': hashlib.sha256((BASE / 'receipt.json').read_bytes()).hexdigest(),
    'scope': 'Full archive transfer/load verification, no GPU task/container recreation/source replacement',
}
TARGET.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
