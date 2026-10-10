#!/usr/bin/env python3
"""Read closed historical streams and sealed receipts; stdlib, no subprocesses."""
from pathlib import Path
import collections
import datetime
import hashlib
import json
import stat

ROOT = Path('/home/dzp/projects/php_parkour')
OLD = ROOT / 'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
RECOVERY = ROOT / 'outputs/research/fresh629-recovery-01'
OUTPUT = RECOVERY / 'writer-mapping-audit-final-01'
ROLES = ('simulator', 'inference')
EXPECTED_MISSING = {
    'high_speed_speed_vault:0004:run_left_45_0.3s',
    'high_speed_speed_vault:0005:run_left_45_0.5s',
    'high_speed_speed_vault:0006:run_left_45_0.9s',
    'high_speed_speed_vault:0007:run_left_45_1.2s',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), str(path))
    require(stat.S_ISREG(path.stat().st_mode), str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': digest.hexdigest()}


def read(path):
    return json.loads(Path(path).read_text())


def actual(path):
    return OLD / 'outputs' / Path(path).relative_to('/outputs')


def check_fingerprint(path, record):
    observed = fingerprint(path)
    require(all(observed[key] == record[key] for key in ('bytes', 'sha256')),
            'Fingerprint mismatch: ' + str(path))
    return observed


def write(name, data):
    with (OUTPUT / name).open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    proof_paths = {
        'matrix': OLD / 'outputs/all-configs/matrix.json',
        'cpu_final': RECOVERY / 'cpu-final-validation/full-validation.json',
        'manager_final': RECOVERY / 'manager/receipt.json',
        'manager_actual_wait': RECOVERY / 'manager-process-exit.json',
        'original_session143': ROOT / 'outputs/research/fresh629-root-terminal-01/session54334.json',
        'original_host_receipt': OLD / 'host/launch-receipt.json',
        'original_observer_launch': OLD / 'host/observer/launch.json',
        'recovery_observer_launch': RECOVERY / 'observer/launch.json',
        'recovery_observer_summary': RECOVERY / 'observer/summary.json',
        'observer_source': OLD / 'control/observe_container_pids.py',
        'historical_audit01_analysis': RECOVERY / 'writer-mapping-audit-01/analysis.json',
        'audit_source': Path(__file__),
    }
    proofs = {name: fingerprint(path) for name, path in proof_paths.items()}
    matrix, cpu, manager = (read(proof_paths[name]) for name in ('matrix', 'cpu_final', 'manager_final'))
    launches = [read(proof_paths[name]) for name in ('original_observer_launch', 'recovery_observer_launch')]
    summary = read(proof_paths['recovery_observer_summary'])
    identity_keys = ('container_id', 'image_id', 'host_init_pid', 'started_at')
    identity = {key: launches[0]['identity'][key] for key in identity_keys}
    for receipt in (*launches, summary):
        require({key: receipt['identity'][key] for key in identity_keys} == identity,
                'Observer container identity differs')
        require(receipt['source_sha256'] == proofs['observer_source']['sha256'],
                'Observer source differs')
    require(summary['stop_reason'] == 'stop_file' and summary['errors'] == [], 'Recovery observer not cleanly closed')
    require(matrix['status'] == 'completed' and matrix['completed_configurations'] == 629
            and len(matrix['selections']) == 629 and matrix['completed_scenarios'] == 17,
            'Original matrix is not completed629')
    require(cpu['status'] == 'passed' and cpu['configurations'] == 629
            and cpu['worker_exit0_empty_group_count'] == 1258 and cpu['full_decoded_mp4_count'] == 629
            and cpu['matrix_sha256'] == proofs['matrix']['sha256'], 'CPU629 proof mismatch')
    check_fingerprint(proof_paths['cpu_final'], manager['full_validation'])
    check_fingerprint(proof_paths['matrix'], manager['terminal_matrix'])
    check_fingerprint(proof_paths['recovery_observer_summary'], manager['recovery_observer_stop']['summary'])
    require(manager['status'] == 'recovered_native_and_cpu_completed_with_host_observer_gap'
            and manager['errors'] == [] and manager['read_errors'] == [], 'Manager final mismatch')
    require(manager['original_daemon_terminal']['exec']['ExitCode'] == 0
            and manager['original_daemon_terminal']['exec']['Running'] is False
            and manager['cpu_validation_returncode'] == 0, 'Native/CPU actual exit mismatch')
    require(manager['snapshot_files_verified_before'] == manager['snapshot_files_verified_after'] == 5206,
            'Sealed snapshot count mismatch')
    require(all(manager[key]['running_after_stop'] is False
                and manager[key]['after']['State']['Running'] is False
                for key in ('adopted_gpu_container_stop', 'owned_cpu_container_stop')),
            'Own GPU/CPU stop not verified')
    require(read(proof_paths['manager_actual_wait'])['actual_wait_returncode'] == 0,
            'Manager actual wait not zero')
    original143 = read(proof_paths['original_session143'])
    require(original143['exit_code'] == original143['actual_tool_result']['exit_code'] == 143
            and original143['normal_zero_exit_verified'] is False,
            'Original143 history differs')
    require(read(proof_paths['original_host_receipt'])['status'] == 'running',
            'Original host receipt was overwritten')

    cpu_cases = {case['case_id']: case for case in cpu['cases']}
    require(len(cpu_cases) == 629, 'Duplicate CPU cases')
    rows, row_by_key = [], {}
    for case in matrix['selections']:
        require(case['status'] == 'completed' and len(case['attempts']) == 1, 'Not once-only completed')
        attempt = case['attempts'][0]
        require(attempt['status'] == 'completed' and attempt['returncode'] == 0, 'Native attempt failed')
        evidence_path = actual(attempt['evidence']['path'])
        evidence_fp = check_fingerprint(evidence_path, attempt['evidence'])
        evidence = read(evidence_path)
        sealed = {item['path']: item for item in evidence['files']}
        cpu_case = cpu_cases[case['case_id']]
        require(cpu_case['parent_returncode'] == 0 and cpu_case['policy_ticks'] == 500
                and cpu_case['worker_exit0_empty_groups'] == 2,
                'CPU case exit/ticks mismatch')
        require(len(cpu_case['videos']) == 1 and all(video['full_decode'] is True
                and video['returncode'] == 0 for video in cpu_case['videos']), 'CPU video proof mismatch')
        cpu_receipts = {item['path']: item for item in cpu_case['worker_receipts']}
        worker_path = attempt['output'] + '/worker-processes.json'
        check_fingerprint(actual(worker_path), sealed[worker_path])
        check_fingerprint(actual(worker_path), cpu_receipts[worker_path])
        workers = read(actual(worker_path))
        final = workers['events'][-1]
        require(final['event'] == 'finally_wait_complete' and final['cleanup_errors'] == []
                and final['unreaped_roles'] == [], 'Final worker cleanup differs')
        require({worker['role'] for worker in final['workers']} == set(ROLES), 'Worker roles differ')
        for worker in final['workers']:
            group = worker['process_group']
            require(worker['returncode'] == 0 and worker['status'] == 'exited'
                    and group['live_members'] == [] and group['ownership_verified'] is True
                    and group['ownership_state'] == 'retired_empty' and group['retired'] is True
                    and group['ownership_lost'] is False, 'Worker not cleanly retired')
        for role in ROLES:
            native_path = attempt['output'] + '/' + role + '-process-start.json'
            entry_path = actual(native_path)
            entry_fp = check_fingerprint(entry_path, sealed[native_path])
            check_fingerprint(entry_path, cpu_receipts[native_path])
            entry = read(entry_path)
            require(entry['role'] == role and entry['schema_version'] == 1
                    and entry['argv'][-2:] == ['--output', attempt['output']], 'Entry identity mismatch')
            process = entry['process']
            key = (attempt['output'], role, process['pid'], process['start_time_clock_ticks'])
            require(key not in row_by_key, 'Duplicate original entry')
            row = {name: case[name] for name in ('case_id', 'scenario', 'configuration_index', 'configuration')}
            row.update(role=role, native_output=key[0], native_pid=key[2], native_birth=key[3],
                       entry=entry_fp, case_evidence=evidence_fp,
                       attempt_started_unix=attempt['started_unix'], attempt_finished_unix=attempt['finished_unix'],
                       mapping_count=0, mappings=[], mapping_status='missing_historical_observation')
            rows.append(row)
            row_by_key[key] = row
    require(len(rows) == 1258, 'Original worker count differs')

    mapping_sets = collections.defaultdict(dict)
    host_process_owners, host_thread_owners = {}, {}
    init_identities, cgroup_shas = set(), set()
    segments = []
    for name, path in (('original', OLD / 'host/observer/snapshots.jsonl'),
                       ('recovery', RECOVERY / 'observer/snapshots.jsonl')):
        before = path.stat()
        digest = hashlib.sha256()
        count, offset, first_utc, last_utc = 0, 0, None, None
        with path.open('rb') as stream:
            for line_number, raw in enumerate(stream, 1):
                require(raw.endswith(b'\n'), 'Incomplete closed stream line')
                digest.update(raw)
                event = json.loads(raw)
                count += 1
                first_utc = first_utc or event['utc']
                last_utc = event['utc']
                for process in event['processes']:
                    if process['container_pid'] == 1:
                        require(process['host_pid'] == identity['host_init_pid'], 'Init hostPID differs')
                        init_identities.add((process['host_pid'], process['start_time_clock_ticks']))
                    threads = process.get('command_writer_threads', [])
                    if not threads:
                        continue
                    native_key = (process['worker_output'], process['role'], process['container_pid'],
                                  process['start_time_clock_ticks'])
                    require(native_key in row_by_key, 'Observed writer not bound to an original sealed entry')
                    hp, cp, birth = process['host_pid'], process['container_pid'], process['start_time_clock_ticks']
                    require(process['nspid'] == [hp, cp]
                            and process['status']['NSpid'] == [hp, cp]
                            and process['status']['NStgid'] == [hp, cp]
                            and int(process['status']['Pid']) == hp and int(process['status']['Tgid']) == hp,
                            'Process host/namespace identity mismatch')
                    cgroup_shas.add(process['cgroup_sha256'])
                    owner_key = (hp, birth)
                    require(host_process_owners.setdefault(owner_key, native_key) == native_key,
                            'Same host process birth claimed by different entries')
                    for thread in threads:
                        ht, ct = thread['host_tid'], thread['container_tid']
                        require(thread['host_tgid'] == hp and thread['container_tgid'] == cp
                                and thread['owner_start_time_clock_ticks'] == birth
                                and thread['nspid'] == [ht, ct] and thread['nstgid'] == [hp, cp]
                                and thread['status']['NSpid'] == [ht, ct]
                                and thread['status']['NStgid'] == [hp, cp]
                                and int(thread['status']['Pid']) == ht and int(thread['status']['Tgid']) == hp
                                and thread['status']['Name'] == 'command_writer'
                                and thread['start_time_clock_ticks'] >= birth,
                                'Thread owner/birth/namespace mismatch')
                        thread_key = (ht, thread['start_time_clock_ticks'])
                        require(host_thread_owners.setdefault(thread_key, native_key) == native_key,
                                'Same host thread birth claimed by different entries')
                        fields = ('host_tid', 'host_tgid', 'container_tid', 'container_tgid',
                                  'owner_start_time_clock_ticks', 'start_time_clock_ticks', 'nspid', 'nstgid')
                        mapped_identity = {field: thread[field] for field in fields}
                        mapped_identity.update(role=process['role'], worker_output=process['worker_output'])
                        mapping_key = json.dumps(mapped_identity, sort_keys=True)
                        records = mapping_sets[native_key]
                        if mapping_key not in records:
                            records[mapping_key] = {'identity': mapped_identity,
                                                   'first_observed_utc': event['utc'],
                                                   'last_observed_utc': event['utc'], 'segments': [name],
                                                   'first_observation': {'segment': name, 'line': line_number,
                                                                         'byte_offset': offset}}
                        else:
                            record = records[mapping_key]
                            record['last_observed_utc'] = event['utc']
                            if name not in record['segments']:
                                record['segments'].append(name)
                offset += len(raw)
        after = path.stat()
        require((before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino), 'Closed stream changed during read')
        observed = fingerprint(path)
        require(observed['bytes'] == offset and observed['sha256'] == digest.hexdigest(), 'Whole stream changed')
        segments.append({'name': name, **observed, 'whole_stream': True, 'complete_event_lines': count,
                         'first_event_utc': first_utc, 'last_event_utc': last_utc,
                         'trailing_incomplete_line_bytes': 0})
    require(len(init_identities) == 1 and len(cgroup_shas) == 1,
            'Container init birth or writer cgroup differs across streams')
    require(segments[1]['complete_event_lines'] == summary['snapshots'], 'Recovery summary count differs')
    for key, row in row_by_key.items():
        row['mappings'] = list(mapping_sets[key].values())
        row['mapping_count'] = len(row['mappings'])
        if row['mapping_count'] == 1:
            row['mapping_status'] = 'unique_observed'
        elif row['mapping_count'] > 1:
            row['mapping_status'] = 'ambiguous_observed'
    missing = [row for row in rows if row['mapping_count'] == 0]
    ambiguous = [row for row in rows if row['mapping_count'] > 1]
    require(len(missing) == 8 and {row['case_id'] for row in missing} == EXPECTED_MISSING
            and {(row['case_id'], row['role']) for row in missing}
            == {(case_id, role) for case_id in EXPECTED_MISSING for role in ROLES},
            'Missing original mapping set differs from exact four-case/eight-worker history')
    require(not ambiguous and sum(row['mapping_count'] == 1 for row in rows) == 1250,
            '1250 unique original mappings not verified')
    historical = read(proof_paths['historical_audit01_analysis'])
    require(set(historical['missing_case_ids']) == EXPECTED_MISSING, 'Historical gap changed')
    for name, proof in proofs.items():
        require(fingerprint(proof['path']) == proof, 'Proof changed during analysis: ' + name)
    write('final-original-worker-mappings.json', rows)
    mappings_fp = fingerprint(OUTPUT / 'final-original-worker-mappings.json')
    analysis = {
        'schema_version': 1, 'analysis_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'original1250_unique_exact8_historical_mapping_gaps_verified',
        'scope': 'Read-only complete closed streams and all629 original sealed worker entries; no Docker, SSH, native, GPU, tests, or video decoding. Existing independent CPU full-validation is consumed by exact SHA.',
        'completed_cases': 629, 'expected_completed_worker_entries': 1258,
        'exactly_one_writer_mapping_workers': 1250, 'missing_mapping_workers': 8,
        'missing_mapping_cases': 4, 'missing_case_ids': sorted(EXPECTED_MISSING),
        'ambiguous_mapping_workers': 0, 'identity_errors': [],
        'container_identity': identity, 'observer_source_sha256': proofs['observer_source']['sha256'],
        'container_init_identity': {'host_pid': next(iter(init_identities))[0],
                                    'start_time_clock_ticks': next(iter(init_identities))[1]},
        'unique_writer_cgroup_sha256': next(iter(cgroup_shas)),
        'unique_host_process_birth_mappings': len(host_process_owners),
        'unique_host_thread_birth_mappings': len(host_thread_owners),
        'segments': segments, 'proofs': proofs,
        'cpu_final_existing_report': {'status': cpu['status'], 'configurations': 629,
                                     'worker_exit0_empty_group_count': 1258, 'full_decoded_mp4_count': 629,
                                     'video_decoding_rerun_by_this_audit': False},
        'transaction_boundaries': {'original_session54334_exit_code': 143,
                                   'original_host_transaction_normal_exit_verified': False,
                                   'recovery_manager_actual_wait_returncode': 0,
                                   'original_native_daemon_exit_code': 0,
                                   'recovery_cpu_validation_returncode': 0,
                                   'gpu_and_cpu_owned_containers_stopped': True,
                                   'sealed_snapshot_files_before_and_after': 5206},
        'quality_verified': False, 'obstacle_course_completion_verified': False,
        'missing_workers': missing, 'worker_mapping_rows': mappings_fp,
        'historical_streams_copied': False,
        'external_history_boundary': 'Whole original/recovery snapshots.jsonl remain external raw dependencies; future chunk publication must preserve these exact whole-stream bytes/SHA. New four-case rerun births must remain separate and never fill original missing mappings.',
    }
    write('analysis.json', analysis)
    text = '''# 全629原始worker历史映射终态核对

原始629配置均已完成，每例的两份原生启动收据均与case-evidence及独立CPU最终报告的SHA一致。两份已关闭观察流逐行核对后，1258个原始worker中1250个有且仅有一个真实host command_writer映射；8个缺失，严格为high_speed_speed_vault的cfg0004–0007各simulator/inference。多义映射0，PID/出生时间、线程NSpid/NStgid、ownerbirth与hostbirth冲突0。

两段绑定同一CID/image/StartedAt/host init PID与出生时间、冻结observer源码SHA。完整流的实际字节/SHA及首末时间保存在analysis.json；原始137MB流与恢复流仍是外部历史依赖，本次没有复制或修改。将来分块出版需保持其whole-stream SHA闭合。

原session54334实际exit143、旧host running收据保持原样。恢复manager实际wait0，原native daemon0、CPU后验0，两只own容器均已停止。已有CPU报告为629配置/1258正常退出空组worker/629完整视频解码；本审计只核对报告SHA与逐例绑定，没有重新解码。

[analysis.json](analysis.json)保存全部证明文件指纹；[final-original-worker-mappings.json](final-original-worker-mappings.json)是可直接消费的1258行list。每行保留原case/role/PID/birth与entry SHA；缺项mapping_status=missing_historical_observation、mapping_count=0、mappings=[]。后续四例补验只能另存新身份，不能把新birth填回这些原始行。映射缺失表示历史观察缺口，不能据此推断策略或worker失败；执行完成亦不代表技能成功，quality_verified=false。
'''
    with (OUTPUT / 'summary.md').open('x') as stream:
        stream.write(text)
    files = [fingerprint(path) for path in sorted(OUTPUT.iterdir()) if path.is_file()]
    write('manifest.json', {'schema_version': 1, 'status': analysis['status'],
                            'files': files, 'external_dependencies': list(proofs.values()) + segments,
                            'original_worker_entry_and_case_evidence_dependencies': mappings_fp,
                            'all_original_bytes_preserved': True, 'quality_verified': False})
    print(json.dumps({'status': analysis['status'], 'rows': len(rows), 'unique': 1250, 'missing': 8,
                      'analysis': fingerprint(OUTPUT / 'analysis.json'),
                      'mappings': mappings_fp, 'manifest': fingerprint(OUTPUT / 'manifest.json')}, indent=2))


if __name__ == '__main__':
    main()
