#!/usr/bin/env python3
"""Independently decode all three exact original MP4s; record each real wait."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/php_parkour/outputs/research/reproduction-20261015')
RAW = ROOT / 'cloud888-first-boundary-preview-raw-01/raw-case'
OUT = ROOT / 'local-checks/first-boundary-independent-decode-01'


def main():
    assert Path('/.dockerenv').exists() and not any(Path('/dev').glob('nvidia[0-9]*'))
    OUT.mkdir(exist_ok=False)
    videos = []
    commands = []
    expected = {'39cf962a0cfeba1da4f85b6e8f534ad99ff7b6cc49e4615f495fb7ba8838d494': 1,
                '4f218a441dde0aee45b398994e7c3dae876d14e2a207323967d8604ef395ed46': 1,
                'bedc51955e5f861ad1ceef3babef6d3862940c192352bdb862b754eb973a5f95': 489}

    def call(argv):
        p = subprocess.run(argv, capture_output=True)
        n = len(commands)
        for label, raw in [('stdout', p.stdout), ('stderr', p.stderr)]:
            (OUT / f'{n}.{label}.raw').write_bytes(raw)
        commands.append({'argv': argv, 'actual_wait_returncode': p.returncode,
                         'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(p.stderr).hexdigest()})
        (OUT / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert p.returncode == 0, p.stderr.decode()
        return p

    files = sorted(RAW.rglob('*.mp4'))
    assert len(files) == 3
    for path in files:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest in expected
        probed = call(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                       '-show_entries', 'stream=nb_read_frames,width,height,r_frame_rate:format=duration',
                       '-of', 'json', str(path)])
        metadata = json.loads(probed.stdout)
        frames = int(metadata['streams'][0]['nb_read_frames'])
        assert frames == expected[digest] and frames > 0
        decoded = call(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', '-hwaccel', 'none',
                        '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn', '-progress', 'pipe:1',
                        '-nostats', '-f', 'null', '-'])
        progress = decoded.stdout.decode().splitlines()
        assert 'progress=end' in progress
        assert [int(x.split('=', 1)[1]) for x in progress if x.startswith('frame=')][-1] == frames
        assert path.read_bytes() == data
        videos.append({'relative': path.relative_to(RAW).as_posix(), 'bytes': len(data),
                       'sha256': digest, 'decoded_frames': frames, 'metadata': metadata})
    (OUT / 'report.json').write_text(json.dumps({'status': 'passed_actual_independent_three_original_full_decodes',
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'videos': videos, 'commands': commands, 'total_frames': sum(x['decoded_frames'] for x in videos),
        'scope': 'Independent existing runc/noGPU/networknone CPU container; all three original MP4 bytes unchanged. No native simulation.'}, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'videos': len(videos), 'frames': 491}))


if __name__ == '__main__':
    main()
