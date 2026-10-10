#!/usr/bin/env python3
"""CPU preparation/retention checks only; native training is root-operated separately."""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

LABELS = ('teacher-locomotion', 'student-pure', 'student-finetune')
ROOT = Path('/workspace/php_parkour')
OUTPUT = Path('/outputs')
PIPELINE = OUTPUT/'resume-smoke/smoke'
ENV_KEYS = ('PHP_RESUME_STAGE_ID', 'HSSIM_PYTHON', 'LOGGER', 'WANDB_MODE', 'NGPUS',
            'CUDA_VISIBLE_DEVICES', 'REGISTRY', 'TEACHER_CHECKPOINT', 'FINETUNE',
            'PHP_RESUME_CONTRACT', 'PHP_RESUME_CONTRACT_SHA')


def require(value, message):
    if not value:
        raise ValueError(message)


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink rejected: '+str(path))
    require(stat.S_ISREG(path.stat().st_mode), 'Not a regular file: '+str(path))
    return path


def sha(path):
    digest = hashlib.sha256()
    with regular(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path):
    path = regular(path)
    return {'path':str(path), 'bytes':path.stat().st_size, 'sha256':sha(path)}


def read(path):
    def invalid(token):
        raise ValueError('Nonfinite JSON: '+token)
    return json.loads(regular(path).read_text(), parse_constant=invalid)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False);stream.write('\n')
    path.chmod(0o644)


def verify_record(row, key='path'):
    actual = fingerprint(row[key])
    require(all(actual[k] == row[k] for k in ('bytes','sha256')), 'Sealed file changed: '+str(row[key]))


def load_contract():
    path = Path(os.environ.get('PHP_RESUME_CONTRACT', '/control/contract.json'))
    expected = os.environ.get('PHP_RESUME_CONTRACT_SHA')
    require(expected and sha(path) == expected, 'Explicit frozen contract SHA is required')
    value = read(path)
    require(value['schema_version'] == 1 and value['status'] == 'prepared_not_native_run', 'Unexpected contract')
    require(value['native_output'] == str(PIPELINE.parent), 'Dedicated output changed')
    for row in value['control_files']:
        verify_record(row)
    verify_record(value['source_manifest'])
    return value


def verify_sources(contract, full=False):
    rows = read(contract['source_manifest']['path'])['files'] if full else contract['used_sources']
    for row in rows:
        verify_record(row, 'native_path')
    return len(rows)


def robot_contract():
    from scripts.research.runtime_robot_assets import verify
    value = read(OUTPUT/'runtime-robot-assets-contract.json')
    verify(value)
    return value


def pipeline_argv(label, target, resume=False, skip=False):
    require(label in LABELS, 'Unknown label')
    action = {'teacher-locomotion':'teachers', 'student-pure':'distill-pure',
              'student-finetune':'distill-finetune'}[label]
    argv = ['/opt/php/bin/train-python', str(ROOT/'scripts/research/train_pipeline.py'), action,
            '--profile','smoke','--assets','/data/assets','--output',str(PIPELINE.parent),
            '--skills','locomotion','--num-envs','16','--iterations',str(target)]
    if resume:argv.append('--resume')
    if skip:argv.append('--skip-completed')
    return argv


def stage_manifest(label, target):
    manifest = read(PIPELINE/'manifests'/f'{label}.json')
    require(manifest['label'] == label and manifest['profile'] == 'smoke'
            and manifest['status'] == 'passed' and manifest['returncode'] == 0
            and manifest['checkpoint_iteration'] == target-1, 'Native stage/iteration did not complete')
    require(manifest['settings']['iterations_target'] == target and manifest['settings']['num_envs'] == 16
            and manifest['settings']['skills'] == ['locomotion']
            and manifest['settings']['registries'] == 'file:///data/assets/motions-locomotion', 'Stage settings differ')
    ckpt = regular(manifest['checkpoint'])
    require(ckpt.is_relative_to(PIPELINE/label) and sha(ckpt) == manifest['checkpoint_sha256'], 'Checkpoint source/hash differs')
    return manifest, ckpt


def finite(value, torch):
    if isinstance(value, torch.Tensor):
        require(not (value.is_floating_point() or value.is_complex()) or torch.isfinite(value).all().item(), 'Nonfinite tensor')
        return 1
    if isinstance(value, dict):return sum(finite(v,torch) for v in value.values())
    if isinstance(value, (list,tuple)):return sum(finite(v,torch) for v in value)
    if isinstance(value, float):require(math.isfinite(value), 'Nonfinite scalar')
    return 0


