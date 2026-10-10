"""CPU control-plane fixtures; no final models, SSH, DDS, daemon or GPU."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(REPO));sys.path.insert(0,str(REPO/'tests'));sys.path.insert(0,str(HERE))
import common as c
import native58 as n
import phase_cpu as cpu
from scripts.research import pull_final_students as pf
from test_posttrain_coverage import canonical
from test_pull_final_students import ready,probe


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);c.write(path,data)


@pytest.fixture
def fetched(ready,tmp_path):
    workspace=tmp_path/'workspace';workspace.mkdir()
    dest=workspace/'outputs/research/final-student-transfer/final-fixture/initial'
    dest.mkdir(parents=True)
    helper=workspace/'scripts/research/pull_final_students.py';helper.parent.mkdir(parents=True)
    shutil.copyfile(REPO/'scripts/research/pull_final_students.py',helper)
    before=probe(ready);payload=before['payload']
    payload['source_tree']=c.TREE;payload['remote_root']=pf.REMOTE_ROOT
    payload['host_coverage_output']=pf.REMOTE_ROOT+'/outputs/'+pf.COVERAGE_DIRECTORY
    for item in payload['files']:
        source=ready.args.root/'outputs'/item['relative'];target=dest/'raw'/item['relative']
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    selection_path=dest/'raw'/pf.COVERAGE_DIRECTORY/'selection.json'
    selection=c.read(selection_path);selection['coverage_source_tree']=c.TREE
    selection['host_coverage_output']=payload['host_coverage_output']
    selection['input_identity']=c.identity({k:v for k,v in selection.items() if k!='input_identity'})
    save(selection_path,selection)
    cpu_path=dest/'raw'/pf.COVERAGE_DIRECTORY/'cpu-ready.json';report=c.read(cpu_path)
    report['input_identity']=selection['input_identity'];save(cpu_path,report)
    payload['selection_identity']=selection['input_identity']
    for item in payload['files']:
        path=dest/'raw'/item['relative'];item.update(sha256=c.sha(path),bytes=path.stat().st_size)
    models=[]
    for pair in payload['pairs']:
        for name,item in pair['models'].items():
            target=dest/'models'/pair['kind']/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(dest/'raw'/item['relative'],target)
            models.append({'kind':pair['kind'],'source_relative':item['relative'],**c.record(target)})
    before['snapshot_identity']=c.identity(payload)
    before['cohort']=f"final-{selection['input_identity'][:12]}-{payload['pairs'][0]['checkpoint']['sha256'][:12]}-{payload['pairs'][1]['checkpoint']['sha256'][:12]}"
    save(dest/'remote-before.json',before);save(dest/'remote-after.json',before)
    save(dest/'fetch-status.json',{'status':'completed','snapshot_identity':before['snapshot_identity'],'destination':str(dest),
        'files':32,'transfer_tool_sha256':c.PULL_SHA,'quality_verified':False,'models':models,
        'total_bytes':sum(item['bytes'] for item in payload['files'])})
    return SimpleNamespace(workspace=workspace,dest=dest,before=before)


def test_missing_fetch_prepare_never_creates_output_or_process(tmp_path,monkeypatch):
    monkeypatch.setattr(n,'call',lambda *_a,**_k:pytest.fail('Missing fetch touched Docker/GPU'))
    monkeypatch.setattr(n.subprocess,'Popen',lambda *_a,**_k:pytest.fail('Missing fetch started daemon'))
    args=SimpleNamespace(workspace=tmp_path,transfer=None,output=tmp_path/'outputs/research/new')
    got=n.prepare(args)
    assert got['status']=='waiting' and got['native_started'] is False and not args.output.exists()


def test_exact_synthetic_completed_fetch_is_accepted_without_process(fetched):
    got=c.transfer(fetched.workspace,fetched.dest)
    assert got['status']=='ready' and len(got['models'])==4 and len(got['origin_files'])==39
    assert got['gpu_started'] is False


@pytest.mark.parametrize('fault',['partial','raw_model','materialized','after','extra_raw','source_tree','coverage','tool'])
def test_partial_or_stale_transfer_is_rejected(fetched,fault):
    dest=fetched.dest
    if fault=='partial':
        path=dest/'fetch-status.json';d=c.read(path);d['status']='failed';save(path,d)
    elif fault=='raw_model':
        path=next((dest/'raw').rglob('student.onnx'));path.write_bytes(b'changed')
    elif fault=='materialized':(dest/'models/pure/student.onnx').write_bytes(b'changed')
    elif fault=='extra_raw':(dest/'raw/other.json').write_text('{}')
    elif fault=='after':
        path=dest/'remote-after.json';d=c.read(path);d['snapshot_identity']='a'*64;save(path,d)
    elif fault=='tool':
        path=dest/'fetch-status.json';d=c.read(path);d['transfer_tool_sha256']='a'*64;save(path,d)
    else:
        path=dest/'remote-before.json';d=c.read(path)
        d['payload']['source_tree' if fault=='source_tree' else 'coverage_output']='a'*64 if fault=='source_tree' else 'coverage-old'
        d['snapshot_identity']=c.identity(d['payload']);save(path,d)
    with pytest.raises((ValueError,KeyError)):
        c.transfer(fetched.workspace,dest)


def test_transfer_alias_cannot_escape_dedicated_tree(fetched):
    link=fetched.workspace/'outputs/research/final-student-transfer/alias';link.symlink_to(fetched.dest,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):c.transfer(fetched.workspace,link)


def test_transfer_dotdot_escape_is_rejected_even_if_missing(tmp_path):
    path=tmp_path/'outputs/research/final-student-transfer/../outside'
    with pytest.raises(ValueError,match='traversal'):c.transfer(tmp_path,path)


def test_prepare_output_dotdot_escape_rejected_before_docker(fetched,monkeypatch):
    monkeypatch.setattr(n,'call',lambda *_a,**_k:pytest.fail('Unsafe output reached Docker'))
    args=SimpleNamespace(workspace=fetched.workspace,transfer=fetched.dest,
        output=fetched.workspace/'outputs/research/../../../escaped')
    with pytest.raises(ValueError,match='Fresh isolated'):n.prepare(args)


def test_reused_helpers_are_exact_original_bytes():
    for item in c.read(HERE/'reused-sources.json')['files']:
        assert c.sha(HERE/item['name'])==c.sha(REPO/item['origin'])==item['sha256']


def test_phase_counts_and_wall_limits_match_original_actual_baselines():
    phases=c.phase_specs()
    assert sum(p['cases'] for p in phases)==58 and sum(2*p['cases'] for p in phases)==116
    baseline=c.read(REPO/'outputs/research/commands12-sdk018-6cb2ae2-prepared01/inputs/native-plan.json')
    for case in baseline['selections']:
        cfg=case['expected_config'];assert cfg['wall_timeout']==373.0 and cfg['seconds_per_command']==8.0
    assert all('--wall-timeout' not in case['launch'] for case in baseline['selections'])
    assert '--all-configs' not in cpu.scene_args() and '--wall-timeout' not in cpu.scene_args()
    assert [(p['ticks'],p['native_wall_timeout_seconds']) for p in phases]==[(400,373.0),(500,413.0)]*2


def test_unapproved_run_refuses_before_any_read_or_process(monkeypatch):
    monkeypatch.setattr(n,'read',lambda *_a:pytest.fail('Unapproved run read a plan'))
    with pytest.raises(ValueError,match='authorization'):n.execute(SimpleNamespace(root_authorized_start=False))


@pytest.mark.parametrize('field',['workspace','global_host_lock','previous_cohort_receipt'])
def test_reidentified_plan_cannot_change_shared_gpu_mutex_or_previous_cohort(field):
    base=c.HOST_WORKSPACE/'outputs/research/native58-test-not-created'
    plan={'output':str(base),'image_id':c.IMAGE,'gpu_uuid':c.UUID,'revision':c.REVISION,'status':'prepared_only','native_started':False,
        'workspace':str(c.HOST_WORKSPACE),'global_host_lock':str(c.HOST_WORKSPACE/'outputs/research'/('.local-native-'+c.UUID+'.lock')),
        'previous_cohort_receipt':str(c.HOST_WORKSPACE/'outputs/research/fresh629-sdk018-6cb2ae2-prepared02/host/launch-receipt.json')}
    plan[field]='/tmp/foreign';plan['plan_sha256']=c.identity(plan)
    with pytest.raises(ValueError,match='Canonical workspace'):n.verify_snapshot(base,plan)


def test_final_pair_substitution_preserves_native12_commands_and_defaults(monkeypatch):
    old=c.read(REPO/'outputs/research/commands12-sdk018-6cb2ae2-prepared01/inputs/native-plan.json')
    final_models=[{'path':'/data/assets/student/'+name,'sha256':str(i+1)*64,'bytes':100+i} for i,name in enumerate(c.MODELS)]
    scenes={'schema_version':3,'planned_scenarios':17,'planned_configurations':17,'all_configurations':False,
        'models':final_models,'model_sha256':{Path(x['path']).name:x['sha256'] for x in final_models},'dependencies':old['dependencies'],
        'selections':[{'case_id':str(i)} for i in range(17)]}
    checked=[]
    class Matrix:
        def make_plan(self,args):return copy.deepcopy(scenes)
        def dependencies(self):return old['dependencies']
        def identity(self,value):return c.identity(value)
        def verify_inputs(self,plan,case):
            assert plan['model_sha256']==scenes['model_sha256']
            assert case['expected_config']['model_sha256']==scenes['model_sha256'];checked.append(case['command'])
    monkeypatch.setattr(cpu,'read',lambda path:copy.deepcopy(old))
    directions,new_scenes=cpu.plans(Matrix())
    assert checked==list(range(12)) and new_scenes==scenes
    for a,b in zip(directions['selections'],old['selections']):
        assert a['launch']==b['launch'] and a['command']==b['command']
        assert a['expected_config']==b['expected_config']|{'model_sha256':scenes['model_sha256'],'python_faulthandler':True}


@pytest.mark.parametrize('changed',['runner','common'])
def test_actual_host_source_change_after_preparation_is_rejected(tmp_path,monkeypatch,changed):
    base=tmp_path/'cohort';(base/'control').mkdir(parents=True)
    runner=tmp_path/'host-native58.py';helper=tmp_path/'host-common.py'
    runner.write_bytes(b'runner');helper.write_bytes(b'common')
    shutil.copyfile(runner,base/'control/native58.py');shutil.copyfile(helper,base/'control/common.py')
    monkeypatch.setattr(n,'__file__',str(runner));monkeypatch.setattr(n.contracts,'__file__',str(helper))
    n.verify_host_sources(base)
    (runner if changed=='runner' else helper).write_bytes(b'changed')
    with pytest.raises(ValueError,match='exact frozen'):n.verify_host_sources(base)


def test_default_pose_joint_permutation_is_checked():
    names=[f'joint{i}' for i in range(29)];native=SimpleNamespace(dof_names=names,default_dof_angles=[i*.01 for i in range(29)])
    reversed_names=list(reversed(names));values=list(reversed(native.default_dof_angles))
    metadata={'joint_names':','.join(reversed_names),'default_joint_pos':','.join(map(str,values))}
    assert cpu.pose_contract(metadata,native)['max_default_pose_absolute_error']==0
    metadata['default_joint_pos']='0,'+','.join(map(str,values[1:]))
    with pytest.raises(ValueError,match='default pose'):cpu.pose_contract(metadata,native)


@pytest.mark.parametrize('fault',['joints','nan'])
def test_bad_model_pose_metadata_is_rejected(fault):
    names=[f'j{i}' for i in range(29)];native=SimpleNamespace(dof_names=names,default_dof_angles=[0.]*29)
    metadata={'joint_names':','.join(names),'default_joint_pos':','.join(['0']*29)}
    if fault=='joints':metadata['joint_names']=','.join(['j0']*29)
    else:metadata['default_joint_pos']='nan,'+','.join(['0']*28)
    with pytest.raises(ValueError):cpu.pose_contract(metadata,native)


@pytest.fixture
def container(tmp_path):
    spec=n.container_spec(tmp_path,'pure','own-name',['/bin/bash','-lc','exec sleep infinity'],True,tmp_path/'phase/outputs')
    cid='a'*64
    info={'Id':cid,'Image':c.IMAGE,'Name':'/own-name','Config':{'WorkingDir':str(n.ROOT),'Entrypoint':['/bin/bash'],'Cmd':['-lc','exec sleep infinity']},
        'HostConfig':{'DeviceRequests':[{'DeviceIDs':[c.UUID],'Count':0}],'NetworkMode':'none','IpcMode':'private',
            'PidMode':'','Privileged':False,'Init':True,'ShmSize':8589934592},
        'Mounts':[{'Source':m['source'],'Destination':m['destination'],'RW':m['rw'],'Type':'bind'} for m in spec['mounts']]}
    return cid,spec,info


def test_exact_owned_gpu_container_contract(container):
    cid,spec,info=container;n.verify_container(info,cid,spec)
    assert all(not m['rw'] for m in spec['mounts'] if m['destination'] in (str(n.ROOT),'/data','/control'))
    assert '--ipc' in spec['argv'] and '--network' in spec['argv']


@pytest.mark.parametrize('fault',['id','image','gpu','mount','pid','ipc','command','privileged'])
def test_foreign_or_mutated_container_is_never_cleanup_owned(container,fault):
    cid,spec,info=container
    if fault=='id':info['Id']='b'*64
    elif fault=='image':info['Image']='sha256:'+'b'*64
    elif fault=='gpu':info['HostConfig']['DeviceRequests'][0]['DeviceIDs']=['GPU-other']
    elif fault=='mount':info['Mounts'][0]['RW']=True
    elif fault=='pid':info['HostConfig']['PidMode']='host'
    elif fault=='ipc':info['HostConfig']['IpcMode']='host'
    elif fault=='command':info['Config']['Cmd']=['-lc','unrelated']
    else:info['HostConfig']['Privileged']=True
    with pytest.raises(ValueError):n.verify_container(info,cid,spec)


def test_source_copy_retains_original_and_refuses_changed_or_existing(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original');target=tmp_path/'snap/file'
    digest=c.sha(source)
    c.copy(source,target,digest,8)
    assert source.read_bytes()==target.read_bytes()==b'original'
    with pytest.raises(ValueError):c.copy(source,target,digest,8)
    with pytest.raises(ValueError):c.copy(source,tmp_path/'other','a'*64,8)


@pytest.fixture
def mapped(tmp_path):
    report=tmp_path/'phase';output='/outputs/commands/command-00'
    maps=[]
    for i,role in enumerate(('simulator','inference')):
        native={'pid':100+i,'start_time_clock_ticks':200+i}
        save(report/'outputs/commands/command-00'/(role+'-process-start.json'),{'process':native})
        maps.append({'role':role,'worker_output':output,'container_tgid':native['pid'],'owner_start_time_clock_ticks':native['start_time_clock_ticks'],
            'host_tid':1000+i,'host_tgid':900+i,'container_tid':300+i,'start_time_clock_ticks':400+i,
            'nspid':[1000+i,300+i],'nstgid':[900+i,native['pid']]})
    observer={'identity':{'container_id':'a'*64,'image_id':c.IMAGE,'started_at':'birth'},'stop_reason':'stop_file',
              'mapping_scope_complete':True,'errors':[],'command_writer_mappings':maps}
    save(report/'observer/summary.json',observer)
    save(report/'outputs/pilot-summary.json',{'status':'completed','native_plan_sha256':'b'*64,'remaining_native_pids':[],
        'cases':[{'case_id':'c','status':'completed','output':output}]})
    phase={'phase':'directions','cases':1,'id':'fixture','native_plan_sha256':'b'*64}
    return report,observer,phase


def test_host_observer_exact_pid_birth_namespace_mapping(mapped):
    report,observer,phase=mapped
    result=n.mappings(report.parent,phase,'a'*64,{'State':{'StartedAt':'birth'}},report)
    assert len(result)==2


@pytest.mark.parametrize('fault',['container','birth','native_birth','duplicate','namespace','time_bound'])
def test_stale_ambiguous_or_incomplete_host_maps_rejected(mapped,fault):
    report,observer,phase=mapped
    if fault=='container':observer['identity']['container_id']='b'*64
    elif fault=='birth':observer['identity']['started_at']='other'
    elif fault=='native_birth':observer['command_writer_mappings'][0]['owner_start_time_clock_ticks']+=1
    elif fault=='duplicate':observer['command_writer_mappings'].append(copy.deepcopy(observer['command_writer_mappings'][0]))
    elif fault=='namespace':observer['command_writer_mappings'][0]['nstgid']=[1,2]
    else:observer['stop_reason']='time_bound'
    save(report/'observer/summary.json',observer)
    with pytest.raises(ValueError):n.mappings(report.parent,phase,'a'*64,{'State':{'StartedAt':'birth'}},report)


@pytest.mark.parametrize('failure',['marker','observer_wait','observer_poll','container_stop','job_wait'])
def test_diagnostic_or_observer_error_never_bypasses_container_and_cli_cleanup(monkeypatch,failure):
    events=[]
    class Process:
        def __init__(self,role):self.role=role;self.waits=0
        def poll(self):
            if failure=='observer_poll' and self.role=='observer':raise OSError('observer poll fixture')
            return None
        def wait(self,timeout):
            events.append(self.role+'-wait');self.waits+=1
            if self.waits==1 and failure==self.role+'_wait':raise OSError('wait fixture')
            return 0
        def terminate(self):events.append(self.role+'-term')
        def kill(self):events.append(self.role+'-kill')
    class Marker:
        def touch(self,exist_ok):
            events.append('marker')
            if failure=='marker':raise OSError('marker fixture')
    def stop(cid,spec):
        events.append('owned-container-stop')
        if failure=='container_stop':raise OSError('owned stop fixture')
        return {'running_after_stop':False}
    monkeypatch.setattr(n,'stop_owned',stop)
    item={'status':'native_completed'}
    n.cleanup_phase('a'*64,{},Process('observer'),Process('job'),Marker(),item)
    assert 'owned-container-stop' in events and 'job-wait' in events
    assert item['status']=='failed' and item['cleanup_errors']
