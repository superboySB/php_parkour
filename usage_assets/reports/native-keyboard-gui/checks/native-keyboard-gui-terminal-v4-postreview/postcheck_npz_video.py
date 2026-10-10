from pathlib import Path
import hashlib,json,subprocess,numpy as np
raw=Path('/raw/outputs');reports=[]
for filename,code,minframes,method in [('1ba294c9803da84cf10e9c2f03c82ac7_duration3.8s_motion.npz',1,80,'manual c'),('1ba294c9803da84cf10e9c2f03c82ac7_duration3.9s_motion.npz',6,45,'STOP o automatic')]:
 p=raw/'recordings'/filename
 with np.load(p,allow_pickle=False) as d:
  assert set(d.files)=={'qpos','vel_cmd','fps'}
  q=d['qpos'];v=d['vel_cmd'];f=d['fps'];assert q.shape[0]>=minframes and q.shape[1:]==(36,) and v.shape==(len(q),15)
  assert q.dtype==np.float32 and v.dtype==np.float32 and f.shape==() and np.issubdtype(f.dtype,np.integer) and int(f)==50
  assert np.isfinite(q).all() and np.isfinite(v).all() and ((v==0)|(v==1)).all() and (v.sum(1)==1).all()
  n=np.linalg.norm(q[:,:4],axis=1);assert np.allclose(n,1,rtol=0,atol=.001)
  assert np.array_equal(q[:,4:7],np.zeros_like(q[:,4:7]));codes,counts=np.unique(v.argmax(1),return_counts=True);assert code in codes
  reports.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'save_method':method,'frames':len(q),'qpos_shape':list(q.shape),'vel_cmd_shape':list(v.shape),'fps':int(f),'quaternion_norm_min':float(n.min()),'quaternion_norm_max':float(n.max()),'world_xyz_all_zero_placeholders':True,'command_counts':dict(zip(map(lambda x:str(int(x)),codes),map(int,counts))),'source':'unmodified native policy recorder, actual command buffer; qpos wxyz+XYZ placeholders+29 joints','not_training_bundle':True})
videos=[]
for p in (raw/'video').rglob('*.mp4'):
 probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,width,height,nb_frames,r_frame_rate','-of','json',str(p)],capture_output=True,text=True)
 assert probe.returncode==0
 argv=['ffmpeg','-hide_banner','-loglevel','error','-xerror','-i',str(p),'-f','null','-'];r=subprocess.run(argv,capture_output=True,text=True,timeout=60)
 assert r.returncode==0
 videos.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'ffprobe':json.loads(probe.stdout),'full_decode':{'argv':argv,'returncode':r.returncode,'stderr':r.stderr}})
assert videos
report={'status':'partial_interfaces_and_artifacts_verified_overall_failed','native_gui_overall_pass':False,'native_clean_exit':False,'reason':'simulator native allocator abort after original main/atexit; Kit wrapper rc1 retained','recordings':reports,'videos':videos,'quality_verified':False,'hardware_verified':False,'cpu_only':True}
Path('/review/npz-video-postcheck.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'recording_frames':[v['frames'] for v in reports],'codes':[v['command_counts'] for v in reports],'videos':len(videos),'full_decodes':all(v['full_decode']['returncode']==0 for v in videos),'overall_native_gui_pass':False}))