def config_check(data, label, resumed):
    algo = data['algo'];cfg = algo['config'];training = data['training']
    expected = {'teacher-locomotion':'holosoma.agents.ppo.ppo.PPO',
                'student-pure':'wbt_training.utils.student_teacher.PhpDistillation',
                'student-finetune':'wbt_training.utils.student_teacher.PhpDistillationPPO'}[label]
    require(algo['_target_'] == expected and training['num_envs'] == 16 and training['seed'] == 42
            and training['registry_name'] == 'file:///data/assets/motions-locomotion', 'Actual model/training config differs')
    require(cfg['num_learning_iterations'] == (3 if resumed else 2) and cfg['num_steps_per_env'] == 24
            and cfg['num_mini_batches'] == 4 and cfg['num_learning_epochs'] == (5 if label.startswith('teacher') else 2)
            and cfg['save_interval'] == 1, 'Actual update schedule differs')
    require(json.loads(training['preprocess_hook_kwargs']) ==
            {'add_onpath_obstacle':True,'num_variants':1,'obstacle_seed':42}, 'Actual terrain schedule differs')
    require(data['logger']['type'] == 'disabled' and data['robot']['asset']['asset_root'] ==
            str(OUTPUT/'runtime-robot-assets/robots'), 'Logger/public asset override differs')
    if label.startswith('teacher'):
        require(cfg['load_optimizer'] is True, 'PPO optimizer restoration disabled')
    else:
        require(cfg['distillation_warmup_steps'] == 0, 'Warmup override differs')
    return {'algo':expected,'num_envs':16,'steps':24,'mini_batches':4,
            'epochs':cfg['num_learning_epochs'],'num_learning_iterations':cfg['num_learning_iterations'],
            'seed':42,'variants':1,'asset_root':data['robot']['asset']['asset_root']}


def checkpoint(path, label, iteration, resumed):
    import torch
    require(not torch.cuda.is_initialized(), 'CPU science must not initialize CUDA')
    value = torch.load(regular(path), map_location='cpu', weights_only=False)
    require(value['iter'] == iteration and value['iteration'] == iteration, 'PT iteration differs')
    require(finite(value,torch)>0, 'Empty checkpoint')
    config_check(value['experiment_config'], label, resumed)
    if not label.startswith('teacher'):
        require(value['num_teachers'] == 1 and value['teacher_loaded'] == [True], 'Single frozen expert not ready')
    return value


def optimizer_rows(value, label):
    keys = ('actor_optimizer_state_dict','critic_optimizer_state_dict') if label.startswith('teacher') else ('optimizer_state_dict',)
    rows=[]
    for key in keys:
        state=value[key]
        seen=set()
        for gi,group in enumerate(state['param_groups']):
            for pi,param in enumerate(group['params']):
                require(param not in seen,'Duplicate optimizer parameter');seen.add(param)
                require(param in state['state'],'Missing optimizer state')
                item=state['state'][param]
                step=float(item['step'])
                require(step.is_integer() and step>0,'Invalid optimizer step')
                rows.append({'optimizer':key,'group':gi,'position':pi,'parameter_id':param,
                             'step':int(step),'lr':group['lr'],'moment_shape':list(item['exp_avg'].shape)})
        require(set(state['state']) == seen, 'Unbound optimizer states')
    require(rows,'Empty optimizer state')
    return rows


def verify_step_counts(base, first, final, label):
    arrays=[optimizer_rows(x,label) for x in (base,first,final)]
    expected=(40,60,100) if label.startswith('teacher') else (16,24,40)
    skeleton=lambda rows:[{k:r[k] for k in ('optimizer','group','position','parameter_id','moment_shape')} for r in rows]
    require(skeleton(arrays[0])==skeleton(arrays[1])==skeleton(arrays[2]), 'Optimizer parameter/group identity changed')
    for rows,step in zip(arrays,expected):
        require(all(row['step']==step for row in rows), 'Optimizer continuity failed (possible fresh fallback)')
    return {'expected_steps':list(expected),'baseline':arrays[0],'resumed_first':arrays[1],'final':arrays[2]}


