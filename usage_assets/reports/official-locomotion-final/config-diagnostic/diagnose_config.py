from pathlib import Path
import torch,yaml,json
p=Path('/artifacts');d=torch.load(p/'model_19999.pt',map_location='cpu',weights_only=False);a=d['experiment_config'];b=yaml.safe_load((p/'holosoma_config.yaml').read_text());rows=[]
def diff(a,b,path='$'):
 if isinstance(a,dict) and isinstance(b,dict):
  for k in sorted(set(a)|set(b)):
   if k not in a or k not in b:rows.append({'path':path+'.'+k,'pt':repr(a.get(k,'<missing>')),'yaml':repr(b.get(k,'<missing>'))})
   else:diff(a[k],b[k],path+'.'+k)
 elif isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):
  if type(a)!=type(b):rows.append({'path':path,'type_only':[type(a).__name__,type(b).__name__]})
  if len(a)!=len(b):rows.append({'path':path,'pt_length':len(a),'yaml_length':len(b)})
  for i,(x,y) in enumerate(zip(a,b)):diff(x,y,path+'['+str(i)+']')
 elif a!=b:rows.append({'path':path,'pt':repr(a),'yaml':repr(b),'types':[type(a).__name__,type(b).__name__]})
diff(a,b)
j={'status':'diagnosed_original_failure','full_equal':a==b,'diffs':rows,'cuda_initialized':torch.cuda.is_initialized()};Path('/diagnostic/config-diff.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j))
