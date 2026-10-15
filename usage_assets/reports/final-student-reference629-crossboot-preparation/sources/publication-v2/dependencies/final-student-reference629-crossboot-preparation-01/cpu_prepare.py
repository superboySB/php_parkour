"""Future no-device container only: fresh official-pair reference plan/import/ORT/pose."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
from types import SimpleNamespace
sys.dont_write_bytecode=True
sys.path.insert(0,'/control/frozen')
from common import IMAGE, SDK, read, record, require, write

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    require(os.environ.get('CUDA_VISIBLE_DEVICES')=='' and os.environ.get('NVIDIA_VISIBLE_DEVICES')=='void','No-device CPU runtime required')
    output=Path('/preflight');plan_path=output/'reference-plan.json'
    require(not plan_path.exists(),'Fresh CPU plan output required')
    m=load('/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py','official_reference_plan')
    args=SimpleNamespace(matrix=Path('/data/matrix.json'),models=Path('/data/assets/student'),output=Path('/outputs/reference629'),
      seconds=10.0,seed=42,gl='egl',sim_python='/opt/php/bin/train-python',inference_python='/opt/php/bin/inference-python',
      image_id=IMAGE,all_configs=True,reference_commands=True)
    plan=m.make_plan(args)
    require(plan['planned_configurations']==629 and plan['planned_scenarios']==17 and plan['reference_commands'] is True
      and all('reference_commands' in c and '--reference-motion' in c['launch'] and '--reference-spawn' in c['launch']
        and '--record-policy' in c['launch'] and '--commands' not in c['launch'] for c in plan['selections']), 'Reference full-frame scope changed')
    write(plan_path,plan);imports=[]
    for role,python in [('simulator','/opt/php/bin/train-python'),('inference','/opt/php/bin/inference-python')]:
        argv=[python,'-B','/control/frozen/verify_snapshot_imports.py','--role',role,'--plan',str(plan_path),'--output',str(output/(role+'.json'))]
        with (output/(role+'.stdout.raw')).open('xb') as stdout,(output/(role+'.stderr.raw')).open('xb') as stderr:
            done=subprocess.run(argv,stdout=stdout,stderr=stderr)
        report=read(output/(role+'.json'))
        require(done.returncode==0 and report['status']=='passed' and report['sdk']['sha256']==SDK[role]
          and report['native_instances_created'] is False and report['robot_or_dds_construction_attempts']==[], 'Actual selected imports/SDK failed')
        imports.append({'argv':argv,'returncode':done.returncode,'report':record(output/(role+'.json'))})
    ort=load('/control/frozen/validate_onnx.py','official_reference_ort')
    checked=ort.validate(Path('/data/assets/student/depth_backbone.onnx'),Path('/data/assets/student/student.onnx'),2026)
    require(checked['status']=='passed' and len(checked['cases'])==30,'Actual official-pair ORT failed')
    from phase_cpu import pose_contract
    from holosoma_inference.config.config_values.inference import g1_wbt_distillation_d435i
    checked['native_default_pose_compatibility']=pose_contract(checked['models'][1]['metadata'],g1_wbt_distillation_d435i.robot)
    write(output/'onnx.json',checked)
    write(output/'summary.json',{'status':'passed','image_id':IMAGE,'plan':record(plan_path),'native_plan_identity':plan['plan_sha256'],
      'configurations':629,'scenarios':17,'ort_cases':30,'models':plan['models'], 'pose':checked['native_default_pose_compatibility'],
      'reference_frames':sum(c['reference_commands']['frames'] for c in plan['selections']),'imports':imports,
      'native_started':False,'gpu_started':False,'quality_verified':False})

if __name__=='__main__':main()
