#!/usr/bin/env python3
"""Render generated G1 reference trajectories, with source hashes and timing.

This performs MuJoCo forward kinematics, with no simulation steps or policy.
The overlay and manifest explicitly label every video REFERENCE / KINEMATIC.
Use MUJOCO_GL=osmesa for CPU rendering inside Docker, without occupying a GPU.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# A GUI container sets MUJOCO_GL=glfw for manual simulation. Reference
# recording must also work without DISPLAY and should not occupy a GPU.
os.environ["MUJOCO_GL"] = os.environ.get("PHP_REFERENCE_GL", "osmesa")
os.environ.setdefault("LP_NUM_THREADS", "2")

import mujoco
import numpy as np
import trimesh
from PIL import Image, ImageDraw

from motion_matching.motion_visualizer import load_motion_data
from motion_matching.utils import G1_MJCF


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scene_model(terrain: Path) -> mujoco.MjModel:
    source = Path(G1_MJCF)
    xml = ET.parse(source)
    compiler = xml.find("compiler")
    meshdir = (source.parent / compiler.get("meshdir", ".")).resolve()
    compiler.set("meshdir", str(meshdir))
    asset = xml.find("asset")
    for mesh in asset.findall("mesh"):
        if mesh.get("file"):
            mesh.set("file", str(meshdir / mesh.get("file")))
    world = xml.find("worldbody")
    ET.SubElement(world, "light", pos="0 0 10", dir="0 0 -1", directional="true", diffuse="0.8 0.8 0.8")
    # The packaged model already has a plane named floor. Two coplanar
    # planes cause severe z-fighting in the CPU renderer.
    if not any(geom.get("type") == "plane" for geom in xml.findall("worldbody/geom")):
        ET.SubElement(world, "geom", name="research_ground", type="plane", size="0 0 0.1", rgba="0.2 0.25 0.29 1")
    combined = trimesh.load(terrain, force="mesh", process=True)
    obstacles = [mesh for mesh in combined.split(only_watertight=False) if np.max(mesh.extents) < 100]
    for index, mesh in enumerate(obstacles):
        name = f"research_terrain_{index}"
        ET.SubElement(asset, "mesh", name=name,
                      vertex=" ".join(format(float(v), ".9g") for v in mesh.vertices.reshape(-1)),
                      face=" ".join(str(int(v)) for v in mesh.faces.reshape(-1)))
        ET.SubElement(world, "geom", name=name, type="mesh", mesh=name, rgba="0.79 0.56 0.28 1", contype="0", conaffinity="0")
    visual = xml.find("visual")
    if visual is None:
        visual = ET.SubElement(xml.getroot(), "visual")
    global_visual = visual.find("global")
    if global_visual is None:
        global_visual = ET.SubElement(visual, "global")
    global_visual.set("offwidth", "1920")
    global_visual.set("offheight", "1080")
    return mujoco.MjModel.from_xml_string(ET.tostring(xml.getroot(), encoding="unicode"))


def render(name: str, motion: Path, destination: Path, width: int, height: int, video_fps: int) -> dict:
    joints, root, qpos, source_fps, commands = load_motion_data(motion)
    terrain = motion.with_name(motion.name.replace("_motion.npz", "_terrain.obj"))
    terrain_variants = motion.with_name(motion.name.replace("_motion.npz", "_terrain.npy"))
    model = scene_model(terrain)
    data = mujoco.MjData(model)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.azimuth = 130
    camera.elevation = -18
    camera.distance = 4.3
    indices = np.minimum(np.floor(np.arange(math.ceil(len(qpos) / source_fps * video_fps)) * source_fps / video_fps).astype(int), len(qpos) - 1)
    # Preserve the final source frame even when the two rates do not divide.
    indices[-1] = len(qpos) - 1
    mp4 = destination / f"{name}.mp4"
    gif = destination / f"{name}.gif"
    png = destination / f"{name}.png"
    encoder_command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(video_fps), "-i", "-", "-an", "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(mp4)]
    previews = []
    preview_interval = max(1, int(round(video_fps / 8)))
    keyframe = int(np.argmax(root[:, 2]))
    keyframe_video = int(np.argmin(np.abs(indices - keyframe)))
    with mujoco.Renderer(model, height=height, width=width) as renderer:
        with subprocess.Popen(encoder_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as encoder:
            try:
                for video_index, frame_index in enumerate(indices):
                    pose = qpos[frame_index]
                    data.qpos[:] = np.concatenate([pose[4:7], pose[:4], pose[7:]])
                    mujoco.mj_forward(model, data)
                    camera.lookat[:] = [pose[4], pose[5], max(0.6, pose[6] - 0.1)]
                    renderer.update_scene(data, camera=camera)
                    frame = Image.fromarray(renderer.render().copy())
                    draw = ImageDraw.Draw(frame)
                    draw.rectangle((0, 0, width, 55), fill=(10, 18, 28))
                    draw.text((12, 8), f"{name}  |  G1 reference trajectory", fill="white")
                    draw.text((12, 30), f"KINEMATIC / NO POLICY  t={frame_index / source_fps:.2f}s  frame={frame_index}/{len(qpos) - 1}", fill=(255, 210, 125))
                    encoder.stdin.write(frame.tobytes())
                    if video_index % preview_interval == 0 or video_index == len(indices) - 1:
                        preview = frame.copy()
                        preview.thumbnail((320, 180))
                        preview = preview.convert("P", palette=Image.Palette.ADAPTIVE, colors=96)
                        previews.append(preview)
                    if video_index == keyframe_video:
                        frame.save(png)
                encoder.stdin.close()
                stderr = encoder.stderr.read().decode(errors="replace")
                if encoder.wait() != 0:
                    raise RuntimeError(f"ffmpeg failed: {stderr}")
            except Exception:
                encoder.kill()
                encoder.wait()
                raise
    durations = [round(1000 * preview_interval / video_fps)] * len(previews)
    durations[-1] = 800
    previews[0].save(gif, save_all=True, append_images=previews[1:], duration=durations, loop=0, optimize=True)
    return {
        "name": name, "kind": "reference_kinematic_playback", "policy_rollout": False,
        "renderer": "MuJoCo mj_forward + packaged G1 mesh; reference OBJ terrain",
        "source_frames": len(qpos), "source_fps": source_fps,
        "video_frames": len(indices), "video_fps": video_fps,
        "duration_seconds": len(qpos) / source_fps,
        "source_frame_indices": indices.tolist(), "png_source_frame": int(indices[keyframe_video]),
        "gif_source_frame_indices": [int(indices[i]) for i in range(len(indices)) if i % preview_interval == 0 or i == len(indices) - 1],
        "gif_last_frame_hold_ms": durations[-1],
        "gif_dimensions": list(previews[0].size), "gif_palette_colors": 96,
        "sources": [{"path": str(p.resolve()), "sha256": sha256(p), "size": p.stat().st_size} for p in (motion, terrain, terrain_variants)],
        "artifacts": [{"path": p.name, "sha256": sha256(p), "size": p.stat().st_size} for p in (mp4, gif, png)],
        "encoder_command": encoder_command,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--video-fps", type=int, default=25)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")
    if args.width % 2 or args.height % 2 or min(args.width, args.height, args.video_fps) <= 0:
        parser.error("video dimensions must be positive/even; FPS must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matrix = json.loads(args.matrix.read_text())
    manifest = {"schema_version": 1, "matrix_sha256": sha256(args.matrix), "seed": matrix["seed"],
                "render_environment": {key: os.environ.get(key) for key in ("MUJOCO_GL", "LP_NUM_THREADS")},
                "selection_policy": "first passed configuration with obstacle boxes when available; otherwise first passed", "clips": []}
    for scenario in matrix["scenarios"]:
        if scenario["status"] != "passed":
            continue
        configurations = [row for row in scenario["result"]["configurations"] if row["status"] == "passed"]
        configuration = next((row for row in configurations if row["terrain_shape"][0] > 0), configurations[0])
        source = Path(configuration["files"][0]["path"])
        clip = render(scenario["name"], source, args.output_dir, args.width, args.height, args.video_fps)
        clip["configuration"] = configuration["name"]
        manifest["clips"].append(clip)
        (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Rendered {scenario['name']}: {clip['video_frames']} frames", flush=True)
    cards = "\n".join(f'<article id="{clip["name"]}"><h2>{clip["name"]}</h2><p>{clip["configuration"]}<br>Reference kinematic playback, no learned policy or physics success claim.</p><video controls loop preload="metadata" poster="{clip["name"]}.png" src="{clip["name"]}.mp4"></video></article>' for clip in manifest["clips"])
    html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PHP G1 reference motions</title><style>body{background:#121b26;color:#edf2f8;font:16px system-ui;margin:30px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:24px}article{background:#203043;padding:16px;border-radius:12px}h2{font-size:20px}video{width:100%}p{color:#bfd0df}</style><h1>PHP G1: ' + str(len(manifest["clips"])) + ' generated motion scenarios</h1><p>MuJoCo forward kinematics renders the actual generated motion arrays and reference terrain. These recordings do not evaluate a control policy. Source hashes and frame indices: <a href="manifest.json">manifest.json</a>.</p><main>' + cards + '</main></html>'
    (args.output_dir / "playback.html").write_text(html)


if __name__ == "__main__":
    main()
