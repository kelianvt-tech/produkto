"""Catalog facts: everything a store states about each product, in one record.

This is the ONLY source of product facts the content agent may use (day 2 of
mvp/content-agent/PLAN.md). If a fact is not in here, a draft must not state
it - it becomes a question for the merchant instead.

Two free, public sources per product:
  * the store's /products.json - title, description, type, tags, options,
    and every variant's price, SKU, barcode, weight;
  * the product page itself - its Product JSON-LD (brand, GTIN, rating,
    review count, availability, additionalProperty specs).

Not available without store access: metafields. Shopify keeps them out of the
public endpoints, so they arrive with the Shopify connection in phase 3.

Every fact carries its source ('catalog' or 'page') so a draft can show where
each claim came from. Records are cached in `catalog_facts` and rebuilt when
older than MAX_AGE.

Run by hand:  python3 catalog_facts.py clubhouseskin.com
"""
import html
import json
import re
import sys
import time
import urllib.error

import catalog
import db
import page_gap

MAX_AGE = 7 * 86400      # rebuild a store's facts weekly
PAGE_DELAY = 0.6         # seconds between product-page requests: be polite
MAX_PAGES = 400          # product pages fetched per build; the rest keep catalog facts only

# "Material: solid oak", "Dimensions - 220 x 95 cm": a short label, then a value.
_SPEC = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 /&()\'-]{1,32}?)\s*[:–—-]\s+(\S.{0,160}?)\s*$')
_BREAKS = re.compile(r'<\s*(?:br|/p|/li|/h[1-6]|/div|/tr)\s*/?\s*>', re.I)
_TAGS = re.compile(r'<[^>]+>')


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS catalog_facts (store_domain TEXT NOT NULL, handle TEXT NOT NULL, '
                  'built_at REAL, data TEXT, PRIMARY KEY (store_domain, handle))')


# --- reading ------------------------------------------------------------------

def text_lines(body_html):
    """Product description HTML -> its visible lines, in order."""
    raw = _BREAKS.sub('\n', body_html or '')
    raw = html.unescape(_TAGS.sub(' ', raw))
    return [re.sub(r'\s+', ' ', l).strip() for l in raw.split('\n') if l.strip()]


def spec_lines(lines):
    """'Label: value' pairs written into a description."""
    out = []
    for line in lines:
        m = _SPEC.match(line)
        if m and len(line) <= 200:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _variant(v):
    return dict(title=v.get('title') or '', price=v.get('price'), compare_at=v.get('compare_at_price'),
                sku=v.get('sku') or '', barcode=v.get('barcode') or '',
                weight=v.get('grams') if v.get('grams') else None, available=v.get('available'))


def page_data(html_text):
    """The facts a product page publishes in its Product JSON-LD."""
    p = page_gap._Parser()
    try:
        p.feed(html_text)
    except Exception:                                   # noqa: BLE001 - malformed markup is common
        pass
    objects = []
    for block in p.jsonld:
        try:
            objects += page_gap._flatten(json.loads(block.strip()))
        except ValueError:
            continue
    prod = page_gap._product(objects) or {}
    brand = prod.get('brand')
    if isinstance(brand, dict):
        brand = brand.get('name')
    rating = prod.get('aggregateRating') or {}
    if isinstance(rating, list):
        rating = rating[0] if rating else {}
    offers = prod.get('offers') or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    props = prod.get('additionalProperty') or []
    if isinstance(props, dict):
        props = [props]
    gtin = next((str(prod[k]) for k in ('gtin', 'gtin13', 'gtin12', 'gtin14', 'gtin8') if prod.get(k)), '')
    return dict(
        has_product_markup=bool(prod),
        brand=str(brand or ''),
        gtin=gtin,
        mpn=str(prod.get('mpn') or ''),
        rating=str(rating.get('ratingValue') or '') if isinstance(rating, dict) else '',
        reviews=page_gap._int(rating.get('reviewCount') or rating.get('ratingCount')) if isinstance(rating, dict) else 0,
        availability=str(offers.get('availability') or '').rsplit('/', 1)[-1] if isinstance(offers, dict) else '',
        properties=[(str(x.get('name')), str(x.get('value'))) for x in props
                    if isinstance(x, dict) and x.get('name') and x.get('value') not in (None, '')],
        text=re.sub(r'\s+', ' ', ' '.join(p.text)).strip()[:20000],
    )


