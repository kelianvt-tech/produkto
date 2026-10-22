"""Render test5/film.html.
  python3 render.py sheet   -> sheet.jpg (one still every 0.25 s)
  python3 render.py full    -> silent.mp4 (30 fps, 1920x1080), then run sound.py
"""
import sys, os, io, threading, http.server, functools, subprocess, asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
FF = os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
MODE = sys.argv[1]; PORT = 8793; W, H, FPS, DUR = 1920, 1080, 30, 5.0

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), functools.partial(Q, directory=HERE))
threading.Thread(target=srv.serve_forever, daemon=True).start()

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': W, 'height': H})
        pg.on('pageerror', lambda e: print('pageerror:', e))
        await pg.goto(f'http://127.0.0.1:{PORT}/film.html')
        await pg.evaluate('window.ready')
        if MODE == 'sheet':
            ts = [round(i * .25, 2) for i in range(20)]
            tw, th, cols = 384, 216, 5
            rows = (len(ts) + cols - 1) // cols
            sheet = Image.new('RGB', (cols * (tw + 6) + 6, rows * (th + 28) + 6), '#222'); d = ImageDraw.Draw(sheet)
            for i, t in enumerate(ts):
                await pg.evaluate(f'seek({t})')
                im = Image.open(io.BytesIO(await pg.screenshot(type='jpeg', quality=85)))
                X = 6 + (i % cols) * (tw + 6); Y = 6 + (i // cols) * (th + 28)
                sheet.paste(im.resize((tw, th)), (X, Y + 22)); d.text((X, Y + 5), f'{t}s', fill='#fff')
            sheet.save(f'{HERE}/sheet.jpg', quality=88); print('sheet.jpg')
        elif MODE == 'at':
            for t in sys.argv[2:]:
                await pg.evaluate(f'seek({float(t)})'); await pg.screenshot(path=f'{HERE}/at-{t}.jpg', type='jpeg', quality=90)
        else:
            ff = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-i', '-',
                                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', '-preset', 'slow', f'{HERE}/silent.mp4'],
                                  stdin=subprocess.PIPE)
            for n in range(int(DUR * FPS)):
                await pg.evaluate(f'seek({n / FPS})')
                ff.stdin.write(await pg.screenshot(type='png'))
            ff.stdin.close(); ff.wait(); print('silent.mp4')
        await b.close()
asyncio.run(main())
