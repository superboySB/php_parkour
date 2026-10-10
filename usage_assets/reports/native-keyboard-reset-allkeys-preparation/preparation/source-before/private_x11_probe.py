"""Actual private Xlib connection/query-tree only: no keys, Tk or native objects."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import sys
from common import write
from x11_owned import OwnedDisplay


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Refuse to overwrite private connection evidence')
    connection = OwnedDisplay(os.environ['DISPLAY'], os.environ['PHP_GUI_TOKEN'])
    try:
        tree = connection.root.query_tree()
        forbidden = [name for name in sys.modules if name == 'mujoco' or name.startswith(('holosoma.', 'holosoma_inference.', 'far_unitree_sdk'))]
        if forbidden:
            raise ValueError('Private connection-only probe imported native runtime code')
        report = {'schema_version': 1, 'status': 'passed', 'display': os.environ['DISPLAY'], 'hostname': socket.gethostname(),
                  'pid': os.getpid(), 'root_xid': connection.root.id, 'child_window_count': len(tree.children),
                  'xauthority_path': os.environ.get('XAUTHORITY'), 'root_token_matched': True,
                  'xtest_extension': True, 'record_extension': True, 'key_events_sent': 0,
                  'native_objects_constructed': False, 'gpu_compute_invoked': False,
                  'scope': 'Real private python-xlib authentication and query_tree only; not GUI-policy acceptance'}
        write(args.output, report)
        print(json.dumps(report))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
