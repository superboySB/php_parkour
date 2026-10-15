#!/usr/bin/env python3
"""Actual CPU contact previews from six already sealed native58 videos only."""
import datetime
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT / 'usage_assets/reports/final-student-native58-resource-wait-04'
SEAL_SHA = '8d9d0b733c4450d01a83f2aa84cde1f41b1f76f0cf50319cf884956d0c38a668'
CID = 'b4ac896a486b040c6f1a9f9f27bc738c22ea4d56228962cbf8ceed9c4b491d50'
ORDINALS = (1, 30, 42, 46, 48, 57)


def fp(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path): return json.loads(path.read_bytes())


def command(argv, directory, name):
    paths = {key: directory / (name + '.' + key + '.raw') for key in ('stdout', 'stderr')}
    row = {'argv': argv, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    child = None; stdout = stderr = b''; failure = None
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        row['pid'] = child.pid
        try: row['stat'] = Path('/proc', str(child.pid), 'stat').read_text()
        except FileNotFoundError:
            assert child.poll() is not None
            row['metadata_unavailable_after_actual_exit'] = True
        stdout, stderr = child.communicate(timeout=60)
    except BaseException as error:
        failure = error; row['error'] = type(error).__name__ + ': ' + str(error)
        if child is not None:
            if child.poll() is None: child.kill()
            stdout, stderr = child.communicate(timeout=5)
    row.update(actual_wait_returncode=None if child is None else child.returncode,
               finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    for label, raw in (('stdout', stdout), ('stderr', stderr)):
        with paths[label].open('xb') as stream: stream.write(raw)
        row[label] = fp(paths[label])
    (directory / (name + '.execution.json')).write_text(json.dumps(row, indent=2) + '\n')
    if failure is not None: raise failure
    assert type(child.returncode) is int and child.returncode == 0, row
    return stdout, row


def decoder(directory, name, baseline):
    raw, receipt = command(['docker', 'container', 'inspect', CID], directory, name)
    info = json.loads(raw)[0]
    assert info['Id'] == CID and info['Image'] == baseline['image'] and info['State']['Running'] is True
    assert info['State']['StartedAt'] == baseline['started_at']
    assert info['HostConfig']['Runtime'] == 'runc' and info['HostConfig']['NetworkMode'] == 'none'
    assert not info['HostConfig'].get('DeviceRequests') and not info['HostConfig'].get('Devices') and not info['HostConfig'].get('Privileged')
    assert len(info['Mounts']) == 1
    mount = info['Mounts'][0]
    assert mount['Type'] == 'bind' and mount['Source'] == str(ROOT) and mount['Destination'] == '/workspace/php_parkour' and mount['RW'] is False
    return {'actual_inspect': receipt['stdout'], 'id': CID, 'started_at': info['State']['StartedAt'], 'mounts': info['Mounts']}


def main():
    restore_path = HERE.parent / 'native58-publication-resource-wait-preparation-05/restore.py'
    assert fp(restore_path)['sha256'] == '57be6ed4f884d4d9fbcb747260c39f8343d80cf117a46514d32a39fefa6c2cab'
    spec = importlib.util.spec_from_file_location('sealed_native58_readonly_verifier', restore_path)
    restore = importlib.util.module_from_spec(spec); spec.loader.exec_module(restore)
    restore.verify(PACKAGE, SEAL_SHA); seal_before = fp(PACKAGE / 'evidence-manifest.json')
    review_path = HERE.parent / 'native58-resource-wait-independent-actual-review-04.json'
    assert fp(review_path)['sha256'] == '1b8dc57dc111c00598c4ea4befa61a748eb564b000dc7ece9bed39467525da10'
    baseline = read(review_path)['decoder_container']
    rows = read(PACKAGE / 'cases.json'); summaries = []
    for ordinal in ORDINALS:
        case = rows[ordinal]; assert case['ordinal'] == ordinal
        video = PACKAGE / case['videos'][0]['path']; poster = PACKAGE / case['videos'][0]['thumbnail']
        source_before = fp(video)
        assert source_before['sha256'] == case['videos'][0]['sha256'] and source_before['bytes'] == case['videos'][0]['bytes']
        directory = HERE / ('case-' + str(ordinal).zfill(3)); manifest = directory / 'manifest.json'
        if manifest.exists():
            completed = read(manifest)
            assert completed['status'] == 'actual_cpu_contact_preview_completed' and completed['source_video'] == source_before
            for record in completed['derived_files']: assert fp(Path(record['path'])) == record
            summaries.append(fp(manifest)); continue
        directory.mkdir(exist_ok=False)
        before = decoder(directory, 'decoder-before', baseline)
        native_video = '/workspace/php_parkour/' + video.relative_to(ROOT).as_posix()
        probe, probe_receipt = command(['docker', 'exec', CID, 'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_frames,avg_frame_rate,width,height,duration', '-of', 'json', native_video], directory, 'ffprobe')
        stream = json.loads(probe)['streams'][0]; count = int(stream['nb_frames']); fps = Fraction(stream['avg_frame_rate'])
        assert count >= 8 and fps > 0
        indices = [round(i * (count - 1) / 7) for i in range(8)]; assert len(set(indices)) == 8
        select = '+'.join('eq(n\\,' + str(index) + ')' for index in indices)
        raw, contact_receipt = command(['docker', 'exec', CID, 'ffmpeg', '-nostdin', '-hide_banner', '-v', 'info',
            '-nostats', '-xerror', '-threads', '1', '-i', native_video, '-map', '0:v:0', '-vf',
            'select=' + select + ',showinfo,scale=480:-2,tile=4x2', '-vsync', '0', '-frames:v', '1',
            '-c:v', 'png', '-threads', '1', '-f', 'image2pipe', '-progress', 'pipe:2', 'pipe:1'], directory, 'ffmpeg-contact')
        stderr = Path(contact_receipt['stderr']['path']).read_text()
        assert re.findall(r'\[Parsed_showinfo_[^\]]*\]\s+n:\s*(\d+)', stderr) == [str(i) for i in range(8)]
        assert 'progress=end' in stderr and raw[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', raw[16:24]) == (1920, 540)
        contact = directory / 'contact-8frames.png'; contact.write_bytes(raw)
        copied_poster = directory / 'original-poster.png'; shutil.copy2(poster, copied_poster)
        assert fp(copied_poster)['sha256'] == fp(poster)['sha256']
        after = decoder(directory, 'decoder-after', baseline)
        assert before['id'] == after['id'] and before['started_at'] == after['started_at']
        assert fp(video) == source_before
        report = {'schema_version': 1, 'status': 'actual_cpu_contact_preview_completed', 'ordinal': ordinal,
            'phase': case['phase'], 'case_id': case['case_id'], 'sealed_case': case,
            'main_publication_seal': seal_before, 'actual_review': fp(review_path), 'source_video': source_before,
            'source_original_poster': fp(poster), 'total_video_frames': count, 'video_average_fps': str(fps),
            'selected_frame_indices': indices, 'selected_video_seconds': [float(Fraction(index, 1) / fps) for index in indices],
            'decoder_before': before, 'decoder_after': after, 'ffprobe': probe_receipt, 'ffmpeg_contact': contact_receipt,
            'derived_files': [fp(contact), fp(copied_poster)], 'quality_verified': False,
            'scope': 'Eight actual movie frames spanning first through last encoded frame, including initialization if present. Original sealed poster copied unchanged. CPU RO decoder only; no new simulation, GIF interval, course success or quality claim.'}
        manifest.write_text(json.dumps(report, indent=2) + '\n'); summaries.append(fp(manifest))
    restore.verify(PACKAGE, SEAL_SHA); assert fp(PACKAGE / 'evidence-manifest.json') == seal_before
    report = {'schema_version': 1, 'status': 'completed_actual_cpu_six_contact_previews', 'case_manifests': summaries,
              'main_seal_before': seal_before, 'main_seal_after': fp(PACKAGE / 'evidence-manifest.json'), 'main_seal_unchanged': True,
              'scope': 'Actual contact/poster previews only, no new scientific or success claim; no GIF generated.'}
    (HERE / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__': main()
