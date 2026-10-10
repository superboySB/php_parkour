"""Synthetic stdlib control-plane tests, no SSH/Docker/native/science execution."""
import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('delivery_waiter_tested',HERE/'wait_final_students.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

def record(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':w.sha(path)}

@pytest.fixture
def env(tmp_path,monkeypatch):
    names={'WORKSPACE':tmp_path,'PREPARATION':tmp_path/'outputs/research/waiter','PULL':tmp_path/'scripts/research/pull_final_students.py',
           'NATIVE':tmp_path/'outputs/research/native58','PREVIOUS':tmp_path/'outputs/research/old629/host/launch-receipt.json',
           'TRANSFER_ROOT':tmp_path/'outputs/research/final-student-transfer/waiter-delivery-01','NATIVE_OUTPUT':tmp_path/'outputs/research/new58',
           'MUTEX':tmp_path/'outputs/research'/('.local-native-'+w.UUID+'.lock')}
    for key,value in names.items():monkeypatch.setattr(w,key,value)
    monkeypatch.setattr(w,'CONTRACT_GUARD',None)
    w.PREPARATION.mkdir(parents=True);shutil.copyfile(HERE/'wait_final_students.py',w.PREPARATION/'wait_final_students.py')
    w.PULL.parent.mkdir(parents=True);w.PULL.write_text('# fake pull\n')
    w.NATIVE.mkdir(parents=True)
    for name in ('native58.py','common.py','reused-sources.json'):(w.NATIVE/name).write_text('# fake control '+name)
    dump(w.NATIVE/'code-freeze.json',{'status':'code_frozen_cpu_control_plane_only','files':[dict(record(w.NATIVE/'native58.py'),path='native58.py')]})
    contract={'schema_version':1,'status':'approved_frozen','workspace':str(w.WORKSPACE),'preparation':str(w.PREPARATION),'pull':str(w.PULL),
              'native58':str(w.NATIVE/'native58.py'),'previous_cohort_receipt':str(w.PREVIOUS),'transfer_output_root':str(w.TRANSFER_ROOT),
              'native_output':str(w.NATIVE_OUTPUT),'gpu_uuid':w.UUID,'gpu_mutex':str(w.MUTEX),'poll_seconds':600,'remote_source_tree':w.REMOTE_TREE,
              'coverage_output':w.COVERAGE,'native_image':w.IMAGE,'expected_counts':dict(w.EXPECTED_COUNTS),'waiter_sha256':w.sha(w.PREPARATION/'wait_final_students.py'),
              'native58_code_freeze':record(w.NATIVE/'code-freeze.json'),
              'sources':[record(w.NATIVE/'common.py'),record(w.PULL),record(w.NATIVE/'native58.py'),record(w.NATIVE/'reused-sources.json')]}
    return contract

def ready():
    payload={'fixture':'synthetic final two pairs, not actual trained models'}
    return {'status':'ready','snapshot_identity':w.identity(payload),'payload':payload,'cohort':'final-synthetic'}

def phase_specs():return [{'id':x,'cases':n} for x,n in [('pure-directions',12),('pure-scenes',17),('finetune-directions',12),('finetune-scenes',17)]]

def finish(base,plan):
    phases=[]
    for phase in plan['phases']:
        path=base/'phases'/phase['id']/'cpu-final/summary.json'
        dump(path,{'status':'passed','case_count':phase['cases'],'worker_exit0_empty_groups':2*phase['cases'],'full_decoded_mp4_count':phase['cases']})
        phases.append({'id':phase['id'],'status':'completed','driver_returncode':0,'observer_returncode':0,'driver_returncode_after_stop':0,
                       'owned_gpu_container_stop':{'running_after_stop':False},'worker_exit0_empty_groups':2*phase['cases'],
                       'host_maps':[{}]*(2*phase['cases']),'full_decoded_mp4_count':phase['cases'],'cpu_final':record(path)})
    dump(base/'host/launch-receipt.json',{'status':'completed','plan_sha256':plan['plan_sha256'],**w.EXPECTED_COUNTS,'quality_verified':False,
                                        'obstacle_course_completion_verified':False,'phases':phases})

class Flow:
    def __init__(self,contract,*,waiting=False,gate=False,fail=None):
        self.contract=contract;self.waiting=waiting;self.open_gate=gate;self.fail=fail;self.calls=[]
        self.pull=SimpleNamespace(validate_receipt=self.validate)
        self.common=SimpleNamespace(transfer=lambda *_:{'status':'ready'})
        self.native=SimpleNamespace(verify_snapshot=lambda *_:None)
    def validate(self,value):assert value==ready()
    def adapter(self,_):return self.pull,self.common,self.native
    def gate(self,*_):return {'ready':self.open_gate,'reason':'synthetic resource gate'}
    def runner(self,argv,logs,label,contract,timeout=None):
        self.calls.append((label,argv));assert w.verify_sources(contract)
        if label==self.fail:raise RuntimeError('synthetic '+label+' error')
        if label=='status':return {'status':'waiting','canonical_stage_count':16,'cpu_ready_present':False} if self.waiting else ready()
        if label=='fetch':
            dest=w.TRANSFER_ROOT/ready()['cohort']/'initial';dest.mkdir(parents=True);dump(dest/'remote-before.json',ready())
            return {'status':'completed','files':32,'destination':str(dest),'transfer_tool_sha256':w.sha(w.PULL)}
        if label=='prepare':
            w.NATIVE_OUTPUT.mkdir();(w.NATIVE_OUTPUT/'control').mkdir();shutil.copyfile(w.NATIVE/'native58.py',w.NATIVE_OUTPUT/'control/native58.py')
            plan={'plan_sha256':'syntheticplan','phases':phase_specs(),'origin_transfer':{'snapshot_identity':ready()['snapshot_identity']}}
            dump(w.NATIVE_OUTPUT/'host-plan.json',plan)
            return {'status':'prepared_only','plan':str(w.NATIVE_OUTPUT/'host-plan.json'),'plan_sha256':plan['plan_sha256'],'actual_cpu_ort_cases':60,'cases':58,'workers':116}
        if label=='run':finish(w.NATIVE_OUTPUT,w.read(w.NATIVE_OUTPUT/'host-plan.json'));return {'status':'completed'}
        raise AssertionError(label)
    def waiter(self):
        path=w.PREPARATION/'execution';path.mkdir()
        return w.Waiter(self.contract,path,runner=self.runner,adapter=self.adapter,gate=self.gate)


def test_waiting_never_fetches_prepares_or_probes_gpu(env):
    flow=Flow(env,waiting=True);waiter=flow.waiter()
    for _ in range(3):assert waiter.step() is False
    assert [x[0] for x in flow.calls]==['status']*3
    assert not w.TRANSFER_ROOT.exists() and not w.NATIVE_OUTPUT.exists()
    assert waiter.state['polls']==3 and not waiter.state['fetch_attempted']

def test_one_fetch_waits_for_old_cohort_without_repoll_or_retry(env):
    flow=Flow(env);waiter=flow.waiter()
    assert waiter.step() is False and waiter.step() is False
    assert [x[0] for x in flow.calls]==['status','fetch']
    assert not w.NATIVE_OUTPUT.exists() and waiter.state['stage']=='local_resource_release'

def test_exact_completed_flow_runs_frozen_copy_and_keeps_quality_false(env):
    flow=Flow(env,gate=True);waiter=flow.waiter();assert waiter.step() is True
    assert [x[0] for x in flow.calls]==['status','fetch','prepare','run']
    assert flow.calls[-1][1][1]==str(w.NATIVE_OUTPUT/'control/native58.py')
    assert flow.calls[-1][1][-1]=='--root-authorized-start'
    assert waiter.state['completion']['cases']==58 and waiter.state['quality_verified'] is False
    with pytest.raises(ValueError,match='Terminal'):waiter.step()

@pytest.mark.parametrize('action',['fetch','prepare','run'])
def test_started_action_failure_is_terminal_partial_preserved(env,action):
    flow=Flow(env,gate=True,fail=action);waiter=flow.waiter()
    with pytest.raises(RuntimeError) as failed:waiter.step()
    waiter.fail(failed.value)
    assert waiter.state[action+'_attempted'] and waiter.state['status']=='failed'
    assert waiter.state['automatic_retry'] is False
    calls=list(flow.calls)
    with pytest.raises(ValueError,match='Terminal'):waiter.step()
    assert flow.calls==calls

@pytest.mark.parametrize('target',['pull','native58','waiter','freeze','contract'])
def test_changed_executable_or_contract_refused_before_any_call(env,target):
    if target=='contract':
        path=w.PREPARATION/'contract.json';dump(path,env);monkey=w.sha(path);w.CONTRACT_GUARD=(path,monkey);path.write_text('{}')
    else:
        path={'pull':w.PULL,'native58':w.NATIVE/'native58.py','waiter':w.PREPARATION/'wait_final_students.py','freeze':w.NATIVE/'code-freeze.json'}[target]
        path.write_text(path.read_text()+'\nchanged')
    with pytest.raises(ValueError):w.verify_sources(env)

@pytest.mark.parametrize('key,value',[('poll_seconds',5),('remote_source_tree','wrong'),('coverage_output','old'),('gpu_uuid','GPU-other'),('native_output','/tmp/escape')])
def test_unreviewed_contract_values_rejected(env,key,value):
    env[key]=value
    with pytest.raises(ValueError):w.verify_sources(env)

def test_source_list_order_does_not_choose_wrong_pull_sha(env):
    assert env['sources'][0]['path']!=str(w.PULL)
    assert Flow(env,gate=True).waiter().step() is True

def test_changed_source_after_status_is_caught_before_fetch(env):
    flow=Flow(env);original=flow.runner
    def runner(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[2]=='status':w.PULL.write_text('changed')
        return value
    flow.runner=runner;waiter=flow.waiter()
    with pytest.raises(ValueError):waiter.step()
    assert [x[0] for x in flow.calls]==['status'] and not w.TRANSFER_ROOT.exists()

def test_changed_ready_snapshot_during_fetch_rejected(env):
    flow=Flow(env);original=flow.runner
    def runner(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[2]=='fetch':dump(Path(value['destination'])/'remote-before.json',{'snapshot_identity':'OTHER','payload':{}})
        return value
    flow.runner=runner;waiter=flow.waiter()
    with pytest.raises(ValueError,match='changed from'):waiter.step()
    assert w.TRANSFER_ROOT.exists() and not w.NATIVE_OUTPUT.exists()

@pytest.mark.parametrize('target',['transfer','native'])
def test_preexisting_partial_dest_never_reused(env,target):
    (w.TRANSFER_ROOT if target=='transfer' else w.NATIVE_OUTPUT).mkdir(parents=True)
    flow=Flow(env);waiter=flow.waiter()
    with pytest.raises(ValueError,match='already exists'):waiter.step()
    assert [x[0] for x in flow.calls]==['status']

def test_symlink_rejected_for_source_or_destination(env):
    original=w.PULL.with_name('original.py');w.PULL.rename(original);w.PULL.symlink_to(original)
    with pytest.raises(ValueError,match='Symlink'):w.verify_sources(env)
    w.PULL.unlink();original.rename(w.PULL)
    w.TRANSFER_ROOT.parent.mkdir(parents=True);w.TRANSFER_ROOT.symlink_to(w.NATIVE)
    flow=Flow(env);waiter=flow.waiter()
    with pytest.raises(ValueError,match='Symlink'):waiter.step()

def test_no_restart_over_existing_waiter_evidence(env):
    flow=Flow(env);waiter=flow.waiter();before=w.sha(waiter.path)
    with pytest.raises(FileExistsError):w.Waiter(env,waiter.directory,adapter=flow.adapter)
    assert w.sha(waiter.path)==before

def stopped(env):
    info={'Id':'exactCID','Image':w.IMAGE,'State':{'Running':False,'StartedAt':'exactBirth'}}
    receipt={'status':'completed','driver_returncode':0,'cpu_validation_returncode':0,'container_id':'exactCID',
             'owned_gpu_container_stop':{'container_id':'exactCID','running_after_stop':False,'state':{'StartedAt':'exactBirth'}}}
    dump(w.PREVIOUS,receipt);w.MUTEX.touch()
    return info,SimpleNamespace(IMAGE=w.IMAGE,inspect=lambda _:info,gpu_idle=lambda:{'uuid':w.UUID})

def test_active_previous_cohort_only_waits_no_docker_gpu_call(env):
    dump(w.PREVIOUS,{'status':'running'})
    native=SimpleNamespace(inspect=lambda _:pytest.fail('Docker'),gpu_idle=lambda:pytest.fail('GPU'))
    assert w.local_ready(env,native)['ready'] is False

@pytest.mark.parametrize('fault',['image','cid','birth','running','driver_rc','cpu_rc','stop'])
def test_previous_cohort_terminal_identity_must_match(env,fault):
    info,native=stopped(env);receipt=w.read(w.PREVIOUS)
    if fault=='image':info['Image']='wrong'
    elif fault=='cid':info['Id']='wrong'
    elif fault=='birth':info['State']['StartedAt']='newBirth'
    elif fault=='running':info['State']['Running']=True
    elif fault=='driver_rc':receipt['driver_returncode']=1
    elif fault=='cpu_rc':receipt['cpu_validation_returncode']=1
    else:receipt['owned_gpu_container_stop']['running_after_stop']=True
    dump(w.PREVIOUS,receipt)
    with pytest.raises(ValueError):w.local_ready(env,native)

def test_uuid_mutex_busy_waits_without_gpu_probe(env):
    _,native=stopped(env);native.gpu_idle=lambda:pytest.fail('GPU read before mutex')
    with w.MUTEX.open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert w.local_ready(env,native)['ready'] is False

def test_gpu_busy_waits_but_wrong_uuid_is_fatal(env):
    _,native=stopped(env)
    def busy():raise ValueError('Selected GPU has existing compute; never stop other work')
    native.gpu_idle=busy;assert w.local_ready(env,native)['ready'] is False
    def wrong():raise ValueError('Approved physical GPU UUID not unique/present')
    native.gpu_idle=wrong
    with pytest.raises(ValueError,match='identity'):w.local_ready(env,native)

@pytest.mark.parametrize('field',['cases','worker_exit0_empty_groups','exact_host_maps','full_decoded_mp4_count','quality_verified','phase_returncode','cpu_final_sha','cpu_final_empty','cpu_final_path'])
def test_completion_requires_exact_actual_terminal_receipts(env,field):
    base=w.NATIVE_OUTPUT;base.mkdir();plan={'plan_sha256':'syntheticplan','phases':phase_specs()};finish(base,plan)
    receipt=w.read(base/'host/launch-receipt.json')
    if field in w.EXPECTED_COUNTS:receipt[field]-=1
    elif field=='quality_verified':receipt[field]=True
    elif field=='phase_returncode':receipt['phases'][0]['driver_returncode_after_stop']=1
    elif field=='cpu_final_sha':receipt['phases'][0]['cpu_final']['sha256']='0'*64
    elif field=='cpu_final_empty':Path(receipt['phases'][0]['cpu_final']['path']).write_text('{}')
    else:
        other=w.PREPARATION/'other-summary.json';shutil.copyfile(receipt['phases'][0]['cpu_final']['path'],other);receipt['phases'][0]['cpu_final']=record(other)
    dump(base/'host/launch-receipt.json',receipt)
    with pytest.raises(ValueError):w.validate_completion(base,plan,SimpleNamespace(verify_snapshot=lambda *_:None))


def test_source_and_parent_escape_paths_rejected(env):
    for path in ('relative','/tmp/elsewhere',str(w.WORKSPACE/'outputs/../escape')):
        with pytest.raises(ValueError):w.safe(path)


def cli(env,monkeypatch,action='check',authorized=False):
    path=w.PREPARATION/'contract.json';dump(path,env)
    monkeypatch.setattr(w,'__file__',str(w.PREPARATION/'wait_final_students.py'))
    argv=['waiter',action,'--contract',str(path),'--contract-sha256',w.sha(path),'--self-sha256',env['waiter_sha256']]
    if authorized:argv.append('--root-authorized-watch')
    monkeypatch.setattr(w.sys,'argv',argv)


def test_check_does_not_create_execution_locks_or_import_controls(env,monkeypatch):
    cli(env,monkeypatch)
    monkeypatch.setattr(w,'adapters',lambda _:pytest.fail('No adapters during check'))
    assert w.main()==0
    assert not (w.PREPARATION/'execution').exists() and not (w.PREPARATION/'waiter.lock').exists()


def test_watch_requires_root_explicit_arm_before_any_mutation(env,monkeypatch):
    cli(env,monkeypatch,'watch')
    with pytest.raises(ValueError,match='root authorization'):w.main()
    assert not (w.PREPARATION/'execution').exists() and not (w.PREPARATION/'waiter.lock').exists()


def test_watch_single_instance_flock_blocks_second_process_control(env,monkeypatch):
    cli(env,monkeypatch,'watch',True)
    lockpath=w.PREPARATION/'waiter.lock';lockpath.touch()
    with lockpath.open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):w.main()
    assert not (w.PREPARATION/'execution').exists()


def test_watch_existing_attempt_is_not_resumed_or_overwritten(env,monkeypatch):
    cli(env,monkeypatch,'watch',True);directory=w.PREPARATION/'execution';directory.mkdir();dump(directory/'state.json',{'status':'failed'})
    before=w.sha(directory/'state.json')
    with pytest.raises(ValueError,match='Existing execution'):w.main()
    assert w.sha(directory/'state.json')==before


def test_launch_lock_fifo_is_rejected_without_blocking_open(env,monkeypatch):
    import os
    cli(env,monkeypatch,'watch',True);os.mkfifo(w.PREPARATION/'waiter.lock')
    with pytest.raises(ValueError,match='Regular file'):w.main()


def test_local_identity_rechecked_after_cpu_prepare_before_run(env):
    flow=Flow(env,gate=True);waiter=flow.waiter();calls=[]
    def gate(*_):calls.append(1);return {'ready':len(calls)==1}
    waiter.gate=gate
    with pytest.raises(ValueError,match='changed during CPU prepare'):waiter.step()
    assert [x[0] for x in flow.calls]==['status','fetch','prepare'] and not waiter.state['run_attempted']


def test_invoke_post_source_mutation_keeps_launch_logs(env,monkeypatch):
    logs=w.PREPARATION/'logs';logs.mkdir()
    def fake(argv,stdout,stderr,**_):stdout.write('{}');w.PULL.write_text('changed');return SimpleNamespace(returncode=0)
    monkeypatch.setattr(w.subprocess,'run',fake)
    with pytest.raises(ValueError):w.invoke(['synthetic'],logs,'source-mutation',env)
    assert len(list(logs.glob('*.json')))==1 and len(list(logs.glob('*.stdout.log')))==1
