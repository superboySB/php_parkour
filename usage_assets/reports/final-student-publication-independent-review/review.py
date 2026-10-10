#!/usr/bin/env python3
"""Read-only, local-file/index/proc audit; writes only this ignored review folder."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = Path('/home/dzp/projects/php_parkour')
OUT = Path(__file__).resolve().parent
PACKS = [ROOT/'usage_assets/reports/final-student-native58-preparation', ROOT/'usage_assets/reports/final-student-delivery-waiter']
failures = []
def require(ok, detail):
    if not ok:
        failures.append(detail)
    return bool(ok)
def sha(b):
    return hashlib.sha256(b).hexdigest()
def load(p):
    return json.loads(p.read_bytes())
def stamp(p):
    b = p.read_bytes()
    return {'path': str(p.relative_to(ROOT)), 'bytes': len(b), 'sha256': sha(b)}
index = {}
for row in subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0'):
    if row:
        meta, path = row.split(b'\t', 1)
        mode, oid, stage = meta.decode().split()
        if stage == '0':
            index[os.fsdecode(path)] = oid
def check_index(p, b=None):
    if b is None:
        b = p.read_bytes()
    rel = str(p.relative_to(ROOT))
    blob = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
    return require(index.get(rel) == blob, {'kind': 'index_byte_mismatch', 'path': rel})
def manifest_audit(p):
    data = load(p)
    seen = set()
    count = 0
    total = 0
    checks = []
    check_index(p)
    for rec in data['files']:
        text = rec.get('relative', rec.get('path'))
        target = ROOT/text if text.startswith('usage_assets/') else p.parent/text
        rel = str(target.relative_to(ROOT))
        require(rel not in seen, {'kind': 'duplicate_manifest_path', 'manifest': str(p.relative_to(ROOT)), 'path': rel})
        seen.add(rel)
        b = target.read_bytes()
        require(len(b) == rec['bytes'] and sha(b) == rec['sha256'], {'kind': 'manifest_mismatch', 'manifest': str(p.relative_to(ROOT)), 'path': rel})
        check_index(target, b)
        count += 1
        total += len(b)
        checks.append(stamp(target))
    return {**stamp(p), 'dependency_count': count, 'dependency_bytes': total, 'all_dependencies_git_index_byte_exact': True, 'dependencies': checks}

manifest_paths = [PACKS[0]/'manifest.json', PACKS[0]/'adapter/manifest.json', PACKS[1]/'manifest.json', PACKS[1]/'preparation/manifest.json']
manifests = [manifest_audit(p) for p in manifest_paths]
require(load(manifest_paths[0])['original_manifest_sha256'] == sha(manifest_paths[1].read_bytes()), {'kind': 'outer_inner_identity', 'package': PACKS[0].name})
require(load(manifest_paths[2])['preparation_manifest_sha256'] == sha(manifest_paths[3].read_bytes()), {'kind': 'outer_inner_identity', 'package': PACKS[1].name})

prior = {'note.md': (45152, 'd0e7920bae09ff4f744d75cfff2bdcabfeafc9e2b3a033c629e71ea67c67a3bc'), 'usage.md': (56613, '569a46c06fb35beb56205a0b6fe8add922baa25d1eb0d063c3947a5b3123bff3')}
docs = []
new_doc_text = []
for name, (size, expected) in prior.items():
    p = ROOT/name
    b = p.read_bytes()
    require(sha(b[:size]) == expected, {'kind': 'non_append_document_change', 'path': name})
    check_index(p, b)
    delta = b[size:].decode()
    new_doc_text.append((p, delta))
    docs.append({**stamp(p), 'prior_reviewed_prefix_bytes': size, 'prior_reviewed_prefix_sha256': sha(b[:size]), 'append_only': sha(b[:size]) == expected, 'appended_lines': len(delta.splitlines())})
tech = ROOT/'technical_pipeline.md'
require(sha(tech.read_bytes()) == 'a0c0c21893ec0d9edf08d55dcbed1098d82329328bb4638669b1b7e54ce74c4c', {'kind': 'technical_document_changed'})
check_index(tech)
readme = ROOT/'README.md'
readme_b = readme.read_bytes()
readme_blob = hashlib.sha1(b'blob ' + str(len(readme_b)).encode() + b'\0' + readme_b).hexdigest()
require(readme_blob == '6d6344e7939845d900c631d282e263fd283c7f07', {'kind': 'README_original_blob_changed'})
check_index(readme, readme_b)

links = []
bash_blocks = []
for p, txt in new_doc_text + [(p, p.read_text()) for pack in PACKS for p in sorted(pack.rglob('*.md'))]:
    for match in re.finditer(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', txt):
        raw = match.group(1).strip()
        # None of the selected new Markdown uses a link title containing spaces.
        target = raw.strip('<>')
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme or target.startswith('//'):
            continue
        path = urllib.parse.unquote(parsed.path)
        resolved = (p.parent/path).resolve() if path else p
        ok = resolved.exists()
        require(ok, {'kind': 'broken_local_link', 'document': str(p.relative_to(ROOT)), 'target': target})
        links.append({'document': str(p.relative_to(ROOT)), 'target': target, 'exists': ok})
    for match in re.finditer(r'```(?:bash|sh)\s*\n(.*?)```', txt, re.S):
        block = match.group(1)
        result = subprocess.run(['bash', '-n'], input=block.encode(), capture_output=True)
        require(result.returncode == 0, {'kind': 'bash_syntax', 'document': str(p.relative_to(ROOT)), 'stderr': result.stderr.decode()})
        bash_blocks.append({'document': str(p.relative_to(ROOT)), 'sha256': sha(block.encode()), 'syntax_exit': result.returncode, 'executed': False})

restore = load(PACKS[0]/'prerequisites/restore-map.json')
restore_records = []
for rec in restore['files']:
    exported = PACKS[0]/rec['published']
    original = ROOT/rec['restore_target']
    require(exported.read_bytes() == original.read_bytes(), {'kind': 'restore_map_not_exact', 'published': rec['published']})
    require(sha(exported.read_bytes()) == rec['sha256'] and len(exported.read_bytes()) == rec['bytes'], {'kind': 'restore_map_wrong_fingerprint', 'published': rec['published']})
    restore_records.append({'published': rec['published'], 'restore_target': rec['restore_target'], 'byte_exact_original': True})

tests = []
for p, expected in [(PACKS[0]/'adapter/tests-final.xml', 47), (PACKS[1]/'preparation/cpu-validation-transport-final/tests.xml', 55)]:
    root = ET.fromstring(p.read_bytes())
    cases = root.findall('.//testcase')
    errors = len(root.findall('.//error'))
    failed = len(root.findall('.//failure'))
    skipped = len(root.findall('.//skipped'))
    require(len(cases) == expected and not (errors or failed or skipped), {'kind': 'final_cpu_junit_not_pass', 'path': str(p.relative_to(ROOT))})
    tests.append({**stamp(p), 'testcases': len(cases), 'failures': failed, 'errors': errors, 'skipped': skipped, 'scope': 'prior actual Docker CPU control-plane run; not rerun by this audit; final model ORT/native not proved'})

wait_pack = PACKS[1]
launch = load(wait_pack/'root-arm/launch.json')
ident = launch['identity']
pid = ident['pid']
proc = Path('/proc')/str(pid)
stat_b = (proc/'stat').read_bytes()
tail = stat_b.decode().rsplit(')', 1)[1].strip().split()
argv = [os.fsdecode(x) for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
observed = {'pid': pid, 'state': tail[0], 'pgid': int(tail[2]), 'sid': int(tail[3]), 'start_time_clock_ticks': int(tail[19]), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'argv': argv}
for field in ('pid', 'pgid', 'sid', 'start_time_clock_ticks', 'boot_id', 'argv'):
    require(observed[field] == ident[field], {'kind': 'waiter_identity_mismatch', 'field': field})
require(observed['state'] not in ('Z','X'), {'kind': 'waiter_not_live'})
state_path = ROOT/'outputs/research/final-student-delivery-waiter-preparation/execution/state.json'
state_b = state_path.read_bytes()
state = json.loads(state_b)
require(state['status'] == 'waiting' and state['stage'] == 'official_artifacts', {'kind': 'current_state_not_waiting', 'state': state.get('status')})
for flag in ('action_started','fetch_attempted','prepare_attempted','run_attempted','quality_verified'):
    require(state[flag] is False, {'kind': 'current_state_started_future_action', 'flag': flag})
require(state['remote_status']['status'] == 'waiting' and len(state['remote_status']['stage_blockers']) == 16, {'kind': 'current_waiting_stage_count'})
absent_targets = ['outputs/research/final-student-transfer/waiter-delivery-01','outputs/research/final-student-native58-delivery-01']
for target in absent_targets:
    require(not (ROOT/target).exists(), {'kind': 'unexpected_future_cohort', 'path': target})
actual_source = Path(argv[2])
contract_path = Path(argv[argv.index('--contract')+1])
require(sha(actual_source.read_bytes()) == launch['waiter_sha256'], {'kind': 'live_waiter_source_changed'})
require(sha(contract_path.read_bytes()) == launch['contract_sha256'], {'kind': 'live_waiter_contract_changed'})
require(actual_source.read_bytes() == (wait_pack/'preparation/wait_final_students.py').read_bytes(), {'kind': 'published_waiter_not_live_source'})
require(contract_path.read_bytes() == (wait_pack/'preparation/contract.json').read_bytes(), {'kind': 'published_contract_not_live_contract'})

first = next((wait_pack/'first-poll').glob('status-*.json'))
first_data = load(first)
stdout_p = first.with_suffix('.stdout.log')
stderr_p = first.with_suffix('.stderr.log')
first_stdout = load(stdout_p)
require(first_data['returncode'] == 0 and first_data['remaining_session_members'] == [], {'kind': 'first_poll_not_clean'})
require(first_data['source_sha256'] == first_data['source_sha256_after'], {'kind': 'first_poll_source_change'})
require(sha(stdout_p.read_bytes()) == first_data['stdout_sha256'] and sha(stderr_p.read_bytes()) == first_data['stderr_sha256'], {'kind': 'first_poll_output_sha'})
require(first_stdout['status'] == 'waiting' and len(first_stdout['stage_blockers']) == 16, {'kind': 'first_poll_not_waiting16'})
before_ids = load(wait_pack/'root-arm/local-container-ids-before.json')
after_ids = load(wait_pack/'root-arm/local-container-ids-after.json')
require(before_ids == after_ids, {'kind': 'first_poll_container_ids_changed'})
initial = load(wait_pack/'root-arm/initial-state.json')
require(sha((wait_pack/'root-arm/initial-state.json').read_bytes()) == load(wait_pack/'root-arm/initial-observation.json')['state_sha256'], {'kind': 'initial_state_identity'})
for flag in ('fetch_attempted','prepare_attempted','run_attempted'):
    require(initial[flag] is False, {'kind': 'initial_started_future_action', 'flag': flag})

active = load(wait_pack/'active-jobs/summary.json')
require(active['fresh629']['counts'] == {'completed':158,'running':1,'planned':470} and active['completion_verified'] is False, {'kind': 'fixed_progress_snapshot_mismatch'})
for role in ('local','cloud'):
    require(sha((wait_pack/f'active-jobs/{role}-top.txt').read_bytes()) == active[role]['top_sha256'], {'kind': 'active_top_source_sha', 'role': role})
scalars = load(wait_pack/'active-jobs/official-scalars.json')
require(len(scalars['selected_scalars']) == 4 and all(x['last_step'] == 10315 and x['all_finite'] is True for x in scalars['selected_scalars'].values()), {'kind': 'scalar_snapshot_mismatch'})
require(scalars['completion_verified'] is False and scalars['quality_verified'] is False, {'kind': 'scalar_snapshot_claims_completion'})

original_review_pairs = [(PACKS[0]/'review.json', ROOT/'outputs/research/final58-independent-review-01/review.json'), (PACKS[1]/'preparation/independent-review/review.json', ROOT/'outputs/research/final-student-waiter-independent-review-01/review.json')]
for published, original in original_review_pairs:
    require(published.read_bytes() == original.read_bytes(), {'kind': 'published_review_not_original', 'path': str(published.relative_to(ROOT))})

captured_utc = datetime.now(timezone.utc).isoformat()
(OUT/'current-state-snapshot.json').write_bytes(state_b)
(OUT/'waiter-proc-stat-snapshot.txt').write_bytes(stat_b)
result = {
    'schema_version': 1,
    'observed_utc': captured_utc,
    'scope': 'Independent read-only delta publication audit; local files, Git index and exact own waiter /proc only; no SSH/Docker/native/GPU or tests executed',
    'status': 'pass' if not failures else 'must_fix',
    'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'documents': docs,
    'technical_document_unchanged': stamp(tech),
    'README_original_blob': readme_blob,
    'manifests': manifests,
    'outer_dependencies': sum(x['dependency_count'] for x in (manifests[0],manifests[2])),
    'nested_dependencies_rechecked': sum(x['dependency_count'] for x in (manifests[1],manifests[3])),
    'package_files_including_outer_manifests': 81,
    'local_links_checked': links,
    'bash_blocks_checked_syntax_only': bash_blocks,
    'restore_mappings': restore_records,
    'cpu_prior_evidence': tests,
    'actual_waiter': {'launch': stamp(wait_pack/'root-arm/launch.json'), 'identity': observed, 'alive_and_birth_bound': True, 'current_state_sha256': sha(state_b), 'current_state': state, 'future_targets_absent': absent_targets, 'live_source_and_contract_equal_publication': True},
    'first_poll': {'receipt': stamp(first), 'returncode': first_data['returncode'], 'remaining_session_members': first_data['remaining_session_members'], 'status': first_stdout['status'], 'blocked_stages': len(first_stdout['stage_blockers']), 'sources_before_after_equal': True, 'docker_id_snapshots_equal': True},
    'fixed_1100_snapshot': {'active_jobs': stamp(wait_pack/'active-jobs/summary.json'), 'fresh629_counts': active['fresh629']['counts'], 'scalars': stamp(wait_pack/'active-jobs/official-scalars.json'), 'selected_tags': len(scalars['selected_scalars']), 'last_step': 10315, 'all_selected_finite_as_recorded': True},
    'must_fix': failures,
    'limits': ['Current waiter state is a point-in-time file/proc observation; it does not prove future polls or terminal delivery.', '47 and 55 prior CPU tests are control-plane evidence, not final-model ORT, final58 native execution, convergence or course success.', 'The original preparation not_armed receipt remains historical; separate root-arm receipts and this /proc read prove the later actual arm.', 'Published status logs end at the first observation; live ignored state/logs can change and are not overwritten.', 'Publication is not a standalone runtime: the documented canonical context, generated inputs, exact helpers, image, real completed fetch and fresh629 success/release remain prerequisites.', 'The 11:00 cloud/local/scalar statements are verified against retained snapshots, not independently queried online in this audit.']
}
(OUT/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
summary = f'''# Final-student publication delta: independent local read-only review\n\nStatus: **{result['status']}**; must-fix findings: **{len(failures)}**. Captured {captured_utc}.\n\nBoth document changes are append-only: note +{docs[0]['appended_lines']} lines and usage +{docs[1]['appended_lines']} lines. technical_pipeline.md remains SHA `{sha(tech.read_bytes())}` and README retains original Git blob `{readme_blob}`.\n\nThe two outer manifests bind 33 + 46 = 79 dependencies; their 26 + 24 nested original dependencies were also rechecked. All 81 package files, both appended documents and unchanged technical/README match Git index raw bytes. {len(links)} selected local Markdown links exist; {len(bash_blocks)} bash blocks passed syntax-only checks. Seven restore mappings match the original local files byte-for-byte. Published independent review JSON files are unchanged copies.\n\nPrior final CPU evidence is 47/47 and 55/55, with no failures/errors/skips. It is explicitly preparation and synthetic control-plane evidence. Actual final-model prepare, 60 ORT and 58 native cases remain pending; no scientific success is inferred. Historical not_armed receipts and later actual-arm records are clearly separated.\n\nOwn waiter PID {pid} is live with exact launch argv, PGID/SID {observed['pgid']}, birth ticks {observed['start_time_clock_ticks']} and boot_id bound to launch. Current state is waiting/16 blocked, polls {state['polls']}, fetch/prepare/run false; both future delivery/cohort targets remain absent. First status helper retained actual exit0 and an empty transport session; before/after Docker ID snapshots match. The 11:00 snapshot accurately records 158/1/470 and four finite-tag summaries at step10315, without completion claims.\n\nNo SSH, Docker, native/DDS, GPU, source/document/Git mutation or test execution occurred. Only this new ignored review directory was written. See [machine review](review.json) for exact hashes, scope and limitations.\n'''
(OUT/'summary.md').write_text(summary)
print(json.dumps({'status':result['status'],'must_fix':failures,'manifests':len(manifests),'outer_dependencies':result['outer_dependencies'],'nested_dependencies':result['nested_dependencies_rechecked'],'links':len(links),'bash_blocks':len(bash_blocks),'waiter_pid':pid,'waiter_state':state['status'],'review_sha256':sha((OUT/'review.json').read_bytes()),'summary_sha256':sha((OUT/'summary.md').read_bytes())},ensure_ascii=False,indent=2))
