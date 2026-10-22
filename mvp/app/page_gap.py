"""Opportunities step 3: missing product details.

For a buyer question where AI named competitors and none of your products,
compare the product pages AI recommended instead with your own page for that
question, and list what theirs state and yours doesn't:

- the buyer question's own words (e.g. "exfoliation", "balance"), checked on
  the visible page text, and
- the product data a page publishes for machines (JSON-LD): review rating,
  brand, barcode (GTIN), price.

Pages are fetched with a plain request (free), the raw HTML only, no
JavaScript, which is close to what an AI crawler receives. Results are cached
in `page_facts` for 14 days; a store's pages are refreshed in a background
thread when its Opportunities page is opened. A page that blocks the request
is skipped, never guessed.

Copy rule: describe what the pages show. Never promise that adding a detail
will move visibility; nobody has shown that yet.
"""
import gzip
import io
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html import escape as E
from html.parser import HTMLParser

import db

TTL = 14 * 86400
TIMEOUT = 15
DELAY = 0.6           # seconds between requests: be polite
WINNER_PAGES = 3      # competitor pages compared per question
MAX_FETCH = 60        # pages fetched per refresh, so one run stays short
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS page_facts (url TEXT PRIMARY KEY, fetched_at REAL, '
                  'ok INTEGER, data TEXT)')


def clean(url):
    """One key per page: no tracking parameters, no fragment."""
    u = urllib.parse.urlsplit((url or '').strip())
    if u.scheme not in ('http', 'https') or not u.netloc:
        return ''
    # A product photo is not a product page (ChatGPT often links its own
    # images.openai.com thumbnails). Those are never compared.
    host = u.netloc.lower()
    if host.startswith(('images.', 'img.', 'cdn.')) or host.endswith('openai.com') or \
            re.search(r'\.(jpe?g|png|webp|gif|avif|svg)$', u.path.lower()):
        return ''
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)
            if not k.lower().startswith(('utm_', 'bvrrp', 'shippingcountry', 'srsltid', 'gclid', '_pos', '_psq', '_psid', '_ss', '_sid'))]
    return urllib.parse.urlunsplit((u.scheme, u.netloc.lower(), u.path, urllib.parse.urlencode(keep), ''))


# ------------------------------------------------------------------ fetch + parse

