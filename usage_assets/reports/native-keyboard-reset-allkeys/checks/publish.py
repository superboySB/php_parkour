"""Publish one completed actual allkeys GUI attempt using only host stdlib."""
from pathlib import Path
from collections import Counter
import ast, datetime, hashlib, html, json, math, re, shutil, struct, zipfile

ROOT = Path('/home/dzp/projects/php_parkour')
RAW = ROOT/'outputs/research/native-keyboard-reset-allkeys-cohort-01'
PREP = ROOT/'outputs/research/native-keyboard-reset-allkeys-preparation-01'
RECOVERY = ROOT/'outputs/research/fresh629-recovery-01'
CARRIER = RECOVERY/'gui-carrier'
PUB = ROOT/'usage_assets/reports/native-keyboard-reset-allkeys'
EXPECTED_PLAN = '422ac089d4208477f0b3822ddbc7aa03268ee2a6e5395868d6dd1473355e2bc8'

def require(value, message):
    if not value: raise ValueError(message)
def fp(path):
    b=path.read_bytes(); return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(path): return json.loads(path.read_bytes())
def identity(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def regular(path):
    require(path.is_file() and not any(p.is_symlink() for p in [path,*path.parents]),'Unsafe source')
def npy(raw):
    require(raw[:6]==b'\x93NUMPY','NPY magic')
    version=tuple(raw[6:8]); n=2 if version==(1,0) else 4
    require(version in [(1,0),(2,0),(3,0)],'NPY version')
    length=int.from_bytes(raw[8:8+n],'little'); head=ast.literal_eval(raw[8+n:8+n+length].decode())
    require(not head['fortran_order'],'Fortran NPZ array unsupported')
    types={'<f4':'f','<i8':'q','<i4':'i'}; require(head['descr'] in types,'Unexpected array dtype')
    code=types[head['descr']]; body=raw[8+n+length:]; size=struct.calcsize('<'+code)
    count=math.prod(head['shape']);require(len(body)==count*size,'NPY payload shape mismatch')
    return head,list(struct.unpack('<'+str(count)+code,body))

plan=read(RAW/'cohort/plan.json'); content=dict(plan); digest=content.pop('plan_sha256')
require(identity(content)==digest==EXPECTED_PLAN,'Plan identity differs')
host=read(RAW/'host/launch-receipt.json'); summary=read(RAW/'outputs/summary.json')
carrier=read(CARRIER/'carrier-receipt.json'); parent=read(CARRIER/'actual-parent-01/process-exit.json')
require(fp(CARRIER/'carrier-receipt.json')['sha256']=='977982053ac7d1450da82568845dfac500690c2566bc39ac67a883b71491d441','Carrier changed')
require(fp(RAW/'host/launch-receipt.json')['sha256']=='092f7d156c2c33a8db49814a7860c57b97479cf404867efd151e1e61cb10a2cb','Host receipt changed')
require(host['status']==summary['status']==carrier['status']=='completed' and parent['actual_wait_returncode']==0,'Actual terminal/parent not zero')
require(not host['errors'] and not carrier['errors'] and host['container_stopped'] and host['plan_sha256']==digest,'Host clean stop missing')
require(all(host[k]==0 for k in ['docker_exec_returncode','docker_exec_final_returncode','observer_returncode']),'Host exits')
require(not summary['cleanup_actions'] and not summary['cleanup_errors'] and summary['quality_verified'] is False,'No forced native cleanup/quality claim')
require(carrier['source_before']==carrier['source_after'],'Carrier sources changed')
worker=read(RAW/'outputs/worker-receipts.json');require(len(worker['workers'])==2 and not worker['cleanup_actions'] and not worker['errors'],'Worker proof')
for w in worker['workers']:
    require(w['return_status']['returncode']==0 and w['process_group']['ownership_state']=='retired_empty'
        and w['process_group']['ownership_verified'] and not w['process_group']['ownership_lost']
        and not w['process_group']['live_members'],'Worker exit/group')
    state=read(RAW/'outputs'/w['role']/'state.json')
    require(state['lifecycle']=='main_returned' and state['last_event']['kind']=='python_atexit','Original native main/atexit')
    require(not re.search(r'Aborted|Segmentation fault|core dumped|Fatal Python error|Traceback \(most recent call last\)|free\(\):',
        (RAW/'outputs'/w['role']/'stdout.txt').read_text()),'Fatal worker text')
    require(host['native_host_pid_mappings'][w['role']]['samples']>0,'Host/native birth map missing')
require(len(summary['recordings'])==len(summary['video_decodes'])==1,'One recording and one video expected')
recording=summary['recordings'][0]; rp=RAW/'outputs'/Path(recording['path']).relative_to('/outputs')
require(fp(rp)=={k:recording[k] for k in ['bytes','sha256']},'NPZ hash')
with zipfile.ZipFile(rp) as z:
    require(set(z.namelist())=={'qpos.npy','vel_cmd.npy','fps.npy'},'Recorded NPZ fields')
    qh,q=npy(z.read('qpos.npy')); vh,v=npy(z.read('vel_cmd.npy')); fh,fps=npy(z.read('fps.npy'))
require(qh['shape']==(424,36) and vh['shape']==(424,15) and fh['shape']==() and fps==[50],'Actual NPZ shapes/fps')
require(all(math.isfinite(x) for x in q+v),'Finite recorded fields')
counts=Counter()
for i in range(424):
    a=v[15*i:15*(i+1)]; b=q[36*i:36*(i+1)]
    require(all(x in [0.,1.] for x in a) and sum(a)==1.,'Recorded one-hot command')
    counts[a.index(1.)]+=1
    require(abs(sum(x*x for x in b[:4])-1.)<.002 and b[4:7]==[0.,0.,0.],'Quaternion/XYZ placeholders')
require(set(counts)==set(range(12)) and min(counts.values())>=10,'All deployed labels')
events=[json.loads(line) for line in (RAW/'outputs/operator-events.jsonl').read_text().splitlines()]
holds=[e for e in events if e['kind']=='direction_hold_verified']; releases=[e for e in events if e['kind']=='direction_release_verified']
require(len(holds)==len(releases)==14 and all(e['label_count_after']-e['label_count_before']>=10 for e in holds),'Actual direction holds')
for mode in [0,1]:
    require({e['keysym'] for e in holds if e['actual_policy']['speed_mode']==mode}==set('wsadqe'),'Both mode six keys')
require(all(e['actual_policy']['active_velocity_command_idx']==0 for e in releases),'Release to zero')
zeros=[e for e in events if e['kind']=='zero_key_verified'];require(len(zeros)==2,'Two held-w z events')
require(all(e['native_zero_dispatch'][0]['command']=='ZERO_VELOCITY' and e['native_zero_dispatch'][0]['before']['active_velocity_command_idx']!=0
    and e['native_zero_dispatch'][0]['after']['active_velocity_command_idx']==0 for e in zeros),'Actual native zero dispatch')
reset=summary['backspace_physical_reset']; before=reset['observation']['before']; after=reset['observation']['after']
require(reset['observation']['scope']=='within_original_render' and before['time']>0 and after['time']==0
    and after['qpos']==after['model_qpos0'] and all(x==0 for x in after['qvel']+after['ctrl'])
    and reset['physics_after']['simulation']['time']>after['time'],'Actual physical reset and subsequent progress')
video=summary['video_decodes'][0];vp=RAW/'outputs'/Path(video['path']).relative_to('/outputs')
require(video['returncode']==0 and '-xerror' in video['command'] and video['command'][-3:]==['-f','null','-']
    and fp(vp)=={k:video[k] for k in ['bytes','sha256']},'Actual full decode and video SHA')

raw_manifest=read(RAW/'manifest.json');require(identity(raw_manifest['files'])==raw_manifest['identity_sha256'],'Raw manifest identity')
sealed={r['relative']:{k:r[k] for k in ['bytes','sha256']} for r in raw_manifest['files']}
require(len(sealed)==len(raw_manifest['files']),'Duplicate raw paths')
PUB.mkdir(exist_ok=False); copied=[]
def copy(source, relative, expected=None):
    regular(source); original=fp(source)
    require(expected is None or expected==original,'Sealed copy source changed: '+str(source))
    target=PUB/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    require(fp(target)==fp(source)==original,'Copy changed')
    copied.append({'source':source.relative_to(ROOT).as_posix(),'relative':relative,**original})
for prefix in ['host','outputs']:
    for path in sorted((RAW/prefix).rglob('*')):
        if not path.is_file():continue
        require(path.name!='private.xauth','Do not publish authentication cookie')
        rel=path.relative_to(RAW).as_posix();require(rel in sealed,'Unsealed actual raw file')
        copy(path,'raw/'+rel,sealed[rel])
for rel in ['cohort/plan.json','manifest.json']:
    copy(RAW/rel,'raw/'+rel,sealed.get(rel))
source=RAW/'cohort/source'
names=['run_php_sim.sh','run_php_inference.sh','scripts/research/run_native_policy.py','scripts/research/run_native_policy.gui-original.py',
    'scripts/research/sim2sim.py','thirdparty/holosoma/src/holosoma/holosoma/run_sim.py',
    'thirdparty/holosoma/src/holosoma/holosoma/run_sim.gui-original.py']
names += [p.relative_to(source).as_posix() for p in sorted((source/'scripts/research/gui_audit').glob('*.py'))]
for rel in names:copy(source/rel,'sources/'+rel,sealed['cohort/source/'+rel])
freeze=read(PREP/'codefreeze.json')
for row in freeze['files']:
    copy(PREP/row['relative'],'original-operator/'+row['relative'],{k:row[k] for k in ['bytes','sha256']})
for rel in ['codefreeze.json','manifest.json']:copy(PREP/rel,'original-operator/'+rel)
for p in sorted(CARRIER.rglob('*')):
    if p.is_file():copy(p,'carrier/'+p.relative_to(CARRIER).as_posix())
copy(ROOT/'outputs/research/host_owned_launch.py','carrier/host_owned_launch.py',{'bytes':(ROOT/'outputs/research/host_owned_launch.py').stat().st_size,'sha256':parent['launcher_sha256']})
for p in sorted((RECOVERY/'controller-adapter').glob('*')):
    if p.is_file():copy(p,'recovery-gate/'+p.name)
copy(Path(__file__),'checks/publish.py')
review={'schema_version':1,'status':'actual_native_allkeys_and_physical_reset_verified','actual_parent_wait_returncode':0,
    'plan_sha256':digest,'image_id':plan['image_id'],'source_manifest_entries':len(plan['files']),
    'original_fourteen_source_hashes_unchanged':True,'carrier_source_before_after_equal':True,
    'recording_count':1,'recording_frames':424,'fps':50,'qpos_shape':[424,36],'vel_cmd_shape':[424,15],
    'command_counts':{str(k):counts[k] for k in sorted(counts)},'actual_direction_holds':len(holds),
    'all_six_keys_both_speed_modes':True,'minimum_observed_hold_ticks':min(e['label_count_after']-e['label_count_before'] for e in holds),
    'zero_native_dispatches_while_w_held':2,'all_releases_zero':True,'worker_exit0_empty_groups':2,'original_main_and_atexit_each_role':True,
    'backspace':{'time_before':before['time'],'time_after':after['time'],'nkey':after['nkey'],'qpos0_max_abs_error':0.,
      'qvel_and_ctrl_all_zero':True,'later_physics_time':reset['physics_after']['simulation']['time'],
      'scope':'MuJoCo physical data reset, not policy history/gantry/SDK reset'},
    'video_count':1,'actual_full_decode_count':1,'independent_redecode_performed':False,'independent_stdlib_npz_validation':True,
    'original_session54334_actual143_preserved':True,'historical_missing_eight_births_not_backfilled':True,
    'quality_verified':False,'hardware_verified':False,'all_media_byte_exact':True,'auth_cookie_excluded':True,
    'external_source_restore':'3313 cohort files are fingerprinted in original raw plan/manifest, not copied as a full source tree; original preparation/restoration evidence remains separately published.'}
write(PUB/'independent-review.json',review)
index='''# 原生 GUI 全方向键与 Backspace 补验

2026-10-10 14:14:52–14:15:32 UTC 的独立原生运行通过：真实父进程 wait0、双方原生 main/atexit 正常返回、两个 wrapper0、出生身份绑定进程组为空、观察器0、独占容器和 Xephyr 已停止。原14份 GUI 源码及既有3313项计划保持不变；新 carrier 只以明确恢复门卫替换旧生命周期前提，原 session54334=143 和八个历史观察缺口仍保留。

低/高速两模式各实际派发 `w/s/a/d/q/e` 并按住至少10个策略 tick，松开回到 command0；两次按住w再发z均观察到原生 ZERO_VELOCITY 事件。`7/8/9/y/g`、模式切换及原生窗口 Backspace 都有真实 XTEST/TTY/状态记录。此次只有 **1份录制、1段视频**：424帧，fps50，qpos424×36、命令424×15，0–11标签全部出现（非零标签最少12帧）。原生录制的 rootXYZ 是零占位，不能当世界轨迹或配对 terrain 训练数据。

Backspace 在原 render 的单次调用前后使 MuJoCo time11.57→0，nkey0、qpos等于model.qpos0、qvel/ctrl为零，随后物理时间继续推进。它证明物理 data reset；没有声称 policy history、gantry 或 SDK 全部 reset。视频已有原始 ffmpeg -xerror 全片解码0，本出版不重解码、不重编码。动作按键和物理重置成功不代表平地策略质量、障碍通关、训练收敛或真实 G1/D435i 验证。

[离线原片与截图](playback.html) · [独立验收](independent-review.json) · [原生summary](raw/outputs/summary.json) · [按键原始事件](raw/outputs/operator-events.jsonl) · [Backspace完整状态](raw/outputs/backspace-reset.json) · [原始host退出](raw/host/launch-receipt.json) · [真实父进程wait](carrier/actual-parent-01/process-exit.json) · [恢复门卫真实0](recovery-gate/root-actual-gate-02.receipt.json) · [SHA清单](publication-manifest.json)。[原CPU准备包](../native-keyboard-reset-allkeys-preparation/index.md)与[旧五次GUI原件](../native-keyboard-gui/summary.md)保持独立，旧双录制不算本次新增数量。

本包保存本次全部host/outputs原始字节、两角色PTY/状态/观察流、NPZ、原MP4/截图、原完整plan/manifest、精确GUI overlays与原14代码、carrier/父wait/两次门卫调用（01失败、02真实通过）。不复制3313源码全树、模型、缓存或Xauth cookie；恢复大依赖请按原plan/manifest及准备包的精确映射，恢复门卫内629+四例证明引用仍属于外部真实cohort，不能修改或补写旧收据。包内原manifest保持原字节，其未复制的大源码条目明确属于外部依赖。
'''
(PUB/'index.md').write_text(index)
vrel='raw/outputs/'+Path(video['path']).relative_to('/outputs').as_posix()
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原生全方向键与Backspace实际补验</title><style>body{font:16px/1.6 system-ui;max-width:1050px;margin:30px auto;padding:0 16px;background:#f5f7fa;color:#182c42}figure{margin:22px 0;padding:16px;background:white;border:1px solid #cdd8e2;border-radius:8px}img,video{width:100%;height:auto}a{color:#075b9d}</style><h1>全方向键与 Backspace：真实平地接口补验</h1><p>原始媒体、无重编码。单个G1接口运行；不代表障碍通关或实机成功。1段视频、1份424帧录制，两个原生worker正常返回。</p><p><a href="index.md">范围/恢复说明</a> · <a href="independent-review.json">验收数据</a> · <a href="raw/outputs/operator-events.jsonl">原始键事件</a> · <a href="publication-manifest.json">SHA</a></p>'''
page+='<figure><video controls preload="none" src="'+html.escape(vrel)+'"></video><figcaption>本次原始离屏视频；原始全片解码0。画面与模拟时间不能证明实时性能或技能质量。</figcaption></figure>'
for name,caption in [('initial-stiff.png','原始可见MuJoCo窗口初态。'),('policy-terminal.png','独占终端原始日志；真实键事件另见原始JSONL。'),('before-backspace.png','原始Backspace前窗口画面。'),('after-backspace.png','原始Backspace后窗口画面；物理重置的定量依据是原render前后time/qpos/qvel/ctrl。'),('all-direction-keys-mode-0.png','低速键批次原始截图，仅表示当时相机视图，不把画面当方向标签或步态成功。'),('all-direction-keys-mode-1.png','高速键批次原始截图，仅表示当时相机视图，不把画面当方向标签或步态成功。'),('viewer-controls-restored.png','7/y/g控制后恢复观察状态的原始截图。')]:
    page+='<figure><img loading="lazy" src="raw/outputs/'+name+'" alt="'+html.escape(caption)+'"><figcaption>'+html.escape(caption)+'</figcaption></figure>'
page+='</html>'; (PUB/'playback.html').write_text(page)
for p in sorted(PUB.rglob('*')):
    if p.is_file() and p.suffix in ['.json','.jsonl','.log','.raw','.txt','.md','.py','.html']:
        data=p.read_bytes()
        require((b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----') not in data and not re.search(rb'(?im)(?:WANDB_API_KEY|AWS_SECRET_ACCESS_KEY|Authorization)\s*[:=]\s*["\x27]?[A-Za-z0-9_/+.-]{16,}',data),'Credential pattern; do not print secret')
for path in [PUB/'index.md',PUB/'playback.html']:
    text=path.read_text(); links=re.findall(r'\]\(([^)]+)\)',text) if path.suffix=='.md' else re.findall(r'(?:href|src)="([^"]+)"',text)
    for link in links:
        if link == 'publication-manifest.json':continue  # Written after this dependency inventory.
        require((path.parent/link.split('#')[0]).exists(),'Missing publication link')
for path in sorted(PUB.rglob('*')):
    if path.is_file() and path.relative_to(PUB).as_posix() not in {r['relative'] for r in copied}:
        copied.append({'source':'generated_from_retained_actual_evidence','relative':path.relative_to(PUB).as_posix(),**fp(path)})
copied.sort(key=lambda r:r['relative'])
write(PUB/'publication-manifest.json',{'schema_version':1,'kind':'byte_exact_actual_native_allkeys_reset_publication',
    'status':'actual_completed_interface_only','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'files':copied,'identity_sha256':identity(copied),'quality_verified':False,'hardware_verified':False,
    'authentication_cookie_excluded':True,'large_source_tree_not_copied':True})
print(json.dumps({'status':'published','directory':str(PUB),'files':len(copied),'bytes':sum(r['bytes'] for r in copied),
    'manifest':fp(PUB/'publication-manifest.json'),'review':fp(PUB/'independent-review.json'),'index':fp(PUB/'index.md')}))
