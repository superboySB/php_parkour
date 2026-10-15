#!/usr/bin/env python3
"""Actual final Git-mode-normalized low-step archive restore and original SHA/mode proof."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour');REPRO=ROOT/'outputs/research/reproduction-20261015'
PACKAGE=ROOT/'usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-preview'
RAW=REPRO/'cloud888-first-lowstep-boundary-preview-raw-01'
SEAL='ce43884e452c6ad1e2852deca724613039ef612982507671a80d138bea0da29d'
OUT=REPRO/'local-checks/first-lowstep-boundary-final-git-restore-01'
PUBLIC=ROOT/'usage_assets/reports/reproduction-20261015/source888-first-lowstep-boundary-final-git-restore'

def fp(p):
    raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    assert fp(PACKAGE/'evidence-manifest.json')['sha256']==SEAL and not PUBLIC.exists()
    OUT.mkdir(exist_ok=False);clone=OUT/'git-permission-normalized';shutil.copytree(PACKAGE,clone)
    files=[]
    for p in clone.rglob('*'):
        assert not p.is_symlink()
        p.chmod((0o755 if p.stat().st_mode&0o111 else 0o644) if p.is_file() else 0o755)
        if p.is_file():files.append(p)
    clone.chmod(0o755)
    manifest=json.loads((clone/'evidence-manifest.json').read_bytes());expected={row['path']:row for row in manifest['files']}
    assert {p.relative_to(clone).as_posix() for p in files}==set(expected)|{'evidence-manifest.json'}
    assert fp(clone/'evidence-manifest.json')['sha256']==SEAL
    for rel,row in expected.items():
        f=fp(clone/rel);assert f['sha256']==row['sha256'] and f['bytes']==row['bytes']
    argv=[sys.executable,'-B',str(clone/'cloud888_report.py'),'restore','--input',str(clone),'--output',str(OUT/'restored-originals'),'--manifest-sha256',SEAL]
    with (OUT/'stdout.raw').open('xb') as stdout,(OUT/'stderr.raw').open('xb') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True);birth=Path(f'/proc/{child.pid}/stat').read_text();code=child.wait()
    execution={'scope':'Actual final sealed package standard-library restore after every publication file is normalized to Git0644/0755; no scientific run.','argv':argv,'pid':child.pid,'birth_stat':birth,'actual_wait_returncode':code,'input_package_sha256':SEAL,'stdout':fp(OUT/'stdout.raw'),'stderr':fp(OUT/'stderr.raw'),'source':fp(Path(__file__))}
    save(OUT/'execution.json',execution);assert code==0,(OUT/'stderr.raw').read_text()
    inventory=json.loads((PACKAGE/'raw-inventory.json').read_bytes());restored=OUT/'restored-originals'
    actual={p.relative_to(restored).as_posix() for p in restored.rglob('*') if p.is_file()};assert actual=={row['path'] for row in inventory}
    rows=[]
    for row in inventory:
        p=restored/row['path'];original=RAW/row['path'];f=fp(p)
        assert f['bytes']==row['bytes'] and f['sha256']==row['sha256']==fp(original)['sha256']
        assert stat.S_IMODE(p.stat().st_mode)==row['mode']==stat.S_IMODE(original.stat().st_mode)
        rows.append({'relative':row['path'],'bytes':f['bytes'],'sha256':f['sha256'],'mode':row['mode']})
    review={'status':'passed_actual_final_lowstep_git_mode_restore','input_package_sha256':SEAL,'publication_files':len(files),'original_files':len(rows),'actual_wait_returncode':code,'exact_sha_bytes_modes_file_set':True,'restored':rows}
    save(OUT/'exact-restoration-review.json',review)
    PUBLIC.mkdir()
    for name in ['execution.json','stdout.raw','stderr.raw','exact-restoration-review.json']:shutil.copyfile(OUT/name,PUBLIC/name)
    shutil.copyfile(Path(__file__),PUBLIC/Path(__file__).name)
    (PUBLIC/'README.md').write_text('# 低台阶单 source：最终包 Git 权限恢复实测\n\n最终媒体包 seal `'+SEAL+'`。完整副本全部普通文件按 Git0644/0755 权限归一化，标准库 restore 实际 wait0，31原件逐一 SHA256、bytes、完整原mode与精确file-set相同。\n\n原件保留在[低台阶单 source 包](../source888-first-lowstep-boundary-preview/README.md)，本旁包仅封存恢复命令/真实wait/raw/核对记录，不修改原媒体 seal，不执行科学作业。\n')
    payload=[{'path':p.relative_to(PUBLIC).as_posix(),'bytes':p.stat().st_size,'sha256':fp(p)['sha256']} for p in sorted(PUBLIC.rglob('*')) if p.is_file()]
    save(PUBLIC/'manifest.json',{'schema_version':1,'input_package_sha256':SEAL,'scope':'Actual final Git-mode-normalized31 original file restore only.','files':payload})
    print(json.dumps({'actual_wait_returncode':code,'original_files':len(rows),'publication_files':len(files),'proof_manifest_sha256':fp(PUBLIC/'manifest.json')['sha256'],'execution_sha256':fp(OUT/'execution.json')['sha256']},indent=2))
if __name__=='__main__':main()
