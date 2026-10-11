"""CPU-only actual plan/import/ORT preparation or post-run native evidence decode."""
from __future__ import annotations
import argparse
import copy
import csv
import dataclasses
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from common import IMAGE, MATRIX_SHA, SUPERVISOR_SHA, SDK, MODELS, identity, load, read, record, require, sha, write

ROOT=Path('/workspace/php_parkour')


def matrix():
    source=ROOT/'scripts/research/sim2sim_scene_matrix.py'
    require(sha(source)==MATRIX_SHA and sha(ROOT/'scripts/research/sim2sim.py')==SUPERVISOR_SHA,
            'Frozen native source revision differs')
    return load(source,'native58_cpu_matrix')


def scene_args():
    return ['--matrix','/data/matrix.json','--models','/data/assets/student','--output','/outputs/scenes17',
            '--seconds','10.0','--seed','42','--gl','egl','--sim-python','/opt/php/bin/train-python',
            '--inference-python','/opt/php/bin/inference-python','--image-id',IMAGE]


def plans(m):
    args=SimpleNamespace(matrix=Path('/data/matrix.json'),models=Path('/data/assets/student'),
        output=Path('/outputs/scenes17'),seconds=10.0,seed=42,gl='egl',sim_python='/opt/php/bin/train-python',
        inference_python='/opt/php/bin/inference-python',image_id=IMAGE,all_configs=False)
    scenes=m.make_plan(args)
    require(scenes['schema_version']==3 and scenes['planned_scenarios']==scenes['planned_configurations']==17
            and scenes['all_configurations'] is False,'Actual native default17 selection changed')
    old=read('/data/baseline-native-plan.json')
    require(old['schema_version']==3 and old['seed']==42 and len(old['selections'])==12
            and [s['command'] for s in old['selections']]==list(range(12))
            and old['dependencies']==scenes['dependencies'],'Baseline12/actual canonical closure changed')
    directions=copy.deepcopy(old)
    directions['models']=scenes['models'];directions['model_sha256']=scenes['model_sha256']
    directions['control_files']=[dict(record(p),path='/control/'+p.name)
        for p in sorted(Path('/control').glob('*.py'))]
    directions['expected_sdk_extension_sha256']=SDK
    directions['model_origin_scope']='Two newly fetched official student exports; not released baseline model weights'
    for s in directions['selections']:
        expected=s['expected_config']
        require(expected['model_sha256']==old['model_sha256'] and expected['models']=='/data/assets/student'
                and expected['seconds_per_command']==8.0 and expected['wall_timeout']==373.0
                and expected['startup_timeout']==180.0 and expected['seed']==42,'Baseline native default timing changed')
        expected['model_sha256']=scenes['model_sha256']
        expected['python_faulthandler']=True
    directions['plan_sha256']=identity({k:v for k,v in directions.items() if k!='plan_sha256'})
    from commands_executor import verify_plan
    verify_plan(directions,m)
    require(m.dependencies()==scenes['dependencies'],'Actual source dependencies changed during CPU preparation')
    return directions,scenes


def call(argv, prefix, timeout=300):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    Path(str(prefix)+'.stdout.log').write_text(result.stdout)
    Path(str(prefix)+'.stderr.log').write_text(result.stderr)
    require(result.returncode==0,'CPU subprocess failed; original logs retained: '+str(prefix))
    return {'argv':argv,'returncode':result.returncode,'stdout':record(str(prefix)+'.stdout.log'),
            'stderr':record(str(prefix)+'.stderr.log')}


