#!/usr/bin/env python3
"""Host stdlib orchestration; learning and physics stay in the existing Docker."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time

root = pathlib.Path('/home/dzp/projects/php_parkour')
output = root / 'outputs/research/source-coverage-host-repaired'

output.mkdir(parents=True, exist_ok=True)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def sample():
    record = {'utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    for name, fields, section in [('gpus', 'index,uuid,memory.used,utilization.gpu', 'gpu'), ('compute', 'pid,process_name,used_memory', 'compute-apps')]:
        result = subprocess.run(['nvidia-smi', f'--query-{section}={fields}', '--format=csv,noheader'], capture_output=True, text=True)
        record[name] = {'return_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    return record

all_results = []
for plan in sys.argv[1:]:
    name = pathlib.Path(plan).parent.name
    log = output / f'{name}-docker.log'
    report_path = output / f'{name}-launch.json'
    samples_path = output / f'{name}-gpu.jsonl'
    if any(path.exists() for path in [log, report_path, samples_path]):
        raise RuntimeError(f'Refusing to overwrite {name}')
    before = sample()
    if before['compute']['stdout'].strip():
        raise RuntimeError('Local GPU already has a compute task; preserve it')
    command = ['docker', 'exec', '-e', 'OMP_NUM_THREADS=1', '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'MKL_NUM_THREADS=1', '-e', 'PYTHONUNBUFFERED=1', '-w', '/workspace/php_parkour', 'php-parkour-research', '/opt/php/bin/train-python', 'scripts/research/eval_source_coverage.py', 'run', '--plan', plan]
    started = time.monotonic()
    report = {'schema_version': 1, 'status': 'running', 'utc': before['utc'], 'command': command, 'gpu_before': before, 'quality_verified': False}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    with log.open('x') as stream, samples_path.open('x') as samples:
        process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
        while True:
            samples.write(json.dumps(sample()) + '\n')
            samples.flush()
            if process.poll() is not None:
                break
            time.sleep(1)
        code = process.wait()
    report.update(status='completed' if code == 0 else 'execution_failed', return_code=code, wall_seconds=time.monotonic() - started, gpu_after=sample(), log_sha256=sha(log), gpu_samples_sha256=sha(samples_path))
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    all_results.append({'name': name, 'return_code': code, 'wall_seconds': report['wall_seconds']})
    print(json.dumps(all_results[-1]), flush=True)
    if code:
        break
(output / 'summary.json').write_text(json.dumps(all_results, indent=2) + '\n')
raise SystemExit(int(any(item['return_code'] for item in all_results)))
