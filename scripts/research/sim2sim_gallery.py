#!/usr/bin/env python3
"""Render measured trajectories and a simulation-time-aligned rollout mosaic."""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.font_manager import findfont

    matrix = json.loads(args.matrix.read_text())
    runs = matrix["commands"]
    if matrix["status"] != "completed" or any(run["result"] is None for run in runs):
        raise ValueError("A completed real rollout matrix is required")
    args.output.mkdir(parents=True, exist_ok=True)
    columns = 4
    rows = math.ceil(len(runs) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(14, 3.5 * rows), squeeze=False)
    records = []
    for ax, run in zip(axes.flat, runs):
        report = Path(run["report"])
        root = report.parent
        result = run["result"]
        code = run["command"]
        mode = "HIGH" if 6 <= code <= 10 else "LOW"
        name = result["inference"]["commands"][0]["name"]
        with (root / "trajectory.csv").open() as file:
            trajectory = [row for row in csv.DictReader(file) if float(row["policy_seconds"]) >= 0]
        x = [float(row["x_m"]) - float(trajectory[0]["x_m"]) for row in trajectory]
        y = [float(row["y_m"]) - float(trajectory[0]["y_m"]) for row in trajectory]
        color = "#20854e" if result["survival_passed"] else "#c53030"
        ax.plot(x, y, color=color, linewidth=2)
        ax.scatter([x[0]], [y[0]], marker="o", color="#182434", s=35, label="start")
        ax.scatter([x[-1]], [y[-1]], marker="x", color=color, s=40, label="end")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=0.25)
        ax.set_xlabel("world X displacement (m)")
        ax.set_ylabel("world Y displacement (m)")
        simulation = result["simulation"]
        title = f"{code:02d} {mode} {name}"
        ax.set_title(f"{title}\npath {simulation['path_length_xy_m']:.2f} m; yaw {simulation['heading_change_deg']:+.0f} deg")
        ax.text(0.03, 0.03, f"{simulation['policy_simulation_seconds']:.2f} simulated s | {'survived' if result['survival_passed'] else 'fell'}",
                transform=ax.transAxes, fontsize=8, color=color)
        release = json.loads((root / "released.json").read_text())["simulation_seconds"]
        records.append({"command": code, "title": title, "report": str(report), "video": str(root / result["videos"][0]),
                        "release_simulation_seconds": release, "duration": result["config"]["duration"],
                        "path_length_xy_m": simulation["path_length_xy_m"], "heading_change_deg": simulation["heading_change_deg"],
                        "survived": result["survival_passed"]})
    for ax in list(axes.flat)[len(runs):]:
        ax.axis("off")
    figure.suptitle("Released PHP student: independent resets, native DDS + D435i depth, 50 Hz control\nContinuous turn commands can trace circles; net displacement is not path length", fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(args.output / "trajectories.png", dpi=150)
    figure.savefig(args.output / "trajectories.svg")
    plt.close(figure)
    evidence = {"source_matrix": str(args.matrix.resolve()), "runs": records, "figures": ["trajectories.png", "trajectories.svg"]}
    if args.video:
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "1"]
        for record in records:
            command += ["-threads", "1", "-i", record["video"]]
        filters = []
        font = findfont("DejaVu Sans")
        duration = min(record["duration"] for record in records)
        for index, record in enumerate(records):
            label = record["title"].replace("_", " ")
            filters.append(f"[{index}:v]trim=start={record['release_simulation_seconds']}:duration={duration},setpts=PTS-STARTPTS,fps=25,scale=320:180,"
                           f"drawtext=fontfile='{font}':text='{label}':fontsize=15:fontcolor=white:box=1:boxcolor=black@0.7:x=5:y=5[v{index}]")
        layout = "|".join(f"{(index % columns) * 320}_{(index // columns) * 180}" for index in range(len(records)))
        filters.append("".join(f"[v{index}]" for index in range(len(records))) + f"xstack=inputs={len(records)}:layout={layout}:fill=black[grid]")
        video = args.output / "directions.mp4"
        command += ["-filter_complex", ";".join(filters), "-map", "[grid]", "-an", "-threads", "2", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", str(video)]
        subprocess.run(command, check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,nb_frames:format=duration", "-of", "json", str(video)],
                               text=True, capture_output=True, check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(duration / 2), "-i", str(video), "-frames:v", "1", str(args.output / "directions.png")], check=True)
        evidence.update(video="directions.mp4", thumbnail="directions.png", video_probe=json.loads(probe.stdout),
                        alignment="Each native clip is trimmed at its recorded gantry-release simulation timestamp, then aligned at policy t=0; playback 25 fps.")
    (args.output / "gallery.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
