"""Pure CPU runner contracts; never invokes Docker, GPU or simulator."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import copy
import pytest

SPEC = importlib.util.spec_from_file_location('preset_runner', Path(__file__).with_name('run_presets.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def row():
    return {'checkpoint':'/outputs/existing/model_00001.pt','native_output':'/outputs/fresh/preset',
            'native_overrides':['--training.export-onnx','False']}


def info():
    return {'Image':'sha256:'+'a'*64,'State':{'Running':True},'HostConfig':{'NetworkMode':'none','IpcMode':'private','PidMode':''},
            'Mounts':[{'Destination':'/workspace/php_parkour','Source':'/frozen/source','RW':False},
                      {'Destination':'/data/assets','Source':'/assets','RW':False},
                      {'Destination':'/outputs','Source':str(runner.ROOT/'outputs/research'),'RW':True}]}


def test_exact_existing_pt_export_disabled_and_timeout():
    command = runner.build_launch(row(),'b'*64)
    assert 'CHECKPOINT=/outputs/existing/model_00001.pt' in command
    assert command[-10:-2] == ['--training.headless','True','--logger.base-dir','/outputs/fresh/preset','--logger.video.interval','1','--logger.video.upload-to-wandb','False']
    assert ['--signal=TERM','--kill-after=30s','600s'] == command[command.index('/usr/bin/timeout')+1:command.index('/usr/bin/timeout')+4]
    assert 'NUM_ENVS=16' in command and 'MAX_EVAL_STEPS=100' in command
    assert command[command.index('scripts/research/eval_quality.sh')+1:command.index('scripts/research/eval_quality.sh')+3] == ['teacher','/outputs/fresh/preset/quality.json']


@pytest.mark.parametrize('fault',['image','source_rw','assets_rw','outputs_mapping','nested_source','network','pid','ipc'])
def test_wrong_container_contract_rejected(fault):
    value=info()
    if fault=='image': value['Image']='sha256:'+'b'*64
    elif fault=='source_rw': value['Mounts'][0]['RW']=True
    elif fault=='assets_rw': value['Mounts'][1]['RW']=True
    elif fault=='outputs_mapping': value['Mounts'][2]['Source']='/another-output-tree'
    elif fault=='nested_source': value['Mounts'].append({'Destination':'/workspace/php_parkour/wbt_training','RW':True,'Source':'/evil'})
    elif fault=='network': value['HostConfig']['NetworkMode']='host'
    elif fault=='pid': value['HostConfig']['PidMode']='host'
    else: value['HostConfig']['IpcMode']='host'
    with pytest.raises(ValueError): runner.container_gate(value,{},'sha256:'+'a'*64)


def test_fixed_ro_contract_accepted():
    runner.container_gate(info(),{},'sha256:'+'a'*64)


@pytest.mark.parametrize('fault',['changed_bytes','symlink','export_enabled','missing_case'])
def test_input_identity_rejected(tmp_path,fault):
    source=tmp_path/'input';source.write_bytes(b'fixed')
    artifact={'host_path':str(source),'bytes':5,'sha256':runner.sha(source)}
    plan={'schema_version':1,'cases':[dict(row(),inputs=[]) for _ in range(5)],'source_closure':[artifact],'cpu_provenance':[],'preparation_helpers':[]}
    if fault=='changed_bytes': source.write_bytes(b'other')
    elif fault=='symlink': source.rename(tmp_path/'target');source.symlink_to(tmp_path/'target')
    elif fault=='export_enabled': plan['cases'][0]['native_overrides'][-1]='True'
    else: plan['cases'].pop()
    with pytest.raises(ValueError): runner.verify_inputs(plan)


def cpu_receipt_fixture(tmp_path,monkeypatch):
    root=tmp_path/'repo';base=root/'outputs/research/preparation';base.mkdir(parents=True)
    (base/'cpu_preflight.py').write_text('# isolated fixture\n')
    monkeypatch.setattr(runner,'ROOT',root);monkeypatch.setattr(runner,'BASE',base)
    path=base/'actual/launch.json';path.parent.mkdir()
    args=SimpleNamespace(container_id='b'*64,expected_image='sha256:'+'a'*64,plan=base/'plan.json',cpu_preflight_receipt=path)
    cases=[];rows=[]
    for index in range(5):
        case=dict(row(),preset=f'fixture{index}',contract={'observation_dim':160},inputs=[{'native_path':row()['checkpoint'],'sha256':'c'*64}])
        cases.append(case)
        rows.append({'preset':case['preset'],'checkpoint_sha256':'c'*64,'checkpoint_iteration':1,'actual_saved_contract':case['contract'],
            'native_parser_passed':True,'num_envs':16,'max_eval_steps':100,'export_onnx':False,
            'logger_base_dir':case['native_output'],'native_overrides':case['native_overrides'],
            'runtime_robot_asset_root':'/outputs/teacher-preset-runtime-assets-v3/robots',
            'runtime_urdf':'g1/main_mesh_arm_collision_halfspherehand.urdf'})
    plan={'cases':cases};args.plan.write_text(runner.json.dumps(plan))
    report={'status':'passed','plan_sha256':runner.sha(args.plan),'cuda_initialized':False,'isaac_started':False,
            'physics_verified':False,'quality_verified':False,'rows':rows}
    (path.parent/'cpu-report.json').write_text(runner.json.dumps(report))
    for name in ['stdout.log','stderr.log']:(path.parent/name).write_text('isolated CPU fixture')
    container=info();container.update(Id=args.container_id);container['State']['StartedAt']='fixed-start'
    receipt={'schema_version':1,'status':'passed','returncode':0,'container_id':args.container_id,'image_id':args.expected_image,
        'container_started_at':'fixed-start','plan_sha256':runner.sha(args.plan),'runner_sha256':runner.sha(Path(runner.__file__)),
        'preflight_source_sha256':runner.sha(base/'cpu_preflight.py'),'command':runner.cpu_launch(args,path),
        'cpu_report':runner.fingerprint(path.parent/'cpu-report.json'),'stdout':runner.fingerprint(path.parent/'stdout.log'),
        'stderr':runner.fingerprint(path.parent/'stderr.log')}
    path.write_text(runner.json.dumps(receipt))
    return path,args,plan,container,receipt


def test_same_actual_cpu_container_image_and_sources_accepted(tmp_path,monkeypatch):
    path,args,plan,container,receipt=cpu_receipt_fixture(tmp_path,monkeypatch)
    assert runner.validate_cpu_receipt(path,args,plan,container)==receipt


@pytest.mark.parametrize('fault',['unknown','stale_plan','image','container','restart','report','source','pt','stdout','argv'])
def test_old_unknown_or_tampered_cpu_receipt_cannot_arm_gpu(tmp_path,monkeypatch,fault):
    path,args,plan,container,receipt=cpu_receipt_fixture(tmp_path,monkeypatch)
    if fault=='unknown': path.unlink()
    elif fault=='stale_plan': args.plan.write_text('changed plan bytes')
    elif fault=='image': receipt['image_id']='sha256:'+'d'*64
    elif fault=='container': receipt['container_id']='d'*64
    elif fault=='restart': container['State']['StartedAt']='restarted'
    elif fault=='report': (path.parent/'cpu-report.json').write_text('{}')
    elif fault=='source': (runner.BASE/'cpu_preflight.py').write_text('# changed helper\n')
    elif fault=='pt':
        report=runner.json.loads((path.parent/'cpu-report.json').read_text());report['rows'][0]['checkpoint_sha256']='d'*64
        (path.parent/'cpu-report.json').write_text(runner.json.dumps(report));receipt['cpu_report']=runner.fingerprint(path.parent/'cpu-report.json')
    elif fault=='stdout': (path.parent/'stdout.log').write_text('changed log')
    else: receipt['command'][-1]='/outputs/another-cpu-report.json'
    if fault!='unknown': path.write_text(runner.json.dumps(receipt))
    with pytest.raises(ValueError): runner.validate_cpu_receipt(path,args,plan,container)


def test_execute_requires_explicit_receipt_before_any_docker_or_gpu_query(monkeypatch):
    monkeypatch.setattr(runner,'capture',lambda _:pytest.fail('must reject before external query'))
    with pytest.raises(ValueError,match='explicit --cpu-preflight-receipt'):
        runner.execute(SimpleNamespace(cpu_preflight_receipt=None),{})


def robot_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    source=tmp_path/'source/g1/test.urdf';source.parent.mkdir(parents=True);source.write_text('<robot/>')
    target=tmp_path/'outputs/research/teacher-preset-runtime-assets-v3/robots/g1/test.urdf'
    target.parent.mkdir(parents=True);target.write_bytes(source.read_bytes())
    def artifact(path,native):
        return {'host_path':str(path),'native_path':native,'sha256':runner.sha(path),'bytes':path.stat().st_size}
    root='/outputs/teacher-preset-runtime-assets-v3/robots'
    return {'runtime_robot_root':root,'robot_assets':[{'relative_path':'g1/test.urdf',
        'source':artifact(source,'/workspace/php_parkour/robots/g1/test.urdf'),
        'copy':artifact(target,root+'/g1/test.urdf')}],
        'cases':[{'native_overrides':['--robot.asset.asset-root',root]}]},target


def test_byte_exact_independent_writable_robot_assets_accepted(tmp_path,monkeypatch):
    plan,_=robot_fixture(tmp_path,monkeypatch)
    runner.verify_robot_assets(plan)


@pytest.mark.parametrize('fault',['path_escape','source_root','tamper','missing','missing_override'])
def test_unsafe_or_changed_runtime_asset_rejected(tmp_path,monkeypatch,fault):
    plan,target=robot_fixture(tmp_path,monkeypatch)
    if fault=='path_escape':plan['robot_assets'][0]['relative_path']='../test.urdf'
    elif fault=='source_root':plan['runtime_robot_root']='/workspace/php_parkour/robots'
    elif fault=='tamper':target.write_text('changed')
    elif fault=='missing':target.unlink()
    else:plan['cases'][0]['native_overrides']=[]
    with pytest.raises(ValueError):runner.verify_robot_assets(plan)


def quality_fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    case=dict(row(),inputs=[{'native_path':row()['checkpoint'],'sha256':'c'*64}])
    output=tmp_path/'outputs/research/fresh/preset';output.mkdir(parents=True)
    saved=output/'native/holosoma_config.yaml';saved.parent.mkdir();saved.write_text('actual: native')
    metric={'samples':1600,'finite':True,'mean':.1,'p95':.2,'max':.3}
    report={'schema_version':1,'status':'completed','checkpoint':case['checkpoint'],'checkpoint_sha256':'c'*64,
        'checkpoint_iteration':1,'num_envs':16,'control_steps':100,'seed':42,
        'registry_order':['file:///data/assets/motions-locomotion'],
        'native_argv':['--checkpoint',case['checkpoint'],*case['native_overrides']],
        'finite_actions':True,'finite_root_states':True,'quality_verified':False,
        'metrics':{key:dict(metric) for key in ['motion/error_ref_pos','motion/error_ref_rot','motion/error_body_pos','motion/error_joint_pos']},
        'failed_resets':43,'timeout_resets':0,'saved_eval_config':'/outputs/fresh/preset/native/holosoma_config.yaml',
        'saved_eval_config_sha256':runner.sha(saved)}
    return case,output/'quality.json',report


def test_quality_gate_keeps_actual_failures_and_does_not_claim_skill_success(tmp_path,monkeypatch):
    case,path,report=quality_fixture(tmp_path,monkeypatch);path.write_text(runner.json.dumps(report))
    evidence=runner.validate_native_quality(case)
    assert evidence['failed_resets']==43 and evidence['physics_verified'] is True and evidence['quality_verified'] is False


@pytest.mark.parametrize('fault',['missing','zero_steps','missing_metric','zero_samples','nonfinite','wrong_pt','config_missing','wrong_asset_argv'])
def test_parent_zero_cannot_pass_missing_or_wrong_native_quality(tmp_path,monkeypatch,fault):
    case,path,report=quality_fixture(tmp_path,monkeypatch)
    if fault=='zero_steps':report['control_steps']=0
    elif fault=='missing_metric':report['metrics'].pop('motion/error_body_pos')
    elif fault=='zero_samples':report['metrics']['motion/error_ref_pos']['samples']=0
    elif fault=='nonfinite':report['finite_actions']=False
    elif fault=='wrong_pt':report['checkpoint_sha256']='d'*64
    elif fault=='config_missing':(path.parent/'native/holosoma_config.yaml').unlink()
    elif fault=='wrong_asset_argv':report['native_argv']+=['--robot.asset.asset-root','/source']
    if fault!='missing':path.write_text(runner.json.dumps(report))
    with pytest.raises(ValueError):runner.validate_native_quality(case)


def test_execute_stops_after_first_zero_exit_without_quality(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    (tmp_path/'outputs/research').mkdir(parents=True)
    monkeypatch.setattr(runner,'inspect',lambda *_:{})
    monkeypatch.setattr(runner,'validate_cpu_receipt',lambda *_:None)
    monkeypatch.setattr(runner,'verify_inputs',lambda *_:None)
    monkeypatch.setattr(runner,'capture',lambda *_:'')
    launches=[]
    monkeypatch.setattr(runner.subprocess,'run',lambda command,**_:launches.append(command) or SimpleNamespace(returncode=0))
    cases=[dict(row(),preset=f'fixture{i}',inputs=[]) for i in range(5)]
    args=SimpleNamespace(cpu_preflight_receipt=tmp_path/'receipt',container_id='b'*64,output=tmp_path/'attempt')
    assert runner.execute(args,{'source_closure':[],'cases':cases})==1
    summary=runner.json.loads((args.output/'execution.json').read_text())
    assert len(launches)==len(summary['cases'])==1 and summary['status']=='execution_failed'
    assert summary['cases'][0]['returncode']==0 and 'without fresh quality.json' in summary['cases'][0]['error']
