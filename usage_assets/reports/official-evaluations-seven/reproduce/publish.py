#!/usr/bin/env python3
"""Publish the actual seven-stage CPU result; does not run a policy."""
import datetime
import hashlib
import html
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def esc(value):
    return html.escape(str(value), quote=True)


def main():
    contract = load(PACKAGE / "control/input-contract.json")
    report = load(PACKAGE / "cpu-01/results/report.json")
    execution = load(PACKAGE / "cpu-01/host/execution.json")
    require(execution["actualpassed"] is True and execution["actual_start_attached_wait_returncode"] == execution["actual_container_exit_code"] == 0, "Actual CPU exit0 required")
    require(report["status"] == "passed" and report["counts"] == {"stages": 7, "videos_attempted": 191, "videos_passed": 191}, "Full seven-stage CPU evidence required")
    require(report["input_before"] == report["input_after"] and execution["inputs_unchanged"] is True and execution["source_unchanged"] is True, "Inputs and source must be unchanged")
    stages, flat = [], []
    for stage, actual in zip(contract["stages"], report["stages"]):
        require(stage["label"] == actual["label"] and actual["status"] == "passed", "Stage ordering or status differs")
        for key in ["manifest", "training_manifest", "quality", "config", "log"]:
            flat.append(stage[key])
        flat.extend(stage["events"] + stage["videos"])
        q = load(PACKAGE / stage["quality"]["path"].removeprefix("/"))
        m = load(PACKAGE / stage["manifest"]["path"].removeprefix("/"))
        chosen = actual["representative_thumbnail"]["value"]
        original = next(v for v in actual["videos"] if v["native_path"] == chosen["source_native_path"])
        stream = original["metadata"]["streams"][0]
        stages.append({
            "label": stage["label"], "native_status": m["status"], "native_returncode": m["returncode"],
            **{key: q[key] for key in ["checkpoint_iteration", "checkpoint", "checkpoint_sha256", "registry_order", "num_envs", "control_steps", "control_dt_seconds", "sim_seconds_per_env", "total_env_seconds", "failed_resets", "timeout_resets", "clip_completions_excluding_failed_timeout_steps", "metrics", "quality_verified"]},
            "native_described_videos": len(stage["videos"]),
            "quality_bound_videos": sum(v["quality_bound"] for v in stage["videos"]),
            "quality_json": stage["quality"]["path"].removeprefix("/"),
            "native_manifest": stage["manifest"]["path"].removeprefix("/"),
            "tensorboard_scalar_tags": len(actual["tensorboard"]["value"]["matched_tags"]),
            "strict_TFRecord_records": sum(e["records"] for e in actual["tensorboard"]["value"]["event_integrity"]["events"]),
            "representative": {"path": original["path"].removeprefix("/"), "bytes": original["bytes"],
                               "sha256": original["sha256"], "duration_seconds": original["duration_seconds"],
                               "width": stream["width"], "height": stream["height"],
                               "probed_frames": original["probed_frames"], "decoded_frames": original["decoded_frames"]},
        })
    require(len(flat) == 233 and len({f["path"] for f in flat}) == 233, "233 unique native files required")
    for fp in flat:
        path = PACKAGE / fp["path"].removeprefix("/")
        require(path.stat().st_size == fp["bytes"] and sha(path) == fp["sha256"], "Native file differs: " + fp["path"])
    summary = {
        "schema_version": 1, "status": "published_actual_seven_stage_CPU_evidence",
        "published_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Five final teachers and both final students: seven preserved native Isaac evaluations, each64 env x3000 steps. CPU consistency/media verification only; no new rollout or success-rate claim.",
        "stages": stages, "original_artifacts": len(flat), "original_artifact_bytes": sum(f["bytes"] for f in flat),
        "original_videos": 191, "quality_bound_videos": 177, "native_described_only_videos": 14,
        "actual_CPU_container_id": execution["container_id"],
        "actual_host_and_container_exit": [execution["actual_start_attached_wait_returncode"], execution["actual_container_exit_code"]],
        "all_191_videos_fully_decoded": True,
        "total_decoded_frames": sum(v["decoded_frames"] for s in report["stages"] for v in s["videos"]),
        "matched_scalar_tags": sum(s["tensorboard_scalar_tags"] for s in stages),
        "strict_TFRecord_records": sum(s["strict_TFRecord_records"] for s in stages),
        "total_failed_resets": sum(s["failed_resets"] for s in stages),
        "total_timeout_resets": sum(s["timeout_resets"] for s in stages),
        "quality_verified": False, "full": False, "convergence_verified": False,
        "official_schedule_complete": False, "physical_hardware_verified": False,
        "original_six_package_modified": False,
        "selection_policy": "Longest quality-bound original in each evaluation, selected deterministically by declared duration; not best/typical/successful.",
        "contract_sha256": sha(PACKAGE / "control/input-contract.json"),
        "validator_sha256": sha(PACKAGE / "reproduce/validate.py"),
        "publisher_sha256": sha(Path(__file__)),
    }
    (PACKAGE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    cards = []
    for stage, originals in zip(stages, contract["stages"]):
        label, r = stage["label"], stage["representative"]
        poster = "cpu-01/results/" + label + "/representative.png"
        videos = "".join(f'<li><a href="{esc(v["path"].removeprefix("/"))}">{esc(Path(v["native_path"]).name)}</a> · {v["declared_duration_seconds"]:g}秒 · {"quality绑定" if v["quality_bound"] else "较早原片，未进入quality时间筛选"}</li>' for v in originals["videos"])
        cards.append(f'''<article data-label="{esc(label)}"><h2>{esc(label)}</h2>
<video controls preload="metadata" poster="{esc(poster)}" src="{esc(r['path'])}"></video>
<img src="{esc(poster)}" alt="{esc(label)}最长原片中点" loading="eager">
<p>checkpoint {stage['checkpoint_iteration']}；整项failed reset {stage['failed_resets']}，timeout {stage['timeout_resets']}，clip结束事件 {stage['clip_completions_excluding_failed_timeout_steps']}。</p>
<p>最长quality绑定原片{r['duration_seconds']:g}秒；按时长确定性选择，不表示最佳或典型表现。指标来自整项64环境，并非只统计本视频。</p>
<p><a href="{esc(r['path'])}">完整原片</a> · <a href="{esc(stage['quality_json'])}">原始指标</a> · <a href="{esc(stage['native_manifest'])}">原生manifest</a></p>
<details><summary>全部{stage['native_described_videos']}段原片（{stage['quality_bound_videos']}段quality绑定）</summary><ul>{videos}</ul></details></article>''')
    page = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>七项正式Isaac评估：五教师与两学生</title><style>body{max-width:1400px;margin:28px auto;padding:0 20px;font:16px/1.65 system-ui;color:#203047;background:#f3f6fa}header{max-width:1100px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:20px}article{background:white;border:1px solid #ccd8e5;border-radius:10px;padding:18px;min-width:0}h2{font-size:20px;overflow-wrap:anywhere}video{width:100%;aspect-ratio:16/9;background:#16283d}img{display:block;width:48%;margin:12px 0}a{color:#175e9f}summary{cursor:pointer}li{overflow-wrap:anywhere}</style></head><body><header><h1>七项正式 Isaac 有界评估</h1>
<p>五类教师checkpoint19999、纯DAgger学生9999、DAgger+PPO学生29999；每项64环境、3000步、0.02秒控制周期，即每环境60秒。</p>
<p>独立CPU容器正常退出0，233原件前后SHA一致；7份TensorBoard整文件CRC/EOF、119标量与191段原片完整解码全部通过。177段进入quality时间筛选，14段较早原片完整保留。</p>
<p>failed reset来自原生terminated标记；clip结束事件排除了同一步failed/timeout，不能作为独立技能通过数或越障成功率。所有项保持quality_verified=false，采样范围不同，不按这些计数排名。</p>
<p><a href="index.md">复现说明</a> · <a href="summary.json">机器汇总</a> · <a href="cpu-01/results/report.json">完整CPU记录</a> · <a href="../official-evaluations-six/index.md">保留的历史六项包</a> · <a href="../../../usage.md">usage.md</a></p></header><main>''' + "\n".join(cards) + "</main></body></html>\n"
    (PACKAGE / "playback.html").write_text(page)
    rows = "\n".join(f"| {s['label']} | {s['checkpoint_iteration']} | {s['failed_resets']} | {s['timeout_resets']} | {s['clip_completions_excluding_failed_timeout_steps']} | {s['native_described_videos']} / {s['quality_bound_videos']} |" for s in stages)
    index = f'''# 七项正式Isaac有界评估：五教师与两学生

2026-10-15补齐最终DAgger+PPO学生的真实评估，形成新的七项包；[历史六项包](../official-evaluations-six/index.md)保持原字节。混合学生训练manifest记录30,000轮、最终checkpoint29999、FINETUNE=1，绑定相同顺序的五个最终教师。原生评估正常退出0。

[集中播放七项原视频](playback.html) · [机器汇总](summary.json) · [原始输入合同](control/input-contract.json) · [完整CPU报告](cpu-01/results/report.json) · [CPU宿主/容器回执](cpu-01/host/execution.json)

| 评估 | checkpoint | failed reset | timeout | clip结束事件 | 原片 / quality绑定 |
| --- | ---: | ---: | ---: | ---: | ---: |
{rows}

每项64环境×3000控制步，0.02秒周期：每环境60秒、每项3840环境秒。四项tracking指标每项192,000样本，完整mean/p95/max及expert分组保留在原quality.json。failed reset统计原生terminated，不能把所有事件称为跌倒；clip结束事件排除同一步failed/timeout，不是独立源动作覆盖、技能通过数或课程成功率。两学生observed_clip_ids=0..4与available_clip_count=1来自不同原生索引语义，不能据此推断296源覆盖。

新增混合学生有31段原片，末编号episode33；编号2、4未列在原生manifest，不能将末编号写成33段。远端目录实际MP4集合与31条manifest精确一致；其中29段quality绑定，另外2段较早原片保留。[只读SSH回传回执](transfer/host-receipt.json)与[逐文件远端前后SHA](transfer/remote-receipt.json)证明37份新增输入未变。另196份输入从历史六项包逐SHA复制。[本地复制记录](transfer/local-six-copy-receipt.json)保留来源合同身份。

新独立CPU容器`{execution['container_id']}`使用既有固定镜像、runc、无网络、无GPU、2CPU/12GiB，宿主attach wait和容器自然退出均为0。233份原件共{summary['original_artifact_bytes']:,} B；全部7份TensorBoard完整CRC/EOF、119标量、191段MP4共{summary['total_decoded_frames']:,}解码帧通过。ffprobe计帧与ffmpeg完整解码帧数逐片相等；来源、合同与执行代码前后SHA均相同。177段quality绑定，14段初始化较早原片也完整保留。

播放页每项确定性展示最长quality绑定片段及中点PNG；选择规则是时长，不能解释为最佳、典型或成功片段。完整191段原片均可逐项下载。

## 独立CPU重放

从已按[note.md](../../../note.md)准备统一镜像的仓库根目录执行。宿主只使用Python标准库与Docker；输出目录必须全新。它重新核对既有证据，不重新训练或运行Isaac。

```bash
python3 -B usage_assets/reports/official-evaluations-seven/reproduce/run_owned_cpu.py \\
  --input usage_assets/reports/official-evaluations-seven \\
  --contract-sha256 {summary['contract_sha256']} \\
  --validator-sha256 {summary['validator_sha256']} \\
  --output outputs/research/official-evaluations-seven-replay-FRESH
```

验收代码基于历史六项工具扩展，精确[validator差异](reproduce/validate.py.adaptation.diff)与[执行器差异](reproduce/run_owned_cpu.py.adaptation.diff)保留：实际总数233/191/177/7及混合学生30000/29999/FINETUNE1身份；数据、CRC、指标、视频和真实退出门卫继续执行。

可选浏览器复查使用已安装Chrome，检查七个展示原片的metadata、中点seek、真实播放推进和七张图片；输出目录全新，不安装任何包：

```bash
python3 -B usage_assets/reports/official-evaluations-seven/browser-reproduce/verify_gallery.py \\
  --package usage_assets/reports/official-evaluations-seven \\
  --output outputs/research/official-evaluations-seven-browser-FRESH
```

本包保持`quality_verified=false`、`convergence_verified=false`、`full=false`。CPU一致性和完整视频只验证本包证据，不验收完整16阶段、888逐源覆盖、最终学生58例/各629配置或真机结果。PT正文未打包；重新运行Isaac仍需原始最终PT、动作/地形资产和相同镜像，并明确设置64环境/3000步。
'''
    (PACKAGE / "index.md").write_text(index)
    print(json.dumps({"status": summary["status"], "artifacts": 233, "videos": 191,
                      "scalar_tags": summary["matched_scalar_tags"], "decoded_frames": summary["total_decoded_frames"]}))


if __name__ == "__main__":
    main()
