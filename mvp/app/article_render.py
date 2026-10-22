"""Article render: the AEO article as a designed page in the store's own style (19 Oct 2026).

The writer (drafts.article) returns blocks, not HTML: a short intro, an "At a glance" box, sections
(optionally numbered steps) with a product card and a photo, an optional table, an FAQ and a closing
banner. This turns them into one HTML block for the store's blog, styled with the brand's fonts, colours
and button corners (brand_style.py), using the store's own product photos.

Approved look: mvp/content-agent/shopify-test/article-mockup-skincare-2026-10-19.html (Kelian, 19 Oct).

Everything is scoped under one class (.pk-a) so it can't restyle the rest of the store. The FAQ also
goes out as FAQPage markup so assistants can read it as questions and answers.
"""
import html
import json
import re

E = lambda s: html.escape(s or '', quote=True)
FOLD = 'pk-a'

# Photo choice: a product's first image is usually a packshot on a plain background; the others are
# lifestyle shots. Packshots go in cards, lifestyle shots go wide.


def _font_face(alias, faces):
    out = []
    for weight, style, url in faces[:3]:
        fmt = 'woff2' if '.woff2' in url else 'woff' if '.woff' in url else 'truetype' if '.ttf' in url else 'opentype'
        out.append('@font-face{font-family:"%s";src:url(%s) format("%s");font-weight:%s;font-style:%s;font-display:swap}'
                   % (alias, url, fmt, re.sub(r'[^\w]', '', str(weight)) or '400', style if style in ('normal', 'italic') else 'normal'))
    return ''.join(out)


def _stack(family, alias, generic):
    names = []
    if alias:
        names.append('"%s"' % alias)
    if family:
        names.append('"%s"' % family.replace('"', ''))
    names.append(generic)
    return ','.join(names)


