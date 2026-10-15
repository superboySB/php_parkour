#!/usr/bin/env python3
"""Serve the repository root and verify preserved media via actual HTTP Chrome."""
import base64,hashlib,http.server,json,os,pathlib,shutil,subprocess,sys,tempfile,threading,time
from urllib.request import urlopen
ROOT=pathlib.Path('/home/dzp/projects/php_parkour');OUT=ROOT/'usage_assets/reports/reproduction-20261015/http-browser'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'usage_assets/reports/official-evaluations-six/browser-reproduce'))
from verify_gallery import connect_cdp
from viser_browser import CDP,free_port
sys.path.insert(0,str(ROOT))
from scripts.research import serve_evidence

def require(v,m):
 if not v:raise ValueError(m)
def fp(p):return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

OUT.mkdir(parents=True,exist_ok=False)
requests=[]
class Handler(serve_evidence.EvidenceHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (BrokenPipeError,ConnectionResetError):pass
 def log_request(self,code='-',size='-'):
  requests.append({'method':self.command,'path':self.path,'status':int(code),'size':size,'range':self.headers.get('Range'),'observed_unix':time.time()})
server=serve_evidence.make_server(ROOT,port=0,handler=Handler);server.daemon_threads=True
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base='http://127.0.0.1:'+str(server.server_address[1]);report={'status':'failed','http_root':str(ROOT),'server_url':base,'scope':'Actual Range HTTP from repository root in existing CPU Chrome:25 preserved-media items,7 final Isaac evaluations and17 newly re-rendered kinematic references; no new policy physics, quality or curve extraction.','pages':[],'requests':requests,'quality_verified':False}
paths=set();browser=cdp=None
media=ROOT/'usage_assets/reproduction-20261015/media';m=json.loads((media/'manifest.json').read_text());s=json.loads((ROOT/'usage_assets/reports/official-evaluations-seven/summary.json').read_text())
for c in m['clips']+m['kinematic_references']:
 paths.update([ROOT/c['source_video'],ROOT/c['source_poster'],media/c['gif']['path'] if 'gif' in c else ROOT/c['existing_gif']])
for c in s['stages']:
 paths.update([ROOT/'usage_assets/reports/official-evaluations-seven'/c['representative']['path'],ROOT/'usage_assets/reports/official-evaluations-seven/cpu-01/results'/c['label']/'representative.png'])
paths.update(ROOT/p for p in ['usage_assets/reports/official-student-finetune-training-curves/figures/learning-curves.png','usage_assets/reports/official-student-finetune-training-curves-replay/cpu/validation/plots/learning-curves.png','usage_assets/reproduction-20261015/media/playback.html','usage_assets/reports/official-evaluations-seven/playback.html'])
paths.update((ROOT/'usage_assets/reproduction-20261015/reference-rerun').glob('*'));paths={p for p in paths if p.is_file()};paths.add(ROOT/'scripts/research/serve_evidence.py');paths.add(pathlib.Path(__file__));report['input_before']=[fp(p) for p in sorted(paths)];report['server_source']=fp(ROOT/'scripts/research/serve_evidence.py')
try:
 chrome=shutil.which('google-chrome') or shutil.which('chromium');require(chrome,'Existing Chrome required')
 with tempfile.TemporaryDirectory(prefix='php-http-review-') as profile,(OUT/'chrome.stdout.log').open('wb') as stdout,(OUT/'chrome.stderr.log').open('wb') as stderr:
  port=free_port();argv=[chrome,'--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required','--window-size=1440,1200','--remote-debugging-address=127.0.0.1','--remote-debugging-port='+str(port),'--user-data-dir='+profile,'about:blank']
  if os.geteuid()==0:argv.insert(1,'--no-sandbox')
  report['browser_command']=argv;browser=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
  try:
   deadline=time.monotonic()+30
   while time.monotonic()<deadline:
    require(browser.poll() is None,'Chrome exited before connection')
    try:
     with urlopen('http://127.0.0.1:'+str(port)+'/json/list',timeout=2) as r:target=next(t for t in json.load(r) if t.get('type')=='page')
     cdp=connect_cdp(CDP,target['webSocketDebuggerUrl']);cdp.socket.settimeout(40);break
    except (OSError,StopIteration):time.sleep(.1)
   require(cdp is not None,'Chrome connection timeout');cdp.call('Page.enable')
   for path,count in [('usage_assets/reproduction-20261015/media/playback.html',25),('usage_assets/reports/official-evaluations-seven/playback.html',7),('usage_assets/reproduction-20261015/reference-rerun/playback.html',17)]:
    url=base+'/'+path;cdp.call('Page.navigate',{'url':url});deadline=time.monotonic()+15
    while time.monotonic()<deadline:
     if cdp.evaluate("document.querySelectorAll('video').length")==count:break
     time.sleep(.1)
    require(cdp.evaluate("document.querySelectorAll('video').length")==count,'Video card count differs')
    row={'url':url,'video_count':count};report['pages'].append(row)
    row['metadata']=cdp.evaluate("""(async()=>{const rows=[];for(const v of document.querySelectorAll('video')){v.preload='auto';await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('metadata timeout')),12000);v.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve();},{once:true});v.addEventListener('error',()=>reject(Error(v.error.message)),{once:true});v.load();});rows.push({url:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration:v.duration,seekable:[...Array(v.seekable.length)].map((_,i)=>[v.seekable.start(i),v.seekable.end(i)]),buffered:[...Array(v.buffered.length)].map((_,i)=>[v.buffered.start(i),v.buffered.end(i)]),error:v.error?.message});}return rows;})()""")
    require(len(row['metadata'])==count and all(min(v['width'],v['height'],v['duration'])>0 and not v.get('error') for v in row['metadata']),'Invalid HTTP metadata')
    row['seeks']=cdp.evaluate("""(async()=>{const rows=[];for(const v of document.querySelectorAll('video')){const target=v.duration/2;await new Promise((resolve,reject)=>{const deadline=performance.now()+15000;const check=()=>{if([...Array(v.seekable.length)].some((_,i)=>v.seekable.start(i)<=target&&v.seekable.end(i)>=target))resolve();else if(performance.now()>deadline)reject(Error('HTTP seekable range timeout: '+v.currentSrc));else setTimeout(check,20);};check();});await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('seek timeout')),12000);v.addEventListener('seeked',()=>{clearTimeout(timer);resolve();},{once:true});v.currentTime=target;});await new Promise((resolve,reject)=>{const deadline=performance.now()+10000;const check=()=>{if(v.readyState>=2&&!v.seeking)resolve();else if(performance.now()>deadline)reject(Error('decoded frame readiness timeout'));else setTimeout(check,20);};check();});rows.push({target,time:v.currentTime,ready:v.readyState,error:v.error?.message});}return rows;})()""")
    require(all(v['ready']>=2 and abs(v['time']-v['target'])<.05 and not v.get('error') for v in row['seeks']),'HTTP midpoint seeks failed')
    row['images']=cdp.evaluate("""(async()=>{const srcs=[...document.querySelectorAll('video')].map(v=>v.poster).concat([...document.querySelectorAll('article img')].map(i=>i.src));return await Promise.all(srcs.map(src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve({url:src,width:i.naturalWidth,height:i.naturalHeight});i.onerror=()=>reject(Error(src));i.src=src;})));})()""")
    require(all(min(v['width'],v['height'])>0 for v in row['images']),'HTTP GIF/PNG decode failed')
    row['playback']=cdp.evaluate("""(async()=>{const vs=[...document.querySelectorAll('video')];const before=await Promise.all(vs.map(async v=>{v.muted=true;v.currentTime=0;await v.play();return v.currentTime;}));await new Promise(r=>setTimeout(r,850));const rows=vs.map((v,i)=>({before:before[i],after:v.currentTime,paused:v.paused,error:v.error?.message}));vs.forEach(v=>v.pause());return rows;})()""")
    require(all(not v['paused'] and v['after']-v['before']>.2 and not v.get('error') for v in row['playback']),'HTTP playback did not advance')
    shot=cdp.call('Page.captureScreenshot',{'format':'png'});(OUT/('media.png' if count==25 else 'official-seven.png' if count==7 else 'reference-rerun.png')).write_bytes(base64.b64decode(shot['data']))
   extra_gifs=[base+'/usage_assets/reports/official-evaluations-seven/student-finetune-preview.gif']+[base+'/'+str(p.relative_to(ROOT)) for p in sorted((ROOT/'usage_assets/reproduction-20261015/reference-rerun').glob('*.gif'))]
   report['additional_gifs']=cdp.evaluate("(async()=>await Promise.all("+json.dumps(extra_gifs)+".map(src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve({url:src,width:i.naturalWidth,height:i.naturalHeight});i.onerror=()=>reject(Error(src));i.src=src;}))))()")
   require(len(report['additional_gifs'])==18 and all(min(i['width'],i['height'])>0 for i in report['additional_gifs']),'Mixed-student/new-reference GIF HTTP decode failed')
   report['curve_images']=[]
   for path in ['usage_assets/reports/official-student-finetune-training-curves/figures/learning-curves.png','usage_assets/reports/official-student-finetune-training-curves-replay/cpu/validation/plots/learning-curves.png']:
    url=base+'/'+path
    with urlopen(url,timeout=10) as r:
     raw=r.read();require(r.status==200 and hashlib.sha256(raw).hexdigest()==fp(ROOT/path)['sha256'],'HTTP curve bytes differ')
    actual=cdp.evaluate("""(async()=>await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve({url:i.src,width:i.naturalWidth,height:i.naturalHeight});i.onerror=()=>reject(Error('curve decode'));i.src="""+json.dumps(url)+""";}))()""")
    require(min(actual['width'],actual['height'])>0,'Curve PNG failed browser decode');report['curve_images'].append(actual)
   with urlopen(base+'/usage.md',timeout=10) as r:report['usage_http_status']=r.status;require(r.status==200,'Usage backlink fails')
   report['status']='passed'
  finally:
   if cdp:
    try:cdp.call('Browser.close')
    except Exception as e:report['browser_close_response']=str(e)
    cdp.socket.close()
   try:report['browser_returncode']=browser.wait(timeout=15);report['cleanup']='natural_wait'
   except subprocess.TimeoutExpired:browser.terminate();report['browser_returncode']=browser.wait(timeout=5);report['cleanup']='owned_browser_terminate'
 require(report['browser_returncode']==0 and report['cleanup']=='natural_wait','Chrome exit is not natural0')
except Exception as e:report['status']='failed';report['error']=type(e).__name__+': '+str(e)
finally:
 server.shutdown();server.server_close();thread.join(timeout=5);report['http_server_stopped']=not thread.is_alive();report['input_after']=[fp(p) for p in sorted(paths)];report['inputs_unchanged']=report['input_before']==report['input_after']
 if not report['inputs_unchanged'] or not report['http_server_stopped']:report['status']='failed'
 report['http_206_responses']=sum(r['status']==206 for r in requests);report['source']=fp(pathlib.Path(__file__));report['content_http_errors']=[r for r in requests if r['status']>=400 and not r['path'].startswith('/favicon.ico')]
 if report['content_http_errors']:report['status']='failed'
 (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');shutil.copyfile(__file__,OUT/'verify_http.py')
print(json.dumps({'status':report['status'],'pages':len(report['pages']),'requests':len(requests),'http_content_errors':len(report['content_http_errors']),'browser_returncode':report.get('browser_returncode'),'source_unchanged':report['inputs_unchanged']}));raise SystemExit(report['status']!='passed')
