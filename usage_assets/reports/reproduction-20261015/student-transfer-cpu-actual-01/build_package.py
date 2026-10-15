#!/usr/bin/env python3
"""Retain actual fetch/failed waiter/CPU prepare originals and final ONNX pairs."""
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path('/home/dzp/projects/php_parkour')
REPRO = ROOT / 'outputs/research/reproduction-20261015'
TRANSFER = ROOT / 'outputs/research/final-student-transfer/waiter-delivery-recovered-01/final-94477a0b18e6-348423173b26-276f9e7f44a6/initial'
BASE = ROOT / 'outputs/research/final-student-native58-delivery-recovered-01'
OUTPUT = ROOT / 'usage_assets/reports/reproduction-20261015/student-transfer-cpu-actual-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, doc):
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n')


def copied(source, target, origins):
    assert source.is_file() and not source.is_symlink(), source
    for p in source.parents:
        assert not p.is_symlink(), p
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(stat.S_IMODE(source.stat().st_mode))
    assert source.read_bytes() == data
    origins.append({'original': str(source), 'retained': target.relative_to(OUTPUT).as_posix(),
                    'bytes': len(data), 'sha256': sha(data)})


def manifest(directory, **extra):
    files = []
    for f in sorted(directory.rglob('*')):
        assert not f.is_symlink(), f
        if f.is_file():
            assert f.name != 'manifest.json' or f.parent != directory
            data = f.read_bytes()
            assert len(data) < 50_000_000
            files.append({'path': f.relative_to(directory).as_posix(), 'bytes': len(data),
                          'sha256': sha(data), 'mode': stat.S_IMODE(f.stat().st_mode)})
    save(directory / 'manifest.json', {'schema': 'student_transfer_retained_bytes_v1',
                                      'files': files, **extra})
    return sha((directory / 'manifest.json').read_bytes())


