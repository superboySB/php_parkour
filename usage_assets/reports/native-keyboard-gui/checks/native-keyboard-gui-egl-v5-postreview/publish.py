"""CPU-only byte-preserving publication of the five actual GUI attempts."""
from pathlib import Path
import hashlib,html,json,re,shutil,time
PROJECT=Path('/home/dzp/projects/php_parkour')
PUB=PROJECT/'usage_assets/reports/native-keyboard-gui'
ROOT=PROJECT/'outputs/research'
EXPECTED='95498d688d2fc84d3c0fc7da8d66e63a04ebb59907e3116c0a9ca8f6a1a94aca'
ATTEMPTS=[
 ('01-auth-failed','native-keyboard-gui-prepared-final','native-keyboard-gui-runner-proposal','failed','Private Python-Xlib authorization failed; no native workers constructed'),
 ('02-settle-failed','native-keyboard-gui-prepared-auth-final','native-keyboard-gui-runner-auth-v2','failed','1000 physics ticks not reached inside original12wall-second deadline; no keys yet'),
 ('03-terminal-failed','native-keyboard-gui-prepared-settle-final','native-keyboard-gui-runner-settle-v3','failed','MuJoCo8/9 acknowledged; Tk logical focus missing, XTEST ] produced no PTY byte'),
 ('04-native-exit-failed','native-keyboard-gui-prepared-terminal-final','native-keyboard-gui-runner-terminal-v4','failed','All interface actions/recordings completed; simulator allocator abort after atexit, wrapper1'),
 ('05-egl-completed','native-keyboard-gui-prepared-egl-final','native-keyboard-gui-runner-egl-v5','completed','Same native interface workflow with EGL offscreen; both original mains returned and actual wrappers0')]

def fp(path):
 b=path.read_bytes();return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
