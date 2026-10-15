#!/usr/bin/env python3
"""Derive the explicitly selected 8s GIF in the existing CPU-only container."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/php_parkour')
INPUT = ROOT / 'outputs/research/reproduction-20261015/cloud888-first-boundary-preview-raw-01/raw-case/native/PHP-research/20261015_051005-teacher-locomotion-wholebodytrackingmanager/renderings_training/episode_4_1792041041.mp4'
OUT = ROOT / 'outputs/research/reproduction-20261015/local-checks/first-boundary-gif-01'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert Path('/.dockerenv').exists() and not any(Path('/dev').glob('nvidia[0-9]*'))
    assert sha(INPUT) == 'bedc51955e5f861ad1ceef3babef6d3862940c192352bdb862b754eb973a5f95'
    OUT.mkdir(exist_ok=False)
    commands = []

    def run(argv):
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        p = subprocess.run(argv, capture_output=True)
        index = len(commands)
        for label, raw in [('stdout', p.stdout), ('stderr', p.stderr)]:
            (OUT / f'{index}.{label}.raw').write_bytes(raw)
        commands.append({'argv': argv, 'started_utc': start,
                         'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         'actual_wait_returncode': p.returncode,
                         'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(p.stderr).hexdigest()})
        (OUT / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert p.returncode == 0, p.stderr.decode()
        return p

    gif = OUT / 'source-boundary-preview.gif'
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-hwaccel', 'none',
         '-ss', '1.76', '-i', str(INPUT), '-t', '8', '-an', '-sn', '-dn',
         '-filter_complex', 'fps=8,scale=480:270:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a',
         '-filter_complex_threads', '1', '-threads', '1', '-loop', '0', '-n', str(gif)])
    probe = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                 '-show_entries', 'stream=nb_read_frames,width,height,r_frame_rate:format=duration',
                 '-of', 'json', str(gif)])
    metadata = json.loads(probe.stdout)
    assert metadata['streams'][0]['width'] == 480 and metadata['streams'][0]['height'] == 270
    assert int(metadata['streams'][0]['nb_read_frames']) == 64
    assert 7.9 <= float(metadata['format']['duration']) <= 8.1
    decoded = run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-hwaccel', 'none',
                   '-i', str(gif), '-map', '0:v:0', '-an', '-sn', '-dn', '-progress', 'pipe:1',
                   '-nostats', '-f', 'null', '-'])
    assert b'progress=end' in decoded.stdout and b'frame=64' in decoded.stdout
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-i', str(gif),
         '-vf', 'fps=0.5,scale=480:270,tile=4x1', '-frames:v', '1', '-threads', '1',
         '-n', str(OUT / 'gif-contact-sheet.png')])
    assert sha(INPUT) == 'bedc51955e5f861ad1ceef3babef6d3862940c192352bdb862b754eb973a5f95'
    report = {'status': 'passed_actual_cpu_gif_derivation_full_decode',
              'input': {'path': str(INPUT), 'sha256': sha(INPUT), 'bytes': INPUT.stat().st_size},
              'gif': {'path': str(gif), 'sha256': sha(gif), 'bytes': gif.stat().st_size,
                      'metadata': metadata, 'start_seconds': 1.76, 'end_seconds_exclusive': 9.76},
              'commands': commands, 'scope': 'Derived preview only; original MP4 preserved. One source boundary, not a complete course or 888 terminal.'}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'gif_sha256': sha(gif), 'frames': 64}))


if __name__ == '__main__':
    main()
