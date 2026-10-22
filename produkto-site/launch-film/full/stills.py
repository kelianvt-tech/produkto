"""One still per shot of film.html -> stills/NN-<id>.jpg (for the storyboard)."""
import os, threading, http.server, functools, asyncio
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); PORT = 8795
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), functools.partial(Q, directory=HERE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
PICK = {'open': .5, 'logo': .6, 'question': .9, 'answer': .8, 'quad-type': .7, 'quad-answer': .9, 'quad-miss': .9, 'scan': .95, 'loader': .55,
        'vis-dark': .5, 'vis-light': .6, 'daily': .5, 'llm-text': .5, 'llm-logos': .9, 'agents': .55, 'remediation': .5, 'revamp': .95, 'care': .5, 'url': .2}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        await pg.goto(f'http://127.0.0.1:{PORT}/film.html'); await pg.evaluate('window.ready')
        shots = await pg.evaluate('SHOTS'); print('duration', await pg.evaluate('DUR'))
        for n, (sid, st, ln) in enumerate(shots, 1):
            await pg.evaluate(f'seek({st + ln * PICK[sid]})')
            await pg.screenshot(path=f'{HERE}/stills/{n:02d}-{sid}.jpg', type='jpeg', quality=82)
            print(n, sid, round(st, 2), round(ln, 2))
        await b.close()
asyncio.run(main())