def ident(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def read(path):return json.loads(path.read_text())
def safe(path,root):
 if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or not path.is_file():raise ValueError('Unsafe artifact path')
def copy(path,dest,expected=None):
 safe(path,path.parent)
 before=fp(path)
 if expected is not None and before!=expected:raise ValueError('Sealed source changed before copy: '+str(path))
 dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
 if fp(dest)!=before or fp(path)!=before:raise ValueError('Copied bytes/source changed: '+str(path))
 return before

def verify_attempt(directory,expected_status):
 m=read(directory/'manifest.json');seen=set()
 for row in m['files']:
  rel=Path(row['relative'])
  if rel.is_absolute() or '..' in rel.parts or str(rel) in seen:raise ValueError('Unsafe/duplicate original manifest')
  seen.add(str(rel));path=directory/rel;safe(path,directory)
  if fp(path)!={k:row[k] for k in ('sha256','bytes')}:raise ValueError('Original frozen artifact changed: '+str(path))
 p=read(directory/'cohort/plan.json');content=dict(p);digest=content.pop('plan_sha256');assert ident(content)==digest
 h=read(directory/'host/launch-receipt.json');s=read(directory/'outputs/summary.json')
 assert s['status']==h['status']==expected_status and s['plan_sha256']==h['plan_sha256']==digest
 assert h['container_stopped'] and h['xephyr_final_group']['live_members']==[] and h['xephyr_final_group']['ownership_verified']
 return m,p,h,s

verified=[verify_attempt(ROOT/name,status) for _,name,_,status,_ in ATTEMPTS]
manifest,plan,host,summary=verified[-1]
assert plan['plan_sha256']==EXPECTED and host['docker_exec_final_returncode']==0 and host['observer_returncode']==0
assert summary['cleanup_actions']==[] and summary['cleanup_errors']==[] and not summary['quality_verified'] and not summary['obstacle_course_completion_verified']
worker=read(ROOT/ATTEMPTS[-1][1]/'outputs/worker-receipts.json');assert not worker['cleanup_actions'] and not worker['errors']
for w in worker['workers']:
 assert w['return_status']['returncode']==0 and w['process_group']['ownership_verified'] and w['process_group']['live_members']==[] and not w['process_group']['ownership_lost']
 state=read(ROOT/ATTEMPTS[-1][1]/'outputs'/w['role']/'state.json')
 assert state['lifecycle']=='main_returned' and state['last_event']['kind']=='python_atexit'
 text=(ROOT/ATTEMPTS[-1][1]/'outputs'/w['role']/'stdout.txt').read_text()
 assert not re.search(r'Aborted|Segmentation fault|core dumped|Fatal Python error|Traceback \(most recent call last\)|free\(\):',text)
 assert w['role'] in host['native_host_pid_mappings'] and host['native_host_pid_mappings'][w['role']]['samples']>0
cpu=read(ROOT/'native-keyboard-gui-egl-v5-postreview/npz-video-postcheck.json')
assert cpu['status']=='cpu_recording_and_video_fields_verified' and len(cpu['recordings'])==2 and len(cpu['videos'])==1
for report in cpu['recordings']+cpu['videos']:
 path=ROOT/ATTEMPTS[-1][1]/'outputs'/Path(report['path']).relative_to('/raw/outputs');assert fp(path)['sha256']==report['sha256']
assert cpu['videos'][0]['full_decode']['returncode']==0
PUB.mkdir(exist_ok=False)
rows=[]
for (label,name,runner,status,reason),(manifest,plan,host,summary) in zip(ATTEMPTS,verified):
 directory=ROOT/name;target=PUB/'attempts'/label
 sealed={r['relative']:{k:r[k] for k in ('sha256','bytes')} for r in manifest['files']}
 copied=[]
 for prefix in ('host','outputs'):
  for path in sorted((directory/prefix).rglob('*')):
   if not path.is_file():continue
   rel=path.relative_to(directory).as_posix()
   if rel=='host/private.xauth':continue
   if rel not in sealed:raise ValueError('Unsealed raw artifact: '+rel)
   copy(path,target/rel,sealed[rel]);copied.append(rel)
 for rel in ('cohort/plan.json','manifest.json'):
  copy(directory/rel,target/rel,sealed.get(rel))
 # Exact diagnostic overlays, original originals, wrappers and ownership bootstrap.
 source=directory/'cohort/source'
 source_paths=['run_php_sim.sh','run_php_inference.sh','scripts/research/run_native_policy.py','scripts/research/run_native_policy.gui-original.py','scripts/research/sim2sim.py','thirdparty/holosoma/src/holosoma/holosoma/run_sim.py','thirdparty/holosoma/src/holosoma/holosoma/run_sim.gui-original.py']
 source_paths += [p.relative_to(source).as_posix() for p in sorted((source/'scripts/research/gui_audit').glob('*.py'))]
 for rel in source_paths:copy(source/rel,target/'sources'/rel,sealed['cohort/source/'+rel])
 run=ROOT/runner
 for rel in ('root-native-launch.log','ready-review.json','manifest.json','README.md'):
  path=run/rel
  if path.exists():copy(path,target/'operator'/rel)
 entries=[r for r in ('simulator','inference') if (directory/'outputs'/r/'process-entry.json').exists()]
 exitcodes=[]
 wr=directory/'outputs/worker-receipts.json'
 if wr.exists():exitcodes=[{'role':w['role'],'wrapper_returncode':w['return_status']['returncode'],'known_owned_group_empty':w['process_group'].get('live_members')==[]} for w in read(wr)['workers']]
 rows.append({'id':label,'status':status,'scope':reason,'original_source_directory':str(directory),'plan_sha256':plan['plan_sha256'],'image_id':plan['image_id'],'original_manifest':fp(directory/'manifest.json'),'original_manifest_records_verified':len(manifest['files']),'raw_files_copied':len(copied),'native_worker_entries':entries,'wrapper_exitcodes':exitcodes,'error':summary.get('error'),'source_after_identity':plan['source_after_identity'],'diagnostic_overlays':plan['diagnostic_overlays'],'operator_helpers':plan['operator_helpers'],'raw_directory':'attempts/'+label,'original_outputs':'attempts/'+label+'/outputs','native_objects_constructed':bool(entries),'finished_unix':host['finished_unix']})
# Independent CPU records, raw primary installed sources and explicit compose one-line change.
checks=PUB/'checks'
for name in ('native-keyboard-gui-egl-v5-postreview','native-keyboard-gui-terminal-v4-postreview'):
 for p in sorted((ROOT/name).glob('*')):
  if p.is_file():copy(p,checks/name/p.name)
for name in ('cpu-tests-egl-final','cpu-imports-egl-final'):
 for p in sorted((ROOT/'native-keyboard-gui-runner-egl-v5'/name).rglob('*')):
  if p.is_file():copy(p,checks/name/p.relative_to(ROOT/'native-keyboard-gui-runner-egl-v5'/name))
for directory in ('private-terminal-cpu-probe','cpu-tests-terminal-final'):
 source=ROOT/'native-keyboard-gui-runner-terminal-v4'/directory
 for p in sorted(source.rglob('*')):
  if p.is_file() and p.name!='private.xauth':copy(p,checks/directory/p.relative_to(source))
before=ROOT/ATTEMPTS[-1][1]/'cohort/source/docker/compose.gui.yml';after=PROJECT/'docker/compose.gui.yml'
assert before.read_text().replace('MUJOCO_GL: glfw','MUJOCO_GL: egl')==after.read_text()
copy(before,PUB/'compose/compose.gui.before.yml');copy(after,PUB/'compose/compose.gui.after.yml');copy(ROOT/'native-keyboard-gui-runner-egl-v5/production-compose-config.json',PUB/'compose/production-compose-config.json')
config=read(PUB/'compose/production-compose-config.json');assert config['services']['php']['environment']['MUJOCO_GL']=='egl'
events=[json.loads(s) for s in (ROOT/ATTEMPTS[-1][1]/'outputs/operator-events.jsonl').read_text().splitlines()]
keyevents=[e for e in events if e['kind'] in ('real_terminal_key_to_pty','xtest_direction_down_requested','xtest_direction_up_requested','acknowledged','normal_interrupt_requested','normal_interrupt_completed')]
review={'schema_version':1,'status':'completed_interface_workflow_independently_verified','scope':'One G1 native ONNX policy interface test on plane in private Xephyr/Docker, not obstacle or robot-hardware success','reviewed_unix':time.time(),'successful_plan_sha256':EXPECTED,'image_id':plan['image_id'],'attempts':rows,'cpu_recordings_and_video':cpu,'actual_native_key_evidence':keyevents,'native_host_pid_mappings':host['native_host_pid_mappings'],'original_worker_receipts':worker,'actual_simulation_ticks':read(ROOT/ATTEMPTS[-1][1]/'outputs/simulator/state.json')['physics_ticks'],'normal_shutdown':'Exact observed native Python birth-bound SIGINT, original handlers return, actual wrappers0, original main_returned+atexit, empty verified process groups; no TERM/KILL fallback for native workers','compose_change':{'before':fp(before),'after':fp(after),'resolved_config':fp(PUB/'compose/production-compose-config.json'),'single_item_change':'MUJOCO_GL glfw→egl (offscreen depth/video), visible passive viewer still explicitly GLFW','isolated_test_different_from_default_compose':'actual acceptance uses network none/privateIPC/newCID/privateXephyr and plane overrides; production compose configuration was parsed, not separately rerun here'},'limits':['Five actual attempts are retained; first four remain failed','One-factor EGL run clean exit does not prove all native heap bugs eradicated','Forward6 screenshot is floor with camera tracking OFF after robot left view; command6 evidence is actual key/state/NPZ, not gait visualization','Native recording wxyz+XYZ placeholders+29 joints with actual velocity_command one-hot; not training-native conversion/terrain bundle','Requested policy50Hz and physics500Hz clocks remain unchanged; actual wall performance differs','No real hardware, obstacle traversal, policy quality or convergence claim'],'auth_cookie_excluded':True,'byte_preserving_publication':True,'quality_verified':False,'hardware_verified':False}
write(PUB/'independent-review.json',review)
write(PUB/'attempts.json',rows)
(PUB/'summary.md').write_text('''# 原生 MuJoCo 窗口与终端键盘验收\n\n第五次实际运行通过平地接口验收：真实私有 MuJoCo 窗口中的8/9、独占终端窗口中经Tk→PTY传递的 `] / c / = / o / i`，以及 XTEST `w` 按住/松开的低速command1、高速command6均有原生状态回执。两段原生录制分别169/196帧（fps50）；手动c保存，STOP/o自动保存。双方原生main/atexit返回、实际外层wrapper均0、出生身份绑定的进程组为空，未使用TERM/KILL兜底。宿主观察器实际关联了容器/宿主PID、出生时间与command_writer线程。\n\n[逐次结果](attempts.json)、[独立验收](independent-review.json)、[离线原片与截图](playback.html)、[完整发布SHA清单](manifest.json)。四次失败的原始日志、退出码、计划与原始manifest全部保留在attempts/；这些失败没有改成成功。CPU后验独立确认NPZ有限值、one-hot标签、原始MP4完整解码，以及每次原始manifest的所有文件哈希。\n\n第四次运行在所有接口完成、视频保存及atexit之后发生 `free(): invalid next size (fast)` / native abort，外层wrapper1，整体失败。第五次只将离屏渲染环境 `MUJOCO_GL=glfw` 改为 `egl`；安装版官方源码显示depth/video Renderer走所选GLContext，而visible passive viewer显式使用GLFW。生产compose仅同样修改该项，并保存了解析后的配置及前后源文件。一次对照成功不证明所有原生内存问题已根除；未加入os._exit、忽略退出码或native算法/动作/清理补丁。\n\n主图只使用初始窗口与终端日志。forward6原始截图因为相机跟随关闭、机器人移出视野而只有地板，保留原图但不作为高速步态可视化证明。命令1/6验收依据真实键事件、状态与NPZ标签；记录的rootXYZ为SDK占位零，不能当作世界轨迹。原始视频可完整播放。\n\n本次证明单个G1平地接口流程，不证明障碍通关、629配置策略覆盖、训练收敛、实时性能或实机运行。NPZ为原生推理录制：wxyz四元数 + XYZ占位 +29关节及15维命令；不是配对terrain的训练native bundle。\n''')
# Small self-contained offline page; all media are original copied bytes.
success='attempts/05-egl-completed/outputs/'
video=next((PUB/success/'video').rglob('*.mp4')).relative_to(PUB).as_posix()
body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原生 GUI 键盘实际验收</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 16px;color:#17233a;background:#f7f9fc}article,figure{background:white;padding:18px;border:1px solid #d7e0eb;border-radius:10px;margin:20px 0}img,video{max-width:100%;height:auto}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #d7e0eb;text-align:left}a{color:#075b9d}code{overflow-wrap:anywhere}</style><h1>真实 MuJoCo 窗口与终端键盘</h1><p>第五次运行完成单个G1平地接口验收。所有媒体为原字节复制；四次失败完整保留。不是障碍通关、策略质量或实机证明。</p><p><a href="summary.md">说明</a> · <a href="independent-review.json">独立报告</a> · <a href="manifest.json">SHA清单</a></p>'''
body+='<figure><video controls preload="metadata" src="'+html.escape(video)+'"></video><figcaption>第五次实际运行保存的原始离屏视频，CPU完整解码通过；无重编码。视频时间基于模拟器录制配置，不能推断实时性能。</figcaption></figure>'
for filename,caption in [('initial-stiff.png','原始真实窗口：初始姿态，画面中仅部分机器人。'),('policy-terminal.png','原始独占终端窗口：自动保存、阻尼与站姿日志。')]:
 body+='<figure><img loading="lazy" src="'+success+filename+'" alt="'+caption+'"><figcaption>'+caption+'</figcaption></figure>'
body+='<details><summary>保留其它原始截图（包括高速时地板空画面）</summary>'
for filename,caption in [('forward-1.png','真实按住w时的窗口，仅是当时相机视图。'),('forward-6.png','相机跟随关闭，机器人已离开视野，只显示地板；不作高速步态视觉证据。'),('damping.png','o阻尼后的原窗口视图；阻尼参数依据原生状态和Python sender观测。'),('final-stiff.png','i站姿后的原窗口视图；状态依据原生回执。')]:
 body+='<figure><img loading="lazy" src="'+success+filename+'" alt="'+caption+'"><figcaption>'+caption+'</figcaption></figure>'
body+='</details><h2>五次原始运行</h2><table><thead><tr><th>尝试</th><th>真实状态 / 边界</th><th>原始证据</th></tr></thead><tbody>'
for row in rows:
 rel=row['raw_directory'];body+='<tr><td>'+html.escape(row['id'])+'</td><td>'+html.escape(row['status']+' — '+row['scope'])+'</td><td><a href="'+rel+'/outputs/summary.json">summary</a> · <a href="'+rel+'/host/launch-receipt.json">host退出</a> · <a href="'+rel+'/manifest.json">原manifest</a></td></tr>'
body+='</tbody></table><h2>两段实际录制</h2><ul>'
for r in cpu['recordings']:
 rel=success+'recordings/'+Path(r['path']).name;body+='<li><a href="'+rel+'">'+html.escape(r['save_method'])+'</a>：'+str(r['frames'])+'帧，command counts '+html.escape(json.dumps(r['command_counts']))+'，fps50；rootXYZ为占位零，不是世界轨迹。</li>'
body+='</ul><p>正常结束通过向精确出生身份绑定的原生Python进程发送SIGINT，保留原处理路径；Esc仅停止键盘listener，不能代替策略停止。单因素EGL对照不能保证所有heap问题已消失。</p></html>'
(PUB/'playback.html').write_text(body)
# Count-only secret scan: no actual secret values printed or included.
secret_findings=[]
for p in PUB.rglob('*'):
 if not p.is_file():continue
 if p.name=='private.xauth':secret_findings.append(p.relative_to(PUB).as_posix())
 if p.suffix in ('.json','.jsonl','.log','.txt','.md','.py','.yml','.html'):
  data=p.read_bytes()
  if (b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----') in data or re.search(rb'(?im)(?:WANDB_API_KEY|AWS_SECRET_ACCESS_KEY|Authorization)\s*[:=]\s*["\']?[A-Za-z0-9_/+.-]{16,}',data):secret_findings.append(p.relative_to(PUB).as_posix())
assert not secret_findings, 'Potential secret pattern; inspect safely before publication'
files=[{'relative':p.relative_to(PUB).as_posix(),**fp(p)} for p in sorted(PUB.rglob('*')) if p.is_file() and p.name!='manifest.json']
# Nested original manifest files must be included; exclude only this outer manifest.
files=[{'relative':p.relative_to(PUB).as_posix(),**fp(p)} for p in sorted(PUB.rglob('*')) if p.is_file() and p!=PUB/'manifest.json']
write(PUB/'manifest.json',{'schema_version':1,'files':files,'identity_sha256':ident(files),'auth_cookie_excluded':True,'all_media_original_bytes':True,'source':str(ROOT/ATTEMPTS[-1][1]),'successful_plan_sha256':EXPECTED,'credential_scan_findings':secret_findings})
print(json.dumps({'status':'published','directory':str(PUB),'files':len(files),'bytes':sum(r['bytes'] for r in files),'manifest':fp(PUB/'manifest.json'),'attempts':[{'id':r['id'],'status':r['status']} for r in rows]}))
