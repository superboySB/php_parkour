import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
import torch

sys.path.insert(0,'/control')
import resume_evidence as e
loader=importlib.machinery.SourceFileLoader('resume_adapter','/control/train-python-with-robot-assets')
spec=importlib.util.spec_from_loader(loader.name,loader);adapter=importlib.util.module_from_spec(spec);loader.exec_module(adapter)


@pytest.mark.parametrize('argv',[['-','teacher','','file:///data/assets/motions-locomotion'],['-c','print(1)'],['-m','other']])
def test_non_native_passthrough(argv):
    assert adapter.forwarded(argv,'/outputs/runtime-robot-assets/robots')==argv


def test_native_only_appends_public_flag():
    argv=['-m','wbt_training.train_agent','exp:x','--training.checkpoint','/a.pt']
    assert adapter.forwarded(argv,'/rw/robots')==argv+['--robot.asset.asset-root','/rw/robots']
    assert argv[-1]=='/a.pt'


def test_duplicate_asset_override_rejected():
    with pytest.raises(ValueError):adapter.forwarded(['-m','wbt_training.train_agent','--robot.asset.asset-root','/x'],'/y')


@pytest.mark.parametrize('label',e.LABELS)
def test_pipeline_fixed_schedule(label):
    argv=e.pipeline_argv(label,4,True,True)
    assert argv[-2:]==['--resume','--skip-completed']
    assert argv[argv.index('--num-envs')+1]=='16'
    assert argv[argv.index('--skills')+1]=='locomotion'


def test_source_symlink_rejected(tmp_path):
    p=tmp_path/'a';p.write_text('x');q=tmp_path/'link';q.symlink_to(p)
    with pytest.raises(ValueError):e.sha(q)


def test_source_tamper_rejected(tmp_path):
    p=tmp_path/'a';p.write_text('x');row=e.fingerprint(p);p.write_text('y')
    with pytest.raises(ValueError):e.verify_record(row)


def test_write_new_no_overwrite_and_finite(tmp_path):
    p=tmp_path/'a.json';e.write_new(p,{'x':1})
    with pytest.raises(FileExistsError):e.write_new(p,{'x':2})
    q=tmp_path/'b.json';q.write_text('{"x":NaN}')
    with pytest.raises(ValueError):e.read(q)


def optimizer(step):
    return {'state':{0:{'step':torch.tensor(float(step)),'exp_avg':torch.ones(2),'exp_avg_sq':torch.ones(2)}},
            'param_groups':[{'params':[0],'lr':.001}]}


def states(step,label):
    keys=('actor_optimizer_state_dict','critic_optimizer_state_dict') if label.startswith('teacher') else ('optimizer_state_dict',)
    return {k:optimizer(step) for k in keys}


@pytest.mark.parametrize('label',e.LABELS)
def test_optimizer_expected_continuity(label):
    steps=(40,60,100) if label.startswith('teacher') else (16,24,40)
    r=e.verify_step_counts(*(states(s,label) for s in steps),label)
    assert r['expected_steps']==list(steps)


@pytest.mark.parametrize('label',e.LABELS)
def test_optimizer_fresh_fallback_rejected(label):
    steps=(40,20,60) if label.startswith('teacher') else (16,8,24)
    with pytest.raises(ValueError):e.verify_step_counts(*(states(s,label) for s in steps),label)


def test_optimizer_missing_state_rejected():
    data=states(16,'student-pure');data['optimizer_state_dict']['state'].clear()
    with pytest.raises(ValueError):e.optimizer_rows(data,'student-pure')


def test_mixed_std_lr_zero_still_requires_optimizer_state():
    opt={'state':{},'param_groups':[]}
    for i in range(4):
        opt['param_groups'].append({'params':[i],'lr':0.0 if i==3 else .0003})
        opt['state'][i]={'step':torch.tensor(16.0),'exp_avg':torch.ones(2)}
    value={'optimizer_state_dict':opt}
    assert e.optimizer_rows(value,'student-finetune')[-1]['step']==16
    del opt['state'][3]
    with pytest.raises(ValueError,match='Missing optimizer state'):e.optimizer_rows(value,'student-finetune')


def test_optimizer_reordered_identity_rejected():
    a=states(16,'student-pure');b=states(24,'student-pure');c=states(40,'student-pure')
    b['optimizer_state_dict']['param_groups'][0]['params']=[2];b['optimizer_state_dict']['state'][2]=b['optimizer_state_dict']['state'].pop(0)
    with pytest.raises(ValueError):e.verify_step_counts(a,b,c,'student-pure')


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_tensor_rejected(bad):
    with pytest.raises(ValueError):e.finite({'x':torch.tensor([bad])},torch)


