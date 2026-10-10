"""Independent CPU-only terminal verification of canonical12 actual native runs."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,subprocess,time
from pathlib import Path
ROOT=Path('/workspace/php_parkour');IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def invalid(value):raise ValueError('Nonfinite JSON constant: '+value)
def load(p):return json.loads(Path(p).read_text(),parse_constant=invalid)
def finite(value):
    if isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite numeric evidence')
    if isinstance(value,dict):
        for v in value.values():finite(v)
    if isinstance(value,list):
        for v in value:finite(v)
def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(p,r):p.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
def verify(out):
    if out.exists():raise ValueError('Fresh independent report required')
    host=load('/cohort/pilot-plan.json');native=load('/data/native-plan.json');receipt=load('/cohort/host/launch-receipt.json')
    observer=load('/cohort/host/observer/summary.json');summary=load('/outputs/pilot-summary.json');oldmatrix=load('/data/baseline-matrix.json')
    report={'schema_version':1,'status':'running','started_unix':time.time(),'image_id':IMAGE,'cases':[],
            'scope':'Independent CPU read/hash/native schema validator/full video decode; no DDS/Robot/simulation',
            'quality_verified':False,'obstacle_course_completion_verified':False,'source_sha256':sha(__file__)};save(out,report)
    try:
        original=dict(host);recorded=original.pop('plan_sha256')
        if identity(original)!=recorded or host['image_id']!=IMAGE:raise ValueError('Host plan/image changed')
        if (receipt['status']!='completed' or receipt['plan_sha256']!=recorded or receipt['driver_returncode']!=0
                or receipt['driver_returncode_after_container_stop']!=0 or receipt['observer_returncode']!=0
                or receipt['owned_container_running_after_stop'] or receipt.get('cleanup_error')):raise ValueError('Real host/driver/observer/owned-container terminal state not passed')
        if (observer['identity']['container_id']!=receipt['container_id'] or observer['identity']['image_id']!=IMAGE
                or observer['stop_reason']!='stop_file' or observer['errors'] or not observer['mapping_scope_complete']):raise ValueError('Observer exactCID/complete lifetime differs')
        info=load('/cohort/host/container-inspect.json')
        if info['State']['StartedAt']!=observer['identity']['started_at']:raise ValueError('Observer container birth differs')
        for item in host['snapshot_files']:
            path=Path('/cohort')/item['relative']
            if path.is_symlink() or not path.resolve().is_relative_to('/cohort') or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:raise ValueError('Frozen snapshot drift: '+item['relative'])
        if sha('/data/native-plan.json')!=host['native_plan_file_sha256'] or native['plan_sha256']!=host['native_plan_sha256']:raise ValueError('Native plan identity changed')
        original=dict(native);recorded=original.pop('plan_sha256')
        if identity(original)!=recorded:raise ValueError('Native plan content identity changed')
        if summary['status']!='completed' or len(summary['cases'])!=12 or summary['remaining_native_pids']!=[]:raise ValueError('Complete12 native summary required')
        spec=importlib.util.spec_from_file_location('native_matrix',ROOT/'scripts/research/sim2sim_scene_matrix.py')
        matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
        mappings=[];threads=set();workers=0;videos=0;raws=[]
        for code,(selection,case) in enumerate(zip(native['selections'],summary['cases'])):
            if case['case_id']!=selection['case_id'] or selection['command']!=code or case['status']!='completed' or case['returncode']!=0 or case['launch']!=selection['launch']:raise ValueError('Original ordered command/native execution differs')
            directory=Path(selection['output']);result_path=directory/'result.json';result=load(result_path)
            matrix.verify_inputs(native,selection);matrix.validate_result(result_path,native,selection)
            sealed=matrix.validate_worker_receipts(directory,native,result)
            cfg=load(directory/'run.json');baseline=load(f'/data/baseline-runs/command-{code:02d}.json')
            expected=baseline|{'record_policy':False,'course_guide':False,'python_faulthandler':True}
            if cfg!=selection['expected_config'] or cfg!=expected or result['config']!=cfg or cfg['wall_timeout']!=373.0 or cfg['startup_timeout']!=180.0 or '--wall-timeout' in case['launch']:raise ValueError('Actual native timing/config differs from original baseline')
            if result['inference']['ticks']!=400 or case['policy_ticks']!=400 or result['simulation']['policy_simulation_seconds']<8.0:raise ValueError('Expected400ticks/8simseconds')
            actual_command=result['inference']['commands'][0];old_command=oldmatrix['commands'][code]['result']['inference']['commands'][0]
            if actual_command['code']!=code or actual_command['name']!=old_command['name']:raise ValueError('Actual policy command label differs')
            exact=[]
            for role in ['simulator','inference']:
                entry_path=directory/(role+'-process-start.json');entry=load(entry_path);process=entry['process']
                found=[m for m in observer['command_writer_mappings'] if m['role']==role and m['worker_output']==str(directory)
                       and m['container_tgid']==process['pid'] and m['owner_start_time_clock_ticks']==process['start_time_clock_ticks']]
                if len(found)!=1:raise ValueError('One exact host writer mapping required')
                m=found[0];key=(m['host_tid'],m['start_time_clock_ticks'])
                if key in threads or m['nspid']!=[m['host_tid'],m['container_tid']] or m['nstgid']!=[m['host_tgid'],process['pid']]:raise ValueError('Host thread namespace/uniqueness differs')
                threads.add(key);exact.append({'role':role,'native_entry_sha256':sha(entry_path),'mapping':m});workers+=1
            decoded=[]
            if len(result['videos'])!=1:raise ValueError('One actual MP4 per command required')
            for relative in result['videos']:
                path=(directory/relative).resolve()
                if path.is_symlink() or not path.is_relative_to(directory):raise ValueError('Video path escapes actual case')
                before=sha(path);argv=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-threads','1','-i',str(path),'-f','null','-']
                d=subprocess.run(argv,capture_output=True,text=True,timeout=120)
                if d.returncode or before!=sha(path):raise ValueError('Independent full MP4 decode failed')
                decoded.append({'path':str(path),'bytes':path.stat().st_size,'sha256':before,'command':argv,'returncode':d.returncode,'stderr':d.stderr,'full_decode':True});videos+=1
            files=[]
            for path in sorted(directory.rglob('*')):
                if not path.is_file():continue
                if path.suffix=='.json':finite(load(path))
                files.append({'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
            report['cases'].append({'command':code,'case_id':case['case_id'],'parent_returncode':0,'policy_ticks':400,
                'actual_wall_timeout_seconds':cfg['wall_timeout'],'actual_startup_timeout_seconds':cfg['startup_timeout'],
                'actual_seed':cfg['seed'],'simulation_seconds':result['simulation']['policy_simulation_seconds'],
                'worker_receipts':sealed,'host_maps':exact,'videos':decoded,'raw_json_numbers_finite':True,
                'original_identity_and_config_preserved':True,'survival_heuristic_passed':result['survival_passed'],
                'path_length_xy_m':result['simulation']['path_length_xy_m'],'heading_change_deg':result['simulation']['heading_change_deg'],
                'files':files,'quality_verified':False});save(out,report)
        if workers!=24 or videos!=12:raise ValueError('Exact24workers/12videos required')
        report.update(status='passed',commands=12,worker_exit0_empty_groups=workers,exact_host_thread_mappings=len(threads),
                      full_decoded_mp4_count=videos,host_wall_seconds=receipt['finished_unix']-receipt['started_unix'],
                      native_wall_seconds=summary['finished_unix']-summary['started_unix'],native_plan_sha256=native['plan_sha256'],
                      host_plan_sha256=host['plan_sha256'],container_id=receipt['container_id'],source_files_verified=len(host['snapshot_files']),
                      original12baseline_sha256=host['baseline_matrix_sha256'],raw_parent_receipt_sha256=sha('/cohort/host/launch-receipt.json'))
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:report['finished_unix']=time.time();save(out,report)
    print(json.dumps({k:report[k] for k in ['status','commands','worker_exit0_empty_groups','exact_host_thread_mappings','full_decoded_mp4_count']}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);verify(p.parse_args().output)
