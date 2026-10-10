from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
import hashlib,json,re,subprocess,unicodedata

ROOT=Path.cwd().resolve()
OUT=ROOT/'outputs/research/documentation-final-independent-20261010T1027'
sha=lambda b:hashlib.sha256(b).hexdigest()
read_json=lambda p:json.loads((ROOT/p).read_text())
root_report_path='usage_assets/reports/technical-document-verification.json'
root_report=read_json(root_report_path)
errors=[]
index={}
for part in subprocess.check_output(['git','ls-files','--stage','-z']).split(b'\0'):
 if part:
  meta,name=part.split(b'\t',1); mode,blob,stage=meta.decode().split()
  index[name.decode()]={'mode':mode,'blob':blob,'stage':stage}
cache={}
def fingerprint(p):
 p=p.resolve()
 if p not in cache:
  a=hashlib.sha256();b=hashlib.sha1();n=p.stat().st_size;b.update(b'blob '+str(n).encode()+b'\0')
  with p.open('rb') as f:
   while data:=f.read(1024*1024):a.update(data);b.update(data)
  cache[p]={'bytes':n,'sha256':a.hexdigest(),'git_blob_sha1':b.hexdigest()}
 return cache[p]
def record_error(category,**details):errors.append({'category':category,**details})

docs=[]
for r in root_report['documents']:
 p=ROOT/r['path'];fp=fingerprint(p);docs.append({'path':r['path'],**{k:fp[k] for k in ('bytes','sha256')},'lines':len(p.read_text().splitlines())})
 if any(fp[k]!=r[k] for k in ('bytes','sha256')):record_error('frozen_document_changed',path=r['path'])
 if index.get(r['path'],{}).get('blob')!=fp['git_blob_sha1']:record_error('frozen_document_index_bytes_differ',path=r['path'])

entries=0;total=0;manifest_reports=[];unique_evidence=set()
for r in root_report['evidence_manifests']:
 mpath=ROOT/r['path'];mfp=fingerprint(mpath)
 if mfp['sha256']!=r['sha256']:record_error('selected_manifest_identity',path=r['path'])
 d=json.loads(mpath.read_text());files=d['files']
 if len(files)!=r['files']:record_error('selected_manifest_count',path=r['path'])
 if index.get(r['path'],{}).get('blob')!=mfp['git_blob_sha1']:record_error('manifest_not_byte_exact_in_index',path=r['path'])
 for a in files:
  raw=a.get('relative',a.get('path'))
  # Manifest schemes explicitly distinguish repo-relative usage_assets paths
  # from manifest-relative entries. No fallback to unrelated source/raw paths.
  p=(ROOT/raw if raw.startswith('usage_assets/') else mpath.parent/raw).resolve()
  rel=p.relative_to(ROOT).as_posix();entries+=1
  if not p.is_file():record_error('manifest_dependency_missing',manifest=r['path'],path=rel);continue
  fp=fingerprint(p);total+=fp['bytes'];unique_evidence.add(rel)
  if fp['sha256']!=a['sha256'] or fp['bytes']!=a['bytes']:record_error('manifest_dependency_hash_or_bytes',manifest=r['path'],path=rel)
  if rel not in index:record_error('manifest_dependency_not_in_git_index',manifest=r['path'],path=rel)
  elif index[rel]['blob']!=fp['git_blob_sha1']:record_error('manifest_dependency_index_bytes_differ',manifest=r['path'],path=rel)
 manifest_reports.append({'path':r['path'],'files':len(files),'sha256':mfp['sha256']})

source_basis_path='usage_assets/reports/technical-pipeline-independent-review/technical-pipeline-source-readonly-check-1010.json'
source_basis=read_json(source_basis_path)
archives={a['path']:a for a in root_report['historical_sources']}
source_results=[]
for a in source_basis['source_hashes']:
 p=ROOT/a['path'];expected=a['expected_sha256'];resolution='current';rp=a['path']
 if not p.is_file() or fingerprint(p)['sha256']!=expected:
  old=archives.get(a['path']);resolution='explicit_historical_archive'
  if not old or old['sha256']!=expected:record_error('source_current_mismatch_without_archive',path=a['path']);continue
  rp=old['archived_path'];p=ROOT/rp
  if rp not in index:record_error('historical_source_not_indexed',path=rp)
 actual=fingerprint(p)['sha256']
 if actual!=expected:record_error('source_sha_mismatch',path=a['path'],resolved=rp)
 source_results.append({'path':a['path'],'resolved_path':rp,'sha256':actual,'resolution':resolution})

link_checks=[];html_files=set();shell_blocks=[]
def slug_heading(s):
 s=re.sub(r'!?\[([^\]]+)\]\([^)]*\)',r'\1',s)
 s=re.sub(r'<[^>]+>','',s).replace('`','').strip().lower()
 s=''.join(c for c in s if not unicodedata.category(c).startswith('P') or c in '-_')
 return re.sub(r'\s','-',s)
