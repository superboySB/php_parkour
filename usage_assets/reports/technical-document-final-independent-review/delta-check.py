from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
p=Path('outputs/research/documentation-final-independent-20261010T1027')
h=lambda b:hashlib.sha256(b).hexdigest()
initial=json.loads((p/'review.json').read_text())
old='目标为`outputs/research/final-student-transfer/<cohort>/initial/`，其中`models/pure/`与`models/finetune/`各有`student.onnx`和`depth_backbone.onnx`。工具校验远端前后身份、本地原文件集合及SHA，保留失败的partial目录；审阅失败后用新的`--attempt`，不会覆盖历史。它不运行ORT或仿真。当前真实status仍是waiting，57项CPU检查通过；最终两组模型尚未回传，更不能拿发布模型的629扫描代替自训模型验收。[检查证据](usage_assets/reports/final-student-transfer/summary.md)。'
b=Path('note.md').read_bytes();s=b.decode();lines=s.splitlines();matches=[(i,l) for i,l in enumerate(lines) if l.startswith('目标为`outputs/research/final-student-transfer/<cohort>/initial/`')]
assert len(matches)==1
line,new=matches[0]
reconstructed=s.replace(new,old,1).encode()
old_doc=next(x for x in initial['documents'] if x['path']=='note.md')
assert h(reconstructed)==old_doc['sha256'] and len(reconstructed)==old_doc['bytes']
docs=[]
for d in initial['documents']:
 q=Path(d['path']);raw=q.read_bytes();indexed=subprocess.check_output(['git','show',':'+d['path']]);assert raw==indexed
 if d['path']!='note.md':assert h(raw)==d['sha256']
 docs.append({'path':d['path'],'bytes':len(raw),'sha256':h(raw)})
link_rx=r'!?\[[^\]]*\]\(([^)\n]+)\)'
assert re.findall(link_rx,old)==re.findall(link_rx,new)
assert '该记录保留为历史' in new and '77项检查' in new and '10:19真实状态' in new
old_status_path=Path('usage_assets/reports/final-student-transfer/final-status.stdout.json')
new_status_path=Path('usage_assets/reports/final-student-transfer-ro-assets-integration/root-readonly-status.json')
a=json.loads(old_status_path.read_text());z=json.loads(new_status_path.read_text())
assert a['status']==z['status']=='waiting'
assert datetime.fromisoformat(a['observed_utc']).astimezone(timezone(timedelta(hours=8))).strftime('%H:%M')=='15:26'
assert datetime.fromisoformat(z['observed_utc']).strftime('%H:%M')=='10:19'
for x in [a,z]:assert len(x['stage_blockers'])==16 and x['cpu_ready_present'] is False and x['transfer_started'] is False and x['gpu_started'] is False
xmls=[]
for q,n in [(Path('usage_assets/reports/final-student-transfer/final-tests.xml'),57),(Path('usage_assets/reports/final-student-transfer-ro-assets-integration/tests-initial.xml'),77)]:
 e=ET.fromstring(q.read_bytes());ss=[e] if e.tag=='testsuite' else list(e.iter('testsuite'))
 c={k:sum(int(i.get(k,0)) for i in ss) for k in ['tests','failures','errors','skipped']}
 assert c=={'tests':n,'failures':0,'errors':0,'skipped':0}
 xmls.append({'path':str(q),'sha256':h(q.read_bytes()),**c})
producer=json.loads(Path('usage_assets/reports/technical-document-verification.json').read_text())
for d in docs:assert next(x for x in producer['documents'] if x['path']==d['path'])['sha256']==d['sha256']
r={'schema_version':1,'utc':datetime.now(timezone.utc).isoformat(),'status':'passed','initial_review':{'path':str(p/'review.json'),'sha256':h((p/'review.json').read_bytes()),'bytes_unchanged':True},'scope':'One-paragraph editorial delta after independent full audit; no45manifest/115source rescan or science test rerun.','documents':docs,'delta':{'document':'note.md','line':line+1,'only_one_paragraph_changed':True,'proof':'Replacing the current paragraph by contemporaneously captured initial text exactly recovers initial note.md SHA256 and bytes.','initial_document_sha256':old_doc['sha256'],'reconstructed_initial_sha256':h(reconstructed),'before':old,'after':new,'same_link_targets':True,'shell_blocks_unchanged':True},'actual_status_sources':[{'path':str(q),'sha256':h(q.read_bytes()),'status':d['status'],'observed_utc':d['observed_utc'],'blockers':len(d['stage_blockers']),'cpu_ready_present':d['cpu_ready_present'],'gpu_started':d['gpu_started'],'transfer_started':d['transfer_started']} for q,d in [(old_status_path,a),(new_status_path,z)]],'cpu_test_xmls':xmls,'technical_and_usage_unchanged':True,'frozen_documents_working_equal_git_index':True,'initial_editorial_note_resolved':True,'must_fix':[],'main_docs_source_git_or_raw_modified_by_auditor':False,'audit_script_sha256':h((p/'delta-check.py').read_bytes())}
(p/'delta-final-review.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
rows='\n'.join(f"- `{d['path']}`: `{d['sha256']}`" for d in docs)
(p/'final-summary.md').write_text(f'''# 最终冻结文档独立复核与单段修订复核

**通过，必须修正项0，编辑遗留0。** 原始初审JSON、summary和脚本均原字节保留。本摘要合并初审与随后仅一段文字变化的增量复核，不改写历史结果。

最终文档SHA256：

{rows}

初审独立核验45份manifest的2403项原始依赖：FS bytes/SHA256和Git索引原字节全部一致。115份源码身份=110当前文件+5明确历史归档，README原blob保持`6d6344e7939845d900c631d282e263fd283c7f07`。377个Markdown链接、166个HTML媒体引用及41个shell块语法通过。核心数学/输入输出/label来源/实机未完成边界及新增GUI、首两例629、watch/回传范围未发现实质错误。

增量复核证明只有`note.md:{line+1}`的一个段落变化：替换回同时保存的原段落后，精确恢复初审note的bytes/SHA256；technical和usage SHA不变，三个最终文档均与Git索引逐字节相同。原57项/北京时间15:26等待响应已明确历史，新77项/10:19UTC等待响应有末段说明。两份实际status仍是waiting、16阻塞、无cpu-ready/GPU/回传；57与77原JUnit分别全通过。链接目标与所有shell块均未变。因此初审唯一非阻塞编辑注已解决。

GUI第五次执行完整性不代表障碍/实机成功；fresh629独立后验仅首两例，固定快照21/1/607，其中cfg1真实跌倒；不宣称629完成。正式七模型及自训学生回传仍待完成。此次没有云端调用、GPU/DDS/仿真、科学测试重跑、源码/文档/原证据修改或Git操作。

机器记录：[初审](review.json)SHA`{h((p/'review.json').read_bytes())}`；[最终delta](delta-final-review.json)SHA`{h((p/'delta-final-review.json').read_bytes())}`。历史604行数学审查保持原字节。
''')
for n in ['delta-final-review.json','final-summary.md']:
 raw=(p/n).read_bytes();print(n,len(raw),h(raw))
