"""Synthetic provenance/transfer control plane; no real models, SSH or GPU.

The canonical fixture exercises the frozen monitor's actual full-artifact
validator. Docker image/CPU-container inspection and SSH/rsync are explicit
test doubles; this does not claim canonical training or physical validation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts.research import pull_final_students as pf
from scripts.research import posttrain_coverage as pc
from test_posttrain_coverage import canonical, save


@pytest.fixture
def ready(canonical, monkeypatch):
    args, stages = canonical
    args.coverage_output = args.root / "outputs/coverage-official-final"
    args.image = pf.IMAGE
    source = args.root / "source" / args.source_tree
    selection = {"schema_version":1, "training_source_tree":pc.TRAIN_TREE,
        "coverage_source_tree":args.source_tree, "image":pf.IMAGE,
        "image_contents_sha256":pc.IMAGE_CONTENTS, "gpu_uuid":args.gpu_uuid,
        "official_output":pc.OFFICIAL, "coverage_output":pc.COVERAGE,
        "host_coverage_output":str(args.coverage_output), "driver_log_sha256":pf.sha(args.driver_log),
        "driver_completion":{"status":"driver_quiescent"},
        **pc.inspect_artifacts(args.official_output, stages)}
    selection["input_identity"] = pf.identity(selection)
    reports = []
    for label, expected in selection["checkpoints"].items():
        teacher = label.startswith("teacher-")
        kind = "teacher" if teacher else label.removeprefix("student-")
        registry = f"file:///data/assets/motions-{label.removeprefix('teacher-')}" if teacher else ",".join(f"file:///data/assets/motions-{s}" for s in pc.SKILLS)
        experts = [] if teacher else [{"original_expert_ordinal":i, "bitwise_equal_to_final_teacher":True,
            "actor_tensors":8, "actor_tensor_keys":[f"{j}.{k}" for j in (0,2,4,6) for k in ("weight","bias")],
            "normalizer_tensors":3, "normalizer_tensor_keys":["mean","std","eps"]} for i in range(5)]
        reports.append({"label":label, **expected, "embedded_config_verified":True,
            "algorithm":{"teacher":"holosoma.agents.ppo.ppo.PPO", "pure":"wbt_training.utils.student_teacher.PhpDistillation", "finetune":"wbt_training.utils.student_teacher.PhpDistillationPPO"}[kind],
            "registry":registry, "tensor_counts":[9,8] if teacher else [100], "frozen_experts":experts})
    plans = []
    for policy in pc.POLICIES:
        path = args.coverage_output / policy / "plan.json"
        save(path, {"policy":policy,"selected_sources":296,"inventory_total_sources":296,"cases":[{}]*296})
        plans.append({"policy":policy,"sources":296,"path":f"{pc.COVERAGE}/{policy}/plan.json","sha256":pf.sha(path)})
    cpu = {"status":"cpu_scientific_checks_passed", "input_identity":selection["input_identity"],
        "simulation_started":False, "quality_verified":False, "total_sources":296,
        "inventory_sha256":"a"*64, "finished_utc":"2026-10-10T10:00:00+00:00", "checkpoints":reports,"plans":plans}
    save(args.coverage_output / "selection.json", selection)
    save(args.coverage_output / "cpu-ready.json", cpu)
    monkeypatch.setattr(pc, "verify_snapshot", lambda _: source)
    name, command = pc.docker_command(args,source,"cpu",selection["input_identity"])
    info = {"Image":pf.IMAGE, "State":{"Running":False,"ExitCode":0},
        "Config":{"Labels":{"php.posttrain.identity":selection["input_identity"],"php.posttrain.role":"cpu"},
            "WorkingDir":"/workspace/php_parkour", "Entrypoint":["/opt/php/bin/entrypoint"],
            "Env":["LOGGER=tensorboard","WANDB_MODE=disabled","CUDA_VISIBLE_DEVICES=","NVIDIA_VISIBLE_DEVICES=void"],
            "Cmd":command[command.index(args.image)+1:]},
        "HostConfig":{"NetworkMode":"none","DeviceRequests":[]},
        "Mounts":[{"Destination":dest,"Source":str(path),"RW":rw} for dest,path,rw in (
            ("/workspace/php_parkour",source,False),(pc.OFFICIAL,args.official_output,False),
            ("/data/assets",args.root/"assets",False),(pc.COVERAGE,args.coverage_output,True))]}
    def inspect(argv, **kwargs):
        assert argv == ["docker","inspect",name]
        return subprocess.CompletedProcess(argv,0,json.dumps([info]),"")
    monkeypatch.setattr(pc.subprocess,"run",inspect)
    transfer = SimpleNamespace(host="tencent-231", remote_root=str(args.root),source_tree=args.source_tree,
        output_root=args.root/"local",attempt="initial")
    return SimpleNamespace(args=args,stages=stages,selection=selection,cpu=cpu,info=info,transfer=transfer)


def probe(fixture):
    return pf.remote_probe(fixture.args.root,fixture.args.source_tree,pc)


def save_stage(fixture,label):
    save(fixture.args.official_output / "official/manifests" / f"{label}.json",fixture.stages[label])


def test_complete_gate_selects_exact_four_models_and_small_bound_json(ready):
    receipt = probe(ready)
    files = pf.validate_receipt(receipt)
    assert receipt["status"] == "ready" and len(files) == 32
    assert sum(x["relative"].endswith(".onnx") for x in files) == 4
    assert not any(x["relative"].endswith(".pt") for x in files)
    assert receipt["payload"]["quality_verified"] is False


def test_incomplete_stages_return_waiting_without_inspection_or_mutation(ready,monkeypatch):
    ready.stages["teacher-locomotion"]["status"] = "running"
    save_stage(ready,"teacher-locomotion")
    before = {str(p):pf.sha(p) for p in ready.args.root.rglob("*") if p.is_file()}
    monkeypatch.setattr(pc,"verify_snapshot",lambda _:pytest.fail("Incomplete run must not inspect Docker"))
    receipt = probe(ready)
    assert receipt["status"] == "waiting" and receipt["canonical_stage_count"] == 16
    assert receipt["stage_blockers"] and receipt["transfer_started"] is False
    assert before == {str(p):pf.sha(p) for p in ready.args.root.rglob("*") if p.is_file()}


def test_missing_cpu_ready_waits_without_inspection(ready,monkeypatch):
    (ready.args.coverage_output/"cpu-ready.json").unlink()
    monkeypatch.setattr(pc,"verify_snapshot",lambda _:pytest.fail("No CPU receipt must wait"))
    assert probe(ready)["status"] == "waiting"


@pytest.mark.parametrize("change",["pt_bytes","iteration","ordered_experts","wrong_export_pt","profile","registry"])
def test_final_training_or_export_provenance_changes_rejected(ready,change):
    teacher = ready.stages["teacher-locomotion"]
    if change == "pt_bytes": pc.host_path(ready.args.official_output,teacher["checkpoint"]).write_bytes(b"tampered")
    elif change == "iteration": teacher["checkpoint_iteration"] = 19;save_stage(ready,"teacher-locomotion")
    elif change == "ordered_experts": ready.stages["student-pure"]["settings"]["source_checkpoints"].reverse();save_stage(ready,"student-pure")
    elif change == "wrong_export_pt": ready.stages["export-student-pure"]["settings"]["source_checkpoints"] = [{"path":teacher["checkpoint"],"sha256":teacher["checkpoint_sha256"]}];save_stage(ready,"export-student-pure")
    elif change == "profile": teacher["profile"] = "smoke";save_stage(ready,"teacher-locomotion")
    else: teacher["settings"]["registries"] = "file:///other";save_stage(ready,"teacher-locomotion")
    with pytest.raises(ValueError): probe(ready)


@pytest.mark.parametrize("change",["identity","reports","iteration","experts","normalizer","actor_keys","count","plans","source","image","driverlog"])
def test_incomplete_cpu_or_selection_proof_rejected(ready,change):
    cpu, selection = ready.cpu,ready.selection
    if change == "identity": cpu["input_identity"] = "f"*64
    elif change == "reports": cpu["checkpoints"].pop()
    elif change == "iteration": cpu["checkpoints"][-1]["iteration"] = 1
    elif change == "experts": cpu["checkpoints"][-1]["frozen_experts"].pop()
    elif change == "normalizer": cpu["checkpoints"][-1]["frozen_experts"][0]["normalizer_tensor_keys"] = ["mean"]
    elif change == "actor_keys": cpu["checkpoints"][-1]["frozen_experts"][0]["actor_tensor_keys"][0] = "missing"
    elif change == "count": cpu["total_sources"] = 1
    elif change == "plans": cpu["plans"][0]["sources"] = 295
    elif change == "driverlog": ready.args.driver_log.write_text("changed\n")
    else:
        selection["coverage_source_tree" if change == "source" else "image"] = "c"*64
        selection["input_identity"] = pf.identity({k:v for k,v in selection.items() if k != "input_identity"})
    save(ready.args.coverage_output/"selection.json",selection)
    save(ready.args.coverage_output/"cpu-ready.json",cpu)
    with pytest.raises(ValueError): probe(ready)


@pytest.mark.parametrize("change",["running","exit","gpu","extra_mount"])
def test_actual_cpu_container_must_be_successful_isolated_identity(ready,change):
    if change == "running": ready.info["State"]["Running"] = True
    elif change == "exit": ready.info["State"]["ExitCode"] = 1
    elif change == "gpu": ready.info["HostConfig"]["DeviceRequests"] = [{"DeviceIDs":["GPU-other"]}]
    else: ready.info["Mounts"].append({"Destination":pc.OFFICIAL+"/override","Source":"/other","RW":True})
    with pytest.raises(ValueError): probe(ready)


def test_cpu_plan_hash_tamper_rejected(ready):
    (ready.args.coverage_output/"teacher/plan.json").write_text("{}")
    with pytest.raises(ValueError): probe(ready)


def test_multiple_export_bundles_are_not_guessed(ready):
    stage = ready.stages["export-student-pure"]
    stage["onnx_validation_reports"] *= 2
    save_stage(ready,"export-student-pure")
    # Selection binds the manifest SHA, so this is rejected before bundle choice.
    with pytest.raises(ValueError): probe(ready)


@pytest.mark.parametrize("change",["symlink","path_escape","report_escape"])
def test_remote_sources_cannot_escape_or_alias(ready,change):
    entry = ready.stages["export-student-pure"]["onnx_validation_reports"][0]
    if change == "symlink":
        path = pc.host_path(ready.args.official_output,entry["bundle"]+"/student.onnx")
        target = ready.args.root/"outside.onnx";path.rename(target);path.symlink_to(target)
    elif change == "path_escape": entry["bundle"] += "/../model"
    else: entry["report"] = pc.OFFICIAL+"/official/teacher-onnx-validation/summary.json"
    save_stage(ready,"export-student-pure")
    with pytest.raises(ValueError): probe(ready)


@pytest.mark.parametrize("change",["pt","teacher_onnx","path_escape","missing_json","missing_model","wrong_pt","report_escape","cohort","bundle","teacher_iteration"])
def test_host_receipt_whitelist_and_pt_binding_reject_bad_payloads(ready,change):
    receipt = probe(ready);payload=receipt["payload"]
    if change in ("pt","teacher_onnx","path_escape"):
        name={"pt":"official-full/large.pt","teacher_onnx":"official-full/official/teacher-locomotion/model.onnx","path_escape":"../outside.json"}[change]
        payload["files"].append({"relative":name,"sha256":"a"*64,"bytes":4})
    elif change == "missing_json": payload["files"] = [x for x in payload["files"] if not x["relative"].endswith("selection.json")]
    elif change == "missing_model": payload["pairs"][0]["models"].pop("student.onnx")
    elif change == "wrong_pt": payload["checkpoints"]["student-pure"]["iteration"] = 1
    elif change == "report_escape": payload["pairs"][0]["report"] = "official-full/elsewhere.json"
    elif change == "cohort": receipt["cohort"] = "final-"+"a"*12+"-"+"b"*12+"-"+"c"*12
    elif change == "bundle": payload["pairs"][0]["bundle"] = "NOTOUTPUT/official-full/official/export-student-pure/model"
    else: payload["checkpoints"]["teacher-locomotion"]["iteration"] = 19
    receipt["snapshot_identity"]=pf.identity(payload)
    with pytest.raises(ValueError): pf.validate_receipt(receipt)


def install_rsync(ready,monkeypatch,*,fault=None,after=None):
    receipt = probe(ready)
    def rsync(argv,**kwargs):
        assert argv[0] == "rsync" and "--delete" not in argv
        listing=Path(argv[argv.index("--files-from")+1]).read_bytes().split(b"\0")[:-1]
        assert {x.decode() for x in listing} == {x["relative"] for x in receipt["payload"]["files"]}
        raw = Path(argv[-1])
        for item in receipt["payload"]["files"]:
            target=raw/item["relative"];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ready.args.root/"outputs"/item["relative"],target)
        if fault == "tamper": (raw/listing[0].decode()).write_bytes(b"changed")
        if fault == "symlink":
            path=raw/listing[0].decode();path.unlink();path.symlink_to(ready.args.root/"outputs"/listing[0].decode())
        if fault == "rsync": raise subprocess.CalledProcessError(23,argv)
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(pf.subprocess,"run",rsync)
    monkeypatch.setattr(pf,"observe_remote",lambda _:copy.deepcopy(receipt if after is None else after))
    return receipt


def test_explicit_fetch_materializes_only_four_models_and_keeps_raw_bytes(ready,monkeypatch):
    receipt=install_rsync(ready,monkeypatch)
    original={x["relative"]:(ready.args.root/"outputs"/x["relative"]).read_bytes() for x in receipt["payload"]["files"]}
    result=pf.fetch(ready.transfer,receipt)
    assert result["status"] == "completed" and len(result["models"]) == 4 and result["files"] == 32
    assert result["quality_verified"] is False and "unexecuted" in result["scope"]
    destination=Path(result["destination"])
    assert {str(p.relative_to(destination/"raw")):p.read_bytes() for p in (destination/"raw").rglob("*") if p.is_file()} == original
    assert all(pf.sha(x["path"]) == x["sha256"] for x in result["models"])
    with pytest.raises(FileExistsError): pf.fetch(ready.transfer,receipt)


@pytest.mark.parametrize("fault",["rsync","tamper","symlink","remote_changed","remote_waiting"])
def test_failed_or_changed_transfer_keeps_fresh_partial_evidence(ready,monkeypatch,fault):
    after=probe(ready)
    if fault == "remote_changed": after["payload"]["selection_identity"] = "f"*64;after["snapshot_identity"] = pf.identity(after["payload"])
    if fault == "remote_waiting": after={"status":"waiting"}
    receipt=install_rsync(ready,monkeypatch,fault=fault,after=after)
    with pytest.raises((ValueError,subprocess.CalledProcessError)): pf.fetch(ready.transfer,receipt)
    destination=ready.transfer.output_root/receipt["cohort"]/"initial"
    report=pf.read(destination/"fetch-status.json")
    assert report["status"] == "failed" and report["partial_evidence_retained"] is True
    assert (destination/"raw").is_dir() and not (destination/"models").exists()


def test_waiting_fetch_does_not_create_target(tmp_path):
    args=SimpleNamespace(output_root=tmp_path/"must-not-exist")
    assert pf.fetch(args,{"status":"waiting"}) == {"status":"waiting"}
    assert not args.output_root.exists()


def test_symlink_destination_rejected_before_mutation(ready,monkeypatch):
    receipt=install_rsync(ready,monkeypatch)
    outside=ready.args.root/"outside";outside.mkdir()
    ready.transfer.output_root.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"): pf.fetch(ready.transfer,receipt)
    assert list(outside.iterdir()) == []


def test_transfer_helper_must_stay_frozen_while_copying(ready,monkeypatch):
    receipt=install_rsync(ready,monkeypatch)
    original_sha=pf.sha
    helper_calls=[]
    def changed(path):
        if str(path) == pf.__file__:
            helper_calls.append(path)
            return original_sha(path) if len(helper_calls) == 1 else "f"*64
        return original_sha(path)
    monkeypatch.setattr(pf,"sha",changed)
    with pytest.raises(ValueError,match="helper changed"): pf.fetch(ready.transfer,receipt)
    report=pf.read(ready.transfer.output_root/receipt["cohort"]/"initial/fetch-status.json")
    assert report["status"] == "failed" and report["partial_evidence_retained"] is True


def test_changed_frozen_monitor_api_is_not_imported(tmp_path):
    source=tmp_path/"source"/pf.TREE/"scripts/research/posttrain_coverage.py"
    source.parent.mkdir(parents=True)
    source.write_text("raise RuntimeError('must not execute mismatched source')\n")
    with pytest.raises(ValueError,match="Frozen monitor revision"): pf.load_monitor(tmp_path,pf.TREE)


@pytest.mark.parametrize("action",["status","dry-run"])
def test_readonly_cli_uses_stdin_probe_without_creating_output(tmp_path,monkeypatch,capsys,action):
    monkeypatch.setattr(pf,"REPO",tmp_path)
    output=tmp_path/"outputs/research/final-student-transfer"
    monkeypatch.setattr(pf.sys,"argv",["pull_final_students.py",action])
    def ssh(argv,**kwargs):
        assert argv[:6] == ["ssh","-p","22","-o","BatchMode=yes","tencent-231"]
        assert "probe" in argv and "-B" in argv and kwargs["input"] == Path(pf.__file__).read_bytes()
        assert not any(x in argv for x in ("docker","rsync","fetch"))
        return subprocess.CompletedProcess(argv,0,json.dumps({"status":"waiting","canonical_stage_count":16,"cpu_ready_present":False}).encode(),b"")
    monkeypatch.setattr(pf.subprocess,"run",ssh)
    assert pf.main() == 0 and json.loads(capsys.readouterr().out)["status"] == "waiting"
    assert not output.exists()


@pytest.mark.parametrize("path",["../escape","/absolute","x/../y","x//y","x\nname",""])
def test_relative_paths_reject_ambiguous_or_escaping_names(path):
    with pytest.raises(ValueError): pf.relative_path(path)
