"""Brand style: the store's own fonts, colours and shapes, read from its website (19 Oct 2026).

Kelian, after the first styled article mockup: it "feels like Produkto, not Clubhouse". An article
has to look like the brand that publishes it, so before the agent renders one it reads the store's
homepage and stylesheets and works out:

  * fonts: the heading font, the body font and the small-label font, with their font files
    (@font-face) or Google Fonts link, by which CSS rules use them (h1/h2/title rules -> heading,
    body/p rules -> body, small uppercase rules or a mono family -> label);
  * whether headings are set in capitals, and how letter-spaced labels are;
  * colours: text, accent, a soft background and a line colour, by how often the CSS uses them;
  * button corners (square or rounded).

Free: plain page and CSS fetches, no AI call. Cached per store in content_settings['brand_style'] and
re-read monthly. The merchant's own corrections ("use a different font") live in
content_settings['brand_style_overrides'] (article_learning.py) and always win over what was read.

On the store itself the fonts are already loaded, so an article only names them. The @font-face
copies are for previews outside the store (Produkto's preview, the test store); a brand's paid fonts
must never be used anywhere public outside its own site.
"""
import colorsys
import json
import re
import time
import urllib.parse
from collections import Counter

TTL = 30 * 86400
MAX_CSS = 30                 # stylesheets read per store
MAX_CSS_BYTES = 4_000_000

# Families that are generic fallbacks, never a brand's choice.
_GENERIC = {'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'system_ui', 'inherit',
            'initial', 'unset', '-apple-system', 'blinkmacsystemfont', 'segoe ui', 'roboto', 'helvetica', 'arial',
            'noto sans', 'liberation sans', 'apple color emoji', 'segoe ui emoji', 'segoe ui symbol',
            'noto color emoji', 'ui-sans-serif', 'ui-serif', 'ui-monospace', 'times new roman', 'times', 'courier',
            'courier new', 'var', ''}
# Icon and widget fonts that show up in stylesheets but never set text.
_ICON = re.compile(r'icon|awesome|slick|swiper|glyph|material|feather|fa-|ionic|dashicons|star|emoji', re.I)
_MONO = re.compile(r'mono|courier|code|typewriter', re.I)

DEFAULT = dict(
    fonts=dict(heading=dict(family='', faces=[]), body=dict(family='', faces=[]), label=dict(family='', faces=[])),
    google_css=[], heading_upper=False, label_upper=True,
    colors=dict(ink='#1a1a1a', accent='#1a1a1a', soft='#f5f4f0', line='#e2e0da', muted='#6b6a66'),
    radius=0, learned_at=0, source='')


# ---- fetching --------------------------------------------------------------------------------------

def _fetch(url):
    import page_gap
    return page_gap.fetch(url)


def _css_urls(html, base):
    out = []
    for m in re.finditer(r'<link\b[^>]*>', html, re.I):
        tag = m.group(0)
        if not re.search(r'rel=["\']?(stylesheet|preload)', tag, re.I):
            continue
        href = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if href and ('.css' in href.group(1) or 'fonts.googleapis' in href.group(1)):
            out.append(urllib.parse.urljoin(base, href.group(1).replace('&amp;', '&')))
    return list(dict.fromkeys(out))


def read_site(domain, pages_out=None):
    """[(css text, its url)] for the store's homepage plus one product page: inline <style> blocks first.
    pages_out, a dict, receives {'home': html, 'product': html} for the cascade check."""
    base = 'https://%s/' % domain
    pages = [base]
    try:
        import catalog_facts
        recs = catalog_facts.get(domain)
        if recs:
            pages.append(recs[0]['url'])
    except Exception:                                                   # noqa: BLE001 - one page is enough
        pass
    sheets, seen, size = [], set(), 0
    for page in pages:
        try:
            html = _fetch(page)
        except Exception:                                               # noqa: BLE001
            continue
        if pages_out is not None:
            pages_out['home' if page == base else 'product'] = html
        for block in re.findall(r'<style\b[^>]*>(.*?)</style>', html, re.I | re.S):
            sheets.append((block, page))
        for u in _css_urls(html, page):
            if u in seen or len(seen) >= MAX_CSS or size > MAX_CSS_BYTES:
                continue
            seen.add(u)
            if 'fonts.googleapis' in u:
                sheets.append(('/*google*/ @import url(%s);' % u, u))
                continue
            try:
                css = _fetch(u)
            except Exception:                                           # noqa: BLE001
                continue
            size += len(css)
            sheets.append((css, u))
    return sheets


