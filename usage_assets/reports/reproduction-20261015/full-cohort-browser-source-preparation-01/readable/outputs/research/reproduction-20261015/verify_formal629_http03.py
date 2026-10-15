#!/usr/bin/env python3
"""Source-only prepared full formal1258 gallery HTTP/CPU-browser verification.

Requires a real already complete sealed publication, explicit external SHA and
reviewed source preparation. No science, Docker, restore or browser install.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from types import ModuleType
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = ROOT/'outputs/research/reproduction-20261015'
PREPARATION = HERE/'formal629-http-browser-preparation-03/manifest.json'
PUBLICATION = ROOT/'outputs/research/final-student-reference629-crossboot-publication-preparation-02'
PUBLICATION_SHA = '255c2a87cc97945ca5cb923ec343264b952c371c1b43bed1efacf6afd96fa412'
RESTORE_SHA = '0a31a96e3faeeb86e095a49fa5d39dd517b12c99734385016fbe08cb4ce86425'
KINDS = ('pure', 'finetune')
COUNTS = {'policies': 2, 'cases': 1258, 'workers': 2516, 'host_maps': 2516, 'full_decodes': 1258}


def require(value, message):
    if not value:
        raise ValueError(message)


def strict_json(path):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'Duplicate JSON key'); out[key] = value
        return out
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON '+value)))


def file_fp(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file(), 'Regular unaliased source required')
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def checked_module(path, row, name):
    require(file_fp(path) == row, 'Bound browser source changed')
    module = ModuleType(name); module.__file__ = str(path); module.__package__ = ''
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def member(package, kind, name, files):
    rel = Path(name); raw = package/kind/rel
    require(not rel.is_absolute() and '\\' not in name
            and not any(p.is_symlink() for p in (raw, *raw.parents)), 'Unaliased gallery-relative member required')
    target = raw.resolve(strict=True)
    require(target.is_relative_to(package) and target.is_file(), 'Gallery member escaped package')
    key = target.relative_to(package).as_posix(); require(key in files, 'Gallery media absent from actual seal')
    return target


def validate_rows(package, summary, all_rows, files):
    require(summary['status'] == 'completed_formal_pair_publication'
            and all(type(summary[k]) is int and summary[k] == v for k, v in COUNTS.items())
            and summary['kind_order'] == list(KINDS) and summary['quality_verified'] is False
            and summary['obstacle_course_completion_verified'] is False, 'Complete formal1258 summary required')
    records, video_paths, image_count = {}, set(), 0
    for kind in KINDS:
        rows, sub = all_rows[kind], strict_json(package/kind/'summary.json')
        expected = next(x for x in summary['kinds'] if x['model_kind'] == kind)
        require(len(rows) == 629 and [x['ordinal'] for x in rows] == list(range(629))
                and len({x['case_id'] for x in rows}) == 629 and len({x['scenario'] for x in rows}) == 17
                and sub['status'] == 'completed_publication' and sub['model_kind'] == kind and sub['preview'] is False
                and sub['configurations'] == sub['planned_configurations'] == 629
                and sub['model_sha256'] == expected['model_sha256']
                and sub['quality_verified'] is sub['obstacle_course_completion_verified'] is False,
                'Exact two model629 galleries required')
        for row in rows:
            require(row['model_kind'] == kind and row['status'] == 'completed' and len(row['videos']) == 1
                    and row['quality_verified'] is row['obstacle_course_completion_verified'] is False,
                    'Single original video per completed formal case required')
            video = row['videos'][0]
            require(type(video['width']) is int and type(video['height']) is int and min(video['width'], video['height']) > 0
                    and math.isfinite(video['duration_seconds']) and video['duration_seconds'] > 0, 'Positive finite video metadata required')
            path = member(package, kind, video['path'], files); require(path.suffix.lower() == '.mp4', 'Original MP4 required')
            video_paths.add(str(path))
            image_paths = [member(package, kind, row['trajectory_svg'], files), member(package, kind, video['thumbnail'], files)]
            image_count += len(image_paths)
            records[(kind, row['case_id'])] = {'video': path, 'images': image_paths, 'expected': video}
        require(sum(x['threshold_event'] for x in rows) == sub['threshold_events']
                and sum(not x['threshold_event'] for x in rows) == sub['no_threshold_events'], 'Outcome filter denominators differ')
    require(len(records) == 1258 and 0 < len(video_paths) <= 1258 and image_count == 2516, 'Full1258 case-video/2516 image visits required')
    return records


def actual_model_table(contract, kind):
    selected = [row for row in contract['admission']['models'] if row['kind'] == kind]
    require(len(selected) == 2 and {Path(x['path']).name for x in selected} == {'student.onnx', 'depth_backbone.onnx'}
            and all(type(x['bytes']) is int and x['bytes'] > 0 and re.fullmatch('[0-9a-f]{64}', x['sha256']) for x in selected),
            'Actual sealed contract must bind both positive ONNX model fingerprints')
    return {Path(x['path']).name: x['sha256'] for x in selected}


def validate_case_binding(package, kind, row, record, contract, mappings, files):
    """Bind a gallery case to its original result/model/video, allowing byte aliases."""
    def linked(actual, original):
        require(str(original) in mappings, 'Original case/model missing from sealed restore-map')
        entry = mappings[str(original)]
        require(entry['storage']['kind'] == 'file' and member(package, '', entry['storage']['path'], files) == actual,
                'Gallery link does not map to this exact original case file')
        sealed = files[actual.relative_to(package).as_posix()]
        require((sealed['bytes'], sealed['sha256']) == (entry['bytes'], entry['sha256']), 'Original mapped bytes differ')
        return entry
    expected_models = actual_model_table(contract, kind)
    evidence_path = member(package, kind, row['case_evidence'], files)
    evidence = strict_json(evidence_path); case_input = evidence['case_input']
    require(case_input['case_id'] == row['case_id'] and case_input['model_sha256'] == expected_models
            and case_input['plan_sha256'] == contract['kinds'][kind]['native_plan_identity']
            and case_input['image_id'] == contract['image_id'], 'Original case identity/model/plan/image differs')
    launch = case_input['launch']; require(launch.count('--output') == 1, 'Unique original case output flag required')
    container_directory = Path(launch[launch.index('--output')+1])
    require('..' not in container_directory.parts and container_directory.is_relative_to('/outputs/reference629'),
            'Canonical actual native case directory required')
    original_directory = Path(contract['base'])/'runs'/kind/'outputs/reference629'/container_directory.relative_to('/outputs/reference629')
    linked(evidence_path, original_directory/'case-evidence.json')
    result_path = member(package, kind, row['result_json'], files)
    result_entry = linked(result_path, original_directory/'result.json'); result = strict_json(result_path)
    require(evidence['result_sha256'] == result_entry['sha256'] and result['status'] == row['status'] == 'completed'
            and result['inference']['ticks'] == row['policy_ticks'] and len(result['video_checks']) == 1,
            'Original result/source fingerprint or case/video count differs')
    check = result['video_checks'][0]; video_entry = linked(record['video'], original_directory/check['video'])
    linked(record['images'][1], original_directory/check['thumbnail'])
    probe = check['probe']; video = record['expected']
    require(video['width'] == probe['streams'][0]['width'] and video['height'] == probe['streams'][0]['height']
            and video['duration_seconds'] == float(probe['format']['duration']), 'Gallery metadata differs from original native result')
    raw_files = {x['path']: x for x in evidence['files']}
    for name, actual in ((check['video'], video_entry), ('result.json', result_entry)):
        original = str(container_directory/name); require(original in raw_files, 'Original case evidence omits linked media/result')
        require((raw_files[original]['bytes'], raw_files[original]['sha256']) == (actual['bytes'], actual['sha256']),
                'Original case evidence media/result fingerprint differs')
    return {'case_evidence': str(evidence_path), 'original_case_directory': str(original_directory),
            'video_original': video_entry['original_path'], 'video_storage_sha256': video_entry['sha256'],
            'model_sha256': expected_models}


def preflight(args):
    require(re.fullmatch('[0-9a-f]{64}', args.preparation_sha256)
            and re.fullmatch('[0-9a-f]{64}', args.manifest_sha256), 'Explicit reviewed SHA256 required')
    require(file_fp(PREPARATION)['sha256'] == args.preparation_sha256, 'Browser preparation differs')
    preparation = strict_json(PREPARATION)
    bindings = preparation['dependencies']; require(len({x['path'] for x in bindings}) == len(bindings), 'Duplicate browser source')
    for row in bindings:
        require(file_fp(row['path']) == row, 'Browser dependency differs')
    self_row = next(x for x in bindings if x['path'] == str(Path(__file__).absolute()))
    require(file_fp(__file__) == self_row, 'Actual browser entrypoint differs')
    require(file_fp(PUBLICATION/'preparation-manifest.json')['sha256'] == PUBLICATION_SHA, 'Original reviewed206 source seal differs')
    core_path = HERE/'evidence_http_browser.py'; core_row = next(x for x in bindings if x['path'] == str(core_path))
    core = checked_module(core_path, core_row, '_formal629_browser_core'); core.preflight_sources()
    restore = core.load(PUBLICATION/'restore.py', RESTORE_SHA, '_formal629_readonly_restore')
    package, output = restore.safe(args.package), restore.safe(args.output)
    require(package.is_relative_to(ROOT/'usage_assets/reports') and output.is_relative_to(ROOT/'outputs/research')
            and not output.exists() and output.parent.is_dir()
            and not output.is_relative_to(package) and not package.is_relative_to(output)
            and not output.is_relative_to(PREPARATION.parent) and not PREPARATION.parent.is_relative_to(output)
            and not output.is_relative_to(PUBLICATION) and not PUBLICATION.is_relative_to(output),
            'Actual package and fresh separate browser output required')
    context = restore.preflight(package, args.manifest_sha256, output)
    bindings = strict_json(package/'bindings.json')
    contract_path = member(package, '', bindings['contract'], context['files'])
    contract = strict_json(contract_path)
    for scientific_base in (Path(contract['base']), Path(contract['admission']['native58_base'])):
        require(not output.is_relative_to(scientific_base) and not scientific_base.is_relative_to(output),
                'Browser output cannot overlap scientific original directories')
    summary = strict_json(package/'summary.json'); rows = {kind: strict_json(package/kind/'cases.json') for kind in KINDS}
    records = validate_rows(package, summary, rows, context['files'])
    mappings = {x['original_path']: x for x in context['rows']}
    require(summary['contract_sha256'] == core.fp(contract_path)['sha256']
            and summary['contract_identity'] == contract['contract_identity']
            and [x['kind'] for x in bindings['kinds']] == list(KINDS), 'Actual contract/ordered model bindings differ')
    for kind in KINDS:
        model_table = actual_model_table(contract, kind)
        require(next(x for x in summary['kinds'] if x['model_kind'] == kind)['model_sha256']
                == strict_json(package/kind/'summary.json')['model_sha256']
                == next(x for x in bindings['kinds'] if x['kind'] == kind)['models'] == model_table,
                'Gallery models differ from the actual complete contract ONNX pair')
        for name, sha in model_table.items():
            original = str(Path(contract['base'])/'inputs'/kind/'assets/student'/name)
            require(original in mappings and mappings[original]['sha256'] == sha and mappings[original]['bytes'] > 0,
                    'Frozen actual model bytes missing from complete sealed restore-map')
        for row in rows[kind]:
            records[(kind, row['case_id'])]['original_binding'] = validate_case_binding(
                package, kind, row, records[(kind, row['case_id'])], contract, mappings, context['files'])
    return core, restore, context, preparation, summary, rows, records


def filter_check(session, element, value, event, expected):
    expression = "(()=>{const e=document.getElementById("+json.dumps(element)+");e.value="+json.dumps(value)+";e.dispatchEvent(new Event("+json.dumps(event)+"));return Number(document.getElementById('visible').textContent.split(' / ')[0]);})()"
    actual = session.evaluate(expression); require(actual == expected, 'Actual gallery filter differs: '+element+'/'+value)
    return {'element': element, 'value': value, 'matched': actual}


def verify(args):
    core, restore, context, preparation, summary, rows, records = preflight(args)
    package, output = context['package'], context['output']; before = core.fp(package/'evidence-manifest.json')
    sources_before = [file_fp(PREPARATION), *preparation['dependencies']]
    output.mkdir(); session = core.Session(output, ROOT)
    report = {'status': 'failed', 'scope': 'Actual complete formal two-policy1258 HTTP/CPU browser only. No new science/restore/decode, threshold or skill-success conclusion.',
              'publication_manifest': before, 'source_before': sources_before, 'videos': [], 'images': [], 'explicit_range_probes': [],
              'filters': [], 'pagination': [], 'policy_pages': [], 'quality_verified': False}
    try:
        base = session.start()
        for kind in KINDS:
            page_url = base+'/'+(package/kind/'playback.html').relative_to(ROOT).as_posix()
            ready = "document.readyState==='complete' && location.href==="+json.dumps(page_url)+" && !!document.getElementById('case-data') && JSON.parse(document.getElementById('case-data').textContent)[0]?.model_kind==="+json.dumps(kind)
            session.navigate(page_url, ready)
            require(session.evaluate("JSON.parse(document.getElementById('case-data').textContent)") == rows[kind], 'Actual DOM differs from sealed per-policy cases')
            title = session.evaluate('document.title'); text = session.evaluate('document.querySelector("header").textContent')
            require(kind in title and kind in text and all(sha in text for sha in next(s for s in summary['kinds'] if s['model_kind'] == kind)['model_sha256'].values()), 'Policy/model SHA identification missing from actual DOM')
            report['policy_pages'].append({'kind': kind, 'url': page_url, 'title': title, 'model_sha_identified': True})
            for value in ('threshold', 'unflagged', 'all'):
                expected = sum(x['threshold_event'] if value == 'threshold' else not x['threshold_event'] if value == 'unflagged' else True for x in rows[kind])
                report['filters'].append(dict(filter_check(session, 'state', value, 'change', expected), kind=kind))
            for scene in sorted({x['scenario'] for x in rows[kind]}):
                report['filters'].append(dict(filter_check(session, 'scene', scene, 'change', sum(x['scenario'] == scene for x in rows[kind])), kind=kind))
            filter_check(session, 'scene', 'all', 'change', 629)
            first = rows[kind][0]['case_id']; filter_check(session, 'search', first, 'input', 1)
            require(session.evaluate("[...document.querySelectorAll('article')].map(a=>a.dataset.case)") == [first], 'Exact case search mismatch')
            filter_check(session, 'search', '', 'input', 629)
            for page in range(math.ceil(629/24)):
                subset = rows[kind][page*24:(page+1)*24]
                require(session.evaluate("[...document.querySelectorAll('article')].map(a=>a.dataset.case)") == [x['case_id'] for x in subset], 'Exact pagination case order differs')
                require(session.evaluate("document.querySelectorAll('video').length") == len(subset), 'One actual DOM video per case required')
                report['pagination'].append({'kind': kind, 'page': page+1, 'case_ids': [x['case_id'] for x in subset]})
                for index, row in enumerate(subset):
                    record = records[(kind, row['case_id'])]; path = record['video']; relative = path.relative_to(package).as_posix()
                    report['explicit_range_probes'].append(session.range_probe(path, context['files'][relative], {'kind': kind, 'case_id': row['case_id']}))
                    url = base+'/'+path.relative_to(ROOT).as_posix()
                    observed = session.check_video(url, record['expected'], "document.querySelectorAll('video')["+str(index)+"]")
                    report['videos'].append(dict(observed, kind=kind, case_id=row['case_id']))
                expected_images = [base+'/'+p.relative_to(ROOT).as_posix() for row in subset for p in records[(kind, row['case_id'])]['images']]
                require(session.evaluate("[...document.querySelectorAll('article img')].map(i=>i.src)") == expected_images, 'Actual DOM trajectory/poster image set differs')
                report['images'].extend(session.check_images(expected_images))
                if page == 0:
                    session.evaluate("document.querySelector('details.trajectory').open=true")
                    shot = session.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
                    (output/(kind+'-page1.png')).write_bytes(base64.b64decode(shot['data']))
                if page+1 < math.ceil(629/24):
                    session.evaluate("document.getElementById('next').click()")
            require(session.evaluate("document.getElementById('next').disabled") is True, 'Final pagination next must be disabled')
        require(len(report['videos']) == 1258 and len(report['images']) == 2516
                and len(report['pagination']) == 54 and len(report['explicit_range_probes']) == 1258, 'Full actual browser coverage missing')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        report['browser_lifecycle'] = session.close()
        try:
            # Original readonly preflight requires a fresh *absent* output, so use
            # an explicitly unused sibling merely as its destination argument.
            check_output = output.with_name(output.name+'.readonly-final-no-write')
            restore.preflight(package, args.manifest_sha256, check_output)
            report['seal_after'] = core.fp(package/'evidence-manifest.json')
            report['source_after'] = [file_fp(x['path']) for x in sources_before]
            require(report['seal_after'] == before and report['source_after'] == sources_before, 'Package/browser source changed')
            report['inputs_unchanged'] = True
        except BaseException as error:
            report['inputs_unchanged'] = False; report['recheck_error'] = {'type': type(error).__name__, 'message': str(error)}
        report['requests'] = session.requests
        browser_requests = session.requests[session.browser_request_start:]
        expected_paths = {urlsplit(x['url']).path for x in report['videos']}
        range_paths = {x['path'].split('?', 1)[0] for x in browser_requests if x['method'] == 'GET' and x['range']
                       and x['status'] == 206 and x['user_agent'] == session.browser_user_agent}
        report['unique_browser_range_video_paths'] = len(expected_paths & range_paths)
        report['expected_unique_video_storage_paths'] = len(expected_paths)
        report['case_video_visits'] = len(report['videos'])
        report['content_http_errors'] = [x for x in session.requests if x['status'] >= 400 and not x['path'].startswith('/favicon.ico')]
        if not (report['browser_lifecycle']['lifecycle_passed'] and report['inputs_unchanged']
                and not report['content_http_errors'] and expected_paths and expected_paths <= range_paths):
            report['status'] = 'failed'
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': report['status'], 'report': core.fp(output/'report.json')}))
    return int(report['status'] != 'passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('manifest-sha256', 'preparation-sha256'):
        parser.add_argument('--'+name, required=True)
    return verify(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
