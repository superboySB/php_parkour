#!/usr/bin/env python3
"""Ordinary CPU signal/parent test child; never imports native58 or queries Docker/GPU."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--code', type=int, default=0)
    p.add_argument('--wait-for-signal', action='store_true')
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('cpu_only_actual_wrapper_signal_functions', HERE / 'run_native58.py')
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    a.output.mkdir(exist_ok=False)
    receipt = a.output / 'cpu-control.json'
    row = {'scope': 'ordinary_cpu_protocol_only_no_scientific_result', 'identity': wrapper.identity(),
           'signals': [], 'native_imported': False, 'docker_gpu_actions': False, 'cleanup_entered': False}
    handlers = wrapper.install_signal_handlers(row, receipt)
    wrapper.write(receipt, row)
    (a.output / 'ready').write_text('ordinary CPU child ready\n')
    try:
        if a.wait_for_signal:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                time.sleep(.05)
            raise ValueError('Expected actual signal was not delivered')
        return a.code
    except KeyboardInterrupt:
        return 130
    finally:
        row['cleanup_entered'] = True
        # A second actual TERM while unwinding must be recorded without another
        # KeyboardInterrupt bypassing this cleanup.
        if a.wait_for_signal:
            time.sleep(.2)
        row['cleanup_completed'] = True
        wrapper.write(receipt, row)
        for number, handler in handlers.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    raise SystemExit(main())
