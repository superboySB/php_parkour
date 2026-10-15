#!/usr/bin/env python3
"""Observe the actually adopted final-student TensorBoard UI; never start TB.

Requires explicit baseline and actual local HTTP/listener review SHA. This
does not start a tunnel, alter events, install packages, or approve adoption.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import ModuleType
from urllib.request import urlopen

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
OBSERVER = HERE / 'tb_adoption_observe_v3.py'
CDP = ROOT / 'usage_assets/reports/official-evaluations-six/browser-reproduce/viser_browser.py'
HANDSHAKE = CDP.with_name('verify_gallery.py')
PINS = {CDP: '8a9edb9a34db22d8f29dc180088abfb94849c6c290a4e6b0336fdbf8b23efb06',
        HANDSHAKE: '7cf157ead34e5a05fa7a65036659bc0f20cff5a41779c165f7a6e65d58123b8f'}


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require(path.is_relative_to(ROOT) and '..' not in path.parts
        and not any(p.is_symlink() for p in (path, *path.parents)), 'Explicit workspace evidence path required')
    return path


def fp(path):
    path = safe(path)
    before, digest = path.stat(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Evidence changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def load(path, expected):
    raw = safe(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Reviewed browser/observer helper changed')
    value = ModuleType('_final_students_browser_' + Path(path).stem)
    value.__file__, value.__package__ = str(path), ''
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + v)))


def inputs(args):
    baseline, checked = fp(args.baseline), fp(args.http_check)
    require(baseline['sha256'] == args.baseline_sha256 and checked['sha256'] == args.http_check_sha256,
        'Explicit actual baseline/HTTP check SHA differs')
    data, report = read(args.baseline), read(args.http_check)
    require(data['status'] == 'actual_completed_student_scalar_baseline_for_future_readonly_http_check'
        and data['base_url'] == 'http://127.0.0.1:6007' and report['status'] == 'passed'
        and report['url'] == data['base_url'] and report['baseline'] == baseline,
        'Actual passed local6007 check must bind this completed scalar baseline')
    require([s['kind'] for s in data['students']] == ['pure', 'finetune']
        and [s['final_step'] for s in data['students']] == [9999, 29999], 'Two actual final student runs required')
    expected_tags = [['Loss/behavior', 'Train/mean_reward'], ['Loss/behavior', 'Loss/total_loss', 'Train/mean_reward']]
    for student, tags in zip(data['students'], expected_tags):
        require(student['display_tags'] == tags and student['events'] and student['run'], 'Exact displayed curve scope differs')
        for tag in tags:
            expected = student['tags'][tag]
            found = [r for r in report['curves'] if r['kind'] == student['kind'] and r['run'] == student['run'] and r['tag'] == tag]
            require(len(found) == 1 and found[0]['last_step'] == student['final_step'] == expected['step']
                and found[0]['all_returned_values_finite'] is True
                and math.isclose(found[0]['last_value'], expected['value'], rel_tol=1e-6, abs_tol=1e-8),
                'Actual HTTP displayed curve differs from completed scalar')
    remote = report['remote_check']
    require(fp(remote['path']) == remote, 'Bound actual remote HTTP/event check changed')
    remote_data = read(remote['path'])
    require(remote_data['status'] == 'passed' and remote_data['events_unchanged'] is True
        and remote_data['baseline']['sha256'] == baseline['sha256'], 'Actual remote events/serving proof missing')
    require(report['observer_source'] == fp(OBSERVER), 'Actual local checker source differs')
    observer = load(OBSERVER, report['observer_source']['sha256'])
    expected = argparse.Namespace(expected_pid=report['expected_listener']['pid'],
        expected_start_ticks=report['expected_listener']['start_time_clock_ticks'])
    observed = observer.port_snapshot(6007)
    owner = observer.owner_guard(observed, expected)
    old = observer.owner_guard(report['listener_after'], expected)
    require(observer.owner_identity(owner) == observer.owner_identity(old)
        and observed['host_boot_id'] == report['listener_after']['host_boot_id']
        and observed['listeners'] == report['listener_after']['listeners'], 'Reviewed SSH listener generation changed')
    bound = [baseline, checked, remote, report['observer_source'], fp(__file__), *[fp(p) for p in PINS]]
    for row in report['requests']:
        require(row['http_status'] == 200 and fp(row['body']['path']) == row['body'], 'Actual checked HTTP raw body changed')
        bound.append(row['body'])
    return data, report, observer, expected, observed, bound


def type_filter(cdp, placeholder, text):
    selector = 'input[placeholder=' + json.dumps(placeholder) + ']'
    cdp.evaluate('(()=>{const e=document.querySelector(' + json.dumps(selector) + ');if(!e)throw Error("filter input missing");e.focus();e.select();})()')
    cdp.call('Input.insertText', {'text': text})
    for kind in ('keyDown', 'keyUp'):
        cdp.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})


def run(args):
    data, http, observer, expected, listener_before, bound = inputs(args)
    output = safe(args.output)
    require(not output.exists() and output.parent.is_dir(), 'Fresh browser output under existing directory required')
    require(not any(Path(r['path']).is_relative_to(output) for r in bound),
        'Browser output may not contain/alter bound evidence')
    helpers = {p.name: load(p, digest) for p, digest in PINS.items()}
    base_cdp, handshake = helpers['viser_browser.py'], helpers['verify_gallery.py']
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    require(chrome, 'Existing Chrome required; no browser installation is performed')
    output.mkdir()
    report = {'schema_version': 1, 'status': 'failed', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'url': data['base_url'], 'baseline': bound[0], 'actual_http_check': bound[1], 'input_before': bound,
        'listener_before': listener_before, 'views': [], 'quality_verified': False, 'convergence_verified': False,
        'scope': 'Actual displayed final-student TensorBoard UI only, guarded by real local SSH listener/HTTP and remote unchanged-event evidence. No TensorBoard/tunnel start, training, adoption approval or quality/convergence claim.'}
    browser = cdp = profile_context = None
    with (output / 'cdp.jsonl').open('x') as protocol:
        def log(kind, value):
            protocol.write(json.dumps({'observed_unix': time.time(), 'direction': kind, 'value': value}, allow_nan=False) + '\n')
            protocol.flush()
        class LoggedCDP(base_cdp.CDP):
            def message(self):
                message = super().message()
                log('received', message)
                return message
            def call(self, method, params=None):
                log('sent', {'method': method, 'params': params or {}})
                return super().call(method, params)
        try:
            profile_context = tempfile.TemporaryDirectory(prefix='tb-final-ui-')
            profile = profile_context.name
            with (output / 'chrome.stdout.raw').open('xb') as stdout, (output / 'chrome.stderr.raw').open('xb') as stderr:
                port = base_cdp.free_port()
                argv = [chrome, '--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run',
                    '--no-default-browser-check', '--disable-dev-shm-usage', '--window-size=1800,1200',
                    '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port), '--user-data-dir=' + profile, 'about:blank']
                if os.geteuid() == 0:
                    argv.insert(1, '--no-sandbox')
                report['browser_argv'] = argv
                browser = subprocess.Popen(argv, stdout=stdout, stderr=stderr, start_new_session=True)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    require(browser.poll() is None, 'Chrome exited before CDP connection')
                    try:
                        with urlopen('http://127.0.0.1:' + str(port) + '/json/list', timeout=2) as response:
                            target = next(t for t in json.load(response) if t.get('type') == 'page')
                        cdp = handshake.connect_cdp(LoggedCDP, target['webSocketDebuggerUrl'])
                        cdp.socket.settimeout(40)
                        break
                    except (OSError, StopIteration):
                        time.sleep(.1)
                require(cdp is not None, 'Actual Chrome CDP connection timeout')
                cdp.call('Page.enable')
                cdp.call('Network.enable')
                cdp.call('Page.navigate', {'url': data['base_url'] + '/#scalars'})
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if cdp.evaluate('!!document.querySelector(\'input[placeholder="Filter tags (regex)"]\')'):
                        break
                    time.sleep(.2)
                else:
                    raise TimeoutError('Actual TensorBoard scalar filters did not appear')
                cdp.evaluate("(()=>{const e=[...document.querySelectorAll('input[type=checkbox]')].find(e=>e.parentElement.parentElement.innerText.includes('Ignore outliers in chart scaling'));if(!e)throw Error('outlier setting missing');if(e.checked)e.click();})()")
                cdp.evaluate("(()=>{const e=[...document.querySelectorAll('input[type=number]')].find(e=>Number(e.value)===0.6);if(!e)throw Error('smoothing input missing');e.focus();e.select();})()")
                for kind in ('keyDown', 'keyUp'):
                    cdp.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'a', 'code': 'KeyA', 'windowsVirtualKeyCode': 65, 'modifiers': 2})
                for kind in ('keyDown', 'keyUp'):
                    cdp.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'Backspace', 'code': 'Backspace', 'windowsVirtualKeyCode': 8})
                cdp.call('Input.insertText', {'text': '0'})
                for kind in ('keyDown', 'keyUp'):
                    cdp.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})
                cdp.evaluate('document.activeElement.blur()')
                time.sleep(.3)
                settings = cdp.evaluate("({smoothing:Number([...document.querySelectorAll('input[type=range]')].find(e=>Number(e.value)<1)?.value),ignore_outliers:[...document.querySelectorAll('input[type=checkbox]')].find(e=>e.parentElement.parentElement.innerText.includes('Ignore outliers in chart scaling'))?.checked})")
                require(settings.get('smoothing') == 0 and settings.get('ignore_outliers') is False, 'Actual chart settings did not apply')
                report['chart_settings'] = settings
                cdp.evaluate('document.querySelector(\'button[aria-label="Close side pane"]\')?.click()')
                for student in data['students']:
                    run_regex = '^' + re.escape(student['run']) + '$'
                    tags_regex = '^(?:' + '|'.join(re.escape(t) for t in student['display_tags']) + ')$'
                    type_filter(cdp, 'Filter runs (regex)', run_regex)
                    type_filter(cdp, 'Filter tags (regex)', tags_regex)
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        text = cdp.evaluate('document.body.innerText') or ''
                        compact = re.sub(r'\s+', '', text)
                        other = next(s['run'] for s in data['students'] if s['kind'] != student['kind'])
                        if all(t in compact for t in student['display_tags']) and other not in text:
                            break
                        time.sleep(.2)
                    else:
                        raise TimeoutError('Exact actual run/tag cards did not appear: ' + student['kind'])
                    cdp.evaluate('Array.from(document.querySelectorAll(\'button[aria-label="Fit line chart domains to data"]\')).forEach(e=>e.click())')
                    time.sleep(.5)
                    controls = cdp.evaluate("({run:document.querySelector('input[placeholder=\"Filter runs (regex)\"]')?.value,tags:document.querySelector('input[placeholder=\"Filter tags (regex)\"]')?.value})")
                    require(controls == {'run': run_regex, 'tags': tags_regex}, 'Actual exact UI filters differ')
                    canvases = cdp.evaluate("[...document.querySelectorAll('canvas')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0}).map(e=>{const c=document.createElement('canvas');c.width=e.width;c.height=e.height;const x=c.getContext('2d');x.drawImage(e,0,0);const p=x.getImageData(0,0,e.width,e.height).data;let colored=0;for(let i=0;i<p.length;i+=4)if(p[i+3]>0&&Math.max(p[i],p[i+1],p[i+2])-Math.min(p[i],p[i+1],p[i+2])>20)colored++;return {width:e.width,height:e.height,colored_pixels:colored};})")
                    require(len(canvases) >= len(student['display_tags']) and all(c['colored_pixels'] >= 10 for c in canvases), 'Actual colored curves did not render')
                    screenshot = output / (student['kind'] + '.png')
                    screenshot.write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})['data']))
                    (output / (student['kind'] + '.dom.html')).write_text(cdp.evaluate('document.documentElement.outerHTML'))
                    (output / (student['kind'] + '.visible.txt')).write_text(text)
                    report['views'].append({'kind': student['kind'], 'run': student['run'], 'final_step': student['final_step'],
                        'display_tags': student['display_tags'], 'exact_ui_filters': controls, 'colored_canvases': canvases,
                        'screenshot': fp(screenshot), 'location': cdp.evaluate('location.href')})
                report['status'] = 'passed'
        except BaseException as error:
            report['status'], report['error'] = 'failed', type(error).__name__ + ': ' + str(error)
            if cdp:
                try:
                    (output / 'failure.dom.html').write_text(cdp.evaluate('document.documentElement.outerHTML'))
                    (output / 'failure.png').write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot', {'format': 'png'})['data']))
                except Exception as diagnostic:
                    report['failure_capture_error'] = str(diagnostic)
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
                    report['browser_cleanup'] = 'owned_browser_terminate'
                    try:
                        report['browser_actual_wait'] = browser.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        browser.kill()
                        report['browser_cleanup'] = 'owned_browser_kill'
                        report['browser_actual_wait'] = browser.wait(timeout=5)
            if profile_context is not None:
                try:
                    profile_context.cleanup()
                    report['profile_cleanup_after_browser_wait'] = True
                except Exception as error:
                    report['status'], report['profile_cleanup_error'] = 'failed', str(error)
            try:
                after = observer.port_snapshot(6007)
                owner = observer.owner_guard(after, expected)
                prior = observer.owner_guard(listener_before, expected)
                require(observer.owner_identity(owner) == observer.owner_identity(prior)
                    and after['host_boot_id'] == listener_before['host_boot_id'] and after['listeners'] == listener_before['listeners'],
                    'Actual reviewed SSH listener changed during browser observation')
                report['listener_after'] = after
                report['input_after'] = [fp(r['path']) for r in bound]
                require(report['input_after'] == bound, 'Actual baseline/reviews/helpers/raw HTTP evidence changed')
                report['inputs_unchanged'] = True
            except Exception as error:
                report['status'], report['final_recheck_error'] = 'failed', str(error)
            if report.get('browser_actual_wait') != 0 or report.get('browser_cleanup') != 'natural_wait':
                report['status'] = 'failed'
            report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
            (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'views': len(report['views']), 'report': str(output / 'report.json')}))
    return int(report['status'] != 'passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'http-check', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('baseline-sha256', 'http-check-sha256'):
        parser.add_argument('--' + name, required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