def changed(before, after, prefix):
    import torch
    names=[k for k,v in before.items() if k.startswith(prefix) and v.is_floating_point()]
    require(names and set(before)==set(after),'Model keyset differs')
    count=0;norm=0.0
    for name in names:
        require(before[name].shape == after[name].shape, 'Weight shape differs')
        delta=(after[name].double()-before[name].double())
        count+=int(torch.count_nonzero(delta));norm+=float(torch.sum(delta*delta))
    require(count>0 and math.isfinite(norm) and norm>0,'No finite trained weight delta')
    return {'prefix':prefix,'changed_elements':count,'l2':math.sqrt(norm)}


def tree(path):
    result={}
    for p in sorted(Path(path).rglob('*')):
        name=p.relative_to(path).as_posix()
        if p.is_symlink():result[name]={'symlink':os.readlink(p)}
        elif p.is_file():result[name]={'bytes':p.stat().st_size,'sha256':sha(p)}
        else:require(p.is_dir(),'Special output file')
    return result


def archive(label):
    manifest,pt=stage_manifest(label,2)
    dest=OUTPUT/'baseline-archive'/label
    dest.mkdir(parents=True,exist_ok=False)
    paths=[PIPELINE/'manifests'/f'{label}.json',pt,pt.parent/'holosoma_config.yaml',regular(manifest['log'])]
    paths+=list(pt.parent.rglob('events.out.tfevents.*'))
    if label.startswith('teacher'):paths.append(pt.with_suffix('.onnx'))
    else:paths+=[pt.with_suffix('')/name for name in ('student.onnx','depth_backbone.onnx')]
    require(any(p.name.startswith('events.out') for p in paths),'No baseline TB')
    rows=[]
    for i,p in enumerate(paths):
        original=fingerprint(p);q=dest/'files'/f'{i:03d}-{p.name}';q.parent.mkdir(exist_ok=True)
        shutil.copyfile(p,q);q.chmod(0o644);copy=fingerprint(q)
        require(all(copy[k]==original[k] for k in ('bytes','sha256')) and fingerprint(p)==original,'Archive changed during copy')
        rows.append({'original':original,'retained':copy,'fixed_manifest_may_change':p==paths[0]})
    write_new(dest/'archive.json',{'schema_version':1,'status':'archived','label':label,
              'baseline_manifest':manifest,'checkpoint_copy':rows[1]['retained'],'files':rows,
              'scope':'Original bytes copied without rewriting. Not a resumed training claim.'})
    return {'status':'archived','receipt':fingerprint(dest/'archive.json')}


def tb_read(directory, steps):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    events=sorted(Path(directory).rglob('events.out.tfevents.*'));require(events,'No fresh TensorBoard events')
    ea=EventAccumulator(str(directory),size_guidance={'scalars':0});ea.Reload()
    tags=ea.Tags()['scalars'];require(any(x.startswith('Loss/') for x in tags),'No native loss scalars')
    require('Train/num_samples' in tags,'No native sample-count scalars')
    observed=set();loss_steps=set()
    for tag in tags:
        for e in ea.Scalars(tag):
            require(math.isfinite(e.value),'Nonfinite TB scalar')
            observed.add(e.step)
            if tag.startswith('Loss/'):loss_steps.add(e.step)
    require(set(steps)<=observed and set(steps)<=loss_steps,'Missing native update TB steps')
    samples=ea.Scalars('Train/num_samples')
    require(set(steps)<={e.step for e in samples} and all(e.value>0 for e in samples),'Missing native sample-count TB steps')
    return {'expected_steps':steps,'observed_steps':sorted(observed),'loss_steps':sorted(loss_steps),
            'num_samples':[{'step':e.step,'value':e.value} for e in samples],
            'tags':tags,'files':[fingerprint(p) for p in events]}


