"""CPU-only actual native dependency and frozen original12 command plan gate."""
import argparse,importlib.util,json,sys
from pathlib import Path
sys.path.insert(0,'/control')
from commands_executor import verify_plan,sha,save
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise ValueError('Fresh CPU gate output required')
root=Path('/workspace/php_parkour');source=root/'scripts/research/sim2sim_scene_matrix.py'
spec=importlib.util.spec_from_file_location('native_matrix',source);matrix=importlib.util.module_from_spec(spec);spec.loader.exec_module(matrix)
plan=json.loads(a.plan.read_text());verify_plan(plan,matrix)
if matrix.dependencies()!=plan['dependencies']:raise ValueError('Actual canonical native dependency closure differs')
save(a.output,{'status':'passed','native_started':False,'native_plan_sha256':plan['plan_sha256'],'actual_dependencies':len(plan['dependencies']),
              'commands':[c['command'] for c in plan['selections']],'seed':42,'seconds_per_command':8.0,'policy_ticks_per_command':400,
              'startup_timeout_seconds':180.0,'expected_native_wall_timeout_seconds':373.0,'probe_sha256':sha(__file__)})
print(json.dumps({'status':'passed','native_started':False,'commands':12,'dependencies':len(plan['dependencies'])}))
