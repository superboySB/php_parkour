#!/usr/bin/env python3
"""Publish actual reviewed native58 media; never launch a scientific process.

This is a document evidence package, not a model/source backup. Its raw restore
map retains original case evidence, CPU/host receipts and the independent
review; model/source bindings excluded from the package remain explicit.
"""
from __future__ import annotations
import argparse
import ast
import csv
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path('/home/dzp/projects/php_parkour')
HERE = Path(__file__).resolve().parent
GATE = ROOT / 'outputs/research/final-student-reference629-crossboot-preparation-02'
COPIER = ROOT / 'outputs/research/final-student-reference629-publication-preparation-01/publisher.py'
LEGACY = ROOT / 'scripts/research/publish_full_scene_matrix.py'
PHASES = ('pure-directions', 'pure-scenes', 'finetune-directions', 'finetune-scenes')
HISTORICAL_BINDING_ONLY_ROOTS = tuple(ROOT / 'outputs/research' / name for name in (
    'fresh629-sdk018-6cb2ae2-prepared02', 'fresh629-recovery-01', 'fresh629-root-terminal-01'))
HISTORICAL_PUBLICATION = ROOT / 'usage_assets/reports/sim2sim-full629-sdk018-recovered/evidence-manifest.json'
CROSSBOOT_SOURCE_PUBLICATION = ROOT / 'usage_assets/reports/native58-crossboot-control-preparation/evidence-manifest.json'
FAILED41_PUBLICATION = ROOT / 'usage_assets/reports/reproduction-20261015/native58-preserved-failed41-01/evidence-manifest.json'
FAILED_GATE02_PUBLICATION = ROOT / 'usage_assets/reports/reproduction-20261015/native58-resource-wait-control02-preserved-01/evidence-manifest.json'
FAILED41_BINDING_ONLY_ROOTS = tuple(ROOT / 'outputs/research' / name for name in (
    'final-student-native58-delivery-recovered-01',
    'reproduction-20261015/student-native58-crossboot-host-01',
    'reproduction-20261015/student-native58-crossboot-control-actual-01'))
FAILED_GATE02_BINDING_ONLY_ROOT = ROOT / 'outputs/research/reproduction-20261015/native58-resource-wait-contract-root-02'
HISTORICAL_BINDING_ONLY_ROOTS += FAILED41_BINDING_ONLY_ROOTS + (FAILED_GATE02_BINDING_ONLY_ROOT,)


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(path):
    path = Path(path).absolute()
    require(path.is_relative_to(ROOT) and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'Unsafe workspace path: ' + str(path))
    return path


