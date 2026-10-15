import json,hashlib,numpy as np
from pathlib import Path
root=Path('/workspace/php_parkour')
base=root/'outputs/research/reproduction-20261015/local-checks/motion-rerun'
old=json.loads((root/'outputs/research/motion-matching/matrix.json').read_text())
new=json.loads((base/'generated/matrix.json').read_text())
def cases(matrix):
 return {(s['name'],i):r for s in matrix['scenarios'] for i,r in enumerate(s['result']['configurations'])}
a,b=cases(old),cases(new)
assert a.keys()==b.keys() and len(a)==629
report={'status':'running','cases':[],'scope':'Same Docker/new empty output versus retained 2026-10-10 generated arrays. Not a historical mm_hs golden reconstruction.'}
for key in sorted(a):
 ar,br=a[key],b[key];sources=[]
 for index in (0,1):
  before=Path(ar['files'][index]['path'])
  if before.is_relative_to('/outputs'):before=root/'outputs/research'/before.relative_to('/outputs')
  after=Path(br['files'][index]['path'])
  if index==0:
   with np.load(before,allow_pickle=False) as x,np.load(after,allow_pickle=False) as y:
    assert sorted(x.files)==sorted(y.files)
    for field in x.files:assert x[field].dtype==y[field].dtype and np.array_equal(x[field],y[field]),(key,field)
    fields=sorted(x.files)
  else:
   x,y=np.load(before,allow_pickle=False),np.load(after,allow_pickle=False)
   assert x.dtype==y.dtype and np.array_equal(x,y),key
   fields=['terrain']
  sources.append({'old':str(before),'new':str(after),'old_sha256':hashlib.sha256(before.read_bytes()).hexdigest(),'new_sha256':hashlib.sha256(after.read_bytes()).hexdigest(),'equal_fields':fields})
 report['cases'].append({'scenario':key[0],'index':key[1],'arrays_equal':True,'sources':sources})
report['status']='passed_same_image_full629_array_reproduction'
(base/'array-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'],len(report['cases']))
