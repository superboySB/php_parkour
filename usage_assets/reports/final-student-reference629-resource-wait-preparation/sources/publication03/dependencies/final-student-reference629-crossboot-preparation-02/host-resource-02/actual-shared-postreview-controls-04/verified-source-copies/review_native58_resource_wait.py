#!/usr/bin/env python3
"""Read actual crossboot native58 evidence; preserve original scientific checks.

No native rollout, GPU, network, scientific-source write or container mutation.
The explicitly supplied running CPU container performs fresh full MP4 decodes.
"""
from __future__ import annotations
import argparse
import ast
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
WORKSPACE = Path('/home/dzp/projects/php_parkour')
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
PINS = {'common.py': 'bef9e7af9a67c9d10360145de7f6715cb167a8722fccb1e44aaaf4c7118371b2',
        'native58.py': '31ecc764ee2375f52a5c75582597f85c0d57a4607725db5cd3bac1cc6e7ebf43',
        'phase_cpu.py': '855d56494c662cbfcd19a96043b6f0baaa49a093f52c47b46a9005657e46bb0f'}
MATRIX_SHA = '5e90c16302b3f9993930e684c3dddb01f8710b06225cff11d5b9f18141611adb'
KINDS = ('pure', 'finetune')
SHARED_CONTROL_SHA = '81674ff7041216c99f5a43d214868d881079a4c274ad493ac0752afddb49a374'
ORIGINAL_REVIEW_SHA = 'cb3039b3074611025972f762c1c4fc538555fd5fe7a003f23ed4604c34cbf278'


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts and path.is_relative_to(WORKSPACE), 'Workspace path required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path rejected')
    return path


