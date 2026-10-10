"""CPU/stdlib publication of terminal native resume evidence; no native imports."""
from pathlib import Path
from collections import Counter
import datetime, hashlib, json, math, os, re, shutil, struct

ROOT=Path('/home/dzp/projects/php_parkour')
PREP=ROOT/'outputs/research/native-resume-acceptance-preparation-01'
OUT=PREP/'run-output-final-frozen'
OLD=ROOT/'outputs/research/native-resume-root-transaction-recovered-01'
NEW=ROOT/'outputs/research/native-resume-root-transaction-continuation-01'
ADAPTER=ROOT/'outputs/research/native-resume-continuation-cpu-adapter-01/verify_resume.py'
PUB=ROOT/'usage_assets/reports/native-resume-acceptance'
LABELS=['teacher-locomotion','student-pure','student-finetune']
LIMIT=25_000_000

def require(value,message):
    if not value:raise ValueError(message)
def fp(p):
    p=Path(p);require(p.is_file() and not any(x.is_symlink() for x in [p,*p.parents]),'Regular source required')
    before=p.stat();h=hashlib.sha256()
    with p.open('rb') as s:
        for b in iter(lambda:s.read(4*1024*1024),b''):h.update(b)
    after=p.stat();require((before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Source changed')
    return {'bytes':before.st_size,'sha256':h.hexdigest()}
def read(p):return json.loads(p.read_bytes())
def ident(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def native_path(value):
    path=Path(value);require(path.is_absolute() and '..' not in path.parts,'Unsafe fingerprint path')
    if path.is_relative_to(ROOT):return path
    for prefix,target in [('/outputs',OUT),('/control',PREP/'control'),('/workspace/php_parkour',PREP/'source')]:
        if path.is_relative_to(prefix):return target/path.relative_to(prefix)
    raise ValueError('Unknown scientific fingerprint namespace: '+str(path))
records={}
def proof_files(v):
    if isinstance(v,dict):
        if v.get('fixed_manifest_may_change') is True:
            proof_files(v['retained']);return
        if {'path','bytes','sha256'}<=set(v):
            p=native_path(v['path']);expected={k:v[k] for k in ['bytes','sha256']}
            require(fp(p)==expected,'Scientific referenced bytes changed: '+str(p));records[p]=expected
        for item in v.values():proof_files(item)
    elif isinstance(v,list):
        for item in v:proof_files(item)

old=read(OLD/'actual/receipt.json');old_parent=read(OLD/'actual-parent-01/process-exit.json')
new=read(NEW/'actual/receipt.json');parent01=read(NEW/'actual-parent-01/process-exit.json');parent02=read(NEW/'actual-parent-02/process-exit.json')
require(old['status']=='failed' and old_parent['actual_wait_returncode']==1 and not old['cleanup_errors'],'Retain original failed1')
require(parent01['actual_wait_returncode']==1 and 'Selected GPU already has compute processes' in (NEW/'actual-parent-01/stderr.raw').read_text(),'Retain first continuation preflight1')
require(new['status']=='completed' and parent02['actual_wait_returncode']==0 and not new['cleanup_errors'],'Actual continuation not completed0')
require(fp(NEW/'run.py')['sha256']=='fe2b1822e7bda774f09fca856d76e8fbe993a0cb854ef513356d3151c3410095'
    and fp(ADAPTER)['sha256']=='5c552a2e9470a243e81ba9e1615d39fa04a30f51405611e837105bc10c8cdcc1','Actual continuation/CPU adapter differs')
require(new['historical_command_exit0_count']==3 and new['new_command_exit0_count']==15 and new['aggregate_command_exit0_count']==18
    and new['historical_native_call_count']==2 and new['new_native_call_count']==4
    and new['native_kit_mapping_count']==new['wrapper_mapping_count']==6 and new['cpu_validation_count']==12,'Aggregate real counts differ')
require(new['input_postcheck_unchanged'] and old['input_postcheck_unchanged']
    and new['owned_container_stop']['running_after_stop'] is False and old['owned_container_stop']['running_after_stop'] is False,'Actual input/stop proofs missing')
require(read(NEW/'actual/input-before.json')==read(NEW/'actual/input-after.json')==read(OLD/'actual/input-before.json')==read(OLD/'actual/input-after.json'),'Source pre/post differs')
aggregate=new['historical_prefix']['steps']+new['steps'];require(len(aggregate)==18 and all(r['returncode']==0 for r in aggregate),'Accepted steps not18 zero')
native=[r for r in aggregate if r['kind']=='actual_native_training_future_only'];require(len(native)==6,'Native count')
for r in native:
    require(r['wrapper_mapping']['host_pid']!=r['kit_mapping']['host_pid'] and r['ancestry'][0]==r['kit_mapping']
        and r['ancestry'][-1]==r['wrapper_mapping'] and len(r['idle_after']['processes'])==2,'Real wrapper/Kit/idle proof')
    proof_files(r['native_exec_receipt'])
for row in aggregate:
    for k in ['stdout','stderr','process_samples']:proof_files(row[k])
reports={}
for label in LABELS:
    for suffix in ['', '-onnx', '-skip']:
        p=OUT/'resume-evidence'/(label+suffix+'.json');d=read(p)
        require(d['status']=='passed' and d['label']==label,'Scientific report must pass')
        proof_files(d);reports[label+suffix]=d
    d=reports[label];require(d['quality_verified'] is False and d['cuda_initialized'] is False,'No quality/GPU-science claim')
    require(d['optimizer_steps']['expected_steps']==([40,60,100] if label.startswith('teacher') else [16,24,40]),'Original strict optimizer continuity')
    require(all(x['changed_elements']>0 and math.isfinite(x['l2']) and x['l2']>0 for x in d['trained_weight_deltas']),'Actual trained weight delta')
    archive=read(OUT/'baseline-archive'/label/'archive.json');proof_files(archive)
    side=read(OUT/'continuation-admission'/(label+'-shutdown-log-validation.json'))
    require(side['status']=='actual_native_zero_kit_gone_and_shutdown_begin_verified' and side['simulation_app_close_return_verified'] is False,'Explicit limited log proof')
    proof_files(side)

# Retain all actual host/transport records and all small training output/log/TB
# evidence. Only PT/ONNX needed by strict reports/archives enter the model closure.
sources={};symlinks=[]
def select_tree(base,prefix):
    for p in sorted(base.rglob('*')):
        if p.is_file():sources[p]=prefix+'/'+p.relative_to(base).as_posix()
select_tree(OLD,'failed-teacher-attempt');select_tree(NEW,'continuation')
for p in sorted(OUT.rglob('*')):
    if p.is_symlink():
        target=p.resolve(strict=True);require(target.is_relative_to(OUT),'External output symlink')
        symlinks.append({'source':p.relative_to(ROOT).as_posix(),'restore_relative':'actual-output/'+p.relative_to(OUT).as_posix(),
            'original_target':os.readlink(p),'relative_target':os.path.relpath(target,p.parent),'target_source':target.relative_to(ROOT).as_posix()})
        continue
    if not p.is_file() or p.is_relative_to(OUT/'runtime-robot-assets'):continue
    if p.suffix in ['.pt','.onnx'] and p not in records:continue
    sources[p]='actual-output/'+p.relative_to(OUT).as_posix()
for p in records:
    if p.is_relative_to(OUT):sources[p]='actual-output/'+p.relative_to(OUT).as_posix()
for rel in ['readiness.json','preparation-manifest.json','root-commands.json','source-manifest.json','registry-inputs.json',
            'control/contract.json','control/resume_evidence.py','control/native_exec_adapter.py','control/train-python-with-robot-assets']:
    p=PREP/rel
    if p.exists():sources[p]='original-controls/'+rel
for rel in ['runtime-robot-assets-contract.json','runtime-robot-assets/manifest.json']:
    sources[OUT/rel]='original-inputs/'+rel
sources[ADAPTER]='cpu-log-adapter/verify_resume.py';sources[Path(__file__).resolve()]='checks/publish.py'
launcher=ROOT/'outputs/research/host_owned_launch.py';require(fp(launcher)['sha256']==parent02['launcher_sha256'],'Parent launcher source differs')
sources[launcher]='controls/host_owned_launch.py'

PUB.mkdir(exist_ok=False);copied=[];large=[];chunks={}
def retained(source,relative,expected=None):
    original=fp(source);require(expected is None or original==expected,'Seal before copy differs')
    if original['bytes']<=LIMIT:
        target=PUB/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        require(fp(target)==fp(source)==original,'Original byte copy changed')
        copied.append({'source':source.relative_to(ROOT).as_posix(),'relative':relative,**original});return
    digest=original['sha256']
    if digest not in chunks:
        part_records=[];whole=hashlib.sha256();offset=0
        with source.open('rb') as stream:
            for index,block in enumerate(iter(lambda:stream.read(LIMIT),b'')):
                name=f'large-files/{digest}/part-{index:04d}.bin';target=PUB/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(block);value={'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()}
                require(fp(target)==value,'Chunk changed');copied.append({'source':source.relative_to(ROOT).as_posix()+f'#bytes={offset}:{offset+len(block)}','relative':name,**value})
                part_records.append({'relative':name,'offset':offset,**value});offset+=len(block);whole.update(block)
        require(offset==original['bytes'] and whole.hexdigest()==digest and fp(source)==original,'Whole chunked source changed')
        chunks[digest]=part_records
    large.append({'source':source.relative_to(ROOT).as_posix(),'restore_relative':relative,**original,'chunks':chunks[digest]})
for source,relative in sorted(sources.items(),key=lambda x:x[1]):retained(source,relative,records.get(source))
write(PUB/'large-file-restoration.json',{'schema_version':1,'chunk_limit_bytes':LIMIT,'all_original_bytes_preserved':True,'files':large})
write(PUB/'symlink-restoration.json',{'schema_version':1,'scope':'Three native latest-log aliases; exact original link text retained, no symlink followed into publication','files':symlinks})

# Decode native SummaryWriter scalar records without a host TensorBoard install.
def fields(data):
    def varint(i):
        n=shift=0
        while True:
            b=data[i];i+=1;n|=(b&127)<<shift
            if b<128:return n,i
            shift+=7;require(shift<70,'Invalid protobuf varint')
    i=0
    while i<len(data):
        key,i=varint(i);number,wire=key>>3,key&7
        if wire==0:value,i=varint(i)
        elif wire in [1,5]:size=8 if wire==1 else 4;value=data[i:i+size];i+=size
        elif wire==2:size,i=varint(i);value=data[i:i+size];i+=size
        else:raise ValueError('Unexpected native event protobuf wire')
        require(i<=len(data),'Truncated event protobuf');yield number,wire,value
def crc32c(data):
    crc=0xffffffff
    for b in data:
        crc^=b
        for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
    crc^=0xffffffff;return (((crc>>15)|(crc<<17))+0xa282ead8)&0xffffffff
tb=[]
for path in sorted(OUT.rglob('events.out.tfevents.*')):
    raw=path.read_bytes();offset=0;scalars=[]
    while offset<len(raw):
        require(len(raw)-offset>=16,'Truncated TFRecord');length=raw[offset:offset+8];count=struct.unpack('<Q',length)[0]
        require(crc32c(length)==struct.unpack('<I',raw[offset+8:offset+12])[0],'TFRecord length CRC')
        data=raw[offset+12:offset+12+count];require(len(data)==count and crc32c(data)==struct.unpack('<I',raw[offset+12+count:offset+16+count])[0],'TFRecord data CRC')
        step=0;wall=None;summaries=[]
        for number,wire,value in fields(data):
            if number==1 and wire==1:wall=struct.unpack('<d',value)[0]
            elif number==2 and wire==0:step=value
            elif number==5 and wire==2:summaries.append(value)
        for summary in summaries:
            for number,wire,value in fields(summary):
                if number!=1 or wire!=2:continue
                tag=None;scalar=None
                for field,kind,item in fields(value):
                    if field==1 and kind==2:tag=item.decode()
                    elif field==2 and kind==5:scalar=struct.unpack('<f',item)[0]
                if scalar is not None:
                    require(tag and math.isfinite(scalar),'Nonfinite scalar');scalars.append({'tag':tag,'step':step,'value':scalar,'wall_time':wall})
        offset+=count+16
    require(scalars,'No actual SummaryWriter simple-value scalars')
    tb.append({'source':path.relative_to(ROOT).as_posix(),'retained_relative':sources[path],**fp(path),'scalars':scalars})
write(PUB/'tensorboard-scalars.json',{'schema_version':1,'status':'native_event_simple_value_scalars_read','all_crc32c_verified':True,
    'source':'Original unmodified native TensorBoard Event/TFRecord bytes; no host packages installed','files':tb})
review={'schema_version':1,'status':'actual_native_three_algorithm_resume_verified','quality_verified':False,'bitwise_continuation_verified':False,
    'actual_parent_wait_returncode':0,'historical_failed_teacher_attempt_returncode':1,'first_continuation_preflight_returncode':1,
    'first_continuation_gpu_occupancy_cause':'unknown; no contemporaneous compute PID snapshot retained',
    'new_command_exit0_count':15,'historical_command_exit0_count':3,'aggregate_command_exit0_count':18,
    'new_native_call_count':4,'historical_native_call_count':2,'real_wrapper_birth_count':6,'real_kit_birth_count':6,
    'strict_cpu_scientific_report_count':12,'old_and_new_owned_containers_stopped':True,'input_before_after_equal':True,
    'cpu_preparation_33tests_not_counted_as_native_execution':True,'labels':{},'large_original_files':len(large),'unique_chunked_blobs':len(chunks),
    'tensorboard_event_files':len(tb),'tensorboard_actual_scalar_points':sum(len(x['scalars']) for x in tb),
    'log_admission':'Original close() may terminate Python before post-close INFO. Only exact load+shutdown-begin+actual native0 and observed Kit gone are admitted; no complete close-return claim.'}
for label in LABELS:
    d=reports[label];review['labels'][label]={'optimizer_expected_steps':d['optimizer_steps']['expected_steps'],
        'actual_update_schedule':d['configuration'],'trained_weight_deltas':d['trained_weight_deltas'],
        'baseline_tb_steps':d['baseline_tb']['observed_steps'],'resumed_tb_steps':d['resumed_tb']['observed_steps'],
        'resume_report':'actual-output/resume-evidence/'+label+'.json','onnx_report':'actual-output/resume-evidence/'+label+'-onnx.json',
        'skip_report':'actual-output/resume-evidence/'+label+'-skip.json',
        'shutdown_log_sidecar':'actual-output/continuation-admission/'+label+'-shutdown-log-validation.json'}
write(PUB/'independent-review.json',review)

restore='''#!/usr/bin/env python3
"""Restore exact chunked files below a fresh chosen directory; no native execution."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
root=a.package.resolve(strict=True);destination=a.destination.absolute();destination.mkdir(parents=True,exist_ok=True)
for row in json.loads((root/'large-file-restoration.json').read_bytes())['files']:
 rel=Path(row['restore_relative']);assert not rel.is_absolute() and '..' not in rel.parts
 target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True)
 assert not any(x.is_symlink() for x in [target,*target.parents])
 h=hashlib.sha256();offset=0
 with target.open('xb') as output:
  for chunk in row['chunks']:
   rel=Path(chunk['relative']);assert not rel.is_absolute() and '..' not in rel.parts and offset==chunk['offset']
   data=(root/rel).read_bytes();assert len(data)==chunk['bytes'] and hashlib.sha256(data).hexdigest()==chunk['sha256']
   output.write(data);h.update(data);offset+=len(data)
 assert offset==row['bytes'] and h.hexdigest()==row['sha256']
print('Restored',len(json.loads((root/'large-file-restoration.json').read_bytes())['files']),'byte-exact files; no training started')
'''
(PUB/'restore_large_files.py').write_text(restore)
index='''# 三类原生续训真实验收

本包是16环境、teacher/Pure DAgger/DAgger+PPO各baseline target2→resume target4的实际接口/优化器状态连续性验收。真实训练共6次，宿主实际观察到6个wrapper和6个不同的Kit Python子进程出生/namespace/祖先链；每次原生训练返回0并回到仅init/sleep的独占容器空闲状态。历史已完成3步 + 新continuation15步组成原18步，3类各原生resume、ONNX CPU检查、达目标skip均通过。既有33个CPU准备测试仍属于单独[准备包](../native-resume-acceptance-preparation/index.md)，不计作这6次真实训练。

教师optimizer严格40→60→100，两个学生严格16→24→40；原生恢复从保存iter1继续，首份新checkpoint仍为iter1，最终iter3。故不能把同名model_00001误当原baseline字节，也不能称只新增两轮。原科学读取同时检查PT迭代/配置、optimizer参数及moment形状/步数、非零有限权重变化、教师冻结、学生mixed std原语义、真实TB更新以及auto-export ONNX和不启动native的skip。它不证明bitwise继续、训练收敛、正式7模型完成或策略质量。

两次失败原件永久保留：最早教师baseline/archive/resume三步真实0后，第4 CPU读日志过度要求close之后的`Training shutdown complete.`而失败，原父wait1/自有容器已停止。原Isaac `simulation_app.close()`可能直接终止Python，所以新adapter仅修改原科学模块对象的native_load_log：精确原生checkpoint加载 + shutdown-begin + 真实native0/Kit已退出。教师有optimizer成功INFO；学生源码成功时没有该句，仍用原严格optimizer实质计数。sidecar明确close()返回未证明，不伪造缺失日志，不覆盖失败报告。

第一次continuation仅在GPU空闲门卫退出1，未建容器/未建actual/admission/未训练；当时占用原因未知，未保留同期compute PID快照。Root随后另存真实UUID空闲查询，显式第二次启动同冻结helper，actual-parent-02最终wait0，两个父回执都保留。第二次续跑复用教师已0前三步，从第4步开始执行15步，没有重训或覆盖老师。原session54334=143、原629观察缺口及四例补验恢复合同仍原样保留。

[独立验收](independent-review.json) · [实际continuation收据](continuation/actual/receipt.json) · [最终真实父wait0](continuation/actual-parent-02/process-exit.json) · [第一次GPU预检父wait1](continuation/actual-parent-01/process-exit.json) · [原教师失败父wait1](failed-teacher-attempt/actual-parent-01/process-exit.json) · [实际TB标量](tensorboard-scalars.json) · [分块还原映射](large-file-restoration.json) · [SHA清单](publication-manifest.json)。三类独立报告链接见independent-review的labels；原始TB events、训练/导出/skip日志、18step stdout/stderr与进程流、native exec receipts、baseline归档、固定输入/源清单均保存。

PT/ONNX仅保存原科学报告与baseline归档所需的闭包，不复制3298源码全树、35个机器人mesh、缓存或其它未使用中间checkpoint。大于25,000,000字节的原PT/进程流按连续offset分块，原wholeSHA与每块SHA完整保留，无压缩/重编码；重复大文件只共用相同wholeSHA的块。运行 `python3 -B restore_large_files.py --package . --destination /绝对路径/新还原目录` 可重建大文件到restore_relative，对已存在文件拒绝覆盖。原报告的容器绝对路径不重写；需按actual-output与原source/inputs/controls映射恢复环境，不能在活cohort上覆盖。原prepared状态和CPU-only措辞是历史准备代理范围，不表示需要再向用户申请训练授权。
'''
(PUB/'index.md').write_text(index)
for p in PUB.rglob('*'):
    if p.is_file() and p.suffix in ['.json','.jsonl','.txt','.log','.raw','.py','.md']:
        data=p.read_bytes();require((b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----') not in data and not re.search(rb'(?im)(?:WANDB_API_KEY|AWS_SECRET_ACCESS_KEY|Authorization)\s*[:=]\s*["\x27]?[A-Za-z0-9_/+.-]{16,}',data),'Potential credential pattern, do not print secret')
for link in re.findall(r'\]\(([^)]+)\)',index):
    if link!='publication-manifest.json':require((PUB/link).exists(),'Missing package link')
for p in sorted(PUB.rglob('*')):
    if p.is_file() and p.relative_to(PUB).as_posix() not in {r['relative'] for r in copied}:
        copied.append({'source':'generated_from_actual_retained_evidence','relative':p.relative_to(PUB).as_posix(),**fp(p)})
copied.sort(key=lambda r:r['relative']);require(max(r['bytes'] for r in copied)<=LIMIT,'Publication item exceeds25MB')
write(PUB/'publication-manifest.json',{'schema_version':1,'kind':'byte_exact_actual_native_resume_acceptance','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status':'actual_18_steps_three_algorithm_resume_verified','files':copied,'identity_sha256':ident(copied),
    'original_failure1_retained':True,'first_continuation_preflight1_retained':True,'quality_verified':False,'chunk_limit_bytes':LIMIT})
print(json.dumps({'status':'published','files':len(copied),'bytes':sum(r['bytes'] for r in copied),'large_files':len(large),'unique_chunked_blobs':len(chunks),
    'manifest':fp(PUB/'publication-manifest.json'),'review':fp(PUB/'independent-review.json'),'index':fp(PUB/'index.md')}))
