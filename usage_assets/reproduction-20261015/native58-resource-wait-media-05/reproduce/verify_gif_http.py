#!/usr/bin/env python3
"""Actual local HTTP/image decode of the three authorized native58 movie GIFs."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote
from urllib.request import urlopen

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
MAIN = ROOT / 'usage_assets/reports/final-student-native58-resource-wait-04'
MAIN_SHA = '8d9d0b733c4450d01a83f2aa84cde1f41b1f76f0cf50319cf884956d0c38a668'
SOURCE_PINS = {
    'scripts/research/serve_evidence.py': 'abd436f0e1b322e2b53191fb98d8dac677ef1aa31f31db5e31c5ae1fb3088024',
    'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py': '8a9edb9a34db22d8f29dc180088abfb94849c6c290a4e6b0336fdbf8b23efb06',
    'usage_assets/reports/official-evaluations-six/browser-reproduce/verify_gallery.py': '7cf157ead34e5a05fa7a65036659bc0f20cff5a41779c165f7a6e65d58123b8f',
    'outputs/research/reproduction-20261015/native58-publication-resource-wait-preparation-05/restore.py': '57be6ed4f884d4d9fbcb747260c39f8343d80cf117a46514d32a39fefa6c2cab',
}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def fp(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def inventory(root):
    files = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'No symlink inputs')
        if path.is_file():
            row = fp(path); row['path'] = path.relative_to(root).as_posix(); files.append(row)
    return files


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.absolute(), args.output.absolute()
    require(package.resolve() == package and package.is_relative_to(ROOT), 'Normalized repository package required')
    require(not output.exists() and not output.is_relative_to(package), 'Separate fresh output required')
    require(fp(package / 'manifest.json')['sha256'] == args.manifest_sha256, 'External derived manifest SHA differs')
    sources = [Path(__file__).absolute()]
    for name, expected in SOURCE_PINS.items():
        path = ROOT / name; require(fp(path)['sha256'] == expected, 'Frozen dependency differs: ' + name); sources.append(path)
    restore = load('native58_main_restore_for_gif_http', sources[-1])
    restore.verify(MAIN, MAIN_SHA)
    input_before, source_before = inventory(package), [fp(p) for p in sources]
    manifest = json.loads((package / 'manifest.json').read_bytes())
    require([c['ordinal'] for c in manifest['cases']] == [1, 30, 57], 'Exactly three selected cases required')
    require(manifest['source_main_seal'] == fp(MAIN / 'evidence-manifest.json'), 'Source seal binding differs')
    cases = json.loads((MAIN / 'cases.json').read_bytes())
    require(fp(package / 'evidence/source-independent-review.json')['sha256'] == '1b8dc57dc111c00598c4ea4befa61a748eb564b000dc7ece9bed39467525da10', 'Actual independent review differs')
    require(fp(package / 'evidence/root-visual-review.json')['sha256'] == 'e97424b60ee01774fc499749cb798e31faf45d51619ed1de5a5ec8d9b5b38e87', 'Actual root visual review differs')
    gifs = []
    for row in manifest['cases']:
        require(row['source_case'] == cases[row['ordinal']], 'Sealed original case binding differs')
        require(fp(MAIN / row['source_case']['videos'][0]['path']) == row['source_video'], 'Original MP4 binding differs')
        path = package / row['gif_path']; require(fp(path) == row['gif'], 'Derived GIF bytes differ')
        require(row['full_decode']['actual_wait_returncode'] == 0 and row['gif_metadata']['streams'][0]['nb_read_frames'] == '64', 'Actual CPU64 decode required')
        gifs.append(path)
    pngs = sorted(package.rglob('*.png'))
    require(len(pngs) == 16, 'Six contacts/posters, detail contact and three GIF contacts required')
    expected = [{'url': '/' + quote(p.relative_to(ROOT).as_posix()), 'size': [480, 270], 'file': fp(p)} for p in gifs]
    expected += [{'url': '/' + quote(p.relative_to(ROOT).as_posix()), 'size': list(struct.unpack('>II', p.read_bytes()[16:24])), 'file': fp(p)} for p in pngs]
    server_module = load('native58_gif_actual_range_server', sources[1])
    browser_module = load('native58_gif_actual_cdp', sources[2])
    gallery_module = load('native58_gif_actual_handshake', sources[3])
    output.mkdir(parents=True)
    report = {'schema_version': 1, 'status': 'failed', 'source_before': source_before,
              'source_main_seal': fp(MAIN / 'evidence-manifest.json'), 'derived_manifest': fp(package / 'manifest.json'),
              'input_before': input_before, 'quality_verified': False, 'course_success_verified': False,
              'scope': 'Actual HTTP200 original-byte readback of3GIFs and Chrome image decode/dimensions for3GIFs+16PNGs. CPU independently fully decoded each64-frame GIF; browser observation does not assert exhaustive animation-frame playback or policy-clock alignment.'}
    requests = []
    class Handler(server_module.EvidenceHandler):
        def log_request(self, code='-', size='-'):
            requests.append({'method': self.command, 'path': self.path, 'status': int(code),
                             'range': self.headers.get('Range'), 'user_agent': self.headers.get('User-Agent')})
        def log_message(self, *_):
            pass
    server = server_module.make_server(ROOT, port=0, handler=Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base_url = 'http://127.0.0.1:' + str(server.server_address[1])
    page_url = base_url + '/' + package.relative_to(ROOT).as_posix() + '/playback.html'
    report.update({'base_url': base_url, 'page_url': page_url})
    browser = cdp = None
    profile = tempfile.mkdtemp(prefix='native58-gif-http-')
    checks = False
    stdout = (output / 'chrome.stdout.raw').open('wb')
    stderr = (output / 'chrome.stderr.raw').open('wb')
    cdp_log = (output / 'cdp.jsonl').open('w')
    try:
        readbacks = []
        for index, row in enumerate(expected[:3]):
            with urlopen(base_url + row['url'], timeout=20) as response:
                data = response.read(); status = response.status; headers = dict(response.headers)
            path = output / ('gif-http-body-' + str(index + 1) + '.raw'); path.write_bytes(data)
            require(status == 200 and fp(path)['sha256'] == row['file']['sha256'] and len(data) == row['file']['bytes'], 'HTTP GIF body differs')
            require(int(headers['Content-Length']) == len(data) and headers['Content-Type'].startswith('image/gif'), 'HTTP GIF headers differ')
            readbacks.append({'url': base_url + row['url'], 'status': status, 'headers': headers, 'body': fp(path), 'original': row['file']})
        report['gif_http_readbacks'] = readbacks
        class LoggedCDP(browser_module.CDP):
            def call(self, method, params=None):
                cdp_log.write(json.dumps({'direction': 'sent', 'message': {'id': self.counter + 1, 'method': method, 'params': params or {}}}) + '\n'); cdp_log.flush()
                return super().call(method, params)
            def message(self):
                value = super().message()
                cdp_log.write(json.dumps({'direction': 'received', 'message': value}) + '\n'); cdp_log.flush()
                return value
        chrome = shutil.which('google-chrome') or shutil.which('chromium'); require(chrome, 'Existing Chrome required')
        port = browser_module.free_port()
        argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run',
                '--no-default-browser-check', '--disable-dev-shm-usage', '--window-size=1440,1200',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port), '--user-data-dir=' + profile, 'about:blank']
        if os.geteuid() == 0:
            argv.insert(1, '--no-sandbox')
        report['browser_argv'] = argv
        browser = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
        report['browser_pid'] = browser.pid; report['browser_birth_stat'] = Path('/proc', str(browser.pid), 'stat').read_text()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            require(browser.poll() is None, 'Browser exited during startup')
            try:
                with urlopen('http://127.0.0.1:' + str(port) + '/json/list', timeout=2) as response:
                    target = next(t for t in json.load(response) if t.get('type') == 'page')
                cdp = gallery_module.connect_cdp(LoggedCDP, target['webSocketDebuggerUrl']); cdp.socket.settimeout(20); break
            except (OSError, StopIteration):
                time.sleep(.1)
        require(cdp is not None, 'CDP startup timeout')
        cdp.call('Page.enable'); cdp.call('Network.enable'); cdp.call('Network.setCacheDisabled', {'cacheDisabled': True})
        cdp.call('Page.navigate', {'url': page_url})
        expression = "Array.from(document.querySelectorAll('article img')).map(i=>({src:i.getAttribute('src'),complete:i.complete,width:i.naturalWidth,height:i.naturalHeight}))"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            rows = cdp.evaluate(expression)
            if len(rows or []) == 3 and all(r['complete'] and r['width'] > 0 for r in rows):
                break
            time.sleep(.1)
        report['page_gifs'] = rows
        require(len(rows or []) == 3 and all(r['src'] == m['gif_path'] and [r['width'], r['height']] == [480, 270] and r['complete'] for r, m in zip(rows, manifest['cases'])), 'Actual page GIF decode differs')
        decode_js = "(async()=>{const wanted=" + json.dumps(expected) + ";const rows=[];for(const w of wanted){const i=new Image();await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('image timeout '+w.url)),15000);i.onload=()=>{clearTimeout(timer);resolve();};i.onerror=()=>{clearTimeout(timer);reject(Error('image load '+w.url));};i.src=w.url;});await i.decode();rows.push({url:w.url,complete:i.complete,width:i.naturalWidth,height:i.naturalHeight});}return rows;})()"
        decoded = cdp.evaluate(decode_js); report['decoded_images'] = decoded
        require(len(decoded) == 19 and all(a['url'] == b['url'] and a['complete'] and [a['width'], a['height']] == b['size'] for a, b in zip(decoded, expected)), 'All19 image decode/dimensions required')
        time.sleep(1)
        metrics = cdp.call('Page.getLayoutMetrics')['cssContentSize']
        screenshot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True,
            'clip': {'x': 0, 'y': 0, 'width': metrics['width'], 'height': metrics['height'], 'scale': 1}})
        (output / 'playback.png').write_bytes(base64.b64decode(screenshot['data']))
        report['page_text'] = cdp.evaluate('document.body.innerText')
        browser_paths = {r['path'] for r in requests if r['status'] == 200 and 'Chrome' in (r['user_agent'] or '')}
        require(all(r['url'] in browser_paths for r in expected), 'Each image requires actual Chrome HTTP200 receipt')
        checks = True
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if browser is not None:
            if cdp is not None and browser.poll() is None:
                report['browser_close_requested'] = True
                try:
                    cdp.call('Browser.close')
                except Exception as error:
                    report['browser_close_socket_outcome'] = str(error)
            try:
                report['browser_actual_wait_returncode'] = browser.wait(timeout=20)
            except subprocess.TimeoutExpired:
                report['browser_cleanup_kill_required'] = True
                browser.kill(); report['browser_actual_wait_returncode'] = browser.wait(timeout=10)
        if cdp is not None:
            cdp.socket.close()
        if browser is not None and report.get('browser_actual_wait_returncode') == 0:
            shutil.rmtree(profile); report['profile_deleted_after_actual_wait'] = not Path(profile).exists()
        else:
            report['preserved_profile'] = profile
        stdout.close(); stderr.close(); cdp_log.close()
        server.shutdown(); thread.join(timeout=10); server.server_close()
        report['server_thread_stopped'] = not thread.is_alive()
        write(output / 'http-requests.json', requests)
        try:
            restore.verify(MAIN, MAIN_SHA)
            report['main_seal_after'] = fp(MAIN / 'evidence-manifest.json')
            report['input_after'] = inventory(package); report['source_after'] = [fp(p) for p in sources]
            report['inputs_unchanged'] = report['input_after'] == input_before and report['source_after'] == source_before
        except BaseException as error:
            report['final_check_error'] = str(error)
        report['status'] = 'passed_actual_http_gif_and_png_browser_decode' if (checks and report.get('browser_actual_wait_returncode') == 0 and report.get('profile_deleted_after_actual_wait') and report.get('server_thread_stopped') and report.get('inputs_unchanged')) else 'failed'
        write(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'report': fp(output / 'report.json')}, ensure_ascii=False))
    return 0 if report['status'].startswith('passed_') else 1


if __name__ == '__main__':
    sys.exit(main())