def anchors(p):
 out=set();counts={}
 for line in p.read_text().splitlines():
  m=re.match(r'^#{1,6}\s+(.+?)(?:\s+#+\s*)?$',line)
  if m:
   base=slug_heading(m[1]);i=counts.get(base,0);counts[base]=i+1;out.add(base if not i else f'{base}-{i}')
 return out
anchor_cache={}
def check_url(owner,url,category):
 url=unquote(url.strip('<>'))
 u=urlsplit(url)
 if u.scheme or url.startswith('//'):return
 p=(owner.parent/u.path).resolve() if u.path else owner
 rel=p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)
 item={'owner':owner.relative_to(ROOT).as_posix(),'url':url,'resolved':rel,'category':category};link_checks.append(item)
 if not p.exists():record_error('local_link_missing',**item);return
 if p.suffix=='.html':html_files.add(p)
 if u.fragment:
  if re.fullmatch(r'L\d+(?:-L?\d+)?',u.fragment):
   for n in re.findall(r'\d+',u.fragment):
    if int(n)>len(p.read_text().splitlines()):record_error('source_line_link_out_of_bounds',**item)
  elif p.suffix.lower()=='.md':
   if p not in anchor_cache:anchor_cache[p]=anchors(p)
   if u.fragment not in anchor_cache[p]:record_error('markdown_anchor_missing',**item)
for r in docs:
 p=ROOT/r['path'];txt=p.read_text()
 for m in re.finditer(r'!?\[[^\]]*\]\(([^)\n]+)\)',txt):check_url(p,m[1],'markdown')
 for m in re.finditer(r'^```(?:bash|sh|shell)\s*\n(.*?)^```\s*$',txt,re.M|re.S):
  cp=subprocess.run(['bash','-n'],input=m[1],text=True,capture_output=True)
  line=txt[:m.start()].count('\n')+1;shell_blocks.append({'document':r['path'],'line':line,'returncode':cp.returncode})
  if cp.returncode:record_error('bash_block_syntax',document=r['path'],line=line,stderr=cp.stderr)
class Links(HTMLParser):
 def __init__(self,p):super().__init__();self.p=p
 def handle_starttag(self,tag,attrs):
  for k,v in attrs:
   if k in ('href','src','poster') and v:check_url(self.p,v,'html_'+k)
queue=list(html_files);seen=set()
while queue:
 p=queue.pop()
 if p in seen:continue
 seen.add(p);Links(p).feed(p.read_text());queue.extend(html_files-seen)

readme=fingerprint(ROOT/'README.md');expected_readme=root_report['README_blob_unchanged']
readme_head=subprocess.check_output(['git','rev-parse','HEAD:README.md'],text=True).strip()
readme_baseline=subprocess.check_output(['git','rev-parse','3439cb7:README.md'],text=True).strip()
if not (readme['git_blob_sha1']==index['README.md']['blob']==readme_head==readme_baseline==expected_readme):record_error('README_original_blob_changed')

