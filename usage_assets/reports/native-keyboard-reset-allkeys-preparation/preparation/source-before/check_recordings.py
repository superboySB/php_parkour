#!/usr/bin/env python3
"""CPU postcheck of two future real native keyboard recordings. No native launch."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def check(path: Path, expected_code: int) -> dict:
    import numpy as np
    payload = path.read_bytes()
    with np.load(path, allow_pickle=False) as data:
        if set(data.files) != {'qpos', 'vel_cmd', 'fps'}:
            raise ValueError(f'{path}: expected native recording qpos/vel_cmd/fps only')
        qpos, commands, fps = data['qpos'], data['vel_cmd'], data['fps']
        if qpos.ndim != 2 or qpos.shape[1] != 36 or qpos.shape[0] < 2:
            raise ValueError(f'{path}: invalid native recording qpos shape')
        if commands.shape != (len(qpos), 15):
            raise ValueError(f'{path}: invalid native recording vel_cmd shape')
        if qpos.dtype != np.float32 or commands.dtype != np.float32:
            raise ValueError(f'{path}: native recording dtype differs from float32')
        if fps.shape != () or not np.issubdtype(fps.dtype, np.integer) or int(fps) != 50:
            raise ValueError(f'{path}: expected native scalar integer fps=50')
        if not np.isfinite(qpos).all() or not np.isfinite(commands).all():
            raise ValueError(f'{path}: nonfinite recording')
        if not np.logical_or(commands == 0, commands == 1).all() or not (commands.sum(axis=1) == 1).all():
            raise ValueError(f'{path}: commands are not actual one-hot vectors')
        norms = np.linalg.norm(qpos[:, :4], axis=1)
        if not np.allclose(norms, 1, atol=1e-3, rtol=0):
            raise ValueError(f'{path}: invalid first-four wxyz quaternion norms')
        codes, counts = np.unique(commands.argmax(axis=1), return_counts=True)
        if expected_code not in codes:
            raise ValueError(f'{path}: key-driven expected command {expected_code} absent')
        return {'path': str(path.resolve()), 'sha256': hashlib.sha256(payload).hexdigest(),
                'bytes': len(payload), 'frames': len(qpos), 'fps': int(fps),
                'qpos_shape': list(qpos.shape), 'vel_cmd_shape': list(commands.shape),
                'command_frame_counts': {str(int(code)): int(count) for code, count in zip(codes, counts)},
                'quaternion_norm_min': float(norms.min()), 'quaternion_norm_max': float(norms.max()),
                'expected_key_command_present': expected_code,
                'format': 'native inference recording: wxyz quaternion + root XYZ placeholders + 29 joint positions',
                'label_source': 'actual policy velocity_command buffer recorded by unmodified native recorder',
                'not_a_training_bundle': True, 'does_not_prove_terrain_traversal': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manual-stop', type=Path, required=True)
    parser.add_argument('--autosave-on-stop', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.manual_stop.resolve() == args.autosave_on_stop.resolve():
        parser.error('the two real recordings must be distinct files')
    if args.output.exists():
        parser.error('refuse to overwrite evidence')
    report = {'schema_version': 1, 'recordings': [check(args.manual_stop, 1), check(args.autosave_on_stop, 6)],
              'scope': 'CPU field checks only; actual key-event, state-transition, GUI and clean-worker evidence are separate required gates'}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