def css(style, theme_title=False):
    """The <style> block. theme_title also restyles the theme's own article title (test stores only)."""
    f, c = style['fonts'], style['colors']
    faces, alias = [], {}
    for role in ('heading', 'body', 'label'):
        fam = f[role]['family']
        if fam and f[role]['faces'] and fam not in alias:
            alias[fam] = 'pk-%s' % role
            faces.append(_font_face(alias[fam], f[role]['faces']))
    generic = dict(heading='Georgia,serif', body='-apple-system,"Helvetica Neue",Arial,sans-serif',
                   label='ui-monospace,Menlo,monospace' if re.search(r'mono', f['label']['family'], re.I)
                   else '-apple-system,"Helvetica Neue",Arial,sans-serif')
    stacks = {r: _stack(f[r]['family'], alias.get(f[r]['family']), generic[r]) for r in ('heading', 'body', 'label')}
    up_h = 'uppercase' if style.get('heading_upper') else 'none'
    up_l = 'uppercase' if style.get('label_upper') else 'none'
    ls_l = style.get('label_spacing') or '.08em'
    if not re.fullmatch(r'-?[\d.]+(em|px|rem)', ls_l):
        ls_l = '.08em'
    r = int(style.get('radius') or 0)
    pill = '999px' if r >= 20 else '%dpx' % r
    google = ''.join('@import url(%s);' % u for u in style.get('google_css') or [] if u.startswith('https://fonts.googleapis.com/'))
    a = '.' + FOLD
    rules = google + ''.join(faces) + '''
A{--ink:INK;--accent:ACC;--soft:SOFT;--line:LINE;--muted:MUTED;--h:HEAD;--b:BODY;--l:LABEL;color:var(--ink);font-family:var(--b);font-size:16px;line-height:1.7}
A *{box-sizing:border-box}
A p{margin:0 0 1.1em}
A .pk-list{margin:-.4em 0 1.1em;padding-left:1.2em}
A .pk-list li{margin:0 0 .35em}
A a{color:var(--accent)}
A .pk-crumbs,A .pk-meta,A .pk-tag,A .pk-step,A .pk-glance h2,A .pk-glance dt,A .pk-pills,A .pk-btn,A thead th,A figcaption,A .pk-note{font-family:var(--l);text-transform:UPL;letter-spacing:LSL;font-weight:400}
A .pk-crumbs{font-size:11px;color:var(--muted);margin:0 0 18px}
A .pk-crumbs a{color:var(--muted);text-decoration:none}
A .pk-meta{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:11px;color:var(--muted);margin:0 0 26px}
A .pk-tag{border:1px solid var(--ink);padding:4px 10px;font-size:10.5px;color:var(--ink);border-radius:RAD}
A .pk-dek{font-family:var(--h);font-size:23px;line-height:1.4;color:var(--accent);margin:0 0 36px}
A .pk-glance{background:var(--soft);padding:26px 28px;margin:0 0 44px;border-radius:RADBOX}
A .pk-glance h2{font-family:var(--l)!important;font-size:11px!important;margin:0 0 16px!important;color:var(--ink)!important;text-transform:UPL!important}
A .pk-glance dl{display:grid;grid-template-columns:130px 1fr;gap:12px 18px;margin:0;border-top:1px solid var(--line);padding-top:16px}
A .pk-glance dt{font-size:11px;color:var(--muted);padding-top:3px}
A .pk-glance dd{margin:0;font-size:15px;line-height:1.55}
A h2{font-family:var(--h);font-weight:400;text-transform:UPH;letter-spacing:.01em;font-size:28px;line-height:1.2;color:var(--accent);margin:60px 0 18px}
A .pk-step{display:block;font-size:11px;color:var(--muted);margin:60px 0 8px}
A .pk-step + h2{margin-top:0}
A .pk-bleed{width:min(1100px,100vw);margin:40px 0 40px 50%;transform:translateX(-50%)}
A .pk-bleed img{width:100%;height:auto;max-height:660px;object-fit:cover;display:block;border-radius:RADBOX}
A figcaption{font-size:10.5px;color:var(--muted);margin-top:10px;padding:0 16px}
A .pk-card{display:grid;grid-template-columns:150px 1fr;gap:22px;align-items:center;border-top:1px solid var(--ink);border-bottom:1px solid var(--line);padding:18px 0;margin:30px 0 10px}
A .pk-card img{width:150px;height:150px;object-fit:cover;background:var(--soft);border-radius:RADBOX}
A .pk-name{font-family:var(--h);text-transform:UPH;font-size:20px;letter-spacing:.01em;color:var(--accent);margin:0 0 6px}
A .pk-why{font-size:14.5px;line-height:1.55;margin:0 0 14px}
A .pk-btn{display:inline-block;background:var(--ink);color:#fff!important;text-decoration:none;font-size:11px;padding:12px 22px;border-radius:PILL}
A .pk-pills{display:flex;flex-wrap:wrap;gap:4px 16px;margin:0 0 10px;font-size:10.5px;color:var(--muted)}
A table{width:100%;border-collapse:collapse;font-size:14.5px;margin:22px 0 10px}
A table,A thead,A tbody,A th,A td,A tr{background:transparent!important}
A mark.pk-gap{background:#fff1c2;color:#5c4400;padding:1px 4px;border-radius:3px}
A th,A td{text-align:left;padding:13px 10px 13px 0;border-bottom:1px solid var(--line);vertical-align:top;font-weight:400}
A thead th{font-size:10.5px;color:var(--muted);border-bottom:1px solid var(--ink)}
A tbody th{font-family:var(--l);font-size:11px;color:var(--muted)}
A .pk-note{font-size:10.5px;color:var(--muted);line-height:1.6}
A .pk-disclaimer{margin-top:40px;text-transform:none;letter-spacing:0;font-family:var(--b);font-size:12.5px}
A .pk-faq{border-top:1px solid var(--ink)}
A .pk-faq details{border-bottom:1px solid var(--line);padding:18px 0}
A .pk-faq summary{cursor:pointer;font-family:var(--h);text-transform:UPH;font-size:17px;color:var(--accent);list-style:none;display:flex;justify-content:space-between;gap:16px}
A .pk-faq summary::-webkit-details-marker{display:none}
A .pk-faq summary:after{content:"+";font-family:var(--l)}
A .pk-faq details[open] summary:after{content:"\\2013"}
A .pk-faq p{margin:12px 0 0;font-size:15px}
A .pk-shop{background:var(--accent);color:#fff;padding:34px;margin:60px 0 10px;display:grid;grid-template-columns:1fr 190px;gap:26px;align-items:center;border-radius:RADBOX}
A .pk-shop h2{color:#fff;margin:0 0 10px;font-size:24px}
A .pk-shop p{margin:0 0 18px;opacity:.88;font-size:15px}
A .pk-shop .pk-btn{background:#fff;color:var(--ink)!important}
A .pk-shop img{width:190px;height:190px;object-fit:cover;border-radius:RADBOX}
@media (max-width:640px){A h2{font-size:23px}A .pk-dek{font-size:20px}A .pk-glance dl{grid-template-columns:1fr}A .pk-card{grid-template-columns:96px 1fr}A .pk-card img{width:96px;height:96px}A .pk-shop{grid-template-columns:1fr}A .pk-shop img{display:none}}
'''
    rules = (rules.replace('A ', a + ' ').replace('A{', a + '{').replace('A *', a + ' *')
             .replace('INK', c['ink']).replace('ACC', c['accent']).replace('SOFT', c['soft']).replace('LINE', c['line'])
             .replace('MUTED', c['muted']).replace('HEAD', stacks['heading']).replace('BODY', stacks['body'])
             .replace('LABEL', stacks['label']).replace('UPH', up_h).replace('UPL', up_l).replace('LSL', ls_l)
             .replace('RADBOX', '%dpx' % min(r, 12)).replace('RAD', '%dpx' % min(r, 6)).replace('PILL', pill))
    if theme_title:
        rules += ('main h1,.article-template h1,article h1,h1.article-template__title,.article__title{font-family:%s!important;'
                  'font-weight:400!important;text-transform:%s!important;letter-spacing:.01em;color:%s!important}'
                  % (stacks['heading'], up_h, c['accent']))
    return '<style>%s</style>' % rules


