"""Stdlib contracts for a future, separately reviewed official-pair attempt."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKSPACE = Path('/home/dzp/projects/php_parkour')
OLD = WORKSPACE/'outputs/research/fresh629-sdk018-6cb2ae2-prepared02'
IMAGE = 'sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
GPU = 'GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
LOCK = WORKSPACE/('outputs/research/.local-native-'+GPU+'.lock')
KINDS = ('pure', 'finetune')
SOURCE_SHAS = {'sim2sim.py':'023fed0f9f31f79b506b370a96013c18e8b1c94239e0504eca4bcea6076c3f4d',
 'reference_commands.py':'1af208fc1f57bac61d37256a4bdbb20fa45b05817291c3372c92b5a8c3807d57',
 'sim2sim_scene_matrix.py':'599c75df14c5ac902d57f88bfd3d752317e332abce5751153bef8d20d8d0bb70'}

def require(value, message):
    if not value: raise ValueError(message)

def safe(path, exists=True):
    p=Path(path).absolute()
    require('..' not in p.parts and p.is_relative_to(WORKSPACE/'outputs/research'), 'Use an explicit research path without parent traversal')
    require(not any(x.is_symlink() for x in (p,*p.parents)), 'Symlink path rejected: '+str(p))
    if exists: require(p.exists(), 'Missing actual prerequisite: '+str(p))
    return p

def fp(path):
    p=Path(path);require(p.is_file() and not p.is_symlink(),'Regular file required: '+str(p))
    a=p.stat();h=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024), b''): h.update(block)
    b=p.stat();require((a.st_ino,a.st_mtime_ns,a.st_size)==(b.st_ino,b.st_mtime_ns,b.st_size),'File changed during hash')
    return {'path':str(p),'bytes':b.st_size,'sha256':h.hexdigest()}

def check(record):
    actual=fp(record['path']);require(actual==record,'Bound bytes changed: '+record['path']);return actual

def read(path):
    return json.loads(Path(path).read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON '+x)))

def write(path,value):
    p=Path(path);temporary=p.with_name(p.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(p)

def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module

def verify_preparation(expected_sha):
    manifest=HERE/'preparation-manifest.json'
    require(fp(manifest)['sha256']==expected_sha,'Preparation manifest differs from reviewed SHA')
    rows=read(manifest)['files'];seen=set()
    for r in rows:
        rel=Path(r['path']);require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in seen,'Unsafe preparation record')
        seen.add(str(rel));require(fp(HERE/rel)==dict(r,path=str(HERE/rel)),'Frozen preparation dependency changed')
    return fp(manifest)

def source_rows():
    original=HERE/'source-original/old-freeze-manifest.json'
    require(fp(original)['sha256']=='599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169','Original source manifest changed')
    rows=[x for x in read(original)['files'] if x['relative'].startswith('source/')]
    require(len(rows)==5184,'Exact original full source count differs')
    return rows

def verify_tree(base,records):
    expected=set()
    for row in records:
        rel=Path(row['relative']);require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected,'Unsafe/duplicate tree record')
        expected.add(str(rel));a=fp(base/rel)
        require((a['bytes'],a['sha256'])==(row['bytes'],row['sha256']),'Frozen tree bytes changed: '+str(rel))
    for group in ('source','overlay','inputs','control'):
        allowed={x for x in expected if x.startswith(group+'/')}
        actual=set()
        for path in (base/group).rglob('*'):
            require(not path.is_symlink(),'Symlink in frozen tree')
            if path.is_file():actual.add(path.relative_to(base).as_posix())
        require(actual==allowed,'Frozen regular file-set changed: '+group)
    return len(records)

def verify_contract(path,sha):
    path=safe(path);require(fp(path)['sha256']==sha,'Contract is not the separately reviewed SHA')
    c=read(path);require(c['schema_version']==1 and c['status']=='prepared_for_separate_review'
      and c['contract_identity']==identity({k:v for k,v in c.items() if k!='contract_identity'})
      and c['image_id']==IMAGE and c['gpu_uuid']==GPU and c['global_host_lock']==str(LOCK)
      and c['expected']=={'policies':2,'cases':1258,'workers':2516,'host_maps':2516,'full_decodes':1258}
      and c['kind_order']==list(KINDS),'Prepared contract identity/scope differs')
    base=safe(c['base']);require(path==base/'contract.json','Contract/base path mismatch')
    check(c['preparation_manifest']);verify_preparation(c['preparation_manifest']['sha256'])
    check(c['freeze_manifest']);verify_tree(base,read(c['freeze_manifest']['path'])['files'])
    for r in c['admission']['bound_files']:check(r)
    for kind in KINDS:
        item=c['kinds'][kind];check(item['cpu_plan']);check(item['cpu_summary']);check(item['cpu_launch'])
        p=read(item['cpu_plan']['path']);require(p['plan_sha256']==item['native_plan_identity']
          and p['planned_configurations']==629 and p['planned_scenarios']==17
          and p['all_configurations'] is True and p['reference_commands'] is True
          and p['image_id']==IMAGE,'Fresh reference629 plan scope differs')
        require(p['model_sha256']=={Path(x['path']).name:x['sha256'] for x in c['admission']['models'] if x['kind']==kind},'Plan does not use this official pair')
    return c
