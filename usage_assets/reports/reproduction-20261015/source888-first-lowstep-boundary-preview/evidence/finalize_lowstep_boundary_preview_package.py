#!/usr/bin/env python3
"""Seal actual low-step single-source media after CPU/HTTP/restore/visual checks."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour');REPRO=ROOT/'outputs/research/reproduction-20261015'
RAW=REPRO/'cloud888-first-lowstep-boundary-preview-raw-01'
PACKAGE=ROOT/'usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-preview'
CANDIDATE='8030a4dbb3cb57fac8851570d5def05101bb3c34ed9a458b4c4ec0b7a9e3530b'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    assert sha(PACKAGE/'evidence-manifest.json')==CANDIDATE
    assert sha(PACKAGE/'cloud888_report.py')=='236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
    spec=importlib.util.spec_from_file_location('lowstep_original_archive',PACKAGE/'cloud888_report.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify_package(PACKAGE)
    case=read(RAW/'raw-case/case.json');quality=read(RAW/'raw-case/quality.json');attempt=read(RAW/'raw-case/posttrain-attempt.json')
    trajectory=[json.loads(line) for line in (RAW/'raw-case/trajectory.jsonl').read_bytes().splitlines()]
    assert attempt['status']=='execution_passed' and type(attempt['returncode']) is int and attempt['returncode']==0
    assert attempt['case_id']==case['case_id'] and attempt['case_sha256']==sha(RAW/'raw-case/case.json')
    for q,c in [('case_id','case_id'),('policy','policy'),('source','source'),('singleton_provenance_sha256','singleton_provenance_sha256'),('inventory_identity_sha256','inventory_sha256'),('source_inventory','source_inventory'),('harness_sources','harness_sources'),('runtime_robot_assets','runtime_robot_assets'),('native_argv','native_argv')]:assert quality[q]==case[c],q
    assert quality['checkpoint']['path']==case['checkpoint'] and quality['checkpoint']['sha256']==case['checkpoint_sha256']
    completion=module.completion(quality,trajectory)
    assert len(trajectory)==505 and completion['source_boundary_completed'] and completion['policy_steps']==503 and completion['failed_resets']==completion['timeout_resets']==0
    cpu_root=REPRO/'local-checks/first-lowstep-boundary-cpu-02';cpu=read(cpu_root/'report.json')
    cpu_host_root=REPRO/'local-checks/first-lowstep-boundary-cpu-host-02';cpu_host=read(cpu_host_root/'execution.json')
    http_root=REPRO/'local-checks/first-lowstep-boundary-http-01';browser=read(http_root/'report.json')
    http_host_root=REPRO/'local-checks/first-lowstep-boundary-http-host-01';http_host=read(http_host_root/'execution.json')
    restore_root=REPRO/'local-checks/first-lowstep-boundary-restore-01';restore=read(restore_root/'exact-restoration-review.json');restore_host=read(restore_root/'execution.json')
    assert cpu['status']=='passed_actual_independent_lowstep_three_full_decodes_and_gif' and cpu['total_decoded_frames']==506
    assert cpu_host['actual_wait_returncode']==0 and cpu_host['container_before_after_equal'] and cpu['all31_source_files_before_after_equal']
    assert all(row['actual_wait_returncode']==0 for row in cpu['commands'])
    assert cpu['gif']['frames']==64 and cpu['gif']['start_seconds']==2.06 and cpu['gif']['end_seconds_exclusive']==10.06
    assert browser['status']=='passed_actual_single_source_range_chrome_play_seek_images'
    assert http_host['actual_wait_returncode']==browser['browser_actual_wait_returncode']==0 and browser['inputs_unchanged'] and browser['http_server_stopped'] and not browser['http_content_errors']
    assert len(browser['range_checks'])==len(browser['browser_206_paths'])==3
    assert browser['candidate_manifest_sha256']==http_host['candidate_manifest_sha256']==restore['candidate_manifest_sha256']==CANDIDATE
    assert restore['original_files']==31 and restore['exact_bytes_sha_modes_file_set'] and restore_host['actual_wait_returncode']==0
    inventory=read(PACKAGE/'raw-inventory.json')
    for row in inventory:
        source=RAW/row['path'];assert source.stat().st_size==row['bytes'] and sha(source)==row['sha256']
    original_videos={row['sha256']:row for row in inventory if row['storage']=='original'};assert len(original_videos)==3
    for row in cpu['videos']:
        assert row['video']['sha256'] in original_videos and row['video']['bytes']==original_videos[row['video']['sha256']]['bytes']
    evidence=PACKAGE/'evidence'
    shutil.copyfile(PACKAGE/'evidence-manifest.json',evidence/'browser-reviewed-candidate-manifest.json')
    for name in ['first-lowstep-boundary-http-01','first-lowstep-boundary-http-host-01']:
        shutil.copytree(REPRO/'local-checks'/name,evidence/name)
    target=evidence/'first-lowstep-boundary-restore-01';target.mkdir()
    for name in ['process-start.json','execution.json','stdout.raw','stderr.raw','exact-restoration-review.json']:
        shutil.copyfile(restore_root/name,target/name)
    for name in ['run_lowstep_preview_checks.py','finalize_lowstep_boundary_preview_package.py']:
        shutil.copyfile(REPRO/name,evidence/name)
    for source in [ROOT/'scripts/research/serve_evidence.py',ROOT/'usage_assets/reports/official-evaluations-six/browser-reproduce/verify_gallery.py',ROOT/'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py']:
        shutil.copyfile(source,evidence/source.name)
    report={'status':'passed_actual_single_lowstep_source_postpublication_media_review','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'case_id':case['case_id'],'case_sha256':sha(RAW/'raw-case/case.json'),'quality_sha256':sha(RAW/'raw-case/quality.json'),'trajectory_sha256':sha(RAW/'raw-case/trajectory.jsonl'),'policy':case['policy'],'source':case['source'],'checkpoint':quality['checkpoint'],
            'completion':completion,'source_frames':505,'trajectory_rows':505,'native_attempt_returncode':0,
            'original_cpu_decode':{'videos':3,'frames':506,'actual_host_docker_exec_wait_returncode':cpu_host['actual_wait_returncode'],'actual_child_returncodes':[r['actual_wait_returncode'] for r in cpu['commands'][:6]],'container_id':cpu_host['container_id'],'container_started_at':cpu_host['container_started_at'],'report_sha256':sha(cpu_root/'report.json'),'host_execution_sha256':sha(cpu_host_root/'execution.json'),'original_root_inspection_sha256':sha(REPRO/'local-checks/first-lowstep-boundary-inspection-01/inspection.json'),'original_root_scope':'Original inspection preserves each actual Docker command Popen/wait/raw, but has no separate outer parent receipt. This independent02 execution retains its own actual host Docker-exec wait and before/after typed inspect.'},
            'gif_derivation':{'input_sha256':cpu['chosen']['sha256'],'start_seconds':2.06,'end_seconds_exclusive':10.06,'width':480,'height':270,'fps':8,'frames':64,'gif_sha256':sha(PACKAGE/'preview.gif'),'actual_host_wait_returncode':0,'full_decode_returncode':0},
            'http_browser':{'nonzero_exact_206_originals':3,'chrome_206_originals':3,'actual_host_wait_returncode':http_host['actual_wait_returncode'],'actual_chrome_wait_returncode':browser['browser_actual_wait_returncode'],'midpoint_seek':browser['seek'],'playback':browser['play'],'decoded_images':browser['images'],'inputs_unchanged':browser['inputs_unchanged'],'server_stopped':browser['http_server_stopped'],'candidate_manifest_sha256':CANDIDATE,'report_sha256':sha(http_root/'report.json')},
            'candidate_restore':{'original_files':31,'all_publication_files_normalized_to_git_mode':True,'exact_bytes_sha_modes_file_set':True,'actual_wait_returncode':0,'candidate_manifest_sha256':CANDIDATE,'review_sha256':sha(restore_root/'exact-restoration-review.json')},
            'visual_review':{'performed':True,'reviewer':'independent local_reproduce agent','images_inspected':['contact-sheet.png','obstacle-window.png','evidence/first-lowstep-boundary-cpu-02/gif-contact-sheet.png','evidence/first-lowstep-boundary-http-01/playback.png'],'observations':'Visible raised legs passing black step geometry, continued walking, then stable standing. Following camera and occlusion limit contact/full-obstacle interpretation. Original Commands: Not available overlay retained; local source completion comes from the original trajectory.'},
            'historical_host_assertion_failure_preserved':True,'original_pending_review_preserved':True,'full_888_terminal':False,'obstacle_course_completion_verified':False,'must_fix':[],
            'scope':'Actual one low-step source, single terrain variant, seed42 first attempt; not888 acceptance, completion ratio, generalization or complete obstacle-course success.'}
    module.save(PACKAGE/'postpublication-media-review.json',report)
    with (PACKAGE/'README.md').open('a') as f:
        f.write('\n媒体终态见 [postpublication-media-review.json](postpublication-media-review.json)：三原片独立 CPU 全解码、派生 GIF 全解码、精确非零 Range、Chrome 自身三原片206/播放/拖动/图片解码和31原件真实恢复均已通过。原当时 pending 字段与首次宿主列表顺序检查失败均原样保留。\n\n自动HTTP再检查依赖原工作区Chrome/CDP/serve_evidence；独立标准库restore不依赖原绝对工作区。浏览器候选seal保留在evidence内，最终seal另封新增的实际收据。\n')
    files=[p for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p!=PACKAGE/'evidence-manifest.json'];assert all(p.stat().st_size<50_000_000 for p in files)
    module.save(PACKAGE/'evidence-manifest.json',{'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_input_files':31,'reviewed_candidate_manifest_sha256':CANDIDATE,'files':[{'path':p.relative_to(PACKAGE).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files],'scope':'One low-step source original archive and actual CPU/GIF/browser/visual/restore evidence, not888 terminal or obstacle-course success.'})
    module.verify_package(PACKAGE)
    print(json.dumps({'package':str(PACKAGE),'final_manifest_sha256':sha(PACKAGE/'evidence-manifest.json'),'postpublication_review_sha256':sha(PACKAGE/'postpublication-media-review.json'),'files':len(files),'max_file_bytes':max(p.stat().st_size for p in files)},indent=2))
if __name__=='__main__':main()
