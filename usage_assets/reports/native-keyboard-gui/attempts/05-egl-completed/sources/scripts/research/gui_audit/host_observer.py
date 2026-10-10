"""Read-only process/thread snapshots of the exact newly owned GUI container."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from common import identity, load, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--container-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text()); frozen = dict(plan); digest = frozen.pop('plan_sha256')
    if identity(frozen) != digest:
        raise ValueError('Observer plan identity differs')
    original = Path(plan['cohort_root']) / 'source/scripts/research/gui_audit/observe_container_pids.py'
    if sha(original) != plan['host_observer_sha256']:
        raise ValueError('Reviewed read-only capture helper differs')
    observer = load(original, 'gui_readonly_host_pid_capture')
    endpoint = observer.local_endpoint()
    initial = observer.inspect_identity(args.container_id, plan['image_id'])
    if not initial['running']:
        raise ValueError('Own observer container is not running')
    args.output.mkdir(exist_ok=False)
    report = {'schema_version': 1, 'plan_sha256': digest, 'identity': initial, 'endpoint': endpoint,
              'scope': 'Exact GUI CID host cgroup/NSpid/birth/command_writer threads; does not control any process',
              'snapshots': 0, 'errors': [], 'started_unix': time.time()}
    write(args.output / 'ready.json', report)
    until = time.monotonic() + plan['max_operator_seconds'] + 30
    try:
        with (args.output / 'snapshots.jsonl').open('x') as stream:
            while not (args.output / 'stop').exists():
                if time.monotonic() > until:
                    raise TimeoutError('Observer bounded duration expired')
                current = observer.inspect_identity(args.container_id, plan['image_id'])
                if current['started_at'] != initial['started_at']:
                    raise ValueError('Owned container restart invalidates host observation')
                if not current['running']:
                    raise ValueError('Owned container stopped before observer stop marker')
                event = {'unix': time.time(), 'processes': [], 'raced_exit_pids': []}
                for row in observer.parse_top(observer.docker('top', args.container_id, '-eo', 'pid,ppid,pgid,sid,stat,comm')):
                    try:
                        event['processes'].append(observer.capture_pid(Path('/proc'), row['host_pid'], args.container_id))
                    except FileNotFoundError:
                        event['raced_exit_pids'].append(row['host_pid'])
                stream.write(json.dumps(event, allow_nan=False) + '\n'); stream.flush()
                report['snapshots'] += 1
                time.sleep(.2)
        report['status'] = 'completed'
    except BaseException as error:
        report['status'] = 'failed'; report['errors'].append(str(error))
    finally:
        report['finished_unix'] = time.time()
        write(args.output / 'summary.json', report)
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
