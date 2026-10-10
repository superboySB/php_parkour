"""Read existing smoke checkpoints on CPU; not a native resume experiment."""
import hashlib
import json
from pathlib import Path
import sys
import torch
sys.path.insert(0,'/control')
from resume_evidence import optimizer_rows,finite

assert not torch.cuda.is_available() and not torch.cuda.is_initialized()
source=json.loads(Path('/data/schema.json').read_text())['checkpoints']
rows=[]
for key,label in [('teacher','teacher-locomotion'),('pure','student-pure'),('mixed','student-finetune')]:
    record=source[key];path=Path('/data/existing')/Path(record['source']).relative_to('/outputs/final-cloud-acceptance/results/smoke')
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==record['sha256']
    value=torch.load(path,map_location='cpu',weights_only=False);assert finite(value,torch)>0
    opt=optimizer_rows(value,label)
    expected=40 if label.startswith('teacher') else 16
    assert all(r['step']==expected for r in opt),(label,opt)
    rows.append({'label':label,'source_path':record['source'],'sha256':record['sha256'],
                 'iter':value['iter'],'iteration':value['iteration'],'num_teachers':value.get('num_teachers'),
                 'optimizer_rows':opt,'expected_steps':expected,
                 'scope':'Existing actual native baseline smoke2; five student experts, not the future single-expert resume or GPU execution.'})
assert not torch.cuda.is_initialized()
result={'status':'passed_actual_existing_schema_cpu_only','cuda_initialized':False,'native_started':False,'gpu_started':False,'rows':rows}
Path('/test-output/actual-existing-optimizer-schema.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'models':len(rows),'parameter_states':[len(r['optimizer_rows']) for r in rows]}))