def test_zero_trained_delta_rejected():
    a={'student.weight':torch.ones(2)}
    with pytest.raises(ValueError):e.changed(a,copy.deepcopy(a),'student.')
    assert e.changed(a,{'student.weight':torch.zeros(2)},'student.')['changed_elements']==2


def test_archive_preserves_original_bytes(tmp_path,monkeypatch):
    output=tmp_path/'out';pipeline=output/'resume-smoke/smoke';run=pipeline/'teacher-locomotion/run';run.mkdir(parents=True)
    pt=run/'model_00001.pt';pt.write_bytes(b'original-PT');(run/'model_00001.onnx').write_bytes(b'ONNX')
    (run/'holosoma_config.yaml').write_text('x: 1');(run/'events.out.tfevents.test').write_bytes(b'event')
    log=pipeline/'log';log.write_text('native log');(pipeline/'manifests').mkdir()
    manifest={'checkpoint':str(pt),'log':str(log)};(pipeline/'manifests/teacher-locomotion.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(e,'OUTPUT',output);monkeypatch.setattr(e,'PIPELINE',pipeline)
    monkeypatch.setattr(e,'stage_manifest',lambda *_:(manifest,pt))
    before=e.tree(pipeline);e.archive('teacher-locomotion');assert e.tree(pipeline)==before
    retained=e.read(output/'baseline-archive/teacher-locomotion/archive.json')
    for row in retained['files']:assert row['original']['sha256']==row['retained']['sha256']
    with pytest.raises(FileExistsError):e.archive('teacher-locomotion')


def test_actual_tensorboard_loss_steps(tmp_path):
    from torch.utils.tensorboard import SummaryWriter
    writer=SummaryWriter(str(tmp_path));writer.add_scalar('Loss/value',.5,1);writer.add_scalar('Loss/value',.2,2);writer.flush();writer.close()
    assert e.tb_read(tmp_path,[1,2])['loss_steps']==[1,2]
    with pytest.raises(ValueError):e.tb_read(tmp_path,[3])


def test_skip_guard_blocks_native_before_exec(monkeypatch):
    monkeypatch.setattr(adapter,'load_contract',lambda:{'runtime_root':'/x'})
    monkeypatch.setattr(adapter,'verify_sources',lambda *_:None)
    monkeypatch.setenv('PHP_RESUME_SKIP_ONLY','1');monkeypatch.setattr(sys,'argv',['wrapper','-m','wbt_training.train_agent'])
    monkeypatch.setattr(os,'execv',lambda *_:pytest.fail('native exec attempted'))
    with pytest.raises(RuntimeError,match='Skip-only'):adapter.main()


def test_contract_explicit_hash_required(tmp_path,monkeypatch):
    p=tmp_path/'c.json';p.write_text('{}');monkeypatch.setenv('PHP_RESUME_CONTRACT',str(p));monkeypatch.delenv('PHP_RESUME_CONTRACT_SHA',raising=False)
    with pytest.raises(ValueError,match='Explicit frozen'):e.load_contract()


def test_pt_actual_top_level_metadata(tmp_path,monkeypatch):
    p=tmp_path/'x.pt';value={'iter':1,'iteration':1,'experiment_config':{'native':'config'},'actor':torch.ones(1)}
    torch.save(value,p);seen=[];monkeypatch.setattr(e,'config_check',lambda cfg,*_:seen.append(cfg))
    assert e.checkpoint(p,'teacher-locomotion',1,False)['iteration']==1
    assert seen==[{'native':'config'}]
    value['iteration']=3;torch.save(value,p)
    with pytest.raises(ValueError,match='iteration'):e.checkpoint(p,'teacher-locomotion',1,False)


def test_adapter_refuses_wrong_logical_command(tmp_path,monkeypatch):
    monkeypatch.setattr(adapter,'load_contract',lambda:{'runtime_root':'/rw/robots'})
    monkeypatch.setattr(adapter,'verify_sources',lambda *_:None);monkeypatch.setattr(adapter,'robot_contract',lambda:{})
    monkeypatch.delenv('PHP_RESUME_SKIP_ONLY',raising=False)
    monkeypatch.setenv('PHP_RESUME_STAGE_ID','teacher-locomotion-baseline-target2')
    monkeypatch.setenv('PHP_RESUME_LOGICAL_COMMAND_JSON',json.dumps(['unrelated','command']))
    monkeypatch.setattr(sys,'argv',['wrapper','-m','wbt_training.train_agent','--training.name','teacher-locomotion'])
    monkeypatch.setattr(os,'execv',lambda *_:pytest.fail('native exec attempted'))
    with pytest.raises(ValueError,match='pipeline argv differs'):adapter.main()
