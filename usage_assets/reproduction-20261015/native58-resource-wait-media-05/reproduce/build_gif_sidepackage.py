#!/usr/bin/env python3
"""Three authorized movie-time GIFs from actual sealed native58 originals."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('actual_native58_contact_helpers', HERE / 'make_contacts.py')
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
ROOT, MAIN = helper.ROOT, helper.PACKAGE
OUTPUT = ROOT / 'usage_assets/reproduction-20261015/native58-resource-wait-media-05'
CLIPS = ((1, 'pure-forward-fall', '纯学生前进跌倒', 3.90, 11.90),
         (30, 'finetune-forward', '混合学生前进', 3.90, 11.90),
         (57, 'finetune-low-beam', '混合学生低横梁附近腾起／继续跑动', 4.00, 12.00))


def native(path): return '/workspace/php_parkour/' + path.relative_to(ROOT).as_posix()


def main():
    restore_path = HERE.parent / 'native58-publication-resource-wait-preparation-05/restore.py'
    spec = importlib.util.spec_from_file_location('actual_native58_gif_source_guard', restore_path)
    restore = importlib.util.module_from_spec(spec); spec.loader.exec_module(restore)
    restore.verify(MAIN, helper.SEAL_SHA)
    seal_before = helper.fp(MAIN / 'evidence-manifest.json'); assert seal_before['sha256'] == helper.SEAL_SHA
    rows = helper.read(MAIN / 'cases.json')
    review_path = HERE.parent / 'native58-resource-wait-independent-actual-review-04.json'
    review = helper.read(review_path)
    timing_path = HERE / 'case-057-detail-4to8/manifest.json'
    timing = {row['ordinal']: row for row in helper.read(timing_path)['three_original_timing_metadata']}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT / 'cpu').mkdir(); (OUTPUT / 'evidence').mkdir()
    before_decoder = helper.decoder(OUTPUT / 'cpu', 'decoder-before', review['decoder_container'])
    contact_rows = []
    for ordinal in helper.ORDINALS:
        source = HERE / ('case-' + str(ordinal).zfill(3)); record = helper.read(source / 'manifest.json')
        assert record['source_video']['sha256'] == rows[ordinal]['videos'][0]['sha256']
        for item in record['derived_files']: assert helper.fp(Path(item['path'])) == item
        target = OUTPUT / 'contacts' / source.name
        shutil.copytree(source, target)
        contact_rows.append({'ordinal': ordinal, 'case_id': rows[ordinal]['case_id'],
            'source_manifest': helper.fp(source / 'manifest.json'), 'copied_contact': target.relative_to(OUTPUT).as_posix() + '/contact-8frames.png',
            'copied_original_poster': target.relative_to(OUTPUT).as_posix() + '/original-poster.png'})
    shutil.copytree(HERE / 'case-057-detail-4to8', OUTPUT / 'contacts/case-057-detail-4to8')
    shutil.copy2(MAIN / 'evidence-manifest.json', OUTPUT / 'evidence/source-main-evidence-manifest.json')
    shutil.copy2(review_path, OUTPUT / 'evidence/source-independent-review.json')
    clips = []
    for ordinal, name, title, start, end in CLIPS:
        case = rows[ordinal]; source = MAIN / case['videos'][0]['path']; source_before = helper.fp(source)
        assert source_before['sha256'] == case['videos'][0]['sha256'] and 0 <= start < end <= case['videos'][0]['duration_seconds']
        directory = OUTPUT / 'cpu' / name; directory.mkdir()
        filters = 'fps=8,scale=480:270:flags=lanczos,split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a'
        gif_raw, encoded = helper.command(['docker', 'exec', helper.CID, 'ffmpeg', '-nostdin', '-v', 'error', '-xerror',
            '-threads', '1', '-ss', str(start), '-t', str(end - start), '-i', native(source), '-filter_complex_threads', '1',
            '-filter_complex', filters, '-loop', '0', '-f', 'gif', '-progress', 'pipe:2', 'pipe:1'], directory, 'gif-encode')
        assert gif_raw[:6] in (b'GIF89a', b'GIF87a')
        gif = OUTPUT / (name + '.gif'); gif.write_bytes(gif_raw)
        probe_raw, probed = helper.command(['docker', 'exec', helper.CID, 'ffprobe', '-v', 'error', '-count_frames',
            '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height,nb_read_frames:format=duration',
            '-of', 'json', native(gif)], directory, 'gif-probe')
        metadata = json.loads(probe_raw); stream = metadata['streams'][0]
        assert stream['codec_name'] == 'gif' and (stream['width'], stream['height'], int(stream['nb_read_frames'])) == (480, 270, 64)
        assert abs(float(metadata['format']['duration']) - 8.0) < .02
        _, decoded = helper.command(['docker', 'exec', helper.CID, 'ffmpeg', '-nostdin', '-v', 'error', '-xerror',
            '-threads', '1', '-i', native(gif), '-map', '0:v:0', '-an', '-sn', '-dn', '-f', 'null',
            '-progress', 'pipe:1', '-'], directory, 'gif-full-decode')
        progress = Path(decoded['stdout']['path']).read_text()
        assert 'progress=end' in progress and int(re.findall(r'^frame=(\d+)$', progress, re.M)[-1]) == 64
        indices = [round(i * 63 / 7) for i in range(8)]
        expression = '+'.join('eq(n\\,' + str(i) + ')' for i in indices)
        image_raw, gif_contact = helper.command(['docker', 'exec', helper.CID, 'ffmpeg', '-nostdin', '-hide_banner', '-v', 'info',
            '-nostats', '-xerror', '-threads', '1', '-i', native(gif), '-map', '0:v:0', '-vf',
            'select=' + expression + ',showinfo,tile=4x2', '-vsync', '0', '-frames:v', '1', '-c:v', 'png', '-threads', '1',
            '-f', 'image2pipe', '-progress', 'pipe:2', 'pipe:1'], directory, 'gif-contact')
        stderr = Path(gif_contact['stderr']['path']).read_text()
        assert re.findall(r'\[Parsed_showinfo_[^\]]*\]\s+n:\s*(\d+)', stderr) == [str(i) for i in range(8)]
        assert struct.unpack('>II', image_raw[16:24]) == (1920, 540)
        contact = OUTPUT / (name + '-gif-contact.png'); contact.write_bytes(image_raw)
        case_evidence = OUTPUT / 'evidence' / name; case_evidence.mkdir()
        for label, path in [('result.json', MAIN / case['result_json']), ('trajectory.csv', MAIN / case['trajectory_csv']),
                            ('released.json', Path(timing[ordinal]['actual_release_receipt']['path'])),
                            ('sim-clock.json', Path(timing[ordinal]['actual_final_clock_receipt']['path']))]:
            shutil.copy2(path, case_evidence / label)
            assert helper.fp(path)['sha256'] == helper.fp(case_evidence / label)['sha256']
        assert helper.fp(source) == source_before
        clips.append({'ordinal': ordinal, 'title': title, 'source_case': case, 'source_video': source_before,
            'source_video_relative_root': source.relative_to(ROOT).as_posix(), 'movie_interval_seconds': [start, end],
            'gif': helper.fp(gif), 'gif_path': gif.name, 'gif_metadata': metadata, 'gif_contact': helper.fp(contact),
            'gif_contact_path': contact.name, 'gif_contact_indices': indices, 'timing_evidence': timing[ordinal],
            'encode': encoded, 'probe': probed, 'full_decode': decoded, 'contact_cpu': gif_contact,
            'scope': '8-second movie-PTS excerpt,480x270/8FPS/64frames; not exact policy-clock alignment or course success.'})
    after_decoder = helper.decoder(OUTPUT / 'cpu', 'decoder-after', review['decoder_container'])
    assert before_decoder['id'] == after_decoder['id'] and before_decoder['started_at'] == after_decoder['started_at']
    restore.verify(MAIN, helper.SEAL_SHA); assert helper.fp(MAIN / 'evidence-manifest.json') == seal_before
    for name in ('make_contacts.py', 'make_jump_detail.py', 'build_gif_sidepackage.py'):
        (OUTPUT / 'reproduce').mkdir(exist_ok=True); shutil.copy2(HERE / name, OUTPUT / 'reproduce' / name)
    manifest = {'schema_version': 1, 'status': 'actual_derived_native58_three_movie_GIFs_and_contacts',
        'source_main_seal': seal_before, 'source_independent_review': helper.fp(review_path), 'cases': clips,
        'six_full_movie_contacts': contact_rows, 'jump057_detail_contact': 'contacts/case-057-detail-4to8/jump057-4to8-contact16.png',
        'decoder_before': before_decoder, 'decoder_after': after_decoder, 'quality_verified': False,
        'scope': 'Three root-viewed authorized bounded8-second movie clips only. Original58 seal/MP4 unchanged. Pure forward fall, finetune forward, finetune knee-flexion/rise near low beam then running; no evidence of completing full obstacle course. No exact PTS-policy mapping was recorded.'}
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    cards = []
    for clip in clips:
        href = os.path.relpath(ROOT / clip['source_video_relative_root'], OUTPUT)
        cards.append('<article><h2>' + clip['title'] + '</h2><p>原片时间[' + str(clip['movie_interval_seconds'][0]) + ',' + str(clip['movie_interval_seconds'][1]) + ')秒；8FPS/64帧；不代表课程成功。</p><img src="' + clip['gif_path'] + '" width="480" height="270"><p><a href="' + href + '">完整原始MP4</a> · <a href="' + clip['gif_contact_path'] + '">GIF8帧联系图</a></p></article>')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>最终学生：三段真实行为截片</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;background:#111827;color:#e5e7eb;padding:20px}a{color:#93c5fd}article{margin:24px 0}img{max-width:100%;height:auto}</style><h1>最终自训学生：三段真实行为截片</h1><p>来自已独立审查的58项原生仿真。本页仅保留指定8秒原片区间；不把survival启发式或未触发阈值称为课程成功。视频时间与policy时钟没有逐帧精确映射。</p><p><a href="manifest.json">原片／case／指标／CPU／时间绑定</a></p>' + ''.join(cards) + '</html>'
    (OUTPUT / 'playback.html').write_text(page)
    (OUTPUT / 'README.md').write_text('三段最终学生实际movie时间截片，含3GIF、各8帧GIF联系图、6组全片8帧+原poster、057[4,8)16原帧、完整CPU argv/wait/raw、原case/result/CSV/release/clock、原58公开seal与独立review。001/030原片[3.90,11.90)，057[4.00,12.00)，480×270/8FPS/64帧，完整CPUdecode0。原MP4与58 seal保持不变。057近低横梁端部的跟随视角不足确认正向跨过整道横梁；全部只能称bounded8秒行为，不称技能或课程成功。各时钟原件保留；没有逐帧MP4PTS→policy时钟记录，不推定精确offset。HTTP/Chrome验收原件另存后再封本侧包。reproduce内源码记录实际历史b4 RO CPU调用；重放须有等价CPU ffmpeg及可验证同SHA原片，不代表提供新的科学runner。\n')
    print(json.dumps({'status': manifest['status'], 'output': str(OUTPUT), 'manifest': helper.fp(OUTPUT / 'manifest.json'), 'gifs': [clip['gif'] for clip in clips]}))


if __name__ == '__main__': main()
