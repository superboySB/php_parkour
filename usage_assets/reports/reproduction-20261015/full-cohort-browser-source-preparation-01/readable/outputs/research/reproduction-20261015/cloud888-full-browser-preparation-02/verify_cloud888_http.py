#!/usr/bin/env python3
"""Browser adapter for the actual sealed236f full888 publication; no simulation."""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import sys
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
CORE = HERE.parent / 'evidence_http_browser.py'
PUBLISHER = HERE.parent / 'cloud888-publication-preparation-01/cloud888_report.py'
PUBLISHER_SHA = '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55'
SELECTION_SHA = 'e455f3da51248094099d948a9bdfe0acb92cf56aeb7e5ac8001b08ad280164fe'
INPUT_IDENTITY = '94477a0b18e673f0ee7d89523c398a2cb8a2dd2953734496afd1d7916d7aa916'
POLICIES = ('teacher', 'pure', 'finetune')
SKILLS = ('locomotion', 'low-step', 'high-step', 'low-climb-76', 'high-climb-76')
COUNTS = (100, 56, 60, 40, 40)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fp(path):
    raw = Path(path).read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def load(path, name, expected):
    raw = path.read_bytes()
    require(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'Compiled reader bytes differ from reviewed dependency')
    module = ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def relative(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and path.parts and str(path) == name, 'Unsafe package member')
    return name


def verify_raw_tree(root, inventory):
    """Read-only complete bytes/modes/file-set comparison to the sealed archive."""
    expected = [{k: r[k] for k in ('path', 'bytes', 'sha256', 'mode')} for r in inventory]
    require(len({r['path'] for r in expected}) == len(expected), 'Duplicate sealed original paths')
    for row in expected:
        relative(row['path'])
    actual = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Aliased restored coverage rejected')
        if path.is_dir():
            continue
        before = path.stat(); require(stat.S_ISREG(before.st_mode), 'Regular restored original required')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
        after = path.stat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, stat.S_IMODE(s.st_mode))
        require(signature(before) == signature(after), 'Restored original changed during read')
        actual.append({'path': path.relative_to(root).as_posix(), 'bytes': after.st_size,
                       'sha256': digest.hexdigest(), 'mode': stat.S_IMODE(after.st_mode)})
    actual.sort(key=lambda r: r['path'])
    require(actual == sorted(expected, key=lambda r: r['path']), 'Full restored coverage bytes/modes/file-set differ from sealed raw inventory')
    return {'root': str(root), 'original_files': len(actual), 'canonical_inventory_sha256': hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'complete_bytes_sha_modes_and_file_set_match': True}


def original_row(attempt, case, quality, observed_completion, videos, policy_video_span):
    """The pinned236f row projection, using original bound model/source/quality."""
    row = {k: attempt.get(k) for k in ('policy', 'case_id', 'source_clip_id', 'status', 'returncode', 'error', 'stop_reason')}
    row.update(skill=case['source']['skill'], source_frames=case['source']['frames'], checkpoint_sha256=case['checkpoint_sha256'],
               source_boundary_completed=False, videos=videos)
    row.update(stop_reason=quality.get('stop_reason'), policy_steps=quality.get('control_steps'), tracking_metrics=quality.get('metrics'))
    row.update(observed_completion)
    row['policy_video_span_covers_policy_steps'] = policy_video_span
    return row


