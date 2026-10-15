#!/usr/bin/env python3
"""Read-only TensorBoard listener/events/HTTP checks. Never starts a service."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
from urllib.request import urlopen


def require(value, message):
    if not value: raise ValueError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''): result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False); stream.write('\n')


def record(path):
    return {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': sha(path)}


def status_values(raw, name):
    lines = [line for line in raw.splitlines() if line.startswith(name + ':')]
    require(len(lines) == 1, 'Missing/duplicate proc status field: ' + name)
    return [int(value) for value in lines[0].split(':', 1)[1].split()]


def own_uid(raw):
    uids = status_values(raw, 'Uid')
    return len(uids) == 4 and all(uid == os.geteuid() for uid in uids)


def port_snapshot(port, proc_root=Path('/proc')):
    sockets, owners = [], []
    for table in ('tcp', 'tcp6'):
        path = proc_root / 'net' / table
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            if int(fields[1].split(':')[1], 16) == port and fields[3] == '0A':
                sockets.append({'table': table, 'local_address': fields[1], 'inode': fields[9], 'uid': int(fields[7])})
    inodes = {row['inode'] for row in sockets}
    if inodes:
        for proc in proc_root.glob('[0-9]*'):
            try:
                status = (proc / 'status').read_text()
                # Host UID1000 never attempts root-owned fd/ns. Container
                # probe runs only in the exact reviewed CID as container UID0.
                if not own_uid(status):
                    continue
                bound = []
                for fd in (proc / 'fd').iterdir():
                    try: target = os.readlink(fd)
                    except OSError: continue
                    if target.startswith('socket:[') and target[8:-1] in inodes: bound.append(target[8:-1])
                if bound:
                    raw = (proc / 'stat').read_text(); fields = raw[raw.rfind(')') + 2:].split()
                    identity = {'pid': int(proc.name), 'start_time_clock_ticks': int(fields[19]), 'state': fields[0],
                        'argv': (proc / 'cmdline').read_bytes().decode().rstrip('\0').split('\0'), 'socket_inodes': sorted(set(bound)),
                        'pid_namespace': os.readlink(proc / 'ns/pid'), 'status_raw': status}
                    after = (proc / 'stat').read_text(); identity['stable_birth'] = int(after[after.rfind(')') + 2:].split()[19]) == identity['start_time_clock_ticks']
                    owners.append(identity)
            except (OSError, ValueError): continue
    return {'observed_utc': now(), 'port': port, 'host_boot_id': (proc_root / 'sys/kernel/random/boot_id').read_text().strip(),
            'listeners': sockets, 'owners': owners, 'unowned_inodes': sorted(inodes - {item for owner in owners for item in owner['socket_inodes']})}


def host_birth(pid, proc_root=Path('/proc')):
    """Only world-readable stat/status; no host root fd/ns/cmdline access."""
    proc = proc_root / str(pid)
    first = (proc / 'stat').read_text()
    fields = first[first.rfind(')') + 2:].split()
    status = (proc / 'status').read_text()
    second = (proc / 'stat').read_text()
    after = second[second.rfind(')') + 2:].split()
    require(first.split(' ', 1)[0] == second.split(' ', 1)[0] == str(pid)
            and fields[19] == after[19] and fields[0] != 'Z' and after[0] != 'Z', 'Host proc birth changed or zombie')
    require(status_values(status, 'Pid') == status_values(status, 'Tgid') == [pid], 'Host PID/TGID differs')
    return {'pid': pid, 'start_time_clock_ticks': int(fields[19]), 'state': after[0],
            'nspid': status_values(status, 'NSpid'), 'nstgid': status_values(status, 'NStgid'),
            'stat_before_raw': first, 'stat_after_raw': second, 'status_raw': status, 'stable_birth': True}


def normalized_mounts(rows):
    """Preserve complete rows; only unique-Destination ordering is irrelevant."""
    require(type(rows) is list and all(type(row) is dict and type(row.get('Destination')) is str for row in rows)
            and len({row['Destination'] for row in rows}) == len(rows), 'Unique complete adopted-container Mounts rows required')
    return sorted(rows, key=lambda row: row['Destination'])


def container_identity(info):
    return {'id': info['Id'], 'image': info['Image'], 'started_at': info['State']['StartedAt'],
            'host_init_pid': info['State']['Pid'], 'config': info['Config'], 'mounts': normalized_mounts(info['Mounts']),
            'network_mode': info['HostConfig']['NetworkMode'], 'pid_mode': info['HostConfig'].get('PidMode', '')}


def probe_source():
    """The same reviewed stdlib port reader, executed inside exact newCID."""
    source = 'import datetime,json,os\nfrom pathlib import Path\n'
    source += '\n'.join(inspect.getsource(fn) for fn in (require, now, status_values, own_uid, port_snapshot))
    source += '''
require(os.geteuid() == 0, 'Exact container UID0 read-only proc probe required')
raw = Path('/proc/1/stat').read_text()
fields = raw[raw.rfind(')') + 2:].split()
init = {'pid': 1, 'start_time_clock_ticks': int(fields[19]), 'stat_raw': raw,
        'status_raw': Path('/proc/1/status').read_text(), 'pid_namespace': os.readlink('/proc/1/ns/pid')}
require(fields[0] != 'Z' and status_values(init['status_raw'], 'Pid') == status_values(init['status_raw'], 'Tgid') == [1]
        and status_values(init['status_raw'], 'NSpid') == status_values(init['status_raw'], 'NStgid') == [1], 'Private container init PID/status differs')
snapshot = port_snapshot(6006)
after = Path('/proc/1/stat').read_text()
require(int(after[after.rfind(')') + 2:].split()[19]) == init['start_time_clock_ticks'], 'Container init birth changed')
require(all(owner['pid_namespace'] == init['pid_namespace'] for owner in snapshot['owners']), 'Owner is outside container init PID namespace')
print(json.dumps({'schema_version': 1, 'effective_uid': os.geteuid(), 'init': init, 'snapshot': snapshot}, allow_nan=False))
'''
    return source.encode()


def docker_read(argv, output, name, data=None):
    timed_out = False
    try:
        completed = subprocess.run(argv, input=data, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        timed_out = True
        completed = type('TimeoutResult', (), {'stdout': error.stdout or b'', 'stderr': error.stderr or b'', 'returncode': None})()
    stdout, stderr = output / (name + '.stdout.raw'), output / (name + '.stderr.raw')
    with stdout.open('xb') as stream: stream.write(completed.stdout)
    with stderr.open('xb') as stream: stream.write(completed.stderr)
    receipt = {'argv': argv, 'actual_wait_returncode': completed.returncode, 'timeout_seconds': 30, 'timed_out': timed_out,
               'stdout': record(stdout), 'stderr': record(stderr)}
    if data is not None:
        source = output / (name + '.stdin.py')
        with source.open('xb') as stream: stream.write(data)
        receipt['stdin'] = record(source)
    save(output / (name + '.execution.json'), receipt)
    require(not timed_out and completed.returncode == 0, 'Read-only Docker observation failed: ' + name)
    return completed.stdout, receipt


def top_pids(raw):
    rows = raw.decode().splitlines()
    require(rows and rows[0].split()[0] == 'PID', 'Docker top PID header differs')
    result = []
    for row in rows[1:]:
        if row.strip():
            value = row.split()[0]
            require(value.isdecimal() and int(value) > 0, 'Invalid Docker top host PID')
            result.append(int(value))
    require(result and len(result) == len(set(result)), 'Empty/duplicate Docker top host PID')
    return set(result)


def map_owner(probe, info, before_pids, after_pids, births):
    """Pure birth/NSpid join of exact-CID proc and Docker host PID inventory."""
    inside = probe['snapshot']
    require(probe['effective_uid'] == 0 and probe['init']['pid'] == 1
            and inside['port'] == 6006 and inside['listeners'] and not inside['unowned_inodes']
            and len(inside['owners']) == 1, 'Exact container listener ownership is ambiguous')
    init_pid = info['State']['Pid']
    require(init_pid in before_pids & after_pids and init_pid in births, 'Container host init absent from both Docker top observations')
    init = births[init_pid]
    require(init['nspid'] == init['nstgid'] == [init_pid, 1]
            and init['start_time_clock_ticks'] == probe['init']['start_time_clock_ticks'] and init['stable_birth'],
            'Host/container init birth or NSpid mapping differs')
    owner = inside['owners'][0]
    require(owner['stable_birth'] and owner['state'] != 'Z' and owner['pid_namespace'] == probe['init']['pid_namespace'], 'Container owner birth/namespace differs')
    matches = [birth for pid, birth in births.items() if pid in before_pids & after_pids
        and birth['nspid'] == birth['nstgid'] == [pid, owner['pid']]
        and birth['start_time_clock_ticks'] == owner['start_time_clock_ticks'] and birth['stable_birth']]
    require(len(matches) == 1, 'Listener must map to exactly one same-birth host PID from exact Docker CID')
    host = matches[0]
    return dict(owner, pid=host['pid'], container_pid=owner['pid'], container_id=info['Id'],
        container_started_at=info['State']['StartedAt'],
        mapping={'host_owner': host, 'host_init': init, 'container_owner': owner,
                 'container_init': probe['init'], 'scope': 'Exact CID docker top + host stat/status NSpid and same birth ticks; host root fd/ns never read.'})


def container_snapshot(cid, output, label):
    require(re.fullmatch('[0-9a-f]{64}', cid) is not None, 'Explicit full exact new CID required')
    def current(name):
        raw, receipt = docker_read(['docker', 'container', 'inspect', cid], output, label + '-' + name)
        data = json.loads(raw)
        require(type(data) is list and len(data) == 1, 'Ambiguous exact CID inspect')
        info = data[0]
        require(info['Id'] == cid and info['State']['Running'] is True and info['State']['Pid'] > 0
                and not info['State'].get('Restarting') and not info['State'].get('Paused')
                and info['State']['StartedAt'] and info['HostConfig']['NetworkMode'] == 'host'
                and info['HostConfig'].get('PidMode', '') == '', 'Running exact CID with private PID/host network required')
        return info, receipt
    first, inspect_before = current('inspect-before')
    raw, top_before = docker_read(['docker', 'top', cid, '-eo', 'pid,ppid,args'], output, label + '-top-before')
    first_pids = top_pids(raw)
    raw, exec_receipt = docker_read(['docker', 'exec', '--user', '0', '-i', cid, '/usr/bin/python3', '-B', '-'],
                                    output, label + '-container-probe', probe_source())
    probe = json.loads(raw)
    raw, top_after = docker_read(['docker', 'top', cid, '-eo', 'pid,ppid,args'], output, label + '-top-after')
    last_pids = top_pids(raw)
    births = {}
    for pid in sorted(first_pids & last_pids):
        try: births[pid] = host_birth(pid)
        except (OSError, ValueError): continue
    owner = map_owner(probe, first, first_pids, last_pids, births)
    last, inspect_after = current('inspect-after')
    require(container_identity(first) == container_identity(last), 'Exact container generation/config changed during listener observation')
    require(probe['snapshot']['host_boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'Container/host boot identity differs')
    return dict(probe['snapshot'], owners=[owner], unowned_inodes=[],
        container=container_identity(first), container_init_identity=probe['init'],
        read_only_docker={'inspect_before': inspect_before, 'top_before': top_before, 'container_probe': exec_receipt,
                          'top_after': top_after, 'inspect_after': inspect_after})


def events(root):
    require(not any(path.is_symlink() for path in (Path(root), *Path(root).parents)), 'Alias in original event root/ancestors')
    root = Path(root).resolve()
    require(root.is_dir(), 'Actual original event root is required')
    result = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Alias in original event tree')
        if path.is_file() and path.name.startswith('events.out.tfevents.'):
            result.append({'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
                           'mode': path.stat().st_mode & 0o777, 'sha256': sha(path)})
    require(result, 'Original TensorBoard events are missing')
    return result


def owner_guard(snapshot, args):
    require(snapshot['listeners'] and not snapshot['unowned_inodes'] and len(snapshot['owners']) == 1, 'Actual listener ownership is ambiguous')
    owner = snapshot['owners'][0]
    require(owner['pid'] == args.expected_pid and owner['start_time_clock_ticks'] == args.expected_start_ticks
            and owner['state'] != 'Z' and owner['stable_birth'], 'Actual listener birth differs')
    argv = owner['argv']
    if snapshot['port'] == 6006:
        require('-m' in argv and argv[argv.index('-m') + 1] == 'tensorboard.main', 'Actual6006 owner is not TensorBoard')
        for flag, value in (('--logdir', '/outputs/official-full'), ('--host', '127.0.0.1'), ('--port', '6006'), ('--load_fast', 'false')):
            require(argv.count(flag) == 1 and argv[argv.index(flag) + 1] == value, 'Actual TensorBoard flag differs')
        require(args.container_init_pid is not None and snapshot['container']['id'] == owner['container_id']
                and snapshot['container']['host_init_pid'] == args.container_init_pid
                and owner['mapping']['host_init']['pid'] == args.container_init_pid
                and owner['pid_namespace'] == snapshot['container_init_identity']['pid_namespace'],
                'TensorBoard lacks exact newCID/init/container-namespace host mapping')
    elif snapshot['port'] == 6007:
        require(Path(argv[0]).name == 'ssh' and '-N' in argv and argv.count('-L') == 1
                and argv[argv.index('-L') + 1] == '127.0.0.1:6007:127.0.0.1:6006' and argv[-1] == 'tencent-231', 'Actual6007 owner is not the intended SSH forward')
    else:
        raise ValueError('Only the separately approved6006/6007 ports are accepted')
    return owner


def scalar_guard(values, expected):
    require(type(values) is list and values and all(type(row) is list and len(row) == 3
            and type(row[1]) is int and all(type(value) in (int, float) and math.isfinite(value) for value in row) for row in values), 'Malformed/nonfinite HTTP scalar')
    steps = [row[1] for row in values]
    require(all(a < b for a, b in zip(steps, steps[1:])) and min(steps) >= 0 and steps[-1] == expected['step']
            and math.isclose(values[-1][2], expected['value'], rel_tol=1e-6, abs_tol=1e-8), 'Actual HTTP final step/value differs from original completed scalar')
    return {'samples_returned': len(values), 'first_step': steps[0], 'last_step': steps[-1], 'last_value': values[-1][2], 'all_returned_values_finite': True,
            'scope': 'HTTP may downsample; this checks its finite returned points and original final step/value, not full-event completeness.'}


def owner_identity(owner):
    keys = ('pid', 'start_time_clock_ticks', 'argv', 'socket_inodes', 'pid_namespace', 'stable_birth')
    return {key: owner[key] for key in (*keys, 'container_pid', 'container_id', 'container_started_at') if key in owner}


def adopted_container(args, output):
    require(args.adoption_result is not None and sha(args.adoption_result) == args.adoption_result_sha256, 'Actual default adoption result SHA required')
    result = read(args.adoption_result)
    require(result['status'] == 'passed_default_sdk018_control_adoption', 'Default adoption has not passed')
    cid = result['new_container_id']
    require(re.fullmatch('[0-9a-f]{64}', cid) is not None and cid != result['original_container_id'], 'Default adoption must name a full exact new CID')
    bound = {'result': record(args.adoption_result), 'new_container_id': cid}
    if urlparse(args.url).port == 6006:
        require(args.adoption_container_inspect is not None and sha(args.adoption_container_inspect) == args.adoption_container_inspect_sha256, 'Original actual adopted-container inspect SHA required')
        archived = read(args.adoption_container_inspect)
        argv = ['docker', 'container', 'inspect', cid]
        raw, receipt = docker_read(argv, output, 'fresh-container-inspect')
        bound['current_inspect_command'] = receipt
        current = json.loads(raw)
        require(type(current) is list and len(current) == 1, 'Ambiguous actual new CID inspect'); current = current[0]
        if type(archived) is list:
            require(len(archived) == 1, 'Ambiguous original adopted-container inspect'); archived = archived[0]
        require(current['Id'] == archived['Id'] == cid and current['Image'] == archived['Image'] == 'sha256:fdfb7221af88ad70236d8b40c463008677f9a622343972394efa99055ad71df3'
                and current['State']['Running'] is True and current['State']['StartedAt'] == archived['State']['StartedAt']
                and current['State']['Pid'] == archived['State']['Pid'] and normalized_mounts(current['Mounts']) == normalized_mounts(archived['Mounts'])
                and current['Config'] == archived['Config'] and current['HostConfig']['NetworkMode'] == 'host', 'Actual adopted CID image/birth/mounts changed')
        require(args.event_root is not None, 'Remote6006 must check the actual original events')
        mounts = {row['Destination']: row['Source'] for row in current['Mounts']}
        require(args.event_root.resolve() == (Path(mounts['/outputs']) / 'official-full').resolve(), 'Observed event tree is not the new CID actual official bind')
        actual_pid = current['State']['Pid']
        require(args.container_init_pid is None or args.container_init_pid == actual_pid, 'Caller supplied another container init PID')
        args.container_init_pid = actual_pid
        require(getattr(args, 'container_id', None) in (None, cid), 'Caller named another container CID')
        args.container_id = cid
        init = host_birth(actual_pid)
        bound.update(container_inspect_at_adoption=record(args.adoption_container_inspect), started_at=current['State']['StartedAt'],
            init_identity=init, actual_container_identity=container_identity(current))
    return bound


def check(args):
    require(sha(args.baseline) == args.baseline_sha256, 'Explicit actual completed scalar baseline SHA required')
    baseline = read(args.baseline)
    require(baseline['status'] == 'actual_completed_student_scalar_baseline_for_future_readonly_http_check', 'Unexpected completed scalar baseline')
    parsed = urlparse(args.url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port in (6006, 6007) and not parsed.username, 'Only the approved loopback endpoint is accepted')
    require(not args.output.exists(), 'Use a fresh observation directory')
    args.output.mkdir()
    report = {'schema_version': 1, 'status': 'failed', 'started_utc': now(), 'observer_source': record(Path(__file__).resolve()),
        'baseline': record(args.baseline), 'url': args.url, 'requests': [], 'curves': [],
        'expected_listener': {'pid': args.expected_pid, 'start_time_clock_ticks': args.expected_start_ticks, 'container_init_pid': args.container_init_pid},
        'scope': 'Read-only serving and original completed student scalar identity; no training, convergence or course-success claim.'}
    try:
        report['adoption'] = adopted_container(args, args.output)
        report['expected_listener']['container_init_pid'] = args.container_init_pid
        before = container_snapshot(args.container_id, args.output, 'listener-before') if parsed.port == 6006 else port_snapshot(parsed.port)
        report['listener_before'] = before; owner = owner_guard(before, args)
        if parsed.port == 6006:
            require(before['container'] == report['adoption']['actual_container_identity'], 'Observed listener CID differs from exact adopted generation')
            report['adoption']['init_identity']['pid_namespace'] = before['container_init_identity']['pid_namespace']
        if args.event_root is not None:
            require(args.events_before is not None and sha(args.events_before) == args.events_before_sha256, 'Explicit actual pre-start event inventory SHA required')
            prior = read(args.events_before)
            require(prior['port']['port'] == 6006 and prior['port']['host_boot_id'] == before['host_boot_id']
                    and not prior['port']['listeners'], 'Actual pre-start6006 port/host identity differs or was not free')
            report['canonical_event_root'] = str(args.event_root.resolve())
            report['events_before'] = prior['events']; report['events_after'] = events(args.event_root)
            require(report['events_before'] == report['events_after'], 'Original events changed across TensorBoard startup')
            for student in baseline['students']:
                for item in student['events']:
                    relative = str(Path(item['native_path']).relative_to('/outputs/official-full'))
                    require(any(row['path'] == relative and row['bytes'] == item['bytes'] and row['sha256'] == item['sha256'] for row in report['events_after']), 'Original completed student event SHA differs')
            report['events_unchanged'] = True
        else:
            require(args.remote_check is not None and sha(args.remote_check) == args.remote_check_sha256, 'Actual verified remote event/HTTP report is required')
            remote = read(args.remote_check)
            require(remote['status'] == 'passed' and remote['url'].rstrip('/') == 'http://127.0.0.1:6006' and remote['events_unchanged'] is True
                    and remote['events_before'] == remote['events_after'] and remote['baseline']['sha256'] == args.baseline_sha256
                    and remote['adoption']['new_container_id'] == report['adoption']['new_container_id']
                    and remote['adoption']['result']['sha256'] == report['adoption']['result']['sha256']
                    and remote['listener_before']['owners'][0]['pid_namespace'] == remote['adoption']['init_identity']['pid_namespace']
                    and remote['listener_before']['host_boot_id'] == remote['listener_after']['host_boot_id'], 'Actual remote serving/events/adoption check did not match this new CID')
            report['remote_check'] = record(args.remote_check)
        def get(label, route, decode=True):
            url = args.url.rstrip('/') + route
            try:
                with urlopen(url, timeout=20) as response:
                    body = response.read(); code = response.status; headers = list(response.headers.items())
            except HTTPError as error:
                body = error.read(); code = error.code; headers = list(error.headers.items())
            path = args.output / (label + '.body.raw'); path.write_bytes(body)
            report['requests'].append({'method': 'GET', 'url': url, 'http_status': code, 'headers': headers, 'body': record(path), 'observed_utc': now()})
            require(code == 200, 'Actual HTTP response is not200')
            return json.loads(body) if decode else body
        get('root', '/', False); runs = get('runs', '/data/runs'); tags = get('tags', '/data/plugin/scalars/tags')
        for student in baseline['students']:
            run = student['run']; require(run in runs and run in tags, 'Exact original student run is missing')
            for index, (tag, expected) in enumerate(student['tags'].items()):
                require(tag in tags[run], 'Original student tag is missing')
                values = get(student['kind'] + '-' + str(index), '/data/plugin/scalars/scalars?' + urlencode({'run': run, 'tag': tag, 'format': 'json'}))
                report['curves'].append({'kind': student['kind'], 'run': run, 'tag': tag, **scalar_guard(values, expected)})
        after = container_snapshot(args.container_id, args.output, 'listener-after') if parsed.port == 6006 else port_snapshot(parsed.port)
        report['listener_after'] = after
        require(owner_identity(owner_guard(after, args)) == owner_identity(owner) and before['host_boot_id'] == after['host_boot_id']
                and before['listeners'] == after['listeners'], 'Actual listener identity changed during HTTP observation')
        if parsed.port == 6006:
            require(after['container'] == before['container'], 'Adopted container changed during complete HTTP observation')
        if args.event_root is not None:
            final = events(args.event_root); require(final == report['events_after'], 'Original events changed during read-only HTTP queries'); report['events_after'] = final
        report['status'] = 'passed'
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    report['finished_utc'] = now(); save(args.output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'report': str(args.output / 'report.json'), 'curves': len(report['curves']), 'error': report.get('error')}))
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    snap = sub.add_parser('snapshot'); snap.add_argument('--port', type=int, required=True); snap.add_argument('--event-root', type=Path); snap.add_argument('--output', type=Path, required=True); snap.add_argument('--container-id')
    observe = sub.add_parser('check')
    for name in ('baseline', 'output', 'events-before', 'event-root', 'remote-check', 'adoption-result', 'adoption-container-inspect'):
        observe.add_argument('--' + name, type=Path, required=name in ('baseline', 'output'))
    for name in ('baseline-sha256', 'events-before-sha256', 'remote-check-sha256', 'url', 'adoption-result-sha256', 'adoption-container-inspect-sha256'):
        observe.add_argument('--' + name, required=name in ('baseline-sha256', 'url'))
    observe.add_argument('--expected-pid', type=int, required=True); observe.add_argument('--expected-start-ticks', type=int, required=True); observe.add_argument('--container-init-pid', type=int)
    observe.add_argument('--container-id')
    args = parser.parse_args()
    if args.action == 'snapshot':
        require(args.port in (6006, 6007), 'Only approved6006/6007 ports')
        if args.container_id:
            require(args.port == 6006 and not args.output.exists(), 'Exact CID snapshot is only for fresh remote6006 evidence')
            logs = args.output.with_name(args.output.name + '.docker-logs')
            require(not logs.exists(), 'Fresh read-only Docker receipt directory required'); logs.mkdir()
            port = container_snapshot(args.container_id, logs, 'snapshot')
        else:
            port = port_snapshot(args.port)
        save(args.output, {'observed_utc': now(), 'port': port, 'events': events(args.event_root) if args.event_root else None, 'observer_source': record(Path(__file__).resolve())})
        return 0
    return check(args)


if __name__ == '__main__': raise SystemExit(main())