def prepare(output):
    require(os.environ.get('CUDA_VISIBLE_DEVICES')=='' and os.environ.get('NVIDIA_VISIBLE_DEVICES')=='void',
            'Explicit no-device runtime required')
    require(not output.exists(),'Fresh CPU preparation report required')
    report={'schema_version':1,'status':'running','native_started':False,'gpu_started':False,
            'started_unix':time.time(),'source_sha256':sha(__file__),'image_id':IMAGE,'commands':[]}
    write(output,report)
    try:
        m=matrix();directions,scenes=plans(m)
        write(output.parent/'directions-plan.json',directions);write(output.parent/'scenes-plan.json',scenes)
        imported=copy.deepcopy(scenes);imported['selections']=directions['selections']+scenes['selections']
        imported['scope']='Import/config-only union of 12 plane commands and 17 representative terrains'
        imported['plan_sha256']=identity({k:v for k,v in imported.items() if k!='plan_sha256'})
        write(output.parent/'import-plan.json',imported)
        for role,python in [('simulator','/opt/php/bin/train-python'),('inference','/opt/php/bin/inference-python')]:
            argv=[python,'/control/verify_snapshot_imports.py','--role',role,'--plan',str(output.parent/'import-plan.json'),
                  '--output',str(output.parent/(role+'.json'))]
            report['commands'].append(call(argv,output.parent/role))
            item=read(output.parent/(role+'.json'))
            require(item['status']=='passed' and item['sdk']['version']=='0.1.8' and item['sdk']['sha256']==SDK[role]
                    and item['native_instances_created'] is False and item['robot_or_dds_construction_attempts']==[],
                    'CPU imported SDK/constructor/config gate failed')
        ort=load(ROOT/'scripts/research/validate_onnx.py','native58_cpu_ort')
        checked=ort.validate(Path('/data/assets/student/depth_backbone.onnx'),Path('/data/assets/student/student.onnx'),2026)
        require(checked['status']=='passed' and len(checked['cases'])==30,'Each real final pair needs all30 CPU ORT cases')
        from holosoma_inference.config.config_values.inference import g1_wbt_distillation_d435i
        robot=g1_wbt_distillation_d435i.robot
        checked['native_default_pose_compatibility']=pose_contract(checked['models'][1]['metadata'],robot)
        write(output.parent/'onnx.json',checked)
        report.update(status='passed',directions_plan_sha256=directions['plan_sha256'],scenes_plan_sha256=scenes['plan_sha256'],
                      directions_cases=12,scene_cases=17,ort_cases=30,dependencies=len(scenes['dependencies']),
                      selected_scene_case_ids=[s['case_id'] for s in scenes['selections']],
                      expected_policy_ticks={'directions':400,'scenes':500},quality_verified=False)
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_unix']=time.time();write(output,report)


def pose_contract(metadata,robot):
    """Native policy uses preset defaults, so mismatched exports must stop here."""
    joints=[name.strip() for name in metadata['joint_names'].split(',')]
    native=list(robot.dof_names)
    require(len(joints)==len(native)==29 and len(set(joints))==29 and set(joints)==set(native),
            'Model joint set differs from native preset')
    defaults=[float(x) for x in metadata['default_joint_pos'].split(',')]
    require(len(defaults)==29 and all(math.isfinite(x) for x in defaults),'Malformed model default pose')
    reordered=[defaults[joints.index(name)] for name in native]
    maximum=max(abs(a-b) for a,b in zip(reordered,robot.default_dof_angles))
    require(maximum<=0.000501,'Export default pose differs from actual native preset beyond exporter3decimal rounding')
    return {'status':'passed','native_joint_names':native,'model_joint_names':joints,
            'native_to_model_permutation':[joints.index(name) for name in native],
            'max_default_pose_absolute_error':maximum,'export_metadata_rounding_tolerance':0.000501,
            'scope':'Native fixed observation order/config gains remain unchanged; metadata observation_names does not reorder native wire fields'}


def finite_json(value):
    if isinstance(value,float):require(math.isfinite(value),'Nonfinite raw JSON number')
    elif isinstance(value,dict):
        for item in value.values():finite_json(item)
    elif isinstance(value,list):
        for item in value:finite_json(item)


