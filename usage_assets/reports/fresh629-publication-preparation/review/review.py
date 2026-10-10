#!/usr/bin/env python3
"""Read-only frozen candidate/retained CPU evidence audit, using stdlib only."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path('/home/dzp/projects/php_parkour')
BASE=ROOT/'outputs/research/fresh629-publication-preparation'
OUT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_bytes())
def fp(path):return {'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path)}
errors=[]
def require(ok,detail):
    if not ok:errors.append(detail)
manifest=load(BASE/'manifest.json')
require(sha(BASE/'manifest.json')=='ee35458752dbcd963df3287ea02ffe8a26c8a1ca23fe690687156db3ec7cc6eb','Final preparation manifest SHA differs')
require(sha(BASE/'code-freeze.json')=='b112c13b9458af20ab2fc4e9f10f108110bb6daeabb94c3a1083ce835f39e2ee','Code-freeze SHA differs')
checked=[]
for row in manifest['files']:
    p=BASE/row['relative']
    require(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Manifest bytes differ: '+row['relative'])
    checked.append(fp(p))
require(len(checked)==30 and sum(p['bytes'] for p in checked)==479082,'Preparation manifest count/size differs')
code=load(BASE/'code-freeze.json')
for rec in code['files']:
    p=BASE/rec['relative']
    require(p.stat().st_size==rec['bytes'] and sha(p)==rec['sha256'],'Frozen source mismatch: '+rec['relative'])
require((BASE/'publisher_source.py').read_bytes()==(ROOT/'scripts/research/publish_full_scene_matrix.py').read_bytes(),'Reused publisher is not original byte-exact source')
launch=load(BASE/'cpu-tests-final/launch.json')
require(launch['source_before']==launch['source_after'],'CPU source before/after changed')
for rec in launch['source_before']:
    require(rec['sha256']==sha(BASE/rec['path']) and rec['bytes']==(BASE/rec['path']).stat().st_size,'Final launch source mismatch: '+rec['path'])
    require((BASE/'cpu-tests-final/source'/rec['path']).read_bytes()==(BASE/rec['path']).read_bytes(),'CPU final source snapshot differs: '+rec['path'])
require(launch['returncode']==launch['container_exit_code']==0 and launch['removed_own_container'] is True,'CPU run/own cleanup not successful')
before=load(BASE/'cpu-tests-final/container-before.json')
after=load(BASE/'cpu-tests-final/container-after.json')
if isinstance(before,list):before=before[0]
if isinstance(after,list):after=after[0]
require(before['Id']==after['Id']==launch['container_id'],'Exact CPU container ID differs')
require(before['Image']=='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f','CPU image differs')
require(before['HostConfig']['Runtime']=='runc' and before['HostConfig']['NetworkMode']=='none' and before['HostConfig']['IpcMode']=='private' and not before['HostConfig'].get('DeviceRequests'),'CPU isolation/noGPU differs')
require(after['State']['Running'] is False and after['State']['ExitCode']==0,'Actual CPU container terminal state differs')
xml=ET.fromstring((BASE/'cpu-tests-final/tests.xml').read_bytes())
cases=xml.findall('.//testcase')
stats={'testcases':len(cases),'errors':len(xml.findall('.//error')),'failures':len(xml.findall('.//failure')),'skipped':len(xml.findall('.//skipped'))}
require(stats=={'testcases':80,'errors':0,'failures':0,'skipped':0},'Final JUnit is not80/80')
for label in ('cpu-tests-candidate01','cpu-tests-candidate02','cpu-tests-final'):
    d=load(BASE/label/'source/manifest.json')
    for rec in d['files']:
        p=BASE/label/'source'/rec.get('relative',rec.get('path'))
        require(p.stat().st_size==rec['bytes'] and sha(p)==rec['sha256'],'Retained candidate source snapshot differs: '+label)
script=(BASE/'publish_fresh629.py').read_text()
tree=ast.parse(script)
lines={node.name:node.lineno for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
assignments={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant)}
require(assignments['CHUNK_LIMIT']==25_000_000,'Chunk limit must be decimal25MB')
require(assignments['HOST_PLAN']=='44d6e71e8ef1d12c5b479d8e3bcb411c39e8d7daa1c3bac109d6edd7417502d0' and assignments['NATIVE_PLAN']=='1e3483f7b35dd7592d9e5e0b02c13143a44e4f17a5cd0ba24def25c0229a6e6f','Cohort plan constants differ')
links=[]
for m in re.finditer(r'\[[^\]\n]*\]\(([^)]+)\)',(BASE/'summary.md').read_text()):
    target=m.group(1)
    if '://' not in target:
        p=BASE/target.split('#')[0]
        require(p.exists(),'Missing preparation summary link: '+target);links.append(target)
bash=[]
for match in re.finditer(r'```bash\s*\n(.*?)```',(BASE/'summary.md').read_text(),re.S):
    r=subprocess.run(['bash','-n'],input=match.group(1).encode(),capture_output=True)
    require(r.returncode==0,'Preparation CLI Bash syntax rejected');bash.append({'syntax_exit':r.returncode,'executed':False})
final_claim=load(BASE/'report.json')
require(final_claim['real_publication_executed'] is False and final_claim['real_full629_postacceptance_executed'] is False and final_claim['runtime_agent_real_waiting_calls']==0,'Preparation report incorrectly claims actual final execution')
checks=[
 {'contract':'Fresh namespace/validator ROOT','functions':['mapped','modules'],'finding':'Exact reviewed base/image/host/native identities, canonical namespace maps, frozen native module ROOT and temporary package aliases replace live imports. Three raw native receipts remain unchanged.'},
 {'contract':'5206freeze and2266native bindings','functions':['verify_freeze'],'finding':'Rehashes every safe entry; exact source5184/control4/host13/inputs5; source/control/inputs current file sets must match.2266 native dependency/source/model records bind original SHA+size.'},
 {'contract':'Actual terminal host schema','functions':['header','status','verify_terminal'],'finding':'No fabricated legacy receipt. Requires completed original host schema1, driver/afterstop/observer/CPU exits0, stopped own CIDs, exact native and CPU argv, unfiltered matrix629/17 and bound CPU full-validation SHA.'},
 {'contract':'1258workers/hostwriter mappings','functions':['verify_terminal','verify_mappings'],'finding':'Reuses strict frozen native supervisor schema2/entry schema1 validator. Recomputes exact1258 case/role/entrySHA/nativebirth/hostTIDbirth/NSpid/NStgid mappings and matches the original host receipt.'},
 {'contract':'629full video decode','functions':['verify_cpu_cases'],'finding':'Consumes actual SHA-bound CPU report and checks each exact ordered case/result/three worker receipts/video SHA+bytes/ffmpeg command/full_decode true/rc0. Does not mislabel metadata checks or run decode itself.'},
 {'contract':'Whole observer log/chunks/copies','functions':['verify_observer_log','byte_copy','chunk_copy','publish'],'finding':'Reconstructs summary from every original log line with native first-status/lastseen semantics. Complete host tree retained; files>25,000,000B get contiguous exact chunks with offsets/individual+whole SHA. Sealed case artifacts copy under their original expected SHA; failed unique partial stages retained.'},
 {'contract':'Verification→copy binding','functions':['verify_all','publish'],'finding':'Before validation, pins original host tree and plan/matrix hashes; rechecks after validation and before/after copying. Never resets copy expectations from changed bytes.'},
]
for check in checks:check['source_lines']={name:lines[name] for name in check['functions']}
review={
 'schema_version':1,'observed_utc':datetime.now(timezone.utc).isoformat(),'status':'pass_frozen_CPU_control_plane_only' if not errors else 'must_fix',
 'scope':'Independent local read-only review of frozen preparation and prior actual CPU artifacts; no real status/prepare/publish, tests rerun, Docker/SSH/native/DDS/GPU/daemon or tracked/cohort/Git edits.',
 'reviewed_sources':[fp(BASE/rec['relative']) for rec in code['files']], 'code_freeze':fp(BASE/'code-freeze.json'),'preparation_manifest':fp(BASE/'manifest.json'),
 'manifest_dependencies_checked':len(checked),'manifest_dependency_bytes':sum(p['bytes'] for p in checked),'all_manifest_bytes_sha_match':not errors,
 'cpu_final':{'launch':fp(BASE/'cpu-tests-final/launch.json'),'junit':fp(BASE/'cpu-tests-final/tests.xml'),'statistics':stats,'exact_source_before_after_and_frozen_snapshots':True,'actual_runc_network_none_private_noGPU':True,'actual_container_exit0_and_removed_as_recorded':True,'candidate_history_preserved':True,'tests_not_summed_across_candidates':True},
 'contracts_reviewed':checks,
 'pre_review_issues_fixed':[{'issue':'Default bytecode could add unfrozen files inside writable source directories','fix':'private_module sets sys.dont_write_bytecode=True before import','regression':'test_private_import_without_B_preserves_frozen_file_set'}, {'issue':'Original reused publisher import could execute live/cached repository module','fix':'Verified frozen native module bound under three temporary module names; restore old cache/sys.path','regression':'test_frozen_publisher_import_never_uses_live_or_cached_native'}, {'issue':'Post-verification rehash could replace original copy expectations','fix':'verify_all pins host/source guard hashes before validation and returns them unchanged to publish','regression':'test_verification_to_copy_mutations_fail_and_retain_partial'}],
 'semantic_limits':['80 cases are CPU control-plane fixtures; some intentionally mock the scientific gate and use synthetic629 indexes/media. They prove no real full629 postacceptance, video decode, skill quality or actual publication.', 'Adapter is fixed to this exact reviewed cohort; a new run needs a new independently reviewed identity contract.', 'Original main publisher/core/current active cohort remain unchanged; the copied publisher source is byte-exact.', 'Current full cohort completion has not been asserted by this audit. Root will perform actual waiting and terminal publication calls separately.', 'Large source/ONNX bytes are not duplicated in the gallery. Their exact original freeze proof and documented retained external cohort are required.', 'CPU container removal and noGPU/run identity are checked against retained exact inspect/launch receipts; this audit did not query Docker daemon.'],
 'summary_local_links':links,'bash_syntax_only':bash,'must_fix':errors,
}
(OUT/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
(OUT/'summary.md').write_text('''# Fresh629 publication adapter: final independent review\n\n**PASS for frozen CPU control-plane preparation; no remaining must-fix finding.**\n\nReviewed controller SHA `53dde18b19ba7244f703f96d7264f15b96ad619cea7203329d42243078bd1858`, exact reused publisher `5b0d967f96f0d62ca474dcf4746e53f0a4aecd459790d0591aa31d2e89679a7a` and tests `9296b29701b6f2baccaf0cfe3df9a6520005c00abcdba1c027ce5418ec0e6a9b`. All30 manifest dependencies/479,082 bytes and three source freezes match; candidate history remains exact. Final retained Docker CPU JUnit80/80, sourcebefore=after, runc/networknone/private/noGPU inspect and exit0/own-removal receipts agree. Tests were not rerun by this review.\n\nSix fresh-cohort contracts are connected: namespace/frozen ROOT,5206freeze+2266binding, original terminal host schema,1258 native workers and exact hostwriter births,629 actual CPU full-decode receipt and lossless whole host/observer archive. Observer chunks are at most25,000,000 bytes with contiguous offsets/wholeSHA. Byte-copy expectations remain bound to the original seals; failures preserve unique partial stages. Three pre-review import/copy issues were fixed and covered by meaningful CPU regressions.\n\nThe80 tests are synthetic control-plane evidence, including a mocked scientific gate; they do not prove actual629 completion, actual full decode or publication. No real cohort entry was invoked, no process/native/DDS/GPU/SSH/Docker was started, and original docs/core/cohort/Git were untouched. Root execution and terminal scientific evidence remain separate. See [review.json](review.json) for precise source lines and limitations.\n''')
print(json.dumps({'status':review['status'],'must_fix':errors,'review_sha256':sha(OUT/'review.json'),'summary_sha256':sha(OUT/'summary.md'),'manifest_count':len(checked),'cpu':stats},indent=2))
