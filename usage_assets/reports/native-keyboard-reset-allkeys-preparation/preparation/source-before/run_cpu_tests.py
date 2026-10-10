"""Writes honest CPU-only unittest/JUnit evidence; no GUI/native acceptance."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
import unittest
import xml.etree.ElementTree as ET
import test_runner
from common import fingerprint, identity, write


class Result(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test); self.started = time.monotonic()
    def record(self, test, status, text=''):
        self.entries.append({'test': str(test), 'status': status, 'seconds': time.monotonic()-self.started, 'detail': text})
    def addSuccess(self, test):
        super().addSuccess(test); self.record(test, 'passed')
    def addFailure(self, test, error):
        super().addFailure(test, error); self.record(test, 'failed', self._exc_info_to_string(error, test))
    def addError(self, test, error):
        super().addError(test, error); self.record(test, 'error', self._exc_info_to_string(error, test))
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.entries = []


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_runner)
    with (args.output / 'tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(suite)
    root = ET.Element('testsuite', name='isolated_gui_operator_CPU_only', tests=str(result.testsRun),
                      failures=str(len(result.failures)), errors=str(len(result.errors)))
    for entry in result.entries:
        case = ET.SubElement(root, 'testcase', name=entry['test'], time=f"{entry['seconds']:.6f}")
        if entry['status'] != 'passed': ET.SubElement(case, entry['status']).text = entry['detail']
    ET.ElementTree(root).write(args.output / 'tests.xml', encoding='utf-8', xml_declaration=True)
    sources = [{'path': p.name, **fingerprint(p)} for p in sorted(Path(__file__).parent.glob('*.py'))]
    write(args.output / 'report.json', {'scope': 'runc/network-none/noGPU Docker CPU tests; ordinary stdlib real PTY; NPZ synthetic fixture',
        'native_gui_acceptance': False, 'native_workers_started': False, 'xserver_started': False,
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'sources': sources, 'sources_identity_sha256': identity(sources), 'entries': result.entries,
        'ordinary_cpu_pty_observations': test_runner.CPU_OBSERVATIONS})
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
