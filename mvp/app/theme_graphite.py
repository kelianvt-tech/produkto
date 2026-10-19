"""Builds theme-graphite.css: the dark "Graphite" look (design variation E).

It reads every colour in the app's light stylesheets and writes an override
rule with the colour moved to the dark palette, so the layout stays exactly
as it is and only the colours change. Hand-tuned rules (page ground, font,
the large product photos) follow at the end, in MANUAL.

Run after changing dashboard.css or workspace.css:  python3 theme_graphite.py
Remove the theme by deleting theme-graphite.css (app.page() skips it then).
"""
import colorsys
import os
import re

import app

HERE = os.path.dirname(os.path.abspath(__file__))
HEX = re.compile(r'#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b')
RGBA = re.compile(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)')
SHADOW = ('box-shadow', 'text-shadow', 'filter')


def remap(r, g, b, prop):
    """Light-theme colour -> Graphite colour, hue kept."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    text = prop in ('color', 'fill', 'stroke', 'caret-color') or prop.startswith('--')
    if s < 0.35 or l > 0.86 or l < 0.2:          # neutrals, tints, navy ink
        if l >= 0.8:                              # light surfaces -> dark panels
            nl = 0.085 + (1 - l) * 0.55
            s = min(s, 0.22)
        elif l <= 0.35:                           # dark ink -> light text
            nl = 0.93 - l * 0.35
            s = min(s, 0.25)
        else:                                     # mid greys -> muted greys
            nl = 1.12 - l
            s = min(s, 0.18)
    else:                                         # real colours: keep, lift a little
        nl = min(0.72, max(0.55, l + 0.12)) if text else min(0.66, max(0.5, l + 0.08))
    nr, ng, nb = colorsys.hls_to_rgb(h, max(0, min(1, nl)), s)
    return round(nr * 255), round(ng * 255), round(nb * 255)


def convert(value, prop):
    if prop in SHADOW:                            # navy shadows -> black shadows
        def shadow(m):
            a = float(m.group(4) or 1)
            return 'rgba(0,0,0,%.2f)' % min(0.6, a * 2.2)
        value = RGBA.sub(shadow, value)
        return HEX.sub(lambda m: '#000000' + (m.group(1)[6:] if len(m.group(1)) == 8 else ''), value)

    def hx(m):
        v = m.group(1)
        if len(v) in (3, 4):
            v = ''.join(c * 2 for c in v)
        r, g, b = (int(v[i:i + 2], 16) for i in (0, 2, 4))
        nr, ng, nb = remap(r, g, b, prop)
        return '#%02x%02x%02x%s' % (nr, ng, nb, v[6:8])

    def rgba(m):
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        nr, ng, nb = remap(r, g, b, prop)
        return 'rgba(%d,%d,%d,%s)' % (nr, ng, nb, m.group(4) or '1')

    value = re.sub(r'(?<![\w-])white\b', '#ffffff', value)
    return RGBA.sub(rgba, HEX.sub(hx, value))


def rules(css):
    """Yield (at-rule prefix, selector, declarations) from flat or @media CSS."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    depth, buf, stack = 0, '', []
    i = 0
    while i < len(css):
        c = css[i]
        if c == '{':
            head = buf.strip()
            if head.startswith('@media') or head.startswith('@supports'):
                stack.append(head)
                buf = ''
            elif head.startswith('@'):           # keyframes etc: skip block
                level, j = 1, i + 1
                while level and j < len(css):
                    level += {'{': 1, '}': -1}.get(css[j], 0)
                    j += 1
                i, buf = j, ''
                continue
            else:
                j = css.index('}', i)
                yield (stack[-1] if stack else None, head, css[i + 1:j])
                i, buf = j + 1, ''
                continue
        elif c == '}':
            if stack:
                stack.pop()
            buf = ''
        else:
            buf += c
        i += 1


def scope(selector):
    """Limit a selector to dark mode: <html class="dark">."""
    parts = []
    for part in selector.split(','):
        part = part.strip()
        if part.startswith(':root'):
            parts.append('html.dark' + part[5:])
        elif part.startswith('html'):
            parts.append('html.dark' + part[4:])
        else:
            parts.append('html.dark ' + part)
    return ','.join(parts)


