"""CPU-only fixed12 baseline/authorization/isolation regression tests."""
import copy,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import commands_executor as executor
import sdk018_commands as host

class Commands(unittest.TestCase):
    def make_plan(self):
        cases=[]
        for code in range(12):
            launch=['python','sim2sim.py','--models','/data/assets/student','--terrain','plane','--commands',str(code),
                    '--seconds-per-command','8.0','--settle-seconds','3.0','--startup-timeout','180.0','--seed','42',
                    '--gl','egl','--ort-threads','1','--python-faulthandler','--output',f'/outputs/commands/command-{code:02d}']
            cases.append({'case_id':f'command-{code:02d}','command':code,'mesh':None,'mesh_sha256':None,'source_files':[],
                          'output':f'/outputs/commands/command-{code:02d}','launch':launch,'expected_config':{'wall_timeout':373.0}})
        plan={'schema_version':3,'pilot_scope':'SDK018 canonical12 original plane commands; each once','seconds_per_configuration':8.0,
              'seed':42,'python_faulthandler':True,'control_files':[],'selections':cases}
        return self.seal(plan)
    def seal(self,plan):
        plan.pop('plan_sha256',None);plan['plan_sha256']=host.identity(plan);return plan
    def check(self,plan):
        seen=[];matrix=types.SimpleNamespace(identity=host.identity,verify_inputs=lambda p,c:seen.append(c['command']))
        executor.verify_plan(plan,matrix);return seen
    def test_all12_original_commands_verified(self):self.assertEqual(self.check(self.make_plan()),list(range(12)))
    def test_changed_plan_identity_rejected(self):
        plan=self.make_plan();plan['seed']=3
        with self.assertRaisesRegex(ValueError,'identity'):self.check(plan)
    def test_ordered_command_identity_rejected(self):
        plan=self.make_plan();plan['selections'][0]['command']=11;self.seal(plan)
        with self.assertRaisesRegex(ValueError,'exact original12'):self.check(plan)
    def test_original_seed_duration_diagnostic_required(self):
        for field,value in [('seed',7),('seconds_per_configuration',10),('python_faulthandler',False)]:
            with self.subTest(field=field):
                plan=self.make_plan();plan[field]=value;self.seal(plan)
                with self.assertRaises(ValueError):self.check(plan)
    def test_no_implicit_native_overrides(self):
        for flag,value in [('--commands','6'),('--seconds-per-command','10.0'),('--seed','1'),('--terrain','custom'),('--startup-timeout','90'),('--settle-seconds','4'),('--ort-threads','2')]:
            with self.subTest(flag=flag):
                plan=self.make_plan();argv=plan['selections'][0]['launch'];argv[argv.index(flag)+1]=value;self.seal(plan)
                with self.assertRaisesRegex(ValueError,'differs'):self.check(plan)
    def test_wall_override_rejected(self):
        plan=self.make_plan();plan['selections'][0]['launch']+=['--wall-timeout','120'];self.seal(plan)
        with self.assertRaisesRegex(ValueError,'differs'):self.check(plan)
    def test_diagnostics_flag_required(self):
        plan=self.make_plan();plan['selections'][0]['launch'].remove('--python-faulthandler');self.seal(plan)
        with self.assertRaisesRegex(ValueError,'differs'):self.check(plan)
    def test_percase_outputs_fresh_unique(self):
        plan=self.make_plan();plan['selections'][1]['output']=plan['selections'][0]['output'];self.seal(plan)
        with self.assertRaisesRegex(ValueError,'differs'):self.check(plan)
    def test_control_source_checked_each_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'control';source.write_text('before');plan=self.make_plan()
            plan['control_files']=[{'path':str(source),'sha256':executor.sha(source)}];self.seal(plan);self.check(plan)
            source.write_text('after')
            with self.assertRaisesRegex(ValueError,'control changed'):self.check(plan)
    def test_authorization_before_any_side_effect(self):
        with patch.object(host,'run',side_effect=AssertionError('Docker called')):
            with self.assertRaisesRegex(ValueError,'authorization'):host.execute(types.SimpleNamespace(root_authorized_start=False))
    def test_isolated_single_uuid_container_argv(self):
        plan={'container_name':'fresh','gpu_uuid':'GPU-fixed','mounts':[],'image_id':host.IMAGE}
        argv=host.container_arguments(plan)
        self.assertEqual(argv[argv.index('--gpus')+1],'device=GPU-fixed');self.assertEqual(argv[argv.index('--ipc')+1],'private')
        self.assertEqual(argv[argv.index('--network')+1],'none');self.assertNotIn('--pid',argv);self.assertIn('--init',argv)
    def test_exact_same_released_model_hashes(self):
        self.assertEqual(host.MODELS,{'depth_backbone.onnx':'5b22466a218944e3b0ab0f4f82a910e3eec35375ee03e7fb94eb65fa88431b56','student.onnx':'e426c4206181d511b838c76efc48e43636299b76cb5a15183977011589931628'})

if __name__=='__main__':unittest.main(verbosity=2)