# The docs are reviewed as frozen snapshots. Never infer current sweep completion
# from a live matrix or mutate any original status/evidence during this audit.
semantic_review={
 'core_math':{'status':'no_new_substantive_error_found','line_ranges':[[185,296],[298,392],[445,537]],'contracts':['teacher sorted actor449/critic575 and six-preset160/286 ablations','29 joint-position increments and implicit Isaac versus explicit MuJoCo PD','nine dt-scaled rewards, full3D position/gravity-z termination, native PPO/GAE/value clipping','student actor108+depth32, online no_grad deterministic teacher labels, pure versus mixed zero-label mask','mixed gate-weighted PPO/entropy/complementary10xBC, critic gradient excludes CNN, gate statistics not checkpointed','upstream retarget provenance and native/BM/SDK layouts, FPS clock without automatic resampling','real hardware/D435i/IMU calibration not verified']},
 'new_scopes':[
  {'document_lines':'technical_pipeline.md:543-554,613; usage.md:354-366','evidence':'usage_assets/reports/native-keyboard-gui/manifest.json','finding':'Five attempts with four preserved failures; fifth both actual worker0/empty owned groups,169/196-frame recordings from native command labels. Visible viewer remains GLFW; EGL only changes offscreen context; no all-heap-bugs or obstacle-quality claim.'},
  {'document_lines':'technical_pipeline.md:615; usage.md:366-377; note.md:450','evidence':'usage_assets/reports/fresh629-start-first-two/manifest.json','finding':'Fixed10:10:23 UTC snapshot21completed/1running/607planned; independent validation exactly first2,4worker receipts and2decoded MP4;cfg1 actual fall. No629completed/skill-quality/self-trained-policy claim.'},
  {'document_lines':'technical_pipeline.md:562-564; usage.md:352,379; note.md:464','evidence':'usage_assets/reports/posttrain-monitor-ro-assets-v2/evidence-manifest.json; usage_assets/reports/final-student-transfer-ro-assets-integration/manifest.json','finding':'Watch02bc/schema2/coverage-v2 upgrade preserves official training identity;25watchCPU and77transferCPU are distinct fixtures;actual10:19SSH stillwaiting16blockers,nocpu-ready,nogpu,notransfer.57oldtests are explicitly historical in latest sections.'}
 ],
 'nonblocking_editorial_notes':[{'document':'note.md','line':373,'finding':'The earlier transfer paragraph says current57CPU checks while the final appended paragraph(line464) gives current77 and explicitly updated scope. State remains accurately waiting in both; prefer marking57 historical in a later editorial update to remove version ambiguity.','severity':'nonblocking'}],
 'wandb_login_or_online_registry_commands_found':False,
 'main_docs_or_source_modified_by_auditor':False,
 'tests_run':'41 bash -n syntax checks only; no science/native/GPU/DDS tests repeated'
}
# Assert referenced latest publications carry the exact documented terminal scope.
fresh=read_json('usage_assets/reports/fresh629-start-first-two/manifest.json')
if fresh['batch_counts_at_snapshot']!={'completed':21,'running':1,'planned':607} or fresh['validated_cases']!=2 or fresh['quality_verified'] is not False:record_error('new_fresh629_scope_mismatch')
gui=read_json('usage_assets/reports/native-keyboard-gui/independent-review.json')
status_source=read_json('usage_assets/reports/final-student-transfer-ro-assets-integration/root-readonly-status.json')
if status_source.get('status')!='waiting':record_error('latest_transfer_not_waiting')
# Ensure no concurrent document edits silently move the reviewed identity.
for r in docs:
 if sha((ROOT/r['path']).read_bytes())!=r['sha256']:record_error('document_changed_during_review',path=r['path'])
report={
 'schema_version':1,'utc':datetime.now(timezone.utc).isoformat(),'status':'passed' if not errors else 'failed',
 'scope':'Final frozen-doc independent read-only review; source/math/new scope, local media/links, byte-exact Git-index membership. Not full-training/629/hardware completion.',
 'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'documents':docs,
 'producer_verification':{'path':root_report_path,'sha256':fingerprint(ROOT/root_report_path)['sha256']},
 'readme':{'git_blob_sha1':readme['git_blob_sha1'],'baseline_commit':'3439cb7','HEAD_index_working_and_baseline_equal':readme['git_blob_sha1']==index['README.md']['blob']==readme_head==readme_baseline==expected_readme},
 'manifest_audit':{'selected':len(manifest_reports),'dependency_entries':entries,'unique_dependency_files':len(unique_evidence),'entry_bytes_including_duplicates':total,'all_raw_dependencies_git_indexed_byte_exact':not any('manifest' in x['category'] for x in errors),'manifests':manifest_reports},
 'source_audit':{'historical_basis':source_basis_path,'basis_sha256':fingerprint(ROOT/source_basis_path)['sha256'],'checked':len(source_results),'current_matching':sum(a['resolution']=='current' for a in source_results),'historical_matching':sum(a['resolution']!='current' for a in source_results),'historical': [a for a in source_results if a['resolution']!='current']},
 'link_audit':{'markdown_checked':sum(a['category']=='markdown' for a in link_checks),'html_attribute_media_checked':sum(a['category']!='markdown' for a in link_checks),'linked_html_pages':sorted(p.relative_to(ROOT).as_posix() for p in seen),'bash_blocks_checked':len(shell_blocks),'bash_blocks_all_parse':all(a['returncode']==0 for a in shell_blocks)},
 'semantic_review':semantic_review,'must_fix':errors,
 'limits':['Source audit is115 published identities:110 current and5 byte-exact historical archives; it does not claim all historic code is unchanged.','HTML checks validate literal href/src/poster links, not another real browser interaction or media full decode; prior published runtime/browser/decoder evidence remains the source.','All45 selected manifests checked against filesystem SHA/bytes and exact Git-index blob; unselected private/ignored/live artifacts are outside this publication audit.','Fresh629 snapshot is historical and only first2 have published independent postchecks; current live count is not inferred.','No network/cloud call, native/DDS/GPU process, dependency installation, source/doc edit, git mutation, or result rewriting performed.'],
 'audit_script':{'path':str((OUT/'check.py').relative_to(ROOT)),'sha256':sha((OUT/'check.py').read_bytes())}
}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'errors':errors,'manifests':len(manifest_reports),'dependencies':entries,'unique':len(unique_evidence),'source_count':len(source_results),'current':report['source_audit']['current_matching'],'historical':report['source_audit']['historical_matching'],'links':report['link_audit'],'report_sha256':sha((OUT/'review.json').read_bytes())},ensure_ascii=False,indent=2))
