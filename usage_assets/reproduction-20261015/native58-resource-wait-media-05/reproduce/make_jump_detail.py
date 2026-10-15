#!/usr/bin/env python3
"""Sixteen unchanged follow-view source frames from actual jump057 video [4,8)."""
import csv
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('actual_contact_helpers', HERE / 'make_contacts.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)


def main():
    package, root = helpers.PACKAGE, helpers.ROOT
    rows = helpers.read(package / 'cases.json')
    seal_before = helpers.fp(package / 'evidence-manifest.json'); assert seal_before['sha256'] == helpers.SEAL_SHA
    metadata = []
    mapping = helpers.read(package / 'restore-map.json')
    for ordinal in (1, 30, 57):
        case = rows[ordinal]; result = helpers.read(package / case['result_json'])
        record = next(row for row in mapping['retained'] if row['sha256'] == case['videos'][0]['sha256'] and row['workspace_relative'].endswith('.mp4'))
        original_case = (root / record['workspace_relative']).parent.parent
        released, clock = original_case / 'released.json', original_case / 'sim-clock.json'
        for path in (released, clock):
            bound = next(row for row in mapping['retained'] if row['workspace_relative'] == path.relative_to(root).as_posix())
            assert helpers.fp(path)['sha256'] == bound['sha256'] and helpers.fp(path)['bytes'] == bound['bytes']
        with (package / case['trajectory_csv']).open() as stream: trajectory = list(csv.DictReader(stream))
        metadata.append({'ordinal': ordinal, 'phase': case['phase'], 'case_id': case['case_id'],
            'video': case['videos'][0], 'actual_release_receipt': helpers.fp(released), 'released': helpers.read(released),
            'actual_final_clock_receipt': helpers.fp(clock), 'final_clock': helpers.read(clock),
            'actual_first_policy_csv_row': next(row for row in trajectory if float(row['policy_seconds']) >= 0),
            'actual_last_csv_row': trajectory[-1], 'configured_policy_duration_seconds': result['config']['duration'],
            'video_policy_mapping_scope': 'released.json and sim-clock.json bind actual simulator/policy clocks. No per-frame MP4 PTS to simulator clock mapping was recorded; do not claim an exact video-policy offset from these records.'})
    directory = HERE / 'case-057-detail-4to8'; directory.mkdir(exist_ok=False)
    review = helpers.read(HERE.parent / 'native58-resource-wait-independent-actual-review-04.json')
    before = helpers.decoder(directory, 'decoder-before', review['decoder_container'])
    case = rows[57]; video = package / case['videos'][0]['path']; source_before = helpers.fp(video)
    assert source_before['sha256'] == case['videos'][0]['sha256']
    indices = [round(200 + i * 199 / 15) for i in range(16)]
    expression = '+'.join('eq(n\\,' + str(index) + ')' for index in indices)
    native = '/workspace/php_parkour/' + video.relative_to(root).as_posix()
    raw, receipt = helpers.command(['docker', 'exec', helpers.CID, 'ffmpeg', '-nostdin', '-hide_banner', '-v', 'info',
        '-nostats', '-xerror', '-threads', '1', '-i', native, '-map', '0:v:0', '-vf',
        'select=' + expression + ',showinfo,tile=4x4', '-vsync', '0', '-frames:v', '1', '-c:v', 'png',
        '-threads', '1', '-f', 'image2pipe', '-progress', 'pipe:2', 'pipe:1'], directory, 'ffmpeg-detail')
    stderr = Path(receipt['stderr']['path']).read_text()
    assert re.findall(r'\[Parsed_showinfo_[^\]]*\]\s+n:\s*(\d+)', stderr) == [str(i) for i in range(16)]
    assert 'progress=end' in stderr and raw[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', raw[16:24]) == (2560, 1440)
    contact = directory / 'jump057-4to8-contact16.png'; contact.write_bytes(raw)
    after = helpers.decoder(directory, 'decoder-after', review['decoder_container'])
    assert before['id'] == after['id'] and before['started_at'] == after['started_at'] and helpers.fp(video) == source_before
    restore_path = HERE.parent / 'native58-publication-resource-wait-preparation-05/restore.py'
    spec = importlib.util.spec_from_file_location('full_seal_after_detail', restore_path)
    restore = importlib.util.module_from_spec(spec); spec.loader.exec_module(restore)
    restore.verify(package, helpers.SEAL_SHA); assert helpers.fp(package / 'evidence-manifest.json') == seal_before
    report = {'schema_version': 1, 'status': 'actual_jump057_contact16_and_timing_metadata_completed',
        'contact': helpers.fp(contact), 'source_video': source_before, 'video_interval_seconds': [4.0, 8.0],
        'selected_frame_indices': indices, 'selected_video_seconds': [index / 50 for index in indices],
        'frame_rate_source': 'Sealed original probe and actual prior ffprobe50/1',
        'ffmpeg': receipt, 'decoder_before': before, 'decoder_after': after, 'three_original_timing_metadata': metadata,
        'main_seal_before': seal_before, 'main_seal_after': helpers.fp(package / 'evidence-manifest.json'),
        'scope': 'Original640x360 follow-view frames tiled without crop/scale. Actual video times only; no GIF, new simulation, success claim or inferred exact MP4-policy alignment.'}
    (directory / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'manifest': helpers.fp(directory / 'manifest.json'), 'contact': report['contact']}))


if __name__ == '__main__': main()