def finalize(phase, output):
    require(os.environ.get('CUDA_VISIBLE_DEVICES')=='' and os.environ.get('NVIDIA_VISIBLE_DEVICES')=='void',
            'CPU finalizer requires no-device runtime')
    require(not output.exists(),'Fresh independent finalization report required')
    m=matrix();plan=read('/data/'+phase+'-plan.json')
    report={'schema_version':1,'status':'running','phase':phase,'started_unix':time.time(),'cases':[],
            'native_started':False,'gpu_started':False,'image_id':IMAGE,'native_plan_sha256':plan['plan_sha256'],
            'quality_verified':False,'obstacle_course_completion_verified':False}
    write(output,report)
    try:
        if phase=='directions':
            summary=read('/outputs/pilot-summary.json')
            require(summary['status']=='completed' and summary['native_plan_sha256']==plan['plan_sha256']
                    and len(summary['cases'])==12 and summary['remaining_native_pids']==[], 'Complete original12 phase required')
            cases=summary['cases'];count=12;ticks=400;wall=373.0
        else:
            summary=read('/outputs/scenes17/matrix.json');cases=summary['selections'];count=17;ticks=500;wall=413.0
            require(summary['status']=='completed' and summary['plan_sha256']==plan['plan_sha256']
                    and summary['completed_configurations']==summary['completed_scenarios']==len(cases)==17
                    and not summary['last_invocation']['resume'] and not summary['last_invocation']['case_ids']
                    and summary['last_invocation']['case_limit'] is None
                    and read('/outputs/scenes17/plan.json')==plan,'Fresh unfiltered exact17 phase required')
        from commands_executor import decode_videos
        for expected,case in zip(plan['selections'],cases):
            require(expected['case_id']==case['case_id'] and case['status']=='completed','Ordered native case changed')
            if phase=='directions':
                require(case['returncode']==0 and case['launch']==expected['launch'],'Direction parent/config launch changed')
                directory=Path(expected['output'])
            else:
                require(len(case['attempts'])==1 and case['attempts'][0]['returncode']==0,'Only a fresh single attempt may pass')
                m.verify_completed(case['attempts'][0],plan,case)
                directory=Path(case['attempts'][0]['output'])
            m.verify_inputs(plan,expected)
            result=m.validate_result(directory/'result.json',plan,expected)
            require(result['inference']['ticks']==ticks and result['config']['wall_timeout']==wall
                    and result['config']['startup_timeout']==180.0,'Actual native ticks/default timing changed')
            if phase=='directions':require(result['config']==expected['expected_config'],'Only final model weights may differ from direction baseline')
            require(len(result['videos'])==1,'Exactly one MP4 per case required')
            receipts=m.validate_worker_receipts(directory,plan,result)
            decoded=decode_videos(directory,result)
            files=[]
            for path in sorted(directory.rglob('*')):
                require(not path.is_symlink(),'Symlink in native evidence tree')
                if path.is_file():
                    if path.suffix=='.json':finite_json(read(path))
                    files.append(record(path))
            report['cases'].append({'case_id':expected['case_id'],'output':str(directory),'worker_receipts':receipts,
                'worker_exit0_empty_groups':2,'ticks':ticks,'actual_wall_timeout_seconds':wall,
                'native_result_sha256':sha(directory/'result.json'),'video_full_decodes':decoded,'files':files,
                'survival_heuristic_passed':result['survival_passed'],'quality_verified':False})
            write(output,report)
        require(len(report['cases'])==count,'Final native case count changed')
        report.update(status='passed',case_count=count,worker_exit0_empty_groups=2*count,full_decoded_mp4_count=count)
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:report['finished_unix']=time.time();write(output,report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','finalize'))
    p.add_argument('--phase',choices=('directions','scenes'));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.output)
    else:
        require(a.phase is not None,'Finalizer needs explicit phase');finalize(a.phase,a.output)


if __name__=='__main__':main()
