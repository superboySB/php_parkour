#!/usr/bin/env python3
"""CPU package metadata and installed-environment resolver checks; no installs."""
import datetime
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys

OUT = Path('/audit/actual-freezes')
OUT.mkdir(exist_ok=False)
BASE = Path('/workspace/php_parkour')


def main():
    runtimes=[]
    environment=os.environ | {'PIP_CONFIG_FILE':'/dev/null','PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1',
        'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'','NVIDIA_VISIBLE_DEVICES':'none'}
    for name,package,constraint in [('train','holosoma','constraints.train-added.txt'),('inference','holosoma-inference','constraints.inference.txt'),('motion',None,None)]:
        python='/opt/php/bin/'+name+'-python'
        code='import importlib.metadata as m,json,sys; print(json.dumps({"python":sys.version,"executable":sys.executable,"packages":{d.metadata["Name"]:d.version for d in m.distributions()},"requirements":m.requires(sys.argv[1]) if sys.argv[1] else []}))'
        command=[python,'-c',code,package or '']
        metadata=subprocess.run(command,capture_output=True,text=True,env=environment,check=True)
        (OUT/(name+'-metadata.json')).write_text(metadata.stdout)
        freeze=subprocess.run([python,'-m','pip','freeze'],capture_output=True,text=True,env=environment,check=True)
        (OUT/(name+'.freeze.txt')).write_text(freeze.stdout)
        row={'runtime':name,'freeze_sha256':hashlib.sha256(freeze.stdout.encode()).hexdigest(),'metadata_sha256':hashlib.sha256(metadata.stdout.encode()).hexdigest(),'solver_checks':[]}
        if package:
            for extra,expected in [('booster',0),('unitree,booster',1)]:
                slug='positive-booster' if expected==0 else 'negative-unitree'
                argv=[python,'-m','pip','install','--dry-run','--no-index','--no-cache-dir','--disable-pip-version-check',
                    '--report',str(OUT/(name+'-'+slug+'-report.json')),'-c','/audit/proposed/docker/'+constraint,package+'['+extra+']','far-unitree-sdk==0.1.8']
                result=subprocess.run(argv,capture_output=True,text=True,env=environment)
                (OUT/(name+'-'+slug+'.stdout.log')).write_text(result.stdout)
                (OUT/(name+'-'+slug+'.stderr.log')).write_text(result.stderr)
                assert (result.returncode==0)==(expected==0), result.stdout+result.stderr
                if expected==0:
                    report=json.loads((OUT/(name+'-'+slug+'-report.json')).read_text())
                    assert report['install']==[], 'No package should need installation in actual candidate environment'
                else:
                    assert '0.1.6' in result.stdout+result.stderr, 'Expected original unitree extra conflict was not observed'
                row['solver_checks'].append({'extra':extra,'argv':argv,'returncode':result.returncode,'expected_success':expected==0})
        runtimes.append(row)
    report={'schema_version':1,'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_image':'sha256:caf61487b69ce478980b3bf9df38a7f1fcaaae4b109d971dfbea10b09bf441aa','status':'passed','runtimes':runtimes,
        'scope':'Actual candidate pip freeze and existing installed-environment dry-run; no install, SDK module import/constructor, DDS, GPU or fresh all-dependency solve'}
    (OUT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':'passed','runtimes':len(runtimes),'source_image':report['source_image']}))


if __name__=='__main__':
    main()