def bind_raw_rows(helper, raw, published, inventory, validations):
    """Reuse the original stdlib verifier, then exactly compare all published rows."""
    selection, summary = helper.read(raw / 'selection.json'), helper.read(raw / 'summary.json')
    require(helper.sha(raw / 'selection.json') == SELECTION_SHA and selection['input_identity'] == INPUT_IDENTITY,
            'Restored actual final selection differs')
    monitor = helper.read(raw / 'monitor-status.json')
    require(summary['status'] == monitor['status'] == 'completed' and monitor['container_exit_code'] == 0
            and monitor['container'] == 'php-parkour-posttrain-gpu-' + INPUT_IDENTITY[:12], 'Original actual terminal monitor differs')
    original_cases = helper.verify_input_chain(raw, selection, summary)
    table = {r['path']: r for r in inventory}; bound_paths = set(); expected_rows = []; bindings = []
    for attempt in summary['cases']:
        case = original_cases[(attempt['policy'], attempt['case_id'])]
        directory = raw / attempt['policy'] / 'cases' / attempt['case_id']
        quality = helper.read(directory / 'quality.json')
        # verify_input_chain already verified the exact quality/native/model/
        # source identities and every declared quality-video byte fingerprint.
        trajectory = helper.local(raw, quality['trajectory']['path'])
        observed = helper.completion(quality, [json.loads(line) for line in trajectory.read_text().splitlines()])
        observed['reference_boundary_observed'] = observed['source_boundary_completed']
        observed['source_boundary_completed'] = observed['source_boundary_completed'] and attempt['status'] == 'execution_passed' and attempt['returncode'] == 0
        videos = []
        for video in quality['videos']:
            path = helper.local(raw, video['path']); record = table[path.relative_to(raw).as_posix()]
            require(record['storage'] == 'original' and record['sha256'] == video['sha256']
                    and record['bytes'] == video['bytes'], 'Original case-quality-video inventory fingerprint differs')
            bound_paths.add(record['path'])
            videos.append({'url': record['stored'], 'sha256': record['sha256'],
                           'duration_seconds': float(validations[record['sha256']]['metadata']['format']['duration']),
                           'association': video['association'], 'quality_bound': True})
        # Preserve the exact original236f distinction: this duration predicate
        # is evaluated on quality-bound videos before adding unbound originals.
        covers = bool(videos) and max(v['duration_seconds'] for v in videos) >= quality.get('policy_sim_seconds', 0) - .04
        prefix = directory.relative_to(raw).as_posix() + '/'
        for record in inventory:
            if record['path'].startswith(prefix) and record['storage'] == 'original' and record['path'] not in bound_paths:
                videos.append({'url': record['stored'], 'sha256': record['sha256'],
                               'duration_seconds': float(validations[record['sha256']]['metadata']['format']['duration']),
                               'quality_bound': False, 'association': 'Original MP4 absent from this quality report; retained and decoded, not proof of completion.'})
        expected_rows.append(original_row(attempt, case, quality, observed, videos, covers))
        bindings.append({'policy': case['policy'], 'case_id': case['case_id'], 'case': fp(directory / 'case.json'),
                         'quality': fp(directory / 'quality.json'), 'checkpoint_sha256': case['checkpoint_sha256'],
                         'source': case['source'], 'quality_video_original_paths': [v['path'] for v in quality['videos']]})
    require(published == expected_rows, 'Published case/model/source/quality/video/trajectory row differs from original sealed coverage')
    return {'selection': fp(raw / 'selection.json'), 'summary': fp(raw / 'summary.json'), 'monitor': fp(raw / 'monitor-status.json'),
            'cases': bindings, 'published_rows_exactly_recomputed': len(expected_rows),
            'scope': 'Read-only replay of original236f verify_input_chain/completion and row projection; no PT loading, GPU, simulation or new scientific runner.'}


