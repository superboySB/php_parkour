#!/usr/bin/env python3
"""Ordinary CPU refusal controls; never connects to TensorBoard or Chrome."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('synthetic_tb_browser_refusal_controls', HERE / 'tb_final_students_browser_v3.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-tb-browser-controls-', dir=HERE)
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.baseline = HERE / 'tb-final-student-baseline.json'
        self.report = self.directory / 'synthetic-http-check.json'
        self.output = self.directory / 'not-created'

    def args(self, baseline_sha=None):
        return argparse.Namespace(baseline=self.baseline, baseline_sha256=baseline_sha or browser.fp(self.baseline)['sha256'],
            http_check=self.report, http_check_sha256=browser.fp(self.report)['sha256'] if self.report.exists() else '0' * 64,
            output=self.output)

    def refuse_without_browser(self, args, error, message=None):
        with patch.object(browser.subprocess, 'Popen') as launch, patch.object(browser, 'urlopen') as http:
            with self.assertRaisesRegex(error, message or '.*'):
                browser.run(args)
            launch.assert_not_called()
            http.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_actual_baseline_missing_future_http_report_refuses(self):
        self.refuse_without_browser(self.args(), FileNotFoundError)

    def test_wrong_explicit_baseline_sha_refuses(self):
        self.report.write_text('{"synthetic_control_only":true}')
        self.refuse_without_browser(self.args('0' * 64), ValueError, 'Explicit actual baseline')

    def test_failed_or_wrong_endpoint_http_report_refuses(self):
        for status, url in [('failed', 'http://127.0.0.1:6007'), ('passed', 'http://127.0.0.1:6006')]:
            self.report.write_text(json.dumps({'synthetic_control_only': True, 'status': status, 'url': url,
                'baseline': browser.fp(self.baseline)}))
            self.refuse_without_browser(self.args(), ValueError, 'Actual passed local6007 check')


if __name__ == '__main__':
    unittest.main(verbosity=2)
