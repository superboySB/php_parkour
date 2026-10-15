#!/usr/bin/env python3
"""Synthetic ordinary-CPU admission controls, never future scientific evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path('/home/dzp/projects/php_parkour')
HERE = ROOT / 'outputs/research/final-student-reference629-crossboot-preparation-02'
OLD = ROOT / 'outputs/research/final-student-reference629-preparation-01'
sys.dont_write_bytecode = True


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class AdmissionControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic629-crossboot-', dir=ROOT / 'outputs/research/reproduction-20261015/local-checks')
        self.root = Path(self.temp.name)
        self.previous_support = sys.modules.get('support')
        self.support = module(HERE / 'support.py', '_synthetic629_support')
        sys.modules['support'] = self.support
        self.gate = module(HERE / 'admission.py', '_synthetic629_admission')
        self.base = self.root / 'native58'
        self.base.mkdir()
        self.transfer = self.root / 'transfer'
        self.transfer.mkdir()
        self.exit = self.root / 'process-exit.json'
        self.save(self.exit, {'synthetic_fixture': True, 'actual_wait_returncode': 0,
                              'argv': ['truthful-synthetic-e238-wrapper-argv']})
        self.review = self.root / 'independent-review.json'
        self.control = {'synthetic_fixture': True, 'mode': 'explicit_crossboot_native58_single_host_function_override',
                        'actual_parent_exit': self.support.fp(self.exit)}
        local_here = self.root / 'reader-controls'
        local_here.mkdir()
        self.save(local_here / 'native58_resource_wait_control.py', {'synthetic_reader_placeholder': True})
        self.gate.HERE = local_here
        self.reader_calls = []
        self.reader_error = None
        self.origin = {'status': 'ready', 'destination': str(self.transfer), 'origin_files': [], 'models': []}
        for kind in self.gate.KINDS:
            for name in ('student.onnx', 'depth_backbone.onnx'):
                f = self.base / 'inputs' / kind / 'assets/student' / name
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(('synthetic-model-' + kind + name).encode())
                self.origin['models'].append(dict(self.support.fp(f), kind=kind))
        self.poses = {}
        self.phases = [{'id': 'synthetic-' + kind, 'cases': 29} for kind in self.gate.KINDS]
        self.plan = {'synthetic_fixture': True, 'output': str(self.base), 'image_id': self.gate.IMAGE,
                     'gpu_uuid': self.gate.GPU, 'origin_transfer': self.origin, 'phases': self.phases,
                     'expected_counts': {'policies': 2, 'cases': 58, 'worker_exit0_empty_groups': 116,
                                         'exact_host_maps': 116, 'full_mp4_decodes': 58, 'cpu_ort_cases': 60}}
        self.save(self.base / 'freeze-manifest.json', {'files': []})
        self.plan['freeze_manifest_sha256'] = self.support.fp(self.base / 'freeze-manifest.json')['sha256']
        self.plan['plan_sha256'] = self.support.identity(self.plan)
        self.save(self.base / 'host-plan.json', self.plan)
        stages = []
        for phase in self.phases:
            post = self.base / 'phases' / phase['id'] / 'cpu-final/summary.json'
            self.save(post, {'synthetic_fixture': True, 'status': 'passed', 'case_count': 29,
                            'worker_exit0_empty_groups': 58, 'full_decoded_mp4_count': 29,
                            'cases': [{'worker_exit0_empty_groups': 2, 'quality_verified': False,
                                       'video_full_decodes': [{'synthetic_fixture': True}], 'files': []} for _ in range(29)]})
            stages.append({'id': phase['id'], 'status': 'completed', 'driver_returncode': 0,
                           'observer_returncode': 0, 'driver_returncode_after_stop': 0,
                           'owned_gpu_container_stop': {'running_after_stop': False},
                           'worker_exit0_empty_groups': 58, 'full_decoded_mp4_count': 29,
                           'cpu_final': self.support.fp(post),
                           'host_maps': [{'phase': phase['id'], 'role': 'simulator' if i % 2 else 'inference',
                                          'mapping': {'host_tid': 1000 + i, 'container_tid': 10 + i,
                                                      'nspid': [1000 + i, 10 + i]}} for i in range(58)]})
        self.save(self.base / 'host/launch-receipt.json', {'synthetic_fixture': True, 'status': 'completed',
            'plan_sha256': self.plan['plan_sha256'], 'cases': 58, 'worker_exit0_empty_groups': 116,
            'exact_host_maps': 116, 'full_decoded_mp4_count': 58, 'quality_verified': False, 'phases': stages})
        for kind in self.gate.KINDS:
            where = self.base / 'host' / ('cpu-' + kind)
            self.save(where / 'launch.json', {'synthetic_fixture': True, 'status': 'passed', 'mode': 'prepare',
                'kind': kind, 'returncode': 0, 'container_exit_code': 0, 'owned_container_stop': {'running_after_stop': False}})
            self.save(where / 'summary.json', {'synthetic_fixture': True, 'status': 'passed', 'ort_cases': 30,
                'directions_cases': 12, 'scene_cases': 17, 'image_id': self.gate.IMAGE,
                'source_sha256': '855d56494c662cbfcd19a96043b6f0baaa49a093f52c47b46a9005657e46bb0f'})
            pose = {'status': 'passed', 'native_joint_names': ['synthetic-joint-' + str(i) for i in range(29)],
                    'max_default_pose_absolute_error': 0.0}
            self.poses[kind] = pose
            models = [dict(self.support.fp(self.base / 'inputs' / kind / 'assets/student' / name),
                           path='/data/assets/student/' + name) for name in ('student.onnx', 'depth_backbone.onnx')]
            self.save(where / 'onnx.json', {'synthetic_fixture': True, 'status': 'passed', 'cases': [{}] * 30,
                                         'models': models, 'native_default_pose_compatibility': pose})
        self.save_review()
        self.args = SimpleNamespace(transfer=self.transfer, native58_base=self.base, native58_exit=self.exit,
            native58_exit_sha256=self.support.fp(self.exit)['sha256'], native58_review=self.review,
            native58_review_sha256=self.support.fp(self.review)['sha256'])

        def verify_parent(base, exit_path, sha, retain=None):
            self.reader_calls.append((base, exit_path, sha))
            if self.reader_error:
                raise ValueError(self.reader_error)
            return {'status': 'synthetic_only_protocol_pass', 'actual_parent_wait': self.support.fp(self.exit),
                    'host_control': self.control, 'bound_files': [self.support.fp(self.exit)]}

        def loader(path, name):
            if path.name == 'common.py':
                return SimpleNamespace(transfer=lambda workspace, path: self.origin)
            if path.name == 'native58_resource_wait_control.py':
                return SimpleNamespace(verify_actual_parent=verify_parent)
            raise AssertionError('Unexpected module load: ' + str(path))

        self.gate.load = loader

    def tearDown(self):
        if self.previous_support is None:
            sys.modules.pop('support', None)
        else:
            sys.modules['support'] = self.previous_support
        self.temp.cleanup()

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')

    def save_review(self, control=None):
        critical = ['host/launch-receipt.json', 'host/cpu-pure/onnx.json', 'host/cpu-finetune/onnx.json',
                    *['phases/' + x['id'] + '/cpu-final/summary.json' for x in self.phases]]
        self.save(self.review, {'synthetic_fixture': True, 'status': 'passed_readonly_native58_postexecution_review',
             'must_fix': [], 'native58_plan_sha256': self.plan['plan_sha256'],
             'actual_parent_wait': self.support.fp(self.exit), 'image_id': self.gate.IMAGE,
             'models': self.origin['models'], 'poses': self.poses,
             'host_control': self.control if control is None else control,
             'evidence_fingerprints': [self.support.fp(self.base / p) for p in critical]})

    def test_positive_truthful_new_schema_and_bound_files(self):
        result = self.gate.admission(self.args)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['host_control'], self.control)
        self.assertIn(self.support.fp(self.exit), result['bound_files'])
        self.assertEqual(self.reader_calls, [(self.base, self.exit, self.args.native58_exit_sha256)])
        self.assertFalse(result['native_started'])
        self.assertFalse(result['gpu_started'])

    def test_missing_explicit_inputs_wait_without_reader(self):
        result = self.gate.admission(SimpleNamespace())
        self.assertEqual(result['status'], 'waiting')
        self.assertEqual(self.reader_calls, [])

    def test_missing_actual_review_wait(self):
        self.review.unlink()
        self.assertEqual(self.gate.admission(self.args)['status'], 'waiting')
        self.assertEqual(self.reader_calls, [])

    def test_bad_parent_sha_rejected_before_reader(self):
        self.args.native58_exit_sha256 = '0' * 64
        with self.assertRaisesRegex(ValueError, 'parent wait SHA'):
            self.gate.admission(self.args)
        self.assertEqual(self.reader_calls, [])

    def test_shared_parent_refusal_propagates(self):
        self.reader_error = 'synthetic shared verifier rejected legacy/fake parent'
        with self.assertRaisesRegex(ValueError, 'rejected legacy/fake parent'):
            self.gate.admission(self.args)

    def test_review_from_other_control_rejected(self):
        self.save_review({'synthetic_fixture': True, 'wrong_control': True})
        self.args.native58_review_sha256 = self.support.fp(self.review)['sha256']
        with self.assertRaisesRegex(ValueError, 'Independent58 postexecution'):
            self.gate.admission(self.args)

    def test_cpu_pair_mismatch_rejected(self):
        path = self.base / 'host/cpu-pure/onnx.json'
        doc = self.support.read(path)
        doc['models'][0]['sha256'] = '0' * 64
        self.save(path, doc)
        with self.assertRaisesRegex(ValueError, 'ORT used another pair'):
            self.gate.admission(self.args)

    def test_pose_failure_rejected(self):
        path = self.base / 'host/cpu-pure/onnx.json'
        doc = self.support.read(path)
        doc['native_default_pose_compatibility']['max_default_pose_absolute_error'] = .1
        self.save(path, doc)
        with self.assertRaisesRegex(ValueError, 'deployment pose mismatch'):
            self.gate.admission(self.args)

    def test_native_counters_failure_rejected(self):
        path = self.base / 'host/launch-receipt.json'
        doc = self.support.read(path)
        doc['worker_exit0_empty_groups'] = 115
        self.save(path, doc)
        with self.assertRaisesRegex(ValueError, 'terminal counters differ'):
            self.gate.admission(self.args)

    def test_scientific_original35_unchanged_except_host_admission_and_resource_runner(self):
        manifest = json.loads((OLD / 'preparation-manifest.json').read_bytes())
        for row in manifest['files']:
            if row['path'] in ('admission.py','native_runner.py'):
                continue
            raw = (HERE / row['path']).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (row['bytes'], row['sha256']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
