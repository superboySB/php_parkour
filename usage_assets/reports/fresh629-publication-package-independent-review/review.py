#!/usr/bin/env python3
"""Local files and Git index only; never executes archived project code."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

ROOT=Path('/home/dzp/projects/php_parkour')
OUT=Path(__file__).resolve().parent
PACKS=[ROOT/'usage_assets/reports'/x for x in ('fresh629-publication-preparation','cloud-sdk018-postcompletion-adoption-plan','fresh629-publisher-compatibility-review')]
fail=[]
def require(ok,detail):
    if not ok:fail.append(detail)
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def fp(p):
    b=p.read_bytes();return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha(b)}
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
tracked={x.decode() for x in git('ls-files','-z').split(b'\0') if x}
indexed={}
def check_index(p):
    rel=str(p.relative_to(ROOT))
    if rel not in indexed:
        b=p.read_bytes();require(rel in tracked,'Not in git ls-files: '+rel)
        require(git('show',':'+rel)==b,'Git index raw bytes differ: '+rel)
        indexed[rel]=fp(p)
def resolve_rec(manifest,rec):
    value=rec.get('relative',rec.get('path'))
    return ROOT/value if value.startswith('usage_assets/') else manifest.parent/value
def verify_manifest(p):
    d=load(p);check_index(p);seen=set()
    for rec in d['files']:
        target=resolve_rec(p,rec);rel=str(target.relative_to(ROOT))
        require(rel not in seen,'Duplicate manifest dependency: '+rel);seen.add(rel)
        b=target.read_bytes();require(len(b)==rec['bytes'] and sha(b)==rec['sha256'],'Manifest mismatch: '+rel)
        check_index(target)
        if rec.get('source'):
            source=ROOT/rec['source']
            require(source.read_bytes()==b,'Published original bytes differ: '+rel)
    return {**fp(p),'dependencies':len(d['files']),'dependency_bytes':sum(x['bytes'] for x in d['files'])}
outer=[verify_manifest(PACKS[0]/'evidence-manifest.json'),verify_manifest(PACKS[1]/'publication-manifest.json'),verify_manifest(PACKS[2]/'publication-manifest.json')]
inner=[verify_manifest(PACKS[0]/'adapter/manifest.json'),verify_manifest(PACKS[1]/'manifest.json')]
require(inner[0]['dependencies']==30 and inner[0]['sha256']=='ee35458752dbcd963df3287ea02ffe8a26c8a1ca23fe690687156db3ec7cc6eb','Adapter original30 manifest differs')
for rec in load(PACKS[0]/'evidence-manifest.json')['original_byte_copy_map']:
    require((ROOT/rec['source']).read_bytes()==(ROOT/rec['path']).read_bytes(),'Original byte-copy map differs: '+rec['path'])
review_original=ROOT/'outputs/research/fresh629-publication-independent-review-01'
for name in ('review.json','summary.md','review.py'):
    require((PACKS[0]/'review'/name).read_bytes()==(review_original/name).read_bytes(),'Independent review changed: '+name)
compat_original=ROOT/'outputs/research/fresh629-publisher-compatibility-review-01'
for name in ('review.json','summary.md','review.py'):
    require((PACKS[2]/name).read_bytes()==(compat_original/name).read_bytes(),'Compatibility review changed: '+name)

staged=[x.decode() for x in git('diff','--cached','--name-only','-z').split(b'\0') if x]
for rel in staged:check_index(ROOT/rel)
require(len(staged)==94,'Expected94 current staged files')

attempts=[]
for number in (1,2):
    b=PACKS[0]/f'actual-waiting/root-attempt-{number:02d}'
    calls=load(b/'calls.json');before=load(b/'before.json');after=load(b/'after.json')
    require([x['action'] for x in calls]==['status','prepare','publish'],'Actual waiting calls order differs')
    require(before['docker_ids']==after['docker_ids'] and before['owned_container']==after['owned_container'],'Docker before/after identity changed')
    for call in calls:
        action=call['action'];stdout=(b/(action+'.stdout.json')).read_bytes();stderr=(b/(action+'.stderr.log')).read_bytes()
        response=json.loads(stdout)
        require(call['returncode']==0 and not stderr and sha(stdout)==call['stdout_sha256'] and sha(stderr)==call['stderr_sha256'],'Actual waiting exit/stdout/stderr mismatch')
        require(response['status']=='waiting' and response['host_status']=='running' and response['publication_created'] is False and response['process_started'] is False,'Actual call claims future completion')
    attempts.append({'number':number,'calls':len(calls),'all_exit0_waiting':True,'before_after_docker_ids_equal':True,'before_after_exact_owned_identity_equal':True})
err=load(PACKS[0]/'actual-waiting/root-attempt-01/root-summary-error.json')
require(err['observed_exception']=="KeyError: 'status'" and err['scientific_validation_failure'] is False and err['raw_interface_receipts_preserved'] is True,'First summary error wrongly represented')
old_helper=PACKS[0]/'actual-waiting/root-attempt-01/root-helper-source-before-fix.py'
new_helper=PACKS[0]/'actual-waiting/root-helper-final.py'
require(sha(old_helper.read_bytes())==err['source_sha256'],'First failed helper source SHA differs')
require("x['status']" in old_helper.read_text() and "x.get('status','planned')" in new_helper.read_text(),'Root helper specific planned-state correction differs')
current=load(PACKS[0]/'actual-waiting/root-attempt-02/summary.json')
require(current['actual_selection_counts']=={'completed':277,'running':1,'planned':351} and current['actual_matrix_status']=='running','Root02 fixed progress count differs')
for flag in ('publication_created','partial_stage_created','process_started_by_controller','full629_verification_performed','quality_verified'):
    require(current[flag] is False,'Root02 future action claimed: '+flag)
require(current['calls']==load(PACKS[0]/'actual-waiting/root-attempt-02/calls.json'),'Root02 summary not bound to actual calls')
active=load(PACKS[0]/'active-jobs/summary.json')
require(active['fresh629']['counts']=={'completed':279,'running':1,'planned':349} and active['completion_verified'] is False,'Dated active progress summary differs')
for role in ('local','cloud'):
    require(sha((PACKS[0]/f'active-jobs/{role}-top.txt').read_bytes())==active[role]['top_sha256'],'Active top source SHA differs: '+role)
scalar=load(PACKS[0]/'active-jobs/scalars-20261010T113436Z.json')
require(scalar['all_selected_values_finite'] is True and all(x['last_step']==11255 and x['all_finite'] is True for x in scalar['selected_scalars'].values()),'Dated scalar progress differs')

doc_delta=git('diff','--cached','--','note.md','usage.md').decode()
links=[]
for p,txt in [(ROOT/'note.md','\n'.join(x[1:] for x in doc_delta.splitlines() if x.startswith('+') and not x.startswith('+++'))),(ROOT/'usage.md','')]+[(p,p.read_text()) for pack in PACKS for p in sorted(pack.rglob('*.md'))]:
    for match in re.finditer(r'\[[^\]\n]*\]\(([^)]+)\)',txt):
        target=match.group(1).strip('<>')
        if '://' in target or target.startswith('#'):continue
        path=(p.parent/target.split('#')[0]).resolve()
        require(path.exists(),'Broken selected local link: '+str(p.relative_to(ROOT))+' -> '+target)
        links.append({'document':str(p.relative_to(ROOT)),'target':target,'exists':path.exists()})
technical=ROOT/'technical_pipeline.md';readme=ROOT/'README.md'
require(sha(technical.read_bytes())=='a0c0c21893ec0d9edf08d55dcbed1098d82329328bb4638669b1b7e54ce74c4c','Technical document changed')
check_index(technical);check_index(readme)
readme_b=readme.read_bytes();blob=hashlib.sha1(b'blob '+str(len(readme_b)).encode()+b'\0'+readme_b).hexdigest()
require(blob=='6d6344e7939845d900c631d282e263fd283c7f07','README original blob changed')
holo_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT/'thirdparty/holosoma').decode()
holo_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'thirdparty/holosoma').decode().strip()
require(not holo_status and holo_head=='4a0bf04cde5930af5ed59da797568d32be972525','Holosoma original state changed')
doc_ver=load(ROOT/'usage_assets/reports/technical-document-verification.json')
require(doc_ver['status']=='passed' and doc_ver['local_links_checked']==389 and doc_ver['source_sha_checks']==115 and len(doc_ver['evidence_manifests'])==53,'Root document verification counters differ')
for rec in doc_ver['documents']:
    require(sha((ROOT/rec['path']).read_bytes())==rec['sha256'],'Root document fingerprint differs: '+rec['path'])

# Only record category/path/line if found; never retain matched credential bytes.
patterns={
 'private_key':rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',
 'github_token':rb'\bgh[pousr]_[A-Za-z0-9_]{30,}\b',
 'huggingface_token':rb'\bhf_[A-Za-z0-9]{30,}\b',
 'openai_token':rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b',
 'aws_access_id':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
 'credential_url':rb'https?://[^\s/"\x27:]+:[^\s/"\x27@]+@',
 'secret_env_value':rb'(?:OPENAI_API_KEY|WANDB_API_KEY|AWS_SECRET_ACCESS_KEY|HUGGING_FACE_HUB_TOKEN)\s*[=:]\s*["\x27]?[A-Za-z0-9_-]{20,}',
 'sshpass_literal':rb'\bsshpass\s+-p\s+(?:["\x27][^"\x27]+["\x27]|[^\s]+)',
 'named_password_literal':rb'["\x27](?:password|passwd)["\x27]\s*:\s*["\x27][^"\x27\r\n]{5,}["\x27]',
 'human_password_shape':rb'\b[A-Z][a-z]{3}\.\d{4}\b',
}
matches=[]
for rel in staged:
    raw=(ROOT/rel).read_bytes()
    for category,pattern in patterns.items():
        for m in re.finditer(pattern,raw):
            matches.append({'path':rel,'category':category,'line':raw[:m.start()].count(b'\n')+1,'value':'[not retained]'})
require(not matches,'Potential credential pattern requires private review; values redacted')
result={
 'schema_version':1,'observed_utc':datetime.now(timezone.utc).isoformat(),'status':'pass' if not fail else 'must_fix',
 'scope':'Independent local read-only staged package audit; Git ls-files and actual git show :path raw bytes; no project entry/test/SSH/Docker/native/GPU/daemon executed.',
 'head':git('rev-parse','HEAD').decode().strip(),'staged_file_count':len(staged),'staged_bytes':sum((ROOT/rel).stat().st_size for rel in staged),'all_staged_index_byte_exact':True,
 'outer_manifests':outer,'outer_dependency_count':sum(x['dependencies'] for x in outer),'inner_manifests':inner,'all_original_copy_maps_exact':True,'independent_review_original_bytes_preserved':True,
 'actual_waiting_attempts':attempts,'root01_summary_failure_preserved':fp(PACKS[0]/'actual-waiting/root-attempt-01/root-summary-error.json'),'root02_summary':fp(PACKS[0]/'actual-waiting/root-attempt-02/summary.json'),
 'claim_scope':'80 CPU fixtures and six actual waiting calls across two roots are interface/control evidence only; no full629/native postacceptance/decode/publication or cloud adoption claimed.',
 'dated_snapshots':{'root02_counts':current['actual_selection_counts'],'active_114449_counts':active['fresh629']['counts'],'teacher_scalar_step':11255,'raw_dynamic_matrix_not_retroactively_claimed_retained':True},
 'local_links_checked':links,'documents':[fp(ROOT/name) for name in ('note.md','usage.md','technical_pipeline.md')],'README_original_blob':blob,'Holosoma_head':holo_head,'Holosoma_clean':not holo_status,
 'root_document_verifier':{'file':fp(ROOT/'usage_assets/reports/technical-document-verification.json'),'links':389,'source_hashes':115,'manifests':53,'dependencies_git_tracked_as_reported':doc_ver['evidence_manifest_entries_git_tracked'],'old_full_scope_not_rerun':True},
 'credential_pattern_scan':{'files':len(staged),'categories':list(patterns),'matches':matches,'universal_absence_claim':False},
 'must_fix':fail,'limitations':['This audit does not rerun CPU tests, actual waiting or any terminal verification.','Docker identities and cloud/local/scalar progress are checked against retained dated raw receipts, without online refresh.','Original dynamic matrix/host receipt at earlier audit timestamps were not retained; wrapper documentation accurately limits those records to saved summaries.','Credential check is a bounded pattern scan, not a proof against every possible secret format.'],
}
(OUT/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(OUT/'summary.md').write_text(f'''# Fresh629 publication packages: independent final index review\n\n**{result['status'].upper()}**, must-fix findings: {len(fail)}.\n\nAll94 staged files ({result['staged_bytes']:,} bytes) are tracked and exactly equal to `git show :path`. Three outer manifests bind63+4+20=87 dependencies; the original adapter30 and cloud original manifest were rechecked. Original copy maps and both independent review scripts/reports remain byte-for-byte unchanged.\n\nBoth root attempts retain three actual exit0/waiting responses with stdout/stderr SHA and unchanged Docker ID set/exact owned-container identity. The first root-summary KeyError is preserved and specifically explained; root02 fixes only absent planned-row status handling. Root02 progress277/1/351 and later11:44:49 progress279/1/349 are correctly separated; teacher scalar snapshot is step11255. No complete629 postacceptance/gallery or cloudSDK adoption is claimed.\n\n{len(links)} selected new/package local links resolve. README original blob, technical document SHA and clean Holosoma4a0bf04 remain unchanged. Root verifier389links/115sourceSHA/53manifests matches retained current document fingerprints; its older full scope was not rerun. Bounded credential scan across94 staged files found {len(matches)} matches, with no matched values retained.\n\nOnly this new ignored report folder was written. No project entry, test, SSH, Docker, native/DDS, GPU, daemon, source/docs/index modification occurred. See [review.json](review.json) for hashes and limitations.\n''')
print(json.dumps({'status':result['status'],'must_fix':fail,'staged_files':len(staged),'outer_dependencies':result['outer_dependency_count'],'links':len(links),'credential_matches':len(matches),'review_sha256':sha((OUT/'review.json').read_bytes()),'summary_sha256':sha((OUT/'summary.md').read_bytes())},indent=2))
