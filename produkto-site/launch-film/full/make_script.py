"""Build SCRIPT-v<N>.html (one card per shot, stills embedded) from the ROWS below."""
import sys, io, base64, os
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, '..', f'SCRIPT-v{sys.argv[1]}.html')
T4, NEW = 'From test 4', 'NEW'
ROWS = [  # stills, time, on screen, picture, sound, status
 (['02-logo'], '0.0–1.5 s', 'Produkto logo. Under it, small: <b>is AI recommending your products?</b>', 'Moving character texture behind, on dark navy.', 'Boom on the first frame, a riser under it.', T4),
 (['03-question'], '1.5–2.6 s', '<b>&gt; What are the best dog leashes for my dog golden retriever?</b>', 'Typed out fast, blinking cursor. Your real ChatGPT capture, word for word.', 'Typing clicks.', NEW),
 (['04-answer'], '2.6–3.6 s', '<b>#1 Ruffwear Front Range</b> → <b>#2 Ruffwear Crag</b> → <b>#3 Halti Multifunctional Lead</b> → <b>#4 Ruffwear Knot a Leash</b> → <b>#5 Non-stop dogwear Touring Bungee</b>', 'One name per hard cut, 0.2 s each: the real top 5 from that answer. (Still shows #1.)', 'A hit on every name.', NEW),
 (['05-scan'], '3.6–4.4 s', '<b>kelian@produkto ~ % produkto scan</b><br>scanning catalog…<br>&gt; reading catalog<br>&gt; writing buyer questions<br>&gt; asking AI<br>&gt; reading answers', 'Typed, lines drop in one by one.', 'Typing clicks, a tick per line.', T4),
 (['06-loader'], '4.4–5.4 s', 'No text.', "The product's filling P loader, filling bottom to top.", 'Dots ticking, riser.', T4),
 (['07-vis-dark'], '5.4–5.9 s', '<b>Your AI visibility</b>', "Dark. The product's sun/moon switch appears and the pointer clicks the sun.", 'Big boom on the cut, a click on the switch.', T4),
 (['08-vis-light'], '5.9–6.35 s', '<b>Your AI visibility</b>', 'Snaps to light mode, same words in navy.', 'Boom on the snap.', T4),
 (['09-daily'], '6.35–7.05 s', '<b>Measured every day.</b>', 'Light.', 'Small hit.', NEW),
 (['10-llm-text'], '7.05–7.65 s', '<b>Across different LLMs.</b>', 'Hard cut back to dark.', 'Boom.', NEW),
 (['11a-llm', '11b-llm', '11c-llm'], '7.65–8.55 s', 'Small label under each logo: <b>ChatGPT</b> → <b>AI Overviews</b> → <b>Perplexity</b>', 'Each logo built from cold white dots that flicker on, 0.3 s each, hard cuts. These are the three engines the scanner runs today.', 'A sharp hit and glitch on each logo.', NEW),
 (['12-agents'], '8.55–9.55 s', '<b>Deploy agents across your catalog.</b>', 'Behind the words: a grid of squares, one per product, lighting up one by one as agents go out across the catalog.', 'Fast rising ticks as the grid lights.', NEW),
 (['13-remediation'], '9.55–10.55 s', '<b>Remediation.</b><br>Under it a product page change: one line removed (red), <b>Good for:</b> / <b>How to use:</b> / <b>FAQ:</b> added (green).', 'The text inside each line is blacked-out bars, so no product facts are made up.', 'Ticks as each line lands.', NEW),
 (['14-care'], '10.55–11.45 s', '<b>Taken care of.</b>', 'Dark.', 'Boom.', T4),
 (['15-url'], '11.45–12.65 s', '<b>getprodukto.com▌</b>', 'Cursor blinking, the hum fades out.', 'Low thud, then silence.', T4),
]
def emb(name):
    im = Image.open(f'{HERE}/stills/{name}.jpg'); im.thumbnail((880, 495)); b = io.BytesIO(); im.save(b, "JPEG", quality=68)
    return f'<img src="data:image/jpeg;base64,{base64.b64encode(b.getvalue()).decode()}" alt="">'
cards = ''.join(f'''<section><div class="imgs">{''.join(emb(f) for f in fs)}</div><div><p class="n">Shot {i} · {t} <span class="{'new' if st == NEW else 'old'}">{st}</span></p>
<p class="k">On screen</p><p>{tx}</p><p class="k">Picture</p><p>{pic}</p><p class="k">Sound</p><p>{snd}</p></div></section>''' for i, (fs, t, tx, pic, snd, st) in enumerate(ROWS, 1))
open(OUT, 'w').write(f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Launch film script</title>
<style>:root{{--bg:#f6f7f9;--ink:#0b1b35;--mut:#5d6b80;--line:#e1e5ec}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,system-ui,sans-serif}}main{{max-width:1180px;margin:0 auto;padding:40px 16px 80px}}
h1{{margin:0 0 4px;font-size:30px}}.lead{{color:var(--mut);margin:0 0 28px}}
section{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:24px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}}
.imgs{{display:grid;gap:8px}}img{{width:100%;border-radius:8px;display:block}}p{{margin:0 0 8px}}.n{{font-weight:700;font-size:18px;margin-bottom:12px}}.k{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:12px 0 2px}}
.new,.old{{font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;margin-left:6px;vertical-align:2px}}.new{{background:#fff3d6;color:#7a5200}}.old{{background:#e6eefb;color:#0b1b35}}
@media(max-width:760px){{section{{grid-template-columns:1fr}}}}</style></head><body><main>
<h1>Produkto launch film: script v{sys.argv[1]}</h1><p class="lead">About 12.5 seconds, 16:9, sound only, no voice. Every image is a real frame from the draft. Tell me changes by shot number.</p>
{cards}</main></body></html>''')
print(OUT)
