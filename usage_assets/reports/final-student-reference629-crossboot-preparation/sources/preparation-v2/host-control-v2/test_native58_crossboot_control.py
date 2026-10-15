"""Ordinary CPU controls; no native/Docker/GPU or future scientific receipt."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_actual_crossboot_parent', HERE / 'native58_crossboot_control.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class ControlTests(unittest.TestCase):
    def test_real_current_process_birth(self):
        row = C.process(Path('/proc/self/stat').read_text())
        self.assertEqual(row['pid'], os.getpid())
        self.assertGreater(row['start_time_clock_ticks'], 0)

    def test_real_outer_self_stat_and_direct_parent_identity(self):
        # Reuse actual readable ordinary process stat fields; no child starts.
        raw = Path('/proc/self/stat').read_text()
        current = C.process(raw)
        parent_raw = Path('/proc', str(current['ppid']), 'stat').read_text()
        parent = C.process(parent_raw)
        outer = {'wrapper_process': {**parent, 'stat': parent_raw}, 'launcher_process': {**current, 'stat': raw}}
        C.verify_outer_birth(outer, current)
        wrong_owner = {**current, 'ppid': current['ppid'] + 1}
        with self.assertRaisesRegex(ValueError, 'direct child'):
            C.verify_outer_birth(outer, wrong_owner)
        changed = copy.deepcopy(outer)
        changed['wrapper_process']['start_time_clock_ticks'] += 1
        with self.assertRaisesRegex(ValueError, 'structured birth'):
            C.verify_outer_birth(changed, current)

    def response(self):
        cid = 'a' * 64
        body = json.dumps({'message': 'No such container: ' + cid}).encode()
        return cid, {'method': 'GET', 'route': '/containers/' + cid + '/json', 'http_status': 404,
                     'body_hex': body.hex(), 'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
                     'json': json.loads(body)}

    def test_recorded_actual_api_bytes_and_route(self):
        cid, row = self.response()
        self.assertEqual(C.recorded_api(row, '/containers/' + cid + '/json'), row['json'])

    def test_recorded_body_changed_rejected(self):
        cid, row = self.response()
        row['body_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fingerprint/route'):
            C.recorded_api(row, '/containers/' + cid + '/json')

    def test_wrong_route_rejected(self):
        _, row = self.response()
        with self.assertRaises(ValueError):
            C.recorded_api(row, '/containers/' + 'b' * 64 + '/json')

    def test_json_duplicate_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                C.parse(raw)

    def test_exact_outer_raw_log_fingerprints(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary)
            for name in ('launcher.stdout.raw', 'launcher.stderr.raw'):
                (root / name).write_text('ordinary CPU fixture only\n')
            outer = {'launcher_logs': [C.fp(root / name) for name in ('launcher.stdout.raw', 'launcher.stderr.raw')]}
            C.verify_outer_logs(outer, root, C.fp)
            outer['launcher_logs'] = []
            with self.assertRaisesRegex(ValueError, 'exactly both'):
                C.verify_outer_logs(outer, root, C.fp)

    def test_wrong_outer_log_path_and_false_source_declaration_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary)
            for name in ('launcher.stdout.raw', 'launcher.stderr.raw', 'other.raw'):
                (root / name).write_text('ordinary CPU fixture only\n')
            outer = {'launcher_logs': [C.fp(root / 'other.raw'), C.fp(root / 'launcher.stderr.raw')]}
            with self.assertRaises(ValueError):
                C.verify_outer_logs(outer, root, C.fp)
            outer = {'launcher_logs': [C.fp(root / name) for name in ('launcher.stdout.raw', 'launcher.stderr.raw')], 'sources_unchanged': False}
            with self.assertRaisesRegex(ValueError, 'unchanged'):
                C.verify_outer_logs(outer, root, C.fp)

    def test_copied_verifier_returns_same_canonical_identity(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            path = Path(temporary) / 'copied_control.py'
            shutil.copyfile(HERE / 'native58_crossboot_control.py', path)
            spec = importlib.util.spec_from_file_location('copied_actual_parent_cpu_control', path)
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            seen = []
            def keep(path):
                row = C.fp(path); seen.append(row); return row
            self.assertEqual(loaded.canonical_verifier(keep), C.canonical_verifier(C.fp))
            self.assertIn(str(path), [x['path'] for x in seen])
            path.write_text(path.read_text() + '\n# changed CPU fixture copy\n')
            with self.assertRaisesRegex(ValueError, 'copied verifier differs'):
                loaded.canonical_verifier(C.fp)

    def test_running_actual_chain_refuses_without_future_wait_or_output(self):
        # This is a real read-only negative observation of the existing chain;
        # if it has ended by the time controls are rerun, use an empty fresh
        # CPU fixture path. Neither branch can produce an acceptance report.
        actual = HERE / 'student-native58-crossboot-host-01/original-parent/process-exit.json'
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            missing = Path(temporary) / 'original-parent/process-exit.json'
            target = missing if actual.exists() else actual
            with patch('subprocess.Popen', side_effect=AssertionError('No process allowed')), patch('subprocess.run', side_effect=AssertionError('No process allowed')):
                with self.assertRaises(FileNotFoundError):
                    C.verify_actual_parent(HERE, target, '0' * 64)

    def test_explicit_exit_sha_refuses_before_contract_import(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary) / 'original-parent'; root.mkdir()
            path = root / 'process-exit.json'; path.write_text('{"scope":"synthetic ordinary CPU fixture"}')
            with patch.object(C.importlib.util, 'spec_from_file_location', side_effect=AssertionError('No gate import allowed')):
                with self.assertRaisesRegex(ValueError, 'exit SHA differs'):
                    C.verify_actual_parent(HERE, path, '0' * 64)

    def test_original_science_and_complete_decoder_ast_unchanged(self):
        old = (HERE / 'review_native58.py').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), 'cb3039b3074611025972f762c1c4fc538555fd5fe7a003f23ed4604c34cbf278')
        def verify_body(path):
            module = ast.parse(path.read_text())
            return next(x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == 'verify').body
        original = verify_body(HERE / 'review_native58.py')
        new = verify_body(HERE / 'review_native58_crossboot.py')
        def assigned(node, name):
            return isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == name for x in node.targets)
        def section(body, start, end):
            a = next(i for i, x in enumerate(body) if start(x))
            b = next(i for i, x in enumerate(body[a:], a) if end(x))
            return ast.dump(ast.Module(body=body[a:b], type_ignores=[]), include_attributes=False)
        # This entire block contains all case/model/pose/worker/map/trajectory
        # checks and every fresh full58 CPU decode including decoder isolation.
        self.assertEqual(section(original, lambda x: assigned(x, 'terminal'), lambda x: assigned(x, 'report')),
                         section(new, lambda x: assigned(x, 'terminal'), lambda x: assigned(x, 'report')))
        self.assertEqual(section(original, lambda x: isinstance(x, ast.FunctionDef) and x.name == 'cpu_inspect', lambda x: assigned(x, 'waited')),
                         section(new, lambda x: isinstance(x, ast.FunctionDef) and x.name == 'cpu_inspect', lambda x: assigned(x, 'parent_module_path')))
        old_report = copy.deepcopy(next(x for x in original if assigned(x, 'report')))
        new_report = copy.deepcopy(next(x for x in new if assigned(x, 'report')))
        for index in reversed(range(len(new_report.value.keys))):
            if isinstance(new_report.value.keys[index], ast.Constant) and new_report.value.keys[index].value in ('host_control', 'control_revision'):
                del new_report.value.keys[index]; del new_report.value.values[index]
        self.assertEqual(ast.dump(old_report, include_attributes=False), ast.dump(new_report, include_attributes=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
