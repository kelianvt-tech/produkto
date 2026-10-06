"""Build soundtrack: song cut to beat map + SFX at measured peaks, loudnorm -14 LUFS, mux with video."""
import sys,os,json,subprocess,numpy as np
H=os.path.dirname(os.path.abspath(__file__));OUT=sys.argv[1]
FF=os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
SR=44100
def load(f):
    r=subprocess.run([FF,'-v','quiet','-i',f,'-ac','2','-ar',str(SR),'-f','f32le','-'],capture_output=True).stdout
    return np.frombuffer(r,np.float32).reshape(-1,2).copy()
song=load(f'{H}/assets/audio/song-mixkit-851.mp3')
BAR=4*60/128;T0=0.117;bs=lambda b:int(round((T0+b*BAR)*SR))
def seg(a,b):return song[bs(a):bs(b)].copy()
parts=[seg(5,15),seg(45,48),seg(48,49)]
xf=int(.012*SR);track=parts[0]
for p in parts[1:]:
    w=np.linspace(0,1,xf)[:,None];tail=track[-xf:]*(1-w)+p[:xf]*w;track=np.concatenate([track[:-xf],tail,p[xf:]])
dur=56*60/128;n=int(dur*SR);track=np.pad(track,((0,max(0,n-len(track))),(0,0)))[:n]
fo=int(.25*SR);track[-fo:]*=np.linspace(1,0,fo)[:,None]
M={'click':'2568','pop':'2358','pop2':'2364','swoosh':'1461','iris':'1471','zoom':'1489','ding':'2870','key':'2568'}
cache={}
for name,k in M.items():
    x=load(f'{H}/assets/audio/sfx-{k}.mp3');pk=int(np.argmax(np.abs(x).sum(1)));cache[name]=(x,pk)
sfx=np.zeros_like(track)
for t,name,v in json.load(open(f'{OUT}/sfx.json')):
    x,pk=cache[name];g=v*(.35 if name=='key' else .6)
    st=int(t*SR)-pk
    if name=='zoom':st=int(t*SR)-pk+int(.39*SR)  # whoosh peak lands as the move lands
    a=max(0,st);b=min(n,st+len(x))
    if b>a:sfx[a:b]+=x[a-st:b-st]*g
mix=track*.8+sfx
mix/=max(1,np.abs(mix).max()/.98)
raw=f'{OUT}/mix.f32';mix.astype(np.float32).tofile(raw)
subprocess.run([FF,'-v','error','-y','-f','f32le','-ar',str(SR),'-ac','2','-i',raw,'-af','loudnorm=I=-14:TP=-1:LRA=11','-ar',str(SR),f'{OUT}/mix.wav'],check=True)
subprocess.run([FF,'-v','error','-y','-i',f'{OUT}/silent.mp4','-i',f'{OUT}/mix.wav','-c:v','copy','-c:a','aac','-b:a','256k','-shortest',f'{H}/produkto-launch-film.mp4'],check=True)
print('done')
