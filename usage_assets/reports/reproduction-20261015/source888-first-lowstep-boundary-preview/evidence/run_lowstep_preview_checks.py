#!/usr/bin/env python3
"""Actual candidate HTTP or Git-mode restore check, with own Popen wait."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour');REPRO=ROOT/'outputs/research/reproduction-20261015'
PACKAGE=ROOT/'usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-preview'
RAW=REPRO/'cloud888-first-lowstep-boundary-preview-raw-01'
CANDIDATE='8030a4dbb3cb57fac8851570d5def05101bb3c34ed9a458b4c4ec0b7a9e3530b'

def fp(p):
    raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['http','restore']);a=ap.parse_args()
    assert fp(PACKAGE/'evidence-manifest.json')['sha256']==CANDIDATE
    if a.stage=='http':
        out=REPRO/'local-checks/first-lowstep-boundary-http-host-01';out.mkdir(exist_ok=False)
        argv=[sys.executable,'-B',str(REPRO/'verify_boundary_preview_http.py'),'--package',str(PACKAGE),'--manifest-sha256',CANDIDATE,'--output',str(REPRO/'local-checks/first-lowstep-boundary-http-01')]
    else:
        out=REPRO/'local-checks/first-lowstep-boundary-restore-01';out.mkdir(exist_ok=False)
        clone=out/'git-permission-normalized';shutil.copytree(PACKAGE,clone)
        for p in clone.rglob('*'):
            assert not p.is_symlink()
            p.chmod((0o755 if p.stat().st_mode&0o111 else 0o644) if p.is_file() else 0o755)
        clone.chmod(0o755)
        assert fp(clone/'evidence-manifest.json')['sha256']==CANDIDATE
        argv=[sys.executable,'-B',str(clone/'cloud888_report.py'),'restore','--input',str(clone),'--output',str(out/'restored-originals'),'--manifest-sha256',CANDIDATE]
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (out/'stdout.raw').open('xb') as stdout,(out/'stderr.raw').open('xb') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
        identity=Path(f'/proc/{child.pid}/stat').read_text()
        save(out/'process-start.json',{'argv':argv,'pid':child.pid,'birth_stat':identity,'started_utc':started,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
        code=child.wait()
    receipt={'argv':argv,'pid':child.pid,'birth_stat':identity,'started_utc':started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actual_wait_returncode':code,'candidate_manifest_sha256':CANDIDATE,'stdout':fp(out/'stdout.raw'),'stderr':fp(out/'stderr.raw'),'source':fp(Path(__file__))}
    save(out/'execution.json',receipt)
    assert code==0,(out/'stderr.raw').read_text()
    if a.stage=='restore':
        expected=json.loads((PACKAGE/'raw-inventory.json').read_bytes());actual={p.relative_to(out/'restored-originals').as_posix() for p in (out/'restored-originals').rglob('*') if p.is_file()}
        assert actual=={row['path'] for row in expected}
        rows=[]
        for row in expected:
            p=out/'restored-originals'/row['path'];original=RAW/row['path'];f=fp(p)
            assert f['bytes']==row['bytes'] and f['sha256']==row['sha256']==fp(original)['sha256'] and stat.S_IMODE(p.stat().st_mode)==row['mode']==stat.S_IMODE(original.stat().st_mode)
            rows.append(dict(relative=row['path'],bytes=f['bytes'],sha256=f['sha256'],mode=stat.S_IMODE(p.stat().st_mode)))
        save(out/'exact-restoration-review.json',{'status':'passed_actual_git_permission_normalized_candidate_restore','candidate_manifest_sha256':CANDIDATE,'original_files':len(rows),'all_publication_files_normalized_to_git_mode':True,'exact_bytes_sha_modes_file_set':True,'actual_wait_returncode':code,'restored':rows,'scope':'Actual standard-library restore only, no scientific execution.'})
    print(json.dumps({'stage':a.stage,'actual_wait_returncode':code,'execution':fp(out/'execution.json')}))
if __name__=='__main__':main()