def build(names=('dashboard.css', 'workspace.css'), target='theme-graphite.css', manual=None, skip=None, base=True):
    sources = [app.CSS] if base else []
    if base:  # the Improve visibility button and its dialog carry their own CSS
        import waitlist
        sources.append(re.sub(r'</?style>', '', waitlist.CSS))
    for name in names:
        with open(os.path.join(HERE, name)) as f:
            sources.append(f.read())
    out = []
    for css in sources:
        for media, sel, body in rules(css):
            if skip and skip.search(sel):
                continue
            decls = []
            for d in body.split(';'):
                if ':' not in d:
                    continue
                prop, val = d.split(':', 1)
                prop = prop.strip().lower()
                if (HEX.search(val) or RGBA.search(val) or re.search(r'(?<![\w-])white\b', val)) and 'url(' not in val:
                    decls.append('%s:%s' % (prop, convert(val.strip(), prop)))
            if decls:
                rule = '%s{%s}' % (scope(sel), ';'.join(decls))
                out.append('%s{%s}' % (media, rule) if media else rule)
    with open(os.path.join(HERE, target), 'w') as f:
        f.write('/* Generated by theme_graphite.py; edit MANUAL there, not this file. */\n')
        f.write('\n'.join(out) + '\n' + (MANUAL if manual is None else manual))
    print('%s: %d rules' % (target, len(out)))


MANUAL = """
/* ---- both modes: Onest type, big product photos (from variation D) ---- */
:root{--font:'Onest',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif}
body,button,input,select,textarea{font-family:var(--font)}
.pc-table .rank-product{gap:18px}
.pc-table td:first-child{padding-top:14px;padding-bottom:14px}
.pc-table .rank-product .rank-thumb{width:104px!important;height:104px!important;border-radius:14px!important;border:1px solid var(--line)!important;background:#f1f0ed!important;flex-shrink:0;overflow:hidden}
.pc-table .rank-product .rank-thumb img{width:100%;height:100%;object-fit:cover;padding:0!important;border-radius:0!important}
.pc-table .rank-product b{font-size:15px;font-weight:600}
.pc-table td:first-child .rank-product>span:last-child{min-width:190px}
@media(max-width:760px){.pc-table .rank-product .rank-thumb{width:72px!important;height:72px!important}}
.theme-switch{display:inline-flex;gap:4px;padding:4px;border-radius:999px;border:0;background:#eef2f7;cursor:pointer;box-shadow:inset 0 0 0 1px #e0e7f0}
.ts-opt{width:40px;height:30px;border-radius:999px;display:grid;place-items:center;color:#94a0b2;transition:background-color .2s ease,color .2s ease!important}
.ts-opt svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.ts-light{background:#dde3ec;color:#0b1b35}
.theme-switch:focus-visible{outline:2px solid #5b9bff;outline-offset:2px}
html.dark .theme-switch{background:#0a0d12;box-shadow:inset 0 0 0 1px #252c36}
html.dark .ts-light{background:transparent;color:#8b95a5}
html.dark .ts-dark{background:#2c3550;color:#fff}
.theme-switch-row{padding:4px 6px 10px}
html.rail-shut .theme-switch-row{padding:4px 0 10px;display:flex;justify-content:center}
html.rail-shut:not(.dark) .rail .ts-dark,html.rail-shut.dark .rail .ts-light{display:none}

/* Chart tooltips sit above every marker and logo, fully opaque. */
.chart-tooltip{z-index:30!important;background:#fff!important}

/* Position chart: the hovered marker gets a blue ring. */
.position-mark{cursor:pointer;outline:none}
.position-mark rect{transition:stroke .12s ease,stroke-width .12s ease}
.position-mark:hover rect,.position-mark:focus-visible rect{stroke:#7aa7ff;stroke-width:3.5}

/* ---- dark mode: Graphite ground, panels ---- */
html.dark,html.dark body:has(.product-head){--ink:#e8ecf2;--ink-2:#ffffff;--text:#d6dce6;--muted:#8b95a5;--faint:#6f7a8a;
--bg:#0e1116;--surface:#151a21;--subtle:#1a2029;--line:#252c36;--line-2:#2f3743;--tint:#171c24;--tint-line:#252c36;color-scheme:dark}
html.dark,html.dark body,html.dark body:has(.product-head){background:#0e1116!important;color:var(--text)}
html.dark body::after,html.dark body:has(.product-head)::after{opacity:0!important}
html.dark ::selection{background:#2b4e86;color:#fff}
html.dark .btn,html.dark .btn:hover{background:#e8ecf2;color:#0e1116}
html.dark .rail{background:#0e1116!important;border-right:1px solid #252c36!important}
html.dark header.top,html.dark body:has(.product-head) header.top{background:#0e1116!important;border-color:#252c36!important}
html.dark .pc-table .rank-product .rank-thumb{border-color:#252c36!important}
html.dark .rail-logo img,html.dark header.top img[src*=logo]{filter:brightness(0) invert(.93)}
html.dark img{color-scheme:light}
/* Store and brand logos are made for light backgrounds: keep them on a white tile. */
html.dark .rail-store-logo,html.dark .rail-store-logo img,html.dark .product-placeholder,html.dark .product-placeholder img,html.dark img[src^="/icon"]{background:#fff!important}
html.dark .rail-store-logo{border-radius:8px;overflow:hidden}
/* Product photos use a white-paper blend; on dark that turns them black. */
html.dark .product-head img.product-hero,html.dark img[style*=multiply]{background:#fff!important;mix-blend-mode:normal!important}
/* Product photos everywhere sit on a light tile, as in white mode. */
html.dark .rank-thumb,html.dark img.product-photo,html.dark .tip-mark{background:#fff!important}
html.dark .chart-tooltip{background:#161b22!important;border-color:#2a313c!important;box-shadow:0 12px 32px rgba(0,0,0,.55)!important}
/* ---- agent board: selection and drop rings stay visible in dark mode ---- */
html.dark .cb-tile[aria-current]{box-shadow:0 0 0 3px #1d3156}
html.dark .cb-drop{background:#15213a;box-shadow:inset 0 0 0 2px #6393e4}
html.dark .cb-on .cb-can{box-shadow:inset 0 0 0 1px rgba(99,147,228,.45)}
html.dark .cb-no{box-shadow:inset 0 0 0 2px rgba(240,113,96,.6)}
html.dark .cal-win{background:#17281d}html.dark .cal-win-mixed{background:#2a2216}html.dark .cal-win-hard{background:#2c1a18}
html.dark .cs-step[aria-current]{box-shadow:0 0 0 3px #232b38}
/* ---- agent voice sample: keep it a clearly blue, highlighted card in dark mode ---- */
html.dark .cs-sample-card{background:#14233b;border:1px solid #23406b}
html.dark .cs-sample-card figcaption{color:#8fb4f0}
"""

