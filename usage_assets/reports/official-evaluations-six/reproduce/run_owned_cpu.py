#!/usr/bin/env python3
"""Own one SHA-bound CPU validation of transferred native evaluation evidence."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'

def require(value, message):
    if not value:
        raise ValueError(message)

def normalized(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            'Normalized paths without symlinks required: ' + str(path))
    return path

def fp(path):
    path = normalized(path)
    require(path.is_file(), 'Regular file required: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8388608), b''):
            digest.update(data)
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')
    require(all(getattr(before, k) == getattr(after, k) for k in keys), 'File changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest(), 'mode': after.st_mode & 0o777}

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--validator-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    code, inputs, base = normalized(Path(__file__).parent), normalized(args.input), normalized(args.output)
    require(not base.exists(), 'Fresh output required')
    require(not any(a.is_relative_to(b) for a, b in ((base, inputs), (inputs, base), (base, code), (code, base))),
            'Output, input and code must be separate')
    control, artifacts = inputs / 'control', inputs / 'artifacts'
    source_paths = [code / name for name in ('run_owned_cpu.py', 'validate.py', 'run_owned_cpu.source-manifest.json')]
    base.mkdir(parents=True)
    logs, results = base / 'host', base / 'results'
    logs.mkdir(); results.mkdir()
    token = str(uuid.uuid4())
    name = 'php-official-eval-cpu-' + token[:12]
    report = {'schema_version': 2, 'status': 'running', 'actualpassed': False, 'image': IMAGE,
              'owner_uuid': token, 'container_name': name, 'container_id': None,
              'started_utc': stamp(), 'commands': [], 'errors': [], 'source_before': [], 'source_after': [],
              'input_before': [], 'input_after': [], 'source_unchanged': False, 'inputs_unchanged': False,
              'create_actual_returncode': None, 'actual_start_attached_wait_returncode': None,
              'actual_container_exit_code': None, 'container_running': None,
              'quality_verified': False, 'full': False, 'convergence_verified': False,
              'official_schedule_complete': False, 'validated_saved_evaluation_evidence': False}
    selected, live, final, attached = [], None, None, None
    def failure(error):
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    def command(label, argv):
        out, err = logs / (label + '.stdout.raw'), logs / (label + '.stderr.raw')
        row = {'label': label, 'command': argv, 'actual_wait_returncode': None}
        report['commands'].append(row)
        try:
            with out.open('xb') as stdout, err.open('xb') as stderr:
                result = subprocess.run(argv, stdout=stdout, stderr=stderr, check=False)
                row['actual_wait_returncode'] = result.returncode
        finally:
            row.update(stdout=fp(out), stderr=fp(err))
        if label == 'create':
            report['create_actual_returncode'] = row['actual_wait_returncode']
        require(row['actual_wait_returncode'] == 0, label + ' actual child wait failed')
        return out.read_bytes()
    def inspect(label):
        value = json.loads(command(label, ['docker', 'inspect', report['container_id']]))[0]
        host, state = value['HostConfig'], value['State']
        env = dict(item.split('=', 1) for item in value['Config']['Env'])
        require(value['Id'] == report['container_id'] and value['Name'] == '/' + name and
                value['Image'] == IMAGE and value['Config']['Image'] == IMAGE and
                value['Config']['Labels'].get('php.official-evaluation.owner') == token and value['RestartCount'] == 0,
                'Owned container CID/name/image/UUID differs')
        require(host['Runtime'] == 'runc' and host['NetworkMode'] == 'none' and
                host['NanoCpus'] == 2000000000 and host['Memory'] == 12884901888 and
                host['PidsLimit'] == 256 and host['Privileged'] is False and
                not host.get('Devices') and not host.get('DeviceRequests') and
                host['RestartPolicy'] == {'Name': 'no', 'MaximumRetryCount': 0} and env.get('CUDA_VISIBLE_DEVICES') == '' and
                env.get('NVIDIA_VISIBLE_DEVICES') == 'void' and env.get('PYTHONDONTWRITEBYTECODE') == '1',
                'CPU isolation/resources differ')
        mounts = {(m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Type'] == 'bind'}
        require(len(value['Mounts']) == 4 and mounts == {(str(code), '/code', False),
                (str(control), '/control', False), (str(artifacts), '/artifacts', False),
                (str(results), '/results', True)}, 'Exact four RO/RO/RO/RW binds required')
        require(state['OOMKilled'] is False and state['Error'] == '', 'Container OOM/runtime error')
        report[label] = {'container_id': value['Id'], 'image': value['Image'], 'name': value['Name'],
                         'started_at': state['StartedAt'], 'state': state, 'host_config': host, 'mounts': value['Mounts']}
        return value
    def child_ok(value):
        return type(value.get('returncode')) is int and value['returncode'] == 0 and value['failure'] is None
    try:
        for digest in (args.contract_sha256, args.validator_sha256):
            require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Actual lowercase SHA256 required')
        report['source_before'] = [fp(path) for path in source_paths]
        frozen = json.loads(source_paths[2].read_bytes())['source']
        require(frozen['path'] == 'run_owned_cpu.py' and frozen['sha256'] == report['source_before'][0]['sha256'] and
                frozen['bytes'] == report['source_before'][0]['bytes'], 'Frozen host executor source differs')
        require(report['source_before'][1]['sha256'] == args.validator_sha256, 'Reviewed validator source differs')
        contract = fp(control / 'input-contract.json')
        report['input_before'].append(contract)
        require(contract['sha256'] == args.contract_sha256, 'Reviewed actual contract differs')
        payload = json.loads((control / 'input-contract.json').read_bytes())
        require(payload['schema_version'] == 1 and len(payload['stages']) == 6, 'Six native stages required')
        def records(value):
            if isinstance(value, dict):
                if {'path', 'sha256', 'bytes'} <= value.keys():
                    yield value
                else:
                    for item in value.values():
                        yield from records(item)
            elif isinstance(value, list):
                for item in value:
                    yield from records(item)
        entries = sorted(records(payload), key=lambda row: row['path'])
        require(len(entries) == 196 and len({row['path'] for row in entries}) == 196, '196 unique selected native artifacts required')
        for entry in entries:
            p = Path(entry['path'])
            require(p.is_absolute() and p.parts[:2] == ('/', 'artifacts') and '..' not in p.parts and
                    entry['native_path'] == '/outputs/' + p.relative_to('/artifacts').as_posix(), 'Native path binding differs')
            path = normalized(artifacts / p.relative_to('/artifacts'))
            selected.append(path)
            value = fp(path)
            report['input_before'].append(value)
            require(value['sha256'] == entry['sha256'] and value['bytes'] == entry['bytes'], 'Transferred native bytes differ')
        videos = [v for s in payload['stages'] for v in s['videos']]
        require(len(videos) == 160 and sum(v['quality_bound'] is True for v in videos) == 148 and
                all(v['native_described'] is True for v in videos), 'Native video selection differs')
        require([fp(path) for path in source_paths] == report['source_before'] and
                fp(control / 'input-contract.json') == contract, 'Reviewed source/contract changed before create')
        argv = ['docker', 'create', '--name', name, '--label', 'php.official-evaluation.owner=' + token,
                '--runtime', 'runc', '--network', 'none', '--cpus', '2', '--memory', '12g',
                '--pids-limit', '256', '--restart', 'no', '--env', 'CUDA_VISIBLE_DEVICES=',
                '--env', 'NVIDIA_VISIBLE_DEVICES=void', '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'HOME=/tmp']
        for source, destination, readonly in ((code, '/code', True), (control, '/control', True),
                                               (artifacts, '/artifacts', True), (results, '/results', False)):
            argv += ['--mount', 'type=bind,src=' + str(source) + ',dst=' + destination + (',readonly' if readonly else '')]
        argv += ['--entrypoint', '/opt/php/bin/train-python', IMAGE, '-B', '/code/validate.py',
                 '--contract-sha256', args.contract_sha256, '--source-sha256', args.validator_sha256]
        cid = command('create', argv).decode().strip()
        require(len(cid) == 64 and all(c in '0123456789abcdef' for c in cid), 'Create did not return actual full CID')
        report['container_id'] = cid
        created = inspect('inspect-created')
        require(created['State']['Status'] == 'created' and created['State']['StartedAt'].startswith('0001-'), 'Container already started')
        out, err = logs / 'attached.stdout.raw', logs / 'attached.stderr.raw'
        row = {'label': 'attached', 'command': ['docker', 'start', '-a', cid], 'actual_wait_returncode': None}
        report['commands'].append(row)
        with out.open('xb') as stdout, err.open('xb') as stderr:
            attached = subprocess.Popen(row['command'], stdout=stdout, stderr=stderr)
            try:
                report['attached_pid'] = attached.pid
                for attempt in range(20):
                    if attached.poll() is not None:
                        break
                    current = inspect('inspect-live-' + str(attempt))
                    if current['State']['Running']:
                        live = current
                        break
                    time.sleep(0.1)
            finally:
                while True:
                    try:
                        row['actual_wait_returncode'] = attached.wait()
                        break
                    except KeyboardInterrupt as error:
                        failure(error)
                report['actual_start_attached_wait_returncode'] = row['actual_wait_returncode']
                stdout.flush(); stderr.flush()
                row.update(stdout=fp(out), stderr=fp(err))
    except BaseException as error:
        failure(error)
    finally:
        if attached is not None:
            try:
                final = inspect('inspect-final')
                state = final['State']
                report.update(actual_container_exit_code=state['ExitCode'], container_running=state['Running'])
                require(report['actual_start_attached_wait_returncode'] == 0 and live is not None and
                        state['Status'] == 'exited' and state['ExitCode'] == 0 and state['Running'] is False and
                        not live['State']['StartedAt'].startswith('0001-') and
                        state['StartedAt'] == live['State']['StartedAt'], 'One actual CPU container did not naturally exit0')
                validation = json.loads((results / 'report.json').read_bytes())
                require(validation['status'] == 'passed' and validation['quality_verified'] is False and validation['full'] is False,
                        'Actual validator report failed or claimed full quality')
                require(validation['errors'] == [] and validation['source_before']['sha256'] == args.validator_sha256 and
                        validation['contract_before']['sha256'] == args.contract_sha256, 'Actual validator admission differs')
                for before, after in (('source_before', 'source_after'), ('contract_before', 'contract_after'), ('input_before', 'input_after')):
                    require(validation[before] and validation[before] == validation[after], 'Validator source/input changed')
                require(validation['input_before']['failures'] == [] and len(validation['input_before']['files']) == 196,
                        'Actual validator input snapshot incomplete')
                require(validation['counts'] == {'stages': 6, 'videos_attempted': 160, 'videos_passed': 160}, 'Actual validator counts differ')
                for program in ('ffmpeg', 'ffprobe'):
                    version = json.loads((results / (program + '-version.execution.json')).read_bytes())
                    require(child_ok(version) and version['command'] == [program, '-version'], 'Version actual child wait failed')
                stages = validation['stages']
                require(len(stages) == 6, 'Six actual validated stages required')
                observed = []
                for stage in stages:
                    require(all(stage[key]['status'] == 'passed' for key in ('native_quality', 'saved_yaml', 'tensorboard', 'representative_thumbnail')),
                            'Actual stage phase failed')
                    tensorboard = stage['tensorboard']['value']
                    integrity = tensorboard['event_integrity']['events']
                    require(tensorboard['event_integrity_complete'] is True and len(integrity) == 1 and
                            all(e['status'] == 'passed' and e['complete_eof'] is True and e['crc32c_verified'] is True for e in integrity),
                            'Strict original TFRecord CRC32C/complete EOF gate failed')
                    require(child_ok(stage['representative_thumbnail']['value']['execution']), 'Thumbnail actual child wait failed')
                    observed.extend(stage['videos'])
                require(len(observed) == 160 and all(v['status'] == 'passed' and child_ok(v['ffprobe']) and child_ok(v['ffmpeg']) and
                        type(v['probed_frames']) is int and v['probed_frames'] > 0 and type(v['decoded_frames']) is int and
                        v['decoded_frames'] == v['probed_frames'] and
                        v['progress_end'] is True for v in observed), 'Video CPU child/decode evidence incomplete')
                report['validator_report'] = fp(results / 'report.json')
                report['validated_saved_evaluation_evidence'] = True
            except BaseException as error:
                failure(error)
        for path in source_paths:
            try:
                report['source_after'].append(fp(path))
            except BaseException as error:
                failure(error)
        for path in (control / 'input-contract.json', *selected):
            try:
                report['input_after'].append(fp(path))
            except BaseException as error:
                failure(error)
        report['source_unchanged'] = bool(report['source_before']) and report['source_before'] == report['source_after']
        report['inputs_unchanged'] = len(report['input_before']) == 197 and report['input_before'] == report['input_after']
        if not report['source_unchanged'] or not report['inputs_unchanged']:
            report['errors'].append('Source or all 196 selected native artifacts plus actual contract changed/incomplete')
        report['actualpassed'] = not report['errors'] and report['validated_saved_evaluation_evidence']
        report['status'] = 'passed_official_evaluation_CPU' if report['actualpassed'] else 'failed_partial_preserved'
        report['finished_utc'] = stamp()
        with (logs / 'execution.json').open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({'status': report['status'], 'container_id': report['container_id'],
                      'actual_attached_wait': report['actual_start_attached_wait_returncode'], 'execution': str(logs / 'execution.json')}))
    return 0 if report['actualpassed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
