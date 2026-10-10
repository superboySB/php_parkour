"""CPU-only tests for fresh629 external controls; never Docker/DDS/GPU."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

prep=load('prepare_fresh629');host=load('run_fresh629');gate=load('run_frozen_matrix');observer=load('observe_container_pids')

class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
    def make_gate(self,children=None):
        own=self.base/'gate.py';own.write_text('frozen')
        called=[];matrix=types.SimpleNamespace(verify_inputs=lambda p,s:called.append((p,s)),running_children=lambda:children or [])
        expected={'plan':'native'};gate.attach_gate(matrix,expected,own,gate.sha(own));return matrix,expected,own,called
    def test_gate_keeps_original_verification(self):
        matrix,plan,own,calls=self.make_gate();matrix.verify_inputs(plan,{'case':'C'});self.assertEqual(calls,[(plan,{'case':'C'})])
    def test_global_leftover_rejects_even_other_case(self):
        matrix,plan,own,calls=self.make_gate([{'pid':42,'output':'other-case'}])
        with self.assertRaisesRegex(ValueError,'Previous native child'):matrix.verify_inputs(plan,{'case':'D'})
        self.assertEqual(calls,[])
    def test_gate_rejects_native_plan_drift(self):
        matrix,plan,own,calls=self.make_gate()
        with self.assertRaisesRegex(ValueError,'plan differs'):matrix.verify_inputs({'plan':'changed'}, {})
        self.assertFalse(calls)
    def test_gate_rechecks_own_bytes_each_case(self):
        matrix,plan,own,calls=self.make_gate();matrix.verify_inputs(plan,{});own.write_text('changed')
        with self.assertRaisesRegex(ValueError,'helper changed'):matrix.verify_inputs(plan,{})
        self.assertEqual(len(calls),1)
    def test_copy_is_exact_readonly(self):
        source=self.base/'source';target=self.base/'new/x';source.write_bytes(b'original\x00bytes')
        record=prep.copy(source,target,prep.sha(source),14)
        self.assertEqual(record['sha256'],prep.sha(target));self.assertEqual(target.stat().st_mode&0o777,0o444)
    def test_copy_refuses_changed_source(self):
        source=self.base/'source';source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'SHA changed'):prep.copy(source,self.base/'new','0'*64)
    def test_copy_refuses_symlink(self):
        source=self.base/'source';source.write_text('x');link=self.base/'link';link.symlink_to(source)
        with self.assertRaises(ValueError):prep.copy(link,self.base/'new')
    def test_container_owned_evidence_is_hashed_without_chmod(self):
        cpu=self.base/'cpu';cpu.mkdir();report=cpu/'report.json';report.write_text('{}')
        with patch.object(Path,'chmod',side_effect=AssertionError('Must not chmod Docker-owned outputs')):
            records=prep.evidence_records(cpu,self.base)
        self.assertEqual(records,[{'relative':'cpu/report.json','sha256':prep.sha(report),'bytes':2}])
    def test_no_authorization_has_no_side_effect(self):
        with patch.object(host,'call',side_effect=AssertionError('Docker queried')):
            with self.assertRaisesRegex(ValueError,'start authorization'):host.execute(types.SimpleNamespace(root_authorized_start=False))
    def test_gpu_argv_keeps_private_namespaces_and_uuid(self):
        plan={'container_name':'fresh'};argv=host.create_args(self.base,plan,True)
        self.assertEqual(argv[argv.index('--gpus')+1],'device='+prep.UUID)
        self.assertEqual(argv[argv.index('--ipc')+1],'private');self.assertEqual(argv[argv.index('--network')+1],'none')
        self.assertNotIn('--pid',argv);self.assertIn('--init',argv);self.assertIn(prep.IMAGE,argv)
        self.assertTrue(any('dst=/data/cache' in x for x in argv));self.assertTrue(any('dst=/data,readonly' in x for x in argv))
    def test_cpu_argv_no_gpu_runc_ro_outputs(self):
        argv=host.create_args(self.base,{'container_name':'fresh'},False)
        self.assertNotIn('--gpus',argv);self.assertEqual(argv[argv.index('--runtime')+1],'runc')
        self.assertIn('NVIDIA_VISIBLE_DEVICES=void',argv);self.assertTrue(any('dst=/outputs,readonly' in x for x in argv))
    def make_snapshot(self):
        cpu=self.base/'host/cpu-preflight';cpu.mkdir(parents=True);(self.base/'inputs').mkdir()
        native=self.base/'inputs/native-plan.json';native.write_text('{}')
        launch=cpu/'launch.json';launch.write_text(json.dumps({'status':'passed','owned_container_running_after_stop':False,'commands':[{'returncode':0}]*3}))
        files=[{'relative':str(p.relative_to(self.base)),'sha256':prep.sha(p),'bytes':p.stat().st_size} for p in (native,launch)]
        manifest=self.base/'freeze-manifest.json';manifest.write_text(json.dumps({'files':files}))
        plan={'output':str(self.base.resolve()),'image_id':prep.IMAGE,'gpu_uuid':prep.UUID,'freeze_manifest_sha256':prep.sha(manifest),
              'native_plan_file_sha256':prep.sha(native),'cpu_preflight_receipt_sha256':prep.sha(launch)}
        plan['plan_sha256']=prep.identity(plan);return plan,launch
    def test_snapshot_passes_exact_frozen_receipts(self):
        plan,_=self.make_snapshot();self.assertEqual(host.verify_snapshot(self.base,plan),2)
    def test_snapshot_rejects_postfreeze_cpu_receipt_change(self):
        plan,launch=self.make_snapshot();launch.write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):host.verify_snapshot(self.base,plan)
    def test_snapshot_rejects_host_identity_change(self):
        plan,_=self.make_snapshot();plan['image_id']='other'
        with self.assertRaisesRegex(ValueError,'identity'):host.verify_snapshot(self.base,plan)
    def test_full_cid_cleanup_identity_gate_before_stop(self):
        with patch.object(host,'inspect',return_value={}),patch.object(host,'verify_container',side_effect=ValueError('foreign')),patch.object(host,'call') as call:
            with self.assertRaisesRegex(ValueError,'foreign'):host.stop_owned('x'*64,self.base,{},True)
            call.assert_not_called()
    def test_observer_proc_stat_with_spaces(self):
        text='20 (command writer) '+' '.join(['S','1','20','20']+['0']*15+['123','0'])
        self.assertEqual(observer.parse_stat(text)['start_time_clock_ticks'],123)
    def test_observer_esrch_thread_is_raced_exit(self):
        root=self.base/'10';task=root/'task/11';task.mkdir(parents=True)
        stat='10 (worker) '+' '.join(['S','1','10','10']+['0']*15+['123','0'])
        for path,text in [(root/'stat',stat),(root/'cgroup','0::/docker/'+'a'*64),(root/'status','Pid:\t10\nTgid:\t10\nNSpid:\t10 2\n'),(task/'stat',stat)]:path.write_text(text)
        (root/'cmdline').write_bytes(b'python\0')
        original=Path.read_text
        def read(path,*args,**kwargs):
            if path==task/'comm':raise ProcessLookupError('thread exited')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):result=observer.capture_pid(self.base,10,'a'*64)
        self.assertEqual(result['command_writer_threads'],[])
    def make_host_mapping_fixture(self):
        (self.base/'host/observer').mkdir(parents=True);(self.base/'inputs').mkdir();(self.base/'outputs').mkdir()
        cid='a'*64;write=prep.write;cases=[];selections=[];mappings=[]
        for number in range(629):
            output='/outputs/case-'+str(number);directory=self.base/'outputs'/('case-'+str(number));directory.mkdir()
            case_id='case-'+str(number);selections.append({'case_id':case_id})
            cases.append({'case_id':case_id,'attempts':[{'output':output,'returncode':0}]})
            for i,role in enumerate(('simulator','inference')):
                pid=number*2+i+100;birth=number*2+i+1000;tid=pid+10000;hostpid=pid+20000
                write(directory/(role+'-process-start.json'),{'process':{'pid':pid,'start_time_clock_ticks':birth}})
                mappings.append({'worker_output':output,'role':role,'container_tgid':pid,'owner_start_time_clock_ticks':birth,
                                 'host_tid':tid,'container_tid':pid+50000,'host_tgid':hostpid,'start_time_clock_ticks':birth+2,
                                 'nspid':[tid,pid+50000],'nstgid':[hostpid,pid]})
        write(self.base/'inputs/native-plan.json',{'selections':selections})
        write(self.base/'outputs/all-configs.tmp',{})
        (self.base/'outputs/all-configs').mkdir()
        write(self.base/'outputs/all-configs/matrix.json',{'status':'completed','completed_configurations':629,'selections':cases,'plan_sha256':'native'})
        write(self.base/'host/container-inspect.json',{'Id':cid,'State':{'StartedAt':'samebirth'}})
        summary={'mapping_scope_complete':True,'errors':[],'stop_reason':'stop_file','command_writer_mappings':mappings,
                 'identity':{'container_id':cid,'image_id':prep.IMAGE,'started_at':'samebirth'}}
        write(self.base/'host/observer/summary.json',summary);return cid,summary
    def test_all1258_exact_host_mappings(self):
        cid,_=self.make_host_mapping_fixture()
        self.assertEqual(len(host.host_mappings(self.base,{'native_plan_sha256':'native'},cid)),1258)
    def test_duplicate_writer_mapping_is_rejected(self):
        cid,summary=self.make_host_mapping_fixture();summary['command_writer_mappings'].append(summary['command_writer_mappings'][0])
        prep.write(self.base/'host/observer/summary.json',summary)
        with self.assertRaisesRegex(ValueError,'one exact host writer'):host.host_mappings(self.base,{'native_plan_sha256':'native'},cid)

if __name__=='__main__':unittest.main(verbosity=2)