# Onboarding keeps its own dark "sky" side panel and animated P as they are.
ONBOARDING = """
:root{font-family:'Onest',ui-sans-serif,system-ui,-apple-system,sans-serif}
body,button,input,select,textarea{font-family:'Onest',ui-sans-serif,system-ui,-apple-system,sans-serif}
.workspace-header{display:flex;align-items:center;justify-content:flex-end}
.theme-switch{display:inline-flex;gap:4px;padding:4px;border-radius:999px;border:0;background:#eef2f7;cursor:pointer;box-shadow:inset 0 0 0 1px #e0e7f0}
.ts-opt{width:40px;height:30px;border-radius:999px;display:grid;place-items:center;color:#94a0b2;transition:background-color .2s ease,color .2s ease!important}
.ts-opt svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.ts-light{background:#dde3ec;color:#0b1b35}
.theme-switch:focus-visible{outline:2px solid #5b9bff;outline-offset:2px}
html.dark .theme-switch{background:#0a0d12;box-shadow:inset 0 0 0 1px #252c36}
html.dark .ts-light{background:transparent;color:#8b95a5}
html.dark .ts-dark{background:#2c3550;color:#fff}
.theme-switch-row{padding:4px 6px 10px}
html.rail-shut .theme-switch-row{padding:4px 0 10px;display:flex;justify-content:center}
html.rail-shut:not(.dark) .rail .ts-dark,html.rail-shut.dark .rail .ts-light{display:none}
html.dark{--ink:#e8ecf2;--muted:#8b95a5;--line:#252c36;--bg:#0e1116;color-scheme:dark}
html.dark .setup-header,html.dark .setup-header nav{background:transparent}
html.dark .segment{color:#8b95a5}
html.dark .segment b{background:#1a2029;border-color:#2f3743;color:#aeb7c5}
html.dark .segment.active{color:#e8ecf2}
html.dark .segment.active b{background:#e8ecf2;border-color:#e8ecf2;color:#0e1116}
html.dark .segment.complete b{background:#1d3a35;border-color:#1d3a35;color:#8fd9c6}
html.dark,html.dark body{background:#0e1116;color:#e8ecf2}
html.dark ::selection{background:#2b4e86;color:#fff}
html.dark .workspace-header img,html.dark header img[src*=logo]{filter:brightness(0) invert(.93)}
html.dark img{color-scheme:light}
"""

if __name__ == '__main__':
    build()
    build(('onboarding.css',), 'theme-graphite-onboarding.css', ONBOARDING,
          re.compile(r'(^|[\s,>])aside\b|\.(sky|starfield|p-mark|pmark|aside-inner|ai-pill|typing-|intro|product-story|mini-dash|md-|story-|journey|preview-|cat-ghost|gw|sk\b|dashboard-link)'), base=False)
