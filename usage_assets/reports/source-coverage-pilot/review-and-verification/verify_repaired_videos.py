import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
report_path = root / 'video-full-decode.json'
if report_path.exists():
    raise RuntimeError('Preserve existing video verification')
records = []
for video in sorted(root.glob('*/cases/*/native/**/*.mp4')):
    info = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,nb_frames,r_frame_rate','-of','json',str(video)],capture_output=True,text=True)
    decoded = subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
    records.append({'path':str(video),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'bytes':video.stat().st_size,'ffprobe_exit_code':info.returncode,'metadata':json.loads(info.stdout) if info.returncode==0 else None,'full_decode_exit_code':decoded.returncode,'decode_stderr':decoded.stderr})
assert records
assert all(item['ffprobe_exit_code']==item['full_decode_exit_code']==0 for item in records)
report = {'status':'passed','scope':'All native MP4s including initialization and warmup; full CPU decode, not proof of policy control or skill success','videos':records}
previews=[]
for kind in ('teacher','pure','finetune'):
    selected=[item for item in records if str(root/kind/'cases') in item['path']]
    longest=max(selected,key=lambda item:float(item['metadata']['format']['duration']))
    stream=longest['metadata']['streams'][0]
    frame=int(stream['nb_frames'])//2
    target=root/kind/'decoded-midpoint.png'
    extracted=subprocess.run(['ffmpeg','-v','error','-i',longest['path'],'-vf',f'select=eq(n\\,{frame})','-frames:v','1',str(target)],capture_output=True,text=True)
    assert extracted.returncode==0 and target.exists(), extracted.stderr
    previews.append({'policy':kind,'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_video':longest['path'],'source_video_sha256':longest['sha256'],'frame_index_zero_based':frame,'association':'midpoint of actual native episode video, including warmup if present'})
report['previews']=previews
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'videos':len(records),'status':'passed'}))