def main():
    assert not OUTPUT.exists()
    review_path = REPRO / 'native58-cpu-prepare-root-review-01/review.json'
    assert sha(review_path.read_bytes()) == '2fa50ed42155337b07423b71377fbda9f10ca009e70a2a94b8d2ce84a4698fc5'
    review = json.loads(review_path.read_bytes())
    assert review['status'] == 'passed_readonly_native58_cpu_preparation_review'
    assert review['must_fix'] == [] and review['frozen_files'] == 5241 and review['cpu_ort_cases'] == 60
    assert all(p['ort_cases'] == 30 and p['pose']['max_default_pose_absolute_error'] == 0.0
               and p['state']['ExitCode'] == 0 and p['state']['Running'] is False for p in review['phases'])
    assert not (BASE / 'host/launch-receipt.json').exists(), 'Native already started; package scope needs explicit new review'
    old_exit = json.loads((REPRO / 'student-delivery-parent-01/process-exit.json').read_bytes())
    cpu_exit = json.loads((REPRO / 'student-native58-cpu-prepare-host-01/original-parent/process-exit.json').read_bytes())
    state = json.loads((REPRO / 'student-delivery-continuation-01/execution/state.json').read_bytes())
    assert old_exit['actual_wait_returncode'] == 1 and cpu_exit['actual_wait_returncode'] == 0
    assert state['status'] == 'failed'
    before = json.loads((TRANSFER / 'remote-before.json').read_bytes())
    after = json.loads((TRANSFER / 'remote-after.json').read_bytes())
    assert before['snapshot_identity'] == after['snapshot_identity'] and before['payload'] == after['payload']
    origins = []
    OUTPUT.mkdir()
    payload = OUTPUT / 'model-payload'
    payload.mkdir()
    originals = payload / 'original-transfer'
    for name in ['remote-before.json', 'remote-after.json', 'fetch-status.json', 'files-from.nul',
                 'rsync.stdout.log', 'rsync.stderr.log']:
        copied(TRANSFER / name, originals / name, origins)
    models = []
    by_raw = {}
    for pair in before['payload']['pairs']:
        for name, item in pair['models'].items():
            assert name in ('student.onnx', 'depth_backbone.onnx')
            raw = TRANSFER / 'raw' / item['relative']
            data = raw.read_bytes()
            assert len(data) == item['bytes'] and sha(data) == item['sha256']
            assert (TRANSFER / 'models' / pair['kind'] / name).read_bytes() == data
            gz_path = 'gzip/' + pair['kind'] + '/' + name + '.gz'
            dest = payload / gz_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
            assert gzip.decompress(dest.read_bytes()) == data and raw.read_bytes() == data
            model = {'target': pair['kind'] + '/' + name, 'raw_relative': item['relative'],
                     'gzip_path': gz_path, 'bytes': len(data), 'sha256': sha(data),
                     'checkpoint': pair['checkpoint']}
            models.append(model)
            by_raw[item['relative']] = model
            origins.append({'original': str(raw), 'retained': dest.relative_to(OUTPUT).as_posix(),
                            'encoding': 'gzip-lossless', 'bytes': len(data), 'sha256': sha(data)})
    assert len(models) == 4
    assert len(before['payload']['files']) == 32
    for item in before['payload']['files']:
        if item['relative'] not in by_raw:
            raw = TRANSFER / 'raw' / item['relative']
            assert raw.stat().st_size == item['bytes'] and sha(raw.read_bytes()) == item['sha256']
            copied(raw, originals / 'raw' / item['relative'], origins)
    helper = REPRO / 'verify_student_transfer_package.py'
    copied(helper, payload / 'verify_package.py', origins)
    (payload / 'README.md').write_text('''# 最终学生 ONNX 原件

本目录保存本轮训练的两个最终 student/depth 配对：pure 对应 iteration 9999，finetune 对应 iteration 29999。
四个模型采用无损 gzip，保留实际 32 文件回传的 before/after/status 与其余 28 个 JSON 原件。
模型 CPU 导出/运行检查通过；原生仿真和物理质量验收仍待完成。

只使用 Python 标准库。先从已审查外部记录取得本目录 manifest 的 SHA256，再验证并恢复到新的空路径：

```bash
python3 verify_package.py --package . --manifest-sha256 <已审查的模型子包SHA256> --restore-models /tmp/student-pairs-new
```

恢复路径必须不存在，父目录必须已经存在；不会覆盖工作区模型。恢复目录含 pure/ 与 finetune/ 各两个 ONNX。
''')
    payload_seal = manifest(payload, models=models, snapshot_identity=before['snapshot_identity'],
                            status='actual_final_model_bytes_cpu_verified_native_pending')
    restore = REPRO / 'student-model-payload-restored-01'
    assert not restore.exists()
    argv = [sys.executable, '-B', str(payload / 'verify_package.py'), '--package', str(payload),
            '--manifest-sha256', payload_seal, '--restore-models', str(restore)]
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(argv, capture_output=True)
    (OUTPUT / 'model-restore.stdout.raw').write_bytes(result.stdout)
    (OUTPUT / 'model-restore.stderr.raw').write_bytes(result.stderr)
    save(OUTPUT / 'model-restore-execution.json', {'argv': argv, 'started_utc': start,
         'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'actual_wait_returncode': result.returncode, 'manifest_sha256': payload_seal,
         'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr),
         'scope': 'Real ordinary CPU child wait and lossless restore only; no inference/GPU/physical execution.'})
    assert result.returncode == 0, result.stderr.decode()
    restored = json.loads(result.stdout)
    assert len(restored['restored_models']) == 4
    for model in models:
        data = (restore / model['target']).read_bytes()
        assert len(data) == model['bytes'] and sha(data) == model['sha256']
    evidence = OUTPUT / 'evidence'
    files = [REPRO / 'review_native58_cpu_prepare.py', REPRO / 'resume_student_delivery.py',
             REPRO / 'student-delivery-continuation-01/continuation.json',
             REPRO / 'student-delivery-continuation-01/execution/state.json',
             REPRO / 'student-delivery-continuation-independent-review.json',
             BASE / 'host-plan.json', BASE / 'freeze-manifest.json']
    for name in ['student-delivery-parent-01', 'student-native58-cpu-prepare-host-01',
                 'native58-cpu-prepare-root-review-01']:
        files.extend(p for p in (REPRO / name).rglob('*') if p.is_file())
    files.extend(p for p in (BASE / 'control').rglob('*') if p.is_file())
    files.extend(p for p in (BASE / 'host').rglob('*') if p.is_file())
    files.extend(p for p in (REPRO / 'student-delivery-continuation-01/execution/logs').glob('fetch-*') if p.is_file())
    # Keep the final actual status observation that immediately preceded fetch.
    files.extend((REPRO / 'student-delivery-continuation-01/execution/logs').glob('status-1792040635360480561.*'))
    for source in sorted(set(files)):
        copied(source, evidence / source.relative_to(ROOT), origins)
    copied(helper, OUTPUT / 'verify_package.py', origins)
    copied(Path(__file__), OUTPUT / 'build_package.py', origins)
    save(OUTPUT / 'origin-inventory.json', origins)
    save(OUTPUT / 'report.json', {'schema': 'student_transfer_cpu_actual_report_v1',
        'status': 'passed_actual_transfer_and_cpu_preparation_native_pending',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'fetch': {'status': 'completed', 'files': 32, 'snapshot_identity': before['snapshot_identity'],
                  'actual_wait_returncode': 0},
        'retained_original_waiter': {'actual_wait_returncode': 1,
          'failure': 'ValueError: Host boot differs from actual recovery', 'stage': 'local_resource_release'},
        'cpu_preparation': {'actual_parent_wait_returncode': 0, 'ort_cases': 60,
          'frozen_files_verified_by_root': 5241, 'root_review_sha256': sha(review_path.read_bytes()),
          'pose_max_default_absolute_errors': [p['pose']['max_default_pose_absolute_error'] for p in review['phases']],
          'cpu_containers_stopped_exit_0': [p['container_id'] for p in review['phases']]},
        'model_payload_manifest_sha256': payload_seal,
        'model_restore': {'actual_wait_returncode': 0, 'restored_files': 4, 'raw_bytes': sum(m['bytes'] for m in models)},
        'native_started_at_snapshot': False, 'physical_validation': 'pending',
        'scope': 'Retained actual CPU-only results. Freeze manifest/root review are retained; the complete 5241-file source tree is not duplicated in this report. No course success or native/GPU execution is claimed.'})
    (OUTPUT / 'README.md').write_text(f'''# 学生回传与 CPU 实测归档

实际回传 **32/32 文件**，两个最终 student/depth 配对共通过 **60 个 ORT 用例**，两组默认关节姿态最大绝对误差均为 **0**。
原始 prepare 的真实宿主父进程 wait 为 **0**；两只无 GPU、runc、无网络 CPU 容器均已退出 **0**。
根审查逐项验证了 **5241 个冻结文件**；本包保留冻结清单、审查源码、审查原件、CPU 输出与宿主日志，不重复归档整棵源树。

旧等待器在成功 fetch 后实际退出 **1**，错误为 `ValueError: Host boot differs from actual recovery`，阶段为 `local_resource_release`。
失败的 state、宿主 process-start/process-exit、完整 stdout/stderr 与成功 fetch 收据原样保留。后续直接调用未修改的原 prepare，仅完成 CPU 准备。
本快照时原生学生仿真尚未开始，物理质量与技能成功验收 **pending**。

四个最终 ONNX 位于独立 [model-payload](model-payload/README.md) 无损压缩子包（不含大 PT）。已实际恢复到全新路径并逐一核对原 SHA256，恢复 CPU 子进程真实退出 0。
该子包的 manifest SHA256：`{payload_seal}`。

本包完整性核验需要从外部已审查记录取得本包 manifest SHA256：

```bash
python3 verify_package.py --package . --manifest-sha256 <已审查的报告包SHA256>
```

原件索引见 [origin-inventory.json](origin-inventory.json)，结论见 [report.json](report.json)，实际恢复日志见 [model-restore-execution.json](model-restore-execution.json)。
所有 Git 单文件小于 50 MB。完整回传的 28 个 JSON 与 4 个 ONNX 的原字节身份通过模型子包的同一 32-file 清单闭合。
''')
    # Originals must still match all retained observations before sealing.
    for origin in origins:
        source = Path(origin['original'])
        data = source.read_bytes()
        assert len(data) == origin['bytes'] and sha(data) == origin['sha256'], source
    parent_seal = manifest(OUTPUT, status='actual_cpu_only_native_pending',
                           model_payload_manifest_sha256=payload_seal)
    print(json.dumps({'package': str(OUTPUT), 'manifest_sha256': parent_seal,
                      'model_payload_manifest_sha256': payload_seal,
                      'restored_directory': str(restore)}, indent=2))


if __name__ == '__main__':
    main()
