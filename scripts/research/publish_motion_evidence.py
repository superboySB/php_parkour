#!/usr/bin/env python3
"""Publish recorded reference videos and compact full-length GIF previews.

Run inside the motion Docker environment after render_motion_evidence.py.
This copies real MP4/PNG recordings and samples their decoded frames, recording
every retained source frame and SHA-256. No trajectory is synthesized here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("usage_assets/motion_matching"))
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.source / "manifest.json").read_text())
    manifest["recording_manifest_sha256"] = sha256(args.source / "manifest.json")
    manifest["preview_policy"] = "decoded MP4 frames, every fourth video frame plus final frame, 320x180, 96-color palette, final hold 800ms"
    for clip in manifest["clips"]:
        name = clip["name"]
        for suffix in (".mp4", ".png"):
            shutil.copy2(args.source / (name + suffix), args.output_dir / (name + suffix))
        video = args.source / (name + ".mp4")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "2", "-i", str(video),
                   "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        frames, selected = [], []
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as decoder:
            for index in range(clip["video_frames"]):
                frame = decoder.stdout.read(320 * 180 * 3)
                if len(frame) != 320 * 180 * 3:
                    raise RuntimeError(f"truncated MP4 frame {index} in {name}")
                if index % 4 == 0 or index == clip["video_frames"] - 1:
                    image = Image.frombytes("RGB", (320, 180), frame)
                    frames.append(image.convert("P", palette=Image.Palette.ADAPTIVE, colors=96))
                    selected.append(index)
            extra = decoder.stdout.read(1)
            stderr = decoder.stderr.read().decode(errors="replace")
            if decoder.wait() or extra:
                raise RuntimeError(f"unexpected MP4 length or decode failure: {stderr}")
        durations = [round(1000 * (right - left) / clip["video_fps"]) for left, right in zip(selected, selected[1:])] + [800]
        gif = args.output_dir / (name + ".gif")
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations, optimize=True, loop=0)
        clip["preview_video_sha256"] = sha256(video)
        clip["gif_video_frame_indices"] = selected
        clip["gif_source_frame_indices"] = [clip["source_frame_indices"][index] for index in selected]
        clip["gif_frame_durations_ms"] = durations
        clip["gif_dimensions"] = [320, 180]
        clip["gif_palette_colors"] = 96
        clip["artifacts"] = [{"path": name + suffix, "sha256": sha256(args.output_dir / (name + suffix)),
                              "size": (args.output_dir / (name + suffix)).stat().st_size} for suffix in (".mp4", ".gif", ".png")]
        print(f"Published {name}: {len(frames)} GIF frames, {gif.stat().st_size} bytes", flush=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copy2(args.source / "playback.html", args.output_dir / "playback.html")


if __name__ == "__main__":
    main()
