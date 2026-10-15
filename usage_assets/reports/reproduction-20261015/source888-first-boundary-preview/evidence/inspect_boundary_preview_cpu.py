#!/usr/bin/env python3
"""Decode three originals and extract a contact sheet for one completed source."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/php_parkour')
WORK = ROOT / 'outputs/research/reproduction-20261015'
RAW = WORK / 'cloud888-first-boundary-preview-raw-01/raw-case'
OUT = WORK / 'local-checks/first-boundary-inspection-01'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(argv, name):
    p = subprocess.run(argv, capture_output=True)
    (OUT / (name + '.stdout.raw')).write_bytes(p.stdout)
    (OUT / (name + '.stderr.raw')).write_bytes(p.stderr)
    rows.append({'argv': argv, 'actual_wait_returncode': p.returncode,
                 'stdout_sha256': sha(OUT / (name + '.stdout.raw')),
                 'stderr_sha256': sha(OUT / (name + '.stderr.raw'))})
    require(p.returncode == 0, name + ' failed')
    return p.stdout


require(Path('/.dockerenv').exists() and not any(Path('/dev').glob('nvidia[0-9]*')), 'Existing CPU-only Docker required')
OUT.mkdir(exist_ok=False)
rows = []
acq = json.loads((RAW.parent / 'inventory.json').read_bytes())
inventory = acq['local_inventory']
require(acq['stable'] and acq['before_inventory'] == acq['after_inventory'] == inventory, 'Original acquisition inventory differs')
files = [r for r in inventory if r['type'] == 'file']
require({p.relative_to(RAW).as_posix() for p in RAW.rglob('*') if p.is_file()} == {r['relative'] for r in files}, 'Raw case file set differs')
for r in files:
    p = RAW / r['relative']
    require(p.stat().st_size == r['bytes'] and sha(p) == r['sha256'], 'Raw original fingerprint differs')
helper = WORK / 'cloud888-publication-preparation-01/cloud888_report.py'
require(sha(helper) == '236f16be436d1f15e31d3db4fea6e2c57a5f5d7241a1075503f186efada28f55', 'Original reviewed completion helper changed')
spec = importlib.util.spec_from_file_location('boundary_helper', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
quality = json.loads((RAW / 'quality.json').read_bytes())
attempt = json.loads((RAW / 'posttrain-attempt.json').read_bytes())
trajectory = [json.loads(line) for line in (RAW / 'trajectory.jsonl').read_text().splitlines()]
completion = module.completion(quality, trajectory)
require(completion['source_boundary_completed'] and attempt['status'] == 'execution_passed' and attempt['returncode'] == 0, 'Actual completed first source required')
videos = []
for i, p in enumerate(sorted(RAW.rglob('*.mp4'))):
    probe = json.loads(call(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
        'stream=nb_read_frames,width,height,r_frame_rate:format=duration', '-of', 'json', str(p)], f'probe-{i}'))
    output = call(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-hwaccel', 'none', '-i', str(p),
        '-map', '0:v:0', '-an', '-sn', '-dn', '-progress', 'pipe:1', '-nostats', '-f', 'null', '-'], f'decode-{i}').decode()
    progress = [int(line.split('=', 1)[1]) for line in output.splitlines() if line.startswith('frame=')]
    frames = int(probe['streams'][0]['nb_read_frames'])
    require(frames > 0 and progress and progress[-1] == frames and 'progress=end' in output, 'Positive full-frame decode mismatch')
    videos.append({'path': str(p), 'relative': p.relative_to(RAW).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size,
                   'duration_seconds': float(probe['format']['duration']), 'decoded_frames': frames, 'metadata': probe})
require(len(videos) == 3, 'Retain all three original clips')
chosen = max(videos, key=lambda r: r['duration_seconds'])
call(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-i', chosen['path'], '-vf',
    'fps=1,scale=320:180,tile=5x2', '-frames:v', '1', '-threads', '1', '-n', str(OUT / 'contact-sheet.png')], 'contact-sheet')
call(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-ss', '5', '-i', chosen['path'], '-vf',
    'scale=640:-2', '-frames:v', '1', '-threads', '1', '-n', str(OUT / 'poster.png')], 'poster')
for r in files:
    require(sha(RAW / r['relative']) == r['sha256'], 'Original changed during CPU inspection')
(OUT / 'inspection.json').write_text(json.dumps({'status': 'three_original_mp4_full_decodes_passed_contact_sheet_extracted',
    'reviewer_source_sha256': sha(Path(__file__)), 'completion': completion, 'videos': videos, 'chosen': chosen,
    'commands': rows, 'visual_review_performed': False, 'scope': 'Single source only; not888 terminal or obstacle-course success.'}, indent=2) + '\n')
print(json.dumps({'status': 'three_original_full_decodes_passed', 'decoded_frames': sum(r['decoded_frames'] for r in videos), 'chosen': chosen['relative']}))
