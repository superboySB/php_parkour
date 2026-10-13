#!/usr/bin/env python3
"""Archive accepted student scalar evidence, verify it, or restore original bytes.

Only Python's standard library is used. This tool launches no subprocess,
Docker, network, scientific computation, training, or model inference.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import zlib

sys.dont_write_bytecode = True
LIMIT = 25_000_000
BLOCK = 8 * 1024 * 1024
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
EXTRACT_SOURCE_SHA256 = None  # Fill only from the independently reviewed strict-TFRecord v2 freeze.
PLOT_SOURCE_SHA256 = None  # Unapproved v1 is deliberately not admitted.
TARGETS = {'pure': 10000, 'finetune': 30000}
CORE = {
    'pure': ['Loss/behavior', 'Loss/warmup_active'],
    'finetune': ['Loss/ppo_coef', 'Loss/warmup_active', 'Loss/learning_rate',
                 'Loss/total_loss', 'Loss/surrogate_loss', 'Loss/value_loss',
                 'Loss/behavior', 'Loss/entropy_mean', 'Loss/mean_kl'],
}
CONDITIONAL = {'Train/mean_reward', 'Train/mean_episode_length', 'Loss/ppo_gate_mean'}
FALSE_FLAGS = ['quality_verified', 'convergence_verified', 'official_schedule_complete',
               'seven_PT_acceptance_verified', 'pt_onnx_numerical_parity_verified']
ROLES = {'input_contract', 'scalars', 'plot_report', 'extract_source', 'plot_source',
         'cpu_execution', 'cpu_phases', 'created_inspect', 'running_inspect',
         'final_inspect', 'root_review', 'independent_review', 'publication_source'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    path = Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            'Nonsymlink canonical file required: ' + str(path))
    require(stat.S_ISREG(path.lstat().st_mode), 'Regular file required: ' + str(path))
    return path


def signature(path):
    value = regular(path).stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mode,
            value.st_mtime_ns, value.st_ctime_ns)


def fingerprint(path):
    path = regular(path)
    before = signature(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(BLOCK), b''):
            digest.update(data)
    require(signature(path) == before, 'Source changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': before[2], 'sha256': digest.hexdigest()}


def body(record):
    require(type(record.get('bytes')) is int and record['bytes'] >= 0
            and re.fullmatch('[0-9a-f]{64}', record.get('sha256', '')),
            'Invalid fingerprint')
    return {'bytes': record['bytes'], 'sha256': record['sha256']}


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path, expected=None):
    path = regular(path)
    before = signature(path)
    raw = path.read_bytes()
    require(signature(path) == before, 'JSON source changed while reading')
    actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        require(actual == body(expected), 'Pinned JSON bytes differ: ' + str(path))
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def relative(value):
    require(isinstance(value, str), 'Relative path must be a string')
    path = PurePosixPath(value)
    require(value and str(path) == value and value != '.' and not path.is_absolute()
            and '..' not in path.parts, 'Unsafe relative path: ' + value)
    return path


def fresh(path, forbidden=()):
    path = Path(path).absolute()
    require('..' not in path.parts and not path.exists() and not path.is_symlink()
            and not any(p.is_symlink() for p in path.parents), 'Use a fresh nonsymlink output')
    for other in forbidden:
        other = Path(other).absolute()
        require(not path.is_relative_to(other) and not other.is_relative_to(path),
                'Output and input/package directories must be separate')
    return path


def inspect_document(value):
    if isinstance(value, list):
        require(len(value) == 1, 'Exactly one owned container inspect required')
        value = value[0]
    return value


def admit(contract_path, contract_sha256):
    """Validate an explicitly reviewed future actual acceptance contract."""
    require(re.fullmatch('[0-9a-f]{64}', contract_sha256), 'Explicit reviewed contract SHA required')
    contract_fp = fingerprint(contract_path)
    require(contract_fp['sha256'] == contract_sha256, 'Acceptance contract SHA differs')
    c = load(contract_path, contract_fp)
    require(c.get('schema_version') == 1
            and c.get('status') == 'reviewed_actual_student_learning_curves_cpu_acceptance'
            and c.get('kind') in TARGETS and set(c.get('files', {})) == ROLES,
            'Incomplete actual student curve acceptance contract')
    kind, target = c['kind'], TARGETS[c['kind']]
    require(set(c.get('figures', {})) == {'png', 'svg'}, 'Both exact PNG/SVG figures required')
    require(isinstance(EXTRACT_SOURCE_SHA256, str) and isinstance(PLOT_SOURCE_SHA256, str)
            and c['files']['extract_source']['sha256'] == EXTRACT_SOURCE_SHA256
            and c['files']['plot_source']['sha256'] == PLOT_SOURCE_SHA256,
            'Actual producers must match the frozen reviewed source version')
    records = {regular(contract_path): contract_fp}

    def retain(record, path=None):
        requested = path or record['path']
        try:
            path = regular(requested)
        except FileNotFoundError as error:
            raise ValueError('Original evidence missing; obtain the exact original, not a regenerated substitute: '
                             + str(requested) + '; native_path=' + str(record.get('native_path', 'see input contract'))
                             + '; bytes=' + str(record['bytes']) + '; sha256=' + record['sha256']) from error
        actual = fingerprint(path)
        require(body(actual) == body(record), 'Bound evidence changed: ' + str(path))
        if path in records:
            require(records[path] == actual, 'Conflicting evidence fingerprint')
        records[path] = actual
        return path

    for record in [*c['files'].values(), *c['figures'].values()]:
        retain(record)
    require(regular(c['files']['publication_source']['path']) == regular(__file__),
            'Reviewed publication source must be this exact file')
    files = {key: load(value['path'], value) for key, value in c['files'].items()
             if key not in {'extract_source', 'plot_source', 'publication_source'}}
    execution, phases = files['cpu_execution'], files['cpu_phases']
    require(type(execution['create_actual_returncode']) is int and execution['create_actual_returncode'] == 0
            and type(execution['actual_start_attached_wait_returncode']) is int
            and execution['actual_start_attached_wait_returncode'] == 0
            and type(execution['actual_container_exit_code']) is int
            and execution['actual_container_exit_code'] == 0 and execution['container_running'] is False
            and execution['source_unchanged'] is True
            and execution['source_before'] == execution['source_after'], 'Actual CPU normal exit/source proof required')
    cid = execution['container_id']
    require(re.fullmatch('[0-9a-f]{64}', cid), 'Full own container ID required')
    inspections = [inspect_document(files[key]) for key in ('created_inspect', 'running_inspect', 'final_inspect')]
    mounts = None
    for value in inspections:
        require(value['Id'] == cid and value['Image'] == IMAGE, 'Own actual CPU identity/image differs')
        cfg = value['HostConfig']
        require(cfg['Runtime'] == 'runc' and cfg['NetworkMode'] == 'none'
                and cfg['DeviceRequests'] in (None, []) and cfg['NanoCpus'] == 2_000_000_000
                and cfg['Memory'] == 12 * 1024**3, 'Actual CPU isolation differs')
        env = dict(item.split('=', 1) for item in value['Config']['Env'])
        require(env.get('CUDA_VISIBLE_DEVICES') == '' and env.get('NVIDIA_VISIBLE_DEVICES') == 'void'
                and env.get('PYTHONDONTWRITEBYTECODE') == '1', 'GPU hidden/bytecode-off required')
        current = sorted(value['Mounts'], key=lambda item: item['Destination'])
        require(len(current) == 4 and len({item['Destination'] for item in current}) == 4,
                'Four unique actual bind mounts required')
        require({item['Destination']: item['RW'] for item in current}
                == {'/code': False, '/control': False, '/artifacts': False, '/validation': True}
                and all(item['Type'] == 'bind' for item in current), 'Three RO and one RW bind required')
        if mounts is not None:
            require(current == mounts, 'Inspect mount identity changed')
        mounts = current
    require(inspections[0]['State']['Status'] == 'created'
            and inspections[1]['State']['Running'] is True
            and inspections[2]['State']['Status'] == 'exited'
            and inspections[2]['State']['Running'] is False
            and inspections[2]['State']['ExitCode'] == 0
            and inspections[1]['State']['StartedAt'] == inspections[2]['State']['StartedAt']
            and all(value['Name'] == inspections[0]['Name'] for value in inspections),
            'Actual created/live/naturally-exited CPU observations required')
    namespace = [(Path(item['Destination']), Path(item['Source'])) for item in mounts]

    def translate(path):
        path = Path(path)
        require(path.is_absolute() and '..' not in path.parts, 'Absolute safe evidence path required')
        for prefix, provider in namespace:
            if path.is_relative_to(prefix):
                return provider / path.relative_to(prefix)
        return path

    def bound(record, role=None):
        path = retain(record, translate(record['path']))
        if role:
            require(path == regular(c['files'][role]['path']), 'Accepted producer binding differs: ' + role)
        return path

    def references(value):
        if isinstance(value, dict):
            if {'path', 'bytes', 'sha256'} <= value.keys():
                bound(value)
            for item in value.values():
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    references(execution)
    require(phases['status'] == 'passed' and phases['inputs_unchanged'] is True
            and phases['inputs_before'] == phases['inputs_after']
            and [row['phase'] for row in phases['phases']] == ['extract', 'plot']
            and all(type(row['actual_wait_returncode']) is int and row['actual_wait_returncode'] == 0
                    for row in phases['phases']), 'Two actual extract/plot phase0 receipts required')
    references(phases)
    sc, pl, inp = files['scalars'], files['plot_report'], files['input_contract']
    require(sc['schema_version'] == 1 and sc['phase'] == 'student_training_scalars'
            and sc['status'] == 'passed' and sc['kind'] == kind and sc['stage'] == 'student-' + kind
            and sc['target_iterations'] == target and sc['training_scalar_integrity_complete'] is True
            and sc['required_core_tags'] == CORE[kind] and sc['diagnostics'] == []
            and sc['input_files_unchanged'] is True and sc['event_integrity_complete'] is True,
            'Typed full scalar and strict event-integrity acceptance required')
    require(all(sc[flag] is False and pl[flag] is False for flag in FALSE_FLAGS),
            'Scalar/archive acceptance cannot claim model, quality, convergence or full schedule acceptance')
    bound(sc['input_contract'], 'input_contract')
    bound(sc['extractor_source'], 'extract_source')
    require(inp['schema_version'] == 1 and inp['kind'] == kind, 'Actual extractor input contract differs')
    native_path = bound(inp['native_manifest'])
    native = load(native_path, inp['native_manifest'])
    require(native['status'] == 'passed' and type(native['returncode']) is int and native['returncode'] == 0
            and native['profile'] == 'official' and native['label'] == 'student-' + kind
            and type(native['checkpoint_iteration']) is int and native['checkpoint_iteration'] == target - 1
            and str(Path(native['checkpoint']).parent) == inp['native_run_directory'],
            'Actual same-run official native manifest identity required')
    require(sc['native_terminal'] == {key: native[key] for key in
            ('label', 'profile', 'status', 'returncode', 'checkpoint', 'checkpoint_iteration',
             'checkpoint_sha256', 'finished_utc')}, 'Scalar native identity subset differs')
    bound(sc['native_manifest'])
    require(body(sc['native_manifest']) == body(inp['native_manifest']), 'Scalar native manifest differs')
    events = inp['events']
    require(events and len({row['path'] for row in events}) == len(events), 'Exact actual event set required')
    run_dir = translate(inp['run_directory'])
    require({str(path) for path in run_dir.glob('events.out.tfevents.*')}
            == {str(translate(row['path'])) for row in events}, 'Actual same-run event file-set changed')
    for row in events:
        require(Path(row['path']).parent == Path(inp['run_directory'])
                and row['native_path'] == str(Path(inp['native_run_directory']) / Path(row['path']).name),
                'Event original run provenance differs')
        bound(row)
    require([{key: row[key] for key in ('path', 'bytes', 'sha256', 'native_path')} for row in sc['events']]
            == events, 'Typed scalar events differ from accepted inputs')
    for row in sc['events']:
        integrity = row['tfrecord_integrity']
        require(integrity['status'] == 'passed' and integrity['format'] == 'TFRecord'
                and integrity['complete_eof'] is True and integrity['crc32c_verified'] is True
                and type(integrity['records']) is int and integrity['records'] > 0
                and body(integrity) == body(row), 'Strict same-whole-event TFRecord CRC/EOF proof required')
    require(sc['input_files'] == [sc['input_contract'], sc['native_manifest'],
            *[{key: row[key] for key in ('path', 'bytes', 'sha256')} for row in events]],
            'Full accepted extractor input inventory differs')
    for tag in CORE[kind]:
        coverage = sc['tag_coverage'][tag]
        unique = coverage['unique_steps']
        require((unique == target or unique == list(range(target))) and coverage['samples'] == target
                and coverage['first_step'] == 0 and coverage['last_step'] == target - 1
                and not any(coverage[key] for key in ('missing_steps', 'duplicate_steps', 'out_of_range_steps', 'out_of_order'))
                and coverage['all_finite'] is True and coverage['required_core'] is True,
                'Core scalar coverage incomplete: ' + tag)
    require(set(sc['tag_coverage']) == set(sc['scalars']) | set(CORE[kind]) | CONDITIONAL
            and all(row['all_finite'] is True for row in sc['tag_coverage'].values()), 'Actual tags must remain complete and finite')
    require(pl['status'] == 'rendered_student_training_curves' and pl['kind'] == kind
            and pl['stage'] == sc['stage'] and pl['target_iterations'] == target
            and pl['input_files_unchanged'] is True and pl['events'] == sc['events']
            and pl['input_contract'] == sc['input_contract'] and pl['native_manifest'] == sc['native_manifest']
            and pl['input_files'] == [*sc['input_files'], pl['input']],
            'Actual matching plot acceptance required')
    bound(pl['input'], 'scalars')
    bound(pl['plot_source'], 'plot_source')
    require(len(pl['figures']) == 2, 'Both actual plot figures required')
    require({str(translate(row['path'])): body(row) for row in pl['figures']}
            == {str(regular(row['path'])): body(row) for row in c['figures'].values()}, 'Plot figure originals differ')
    references(sc)
    references(pl)
    for phase, role in zip(phases['phases'], ('extract_source', 'plot_source')):
        matching = [arg for arg in phase['argv'] if isinstance(arg, str)
                    and Path(arg).name == Path(c['files'][role]['path']).name]
        require(len(matching) == 1 and translate(matching[0]) == regular(c['files'][role]['path']),
                'Actual phase argv does not bind accepted producer source')
        argv = phase['argv']
        def argument(flag):
            require(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv),
                    'Actual producer argument missing/duplicated: ' + flag)
            return argv[argv.index(flag) + 1]
        if role == 'extract_source':
            require(translate(argument('--contract')) == regular(c['files']['input_contract']['path'])
                    and argument('--contract-sha256') == c['files']['input_contract']['sha256']
                    and translate(argument('--output')) == regular(c['files']['scalars']['path']),
                    'Actual extract argv input/output SHA binding differs')
        else:
            require(translate(argument('--input')) == regular(c['files']['scalars']['path'])
                    and argument('--input-sha256') == c['files']['scalars']['sha256']
                    and translate(argument('--output')) == regular(c['files']['plot_report']['path']).parent,
                    'Actual plot argv input/output SHA binding differs')
    required_review_paths = {str(regular(c['files'][role]['path'])) for role in
                             ('input_contract', 'scalars', 'plot_report', 'cpu_execution', 'cpu_phases',
                              'extract_source', 'plot_source')}
    required_review_paths |= {str(regular(row['path'])) for row in c['figures'].values()}
    for role in ('root_review', 'independent_review'):
        review = files[role]
        require(review.get('status') in ('passed', 'passed_readonly_postexecution_review',
                                        'passed_student_learning_curves_postexecution_review')
                and review.get('must_fix') == [], 'Actual reviewed CPU acceptance required: ' + role)
        refs = review.get('evidence_fingerprints')
        require(isinstance(refs, list) and required_review_paths <= {str(translate(row['path'])) for row in refs},
                'Review must bind actual scientific, execution, source and figure evidence')
        references(review)
    rows = [('acceptance/contract.json', contract_fp, False)]
    rows += [('acceptance/' + role + Path(row['path']).suffix, row, False) for role, row in c['files'].items()]
    rows += [('figures/learning-curves.' + suffix, row, False) for suffix, row in c['figures'].items()]
    rows += [('inputs/native-manifest.json', fingerprint(native_path), False)]
    rows += [('inputs/events/' + str(index).zfill(4) + '/' + Path(row['path']).name,
              fingerprint(translate(row['path'])), True) for index, row in enumerate(events)]
    # Retain every fingerprinted input/source/raw receipt referenced by either
    # actual review, not just the explicitly named report/figure subset.
    used = {str(regular(row['path'])) for _, row, _ in rows}
    for index, (path, record) in enumerate(sorted(records.items(), key=lambda item: str(item[0]))):
        if str(path) not in used:
            rows.append(('referenced/' + str(index).zfill(5) + '/' + path.name, record, False))
    return c, sc, rows, records


class ChunkWriter:
    def __init__(self, package, prefix):
        self.package, self.prefix = package, prefix
        self.rows, self.stream, self.current, self.total = [], None, None, 0
        self.whole = hashlib.sha256()

    def write(self, data):
        original = len(data)
        while data:
            if self.stream is None:
                path = self.prefix + '/' + str(len(self.rows)).zfill(5) + '.bin'
                target = self.package / path
                target.parent.mkdir(parents=True, exist_ok=True)
                self.stream = target.open('xb')
                self.current = {'path': path, 'offset': self.total, 'bytes': 0, 'sha256': None}
                self.digest = hashlib.sha256()
            part, data = data[:LIMIT - self.current['bytes']], data[LIMIT - self.current['bytes']:]
            self.stream.write(part)
            self.digest.update(part)
            self.whole.update(part)
            self.current['bytes'] += len(part)
            self.total += len(part)
            if self.current['bytes'] == LIMIT:
                self.close_chunk()
        return original

    def flush(self):
        if self.stream:
            self.stream.flush()

    def close_chunk(self):
        if self.stream is not None:
            self.stream.close()
            self.current['sha256'] = self.digest.hexdigest()
            self.rows.append(self.current)
            self.stream = None

    def finish(self):
        self.close_chunk()
        return self.rows, {'bytes': self.total, 'sha256': self.whole.hexdigest()}


def archive_record(package, logical, original, event, shared):
    source = regular(original['path'])
    initial = signature(source)
    require(stat.S_IMODE(initial[3]) <= 0o777, 'Special permission bits are outside the restore contract')
    require(body(fingerprint(source)) == body(original), 'Accepted source changed before archive')
    compressed = event or original['bytes'] > LIMIT
    encoding = 'gzip' if compressed else 'raw'
    key = (encoding, original['sha256'], original['bytes'])
    if key not in shared:
        writer = ChunkWriter(package, 'payload/' + encoding + '-' + original['sha256'])
        sink = gzip.GzipFile(filename='', mode='wb', fileobj=writer, mtime=0) if compressed else writer
        actual_sha, actual_bytes = hashlib.sha256(), 0
        try:
            with source.open('rb') as stream:
                for data in iter(lambda: stream.read(BLOCK), b''):
                    actual_sha.update(data)
                    actual_bytes += len(data)
                    sink.write(data)
        finally:
            if compressed:
                sink.close()
            chunks, encoded = writer.finish()
        require({'bytes': actual_bytes, 'sha256': actual_sha.hexdigest()} == body(original), 'Archive input changed while copying')
        shared[key] = {'encoding': encoding, 'gzip_mtime': 0 if compressed else None,
                       'encoded': encoded, 'chunks': chunks}
    require(signature(source) == initial and body(fingerprint(source)) == body(original),
            'Source changed during archive')
    return {'logical_path': logical, 'source': str(source), 'bytes': original['bytes'],
            'sha256': original['sha256'], 'mode': stat.S_IMODE(initial[3]), **shared[key]}


def decode_record(package, record, destination=None):
    encoded_sha, original_sha = hashlib.sha256(), hashlib.sha256()
    encoded_size = original_size = 0
    decoder = zlib.decompressobj(31) if record['encoding'] == 'gzip' else None
    require(record['encoding'] in ('raw', 'gzip')
            and (decoder is None or record['gzip_mtime'] == 0), 'Unsupported archive encoding')
    for chunk in record['chunks']:
        path = package.joinpath(*relative(chunk['path']).parts)
        require(chunk['offset'] == encoded_size and 0 < chunk['bytes'] <= LIMIT
                and body(fingerprint(path)) == body(chunk), 'Chunk offset, size or SHA differs')
        with path.open('rb') as stream:
            for data in iter(lambda: stream.read(BLOCK), b''):
                encoded_sha.update(data)
                encoded_size += len(data)
                pending = data
                while pending:
                    output = decoder.decompress(pending, BLOCK) if decoder else pending
                    pending = decoder.unconsumed_tail if decoder else b''
                    original_size += len(output)
                    require(original_size <= record['bytes'], 'Decoded original exceeds declared size')
                    original_sha.update(output)
                    if destination:
                        destination.write(output)
        require(body(fingerprint(path)) == body(chunk), 'Chunk changed during restoration')
    if decoder:
        output = decoder.flush()
        original_size += len(output)
        original_sha.update(output)
        if destination:
            destination.write(output)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'Truncated or trailing gzip data')
    require({'bytes': encoded_size, 'sha256': encoded_sha.hexdigest()} == record['encoded']
            and {'bytes': original_size, 'sha256': original_sha.hexdigest()} == body(record),
            'Encoded or original whole SHA differs')


def verify(package, manifest_sha256):
    package = Path(package).absolute()
    expected = fingerprint(package / 'evidence-manifest.json')
    require(expected['sha256'] == manifest_sha256, 'Explicit package manifest SHA differs')
    manifest = load(package / 'evidence-manifest.json', expected)
    require(manifest['status'] == 'completed_student_learning_curves_archive'
            and manifest['kind'] in TARGETS and manifest['quality_verified'] is False
            and manifest['official_schedule_complete'] is False, 'Actual scalar archive manifest required')
    paths = set()
    for row in manifest['files']:
        rel = str(relative(row['path']))
        require(rel not in paths and row['bytes'] <= LIMIT, 'Duplicate or over-limit Git blob')
        paths.add(rel)
        require(body(fingerprint(package / rel)) == body(row), 'Package bytes changed: ' + rel)
    require({str(path.relative_to(package)) for path in package.rglob('*') if path.is_file()}
            == paths | {'evidence-manifest.json'}
            and not any(path.is_symlink() for path in package.rglob('*')), 'Exact package file-set differs')
    mapping = load(package / 'restore-map.json')
    logical = set()
    for row in mapping['records']:
        rel = str(relative(row['logical_path']))
        require(rel != 'restoration.json' and rel not in logical
                and type(row['mode']) is int and 0 <= row['mode'] <= 0o777,
                'Duplicate restore path or unsupported mode')
        require(not any(rel.startswith(other + '/') or other.startswith(rel + '/') for other in logical),
                'Restore file/directory collision')
        logical.add(rel)
        require(all(str(relative(chunk['path'])) in paths for chunk in row['chunks']), 'Unsealed restore chunk')
        decode_record(package, row)
    require(mapping['status'] == 'original_byte_restore_map' and len(logical) == manifest['restore_records'],
            'Restore record count differs')
    return manifest, mapping


def publish(args):
    c, scalars, inputs, expected = admit(args.contract, args.contract_sha256)
    output = fresh(args.output, [Path(row['path']).parent for _, row, _ in inputs])
    output.mkdir(exist_ok=False)
    try:
        mapping, shared = [], {}
        for logical, record, event in inputs:
            relative(logical)
            mapping.append(archive_record(output, logical, record, event, shared))
        # Ordinary figures remain directly readable. Large SVG, PNG, JSON, event
        # or other evidence bodies still archive completely through gzip chunks.
        direct_figures = {}
        for suffix, original in c['figures'].items():
            direct_figures[suffix] = original['bytes'] <= LIMIT
            if not direct_figures[suffix]:
                continue
            target = output / 'figures' / ('learning-curves.' + suffix)
            target.parent.mkdir(exist_ok=True)
            with regular(original['path']).open('rb') as source, target.open('xb') as destination:
                shutil.copyfileobj(source, destination, BLOCK)
            require(body(fingerprint(target)) == body(original), 'Original figure copy differs')
        helper = output / 'student_curves_archive.py'
        with regular(__file__).open('rb') as source, helper.open('xb') as destination:
            shutil.copyfileobj(source, destination, BLOCK)
        require(body(fingerprint(helper)) == body(c['files']['publication_source']),
                'Public verification/restoration helper copy differs')
        save(output / 'restore-map.json', {'schema_version': 1, 'status': 'original_byte_restore_map',
             'raw_json_rewritten': False, 'mode_restored_not_uid_gid': True, 'records': mapping})
        summary = {'schema_version': 1, 'status': 'accepted_student_scalar_archive', 'kind': c['kind'],
                   'target_iterations': TARGETS[c['kind']], 'required_core_tags': scalars['required_core_tags'],
                   'tag_coverage': scalars['tag_coverage'], 'event_count': len(scalars['events']),
                   'direct_figure_previews': direct_figures,
                   'actual_CPU_phase_exits': [0, 0], 'scope': 'Scalar integrity, actual accepted curves and lossless evidence archive only',
                   'quality_verified': False, 'convergence_verified': False, 'official_schedule_complete': False,
                   'seven_PT_acceptance_verified': False, 'pt_onnx_numerical_parity_verified': False}
        save(output / 'summary.json', summary)
        image = ('![真实训练曲线](figures/learning-curves.png)\n\n' if direct_figures['png'] else
                 '原始PNG超过25MB，已完整gzip分块；请按恢复映射恢复后查看，未生成替代图。\n\n')
        svg = ('[SVG](figures/learning-curves.svg)' if direct_figures['svg'] else
               '[原始SVG超过25MB：完整分块及无损恢复路径](restore-map.json)')
        (output / 'index.md').write_text('# 正式学生原始训练曲线\n\n'
            + c['kind'] + '：实际 extract/plot CPU验收与完整原始事件归档。'
            + '本包不证明模型质量、收敛、物理技能、全部日程或PT/ONNX parity。\n\n'
            + image + svg + ' · [范围和真实coverage](summary.json) · '
            + '[原字节恢复映射](restore-map.json) · [SHA清单](evidence-manifest.json) · '
            + '[校验与恢复源码](student_curves_archive.py)\n\n'
            + '用已审源码 student_curves_archive.py 的 verify/restore 子命令，显式传本manifest SHA；'
            + 'restore只向全新目录恢复原bytes及mode，不改JSON内部原绝对路径，不运行科学任务。\n')
        for row in expected.values():
            require(body(fingerprint(row['path'])) == body(row), 'Accepted source changed before seal')
        for row in mapping:
            require(stat.S_IMODE(regular(row['source']).stat().st_mode) == row['mode'],
                    'Source mode changed before seal')
            decode_record(output, row)
        files = []
        for path in sorted(output.rglob('*')):
            if path.is_file():
                row = fingerprint(path)
                require(row['bytes'] <= LIMIT, 'Publication file exceeds 25MB')
                files.append({'path': str(path.relative_to(output)), **body(row)})
        manifest = {'schema_version': 1, 'status': 'completed_student_learning_curves_archive',
                    'kind': c['kind'], 'acceptance_contract_sha256': args.contract_sha256,
                    'restore_records': len(mapping), 'chunk_limit_bytes': LIMIT, 'files': files,
                    'raw_json_rewritten': False, 'quality_verified': False, 'official_schedule_complete': False}
        save(output / 'evidence-manifest.json', manifest)  # Only successful seal, always last.
        return {'status': manifest['status'], 'package': str(output),
                'manifest': fingerprint(output / 'evidence-manifest.json'), 'files': len(files) + 1}
    except BaseException as error:
        save(output / 'publication-failure.json', {'status': 'failed_partial_archive',
             'error': type(error).__name__ + ': ' + str(error), 'success_manifest_created': False})
        raise


def restore(args):
    package = Path(args.package).absolute()
    manifest, mapping = verify(package, args.manifest_sha256)  # Entire preflight before mkdir.
    output = fresh(args.output, [package])
    output.mkdir(exist_ok=False)
    restored = []
    for row in mapping['records']:
        path = output.joinpath(*relative(row['logical_path']).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            decode_record(package, row, stream)
        path.chmod(row['mode'])
        actual = fingerprint(path)
        require(body(actual) == body(row) and stat.S_IMODE(path.stat().st_mode) == row['mode'],
                'Restored bytes/mode differ')
        restored.append(actual)
    verify(package, args.manifest_sha256)
    receipt = {'status': 'original_student_curve_evidence_restored', 'package_manifest_sha256': args.manifest_sha256,
               'restored': restored, 'raw_json_rewritten': False, 'science_executed': False,
               'mode_restored_not_uid_gid': True}
    save(output / 'restoration.json', receipt)  # Failure retains partial without success receipt.
    return {'status': receipt['status'], 'output': str(output), 'records': len(restored),
            'receipt': fingerprint(output / 'restoration.json'), 'science_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pub = commands.add_parser('publish')
    pub.add_argument('--contract', type=Path, required=True)
    pub.add_argument('--contract-sha256', required=True)
    pub.add_argument('--output', type=Path, required=True)
    for name in ('verify', 'restore'):
        item = commands.add_parser(name)
        item.add_argument('--package', type=Path, required=True)
        item.add_argument('--manifest-sha256', required=True)
        if name == 'restore':
            item.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'publish':
        result = publish(args)
    elif args.command == 'restore':
        result = restore(args)
    else:
        manifest, mapping = verify(args.package, args.manifest_sha256)
        result = {'status': 'verified_student_curve_archive', 'kind': manifest['kind'],
                  'records': len(mapping['records']), 'science_executed': False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
