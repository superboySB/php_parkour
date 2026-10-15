#!/usr/bin/env python3
"""Independent static source/actual ordinary CPU receipts, no future postexecution."""
import ast
import copy
import datetime
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour');HERE=ROOT/'outputs/research/reproduction-20261015'
def fp(p):
    raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def check(r):assert fp(Path(r['path']))==r

def main():
    shared=HERE/'native58_resource_wait_control.py';review=HERE/'review_native58_resource_wait.py';test=HERE/'test_native58_resource_wait_control.py';original=HERE/'review_native58.py'
    for p,sha in [(shared,'81674ff7041216c99f5a43d214868d881079a4c274ad493ac0752afddb49a374'),(review,'636af46e588c3c6c0a41abf447b3310af833a746e0c70da730c86df7db5563f2'),(test,'f6ee7a3c4b98960fa0033aff5d4f4895fa043fa68c81defa34e3aa8ac259f6ea')]:assert fp(p)['sha256']==sha
    controls=[]
    for version,sha in [('04','bd135a2e24444366b65f3e0e459fe8fa5f37a451e22e085f6ee45ea61205173f'),('05','8c49458767b52bcb376333d25c1b9c7344ae2ea7f4c637b9b7c62d7fc68c49b8')]:
        p=HERE/f'local-checks/native58-resource-wait-postreview-controls-{version}/execution.json';assert fp(p)['sha256']==sha;data=json.loads(p.read_bytes());assert data['sources_before']==data['sources_after'] and data['sources_unchanged']
        records=data.get('records',[data])
        for row in records:
            assert row['actual_wait_returncode']==0;check(row['stdout']);check(row['stderr'])
        for row in data['sources_before']:
            source=Path(row['path'])
            if fp(source)!=row:
                copies=(p.parent/'verified-source-copies').rglob('*')
                assert any(q.is_file() and fp(q)['sha256']==row['sha256'] and fp(q)['bytes']==row['bytes'] for q in copies)
        controls.append({'execution':fp(p),'record_count':len(records),'sources_before_after_identical':True})
    def body(p):return next(n for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='verify').body
    def assigned(n,name):return isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in n.targets)
    def section(b,start,end):
        a=next(i for i,n in enumerate(b) if start(n));z=next(i for i,n in enumerate(b[a:],a) if end(n));return ast.dump(ast.Module(body=b[a:z],type_ignores=[]),include_attributes=False)
    a,b=body(original),body(review)
    assert section(a,lambda n:assigned(n,'terminal'),lambda n:assigned(n,'report'))==section(b,lambda n:assigned(n,'terminal'),lambda n:assigned(n,'report'))
    assert section(a,lambda n:isinstance(n,ast.FunctionDef) and n.name=='cpu_inspect',lambda n:assigned(n,'waited'))==section(b,lambda n:isinstance(n,ast.FunctionDef) and n.name=='cpu_inspect',lambda n:assigned(n,'parent_module_path'))
    x=copy.deepcopy(next(n for n in a if assigned(n,'report')));y=copy.deepcopy(next(n for n in b if assigned(n,'report')))
    for i in reversed(range(len(y.value.keys))):
        if isinstance(y.value.keys[i],ast.Constant) and y.value.keys[i].value in ['host_control','control_revision']:del y.value.keys[i];del y.value.values[i]
    assert ast.dump(x,include_attributes=False)==ast.dump(y,include_attributes=False)
    report={'schema_version':1,'status':'passed_source_only_native58_resource_wait_postreview_review','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'must_fix':[],'shared':fp(shared),'reviewer':fp(review),'tests':fp(test),'original_scientific_reviewer':fp(original),'review_source':fp(Path(__file__)),'existing_actual_cpu_controls':controls,'ordinary_cpu_cases':32,
    'ordinary_cpu_batches':'Original30+help bd135, then only2 container-route cases8c494. Original9c test source preserved in verified-source-copies; currentf6 is not retroactively claimed at original runtime.',
    'scientific_and_full58_decoder_AST_identical':True,'cpu_decoder_isolation_AST_identical':True,'original_report_fields_identical_except_host_control_and_revision':True,
    'checks':['Exact real15argv/e238 wait0/direct-parent birth+rawlogs/closedtwoowned sessions, root143b+0ef protocol, b469/d5f/0bcc/resource8e09 and schema3.','Complete query/raw/API+CLI journal/proof linking,9originalgpu_idle AST replay,busy-onlywaiting and real43200 wall/finite1800max3600 policy.','Sameboot failed41 actualparent1/partial41/threeidleGPUstop143 and independentlyreleased resources; oldboot143+8mappinggap preserved separately, no complete58 inference.','Both current200 comparisons normalize complete Mounts rows with uniqueDestination and preserve raw; all bound_files/operational directories flow to downstreamarchive.','Canonical/copiedshared samebytes and host_control independent ofloadedcopypath/retain callback; actual review and629copy can agree exactly.'],
    'actions_taken':{'fresh_gate':False,'docker':False,'gpu':False,'ssh':False,'native58_postexecution_review':False,'decode':False,'formal629_prepare':False},'scope':'Independent static source/control review only. Actualfull58 and actuale238parentwait0 are mandatory before actualpostexecutionreview. No futurepass/quality/course-success claim.'}
    out=HERE/'native58-resource-wait-postreview-independent-static-review.json';assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(fp(out),indent=2))
if __name__=='__main__':main()
