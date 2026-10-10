#!/usr/bin/env python3
"""Publish a completed 17-scene physical rollout matrix without editing media.

Host standard library only. All simulation, inference, ffprobe and thumbnail
decoding have already run inside Docker. Every rollout, including threshold
events and execution failures, remains visible. Planned/running inputs are
refused so no results are published ahead of their execution.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import struct
from pathlib import Path

from sim2sim_scene_matrix import SCENARIOS


ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    "random_locomotion": "自由移动与散落障碍", "low_speed_step": "低速台阶", "high_speed_step": "高速台阶",
    "low_speed_climb_58": "低速攀爬 58", "high_speed_climb_58": "高速攀爬 58",
    "low_speed_climb_76": "低速攀爬 76", "high_speed_climb_76": "高速攀爬 76",
    "low_speed_climb_94": "低速攀爬 94", "high_speed_climb_94": "高速攀爬 94",
    "low_speed_roll_78": "低速翻滚 78", "low_speed_roll_90": "低速翻滚 90", "high_speed_roll_134": "高速翻滚 134",
    "high_speed_hurdle": "高速跨栏", "high_speed_dash_vault": "高速 dash vault",
    "high_speed_speed_vault": "高速 speed vault", "high_speed_cat_vault": "高速 cat vault", "high_speed_jump_35": "跳跃 35",
}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def host_path(path: str) -> Path:
    """Translate only the documented Docker bind-mount paths."""
    value = Path(path)
    for prefix, destination in ((Path("/outputs"), ROOT / "outputs/research"),
                                (Path("/workspace/php_parkour"), ROOT)):
        try:
            return destination / value.relative_to(prefix)
        except ValueError:
            pass
    return value if value.is_absolute() else ROOT / value


def validate_matrix(matrix: dict) -> None:
    if matrix.get("status") not in ("completed", "execution_failed"):
        raise ValueError("the entire matrix must finish before publication; planned/running inputs are refused")
    rows = matrix.get("selections", [])
    if len(rows) != len(SCENARIOS) or {row["scenario"] for row in rows} != set(SCENARIOS):
        raise ValueError("exactly one result for each of the 17 declared scenarios is required")
    if any(row.get("status") not in ("completed", "execution_failed") for row in rows):
        raise ValueError("all 17 scenarios must have a terminal result, including any execution failures")
    if matrix.get("quality_verified") or matrix.get("obstacle_course_completion_verified"):
        raise ValueError("this bounded representative rollout publisher does not certify policy quality or course completion")


def number(value, digits=3) -> str:
    return "未记录" if value is None else f"{value:.{digits}f}"


def make_page(manifest: dict) -> str:
    escape = html.escape
    counts = manifest["counts"]
    cards = []
    for row in manifest["scenarios"]:
        name = row["scenario"]
        sim = row.get("simulation", {})
        if row["status"] != "completed":
            state, badge = "execution_failed", "执行失败 · 保留结果"
        elif row["fall_detected"]:
            state, badge = "threshold", "触发高度/倾斜阈值"
        else:
            state, badge = "unflagged", "本次未触发阈值"
        videos = []
        for video in row["videos"]:
            poster = f' poster="{escape(video["thumbnail"], quote=True)}"' if video.get("thumbnail") else ""
            videos.append(f'<video controls preload="metadata"{poster} src="{escape(video["path"], quote=True)}"></video>'
                          f'<p class="small">原片 {number(video["duration_seconds"], 2)} 秒，{video["width"]} × {video["height"]}，'
                          f'{escape(video["fps"])} FPS · <a href="{escape(video["path"], quote=True)}">下载 MP4</a></p>')
        if not videos:
            videos.append('<p class="missing">本次执行未生成可验收视频。查看下方失败报告。</p>')
        delta = sim.get("displacement_xy_m")
        delta_text = "未记录" if delta is None else ", ".join(number(value) for value in delta)
        links = " · ".join(f'<a href="{escape(item["path"], quote=True)}">{escape(item["kind"])}</a>'
                           for item in row["artifacts"] if item["kind"] in ("result.json", "trajectory.csv", "error.json", "execution.log"))
        command = "低速前进（1）" if row["command"] == 1 else "高速前进（6）"
        training = "有" if row["matching_released_training_bundle_available"] else "无"
        cards.append(f'''<article id="{escape(name, quote=True)}" data-state="{state}" data-search="{escape(name + ' ' + row['configuration'], quote=True)}">
<div class="card-head"><h2>{escape(LABELS[name])}</h2><span class="badge {state}">{badge}</span></div>
<p class="name">{escape(name)}</p><p class="config">源索引 {row['configuration_index']}（共 {row['available_configurations']} 组）：<code>{escape(row['configuration'])}</code></p>
{''.join(videos)}
<dl><div><dt>持续输入</dt><dd>{command}</dd></div><div><dt>实际策略时间</dt><dd>{number(sim.get('policy_simulation_seconds'))} s</dd></div>
<div><dt>XY 净位移</dt><dd>({delta_text}) m</dd></div><div><dt>XY 路径长度</dt><dd>{number(sim.get('path_length_xy_m'))} m</dd></div>
<div><dt>最低骨盆高度</dt><dd>{number(sim.get('minimum_pelvis_height_m'))} m</dd></div><div><dt>最低朝上余弦</dt><dd>{number(sim.get('minimum_base_up_z'))}</dd></div>
<div><dt>倾斜阈值累计时间</dt><dd>{number(sim.get('tilt_threshold_sample_seconds'))} s</dd></div><div><dt>同类发布训练数据</dt><dd>{training}</dd></div></dl>
<details><summary>配置、输入与原始证据</summary><p>这是所选场景的地形几何。持续前进指令没有重放参考动作中的翻滚、跳跃或翻越序列。</p>
<p class="hash">OBJ SHA-256：<code>{escape(row['mesh_sha256'])}</code></p><p>{links}</p></details></article>''')
    seconds = number(manifest["requested_policy_seconds"], 0)
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>G1 · 17 场景 ONNX 物理闭环</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{background:#121b26;color:#edf2f8;font:16px/1.55 system-ui;margin:0;padding:30px}}a{{color:#8dc7ff}}header,.toolbar,.counts{{max-width:1500px;margin:0 auto 24px}}h1{{font-size:30px;margin:0 0 12px}}p{{color:#bfd0df;margin:10px 0}}.counts{{display:flex;gap:12px;flex-wrap:wrap}}.counts span{{background:#203043;border:1px solid #395169;border-radius:8px;padding:10px 15px}}.toolbar{{display:flex;gap:12px;flex-wrap:wrap}}input,select{{font:inherit;color:inherit;background:#203043;border:1px solid #526980;border-radius:6px;padding:9px 12px}}input{{flex:1;min-width:240px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:24px;max-width:1500px;margin:auto}}article{{background:#203043;padding:18px;border-radius:12px;min-width:0}}.card-head{{display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap}}h2{{font-size:21px;margin:0}}.name{{font-size:14px;color:#91a9bd;margin-top:3px}}.config{{min-height:52px;font-size:14px;overflow-wrap:anywhere}}.badge{{font-size:12px;border-radius:99px;padding:5px 10px;background:#35485b;white-space:nowrap}}.threshold{{background:#6b3929;color:#ffd5bc}}.unflagged{{background:#23553f;color:#c2f1d4}}.execution_failed{{background:#74313d;color:#ffd5dd}}video{{width:100%;display:block;border-radius:6px;background:#0b1119;aspect-ratio:16/9}}.small{{font-size:12px}}dl{{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;margin:14px 0}}dl div{{min-width:0}}dt{{font-size:12px;color:#9cb5c9}}dd{{margin:1px 0;font-variant-numeric:tabular-nums;font-size:14px}}details{{border-top:1px solid #40566b;padding-top:10px;font-size:13px}}summary{{cursor:pointer;color:#b8dcff}}.hash{{overflow-wrap:anywhere}}.missing{{padding:30px 10px;background:#172330}}[hidden]{{display:none!important}}footer{{max-width:1500px;margin:28px auto;color:#91a9bd;font-size:13px}}code{{font-size:12px}}@media(max-width:600px){{body{{padding:18px}}h1{{font-size:25px}}}}
</style></head><body><header><h1>G1 · 17 场景 ONNX 物理闭环</h1>
<p>真实 MuJoCo 物理、原生 Unitree DDS 与深度共享内存、公开学生 ONNX 策略。每种场景只选一个完整生成配置的 OBJ，持续输入低速或高速前进，目标为 {seconds} 秒策略时间，seed {manifest['seed']}。本页覆盖 17 个代表几何，不是 629 个策略试验，也不证明同名参考技能或整个障碍课程完成。</p>
<p>高度/倾斜阈值：移除吊架后，骨盆高度 &lt; 0.4 m 或基座朝上余弦 &lt; 0.35。正常攀爬也可能触发倾斜阈值；未触发不等于课程成功。原片保留起始安置阶段，策略控制阶段吊架已移除。所有触发事件和执行失败均保留。</p>
<p><a href="manifest.json">媒体与来源 SHA-256</a> · <a href="matrix.json">完整原始验收矩阵</a></p></header>
<div class="counts"><span>代表场景 <b>{counts['planned']}</b></span><span>执行完成 <b>{counts['completed']}</b></span><span>未触发阈值 <b>{counts['unflagged']}</b></span><span>阈值事件 <b>{counts['threshold_triggered']}</b></span><span>执行失败 <b>{counts['execution_failed']}</b></span></div>
<div class="toolbar"><input id="search" type="search" placeholder="搜索场景或配置" aria-label="搜索场景或配置"><select id="state" aria-label="筛选结果"><option value="all">全部结果</option><option value="threshold">触发高度/倾斜阈值</option><option value="unflagged">未触发阈值</option><option value="execution_failed">执行失败</option></select><span id="visible"></span></div>
<main>{''.join(cards)}</main><footer>同类发布训练数据仅表示该类 bundle 可下载，不认证本次策略掌握该技能。完整输入选择规则、模型、镜像与地形哈希见原始矩阵。所有媒体由原片逐字节复制，页面不生成或修改机器人轨迹。</footer>
<script>const cards=[...document.querySelectorAll('article')],search=document.getElementById('search'),state=document.getElementById('state');function filter(){{let count=0;for(const card of cards){{card.hidden=!(card.dataset.search.toLowerCase().includes(search.value.toLowerCase())&&(state.value==='all'||card.dataset.state===state.value));if(!card.hidden)count++;}}document.getElementById('visible').textContent=count+' / '+cards.length+' 场景';}}search.addEventListener('input',filter);state.addEventListener('change',filter);filter();</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "usage_assets/sim2sim/scenarios")
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    try:
        validate_matrix(matrix)
    except ValueError as error:
        parser.error(str(error))
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("use an empty publication directory; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "scope": matrix["scope"], "source_matrix": str(args.matrix.resolve()),
                "source_matrix_sha256": digest(args.matrix), "image_id": matrix["image_id"], "seed": matrix["seed"],
                "model_sha256": matrix["model_sha256"], "requested_policy_seconds": matrix["seconds_per_scenario"],
                "selection_rule": matrix["selection_rule"], "quality_verified": False, "obstacle_course_completion_verified": False,
                "publisher_sha256": digest(Path(__file__)), "media_policy": "unaltered byte-for-byte copies of actual recordings and decoded thumbnails", "scenarios": []}
    by_name = {row["scenario"]: row for row in matrix["selections"]}
    for name in SCENARIOS:
        selection = by_name[name]
        source = host_path(selection["output"])
        destination = output / name
        destination.mkdir()
        artifacts = []

        def copy(path: Path, filename: str, kind: str) -> str:
            target = destination / filename
            before = digest(path)
            shutil.copy2(path, target)
            if digest(target) != before:
                raise ValueError(f"copied artifact changed: {path}")
            relative = target.relative_to(output).as_posix()
            artifacts.append({"path": relative, "kind": kind, "source": str(path), "sha256": before, "size": target.stat().st_size})
            return relative

        result = selection.get("result")
        row = {key: selection[key] for key in ("scenario", "configuration", "configuration_index", "available_configurations", "command", "mesh_sha256", "matching_released_training_bundle_available", "status")}
        row.update(videos=[], artifacts=artifacts, fall_detected=None, heuristic_survival_passed=None)
        for filename in ("result.json", "trajectory.csv", "error.json"):
            if (source / filename).is_file():
                if filename == "result.json" and json.loads((source / filename).read_text()) != result:
                    raise ValueError(f"matrix embeds a different result: {name}")
                copy(source / filename, filename, filename)
        if (args.matrix.parent / (name + ".log")).is_file():
            copy(args.matrix.parent / (name + ".log"), "execution.log", "execution.log")
        if selection["status"] == "completed":
            if not result or result.get("status") != "completed" or not result.get("video_checks"):
                raise ValueError(f"completed scene lacks its actual result or verified video: {name}")
            if result["config"].get("mesh_sha256") != selection["mesh_sha256"] or result["config"].get("model_sha256") != matrix["model_sha256"]:
                raise ValueError(f"rollout input hashes differ from the matrix: {name}")
            if not result["simulation"].get("gantry_disabled_during_policy"):
                raise ValueError(f"representative rollout was not recorded without gantry support: {name}")
            row.update(simulation=result["simulation"], inference=result["inference"], fall_detected=result["simulation"]["fall_detected"],
                       heuristic_survival_passed=result["survival_passed"])
            if row["heuristic_survival_passed"] == row["fall_detected"]:
                raise ValueError(f"inconsistent heuristic result: {name}")
        for index, check in enumerate((result or {}).get("video_checks", []), 1):
            video = source / check["video"]
            thumbnail = source / check["thumbnail"]
            probe = check["probe"]
            stream = probe["streams"][0]
            duration = float(probe["format"]["duration"])
            if duration <= 0 or min(stream["width"], stream["height"]) <= 0:
                raise ValueError(f"invalid recorded video metadata: {video}")
            header = thumbnail.read_bytes()[:24]
            if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (stream["width"], stream["height"]):
                raise ValueError(f"thumbnail does not match the video dimensions: {thumbnail}")
            row["videos"].append({"path": copy(video, f"rollout-{index:02}.mp4", "video"),
                                  "thumbnail": copy(thumbnail, f"rollout-{index:02}.png", "thumbnail"), "duration_seconds": duration,
                                  "width": stream["width"], "height": stream["height"], "fps": stream["avg_frame_rate"],
                                  "frames": stream.get("nb_frames"), "codec": stream["codec_name"]})
        manifest["scenarios"].append(row)
        print(f"Published {name}: {selection['status']}, threshold={row['fall_detected']}, videos={len(row['videos'])}", flush=True)
    rows = manifest["scenarios"]
    completed = sum(row["status"] == "completed" for row in rows)
    flagged = sum(row["status"] == "completed" and row["fall_detected"] for row in rows)
    manifest["counts"] = {"planned": len(rows), "completed": completed, "threshold_triggered": flagged,
                          "unflagged": completed - flagged, "execution_failed": len(rows) - completed,
                          "videos": sum(len(row["videos"]) for row in rows)}
    copy_source = output / "matrix.json"
    shutil.copy2(args.matrix, copy_source)
    if digest(copy_source) != manifest["source_matrix_sha256"]:
        raise ValueError("matrix changed during publication")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    (output / "playback.html").write_text(make_page(manifest))
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
