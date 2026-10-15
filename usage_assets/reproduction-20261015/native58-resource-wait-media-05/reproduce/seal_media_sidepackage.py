#!/usr/bin/env python3
"""Seal the actual native58 derived-media package after completed HTTP checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat

ROOT = Path('/home/dzp/projects/php_parkour')
RESEARCH = ROOT / 'outputs/research/reproduction-20261015'
PACKAGE = ROOT / 'usage_assets/reproduction-20261015/native58-resource-wait-media-05'
MAIN = ROOT / 'usage_assets/reports/final-student-native58-resource-wait-04'
MAIN_SHA = '8d9d0b733c4450d01a83f2aa84cde1f41b1f76f0cf50319cf884956d0c38a668'


def fp(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    assert not (PACKAGE / 'evidence-manifest.json').exists()
    restore_path = RESEARCH / 'native58-publication-resource-wait-preparation-05/restore.py'
    assert fp(restore_path)['sha256'] == '57be6ed4f884d4d9fbcb747260c39f8343d80cf117a46514d32a39fefa6c2cab'
    spec = importlib.util.spec_from_file_location('native58_media_main_source_verify', restore_path)
    restore = importlib.util.module_from_spec(spec); spec.loader.exec_module(restore)
    restore.verify(MAIN, MAIN_SHA)
    report_path = PACKAGE / 'browser/report.json'
    assert fp(report_path)['sha256'] == '4c9bc0cca48d53ce48182e815cf2f857afd8089535bced82fce2c78100f01b01'
    report = json.loads(report_path.read_bytes())
    assert report['status'] == 'passed_actual_http_gif_and_png_browser_decode' and report['browser_actual_wait_returncode'] == 0 and report['inputs_unchanged']
    assert len(report['decoded_images']) == 19 and len(report['gif_http_readbacks']) == 3
    parent = json.loads((PACKAGE / 'browser-parent/process-exit.json').read_bytes())
    assert parent['actual_wait_returncode'] == 0 and parent['pending_signals'] == [] and parent['launcher_sha256'] == 'e2384395eee2d8d574547ce5992ed163cce0060f554f654bec49ee3bc939ed15'
    unchanged_after_http = []
    for row in report['input_after']:
        if row['path'] == 'README.md':
            continue
        current = fp(PACKAGE / row['path'])
        assert current['bytes'] == row['bytes'] and current['sha256'] == row['sha256']
        unchanged_after_http.append(row['path'])
    metadata = json.loads((PACKAGE / 'manifest.json').read_bytes())
    assert metadata['source_main_seal']['sha256'] == MAIN_SHA
    for row in metadata['cases']:
        assert fp(Path(row['source_video']['path'])) == row['source_video']
        assert fp(PACKAGE / row['gif_path']) == row['gif']
        assert row['full_decode']['actual_wait_returncode'] == 0 and row['gif_metadata']['streams'][0]['nb_read_frames'] == '64'
    root_review = PACKAGE / 'evidence/root-visual-review.json'
    assert fp(root_review)['sha256'] == 'e97424b60ee01774fc499749cb798e31faf45d51619ed1de5a5ec8d9b5b38e87'
    source_copies = []
    copy_roots = [(RESEARCH / 'native58-contact-preview-05' / name, PACKAGE / 'contacts' / name)
                  for name in ['case-001', 'case-030', 'case-042', 'case-046', 'case-048', 'case-057', 'case-057-detail-4to8']]
    copy_roots += [(RESEARCH / 'native58-gif-http-05', PACKAGE / 'browser'), (RESEARCH / 'native58-gif-http-parent-05', PACKAGE / 'browser-parent')]
    for source, target in copy_roots:
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            assert not path.is_symlink()
            destination = target / path.relative_to(source)
            a, b = fp(path), fp(destination)
            assert (a['bytes'], a['sha256']) == (b['bytes'], b['sha256'])
            source_copies.append({'source': a, 'copied_path': destination.relative_to(PACKAGE).as_posix()})
    shutil.copy2(Path(__file__).absolute(), PACKAGE / 'reproduce/seal_media_sidepackage.py')
    files = []
    for path in sorted(PACKAGE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            row = fp(path); row['path'] = path.relative_to(PACKAGE).as_posix(); row['mode'] = stat.S_IMODE(path.stat().st_mode)
            assert row['bytes'] < 100 * 1024 * 1024
            files.append(row)
    seal = {'schema_version': 1, 'status': 'sealed_actual_native58_derived_media_side_package', 'files': files,
            'source_main_seal': fp(MAIN / 'evidence-manifest.json'), 'source_independent_review': metadata['source_independent_review'],
            'source_root_visual_review': metadata['source_root_visual_review'], 'source_copies': source_copies,
            'actual_http_report': fp(report_path), 'actual_http_parent_exit': fp(PACKAGE / 'browser-parent/process-exit.json'),
            'preseal_collection': {'unchanged_after_actual_HTTP_files': unchanged_after_http, 'README_updated_after_HTTP': True,
                'additional_files': ['browser receipts and raw files', 'root communicated derived-contact review', 'offline verifier and actual sealer source']},
            'quality_verified': False, 'course_success_verified': False,
            'scope': 'Actual derived media and evidence only. Three8-second movie intervals,64 frames each; encoded GIF duration8.01s due centisecond quantization. No new physics, exact policy-clock mapping, obstacle-crossing or course-success claim. Full original MP4/model/scientific assets remain separately linked and bound.'}
    restore.verify(MAIN, MAIN_SHA)
    seal_path = PACKAGE / 'evidence-manifest.json'; seal_path.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'seal': fp(seal_path), 'payload_files': len(files), 'payload_bytes': sum(r['bytes'] for r in files)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
