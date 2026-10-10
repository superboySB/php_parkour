"""Independent CPU fixture only. Does not touch any real source/run evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys

import pytest

ROOT = Path('/workspace/php_parkour')
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('publisher_fixture', ROOT / 'tests/test_publish_full_scene_matrix.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

with tempfile.TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as monkeypatch:
    f = fixture.fixture.__wrapped__(Path(directory), monkeypatch)
    base = fixture.add_historical_attempt(f, sealed=True)
    target = base / 'video/fixture.mp4'
    seal = json.loads((base / 'case-evidence.json').read_text())
    sealed = next(record['sha256'] for record in seal['files'] if Path(record['path']) == target)
    original_check = fixture.pub.check_record
    injections = []

    def check_record(record):
        result = original_check(record)
        if result == target and not injections:
            injections.append({'stage': 'Immediately after original seal SHA verified, before archive fingerprints',
                               'sealed_sha256': sealed})
            target.write_bytes(b'Changed between sealed validation and archive re-fingerprinting: CPU fixture only')
        return result

    monkeypatch.setattr(fixture.pub, 'check_record', check_record)
    result = fixture.pub.publish(f.args)
    copied = f.args.output / 'cases/random_locomotion/config-0000/attempt-0001/video/fixture.mp4'
    report = {'scope': 'Synthetic CPU fixture only; no real media, simulation, DDS or evidence mutation',
              'publication_status': result['status'], 'injections': injections,
              'original_sealed_sha256': sealed, 'copied_sha256': fixture.pub.digest(copied),
              'copied_matches_original_seal': fixture.pub.digest(copied) == sealed,
              'copied_bytes_equal_tampered_fixture': copied.read_bytes() == target.read_bytes(),
              'source_script': str(ROOT / 'scripts/research/publish_full_scene_matrix.py'),
              'source_sha256': fixture.pub.digest(ROOT / 'scripts/research/publish_full_scene_matrix.py')}
    assert report['publication_status'] == 'completed_publication'
    assert report['copied_matches_original_seal'] is False and report['copied_bytes_equal_tampered_fixture'] is True
    (ROOT / 'outputs/research/publisher-schema3-independent-review/historical-copy-race.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
