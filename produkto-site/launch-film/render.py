"""Render film.html to MP4. Usage: python3 render.py beats|full"""
import sys, os, threading, http.server, functools, subprocess, asyncio
from playwright.async_api import async_playwright
HERE=os.path.dirname(os.path.abspath(__file__))
FF=os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
OUT=sys.argv[2] if len(sys.argv)>2 else os.path.join(HERE,'out')
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
srv=http.server.ThreadingHTTPServer(('127.0.0.1',8765),functools.partial(Q,directory=HERE))
threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main(mode):
    os.makedirs(OUT,exist_ok=True)
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={'width':1440,'height':1440})
        pg.on('console',lambda m: print('console:',m.text) if m.type=='error' else None)
        pg.on('pageerror',lambda e: print('pageerror:',e))
        await pg.goto('http://127.0.0.1:8765/film.html'); await pg.evaluate('window.ready')
        dur=await pg.evaluate('DUR'); B=60/await pg.evaluate('BPM')
        if mode=='beats':
            for n in range(1,57):
                for off in (0,.5):
                    t=(n-1+off)*B
                    await pg.evaluate(f'seek({t})'); await pg.screenshot(path=f'{OUT}/b{n:02d}{"h" if off else ""}.jpg',type='jpeg',quality=80)
        elif mode=='at':
            for t in sys.argv[3:]:
                await pg.evaluate(f'seek({float(t)})'); await pg.screenshot(path=f'{OUT}/t{t}.jpg',type='jpeg',quality=85)
        else:
            import json; open(f'{OUT}/sfx.json','w').write(json.dumps(await pg.evaluate('SFX')))
            n=int(round(dur*60))*4
            proc=subprocess.Popen([FF,'-v','error','-y','-f','image2pipe','-framerate','240','-c:v','mjpeg','-i','-',
              '-vf','tmix=frames=4,select=not(mod(n+1\\,4)),setpts=N/60/TB','-r','60','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',f'{OUT}/silent.mp4'],stdin=subprocess.PIPE)
            for i in range(n):
                await pg.evaluate(f'seek({(i+.5)/240})')
                proc.stdin.write(await pg.screenshot(type='jpeg',quality=94))
                if i%240==0: print('frame',i,'/',n,flush=True)
            proc.stdin.close(); proc.wait()
        await b.close()
asyncio.run(main(sys.argv[1]))