class _Parser(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'template', 'svg'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.jsonld, self._skip, self._ld = [], [], 0, None
        # The page's shape (18 Oct): headings in order, tables, list items. Articles copy the shape, never the words.
        self.heads, self.tables, self.items, self._h = [], 0, 0, None

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self._ld = []
        elif tag in self.SKIP:
            self._skip += 1
        elif not self._skip and tag in ('h1', 'h2', 'h3'):
            self._h = (tag, [])
        elif not self._skip and tag == 'table':
            self.tables += 1
        elif not self._skip and tag == 'li':
            self.items += 1

    def handle_endtag(self, tag):
        if tag == 'script' and self._ld is not None:
            self.jsonld.append(''.join(self._ld))
            self._ld = None
        elif tag in self.SKIP and self._skip:
            self._skip -= 1
        elif self._h and tag == self._h[0]:
            t = re.sub(r'\s+', ' ', ''.join(self._h[1])).strip()
            if t and len(self.heads) < 30:
                self.heads.append('%s %s' % (tag, t[:120]))
            self._h = None

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        elif not self._skip:
            self.text.append(data)
            if self._h:
                self._h[1].append(data)


def _flatten(data):
    out = []
    if isinstance(data, list):
        for x in data:
            out += _flatten(x)
    elif isinstance(data, dict):
        out.append(data)
        for v in data.values():
            if isinstance(v, (dict, list)):
                out += _flatten(v)
    return out


def _product(objects):
    for o in objects:
        t = o.get('@type')
        types = [str(x).lower() for x in (t if isinstance(t, list) else [t])]
        if 'product' in types or 'productgroup' in types:
            return o
    return None


# Markers of the review apps Shopify stores use, in the page's HTML.
REVIEW_APPS = ('jdgm', 'judge.me', 'yotpo', 'okendo', 'stamped.io', 'stamped-', 'loox', 'reviews.io', 'junip',
               'spr-review', 'shopify-product-reviews', 'trustpilot', 'rivyo', 'alireviews', 'ali-reviews', 'reviewsio',
               'fera.ai', 'kudobuzz', 'opinew', 'growave', 'air-reviews', 'klaviyo-reviews', 'kl-reviews')
QA_HEADING = re.compile(r'\b(faqs?|q\s*&(amp;)?\s*a|questions|frequently asked)\b', re.I)


def parse(html_text):
    """Visible text plus the facts a page publishes in its Product JSON-LD."""
    p = _Parser()
    try:
        p.feed(html_text)
    except Exception:                                   # noqa: BLE001 - malformed markup is common
        pass
    objects = []
    for block in p.jsonld:
        try:
            objects += _flatten(json.loads(block.strip()))
        except ValueError:
            continue
    prod = _product(objects) or {}
    # Shopify themes that publish a ProductGroup put price, stock and barcode on each variant.
    variant = next((v for v in (prod.get('hasVariant') if isinstance(prod.get('hasVariant'), list) else [])
                    if isinstance(v, dict)), {})
    rating = prod.get('aggregateRating') or {}
    if isinstance(rating, list):
        rating = rating[0] if rating else {}
    offers = prod.get('offers') or variant.get('offers') or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    brand = prod.get('brand')
    if isinstance(brand, dict):
        brand = brand.get('name')
    text = re.sub(r'\s+', ' ', ' '.join(p.text)).strip()
    m = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.S | re.I)
    title = re.sub(r'\s+', ' ', __import__('html').unescape(m.group(1))).strip()[:200] if m else ''
    types = {t for o in objects if isinstance(o, dict) for t in ([o.get('@type')] if isinstance(o.get('@type'), str) else (o.get('@type') or []))}
    low = html_text.lower()
    return dict(
        title=title,
        text=text[:60000],
        # Customer reviews shown on the page: a review app's widget, or review data (19 Oct 2026, Opportunities).
        review_app=any(k in low for k in REVIEW_APPS),
        # A questions section: FAQPage data, or a heading like "FAQ" / "Q&A" with questions under it (a footer
        # "FAQ" link alone doesn't count).
        qa='FAQPage' in types or 'QAPage' in types or (any(QA_HEADING.search(h) for h in p.heads) and text.count('?') >= 3),
        product=bool(prod),
        rating=bool(isinstance(rating, dict) and (rating.get('ratingValue') or rating.get('reviewCount'))),
        reviews=_int(rating.get('reviewCount') or rating.get('ratingCount')) if isinstance(rating, dict) else 0,
        brand=bool(brand),
        gtin=any(o.get(k) for o in (prod, variant) for k in ('gtin', 'gtin8', 'gtin12', 'gtin13', 'gtin14', 'mpn')),
        price=bool(isinstance(offers, dict) and (offers.get('price') or offers.get('lowPrice'))),
        availability=bool(isinstance(offers, dict) and offers.get('availability')),
        shape=dict(headings=p.heads, tables=p.tables, list_items=p.items, words=len(text.split())),
    )


def _int(v):
    try:
        return int(float(str(v).replace(',', '')))
    except (TypeError, ValueError):
        return 0


def fetch(url, country=''):
    """country: a two-letter code. Shopify stores then show that market's prices; without it they guess from
    our server's location (Germany), so a US store showed euros (5strands.com, 21 Oct 2026)."""
    headers = {'User-Agent': UA, 'Accept': 'text/html,*/*;q=0.8', 'Accept-Encoding': 'gzip', 'Accept-Language': 'en'}
    if re.fullmatch(r'[A-Z]{2}', country or ''):
        headers['Cookie'] = 'localization=%s' % country
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(3_000_000)
        if resp.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        return raw.decode(resp.headers.get_content_charset() or 'utf-8', errors='replace')


def facts(url):
    """Cached facts for a page, or None if never fetched or it blocked us."""
    row = db.one('SELECT ok,data FROM page_facts WHERE url=?', (clean(url),))
    return json.loads(row['data']) if row and row['ok'] else None