def verify_resume(label):
    import torch,yaml
    require(not torch.cuda.is_initialized(),'Scientific reader initialized CUDA')
    archived=read(OUTPUT/'baseline-archive'/label/'archive.json')
    for row in archived['files']:
        verify_record(row['retained'])
        if not row['fixed_manifest_may_change']:verify_record(row['original'])
    old=archived['baseline_manifest'];manifest,final_path=stage_manifest(label,4)
    require(manifest['resume_checkpoint']==old['checkpoint'],'Actual resume path differs')
    require(final_path.parent != Path(old['checkpoint']).parent,'Resume logdir collided with baseline')
    require(old['settings']['source_checkpoints']==manifest['settings']['source_checkpoints'],'Fixed teacher source changed')
    if not label.startswith('teacher'):
        teacher,teacher_pt=stage_manifest('teacher-locomotion',4)
        expected=[{'path':str(teacher_pt),'sha256':teacher['checkpoint_sha256']}]
        require(manifest['settings']['source_checkpoints']==expected,'Self PT was mistaken for teacher or teacher changed')
    history=PIPELINE/'manifests/history'
    require(any(sha(p)==archived['files'][0]['original']['sha256'] for p in history.glob(label+'-*.json')),'Original manifest not byte-retained')
    log=regular(manifest['log']).read_text()
    require('Loading' in log and old['checkpoint'] in log and 'Training shutdown complete.' in log,'Missing real native load/shutdown log')
    require('Could not load optimizer state' not in log and 'Exception occurred during training' not in log,'Native restoration/training error')
    original_copy=archived['checkpoint_copy']['path'];first_path=final_path.parent/'model_00001.pt'
    base=checkpoint(original_copy,label,1,False);first=checkpoint(first_path,label,1,True);final=checkpoint(final_path,label,3,True)
    actual_yaml=regular(final_path.parent/'holosoma_config.yaml')
    cfg=yaml.safe_load(actual_yaml.read_text());configuration=config_check(cfg,label,True)
    counters=verify_step_counts(base,first,final,label)
    mixed_std=None
    if label.startswith('teacher'):
        deltas=[changed(base['actor_model_state_dict'],final['actor_model_state_dict'],'actor_module.'),
                changed(base['critic_model_state_dict'],final['critic_model_state_dict'],'')]
    else:
        b=base['model_state_dict'];f=final['model_state_dict']
        deltas=[changed(b,f,'student.'),changed(b,f,'depth_backbone.')]
        if label=='student-finetune':deltas.append(changed(b,f,'critic.'))
        teacher_keys=[k for k in b if k.startswith(('teachers.','teacher_obs_normalizers.','teacher_normalizers.'))]
        require(teacher_keys and all(torch.equal(b[k],f[k]) for k in teacher_keys),'Frozen teacher changed')
        if label=='student-finetune':
            require(abs(final['ppo_coef']-.0003)<1e-9,'Mixed schedule reset')
            rates=[v['optimizer_state_dict']['param_groups'][3]['lr'] for v in (base,first,final)]
            require(rates==[0.0,0.0,0.0],'Early mixed std LR differs from native schedule')
            require(torch.equal(b['std'],first['model_state_dict']['std']) and torch.equal(b['std'],f['std']),
                    'Native LR0 mixed std weights unexpectedly changed')
            mixed_std={'learning_rates':rates,'baseline_final_equal':torch.equal(b['std'],f['std']),
                       'optimizer_steps':[r['step'] for rows in (counters['baseline'],counters['resumed_first'],counters['final']) for r in rows if r['group']==3],
                       'scope':'Native early PPO std LR is zero; state counters advance but a nonzero std weight delta is not required.'}
    baseline_tb=tb_read(Path(old['checkpoint']).parent,[0,1]);new_tb=tb_read(final_path.parent,[1,2,3])
    exec_rows=[]
    for target,resume in ((2,False),(4,True)):
        stage=label+('-resume-target4' if resume else '-baseline-target2')
        matches=list((OUTPUT/'exec-receipts').glob(stage+'-*.json'))
        require(len(matches)==1,'Expected one actual native exec receipt per stage')
        receipt=read(matches[0]);contract=load_contract()
        require(receipt['original_pipeline_argv']==pipeline_argv(label,target,resume), 'Recorded pipeline argv differs')
        require(receipt['source_manifest']==contract['source_manifest']
                and receipt['used_source_fingerprints']==contract['used_sources']
                and receipt['control_files']==contract['control_files'], 'Exec source/transport identity differs')
        before=receipt['python_argv_before_transport'];after=receipt['actual_exec_argv']
        require(before[:2]==['-m','wbt_training.train_agent']
                and after==['/opt/php/bin/train-python',*before,'--robot.asset.asset-root',contract['runtime_root']],
                'Transport changed native training argv')
        require(before[before.index('--training.name')+1]==label
                and before[before.index('--algo.config.num-learning-iterations')+1]==('3' if resume else '2'),
                'Native exec label/remaining iterations differs')
        require(('--training.checkpoint' in before)==resume, 'Actual native self-resume flag differs')
        if resume:require(before[before.index('--training.checkpoint')+1]==old['checkpoint'],'Actual loaded PT path differs')
        require(receipt['environment'].get('WANDB_MODE')=='disabled'
                and receipt['environment'].get('HSSIM_PYTHON')=='/control/train-python-with-robot-assets', 'Exec environment differs')
        exec_rows.append(fingerprint(matches[0]))
    report={'schema_version':1,'status':'passed','label':label,'quality_verified':False,
            'scope':'Actual native single-expert resume execution/state continuity; not convergence or bitwise continuation.',
            'archive_receipt':fingerprint(OUTPUT/'baseline-archive'/label/'archive.json'),
            'original_input':fingerprint(old['checkpoint']),'baseline_copy':fingerprint(original_copy),
            'resumed_first':fingerprint(first_path),'final_checkpoint':fingerprint(final_path),
            'manifest':fingerprint(PIPELINE/'manifests'/f'{label}.json'),'log':fingerprint(manifest['log']),
            'actual_yaml':fingerprint(actual_yaml),'configuration':configuration,'optimizer_steps':counters,'exec_receipts':exec_rows,
            'trained_weight_deltas':deltas,'baseline_tb':baseline_tb,'resumed_tb':new_tb,
            'mixed_std_original_semantics':mixed_std,'cuda_initialized':torch.cuda.is_initialized()}
    require(not report['cuda_initialized'],'CPU science initialized CUDA')
    write_new(OUTPUT/'resume-evidence'/f'{label}.json',report)
    del base,first,final;gc.collect()
    return report


