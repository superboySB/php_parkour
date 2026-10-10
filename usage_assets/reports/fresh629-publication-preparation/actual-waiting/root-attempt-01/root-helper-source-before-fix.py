import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path('/home/dzp/projects/php_parkour')
prep = root/'outputs/research/fresh629-publication-preparation'
evidence = root/'outputs/research/fresh629-publication-root-waiting-01'
target = root/'usage_assets/reports/sim2sim-full629-sdk018'
cohort = root/'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
cid = '2d09d396cf6936c28334e3798a03db87eeceac6562bbc280ab0586e99253a8e1'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')

def verify_preparation():
    assert sha(prep/'manifest.json') == 'ee35458752dbcd963df3287ea02ffe8a26c8a1ca23fe690687156db3ec7cc6eb'
    for item in json.loads((prep/'manifest.json').read_bytes())['files']:
        path = prep/item['relative']
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']

def docker_ids():
    return sorted(subprocess.check_output(['docker','ps','-aq','--no-trunc'],text=True).split())

def inspect_owned():
    item = json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
    assert item['Id'] == cid and item['Image'] == 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
    assert item['State']['Running'] and item['State']['StartedAt'] == '2026-10-10T10:02:25.221860961Z'
    return {key:item[key] for key in ('Id','Image','State')}

verify_preparation()
assert not target.exists() and not list(target.parent.glob(target.name+'.partial-*'))
assert json.loads((cohort/'host/launch-receipt.json').read_bytes())['status'] == 'running'
evidence.mkdir(exist_ok=False)
started = dt.datetime.now(dt.timezone.utc).isoformat()
before = {'docker_ids':docker_ids(),'owned_container':inspect_owned()}
write(evidence/'before.json',before)
calls = []
for action in ('status','prepare','publish'):
    command = [sys.executable,'-B',str(prep/'publish_fresh629.py'),action]
    if action == 'publish':
        command += ['--output',str(target)]
    result = subprocess.run(command,text=True,capture_output=True)
    (evidence/(action+'.stdout.json')).write_text(result.stdout)
    (evidence/(action+'.stderr.log')).write_text(result.stderr)
    receipt = {'action':action,'argv':command,'returncode':result.returncode,
               'stdout_sha256':sha(evidence/(action+'.stdout.json')),
               'stderr_sha256':sha(evidence/(action+'.stderr.log'))}
    calls.append(receipt)
    write(evidence/'calls.json',calls)
    assert result.returncode == 0 and result.stderr == ''
    response = json.loads(result.stdout)
    assert response['status'] == 'waiting' and response['host_status'] == 'running'
    assert response['publication_created'] is False and response['process_started'] is False
    assert not target.exists() and not list(target.parent.glob(target.name+'.partial-*'))
after = {'docker_ids':docker_ids(),'owned_container':inspect_owned()}
write(evidence/'after.json',after)
assert before['docker_ids'] == after['docker_ids']
assert before['owned_container']['Id'] == after['owned_container']['Id']
verify_preparation()
matrix_bytes = (cohort/'outputs/all-configs/matrix.json').read_bytes()
matrix = json.loads(matrix_bytes)
summary = {'schema_version':1,'status':'passed_actual_running_cohort_waiting_only',
           'started_utc':started,'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
           'controller_sha256':sha(prep/'publish_fresh629.py'),'preparation_manifest_sha256':sha(prep/'manifest.json'),
           'calls':calls,'docker_id_set_unchanged':True,'original_container_identity_unchanged':True,
           'actual_matrix_status':matrix['status'],'actual_selection_counts':dict(collections.Counter(x['status'] for x in matrix['selections'])),
           'actual_matrix_snapshot_sha256':hashlib.sha256(matrix_bytes).hexdigest(),
           'publication_created':False,'partial_stage_created':False,'process_started_by_controller':False,
           'full629_verification_performed':False,'quality_verified':False}
write(evidence/'summary.json',summary)
print(json.dumps(summary,indent=2,ensure_ascii=False))
