"""Execute actual independent CPU phases against the frozen final teacher."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import subprocess

OUT = Path('/validation')

def fp(path):
    path=Path(path); h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''): h.update(b)
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':h.hexdigest()}

def inputs():
    manifest=Path('/control/input-manifest.json'); rows=json.loads(manifest.read_text())['records']
    for r in rows: assert fp(r['path'])==r, r['path']
    return [*rows,fp(manifest),*(fp(p) for p in sorted(Path('/code').glob('*.py')))]

def main():
    assert not any(OUT.iterdir()), 'Fresh validation directory required'
    before=inputs()
    report={'status':'running','started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'scope':'One real final official teacher CPU validation; no physics, whole-schedule or policy-quality completion',
            'inputs_before':before,'phases':[],'quality_verified':False,'official_schedule_complete':False,
            'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
            'nvidia_visible_devices':os.environ.get('NVIDIA_VISIBLE_DEVICES')}
    phases=[
      ('checkpoint',['/opt/php/bin/train-python','-B','/code/accept_teacher.py','checkpoint','--artifacts','/artifacts','--baseline','/control/model_00000.pt','--output','/validation/checkpoint.json']),
      ('scalars',['/opt/php/bin/train-python','-B','/code/accept_teacher.py','scalars','--artifacts','/artifacts','--output','/validation/scalars.json']),
      ('onnx',['/opt/php/bin/inference-python','-B','/code/validate_teacher_onnx.py','--model','/artifacts/model_19999.onnx','--output','/validation/onnx.json','--seed','2026','--expected-observation-dim','449']),
      ('bind',['/opt/php/bin/inference-python','-B','/code/accept_teacher.py','bind','--artifacts','/artifacts','--checkpoint-report','/validation/checkpoint.json','--scalars-report','/validation/scalars.json','--onnx-report','/validation/onnx.json','--output','/validation/bind.json']),
      ('plots',['/opt/php/bin/train-python','-B','/code/plot_learning_curves.py','--input','/validation/scalars.json','--output','/validation/plots'])]
    try:
        for label,argv in phases:
            row={'phase':label,'argv':argv,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
            with (OUT/(label+'.stdout.raw')).open('xb') as stdout, (OUT/(label+'.stderr.raw')).open('xb') as stderr:
                child=subprocess.Popen(argv,stdout=stdout,stderr=stderr); rc=child.wait()
            row.update(actual_wait_returncode=rc,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
            report['phases'].append(row)
            assert rc==0, f'{label} actual exit {rc}; retain original failure'
        after=inputs(); assert after==before
        report.update(status='passed',inputs_after=after,inputs_unchanged=True)
    except BaseException as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        peak=Path('/sys/fs/cgroup/memory.peak')
        if peak.exists(): report['cgroup_memory_peak_bytes']=int(peak.read_text())
        report['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        (OUT/'phases.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'actual_phase_exits':[r['actual_wait_returncode'] for r in report['phases']],
                      'inputs_unchanged':True,'official_schedule_complete':False,'quality_verified':False}))

if __name__=='__main__': main()
