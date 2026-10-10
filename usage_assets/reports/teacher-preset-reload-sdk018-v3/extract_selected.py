#!/usr/bin/env python3
"""CPU ffmpeg extraction from each preset's longest original linked video."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

base=Path('/audit')
report=json.loads((base/'review.json').read_text())
assert report['status']=='passed_execution_evidence' and len(report['cases'])==5
target=base/'selected';target.mkdir(exist_ok=False)
rows=[]
for case in report['cases']:
    video=max((v for v in case['videos'] if v['quality_linked']),key=lambda v:(v['duration_seconds'],v['path']))
    source=Path(video['path']);copy=target/(case['preset']+'.mp4');image=target/(case['preset']+'.png')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==video['sha256']
    shutil.copyfile(source,copy);copy.chmod(0o644)
    command=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-threads','1','-ss',str(video['duration_seconds']/2),'-i',str(source),'-frames:v','1',str(image)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and image.is_file() and image.stat().st_size>0,result.stderr
    image.chmod(0o644)
    rows.append({'preset':case['preset'],'selection_rule':'Longest original quality-linked MP4; lexical path tie break.',
        'source_video':video,'selected_video':{'path':str(copy),'sha256':hashlib.sha256(copy.read_bytes()).hexdigest()},
        'frame_seconds':video['duration_seconds']/2,'extract_argv':command,'extract_returncode':result.returncode,
        'screenshot':{'path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'bytes':image.stat().st_size}})
(base/'selected-media.json').write_text(json.dumps({'schema_version':1,'cases':rows},indent=2)+'\n')
