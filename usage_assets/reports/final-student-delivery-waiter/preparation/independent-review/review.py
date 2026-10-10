from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as E
from datetime import datetime,timezone
ROOT=Path.cwd();SRC=ROOT/'outputs/research/final-student-delivery-waiter-preparation';OUT=ROOT/'outputs/research/final-student-waiter-independent-review-01'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def rec(p):return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':h(p)}
expected={'wait_final_students.py':'049678a74ff34776120fda26da9c6ebb54c215f084929629a60fc5bfba50535f','test_wait_final_students.py':'9d02b7194997e1b81d9c4d5413a51fc0fd8308ee27dd234f5b95cbd5a2bfd4aa','contract.json':'b4cde2ba7b361bd5f18cce9a0a10b1c234fa1519cfe5787fa14e9aef0f0d7f4f'}
for n,s in expected.items():assert h(SRC/n)==s
for n in ['wait_final_students.py','test_wait_final_students.py']:ast.parse((SRC/n).read_text())
contract=json.loads((SRC/'contract.json').read_text());assert contract['status']=='approved_frozen' and contract['poll_seconds']==600 and contract['root_authorized_watch_required'] is True
sources=[]
for d in contract['sources']:
 p=Path(d['path']);assert p.is_file() and not p.is_symlink() and h(p)==d['sha256'] and p.stat().st_size==d['bytes'];sources.append(rec(p))
assert len(sources)==11
freeze_record=contract['native58_code_freeze'];f=Path(freeze_record['path']);assert h(f)==freeze_record['sha256']=='1875e0bae5ad6063cbd3b57bd290cdce7bef3daf9f6eccdb131c4548f8cfc39e' and f.stat().st_size==freeze_record['bytes']
freeze=json.loads(f.read_text())
for d in freeze['files']:
 p=f.parent/d['path'];assert h(p)==d['sha256'] and p.stat().st_size==d['bytes']
launch_path=SRC/'cpu-validation-transport-final/launch.json';launch=json.loads(launch_path.read_text())
assert launch['returncode']==0 and launch['network']=='none' and launch['runtime']=='runc' and launch['gpu_requested'] is False
assert launch['source_before']==launch['source_after']
for d in launch['source_after']:
 p=Path(d['path']);assert h(p)==d['sha256'] and p.stat().st_size==d['bytes']
xml=SRC/'cpu-validation-transport-final/tests.xml';root=E.fromstring(xml.read_bytes());ss=list(root.iter('testsuite'))
counts={k:sum(int(s.get(k,0)) for s in ss) for k in ['tests','failures','errors','skipped']}
assert counts=={'tests':55,'failures':0,'errors':0,'skipped':0}
prep_path=SRC/'preparation-receipt.json';prep=json.loads(prep_path.read_text());assert prep['status']=='prepared_not_armed' and prep['returncode']==0 and prep['no_ssh_fetch_daemon_or_native_started'] is True and prep['production_or_active_dependencies_changed'] is False
for k in ['contract','waiter','tests']:
 d=prep[k];p=Path(d['path']);assert h(p)==d['sha256'] and p.stat().st_size==d['bytes']
stdout=SRC/'check.stdout.log';check=json.loads(stdout.read_text());assert check['status']=='prepared_only' and check['armed'] is False and check['ssh_fetch_gpu_started'] is False
assert not (SRC/'check.stderr.log').read_bytes()
assert check['contract_identity']==hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
paths=[]
for raw,was_absent in prep['dedicated_paths_absent'].items():
 p=Path(raw);assert was_absent and not p.exists();paths.append({'path':raw,'currently_absent':True})
