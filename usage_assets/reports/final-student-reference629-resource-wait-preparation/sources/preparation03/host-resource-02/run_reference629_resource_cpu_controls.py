#!/usr/bin/env python3
"""Retain actual ordinary CPU protocol execution; no scientific or GPU work."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour')
CANDIDATE=ROOT/'outputs/research/final-student-reference629-crossboot-preparation-02'
TEST=ROOT/'outputs/research/reproduction-20261015/test_reference629_gpu_resource_wait.py'

def fp(p):
    raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def sources():return [fp(p) for p in sorted(CANDIDATE.rglob('*')) if p.is_file()]+[fp(TEST),fp(Path(__file__))]
def birth(pid):
    raw=Path(f'/proc/{pid}/stat').read_text();f=raw.rsplit(')',1)[1].split()
    return {'pid':pid,'ppid':int(f[1]),'pgid':int(f[2]),'sid':int(f[3]),'start_time_clock_ticks':int(f[19]),'stat_raw':raw}
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.absolute();out.mkdir(exist_ok=False);(out/'fixtures').mkdir()
    old=(CANDIDATE/'host-resource-02/native_runner-before.py').read_text().splitlines(True)
    new=(CANDIDATE/'native_runner.py').read_text().splitlines(True)
    (out/'native_runner.diff').write_text(''.join(difflib.unified_diff(old,new,fromfile='prep01/native_runner.py',tofile='prep02/native_runner.py')))
    before=sources();argv=[sys.executable,'-B',str(TEST)]
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['REFERENCE629_CPU_PROTOCOL_EVIDENCE']=str(out/'fixtures')
    started=time.time()
    with (out/'stdout.raw').open('xb') as stdout,(out/'stderr.raw').open('xb') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True);identity=birth(child.pid)
        save(out/'process-start.json',{'scope':'Actual ordinary CPU protocol tests, not future resource/native evidence.','argv':argv,'child':identity,'parent':birth(os.getpid()),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
        code=child.wait()
    after=sources();sessions=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():continue
        try:row=birth(int(p.name))
        except (FileNotFoundError,ProcessLookupError):continue
        if row['pgid']==child.pid or row['sid']==child.pid:sessions.append(row)
    receipt={'scope':'Actual standard-library ordinary CPU protocol tests only; all query clients are Python fixtures. No Docker, nvidia, GPU or scientific run.','argv':argv,'child':identity,'actual_wait_returncode':code,'started_unix':started,'finished_unix':time.time(),'sources_before':before,'sources_after':after,'sources_unchanged':before==after,'remaining_owned_session_members':sessions,'stdout':fp(out/'stdout.raw'),'stderr':fp(out/'stderr.raw'),'test_fixture_tree_retained':str(out/'fixtures'),'source_diff':fp(out/'native_runner.diff')}
    save(out/'execution.json',receipt)
    print(json.dumps({'actual_wait_returncode':code,'source_count':len(before),'sources_unchanged':before==after,'remaining_owned_session_members':sessions,'execution':fp(out/'execution.json'),'helper':fp(CANDIDATE/'reference629_gpu_resource_wait.py'),'runner':fp(CANDIDATE/'native_runner.py'),'test':fp(TEST)},indent=2))
    return int(bool(code or before!=after or sessions))
if __name__=='__main__':raise SystemExit(main())