def check_skip(label):
    stage_manifest(label,4)
    before=tree(PIPELINE);receipts=tree(OUTPUT/'exec-receipts')
    env=os.environ.copy();env.update(PHP_RESUME_SKIP_ONLY='1',CUDA_VISIBLE_DEVICES='',
            PHP_RESUME_STAGE_ID=label+'-skip-target4',HSSIM_PYTHON='/control/train-python-with-robot-assets')
    argv=pipeline_argv(label,4,True,True)
    completed=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
    log=OUTPUT/'resume-evidence'/f'{label}-skip.log';log.parent.mkdir(exist_ok=True)
    with log.open('x') as stream:stream.write(completed.stdout+completed.stderr)
    require(completed.returncode==0 and 'Verified checkpoint already reaches target 4' in completed.stdout,'Skip did not take safe completed path')
    require(tree(PIPELINE)==before,'Skip mutated training outputs')
    require(tree(OUTPUT/'exec-receipts')==receipts,'Skip attempted a native child')
    result={'status':'passed','scope':'Actual completed target4 resume+skip; no native-m launch, byte-exact pipeline output tree unchanged.',
            'label':label,'argv':argv,'log':fingerprint(log),'native_child_receipts_unchanged':True,'pipeline_files_unchanged':True}
    write_new(OUTPUT/'resume-evidence'/f'{label}-skip.json',result)
    return result


def verify_onnx(label):
    manifest,pt=stage_manifest(label,4)
    if label.startswith('teacher'):
        argv=['/opt/php/bin/train-python',str(ROOT/'scripts/research/validate_teacher_exports.py'),
              '--output',str(PIPELINE.parent),'--profile','smoke','--skills','locomotion']
        result=PIPELINE/'teacher-onnx-validation/summary.json'
        require(not result.exists(),'ONNX validation report already exists; retain the previous attempt')
        subprocess.run(argv,cwd=ROOT,check=True,timeout=300)
        report=read(result)
        require(report['status']=='passed' and len(report['teachers'])==1
                and report['teachers'][0]['checkpoint_sha256']==manifest['checkpoint_sha256']
                and report['teachers'][0]['cpu_cases']==12,'Teacher ONNX validation differs')
        artifacts=[fingerprint(pt.with_suffix('.onnx')),fingerprint(result),fingerprint(report['teachers'][0]['report'])]
    else:
        result=OUTPUT/'resume-evidence'/f'{label}-onnx-ort.json'
        require(not result.exists(),'ONNX validation report already exists; retain the previous attempt')
        argv=['/opt/php/bin/inference-python',str(ROOT/'scripts/research/validate_onnx.py'),
              '--models',str(pt.with_suffix('')),'--output',str(result)]
        subprocess.run(argv,cwd=ROOT,check=True,timeout=300)
        report=read(result)
        require(report['status']=='passed' and len(report['cases'])==30,'Student ONNX validation differs')
        artifacts=[fingerprint(pt.with_suffix('')/name) for name in ('student.onnx','depth_backbone.onnx')]+[fingerprint(result)]
    value={'status':'passed','label':label,'quality_verified':False,'checkpoint':fingerprint(pt),
           'argv':argv,'artifacts':artifacts,'scope':'Actual native final iter3 auto-export CPU ORT contract; not PT/ONNX parity or policy quality.'}
    write_new(OUTPUT/'resume-evidence'/f'{label}-onnx.json',value)
    return value


