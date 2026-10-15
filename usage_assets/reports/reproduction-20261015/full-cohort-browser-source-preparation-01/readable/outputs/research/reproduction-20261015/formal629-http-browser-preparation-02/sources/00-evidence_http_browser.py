"""Reviewed stdlib HTTP/CPU-Chrome primitives; no science, Docker or installation.

Callers must verify their actual publication and this source before Session.start.
No service or browser starts on import, preflight, or any file-only helper.
"""
from __future__ import annotations
import base64
import datetime
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
SOURCES = {
    ROOT/'scripts/research/serve_evidence.py': 'abd436f0e1b322e2b53191fb98d8dac677ef1aa31f31db5e31c5ae1fb3088024',
    ROOT/'usage_assets/reports/official-evaluations-six/browser-reproduce/verify_gallery.py': '7cf157ead34e5a05fa7a65036659bc0f20cff5a41779c165f7a6e65d58123b8f',
    ROOT/'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py': '8a9edb9a34db22d8f29dc180088abfb94849c6c290a4e6b0336fdbf8b23efb06',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fp(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents))
            and path.is_file(), 'Unaliased regular file required')
    before = path.stat(); digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            digest.update(chunk)
    after = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(signature(before) == signature(after), 'File changed during hash')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def load(path, expected, name):
    require(fp(path)['sha256'] == expected, 'Pinned browser dependency changed')
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Dependency changed before loading')
    module = ModuleType(name); module.__file__ = str(path); module.__package__ = ''
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def preflight_sources():
    rows = [fp(Path(__file__))]
    for path, digest in SOURCES.items():
        row = fp(path); require(row['sha256'] == digest, 'Pinned HTTP/CDP source differs'); rows.append(row)
    return rows


def birth(pid):
    raw = Path(f'/proc/{pid}/stat').read_text(); fields = raw.rsplit(')', 1)[1].split()
    return {'pid': pid, 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
            'start_time_clock_ticks': int(fields[19]), 'stat_raw': raw}


def session_members(identity):
    rows = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            raw = path.read_text(); f = raw.rsplit(')', 1)[1].split()
            if int(f[3]) == identity['sid']:
                rows.append({'pid': int(path.parent.name), 'state': f[0], 'stat_raw': raw})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def wait_owned_browser(child, receipt):
    """Wait or clean up only this actual unreaped Popen child, never a PID/group."""
    try:
        code = child.wait(timeout=15); receipt['browser_cleanup'] = 'natural_wait'
    except subprocess.TimeoutExpired:
        child.terminate(); receipt['browser_cleanup'] = 'owned_browser_terminate'
        try:
            code = child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill(); receipt['browser_cleanup'] = 'owned_browser_kill'; code = child.wait(timeout=5)
    receipt['browser_actual_wait_returncode'] = code
    return code


