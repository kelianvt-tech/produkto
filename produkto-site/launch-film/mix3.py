"""Soundtrack for film-v3: Stylz from the top, trimmed to the film with a 2.5 s fade, SFX at cue peaks, -14 LUFS."""
import sys,os,json,subprocess,numpy as np
H=os.path.dirname(os.path.abspath(__file__));OUT=sys.argv[1];NAME=sys.argv[2]
FF=os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
SR=44100
def load(f):
    r=subprocess.run([FF,'-v','quiet','-i',f,'-ac','2','-ar',str(SR),'-f','f32le','-'],capture_output=True).stdout
    return np.frombuffer(r,np.float32).reshape(-1,2).copy()
dur=float(sys.argv[3]);n=int(dur*SR)
song=load(f'{H}/assets/v3/music/stylz-160.mp3')[:n]
song=np.pad(song,((0,max(0,n-len(song))),(0,0)))
fi=int(.4*SR);song[:fi]*=np.linspace(0,1,fi)[:,None]
fo=int(2.5*SR);song[-fo:]*=np.linspace(1,0,fo)[:,None]
M={'click':'2568','pop':'2358','pop2':'2364','swoosh':'1461','zoom':'1489','ding':'2870','key':'2568'}
cache={k:None for k in M}
for name,k in M.items():
    x=load(f'{H}/assets/audio/sfx-{k}.mp3');cache[name]=(x,int(np.argmax(np.abs(x).sum(1))))
sfx=np.zeros_like(song)
for t,name,v in json.load(open(f'{OUT}/sfx.json')):
    x,pk=cache[name];g=v*.55;st=int(t*SR)-pk
    a=max(0,st);b=min(n,st+len(x))
    if b>a:sfx[a:b]+=x[a-st:b-st]*g
vo_path=f'{H}/assets/v3/vo/voiceover-fast.wav'
vo=load(vo_path)[:n];vo=np.pad(vo,((0,max(0,n-len(vo))),(0,0)))
# duck the music under the voice: smooth envelope of voice loudness
env=np.abs(vo).mean(1);k=int(.25*SR);env=np.convolve(env,np.ones(k)/k,'same');duck=1-.62*np.clip(env/ (env.max()*.15+1e-9),0,1)
song=song*duck[:,None]
mix=song*.75+sfx*.8+vo*1.15;mix/=max(1,np.abs(mix).max()/.98)
raw=f'{OUT}/mix.f32';mix.astype(np.float32).tofile(raw)
subprocess.run([FF,'-v','error','-y','-f','f32le','-ar',str(SR),'-ac','2','-i',raw,'-af','loudnorm=I=-14:TP=-1:LRA=11','-ar',str(SR),f'{OUT}/mix.wav'],check=True)
subprocess.run([FF,'-v','error','-y','-i',f'{OUT}/silent.mp4','-i',f'{OUT}/mix.wav','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest',f'{H}/{NAME}'],check=True)
print('done')