def fp(path):
    path = safe(path)
    require(path.is_file(), 'Missing actual regular file: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(data)
    after = path.stat()
    signature = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    require(signature(before) == signature(after), 'Evidence changed during hash')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify(args):
    base, exit_path, output = map(safe, (args.base, args.parent_exit, args.output))
    require(not output.exists(), 'Fresh review output required')
    evidence = {}

    def retain(path, expected=None):
        actual = fp(path)
        if expected is not None:
            require(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'], 'Retained bytes differ: ' + str(path))
        require(actual['path'] not in evidence or evidence[actual['path']] == actual, 'Conflicting evidence record')
        evidence[actual['path']] = actual
        return actual

    def actual(path):
        retain(path)
        return read(path)

    review_source = retain(__file__)
    require(retain(Path(__file__).with_name('review_native58.py'))['sha256'] == ORIGINAL_REVIEW_SHA,
            'Original scientific review source changed')

    def cpu_inspect(path, cid):
        info = actual(path)
        env = dict(x.split('=', 1) for x in info['Config']['Env'])
        require(info['Id'] == cid and info['Image'] == IMAGE and info['State']['ExitCode'] == 0
                and info['State']['Running'] is False and info['State']['OOMKilled'] is False
                and info['HostConfig']['Runtime'] == 'runc' and info['HostConfig']['NetworkMode'] == 'none'
                and not info['HostConfig'].get('Devices') and not info['HostConfig'].get('DeviceRequests')
                and env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void',
                'Actual CPU container isolation/image/normal exit differs')

    plan = actual(base / 'host-plan.json')
    require(plan['plan_sha256'] == identity({k: v for k, v in plan.items() if k != 'plan_sha256'})
            and plan['output'] == str(base) and plan['image_id'] == IMAGE and plan['gpu_uuid'] == GPU,
            'Plan identity/output/image/GPU differs')
    require(plan['expected_counts'] == {'policies': 2, 'cases': 58, 'worker_exit0_empty_groups': 116,
            'exact_host_maps': 116, 'full_mp4_decodes': 58, 'cpu_ort_cases': 60}, 'Plan counts differ')
    expected_phases = [kind + '-' + phase for kind in KINDS for phase in ('directions', 'scenes')]
    require([p['id'] for p in plan['phases']] == expected_phases, 'Four ordered phases required')
    freeze = actual(base / 'freeze-manifest.json')
    require(fp(base / 'freeze-manifest.json')['sha256'] == plan['freeze_manifest_sha256'], 'Frozen manifest differs')
    frozen_paths = set()
    for row in freeze['files']:
        relative = Path(row['relative'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(relative) not in frozen_paths, 'Unsafe/duplicate frozen path')
        frozen_paths.add(str(relative))
        retain(base / relative, row)
    for name, digest in PINS.items():
        require(retain(base / 'control' / name)['sha256'] == digest, 'Frozen control changed: ' + name)
    common_path = base / 'control/common.py'
    spec = importlib.util.spec_from_file_location('independent_native58_transfer_checks', common_path)
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)  # Reviewed stdlib read-only transfer checker.
    origin = common.transfer(WORKSPACE, safe(args.transfer))
    require(origin['status'] == 'ready' and origin == plan['origin_transfer'], 'Actual fetch/model origin differs')
    for row in origin['origin_files']:
        retain(row['path'], row)

    parent_module_path = safe(Path(__file__).with_name('native58_resource_wait_control.py'))
    require(retain(parent_module_path)['sha256'] == SHARED_CONTROL_SHA, 'Reviewed crossboot parent verifier source differs')
    spec = importlib.util.spec_from_file_location('actual_native58_crossboot_parent_control', parent_module_path)
    parent_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent_module)
    actual_parent = parent_module.verify_actual_parent(base, exit_path, args.parent_exit_sha256, retain)
    terminal = actual(base / 'host/launch-receipt.json')
    require(terminal['status'] == 'completed' and terminal['plan_sha256'] == plan['plan_sha256']
            and terminal['cases'] == 58 and terminal['worker_exit0_empty_groups'] == 116
            and terminal['exact_host_maps'] == 116 and terminal['full_decoded_mp4_count'] == 58
            and terminal['quality_verified'] is False, 'Completed58/116/116/58 required')
    require([p['id'] for p in terminal['phases']] == expected_phases, 'Terminal phase order differs')

    matrix_path = base / 'source/scripts/research/sim2sim_scene_matrix.py'
    require(retain(matrix_path)['sha256'] == MATRIX_SHA, 'Original matrix source differs')
    text = matrix_path.read_text()
    tree = ast.parse(text)
    worker_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_worker_receipts')
    namespace = {'Path': Path, 'json': json, 'math': math, 're': re, 'ROOT': base / 'source',
                 'digest': lambda p: fp(p)['sha256'], 'fingerprint': fp}
    exec(compile(ast.Module(body=[worker_fn], type_ignores=[]), str(matrix_path), 'exec'), namespace)
    validate_workers = namespace['validate_worker_receipts']  # Exact original function AST; no module entrypoint/imports.
    videos, mappings, case_count = [], set(), 0
    for stage, expected in zip(terminal['phases'], plan['phases']):
        count = 12 if expected['phase'] == 'directions' else 17
        require(expected['cases'] == count and expected['ticks'] == (400 if count == 12 else 500), 'Phase scope changed')
        require(stage['status'] == 'completed' and all(type(stage[k]) is int and stage[k] == 0 for k in
                ('driver_returncode', 'observer_returncode', 'driver_returncode_after_stop'))
                and stage['owned_gpu_container_stop']['running_after_stop'] is False
                and stage['worker_exit0_empty_groups'] == 2 * count and len(stage['host_maps']) == 2 * count
                and stage['full_decoded_mp4_count'] == count, 'Actual phase/direct waits/cleanup/counts differ')
        phase_root = base / 'phases' / expected['id']
        post_path = phase_root / 'cpu-final/summary.json'
        require(retain(post_path) == stage['cpu_final'], 'CPU summary fingerprint differs')
        post = read(post_path)
        require(post['status'] == 'passed' and post['case_count'] == count and len(post['cases']) == count
                and post['worker_exit0_empty_groups'] == 2 * count and post['full_decoded_mp4_count'] == count,
                'CPU phase was not complete')
        cpu_launch = actual(phase_root / 'cpu-final/launch.json')
        require(cpu_launch['status'] == 'passed' and cpu_launch['mode'] == 'finalize'
                and cpu_launch['returncode'] == cpu_launch['container_exit_code'] == 0
                and cpu_launch['owned_container_stop']['running_after_stop'] is False, 'CPU finalizer actual wait absent')
        cpu_inspect(phase_root / 'cpu-final/container-inspect.json', cpu_launch['container_id'])
        observer = actual(phase_root / 'observer/summary.json')
        info = actual(phase_root / 'container-inspect.json')
        require(observer['identity']['container_id'] == stage['container_id'] == info['Id']
                and observer['identity']['image_id'] == IMAGE == info['Image']
                and observer['identity']['started_at'] == info['State']['StartedAt']
                and observer['stop_reason'] == 'stop_file' and observer['mapping_scope_complete'] and observer['errors'] == [],
                'Observer scope/container birth differs')
        native_plan = actual(base / 'inputs' / expected['kind'] / (expected['phase'] + '-plan.json'))
        require(native_plan['plan_sha256'] == expected['native_plan_sha256'] and fp(base / 'inputs' / expected['kind'] /
                (expected['phase'] + '-plan.json'))['sha256'] == expected['native_plan_file_sha256'], 'Native phase plan changed')

        def translate(value):
            path = Path(value)
            for prefix, target in ((Path('/outputs'), phase_root / 'outputs'), (Path('/workspace/php_parkour'), base / 'source'),
                                   (Path('/data'), base / 'inputs' / expected['kind']), (Path('/control'), base / 'control')):
                if path.is_relative_to(prefix):
                    return str(target / path.relative_to(prefix))
            return str(path)

        require([x['case_id'] for x in post['cases']] == [x['case_id'] for x in native_plan['selections']], 'Case order differs')
        for case in post['cases']:
            require(case['worker_exit0_empty_groups'] == 2 and case['ticks'] == expected['ticks']
                    and case['quality_verified'] is False and len(case['video_full_decodes']) == 1, 'Per-case CPU gate differs')
            directory = safe(translate(case['output']))
            for row in case['files']:
                retain(translate(row['path']), row)
            result = actual(directory / 'result.json')
            require(fp(directory / 'result.json')['sha256'] == case['native_result_sha256']
                    and result['status'] == 'completed' and result['inference']['ticks'] == expected['ticks']
                    and result['inference']['control_period_simulation_seconds'] == .02
                    and result['config']['model_sha256'] == native_plan['model_sha256']
                    and result['config']['wall_timeout'] == expected['native_wall_timeout_seconds']
                    and result['config']['startup_timeout'] == 180.0 and result['quality_verified'] is False,
                    'Actual result/model/ticks/default timing differs')
            receipts = validate_workers(directory, native_plan, result, translate)
            require(len(receipts) == 3, 'Three original worker receipt files required')
            for row in receipts:
                retain(row['path'], row)
            for role in ('simulator', 'inference'):
                entry_path = directory / (role + '-process-start.json')
                native = actual(entry_path)['process']
                found = [m for m in stage['host_maps'] if m['case_id'] == case['case_id'] and m['role'] == role]
                require(len(found) == 1, 'Missing/duplicate terminal host map')
                saved = found[0]
                m = saved['mapping']
                require(saved['phase'] == stage['id'] and saved['entry_sha256'] == fp(entry_path)['sha256']
                        and m in observer['command_writer_mappings'] and m['worker_output'] == case['output']
                        and m['container_tgid'] == native['pid'] and m['owner_start_time_clock_ticks'] == native['start_time_clock_ticks']
                        and m['nspid'] == [m['host_tid'], m['container_tid']] and m['nstgid'] == [m['host_tgid'], native['pid']],
                        'Actual command_writer host namespace/birth mapping differs')
                key = (m['host_tid'], m['start_time_clock_ticks'])
                require(key not in mappings, 'Duplicate host writer birth identity')
                mappings.add(key)
            decode = case['video_full_decodes'][0]
            video = safe(directory / decode['file'])
            require(video.is_relative_to(directory) and decode['full_decode'] is True and decode['returncode'] == 0
                    and decode['command'] == ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-threads', '1',
                        '-i', str(Path(case['output']) / decode['file']), '-f', 'null', '-'], 'Original CPU full decode receipt differs')
            retain(video, decode)
            videos.append(video)
            with (directory / 'trajectory.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            require(rows and all(math.isfinite(float(v)) for r in rows for v in r.values()), 'Nonfinite/missing trajectory')
            active = [r for r in rows if float(r['policy_seconds']) >= 0]
            require(len(active) >= expected['ticks'] and all(float(r['gantry_enabled']) == 0 for r in active), 'Unsupported trajectory coverage absent')
            case_count += 1

    poses = {}
    for kind in KINDS:
        where = base / 'host' / ('cpu-' + kind)
        cpu, summary, onnx = [actual(where / name) for name in ('launch.json', 'summary.json', 'onnx.json')]
        require(cpu['status'] == 'passed' and cpu['mode'] == 'prepare' and cpu['kind'] == kind
                and cpu['returncode'] == cpu['container_exit_code'] == 0 and cpu['owned_container_stop']['running_after_stop'] is False,
                'Original CPU preparation actual exit missing')
        cpu_inspect(where / 'container-inspect.json', cpu['container_id'])
        require(summary['status'] == 'passed' and summary['ort_cases'] == 30 and summary['directions_cases'] == 12
                and summary['scene_cases'] == 17 and summary['image_id'] == IMAGE and summary['source_sha256'] == PINS['phase_cpu.py']
                and onnx['status'] == 'passed' and len(onnx['cases']) == 30, 'Each formal pair needs30 actual ORT cases')
        pairs = {Path(r['path']).name: (r['bytes'], r['sha256']) for r in origin['models'] if r['kind'] == kind}
        require({Path(r['path']).name: (r['bytes'], r['sha256']) for r in onnx['models']} == pairs, 'ORT pair identity differs')
        for name, (size, digest) in pairs.items():
            retain(base / 'inputs' / kind / 'assets/student' / name, {'bytes': size, 'sha256': digest})
        pose = onnx['native_default_pose_compatibility']
        require(pose['status'] == 'passed' and len(pose['native_joint_names']) == len(set(pose['native_joint_names'])) == 29
                and sorted(pose['native_to_model_permutation']) == list(range(29))
                and math.isfinite(pose['max_default_pose_absolute_error']) and pose['max_default_pose_absolute_error'] <= .000501,
                'Native default pose/joint permutation failed')
        poses[kind] = pose
    require(case_count == len(videos) == 58 and len(mappings) == 116, 'Independent actual counts differ')

    # Only CPU ffmpeg is invoked. The scientific/cohort files remain read-only.
    def inspect_cpu():
        r = subprocess.run(['docker', 'inspect', '--type', 'container', args.decode_container], capture_output=True, text=True, check=True)
        info = json.loads(r.stdout)[0]
        env = dict(x.split('=', 1) for x in info['Config']['Env'])
        require(info['Image'] == IMAGE and info['State']['Running'] is True and info['HostConfig']['Runtime'] == 'runc'
                and info['HostConfig']['NetworkMode'] == 'none' and info['HostConfig']['Privileged'] is False
                and not info['HostConfig'].get('Devices') and not info['HostConfig'].get('DeviceRequests')
                and env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void', 'Explicit CPU decoder container required')
        workspace_destination = Path('/workspace/php_parkour')
        exact = [m for m in info['Mounts'] if m['Type'] == 'bind' and m['Source'] == str(WORKSPACE)
                 and m['Destination'] == str(workspace_destination) and m['RW'] is False]
        require(len(exact) == 1, 'Decoder requires one exact read-only scientific workspace bind')
        for mount in info['Mounts']:
            destination = Path(mount['Destination'])
            require(destination.is_absolute() and '..' not in destination.parts,
                    'Unsafe decoder mount destination')
            if mount is not exact[0]:
                require(not destination.is_relative_to(workspace_destination)
                        and not workspace_destination.is_relative_to(destination),
                        'Another decoder mount overrides the SHA-verified scientific workspace')
        return info
    decoder = inspect_cpu()
    logdir = output.with_suffix('.decode-logs')
    require(not logdir.exists(), 'Fresh independent decode log directory required')
    logdir.mkdir(parents=True)
    decode_rows = []
    for index, video in enumerate(videos):
        container_path = str(Path('/workspace/php_parkour') / video.relative_to(WORKSPACE))
        argv = ['docker', 'exec', decoder['Id'], 'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-xerror',
                '-threads', '1', '-hwaccel', 'none', '-i', container_path, '-map', '0:v:0', '-an', '-vsync', '0',
                '-progress', 'pipe:1', '-nostats', '-f', 'null', '-']
        out, err = logdir / f'{index:02d}.stdout', logdir / f'{index:02d}.stderr'
        before = fp(video)
        with out.open('xb') as stdout, err.open('xb') as stderr:
            code = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=120).returncode
        progress = dict(line.split('=', 1) for line in out.read_text().splitlines() if '=' in line)
        decoded_frames = int(progress.get('frame', '0'))
        require(type(code) is int and code == 0 and decoded_frames > 0 and progress.get('progress') == 'end'
                and fp(video) == before, 'Independent positive-frame complete MP4 CPU decode failed')
        decode_rows.append({'video': before, 'argv': argv, 'actual_wait': code, 'decoded_frames': decoded_frames,
                            'progress_end': True, 'stdout': retain(out), 'stderr': retain(err)})
    decoder_after = inspect_cpu()
    require(decoder_after['Id'] == decoder['Id']
            and decoder_after['State']['StartedAt'] == decoder['State']['StartedAt'],
            'Decoder container identity or running generation changed')
    for row in list(evidence.values()):
        require(fp(row['path']) == row, 'Reviewed evidence changed before completion')
    report = {'schema_version': 1, 'status': 'passed_readonly_native58_postexecution_review', 'must_fix': [],
        'reviewed_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'review_source': review_source,
        'native58_plan_sha256': plan['plan_sha256'], 'actual_parent_wait': fp(exit_path),
        'image_id': IMAGE, 'models': origin['models'], 'poses': poses, 'evidence_fingerprints': list(evidence.values()),
        'host_control': actual_parent['host_control'], 'control_revision': 4,
        'counts': {'cases': case_count, 'workers': 116, 'host_maps': len(mappings), 'full_decodes': len(decode_rows), 'cpu_ort_cases': 60},
        'independent_cpu_decodes': decode_rows,
        'decoder_container': {'id': decoder['Id'], 'image': decoder['Image'], 'started_at': decoder['State']['StartedAt'],
                              'mounts': decoder['Mounts'], 'runtime': decoder['HostConfig']['Runtime'],
                              'network_mode': decoder['HostConfig']['NetworkMode']},
        'quality_verified': False, 'obstacle_course_completion_verified': False,
        'scope': 'Read-only original parent, exact pair/pose, frozen inputs, worker receipts, host birth maps and fresh CPU full video decode; no rollout/training/GPU.'}
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'review': fp(output), 'counts': report['counts']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'transfer', 'parent-exit', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--decode-container', required=True)
    parser.add_argument('--parent-exit-sha256', required=True, help='Actual original e238 process-exit SHA; new argv/schema is retained truthfully')
    verify(parser.parse_args())


if __name__ == '__main__':
    main()
