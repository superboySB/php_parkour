"""Read-only host-stdlib collection; no docker exec or scientific package reads."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess
ROOT=Path('/diff/dzp_is_sb/php-parkour-research');TREE='0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab';SRC=ROOT/'source'/TREE
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(argv):return subprocess.run(argv,capture_output=True,text=True,check=True).stdout
def record(p):
 p=Path(p);data=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'text':data.decode()}
def proc(pid):
 p=Path('/proc')/str(pid)
 return {'pid':pid,'stat':(p/'stat').read_text(),'cmdline':(p/'cmdline').read_bytes().decode().split('\0')}
r={'schema_version':1,'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Read-only inspect/top and existing host files; no docker exec, restart, change or GPU/DDS job','source_tree':TREE}
info=json.loads(get(['docker','inspect','--type','container','php-parkour-cloud-research']))[0]
r['container_inspect']=info;r['docker_top']=get(['docker','top','php-parkour-cloud-research','-eo','pid,ppid,args'])
r['native_processes']=[proc(int(x.split(None,1)[0])) for x in r['docker_top'].splitlines() if ' -m wbt_training.train_agent ' in x]
manifest=json.loads((SRC/'source-manifest.json').read_text());r['original_source_manifest']=manifest
mismatch=[]
for f in manifest['files']:
 p=SRC/f['path'];actual=hashlib.sha256(os.readlink(p).encode()).hexdigest() if f['symlink'] else sha(p)
 if actual!=f['sha256']:mismatch.append({'path':f['path'],'expected':f['sha256'],'actual':actual})
r['original_manifest_sha256']=sha(SRC/'source-manifest.json');r['original_source_recorded_files_unchanged']=not mismatch;r['source_mismatches']=mismatch
files=['scripts/research/train_pipeline.py','scripts/research/run_official_acceptance.sh','scripts/research/eval_quality.py','scripts/research/eval_quality.sh','scripts/research/train_pipeline.sh','scripts/research/validate_teacher_exports.py','scripts/research/validate_teacher_onnx.py','wbt_training/train_agent.py','wbt_training/training_runs/eval_teacher.py','wbt_training/training_runs/eval_student.py','wbt_training/training_runs/export_distill_onnx.py','wbt_training/training_runs/setup_env.sh','thirdparty/holosoma/src/holosoma/holosoma/simulator/isaacsim/isaacsim.py','thirdparty/holosoma/src/holosoma/holosoma/config_values/robot/g1.py']
r['sources']={rel:record(SRC/rel) for rel in files if (SRC/rel).is_file()};r['missing_sources']=[rel for rel in files if not (SRC/rel).is_file()]
logs=ROOT/'outputs/official-full-driver.log';data=logs.read_bytes();r['driver_log_snapshot']={'path':str(logs),'read_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'tail_text':data[-30000:].decode(errors='replace')}
r['stages']={}
for p in sorted((ROOT/'outputs/official-full/official/manifests').glob('*.json')):r['stages'][p.stem]=record(p)
r['saved_configs']={}
for p in sorted((ROOT/'outputs/official-full/official').glob('*/PHP-research/*/holosoma_config.yaml')):r['saved_configs'][str(p.relative_to(ROOT))]=record(p)
robots=SRC/'thirdparty/holosoma/src/holosoma/holosoma/data/robots'
r['robot_asset_directory']={'path':str(robots),'exists':robots.is_dir(),'mode':oct(robots.stat().st_mode&0o777),'generated_dirs':[{'path':str(p),'mode':oct(p.stat().st_mode&0o777),'usd_files':[str(f.relative_to(p)) for f in p.rglob('*.usd')]} for p in sorted(robots.glob('converted_rank*'))]}
status=ROOT/'outputs/coverage-official-final-ro-assets-v2/monitor-status.json'
r['monitor_status']=record(status) if status.is_file() else None
r['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();print(json.dumps(r,indent=2))
