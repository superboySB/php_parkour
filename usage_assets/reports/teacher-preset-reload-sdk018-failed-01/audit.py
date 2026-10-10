#!/usr/bin/env python3
"""Read only stdlib post-check of the terminal, failed first preset cohort."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path('/home/dzp/projects/php_parkour')
OUT = Path(__file__).resolve().parent
RESEARCH = ROOT / 'outputs/research'
PREP = RESEARCH / 'teacher-preset-reload-preparation-v2'
RUN = RESEARCH / 'teacher-preset-reload-execution-01'
HOST = RESEARCH / 'teacher-preset-sdk018-host-01'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), path
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def retain(path, name):
    destination = OUT / 'retained' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert not destination.exists(), destination
    shutil.copyfile(path, destination)
    destination.chmod(0o644)
    assert sha(destination) == sha(path)
    return fingerprint(destination)


def main():
    plan = json.loads((PREP / 'plan.json').read_text())
    execution = json.loads((RUN / 'execution.json').read_text())
    assert execution['status'] == 'native_exits_zero_pending_evidence_validation'
    assert len(execution['cases']) == len(plan['cases']) == 5
    launch = json.loads((HOST / 'launch.json').read_text())
    cpu_launch = json.loads((PREP / 'new-canonical-cpu/launch.json').read_text())
    cpu_report = json.loads((PREP / 'new-canonical-cpu/cpu-report.json').read_text())
    assert cpu_launch['status'] == 'passed' and cpu_launch['returncode'] == 0
    assert cpu_launch['container_id'] == launch['container_id']
    assert cpu_launch['image_id'] == launch['image_id']
    assert cpu_launch['plan_sha256'] == sha(PREP / 'plan.json')
    assert cpu_launch['runner_sha256'] == sha(PREP / 'run_presets.py')
    assert cpu_launch['cpu_report']['sha256'] == sha(PREP / 'new-canonical-cpu/cpu-report.json')
    assert cpu_report['status'] == 'passed' and len(cpu_report['rows']) == 5
    assert cpu_report['cuda_initialized'] is False and cpu_report['isaac_started'] is False
    cases = []
    for expected, observed, cpu in zip(plan['cases'], execution['cases'], cpu_report['rows']):
        assert expected['preset'] == observed['preset'] == cpu['preset']
        inputs = []
        for item in expected['inputs']:
            actual = fingerprint(item['host_path'])
            unchanged = actual['sha256'] == item['sha256'] and actual['bytes'] == item['bytes']
            assert unchanged, item['host_path']
            inputs.append({**actual, 'expected_sha256': item['sha256'], 'unchanged': unchanged})
        log = RUN / (expected['preset'] + '.log')
        text = log.read_text(errors='replace')
        assert sha(log) == observed['log_sha256']
        error_lines = [{'line': index, 'text': line} for index, line in enumerate(text.splitlines(), 1)
                       if re.match(r'^(?:OSError|RuntimeError|ValueError|[A-Za-z.]*Error):', line)]
        quality = RESEARCH / observed['native_quality'].removeprefix('/outputs/')
        assert observed['returncode'] == 0
        assert not quality.exists()
        assert text.count('Traceback (most recent call last):') == 1
        assert any("OSError: [Errno 30] Read-only file system:" in row['text']
                   and '/holosoma/data/robots/converted_rank0_pid' in row['text'] for row in error_lines)
        assert cpu['checkpoint_iteration'] == 1 and cpu['num_envs'] == 16 and cpu['max_eval_steps'] == 100
        assert cpu['actual_saved_contract'] == expected['contract']
        cases.append({'preset': expected['preset'], 'status': 'native_initialization_failed',
            'parent_returncode': observed['returncode'], 'parent_zero_is_physics_success': False,
            'inputs': inputs, 'original_inputs_unchanged': True,
            'cpu_only_contract': cpu['actual_saved_contract'], 'cpu_only_checkpoint_iteration': 1,
            'planned_native_settings': {'num_envs': 16, 'max_eval_steps': 100, 'num_variants': 1, 'seed': 42,
                'registry': 'file:///data/assets/motions-locomotion', 'export_onnx': False},
            'actual_native_saved_config': None, 'actual_control_steps': None,
            'tracking_metrics': None, 'failed_resets': None, 'timeout_resets': None,
            'finite_actions': None, 'finite_root_states': None, 'quality_report_exists': False,
            'quality_report_expected_path': str(quality), 'raw_traceback_count': 1,
            'error_lines': error_lines, 'raw_log': retain(log, log.name),
            'video_count': 0, 'video_decode_verified': False, 'tensorboard_verified': False,
            'physics_verified': False, 'quality_verified': False})
    provenance = []
    for path, name in [(RUN / 'execution.json', 'execution.json'), (HOST / 'launch.json', 'launch.json'),
            (HOST / 'container-inspect.json', 'container-inspect.json'),
            (HOST / 'container-final-inspect.json', 'container-final-inspect.json'),
            (PREP / 'new-canonical-cpu/launch.json', 'cpu-launch.json'),
            (PREP / 'new-canonical-cpu/cpu-report.json', 'cpu-report.json'),
            (PREP / 'new-canonical-cpu/stdout.log', 'cpu-stdout.log'),
            (PREP / 'new-canonical-cpu/stderr.log', 'cpu-stderr.log'),
            (PREP / 'plan.json', 'plan.json'), (PREP / 'run_presets.py', 'run_presets.py'),
            (PREP / 'cpu_preflight.py', 'cpu_preflight.py'),
            (PREP / 'cpu-runner-v2-tests.xml', 'preparer-26-tests.xml')]:
        provenance.append({'original': fingerprint(path), 'retained': retain(path, name)})
    report = {'schema_version': 1, 'audited_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'failed_postvalidation', 'scope': 'Independent read-only terminal evidence audit of five nondefault smoke teacher reload attempts',
        'image_id': launch['image_id'], 'container_id': launch['container_id'],
        'input_integrity_verified': True, 'input_artifact_count': sum(len(c['inputs']) for c in cases),
        'cpu_parse_verified': True, 'physics_verified': False, 'quality_verified': False,
        'execution_parent_exit_zero_count': 5, 'native_initialization_failure_count': 5,
        'quality_report_count': 0, 'decoded_video_count': 0, 'tensorboard_verified_count': 0,
        'failure_reason': 'URDF converter writes converted_rank0_pid* below read-only robot asset_root before physical evaluation.',
        'failure_is_skill_quality_measurement': False,
        'missing_metric_finiteness_is_not_success': True,
        'source_evidence': {'file': 'thirdparty/holosoma/src/holosoma/holosoma/simulator/isaacsim/isaacsim.py',
            'sha256': sha(ROOT / 'thirdparty/holosoma/src/holosoma/holosoma/simulator/isaacsim/isaacsim.py'),
            'lines': '342-357', 'formula': 'usd_conversion_dir = abspath(join(asset_root, converted_rank{local_rank}_pid{pid}))'},
        'cases': cases, 'provenance': provenance,
        'mutations': 'Only this new ignored review directory was created; existing raw outputs, input models, frozen preparation and source were read only.',
        'new_docker_containers_started': 0, 'new_gpu_or_native_jobs_started': 0}
    (OUT / 'review.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    (OUT / 'summary.md').write_text('''# Five preset reload: independent terminal post-validation\n\nAll five original smoke PTs reached a parent exit code of zero but failed native initialization. Each retained raw log contains one OSError traceback: IsaacLab UrdfConverter attempts to create `converted_rank0_pid*` below the read-only Holosoma robot asset directory. No quality.json, rollout metrics, native saved evaluation config, MP4 or TensorBoard rollout evidence was produced. This cohort fails post-validation; these are initialization failures, not measured skill failures. Empty or absent metrics do not establish finiteness.\n\nThe exact original 5 PT, 5 YAML, 5 ONNX and 5 training manifest inputs remain byte-for-byte unchanged (20 SHA checks). The actual new-canonical CPU receipt is bound to image/CID, current plan and helper hashes; its five saved contracts are 160/449 observations with the expected anchor and scaling. This proves CPU checkpoint/config compatibility only. Each planned rollout was iteration1,16env,100steps,1variant,seed42; actual rollout duration and failure counts remain unavailable.\n\n`review.json` records the original error line numbers and full input/provenance fingerprints. `retained/` contains byte-exact copies of the five logs, original driver/container/CPU receipts, plan/helpers and the preparation26-test JUnit. No existing raw file was changed; no new container, package, GPU, Isaac or DDS job was started for this audit.\n\nA future fresh attempt needs a writable generated-USD directory while keeping Python source frozen. The native implementation currently derives that directory from `robot.asset.asset_root`; an explicit independent robot-asset copy plus a parsed asset_root override is a possible fix, pending a separately reviewed plan. This review does not apply it or reinterpret the present five attempts as passes.\n''')
    manifest = [fingerprint(path) | {'relative_path': str(path.relative_to(OUT))}
                for path in sorted(OUT.rglob('*')) if path.is_file() and path.name != 'manifest.json']
    (OUT / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'files': manifest}, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'input_sha_checks': 20,
        'native_initialization_failures': 5, 'quality_verified': False, 'review': str(OUT / 'review.json')}))


if __name__ == '__main__':
    main()
