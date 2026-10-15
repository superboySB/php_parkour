"""Ordinary CPU controls; no native/Docker/GPU or future scientific receipt."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import types
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_actual_crossboot_parent', HERE / 'native58_resource_wait_control.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class ControlTests(unittest.TestCase):
    def test_real_current_process_birth(self):
        row = C.process(Path('/proc/self/stat').read_text())
        self.assertEqual(row['pid'], os.getpid())
        self.assertGreater(row['start_time_clock_ticks'], 0)

    def test_real_outer_self_stat_and_direct_parent_identity(self):
        # Reuse actual readable ordinary process stat fields; no child starts.
        raw = Path('/proc/self/stat').read_text()
        current = C.process(raw)
        parent_raw = Path('/proc', str(current['ppid']), 'stat').read_text()
        parent = C.process(parent_raw)
        outer = {'wrapper_process': {**parent, 'stat': parent_raw}, 'launcher_process': {**current, 'stat': raw}}
        C.verify_outer_birth(outer, current)
        wrong_owner = {**current, 'ppid': current['ppid'] + 1}
        with self.assertRaisesRegex(ValueError, 'direct child'):
            C.verify_outer_birth(outer, wrong_owner)
        changed = copy.deepcopy(outer)
        changed['wrapper_process']['start_time_clock_ticks'] += 1
        with self.assertRaisesRegex(ValueError, 'structured birth'):
            C.verify_outer_birth(changed, current)

    def response(self):
        cid = 'a' * 64
        body = json.dumps({'message': 'No such container: ' + cid}).encode()
        return cid, {'method': 'GET', 'route': '/containers/' + cid + '/json', 'http_status': 404,
                     'body_hex': body.hex(), 'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
                     'json': json.loads(body)}

    def test_recorded_actual_api_bytes_and_route(self):
        cid, row = self.response()
        self.assertEqual(C.recorded_api(row, '/containers/' + cid + '/json'), row['json'])

    def test_recorded_body_changed_rejected(self):
        cid, row = self.response()
        row['body_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fingerprint/route'):
            C.recorded_api(row, '/containers/' + cid + '/json')

    def test_wrong_route_rejected(self):
        _, row = self.response()
        with self.assertRaises(ValueError):
            C.recorded_api(row, '/containers/' + 'b' * 64 + '/json')

    def test_json_duplicate_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                C.parse(raw)

    def test_exact_outer_raw_log_fingerprints(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary)
            for name in ('launcher.stdout.raw', 'launcher.stderr.raw'):
                (root / name).write_text('ordinary CPU fixture only\n')
            outer = {'launcher_logs': [C.fp(root / name) for name in ('launcher.stdout.raw', 'launcher.stderr.raw')]}
            C.verify_outer_logs(outer, root, C.fp)
            outer['launcher_logs'] = []
            with self.assertRaisesRegex(ValueError, 'exactly both'):
                C.verify_outer_logs(outer, root, C.fp)

    def test_wrong_outer_log_path_and_false_source_declaration_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary)
            for name in ('launcher.stdout.raw', 'launcher.stderr.raw', 'other.raw'):
                (root / name).write_text('ordinary CPU fixture only\n')
            outer = {'launcher_logs': [C.fp(root / 'other.raw'), C.fp(root / 'launcher.stderr.raw')]}
            with self.assertRaises(ValueError):
                C.verify_outer_logs(outer, root, C.fp)
            outer = {'launcher_logs': [C.fp(root / name) for name in ('launcher.stdout.raw', 'launcher.stderr.raw')], 'sources_unchanged': False}
            with self.assertRaisesRegex(ValueError, 'unchanged'):
                C.verify_outer_logs(outer, root, C.fp)

    def test_copied_verifier_returns_same_canonical_identity(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            path = Path(temporary) / 'copied_control.py'
            shutil.copyfile(HERE / 'native58_resource_wait_control.py', path)
            spec = importlib.util.spec_from_file_location('copied_actual_parent_cpu_control', path)
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            seen = []
            def keep(path):
                row = C.fp(path); seen.append(row); return row
            self.assertEqual(loaded.canonical_verifier(keep), C.canonical_verifier(C.fp))
            self.assertIn(str(path), [x['path'] for x in seen])
            path.write_text(path.read_text() + '\n# changed CPU fixture copy\n')
            with self.assertRaisesRegex(ValueError, 'copied verifier differs'):
                loaded.canonical_verifier(C.fp)

    def test_running_actual_chain_refuses_without_future_wait_or_output(self):
        # This is a real read-only negative observation of the existing chain;
        # if it has ended by the time controls are rerun, use an empty fresh
        # CPU fixture path. Neither branch can produce an acceptance report.
        actual = HERE / 'student-native58-resource-wait-host-04/original-parent/process-exit.json'
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            missing = Path(temporary) / 'original-parent/process-exit.json'
            target = missing if actual.exists() else actual
            with patch('subprocess.Popen', side_effect=AssertionError('No process allowed')), patch('subprocess.run', side_effect=AssertionError('No process allowed')):
                with self.assertRaises(FileNotFoundError):
                    C.verify_actual_parent(HERE, target, '0' * 64)

    def test_explicit_exit_sha_refuses_before_contract_import(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root = Path(temporary) / 'original-parent'; root.mkdir()
            path = root / 'process-exit.json'; path.write_text('{"scope":"synthetic ordinary CPU fixture"}')
            with patch.object(C.importlib.util, 'spec_from_file_location', side_effect=AssertionError('No gate import allowed')):
                with self.assertRaisesRegex(ValueError, 'exit SHA differs'):
                    C.verify_actual_parent(HERE, path, '0' * 64)

    def test_original_science_and_complete_decoder_ast_unchanged(self):
        old = (HERE / 'review_native58.py').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), 'cb3039b3074611025972f762c1c4fc538555fd5fe7a003f23ed4604c34cbf278')
        def verify_body(path):
            module = ast.parse(path.read_text())
            return next(x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == 'verify').body
        original = verify_body(HERE / 'review_native58.py')
        new = verify_body(HERE / 'review_native58_resource_wait.py')
        def assigned(node, name):
            return isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == name for x in node.targets)
        def section(body, start, end):
            a = next(i for i, x in enumerate(body) if start(x))
            b = next(i for i, x in enumerate(body[a:], a) if end(x))
            return ast.dump(ast.Module(body=body[a:b], type_ignores=[]), include_attributes=False)
        # This entire block contains all case/model/pose/worker/map/trajectory
        # checks and every fresh full58 CPU decode including decoder isolation.
        self.assertEqual(section(original, lambda x: assigned(x, 'terminal'), lambda x: assigned(x, 'report')),
                         section(new, lambda x: assigned(x, 'terminal'), lambda x: assigned(x, 'report')))
        self.assertEqual(section(original, lambda x: isinstance(x, ast.FunctionDef) and x.name == 'cpu_inspect', lambda x: assigned(x, 'waited')),
                         section(new, lambda x: isinstance(x, ast.FunctionDef) and x.name == 'cpu_inspect', lambda x: assigned(x, 'parent_module_path')))
        old_report = copy.deepcopy(next(x for x in original if assigned(x, 'report')))
        new_report = copy.deepcopy(next(x for x in new if assigned(x, 'report')))
        for index in reversed(range(len(new_report.value.keys))):
            if isinstance(new_report.value.keys[index], ast.Constant) and new_report.value.keys[index].value in ('host_control', 'control_revision'):
                del new_report.value.keys[index]; del new_report.value.values[index]
        self.assertEqual(ast.dump(old_report, include_attributes=False), ast.dump(new_report, include_attributes=False))


class ResourceReceiptTests(unittest.TestCase):
    """Offline synthetic raw receipts test validators; no query process starts."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = HERE.parent / 'final-student-native58-resource-wait-02'
        self.owner = C.process(Path('/proc/self/stat').read_text())
        self.mutex = {'owner_pid': self.owner['ppid'], 'scope': 'synthetic offline CPU receipt'}
        self.data = {'resource_wait_seconds': 1800, 'resource_poll_seconds': 5}
        self.plan = {'host_total_timeout_seconds': 43200}
        self.queries, self.calls = [], []
        for call_index in range(9):
            rounds = []
            states = ['busy', 'idle'] if call_index == 0 else ['idle']
            for round_index, state in enumerate(states):
                queries = []
                for query_index, argv in enumerate([
                    ['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'],
                    ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits']]):
                    index = len(self.queries)
                    stdout, stderr = self.root/f'{index:05d}.stdout.raw', self.root/f'{index:05d}.stderr.raw'
                    stdout.write_text(('GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25\n' if query_index == 0 else
                        'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25, 123456789\n' if state == 'busy' else ''))
                    stderr.write_bytes(b'')
                    row = {'index':index,'argv':argv,'child_created':True,'pid':self.owner['pid'],
                        'actual_wait_returncode':0,'timed_out':False,'actual_query_timeout_seconds':30,
                        'requested_original_call_timeout_seconds':60,'started_monotonic':call_index*10+round_index,
                        'finished_monotonic':call_index*10+round_index+.1,'mutex':self.mutex,
                        'stat':Path('/proc/self/stat').read_text(),'stdout':C.fp(stdout),'stderr':C.fp(stderr),
                        'scope':'Synthetic CPU validation data; not an actual query Popen or science receipt.'}
                    self.queries.append(row);queries.append(row);self.save(row)
                rounds.append({'status':'exact_original_gpu_'+state,'queries':queries,
                               'observed_monotonic':call_index*10+round_index+.2})
            self.calls.append({'index':call_index,'status':'idle','budget_seconds':1800,
                'original_overall_limit_seconds':43200,'started_monotonic':call_index*10,
                'finished_monotonic':call_index*10+2,'actual_wall_seconds':2.0001,'rounds':rounds})
        nodes=C.original_gpu_nodes(self.base,self.keep)
        self.control={'gpu_queries':self.queries,'resource_wait_calls':self.calls,
            'original_execute_started_monotonic':0,
            'overall_guard_start_scope':'Conservative actual host monotonic immediately before original execute, earlier than its local deadline',
            'original_gpu_guard_ast_sha256':hashlib.sha256(ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False).encode()).hexdigest(),
            'resource_policy':{'per_gpu_idle_call_budget_seconds':1800,'max_contract_budget_seconds':3600,
                'query_timeout_seconds_max':30,'overall_original_wall_seconds':43200,
                'waiting_counts_against_original_wall':True,'original_plan_and_worker_timers_unchanged':True}}

    def keep(self,path,expected=None):
        row=C.fp(path)
        if expected is not None:self.assertEqual(row,expected)
        return row

    def read(self,path,expected=None):
        self.keep(path,expected);return C.parse(Path(path).read_bytes())

    def save(self,row):
        (self.root/f"{row['index']:05d}.json").write_text(json.dumps(row))

    def verify(self):
        return C.verify_resource_queries(self.control,self.data,self.plan,self.base,self.keep,self.read,
                                        lambda row:self.assertEqual(row,self.mutex))

    def test_offline_original_AST_busy_then_idle_and_all9_calls(self):
        queries, used=self.verify();self.assertEqual(len(queries),20);self.assertEqual(used,set(range(20)))

    def test_recorded_bool_wait_is_rejected(self):
        self.queries[0]['actual_wait_returncode']=False;self.save(self.queries[0])
        with self.assertRaises(ValueError):self.verify()

    def test_modified_guard_AST_digest_is_rejected(self):
        self.control['original_gpu_guard_ast_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'guard AST'):self.verify()

    def test_busy_raw_bytes_cannot_claim_idle(self):
        self.calls[0]['rounds'][0]['status']='exact_original_gpu_idle'
        with self.assertRaises(ValueError):self.verify()

    def test_query_inventory_JSON_mismatch_is_rejected(self):
        row=self.queries[0];path=self.root/f"{row['index']:05d}.json";path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'per-query JSON'):self.verify()

    def test_query_reuse_in_a_different_round_is_rejected(self):
        self.calls[1]['rounds'][0]['queries']=self.calls[0]['rounds'][1]['queries']
        with self.assertRaisesRegex(ValueError,'reused'):self.verify()

    def test_8_or_10_native_calls_do_not_admit_complete58(self):
        for calls in [self.calls[:8],self.calls+[self.calls[0]]]:
            self.control['resource_wait_calls']=calls
            with self.assertRaisesRegex(ValueError,'four pairs'):self.verify()

    def test_original_budget_or_plan_wall_change_is_rejected(self):
        self.plan['host_total_timeout_seconds']=43201
        with self.assertRaises(ValueError):self.verify()

    def test_round_after_original_call_deadline_is_rejected(self):
        self.calls[0]['rounds'][-1]['observed_monotonic']=1801
        with self.assertRaisesRegex(ValueError,'round time'):self.verify()


class PreviousReleaseTests(unittest.TestCase):
    """Actual archived failed41 inputs plus synthetic offline API observations."""
    def setUp(self):
        self.review_path=HERE/'native58-failed41-independent-audit-02/review.json'
        self.review=C.parse(self.review_path.read_bytes());self.review_fp=C.fp(self.review_path)
        self.data={'failed41_review':self.review_fp,'current_boot_id':'8784ea50-b638-4b41-a7e4-4bdb833c27ef'}
        self.gate=types.SimpleNamespace(FAILED_REVIEW_SHA=self.review_fp['sha256'],
            typed_absent=lambda response,cid:response['http_status']==404 and response['json']=={'message':'No such container: '+cid})
        root=HERE/'student-native58-crossboot-host-01'
        parent=C.parse((root/'original-parent/process-exit.json').read_bytes())
        outer=C.parse((root/'wrapper-exit.json').read_bytes());birth=C.process(parent['stat'])
        owners=[outer['wrapper_process'],outer['launcher_process'],
            {'pid':parent['pid'],'sid':birth['sid'],'start_time_clock_ticks':birth['start_time_clock_ticks']}]
        containers=[]
        for old in self.review['stopped_gpu_containers']:
            cid=old['container_id'];archived=C.parse(Path(old['execution']['stdout']['path']).read_bytes())[0]
            first=self.response(cid,archived);final=self.response(cid,{**archived,'Mounts':list(reversed(archived['Mounts']))})
            containers.append({'container_id':cid,'historical_inspect':old['execution']['stdout'],
                'current_status':'current_stopped143_full_identity_verified','actual_current_request':first,
                'actual_current_recheck':final})
        self.release={'status':'preserved_failed41_current_resources_released','failed41_review':self.review_fp,
            'current_boot_id':self.data['current_boot_id'],'original_parent_wait_returncode':1,'original_completed_cases':41,
            'current_owned_session_members':[],'is_complete58_admission':False,'evidence':self.review['evidence_fingerprints'],
            'containers':containers,'current_pid_checks':[{'historical_identity':owner,'current_status':'absent_same_boot'} for owner in owners]}

    def response(self,cid,value,status=200):
        raw=json.dumps(value).encode()
        return {'method':'GET','route':'/containers/'+cid+'/json','http_status':status,'body_hex':raw.hex(),
            'body_bytes':len(raw),'body_sha256':hashlib.sha256(raw).hexdigest(),'json':copy.deepcopy(value),
            'scope':'Synthetic offline CPU API fixture; not a real Docker GET.'}

    def keep(self,path,expected=None):
        # Existing historical SHA proof itself was independently checked by
        # failed41 actual audit. This test isolates offline semantic matching.
        return expected if expected is not None else C.fp(path)

    def read(self,path,expected=None):
        return C.parse(Path(path).read_bytes())

    def verify(self):
        with patch.object(C,'empty_session',return_value=[]):
            return C.verify_failed41_release(self.release,self.data,self.gate,self.keep,self.read)

    def test_complete_mount_rows_reordered_are_equivalent(self):
        self.assertTrue(self.verify()['never_complete58_evidence'])

    def test_changed_mount_row_is_rejected(self):
        row=self.release['containers'][0];value=copy.deepcopy(row['actual_current_recheck']['json'])
        value['Mounts'][0]['RW']=not value['Mounts'][0]['RW']
        row['actual_current_recheck']=self.response(row['container_id'],value)
        with self.assertRaisesRegex(ValueError,'current identity'):self.verify()

    def test_changed_state_is_rejected(self):
        row=self.release['containers'][0];value=copy.deepcopy(row['actual_current_recheck']['json'])
        value['State']['Running']=True;row['actual_current_recheck']=self.response(row['container_id'],value)
        with self.assertRaisesRegex(ValueError,'current identity'):self.verify()

    def test_typed404_cannot_turn_into200_during_recheck(self):
        row=self.release['containers'][0];row['current_status']='current_absent_typed_404'
        row['actual_current_request']=self.response(row['container_id'],{'message':'No such container: '+row['container_id']},404)
        with self.assertRaisesRegex(ValueError,'typed404'):self.verify()

    def test_changed_previous_owner_or_wait1_is_rejected(self):
        self.release['current_pid_checks'][0]['historical_identity']=copy.deepcopy(self.release['current_pid_checks'][0]['historical_identity'])
        self.release['current_pid_checks'][0]['historical_identity']['pid']+=1
        with self.assertRaisesRegex(ValueError,'exact real previous owners'):self.verify()


class ReadonlyJournalTests(unittest.TestCase):
    """Offline synthetic API/CLI journal controls; no service or process call."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=HERE);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.directory=self.root/'readonly-observations';self.directory.mkdir()
        body=b'{"ID":"synthetic_CPU_only_not_real_Docker"}'
        api={'method':'GET','route':'/info','http_status':200,'headers':[['Content-Type','application/json']],
             'body_hex':body.hex(),'body_bytes':len(body),'body_sha256':hashlib.sha256(body).hexdigest()}
        records=[]
        body_path=self.directory/'00000.docker_api.body.raw';body_path.write_bytes(body)
        record={'index':0,'kind':'docker_api','observation':api,
            'scope':'actual_readonly_control_observation_not_scientific_completion','body':C.fp(body_path)}
        path=self.directory/'00000.docker_api.json';path.write_text(json.dumps(record));records.append(C.fp(path))
        stdout,stderr=self.directory/'00001.docker_cli.stdout.raw',self.directory/'00001.docker_cli.stderr.raw'
        stdout.write_bytes(b'default\n');stderr.write_bytes(b'')
        cli={'argv':['docker','context','show'],'actual_wait_returncode':0,'stdout_hex':stdout.read_bytes().hex(),'stderr_hex':''}
        record={'index':1,'kind':'docker_cli','observation':cli,
            'scope':'actual_readonly_control_observation_not_scientific_completion','stdout':C.fp(stdout),'stderr':C.fp(stderr)}
        path=self.directory/'00001.docker_cli.json';path.write_text(json.dumps(record));records.append(C.fp(path))
        self.control={'readonly_diagnostic_records':records,'api_proof':{**api,'json':json.loads(body)},'cli_proof':cli,
            'fixture_scope':'Synthetic offline CPU journal only; not a real HTTP/Docker/CLI execution.'}

    def keep(self,path,expected=None):
        actual=C.fp(path)
        if expected is not None:self.assertEqual(actual,expected)
        return actual

    def read(self,path,expected=None):
        self.keep(path,expected);return C.parse(Path(path).read_bytes())

    def verify(self):return C.verify_readonly_diagnostics(self.control,self.root,self.keep,self.read)

    def test_complete_raw_API_CLI_journal_and_proofs_are_bound(self):
        self.assertEqual(self.verify()['record_count'],2)

    def test_unjournalled_control_API_proof_is_rejected(self):
        self.control['api_proof']['body_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'absent from actual raw'):self.verify()

    def test_extra_unbound_raw_file_is_rejected(self):
        (self.directory/'orphan.raw').write_bytes(b'synthetic CPU orphan')
        with self.assertRaisesRegex(ValueError,'file set'):self.verify()

    def test_failed_or_partial_diagnostic_cannot_admit_complete_run(self):
        path=self.directory/'00000.docker_api.json';row=json.loads(path.read_text());row['kind']='docker_api_error'
        path.write_text(json.dumps(row));self.control['readonly_diagnostic_records'][0]=C.fp(path)
        with self.assertRaisesRegex(ValueError,'failed or unexpected'):self.verify()


if __name__ == '__main__':
    unittest.main(verbosity=2)
