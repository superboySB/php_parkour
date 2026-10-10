#!/usr/bin/env python3
"""CPU-only post-run629 evidence/receipt/hash verification and full MP4 decode."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ROOT=Path('/workspace/php_parkour')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path,value):
    temporary=path.with_name(path.name+'.tmp');temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh CPU finalization receipt required')
    plan=json.loads(args.plan.read_text());raw=Path('/outputs/all-configs/matrix.json');report=json.loads(raw.read_text())
    result={'schema_version':1,'status':'running','scope':'Read-only native evidence and CPU full video decode; no simulator/DDS/GPU',
            'started_unix':time.time(),'native_plan_sha256':plan['plan_sha256'],'matrix_sha256':sha(raw),'cases':[]}
    write(args.output,result)
    try:
        if (report['status']!='completed' or report['completed_configurations']!=629 or report['completed_scenarios']!=17
                or not report['configuration_coverage_complete'] or len(report['selections'])!=629
                or report['last_invocation']['case_ids'] or report['last_invocation']['case_limit'] is not None
                or report['last_invocation']['resume'] or report['last_invocation']['requested_configurations']!=629):
            raise ValueError('Only fresh unfiltered complete629 matrix may pass finalization')
        if json.loads(Path('/outputs/all-configs/plan.json').read_text()) != plan:raise ValueError('Executed plan differs from CPU plan')
        spec=importlib.util.spec_from_file_location('native_matrix',ROOT/'scripts/research/sim2sim_scene_matrix.py')
        matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
        if any(report.get(key)!=value for key,value in plan.items() if key not in ('status','selections')):raise ValueError('Matrix immutable identity differs')
        workers=0;videos=0
        for expected,case in zip(plan['selections'],report['selections']):
            if any(case.get(key)!=value for key,value in expected.items()):raise ValueError('Case native input identity differs')
            attempts=case['attempts']
            if case['status']!='completed' or len(attempts)!=1 or attempts[0]['status']!='completed' or attempts[0]['returncode']!=0:
                raise ValueError('Fresh once-only completed attempt required')
            matrix.verify_inputs(plan,expected);matrix.verify_completed(attempts[0],plan,case)
            directory=Path(attempts[0]['output']);native=json.loads((directory/'result.json').read_text())
            sealed=matrix.validate_worker_receipts(directory,plan,native)
            if native['inference']['ticks']!=500:raise ValueError('Expected500 policy ticks')
            workers+=2
            decoded=[]
            if len(native['videos'])!=1:raise ValueError('Exactly one fresh native MP4 per configuration required')
            for relative in native['videos']:
                path=(directory/relative).resolve()
                if not path.is_relative_to(directory.resolve()) or path.is_symlink():raise ValueError('Unsafe video path')
                before=sha(path)
                command=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-threads','1','-i',str(path),'-f','null','-']
                completed=subprocess.run(command,capture_output=True,text=True,timeout=120)
                decode={'path':str(path),'sha256':before,'bytes':path.stat().st_size,'command':command,
                        'returncode':completed.returncode,'stderr':completed.stderr,'full_decode':completed.returncode==0}
                if completed.returncode or before!=sha(path):raise ValueError('Immutable full video decode failed: '+case['case_id'])
                decoded.append(decode);videos+=1
            result['cases'].append({'case_id':case['case_id'],'native_result_sha256':sha(directory/'result.json'),
                                    'parent_returncode':0,'worker_receipts':sealed,'worker_exit0_empty_groups':2,'policy_ticks':500,
                                    'videos':decoded,'survival_heuristic_passed':native['survival_passed'],
                                    'quality_verified':False,'obstacle_course_completion_verified':False})
            write(args.output,result)
        if workers!=1258 or videos!=629:raise ValueError('Final exact worker/video counts differ')
        result.update(status='passed',worker_exit0_empty_group_count=workers,full_decoded_mp4_count=videos,
                      configurations=629,scenarios=17,quality_verified=False,obstacle_course_completion_verified=False)
    except BaseException as error:
        result.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        result['finished_unix']=time.time();write(args.output,result)

if __name__=='__main__':main()