# ---- parsing ---------------------------------------------------------------------------------------

def _family(value, variables):
    """The first real family named in a font-family value, resolving var(--x)."""
    value = value.replace('!important', '').strip()
    m = re.match(r'var\((--[\w-]+)\)', value)
    if m:
        value = variables.get(m.group(1), '')
    for part in value.split(','):
        name = part.strip().strip('"\'').strip()
        if name.lower() not in _GENERIC and not name.startswith('var(') and not _ICON.search(name):
            return name
    return ''


def _faces(css, css_url):
    """{family: [(weight, style, url)]} from @font-face rules, urls made absolute."""
    out = {}
    for block in re.findall(r'@font-face\s*\{([^}]*)\}', css, re.I):
        fam = re.search(r'font-family\s*:\s*([^;]+)', block, re.I)
        if not fam:
            continue
        name = fam.group(1).strip().strip('"\'').strip()
        if _ICON.search(name):
            continue
        srcs = re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)\s*format\(\s*["\']?([\w-]+)', block, re.I) or \
            [(u, '') for u in re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', block, re.I)]
        best = next((u for u, f in srcs if 'woff2' in f.lower() or u.split('?')[0].endswith('.woff2')), None) or \
            next((u for u, f in srcs if 'woff' in f.lower()), None) or (srcs[0][0] if srcs else None)
        if not best or best.startswith('data:'):
            continue
        w = re.search(r'font-weight\s*:\s*(\w+)', block, re.I)
        st = re.search(r'font-style\s*:\s*(\w+)', block, re.I)
        weight = {'normal': '400', 'bold': '700'}.get((w.group(1) if w else '400').lower(), w.group(1) if w else '400')
        out.setdefault(name, []).append((weight, (st.group(1) if st else 'normal').lower(),
                                         urllib.parse.urljoin(css_url, best)))
    return out


def _rules(css):
    """(selector, declarations) for every plain rule, with @media wrappers flattened."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'@font-face\s*\{[^}]*\}', '', css, flags=re.I)
    for m in re.finditer(r'([^{}@;]+)\{([^{}]*)\}', css):
        yield m.group(1).strip(), m.group(2)


def _decl(decls, prop):
    m = re.findall(r'(?:^|;)\s*%s\s*:\s*([^;]+)' % re.escape(prop), decls, re.I)
    return m[-1].strip() if m else ''


_HEAD_SEL = re.compile(r'(^|[\s,>+~])h[1-3]\b|heading|title|headline|display|\.h[0-2]\b', re.I)
_BODY_SEL = re.compile(r'(^|[\s,])(body|html|p)(\b|$)|\.rte\b|body-?text|paragraph|description', re.I)
_LABEL_SEL = re.compile(r'label|caption|eyebrow|subtitle|badge|tag|menu|nav|button|btn|price|breadcrumb|vendor', re.I)


def _px(size):
    m = re.match(r'([\d.]+)\s*(px|rem|em)?', size or '')
    if not m:
        return None
    n = float(m.group(1))
    return n * 16 if m.group(2) in ('rem', 'em') else n


def _hexes(text):
    out = []
    for h in re.findall(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', text):
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        out.append('#' + h.lower())
    for r, g, b in re.findall(r'rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})', text):
        out.append('#%02x%02x%02x' % (int(r), int(g), int(b)))
    for r, g, b in re.findall(r'--color-[\w-]+\s*:\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})', text):
        out.append('#%02x%02x%02x' % (int(r), int(g), int(b)))       # Shopify themes: "--color-base-text: 18, 18, 18"
    return out


def _hls(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def _colors(texts):
    count = Counter()
    for t in texts:
        count.update(_hexes(t))
    dark = [(c, n) for c, n in count.most_common() if _hls(c)[1] < 0.3 and c not in ('#000000',)]
    ink = dark[0][0] if dark else ('#000000' if count.get('#000000') else DEFAULT['colors']['ink'])
    # Accent: the most used colour with some hue that isn't near-white or near-black.
    tinted = [c for c, n in count.most_common() if 0.12 < _hls(c)[1] < 0.75 and _hls(c)[2] > 0.18]
    darktint = [c for c, _ in dark if _hls(c)[2] > 0.12]
    accent = (darktint[0] if darktint else tinted[0] if tinted else ink)
    soft = next((c for c, _ in count.most_common() if 0.9 < _hls(c)[1] < 0.985), DEFAULT['colors']['soft'])
    line = next((c for c, _ in count.most_common() if 0.8 < _hls(c)[1] <= 0.9), DEFAULT['colors']['line'])
    muted = next((c for c, _ in count.most_common() if 0.35 < _hls(c)[1] < 0.6 and _hls(c)[2] < 0.15),
                 DEFAULT['colors']['muted'])
    return dict(ink=ink, accent=accent, soft=soft, line=line, muted=muted)


# ---- which rule wins on a real element --------------------------------------------------------------
# No browser on the server, so a small cascade: find the product page's title, description and price in its
# HTML, then the font-family rule with the highest specificity whose selector matches that element and its
# ancestors (later rules win ties, !important beats everything). Rough, but it is what separates a brand's
# own heading face from the theme default that a plain count of rules gets wrong.

from html.parser import HTMLParser


class _Tree(HTMLParser):
    VOID = {'br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'wbr', 'area', 'col', 'embed', 'track', 'base'}

    def __init__(self, need_main=True):
        super().__init__(convert_charrefs=True)
        self.stack, self.found, self.need_main = [], {}, need_main

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        node = dict(tag=tag, classes=set((a.get('class') or '').split()), id=a.get('id') or '')
        chain = self.stack + [node]
        cls = ' '.join(node['classes'])
        # Only the page's main content: headers, drawers, menus and popups have their own fonts.
        in_main = any(n['tag'] == 'main' or n['id'] in ('MainContent', 'main', 'main-content') for n in chain)
        skip = any(re.search(r'drawer|header|menu|popup|modal|cart|footer|announcement|cookie', ' '.join(n['classes']) + ' ' + n['id'], re.I)
                   for n in chain)
        if (self.need_main and not in_main) or skip:
            if tag not in self.VOID:
                self.stack.append(node)
            return
        if tag == 'h1' and 'h1' not in self.found:
            self.found['h1'] = chain
        if 'price' in cls and 'price' not in self.found and tag in ('span', 'div', 'p', 's', 'strong', 'dd'):
            self.found['price'] = chain
        if tag == 'p' and 'p' not in self.found and any('description' in c or c == 'rte' for n in chain for c in n['classes']):
            self.found['p'] = chain
        if tag == 'h2' and 'h2' not in self.found:
            self.found['h2'] = chain
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                return


_PSEUDO = re.compile(r':(hover|focus|active|visited|before|after|placeholder|checked|disabled|not\([^)]*\)|'
                     r'nth-[\w-]+\([^)]*\)|first-child|last-child|[\w-]+)', re.I)


def _compound(tok):
    """'.a.b#c h1' token -> (tag, classes, id) or None if it has attribute selectors we can't judge."""
    tok = _PSEUDO.sub('', tok)
    if '[' in tok:
        tok = re.sub(r'\[[^\]]*\]', '', tok)
    m = re.match(r'^([a-zA-Z][\w-]*|\*)?((?:[.#][\w-]+)*)$', tok)
    if not m:
        return None
    tag = (m.group(1) or '').lower()
    classes = set(re.findall(r'\.([\w-]+)', m.group(2)))
    ids = re.findall(r'#([\w-]+)', m.group(2))
    return tag, classes, ids[0] if ids else ''


def _matches(comp, node):
    tag, classes, id_ = comp
    return (not tag or tag == '*' or tag == node['tag']) and classes <= node['classes'] and (not id_ or id_ == node['id'])


def _selector_hits(sel, chain):
    """Specificity (ids, classes, tags) if the selector matches the last node of chain, else None."""
    toks = [t for t in re.split(r'\s*[>+~]\s*|\s+', sel.strip()) if t]
    if not toks:
        return None
    comps = [_compound(t) for t in toks]
    if any(c is None for c in comps) or not _matches(comps[-1], chain[-1]):
        return None
    i = len(chain) - 2
    for comp in reversed(comps[:-1]):                 # each earlier part must match some ancestor, in order
        while i >= 0 and not _matches(comp, chain[i]):
            i -= 1
        if i < 0:
            return None
        i -= 1
    return (sum(1 for c in comps if c[2]), sum(len(c[1]) for c in comps), sum(1 for c in comps if c[0] and c[0] != '*'))


def _winning(chain, sheets, prop, value_of):
    """(value, selector) of the strongest rule setting prop on the chain's last element, or None.
    Inherited properties also come from the nearest ancestor that sets them."""
    for depth in range(len(chain), 0, -1):
        sub = chain[:depth]
        best, order = None, 0
        for css, _ in sheets:
            for sel, decls in _rules(css):
                order += 1
                raw = _decl(decls, prop)
                if not raw:
                    continue
                val = value_of(raw)
                if not val or val in ('inherit', 'initial', 'unset'):
                    continue
                for part in sel.split(','):
                    spec = _selector_hits(part, sub)
                    if spec is None:
                        continue
                    rank = ('!important' in raw, spec, order)
                    if best is None or rank > best[0]:
                        best = (rank, val, part.strip()[:80])
        if best:
            return best[1], best[2]
    return None


def element_fonts(pages, sheets, variables):
    """{'title': font, 'text': font, 'price': font, 'section': font} as the product page actually shows them."""
    targets = {}
    for key, page in (('product', pages.get('product')), ('home', pages.get('home'))):
        if not page:
            continue
        t = _Tree()
        try:
            t.feed(page)
            if not t.found:                                              # no <main>: the whole page, minus chrome
                t = _Tree(need_main=False)
                t.feed(page)
        except Exception:                                                # noqa: BLE001 - broken markup
            continue
        for name, chain in t.found.items():
            role = dict(h1='title', p='text', price='price', h2='section')[name]
            if key == 'product' or role not in targets:
                targets.setdefault(role, chain)
    out = {}
    for role, chain in targets.items():
        fam = _winning(chain, sheets, 'font-family', lambda v: _family(v, variables))
        if fam:
            caps = _winning(chain, sheets, 'text-transform', lambda v: v.replace('!important', '').strip().lower())
            out[role] = dict(font=fam[0], rule=fam[1], upper=bool(caps and caps[0] == 'uppercase'))
    return out


def evidence(sheets, pages=None):
    """What the CSS shows: every loaded font with the rules that use it, the colours by how often and
    where they are used, button corners. Pure function, so it can be tested on saved CSS."""
    variables, faces, google = {}, {}, []
    for css, url in sheets:
        for k, v in re.findall(r'(--[\w-]+)\s*:\s*([^;}]+)', css):
            variables.setdefault(k, v.strip())
        for fam, fs in _faces(css, url).items():
            faces.setdefault(fam, [])
            faces[fam] += [f for f in fs if f not in faces[fam]]
        google += re.findall(r'@import url\((https://fonts\.googleapis[^)]+)\)', css)
    loaded = set(faces) | {urllib.parse.unquote_plus(m) for g in google for m in re.findall(r'family=([^:&]+)', g)}
    fonts = {f: dict(rules=0, caps=0, sizes=Counter(), selectors=[], score=Counter()) for f in loaded}
    spacing, radius, colours = Counter(), Counter(), {}
    for css, _ in sheets:
        for sel, decls in _rules(css):
            for prop in ('color', 'background-color', 'background', 'border-color', 'border', 'border-top',
                         'border-bottom'):
                v = _decl(decls, prop)
                for h in _hexes(v):
                    c = colours.setdefault(h, dict(n=0, text=0, bg=0, line=0, selectors=[]))
                    c['n'] += 1
                    c['text' if prop == 'color' else 'bg' if prop.startswith('background') else 'line'] += 1
                    if len(c['selectors']) < 4:
                        c['selectors'].append(sel[:60])
            if re.search(r'button|btn', sel, re.I):
                r = _px(_decl(decls, 'border-radius'))
                if r is not None:
                    radius[min(int(r), 999)] += 1
            ff = _decl(decls, 'font-family')
            fam = _family(ff, variables) if ff else ''
            if fam not in fonts:
                continue
            caps = _decl(decls, 'text-transform').lower().startswith('uppercase')
            size = _px(_decl(decls, 'font-size'))
            f = fonts[fam]
            f['rules'] += 1
            f['caps'] += caps
            if size:
                f['sizes'][round(size)] += 1
            if len(f['selectors']) < 14 and sel[:70] not in f['selectors']:
                f['selectors'].append(sel[:70])
            if _HEAD_SEL.search(sel):
                f['score']['heading'] += 3
            if _BODY_SEL.search(sel):
                f['score']['body'] += 2
            if _LABEL_SEL.search(sel) or (caps and size and size <= 14) or _MONO.search(fam):
                f['score']['label'] += 2 + 2 * caps + 2 * bool(_MONO.search(fam))
                ls = _decl(decls, 'letter-spacing')
                if ls and caps:
                    spacing[ls] += 1
    for role, key in (('heading', '--font-heading-family'), ('body', '--font-body-family')):
        fam = _family(variables.get(key, ''), variables)
        if fam in fonts:
            fonts[fam]['score'][role] += 4
            fonts[fam]['theme_variable'] = key
    applied = element_fonts(pages or {}, sheets, variables)
    for role, a in applied.items():
        if a['font'] in fonts:
            fonts[a['font']]['score'][dict(title='heading', section='heading', text='body', price='label')[role]] += 6
    return dict(fonts=fonts, faces=faces, google=list(dict.fromkeys(google))[:3], colours=colours,
                radius=radius, spacing=spacing, applied=applied)


def _heuristic(ev):
    fonts = ev['fonts']

    def pick(role, avoid=()):
        ranked = sorted(fonts, key=lambda f: -fonts[f]['score'][role])
        return next((f for f in ranked if fonts[f]['score'][role] and f not in avoid), '')
    body = pick('body') or next(iter(sorted(fonts, key=lambda f: -fonts[f]['rules'])), '')
    heading = pick('heading') or body
    label = pick('label', avoid=(heading,)) or body
    count = Counter({h: c['n'] for h, c in ev['colours'].items()})
    texts = []
    for h, c in ev['colours'].items():
        texts += [h] * c['n']
    cols = _colors([' '.join(texts)])
    caps = lambda f: bool(f and fonts[f]['rules'] and fonts[f]['caps'] * 2 > fonts[f]['rules'])
    return dict(heading_font=heading, body_font=body, label_font=label, heading_upper=caps(heading),
                label_upper=True if label != body else caps(label), radius=ev['radius'].most_common(1)[0][0]
                if ev['radius'] else 0, **cols, why='Read from the stylesheet rules (no AI).')


DECIDE_RULES = """You are a web designer reading an online store's CSS to copy its look for a blog article.

From the evidence, choose:
- heading_font: the font the brand uses for headlines and product names (look at h1/h2, product title, section heading selectors). Often a serif or display face; may differ from what a theme variable says.
- body_font: the font for running text (body, p, product descriptions).
- label_font: the font for small labels, menus, buttons, prices and tags (often a mono or the body font).
- heading_upper / label_upper: whether those are set in capitals (text-transform uppercase on most of their rules).
- ink (main text colour), accent (the brand's signature dark or colour used for headings, buttons or bands; not a sale red or an alert colour), soft (a light background tint for panels; not pure white), line (a light border colour), muted (grey for secondary text). Each must be one of the hex values listed.
- radius: button corner radius in px (0 if the brand's main buttons are square).
Pick fonts only from the FONTS list. Ignore fonts used only by apps, widgets, cookie banners, reviews or checkout (e.g. selectors with "jdgm", "klaviyo", "cookie", "shopify-pc", "spr-"). why: one short sentence."""

DECIDE_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["heading_font", "body_font", "label_font", "heading_upper", "label_upper", "ink",
                              "accent", "soft", "line", "muted", "radius", "why"],
                 "properties": {k: {"type": "string"} for k in ("heading_font", "body_font", "label_font", "ink",
                                                                 "accent", "soft", "line", "muted", "why")}}
DECIDE_SCHEMA["properties"].update(heading_upper={"type": "boolean"}, label_upper={"type": "boolean"},
                                   radius={"type": "integer"})


def _evidence_text(ev):
    lines = ['FONTS (name: rules using it, of which in capitals; common sizes px; theme variable; sample selectors)']
    for f, d in sorted(ev['fonts'].items(), key=lambda kv: -kv[1]['rules']):
        lines.append('- %s: %d rules, %d in capitals; sizes %s; %s; %s' % (
            f, d['rules'], d['caps'], ', '.join(str(k) for k, _ in d['sizes'].most_common(4)) or '-',
            d.get('theme_variable', 'no theme variable'), ' | '.join(d['selectors'][:12]) or '(no rules)'))
    if ev.get('applied'):
        lines.append('\nWHAT THE PAGES ACTUALLY SHOW (strongest matching rule on the real element; trust this over counts):')
        names = dict(title='Product page title (h1)', text='Product description text', price='Price',
                     section='Homepage section heading (h2)')
        for role, a in ev['applied'].items():
            lines.append('- %s: %s%s  (rule: %s)' % (names[role], a['font'], ', in capitals' if a.get('upper') else '', a['rule']))
    lines.append('\nCOLOURS (hex: uses; as text / background / border; sample selectors)')
    for h, c in sorted(ev['colours'].items(), key=lambda kv: -kv[1]['n'])[:28]:
        lines.append('- %s: %d (%d/%d/%d) %s' % (h, c['n'], c['text'], c['bg'], c['line'], ' | '.join(c['selectors'])))
    lines.append('\nBUTTON RADIUS px (value: rules): ' + ', '.join('%s: %d' % kv for kv in ev['radius'].most_common(6)))
    return '\n'.join(lines)


def decide(ev, usage=None, ai=True):
    """Roles and colours from the evidence: one helper-model call (~0.1 cent), checked against the evidence;
    the rule-based guess when the AI is off or answers with something that isn't on the page."""
    guess = _heuristic(ev)
    if not ai or not ev['fonts']:
        return guess
    import llm
    try:
        d = llm.json_call(DECIDE_RULES, _evidence_text(ev), 'brand_style', DECIDE_SCHEMA, usage=usage, attempts=2)
    except Exception:                                                    # noqa: BLE001 - no credit, no network
        return guess
    for k in ('heading_font', 'body_font', 'label_font'):
        if d.get(k) not in ev['fonts']:
            d[k] = guess[k]
    light = dict(ink=(0, .35), accent=(0, .75), soft=(.86, .99), line=(.72, .95), muted=(.25, .65))
    for k in ('ink', 'accent', 'soft', 'line', 'muted'):
        v = (d.get(k) or '').lower()
        if v not in ev['colours'] or not light[k][0] <= _hls(v)[1] <= light[k][1]:
            d[k] = guess[k] if light[k][0] <= _hls(guess[k])[1] <= light[k][1] else DEFAULT['colors'][k]
        d[k] = d[k].lower()
    title = (ev.get('applied') or {}).get('title')
    if title and title['font'] == d['heading_font']:
        d['heading_upper'] = title['upper']           # what the real product title does beats a guess
    d['radius'] = max(0, min(40, int(d.get('radius') or 0)))
    return d


def learn_from(sheets, usage=None, ai=True, pages=None):
    """The style from [(css, url)] (and the pages' HTML, for the cascade check)."""
    ev = evidence(sheets, pages)
    d = decide(ev, usage=usage, ai=ai)
    fonts = {role: dict(family=d[role + '_font'], faces=ev['faces'].get(d[role + '_font'], []))
             for role in ('heading', 'body', 'label')}
    return dict(fonts=fonts, google_css=ev['google'], heading_upper=bool(d['heading_upper']),
                label_upper=bool(d['label_upper']),
                label_spacing=(ev['spacing'].most_common(1)[0][0] if ev['spacing'] else '.08em'),
                colors={k: d[k] for k in ('ink', 'accent', 'soft', 'line', 'muted')}, radius=d['radius'],
                why=d.get('why', ''), learned_at=time.time())


# ---- stored style ----------------------------------------------------------------------------------

def learn(domain, force=False, usage=None):
    """Read the store's site and cache its style. Returns the style (DEFAULT when the site can't be read)."""
    import content_setup
    s = content_setup.get(domain)
    cached = s.get('brand_style')
    if cached and not force and time.time() - cached.get('learned_at', 0) < TTL:
        return cached
    pages = {}
    sheets = read_site(domain, pages)
    style = learn_from(sheets, usage=usage, pages=pages) if sheets else dict(DEFAULT, learned_at=time.time())
    style['source'] = 'https://%s/' % domain
    s = content_setup.get(domain)
    s['brand_style'] = style
    content_setup.put(domain, s)
    return style


def get(domain, learn_if_missing=True):
    """The style to render with: what was read, with the merchant's corrections on top."""
    import content_setup
    s = content_setup.get(domain)
    style = s.get('brand_style') or (learn(domain) if learn_if_missing else None) or dict(DEFAULT)
    return apply_overrides(style, s.get('brand_style_overrides') or {})


def apply_overrides(style, overrides):
    out = json.loads(json.dumps(style))
    for k, v in overrides.items():
        if k in ('heading_font', 'body_font', 'label_font'):
            role = k.split('_')[0]
            out['fonts'][role] = dict(family=v, faces=_known_faces(style, v))
        elif k in ('ink', 'accent', 'soft', 'line', 'muted') and re.fullmatch(r'#[0-9a-fA-F]{6}', v or ''):
            out['colors'][k] = v.lower()
        elif k in ('heading_upper', 'label_upper'):
            out[k] = bool(v)
        elif k == 'radius':
            try:
                out['radius'] = max(0, min(40, int(v)))
            except (TypeError, ValueError):
                pass
    return out


def _known_faces(style, family):
    for f in style['fonts'].values():
        if f['family'] == family:
            return f['faces']
    return []


def families(style):
    """The distinct fonts the store uses, for the learning step to choose from."""
    return [f for f in dict.fromkeys(style['fonts'][r]['family'] for r in ('heading', 'body', 'label')) if f]


def summary(style):
    """One plain line for the merchant: 'Headings in PS Times (capitals), text in Helvetica Neue, ...'."""
    f = style['fonts']
    parts = []
    if f['heading']['family']:
        parts.append('headings in %s%s' % (f['heading']['family'], ' (capitals)' if style.get('heading_upper') else ''))
    if f['body']['family'] and f['body']['family'] != f['heading']['family']:
        parts.append('text in %s' % f['body']['family'])
    if f['label']['family'] and f['label']['family'] not in (f['heading']['family'], f['body']['family']):
        parts.append('labels in %s' % f['label']['family'])
    parts.append('%s buttons' % ('square' if not style.get('radius') else 'rounded'))
    out = ', '.join(parts)
    return out[:1].upper() + out[1:] + '.'


if __name__ == '__main__':
    import sys
    pg = {}
    st = learn_from(read_site(sys.argv[1], pg), ai='--no-ai' not in sys.argv, pages=pg)
    print(json.dumps({k: v for k, v in st.items()}, indent=1)[:3000])
    print(summary(st))
