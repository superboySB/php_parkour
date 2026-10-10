#!/usr/bin/env python3
"""Local stdlib read-only compatibility probes. No publish/main/native calls."""
from pathlib import Path
from datetime import datetime, timezone
import collections
import hashlib
import importlib.util
import json

ROOT = Path('/home/dzp/projects/php_parkour')
BASE = ROOT/'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
OUT = Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_bytes())
def fp(path): return {'path':str(path.relative_to(ROOT)), 'bytes':path.stat().st_size, 'sha256':sha(path)}
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
def capture(fn):
    try:
        value=fn()
        return {'status':'accepted','value':value}
    except Exception as exc:
        return {'status':'rejected','error_type':type(exc).__name__,'error':str(exc)}
def fresh_path(value):
    path=Path(value)
    for prefix,target in [(Path('/workspace/php_parkour'),BASE/'source'), (Path('/outputs'),BASE/'outputs'),(Path('/data'),BASE/'inputs'),(Path('/control'),BASE/'control')]:
        if path.is_relative_to(prefix):return target/path.relative_to(prefix)
    raise ValueError('No retained cohort namespace binding: '+value)

pub=module('readonly_publisher',ROOT/'scripts/research/publish_full_scene_matrix.py')
plan=load(BASE/'inputs/native-plan.json')
hostplan=load(BASE/'host-plan.json')
matrix_path=BASE/'outputs/all-configs/matrix.json'
matrix_raw=matrix_path.read_bytes()
matrix=json.loads(matrix_raw)
receipt_raw=(BASE/'host/launch-receipt.json').read_bytes()
receipt=json.loads(receipt_raw)
freeze=load(BASE/'freeze-manifest.json')
freeze_index={r['relative']:r for r in freeze['files']}
frozen_native=module('readonly_frozen_matrix',BASE/'source/scripts/research/sim2sim_scene_matrix.py')
first=next(r for r in matrix['selections'] if r['status']=='completed')
directory=fresh_path(first['attempts'][-1]['output'])
result=load(directory/'result.json')
probes={
 'native_plan_shape':capture(lambda:pub.validate_plan(plan,matrix,hostplan['native_plan_sha256'],hostplan['matrix_source_sha256'],False)),
 'actual_host_receipt_as_legacy_driver':capture(lambda:pub.validate_driver(receipt,receipt,BASE/'host/run_fresh629.py',plan,matrix,hashlib.sha256(matrix_raw).hexdigest(),True,hostplan['matrix_source_sha256'])),
 'legacy_source_matrix_check':capture(lambda:str(pub.check_record(plan['source_matrix_record']))),
 'current_shared_worker_validator_with_correct_cohort_translation':capture(lambda:pub.validate_worker_receipts(directory,plan,result,translate=fresh_path)),
 'frozen_cohort_worker_validator_with_correct_cohort_translation':capture(lambda:frozen_native.validate_worker_receipts(directory,plan,result,translate=fresh_path)),
}
paths=[]
for value in [plan['source_matrix'],plan['dependencies'][0]['path'],plan['models'][0]['path'],first['attempts'][0]['output'],plan['worker_harness_record']['path']]:
    old=pub.host_path(value);fresh=fresh_path(value)
    paths.append({'native':value,'publisher_current':str(old),'actual_cohort':str(fresh),'same_path':old==fresh,'current_exists':old.exists(),'actual_exists':fresh.exists()})

native_records=[plan['source_matrix_record'],*plan['dependencies'],*plan['models'],*(r for s in plan['selections'] for r in s['source_files'])]
freeze_unbound=[]
for rec in native_records:
    relative=str(fresh_path(rec['path']).relative_to(BASE));retained=freeze_index.get(relative)
    if retained is None or retained['sha256']!=rec['sha256'] or retained['bytes']!=rec.get('bytes',rec.get('size')):
        freeze_unbound.append(relative)
