"""Ordinary CPU source/refusal/lifecycle controls; never Chrome/HTTP/science."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path('/home/dzp/projects/php_parkour/outputs/research/reproduction-20261015')


def load(name):
    p = HERE/(name+'.py'); m = ModuleType(name); m.__file__ = str(p)
    exec(compile(p.read_bytes(), str(p), 'exec'), m.__dict__); return m


core = load('evidence_http_browser'); adapter = load('verify_formal629_http')


class BrowserControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE/'local-checks'); self.base = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def observed(self, duration=1.0):
        return {'url': 'http://127.0.0.1/video.mp4', 'width': 640, 'height': 360, 'duration': duration,
                'seek_target': duration/2, 'seek_actual': duration/2, 'play_before': 0.,
                'play_after': min(.35, duration), 'ended': duration <= .35, 'ready': 4, 'controls': True}
    def video(self, actual, duration=1.0, frames=50):
        session = core.Session.__new__(core.Session); session.evaluate = lambda script: actual
        return session.check_video('http://127.0.0.1/video.mp4', {'width': 640, 'height': 360,
                                  'duration_seconds': duration, 'decoded_frames': frames})
    def test_pinned_sources_readonly_without_Popen_or_HTTP(self):
        with patch.object(core.subprocess, 'Popen', side_effect=AssertionError('No process allowed')), patch.object(core, 'urlopen', side_effect=AssertionError('No HTTP allowed')):
            self.assertEqual(len(core.preflight_sources()), 4)
    def test_missing_or_wrong_preparation_refuses_before_output_or_network(self):
        p = self.base/'manifest.json'; p.write_text('{}')
        args = SimpleNamespace(preparation_sha256='0'*64, manifest_sha256='1'*64, package=self.base/'missing', output=self.base/'out')
        with patch.object(adapter, 'PREPARATION', p), patch.object(core.subprocess, 'Popen', side_effect=AssertionError('No process')), patch.object(core, 'urlopen', side_effect=AssertionError('No HTTP')):
            with self.assertRaisesRegex(ValueError, 'Browser preparation differs'):
                adapter.preflight(args)
        self.assertFalse(args.output.exists())
    def test_long_media_actual_positive_play(self):
        self.assertFalse(self.video(self.observed())['one_frame_complete'])
    def test_one_frame_positive_end_is_complete_not_visible_motion(self):
        row = self.video(self.observed(.02), .02, 1); self.assertTrue(row['one_frame_complete'])
    def test_short_without_positive_progress_or_end_rejected(self):
        for change in ({'play_after': 0.}, {'ended': False}):
            row = dict(self.observed(.02), **change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'playback'):
                self.video(row, .02, 1)
    def test_metadata_seek_error_controls_mismatch_refused(self):
        for change in ({'width': 641}, {'url': 'http://other/x'}, {'duration': 1.3},
                       {'seek_actual': .7}, {'ready': 1}, {'controls': False}, {'error': 'decode failed'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'metadata'):
                self.video(dict(self.observed(), **change))
    def test_nonadvancing_long_video_rejected(self):
        with self.assertRaisesRegex(ValueError, 'playback'):
            self.video(dict(self.observed(), play_after=.05))
    def test_gallery_alias_and_outside_member_rejected(self):
        package = self.base/'package'; (package/'pure').mkdir(parents=True)
        (self.base/'outside.mp4').write_bytes(b'x'); (package/'pure/alias.mp4').symlink_to(self.base/'outside.mp4')
        for name in ('alias.mp4', '../../outside.mp4'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                adapter.member(package, 'pure', name, {})
    def fixture(self):
        summary = {'status': 'completed_formal_pair_publication', **adapter.COUNTS,
                   'kind_order': ['pure', 'finetune'], 'quality_verified': False, 'obstacle_course_completion_verified': False,
                   'kinds': [{'model_kind': k, 'model_sha256': {'synthetic.onnx': k}} for k in adapter.KINDS]}
        rows = {k: [{'ordinal': i, 'case_id': f'case-{i:04d}', 'scenario': 'scene-'+str(i%17), 'model_kind': k,
                     'status': 'completed', 'videos': [{'path': f'media-{i}.mp4', 'thumbnail': f'poster-{i}.png',
                     'width': 640, 'height': 360, 'duration_seconds': 1.}], 'trajectory_svg': f'trajectory-{i}.svg',
                     'threshold_event': False, 'quality_verified': False, 'obstacle_course_completion_verified': False}
                    for i in range(629)] for k in adapter.KINDS}
        sub = {k: {'status': 'completed_publication', 'model_kind': k, 'preview': False, 'configurations': 629,
                   'planned_configurations': 629, 'model_sha256': {'synthetic.onnx': k}, 'threshold_events': 0,
                   'no_threshold_events': 629, 'quality_verified': False, 'obstacle_course_completion_verified': False}
               for k in adapter.KINDS}
        return summary, rows, sub
    def validate(self, summary, rows, sub):
        # Explicit synthetic pure-schema fixtures, no actual published bytes or browser admission.
        with patch.object(adapter, 'strict_json', side_effect=lambda p: sub[p.parent.name]), patch.object(adapter, 'member', side_effect=lambda p,k,n,f: p/k/n):
            return adapter.validate_rows(self.base, summary, rows, {})
    def test_synthetic_exact_two629_schema(self):
        s, rows, sub = self.fixture(); self.assertEqual(len(self.validate(s, rows, sub)), 1258)
    def test_partial_wrong_policy_duplicate_case_or_media_refused(self):
        for which in ('count', 'policy', 'case', 'video', 'model'):
            s, rows, sub = self.fixture()
            if which == 'count': rows['pure'].pop()
            elif which == 'policy': rows['pure'][0]['model_kind'] = 'finetune'
            elif which == 'case': rows['pure'][1]['case_id'] = rows['pure'][0]['case_id']
            elif which == 'video': rows['pure'][1]['videos'][0]['path'] = rows['pure'][0]['videos'][0]['path']
            else: sub['pure']['model_sha256'] = {'wrong': 'model'}
            with self.subTest(which=which), self.assertRaises(ValueError): self.validate(s, rows, sub)
    def test_range_partial_headers_retained_no_server(self):
        media = self.base/'test.mp4'; media.write_bytes(b'x'*5000)
        out = self.base/'output'; out.mkdir(); session = core.Session(out, self.base); session.base_url = 'http://127.0.0.1:9'
        class Response:
            status = 206; headers = {'Content-Range': 'bytes 97-4192/5000', 'Content-Length': '4096', 'Accept-Ranges': 'bytes'}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): raise http.client.IncompleteRead(b'actual synthetic partial', 4096)
        with patch.object(core, 'urlopen', return_value=Response()), self.assertRaises(http.client.IncompleteRead):
            session.range_probe(media, core.fp(media), {'synthetic_fixture': True})
        row = json.loads((out/'explicit-ranges.raw.jsonl').read_text()); self.assertFalse(row['body_complete']); self.assertEqual(row['status'], 206)
        self.assertEqual(Path(row['actual_partial_body']['path']).read_bytes(), b'actual synthetic partial')
    def test_range_wrong_status_retains_body_no_server(self):
        media = self.base/'test.mp4'; media.write_bytes(b'x'*5000); out = self.base/'output'; out.mkdir()
        session = core.Session(out, self.base); session.base_url = 'http://127.0.0.1:9'
        class Response:
            status = 200; headers = {}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'x'*4096
        with patch.object(core, 'urlopen', return_value=Response()), self.assertRaisesRegex(ValueError, 'Range206'):
            session.range_probe(media, core.fp(media), {'synthetic_fixture': True})
        row = json.loads((out/'explicit-ranges.raw.jsonl').read_text()); self.assertEqual(row['status'], 200); self.assertTrue(row['body_complete'])
    def test_real_ordinary_cpu_child_natural_zero_and_seven(self):
        controls = Path(os.environ.get('PHP_BROWSER_CONTROL_DIR', str(self.base)))
        for code in (0, 7):
            argv = ['/usr/bin/python3', '-B', '-c', f'raise SystemExit({code})']; receipt = {'scope': 'Actual ordinary CPU stand-in only; never Chrome'}
            with (controls/f'child-{code}.stdout.raw').open('xb') as out, (controls/f'child-{code}.stderr.raw').open('xb') as err:
                child = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True); receipt.update(argv=argv, actual_child=core.birth(child.pid))
                self.assertEqual(core.wait_owned_browser(child, receipt), code)
            self.assertEqual(receipt['browser_cleanup'], 'natural_wait'); self.assertEqual(core.session_members(receipt['actual_child']), [])
            (controls/f'child-{code}.json').write_text(json.dumps(receipt, indent=2)+'\n')
    def test_real_owned_term_then_kill_is_preserved_nonzero(self):
        controls = Path(os.environ.get('PHP_BROWSER_CONTROL_DIR', str(self.base)))
        argv = ['/usr/bin/python3', '-B', '-c', "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(30)"]
        with (controls/'child-kill.stderr.raw').open('xb') as err:
            child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=err, start_new_session=True)
            ready = child.stdout.readline(); (controls/'child-kill.stdout.raw').write_bytes(ready); self.assertEqual(ready, b'ready\n')
            receipt = {'scope': 'Actual ordinary CPU stand-in, shortened test wait budget; never Chrome', 'argv': argv, 'actual_child': core.birth(child.pid)}
            class ShortOwnedWait:
                def wait(self, timeout): return child.wait(timeout=min(timeout, .05))
                def terminate(self): return child.terminate()
                def kill(self): return child.kill()
            self.assertEqual(core.wait_owned_browser(ShortOwnedWait(), receipt), -9)
            child.stdout.close()
        self.assertEqual(receipt['browser_cleanup'], 'owned_browser_kill'); self.assertEqual(core.session_members(receipt['actual_child']), [])
        (controls/'child-kill.json').write_text(json.dumps(receipt, indent=2)+'\n')
    def test_real_cpu_owned_wait_before_profile_remove_and_server_stop_protocol(self):
        controls = Path(os.environ.get('PHP_BROWSER_CONTROL_DIR', str(self.base)))
        output = self.base/'output'; output.mkdir(); session = core.Session(output, self.base)
        session.profile = tempfile.mkdtemp(dir=self.base); profile = Path(session.profile)
        argv = ['/usr/bin/python3', '-B', '-c', 'raise SystemExit(0)']
        with (controls/'child-profile.stdout.raw').open('xb') as out, (controls/'child-profile.stderr.raw').open('xb') as err:
            session.browser = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
            session.receipt.update(browser_identity=core.birth(session.browser.pid), actual_Popen_browser_pid=session.browser.pid,
                                   synthetic_scope='Actual ordinaryCPU child and fake no-server cleanup protocol, never Chrome/HTTP')
            class NoServer:
                def shutdown(self): return None
                def server_close(self): return None
            class NoThread:
                def join(self, timeout): return None
                def is_alive(self): return False
            session.server = NoServer(); session.thread = NoThread()
            row = session.close()
        self.assertTrue(row['lifecycle_passed']); self.assertEqual(row['browser_actual_wait_returncode'], 0); self.assertFalse(profile.exists())
        (controls/'child-profile.json').write_text(json.dumps(row, indent=2)+'\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