# ---- photos ----------------------------------------------------------------------------------------

def photo_plan(body, products):
    """{'cover': url, 'sections': {i: url}, 'cards': {id: url}} using each product's own photos.
    Packshots (first image) in cards; the other images go wide, never the same one twice. Photos the owner
    picked (body['photo_overrides'], keys 'cover' / 's.<i>', 20 Oct 2026) always win."""
    by_id = {'P%d' % (i + 1): p for i, p in enumerate(products)}
    chosen = body.get('photo_overrides') or {}
    used, plan = set(v for v in chosen.values() if v), dict(cover='', sections={}, cards={})

    def lifestyle(pid=None):
        order = ([by_id[pid]] if pid in by_id else []) + [p for k, p in by_id.items() if k != pid]
        for p in order:
            for u in (p.get('images') or [])[1:]:
                if u and u not in used:
                    used.add(u)
                    return u
        return ''
    for k, p in by_id.items():
        plan['cards'][k] = p.get('image') or (p.get('images') or [''])[0]
    first = next((s.get('product_id') for s in body.get('sections') or [] if s.get('product_id')), None)
    plan['cover'] = chosen.get('cover') or lifestyle(first) or plan['cards'].get(first or 'P1', '')
    for i, s in enumerate(body.get('sections') or []):
        if chosen.get('s.%d' % i):
            plan['sections'][i] = chosen['s.%d' % i]
        elif s.get('photo'):
            u = lifestyle(s.get('product_id'))
            if u:
                plan['sections'][i] = u
    return plan


def _img(url, width):
    if not url:
        return ''
    if 'cdn.shopify.com' in url or '/cdn/shop/' in url:
        url = re.sub(r'([?&])width=\d+&?', r'\1', url).rstrip('?&')
        url += ('&' if '?' in url else '?') + 'width=%d' % width
    return url


# ---- blocks ----------------------------------------------------------------------------------------

def _price(p, symbol):
    v = p.get('price')
    if not v:
        return ''
    try:
        n = float(v)
    except (TypeError, ValueError):
        return E(str(v))
    return '%s%s' % (symbol, ('%d' % n) if n == int(n) else ('%.2f' % n))


def _card(pid, by_id, picks, plan, symbol, mark=lambda *_: ''):
    p = by_id.get(pid)
    if not p:
        return ''
    k = picks.get(pid) or {}
    labels = ''.join('<span>%s</span>' % E(x) for x in (k.get('labels') or [])[:4])
    price = _price(p, symbol)
    return ('<div class="pk-card"%s><img src="%s" alt="%s" loading="lazy"><div><p class="pk-name">%s</p>%s'
            '<p class="pk-why"%s>%s</p><a class="pk-btn" href="%s">Shop%s</a></div></div>') % (
        mark('card.%s' % pid), E(_img(plan['cards'].get(pid), 400)), E(p['title']), E(p['title']),
        ('<div class="pk-pills">%s</div>' % labels) if labels else '', mark('picks.%d.text' % k['_i']) if '_i' in k else '',
        E(k.get('text', '')), E(p['url']), (' &middot; ' + price) if price else '')