def prefilter(summary, cases, inventory, sealed_files, validations):
    """Pure schema/cross-binding guard; all MP4s, including short/orphan clips."""
    require(summary['attempts'] == len(cases) == 888 and summary['original_batch_status'] == 'completed'
            and summary['input_identity'] == INPUT_IDENTITY and summary['quality_verified'] is False
            and summary['obstacle_course_completion_verified'] is False, 'Actual completed888 scope required')
    identities = [(r['policy'], r['case_id']) for r in cases]
    require(len(set(identities)) == 888 and Counter(r['policy'] for r in cases) == dict.fromkeys(POLICIES, 296), 'All unique888 first attempts required')
    groups = []
    source_ids = []
    for policy in POLICIES:
        chosen = [r for r in cases if r['policy'] == policy]
        ids = [r['source_clip_id'] for r in chosen]
        require(len(set(ids)) == 296, 'Policy source IDs must be unique')
        source_ids.append(set(ids))
        for skill, count in zip(SKILLS, COUNTS):
            selected = [r for r in chosen if r['skill'] == skill]
            require(len(selected) == count and all(type(r['source_boundary_completed']) is bool for r in selected), 'Original five source groups differ')
            groups.append({'policy': policy, 'skill': skill, 'attempts': count,
                           'execution_passed': sum(r['status'] == 'execution_passed' for r in selected),
                           'source_boundary_completed': sum(r['source_boundary_completed'] for r in selected)})
    require(source_ids[0] == source_ids[1] == source_ids[2], 'Policies must cover the same296 sources')
    require(len(summary['groups']) == 15 and all(all(actual[k] == expected[k] for k in expected) for actual, expected in zip(summary['groups'], groups)), 'Summary/group/case counters differ')
    require(all(r['status'] == 'execution_passed' and type(r['returncode']) is int and r['returncode'] == 0 for r in cases), 'Original888 execution must have passed')
    table = {r['path']: r for r in sealed_files}
    require(len(table) == len(sealed_files) and all(relative(k) == k for k in table), 'Unique safe sealed members required')
    media = {name: row for name, row in table.items() if name.endswith('.mp4')}
    require(media and summary['unique_videos_full_decoded'] == len(media), 'Every unique sealed MP4 must have full CPU validation')
    original_media = [r for r in inventory if r['storage'] == 'original' and r['stored'].endswith('.mp4')]
    require({r['stored'] for r in original_media} == set(media), 'Original inventory and sealed MP4 sets differ')
    references = {name: [] for name in media}
    original_records = {name: [] for name in media}
    require(len({r['path'] for r in original_media}) == len(original_media), 'Duplicate original MP4 paths')
    for row in original_media:
        require(relative(row['path']) == row['path'] and row['stored'] in media, 'Unsafe original MP4 inventory')
        require(type(row['mode']) is int and 0 <= row['mode'] <= 0o777, 'Original MP4 permission mode differs')
        wanted = media[row['stored']]
        require(row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256'], 'Original/sealed MP4 fingerprint differs')
        original_records[row['stored']].append(row)
    for case in cases:
        require(case['videos'], 'Each passed attempt requires retained video links')
        for index, video in enumerate(case['videos']):
            require(video['url'] in media and video['sha256'] == media[video['url']]['sha256'], 'Case video is outside the sealed MP4 set')
            references[video['url']].append({'policy': case['policy'], 'case_id': case['case_id'], 'video_index': index,
                                           'quality_bound': video['quality_bound'], 'association': video['association']})
    videos = []
    for name, row in sorted(media.items()):
        require(name == 'media/' + row['sha256'] + '.mp4' and row['bytes'] > 1, 'Canonical content-addressed positive MP4 required')
        validation = validations[row['sha256']]
        require(validation['sha256'] == row['sha256'] and validation['bytes'] == row['bytes']
                and validation['ffprobe_returncode'] == validation['ffmpeg_returncode'] == 0, 'Actual original CPU media validation differs')
        metadata = validation['metadata']; streams = metadata['streams']
        require(len(streams) == 1, 'One selected video stream expected from pinned ffprobe')
        stream = streams[0]; frames = int(stream['nb_read_frames']); duration = float(metadata['format']['duration'])
        require(frames == validation['decoded_frames'] > 0 and min(stream['width'], stream['height']) > 0
                and math.isfinite(duration) and duration > 0 and Fraction(stream['r_frame_rate']) > 0, 'Positive finite full media metadata required')
        videos.append({'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'], 'width': stream['width'], 'height': stream['height'],
                       'duration_seconds': duration, 'decoded_frames': frames, 'case_references': references[name],
                       'original_inventory_records': original_records[name],
                       'browser_play_scope': 'A one-frame/short clip can only prove decode, positive clock progression and end-of-media; not visible robot motion.' if frames == 1 or duration <= .2 else 'Bounded positive playback of the original encoded clip.'})
    for case in cases:
        for video in case['videos']:
            require(abs(video['duration_seconds'] - float(validations[video['sha256']]['metadata']['format']['duration'])) < .05, 'Case/CPU duration differs')
    return {'videos': videos, 'groups': groups, 'cases': len(cases), 'page_image_count': 0,
            'case_video_references': sum(len(r['videos']) for r in cases), 'one_frame_unique_videos': sum(v['decoded_frames'] == 1 for v in videos)}


