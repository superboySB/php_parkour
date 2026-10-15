#!/usr/bin/env python3
"""Independent CPU full decode and selected GIF; no simulator or GPU use."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT=Path('/workspace/php_parkour/outputs/research/reproduction-20261015')
RAW=ROOT/'cloud888-first-lowstep-boundary-preview-raw-01'
OUT=ROOT/'local-checks/first-lowstep-boundary-cpu-02'
EXPECTED={'39cf962a0cfeba1da4f85b6e8f534ad99ff7b6cc49e4615f495fb7ba8838d494':1,
'a85fa283a1c0112943d03b9483fd1300451c80c5fde7b3037318a3cb7e9e5ce8':1,
'f7220a6e6014daed278726148b57407ff8a02e97f2c589562e96b0c394e2fa89':504}

def fp(path):
    raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def inventory():
    rows=[]
    for p in sorted(RAW.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():rows.append(dict(fp(p),relative=p.relative_to(RAW).as_posix(),mode=stat.S_IMODE(p.stat().st_mode)))
    assert len(rows)==31
    return rows

def main():
    assert Path('/.dockerenv').exists() and not any(Path('/dev').glob('nvidia[0-9]*'))
    assert os.environ.get('NVIDIA_VISIBLE_DEVICES')=='void' and os.environ.get('CUDA_VISIBLE_DEVICES')==''
    OUT.mkdir(exist_ok=False);before=inventory();commands=[]
    def run(argv,label):
        started=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (OUT/(label+'.stdout.raw')).open('xb') as stdout,(OUT/(label+'.stderr.raw')).open('xb') as stderr:
            child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            birth=Path(f'/proc/{child.pid}/stat').read_text();code=child.wait()
        row={'argv':argv,'child_pid':child.pid,'child_stat':birth,'actual_wait_returncode':code,'started_utc':started,
             'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stdout':fp(OUT/(label+'.stdout.raw')),'stderr':fp(OUT/(label+'.stderr.raw'))}
        commands.append(row);(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        assert code==0,(OUT/(label+'.stderr.raw')).read_text()
        return (OUT/(label+'.stdout.raw')).read_bytes()
    videos=[];chosen=None
    paths=sorted((RAW/'raw-case').rglob('*.mp4'));assert len(paths)==3
    for i,p in enumerate(paths):
        file=fp(p);assert file['sha256'] in EXPECTED
        metadata=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames,width,height,r_frame_rate:format=duration','-of','json',str(p)],f'probe-{i}'))
        frames=int(metadata['streams'][0]['nb_read_frames']);assert frames==EXPECTED[file['sha256']]
        raw=run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','1','-hwaccel','none','-i',str(p),'-map','0:v:0','-an','-sn','-dn','-progress','pipe:1','-nostats','-f','null','-'],f'decode-{i}')
        progress=raw.decode().splitlines();assert 'progress=end' in progress
        assert [int(x.split('=',1)[1]) for x in progress if x.startswith('frame=')][-1]==frames
        videos.append({'video':file,'metadata':metadata,'decoded_frames':frames})
        if frames==504:chosen=p
    assert chosen is not None
    gif=OUT/'source-lowstep-boundary-preview.gif'
    run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','1','-hwaccel','none','-ss','2.06','-i',str(chosen),'-t','8','-an','-sn','-dn','-filter_complex','fps=8,scale=480:270:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a','-filter_complex_threads','1','-threads','1','-loop','0','-n',str(gif)],'gif-derive')
    metadata=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames,width,height,r_frame_rate:format=duration','-of','json',str(gif)],'gif-probe'))
    assert metadata['streams'][0]['width']==480 and metadata['streams'][0]['height']==270
    assert int(metadata['streams'][0]['nb_read_frames'])==64 and 7.9<=float(metadata['format']['duration'])<=8.1
    decoded=run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','1','-hwaccel','none','-i',str(gif),'-map','0:v:0','-an','-sn','-dn','-progress','pipe:1','-nostats','-f','null','-'],'gif-decode')
    assert b'progress=end' in decoded and b'frame=64' in decoded
    run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','1','-i',str(gif),'-vf','fps=0.5,scale=480:270,tile=4x1','-frames:v','1','-threads','1','-n',str(OUT/'gif-contact-sheet.png')],'gif-contact-sheet')
    after=inventory();assert before==after
    report={'status':'passed_actual_independent_lowstep_three_full_decodes_and_gif','source':fp(Path(__file__)),
            'original_inventory_before':before,'original_inventory_after':after,'all31_source_files_before_after_equal':True,
            'videos':videos,'total_decoded_frames':sum(v['decoded_frames'] for v in videos),'chosen':fp(chosen),
            'gif':dict(fp(gif),metadata=metadata,start_seconds=2.06,end_seconds_exclusive=10.06,width=480,height=270,fps=8,frames=64),
            'commands':commands,'scope':'Independent existing runc/noGPU/networknone CPU decoding and selected derivative only. Source505 frames/policy503, not888 terminal or obstacle-course success.'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'videos':len(videos),'original_frames':report['total_decoded_frames'],'gif_frames':64,'gif_sha256':report['gif']['sha256']}))
if __name__=='__main__':main()
