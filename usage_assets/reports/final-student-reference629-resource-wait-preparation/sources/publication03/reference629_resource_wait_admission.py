"""Pure readonly host-resource receipt admission, never queries or starts work."""
import ast
import math
import os
from pathlib import Path
import re

GPU='GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
HELPER_SHA='880395f6dd4eece4f9e948fea43123003b871b34331485c2a270c44c814c4373'


def require(value,message):
    if not value:raise ValueError(message)


def process(raw):
    fields=raw.rsplit(')',1)[1].split()
    return {'pid':int(raw.split('(',1)[0]),'ppid':int(fields[1]),'pgid':int(fields[2]),'sid':int(fields[3]),
            'start_time_clock_ticks':int(fields[19]),'state':fields[0]}


def verify(evidence,preparation,contract,item,parent_start,parent_process):
    """Check only completed pre-container host admission; retain all raw files."""
    preparation=Path(preparation);base=Path(contract['base']);kind=item['kind'];native=item['native_receipt']
    require(kind in ('pure','finetune'),'Unknown hostresource kind')
    directory=base/'runs'/kind/'host/resource-admission'
    helper=preparation/'reference629_gpu_resource_wait.py';source=evidence.fingerprint(helper)
    require(source['sha256']==HELPER_SHA,'Reviewed unique629 resource helper changed')
    tree=ast.parse(helper.read_bytes())
    nodes=[next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name) for name in ('require','parse_compute')]
    namespace={'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(helper),'exec'),namespace)
    parse_compute=namespace['parse_compute']
    file=evidence.bound(native['host_resource_admission_receipt'])
    require(file['path']==str(directory/'receipt.json'),'Exact hostresource receipt path differs')
    receipt=evidence.read(directory/'receipt.json')
    require(receipt==native['host_resource_admission'] and receipt['schema_version']==1 and receipt['status']=='ready'
            and receipt['gpu_uuid']==GPU and receipt['source']==receipt['source_after']==source
            and receipt['budget_seconds']==1800 and receipt['poll_seconds']==5 and receipt['query_timeout_seconds']==15
            and receipt['native_started'] is receipt['gpu_started'] is receipt['science_time_or_timeout_modified'] is False
            and receipt['pending_signals']==[] and not any(k in receipt for k in ('error','final_errors'))
            and math.isfinite(receipt['elapsed_real_seconds']) and 0<=receipt['elapsed_real_seconds']<=1800,
            'Complete successful finite hostresource admission required')
    keys=('pid','ppid','pgid','sid','start_time_clock_ticks')
    owner=receipt['owner'];boot=receipt['boot_id']
    require(all(type(owner[k]) is int and owner[k]==parent_process[k] for k in keys)
            and boot==parent_start['boot_id'] and all(process(owner['stat_raw'])[k]==owner[k] for k in keys)
            and process(owner['stat_raw'])['state']==owner['state']!='Z','Hostresource actual parent owner/birth/boot differs')
    initial=receipt['mutex_initial'];query_births=set()
    require(initial['path']==contract['global_host_lock'] and type(initial['device']) is int
            and type(initial['inode']) is int and initial['inode']>0 and type(initial['fd']) is int and initial['fd']>=0,
            'Canonical held mutex identity missing')
    def mutex(row):
        require(all(row[k]==initial[k] for k in ('path','fd','device','inode')) and row['boot_id']==boot
                and all(row['owner'][k]==owner[k] for k in keys)
                and all(process(row['owner']['stat_raw'])[k]==owner[k] for k in keys)
                and process(row['owner']['stat_raw'])['state']==row['owner']['state']!='Z','Same actual owner FD/inode/boot mutex required')
        fields=row['actual_proc_locks_line'].split();require(len(fields)==8,'Full actual kernel flock line required')
        major,minor,inode=fields[5].split(':')
        require(fields[1:4]==['FLOCK','ADVISORY','WRITE'] and int(fields[4])==owner['pid'] and fields[6:]==['0','EOF']
                and (int(major,16),int(minor,16),int(inode))==(os.major(initial['device']),os.minor(initial['device']),initial['inode']),
                'Actual exclusive kernel FLOCK owner/device/inode differs')
    mutex(initial);mutex(receipt['mutex_final'])
    rounds=receipt['rounds'];require(rounds and [r['index'] for r in rounds]==list(range(len(rounds))),'Complete contiguous resource rounds required')
    expected_files={str(directory/'receipt.json')};last_elapsed=-1
    argv={ 'identity_query':['nvidia-smi','--query-gpu=uuid','--format=csv,noheader,nounits'],
           'compute_query':['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits']}
    for index,row in enumerate(rounds):
        round_dir=directory/f'round-{index:05d}';mutex(row['mutex_before']);mutex(row['mutex_after'])
        require(math.isfinite(row['elapsed_real_seconds']) and last_elapsed<=row['elapsed_real_seconds']<=receipt['elapsed_real_seconds'],
                'Hostresource round real elapsed order differs');last_elapsed=row['elapsed_real_seconds']
        raw={}
        for key,label in [('identity_query','gpu-identity'),('compute_query','gpu-compute')]:
            q=row[key];qfile=round_dir/(label+'.execution.json');expected_files.add(str(qfile))
            require(evidence.read(qfile)==q and q['argv']==argv[key] and q['status']=='completed'
                    and type(q['actual_wait_returncode']) is int and q['actual_wait_returncode']==0
                    and q['errors']==q['signals_to_owned_query']==q['remaining_owned_query_session_members']==[]
                    and not q.get('owned_query_cleanup_unresolved',False) and math.isfinite(q['elapsed_real_seconds'])
                    and 0<=q['elapsed_real_seconds']<=15,'Actual query0/finite budget/empty session/clean receipt required')
            child=q['child_identity'];saved=process(child['stat_raw'])
            require(all(type(child[k]) is int and child[k]==saved[k] for k in keys)
                    and child['pid']==child['pgid']==child['sid']==q['actual_Popen_child_pid'] and child['pid']!=owner['pid']
                    and child['ppid']==q['actual_direct_parent_pid']==owner['pid']
                    and child['start_time_clock_ticks']>=owner['start_time_clock_ticks']>0,'Exact owned readonly query child birth differs')
            birth=(child['pid'],child['start_time_clock_ticks']);require(birth not in query_births,'Readonly query child birth reused');query_births.add(birth)
            mutex(q['mutex_before']);mutex(q['mutex_after'])
            for stream in ('stdout','stderr'):
                path=round_dir/(label+'.'+stream+'.raw');expected_files.add(str(path))
                require(evidence.bound(q[stream])['path']==str(path),'Exact query raw path differs')
                if stream=='stdout':raw[key]=path.read_text()
        require(raw['identity_query'].splitlines().count(GPU)==1,'Raw actual GPU identity differs')
        selected=parse_compute(raw['compute_query'],GPU)
        require(selected==row['existing_selected_compute_processes'] and row['status']==('busy' if selected else 'idle')
                and bool(selected)==(index<len(rounds)-1),'Raw GPU predicate must be busy-only rounds ending idle')
    actual_files={str(p) for p in directory.rglob('*') if p.is_file()}
    require(actual_files==expected_files,'Complete hostresource raw/query file-set differs')
    return {'status':'verified_actual_host_only_resource_admission','kind':kind,'receipt':file,'source':source,
            'rounds':len(rounds),'busy_rounds':len(rounds)-1,'query_count':2*len(rounds),
            'actual_parent_owner':owner,'mutex_identity':{k:initial[k] for k in ('path','device','inode')},
            'query_births':sorted(query_births),'scope':'Readonly completed pre-container resource admission only; original science is checked separately.'}
