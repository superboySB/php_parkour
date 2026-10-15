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


core = load('evidence_http_browser'); adapter = load('verify_formal629_http05')


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
    def test_exact_compiled_module_bytes_loaded_without_process_or_network(self):
        path = self.base/'synthetic.py'; path.write_text('value = 123\n'); expected = adapter.file_fp(path)
        with patch.object(core.subprocess, 'Popen', side_effect=AssertionError('No process')), patch.object(core, 'urlopen', side_effect=AssertionError('No network')):
            self.assertEqual(adapter.checked_module(path, expected, 'synthetic_source').value, 123)
    def test_module_read_drift_refused_before_changed_bytes_compile(self):
        path = self.base/'synthetic.py'; path.write_text('value = 1\n'); expected = adapter.file_fp(path)
        path.write_text("raise AssertionError('changed bytes must never execute')\n")
        with patch.object(adapter, 'file_fp', return_value=expected), self.assertRaisesRegex(ValueError, 'before compile'):
            adapter.checked_module(path, expected, 'synthetic_changed_source')
    def test_missing_or_wrong_preparation_refuses_before_output_or_network(self):
        p = self.base/'manifest.json'; p.write_text('{}')
        args = SimpleNamespace(preparation_sha256='0'*64, manifest_sha256='1'*64, package=self.base/'missing', output=self.base/'out')
        with patch.object(adapter, 'PREPARATION', p), patch.object(core.subprocess, 'Popen', side_effect=AssertionError('No process')), patch.object(core, 'urlopen', side_effect=AssertionError('No HTTP')):
            with self.assertRaisesRegex(ValueError, 'Browser preparation differs'):
                adapter.preflight(args)
        self.assertFalse(args.output.exists())
    def test_old_sealed_preparation_cannot_be_browser_output_parent(self):
        manifest = self.base/'synthetic-manifest.json'
        dependencies = [adapter.file_fp(HERE/'verify_formal629_http05.py'), adapter.file_fp(HERE/'evidence_http_browser.py')]
        manifest.write_text(json.dumps({'synthetic_fixture': True, 'dependencies': dependencies}))
        output = HERE/'formal629-http-browser-preparation-02/synthetic-must-never-create'
        args = SimpleNamespace(preparation_sha256=adapter.file_fp(manifest)['sha256'], manifest_sha256='1'*64,
                               package=adapter.ROOT/'usage_assets/reports/synthetic-missing-never-created', output=output)
        with patch.object(adapter, 'PREPARATION', manifest), patch.object(core.subprocess, 'Popen', side_effect=AssertionError('No process')), patch.object(core, 'urlopen', side_effect=AssertionError('No network')):
            with self.assertRaisesRegex(ValueError, 'fresh separate browser output'):
                adapter.preflight(args)
        self.assertFalse(output.exists())
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
    def test_legal_byte_alias_keeps1258_case_video_visits(self):
        s, rows, sub = self.fixture(); rows['pure'][1]['videos'][0]['path'] = rows['pure'][0]['videos'][0]['path']
        result = self.validate(s, rows, sub); self.assertEqual(len(result), 1258)
        self.assertEqual(result[('pure', 'case-0000')]['video'], result[('pure', 'case-0001')]['video'])
    def case_fixture(self):
        # An explicit synthetic raw/model/map schema, never an actual publication.
        package = self.base/'synthetic-package'; (package/'raw').mkdir(parents=True); (package/'pure').mkdir()
        contract = {'base': str(self.base/'synthetic-original'), 'image_id': 'synthetic-image',
                    'kinds': {'pure': {'native_plan_identity': 'synthetic-plan'}}, 'admission': {'models': [
                        {'kind': 'pure', 'path': '/synthetic/student.onnx', 'bytes': 100, 'sha256': '0'*64},
                        {'kind': 'pure', 'path': '/synthetic/depth_backbone.onnx', 'bytes': 100, 'sha256': '1'*64}]}}
        models = {'student.onnx': '0'*64, 'depth_backbone.onnx': '1'*64}; files = {}; mappings = {}; cases = []
        def store(name, raw):
            path = package/'raw'/name; path.write_bytes(raw); record = core.fp(path)
            files['raw/'+name] = {k: record[k] for k in ('bytes', 'sha256')}; return path
        video = store('aliased.mp4', b'synthetic pixels; not a real MP4'); poster = store('aliased.png', b'synthetic PNG fixture')
        trajectory = store('trajectory.csv', b'synthetic trajectory fixture\n')
        result = store('result.json', json.dumps({'status': 'completed', 'inference': {'ticks': 1}, 'video_checks': [
            {'video': 'video/a.mp4', 'thumbnail': 'video/a.png', 'probe': {'streams': [{'width': 640, 'height': 360}], 'format': {'duration': '1.0'}}}]}).encode())
        for index in range(2):
            container = '/outputs/reference629/scene/config-'+str(index); original = Path(contract['base'])/'runs/pure/outputs/reference629/scene'/('config-'+str(index))
            raw_files = []
            for actual, name in ((result, 'result.json'), (video, 'video/a.mp4'), (poster, 'video/a.png'), (trajectory, 'trajectory.csv')):
                a = core.fp(actual); raw_files.append({'path': container+'/'+name, 'bytes': a['bytes'], 'sha256': a['sha256']})
                mappings[str(original/name)] = {'original_path': str(original/name), 'bytes': a['bytes'], 'sha256': a['sha256'], 'storage': {'kind': 'file', 'path': actual.relative_to(package).as_posix()}}
            case_id = f'scene:{index:04d}:synthetic-configuration'
            evidence = store('case-'+str(index)+'.json', json.dumps({'case_input': {'case_id': case_id, 'model_sha256': models,
                'plan_sha256': 'synthetic-plan', 'image_id': 'synthetic-image', 'launch': ['python', '--output', container]},
                'result_sha256': core.fp(result)['sha256'], 'files': raw_files}).encode())
            e = core.fp(evidence); mappings[str(original/'case-evidence.json')] = {'original_path': str(original/'case-evidence.json'), 'bytes': e['bytes'], 'sha256': e['sha256'], 'storage': {'kind': 'file', 'path': evidence.relative_to(package).as_posix()}}
            row = {'case_id': case_id, 'scenario': 'scene', 'configuration_index': index, 'configuration': 'synthetic-configuration',
                   'case_evidence': '../'+evidence.relative_to(package).as_posix(), 'result_json': '../raw/result.json', 'trajectory_csv': '../raw/trajectory.csv', 'status': 'completed', 'policy_ticks': 1}
            svg = package/'pure/cases/scene'/f'config-{index:04d}'/'world-xy.svg'
            record = {'video': video, 'images': [svg, poster], 'expected': {'width': 640, 'height': 360, 'duration_seconds': 1.0}}
            cases.append((row, record))
        return package, contract, mappings, files, cases
    def test_actual_raw_schema_allows_two_original_cases_same_video_blob(self):
        package, contract, mappings, files, cases = self.case_fixture()
        for row, record in cases:
            result = adapter.validate_case_binding(package, 'pure', row, record, contract, mappings, files)
            self.assertEqual(result['model_sha256'], adapter.actual_model_table(contract, 'pure'))
    def test_wrong_case_video_mapping_and_empty_or_wrong_model_rejected(self):
        for which in ('case', 'video', 'empty_model', 'wrong_model'):
            package, contract, mappings, files, cases = self.case_fixture() if not (self.base/'synthetic-package').exists() else self._fixture_rebuild()
            row, record = cases[0]
            if which == 'case': row['case_id'] = 'wrong-case'
            elif which == 'video': record['video'] = record['images'][1]
            elif which == 'empty_model': contract['admission']['models'] = []
            else: contract['admission']['models'][0]['sha256'] = '2'*64
            with self.subTest(which=which), self.assertRaises(ValueError):
                adapter.validate_case_binding(package, 'pure', row, record, contract, mappings, files)
    def test_wrong_derived_svg_case_fields_or_trajectory_alias_rejected(self):
        for which in ('svg', 'scenario', 'index', 'configuration', 'trajectory'):
            package, contract, mappings, files, cases = self.case_fixture() if not (self.base/'synthetic-package').exists() else self._fixture_rebuild()
            row, record = cases[0]
            if which == 'svg': record['images'][0] = cases[1][1]['images'][0]
            elif which == 'scenario': row['scenario'] = 'other-scene'
            elif which == 'index': row['configuration_index'] = 1
            elif which == 'configuration': row['configuration'] = 'other-configuration'
            else: row['trajectory_csv'] = '../raw/aliased.mp4'
            with self.subTest(which=which), self.assertRaises(ValueError):
                adapter.validate_case_binding(package, 'pure', row, record, contract, mappings, files)
    def _fixture_rebuild(self):
        import shutil
        shutil.rmtree(self.base/'synthetic-package'); return self.case_fixture()
    def test_partial_wrong_policy_duplicate_case_or_media_refused(self):
        for which in ('count', 'policy', 'case', 'model'):
            s, rows, sub = self.fixture()
            if which == 'count': rows['pure'].pop()
            elif which == 'policy': rows['pure'][0]['model_kind'] = 'finetune'
            elif which == 'case': rows['pure'][1]['case_id'] = rows['pure'][0]['case_id']
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