class Session:
    def __init__(self, output, root=ROOT):
        self.output, self.root = Path(output).absolute(), Path(root).absolute()
        self.sources_before = preflight_sources()
        self.requests = []; self.browser_request_start = 0
        self.server = self.thread = self.browser = self.cdp = self.profile = None
        self.base_url = None; self.receipt = {'status': 'not_started', 'scope': 'HTTP/CPU browser only; no science',
            'started_utc': utc(), 'sources_before': self.sources_before}
        self.browser_user_agent = None
        self._lock = threading.Lock()

    def append(self, name, row):
        with self._lock, (self.output/name).open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); stream.flush()

    def start(self):
        require(self.output.is_dir() and self.root.is_dir()
                and not any(p.is_symlink() for p in (self.output, *self.output.parents, self.root, *self.root.parents)),
                'Caller-owned fresh output and regular HTTP root required')
        server_module, connect_module, cdp_module = [load(p, SOURCES[p], '_browser_'+p.stem) for p in SOURCES]
        owner = self
        class Handler(server_module.EvidenceHandler):
            def log_message(self, *args):
                pass
            def log_request(self, code='-', size='-'):
                row = {'observed_utc': utc(), 'method': self.command, 'path': self.path,
                       'status': int(code), 'range': self.headers.get('Range'), 'size': size,
                       'user_agent': self.headers.get('User-Agent'),
                       'request_headers': list(self.headers.items())}
                owner.requests.append(row); owner.append('http-requests.raw.jsonl', row)
        self.server = server_module.make_server(self.root, port=0, handler=Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base_url = 'http://127.0.0.1:'+str(self.server.server_address[1])
        self.receipt['base_url'] = self.base_url
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        require(chrome, 'Existing Chrome/Chromium required; installs nothing')
        self.profile = tempfile.mkdtemp(prefix='php-evidence-http-')
        port = cdp_module.free_port()
        argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run',
                '--no-default-browser-check', '--disable-dev-shm-usage', '--autoplay-policy=no-user-gesture-required',
                '--disable-features=VaapiVideoDecoder,AcceleratedVideoDecodeLinuxGL', '--window-size=1600,1200',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port='+str(port),
                '--user-data-dir='+self.profile, 'about:blank']
        if os.geteuid() == 0:
            argv.insert(1, '--no-sandbox')
        with (self.output/'chrome.stdout.raw').open('xb') as out, (self.output/'chrome.stderr.raw').open('xb') as err:
            self.browser = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                            start_new_session=True, close_fds=True)
        self.receipt.update(browser_argv=argv, actual_Popen_browser_pid=self.browser.pid)
        self.receipt.update(browser_argv=argv, browser_identity=birth(self.browser.pid),
                            host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        self.append('browser-start.raw.jsonl', self.receipt)
        deadline = time.monotonic()+35
        while time.monotonic() < deadline:
            require(self.browser.poll() is None, 'Owned Chrome exited during startup')
            try:
                with urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2) as response:
                    target = next(t for t in json.load(response) if t.get('type') == 'page')
                self.cdp = connect_module.connect_cdp(cdp_module.CDP, target['webSocketDebuggerUrl'])
                self.cdp.socket.settimeout(90); break
            except (OSError, StopIteration):
                time.sleep(.1)
        require(self.cdp is not None, 'Owned Chrome CDP startup timed out')
        self.call('Page.enable'); self.call('Network.enable'); self.call('Network.setCacheDisabled', {'cacheDisabled': True})
        self.browser_user_agent = self.call('Browser.getVersion')['userAgent']
        self.receipt['browser_user_agent'] = self.browser_user_agent
        self.browser_request_start = len(self.requests); self.receipt['status'] = 'running'
        return self.base_url

    def call(self, method, params=None):
        row = {'started_utc': utc(), 'method': method, 'params': params or {}}
        try:
            row['actual_response'] = result = self.cdp.call(method, params)
            return result
        except BaseException as error:
            row['actual_error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            row['finished_utc'] = utc(); self.append('cdp.raw.jsonl', row)

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        require('exceptionDetails' not in result, 'Actual browser JS failed: '+str(result.get('exceptionDetails')))
        return result.get('result', {}).get('value')

    def navigate(self, url, ready_expression):
        self.call('Page.navigate', {'url': url}); deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            try:
                if self.evaluate(ready_expression):
                    return
            except (RuntimeError, ValueError):
                pass
            time.sleep(.1)
        raise TimeoutError('Actual gallery readiness timed out')

    def range_probe(self, path, expected, identity):
        path = Path(path).absolute(); require(path.is_relative_to(self.root), 'Media outside HTTP root')
        before = fp(path); require(all(before[k] == expected[k] for k in ('bytes', 'sha256')), 'Original media differs')
        size = before['bytes']; require(size > 1, 'Nonzero media range required')
        start, end = min(97, size-1), min(size-1, min(97, size-1)+4095)
        with path.open('rb') as stream:
            stream.seek(start); original = stream.read(end-start+1)
        url = self.base_url+'/'+path.relative_to(self.root).as_posix()
        index = len(list(self.output.glob('range-*.body.raw')))
        body = self.output/f'range-{index:05d}.body.raw'
        row = {**identity, 'url': url, 'original': before, 'requested_range': f'bytes={start}-{end}'}
        try:
            with urlopen(Request(url, headers={'Range': row['requested_range'], 'User-Agent': 'php-evidence-explicit-range-probe'}), timeout=15) as response:
                row.update(status=response.status, response_headers=list(response.headers.items()))
                try:
                    data = response.read()
                except BaseException as error:
                    partial = getattr(error, 'partial', None)
                    if isinstance(partial, bytes):
                        body.write_bytes(partial); row['actual_partial_body'] = fp(body); row['body_complete'] = False
                    raise
                body.write_bytes(data); row['actual_body'] = fp(body); row['body_complete'] = True
                require(response.status == 206 and response.headers.get('Content-Range') == f'bytes {start}-{end}/{size}'
                        and response.headers.get('Accept-Ranges') == 'bytes' and response.headers.get('Content-Length') == str(len(original))
                        and data == original, 'Actual nonzero Range206 bytes/headers differ')
            row['source_segment_sha256'] = hashlib.sha256(original).hexdigest()
            require(fp(path) == before, 'Media changed during HTTP range')
            return row
        except BaseException as error:
            row['actual_error'] = {'type': type(error).__name__, 'message': str(error)}; raise
        finally:
            self.append('explicit-ranges.raw.jsonl', row)

    def check_video(self, url, expected, selector=None):
        expression = selector or "(()=>{const v=document.createElement('video');v.controls=true;document.body.append(v);return v;})()"
        script = '''(async()=>{const v=SELECTOR;const temporary=TEMPORARY;try{if(!temporary&&v.src!==URL)throw Error('actual DOM video source differs');v.src=URL;v.preload='auto';v.muted=true;
await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('metadata timeout')),15000);v.addEventListener('loadedmetadata',()=>{clearTimeout(t);resolve();},{once:true});v.addEventListener('error',()=>{clearTimeout(t);reject(Error(v.error?.message));},{once:true});v.load();});
const duration=v.duration,target=duration/2;await new Promise((resolve,reject)=>{const deadline=performance.now()+15000;const check=()=>{if([...Array(v.seekable.length)].some((_,i)=>v.seekable.start(i)<=target&&v.seekable.end(i)>=target))resolve();else if(performance.now()>deadline)reject(Error('seekable timeout'));else setTimeout(check,20);};check();});await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('seek timeout')),15000);v.addEventListener('seeked',()=>{clearTimeout(t);resolve();},{once:true});v.currentTime=target;});
await new Promise((resolve,reject)=>{const deadline=performance.now()+15000;const check=()=>{if(!v.seeking&&v.readyState>=2)resolve();else if(performance.now()>deadline)reject(Error('frame timeout'));else setTimeout(check,20);};check();});
const seek=v.currentTime;v.currentTime=0;const before=v.currentTime;await Promise.race([v.play(),new Promise((_,reject)=>setTimeout(()=>reject(Error('play timeout')),15000))]);await new Promise(r=>setTimeout(r,350));const after=v.currentTime;v.pause();return {url:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration,seek_target:target,seek_actual:seek,play_before:before,play_after:after,ended:v.ended,ready:v.readyState,controls:v.controls,error:v.error?.message};
}finally{v.pause();if(temporary){v.removeAttribute('src');v.load();v.remove();}}})()'''
        script = script.replace('SELECTOR', expression).replace('TEMPORARY', 'false' if selector else 'true').replace('URL', json.dumps(url))
        observed = self.evaluate(script)
        require(observed['url'] == url and observed['width'] == expected['width'] and observed['height'] == expected['height']
                and abs(observed['duration']-expected['duration_seconds']) < .05 and observed['duration'] > 0
                and abs(observed['seek_actual']-observed['seek_target']) < .05 and observed['ready'] >= 2
                and observed['controls'] is True and not observed.get('error'), 'Actual metadata/midpoint decoded seek differs')
        advance = observed['play_after']-observed['play_before']
        require((advance > .1 if observed['duration'] >= .25 else advance > 0 and observed['ended'] is True),
                'Actual per-video playback failed to advance/end')
        observed['one_frame_complete'] = expected.get('decoded_frames') == 1 and observed['ended'] is True and advance > 0
        return observed

    def check_images(self, urls):
        script = '''Promise.all(URLS.map(src=>new Promise((resolve,reject)=>{const i=new Image();const t=setTimeout(()=>reject(Error('image timeout')),15000);i.onload=()=>{clearTimeout(t);resolve({url:src,width:i.naturalWidth,height:i.naturalHeight});};i.onerror=()=>{clearTimeout(t);reject(Error(src));};i.src=src;})))'''.replace('URLS', json.dumps(urls))
        rows = self.evaluate(script)
        require([r['url'] for r in rows] == urls and all(min(r['width'], r['height']) > 0 for r in rows), 'Actual image decode/set differs')
        return rows

    def source_recheck(self):
        after = [fp(row['path']) for row in self.sources_before]
        require(after == self.sources_before, 'Browser/HTTP/CDP source changed')
        return after

    def close(self):
        errors = []
        if self.cdp:
            try:
                self.call('Browser.close')
            except Exception as error:
                self.receipt['browser_close_actual_error'] = str(error)
            finally:
                try:
                    self.cdp.socket.close()
                except Exception as error:
                    errors.append({'phase': 'cdp_socket_close', 'message': str(error)})
        waited = self.browser is None
        if self.browser is not None:
            try:
                wait_owned_browser(self.browser, self.receipt); waited = True
            except BaseException as error:
                errors.append({'phase': 'owned_browser_wait', 'type': type(error).__name__, 'message': str(error)})
        members = []
        identity = self.receipt.get('browser_identity')
        if identity is None and self.receipt.get('actual_Popen_browser_pid'):
            identity = {'sid': self.receipt['actual_Popen_browser_pid']}
        if identity:
            deadline = time.monotonic()+5
            while True:
                try:
                    members = session_members(identity)
                except BaseException as error:
                    errors.append({'phase': 'owned_session_scan_incomplete', 'type': type(error).__name__, 'message': str(error)})
                    members = [{'scan_incomplete': True}]
                    break
                if not members or time.monotonic() >= deadline:
                    break
                time.sleep(.05)
        self.receipt['remaining_owned_browser_session_members'] = members
        if self.profile and waited and not members:
            try:
                shutil.rmtree(self.profile); self.receipt['browser_profile_removed_after_actual_wait'] = True
            except Exception as error:
                errors.append({'phase': 'profile_cleanup', 'message': str(error)})
        elif self.profile:
            self.receipt['preserved_browser_profile'] = self.profile
        if self.server:
            try:
                self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
                self.receipt['http_server_stopped'] = not self.thread.is_alive()
            except Exception as error:
                errors.append({'phase': 'server_cleanup', 'message': str(error)})
        try:
            self.receipt['sources_after'] = self.source_recheck()
        except Exception as error:
            errors.append({'phase': 'source_recheck', 'message': str(error)})
        self.receipt.update(finished_utc=utc(), errors=errors)
        self.receipt['lifecycle_passed'] = (type(self.receipt.get('browser_actual_wait_returncode')) is int
            and self.receipt['browser_actual_wait_returncode'] == 0 and self.receipt.get('browser_cleanup') == 'natural_wait'
            and self.receipt.get('browser_profile_removed_after_actual_wait') is True and not members
            and self.receipt.get('http_server_stopped') is True and not errors)
        self.append('browser-final.raw.jsonl', self.receipt)
        return self.receipt
