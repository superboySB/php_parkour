#!/usr/bin/env python3
"""Publish verified full629 physical evidence, or an explicitly partial preview.

Host standard library only. This tool never starts simulation or edits input
evidence. Full publication requires the frozen plan, successful terminal driver
receipt, all 629 completed cases and every retained input/artifact checksum.
Video, thumbnails and logs are copied byte for byte; plots use measured CSVs.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.sim2sim_scene_matrix import validate_worker_receipts

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_COUNTS = dict(zip((
    "random_locomotion", "low_speed_step", "high_speed_step", "low_speed_climb_58", "high_speed_climb_58",
    "low_speed_climb_76", "high_speed_climb_76", "low_speed_climb_94", "high_speed_climb_94",
    "low_speed_roll_78", "low_speed_roll_90", "high_speed_roll_134", "high_speed_hurdle",
    "high_speed_dash_vault", "high_speed_speed_vault", "high_speed_cat_vault", "high_speed_jump_35"),
    (100, 56, 60, 40, 40, 40, 40, 20, 15, 1, 3, 40, 51, 51, 20, 51, 1)))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_bytes(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"Nonfinite JSON literal: {value}")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def host_path(value: str) -> Path:
    path = Path(value)
    for prefix, target in ((Path("/workspace/php_parkour"), ROOT), (Path("/outputs"), ROOT / "outputs/research"),
                           (Path("/data/assets"), ROOT / "outputs/research/assets")):
        if path.is_relative_to(prefix):
            return target / path.relative_to(prefix)
    return path if path.is_absolute() else ROOT / path


def check_record(record: dict) -> Path:
    path = host_path(record["path"])
    size = record.get("bytes", record.get("size"))
    if not path.is_file() or path.is_symlink() or (size is not None and path.stat().st_size != size) or digest(path) != record["sha256"]:
        raise ValueError(f"Missing or changed retained file: {record['path']}")
    return path


def safe_child(directory: Path, relative: str) -> Path:
    path = (directory / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError(f"Unsafe or missing artifact path: {relative}")
    return path


def option(command: list, flag: str) -> str:
    if command.count(flag) != 1:
        raise ValueError(f"Expected one {flag} in retained argv")
    return command[command.index(flag) + 1]


def validate_plan(plan: dict, matrix: dict, expected_plan: str, expected_harness: str, preview: bool) -> None:
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in (expected_plan, expected_harness)):
        raise ValueError("Explicit expected plan and harness SHA256 are required")
    content = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if identity(content) != plan.get("plan_sha256") or plan.get("plan_sha256") != expected_plan:
        raise ValueError("Frozen plan identity changed")
    expected_total = sum(SCENARIO_COUNTS.values())
    if ((plan.get("schema_version") != 3 and not (preview and plan.get("schema_version") == 2)) or plan.get("status") != "planned" or plan.get("all_configurations") is not True
            or plan.get("planned_configurations") != expected_total or plan.get("planned_scenarios") != len(SCENARIO_COUNTS)
            or plan.get("seed") != 42 or plan.get("seconds_per_configuration") != 10
            or plan.get("quality_verified") is not False or plan.get("obstacle_course_completion_verified") is not False
            or len(plan["selections"]) != expected_total):
        raise ValueError("Expected the fixed 17-scenario/629-configuration, seed42, 10-second plan")
    if any(matrix.get(k) != v for k, v in plan.items() if k not in ("status", "selections")) or len(matrix["selections"]) != expected_total:
        raise ValueError("Matrix immutable fields differ from the frozen plan")
    if not any(Path(r["path"]).name == "sim2sim_scene_matrix.py" and r["sha256"] == expected_harness for r in plan["dependencies"]):
        raise ValueError("Frozen production harness missing from plan dependencies")
    seen = set()
    ordinal = 0
    for scenario, count in SCENARIO_COUNTS.items():
        for index in range(count):
            p, row = plan["selections"][ordinal], matrix["selections"][ordinal]
            if (p["scenario"] != scenario or p["configuration_index"] != index or p["available_configurations"] != count
                    or p["case_id"] in seen or any(row.get(k) != v for k, v in p.items())):
                raise ValueError("Case order, source index or immutable case identity changed")
            if (len(p["source_files"]) != 3 or {Path(r["path"]).suffix for r in p["source_files"]} != {".npz", ".npy", ".obj"}
                    or not any(r["path"] == p["mesh"] and r["sha256"] == p["mesh_sha256"] for r in p["source_files"])):
                raise ValueError("Invalid motion/terrain/OBJ source triple")
            seen.add(p["case_id"])
            ordinal += 1


def validate_driver(receipt: dict, launch: dict, wrapper: Path, plan: dict, matrix: dict, matrix_sha: str, preview: bool, expected_harness: str) -> None:
    if (digest(wrapper) != launch["launcher_sha256"] or launch.get("launch_exit_code") != 0
            or receipt.get("image_id") != plan["image_id"] or launch.get("image_id") != plan["image_id"]
            or receipt.get("harness_sha256") != expected_harness or receipt.get("quality_verified") is not False):
        raise ValueError("Driver wrapper, image or frozen harness identity mismatch")
    command = receipt["command"]
    if ("--all-configs" not in command
            or option(command, "--matrix") != plan["source_matrix"]
            or option(command, "--models") != str(Path(plan["models"][0]["path"]).parent)
            or option(command, "--image-id") != plan["image_id"] or float(option(command, "--seconds")) != 10
            or host_path(option(command, "--output")).resolve() != host_path(plan["selections"][0]["output"]).parent.parent.resolve()
            or not any(Path(arg).name == "sim2sim_scene_matrix.py" for arg in command)):
        raise ValueError("Driver argv is not bound to this fixed full629 plan")
    if preview:
        return
    total = sum(SCENARIO_COUNTS.values())
    if (receipt.get("status") != "completed" or receipt.get("returncode") != 0 or receipt.get("completion_verified") is not True
            or receipt.get("completed_configurations") != total or receipt.get("matrix_sha256") != matrix_sha
            or not receipt.get("finished_utc") or matrix.get("status") != "completed"
            or matrix.get("completed_configurations") != total or matrix.get("completed_scenarios") != len(SCENARIO_COUNTS)
            or matrix.get("configuration_coverage_complete") is not True or not matrix.get("finished_unix")):
        raise ValueError("Full publication requires actual terminal driver exit0 and completed629 matrix/hash/coverage")


def validate_case(plan: dict, row: dict) -> dict:
    if row.get("status") != "completed" or row.get("returncode") != 0 or not row.get("attempts"):
        raise ValueError(f"Case has no successful terminal execution: {row['case_id']}")
    attempt = row["attempts"][-1]
    if attempt.get("status") != "completed" or attempt.get("returncode") != 0:
        raise ValueError("Last attempt is not completed exit0")
    evidence_path = check_record(attempt["evidence"])
    evidence = load_bytes(evidence_path.read_bytes())
    directory = host_path(attempt["output"]).resolve()
    expected_launch = list(row["launch"])
    expected_launch[expected_launch.index("--output") + 1] = attempt["output"]
    expected_input = {k: plan[k] for k in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
        "case_id": row["case_id"], "source_files": row["source_files"], "launch": row["launch"]}
    if (evidence_path.resolve() != directory / "case-evidence.json" or evidence["case_input"] != expected_input
            or attempt["launch"] != expected_launch or evidence["execution"] != {
                "output": attempt["output"], "launch": expected_launch, "log": attempt["log"], "returncode": 0}
            or evidence.get("expected_policy_ticks") != 500):
        raise ValueError("Retained evidence input/attempt/argv/provenance mismatch")
    check_record(attempt["log"])
    retained = set()
    for record in evidence["files"]:
        path = check_record(record).resolve()
        if not path.is_relative_to(directory) or path in retained:
            raise ValueError("Unsafe or duplicate retained artifact")
        retained.add(path)
    result_path = directory / "result.json"
    if row.get("result_report") != str(Path(attempt["output"]) / "result.json") or digest(result_path) != evidence["result_sha256"]:
        raise ValueError("Result report path/checksum mismatch")
    result = load_bytes(result_path.read_bytes())
    if result != row["result"]:
        raise ValueError("Embedded and independent native results differ")
    if plan.get("schema_version") == 3:
        receipts = validate_worker_receipts(directory, plan, result, translate=host_path)
        expected_receipts = {host_path(record["path"]).resolve(): record for record in evidence.get("worker_receipts", [])}
        if (len(expected_receipts) != 3 or any(record["sha256"] != expected_receipts.get(Path(record["path"]), {}).get("sha256")
                or record["bytes"] != expected_receipts.get(Path(record["path"]), {}).get("bytes") for record in receipts)):
            raise ValueError("Worker process receipt fingerprints differ from retained evidence")
        required = {directory / name for name in ("worker-processes.json", "simulator-process-start.json", "inference-process-start.json")}
        if not required.issubset(retained):
            raise ValueError("Worker process receipts absent from retained evidence")
    cfg, sim, inference = result["config"], result["simulation"], result["inference"]
    if (any(item.get("status") != "completed" for item in (result, sim, inference)) or cfg["model_sha256"] != plan["model_sha256"]
            or cfg["mesh"] != row["mesh"] or cfg["mesh_sha256"] != row["mesh_sha256"]
            or cfg["models"] != str(Path(plan["models"][0]["path"]).parent) or cfg["commands"] != [row["command"]]
            or cfg["seed"] != plan["seed"] or cfg["gl"] != option(row["launch"], "--gl")
            or cfg["duration"] != 10 or cfg["record_policy"] or cfg["course_guide"]
            or inference["ticks"] != 500 or inference["control_period_simulation_seconds"] != .02
            or not inference["lifecycle"]["damping_mode_active"] or not inference["lifecycle"]["policy_action_disabled"]
            or sim["gantry_disabled_during_policy"] is not True or not 10 <= sim["policy_simulation_seconds"] < 10.1
            or result.get("quality_verified") is not False or result.get("obstacle_course_completion_verified") is not False
            or type(sim["fall_detected"]) is not bool or result["survival_passed"] is not (not sim["fall_detected"])):
        raise ValueError("Native config/500 ticks/unsupported policy lifecycle or heuristic mismatch")
    trajectory_path = directory / "trajectory.csv"
    trajectory = list(csv.DictReader(io.StringIO(trajectory_path.read_text())))
    if not trajectory or any(not math.isfinite(float(v)) for r in trajectory for v in r.values()):
        raise ValueError("Missing or nonfinite measured trajectory")
    active = [r for r in trajectory if float(r["policy_seconds"]) >= 0]
    if len(active) < 500 or any(float(r["gantry_enabled"]) != 0 for r in active):
        raise ValueError("Insufficient unsupported trajectory samples")
    checks = result["video_checks"]
    if not checks or len(checks) != len(result["videos"]) or {c["video"] for c in checks} != set(result["videos"]):
        raise ValueError("Missing/duplicate native video checks")
    mandatory = {result_path, trajectory_path}
    for check in checks:
        video, png = (safe_child(directory, check[k]) for k in ("video", "thumbnail"))
        probe = check["probe"]; stream = probe["streams"][0]
        duration = float(probe["format"]["duration"])
        header = png.read_bytes()[:24]
        if (not math.isfinite(duration) or duration <= 0 or min(stream["width"], stream["height"]) <= 0
                or header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (stream["width"], stream["height"])):
            raise ValueError("Invalid video metadata or PNG dimensions")
        mandatory.update((video, png))
    if not mandatory <= retained:
        raise ValueError("Result/trajectory/media absent from retained checksummed evidence")
    # Reject unrecorded additions to completed evidence instead of silently dropping them.
    actual = {p.resolve() for p in directory.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob("*")) or actual != retained | {evidence_path.resolve()}:
        raise ValueError("Completed output file set changed after retention")
    return {"row": row, "directory": directory, "evidence": evidence, "trajectory": active, "result": result}


def owned_attempt_files(directory: Path, all_directories: list[Path]) -> list[Path]:
    """Separate recorded retries; refuse an otherwise silently skipped retry."""
    nested = [p for p in all_directories if p != directory and p.is_relative_to(directory)]
    if not directory.exists():
        return []
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in retained attempt output")
        if any(path == p or path.is_relative_to(p) for p in nested):
            continue
        if path.is_dir() and path.name.startswith("attempt-"):
            raise ValueError("Unrecorded attempt directory would be omitted")
        if path.is_file():
            files.append(path)
    return files


def validate_attempt_archive(plan: dict, row: dict, attempt: dict, all_directories: list[Path]) -> dict:
    directory = host_path(attempt["output"]).resolve()
    files = owned_attempt_files(directory, all_directories)
    expected_launch = list(row["launch"])
    expected_launch[expected_launch.index("--output") + 1] = attempt["output"]
    if attempt["launch"] != expected_launch:
        raise ValueError("Historical attempt launch changed")
    if attempt.get("log"):
        check_record(attempt["log"])
    sealed = bool(attempt.get("evidence"))
    if sealed:
        evidence_path = check_record(attempt["evidence"]).resolve()
        evidence = load_bytes(evidence_path.read_bytes())
        expected_input = {k: plan[k] for k in ("plan_sha256", "image_id", "source_matrix_sha256", "model_sha256")} | {
            "case_id": row["case_id"], "source_files": row["source_files"], "launch": row["launch"]}
        if (evidence_path != directory / "case-evidence.json" or evidence["case_input"] != expected_input
                or evidence["execution"] != {"output": attempt["output"], "launch": expected_launch,
                    "log": attempt.get("log"), "returncode": attempt.get("returncode")}):
            raise ValueError("Historical sealed attempt identity/execution changed")
        retained = set()
        for r in evidence["files"]:
            path = check_record(r).resolve()
            if not path.is_relative_to(directory) or path in retained:
                raise ValueError("Unsafe or duplicate historical artifact")
            retained.add(path)
        if retained | {evidence_path} != set(files):
            raise ValueError("Historical sealed artifact set changed")
        if evidence.get("result_sha256") and digest(directory / "result.json") != evidence["result_sha256"]:
            raise ValueError("Historical sealed result checksum changed")
        # Keep the original seal's expectations through copying. Rehashing here
        # would accept a file changed after check_record verified the seal.
        fingerprints = [{**record, "path": str(host_path(record["path"]).resolve())}
                        for record in [*evidence["files"], attempt["evidence"]]]
    else:
        fingerprints = [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]
    # No seal means only the current original bytes can be fingerprinted. This
    # is preserved failed-attempt history, never retroactively verified physics.
    return {"sealed": sealed, "integrity_scope": "retained seal and files verified" if sealed else "unsealed history: current original byte fingerprints only",
            "files": fingerprints}


def validate_all(plan: dict, matrix: dict, receipt: dict, launch: dict, wrapper: Path, matrix_sha: str, preview_count=0, *, expected_plan=None, expected_harness=None) -> list[dict]:
    validate_plan(plan, matrix, expected_plan, expected_harness, bool(preview_count))
    validate_driver(receipt, launch, wrapper, plan, matrix, matrix_sha, bool(preview_count), expected_harness)
    for record in [plan["source_matrix_record"], *plan["dependencies"], *plan["models"],
                   *(record for row in plan["selections"] for record in row["source_files"])]:
        check_record(record)
    rows = matrix["selections"]
    if preview_count:
        if type(preview_count) is not int or not 1 <= preview_count <= 2:
            raise ValueError("Preview is restricted to one or two actual completed cases")
        rows = [r for r in rows if r.get("status") == "completed"][:preview_count]
        if len(rows) != preview_count:
            raise ValueError("Preview lacks requested completed real cases")
    verified = []
    for row in rows:
        item = validate_case(plan, row)
        directories = [host_path(a["output"]).resolve() for a in row["attempts"]]
        if len(set(directories)) != len(directories) or len({a["number"] for a in row["attempts"]}) != len(directories):
            raise ValueError("Duplicate retained attempt directory or number")
        item["attempt_archives"] = [validate_attempt_archive(plan, row, a, directories) for a in row["attempts"]]
        verified.append(item)
    return verified


def trajectory_svg(rows: list[dict]) -> str:
    points = [(float(r["x_m"]), float(r["y_m"])) for r in rows]
    xs, ys = zip(*points); lowx, highx, lowy, highy = min(xs), max(xs), min(ys), max(ys)
    scale = min(570 / max(highx - lowx, .1), 300 / max(highy - lowy, .1))
    def xy(x, y): return 45 + (x - lowx) * scale, 340 - (y - lowy) * scale
    path = " ".join(f"{px:.2f},{py:.2f}" for px, py in (xy(x, y) for x, y in points))
    start, end = xy(*points[0]), xy(*points[-1])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 390" role="img" aria-label="Measured world XY trajectory">'
            '<rect width="660" height="390" fill="#142334"/><g fill="#cbd8e8" font-family="sans-serif" font-size="14">'
            f'<text x="24" y="25">Measured world XY (m), policy stage; +Y upward</text><text x="24" y="373">'
            f'X [{lowx:.3f}, {highx:.3f}], Y [{lowy:.3f}, {highy:.3f}] — start circle, end cross</text></g>'
            f'<polyline points="{path}" fill="none" stroke="#80c7ff" stroke-width="2"/>'
            f'<circle cx="{start[0]:.2f}" cy="{start[1]:.2f}" r="5" fill="#74e5ab"/>'
            f'<path d="M{end[0]-5:.2f},{end[1]-5:.2f}l10,10m0,-10l-10,10" stroke="#ffc48a" stroke-width="3"/></svg>')


def make_page(summary: dict, cases: list[dict]) -> str:
    data = json.dumps(cases, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    title = "PREVIEW · 2-case interface check" if summary["preview"] else "G1 · all 629 configuration rollouts"
    if summary["preview"]:
        title = f'PREVIEW · {len(cases)} cases · full629 not certified'
        if summary.get("legacy_normal_exit_unverified"):
            title += ' · historical status, worker exits unverified'
    scene_options = ''.join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in SCENARIO_COUNTS)
    scene_rows = ''.join(f'<tr><td>{html.escape(r["scenario"])}</td><td>{r["configurations"]}</td><td>{r["threshold_events"]}</td><td>{r["no_threshold_events"]}</td></tr>' for r in summary["scenarios"])
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + html.escape(title) + '''</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#101a27;color:#edf4fc;font:15px/1.6 system-ui;margin:0;padding:24px}header,.toolbar,.pager,main,footer{max-width:1500px;margin:0 auto 22px}h1{font-size:29px;margin:0}a{color:#92c9ff}p{color:#c0d0e0}.warning{padding:14px;background:#503627;border:1px solid #bc8357;border-radius:8px}.toolbar,.pager{display:flex;gap:10px;flex-wrap:wrap;align-items:center}input,select,button{font:inherit;color:inherit;background:#23374d;border:1px solid #647c95;border-radius:6px;padding:8px}input{min-width:240px;flex:1}button{cursor:pointer}button:disabled{opacity:.4}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:20px}article{background:#1d2e43;padding:17px;border-radius:10px;min-width:0}h2{font-size:19px;margin:0}.name,code{overflow-wrap:anywhere}.small{font-size:12px}.badge{display:inline-block;border-radius:20px;padding:3px 10px;background:#285542}.threshold{background:#713c2c}video,img{display:block;width:100%;background:#101923;border-radius:5px}video{aspect-ratio:16/9}.facts{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px}.facts span{padding:4px;background:#142338}details{margin:12px 0}summary{cursor:pointer}table{border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #41536a;padding:5px 14px;text-align:left}.preview{color:#ffc27f}footer{font-size:13px;color:#a8bed4}
</style></head><body><header><h1>''' + html.escape(title) + '''</h1><p class="warning">''' + (
        ('本页仅为两例以内的历史reported completed身体数据预览；旧监督未证明全部worker正常退出，不能作为通过验收。'
         if summary.get('legacy_normal_exit_unverified') else
         '本页仅为两例以内的实际结果预览，测试离线页面与媒体；完整629扫描尚未通过发布门卫。') if summary['preview'] else
        '固定计划的629个配置均完成10秒物理rollout及500策略ticks。629是配置数量，不代表629种独立几何，更不代表629种技能成功。') + '''
使用发布学生ONNX、原生DDS/深度SHM、MuJoCo/PD，恒定forward输入；不是reference replay。所有高度/倾斜阈值事件与历史失败attempt原样保留。未触发阈值不等于课程完成；正常攀爬也可能触发倾斜阈值。quality_verified=false。</p>
<p><a href="summary.json">机器汇总</a> · <a href="cases.json">逐配置JSON</a> · <a href="cases.csv">逐配置CSV</a> · <a href="matrix.json">原始matrix</a> · <a href="plan.json">固定plan</a> · <a href="evidence-manifest.json">完整SHA清单</a></p>
<details><summary>17场景统计（阈值不是技能成功率）</summary><table><thead><tr><th>场景</th><th>本页配置</th><th>高度/倾斜事件</th><th>未触发</th></tr></thead><tbody>''' + scene_rows + '''</tbody></table></details></header>
<div class="toolbar"><input id="search" type="search" placeholder="搜索场景、配置、case ID、mesh SHA" aria-label="搜索配置"><select id="scene" aria-label="场景"><option value="all">全部场景</option>''' + scene_options + '''</select><select id="state" aria-label="阈值"><option value="all">全部结果</option><option value="threshold">触发高度/倾斜阈值</option><option value="unflagged">未触发阈值</option></select><span id="visible"></span></div>
<div class="pager"><button id="previous">上一页</button><span id="page"></span><button id="next">下一页</button></div><main id="cards"></main><footer>视频、PNG、JSON、CSV和日志均从原证据逐字节复制。世界XY图只绘制CSV中的policy阶段实际位置，未平滑或改写轨迹。媒体按页加载；file://或标准库HTTP服务均可离线使用。</footer>
<script id="case-data" type="application/json">''' + data + '''</script><script>
const cases=JSON.parse(document.getElementById('case-data').textContent),search=document.getElementById('search'),scene=document.getElementById('scene'),state=document.getElementById('state');let page=0,selected=cases;const pageSize=24;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v).toFixed(3);
function render(){const pages=Math.max(1,Math.ceil(selected.length/pageSize));page=Math.min(page,pages-1);document.getElementById('visible').textContent=selected.length+' / '+cases.length+' 配置';document.getElementById('page').textContent=(page+1)+' / '+pages;document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page===pages-1;
document.getElementById('cards').innerHTML=selected.slice(page*pageSize,(page+1)*pageSize).map(r=>`<article data-case="${esc(r.case_id)}" data-state="${r.threshold_event?'threshold':'unflagged'}"><h2>${esc(r.scenario)} · ${r.configuration_index}</h2><span class="badge ${r.threshold_event?'threshold':''}">${r.threshold_event?'触发高度/倾斜阈值':'本次未触发阈值'}</span><p class="name small">${esc(r.configuration)}</p>${r.videos.map(v=>`<video controls preload="none" poster="${esc(v.thumbnail)}" src="${esc(v.path)}"></video><p class="small"><a href="${esc(v.path)}">原始MP4</a> · ${num(v.duration_seconds)}s · ${v.width}×${v.height}</p>`).join('')}<div class="facts"><span>${r.policy_ticks} ticks · ${num(r.policy_seconds)}s</span><span>command ${r.command} · seed42</span><span>最低pelvis ${num(r.minimum_pelvis_height_m)}m</span><span>最低up ${num(r.minimum_base_up_z)}</span><span>XY路径 ${num(r.path_length_xy_m)}m</span><span>末态up ${num(r.final_base_up_z)}</span></div><details class="trajectory"><summary>实际世界XY轨迹与截图</summary><img loading="lazy" src="${esc(r.trajectory_svg)}" alt="Measured world XY trajectory">${r.videos.map(v=>`<a href="${esc(v.thumbnail)}"><img loading="lazy" src="${esc(v.thumbnail)}" alt="Original decoded thumbnail"></a>`).join('')}<a href="${esc(r.trajectory_csv)}">原始world XYZ/倾斜CSV</a></details><details><summary>SHA、原始结果和全部attempt</summary><p class="small">OBJ SHA ${esc(r.mesh_sha256)}。${r.attempts.length} 次attempt；失败记录未删除。没有按reference技能序列控制。</p><p><a href="${esc(r.result_json)}">result JSON</a> · <a href="${esc(r.case_evidence)}">case-evidence</a> · <a href="${esc(r.attempts_json)}">全部attempt原始文件链接</a></p></details></article>`).join('');}
function filter(){const q=search.value.toLowerCase();selected=cases.filter(r=>(r.case_id+' '+r.configuration+' '+r.mesh_sha256).toLowerCase().includes(q)&&(scene.value==='all'||r.scenario===scene.value)&&(state.value==='all'||(r.threshold_event?'threshold':'unflagged')===state.value));page=0;render();}search.addEventListener('input',filter);scene.addEventListener('change',filter);state.addEventListener('change',filter);document.getElementById('previous').onclick=()=>{page--;render();};document.getElementById('next').onclick=()=>{page++;render();};filter();
</script></body></html>'''


def publish(args) -> dict:
    output = args.output.resolve()
    preview = bool(args.preview_case_count)
    if preview and not output.is_relative_to((ROOT / "outputs/research").resolve()):
        raise ValueError("Preview output must remain in ignored outputs/research, never published usage_assets")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory; existing evidence is preserved")
    if output.is_relative_to(args.matrix.resolve().parent) or output.is_relative_to(args.driver_receipt.resolve().parent):
        raise ValueError("Publication cannot modify the running/raw evidence directory")
    raw = {name: path.read_bytes() for name, path in (("plan.json", args.plan), ("matrix.json", args.matrix),
           ("driver-receipt.json", args.driver_receipt), ("driver-launch.json", args.driver_launch))}
    plan, matrix, receipt, launch = (load_bytes(raw[name]) for name in ("plan.json", "matrix.json", "driver-receipt.json", "driver-launch.json"))
    verified = validate_all(plan, matrix, receipt, launch, args.driver_wrapper, hashlib.sha256(raw["matrix.json"]).hexdigest(), args.preview_case_count,
                            expected_plan=args.expected_plan_sha256, expected_harness=args.expected_harness_sha256)
    expected_copy_hashes = {host_path(r["path"]).resolve(): r["sha256"] for item in verified for r in item["evidence"]["files"]}
    for item in verified:
        for archive in item["attempt_archives"]:
            for record in archive["files"]:
                expected_copy_hashes[Path(record["path"]).resolve()] = record["sha256"]
    for item in verified:
        for attempt in item["row"]["attempts"]:
            for key in ("evidence", "log"):
                if attempt.get(key): expected_copy_hashes[host_path(attempt[key]["path"]).resolve()] = attempt[key]["sha256"]
    expected_copy_hashes[args.driver_wrapper.resolve()] = launch["launcher_sha256"]
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".publishing-", dir=output.parent))
    copied = []
    def copy(src: Path, rel: str) -> str:
        target = staging / rel; target.parent.mkdir(parents=True, exist_ok=True)
        source_sha = digest(src)
        if src.resolve() in expected_copy_hashes and source_sha != expected_copy_hashes[src.resolve()]:
            raise ValueError(f"Verified artifact changed before copy: {src}")
        shutil.copyfile(src, target)
        if digest(src) != source_sha or digest(target) != source_sha:
            raise ValueError(f"Source changed during byte copy: {src}")
        copied.append({"path": rel, "source": str(src), "sha256": source_sha, "bytes": target.stat().st_size})
        return rel
    try:
        for name, content in raw.items(): (staging / name).write_bytes(content)
        copy(args.driver_wrapper, "sources/full_driver.py")
        copy(Path(__file__), "sources/publish_full_scene_matrix.py")
        cases = []
        for ordinal, item in enumerate(verified):
            row, result = item["row"], item["result"]; sim = result["simulation"]
            prefix = f'cases/{row["scenario"]}/config-{row["configuration_index"]:04d}'
            attempts = []
            for attempt, archive in zip(row["attempts"], item["attempt_archives"]):
                directory = host_path(attempt["output"]).resolve(); folder = f'{prefix}/attempt-{attempt["number"]:04d}'
                files = []
                for record in archive["files"]:
                    src = Path(record["path"])
                    files.append(copy(src, folder + "/" + src.relative_to(directory).as_posix()))
                parent_log = copy(check_record(attempt["log"]), folder + "/parent-execution.log") if attempt.get("log") else None
                attempts.append({"number": attempt["number"], "status": attempt["status"], "returncode": attempt.get("returncode"),
                                 "files": files, "parent_log": parent_log, "original_receipt": attempt,
                                 "sealed": archive["sealed"], "integrity_scope": archive["integrity_scope"]})
            current = f'{prefix}/attempt-{row["attempts"][-1]["number"]:04d}'
            (staging / (prefix + "/attempts.json")).write_text(json.dumps(attempts, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
            svg = prefix + "/world-xy.svg"; (staging / svg).write_text(trajectory_svg(item["trajectory"]))
            videos = []
            for check in result["video_checks"]:
                stream = check["probe"]["streams"][0]
                videos.append({"path": current + "/" + check["video"], "thumbnail": current + "/" + check["thumbnail"],
                               "duration_seconds": float(check["probe"]["format"]["duration"]), "width": stream["width"], "height": stream["height"]})
            cases.append({"ordinal": ordinal, **{k: row[k] for k in ("case_id", "scenario", "configuration", "configuration_index", "command", "mesh_sha256")},
                          "status": "completed", "policy_ticks": result["inference"]["ticks"], "policy_seconds": sim["policy_simulation_seconds"],
                          "threshold_event": sim["fall_detected"], **{k: sim[k] for k in ("minimum_pelvis_height_m", "minimum_base_up_z", "final_base_up_z", "path_length_xy_m", "final_position_xyz_m")},
                          "videos": videos, "trajectory_svg": svg, "trajectory_csv": current + "/trajectory.csv", "result_json": current + "/result.json",
                          "case_evidence": current + "/case-evidence.json", "attempts_json": prefix + "/attempts.json", "attempts": attempts,
                          "quality_verified": False, "obstacle_course_completion_verified": False})
        scenes = []
        for name in SCENARIO_COUNTS:
            rows = [r for r in cases if r["scenario"] == name]; flags = sum(r["threshold_event"] for r in rows)
            scenes.append({"scenario": name, "planned_configurations": SCENARIO_COUNTS[name], "configurations": len(rows), "threshold_events": flags,
                           "no_threshold_events": len(rows) - flags, "historical_noncompleted_attempts": sum(a["status"] != "completed" for r in rows for a in r["attempts"])})
        summary = {"schema_version": 1, "status": "preview" if preview else "completed_publication", "preview": preview,
                   "legacy_normal_exit_unverified": plan.get("schema_version") == 2,
                   "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "plan_sha256": plan["plan_sha256"], "image_id": plan["image_id"],
                   "matrix_sha256": hashlib.sha256(raw["matrix.json"]).hexdigest(), "model_sha256": plan["model_sha256"], "configurations": len(cases),
                   "planned_configurations": sum(SCENARIO_COUNTS.values()), "policy_ticks": sum(r["policy_ticks"] for r in cases),
                   "policy_seconds": sum(r["policy_seconds"] for r in cases), "threshold_events": sum(r["threshold_event"] for r in cases),
                   "no_threshold_events": sum(not r["threshold_event"] for r in cases), "scenarios": scenes,
                   "scope": "Configuration coverage of constant-forward native ONNX physical rollouts; not 629 independent geometries or successful skills. All threshold events and historical attempts retained.",
                   "configuration_coverage_complete": not preview, "quality_verified": False, "obstacle_course_completion_verified": False,
                   "media_policy": "Original video/PNG/log/JSON/CSV bytes, no transcoding or trajectory smoothing; derived world XY SVG from measured policy trajectory only",
                   "publisher_sha256": digest(Path(__file__))}
        for name, obj in (("summary.json", summary), ("cases.json", cases), ("scenarios.json", scenes)):
            (staging / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        fields = ["ordinal", "case_id", "scenario", "configuration_index", "configuration", "command", "mesh_sha256", "policy_ticks", "policy_seconds", "threshold_event",
                  "minimum_pelvis_height_m", "minimum_base_up_z", "final_base_up_z", "path_length_xy_m", "result_json", "trajectory_csv"]
        with (staging / "cases.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(cases)
        (staging / "playback.html").write_text(make_page(summary, cases))
        records = [{"path": p.relative_to(staging).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(staging.rglob("*")) if p.is_file()]
        manifest = {"schema_version": 1, "preview": preview, "source_matrix_sha256": summary["matrix_sha256"], "plan_sha256": plan["plan_sha256"],
                    "files": records, "byte_copies": copied, "bytes_excluding_manifest": sum(r["bytes"] for r in records)}
        (staging / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        if args.plan.read_bytes() != raw["plan.json"]:
            raise ValueError("Plan changed during publication")
        if not preview and (args.matrix.read_bytes() != raw["matrix.json"] or args.driver_receipt.read_bytes() != raw["driver-receipt.json"]):
            raise ValueError("Terminal matrix/driver receipt changed during publication")
        if output.exists(): output.rmdir()
        staging.rename(output)
        return summary
    except BaseException:
        shutil.rmtree(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True,
                        help="Identity from the independently frozen cohort plan")
    parser.add_argument("--expected-harness-sha256", required=True,
                        help="SHA256 of that cohort sim2sim_scene_matrix.py source")
    for name in ("plan", "matrix", "driver-receipt", "driver-launch", "driver-wrapper", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--preview-case-count", type=int, choices=(1, 2), default=0,
                        help="Only actual completed cases; output restricted to ignored outputs/research, never a full publication")
    args = parser.parse_args()
    try:
        summary = publish(args)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        parser.error(str(error))
    print(json.dumps({k: summary[k] for k in ("status", "configurations", "threshold_events", "configuration_coverage_complete")}, indent=2))


if __name__ == "__main__":
    main()
