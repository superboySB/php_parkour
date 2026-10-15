#!/usr/bin/env python3
"""Inspect six preserved videos in existing CPU Chrome; stdlib only."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

LABELS = ['eval-teacher-' + s for s in ('locomotion', 'low-step', 'high-step', 'low-climb-76', 'high-climb-76')] + ['eval-student-pure']
CDP_SHA = '8a9edb9a34db22d8f29dc180088abfb94849c6c290a4e6b0336fdbf8b23efb06'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fp(p):
    data = p.read_bytes()
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def png_size(p):
    data = p.read_bytes()[:24]
    require(data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR', 'Invalid PNG')
    return list(struct.unpack('!II', data[16:24]))


def connect_cdp(CDP, url):
    # The exact borrowed handshake lacks an EOF check; bound construction here.
    def expired(*_):
        raise TimeoutError('CDP handshake deadline exceeded')
    old_handler = signal.signal(signal.SIGALRM, expired)
    old_timer = signal.setitimer(signal.ITIMER_REAL, 15)
    client = CDP.__new__(CDP)
    try:
        CDP.__init__(client, url)
        return client
    except BaseException:
        if getattr(client, 'socket', None):
            client.socket.close()
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        signal.setitimer(signal.ITIMER_REAL, *old_timer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.absolute(), args.output.absolute()
    require(not output.exists(), 'Fresh output required')
    require(not output.is_relative_to(package) and not package.is_relative_to(output), 'Separate package/output required')
    require(package.resolve() == package and output.parent.resolve() == output.parent, 'Normalized paths without symlinks required')
    output.mkdir(parents=True)
    report = {'status': 'failed', 'scope': 'Six representative browser metadata, midpoint seeks, PNGs and actual playback; CPU separately decoded all160 originals.', 'quality_verified': False, 'full': False}
    browser = cdp = None
    checks = False
    paths = []
    sources = [Path(__file__).absolute(), Path(__file__).absolute().with_name('viser_browser.py')]
    report['source_before'] = [fp(p) for p in sources]
    try:
        require(fp(sources[1])['sha256'] == CDP_SHA, 'Borrowed CDP source differs')
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(sources[1].parent))
        from viser_browser import CDP, free_port

        def member(name):
            rel = Path(name)
            require(not rel.is_absolute() and '..' not in rel.parts, 'Relative package member required')
            p = package / rel
            require(p.is_file() and p.resolve() == p, 'Regular package member without symlinks required')
            paths.append(p)
            return p

        summary_path, page = member('summary.json'), member('playback.html')
        stages = json.loads(summary_path.read_bytes())['stages']
        require([s['label'] for s in stages] == LABELS, 'Six ordered stages required')
        expected = []
        for stage in stages:
            r, label = stage['representative'], stage['label']
            video = member(r['path'])
            require(fp(video)['sha256'] == r['sha256'] and video.stat().st_size == r['bytes'], 'Representative bytes differ')
            require(r['duration_seconds'] > 0 and r['probed_frames'] == r['decoded_frames'] > 0, 'Positive CPU frame agreement required')
            poster = 'cpu-02/results/' + label + '/representative.png'
            size = png_size(member(poster))
            require(size == [r['width'], r['height']] and min(size) > 0, 'Poster dimensions differ')
            expected.append({'label': label, 'src': r['path'], 'poster': poster, 'duration': r['duration_seconds'], 'width': r['width'], 'height': r['height']})
        report['input_before'] = [fp(p) for p in paths]
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        require(chrome, 'Existing Chrome required; installs nothing')
        with tempfile.TemporaryDirectory(prefix='php-six-gallery-') as profile, (output / 'chrome.stdout.raw').open('wb') as stdout, (output / 'chrome.stderr.raw').open('wb') as stderr:
            port = free_port()
            argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--disable-dev-shm-usage', '--allow-file-access-from-files', '--autoplay-policy=no-user-gesture-required', '--window-size=1440,1200', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port), '--user-data-dir=' + profile, 'about:blank']
            if os.geteuid() == 0:
                argv.insert(1, '--no-sandbox')
            report['browser_command'] = argv
            browser = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
            report['browser_pid'] = browser.pid
            try:
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    require(browser.poll() is None, 'Browser exited during startup')
                    try:
                        with urlopen('http://127.0.0.1:' + str(port) + '/json/list', timeout=2) as response:
                            target = next(t for t in json.load(response) if t.get('type') == 'page')
                        cdp = connect_cdp(CDP, target['webSocketDebuggerUrl'])
                        cdp.socket.settimeout(20)
                        break
                    except (OSError, StopIteration):
                        time.sleep(.1)
                require(cdp is not None, 'Browser CDP startup timeout')
                cdp.call('Page.enable')
                cdp.call('Page.navigate', {'url': page.as_uri()})
                snapshot = "Array.from(document.querySelectorAll('article[data-label]')).map(a=>{const v=a.querySelector('video');return {label:a.dataset.label,src:v?.getAttribute('src'),poster:v?.getAttribute('poster'),duration:v?.duration,width:v?.videoWidth,height:v?.videoHeight,ready:v?.readyState,error:v?.error?.message};})"
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    dom = cdp.evaluate(snapshot)
                    if dom and len(dom) == 6 and all(v.get('ready', 0) >= 1 for v in dom):
                        break
                    time.sleep(.1)
                require(len(dom or []) == 6, 'Six video articles required')
                report['metadata'] = dom
                for actual, wanted in zip(dom, expected):
                    require(all(actual[k] == wanted[k] for k in ('label', 'src', 'poster', 'width', 'height')) and actual['ready'] >= 1 and not actual.get('error') and abs(actual['duration'] - wanted['duration']) < .05, 'Browser metadata/source differs')
                cdp.evaluate("window.__auditImages=Array.from(document.querySelectorAll('article[data-label] video')).map(v=>{const i=new Image();i.src=v.poster;return i;});true")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    images = cdp.evaluate('window.__auditImages.map(i=>({complete:i.complete,width:i.naturalWidth,height:i.naturalHeight}))')
                    if all(i['complete'] and i['width'] > 0 for i in images):
                        break
                    time.sleep(.1)
                report['images'] = images
                require(len(images) == 6 and all(i['complete'] and [i['width'], i['height']] == [e['width'], e['height']] for i, e in zip(images, expected)), 'Browser PNG decode/dimensions failed')
                seeks = cdp.evaluate("(async()=>{const rows=[];for(const v of document.querySelectorAll('article[data-label] video')){const target=v.duration/2;await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('seek timeout')),15000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve();},{once:true});v.currentTime=target;});rows.push({target,time:v.currentTime,ready:v.readyState,error:v.error?.message});}return rows;})()")
                report['midpoint_seeks'] = seeks
                require(len(seeks) == 6 and all(s['ready'] >= 2 and not s.get('error') and abs(s['time'] - s['target']) < .05 for s in seeks), 'Midpoint seek failed')
                playing = cdp.evaluate("(async()=>{const vs=Array.from(document.querySelectorAll('article[data-label] video'));const before=await Promise.all(vs.map(async v=>{v.muted=true;v.currentTime=0;await v.play();return v.currentTime;}));await new Promise(r=>setTimeout(r,800));const rows=vs.map((v,i)=>({before:before[i],after:v.currentTime,paused:v.paused,error:v.error?.message}));vs.forEach(v=>v.pause());return rows;})()")
                report['actual_playback'] = playing
                require(len(playing) == 6 and all(not p['paused'] and not p.get('error') and p['after'] - p['before'] > .2 for p in playing), 'Actual playback did not advance')
                size = cdp.call('Page.getLayoutMetrics')['cssContentSize']
                shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True, 'clip': {**size, 'scale': 1}})
                screenshot = output / 'playback.png'
                screenshot.write_bytes(base64.b64decode(shot['data']))
                report['screenshot'] = {**fp(screenshot), 'dimensions': png_size(screenshot)}
                checks = True
            finally:
                if cdp:
                    report['browser_close_requested'] = True
                    try:
                        cdp.call('Browser.close')
                    except Exception as error:
                        report['browser_close_response_error'] = str(error)
                    cdp.socket.close()
                for mode, sig, timeout in [('natural_wait', None, 15), ('owned_group_sigterm', signal.SIGTERM, 5), ('owned_group_sigkill', signal.SIGKILL, 5)]:
                    report['cleanup'] = mode
                    if sig and browser.poll() is None:
                        try:
                            require(os.getpgid(browser.pid) == browser.pid, 'Owned browser group identity differs')
                            os.killpg(browser.pid, sig)
                        except ProcessLookupError:
                            pass
                    try:
                        report['actual_browser_wait_returncode'] = browser.wait(timeout=timeout)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                else:
                    raise TimeoutError('Owned browser still not reaped after SIGKILL')
        require(checks and report['cleanup'] == 'natural_wait' and type(report.get('actual_browser_wait_returncode')) is int and report['actual_browser_wait_returncode'] == 0, 'Browser checks or natural exit failed')
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        def final_snapshot(selected):
            rows = []
            for p in selected:
                try:
                    rows.append(fp(p))
                except Exception as error:
                    rows.append({'path': str(p), 'error': type(error).__name__ + ': ' + str(error)})
            return rows
        report['source_after'] = final_snapshot(sources)
        report['input_after'] = final_snapshot(paths)
        report['sources_unchanged'] = report['source_before'] == report['source_after']
        report['inputs_unchanged'] = report.get('input_before') == report['input_after']
        if not report['sources_unchanged'] or not report['inputs_unchanged']:
            report['status'] = 'failed'
        report['artifacts'] = [fp(p) for p in sorted(output.iterdir()) if p.is_file()]
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(output), 'actual_browser_wait_returncode': report.get('actual_browser_wait_returncode')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