def fp(path):
    path = safe(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Regular file required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
    require(signature(before) == signature(after), 'Source changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def load(path, name, expected):
    path = safe(path)
    raw = path.read_bytes()
    require(fp(path) == expected and len(raw) == expected['bytes']
            and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'Reviewed source differs: ' + str(path))
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ''
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def preparation(expected):
    manifest = HERE / 'preparation-manifest.json'
    require(fp(manifest)['sha256'] == expected, 'Explicit publication preparation SHA differs')
    value = read(manifest)
    require(value['status'] == 'source_only_prepared' and value['scientific_execution'] is False,
            'Source preparation status differs')
    records = {row['path']: row for row in value['dependencies']}
    require(len(records) == len(value['dependencies']), 'Duplicate dependency')
    for row in records.values():
        require(fp(row['path']) == row, 'Publication dependency changed: ' + row['path'])
    for path in (Path(__file__).absolute(), GATE / 'support.py', GATE / 'admission.py',
                 GATE / 'frozen/common.py', COPIER, LEGACY, HERE / 'verify_http.py', HERE / 'restore.py', HISTORICAL_PUBLICATION, CROSSBOOT_SOURCE_PUBLICATION, FAILED41_PUBLICATION, FAILED_GATE02_PUBLICATION):
        require(str(path) in records, 'Required reviewed dependency omitted')
    return records, fp(manifest)


def admit(args, records):
    support = load(GATE / 'support.py', '_native58_doc_support', records[str(GATE / 'support.py')])
    old = sys.modules.get('support')
    try:
        sys.modules['support'] = support
        gate = load(GATE / 'admission.py', '_native58_doc_admission', records[str(GATE / 'admission.py')])
    finally:
        if old is None:
            sys.modules.pop('support', None)
        else:
            sys.modules['support'] = old
    return gate.admission(args)


def retained_for_document(path, base):
    path = safe(path)
    if any(path.is_relative_to(root) for root in HISTORICAL_BINDING_ONLY_ROOTS):
        return False
    if not path.is_relative_to(base):
        return path.suffix.lower() not in {'.pt', '.pth', '.onnx', '.pkl', '.npz', '.npy', '.obj', '.stl', '.urdf'}
    relative = path.relative_to(base)
    if relative.parts[0] in {'source', 'overlay'}:
        return False
    if relative.parts[0] == 'inputs':
        return relative.name in {'directions-plan.json', 'scenes-plan.json'}
    return True


def operational_inventory(base, admitted):
    """Lock all terminal host/phase originals, including files outside review.

    Independent review bindings remain unchanged. Supplemental raw logs and
    driver/matrix/observer files are explicitly current byte snapshots, never
    retrospectively represented as independently reviewed scientific evidence.
    """
    records = {r['path']: r for r in admitted['bound_files']}
    reviewed_paths = set(records)
    file_sets = {}
    host_control = admitted['host_control']
    control_directory = safe(host_control['control_directory'])
    parent_directory = safe(host_control['original_parent_directory'])
    operation_directories = [safe(path) for path in host_control['operational_directories']]
    require(any(control_directory.is_relative_to(path) for path in operation_directories)
            and any(parent_directory.is_relative_to(path) for path in operation_directories),
            'Crossboot control and original actual-parent trees must be included completely')
    require(all(path.is_relative_to(ROOT / 'outputs/research') and not path.is_relative_to(base)
                and not base.is_relative_to(path) for path in operation_directories),
            'External host control evidence tree overlaps original prepared science base')
    require((control_directory / 'control-receipt.json').is_file()
            and all((parent_directory / name).is_file() for name in ('process-start.json', 'process-exit.json', 'stdout.raw', 'stderr.raw')),
            'Actual new wrapper and original e238 start/exit/raw logs are required')
    for directory in (base / 'host', base / 'phases', *operation_directories):
        directory = safe(directory)
        require(directory.is_dir(), 'Complete terminal operation tree required')
        expected = set()
        for path in sorted(directory.rglob('*')):
            path = safe(path)
            if path.is_dir():
                continue
            row = fp(path)
            require(row['path'] not in records or records[row['path']] == row,
                    'Review-bound file changed before operational inventory')
            records[row['path']] = row
            expected.add(row['path'])
        file_sets[str(directory)] = sorted(expected)
    for phase in PHASES:
        stage = base / 'phases' / phase
        names = ['driver.log', 'observer.log', 'observer/launch.json', 'observer/summary.json',
                 'cpu-final/launch.json', 'cpu-final/summary.json', 'cpu-final/stdout.log', 'cpu-final/stderr.log']
        names += ['outputs/pilot-summary.json'] if phase.endswith('directions') else [
            'outputs/scenes17/matrix.json', 'outputs/scenes17/plan.json']
        require(all(str(stage / name) in records for name in names),
                'Missing original driver/observer/CPU/matrix operational evidence: ' + phase)
    supplemental = [r for path, r in records.items() if path not in reviewed_paths]
    return list(records.values()), file_sets, supplemental


def case_rows(base, admitted, copies, svg):
    reviewed = {r['path']: r for r in read(admitted['independent_review']['path'])['evidence_fingerprints']}
    rows = []
    for phase in PHASES:
        phase_root = base / 'phases' / phase
        summary = read(phase_root / 'cpu-final/summary.json')
        expected = 12 if phase.endswith('directions') else 17
        require(len(summary['cases']) == expected, 'Native phase case count differs')
        for case in summary['cases']:
            native = Path(case['output'])
            require(native.is_absolute() and native.is_relative_to('/outputs') and '..' not in native.parts,
                    'Unsafe native case output')
            directory = safe(phase_root / 'outputs' / native.relative_to('/outputs'))
            result = read(directory / 'result.json')
            require(fp(directory / 'result.json')['sha256'] == case['native_result_sha256']
                    and result['quality_verified'] is False
                    and result['obstacle_course_completion_verified'] is False, 'Case result SHA/quality scope differs')
            videos = []
            require(len(result['video_checks']) == len(case['video_full_decodes']) == 1, 'One actual decoded video per case required')
            for check in result['video_checks']:
                video, poster = [safe(directory / check[k]) for k in ('video', 'thumbnail')]
                require(video.is_relative_to(directory) and poster.is_relative_to(directory)
                        and fp(video) == reviewed[str(video)] and fp(poster) == reviewed[str(poster)],
                        'Media lacks exact independent review binding')
                stream, duration = check['probe']['streams'][0], float(check['probe']['format']['duration'])
                require(duration > 0 and min(stream['width'], stream['height']) > 0, 'Invalid original media metadata')
                videos.append({'path': copies.link(video), 'thumbnail': copies.link(poster),
                    'bytes': video.stat().st_size, 'sha256': reviewed[str(video)]['sha256'],
                    'duration_seconds': duration, 'width': stream['width'], 'height': stream['height']})
            with (directory / 'trajectory.csv').open() as stream:
                trajectory = [r for r in csv.DictReader(stream) if float(r['policy_seconds']) >= 0]
            require(trajectory, 'Actual policy trajectory required')
            relative = f'derived/{phase}/{len(rows):02d}-world-xy.svg'
            copies.generated(relative, svg(trajectory).encode())
            simulation = result['simulation']
            require(type(simulation['fall_detected']) is bool and type(result['survival_passed']) is bool,
                    'Native heuristic flags must be booleans')
            rows.append({'ordinal': len(rows), 'phase': phase, 'model_kind': phase.split('-')[0],
                'case_id': case['case_id'], 'policy_ticks': result['inference']['ticks'],
                'commands': result['config']['commands'], 'threshold_event': simulation['fall_detected'],
                'survival_heuristic_passed': result['survival_passed'],
                'metrics': {key: simulation[key] for key in ('policy_simulation_seconds', 'minimum_pelvis_height_m',
                    'minimum_base_up_z', 'final_base_up_z', 'path_length_xy_m', 'final_position_xyz_m')},
                'videos': videos, 'trajectory_svg': relative,
                'trajectory_csv': copies.link(directory / 'trajectory.csv'),
                'result_json': copies.link(directory / 'result.json'),
                'quality_verified': False, 'obstacle_course_completion_verified': False})
    require(len(rows) == 58 and len({(r['phase'], r['case_id']) for r in rows}) == 58,
            'Exactly58 unique actual cases required')
    return rows


def gallery(rows):
    intro = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>正式学生 · 58项原生仿真</title><style>body{font:16px system-ui;background:#111827;color:#e5e7eb;max-width:1300px;margin:30px auto;padding:0 20px}a{color:#93c5fd}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:20px}article{border:1px solid #374151;border-radius:12px;padding:16px;min-width:0}video,img{width:100%;max-width:640px}code{overflow-wrap:anywhere}button,select{font:inherit;padding:8px}p{line-height:1.6}</style><h1>正式最终学生：58项原生仿真</h1><p>纯蒸馏与混合微调各含12个平地方向、17种场景。全部真实父进程、116个worker退出、116个host映射和58段完整解码，经独立review绑定后才生成此页。视频可能包含初始化；下方轨迹仅画policy阶段。</p><p>高度／倾斜阈值与survival启发式用于描述姿态。未触发阈值不代表技能或完整越障课程成功；本页不计算成功率。</p><p><a href="summary.json">汇总</a> · <a href="cases.json">全部58项指标</a> · <a href="admission.json">真实来源和review绑定</a> · <a href="restore-map.json">原始字节归档表</a> · <a href="README.md">重放与归档范围</a></p><label>筛选 <select id="phase"><option value="">全部58项</option>'''
    intro += ''.join(f'<option>{phase}</option>' for phase in PHASES) + '</select></label><main>'
    cards = []
    for row in rows:
        escape = lambda x: html.escape(str(x), quote=True)
        video = row['videos'][0]
        metrics = row['metrics']
        cards.append(f'''<article data-phase="{escape(row['phase'])}" data-case="{escape(row['case_id'])}"><h2>{escape(row['phase'])} · {escape(row['case_id'])}</h2><p>{'触发高度／倾斜阈值' if row['threshold_event'] else '本次未触发高度／倾斜阈值'}；survival启发式 {escape(row['survival_heuristic_passed'])}；{row['policy_ticks']} policy ticks</p><video controls preload="metadata" poster="{escape(video['thumbnail'])}" src="{escape(video['path'])}"></video><p><a href="{escape(video['path'])}">原始MP4</a> · {video['duration_seconds']:.2f}秒 · {video['width']}×{video['height']}</p><p>最低pelvis {metrics['minimum_pelvis_height_m']:.3f} m；最低up {metrics['minimum_base_up_z']:.3f}；XY路径 {metrics['path_length_xy_m']:.3f} m</p><details><summary>轨迹和原始证据</summary><img loading="lazy" src="{escape(row['trajectory_svg'])}" alt="实际policy世界XY轨迹"><p><a href="{escape(row['trajectory_csv'])}">原始CSV</a> · <a href="{escape(row['result_json'])}">原始result JSON</a></p><p>MP4 SHA256 <code>{escape(video['sha256'])}</code></p></details></article>''')
    return intro + ''.join(cards) + '''</main><script>document.querySelector('#phase').onchange=e=>{for(const a of document.querySelectorAll('article'))a.hidden=!!e.target.value&&a.dataset.phase!==e.target.value;for(const v of document.querySelectorAll('article[hidden] video'))v.pause();};</script></html>'''


def publish(args):
    required = ('preparation_sha256', 'transfer', 'native58_base', 'native58_exit', 'native58_exit_sha256',
                'native58_review', 'native58_review_sha256', 'output')
    missing = [name for name in required if not getattr(args, name, None)]
    if missing:
        return {'status': 'waiting', 'missing_explicit_prerequisites': missing,
                'publication_started': False, 'native_started': False, 'gpu_started': False}
    records, preparation_fp = preparation(args.preparation_sha256)
    admitted = admit(args, records)
    if admitted['status'] != 'ready':
        return dict(admitted, publication_started=False)
    require(admitted['host_control']['control_revision'] == 4
            and admitted['host_control']['status'] == 'verified_actual_resource_wait_native58_parent_and_control'
            and admitted['host_control']['readonly_diagnostics']['complete_raw_journal_bound'] is True,
            'Explicit actual revision4 resource-wait host control and complete raw journal required')
    base, output = safe(args.native58_base), safe(args.output)
    require(output.is_relative_to(ROOT / 'usage_assets') and not output.exists()
            and not base.is_relative_to(output) and not output.is_relative_to(base), 'Fresh separate usage_assets output required')
    module = load(COPIER, '_native58_document_byte_copier', records[str(COPIER)])
    tree = ast.parse(LEGACY.read_bytes())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'trajectory_svg')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(LEGACY), 'exec'), namespace)
    require(len({r['path'] for r in admitted['bound_files']}) == len(admitted['bound_files']), 'Duplicate admission binding')
    bound, operation_file_sets, supplemental = operational_inventory(base, admitted)
    modes = module.original_modes(bound)
    retained = [r for r in bound if retained_for_document(r['path'], base)]
    omitted = [dict(r, reason=('Prior historical/failed41/pre-native gate tree: complete fingerprint retained; excluded from this new independent58 restore; see exact prior publication seals'
               if any(Path(r['path']).is_relative_to(root) for root in HISTORICAL_BINDING_ONLY_ROOTS)
               else 'Model, asset or scientific source; bound read-only, not included in this document evidence package'))
               for r in bound if r not in retained]
    # No output directory is created until actual completed evidence and review passed.
    output.mkdir(parents=True)
    copies = module.Copies(output, retained, modes)
    try:
        for row in retained:
            copies.archive(row)
        rows = case_rows(base, admitted, copies, namespace['trajectory_svg'])
        summary = {'schema_version': 1, 'status': 'completed_review_bound_native58_document_publication',
            'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'cases': 58, 'worker_exit0_empty_groups': 116,
            'host_mappings': 116, 'independent_full_video_decodes': 58, 'cpu_ort_cases': 60,
            'phases': [{'phase': phase, 'cases': sum(r['phase'] == phase for r in rows),
                'threshold_events': sum(r['threshold_event'] for r in rows if r['phase'] == phase),
                'survival_heuristic_passed': sum(r['survival_heuristic_passed'] for r in rows if r['phase'] == phase)} for phase in PHASES],
            'quality_verified': False, 'obstacle_course_completion_verified': False,
            'native58_plan_sha256': admitted['native58_plan_sha256'], 'actual_parent_wait': admitted['actual_parent_wait'],
            'independent_review': admitted['independent_review'], 'preparation': preparation_fp,
            'host_control': admitted['host_control'],
            'historical_binding_only_roots': [str(root) for root in HISTORICAL_BINDING_ONLY_ROOTS],
            'historical_prior_publication': fp(HISTORICAL_PUBLICATION),
            'host_control_source_publication': fp(CROSSBOOT_SOURCE_PUBLICATION),
            'preserved_failed41_publication': fp(FAILED41_PUBLICATION),
            'preserved_pre_native_gate02_publication': fp(FAILED_GATE02_PUBLICATION),
            'scope': 'All58 actual videos and native case/CPU/host/review evidence. Scientific source/models excluded explicitly; no new physics, training, success rate or automatic clip claim.'}
        copies.json('summary.json', summary)
        copies.json('cases.json', rows)
        copies.json('admission.json', admitted)
        copies.json('publication-inventory.json', {'schema_version': 1, 'bound_files': bound,
            'operational_file_sets': operation_file_sets,
            'original_modes': modes,
            'supplemental_operational_files': supplemental,
            'supplemental_integrity_scope': 'Initial read-only byte/mode/file-set snapshot after true terminal admission, rechecked at publication end. These original logs/matrix/observer files were not added to the independent scientific review retroactively.'})
        copies.json('restore-map.json', {'schema_version': 1, 'retained': copies.records, 'excluded_bindings': omitted,
            'historical_binding_only_roots': [str(root) for root in HISTORICAL_BINDING_ONLY_ROOTS],
            'historical_prior_publication': fp(HISTORICAL_PUBLICATION),
            'host_control_source_publication': fp(CROSSBOOT_SOURCE_PUBLICATION),
            'preserved_failed41_publication': fp(FAILED41_PUBLICATION),
            'preserved_pre_native_gate02_publication': fp(FAILED_GATE02_PUBLICATION),
            'scope': 'Restore retained new58 document evidence bytes/modes only. Listed models/assets/scientific source and listed historical prior629, failed41 run/outer/control and rejected pre-native gate02 trees are binding-only; their full file fingerprints remain in excluded_bindings, not restored bytes.'})
        copies.generated('playback.html', gallery(rows).encode())
        for name in ('publish.py', 'restore.py', 'verify_http.py', 'preparation-manifest.json'):
            copies.generated('reproduce/' + name, (HERE / name).read_bytes())
        copies.generated('README.md', ('# 真实58项视频与原始证据\n\n'
            '本包经过真实native58完成及显式SHA绑定的独立review门卫，包含全部58段原始MP4与case证据；不将高度／倾斜阈值或survival启发式称为课程成功。\n\n'
            '明确revision4资源等待控制仅覆盖recovered_previous/gpu_idle两个宿主函数，等待真实计入原12h上限，所有本次API/query原字节均归档。明确crossboot控制使用真实新wrapper与原e238 parent argv/actual_wait_returncode，不回写旧argv或旧parent receipt。新58 case/MP4、CPU/driver/observer及本次parent/outer/control完整原件均归档。\n\n'
            '早期control01跨boot控制源、24项普通CPU协议及独立源审另有[历史source-only控制包](' + os.path.relpath(CROSSBOOT_SOURCE_PUBLICATION.parent / 'README.md', output) + ')和[实际seal](' + os.path.relpath(CROSSBOOT_SOURCE_PUBLICATION, output) + ')。其准备、waiting和启动原件不替代本包的真实native终态、parent wait及独立postexecution review。\n\n'
            '以下三历史根整体只绑定逐文件SHA/字节，均列在restore-map.json.excluded_bindings：`fresh629-sdk018-6cb2ae2-prepared02`、`fresh629-recovery-01`、`fresh629-root-terminal-01`（均位于原workspace的outputs/research下）。已review历史gate逐项核验这些原证据，原root143及8个历史映射缺口保持；本新58文档包不单独恢复整套历史科学树、不把旧629影片算入58片。既有[恢复629公开证据](' + os.path.relpath(HISTORICAL_PUBLICATION.parent / 'index.md', output) + ')及其[实际seal](' + os.path.relpath(HISTORICAL_PUBLICATION, output) + ')另列，summary/restore-map也保留该seal的真实fingerprint。\n\n'
            '旧失败41 cohort的base/outer/control及只读门卫02拒绝目录同样仅绑定逐原file fingerprint，列于excluded_bindings；不能从本新58包单独恢复，不能算入本次58影片。原件另见[失败41保留包](' + os.path.relpath(FAILED41_PUBLICATION.parent / 'README.md', output) + ')及[实际seal](' + os.path.relpath(FAILED41_PUBLICATION, output) + ')、[门卫02原始拒绝/source保留包](' + os.path.relpath(FAILED_GATE02_PUBLICATION.parent / 'README.md', output) + ')及[实际seal](' + os.path.relpath(FAILED_GATE02_PUBLICATION, output) + ')。旧parent/outer1、三容器stop143及未保存旧拒绝query的限制永久保留；新58与旧失败cohort独立。\n\n'
            '在仓库根运行 `python3 scripts/research/serve_evidence.py`，浏览本目录 `playback.html` 对应的HTTP路径。Range服务器支持拖动；仅打开本地文件不足以验证HTTP播放。\n\n'
            '`python3 reproduce/restore.py verify --package 本包绝对路径 --manifest-sha256 已审查sealSHA` 校验封存和分块；`restore --package 本包绝对路径 --manifest-sha256 已审查sealSHA --output 一个全新绝对目录` 恢复 `restore-map.json` 中保留的workspace相对路径、字节与权限。排除的模型、资产及科学源码只保留SHA绑定，不能从本包恢复。重放不执行科学仿真。\n\n'
            '浏览器验证在包外写收据：`python3 reproduce/verify_http.py --package 本包绝对路径 --manifest-sha256 已审查sealSHA --preparation-sha256 已审查准备SHA --output 一个全新仓库内目录`。其实际HTTP metadata、midpoint seek、play和SHA复核不增加物理或技能质量结论。\n\n'
            '`restore.py`仅依赖标准库与本包，可独立恢复保留证据。自动`verify_http.py`仍绑定原绝对工作区preparation.dependencies（含outputs下原准备/629 helper、Range/CDP工具）及现有Chrome，须保留这些依赖；本包未包含全部控制依赖，不能单独重跑自动浏览器验收。复制的publish源码供审查，重新出版应从原准备目录调用。\n').encode())
        module.recheck(bound, operation_file_sets, modes)
        for row in records.values():
            require(fp(row['path']) == row, 'Preparation source changed during publication')
        require(fp(HERE / 'preparation-manifest.json') == preparation_fp, 'Preparation manifest changed')
        files = [dict(fp(path), path=path.relative_to(output).as_posix())
                 for path in sorted(output.rglob('*')) if path.is_file()]
        copies.json('evidence-manifest.json', {'schema_version': 1, 'status': 'sealed_document_publication',
            'files': files, 'independent_review': admitted['independent_review'], 'cases': 58,
            'native_started': False, 'gpu_started': False, 'quality_verified': False})
        return {'status': summary['status'], 'output': str(output), 'cases': 58,
                'retained_original_files': len(retained), 'excluded_bound_files': len(omitted),
                'seal': fp(output / 'evidence-manifest.json'), 'publication_started': True,
                'native_started': False, 'gpu_started': False, 'quality_verified': False}
    except BaseException as error:
        failure = {'status': 'failed_publication_preserved', 'error': type(error).__name__ + ': ' + str(error),
                   'native_started': False, 'gpu_started': False, 'quality_verified': False}
        with (output / 'publication-failed.json').open('x') as stream:
            json.dump(failure, stream, indent=2)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation-sha256', 'native58-exit-sha256', 'native58-review-sha256'):
        parser.add_argument('--' + name)
    for name in ('transfer', 'native58-base', 'native58-exit', 'native58-review', 'output'):
        parser.add_argument('--' + name, type=Path)
    result = publish(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
