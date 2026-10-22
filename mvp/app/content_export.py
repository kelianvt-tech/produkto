"""Export: approved drafts as files the merchant brings into Shopify.

Day 12 of mvp/content-agent/PLAN.md. Nothing is written to the store (no store
access in v1); the merchant downloads one zip from the Calendar:

  products.csv    Shopify's product CSV, only Handle, Title and Body (HTML).
                  Imported with "Overwrite products with matching handles".
                  One row per product: its page fix and its FAQ are merged,
                  and an FAQ alone is added below the product's ORIGINAL
                  description HTML, so the merchant's formatting is kept.
  pages/*.html    comparison pages and buying guides, one file each, to paste
                  into Online Store > Pages or Blog posts.
  README.txt      what each file is and how to import it, in plain words.

A draft that still holds an "[ask merchant: ...]" gap is never exported (it
can't be approved either). Each export is recorded on the drafts it contains.

Tested on a Shopify dev store (day 13, 15 Oct 2026): an overwrite import of
Handle, Title, Body (HTML) + the option columns keeps prices, compare-at prices,
SKUs, stock, images, vendor, type and tags; the FAQPage <script> survives in the
body; products not in the file are untouched. Without the option columns
Shopify rejects the file. (Its import PREVIEW shows $0.00 and no images; that
is the file's contents, not the result.)
"""
import csv
import io
import json
import re
import time
import zipfile

import db
import storetime

PRODUCT_TYPES = ('product_fix', 'faq')
PAGE_TYPES = ('comparison', 'guide')


def init():
    with db.conn() as c:
        cols = [r[1] for r in c.execute('PRAGMA table_info(content_drafts)')]
        if 'exported_at' not in cols:
            c.execute('ALTER TABLE content_drafts ADD COLUMN exported_at REAL')


def ready(domain, include_exported=False):
    """Approved drafts waiting to go to the store, oldest planned first, with their latest body."""
    import content_agent
    import content_review
    init()
    rows = db.all_("SELECT * FROM content_drafts WHERE store_domain=? AND status IN ('approved','scheduled')"
                   + ('' if include_exported else ' AND exported_at IS NULL')
                   + ' ORDER BY COALESCE(planned_at, approved_at)', (domain,))
    out = []
    for r in rows:
        _, body, _ = content_review.load(r['id'], domain)
        if not body or content_agent.placeholders(body):
            continue
        try:
            content_review.rebuild(body, r['draft_type'])
        except (KeyError, TypeError):            # a draft missing its text can't be exported
            continue
        out.append((r, body))
    return out


def _original_body(domain, handle):
    row = db.one('SELECT raw_json FROM products WHERE store_domain=? AND handle=?', (domain, handle))
    try:
        return json.loads(row['raw_json']).get('body_html') or '' if row else ''
    except (TypeError, ValueError):
        return ''


def options(domain, handle):
    """[(option name, [value per variant])] as the store has them, from its public product JSON.

    Shopify refuses an overwrite import that leaves out the option columns ("Product options input is
    required when updating variants", found on the day-13 test store), so every variant's option
    values are copied in unchanged. None when the product can't be read."""
    import page_gap
    try:
        raw = page_gap.fetch('https://%s/products/%s.json' % (domain, handle))
        data = json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw)['product']
    except Exception:                                   # noqa: BLE001 - offline, removed, password page
        return None
    names = [o['name'] for o in data.get('options') or []][:3]
    variants = data.get('variants') or []
    if not names or not variants:
        return None
    return [(n, [v.get('option%d' % (i + 1)) or '' for v in variants]) for i, n in enumerate(names)]


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or 'page').lower()).strip('-')[:60] or 'page'


