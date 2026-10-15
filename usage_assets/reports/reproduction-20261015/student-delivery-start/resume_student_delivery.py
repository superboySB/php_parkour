#!/usr/bin/env python3
"""Resume a cancelled, never-started delivery in a fresh host evidence directory.

The original reviewed waiter, transfer and native58 sources/contracts stay intact.
This host wrapper only chooses a fresh execution directory after checking that the
old waiter attempted no action, and records that additional control explicitly.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode = True
WORKSPACE = Path('/home/dzp/projects/php_parkour')
ORIGINAL = WORKSPACE / 'outputs/research/final-student-delivery-waiter-ssh-recovery-02'
EXPECTED_WAITER_SHA = 'cb741ba88bcf22c8a15831b67d13f0dcb7a40ef99946b3fdffdf9240f1133333'


def fp(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Regular original required: ' + str(path))
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous-state-sha256', required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--root-authorized-watch', action='store_true')
    args = parser.parse_args()
    if not args.root_authorized_watch:
        raise ValueError('Explicit operator start flag required')
    output = args.output.absolute()
    if (output.exists() or '..' in output.parts
            or not output.is_relative_to(WORKSPACE / 'outputs/research/reproduction-20261015')
            or any(p.is_symlink() for p in (output, *output.parents))):
        raise ValueError('Use a fresh isolated execution directory')
    source = ORIGINAL / 'wait_final_students.py'
    previous = ORIGINAL / 'execution/state.json'
    contract_path = ORIGINAL / 'contract.json'
    if fp(source)['sha256'] != EXPECTED_WAITER_SHA:
        raise ValueError('Reviewed original waiter changed')
    if fp(previous)['sha256'] != args.previous_state_sha256:
        raise ValueError('Cancelled state changed')
    if fp(contract_path)['sha256'] != args.contract_sha256:
        raise ValueError('Reviewed contract changed')
    old = json.loads(previous.read_bytes())
    if old['status'] != 'failed' or any(old.get(k) is not False for k in
            ('action_started', 'fetch_attempted', 'prepare_attempted', 'run_attempted')):
        raise ValueError('A previously started action must be reviewed separately')
    spec = importlib.util.spec_from_file_location('original_reviewed_student_waiter', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONTRACT_GUARD = (contract_path, args.contract_sha256)
    contract = module.read(contract_path)
    module.verify_sources(contract)
    if module.TRANSFER_ROOT.exists() or module.NATIVE_OUTPUT.exists():
        raise ValueError('Previous action output exists; preserve it without retry')

    def interrupted(signum, _):
        raise KeyboardInterrupt('Owned continuation received signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    with module.WAITER_LOCK.open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir()
        (output / 'continuation.json').write_text(json.dumps(dict(
            status='reviewed_cancelled_unstarted_delivery_continuation',
            wrapper=fp(__file__), original_waiter=fp(source),
            previous_state=fp(previous), contract=fp(contract_path), argv=sys.argv,
            scope='Fresh host execution directory; original sources and scientific contracts unchanged',
            quality_verified=False), indent=2) + '\n')
        execution = output / 'execution'
        execution.mkdir()
        waiter = module.Waiter(contract, execution)
        try:
            while not waiter.step():
                time.sleep(module.POLL_SECONDS)
        except BaseException as error:
            waiter.fail(error)
            raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
