#!/usr/bin/env python3
"""Actual loopback Range/Chrome review for the single-source preview."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
sys.path.insert(0, str(ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce'))
from verify_gallery import connect_cdp
from viser_browser import CDP, free_port
sys.path.insert(0, str(ROOT))
from scripts.research import serve_evidence


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    package = args.package.absolute()
    require(sha(package / 'evidence-manifest.json') == args.manifest_sha256, 'External candidate seal mismatch')
    helper = package / 'cloud888_report.py'
    require(sha(helper) == '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55', 'Original byte-archive helper changed')
    spec = importlib.util.spec_from_file_location('boundary_archive', helper)
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    archive.verify_package(package)
    require(not args.output.exists(), 'Fresh review output required')
    args.output.mkdir()
    manifest = json.loads((package / 'evidence-manifest.json').read_bytes())
    before = {r['path']: {'bytes': (package / r['path']).stat().st_size,
                          'sha256': sha(package / r['path'])} for r in manifest['files']}
    requests = []

    class Handler(serve_evidence.EvidenceHandler):
        def log_message(self, *a):
            pass

        def copyfile(self, source, outputfile):
            try:
                super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_request(self, code='-', size='-'):
            requests.append({'method': self.command, 'path': self.path, 'status': int(code),
                             'range': self.headers.get('Range'), 'observed_unix': time.time()})

    server = serve_evidence.make_server(ROOT, port=0, handler=Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_address[1])
    report = {'status': 'failed', 'candidate_manifest_sha256': args.manifest_sha256,
              'requests': requests, 'source': {'path': str(Path(__file__)), 'sha256': sha(Path(__file__))},
              'range_checks': [], 'scope': 'Single-source original bytes and actual browser playback only; not888 terminal or obstacle-course success.'}
    browser = cdp = None
    try:
        for path in sorted((package / 'media').glob('*.mp4')):
            data = path.read_bytes()
            offset = max(1, len(data) // 2)
            end = min(len(data) - 1, offset + 127)
            url = base + '/' + path.relative_to(ROOT).as_posix()
            with urlopen(Request(url, headers={'Range': f'bytes={offset}-{end}'}), timeout=10) as response:
                body = response.read()
                row = {'path': path.relative_to(package).as_posix(), 'offset': offset, 'end': end,
                       'status': response.status, 'headers': dict(response.headers),
                       'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
            require(row['status'] == 206 and row['headers']['Content-Range'] == f'bytes {offset}-{end}/{len(data)}'
                    and int(row['headers']['Content-Length']) == end - offset + 1
                    and row['headers']['Accept-Ranges'] == 'bytes' and body == data[offset:end + 1], 'Exact nonzero Range failed')
            report['range_checks'].append(row)
        require(len(report['range_checks']) == 3, 'Expected exactly three original MP4s')
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        require(chrome, 'Existing Chrome required')
        with tempfile.TemporaryDirectory(prefix='php-boundary-http-') as profile, (args.output / 'chrome.stdout.raw').open('wb') as stdout, (args.output / 'chrome.stderr.raw').open('wb') as stderr:
            port = free_port()
            argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking',
                    '--no-first-run', '--no-default-browser-check', '--disable-dev-shm-usage',
                    '--autoplay-policy=no-user-gesture-required', '--window-size=1280,1200',
                    '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port),
                    '--user-data-dir=' + profile, 'about:blank']
            if os.geteuid() == 0:
                argv.insert(1, '--no-sandbox')
            report['browser_argv'] = argv
            browser = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
            report['browser_pid'] = browser.pid
            report['browser_birth_stat'] = Path(f'/proc/{browser.pid}/stat').read_text()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                require(browser.poll() is None, 'Chrome exited before connection')
                try:
                    with urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2) as response:
                        target = next(t for t in json.load(response) if t.get('type') == 'page')
                    cdp = connect_cdp(CDP, target['webSocketDebuggerUrl'])
                    cdp.socket.settimeout(40)
                    break
                except (OSError, StopIteration):
                    time.sleep(.1)
            require(cdp is not None, 'Chrome connection timeout')
            cdp.call('Page.enable')
            cdp.call('Network.enable')
            cdp.call('Network.setCacheDisabled', {'cacheDisabled': True})
            report['browser_request_start'] = len(requests)
            url = base + '/' + (package / 'playback.html').relative_to(ROOT).as_posix()
            report['page_url'] = url
            cdp.call('Page.navigate', {'url': url})
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if cdp.evaluate("document.querySelectorAll('video').length") == 3:
                    break
                time.sleep(.1)
            require(cdp.evaluate("document.querySelectorAll('video').length") == 3, 'Three original video entries required')
            report['metadata'] = cdp.evaluate("""(async()=>{const rows=[];for(const v of document.querySelectorAll('video')){v.preload='auto';await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('metadata timeout')),12000);v.onloadedmetadata=()=>{clearTimeout(t);resolve();};v.onerror=()=>reject(Error(v.error.message));v.load();});rows.push({url:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration:v.duration,error:v.error?.message});}return rows;})()""")
            require(all(min(v['width'], v['height'], v['duration']) > 0 and not v.get('error') for v in report['metadata']), 'Invalid MP4 metadata')
            report['seek'] = cdp.evaluate("""(async()=>{const v=document.querySelector('video[data-primary]');const target=v.duration/2;await new Promise((resolve,reject)=>{const d=performance.now()+15000;const check=()=>{if([...Array(v.seekable.length)].some((_,i)=>v.seekable.start(i)<=target&&v.seekable.end(i)>=target))resolve();else if(performance.now()>d)reject(Error('seekable timeout'));else setTimeout(check,20);};check();});await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('seek timeout')),12000);v.onseeked=()=>{clearTimeout(t);resolve();};v.currentTime=target;});await new Promise((resolve,reject)=>{const d=performance.now()+10000;const check=()=>{if(v.readyState>=2&&!v.seeking)resolve();else if(performance.now()>d)reject(Error('frame timeout'));else setTimeout(check,20);};check();});return {target,time:v.currentTime,ready:v.readyState,error:v.error?.message};})()""")
            require(report['seek']['ready'] >= 2 and abs(report['seek']['time'] - report['seek']['target']) < .05 and not report['seek'].get('error'), 'Actual midpoint seek failed')
            report['images'] = cdp.evaluate("""(async()=>await Promise.all([...document.querySelectorAll('img')].map(i=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve({url:image.src,width:image.naturalWidth,height:image.naturalHeight});image.onerror=()=>reject(Error(i.src));image.src=i.src;}))))()""")
            require(len(report['images']) == 3 and all(min(v['width'], v['height']) > 0 for v in report['images']), 'PNG/GIF browser decode failed')
            report['play'] = cdp.evaluate("""(async()=>{const v=document.querySelector('video[data-primary]');v.muted=true;v.currentTime=0;await v.play();const before=v.currentTime;await new Promise(r=>setTimeout(r,850));const result={before,after:v.currentTime,paused:v.paused,error:v.error?.message};v.pause();return result;})()""")
            require(not report['play']['paused'] and report['play']['after'] - report['play']['before'] > .2 and not report['play'].get('error'), 'Actual playback did not advance')
            screenshot = cdp.call('Page.captureScreenshot', {'format': 'png'})
            (args.output / 'playback.png').write_bytes(base64.b64decode(screenshot['data']))
            cdp.call('Browser.close')
            cdp.socket.close()
            cdp = None
            report['browser_actual_wait_returncode'] = browser.wait(timeout=15)
            report['cleanup'] = 'natural_wait'
            require(report['browser_actual_wait_returncode'] == 0, 'Chrome actual wait nonzero')
        browser_requests = requests[report['browser_request_start']:]
        required_paths = {'/' + (package / row['path']).relative_to(ROOT).as_posix() for row in report['range_checks']}
        actual_paths = {r['path'] for r in browser_requests if r['status'] == 206 and r['range']}
        report['browser_206_paths'] = sorted(actual_paths)
        require(required_paths <= actual_paths, 'Chrome itself did not issue Range for every original MP4')
        report['status'] = 'passed_actual_single_source_range_chrome_play_seek_images'
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if cdp:
            try:
                cdp.call('Browser.close')
            except Exception:
                pass
            cdp.socket.close()
        if browser and browser.poll() is None:
            try:
                report['browser_actual_wait_returncode'] = browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.terminate()
                report['browser_actual_wait_returncode'] = browser.wait(timeout=5)
            report['cleanup'] = 'owned_browser_cleanup_after_failure'
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        report['http_server_stopped'] = not thread.is_alive()
        after = {r['path']: {'bytes': (package / r['path']).stat().st_size,
                             'sha256': sha(package / r['path'])} for r in manifest['files']}
        report['inputs_unchanged'] = before == after
        report['http_content_errors'] = [r for r in requests if r['status'] >= 400 and not r['path'].startswith('/favicon.ico')]
        archive.verify_package(package)
        require(sha(package / 'evidence-manifest.json') == args.manifest_sha256, 'Candidate seal changed')
        if not report['inputs_unchanged'] or not report['http_server_stopped'] or report['http_content_errors']:
            report['status'] = 'failed'
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'range_checks': len(report['range_checks']),
                      'browser_wait': report.get('browser_actual_wait_returncode'), 'error': report.get('error')}))
    raise SystemExit(report['status'] == 'failed')


if __name__ == '__main__':
    main()
