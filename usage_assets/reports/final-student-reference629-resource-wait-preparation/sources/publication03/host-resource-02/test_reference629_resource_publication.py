#!/usr/bin/env python3
"""Synthetic/readonly ordinary CPU controls for versioned publication pins."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path('/home/dzp/projects/php_parkour')
PREP = ROOT / 'outputs/research/final-student-reference629-crossboot-preparation-02'
PUB = ROOT / 'outputs/research/final-student-reference629-crossboot-publication-preparation-02'
OLD = ROOT / 'outputs/research/final-student-reference629-publication-preparation-01'
PREP_SHA = '9f32c251bcb25c3ed1fbe999bd49c8081a712ce0d6985a99f8ed6820c661af2b'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicationControls(unittest.TestCase):
    def setUp(self):
        self.gate = load(PUB / 'admission.py', '_tested_crossboot629_publication')
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic629-publication-', dir=ROOT / 'outputs/research/reproduction-20261015/local-checks')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, path, value):
        path.write_text(json.dumps(value, indent=2) + '\n')
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_explicit_v2_upstream_path_sha_and_count(self):
        self.assertEqual(self.gate.PREPARATION, PREP)
        self.assertEqual(self.gate.PREPARATION_SHA, PREP_SHA)
        self.assertEqual(hashlib.sha256((PREP / 'preparation-manifest.json').read_bytes()).hexdigest(), PREP_SHA)
        self.assertEqual(len(json.loads((PREP / 'preparation-manifest.json').read_bytes())['files']), 85)

    def test_unchanged_original_publisher_restore_and51dependencies(self):
        rows = json.loads((OLD / 'preparation-manifest.json').read_bytes())['files']
        count = 0
        for row in rows:
            if row['path'] == 'admission.py':
                continue
            data = (PUB / row['path']).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (row['bytes'], row['sha256']))
            count += 1
        self.assertEqual(count, 51)

    def test_actual_readonly_module_closure_missing_future_waits(self):
        evidence = self.gate.Evidence()
        with self.gate.reviewed_modules(evidence, self.gate.PUBLISHER) as (support, prior, publisher):
            answer = prior.admission(SimpleNamespace())
            self.assertEqual(answer['status'], 'waiting')
            self.assertFalse(answer['native_started'])
            self.assertFalse(answer['gpu_started'])
            self.assertEqual(support.HERE, PREP)
            self.assertTrue(callable(publisher._publish))
        evidence.recheck()

    def synthetic_parent(self):
        # Read actual ordinary unit-process identity but explicitly synthesize
        # protocol records; these are not a scientific execution receipt.
        stat = Path('/proc/self/stat').read_text()
        parent = os.getppid()
        parent_stat = Path('/proc', str(parent), 'stat').read_text()
        contract = self.root / 'contract.json'
        contract_sha = self.save(contract, {'synthetic_fixture': True})
        argv = ['/usr/bin/python3', '-B', str(PREP / 'adapter.py'), 'execute',
                '--preparation-sha256', PREP_SHA, '--contract', str(contract),
                '--contract-sha256', contract_sha, '--root-authorized-start']
        start = {'synthetic_fixture': True, 'argv': argv,
                 'helper_sha256': hashlib.sha256((PREP / 'adapter.py').read_bytes()).hexdigest(),
                 'launcher_sha256': self.gate.LAUNCHER_SHA, 'pid': os.getpid(), 'stat': stat,
                 'parent_pid': parent, 'parent_stat': parent_stat,
                 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        end = dict(start, actual_wait_returncode=0, pending_signals=[], finished_utc='2026-10-15T00:00:00+00:00')
        start_path, end_path = self.root / 'process-start.json', self.root / 'process-exit.json'
        start_sha, end_sha = self.save(start_path, start), self.save(end_path, end)
        for name in ('stdout.raw', 'stderr.raw'):
            (self.root / name).write_text('synthetic ordinary CPU protocol only\n')
        return start_path, start_sha, end_path, end_sha, contract, contract_sha

    def test_truthful_new_adapter_argv_actual_wait_schema_protocol(self):
        args = self.synthetic_parent()
        start, process = self.gate.outer_parent(self.gate.Evidence(), *args)
        self.assertEqual(start['pid'], process['pid'])
        self.assertEqual(start['argv'][2], str(PREP / 'adapter.py'))

    def test_old_adapter_argv_is_rejected(self):
        args = list(self.synthetic_parent())
        start = json.loads(args[0].read_bytes())
        end = json.loads(args[2].read_bytes())
        start['argv'][2] = end['argv'][2] = str(ROOT / 'outputs/research/final-student-reference629-preparation-01/adapter.py')
        args[1], args[3] = self.save(args[0], start), self.save(args[2], end)
        with self.assertRaisesRegex(ValueError, 'outer launcher/start/child.wait0/argv binding'):
            self.gate.outer_parent(self.gate.Evidence(), *args)

    def test_nonzero_or_bool_parent_wait_rejected(self):
        for code in (1, True, None):
            with self.subTest(code=code):
                args = list(self.synthetic_parent())
                end = json.loads(args[2].read_bytes())
                end['actual_wait_returncode'] = code
                args[3] = self.save(args[2], end)
                with self.assertRaisesRegex(ValueError, 'outer launcher/start/child.wait0/argv binding'):
                    self.gate.outer_parent(self.gate.Evidence(), *args)

    def test_missing_dependency_refused_before_module_execution(self):
        clone = self.root / 'prep-copy'
        shutil.copytree(PREP, clone)
        (clone / 'native58_resource_wait_control.py').unlink()
        self.gate.PREPARATION = clone
        with self.assertRaises((ValueError, FileNotFoundError)):
            with self.gate.reviewed_modules(self.gate.Evidence(), self.gate.PUBLISHER):
                self.fail('Missing dependency must never enter reviewed modules')

    def test_wrong_precise_upstream_count_refused(self):
        clone = self.root / 'prep-copy'
        shutil.copytree(PREP, clone)
        manifest = json.loads((clone / 'preparation-manifest.json').read_bytes())
        manifest['files'].pop()
        self.gate.PREPARATION = clone
        self.gate.PREPARATION_SHA = self.save(clone / 'preparation-manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'preparation85'):
            with self.gate.reviewed_modules(self.gate.Evidence(), self.gate.PUBLISHER):
                self.fail('Wrong exact inventory count must never enter reviewed modules')


if __name__ == '__main__':
    unittest.main(verbosity=2)
