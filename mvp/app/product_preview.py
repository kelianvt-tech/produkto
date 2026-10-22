"""Product page preview: a product fix shown ON the store's real product page (20 Oct 2026).

Kelian, after the designed articles: product page fixes need "a preview, just like how it would look on the
website". So we read the store's own product page (free, one plain fetch, cached a day), find the title and the
description on it, and put the draft's title, description, spec table and FAQ in their place. Everything else is
the store's: its theme, fonts, photos, price, buttons and menus. Before / After shows the page as it is now.

Safety: the store's page is shown inside Produkto, so every script, inline event handler, frame, form target and
meta refresh is removed before it is served, and the response carries a CSP that blocks scripts anyway. The page
then renders the way the theme renders with JavaScript off, which Shopify themes support (they're built to be
read by search engines). Links and buttons do nothing in the preview.

If the page can't be read (bot wall, timeout) or the title/description can't be found on it, the preview falls
back to a simple product page in the store's fonts and colours (brand_style), with its own photos and price, and
says so.

marks=True tags the draft's parts with data-pk paths so the pencil editor (content_review.editor) can work on them:
  title, desc.<n> (the n-th block of the description), spec_table, spec_table.<n>, faqs.<n>, faqs.<n>.answer
"""
import html
import json
import re
import time
import urllib.parse
from html.parser import HTMLParser

import db

E = lambda s: html.escape(s or '', quote=True)
TTL = 86400
CSP = ("default-src 'none'; img-src * data: blob:; style-src * 'unsafe-inline'; font-src * data:; "
       "media-src *; script-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri https:")
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS product_page_cache (url TEXT PRIMARY KEY, html TEXT, ok INTEGER, at REAL)')


def fetch(url, force=False, country=''):
    """The product page's HTML ('' if it couldn't be read). Cached a day, failures too (a bot wall stays a wall)."""
    import page_gap
    init()
    key = url + ('#' + country if country else '')     # each market's prices cached apart
    row = db.one('SELECT html, ok, at FROM product_page_cache WHERE url=?', (key,))
    if row and not force and time.time() - (row['at'] or 0) < TTL:
        return row['html'] if row['ok'] else ''
    try:
        text = page_gap.fetch(url, country)
        ok = 1 if len(text) > 2000 and '<' in text else 0
    except Exception:                                                       # noqa: BLE001 - blocked, timeout
        text, ok = '', 0
    db.write('INSERT OR REPLACE INTO product_page_cache VALUES (?,?,?,?)', (key, text if ok else '', ok, time.time()))
    return text if ok else ''


# ---- a light map of the page: where each element starts and ends, and its text ---------------------------

