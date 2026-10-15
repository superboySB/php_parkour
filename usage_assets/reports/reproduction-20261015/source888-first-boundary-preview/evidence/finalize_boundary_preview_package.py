#!/usr/bin/env python3
"""Close actual single-source media evidence after CPU/browser/restore pass."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path('/home/dzp/projects/php_parkour')
REPRO = ROOT / 'outputs/research/reproduction-20261015'
RAW = REPRO / 'cloud888-first-boundary-preview-raw-01'
PACKAGE = ROOT / 'usage_assets/reports/reproduction-20261015/source888-first-boundary-preview'
CANDIDATE = '084a4281d52e67f70a6fbdc47344dfb7534faf1518f332da0cde0e94757576dc'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_bytes())


def main():
    assert sha(PACKAGE / 'evidence-manifest.json') == CANDIDATE
    helper = PACKAGE / 'cloud888_report.py'
    assert sha(helper) == '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
    spec = importlib.util.spec_from_file_location('single_source_archive', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_package(PACKAGE)
    case = load(RAW / 'raw-case/case.json')
    quality = load(RAW / 'raw-case/quality.json')
    attempt = load(RAW / 'raw-case/posttrain-attempt.json')
    trajectory = [json.loads(line) for line in (RAW / 'raw-case/trajectory.jsonl').read_bytes().splitlines()]
    assert attempt['status'] == 'execution_passed' and type(attempt['returncode']) is int and attempt['returncode'] == 0
    assert attempt['case_sha256'] == sha(RAW / 'raw-case/case.json') and attempt['case_id'] == case['case_id']
    for q, c in [('case_id', 'case_id'), ('policy', 'policy'), ('source', 'source'),
                 ('singleton_provenance_sha256', 'singleton_provenance_sha256'),
                 ('inventory_identity_sha256', 'inventory_sha256'), ('source_inventory', 'source_inventory'),
                 ('harness_sources', 'harness_sources'), ('runtime_robot_assets', 'runtime_robot_assets'),
                 ('native_argv', 'native_argv')]:
        assert quality[q] == case[c], q
    assert quality['checkpoint']['path'] == case['checkpoint'] and quality['checkpoint']['sha256'] == case['checkpoint_sha256']
    completion = module.completion(quality, trajectory)
    assert completion['source_boundary_completed'] and len(trajectory) == 490 and completion['policy_steps'] == 488
    http_root = REPRO / 'local-checks/first-boundary-http-01'
    browser = load(http_root / 'report.json')
    host = load(REPRO / 'local-checks/first-boundary-http-host-01/process-exit.json')
    restore_root = REPRO / 'local-checks/first-boundary-restore-01'
    restore = load(restore_root / 'exact-restoration-review.json')
    restored_child = load(restore_root / 'execution.json')
    gif = load(REPRO / 'local-checks/first-boundary-gif-01/report.json')
    gif_host = load(REPRO / 'local-checks/first-boundary-gif-host-01/execution.json')
    inspection = load(REPRO / 'local-checks/first-boundary-inspection-01/inspection.json')
    independent_decode = load(REPRO / 'local-checks/first-boundary-independent-decode-01/report.json')
    independent_decode_host = load(REPRO / 'local-checks/first-boundary-independent-decode-host-01/process-exit.json')
    assert browser['status'] == 'passed_actual_single_source_range_chrome_play_seek_images'
    assert browser['candidate_manifest_sha256'] == restore['candidate_manifest_sha256'] == CANDIDATE
    assert host['actual_wait_returncode'] == browser['browser_actual_wait_returncode'] == 0
    assert browser['inputs_unchanged'] and browser['http_server_stopped'] and not browser['http_content_errors']
    assert restore['original_files'] == 31 and restored_child['actual_wait_returncode'] == 0
    assert gif_host['actual_wait_returncode'] == 0 and gif['status'] == 'passed_actual_cpu_gif_derivation_full_decode'
    assert sum(v['decoded_frames'] for v in inspection['videos']) == 491
    assert independent_decode['status'] == 'passed_actual_independent_three_original_full_decodes'
    assert independent_decode['total_frames'] == 491 and independent_decode_host['actual_wait_returncode'] == 0
    for row in load(PACKAGE / 'raw-inventory.json'):
        source = RAW / row['path']
        assert source.stat().st_size == row['bytes'] and sha(source) == row['sha256']
    shutil.copyfile(PACKAGE / 'evidence-manifest.json', PACKAGE / 'evidence/browser-reviewed-candidate-manifest.json')
    for name in ['first-boundary-http-01', 'first-boundary-http-host-01', 'first-boundary-restore-01',
                 'first-boundary-independent-decode-01', 'first-boundary-independent-decode-host-01']:
        shutil.copytree(REPRO / 'local-checks' / name, PACKAGE / 'evidence' / name)
    shutil.copyfile(REPRO / 'decode_boundary_originals_cpu.py', PACKAGE / 'evidence/decode_boundary_originals_cpu.py')
    shutil.copyfile(Path(__file__), PACKAGE / 'evidence/finalize_boundary_preview_package.py')
    for source in [ROOT / 'scripts/research/serve_evidence.py',
                   ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce/verify_gallery.py',
                   ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py']:
        shutil.copyfile(source, PACKAGE / 'evidence' / source.name)
    report = {'status': 'passed_actual_single_source_postpublication_media_review',
        'reviewed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'case_id': case['case_id'], 'policy': case['policy'], 'source': case['source'],
        'checkpoint': quality['checkpoint'], 'completion': completion,
        'source_frames': 490, 'trajectory_rows': 490, 'native_attempt_returncode': 0,
        'case_sha256': sha(RAW / 'raw-case/case.json'), 'quality_sha256': sha(RAW / 'raw-case/quality.json'),
        'trajectory_sha256': sha(RAW / 'raw-case/trajectory.jsonl'),
        'original_cpu_decode': {'videos': 3, 'frames': 491, 'actual_host_wait_returncode': 0,
                                'actual_child_returncodes': [r['actual_wait_returncode'] for r in independent_decode['commands']],
                                'container_id': independent_decode_host['container_id'],
                                'container_started_at': independent_decode_host['container_started_at'],
                                'independent_report_sha256': sha(REPRO / 'local-checks/first-boundary-independent-decode-01/report.json'),
                                'independent_host_exit_sha256': sha(REPRO / 'local-checks/first-boundary-independent-decode-host-01/process-exit.json'),
                                'original_inspection_sha256': sha(REPRO / 'local-checks/first-boundary-inspection-01/inspection.json'),
                                'original_inspection_host_receipt_scope': 'Historical original inspection has internal eight command waits; no separately persisted outer host wait receipt. The independent decode supplies its own actual outer wait and typed before/after inspect.'},
        'gif_derivation': {'start_seconds': 1.76, 'end_seconds_exclusive': 9.76, 'width': 480, 'height': 270,
                           'fps': 8, 'frames': 64, 'full_decode_returncode': 0, 'actual_host_wait_returncode': 0,
                           'gif_sha256': sha(PACKAGE / 'preview.gif')},
        'http_browser': {'nonzero_exact_206_originals': 3, 'chrome_206_originals': 3,
                         'actual_host_wait_returncode': 0, 'actual_chrome_wait_returncode': 0,
                         'midpoint_seek': browser['seek'], 'playback': browser['play'],
                         'decoded_images': browser['images'], 'inputs_unchanged': True, 'server_stopped': True,
                         'candidate_manifest_sha256': CANDIDATE, 'report_sha256': sha(http_root / 'report.json')},
        'restore': {'original_files': 31, 'exact_bytes_sha_modes_file_set': True,
                    'actual_wait_returncode': 0, 'candidate_manifest_sha256': CANDIDATE,
                    'review_sha256': sha(restore_root / 'exact-restoration-review.json')},
        'visual_review': {'performed': True, 'reviewer': 'independent local_reproduce agent',
                          'images_inspected': ['contact-sheet.png', 'poster.png', 'evidence/first-boundary-gif-01/gif-contact-sheet.png', 'evidence/first-boundary-http-01/playback.png'],
                          'observations': 'Flat plane; standing initially, forward motion and turning, then standing at the end. No obstacle is visible. Original Commands: Not available overlay is preserved. Completion is derived from the original trajectory.'},
        'original_pending_review_preserved': True, 'full_888_terminal': False,
        'obstacle_course_completion_verified': False, 'must_fix': [],
        'scope': 'Actual completed single source, one terrain variant, seed42 first attempt and its media. This is not full888 acceptance or an obstacle-course success claim.'}
    module.save(PACKAGE / 'postpublication-media-review.json', report)
    with (PACKAGE / 'README.md').open('a') as f:
        f.write('\n后续实测媒体终态见 [postpublication-media-review.json](postpublication-media-review.json)：CPU/GIF完整解码、三原片精确 Range、Chrome 实际播放/拖动/图片解码、31 原件完整 SHA/bytes/mode/file-set 恢复均通过。原当时 pending 记录保持不变。\n\n自动 HTTP 再核验依赖原工作区的 Chrome/CDP/serve_evidence 文件；独立标准库 restore 不依赖原绝对工作区。浏览器核验候选 seal 与最终包新增的收据、终态审查由本包最终 evidence-manifest 全部封存。\n')
    files = [p for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p != PACKAGE / 'evidence-manifest.json']
    assert all(p.stat().st_size < 50_000_000 for p in files)
    module.save(PACKAGE / 'evidence-manifest.json', {'schema_version': 1,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_input_files': 31,
        'reviewed_candidate_manifest_sha256': CANDIDATE,
        'files': [{'path': p.relative_to(PACKAGE).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files],
        'scope': 'Single-source original archive and actual media/restore evidence; not888 terminal or obstacle-course success.'})
    module.verify_package(PACKAGE)
    print(json.dumps({'package': str(PACKAGE), 'final_manifest_sha256': sha(PACKAGE / 'evidence-manifest.json'),
                      'postpublication_review_sha256': sha(PACKAGE / 'postpublication-media-review.json'),
                      'files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