findings=[
 {'id':'F1','severity':'compatibility_blocker','source':'scripts/research/publish_full_scene_matrix.py:63','finding':'host_path is the legacy live-workspace mapping, not the isolated cohort mapping. /data/matrix.json has no mapping at all; /outputs resolves outside the actual cohort; /workspace sources use live ROOT instead of frozen source.','actual_probe':'legacy_source_matrix_check','minimal_adaptation':'Add an explicit fresh-cohort contract deriving exact source/inputs/outputs/control mounts from the identity-bound host plan and original launch/inspect receipts. Reject foreign paths, symlinks and traversal. Do not rewrite native JSON or symlink missing paths into the old layout.'},
 {'id':'F2','severity':'compatibility_blocker','source':'scripts/research/publish_full_scene_matrix.py:125','finding':'The old launch/driver schema requires launcher_sha256/launch_exit_code/image_id and command/harness_sha256/returncode/completion_verified/finished_utc/matrix_sha256. Fresh host/launch-receipt is schema1 with native_argv, host plan identity, driver_returncode, observer_returncode, CPU finalizer result and stopped-owned-CID records. It never emits the old fields. Its native argv invokes /control/run_frozen_matrix.py, not a direct sim2sim_scene_matrix.py token.','actual_probe':'actual_host_receipt_as_legacy_driver','minimal_adaptation':'Validate the real fresh host receipt in a separate mode, bound to expected host/native plan identities and frozen host/control wrapper SHAs. Require actual completed status, driver0 and after-stop0, observer0, cpu_validation0, both stopped exact CIDs, finished_unix and no cleanup/post errors. Preserve original receipt bytes; do not synthesize a passing legacy receipt.'},
 {'id':'F3','severity':'compatibility_blocker','source':'scripts/research/sim2sim_scene_matrix.py:298','finding':'A correct fresh path translator still fails the currently imported validator because it anchors the harness path to that imported module ROOT. Current imported ROOT is the live repository; fresh harness is under cohort/source.','actual_probe':'current_shared_worker_validator_with_correct_cohort_translation','minimal_adaptation':'After checking its frozen dependency/manifest SHA, load the unchanged matrix module from cohort/source so its ROOT is naturally the frozen source. Keep the strict shared worker receipt validator and raw namespace values unchanged; the first real completed case passes this form.'},
 {'id':'F4','severity':'missing_fresh_publication_gate','source':'scripts/research/publish_full_scene_matrix.py:289','finding':'Publisher has no input or validation for the exact 1258 host command_writer birth/namespace mappings, original observer summary or exact own container identity. Native receipt validation proves private container process groups and entry births, not host PID/TID correspondence.','minimal_adaptation':'Require the terminal host receipt and observer summary/launch/inspect snapshots. Recheck one mapping for every (case, role, native PID, birth) with entry SHA, unique host thread (TID,birth), NSpid/NStgid endpoints and exact CID/image/StartedAt. Copy these original receipts and bind their SHAs in the publication manifest.'},
 {'id':'F5','severity':'missing_fresh_publication_gate','source':'scripts/research/publish_full_scene_matrix.py:208','finding':'Publisher checks stored ffprobe metadata and PNG header/dimensions only. It neither performs full video decode nor requires the actual CPU full-validation receipt; it therefore does not prove the fresh629 full-decode gate.','minimal_adaptation':'Consume host/final-validation/full-validation.json only after completed host receipt binds full_validation_sha256 and CPU exit0. Require passed/629cases/1258workers/629decodes, ordered exact case/result/three-receipt/video SHA+bytes correspondence, full_decode true/returncode0 and exact completed matrix/native plan identities. Preserve the actual ffmpeg command/stderr and original media bytes; do not relabel metadata probing as decoding.'},
 {'id':'F6','severity':'missing_fresh_publication_gate','source':'scripts/research/publish_full_scene_matrix.py:292','finding':'Publisher verifies the native input closure (376 dependencies, 1887 generated triples, 2 models and source matrix), but does not verify the identity-bound 5206-file fresh freeze manifest or host/control/CPU preflight contracts. 5206 is the total frozen source/input/control/evidence-file count, not 5206 distinct motion inputs.','minimal_adaptation':'Require expected host-plan identity, freeze_manifest_sha256 and snapshot_files_verified_before/after=5206; independently rehash every safe freeze entry before publication and verify identity-linked CPU-preflight receipt, native plan file and wrappers. Keep expected hashes fixed through copying. Retain the original freeze manifest and complete byte provenance; no need to duplicate all 5206 source bytes into the media gallery if retained source/archive availability is stated.'},
]
report={
 'schema_version':1,'observed_utc':datetime.now(timezone.utc).isoformat(),'status':'adaptation_required_not_published',
 'scope':'Local standard-library read-only code/schema compatibility audit. No main/publish/driver/finalizer executed, no media read/decode, no SSH/Docker/native/GPU/daemon or Git/source/raw mutation.',
 'reviewed_sources':[fp(ROOT/'scripts/research/publish_full_scene_matrix.py'),fp(ROOT/'scripts/research/sim2sim_scene_matrix.py'),fp(BASE/'source/scripts/research/sim2sim_scene_matrix.py'),fp(BASE/'host/run_fresh629.py'),fp(BASE/'host/prepare_fresh629.py'),fp(BASE/'control/run_frozen_matrix.py'),fp(BASE/'control/finalize_fresh629.py'),fp(BASE/'control/observe_container_pids.py'),fp(ROOT/'tests/test_publish_full_scene_matrix.py')],
 'cohort':{'base':str(BASE),'host_plan':fp(BASE/'host-plan.json'),'host_plan_identity':hostplan['plan_sha256'],'native_plan':fp(BASE/'inputs/native-plan.json'),'native_plan_identity':plan['plan_sha256'],'executed_plan_equal_inputs':load(BASE/'outputs/all-configs/plan.json')==plan,'matrix_sha256':hashlib.sha256(matrix_raw).hexdigest(),'matrix_status':matrix['status'],'selection_counts':dict(collections.Counter(r.get('status','planned') for r in matrix['selections'])),'host_receipt_sha256':hashlib.sha256(receipt_raw).hexdigest(),'host_receipt_status':receipt['status'],'terminal_observer_exists':(BASE/'host/observer/summary.json').exists(),'cpu_final_exists':(BASE/'host/final-validation/full-validation.json').exists(),'completion_claim':False},
 'path_comparison':paths,'readonly_function_probes':probes,
 'freeze_contract':{'manifest':fp(BASE/'freeze-manifest.json'),'manifest_identity_matches_host_plan':sha(BASE/'freeze-manifest.json')==hostplan['freeze_manifest_sha256'],'entries':len(freeze['files']),'prefix_counts':dict(collections.Counter(r['relative'].split('/')[0] for r in freeze['files'])),'source_files_declared':hostplan['source_files'],'generated_inputs_declared':hostplan['generated_input_files'],'native_plan_records_in_freeze_checked':len(native_records),'unbound_or_different_fingerprint_records':freeze_unbound,'all5206_current_bytes_rehashed':False},
 'findings':findings,
 'compatible_reusable_contracts':['Explicit expected plan/harness identities are already CLI requirements; native schema3 plan shape and immutable case order accept the actual frozen plan.', 'Schema3 worker supervisor and three-receipt sealing can be reused unchanged under the correct frozen module ROOT.', 'Byte-exact copy, sealed historical-attempt checks, threshold preservation, 24-card pagination, CSV/JSON and world-XY gallery remain suitable after a strict fresh-cohort validation stage.', 'Current rejection is safe. Running matrix/missing terminal observer and CPU final receipts are expected incomplete state, not a fault to bypass.'],
 'minimum_tests_for_future_adapter':['Actual fresh-schema read-only fixture; reject old schema silently coerced to fresh.', 'Foreign mount/live ROOT substitution, .. and symlink rejection; correct frozen validator module binding.', 'Host receipt nonterminal/nonzero/still-running/wrong CID/image/StartedAt/plan rejects.', 'Missing/duplicate/reused birth or case/role hostwriter mapping rejects, exact1258 required.', 'CPU final wrong native plan/matrix/result/worker/video SHA, decode false/nonzero/missing629 rejects.', 'Freeze manifest or one frozen input/control/current copy tampering rejects; copy retains original expected hashes.', 'A two-case preview remains explicitly partial and cannot claim1258/629/5206 terminal success.'],
 'limitations':['Only the first already completed case three-receipt validation was probed, not all currently completed cases.', 'No full video decode or 5206-byte rehash was performed in this audit. The existing actual automatic finalizer remains responsible for future terminal CPU evidence.', 'No existing active cohort control/core is changed. A separate reviewed publisher adapter can be developed without disturbing it.']
}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
summary='''# Fresh629 publisher compatibility review\n\nThe current `scripts/research/publish_full_scene_matrix.py` **cannot directly publish this isolated fresh629 cohort**. Its strict rejection is safe; the current run is still in progress and is not certified by this audit.\n\nSix concrete boundaries need a separate strict cohort adapter:\n\n1. Legacy `host_path` maps `/outputs` to the wrong directory, `/workspace` to live source, and does not map `/data/matrix.json`. The actual mounts are `base/{outputs,source,inputs,control}`.\n2. Legacy driver/launch keys and direct-driver argv differ from the actual fresh host schema1 receipt and `/control/run_frozen_matrix.py` invocation. Validate the original host receipt, do not fabricate old-schema success JSON.\n3. Correct path translation alone still fails the shared validator's `ROOT` anchor. A read-only probe confirmed the live imported validator rejects it; the unchanged frozen cohort matrix module accepts the first real completed case's three receipts.\n4. Require/recheck all1258 exact hostwriter PID/TID birth/namespace mappings and original observer/CID/image/birth receipts. The current publisher checks only native receipts.\n5. Bind the actual terminal CPU full-validation report:629 full MP4 decodes,1258 workers, exact case/result/receipt/video SHA+bytes. Current publisher only checks stored metadata and PNG dimensions.\n6. Bind/recheck the host plan and all5206 frozen files, CPU preflight and wrapper identities. Current publisher verifies native376+1887+models+matrix closure only.5206 is a total frozen-file count, not distinct motion inputs.\n\nThe existing byte-copy/history/threshold-preservation/paged-gallery logic can be reused after those gates. Original JSON, namespace paths, failed attempts and quality=false remain unchanged. No GPU/native/daemon/SSH/Docker, publishing, decoding, tests or tracked/raw edits occurred. See [review.json](review.json) for exact source hashes, line references, actual read-only probes and minimum adapter tests.\n'''
(OUT/'summary.md').write_text(summary)
print(json.dumps({'review_sha256':sha(OUT/'review.json'),'summary_sha256':sha(OUT/'summary.md'),'status':report['status'],'selection_counts':report['cohort']['selection_counts'],'probes':probes,'freeze_unbound':freeze_unbound},ensure_ascii=False,indent=2))
