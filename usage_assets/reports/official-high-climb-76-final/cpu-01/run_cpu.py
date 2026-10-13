"""Actually run one isolated CPU final-teacher acceptance; never touches trainers."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parent
IMAGE='sha256:2be18521015b2a84ef7a4442af9a94ef041a19feb9ce385ae15424b1dc158d8f'
NAME='php-official-high-climb-76-final-cpu-01'

def fp(path):
    p=Path(path).resolve(); h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}

def main():
    host=BASE/'host';validation=BASE/'validation'
    host.mkdir(exist_ok=False);validation.mkdir(exist_ok=False)
    source=[fp(p) for p in sorted((BASE/'source').glob('*.py'))]
    expected={'accept_teacher.py':'3023998a5e449cc7943f9d4e3c44d463f6780d1dd50465ea2961e3fb2d2ed062',
              'plot_learning_curves.py':'887ba33796d7395719b97bfaf8cb879d47ec45265515ef669c7245deec7fc554'}
    assert all(next(r for r in source if Path(r['path']).name==name)['sha256']==sha for name,sha in expected.items())
    original=ROOT/'scripts/research/validate_teacher_onnx.py'
    assert fp(original)['sha256']==fp(BASE/'source/validate_teacher_onnx.py')['sha256']
    argv=['docker','create','--name',NAME,'--runtime','runc','--init','--network','none','--cpus','2','--memory','12g',
          '--label','php.research.owner=official-high-climb-76-final-cpu-01',
          '-e','CUDA_VISIBLE_DEVICES=','-e','NVIDIA_VISIBLE_DEVICES=void','-e','PYTHONDONTWRITEBYTECODE=1',
          '-e','OMP_NUM_THREADS=1','-e','OPENBLAS_NUM_THREADS=1','-e','MKL_NUM_THREADS=1',
          '-e','ACCEPT_EULA=Y','-e','OMNI_KIT_ACCEPT_EULA=YES']
    for src,dst,ro in [(BASE/'source','/code',True),(BASE/'input','/control',True),
                       (BASE.parent/'teacher-high-climb-76-final-01/artifacts','/artifacts',True),
                       (validation,'/validation',False)]:
        argv += ['--mount',f'type=bind,src={src.resolve()},dst={dst}'+(',readonly' if ro else '')]
    argv += [IMAGE,'/usr/bin/python3','-B','/code/run_cpu_phases.py']
    report={'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'helper':fp(__file__),
            'source_before':source,'create_argv':argv,'quality_verified':False,'official_schedule_complete':False}
    r=subprocess.run(argv,capture_output=True)
    (host/'create.stdout.raw').write_bytes(r.stdout);(host/'create.stderr.raw').write_bytes(r.stderr)
    report['create_actual_returncode']=r.returncode;assert r.returncode==0,r.stderr.decode(errors='replace')
    cid=r.stdout.decode().strip();report['container_id']=cid
    raw=subprocess.check_output(['docker','inspect',cid]);(host/'inspect-before.raw.json').write_bytes(raw);before=json.loads(raw)[0]
    assert before['Id']==cid and before['Image']==IMAGE and before['Name']=='/'+NAME
    rc=None
    try:
        with (host/'start.stdout.raw').open('xb') as stdout,(host/'start.stderr.raw').open('xb') as stderr:
            child=subprocess.Popen(['docker','start','--attach',cid],stdout=stdout,stderr=stderr);rc=child.wait()
        report['actual_start_attached_wait_returncode']=rc
    finally:
        raw=subprocess.check_output(['docker','inspect',cid]);after=json.loads(raw)[0]
        assert after['Id']==cid and after['Image']==IMAGE and after['Name']=='/'+NAME
        if after['State']['Running']:
            stop=subprocess.run(['docker','stop','--time','20',cid],capture_output=True)
            (host/'stop.stdout.raw').write_bytes(stop.stdout);(host/'stop.stderr.raw').write_bytes(stop.stderr)
            report['owned_cleanup_stop_returncode']=stop.returncode
            raw=subprocess.check_output(['docker','inspect',cid]);after=json.loads(raw)[0]
        (host/'inspect-after.raw.json').write_bytes(raw)
        report.update(container_running=after['State']['Running'],actual_container_exit_code=after['State']['ExitCode'],
                      source_after=[fp(p) for p in sorted((BASE/'source').glob('*.py'))],finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        report['source_unchanged']=report['source_after']==report['source_before']
        (host/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
    assert rc==0 and report['actual_container_exit_code']==0 and not report['container_running'] and report['source_unchanged']
    phases=json.loads((validation/'phases.json').read_bytes());assert phases['status']=='passed'
    print(json.dumps({'status':'passed','container_id':cid,'actual_container_exit_code':0,
                      'actual_start_attached_wait_returncode':rc,'phase_exits':[r['actual_wait_returncode'] for r in phases['phases']],
                      'source_unchanged':True,'quality_verified':False,'official_schedule_complete':False}))

if __name__=='__main__': main()
