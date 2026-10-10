"""Motion-save helper: qpos -> FAR-tracking npz.

Shared by ``process_scenario`` (generation) and ``run_interactive``'s
end-recording handler. Both resample a ``(N, 36)`` qpos buffer to a target fps
and write it through :func:`qpos_to_tracking`; this collects that exact
sequence so the two call sites cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Optional

import numpy as np

from motion_matching.utils.data_utils import (
    adjust_data_speed,
    adjust_vel_cmd_speed,
    resample_data,
    resample_vel_cmd,
)
from motion_matching.utils.tracking_format import qpos_to_tracking


def paired_terrain_paths(motion_file: str | Path) -> tuple[Path, Path]:
    """Return the box/mesh filenames paired with a generated motion."""
    motion = Path(motion_file)
    stem = "terrain".join(motion.stem.rsplit("motion", 1)) if "motion" in motion.stem else motion.stem + "_terrain"
    return motion.with_name(stem + ".npy"), motion.with_name(stem + ".obj")


def copy_paired_terrain(source_motion: str | Path, saved_motion: str | Path) -> list[Path]:
    """Keep available source terrain paired when saving an edited motion.

    Copies all NPY variants without inventing geometry or changing labels.
    An explicitly motion-only source remains motion-only.
    """
    source = Path(source_motion)
    targets = paired_terrain_paths(saved_motion)
    sources = paired_terrain_paths(source)
    if not any(path.exists() for path in sources):
        sources = tuple(source.with_name(source.stem + "_terrain" + ext) for ext in (".npy", ".obj"))
    copied = []
    for src, dst in zip(sources, targets):
        if src.is_file():
            if src.resolve() != dst.resolve():
                shutil.copyfile(src, dst)
            copied.append(dst)
    return copied


def save_recording_bundle(qpos: np.ndarray, motion_file: str | Path, posed_meshes: list,
                          terrain_metadata: list, *, source_fps: float = 60,
                          target_fps: int = 50, num_variants: int = 10) -> dict:
    """Save an unlabeled interactive reference and consistently paired terrain.

    Interactive recording captures poses only. It does not infer training
    direction labels from motion displacement or pretend to record intent.
    """
    from motion_matching.io.terrain_io import build_combined_terrain_mesh, randomize_terrain_variants

    if len(qpos) < 4 or int(target_fps / source_fps * len(qpos)) < 2:
        raise ValueError("Record at least four source frames before saving")
    motion = Path(motion_file)
    motion.parent.mkdir(parents=True, exist_ok=True)
    tracking = save_motion_npz(qpos, str(motion), target_fps=target_fps, source_fps=source_fps)
    terrain_npy, terrain_obj = paired_terrain_paths(motion)
    variants = (randomize_terrain_variants(terrain_metadata, num_variants=num_variants)
                if terrain_metadata else np.empty((0, num_variants, 10), dtype=np.float32))
    np.save(terrain_npy, variants)
    build_combined_terrain_mesh(posed_meshes).export(terrain_obj)
    metadata = {"schema_version": 1, "kind": "interactive_kinematic_reference", "source_fps": source_fps,
                "fps": target_fps, "source_frames": len(qpos), "saved_frames": len(tracking["joint_pos"]),
                "vel_cmd_present": False, "command_label_source": None,
                "command_limit": "Only qpos was recorded. No direction labels were inferred; provide explicit frame-aligned intent labels before direction-conditioned student training.",
                "motion": motion.name, "terrain_npy": terrain_npy.name, "terrain_obj": terrain_obj.name}
    motion.with_suffix(".recording.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def save_motion_npz(
    qpos: np.ndarray,
    output_file: str,
    *,
    target_fps: int = 50,
    source_fps: int = 60,
    vel_cmd: Optional[np.ndarray] = None,
) -> dict[str, np.ndarray]:
    """Resample ``qpos`` to ``target_fps`` and save it as a FAR-tracking npz.

    Args:
        qpos: ``(N, 36)`` motion-matching qpos at ``source_fps``.
        output_file: Destination ``.npz`` path.
        target_fps: Output frame rate (the schema's ``fps``).
        source_fps: Frame rate of ``qpos`` before resampling.
        vel_cmd: Optional ``(N, .)`` velocity-command array to attach under the
            ``vel_cmd`` key. The caller is responsible for having already
            resampled it to ``target_fps`` (it is stored verbatim as float32).

    Returns:
        The tracking dict that was written (handy for tests / further use).
    """
    qpos = resample_data(qpos, target_fps, original_fps=source_fps)
    tracking = qpos_to_tracking(qpos, target_fps)
    if vel_cmd is not None:
        tracking["vel_cmd"] = vel_cmd.astype(np.float32)
    np.savez(output_file, **tracking)
    return tracking


def save_edited_motion_npz(
    qpos: np.ndarray,
    output_file: str,
    *,
    source_fps: float,
    target_fps: float,
    speed: float = 1.0,
    vel_cmd: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Save a speed-edited motion, keeping commands aligned with its frames.

    Velocity commands use the same two sampling grids as the motion (speed,
    then FPS), with zero-order hold to preserve discrete command labels.
    """
    if not np.isfinite(speed) or speed <= 0:
        raise ValueError("speed must be positive and finite")
    if not np.isfinite(source_fps) or source_fps <= 0:
        raise ValueError("source_fps must be positive and finite")
    if not np.isfinite(target_fps) or target_fps <= 0 or not float(target_fps).is_integer():
        raise ValueError("target_fps must be a positive integer")
    if vel_cmd is not None and (vel_cmd.ndim != 2 or len(vel_cmd) != len(qpos)):
        raise ValueError("vel_cmd must have one row per source motion frame")
    adjusted_frames = int(1 / speed * len(qpos))
    saved_frames = int(target_fps / source_fps * adjusted_frames)
    if len(qpos) < 4 or adjusted_frames < 4 or saved_frames < 2:
        raise ValueError("Motion is too short for cubic speed/FPS resampling")

    adjusted_qpos = adjust_data_speed(qpos, speed)
    adjusted_qpos = resample_data(adjusted_qpos, target_fps, original_fps=source_fps)
    tracking = qpos_to_tracking(adjusted_qpos, int(target_fps))
    if vel_cmd is not None:
        adjusted_commands = adjust_vel_cmd_speed(vel_cmd, speed)
        adjusted_commands = resample_vel_cmd(adjusted_commands, target_fps, original_fps=source_fps)
        tracking["vel_cmd"] = adjusted_commands.astype(np.float32)
    np.savez(output_file, **tracking)
    return tracking
