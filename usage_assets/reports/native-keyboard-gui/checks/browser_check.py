from pathlib import Path
import base64,json,os,shutil,signal,subprocess,sys,tempfile,time
from urllib.request import urlopen
ROOT=Path('/home/dzp/projects/php_parkour')
sys.path.insert(0,str(ROOT/'scripts/research'));from viser_browser import CDP,free_port
sys.path.insert(0,str(ROOT/'outputs/research/native-keyboard-gui-runner-egl-v5'));from common import load,birth_group,cleanup_group,fingerprint,write
output=ROOT/'outputs/research/native-keyboard-gui-egl-v5-postreview/browser';output.mkdir(exist_ok=False)
gallery=ROOT/'usage_assets/reports/native-keyboard-gui/playback.html'
module=load(ROOT/'outputs/research/native-keyboard-gui-prepared-egl-final/cohort/source/scripts/research/sim2sim.py','gui_offline_browser_ownership')
report={'schema_version':1,'scope':'CPU-only headless Chrome checks original published media loading/playback; no policy/native/DDS/desktop interaction','gallery':fingerprint(gallery),'status':'failed','gpu_disabled':True}
cdp=process=group=None
with tempfile.TemporaryDirectory(prefix='php-gui-offline-chrome-') as profile,(output/'chrome.log').open('xb') as log:
 try:
  port=free_port();argv=[shutil.which('google-chrome') or shutil.which('chromium'),'--headless=new','--disable-gpu','--no-first-run','--disable-dev-shm-usage','--window-size=1400,1100','--autoplay-policy=no-user-gesture-required',f'--remote-debugging-port={port}',f'--user-data-dir={profile}',gallery.as_uri()]
  process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);group=birth_group(module,process);report['argv']=argv
  until=time.monotonic()+20
  while time.monotonic()<until:
   try:
    with urlopen(f'http://127.0.0.1:{port}/json/list',timeout=1) as response:targets=json.load(response)
    target=next(v for v in targets if v.get('type')=='page');cdp=CDP(target['webSocketDebuggerUrl']);break
   except (OSError,StopIteration):time.sleep(.1)
  if cdp is None:raise TimeoutError('Owned CPU Chrome not initialized')
  cdp.call('Page.enable')
  cdp.evaluate("document.querySelector('details').open=true;Array.from(document.images).forEach(i=>i.loading='eager')")
  until=time.monotonic()+15
  while time.monotonic()<until:
   state=cdp.evaluate("({images:Array.from(document.images).map(i=>({src:i.getAttribute('src'),complete:i.complete,width:i.naturalWidth,height:i.naturalHeight})),videos:Array.from(document.querySelectorAll('video')).map(v=>({src:v.getAttribute('src'),width:v.videoWidth,height:v.videoHeight,duration:v.duration,ready:v.readyState,error:v.error&&v.error.code}))})")
   if all(v['complete'] and v['width']>0 for v in state['images']) and all(v['ready']>=1 for v in state['videos']):break
   time.sleep(.1)
  assert len(state['images'])==6 and all(v['complete'] and v['width']>0 for v in state['images']);assert len(state['videos'])==1 and state['videos'][0]['width']==640 and state['videos'][0]['height']==360 and not state['videos'][0]['error']
  seek=cdp.evaluate("new Promise((resolve,reject)=>{const v=document.querySelector('video');const timer=setTimeout(()=>reject(Error('seek timeout')),5000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve({time:v.currentTime,ready:v.readyState})},{once:true});v.currentTime=v.duration/2;})")
  assert seek['ready']>=2
  before=cdp.evaluate("document.querySelector('video').play().then(()=>document.querySelector('video').currentTime)");time.sleep(.5)
  after=cdp.evaluate("(()=>{const v=document.querySelector('video');v.pause();return v.currentTime;})()");assert after>before+.2
  cdp.evaluate("document.querySelector('details').open=false;window.scrollTo(0,0)");time.sleep(.2)
  (output/'page.png').write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data']))
  report.update(status='passed',metadata=state,keyframe=seek,playback={'before':before,'after':after},screenshot=fingerprint(output/'page.png'))
 except BaseException as error:report.update(error=type(error).__name__+': '+str(error))
 finally:
  if cdp:cdp.socket.close()
  if process is not None and group is not None:report['own_browser_final_group']=cleanup_group(module,process,group,[],.1)
write(output/'results.json',report);print(json.dumps({'status':report['status'],'videos':len(report.get('metadata',{}).get('videos',[])),'images':len(report.get('metadata',{}).get('images',[])),'error':report.get('error')}));raise SystemExit(0 if report['status']=='passed' else 1)