class _Map(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.src = text
        self.lines = [0]
        for m in re.finditer('\n', text):
            self.lines.append(m.end())
        self.stack, self.els, self.buf, self.n = [], [], [], 0
        self.skip = 0

    def _off(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._off()
        raw = self.get_starttag_text() or ''
        if tag in ('script', 'style', 'template', 'noscript', 'svg'):
            self.skip += 1 if tag not in _VOID else 0
        if tag in _VOID:
            return
        el = dict(tag=tag, attrs=dict(attrs), start=start, inner=start + len(raw), end=None, close=None, ts=self.n,
                  te=None, depth=len(self.stack))
        self.stack.append(el)
        self.els.append(el)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        pos = self._off()
        if tag in ('script', 'style', 'template', 'noscript', 'svg') and self.skip:
            self.skip -= 1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                for el in self.stack[i:]:
                    el['close'], el['te'] = pos, self.n
                    m = self.src.find('>', pos)
                    el['end'] = (m + 1) if m != -1 else pos
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.skip:
            return
        t = re.sub(r'\s+', ' ', data)
        if t.strip():
            self.buf.append(t)
            self.n += len(t)

    def text(self, el):
        full = getattr(self, 'full', None)
        if full is None:
            full = self.full = ''.join(self.buf)
        return _norm(full[el['ts']:el['te'] if el['te'] is not None else self.n])


def _norm(s):
    return re.sub(r'\s+', ' ', html.unescape(s or '')).strip().lower()


def _page_map(text):
    m = _Map(text)
    try:
        m.feed(text)
        m.close()
    except Exception:                                                       # noqa: BLE001 - odd markup
        pass
    m.full = ''.join(m.buf)
    m._cache = {}
    return m


def _in_body(m, el):
    body = next((e for e in m.els if e['tag'] == 'body'), None)
    return not body or el['start'] >= body['start']


_NOT_TITLE = ('a', 'nav', 'header', 'footer', 'li', 'button', 'option')


def _inside(m, el, tags):
    """True if el sits inside one of these tags (a menu, a link, a product card)."""
    return any(o['tag'] in tags and o['close'] is not None and o['start'] < el['start'] and o['close'] >= el['close']
               for o in m.els)


def find_title(m, title, near=None):
    """The element that shows the product's title (an h1 first), or None.

    Themes often repeat the product name in menus, cards and recently-viewed lists, sometimes as an h1 inside a
    link. Those never count; among the rest, the one closest before the description (near) wins."""
    want = _norm(title)
    if not want:
        return None
    cands = [e for e in m.els if e['close'] and _in_body(m, e) and m.text(e) == want and e['tag'] not in ('a', 'option', 'title', 'button')]
    cands = [e for e in cands if not _inside(m, e, _NOT_TITLE)] or []
    if not cands:
        return None
    if near is not None:
        before = [e for e in cands if e['start'] <= near['start']]
        pool = before or cands
        return min(pool, key=lambda e: (e['tag'] != 'h1', abs(near['start'] - e['start'])))
    h1 = [e for e in cands if e['tag'] == 'h1']
    return (h1 or sorted(cands, key=lambda e: -e['depth']))[0]


def find_description(m, lines):
    """The smallest element that holds the whole current description, or None."""
    lines = [_norm(l) for l in lines or [] if _norm(l)]
    if not lines:
        return None
    first, last = lines[0][:60], lines[-1][-60:]
    best = None
    for e in m.els:
        if not e['close'] or e['tag'] in ('head', 'meta', 'title', 'script', 'style') or not _in_body(m, e):
            continue
        t = m.text(e)
        if first in t and last in t and t.find(first) <= t.rfind(last):
            if best is None or len(t) < len(m.text(best)) or (len(t) == len(m.text(best)) and e['depth'] > best['depth']):
                best = e
    if best is None:
        return None
    # Too big = we found a whole column, not the description (e.g. "add to cart" sits inside it). Refuse.
    want = sum(len(l) for l in lines)
    return best if len(m.text(best)) <= max(want * 1.6, want + 400) else None


# ---- clean the store's page so it's safe to show inside Produkto ------------------------------------------

# Photo sliders stay hidden until their script runs; with scripts removed, show the first slide.
NOJS_CSS = ('<style>.splide,.splide__track,.splide__list,.splide__slide{visibility:visible!important}'
            '.splide__track{overflow:hidden}.splide__list{flex-wrap:nowrap!important}.splide__slide{flex:0 0 100%}'
            '.swiper:not(.swiper-initialized) .swiper-wrapper{display:flex;overflow:hidden}'
            '.swiper:not(.swiper-initialized) .swiper-slide{flex:0 0 100%}</style>')


def _style_on(m):
    """Themes load stylesheets as rel=preload or media=print and switch them on with an onload script. The
    scripts are removed below, so switch them on here or the page renders unstyled (5strands.com, 21 Oct 2026)."""
    tag = m.group(0)
    if not re.search(r'\sonload\s*=', tag, re.I):
        return tag
    if re.search(r'\bas\s*=\s*["\']?style', tag, re.I):
        tag = re.sub(r'\brel\s*=\s*(["\']?)preload\1', 'rel="stylesheet"', tag, flags=re.I)
    if re.search(r'stylesheet', tag, re.I):
        tag = re.sub(r'\bmedia\s*=\s*(["\'])print\1', 'media="all"', tag, flags=re.I)
    return tag


def sanitize(text, base):
    t = re.sub(r'<script\b.*?</script\s*>', '', text, flags=re.S | re.I)
    t = re.sub(r'<script\b[^>]*/?>', '', t, flags=re.I)
    t = re.sub(r'<(iframe|object|embed|frame|frameset)\b.*?(</\1\s*>|/?>)', '', t, flags=re.S | re.I)
    t = re.sub(r'<meta[^>]+http-equiv\s*=\s*["\']?refresh[^>]*>', '', t, flags=re.I)
    t = re.sub(r'<base\b[^>]*>', '', t, flags=re.I)
    t = re.sub(r'<link\b[^>]*>', _style_on, t, flags=re.I)
    t = re.sub(r'\s+on[a-z]+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', t, flags=re.I)
    t = re.sub(r'(href|src|action|formaction)\s*=\s*(["\'])\s*javascript:[^"\']*\2', r'\1="#"', t, flags=re.I)
    # lazy-loaded photos that a theme script would swap in
    t = re.sub(r'\sdata-srcset=', ' srcset=', t)
    t = re.sub(r'<img([^>]*?)\sdata-src=', r'<img\1 src=', t)
    t = re.sub(r'<html([^>]*)\bclass="([^"]*)\bno-js\b', r'<html\1class="\2no-js', t, count=1)
    head = ('<base href="%s"><meta name="referrer" content="no-referrer">' % E(base)) + NOJS_CSS
    return re.sub(r'<head([^>]*)>', lambda mm: '<head%s>%s' % (mm.group(1), head), t, count=1, flags=re.I) \
        if re.search(r'<head[^>]*>', t, re.I) else head + t


# ---- the draft's parts as HTML ---------------------------------------------------------------------------

_BLOCK = re.compile(r'<(p|ul|ol|h2|h3|h4|table|div|blockquote)\b[^>]*>.*?</\1\s*>', re.S | re.I)


def blocks(description_html):
    """The description's top-level blocks (paragraphs, lists, headings), each as HTML."""
    h = (description_html or '').strip()
    out, pos = [], 0
    for m in _BLOCK.finditer(h):
        loose = h[pos:m.start()].strip()
        if re.sub(r'<[^>]+>', '', loose).strip():
            out.append('<p>%s</p>' % loose)
        out.append(m.group(0))
        pos = m.end()
    rest = h[pos:].strip()
    if re.sub(r'<[^>]+>', '', rest).strip():
        out.append('<p>%s</p>' % rest)
    return out


def _mark(block, path):
    return re.sub(r'^<([a-z0-9]+)', lambda m: '<%s data-pk="%s"' % (m.group(1), E(path)), block, count=1, flags=re.I)


def _gaps(text, marks):
    return re.sub(r'\[ask merchant: ([^\]]*)\]', lambda m: '<mark class="pk-gap"%s>[ask merchant: %s]</mark>' % (
        (' data-gap="%s"' % m.group(1).replace('"', '&quot;')) if marks else '', m.group(1)), text)


PART_CSS = ('.pk-fix-spec{width:100%;border-collapse:collapse;margin:1.2em 0;font-size:.95em}'
            '.pk-fix-spec th,.pk-fix-spec td{text-align:left;padding:.55em .8em .55em 0;border-bottom:1px solid rgba(0,0,0,.12);vertical-align:top}'
            '.pk-fix-spec th{font-weight:600;width:40%}'
            '.pk-fix-faq{margin:1.6em 0 0}.pk-fix-faq h2{margin:0 0 .6em}.pk-fix-faq h3{margin:1em 0 .3em;font-size:1.05em}'
            'mark.pk-gap{background:#fff1c2;color:#5c4400;padding:1px 4px;border-radius:3px}'
            '.pk-new{box-shadow:0 0 0 2px #12a150;border-radius:4px;position:relative}'
            '.pk-new-tag{position:absolute;top:-11px;right:6px;background:#12a150;color:#fff;font:600 10px/1 -apple-system,Helvetica,Arial,sans-serif;'
            'letter-spacing:.04em;text-transform:uppercase;padding:4px 7px;border-radius:999px;z-index:3}')


def description_part(body, marks=False):
    """The new description (+ spec table) as it goes on the page."""
    out = [(_mark(b, 'desc.%d' % i) if marks else b) for i, b in enumerate(blocks(body.get('description_html', '')))]
    rows = body.get('spec_table') or []
    if rows:
        out.append('<table class="pk-fix-spec"%s><tbody>%s</tbody></table>' % (
            ' data-pk="spec_table"' if marks else '', ''.join(
                '<tr%s><th>%s</th><td>%s</td></tr>' % ((' data-pk="spec_table.%d"' % i) if marks else '', E(r['label']), E(r['value']))
                for i, r in enumerate(rows))))
    return _gaps(''.join(out), marks)


def faq_part(body, marks=False, heading='Questions and answers'):
    faqs = [(i, f) for i, f in enumerate(body.get('faqs') or []) if f.get('question') and f.get('answer')]
    if not faqs:
        return ''
    return _gaps('<div class="pk-fix-faq"><h2>%s</h2>%s</div>' % (E(heading), ''.join(
        '<div%s><h3>%s</h3><p%s>%s</p></div>' % ((' data-pk="faqs.%d"' % i) if marks else '', E(f['question']),
                                                 (' data-pk="faqs.%d.answer"' % i) if marks else '', E(f['answer']))
        for i, f in faqs)), marks)


# ---- put it together -------------------------------------------------------------------------------------

def _product(domain, body):
    import catalog_facts
    p = body.get('product') or {}
    rec = next((r for r in catalog_facts.get(domain) if r.get('handle') == p.get('handle')), None) or {}
    return dict(rec, **{k: v for k, v in p.items() if v}) if rec else p


def _current_lines(body, rec):
    cur = body.get('current') or {}
    return cur.get('description') or rec.get('description') or []


def on_page(domain, body, draft_type, marks=False, after=True, force=False):
    """(html, mode) - mode 'live' (the store's real page) or 'styled' (our stand-in), or None if nothing to show."""
    rec = _product(domain, body)
    url = rec.get('url') or ''
    country = ((db.brand(domain) or {}).get('country') or '').upper()
    page = fetch(url, force=force, country=country) if url else ''
    if page:
        out = _swap(page, url, body, rec, draft_type, marks, after)
        if out:
            return out, 'live'
    return styled(domain, body, rec, draft_type, marks, after), 'styled'


def _swap(page, url, body, rec, draft_type, marks, after):
    m = _page_map(page)
    cur_title = (body.get('current') or {}).get('title') or rec.get('title') or ''
    d_el = find_description(m, _current_lines(body, rec))
    t_el = find_title(m, cur_title, d_el)
    if draft_type == 'product_fix' and not d_el:
        return None
    if draft_type == 'faq' and not (d_el or t_el):
        return None
    edits = []                                                             # (start, end, replacement)
    if after:
        if draft_type == 'product_fix':
            new_t = body.get('title') or cur_title
            if t_el and new_t:
                edits.append((t_el['inner'], t_el['close'], ('<span data-pk="title">%s</span>' if marks else '%s') % E(new_t)))
            edits.append((d_el['inner'], d_el['close'], '<div class="pk-new">%s%s</div>' % (
                '<span class="pk-new-tag">New</span>' if not marks else '', description_part(body, marks))))
        else:
            anchor = d_el or t_el
            edits.append((anchor['end'], anchor['end'], '<div class="pk-new">%s%s</div>' % (
                '<span class="pk-new-tag">New</span>' if not marks else '', faq_part(body, marks))))
    for start, end, rep in sorted(edits, key=lambda e: -e[0]):
        page = page[:start] + rep + page[end:]
    split = urllib.parse.urlsplit(url)
    out = sanitize(page, '%s://%s/' % (split.scheme or 'https', split.netloc))
    style = '<style>%s%s</style>' % (PART_CSS, 'html{scroll-behavior:auto}')
    return re.sub(r'</head\s*>', lambda mm: style + mm.group(0), out, count=1, flags=re.I) if re.search(r'</head\s*>', out, re.I) \
        else style + out


def styled(domain, body, rec, draft_type, marks=False, after=True):
    """A simple product page in the store's own fonts and colours, when its real page can't be read."""
    import article_render
    import brand_style
    import drafts
    st = brand_style.get(domain)
    c, f = st['colors'], st['fonts']
    head = article_render._stack(f['heading']['family'], 'pk-heading' if f['heading']['faces'] else None, 'Georgia,serif')
    css = article_render.css(st)[len('<style>'):-len('</style>')]
    cur = body.get('current') or {}
    title = (body.get('title') if after and draft_type == 'product_fix' else None) or cur.get('title') or rec.get('title') or ''
    imgs = rec.get('images') or ([rec['image']] if rec.get('image') else [])
    price = article_render._price(rec, drafts._symbol(domain)) if rec.get('price') else ''
    if not price and rec.get('variants'):
        price = article_render._price(dict(price=(rec['variants'][0] or {}).get('price')), drafts._symbol(domain))
    if after and draft_type == 'product_fix':
        desc = '<div class="pk-new">%s</div>' % description_part(body, marks)
    else:
        desc = ''.join('<p>%s</p>' % E(t) for t in _current_lines(body, rec))
        if after and draft_type == 'faq':
            desc += '<div class="pk-new">%s</div>' % faq_part(body, marks)
    gallery = ''.join('<img src="%s" alt="">' % E(article_render._img(u, 900)) for u in imgs[:3])
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>%s%s body{margin:0;background:#fff}.pk-p{max-width:1100px;margin:0 auto;padding:36px 20px 80px;display:grid;'
            'grid-template-columns:1.1fr 1fr;gap:44px}.pk-p .pk-g img{width:100%%;display:block;margin:0 0 10px;background:%s}'
            '.pk-p h1{font-family:%s;font-weight:400;text-transform:%s;color:%s;font-size:34px;line-height:1.15;margin:0 0 12px}'
            '.pk-p .pk-price{font-family:var(--l);font-size:15px;margin:0 0 22px}.pk-p .pk-cta{display:block;text-align:center;background:%s;'
            'color:#fff;padding:15px;margin:0 0 30px;font-family:var(--l);text-transform:uppercase;letter-spacing:.08em;font-size:12px;'
            'border-radius:%dpx}.pk-note2{max-width:1100px;margin:0 auto;padding:10px 20px 0;font:12px -apple-system,Helvetica,Arial,'
            'sans-serif;color:#8a6d00}@media(max-width:760px){.pk-p{grid-template-columns:1fr}}</style></head><body>'
            '<p class="pk-note2">Your product page couldn\'t be read, so this is a stand-in in your store\'s fonts and colours.</p>'
            '<div class="pk-a pk-p"><div class="pk-g">%s</div><div><h1%s>%s</h1><p class="pk-price">%s</p>'
            '<span class="pk-cta">Add to cart</span><div class="pk-desc">%s</div></div></div></body></html>') % (
        css, PART_CSS, c['soft'], head, 'uppercase' if st.get('heading_upper') else 'none', c['accent'], c['ink'],
        min(int(st.get('radius') or 0), 12), gallery, ' data-pk="title"' if marks and after and draft_type == 'product_fix' else '',
        E(title), E(price), desc)


def preview(q):
    """GET /content/fix-preview?d=&id=[&before=1][&embed=1][&fresh=1]: a product fix or FAQ on the product page."""
    import accounts
    import content_agent
    import content_review
    domain = q.get('d', '')
    if not content_agent.enabled() or not accounts.can_see(domain):
        return 404, '<h1>Not found</h1>'
    try:
        row, body, _ = content_review.load(int(q.get('id', '')), domain)
    except ValueError:
        row = None
    if not row or row['draft_type'] not in ('product_fix', 'faq'):
        return 404, '<h1>Not found</h1>'
    content_review.rebuild(body, row['draft_type'])
    page, mode = on_page(domain, body, row['draft_type'], marks=bool(q.get('embed')), after=not q.get('before'),
                         force=bool(q.get('fresh')))
    if not q.get('embed'):
        bar = ('<div style="position:sticky;top:0;z-index:2147483647;background:#0b1b35;color:#fff;font:600 13px/1.4 -apple-system,'
               'Helvetica,Arial,sans-serif;padding:10px 16px;display:flex;justify-content:space-between;gap:12px">'
               '<span>Preview: %s on your product page. Not live.</span><a style="color:#fff" href="%s">Back to the draft</a></div>') % (
            'your page now' if q.get('before') else 'this draft',
            E('/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=row['id']))))
        page = re.sub(r'<body([^>]*)>', lambda mm: '<body%s>%s' % (mm.group(1), bar), page, count=1, flags=re.I)
    return 200, ('csp', page)


def frame(domain, did, height=900, before=False):
    """The iframe for the draft screens. The pencil works on it (same origin; the page's own scripts are gone)."""
    src = '/content/fix-preview?' + urllib.parse.urlencode(dict(d=domain, id=did, embed=1, **({'before': 1} if before else {})))
    js = ("var f=this;function h(){try{var d=f.contentDocument,t=d.querySelector('.pk-new,[data-pk]');"
          "if(t&&!f.dataset.sc){f.dataset.sc=1;f.contentWindow.scrollTo(0,Math.max(0,t.getBoundingClientRect().top+f.contentWindow.scrollY-140))}}catch(e){}}"
          "h();setTimeout(h,600);if(window.pkEditorReady)window.pkEditorReady(f)")
    return ('<iframe class="cr-frame pk-fixframe" id="pk-frame" title="Product page preview" src="%s" style="height:%dpx" '
            'onload="%s"></iframe>') % (E(src), height, E(js))


def toggle(domain, did):
    """Before / After switch over the frame."""
    return ('<div class="pk-ba" role="group" aria-label="Show"><button type="button" aria-pressed="false" data-ba="before">Now on your store</button>'
            '<button type="button" aria-pressed="true" data-ba="after">With this draft</button></div>'
            '<script>(function(){var g=document.currentScript.previousElementSibling;g.addEventListener("click",function(e){'
            'var b=e.target.closest("[data-ba]");if(!b)return;var f=document.getElementById("pk-frame");if(!f)return;'
            'g.querySelectorAll("[data-ba]").forEach(function(x){x.setAttribute("aria-pressed",x===b?"true":"false")});'
            'var u=new URL(f.src,location.href);if(b.dataset.ba==="before")u.searchParams.set("before","1");else u.searchParams.delete("before");'
            'delete f.dataset.sc;f.src=u.pathname+u.search;var t=document.querySelector(".pk-tools");if(t)t.classList.toggle("pk-locked",b.dataset.ba==="before")})})()</script>')


CSS = """
.pk-fixframe{width:100%;border:1px solid var(--line,#e3e8ef);border-radius:10px;background:#fff;display:block}
.pk-ba{display:inline-flex;gap:2px;background:var(--tint,#eef3fb);padding:3px;border-radius:9px;margin:0 0 10px}
.pk-ba button{border:0;background:transparent;font:600 13px/1 inherit;padding:8px 12px;border-radius:7px;cursor:pointer;color:inherit}
.pk-ba button[aria-pressed=true]{background:#fff;color:#0b1b35;box-shadow:0 1px 2px rgba(11,27,53,.12)}
.pk-tools.pk-locked .pk-pencil{opacity:.4;pointer-events:none}
"""
