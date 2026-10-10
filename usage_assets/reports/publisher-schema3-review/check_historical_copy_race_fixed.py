"""Reuse original synthetic race injection; current publisher must refuse it."""
import hashlib
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ROOT = Path('/workspace/php_parkour')
try:
    runpy.run_path(str(HERE / 'check_historical_copy_race.py'))
except ValueError as error:
    assert 'changed before copy' in str(error), str(error)
    result = {'status': 'passed', 'scope': 'Original synthetic CPU fixture injection; no real evidence/media/DDS/GPU',
              'publication_refused': True, 'error': str(error),
              'publisher_sha256': hashlib.sha256((ROOT / 'scripts/research/publish_full_scene_matrix.py').read_bytes()).hexdigest(),
              'original_counterexample_sha256': hashlib.sha256((HERE / 'check_historical_copy_race.py').read_bytes()).hexdigest()}
    (HERE / 'historical-copy-race-fixed.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
else:
    raise AssertionError('Current publisher unexpectedly accepted changed historical sealed bytes')
