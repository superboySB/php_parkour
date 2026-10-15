#!/usr/bin/env python3
"""Verify all58 actual published videos through Range HTTP and CPU Chrome.

Requires an already sealed real publication. Writes browser/request/wait
receipts only to a fresh separate workspace directory; no scientific process.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
SOURCES = {
    ROOT / 'scripts/research/serve_evidence.py': 'abd436f0e1b322e2b53191fb98d8dac677ef1aa31f31db5e31c5ae1fb3088024',
    ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce/verify_gallery.py': '7cf157ead34e5a05fa7a65036659bc0f20cff5a41779c165f7a6e65d58123b8f',
    ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py': '8a9edb9a34db22d8f29dc180088abfb94849c6c290a4e6b0336fdbf8b23efb06',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def load(path, name, expected=None):
    raw = path.read_bytes()
    require(expected is None or hashlib.sha256(raw).hexdigest() == expected, 'Reviewed helper source differs')
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ''
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def cleanup_profile(profile, browser, report):
    require(browser is None or browser.poll() is not None,
            'Live owned browser profile must be retained until actual process wait')
    shutil.rmtree(profile)
    report['browser_profile_removed_after_actual_wait'] = True


def verify(args):
    raw_preparation = (HERE / 'preparation-manifest.json').read_bytes()
    require(hashlib.sha256(raw_preparation).hexdigest() == args.preparation_sha256,
            'Explicit reviewed preparation SHA differs')
    preparation = json.loads(raw_preparation)
    for row in preparation['dependencies']:
        raw = Path(row['path']).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Frozen dependency changed before browser review')
    self_binding = next(r for r in preparation['dependencies'] if Path(r['path']).name == 'verify_http.py')
    raw_self = Path(__file__).read_bytes()
    require(len(raw_self) == self_binding['bytes'] and hashlib.sha256(raw_self).hexdigest() == self_binding['sha256'],
            'Browser entrypoint differs from reviewed preparation')
    pinned_restore = next(r for r in preparation['dependencies'] if Path(r['path']).name == 'restore.py')
    restore = load(HERE / 'restore.py', '_native58_browser_restore', pinned_restore['sha256'])
    package, output = restore.safe(args.package), restore.safe(args.output)
    require(package.is_relative_to(ROOT / 'usage_assets') and output.is_relative_to(ROOT)
            and not output.exists() and not output.is_relative_to(package) and not package.is_relative_to(output),
            'Actual package and fresh separate workspace output required')
    require(restore.fingerprint(HERE / 'restore.py') == {k: pinned_restore[k] for k in ('bytes', 'sha256')}, 'Restore checker changed')
    restore.verify(package, args.manifest_sha256)
    summary, rows = restore.read(package / 'summary.json'), restore.read(package / 'cases.json')
    require(summary['status'] == 'completed_review_bound_native58_document_publication'
            and summary['cases'] == len(rows) == 58 and summary['quality_verified'] is False
            and summary['obstacle_course_completion_verified'] is False
            and summary['independent_review'] == restore.read(package / 'evidence-manifest.json')['independent_review'],
            'Actual review-bound58 document publication required')
    before = restore.fingerprint(package / 'evidence-manifest.json')
    helpers = {p.name: load(p, '_native58_http_' + p.stem, digest) for p, digest in SOURCES.items()}
    server_module, cdp_module, gallery_module = [helpers[n] for n in ('serve_evidence.py', 'viser_browser.py', 'verify_gallery.py')]
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    require(chrome, 'Existing Chrome required')
    output.mkdir(parents=True)
    requests, thread, server, browser, cdp, profile = [], None, None, None, None, None
    report = {'status': 'failed', 'scope': 'Actual HTTP Range metadata, midpoint seek, positive playback and poster/trajectory image decode for all58 already reviewed videos; no new physics/quality conclusion.',
              'package': str(package), 'seal_before': before, 'requests': requests, 'quality_verified': False,
              'source_before': [{'path': str(p), **restore.fingerprint(p)} for p in (Path(__file__).absolute(), HERE / 'restore.py', HERE / 'preparation-manifest.json', *SOURCES)]}
    class Handler(server_module.EvidenceHandler):
        def log_message(self, *args):
            pass
        def log_request(self, code='-', size='-'):
            requests.append({'method': self.command, 'path': self.path, 'status': int(code),
                             'range': self.headers.get('Range'), 'size': size, 'observed_unix': time.time()})
    try:
        server = server_module.make_server(ROOT, port=0, handler=Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_address[1])
        url = base + '/' + package.relative_to(ROOT).as_posix() + '/playback.html'
        report['page_url'] = url
        report['explicit_range_probes'] = []
        for row in rows:
            video = row['videos'][0]
            path = package / restore.relative(video['path'])
            size = path.stat().st_size
            require(size > 1, 'Positive nonzero-offset media range required')
            start, end = min(97, size - 1), min(size - 1, min(97, size - 1) + 4095)
            media_url = base + '/' + path.relative_to(ROOT).as_posix()
            with path.open('rb') as stream:
                stream.seek(start)
                expected_bytes = stream.read(end - start + 1)
            with urlopen(Request(media_url, headers={'Range': f'bytes={start}-{end}'}), timeout=15) as response:
                data = response.read()
                observed = {'phase': row['phase'], 'case_id': row['case_id'], 'url': media_url,
                    'requested_range': f'bytes={start}-{end}', 'status': response.status,
                    'content_range': response.headers.get('Content-Range'), 'accept_ranges': response.headers.get('Accept-Ranges'),
                    'content_length': response.headers.get('Content-Length'), 'bytes': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(), 'source_segment_sha256': hashlib.sha256(expected_bytes).hexdigest()}
                require(response.status == 206 and observed['content_range'] == f'bytes {start}-{end}/{size}'
                        and observed['accept_ranges'] == 'bytes' and observed['content_length'] == str(end - start + 1)
                        and data == expected_bytes, 'Explicit media Range response differs')
                report['explicit_range_probes'].append(observed)
        require(len(report['explicit_range_probes']) == 58, 'All58 explicit Range probes required')
        browser_request_start = len(requests)
        # No automatic finalizer can delete a still-running Chrome profile.
        profile = tempfile.mkdtemp(prefix='native58-http-')
        with (output / 'chrome.stdout.log').open('xb') as stdout, (output / 'chrome.stderr.log').open('xb') as stderr:
            port = cdp_module.free_port()
            argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run',
                    '--no-default-browser-check', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required',
                    '--window-size=1440,1200', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port),
                    '--user-data-dir=' + profile, 'about:blank']
            if os.geteuid() == 0:
                argv.insert(1, '--no-sandbox')
            report['browser_argv'] = argv
            browser = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                require(browser.poll() is None, 'Chrome exited before CDP')
                try:
                    with urlopen('http://127.0.0.1:' + str(port) + '/json/list', timeout=2) as response:
                        target = next(t for t in json.load(response) if t.get('type') == 'page')
                    cdp = gallery_module.connect_cdp(cdp_module.CDP, target['webSocketDebuggerUrl'])
                    cdp.socket.settimeout(60)
                    break
                except (OSError, StopIteration):
                    time.sleep(.1)
            require(cdp is not None, 'CDP connection timeout')
            cdp.call('Page.enable')
            cdp.call('Network.enable')
            cdp.call('Network.setCacheDisabled', {'cacheDisabled': True})
            cdp.call('Page.navigate', {'url': url})
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and cdp.evaluate("document.querySelectorAll('video').length") != 58:
                time.sleep(.1)
            require(cdp.evaluate("document.querySelectorAll('video').length") == 58, 'All58 video cards required')
            report['videos'] = []
            for index, row in enumerate(rows):
                observed = cdp.evaluate('''(async()=>{const v=document.querySelectorAll('video')[''' + str(index) + '''];v.preload='auto';await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('metadata timeout')),15000);v.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve();},{once:true});v.addEventListener('error',()=>reject(Error(v.error.message)),{once:true});v.load();});const target=v.duration/2;await new Promise((resolve,reject)=>{const deadline=performance.now()+15000;const check=()=>{if([...Array(v.seekable.length)].some((_,i)=>v.seekable.start(i)<=target&&v.seekable.end(i)>=target))resolve();else if(performance.now()>deadline)reject(Error('seekable timeout'));else setTimeout(check,20);};check();});await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('seek timeout')),15000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve();},{once:true});v.currentTime=target;});await new Promise((resolve,reject)=>{const deadline=performance.now()+15000;const check=()=>{if(!v.seeking&&v.readyState>=2)resolve();else if(performance.now()>deadline)reject(Error('frame timeout'));else setTimeout(check,20);};check();});const seek=v.currentTime;v.muted=true;await v.play();const before=v.currentTime;await new Promise(r=>setTimeout(r,350));const after=v.currentTime;v.pause();return {url:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration:v.duration,seek_target:target,seek_actual:seek,play_before:before,play_after:after,error:v.error?.message};})()''')
                expected = row['videos'][0]
                require(observed['url'] == base + '/' + (package / expected['path']).relative_to(ROOT).as_posix()
                        and observed['width'] == expected['width'] and observed['height'] == expected['height']
                        and abs(observed['duration'] - expected['duration_seconds']) < .05
                        and abs(observed['seek_actual'] - observed['seek_target']) < .05
                        and observed['play_after'] - observed['play_before'] > .1 and not observed.get('error'),
                        'Actual HTTP metadata/seek/play differs: ' + str(index))
                report['videos'].append(dict(observed, phase=row['phase'], case_id=row['case_id']))
            report['images'] = cdp.evaluate('''(async()=>{const srcs=[...document.querySelectorAll('video')].map(v=>v.poster).concat([...document.querySelectorAll('article img')].map(i=>i.src));return await Promise.all(srcs.map(src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve({url:src,width:i.naturalWidth,height:i.naturalHeight});i.onerror=()=>reject(Error(src));i.src=src;})));})()''')
            require(len(report['images']) == 116 and all(min(i['width'], i['height']) > 0 for i in report['images']), 'Poster/trajectory decode differs')
            shot = cdp.call('Page.captureScreenshot', {'format': 'png'})
            (output / 'playback.png').write_bytes(base64.b64decode(shot['data']))
            report['status'] = 'passed'
    except BaseException as error:
        report['status'], report['error'] = 'failed', type(error).__name__ + ': ' + str(error)
    finally:
        if cdp:
            try:
                cdp.call('Browser.close')
            except Exception as error:
                report['browser_close_response'] = str(error)
            cdp.socket.close()
        if browser:
            try:
                report['browser_actual_wait'] = browser.wait(timeout=15)
                report['browser_cleanup'] = 'natural_wait'
            except subprocess.TimeoutExpired:
                browser.terminate()
                report['browser_actual_wait'] = browser.wait(timeout=5)
                report['browser_cleanup'] = 'owned_browser_terminate'
        if profile is not None:
            try:
                cleanup_profile(profile, browser, report)
            except Exception as error:
                report['status'], report['profile_cleanup_error'] = 'failed', str(error)
                report['preserved_browser_profile'] = profile
        if server:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            report['http_server_stopped'] = not thread.is_alive()
        try:
            restore.verify(package, args.manifest_sha256)
            for row in preparation['dependencies']:
                require(restore.fingerprint(row['path']) == {k: row[k] for k in ('bytes', 'sha256')},
                        'Frozen preparation dependency changed during browser review')
            report['seal_after'] = restore.fingerprint(package / 'evidence-manifest.json')
            report['source_after'] = [{'path': r['path'], **restore.fingerprint(r['path'])} for r in report['source_before']]
            report['inputs_unchanged'] = report['seal_after'] == before and report['source_before'] == report['source_after']
        except Exception as error:
            report['inputs_unchanged'], report['source_recheck_error'] = False, str(error)
        report['content_http_errors'] = [r for r in requests if r['status'] >= 400 and not r['path'].startswith('/favicon.ico')]
        report['http_206_responses'] = sum(r['status'] == 206 for r in requests)
        report['browser_media_range_requests'] = [r for r in requests[locals().get('browser_request_start', len(requests)):]
            if r['method'] == 'GET' and r['range'] and r['path'].split('?', 1)[0].endswith('.mp4')]
        expected_paths = {'/' + (package / v['path']).relative_to(ROOT).as_posix() for r in rows for v in r['videos']}
        range_paths = {r['path'].split('?', 1)[0] for r in report['browser_media_range_requests'] if r['status'] == 206}
        report['browser_range_expected_unique_video_paths'] = len(expected_paths)
        report['browser_range_verified_unique_video_paths'] = len(expected_paths & range_paths)
        if not (report.get('browser_actual_wait') == 0 and report.get('browser_cleanup') == 'natural_wait'
                and report.get('browser_profile_removed_after_actual_wait')
                and report.get('http_server_stopped') and report['inputs_unchanged'] and not report['content_http_errors']
                and len(report.get('explicit_range_probes', [])) == 58 and report['http_206_responses'] >= 58
                and expected_paths <= range_paths):
            report['status'] = 'failed'
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'video_count': len(report.get('videos', [])), 'receipt': str(output / 'report.json')}))
    return int(report['status'] != 'passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--preparation-sha256', required=True)
    return verify(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