assert len(paths)==4
code=(SRC/'wait_final_students.py').read_text()
# Manual read-only review of exact frozen code supplements these identity checks.
r={'schema_version':1,'utc':datetime.now(timezone.utc).isoformat(),'status':'passed_readonly_pre_arm_contract_review','scope':'Frozen waiter andnative58source contracts, existing55CPUcontrol-plane tests andreal localreadonlycheck; not arming orfinaldelivery/physics completion.','reviewed_files':[rec(SRC/n) for n in expected],'contract_source_count':len(sources),'contract_sources':sources,'native58_code_freeze':rec(f),'native58_frozen_python_files_verified':len(freeze['files']),'cpu_validation':{'launch':rec(launch_path),'junit':rec(xml),'counts':counts,'sources_before_after_equal':True,'runtime':'runc','network':'none','gpu_requested':False,'actual_owned_plain_cpu_helper_and_grandchild_tests':True},'actual_readonly_check':{'receipt':rec(prep_path),'stdout':rec(stdout),'stderr':rec(SRC/'check.stderr.log'),'status':'prepared_only','armed':False,'dedicated_paths':paths},'verified_contracts':['Exact selfSHA+contractSHA+11 executable/provenance sources andnative58freeze10members checkedbefore/after actions; actualloadedcommon/nativepair checked.','Fixedcanonicalworkspace,transfer/nativeoutputs,previousfresh629receipt,remote02bc+coveragev2,image2be,UUIDmutex,poll600 and58/116/116/58 contract.','check doesnotarm/createexecution orwaiterlock; watch needsexplicitrootflag,singleinstanceflock andfreshneverresumed executiondirectory.','Read-onlystatus onlyuntilrealready; readyreceipt validated beforeoneshotfetch; fixed4ONNX28JSON provenance andreadybefore/fetchsnapshot equality required.','Startedfetch/prepare/run flagpersisted beforechild; failureterminal/partialpreserved/noautomaticretry/noexistingattempt overwrite.','Wait forcurrentfresh629realcompleted driver0/CPUvalidator0,exactstoppedCID/birth,freeUUIDlock/idleGPU; noofficial/watch/active629stop/exec/mutation.','Actualnative58CPUprepare60ORT precedesreviewedcohort/controlrun; runagainbindssource+canonicalwholebatchUUIDmutex.','OwnPopen startsprivatePGID/SID; startupPID/birthreceiptwithparentsignalsblockeduntilrecordandchildmaskrestored; SIGTERMconvertedtocontrolledcancellation.','Native58prepare/run cancellation sendsSIGINT onlytoownedhelperafterbirth/groupcheck andwaitsforitsfinally; transportstatus/fetch sendsSIGINTtoverifiedownprivatesession,30sgrace thenfailswithoutKILL.','Receipt retains rawreturncode/sourcebeforeafter/sessionmembers/cleanupdiagnostics; unknownbirth refuses signal; nonempty/unknownsession nevercounts success.','Native58 completion requiresactual58cases/116worker0-emptygroups/116hostmaps/58MP4decode,4orderedphase receipts,hash-boundCPUfinalreports andqualityfalse.'],'must_fix':[],'pre_review_issue':{'issue':'Initialsubprocess.run/defaultSIGTERM didnotownorrecordhelper/transportsubtree lifecycle.','fixed':True,'scope':'PrivatePopen/birth/startreceipt,controlledSIGTERM/SIGINT,transportgroupgrandchild test,normalexit/sessiongate andgracefailureevidence.','mechanism_correction':'Python3.12subprocess.run handlesKeyboardInterruptbykillingitsdirectchild andPopen.__exit__shortwaits; earlierreviewmessageclaimofmandatoryinfinite__exit__waitwasincorrectandwithdrawn. SSHgrandchild/sessionownershipremainedthevalidboundary.'},'limitations':['No daemon hasbeenarmedbyreviewer; noSSH/status/fetch/Docker/native/GPU/official/watchoperation performed.','55tests use syntheticartifacts/mocks plusactualplainCPUhelperandgrandchild; finalmodels/60ORT/58native remainpending.','Atransport refusingSIGINTafter30sgrace isrecordedfailed/unreaped formanualreview withoutSIGKILL; nonzero/unknown/residualidentity cannotbeclaimedclean.','Native58helpercancellation intentionallywaitsfornative58owncleanup ratherthanexternallyKILLingit; noncooperativehelpermayrequiremanualreview,notautomaticrestart.','Old50candidatehistorysource was reconstructedbyreversinglifecyclepatch andisexplicitlynotanoriginalcontemporaneoussnapshot; final55before/afterSHAbindingisexact.'],'reviewer_modified_main_source_docs_raw_git':False,'reviewer_started_any_daemon_ssh_docker_native_gpu':False,'audit_script':rec(OUT/'review.py')}
(OUT/'review.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
(OUT/'summary.md').write_text(f'''# 最终学生等待器独立只读预启动审查

通过，剩余必须修正项0。入口SHA`{expected['wait_final_students.py']}`，合同SHA`{expected['contract.json']}`。核11个执行/来源文件和native58冻结10成员，最终Docker CPU55/55、源SHA前后一致；实际本地check exit0/prepared_only，transfer/native/execution/lock四专用路径尚未创建。

单实例flock、600秒只读status、真实ready后单次fetch、固定4ONNX28JSON来源、partial保留且不自动重试、fresh629正常终态/停止/UUID空闲门卫均符合范围。真正prepare后调用封存cohort/control/native58 run，终态要求58例/116worker/116host映射/58原片解码，quality始终不由执行完整性推断。

初稿子进程生命周期缺口已修复：独立session/PID出生身份启动回执，SIGTERM受控取消；native58先自身SIGINT/finally清理，SSH/传输使用核身份的私有组SIGINT。普通CPU helper和孙进程真实回收测试通过，身份变化/残留拒绝通过。transport超过30秒宽限会失败并留现场，不KILL、不自动重试；native58取消等待其自身清理，不能宣称非合作进程总能回收。

审查者未arm daemon、SSH、Docker、fetch、native/GPU，也未改生产/原证据/Git。最终模型交付及60ORT/58native仍待真实就绪后执行。旧50源码重建标识保留，只有final55具有精确前后SHA绑定。

[机器报告](review.json)，SHA256`{h(OUT/'review.json')}`。
''')
for n in ['review.json','summary.md']:
 p=OUT/n;print(n,p.stat().st_size,h(p))
