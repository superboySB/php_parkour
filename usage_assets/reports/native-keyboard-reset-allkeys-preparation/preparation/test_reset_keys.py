"""CPU fixtures for only the new GUI protocol. No display/robot/SDK construction."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import common
import container_runner as runner
import host_runner as host
import observe_native as observer
from reset_checks import LOW, HIGH, onehot_matches, validate_reset, validate_state, validate_shutdown


def physical(time=4., pose=2.):
    return {'time': time, 'qpos': [pose] + [0.]*35, 'qvel': [0.]*35,
            'ctrl': [0.]*29, 'model_qpos0': [0.]*36, 'nq': 36, 'nv': 35, 'nu': 29, 'nkey': 0,
            'physics_dt': .002, 'gantry_enabled': False, 'gantry_length': .6,
            'camera_tracking': True, 'show_text_overlay': True}


def policy(code):
    return {'active_velocity_command_idx': code, 'velocity_command': [[float(i == code) for i in range(15)]]}


def fake_modules(leaves):
    modules = {}
    for name, attrs in leaves.items():
        for i in range(1, len(name.split('.'))+1):
            prefix = '.'.join(name.split('.')[:i])
            modules.setdefault(prefix, types.ModuleType(prefix)); modules[prefix].__path__ = []
        modules[name].__dict__.update(attrs)
    return modules


class ResetContractTests(unittest.TestCase):
    def test_native_main_then_atexit_required_without_duplicates_or_raised(self):
        events=[{'kind':'original_main_returned'},{'kind':'python_atexit'}]
        self.assertEqual(validate_shutdown(events)['python_atexit_index'],1)
        for bad in (events[:1],events[::-1],events+events,[{'kind':'original_main_raised'}]+events):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_shutdown(bad)

    def observation(self, scope='within_original_render'):
        return {'scope': scope, 'unix': 11., 'before': physical(), 'after': physical(0., 0.),
                'physics_ticks': 2500, 'render_index': 80}

    def test_actual_clock_and_qpos_change_are_required(self):
        item = self.observation(); result = validate_reset(item, 10., 0, 1)
        self.assertEqual(result['actual_clock_drop'], 4.)
        self.assertEqual(result['qpos_max_abs_change'], 2.)
        self.assertEqual(result['qpos0_max_abs_error'], 0.)

    def test_between_samples_is_explicitly_distinguished(self):
        item = self.observation('between_render_samples'); item['after']['time'] = .016
        self.assertEqual(validate_reset(item, 10., 2, 3)['observation_scope'], 'between_render_samples')

    def test_key_request_without_clock_reset_is_rejected(self):
        item = self.observation(); item['after']['time'] = 4.002
        with self.assertRaises(ValueError): validate_reset(item, 10., 0, 1)

    def test_clock_only_without_qpos_change_is_rejected(self):
        item = self.observation(); item['after']['qpos'] = item['before']['qpos'][:]
        with self.assertRaises(ValueError): validate_reset(item, 10., 0, 1)

    def test_old_or_multiple_or_late_reset_is_rejected(self):
        for request, before_count, after_count, after_time in [(12.,0,1,0.), (10.,0,2,0.), (10.,0,1,.2)]:
            item = self.observation(); item['after']['time'] = after_time
            with self.subTest(request=request, count=after_count), self.assertRaises(ValueError):
                validate_reset(item, request, before_count, after_count)

    def test_nonfinite_or_incomplete_state_is_rejected(self):
        for field, value in [('qpos',[0.]*35), ('qvel',[float('nan')]*35), ('time',float('inf'))]:
            state = physical(); state[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_state(state)

    def test_model_changed_during_reset_is_rejected(self):
        item = self.observation(); item['after']['model_qpos0'][0] = .3
        with self.assertRaises(ValueError): validate_reset(item, 10., 0, 1)

    def test_all_actual_low_high_codes_not_reserved(self):
        self.assertEqual(LOW, {'w':1,'s':11,'a':2,'d':4,'q':3,'e':5})
        self.assertEqual(HIGH, {'w':6,'s':11,'a':7,'d':9,'q':8,'e':10})
        self.assertEqual(set(LOW.values()) | set(HIGH.values()) | {0}, set(range(12)))

    def test_onehot_must_match_active_index(self):
        self.assertTrue(onehot_matches(policy(11),11)); wrong = policy(11)
        wrong['velocity_command'][0][12] = 1.
        self.assertFalse(onehot_matches(wrong,11))


class NewObserverTests(unittest.TestCase):
    def setUp(self): observer.REPORT.clear()

    def test_label_counter_observes_native_buffer_without_mutating_it(self):
        value = policy(5)['velocity_command']; before = copy.deepcopy(value)
        for _ in range(10): observer.record_control_label(value, 5)
        self.assertEqual(observer.REPORT['velocity_command_tick_counts']['5'], 10)
        self.assertEqual(value, before)

    def test_label_counter_rejects_mismatch_multihot_and_reserved_shape(self):
        for value, idx in [(policy(1)['velocity_command'],2), ([[1.]*15],0), ([[1.]+[0.]*13],0)]:
            with self.subTest(idx=idx), self.assertRaises(ValueError): observer.record_control_label(value,idx)

    def test_render_observer_calls_original_once_preserves_args_rng_and_native_state(self):
        import numpy as np
        calls = []
        class Sim:
            def render(self, *args, **kwargs):
                calls.append((args,kwargs)); self.root_data.time = 0.; self.root_data.qpos[:] = 0.; return 'original-result'
            def _key_callback(self, key): calls.append(('key',key)); return 4
            def simulate_at_each_physics_step(self): self.root_data.time += .002; return 5
        class Direct:
            def initialize(self): return 6
        value = Sim()
        value.root_data = types.SimpleNamespace(time=4., qpos=np.full(36,2.), qvel=np.zeros(35), ctrl=np.ones(29))
        value.root_model = types.SimpleNamespace(qpos0=np.zeros(36), nq=36,nv=35,nu=29,nkey=0,opt=types.SimpleNamespace(timestep=.002))
        value.virtual_gantry = types.SimpleNamespace(enabled=False,length=.6)
        value.simulator_config = types.SimpleNamespace(viewer=types.SimpleNamespace(enable_tracking=True))
        value.show_text_overlay = True
        modules = fake_modules({'holosoma.simulator.mujoco.mujoco':{'MuJoCo':Sim},'holosoma.utils.sim_utils':{'DirectSimulation':Direct}})
        rng, np_rng = random.getstate(), copy.deepcopy(np.random.get_state())
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules,modules):
            observer.OUT = Path(tmp); observer.install_simulator()
            self.assertEqual(value.render(False, fixture='argument'), 'original-result')
            self.assertEqual(calls, [((False,),{'fixture':'argument'})])
            np.testing.assert_array_equal(value.root_data.qpos,np.zeros(36))
            np.testing.assert_array_equal(value.root_data.ctrl,np.ones(29))
            self.assertEqual(observer.REPORT['render_calls'],1)
            self.assertEqual(observer.REPORT['physics_clock_drop_observations'][0]['scope'],'within_original_render')
            self.assertEqual(value._key_callback(259),4)
            self.assertEqual(calls[-1],('key',259))
            self.assertEqual(value.simulate_at_each_physics_step(),5)
            self.assertEqual(value.root_data.time,.002)
        self.assertEqual(random.getstate(),rng)
        current = np.random.get_state(); self.assertEqual(current[0],np_rng[0]); np.testing.assert_array_equal(current[1],np_rng[1]); self.assertEqual(current[2:],np_rng[2:])

    def test_between_render_samples_clock_drop_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            observer.OUT = Path(tmp)
            observer.record_render(physical(3.),physical(3.))
            observer.record_render(physical(.016,0.),physical(.016,0.))
            item = observer.REPORT['physics_clock_drop_observations'][0]
            self.assertEqual(item['scope'],'between_render_samples')
            self.assertEqual(item['before']['time'],3.)


class ProtocolControlTests(unittest.TestCase):
    def session(self, tmp, table=LOW):
        session = runner.Session.__new__(runner.Session); session.output=Path(tmp)
        (session.output/'inference').mkdir(); (session.output/'inference/observations.jsonl').write_text('')
        state={'policy':policy(0),'velocity_command_tick_counts':{str(i):0 for i in range(15)}}
        actions=[]; session.state=lambda role:state; session.guard_display=lambda:None
        session.focus_terminal=lambda:actions.append('focus'); session.terminal_xid=7;session.allowed={7}
        session.record=lambda kind,**values:actions.append((kind,values))
        def key(xid,name,pressed,allowed):
            actions.append(('XTEST',name,pressed)); state['policy']=policy(table[name] if pressed else 0)
        session.display=types.SimpleNamespace(key=key)
        def wait(predicate, description, *args, **kwargs):
            if not predicate():
                idx=state['policy']['active_velocity_command_idx'];state['velocity_command_tick_counts'][str(idx)]+=10
            if not predicate(): raise RuntimeError('fixture predicate did not acknowledge: '+description)
        session.wait=wait
        def tap(name):
            self.assertEqual(name,'z'); before=copy.deepcopy(state['policy']);state['policy']=policy(0)
            with (session.output/'inference/observations.jsonl').open('a') as stream:
                import time
                stream.write(json.dumps({'kind':'native_dispatch','unix':time.time(),'command':'ZERO_VELOCITY',
                    'before':before,'after':policy(0)})+'\n')
            actions.append(('PTY',name))
        session.tap=tap
        return session,state,actions

    def test_all_direction_holds_wait_ten_labels_and_release(self):
        for table in (LOW,HIGH):
            for name,code in table.items():
                with tempfile.TemporaryDirectory() as tmp:
                    session,state,actions=self.session(tmp,table);session.hold_direction(name,code)
                    self.assertEqual(state['velocity_command_tick_counts'][str(code)],10)
                    self.assertIn(('XTEST',name,False),actions)
                    self.assertTrue(onehot_matches(state['policy'],0))

    def test_zero_is_tested_while_nonzero_key_is_still_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            session,state,actions=self.session(tmp);session.hold_direction('w',1,reset_with_z=True)
            self.assertLess(actions.index(('PTY','z')),actions.index(('XTEST','w',False)))
            self.assertGreaterEqual(state['velocity_command_tick_counts']['0'],10)

    def test_direction_is_released_even_when_native_ack_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            session,state,actions=self.session(tmp);session.wait=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('ack'))
            with self.assertRaises(RuntimeError):session.hold_direction('q',3)
            self.assertIn(('XTEST','q',False),actions)

    def test_no_operator_authorization_starts_no_docker(self):
        with patch.object(host,'command') as command, self.assertRaises(ValueError):
            host.run(types.SimpleNamespace(root_authorized_start=False))
        command.assert_not_called()

    def test_viewer7_y_g_restore_via_keys_only(self):
        session=runner.Session.__new__(runner.Session);state={'simulation':physical()};actions=[]
        session.state=lambda role:state;session.native_xid=99;session.capture=lambda label:actions.append(('capture',label))
        def tap(key,xid):
            self.assertEqual(xid,99);actions.append(key);s=state['simulation']
            if key in ('7','8'):s['gantry_length']+= -.1 if key=='7' else .1
            else:
                name='camera_tracking' if key=='y' else 'show_text_overlay';s[name]=not s[name]
        session.tap=tap;session.wait=lambda predicate,*args:self.assertTrue(predicate())
        session.viewer_controls()
        self.assertEqual([a for a in actions if isinstance(a,str)],['7','8','y','y','g','g'])
        self.assertTrue(state['simulation']['camera_tracking']);self.assertTrue(state['simulation']['show_text_overlay'])


class PriorCohortTests(unittest.TestCase):
    def fixtures(self, root):
        (root/'host/final-validation').mkdir(parents=True)
        plan={'plan_sha256':host.PREVIOUS_PLAN_SHA,'image_id':host.IMAGE,'gpu_uuid':host.GPU}
        post={'status':'passed','configurations':629,'scenarios':17,'worker_exit0_empty_group_count':1258,'full_decoded_mp4_count':629}
        common.write(root/'host-plan.json',plan);common.write(root/'host/final-validation/full-validation.json',post)
        receipt={'plan_sha256':host.PREVIOUS_PLAN_SHA,'status':'completed','driver_returncode':0,'driver_returncode_after_stop':0,
                 'observer_returncode':0,'cpu_validation_returncode':0,'owned_gpu_container_stop':{'running_after_stop':False},
                 'owned_cpu_container_stop':{'running_after_stop':False},'full_validation_sha256':common.sha(root/'host/final-validation/full-validation.json'),
                 'container_id':'a'*64,'cpu_container_id':'b'*64}
        common.write(root/'host/launch-receipt.json',receipt)
        return receipt

    def test_terminal629_cpu_and_both_owned_stops_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixtures(root)
            def command(argv):return json.dumps([{'Id':argv[-1],'Image':host.IMAGE,'State':{'Running':False}}])
            with patch.object(host,'PREVIOUS',root),patch.object(host,'command',side_effect=command):
                self.assertTrue(host.previous_completed()['native629_terminal_cpu_passed'])

    def test_running_or_failed_or_missing_cpu_receipt_starts_no_resource(self):
        for bad in ('running','failed','cpu-running','missing'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);receipt=self.fixtures(root)
                if bad in ('running','failed'):receipt['status']=bad
                if bad=='cpu-running':receipt['owned_cpu_container_stop']['running_after_stop']=True
                common.write(root/'host/launch-receipt.json',receipt)
                if bad=='missing':(root/'host/final-validation/full-validation.json').unlink()
                with patch.object(host,'PREVIOUS',root),patch.object(host,'command') as command,self.assertRaises(ValueError):host.previous_completed()
                command.assert_not_called()

    def test_receipt_stopped_but_actual_container_running_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixtures(root)
            with patch.object(host,'PREVIOUS',root),patch.object(host,'command',return_value=json.dumps([{'Id':'a'*64,'Image':host.IMAGE,'State':{'Running':True}}])), self.assertRaises(ValueError):host.previous_completed()


class AllKeysRecordingTests(unittest.TestCase):
    def test_actual_schema_all_twelve_labels_and_missing_reserved_rejection(self):
        import numpy as np
        from check_recordings import check_allkeys
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture-only.npz';commands=np.eye(15,dtype=np.float32)[np.repeat(np.arange(12),10)]
            qpos=np.zeros((len(commands),36),dtype=np.float32);qpos[:,0]=1.
            np.savez(path,qpos=qpos,vel_cmd=commands,fps=np.array(50))
            self.assertEqual(check_allkeys(path)['all_deployed_labels_present'],list(range(12)))
            commands[-1]=np.eye(15,dtype=np.float32)[12]
            np.savez(path,qpos=qpos,vel_cmd=commands,fps=np.array(50))
            with self.assertRaises(ValueError):check_allkeys(path)


if __name__=='__main__':unittest.main(verbosity=2)
