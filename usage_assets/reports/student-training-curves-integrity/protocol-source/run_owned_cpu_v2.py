#!/usr/bin/env python3
"""Own one isolated protocol-only Docker invocation and preserve its actual waits."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
MANIFEST_SHA = 'c16c627c310c07bce1ed3c3bea8e026d43fe5c53911857e5b700404b7d92aa22'
EVENT = Path('/home/dzp/projects/php_parkour/outputs/research/official-full/teacher-high-climb-76-final-01/artifacts/events.out.tfevents.1791793401.pro5000-6.135317.0')

def require(value, message):
    if not value:
        raise ValueError(message)

def fp(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file(), 'Regular source required')
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            digest.update(chunk)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Input changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}

def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = args.output.absolute()
    require(not base.exists() and not any(p.is_symlink() for p in (base, *base.parents)), 'Fresh normalized output required')
    base.mkdir(parents=True)
    logs = base / 'host-logs'; logs.mkdir()
    validation = base / 'validation'; validation.mkdir()
    code = Path(__file__).absolute().parent
    manifest_fp = fp(code / 'source-manifest.json')
    require(manifest_fp['sha256'] == MANIFEST_SHA, 'Frozen source manifest changed')
    manifest = json.loads((code / 'source-manifest.json').read_bytes())
    sources = [manifest_fp, fp(Path(__file__).absolute())]
    for row in manifest['files']:
        path = code / row['path']
        require('..' not in Path(row['path']).parts and not Path(row['path']).is_absolute(), 'Unsafe manifest path')
        actual = fp(path)
        require(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'], 'Frozen dependency changed')
        sources.append(actual)
    event = fp(EVENT)
    require(event['bytes'] == 72561360 and event['sha256'] == 'ca8621a8c9919f27c3bfd0e397ba4d425f3eb5904ed0f797e5eed5b6b6cd0478', 'Original event changed')
    sources.append(event)
    token = uuid.uuid4().hex
    name = 'php-student-tfrecord-protocol-' + token[:12]
    report = {'schema_version': 1, 'phase': 'tfrecord_protocol_validation', 'status': 'running',
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'owner_pid': os.getpid(),
        'ownership_token': token, 'container_name': name, 'image': IMAGE,
        'input_sources_before': sources, 'input_sources_after': None, 'commands': [],
        'container_id': None, 'attached_actual_wait': None, 'observed_live': False,
        'student_training_completed': False, 'student_training_scalars_verified': False,
        'official_schedule_complete': False, 'quality_verified': False, 'convergence_verified': False}
    def command(label, argv):
        out, err = logs / (label + '.stdout'), logs / (label + '.stderr')
        with out.open('xb') as stdout, err.open('xb') as stderr:
            completed = subprocess.run(argv, stdout=stdout, stderr=stderr, check=False)
        report['commands'].append({'label': label, 'argv': argv, 'actual_wait': completed.returncode,
            'stdout': fp(out), 'stderr': fp(err)})
        require(completed.returncode == 0, label + ' actual child wait nonzero')
        return out.read_bytes()
    def inspect(label):
        raw = command(label, ['docker', 'inspect', report['container_id']])
        value = json.loads(raw)[0]
        cfg, host = value['Config'], value['HostConfig']
        env = dict(item.split('=', 1) for item in cfg['Env'] if '=' in item)
        require(value['Id'] == report['container_id'] and value['Image'] == IMAGE and
            cfg['Labels'].get('php.protocol.owner') == token, 'Container ownership differs')
        require(host['Runtime'] == 'runc' and host['NetworkMode'] == 'none' and
            host['NanoCpus'] == 2000000000 and host['Memory'] == 12884901888 and
            not host.get('DeviceRequests') and not host.get('Devices') and
            not host.get('Privileged') and env.get('CUDA_VISIBLE_DEVICES') == '' and
            env.get('NVIDIA_VISIBLE_DEVICES') == 'void', 'CPU isolation differs')
        actual_mounts = {(m['Source'], m['Destination'], m['RW']) for m in value['Mounts'] if m['Type'] == 'bind'}
        require(actual_mounts == {(str(code), '/code', False), (str(EVENT), '/artifacts/' + EVENT.name, False),
            (str(validation), '/validation', True)}, 'Input/output mounts differ')
        require(not value['State']['OOMKilled'] and not value['State']['Error'], 'Container OOM/error')
        return value
    try:
        plan = json.loads((code / 'protocol-plan.json').read_bytes())
        argv = ['docker', 'create', '--name', name, '--label', 'php.protocol.owner=' + token,
            '--runtime', 'runc', '--network', 'none', '--cpus', '2', '--memory', '12g', '--pids-limit', '256',
            '--env', 'CUDA_VISIBLE_DEVICES=', '--env', 'NVIDIA_VISIBLE_DEVICES=void',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'HOME=/tmp',
            '--mount', 'type=bind,src=' + str(code) + ',dst=/code,readonly',
            '--mount', 'type=bind,src=' + str(EVENT) + ',dst=/artifacts/' + EVENT.name + ',readonly',
            '--mount', 'type=bind,src=' + str(validation) + ',dst=/validation',
            '--entrypoint', plan['future_cli'][0], IMAGE, *plan['future_cli'][1:]]
        cid = command('create', argv).decode().strip()
        require(len(cid) == 64 and all(c in '0123456789abcdef' for c in cid), 'Actual create returned no CID')
        report['container_id'] = cid
        before = inspect('inspect-created')
        require(before['State']['Status'] == 'created', 'Container already started')
        attached_out, attached_err = logs / 'attached.stdout', logs / 'attached.stderr'
        attached_argv = ['docker', 'start', '-a', cid]
        with attached_out.open('xb') as stdout, attached_err.open('xb') as stderr:
            process = subprocess.Popen(attached_argv, stdout=stdout, stderr=stderr)
            report['attached_pid'] = process.pid
            try:
                for attempt in range(20):
                    if process.poll() is not None:
                        break
                    live = inspect('inspect-live-' + str(attempt))
                    if live['State']['Running']:
                        report['observed_live'] = True
                        break
                    time.sleep(0.1)
            finally:
                # An inspection failure must still reap the process we own.
                # Preserve that failure; wait for natural exit without retry/kill.
                report['attached_actual_wait'] = process.wait()
                stdout.flush(); stderr.flush()
                report['commands'].append({'label': 'attached', 'argv': attached_argv,
                    'actual_wait': report['attached_actual_wait'], 'stdout': fp(attached_out), 'stderr': fp(attached_err)})
        final = inspect('inspect-final')
        require(report['attached_actual_wait'] == 0 and report['observed_live'] and
            final['State']['Status'] == 'exited' and not final['State']['Running'] and
            final['State']['ExitCode'] == 0, 'Protocol phase did not naturally complete with zero')
        protocol_fp = fp(validation / 'protocol.json')
        protocol = json.loads((validation / 'protocol.json').read_bytes())
        require(protocol['status'] == 'passed_protocol_validation' and
            protocol['phase'] == 'tfrecord_protocol_validation' and protocol['input_sources_unchanged'] is True and
            len(protocol['synthetic_protocol_fixture_cases']) == 20 and
            all(r['outcome_matches_expected'] for r in protocol['synthetic_protocol_fixture_cases']) and
            len(protocol['known_vectors']) == 3 and all(r['matched'] for r in protocol['known_vectors']) and
            protocol['real_teacher_event']['result']['status'] == 'passed' and
            all(protocol.get(k) is False for k in ('student_training_completed', 'student_training_scalars_verified',
                'official_schedule_complete', 'quality_verified', 'convergence_verified')), 'Protocol report failed or exceeds scope')
        report['protocol_report'] = protocol_fp
        report['input_sources_after'] = [fp(row['path']) for row in sources]
        require(report['input_sources_after'] == sources, 'Host source or original event changed')
        report['status'] = 'passed_protocol_validation'
    except Exception as error:
        report['status'] = 'failed_protocol_validation'
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(base / 'execution.json', report)
    print(json.dumps({'status': report['status'], 'container_id': report['container_id'],
        'attached_actual_wait': report['attached_actual_wait'], 'execution_report': str(base / 'execution.json')}))
    return 0 if report['status'] == 'passed_protocol_validation' else 1

if __name__ == '__main__':
    raise SystemExit(main())