def build(domain, include_exported=False):
    """(zip bytes, draft ids in it, counts) or (None, [], {}) when nothing is ready."""
    items = ready(domain, include_exported)
    if not items:
        return None, [], {}
    products = {}                               # handle -> dict(title, body, fix, faq)
    pages = []
    for r, body in items:
        if r['draft_type'] in PRODUCT_TYPES:
            handle = (body.get('product') or {}).get('handle')
            if not handle:
                continue
            p = products.setdefault(handle, dict(title=None, fix=None, faq=None))
            if r['draft_type'] == 'product_fix':
                p['title'], p['fix'] = body.get('title'), body.get('html') or body.get('description_html', '')
            else:
                p['faq'] = body.get('html', '')
        elif r['draft_type'] in PAGE_TYPES:
            pages.append((r, body))

    csv_buf = io.StringIO()
    w = csv.writer(csv_buf)
    w.writerow(['Handle', 'Title', 'Body (HTML)', 'Option1 Name', 'Option1 Value', 'Option2 Name', 'Option2 Value',
                'Option3 Name', 'Option3 Value'])
    skipped = []
    for handle, p in products.items():
        opts = options(domain, handle)
        if not opts:
            skipped.append(handle)
            continue
        main = p['fix'] if p['fix'] is not None else _original_body(domain, handle)
        faq = ('\n<h2>Questions and answers</h2>\n' + p['faq']) if p['faq'] else ''
        title = p['title'] or (db.one('SELECT title FROM products WHERE store_domain=? AND handle=?',
                                      (domain, handle)) or {'title': ''})['title']
        body = re.sub(r' class="cr-[a-z-]+"', '', main + faq)        # no Produkto styling in the store
        for i in range(len(opts[0][1])):
            cells = []
            for k in range(3):
                name, values = opts[k] if k < len(opts) else ('', [])
                cells += [name if i == 0 else '', values[i] if i < len(values) else '']
            w.writerow(([handle, title, body] if i == 0 else [handle, '', '']) + cells)
    written = {h: p for h, p in products.items() if h not in skipped}

    tz = storetime.zone(domain)
    stamp = storetime.label(time.time(), tz, '%Y-%m-%d')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        if written:
            z.writestr('products.csv', csv_buf.getvalue())
        names = set()
        for r, body in pages:
            title = body.get('title') or r['title'] or 'Page'
            name = _slug(title)
            while name in names:
                name += '-2'
            names.add(name)
            kind = 'Comparison page' if r['draft_type'] == 'comparison' else 'Buying guide (blog post)'
            z.writestr('pages/%s.html' % name, '<!-- %s -->\n<h1>%s</h1>\n%s\n' % (
                kind, title.replace('<', '&lt;'), body.get('html', '')))
        z.writestr('README.txt', _readme(domain, written, pages, stamp, skipped))
    counts = dict(products=len(written), pages=len(pages), drafts=len(items), skipped=len(skipped))
    ids = [r['id'] for r, b in items
           if not (r['draft_type'] in PRODUCT_TYPES and (b.get('product') or {}).get('handle') in skipped)]
    return buf.getvalue(), ids, counts


def _readme(domain, products, pages, stamp, skipped=()):
    lines = ['Produkto export for %s, %s' % (domain, stamp), '']
    if skipped:
        lines += ['Not included: %s. We couldn\'t read %s from your store just now; download again later.'
                  % (', '.join(skipped), 'its sizes and options' if len(skipped) == 1 else 'their sizes and options'), '']
    if products:
        lines += ['products.csv: changes to %d product page%s.' % (len(products), '' if len(products) == 1 else 's'),
                  'In Shopify: Products > Import > choose products.csv > tick "Overwrite products with matching handles" > Import.',
                  'Only the title and description of these products change. The file repeats each product\'s options '
                  'exactly as they are, because Shopify asks for them. Prices, images, SKUs and stock are not in the file '
                  'and stay as they are (tested on a Shopify store, 15 Oct 2026).',
                  '']
    if pages:
        lines += ['pages/: %d new page%s.' % (len(pages), '' if len(pages) == 1 else 's'),
                  'Comparison pages: Online Store > Pages > Add page > show HTML (the <> button) > paste the file.',
                  'Buying guides: Online Store > Blog posts > Add blog post > show HTML > paste the file.', '']
    lines += ['Everything here was approved by you in Produkto. Nothing was changed on your store.']
    return '\n'.join(lines) + '\n'


def mark(ids):
    init()
    now = time.time()
    with db.conn() as c:
        c.executemany('UPDATE content_drafts SET exported_at=? WHERE id=?', [(now, i) for i in ids])


def bar(domain):
    """The Calendar's export bar: what is ready and the download link."""
    import urllib.parse
    from html import escape as E
    n_new = len(ready(domain))
    n_all = len(ready(domain, include_exported=True))
    if not n_all:
        return ''
    link = '/content/export?' + urllib.parse.urlencode(dict(d=domain))
    if n_new:
        text = '%d approved draft%s ready for your store.' % (n_new, '' if n_new == 1 else 's')
        btn = '<a class="ca-btn ca-primary" href="%s">Download for Shopify</a>' % E(link)
    else:
        text = 'Everything approved has been downloaded.'
        btn = '<a class="ca-btn" href="%s">Download again</a>' % E(link + '&all=1')
    return '<div class="ex-bar"><span>%s</span>%s</div>' % (text, btn)


CSS = """
.ex-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 14px;margin:0 0 12px;border:1px solid #e6e9ef;border-radius:10px;background:#ffffff;font-size:14px;color:#1a2436}
"""
