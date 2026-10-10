#!/usr/bin/env python3
"""Root-approved one-shot delivery waiter. Preparation/tests never arm it.

Only the reviewed pull tool performs SSH/fetch. Only frozen native58 performs
CPU preparation/GPU execution and cleanup. Failed/started actions never retry.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
sys.dont_write_bytecode=True

WORKSPACE=Path('/home/dzp/projects/php_parkour')
PREPARATION=WORKSPACE/'outputs/research/final-student-delivery-waiter-recovered-preparation-01'
PULL=WORKSPACE/'scripts/research/pull_final_students.py'
NATIVE=WORKSPACE/'outputs/research/final-student-native58-recovered-preparation-01'
PREVIOUS=WORKSPACE/'outputs/research/fresh629-recovery-01/missing-four-run-01/host/launch-receipt.json'
TRANSFER_ROOT=WORKSPACE/'outputs/research/final-student-transfer/waiter-delivery-recovered-01'
NATIVE_OUTPUT=WORKSPACE/'outputs/research/final-student-native58-delivery-recovered-01'
WAITER_LOCK=WORKSPACE/'outputs/research/final-student-delivery-waiter-preparation/waiter.lock'
RECOVERED_GATE_SHA='dbc64d32e4da4e1d3791e4b34ab38c3a4035e70c59402183985dd0bc03ce6525'
LIFECYCLE='recovered_original629_and_separate_four_preserving_root143'
UUID='GPU-1803972d-e774-ee96-e6f6-1ee1ce47bb25'
MUTEX=WORKSPACE/'outputs/research'/('.local-native-'+UUID+'.lock')
REMOTE_TREE='02bc110026d8402cd6046afecb039ee40fbd918c760554ad86f7effa678f9f3c'
COVERAGE='coverage-official-final-ro-assets-v2'
IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
EXPECTED_COUNTS={'cases':58,'worker_exit0_empty_groups':116,'exact_host_maps':116,'full_decoded_mp4_count':58}
POLL_SECONDS=600
CONTRACT_GUARD=None


def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def require(value,message):
    if not value:raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8<<20),b''):h.update(block)
    return h.hexdigest()
def read(path):
    return json.loads(Path(path).read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON '+x)))
def identity(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def safe(path,*,exists=False,file=False,root=None):
    path=Path(path)
    root=WORKSPACE if root is None else Path(root)
    require(path.is_absolute() and '..' not in path.parts,'Absolute canonical path required')
    require(not any(p.is_symlink() for p in (path,*path.parents)),'Symlink path/ancestor rejected')
    real=path.resolve(strict=exists)
    require(real==path and real.is_relative_to(root.resolve()),'Path escapes reviewed dedicated workspace')
    if file:require(stat.S_ISREG(path.stat().st_mode),'Regular file required')
    return real

def write(path,data):
    path=safe(path);safe(path.parent,exists=True)
    if path.exists():safe(path,exists=True,file=True)
    temporary=path.with_name(path.name+'.tmp')
    require(not temporary.exists() and not temporary.is_symlink(),'Stale state temporary retained; manual review required')
    with temporary.open('x') as stream:
        json.dump(data,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o644);temporary.replace(path)

def verify_sources(contract):
    if CONTRACT_GUARD is not None:
        path,expected=CONTRACT_GUARD
        require(sha(safe(path,exists=True,file=True))==expected,'Armed contract file SHA changed')
    require(contract.get('schema_version')==1 and contract.get('status')=='frozen_recovered_lifecycle_requires_root_review',
            'Recovered lifecycle freeze contract not ready')
    fixed={'workspace':str(WORKSPACE),'preparation':str(PREPARATION),'pull':str(PULL),'native58':str(NATIVE/'native58.py'),
           'previous_cohort_receipt':str(PREVIOUS),'transfer_output_root':str(TRANSFER_ROOT),'native_output':str(NATIVE_OUTPUT),
           'gpu_uuid':UUID,'gpu_mutex':str(MUTEX),'poll_seconds':600,'remote_source_tree':REMOTE_TREE,
           'coverage_output':COVERAGE,'native_image':IMAGE,'waiter_singleton_lock':str(WAITER_LOCK),
           'previous_lifecycle':LIFECYCLE,'previous_gate_sha256':RECOVERED_GATE_SHA}
    require(all(contract.get(k)==v for k,v in fixed.items()),'Reviewed fixed path/UUID/poll contract differs')
    require(contract.get('expected_counts')==EXPECTED_COUNTS,'Final58 count contract differs')
    waiter=safe(PREPARATION/'wait_final_students.py',exists=True,file=True)
    require(sha(waiter)==contract.get('waiter_sha256'),'Waiter executable SHA changed')
    freeze=contract['native58_code_freeze'];path=safe(freeze['path'],exists=True,file=True)
    require(path==NATIVE/'code-freeze.json' and sha(path)==freeze['sha256'] and path.stat().st_size==freeze['bytes'],
            'Native58 reviewed code-freeze receipt changed')
    frozen=read(path)
    require(frozen['status']=='code_frozen_recovered_lifecycle_no_new_execution','Native58 recovered freeze status differs')
    for record in frozen['files']:
        member=safe(NATIVE/record['path'],exists=True,file=True,root=NATIVE)
        require(member.parent==NATIVE and sha(member)==record['sha256'] and member.stat().st_size==record['bytes'],
                'Native58 reviewed freeze member changed')
    records=contract.get('sources',[]);paths=[x['path'] for x in records]
    require(len(paths)==len(set(paths)) and str(PULL) in paths and str(NATIVE/'native58.py') in paths
            and str(NATIVE/'common.py') in paths and str(NATIVE/'reused-sources.json') in paths,'Missing/duplicate frozen controls')
    require(all(Path(x)==PULL or Path(x).parent==NATIVE for x in paths),'Unapproved executable source path')
    for item in records:
        path=safe(item['path'],exists=True,file=True)
        require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],'Frozen source SHA changed: '+str(path))
    return {x['path']:x['sha256'] for x in records}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def adapters(contract):
    """Import only SHA-verified stdlib controls; imported modules do no work."""
    sources=verify_sources(contract);pull=load(PULL,'delivery_reviewed_pull')
    common=load(NATIVE/'common.py','delivery_reviewed_common')
    require(common.PULL_SHA==sources[str(PULL)] and common.HOST_WORKSPACE==WORKSPACE,'Native58/pull contract disagrees')
    require(common.TREE==REMOTE_TREE and pull.COVERAGE_DIRECTORY==COVERAGE and common.IMAGE==IMAGE,'Native58 remote/image contract differs')
    previous=sys.modules.get('common');sys.modules['common']=common
    sys.path.insert(0,str(NATIVE))
    try:native=load(NATIVE/'native58.py','delivery_reviewed_native58')
    finally:
        sys.path.remove(str(NATIVE))
        if previous is None:sys.modules.pop('common',None)
        else:sys.modules['common']=previous
    required={str(NATIVE/name) for name in native.CONTROL}|{str(PULL),str(NATIVE/'reused-sources.json')}
    require(set(sources)==required,'Contract must cover all ten native58 controls and reused provenance')
    require(native.RECOVERED_GATE_SHA==RECOVERED_GATE_SHA and native.RECOVERED_PREVIOUS==PREVIOUS
            and native.LIFECYCLE==LIFECYCLE,'Waiter/native58 recovered lifecycle contract differs')
    return pull,common,native

def process_identity(pid):
    data=(Path('/proc')/str(pid)/'stat').read_text();parts=data[data.rfind(')')+2:].split()
    return {'pid':pid,'pgid':int(parts[2]),'sid':int(parts[3]),'start_time_clock_ticks':int(parts[19]),'state':parts[0]}

def group_members(pgid,sid):
    found=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:item=process_identity(int(path.name))
        except (FileNotFoundError,ProcessLookupError):continue
        if item['pgid']==pgid and item['sid']==sid:found.append(item)
    return found

def finish_interrupted_child(child,receipt,label):
    """Notify only our still-owned Popen, then let its finally cleanup finish."""
    handlers={s:signal.signal(s,signal.SIG_IGN) for s in (signal.SIGINT,signal.SIGTERM)}
    try:
        if child.poll() is None:
            actual=process_identity(child.pid)
            require(all(actual[key]==receipt['child_identity'][key] for key in ('pid','pgid','sid','start_time_clock_ticks')),
                    'Owned helper birth/group changed before cancellation')
            if label in ('status','fetch'):
                # Only this verified private transport session: SSH/rsync must also receive cancellation.
                os.killpg(child.pid,signal.SIGINT);receipt['owned_transport_group_sigint_sent']=True
            else:child.send_signal(signal.SIGINT)
            receipt['owned_child_sigint_sent']=True
        receipt['returncode']=child.wait(timeout=30 if label in ('status','fetch') else None)
        # Native58 owns bounded GPU cleanup. Transport refusing SIGINT fails for manual review; no external KILL.
    finally:
        for sig,handler in handlers.items():signal.signal(sig,handler)

def invoke(argv,logs,label,contract,timeout=None):
    """No shell expansion; pre/post SHA checks. Native58 owns all GPU cleanup."""
    verify_sources(contract);safe(logs,exists=True)
    base=logs/(label+'-'+str(time.time_ns()))
    receipt={'schema_version':1,'argv':argv,'started_utc':now(),'source_sha256':verify_sources(contract)}
    child=None
    with base.with_suffix('.stdout.log').open('x') as stdout,base.with_suffix('.stderr.log').open('x') as stderr:
        try:
            blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                # Dedicated single-thread host daemon: unblock the child's inherited mask before exec.
                child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True,
                                       preexec_fn=lambda:signal.pthread_sigmask(signal.SIG_SETMASK,blocked))
                receipt['child_identity']=process_identity(child.pid)
                require(receipt['child_identity']['pid']==receipt['child_identity']['pgid']==receipt['child_identity']['sid'],
                        'Owned helper did not enter its own session')
                write(base.with_suffix('.json'),receipt)
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
            receipt['returncode']=child.wait(timeout=timeout)
        except BaseException as error:
            receipt['error']=f'{type(error).__name__}: {error}'
            if child is not None:
                try:finish_interrupted_child(child,receipt,label)
                except BaseException as cleanup:receipt['cleanup_error']=f'{type(cleanup).__name__}: {cleanup}'
            raise
        finally:
            receipt['finished_utc']=now()
            if child is not None and 'child_identity' in receipt:
                ident=receipt['child_identity']
                try:receipt['remaining_session_members']=group_members(ident['pgid'],ident['sid'])
                except BaseException as diagnostic:receipt['session_diagnostic_error']=f'{type(diagnostic).__name__}: {diagnostic}'
            try:receipt['source_sha256_after']=verify_sources(contract)
            except BaseException as changed:receipt['source_verification_error']=f'{type(changed).__name__}: {changed}'
            receipt['stdout_sha256']=sha(base.with_suffix('.stdout.log'));receipt['stderr_sha256']=sha(base.with_suffix('.stderr.log'))
            write(base.with_suffix('.json'),receipt)
    try:verify_sources(contract)
    finally:write(base.with_suffix('.json'),receipt)
    require(receipt['returncode']==0 and receipt.get('remaining_session_members')==[],
            'Child failed or left session members; logs/partial preserved: '+str(base))
    return read(base.with_suffix('.stdout.log'))

def local_ready(contract,native):
    """Recovery proof is distinct from the original143; no GPU starts."""
    verify_sources(contract)
    safe(MUTEX)
    safe(MUTEX,exists=True,file=True)
    with MUTEX.open('r+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'ready':False,'reason':'Shared fixed UUID native mutex occupied'}
        try:
            previous=native.recovered_previous()
            if previous.get('ready') is not True:
                return {'ready':False,'reason':'Recovered original629 and separate four not ready',
                        'previous_recovered_proof':previous}
            require(previous['status']=='recovered_previous_ready','Unknown recovered lifecycle state')
            try:idle=native.gpu_idle()
            except ValueError as error:
                require(str(error)=='Selected GPU has existing compute; never stop other work','GPU identity/readback failed: '+str(error))
                return {'ready':False,'reason':str(error)}
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
    verify_sources(contract)
    return {'ready':True,'previous_lifecycle':LIFECYCLE,'previous_recovered_proof':previous,
            'original_session54334_exit_code':143,'previous_receipt_sha256':sha(PREVIOUS),'gpu':idle,'mutex':str(MUTEX)}

def validate_completion(base,plan,native):
    native.verify_snapshot(base,plan)
    path=safe(base/'host/launch-receipt.json',exists=True,file=True);receipt=read(path)
    require(receipt.get('status')=='completed' and receipt.get('plan_sha256')==plan['plan_sha256']
            and all(type(receipt.get(k)) is int and receipt[k]==v for k,v in EXPECTED_COUNTS.items()),'Native58 terminal58/116/116/58 gate failed')
    require(receipt.get('quality_verified') is False and receipt.get('obstacle_course_completion_verified') is False,'Execution completion must not infer quality')
    require([x['id'] for x in receipt['phases']]==[x['id'] for x in plan['phases']],'Ordered native58 phase receipt differs')
    for actual,phase in zip(receipt['phases'],plan['phases']):
        require(actual['status']=='completed' and actual['driver_returncode']==actual['observer_returncode']==actual['driver_returncode_after_stop']==0
                and actual['owned_gpu_container_stop']['running_after_stop'] is False
                and actual['worker_exit0_empty_groups']==2*phase['cases'] and len(actual['host_maps'])==2*phase['cases']
                and actual['full_decoded_mp4_count']==phase['cases'],'Incomplete native58 phase/cleanup')
        record=actual['cpu_final'];file=safe(record['path'],exists=True,file=True,root=base)
        require(file==base/'phases'/phase['id']/'cpu-final/summary.json','CPU final path differs from frozen phase')
        require(sha(file)==record['sha256'] and file.stat().st_size==record['bytes'],'CPU final receipt changed')
        post=read(file)
        require(post['status']=='passed' and post['case_count']==phase['cases'] and post['worker_exit0_empty_groups']==2*phase['cases']
                and post['full_decoded_mp4_count']==phase['cases'],'CPU final exact counts differ')
    return {'receipt':str(path),'sha256':sha(path),**EXPECTED_COUNTS,'quality_verified':False}

class Waiter:
    def __init__(self,contract,directory,runner=invoke,gate=local_ready,adapter=adapters):
        self.contract=contract;self.directory=directory;self.runner=runner;self.gate=gate
        self.pull,self.common,self.native=adapter(contract)
        self.path=directory/'state.json';self.logs=directory/'logs';self.logs.mkdir(exist_ok=False)
        require(not self.path.exists(),'Existing waiter state retained; automatic restart/retry forbidden')
        self.state={'schema_version':1,'status':'waiting','started_utc':now(),'contract_identity':identity(contract),'action_started':False,
                    'fetch_attempted':False,'prepare_attempted':False,'run_attempted':False,'quality_verified':False,'polls':0}
        self.save()
    def save(self):self.state['observed_utc']=now();write(self.path,self.state)
    def action(self,name,argv,timeout=None):
        self.state.update(action_started=True,status=name+'_running');self.state[name+'_attempted']=True;self.save()
        result=self.runner(argv,self.logs,name,self.contract,timeout=timeout);verify_sources(self.contract);return result
    def step(self):
        verify_sources(self.contract)
        require(self.state['status'] not in ('failed','completed'),'Terminal waiter cannot repeat or resume actions')
        if not self.state['fetch_attempted']:
            argv=[sys.executable,str(PULL),'status','--source-tree',self.contract['remote_source_tree'],'--coverage-output',self.contract['coverage_output'],'--output-root',str(TRANSFER_ROOT)]
            observed=self.runner(argv,self.logs,'status',self.contract,timeout=540);verify_sources(self.contract);self.state['polls']+=1
            require(observed.get('status') in ('waiting','ready'),'Unknown pull status')
            if observed['status']=='waiting':
                self.state.update(status='waiting',stage='official_artifacts',remote_status=observed);self.save();return False
            self.pull.validate_receipt(observed)
            self.state['ready_snapshot_identity']=observed['snapshot_identity'];self.state['ready_cohort']=observed['cohort'];self.save()
            expected=TRANSFER_ROOT/observed['cohort']/'initial';safe(expected)
            require(not TRANSFER_ROOT.exists() and not NATIVE_OUTPUT.exists(),'Delivery destination already exists; never discover/reuse partial output')
            fetched=self.action('fetch',[sys.executable,str(PULL),'fetch','--source-tree',self.contract['remote_source_tree'],'--coverage-output',self.contract['coverage_output'],'--output-root',str(TRANSFER_ROOT),'--attempt','initial'])
            require(fetched.get('status')=='completed' and fetched.get('files')==32 and fetched.get('destination')==str(expected)
                    and fetched.get('transfer_tool_sha256')==verify_sources(self.contract)[str(PULL)],'Selective fetch did not complete exact bound32files')
            safe(expected,exists=True);before=read(safe(expected/'remote-before.json',exists=True,file=True))
            require(before['snapshot_identity']==observed['snapshot_identity'] and before['payload']==observed['payload'],'Fetch changed from the observed ready snapshot')
            require(self.common.transfer(WORKSPACE,expected)['status']=='ready','Transferred local provenance did not pass native58 gate')
            self.state.update(transfer=str(expected),fetch_result=fetched,status='waiting',stage='local_resource_release');self.save()
        ready=self.gate(self.contract,self.native)
        if not ready['ready']:
            self.state.update(status='waiting',stage='local_resource_release',local_gate=ready);self.save();return False
        self.state['local_gate']=ready;self.save()
        require(not self.state['prepare_attempted'] and not self.state['run_attempted'],'Previous action started; no automatic continuation/retry')
        prepared=self.action('prepare',[sys.executable,str(NATIVE/'native58.py'),'prepare','--workspace',str(WORKSPACE),'--transfer',self.state['transfer'],'--output',str(NATIVE_OUTPUT)])
        expected_plan=NATIVE_OUTPUT/'host-plan.json';safe(expected_plan,exists=True,file=True)
        require(prepared.get('status')=='prepared_only' and prepared.get('plan')==str(expected_plan) and prepared.get('actual_cpu_ort_cases')==60
                and prepared.get('cases')==58 and prepared.get('workers')==116,'Native58 CPU preparation incomplete')
        plan=read(expected_plan);self.native.verify_snapshot(NATIVE_OUTPUT,plan)
        require(plan['plan_sha256']==prepared['plan_sha256'] and plan['origin_transfer']['snapshot_identity']==self.state['ready_snapshot_identity'],'Prepared native58 plan points to another fetched pair')
        self.state['prepared_plan_sha256']=plan['plan_sha256'];self.save()
        # Final ownership check is repeated atomically under native58's own mutex.
        frozen=NATIVE_OUTPUT/'control/native58.py'
        safe(frozen,exists=True,file=True)
        require(sha(frozen)==verify_sources(self.contract)[str(NATIVE/'native58.py')],'Prepared native58 control copy changed')
        require(self.gate(self.contract,self.native)['ready'],'Local ownership changed during CPU prepare; stop for review without starting native')
        self.action('run',[sys.executable,str(frozen),'run','--workspace',str(WORKSPACE),'--plan',str(expected_plan),'--root-authorized-start'])
        final=validate_completion(NATIVE_OUTPUT,plan,self.native);verify_sources(self.contract)
        self.state.update(status='completed',finished_utc=now(),completion=final);self.save();return True
    def fail(self,error):
        self.state.update(status='failed',error=f'{type(error).__name__}: {error}',finished_utc=now(),partial_evidence_retained=True,automatic_retry=False);self.save()

def main():
    global CONTRACT_GUARD
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('check','watch'));p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--contract-sha256',required=True);p.add_argument('--self-sha256',required=True);p.add_argument('--root-authorized-watch',action='store_true');a=p.parse_args()
    safe(Path(__file__),exists=True,file=True);require(Path(__file__).parent==PREPARATION,'Use the dedicated reviewed preparer directory')
    require(sha(__file__)==a.self_sha256,'Waiter source differs from reviewed SHA');safe(a.contract,exists=True,file=True)
    require(a.contract==PREPARATION/'contract.json' and sha(a.contract)==a.contract_sha256,'Waiter contract SHA/path differs')
    CONTRACT_GUARD=(a.contract,a.contract_sha256)
    contract=read(a.contract);verify_sources(contract)
    if a.action=='check':print(json.dumps({'status':'prepared_only','armed':False,'contract_identity':identity(contract),'ssh_fetch_gpu_started':False}));return 0
    require(a.root_authorized_watch,'Explicit root authorization required to arm waiting/fetch/native58 actions')
    def interrupted(signum,_frame):raise KeyboardInterrupt('Owned waiter received signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    # Same existing singleton as the old waiter: Root must first end its exact
    # birth. An accidental overlapping arm fails before any status/fetch action.
    lockpath=WAITER_LOCK;safe(lockpath,exists=True,file=True)
    with lockpath.open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory=PREPARATION/'execution';safe(directory)
        require(not directory.exists(),'Existing execution/partial retained; root review required before any new cohort')
        directory.mkdir();waiter=Waiter(contract,directory)
        try:
            while not waiter.step():time.sleep(POLL_SECONDS)
        except BaseException as error:waiter.fail(error);raise
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'rejected','error':f'{type(error).__name__}: {error}','automatic_retry':False}),file=sys.stderr);raise SystemExit(1)
