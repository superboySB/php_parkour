#!/usr/bin/env python3
"""Prepared separate service launch; run only after actual default adoption.

This records a live TensorBoard child, not its future exit status. The host
operator separately verifies the new CID, host listener, HTTP and event SHA.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tb_adoption_observe_v3 import events, now, port_snapshot, read, record, require, save, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-cid', required=True)
    parser.add_argument('--adoption-result', type=Path, required=True)
    parser.add_argument('--adoption-result-sha256', required=True)
    parser.add_argument('--events-before', type=Path, required=True)
    parser.add_argument('--events-before-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').is_file() and socket.gethostname() == args.new_cid[:12], 'Use the actual adopted default CID, not a host/other container')
    require(sha(args.adoption_result) == args.adoption_result_sha256, 'Actual adoption result SHA differs')
    adoption = read(args.adoption_result)
    require(adoption['status'] == 'passed_default_sdk018_control_adoption' and adoption['new_container_id'] == args.new_cid, 'Actual default adoption must pass first')
    require(sha(args.events_before) == args.events_before_sha256, 'Actual pre-start event receipt SHA differs')
    before = read(args.events_before)
    require(before['port']['port'] == 6006 and not before['port']['listeners'] and not port_snapshot(6006)['listeners'], 'Port6006 is not freshly free; do not replace a service')
    require(events(Path('/outputs/official-full')) == before['events'], 'Original events changed before service launch')
    require('..' not in args.output.parts and not any(path.is_symlink() for path in (args.output, *args.output.parents)) and args.output.is_absolute()
            and args.output.is_relative_to('/outputs') and not args.output.is_relative_to('/outputs/official-full')
            and not Path('/outputs/official-full').is_relative_to(args.output)
            and args.output.parts[2].startswith('tb-sdk018-default-'), 'Use a separate fresh TB control log tree')
    require(not args.output.exists(), 'Use a fresh service log directory')
    args.output.mkdir()
    argv = ['/opt/php/bin/train-python', '-m', 'tensorboard.main', '--logdir', '/outputs/official-full', '--host', '127.0.0.1', '--port', '6006', '--load_fast', 'false']
    environment = os.environ.copy(); environment['CUDA_VISIBLE_DEVICES'] = ''
    receipt = {'status': 'prepared_to_spawn_tensorboard', 'started_utc': now(), 'container_id': args.new_cid,
        'argv': argv, 'actual_child_wait_returncode': None, 'adoption_result': record(args.adoption_result), 'events_before': record(args.events_before),
        'launcher_source': record(Path(__file__).resolve()), 'tensorboard_version': importlib.metadata.version('tensorboard'), 'child_cuda_visible_devices': '',
        'scope': 'Separate local-event serving only. Live process launch is not HTTP readiness, training, convergence or course success.'}
    save(args.output / 'before-spawn.json', receipt)
    child = None
    try:
        with (args.output / 'stdout.raw').open('xb') as stdout, (args.output / 'stderr.raw').open('xb') as stderr:
            child = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=environment, start_new_session=True)
            raw = (Path('/proc') / str(child.pid) / 'stat').read_text(); fields = raw[raw.rfind(')') + 2:].split()
            receipt.update(status='spawned_live_tensorboard_requires_host_listener_http_browser_checks',
                container_child_identity={'pid': child.pid, 'pgid': os.getpgid(child.pid), 'sid': os.getsid(child.pid), 'start_time_clock_ticks': int(fields[19])})
            save(args.output / 'launch.json', receipt)
    except BaseException as exc:
        receipt.update(status='failed_service_launch_partial_preserved', error=type(exc).__name__ + ': ' + str(exc))
        if child is not None:
            members = []
            for path in Path('/proc').glob('[0-9]*/stat'):
                try:
                    raw = path.read_text(); fields = raw[raw.rfind(')') + 2:].split()
                except (FileNotFoundError, ProcessLookupError): continue
                if int(fields[3]) == child.pid and fields[0] != 'Z': members.append(int(path.parent.name))
            if members:
                if child.poll() is None:
                    require(os.getpgid(child.pid) == os.getsid(child.pid) == child.pid, 'Refuse to signal another service session')
                os.killpg(child.pid, signal.SIGTERM)
            receipt['signalled_own_session_members'] = members
            receipt['actual_child_wait_returncode'] = child.wait()
        print(json.dumps(receipt), flush=True)
        save(args.output / 'failure.json', receipt)
        raise
    print(json.dumps(receipt))


if __name__ == '__main__': main()