def store(url, ok, data):
    db.write('INSERT INTO page_facts(url,fetched_at,ok,data) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET '
             'fetched_at=excluded.fetched_at, ok=excluded.ok, data=excluded.data',
             (clean(url), time.time(), 1 if ok else 0, json.dumps(data)))


def _due(url):
    row = db.one('SELECT fetched_at FROM page_facts WHERE url=?', (clean(url),))
    return not row or time.time() - (row['fetched_at'] or 0) > TTL


def browser_fetch(url):
    """A page that blocked the plain request, through Apify's RAG Web Browser (paid, see config)."""
    import apify_answers
    items = apify_answers._request('POST', '/acts/apify~rag-web-browser/run-sync-get-dataset-items',
                                   {'query': url, 'maxResults': 1, 'outputFormats': ['html']}, timeout=120)
    html_text = (items[0] if items else {}).get('html') or ''
    if not html_text:
        raise ValueError('browser returned no page')
    return html_text


def fetch_all(urls, limit=MAX_FETCH, delay=DELAY):
    """Fetch the pages not yet cached (or older than TTL). Returns how many were fetched.

    A page that blocks the plain request (or sends back an empty shell) is
    retried through the paid browser when config.PAGE_BROWSER is on."""
    import config
    init()
    n, paid = 0, 0
    for url in urls:
        if n >= limit:
            break
        url = clean(url)
        if not url or not _due(url):
            continue
        try:
            f = parse(fetch(url))
            if len(f['text']) < 1500 and not f['product']:
                raise ValueError('empty shell: the page needs a browser')   # Boots sends ~700 characters
            store(url, True, f)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            if config.PAGE_BROWSER and paid < config.PAGE_BROWSER_MAX:
                paid += 1
                try:
                    fb = parse(browser_fetch(url))
                    if len(fb['text']) < 1500 and not fb['product']:
                        raise ValueError('blocked even in a browser: %s' % fb.get('title', '')[:60])
                    store(url, True, fb)
                    n += 1
                    continue
                except Exception as exc2:                       # noqa: BLE001
                    exc = exc2
            store(url, False, dict(error=str(exc)[:200]))
        n += 1
        time.sleep(delay)
    return n


# ------------------------------------------------------------------ comparison

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("""a an and are as at be best but by can do does for from good have how i if in is it its
 my of on or should that the their them there this to use using want what whats when where which while who
 why will with without you your get choose buy keep keeps all every day daily me im more most than very
 better under over one two three like something product products need help great really also""".split())


def _norm(w):
    # UK and US spellings count as the same word: moisturiser = moisturizer.
    # Word families count as one: cleanse = cleanser = cleansing.
    w = w.replace('ise', 'ize').replace('isi', 'izi').replace('our', 'or')
    w = w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith('ss') else w
    return w[:6] if len(w) > 6 else w


def words(text):
    return {_norm(w) for w in _WORD.findall((text or '').lower().replace("’", "'").replace("'s", ''))
            if len(w) > 2 and w not in _STOP and not w.isdigit()}


def question_words(q):
    """The buyer question's content words, in order, once each."""
    out = []
    for w in _WORD.findall(q.lower().replace("’", "'").replace("'s", '')):
        if len(w) > 2 and w not in _STOP and not w.isdigit() and _norm(w) not in [_norm(x) for x in out]:
            out.append(w)
    return out


DATA_LABELS = (('rating', 'a review rating'), ('brand', 'the brand name'),
               ('gtin', 'a barcode (GTIN)'), ('price', 'a price'))


def gaps(question, own_text, own_data, winners):
    """What most winning pages state that yours doesn't.

    `winners` is a list of fetched page facts. One page is too thin to call a
    pattern, so it takes two or more, and a word or data field counts as a gap
    when at least two of them have it."""
    if len(winners) < 2:
        return [], []
    need = 2
    own = words(own_text)
    missing = []
    for w in question_words(question):
        n = _norm(w)
        if n not in own and sum(1 for f in winners if n in words(f['text'])) >= need:
            missing.append(w)
    data = [label for key, label in DATA_LABELS
            if not (own_data or {}).get(key) and sum(1 for f in winners if f.get(key)) >= need]
    return missing, data


# ------------------------------------------------------------------ finding a competitor's page

