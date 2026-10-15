#!/usr/bin/env python3
"""Create small, traceable previews from existing rollout videos (CPU only)."""

import argparse
import hashlib
import html
import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[3]
SOURCE = pathlib.Path(__file__).with_name("sources.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stderr}")
    return result


def probe(path):
    return json.loads(run([
        "ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "format=duration:stream=width,height,codec_name,pix_fmt,r_frame_rate,nb_read_frames",
        "-of", "json", str(path),
    ]).stdout)


def href(path):
    return "../../../" + path


def esc(value):
    return html.escape(str(value), quote=True)


def facts(clip):
    names = {
        "policy_ticks": "策略tick", "reference_policy_seconds": "完整参考秒",
        "simulation_seconds": "完整仿真秒", "path_length_xy_m": "完整XY路径m",
        "minimum_pelvis_height_m": "最低骨盆m", "minimum_base_up_z": "最低朝上余弦",
        "final_base_up_z": "末态朝上余弦", "heading_change_deg": "累计转角°",
        "threshold_event": "高度/倾斜阈值事件", "survival_heuristic_passed": "存活启发式通过",
        "conservative_height_or_tilt_event": "高度/倾斜阈值事件",
        "low_pelvis_event": "低骨盆事件", "checkpoint_iteration": "checkpoint迭代",
        "num_envs": "评估环境数", "control_steps": "每环境控制步",
        "failed_resets": "整项失败reset", "clip_completions_excluding_failed_timeout_steps": "整项clip结束事件",
        "source_frames": "完整参考帧", "source_fps": "参考FPS",
    }
    rows = []
    for key, label in names.items():
        if key not in clip["metrics"]:
            continue
        value = clip["metrics"][key]
        if isinstance(value, bool):
            value = "是" if value else "否"
        elif isinstance(value, float):
            value = f"{value:.4f}"
        rows.append(f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def build_page(manifest):
    cards = []
    for clip in manifest["clips"] + manifest["kinematic_references"]:
        gif = clip.get("gif", {})
        gif_href = gif.get("path", href(clip.get("existing_gif", "")))
        timing = (f"GIF为原片{clip['gif_start_seconds']:.2f}–"
                  f"{clip['gif_start_seconds'] + clip['gif_duration_seconds']:.2f}秒，8 FPS、原速；"
                  "指标属于完整试验。") if gif else "复用原完整参考GIF；KINEMATIC / NO POLICY。"
        tag = {"flat": "平地策略", "reference-commands": "逐帧指令策略",
               "legacy": "历史接触/失败对照", "isaac": "正式Isaac评估",
               "kinematic": "参考运动 · 没有策略"}[clip["category"]]
        cards.append(f'''<article data-category="{esc(clip['category'])}">
<span class="tag">{esc(tag)}</span><h2>{esc(clip['title'])}</h2>
<p>{esc(clip['model_origin'])}</p>
<video controls preload="none" playsinline poster="{esc(href(clip['source_poster']))}" src="{esc(href(clip['source_video']))}"></video>
<p><a href="{esc(href(clip['source_video']))}">完整原始MP4</a> · <a href="{esc(gif_href)}">GIF预览</a> · <a href="{esc(href(clip['evidence']['path']))}">原始指标/来源</a></p>
<p class="observation">{esc(clip['visual_observation'])}</p>
<details><summary>查看GIF与抽取区间</summary><p>{esc(timing)}</p><img loading="lazy" src="{esc(gif_href)}" alt="{esc(clip['title'])}：原视频抽帧预览"></details>
<details><summary>完整试验指标与选取理由</summary>{facts(clip)}<p>{esc(clip['selection_reason'])}</p><p>{esc(clip.get('worker_exit_integrity', '参考位姿播放，不涉及策略worker退出验收。'))}</p></details>
</article>''')
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PHP Parkour 仿真实验视频与参考动作</title>
<style>
:root{font:16px/1.65 system-ui;color:#203047;background:#f3f6fa}body{max-width:1280px;margin:auto;padding:28px 20px}h1{font-size:30px;line-height:1.3}h2{font-size:21px;margin:10px 0}a{color:#175e9f}header{max-width:1000px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}button{font:inherit;border:1px solid #b8c6d7;border-radius:6px;background:white;padding:8px 12px;cursor:pointer}button[aria-pressed=true]{background:#173d68;color:white}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:20px}article{background:white;border:1px solid #ccd8e5;border-radius:10px;padding:18px;min-width:0}article[hidden]{display:none}video,img{width:100%;height:auto;display:block;background:#12253b;border-radius:5px}video{aspect-ratio:16/9}.tag{font-size:13px;border-radius:4px;padding:4px 8px;background:#e6edf7}.observation{border-left:3px solid #c48b36;padding-left:12px}details{margin-top:12px}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{text-align:left;border-bottom:1px solid #e2e7ee;padding:5px;font-size:14px}th{font-weight:500}code{overflow-wrap:anywhere}footer{margin-top:25px;font-size:14px}
</style></head><body><header>
<h1>仿真实验视频与参考动作</h1>
<p>并列观看正常跑动、从障碍旁经过、接触后恢复、真实跌倒，以及正式自训学生的Isaac原片。8个新增GIF由已有原视频抽取，另复用17类参考运动；本页没有重新运行策略。</p>
<p>全629逐帧指令试验中，321例触发高度/倾斜阈值、308例未触发；这些计数不是越障成功率。未触发的样例也可能绕开障碍。参考动作画面标有 <strong>KINEMATIC / NO POLICY</strong>，表示通过设置参考姿态播放。</p>
<p><a href="manifest.json">全部源SHA、抽帧参数和解码结果</a> · <a href="../../../usage.md">回到usage.md</a> · <a href="../../reports/reference629-full/playback.html">全部629逐帧原片</a> · <a href="../../reports/official-evaluations-six/playback.html">六项正式Isaac评估160段原片</a></p>
</header><nav aria-label="视频分类">
<button data-filter="all" aria-pressed="true">全部25项</button><button data-filter="flat">平地1项</button><button data-filter="reference-commands">逐帧指令4项</button><button data-filter="legacy">接触/失败2项</button><button data-filter="isaac">正式Isaac 1项</button><button data-filter="kinematic">参考运动17项</button>
</nav><p id="count" aria-live="polite">显示25项</p><main>''' + "\n".join(cards) + '''</main>
<footer>GIF只降低分辨率和帧率，原速播放，没有重排、轨迹平滑或补帧。完整原片、失败记录、原始指标均保留。选样与目检不能替代完整课程完成判据。</footer>
<script>
const buttons=[...document.querySelectorAll('button[data-filter]')];
buttons.forEach(button=>button.addEventListener('click',()=>{let count=0;document.querySelectorAll('article').forEach(card=>{card.hidden=button.dataset.filter!=='all'&&card.dataset.category!==button.dataset.filter;if(!card.hidden)count++;});buttons.forEach(item=>item.setAttribute('aria-pressed',String(item===button)));document.getElementById('count').textContent='显示'+count+'项';}));
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=SOURCE.parent)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(SOURCE.read_text())
    manifest["sources_sha256"] = sha(SOURCE)
    manifest["builder_sha256"] = sha(pathlib.Path(__file__))
    manifest["tools"] = {tool: run([tool, "-version"]).stdout.splitlines()[0]
                         for tool in ["ffmpeg", "ffprobe"]}
    for clip in manifest["clips"] + manifest["kinematic_references"]:
        for key in ["source_video", "source_poster", "existing_gif"]:
            if key in clip and sha(ROOT / clip[key]) != clip[key + "_sha256"]:
                raise RuntimeError(f"Source SHA mismatch: {clip[key]}")
        for key in ["evidence", "original_report", "corpus"]:
            if key in clip and sha(ROOT / clip[key]["path"]) != clip[key]["sha256"]:
                raise RuntimeError(f"Evidence SHA mismatch: {clip[key]['path']}")
        source = ROOT / clip["source_video"]
        metadata = probe(source)
        run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "1",
             "-i", str(source), "-f", "null", "-"])
        clip["source_metadata"] = metadata
        clip["source_full_decode_returncode"] = 0
        if "gif_start_seconds" not in clip:
            continue
        start, duration = clip["gif_start_seconds"], clip["gif_duration_seconds"]
        if start < 0 or start + duration > float(metadata["format"]["duration"]) + 0.001:
            raise RuntimeError(f"GIF interval outside source: {clip['id']}")
        target = output / (clip["id"] + ".gif")
        if target.exists():
            raise RuntimeError(f"Use a fresh output directory; file exists: {target}")
        filters = ("fps=8,scale=480:270:flags=lanczos,split[a][b];"
                   "[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a")
        command = ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "1",
                   "-ss", str(start), "-t", str(duration), "-i", str(source),
                   "-filter_complex_threads", "1", "-filter_complex", filters,
                   "-loop", "0", "-n", str(target)]
        run(command)
        run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "1",
             "-i", str(target), "-f", "null", "-"])
        gif_meta = probe(target)
        frames = int(gif_meta["streams"][0]["nb_read_frames"])
        if abs(float(gif_meta["format"]["duration"]) - duration) > 0.14 or frames <= 0:
            raise RuntimeError(f"Unexpected GIF duration/frame count: {target}")
        clip["gif"] = {"path": target.name, "sha256": sha(target), "bytes": target.stat().st_size,
                       "metadata": gif_meta, "full_decode_returncode": 0,
                       "command": command, "source_video_interval_seconds": [start, start + duration]}
        print(clip["id"], frames, target.stat().st_size, flush=True)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "playback.html").write_text(build_page(manifest))
    print(json.dumps({"status": "completed", "new_gifs": len(manifest["clips"]),
                      "reused_reference_gifs": len(manifest["kinematic_references"]),
                      "all_25_source_videos_full_decode_verified": True}))


if __name__ == "__main__":
    main()
