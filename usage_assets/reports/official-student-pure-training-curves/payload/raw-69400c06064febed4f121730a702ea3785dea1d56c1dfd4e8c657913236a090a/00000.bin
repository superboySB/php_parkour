#!/usr/bin/env python3
"""Own an isolated, SHA-bound student scalar extract/plot CPU invocation."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
PINS = {'extract_student_scalars.py': 'e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12',
        'plot_student_learning_curves.py': '6a14cfa86df96199e575384c48466d44046b1a2fad8ce76c1427b7d5add7abd0'}

def require(condition, message):
    if not condition: raise ValueError(message)

def fp(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(x.is_symlink() for x in (path, *path.parents)) and path.is_file(), 'Regular normalized input required')
    before = path.stat(); digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8388608), b''): digest.update(data)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'File changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--phase-source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    code = Path(__file__).absolute().parent
    inputs, base = args.input.absolute(), args.output.absolute()
    control, artifacts = inputs / 'control', inputs / 'artifacts'
    require(not base.exists() and '..' not in base.parts and not any(x.is_symlink() for x in (base, *base.parents)), 'Fresh output required')
    require(not base.is_relative_to(inputs) and not inputs.is_relative_to(base) and
            not base.is_relative_to(code) and not code.is_relative_to(base), 'Output and original inputs/source must be separate')
    source_before = [fp(code / name) for name in [*PINS, 'run_phases.py', 'run_cpu.py']]
    for row in source_before:
        if Path(row['path']).name in PINS: require(row['sha256'] == PINS[Path(row['path']).name], 'Reviewed producer changed')
    require(fp(code / 'run_phases.py')['sha256'] == args.phase_source_sha256, 'Reviewed phase driver differs')
    contract = fp(control / 'input-contract.json')
    require(contract['sha256'] == args.contract_sha256, 'Reviewed actual input contract differs')
    payload = json.loads((control / 'input-contract.json').read_bytes())
    require(payload['kind'] in ('pure', 'finetune'), 'Actual student kind required')
    base.mkdir(parents=True); logs = base / 'host'; logs.mkdir(); validation = base / 'validation'; validation.mkdir()
    token = uuid.uuid4().hex; name = 'php-student-curves-' + token[:12]
    report = {'schema_version': 1, 'status': 'running', 'kind': payload['kind'], 'image': IMAGE,
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'ownership_token': token,
        'container_id': None, 'commands': [], 'cpu_raw_logs': {}, 'source_before': source_before,
        'source_after': None, 'source_unchanged': False, 'input_contract': contract,
        'create_actual_returncode': None, 'actual_start_attached_wait_returncode': None,
        'actual_container_exit_code': None, 'container_running': None,
        'student_training_scalars_verified': False, 'official_schedule_complete': False,
        'quality_verified': False, 'convergence_verified': False}
    def command(label, argv):
        out, err = logs / (label + '.stdout'), logs / (label + '.stderr')
        with out.open('xb') as stdout, err.open('xb') as stderr:
            result = subprocess.run(argv, stdout=stdout, stderr=stderr)
        row = {'label': label, 'argv': argv, 'actual_wait_returncode': result.returncode,
               'stdout': fp(out), 'stderr': fp(err)}; report['commands'].append(row)
        if label == 'create':
            report['create_actual_returncode'] = result.returncode
            report['cpu_raw_logs'].update(create_stdout=row['stdout'], create_stderr=row['stderr'])
        require(result.returncode == 0, label + ' actual child wait failed')
        return out.read_bytes()
    def inspect(label):
        value = json.loads(command(label, ['docker', 'inspect', report['container_id']]))[0]
        host, env = value['HostConfig'], dict(item.split('=', 1) for item in value['Config']['Env'])
        require(value['Id'] == report['container_id'] and value['Image'] == IMAGE and
            value['Config']['Image'] == IMAGE and value['Config']['Labels'].get('php.curves.owner') == token,
            'Owned container identity/image differs')
        require(host['Runtime'] == 'runc' and host['NetworkMode'] == 'none' and
            host['NanoCpus'] == 2000000000 and host['Memory'] == 12884901888 and
            host['Privileged'] is False and not host.get('DeviceRequests') and not host.get('Devices') and
            env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void' and
            env.get('PYTHONDONTWRITEBYTECODE') == '1', 'CPU isolation differs')
        mounts = {(x['Source'], x['Destination'], x['RW']) for x in value['Mounts'] if x['Type'] == 'bind'}
        require(len(value['Mounts']) == 4 and mounts == {(str(code), '/code', False), (str(control), '/control', False),
            (str(artifacts), '/artifacts', False), (str(validation), '/validation', True)}, 'Exact three RO and one RW mounts required')
        require(value['State']['OOMKilled'] is False and value['State']['Error'] == '', 'Container OOM/runtime error')
        return value
    try:
        argv = ['docker', 'create', '--name', name, '--label', 'php.curves.owner=' + token,
            '--runtime', 'runc', '--network', 'none', '--cpus', '2', '--memory', '12g', '--pids-limit', '256',
            '--env', 'CUDA_VISIBLE_DEVICES=', '--env', 'NVIDIA_VISIBLE_DEVICES=void', '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'HOME=/tmp',
            '--mount', 'type=bind,src=' + str(code) + ',dst=/code,readonly',
            '--mount', 'type=bind,src=' + str(control) + ',dst=/control,readonly',
            '--mount', 'type=bind,src=' + str(artifacts) + ',dst=/artifacts,readonly',
            '--mount', 'type=bind,src=' + str(validation) + ',dst=/validation',
            '--entrypoint', '/opt/php/bin/train-python', IMAGE, '-B', '/code/run_phases.py',
            '--contract-sha256', args.contract_sha256]
        cid = command('create', argv).decode().strip()
        require(len(cid) == 64 and all(c in '0123456789abcdef' for c in cid), 'Actual create did not return full CID')
        report['container_id'] = cid
        created = inspect('inspect-created'); require(created['State']['Status'] == 'created', 'Already started')
        attached_out, attached_err = logs / 'attached.stdout', logs / 'attached.stderr'
        attached_argv = ['docker', 'start', '-a', cid]; live = None
        with attached_out.open('xb') as stdout, attached_err.open('xb') as stderr:
            process = subprocess.Popen(attached_argv, stdout=stdout, stderr=stderr)
            report['attached_pid'] = process.pid
            try:
                for attempt in range(20):
                    if process.poll() is not None: break
                    current = inspect('inspect-live-' + str(attempt))
                    if current['State']['Running']:
                        live = current; report['running_inspect_label'] = 'inspect-live-' + str(attempt); break
                    time.sleep(0.1)
            finally:
                report['actual_start_attached_wait_returncode'] = process.wait()
                stdout.flush(); stderr.flush()
                report['cpu_raw_logs'].update(attached_stdout=fp(attached_out), attached_stderr=fp(attached_err))
                report['commands'].append({'label': 'attached', 'argv': attached_argv,
                    'actual_wait_returncode': report['actual_start_attached_wait_returncode'],
                    'stdout': fp(attached_out), 'stderr': fp(attached_err)})
        final = inspect('inspect-final')
        report.update(actual_container_exit_code=final['State']['ExitCode'], container_running=final['State']['Running'])
        require(report['actual_start_attached_wait_returncode'] == 0 and live is not None and
            final['State']['Status'] == 'exited' and report['actual_container_exit_code'] == 0 and
            report['container_running'] is False and live['State']['StartedAt'] == final['State']['StartedAt'],
            'Actual CPU phase driver did not naturally exit0')
        phases = json.loads((validation / 'phases.json').read_bytes())
        require(phases['status'] == 'passed' and phases['inputs_unchanged'] is True and
            phases['inputs_before'] == phases['inputs_after'] and phases['inputs_before'] and
            [x['phase'] for x in phases['phases']] == ['extract', 'plot'] and
            all(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode'] == 0 for x in phases['phases']),
            'Both actual CPU stages must pass with unchanged original inputs')
        report['phases_report'] = fp(validation / 'phases.json')
        report['source_after'] = [fp(row['path']) for row in source_before]
        require(report['source_after'] == source_before and fp(contract['path']) == contract, 'Source or actual contract changed')
        report.update(status='passed_student_learning_curves_CPU', source_unchanged=True, student_training_scalars_verified=True)
    except Exception as error:
        report.update(status='failed_partial_preserved', error=type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        with (logs / 'execution.json').open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'status': report['status'], 'container_id': report['container_id'],
        'actual_attached_wait': report['actual_start_attached_wait_returncode'], 'execution': str(logs / 'execution.json')}))
    return 0 if report['status'] == 'passed_student_learning_curves_CPU' else 1

if __name__ == '__main__': raise SystemExit(main())