def _title_words(s):
    return {w for w in _WORD.findall((s or '').lower()) if len(w) > 2}


def lookup_key(site, name):
    return 'find:%s|%s' % (site, ' '.join(sorted(_title_words(name))))


def lookup_cached(site, name):
    """The product page found earlier for a competitor product, or ''."""
    row = db.one('SELECT data FROM page_facts WHERE url=? AND ok=1', (lookup_key(site, name),))
    return json.loads(row['data']).get('url', '') if row else ''


def lookup(site, name):
    """Find a competitor product's own page through its store's Shopify search.

    ChatGPT often names a product without linking it. Most DTC brands run on
    Shopify, whose /search/suggest.json answers without a browser. Only a close
    title match counts (half the words shared), so a different product from
    the same brand is never compared."""
    key = lookup_key(site, name)
    if not site or not _due(key):
        return lookup_cached(site, name)
    want = _title_words(name)
    found = ''
    q = urllib.parse.urlencode({'q': name, 'resources[type]': 'product', 'resources[limit]': 3})
    for host in [site] + ([site[:-4] + '.co'] if site.endswith('.com') else []):
        try:
            items = json.loads(fetch('https://%s/search/suggest.json?%s' % (host, q)))['resources']['results']['products']
        except Exception:                               # noqa: BLE001 - not Shopify, or blocked
            continue
        for it in items:
            got = _title_words(it.get('title'))
            if want and got and len(want & got) / len(want | got) >= .5 and it.get('url'):
                found = clean(urllib.parse.urljoin('https://%s/' % host, it['url']))
                break
        break
    db.write('INSERT INTO page_facts(url,fetched_at,ok,data) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET '
             'fetched_at=excluded.fetched_at, ok=excluded.ok, data=excluded.data',
             (key, time.time(), 1 if found else 0, json.dumps(dict(url=found))))
    return found


def names_on_page(facts_, names):
    """Which of these brand names the page's visible text mentions."""
    text = ' %s ' % re.sub(r'[^a-z0-9]+', ' ', (facts_ or {}).get('text', '').lower())
    found = []
    for n in names:
        key = re.sub(r'[^a-z0-9]+', ' ', (n or '').lower()).strip()
        if len(key) > 2 and ' %s ' % key in text:
            found.append(n)
    return found


# ------------------------------------------------------------------ AI: why a page picks competitors

EXPLAIN_SCHEMA = {"type": "object", "additionalProperties": False,
                  "properties": {"why": {"type": "string"}}, "required": ["why"]}
EXPLAIN_RULES = ("You read one web page that an AI assistant cited when it recommended these competitor "
                 "products instead of the merchant's. In ONE plain sentence of at most 30 words, say what the page "
                 "is (e.g. a ranked list, a review, a retailer listing) and what it says about the competitors that "
                 "made them the pick. Only use what the page says. Never advise, never promise results.")


def explained(url):
    row = db.one('SELECT data FROM page_facts WHERE url=? AND ok=1', ('why:' + clean(url),))
    return json.loads(row['data']).get('why', '') if row else ''


def explain(url, competitors):
    """One cached AI sentence per page. Paid, so only called when config.PAGE_EXPLAIN is on."""
    import config
    import llm
    key = 'why:' + clean(url)
    if not config.PAGE_EXPLAIN or db.one('SELECT 1 FROM page_facts WHERE url=?', (key,)):
        return explained(url)
    f = facts(url)
    if not f:
        return ''
    try:
        why = llm.json_call(EXPLAIN_RULES, 'Competitors: %s\nPage title: %s\nPage text: %s'
                            % (', '.join(competitors), f.get('title', ''), f['text'][:12000]),
                            'page_reason', EXPLAIN_SCHEMA, attempts=2)['why'].strip()
        ok = bool(why)
    except Exception:                                   # noqa: BLE001 - no balance, rate limit: skip
        why, ok = '', False
    db.write('INSERT INTO page_facts(url,fetched_at,ok,data) VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET '
             'fetched_at=excluded.fetched_at, ok=excluded.ok, data=excluded.data',
             (key, time.time(), 1 if ok else 0, json.dumps(dict(why=why))))
    return why
