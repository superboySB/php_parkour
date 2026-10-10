#!/usr/bin/env python3
"""Import/metadata only; no SDK object, robot, DDS participant or CUDA call."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import unitree_interface

package = Path(unitree_interface.__file__).parent
binaries = sorted(package.glob('unitree_interface.cpython-*.so'))
if len(binaries) != 1:
    raise RuntimeError('Expected one CPython Unitree extension')
print(json.dumps({'version': importlib.metadata.version('far-unitree-sdk'),
                  'executable': sys.executable, 'prefix': sys.prefix,
                  'extension': str(binaries[0]),
                  'sha256': hashlib.sha256(binaries[0].read_bytes()).hexdigest(),
                  'api': sorted(n for n in dir(unitree_interface.UnitreeInterface) if not n.startswith('__'))}))
