"""Read completed evidence only; never launch Docker, media tools or candidate code."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import struct
import uuid

ROOT = Path('/home/dzp/projects/php_parkour/outputs/research/official-full')
GOOD = ROOT / 'official-evaluation-cpu-02'
BAD = ROOT / 'official-evaluation-cpu-01'
INPUT = ROOT / 'official-evaluation-transfer-01'
OUT = Path(__file__).absolute().parent
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'

def need(condition, message):
    if not condition:
        raise ValueError(message)

def read_json(path):
    return json.loads(Path(path).read_bytes())

def fingerprint(path):
    path = Path(path).absolute()
    need(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular path: ' + str(path))
    before = path.stat()
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8388608), b''):
            sha.update(data)
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')
    need(all(getattr(before, k) == getattr(after, k) for k in keys), 'changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': after.st_size, 'sha256': sha.hexdigest(), 'mode': after.st_mode & 0o777}

def verify_fingerprint(value):
    actual = fingerprint(value['path'])
    need(all(actual[k] == v for k, v in value.items()), 'saved fingerprint: ' + value['path'])
    return actual

def inventory(base):
    files = sorted(p for p in base.rglob('*') if p.is_file())
    need(not any(p.is_symlink() for p in base.rglob('*')), 'artifact symlink')
    return [fingerprint(p) for p in files]

def inspect_host(execution, base, prep, expected_exit):
    commands = execution['commands']
    need(sum(c['label'] == 'create' for c in commands) == 1, 'single create')
    need(sum(c['label'] == 'attached' for c in commands) == 1, 'single attached start')
    states = []
    for command in commands:
        for key in ('stdout', 'stderr'):
            verify_fingerprint(command[key])
        expected = expected_exit if command['label'] == 'attached' else 0
        need(type(command['actual_wait_returncode']) is int and command['actual_wait_returncode'] == expected,
             'actual host child wait: ' + command['label'])
        need(command['command'][:2] in (['docker', 'create'], ['docker', 'inspect'], ['docker', 'start']), 'unexpected Docker action')
        if command['label'] == 'create':
            need(Path(command['stdout']['path']).read_text().strip() == execution['container_id'], 'actual create CID')
        elif command['label'] == 'attached':
            need(command['command'] == ['docker', 'start', '-a', execution['container_id']], 'actual attached argv')
        elif command['label'].startswith('inspect-'):
            values = read_json(command['stdout']['path'])
            need(len(values) == 1, 'one inspect container')
            value = values[0]
            host, state = value['HostConfig'], value['State']
            need(value['Id'] == execution['container_id'] and value['Name'] == '/' + execution['container_name'], 'CID/name')
            need(value['Image'] == value['Config']['Image'] == IMAGE and value['RestartCount'] == 0, 'image/restart')
            need(value['Config']['Labels']['php.official-evaluation.owner'] == execution['owner_uuid'], 'owner UUID')
            need(host['Runtime'] == 'runc' and host['NetworkMode'] == 'none' and host['NanoCpus'] == 2000000000
                 and host['Memory'] == 12884901888 and host['PidsLimit'] == 256, 'CPU resources')
            need(host['Privileged'] is False and not host['Devices'] and not host['DeviceRequests']
                 and host['RestartPolicy'] == {'Name': 'no', 'MaximumRetryCount': 0}, 'no GPU devices/privilege/restart')
            env = dict(item.split('=', 1) for item in value['Config']['Env'])
            need(env['CUDA_VISIBLE_DEVICES'] == '' and env['NVIDIA_VISIBLE_DEVICES'] == 'void'
                 and env['PYTHONDONTWRITEBYTECODE'] == '1', 'CPU env')
            mounts = {(m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Type'] == 'bind'}
            need(len(value['Mounts']) == 4 and mounts == {(str(prep), '/code', False), (str(INPUT / 'control'), '/control', False),
                 (str(INPUT / 'artifacts'), '/artifacts', False), (str(base / 'results'), '/results', True)}, 'four exact binds')
            need(state['OOMKilled'] is False and state['Error'] == '' and state['Dead'] is False
                 and state['Restarting'] is False, 'runtime/OOM state')
            states.append({'label': command['label'], 'status': state['Status'], 'running': state['Running'],
                           'started_at': state['StartedAt'], 'finished_at': state['FinishedAt'], 'exit_code': state['ExitCode']})
    created = next(s for s in states if s['label'] == 'inspect-created')
    final = next(s for s in states if s['label'] == 'inspect-final')
    live = [s for s in states if s['label'].startswith('inspect-live-') and s['running']]
    need(created['status'] == 'created' and created['running'] is False and created['started_at'].startswith('0001-'), 'created state')
    need(live and all(s['started_at'] == final['started_at'] for s in live), 'same live/final StartedAt')
    need(final['status'] == 'exited' and final['running'] is False and final['exit_code'] == expected_exit, 'natural final exit')
    need(execution['actual_start_attached_wait_returncode'] == execution['actual_container_exit_code'] == expected_exit, 'actual waits/final agree')
    return {'container_id': execution['container_id'], 'owner_uuid': execution['owner_uuid'], 'image': IMAGE,
            'all_created_live_final_identity_resource_mount_checks_passed': True, 'actual_host_commands': len(commands), 'states': states}

def main():
    need(not (OUT / 'report.json').exists(), 'fresh report')
    host = read_json(GOOD / 'host/execution.json')
    actual = read_json(GOOD / 'results/report.json')
    failed = read_json(BAD / 'host/execution.json')
    need(host['status'] == 'passed_official_evaluation_CPU' and host['actualpassed'] is True and host['errors'] == [], 'host pass')
    need(host['container_id'] == 'a1c6635652c665d63dcfcbb0680eb845852d3e9039d5dcfa5f2800a51e4a2caa', 'expected actual CID')
    need(str(uuid.UUID(host['owner_uuid'])) == host['owner_uuid'], 'UUID syntax')
    need(host['create_actual_returncode'] == host['actual_start_attached_wait_returncode'] == host['actual_container_exit_code'] == 0, 'actual create/start/final0')
    need(host['container_running'] is False, 'not running')
    need(actual['status'] == 'passed' and actual['errors'] == [] and actual['counts'] == {'stages': 6, 'videos_attempted': 160, 'videos_passed': 160}, 'actual validator counts/pass')
    for key in ('quality_verified', 'full'):
        need(host[key] is False and actual[key] is False, 'limited scope ' + key)
    need(host['convergence_verified'] is False and host['official_schedule_complete'] is False, 'no convergence/schedule claim')
    need(actual['guard']['dockerenv'] is True and actual['guard']['CUDA_VISIBLE_DEVICES'] == ''
         and actual['guard']['NVIDIA_VISIBLE_DEVICES'] == 'void' and actual['guard']['gpu_devices'] == [], 'actual CPU guard')
    source_pins = {'run_owned_cpu.py': 'f70938355e4e36b0f7758c00e48da141d9707c684d04cd55709f15f80b1270fb',
                   'validate.py': '86ad6bb0f41f60951b4a784285851525eb0efb2bf398da38cbe1ef8f71688ac4',
                   'run_owned_cpu.source-manifest.json': '8e762fab09637bd031adf09b054192c1f0753470aa75fd4c499a3edba420be73'}
    need(host['source_unchanged'] is True and host['source_before'] == host['source_after'] and len(host['source_after']) == 3, 'three unchanged sources')
    need({Path(r['path']).name: r['sha256'] for r in host['source_after']} == source_pins, 'reviewed source pins')
    need(host['inputs_unchanged'] is True and host['input_before'] == host['input_after'] and len(host['input_after']) == 197, '197 unchanged inputs')
    for row in host['source_after'] + host['input_after']:
        verify_fingerprint(row)
    contract = read_json(INPUT / 'control/input-contract.json')
    contract_fp = fingerprint(INPUT / 'control/input-contract.json')
    need(contract_fp == host['input_after'][0] and contract_fp['sha256'] == '4ca7fb20e21328235b1dd40def4852ceccc81cdd414782523adefd52cc05fb72', 'actual contract pin')
    flat = [s[k] for s in contract['stages'] for k in ('manifest', 'training_manifest', 'quality', 'config', 'log')]
    flat += [r for s in contract['stages'] for key in ('events', 'videos') for r in s[key]]
    need(len(flat) == 196 and len({r['path'] for r in flat}) == 196, '196 originals')
    selected = {str(INPUT / 'artifacts' / Path(r['path']).relative_to('/artifacts')): r for r in flat}
    need(set(selected) == {r['path'] for r in host['input_after'][1:]}, 'exact selected host paths')
    for row in host['input_after'][1:]:
        need(all(row[k] == selected[row['path']][k] for k in ('bytes', 'sha256')), 'original hash/size binding')
    for row in flat:
        need(row['path'] == '/artifacts/' + Path(row['native_path']).relative_to('/outputs').as_posix(), 'native topology')
    for key in ('source', 'contract', 'input'):
        need(actual[key + '_before'] == actual[key + '_after'], 'validator before/after ' + key)
    need(actual['source_after']['sha256'] == source_pins['validate.py'] and actual['contract_after']['sha256'] == contract_fp['sha256'], 'validator source/contract binding')
    need(actual['input_after'] == read_json(GOOD / 'results/input-before.json') == read_json(GOOD / 'results/input-after.json'), 'saved input snapshots')
    need(actual['input_after']['failures'] == [] and {r['path']: (r['bytes'], r['sha256']) for r in actual['input_after']['files']}
         == {r['path']: (r['bytes'], r['sha256']) for r in flat}, 'validator all196 exact originals')
    verify_fingerprint(host['validator_report'])
    owned = inspect_host(host, GOOD, ROOT / 'official-evaluation-cpu-preparation-03', 0)
    stdout = read_json(GOOD / 'host/attached.stdout.raw')
    need(stdout['status'] == 'passed' and stdout['counts'] == actual['counts'] and stdout['errors'] == [], 'raw attached terminal summary')
    executions = {}
    for path in sorted((GOOD / 'results').rglob('*.execution.json')):
        value = read_json(path)
        need(type(value['returncode']) is int and value['returncode'] == 0 and value['failure'] is None, 'actual CPU child wait ' + str(path))
        need(math.isfinite(value['elapsed_seconds']) and value['elapsed_seconds'] >= 0, 'child elapsed')
        prefix = str(path).removesuffix('.execution.json')
        need(Path(prefix + '.stdout.raw').is_file() and Path(prefix + '.stderr.raw').is_file(), 'raw child stdout/stderr')
        executions[path] = value
    expected_children = set()
    for program in ('ffmpeg', 'ffprobe'):
        path = GOOD / 'results' / (program + '-version.execution.json')
        need(executions[path]['command'] == [program, '-version'], 'version command')
        expected_children.add(path)
    videos, stages, teachers = [], [], []
    scalar_total, event_total, record_total, thumb_total, max_residual = 0, 0, 0, 0, 0
    need(len(actual['stages']) == len(contract['stages']) == 6, 'six actual stages')
    for stage, result in zip(contract['stages'], actual['stages']):
        label, folder = stage['label'], GOOD / 'results' / stage['label']
        need(result['label'] == label and result['status'] == 'passed' and result == read_json(folder / 'stage-result.json'), 'stage saved result ' + label)
        phases = ('native_quality', 'saved_yaml', 'tensorboard', 'representative_thumbnail')
        need(all(result[p]['status'] == 'passed' for p in phases), 'four phases ' + label)
        def native(key):
            return read_json(INPUT / 'artifacts' / Path(stage[key]['path']).relative_to('/artifacts'))
        train, manifest, quality = native('training_manifest'), native('manifest'), native('quality')
        identity = actual['checkpoint_identities_without_loading_pt'][label]
        need(identity['path'] == train['checkpoint'] == quality['checkpoint'] and identity['sha256'] == train['checkpoint_sha256'] == quality['checkpoint_sha256'], 'native checkpoint identity ' + label)
        need(identity['iteration'] == train['checkpoint_iteration'] == quality['checkpoint_iteration'] == (9999 if label == 'eval-student-pure' else 19999), 'final recorded iteration ' + label)
        need(train['status'] == manifest['status'] == 'passed' and train['returncode'] == manifest['returncode'] == 0, 'native completed manifests ' + label)
        need(quality['status'] == 'completed' and quality['quality_verified'] is False and quality['num_envs'] == 64 and quality['control_steps'] == 3000 and quality['seed'] == 42, 'native64x3000 ' + label)
        need(all(m['samples'] == 192000 for m in quality['metrics'].values()) and identity['registries'] == quality['registry_order'], 'native sample/registry ' + label)
        checkpoint = {'path': identity['path'], 'sha256': identity['sha256']}
        need(manifest['settings']['source_checkpoints'] == [checkpoint], 'evaluation final source ' + label)
        if label == 'eval-student-pure':
            need(train['settings']['source_checkpoints'] == teachers and train['environment']['FINETUNE'] == '0', 'ordered five teachers, pure student')
        else:
            teachers.append(checkpoint)
        for key in ('metrics', 'failed_resets', 'timeout_resets', 'observed_clip_ids', 'available_clip_count', 'metrics_by_expert', 'resets_by_expert'):
            need(result['native_quality']['value'][key] == quality[key], 'derived/native quality ' + label + ' ' + key)
        native_videos = {r['path']: r for r in manifest['evaluation_videos']}
        bound_videos = {r['path']: r for r in quality['videos']}
        need(set(native_videos) == {r['native_path'] for r in stage['videos']} and set(bound_videos) == {r['native_path'] for r in stage['videos'] if r['quality_bound']}, '148/12 native distinction ' + label)
        training = result['saved_yaml']['value']['training']
        need(training['num_envs'] == 64 and training['max_eval_steps'] == 3000 and training['seed'] == 42 and training['checkpoint'] is None and training['export_onnx'] is False, 'actual saved YAML ' + label)
        need(training['registry_name'] == ','.join(identity['registries']) and training['teacher_checkpoint'] == train['environment'].get('TEACHER_CHECKPOINT'), 'YAML registry/teacher sources ' + label)
        tb = result['tensorboard']['value']; integrity = tb['event_integrity']
        need(tb['event_integrity_complete'] is True and integrity == read_json(folder / 'tensorboard-integrity.json') and len(integrity['events']) == len(stage['events']), 'strict integrity saved result ' + label)
        record_counts = []
        for original, checked in zip(stage['events'], integrity['events']):
            need(checked['expected_file'] == {k: original[k] for k in ('path', 'bytes', 'sha256')}, 'strict original identity ' + label)
            need(checked['status'] == 'passed' and checked['complete_eof'] is True and checked['crc32c_verified'] is True and checked['diagnostics'] == [], 'strict CRC/EOF outcome ' + label)
            need(type(checked['records']) is int and checked['records'] > 0 and checked['bytes'] == original['bytes'] and checked['sha256'] == original['sha256'], 'strict complete file/count ' + label)
            record_counts.append(checked['records']); event_total += 1; record_total += checked['records']
        scalar = read_json(folder / 'tensorboard-scalars.json')
        expected = {'Evaluation/failed_resets': quality['failed_resets'], 'Evaluation/timeouts': quality['timeout_resets'], 'Evaluation/control_steps': quality['control_steps'], 'Evaluation/sim_seconds_per_env': quality['sim_seconds_per_env'], 'Evaluation/clip_completions': quality['clip_completions_excluding_failed_timeout_steps']}
        for metric, value in quality['metrics'].items():
            for aggregate in ('mean', 'p95', 'max'):
                expected['Evaluation/tracking_error/' + metric.removeprefix('motion/') + '/' + aggregate] = value[aggregate]
        need(scalar['expected'] == expected and set(scalar['observed']) == set(expected) and len(expected) == 17 and tb['matched_tags'] == sorted(expected), '17 actual scalar tags ' + label)
        for tag, values in scalar['observed'].items():
            need(len(values) == 1 and values[0]['step'] == 3000 and math.isfinite(values[0]['wall_time']) and math.isfinite(values[0]['value']), 'actual scalar sample ' + label)
            need(math.isclose(values[0]['value'], expected[tag], abs_tol=1e-6, rel_tol=1e-6), 'actual scalar/native value ' + tag)
            max_residual = max(max_residual, abs(values[0]['value'] - expected[tag])); scalar_total += 1
        need(len(result['videos']) == len(stage['videos']), 'all clips attempted ' + label)
        for index, (original, video) in enumerate(zip(stage['videos'], result['videos'])):
            need(video['status'] == 'passed' and all(video[k] == value for k, value in original.items()), 'video original binding ' + label)
            prefix = folder / 'videos' / (str(index).zfill(3) + '-' + Path(original['path']).stem)
            need(video == read_json(str(prefix) + '.result.json'), 'video saved result')
            for field in ('ffprobe', 'ffmpeg'):
                path = Path(str(prefix) + '.' + field + '.execution.json')
                need(executions[path] == video[field], 'video actual child record ' + field)
                expected_children.add(path)
            metadata = read_json(str(prefix) + '.ffprobe.stdout.raw')
            need(metadata == video['metadata'], 'raw ffprobe metadata')
            progress = dict(line.split('=', 1) for line in Path(str(prefix) + '.ffmpeg.stdout.raw').read_text().splitlines() if '=' in line)
            frames, decoded = int(metadata['streams'][0]['nb_read_frames']), int(progress['frame'])
            need(type(video['probed_frames']) is int and type(video['decoded_frames']) is int and frames == decoded == video['probed_frames'] == video['decoded_frames'] and frames > 0, 'positive full frame equality')
            need(progress['progress'] == 'end' and video['progress_end'] is True and int(metadata['streams'][0]['width']) > 0 and int(metadata['streams'][0]['height']) > 0, 'full progress/dimensions')
            need(metadata['format']['filename'] == original['path'] and int(metadata['format']['size']) == original['bytes'], 'actual probe source/size')
            need(math.isclose(float(metadata['format']['duration']), original['declared_duration_seconds'], abs_tol=1e-6, rel_tol=1e-6), 'actual/native duration')
            need(video['ffprobe']['command'][-1] == original['path'] and video['ffmpeg']['command'][video['ffmpeg']['command'].index('-i') + 1] == original['path'], 'actual media input argv')
            need(video['ffmpeg']['command'][-3:] == ['-f', 'null', '-'] and '-hwaccel' not in video['ffmpeg']['command'], 'CPU full decode argv')
            if original['quality_bound']:
                need(bound_videos[original['native_path']]['sha256'] == original['sha256'], 'quality bound video SHA')
            videos.append({'label': label, 'native_path': original['native_path'], 'sha256': original['sha256'], 'quality_bound': original['quality_bound'], 'native_described': original['native_described'], 'probed_frames': frames, 'decoded_frames': decoded, 'progress_end': True, 'duration_seconds': video['duration_seconds']})
        thumb = result['representative_thumbnail']['value']
        chosen = max((video for video in result['videos'] if video['quality_bound']), key=lambda video: video['declared_duration_seconds'])
        need(thumb['source_native_path'] == chosen['native_path'] and thumb['source_sha256'] == chosen['sha256'] and thumb['seek_seconds'] == chosen['duration_seconds'] / 2, 'longest fully decoded representative source')
        path = folder / 'thumbnail.ffmpeg.execution.json'
        need(executions[path] == thumb['execution'], 'actual thumbnail child record'); expected_children.add(path)
        png_path = GOOD / 'results' / Path(thumb['thumbnail']['path']).relative_to('/results')
        png_fp = fingerprint(png_path)
        need(png_fp['bytes'] == thumb['thumbnail']['bytes'] and png_fp['sha256'] == thumb['thumbnail']['sha256'], 'thumbnail bytes/SHA')
        png = png_path.read_bytes()
        need(png[:8] == bytes.fromhex('89504e470d0a1a0a') and png[12:16] == b'IHDR', 'PNG signature')
        width, height = struct.unpack('>II', png[16:24]); need(width > 0 and height > 0, 'PNG dimensions'); thumb_total += 1
        stages.append({'label': label, 'phases': {key: result[key]['status'] for key in phases}, 'num_envs': quality['num_envs'], 'control_steps': quality['control_steps'], 'checkpoint_identity_without_loading_pt': identity, 'videos': len(stage['videos']), 'quality_bound_videos': len(bound_videos), 'native_described_only_videos': len(native_videos) - len(bound_videos), 'decoded_frames': sum(video['decoded_frames'] for video in result['videos']), 'strict_original_record_counts': record_counts, 'scalars': len(expected), 'thumbnail': {'source_native_path': thumb['source_native_path'], 'source_sha256': thumb['source_sha256'], 'file': png_fp, 'width': width, 'height': height}, 'failed_resets': quality['failed_resets'], 'timeout_resets': quality['timeout_resets'], 'available_clip_count': quality['available_clip_count'], 'observed_clip_ids': quality['observed_clip_ids']})
    need(expected_children == set(executions) and len(executions) == 2 + 2 * len(videos) + thumb_total, 'complete actual child set')
    need(len(videos) == 160 and sum(video['quality_bound'] for video in videos) == 148 and sum(not video['quality_bound'] for video in videos) == 12, '160/148/12 actual clips')
    need(scalar_total == 102 and event_total == 6 and thumb_total == 6, 'actual scalars/events/thumbs')
    need(failed['status'] == 'failed_partial_preserved' and failed['actualpassed'] is False and failed['source_unchanged'] is True and failed['inputs_unchanged'] is True, 'failed01 preserved status')
    need(failed['source_before'] == failed['source_after'] and failed['input_before'] == failed['input_after'] and len(failed['input_after']) == 197, 'failed01 unchanged before/after')
    for row in failed['source_after'] + failed['input_after']:
        verify_fingerprint(row)
    failed_owned = inspect_host(failed, BAD, ROOT / 'official-evaluation-cpu-preparation-02', 1)
    stderr = (BAD / 'host/attached.stderr.raw').read_bytes()
    need(b'CPU Docker guard failed' in stderr and b"'gpu_devices': []" in stderr and b"'nvidia_proc': True" in stderr and b'state = guard()' in stderr, 'failed01 exact raw cause')
    need(not list((BAD / 'results').iterdir()), 'failed01 before validator results')
    failed_stdout = (BAD / 'host/attached.stdout.raw').read_text()
    need(failed_stdout == 'There was an error running python\n', 'failed01 actual entrypoint failure stdout')
    good_files, bad_files = inventory(GOOD), inventory(BAD)
    for row in good_files + bad_files + host['source_after'] + host['input_after'] + failed['source_after']:
        verify_fingerprint(row)
    evidence = {}
    data_files = {'actual02-artifact-inventory.json': good_files, 'failed01-artifact-inventory.json': bad_files,
                  'originals-and-sources.json': {'actual02_source': host['source_after'], 'actual02_contract_and_196_inputs': host['input_after'], 'failed01_source': failed['source_after']},
                  'actual02-video-evidence.json': videos, 'actual02-child-waits.json': [{'path': str(path), **value} for path, value in executions.items()],
                  'actual02-stage-evidence.json': stages, 'actual02-owned-container.json': owned, 'failed01-owned-container.json': failed_owned}
    for name, value in data_files.items():
        path = OUT / name
        with path.open('x') as stream:
            json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
        value = fingerprint(path)
        evidence[name] = {'bytes': value['bytes'], 'sha256': value['sha256']}
    with (OUT / 'failed01-attached.stderr.raw').open('xb') as stream:
        stream.write(stderr)
    value = fingerprint(OUT / 'failed01-attached.stderr.raw')
    evidence['failed01-attached.stderr.raw'] = {'bytes': value['bytes'], 'sha256': value['sha256']}
    report = {'schema_version': 1, 'status': 'passed_independent_actual_CPU_evidence_review', 'reviewer': 'official_eval_runtime', 'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'Read and SHA256 audit of completed actual CPU02 evidence and preserved failed CPU01; no candidate, Docker, scientific library, media subprocess or model execution by reviewer.',
              'candidate_executed_by_reviewer': False, 'candidate_imported_by_reviewer': False, 'docker_invoked_by_reviewer': False, 'new_media_created': False, 'model_loaded': False,
              'quality_verified': False, 'full': False, 'convergence_verified': False, 'official_schedule_complete': False,
              'actual02': {'container_id': host['container_id'], 'owner_uuid': host['owner_uuid'], 'image': IMAGE,
                           'created_live_final_identity_cpu_resources_and_four_binds_verified': True,
                           'actual_attached_wait': 0, 'actual_natural_container_exit': 0, 'no_gpu_devices': actual['guard']['gpu_devices'] == [], 'nvidia_proc_metadata_visible': actual['guard']['nvidia_proc'], 'source_before_after_and_current_exact': True,
                           'contract_plus196_originals_before_after_and_current_exact': True, 'artifact_files_rehashed': len(good_files), 'all_raw_actual_child_waits_zero': len(executions),
                           'ffprobe_waits': len(videos), 'full_ffmpeg_decode_waits': len(videos), 'thumbnail_waits': thumb_total, 'version_waits': 2,
                           'positive_equal_frames_and_progress_end_clips': len(videos), 'decoded_frames_total': sum(video['decoded_frames'] for video in videos),
                           'quality_bound_clips': sum(video['quality_bound'] for video in videos), 'native_described_only_clips': sum(not video['quality_bound'] for video in videos),
                           'strict_crc32c_complete_eof_files': event_total, 'strict_original_record_counts_by_stage': [stage['strict_original_record_counts'] for stage in stages],
                           'strict_original_record_total_derived': record_total, 'scalar_values': scalar_total, 'maximum_scalar_absolute_residual': max_residual,
                           'scalar_absolute_tolerance': 1e-6, 'scalar_relative_tolerance': 1e-6, 'stages': len(stages)},
              'failed01': {'status': failed['status'], 'container_id': failed['container_id'],
                           'actual_attached_wait': 1, 'actual_natural_container_exit': 1, 'failure': 'CPU guard rejected visible proc driver metadata while actual GPU device list was empty; traceback precedes third-party imports and all media/version children.',
                           'actual_entrypoint_stdout': failed_stdout,
                           'results_empty': True, 'sources_and_contract_plus196_originals_before_after_and_current_exact': True,
                           'original_evidence_preserved': True, 'artifact_files_rehashed': len(bad_files)},
              'evidence_artifacts': evidence, 'review_audit_source': fingerprint(Path(__file__)),
              'limitations': ['Audit binds actual saved evidence for six existing64envx3000 evaluations; it establishes no new rollout, performance threshold, convergence, full quality, official schedule completion or source-motion coverage.',
                              'Checkpoint paths, SHA256 identities and final iterations match immutable native records; checkpoint tensors were not loaded or separately transferred by this audit.',
                              'CRC outcomes and scalar reloads are from the reviewed, SHA-bound actual validator; this independent review reads their complete results and raw media outputs without invoking those parsers/tools again.']}
    with (OUT / 'report.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'report': fingerprint(OUT / 'report.json'), 'status': report['status'], 'artifact_files': len(good_files), 'cpu_child_waits': len(executions),
                      'decoded_frames': report['actual02']['decoded_frames_total'], 'strict_records': record_total, 'strict_by_stage': report['actual02']['strict_original_record_counts_by_stage'], 'scalars': scalar_total}))

if __name__ == '__main__':
    main()