def preflight(contract):
    import torch,tyro
    require(not torch.cuda.is_available() and not torch.cuda.is_initialized(),'CPU preparation requires hidden GPU')
    verify_sources(contract,True)
    from scripts.research.runtime_robot_assets import contract as make,prepare,validate_config
    from holosoma.utils.tyro_utils import TYRO_CONIFG
    from wbt_training.config_values.experiment import AnnotatedExperimentConfig
    source=ROOT/'thirdparty/holosoma/src/holosoma/holosoma/data/robots'
    assets=make(source,OUTPUT/'runtime-robot-assets/robots');prepare(assets)
    write_new(OUTPUT/'runtime-robot-assets-contract.json',assets)
    rows=[]
    for label in LABELS:
        preset={'teacher-locomotion':'g1-wbt-terrain-ref-noscale','student-pure':'g1-wbt-terrain-warp-distill',
                'student-finetune':'g1-wbt-terrain-warp-distill-finetune'}[label]
        args=['exp:'+preset,'simulator:isaacsim','logger:disabled','--training.registry-name','file:///data/assets/motions-locomotion',
              '--training.headless','True','--training.num-envs','16','--training.seed','42',
              '--algo.config.num-learning-iterations','2','--algo.config.num-mini-batches','4','--algo.config.save-interval','1',
              '--training.preprocess-hook-kwargs','{"add_onpath_obstacle": true, "num_variants": 1, "obstacle_seed": 42}']
        if not label.startswith('teacher'):args+=['--algo.config.distillation-warmup-steps','0']
        baseline=tyro.cli(AnnotatedExperimentConfig,args=args,config=TYRO_CONIFG)
        actual=tyro.cli(AnnotatedExperimentConfig,args=args+['--robot.asset.asset-root',assets['runtime_root']],config=TYRO_CONIFG)
        b=baseline.to_serializable_dict();a=actual.to_serializable_dict();old=b['robot']['asset']['asset_root'];b['robot']['asset']['asset_root']=a['robot']['asset']['asset_root']
        require(b==a,'Public asset-root override changed another config field')
        config_check(a,label,False);validate_config(actual,assets)
        rows.append({'label':label,'native_tyro_args':args,'old_asset_root':old,'configuration':config_check(a,label,False),'only_asset_root_changed':True})
    # Real native file:// resolution/preprocessing is isolated CPU work; no simulator/object or training loader is called.
    from wbt_training.config_values.terrain import apply_terrain_preprocess
    processed=apply_terrain_preprocess(tyro.cli(AnnotatedExperimentConfig,args=rows[0]['native_tyro_args']+
              ['--robot.asset.asset-root',assets['runtime_root']],config=TYRO_CONIFG),add_onpath_obstacle=True,num_variants=1,obstacle_seed=42)
    result={'status':'passed_cpu_only','native_started':False,'gpu_started':False,'cuda_initialized':torch.cuda.is_initialized(),
            'rows':rows,'robot_assets':assets,'processed_teacher_config':processed.to_serializable_dict(),
            'source_files_verified':len(read(contract['source_manifest']['path'])['files'])}
    require(not result['cuda_initialized'],'CPU preprocessing initialized CUDA')
    write_new(OUTPUT/'cpu-preflight.json',result)
    return {'status':result['status'],'rows':len(rows),'native_started':False,'gpu_started':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','archive','verify-resume','verify-onnx','check-skip'))
    parser.add_argument('--label',choices=LABELS)
    args=parser.parse_args()
    contract=load_contract();verify_sources(contract)
    if args.action=='preflight':result=preflight(contract)
    else:
        require(args.label is not None,'Explicit label required');robot_contract()
        if args.action=='archive':result=archive(args.label)
        elif args.action=='verify-resume':result=verify_resume(args.label)
        elif args.action=='verify-onnx':result=verify_onnx(args.label)
        else:result=check_skip(args.label)
        robot_contract();verify_sources(contract)
    print(json.dumps({'status':result['status'],'label':args.label},allow_nan=False))


if __name__=='__main__':main()
