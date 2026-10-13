#!/usr/bin/env python3
"""Replay original CPU phases from a sealed student-curve archive."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

ARCHIVE_SHA = '068c13d5e8e61a7e7a4b80b2813a96ac617efee408674e9fe1f65a498b50dcc2'
CODE_SHAS = {
  'run_cpu.py': '69400c06064febed4f121730a702ea3785dea1d56c1dfd4e8c657913236a090a',
  'run_phases.py': 'aeaf2431cc102e933c103478c5d0e7a8dedbbf6498a43c205f47439f215b4b6f',
  'extract_student_scalars.py': 'e8bf7156013e7c31200ab39c9511020ed17c2e6726d79bc368939b44b5507b12',
  'plot_student_learning_curves.py': '6a14cfa86df96199e575384c48466d44046b1a2fad8ce76c1427b7d5add7abd0',
}
FALSE_FLAGS = {key: False for key in ('quality_verified', 'convergence_verified',
  'official_schedule_complete', 'seven_PT_acceptance_verified', 'pt_onnx_numerical_parity_verified')}

def check(condition, message):
  if not condition:
    raise ValueError(message)

def safe(path):
  path = Path(path).absolute()
  check('..' not in path.parts and not any(x.is_symlink() for x in (path, *path.parents)),
    'Unsafe path: ' + str(path))
  return path

def relative(value):
  path = Path(value)
  check(isinstance(value, str) and value and not path.is_absolute()
    and '..' not in path.parts and str(path) == value and value != '.', 'Unsafe archive path')
  return path

def fp(path, raw=False):
  path = safe(path)
  before = path.stat()
  check(stat.S_ISREG(before.st_mode), 'Not a file: ' + str(path))
  digest, chunks = hashlib.sha256(), []
  with path.open('rb') as stream:
    for data in iter(lambda: stream.read(8388608), b''):
      digest.update(data)
      if raw:
        chunks.append(data)
  after = path.stat()
  sig = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
  check(sig(before) == sig(after), 'Changed file: ' + str(path))
  pin = {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}
  return (pin, b''.join(chunks)) if raw else pin

def body(row):
  return {key: row[key] for key in ('bytes', 'sha256')}

def parse(raw):
  def pairs(items):
    result = {}
    for key, value in items:
      check(key not in result, 'Duplicate key: ' + key)
      result[key] = value
    return result
  return json.loads(raw, object_pairs_hook=pairs,
    parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))

def load(path):
  return parse(fp(path, True)[1])

def command(label, argv, output, report):
  stdout, stderr = output / (label + '.stdout'), output / (label + '.stderr')
  row = {'label': label, 'argv': argv, 'actual_wait_returncode': None}
  report['commands'].append(row)
  try:
    with stdout.open('xb') as out, stderr.open('xb') as err:
      row['actual_wait_returncode'] = subprocess.run(argv, stdout=out, stderr=err, check=False).returncode
  finally:
    for key, path in (('stdout', stdout), ('stderr', stderr)):
      if path.exists():
        row[key] = fp(path)
  check(type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0,
    label + ' failed; partial retained')

def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--package', type=Path, required=True)
  parser.add_argument('--manifest-sha256', required=True)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  package, output = safe(args.package), safe(args.output)
  check(package.is_dir() and not output.exists() and not output.is_relative_to(package)
    and not package.is_relative_to(output), 'Fresh separate output required')
  seal, raw = fp(package / 'evidence-manifest.json', True)
  check(re.fullmatch('[0-9a-f]{64}', args.manifest_sha256)
    and seal['sha256'] == args.manifest_sha256, 'Manifest SHA differs')
  manifest = parse(raw)
  helper = package / 'student_curves_archive.py'
  helper_pin = fp(helper)
  matched = [x for x in manifest['files'] if x['path'] == 'student_curves_archive.py']
  check(len(matched) == 1 and body(matched[0]) == body(helper_pin)
    and helper_pin['sha256'] == ARCHIVE_SHA, 'Helper SHA differs')
  output.mkdir(parents=True, exist_ok=False)
  report = {'schema_version': 1, 'status': 'running', 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    'package_manifest': seal, 'archive_source': helper_pin,
    'commands': [], 'restaged_files': [], 'scope': 'Scalar CPU replay only; no model or rollout.',
    **FALSE_FLAGS}
  failed = False
  try:
    restored = output / 'restored'
    command('restore', [sys.executable, '-B', str(helper), 'restore', '--package', str(package),
      '--manifest-sha256', args.manifest_sha256, '--output', str(restored)], output, report)
    receipt = load(restored / 'restoration.json')
    check(receipt['status'] == 'original_student_curve_evidence_restored'
      and receipt['package_manifest_sha256'] == args.manifest_sha256, 'Restore receipt differs')
    mapping = load(package / 'restore-map.json')
    origins, by_logical = {}, {}
    for row in mapping['records']:
      source = str(safe(row['source']))
      logical = str(relative(row['logical_path']))
      check(source not in origins and logical not in by_logical, 'Duplicate archive path')
      origins[source] = row; by_logical[logical] = row

    def original(row):
      check(row['path'] in origins, 'Missing source: ' + row['path'])
      record = origins[row['path']]
      check(body(record) == body(row), 'Archive bytes differ')
      path = restored / relative(record['logical_path'])
      check(body(fp(path)) == body(row) and stat.S_IMODE(path.stat().st_mode) == record['mode'],
        'Restore differs')
      return path, record

    accepted = by_logical['acceptance/contract.json']
    check(accepted['sha256'] == manifest['acceptance_contract_sha256'], 'Contract seal differs')
    acceptance_path, _ = original(dict(accepted, path=accepted['source']))
    acceptance = load(acceptance_path)
    check(len(acceptance['files']) == 13 and acceptance['kind'] in ('pure', 'finetune'), 'Roles differ')
    roles = {key: original(row)[0] for key, row in acceptance['files'].items()}
    execution = load(roles['cpu_execution'])
    created = load(roles['created_inspect'])
    mounts = created[0]['Mounts']
    namespace = {Path(x['Destination']): safe(x['Source']) for x in mounts}
    check(len(mounts) == len(namespace) == 4 and set(namespace)
      == {Path(x) for x in ('/code', '/control', '/artifacts', '/validation')}, 'Mounts differ')

    def translate(path):
      path = Path(path)
      check(path.is_absolute() and '..' not in path.parts, 'Unsafe container path')
      for prefix, source in namespace.items():
        if path.is_relative_to(prefix):
          return str(source / path.relative_to(prefix))
      raise ValueError('Unmapped path: ' + str(path))

    targets = set()

    def copy_original(pin, target):
      source, record = original(pin)
      target = safe(target)
      check(target.is_relative_to(output) and str(target) not in targets
        and not any(target.is_relative_to(x) or Path(x).is_relative_to(target) for x in targets),
        'Copy path collision')
      target.parent.mkdir(parents=True, exist_ok=True)
      with source.open('rb') as src, target.open('xb') as dst:
        for data in iter(lambda: src.read(8388608), b''):
          dst.write(data)
      target.chmod(record['mode'])
      check(body(fp(target)) == body(pin) and body(fp(source)) == body(pin)
        and stat.S_IMODE(target.stat().st_mode) == record['mode'], 'Copy differs')
      targets.add(str(target))
      report['restaged_files'].append({'original_source': pin['path'], 'logical_path': record['logical_path'],
        'restaged': fp(target), 'mode': record['mode']})

    input_pin = acceptance['files']['input_contract']
    check(translate('/control/input-contract.json') == input_pin['path'], 'Input namespace differs')
    copy_original(input_pin, output / 'input/control/input-contract.json')
    contract = load(roles['input_contract'])
    seen_inputs = {}

    def stage_inputs(value):
      if isinstance(value, dict):
        if {'path', 'bytes', 'sha256'} <= value.keys():
          path = Path(value['path'])
          prefix = next((x for x in (Path('/control'), Path('/artifacts')) if path.is_relative_to(x)), None)
          check(prefix is not None and '..' not in path.parts, 'Input outside RO mounts')
          source = translate(value['path'])
          target = output / 'input' / prefix.name / path.relative_to(prefix)
          check(source not in seen_inputs or seen_inputs[source] == body(value), 'Conflicting input fp')
          if source not in seen_inputs:
            copy_original(dict(value, path=source), target); seen_inputs[source] = body(value)
        for child in value.values():
          stage_inputs(child)
      elif isinstance(value, list):
        for child in value:
          stage_inputs(child)

    stage_inputs(contract)
    check(contract['kind'] == acceptance['kind'] and len(seen_inputs) >= 2, 'Inputs missing')
    for name, sha in CODE_SHAS.items():
      source = translate('/code/' + name)
      matches = [x for x in execution['source_before'] if x['path'] == source]
      check(len(matches) == 1 and matches[0]['sha256'] == sha, 'Source SHA differs')
      pin = matches[0]
      if name in ('extract_student_scalars.py', 'plot_student_learning_curves.py'):
        role = 'extract_source' if name.startswith('extract') else 'plot_source'
        check(acceptance['files'][role] == pin, 'Producer differs')
      copy_original(pin, output / 'code' / name)
    command('cpu', [sys.executable, '-B', str(output / 'code/run_cpu.py'), '--input', str(output / 'input'),
      '--contract-sha256', input_pin['sha256'], '--phase-source-sha256', CODE_SHAS['run_phases.py'],
      '--output', str(output / 'cpu')], output, report)
    result = load(output / 'cpu/host/execution.json')
    check(result['status'] == 'passed_student_learning_curves_CPU'
      and result['actual_start_attached_wait_returncode'] == 0
      and result['actual_container_exit_code'] == 0 and result['container_running'] is False,
      'CPU execution failed')
    phases = load(output / 'cpu/validation/phases.json')
    check(phases['status'] == 'passed' and [x['phase'] for x in phases['phases']] == ['extract', 'plot']
      and all(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode'] == 0 for x in phases['phases']), 'Phase waits differ')
    old, new = load(roles['scalars']), load(output / 'cpu/validation/scalars.json')
    compared = {key: old[key] == new[key] for key in ('scalars', 'tag_coverage', 'native_terminal', 'events')}
    check(new['status'] == 'passed' and all(compared.values()) and all(new[k] is False for k in FALSE_FLAGS),
      'Scalar content differs')
    report.update(status='passed_public_student_curve_CPU_replay', kind=contract['kind'], exact_comparisons=compared,
      tag_count=len(new['scalars']), scalar_row_count=sum(map(len, new['scalars'].values())),
      new_cpu_execution=fp(output / 'cpu/host/execution.json'),
      original_scalars=fp(roles['scalars']), replay_scalars=fp(output / 'cpu/validation/scalars.json'),
      replay_phases=fp(output / 'cpu/validation/phases.json'),
      replay_plot_report=fp(output / 'cpu/validation/plots/plot-report.json'))
    check(fp(package / 'evidence-manifest.json') == seal
      and fp(helper) == helper_pin, 'Sealed source changed')
  except Exception as error:
    failed = True
    report.update(status='failed_partial_replay', error=type(error).__name__ + ': ' + str(error))
  report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
  with (output / 'replay.json').open('x') as stream:
    json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
  print(json.dumps({'status': report['status'], 'report': str(output / 'replay.json')}))
  return int(failed)


if __name__ == '__main__':
  raise SystemExit(main())