def _table(t, mark=lambda *_: '', ti=0):
    if not t or not t.get('columns') or not t.get('rows'):
        return ''
    head = ''.join('<th>%s</th>' % E(c) for c in t['columns'])
    rows = ''.join('<tr>%s</tr>' % ''.join(('<th>%s</th>' if j == 0 else '<td>%s</td>') % E(v)
                                           for j, v in enumerate(r['cells'])) for r in t['rows'])
    return '<div%s>%s<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s</div>' % (
        mark('tables.%d' % ti), ('<h2>%s</h2>' % E(t['heading'])) if t.get('heading') else '', head, rows,
        ('<p class="pk-note">%s</p>' % E(t['note'])) if t.get('note') else '')


def _para(text, attr=''):
    """A paragraph, or a short intro plus bullet points when its lines start with "- " (the owner's "Make it a list")."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    items = [l[2:].strip() for l in lines if l.startswith(('- ', '\u2022 ', '* '))]
    if len(items) >= 2:
        intro = ' '.join(l for l in lines if not l.startswith(('- ', '\u2022 ', '* ')))
        return '<div%s>%s<ul class="pk-list">%s</ul></div>' % (
            attr, ('<p>%s</p>' % E(intro)) if intro else '', ''.join('<li>%s</li>' % E(x) for x in items))
    return '<p%s>%s</p>' % (attr, E(text))


def faq_ld(faqs):
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f['question'], "acceptedAnswer": {"@type": "Answer", "text": f['answer']}}
        for f in faqs if f.get('question') and f.get('answer')]}
    return '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False).replace('</', '<\\/')


def render(body, products, style, brand='', symbol='', blog_url='', theme_title=False, read_minutes=None, marks=False):
    """The article's HTML (style + content). products: [{title, url, image, images, price}] in P1.. order.
    marks=True (Produkto's editable preview only, never the store) tags every piece with data-pk="<path>"
    (e.g. "sections.2.paragraphs.1"), photos with data-photo and gaps with data-gap, so the owner can click a
    part and change just that (content_review.editor, 20 Oct 2026)."""
    mark = (lambda path: ' data-pk="%s"' % E(path)) if marks else (lambda path: '')
    photo = (lambda slot: ' data-photo="%s"' % E(slot)) if marks else (lambda slot: '')
    by_id = {'P%d' % (i + 1): p for i, p in enumerate(products)}
    picks = {k['id']: dict(k, _i=n) for n, k in enumerate(body.get('picks') or [])}
    plan = photo_plan(body, products)
    text = [body.get('dek', '')] + [g.get('text', '') for g in body.get('glance') or []] + \
        [t for sec in body.get('sections') or [] for t in [sec.get('heading', '')] + list(sec.get('paragraphs') or [])] + \
        [f.get('question', '') + ' ' + f.get('answer', '') for f in body.get('faqs') or []]
    words = len(' '.join(text).split())
    minutes = read_minutes or max(2, round(words / 230))
    cat = body.get('category') or 'Guides'
    out = [css(style, theme_title), '<div class="%s">' % FOLD]
    out.append('<p class="pk-crumbs"><a href="%s">Journal</a> &nbsp;&rsaquo;&nbsp; %s</p>' % (E(blog_url or '/blogs/news'), E(cat)))
    out.append('<div class="pk-meta"><span class="pk-tag"%s>%s</span>%s<span>%d min read</span></div>' % (
        mark('category'), E(cat), ('<span>By %s</span>' % E(brand)) if brand else '', minutes))
    if body.get('dek'):
        out.append('<p class="pk-dek"%s>%s</p>' % (mark('dek'), E(body['dek'])))
    glance = [(n, g) for n, g in enumerate(body.get('glance') or []) if g.get('label') and g.get('text')]
    if glance:
        out.append('<div class="pk-glance"%s><h2>At a glance</h2><dl>%s</dl></div>' % (mark('glance'), ''.join(
            '<dt>%s</dt><dd%s>%s</dd>' % (E(g['label']), mark('glance.%d.text' % n), E(g['text'])) for n, g in glance)))
    tables = {}
    for ti, t in enumerate(body.get('tables') or []):
        tables.setdefault(int(t.get('after_section', -1)), []).append((ti, t))
    carded = set()
    for i, s in enumerate(body.get('sections') or []):
        out.append('<div class="pk-sec"%s>' % mark('sections.%d' % i))
        if s.get('step_label'):
            out.append('<span class="pk-step">%s</span>' % E(s['step_label']))
        out.append('<h2%s>%s</h2>' % (mark('sections.%d.heading' % i), E(s.get('heading'))))
        out += [_para(t, mark('sections.%d.paragraphs.%d' % (i, j)))
                for j, t in enumerate(s.get('paragraphs') or []) if t.strip()]
        if i in plan['sections']:
            out.append('<figure class="pk-bleed"><img src="%s" alt="%s" loading="lazy"%s></figure>' % (
                E(_img(plan['sections'][i], 1600)), E(by_id.get(s.get('product_id'), {}).get('title') or s.get('heading')),
                photo('s.%d' % i)))
        pid = s.get('product_id')
        if pid in by_id and pid not in carded:
            out.append(_card(pid, by_id, picks, plan, symbol, mark))
            carded.add(pid)
        out.append('</div>')
        out += [_table(t, mark, ti) for ti, t in tables.get(i, [])]
    out += [_table(t, mark, ti) for ti, t in tables.get(-1, [])]
    faqs = [(j, f) for j, f in enumerate(body.get('faqs') or []) if f.get('question') and f.get('answer')]
    if faqs:
        out.append('<h2>%s</h2><div class="pk-faq">%s</div>' % (E(body.get('faq_heading') or 'Questions people ask'), ''.join(
            '<details%s%s><summary>%s</summary><p%s>%s</p></details>' % (
                ' open' if n == 0 or marks else '', mark('faqs.%d' % j), E(f['question']), mark('faqs.%d.answer' % j), E(f['answer']))
            for n, (j, f) in enumerate(faqs))))
    close = body.get('closing') or {}
    cp = by_id.get(close.get('product_id'))
    if cp and close.get('heading'):
        price = _price(cp, symbol)
        out.append('<div class="pk-shop"%s><div><h2>%s</h2><p>%s</p><a class="pk-btn" href="%s">Shop %s%s</a></div>'
                   '<img src="%s" alt="%s"></div>' % (
                       mark('closing'), E(close['heading']), E(close.get('text')), E(cp['url']), E(cp['title']),
                       (' &middot; ' + price) if price else '', E(_img(plan['cards'].get(close['product_id']), 400)), E(cp['title'])))
    if body.get('disclaimer'):
        out.append('<p class="pk-note pk-disclaimer">%s</p>' % E(body['disclaimer']))
    out.append('</div>')
    if faqs:
        out.append(faq_ld([f for _, f in faqs if '[ask merchant:' not in f['answer']]))
    page = re.sub(r'\[ask merchant: ([^\]]*)\]', lambda m: '<mark class="pk-gap"%s>[ask merchant: %s]</mark>' % (
        (' data-gap="%s"' % m.group(1).replace('"', '&quot;')) if marks else '', m.group(1)), ''.join(out))
    return page, plan['cover']


def preview_page(title, html_body, cover, style, marks=False):
    """A whole page for Produkto's preview frame: the title and cover the store's theme would show, then the article."""
    c = style['colors']
    f = style['fonts']['heading']
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>body{margin:0;background:#fff;color:%s}.pk-wrap{max-width:1100px;margin:0 auto;padding:40px 20px 80px}'
            '.pk-title{font-family:%s;font-weight:400;text-transform:%s;color:%s;font-size:40px;line-height:1.15;text-align:center;'
            'max-width:760px;margin:0 auto 30px}.pk-cover{width:100%%;max-height:620px;object-fit:cover;display:block;margin:0 0 40px}'
            '.pk-col{max-width:540px;margin:0 auto}</style></head><body><div class="pk-wrap"><h1 class="pk-title"%s>%s</h1>%s'
            '<div class="pk-col">%s</div></div></body></html>') % (
        c['ink'], _stack(f['family'], 'pk-heading' if f['faces'] else None, 'Georgia,serif'),
        'uppercase' if style.get('heading_upper') else 'none', c['accent'], ' data-pk="title"' if marks else '', E(title),
        ('<img class="pk-cover" src="%s" alt=""%s>' % (E(_img(cover, 1600)), ' data-photo="cover"' if marks else '')) if cover else '',
        html_body)