def record(product, domain, currency='', category='', page=None):
    """One product from /products.json (+ its page, if read) -> its facts record."""
    variants = [_variant(v) for v in product.get('variants') or []]
    options = {o.get('name'): [x for x in (o.get('values') or []) if x != 'Default Title']
               for o in product.get('options') or [] if o.get('name') and o.get('name') != 'Title'}
    prices = sorted(float(v['price']) for v in variants if _num(v['price']))
    lines = text_lines(product.get('body_html'))
    tags = product.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    facts = []

    def add(label, value, source):
        if value not in (None, '', [], 0):
            facts.append(dict(label=label, value=str(value), source=source))

    add('Title', product.get('title'), 'catalog')
    add('Brand', product.get('vendor'), 'catalog')
    add('Product type', product.get('product_type'), 'catalog')
    add('Category', category, 'catalog')
    for name, values in options.items():
        add(name, ', '.join(values), 'catalog')
    if prices:
        lo, hi = prices[0], prices[-1]
        add('Price', ('%s %.2f' % (currency, lo) if lo == hi else '%s %.2f-%.2f' % (currency, lo, hi)).strip(), 'catalog')
    weights = sorted({v['weight'] for v in variants if v['weight']})
    if len(weights) == 1:
        add('Shipping weight', '%g g' % weights[0], 'catalog')   # Shopify's variant grams: package weight, not product size
    barcodes = [v['barcode'] for v in variants if v['barcode']]
    add('Barcode (GTIN)', ', '.join(barcodes[:5]), 'catalog')
    for label, value in spec_lines(lines):
        add(label, value, 'catalog')
    if page:
        add('Brand (page markup)', page.get('brand'), 'page')
        add('GTIN (page markup)', page.get('gtin'), 'page')
        add('Rating', page.get('rating'), 'page')
        add('Review count', page.get('reviews'), 'page')
        add('Availability', page.get('availability'), 'page')
        for label, value in page.get('properties') or []:
            add(label, value, 'page')
    images = product.get('images') or []
    return dict(
        handle=product.get('handle'),
        shopify_id=product.get('id'),
        title=(product.get('title') or '').strip(),
        url='https://%s/products/%s' % (domain, product.get('handle')),
        image=(images[0].get('src') if images else '') or '',
        images=[i.get('src') for i in images if i.get('src')][:8],   # articles use the lifestyle shots (19 Oct)
        vendor=product.get('vendor') or '',
        product_type=product.get('product_type') or '',
        category=category,
        tags=tags,
        options=options,
        variants=variants,
        description=lines,
        page=page or None,
        facts=facts,
        missing_from_store=['metafields (need store access)'],
    )


def _num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# --- building -----------------------------------------------------------------

def _products(domain):
    out, page = [], 1
    while page <= catalog.MAX_PAGES:
        status, body = catalog._get('https://%s/products.json?limit=%d&page=%d' % (domain, catalog.PAGE_LIMIT, page))
        batch = json.loads(body).get('products', []) if status == 200 else []
        out += batch
        if len(batch) < catalog.PAGE_LIMIT:
            break
        page += 1
    return out


def build(domain, pages=True, log=None):
    """Read the store now and save every product's record. Returns the records."""
    init()
    meta = catalog.store_meta(domain)
    stored = {r['handle']: json.loads(r['raw_json'] or '{}').get('category', '')
              for r in db.all_('SELECT handle, raw_json FROM products WHERE store_domain=?', (domain,))}
    out = []
    for i, p in enumerate(_products(domain)):
        page = None
        if pages and i < MAX_PAGES:
            url = 'https://%s/products/%s' % (domain, p.get('handle'))
            try:
                page = page_data(page_gap.fetch(url))
            except (urllib.error.URLError, OSError, ValueError) as e:
                page = dict(error=str(e)[:200])
            time.sleep(PAGE_DELAY)
        rec = record(p, domain, meta.get('currency', ''), stored.get(p.get('handle'), ''), page)
        out.append(rec)
        if log:
            log('%s: %d facts' % (rec['title'], len(rec['facts'])))
    now = time.time()
    with db.conn() as c:
        c.execute('DELETE FROM catalog_facts WHERE store_domain=?', (domain,))
        c.executemany('INSERT INTO catalog_facts VALUES (?,?,?,?)',
                      [(domain, r['handle'], now, json.dumps(r)) for r in out])
    return out


def get(domain):
    """Cached records for a store, oldest-first build time; [] if never built."""
    init()
    return [json.loads(r['data']) for r in db.all_(
        'SELECT data FROM catalog_facts WHERE store_domain=? ORDER BY handle', (domain,))]


def stale(domain):
    init()
    row = db.one('SELECT MIN(built_at) t FROM catalog_facts WHERE store_domain=?', (domain,))
    return not row or not row['t'] or time.time() - row['t'] > MAX_AGE


if __name__ == '__main__':
    recs = build(sys.argv[1], log=print)
    print('%d products, %d facts' % (len(recs), sum(len(r['facts']) for r in recs)))
