"""Render film-v3.html.
  python3 render2.py sheet  sq|v      -> out-<fmt>/sheet.jpg  (one still per beat + strips around fast moves)
  python3 render2.py full   sq|v      -> out-<fmt>/silent.mp4 + sfx.json, then run mix2.py
  python3 render2.py pops   sq|v      -> lists single-frame pops (frame-difference spikes 3x their neighbours)
"""
import sys, os, threading, http.server, functools, subprocess, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
FF = os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
MODE, FMT = sys.argv[1], sys.argv[2]
W, H = (1080, 1920) if FMT == 'v' else (1440, 1440)
OUT = os.path.join(HERE, f'out3-{FMT}')
PORT = 8776 if FMT == 'v' else 8777

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), functools.partial(Q, directory=HERE))
threading.Thread(target=srv.serve_forever, daemon=True).start()

# beats with fast transitions: get a 4-frame strip around them
FAST = [4.3, 8.0, 12.3, 14.2, 16.5, 21.4, 23.3, 26.9, 28.6, 29.6, 34.9, 39.2]

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': W, 'height': H})
        pg.on('pageerror', lambda e: print('pageerror:', e))
        pg.on('console', lambda m: print('console:', m.text) if m.type == 'error' else None)
        await pg.goto(f'http://127.0.0.1:{PORT}/film-v3.html' + ('?f=v' if FMT == 'v' else ''))
        await pg.evaluate('window.ready')
        dur = await pg.evaluate('DUR'); Bt = 60 / await pg.evaluate('BPM')
        shot = lambda: pg.screenshot(type='jpeg', quality=82)
        if MODE == 'sheet':
            ims = []
            for n in range(0, int(dur)):
                await pg.evaluate(f'seek({n + .5})')
                ims.append((f'{n+.5}s', Image.open(io.BytesIO(await shot()))))
            strips = []
            for fb in FAST:
                for k in range(4):
                    t = fb + k * .15
                    await pg.evaluate(f'seek({t})')
                    strips.append((f'{fb}+{k}/4', Image.open(io.BytesIO(await shot()))))
            for name, items, cols in (('sheet', ims, 8), ('strips', strips, 8)):
                tw = 300; th = int(tw * H / W)
                rows = (len(items) + cols - 1) // cols
                sheet = Image.new('RGB', (cols * (tw + 8) + 8, rows * (th + 34) + 8), '#222')
                d = ImageDraw.Draw(sheet)
                for i, (lbl, im) in enumerate(items):
                    x = 8 + (i % cols) * (tw + 8); y = 8 + (i // cols) * (th + 34)
                    sheet.paste(im.resize((tw, th)), (x, y + 26)); d.text((x, y + 6), lbl, fill='#fff')
                sheet.save(f'{OUT}/{name}.jpg', quality=85)
            print('sheets written')
        elif MODE == 'at':
            for t in sys.argv[3:]:
                await pg.evaluate(f'seek({float(t)})')
                await pg.screenshot(path=f'{OUT}/at-{t}.jpg', type='jpeg', quality=88)
        elif MODE == 'pops':
            import numpy as np
            prev = None; diffs = []
            n = int(dur * 30)
            for i in range(n):
                await pg.evaluate(f'seek({i / 30})')
                a = np.asarray(Image.open(io.BytesIO(await pg.screenshot(type='jpeg', quality=50))).resize((180, int(180 * H / W))), dtype=np.int16)
                if prev is not None: diffs.append(float(np.abs(a - prev).mean()))
                prev = a
            for i in range(1, len(diffs) - 1):
                if diffs[i] > 3 * max(diffs[i - 1], diffs[i + 1], 1.0) and diffs[i] > 6:
                    print(f'pop at {i / 30:.2f}s (beat {i / 30 / Bt + 1:.2f}) diff {diffs[i]:.1f}')
            print('pop scan done')
        else:
            import json
            open(f'{OUT}/sfx.json', 'w').write(json.dumps(await pg.evaluate('SFX')))
            n = int(round(dur * 60)) * 4
            proc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', '240', '-c:v', 'mjpeg', '-i', '-',
                '-vf', 'tmix=frames=4,select=not(mod(n+1\\,4)),setpts=N/60/TB,scale=in_range=pc:out_range=tv,format=yuv420p', '-r', '60', '-c:v', 'libx264', '-crf', '17', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-level', '4.2', '-color_range', 'tv', '-movflags', '+faststart',
                f'{OUT}/silent.mp4'], stdin=subprocess.PIPE)
            for i in range(n):
                await pg.evaluate(f'seek({(i + .5) / 240})')
                proc.stdin.write(await pg.screenshot(type='jpeg', quality=93))
                if i % 960 == 0: print('frame', i, '/', n, flush=True)
            proc.stdin.close(); proc.wait()
        await b.close()
asyncio.run(main())