def verify_ui(session, cases):
    require(session.evaluate('rows') == cases, 'Actual gallery row data differs from sealed cases')
    checks = {'filters': [], 'pagination': []}
    def change(name, value):
        text = session.evaluate("(()=>{const e=document.getElementById(" + json.dumps(name) + ");e.value=" + json.dumps(value) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return document.querySelector('#count').textContent;})()")
        return int(text.split(' ', 1)[0])
    for policy in POLICIES:
        require(change('policy', policy) == 296, 'Policy filter differs')
        for skill, count in zip(SKILLS, COUNTS):
            observed = change('skill', skill); require(observed == count, 'Policy/skill filter differs')
            checks['filters'].append({'policy': policy, 'skill': skill, 'count': observed})
        change('skill', '')
    change('policy', '')
    for value, completed in (('complete', True), ('incomplete', False)):
        observed = change('result', value); require(observed == sum(r['source_boundary_completed'] is completed for r in cases), 'Completion filter differs')
        checks['filters'].append({'result': value, 'count': observed})
    change('result', ''); change('policy', 'teacher')
    require(change('search', cases[0]['source_clip_id']) == 1, 'Policy/source search must isolate one source')
    checks['search'] = {'policy': 'teacher', 'source_clip_id': cases[0]['source_clip_id'], 'count': 1}
    change('search', ''); change('policy', '')
    for page in range(74):
        chosen = cases[page * 12:(page + 1) * 12]
        expected = [{'title': r['policy'] + ' · ' + r['skill'] + ' · ' + r['source_clip_id'],
                     'video': sorted(r['videos'], key=lambda v: -v['duration_seconds'])[0]['url'],
                     'links': [v['url'] for v in sorted(r['videos'], key=lambda v: -v['duration_seconds'])]} for r in chosen]
        observed = session.evaluate("Array.from(document.querySelectorAll('main article')).map(a=>({title:a.querySelector('h3').textContent,video:a.querySelector('video')?.getAttribute('src'),links:Array.from(a.querySelectorAll('a')).map(l=>l.getAttribute('href'))}))")
        require(observed == expected and len(observed) <= 12, 'All888 pagination identity/longest-video/original-links must match')
        checks['pagination'].append({'page': page + 1, 'cards': len(observed)})
        if page < 73:
            session.evaluate("document.querySelector('#next').click();true")
    change('policy', '')
    require(session.evaluate('document.images.length') == 0, 'Pinned236f gallery unexpectedly contains images')
    checks['page_images'] = []; checks['image_scope'] = 'Pinned236f gallery has no poster, PNG or SVG image elements; all original MP4 links are independently checked.'
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--preparation-sha256', required=True)
    parser.add_argument('--restored-coverage', type=Path, required=True, help='Actual complete coverage restored by the pinned236f helper, read-only verified against the sealed raw inventory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    preparation_path = HERE / 'manifest.json'
    require(fp(preparation_path)['sha256'] == args.preparation_sha256, 'Externally reviewed preparation SHA differs')
    preparation = json.loads(preparation_path.read_bytes())
    require(preparation['status'] == 'source_only_full888_http_browser_preparation', 'Wrong preparation scope')
    for row in preparation['dependencies']:
        require(fp(Path(row['path'])) == row, 'Frozen browser dependency differs')
    source_before = [fp(Path(r['path'])) for r in preparation['dependencies']] + [fp(preparation_path)]
    require(fp(PUBLISHER)['sha256'] == PUBLISHER_SHA, 'Pinned236f publication reader differs')
    dependencies = {r['path']: r for r in preparation['dependencies']}
    require(str(Path(__file__).absolute()) in dependencies and fp(Path(__file__).absolute()) == dependencies[str(Path(__file__).absolute())], 'Reviewed adapter source differs')
    helper = load(PUBLISHER, '_actual236_cloud888_browser_reader', dependencies[str(PUBLISHER)])
    core = load(CORE, '_reviewed_evidence_browser_core', dependencies[str(CORE)])
    package, output, raw = args.package.absolute(), args.output.absolute(), args.restored_coverage.absolute()
    require(package.resolve() == package and package.is_relative_to(ROOT / 'usage_assets') and output.resolve() == output
            and output.parent == HERE.parent and not output.exists()
            and not output.is_relative_to(package) and not package.is_relative_to(output), 'Actual package and fresh separate workspace output required')
    require(raw.resolve() == raw and raw.is_dir() and raw.is_relative_to(ROOT / 'outputs/research')
            and not any(p.is_symlink() for p in (raw, *raw.parents))
            and not output.is_relative_to(raw) and not raw.is_relative_to(output)
            and not output.is_relative_to(HERE) and not output.is_relative_to(PUBLISHER.parent),
            'Actual unaliased restored coverage and independent direct research sibling output required')
    seal_path = package / 'evidence-manifest.json'
    require(fp(seal_path)['sha256'] == args.manifest_sha256, 'External publication seal SHA differs')
    helper.verify_package(package)
    seal = helper.read(seal_path); require(seal['selection_sha256'] == SELECTION_SHA, 'Actual final888 selection differs')
    cases, summary = helper.read(package / 'cases.json'), helper.read(package / 'summary.json')
    table = {r['path']: r for r in seal['files']}
    validations = {Path(name).stem: helper.read(package / name) for name in table if name.startswith('media-validation/') and name.endswith('.json')}
    inventory = helper.read(package / 'raw-inventory.json')
    selected = prefilter(summary, cases, inventory, seal['files'], validations)
    require(set(validations) == {v['sha256'] for v in selected['videos']}, 'Exact complete CPU validation set differs')
    raw_before = verify_raw_tree(raw, inventory)
    original_binding = bind_raw_rows(helper, raw, cases, inventory, validations)
    require(original_binding['monitor']['sha256'] == summary['terminal_monitor_sha256'], 'Published monitor fingerprint differs from original')
    core.preflight_sources()
    seal_before = fp(seal_path)
    output.mkdir(parents=True)
    session = core.Session(output, ROOT)
    report = {'schema_version': 1, 'status': 'failed', 'package_seal_before': seal_before, 'source_before': source_before,
              'restored_raw_before': raw_before, 'original_case_model_video_binding': original_binding,
              'prefilter': selected, 'quality_verified': False, 'course_success_verified': False,
              'scope': 'All unique original MP4 metadata/Range/midpoint seek/bounded play and full888 page controls only. One-frame clips prove decode/progression/end, not visible robot motion. No scientific execution or exact policy-video mapping.'}
    content_passed = False
    try:
        base = session.start(); page_url = base + '/' + package.relative_to(ROOT).as_posix() + '/playback.html'
        session.navigate(page_url, "typeof rows!=='undefined' && !!document.querySelector('#count')")
        report['ui'] = verify_ui(session, cases)
        report['ranges'], report['videos'] = [], []
        for video in selected['videos']:
            path = package / video['path']; url = base + '/' + path.relative_to(ROOT).as_posix()
            report['ranges'].append(session.range_probe(path, video, {'media_path': video['path'], 'case_references': video['case_references']}))
            report['videos'].append(session.check_video(url, video))
        report['images'] = session.check_images([])
        require(report['images'] == [] and session.evaluate('document.images.length') == 0, 'Expected0 actual page images')
        screenshot = session.call('Page.captureScreenshot', {'format': 'png'})
        (output / 'playback.png').write_bytes(base64.b64decode(screenshot['data']))
        content_passed = True
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        try:
            report['lifecycle'] = session.close()
        except BaseException as error:
            report['lifecycle_error'] = type(error).__name__ + ': ' + str(error)
        try:
            helper.verify_package(package)
            report['restored_raw_after'] = verify_raw_tree(raw, inventory)
            report['package_seal_after'] = fp(seal_path)
            report['source_after'] = [fp(Path(r['path'])) for r in source_before]
            report['inputs_unchanged'] = (report['package_seal_after'] == seal_before and report['source_after'] == source_before
                                          and report['restored_raw_after'] == raw_before)
            report['requests'] = session.requests
            expected = {'/' + (package / v['path']).relative_to(ROOT).as_posix() for v in selected['videos']}
            browser = session.requests[session.browser_request_start:]
            actual = {r['path'].split('?', 1)[0] for r in browser if r['method'] == 'GET' and r['status'] == 206 and r['range']
                      and r['user_agent'] == session.browser_user_agent and r['path'].split('?', 1)[0].endswith('.mp4')}
            report['browser_range_expected_paths'] = sorted(expected); report['browser_range_verified_paths'] = sorted(actual & expected)
            report['all_unique_videos_browser_range_verified'] = expected <= actual
            report['content_http_errors'] = [r for r in session.requests if r['status'] >= 400 and not r['path'].startswith('/favicon.ico')]
        except BaseException as error:
            report['final_check_error'] = type(error).__name__ + ': ' + str(error)
        passed = (content_passed and report.get('inputs_unchanged') and report.get('all_unique_videos_browser_range_verified')
                  and not report.get('content_http_errors') and report.get('lifecycle', {}).get('lifecycle_passed')
                  and len(report.get('videos', [])) == len(report.get('ranges', [])) == len(selected['videos']))
        report['status'] = 'passed_actual_full888_http_browser_readback' if passed else 'failed'
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'report': fp(output / 'report.json')}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
