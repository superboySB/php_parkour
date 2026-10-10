"""Read generated 50 Hz reference labels without changing their timing.

``tracking_format.py`` writes world body poses in wxyz order, with pelvis at
body index zero. ``motion_convert.py`` preserves that root at index zero in
the native 32-body layout. This reader needs labels and those world poses;
it does not infer commands from displacement or resample any input.
"""
from __future__ import annotations

import hashlib
import io
import math
from numbers import Integral
from pathlib import Path
from typing import Any


def load_reference_commands(path: str | Path) -> dict[str, Any]:
    """Return JSON-safe labels, file identity and initial pelvis XY/yaw.

    Required fields are ``fps`` (one exact value 50), ``vel_cmd`` (T, 15),
    ``body_pos_w`` (T, B, 3) and ``body_quat_w`` (T, B, 4), with T/B positive.
    Every command must be exact one-hot with its one in columns 0..11.
    ``codes`` contains one integer per frame; ``commands`` preserves all 15
    input components. ``root_yaw`` is in radians about world Z.

    SHA-256 covers the same bytes parsed by NumPy, rather than a later read
    of a possibly replaced file. No pickle, label repair or resampling occurs.
    """
    import numpy as np

    source = Path(path).resolve(strict=True)
    raw = source.read_bytes()
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        required = {"fps", "vel_cmd", "body_pos_w", "body_quat_w"}
        if missing := required - set(archive.files):
            raise ValueError(f"Reference NPZ missing fields: {sorted(missing)}")
        arrays = {name: archive[name] for name in required}
        names = archive["body_names"] if "body_names" in archive.files else None

    for name, value in arrays.items():
        if value.dtype.kind not in "fiu" or not np.isfinite(value).all():
            raise ValueError(f"{name} must contain finite real numeric values")
    fps = arrays["fps"]
    if fps.shape not in ((), (1,)) or float(fps.reshape(-1)[0]) != 50.0:
        raise ValueError("Reference fps must be one exact value 50; no resampling is performed")

    commands = arrays["vel_cmd"]
    if commands.ndim != 2 or commands.shape[1] != 15 or commands.shape[0] < 1:
        raise ValueError(f"vel_cmd must be nonempty (T, 15), got {commands.shape}")
    if not np.logical_or(commands == 0, commands == 1).all() or not (commands.sum(axis=1) == 1).all():
        raise ValueError("vel_cmd must be exact one-hot in every frame")
    if (commands[:, 12:] != 0).any():
        raise ValueError("vel_cmd codes must be in 0..11; columns 12..14 are unsupported")
    # The exact-one-hot checks above make nonzero extraction unambiguous.
    codes = np.nonzero(commands)[1].tolist()
    frames = int(commands.shape[0])

    positions, quaternions = arrays["body_pos_w"], arrays["body_quat_w"]
    if positions.ndim != 3 or positions.shape[0] != frames or positions.shape[1] < 1 or positions.shape[2] != 3:
        raise ValueError(f"body_pos_w must be (T, B, 3) matching vel_cmd, got {positions.shape}")
    if quaternions.shape != (frames, positions.shape[1], 4):
        raise ValueError(f"body_quat_w must be (T, B, 4) matching body_pos_w, got {quaternions.shape}")
    if names is not None:
        if names.shape != (positions.shape[1],) or names.dtype.kind not in "US":
            raise ValueError("body_names must be one string per body")
        first_name = names[0].decode() if names.dtype.kind == "S" else str(names[0])
        if first_name != "pelvis":
            raise ValueError("body_names[0] must be pelvis for the tracking root layout")
    root_quat = [float(component) for component in quaternions[0, 0]]
    if not math.isclose(sum(component * component for component in root_quat), 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise ValueError("Initial pelvis quaternion must be unit wxyz (tolerance 1e-5)")
    w, x, y, z = root_quat
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return {
        "path": str(source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "fps": 50,
        "frames": frames,
        "commands": commands.tolist(),
        "codes": codes,
        "unique_codes": sorted(set(codes)),
        "root_body": "pelvis",
        "root_body_index": 0,
        "quaternion_order": "wxyz",
        "root_xy": [float(value) for value in positions[0, 0, :2]],
        "root_quat_wxyz": root_quat,
        "root_yaw": yaw,
    }


def reference_frame_for_step(step: int, anchor: int, decimation: int, frames: int) -> int:
    """Select by integer physical ticks, returning ``frames`` at/after end.

    ``anchor`` is the physical step for reference frame zero. Only control
    ticks ``anchor + k * decimation`` are valid; earlier or unaligned steps
    raise ValueError. The end sentinel must stop playback, never index or
    repeat the last command. Booleans and floating-point values are rejected.
    """
    values = {"step": step, "anchor": anchor, "decimation": decimation, "frames": frames}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{name} must be an integer")
    step, anchor, decimation, frames = (int(value) for value in (step, anchor, decimation, frames))
    if step < 0 or anchor < 0 or decimation <= 0 or frames <= 0:
        raise ValueError("step/anchor must be nonnegative and decimation/frames positive")
    if step < anchor:
        raise ValueError("step is before the reference anchor")
    if (step - anchor) % decimation:
        raise ValueError("step is not aligned to the reference control tick")
    return min((step - anchor) // decimation, frames)
