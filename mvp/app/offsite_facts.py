"""Off-site facts: what pages outside the store say about its products. Free version.

Kelian's idea, 16 Oct 2026: when a store's own pages leave a fact out, the
brand has often stated it elsewhere (a marketplace or retailer listing, a
press or review article). This reads only pages the app already knows about,
so there is no search fee:

  * links AI attached when it named one of the store's own products, and
  * pages AI cited when answering the store's buyer questions,

over the last 30 days of answers, minus the store's own site. Pages are
fetched with a plain request (free, cached 14 days by page_gap). A page is
only used for a product when it names both the brand and that product, so a
same-named brand or a different product can't slip in.

Nothing here becomes a fact by itself. content_setup.find_missing shows what
these pages say as a suggestion with its source link, and the merchant has to
click "Use this" before it counts.

Paid step (16 Oct, Kelian approved): for a product the free pages say nothing
about, ONE Google search ("Brand" "Product") through Apify's Google Search
Scraper, then the result pages are read free like the rest. Bounded three ways
so cost follows the plan, not the catalog size (a Growth store: ~$0.25/month):
  * only products setup asks about (the ones in open Opportunities first);
  * each product searched once, re-searched only after SEARCH_TTL;
  * at most the store's monthly page-fix allowance in searches (50 if
    unlimited), counted in `offsite_searches`, which also records what each
    Apify run actually cost. Off with PRODUKTO_OFFSITE_SEARCH=0.
"""
import json
import re
import time
import urllib.parse
from collections import Counter

import db
import page_gap

MAX_PAGES = 15          # off-site pages read per store
SEARCH_TTL = 90 * 86400  # a product is searched again after this long
SEARCH_CAP_UNLIMITED = 50
RESULTS_READ = 3        # result pages read per searched product
ACTOR = 'apify~google-search-scraper'
SKIP_HOSTS = ('instagram.com', 'facebook.com', 'tiktok.com', 'youtube.com', 'pinterest.com', 'x.com',
              'twitter.com', 'linkedin.com', 'reddit.com')   # need a login or a browser to read
EXCERPT = 1200          # characters kept after each mention of a product
PER_PRODUCT = 3         # pages passed to the model per product


def _host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith('www.') else h


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '').replace('’', "'").lower()).strip()


def candidate_urls(domain):
    """Off-store pages AI linked for this store's products or cited for its questions, most used first."""
    import briefs
    import evidence
    import opportunities
    import period
    import storetime
    ps = db.get_prompt_set(domain)
    if not ps:
        return []
    _, _, start, end = period.bounds(opportunities.WINDOW, tz=storetime.zone(domain))
    scans = period.done_scans(ps['id'], start, end)
    if not scans:
        return []
    p = evidence.product_context(ps)
    _, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    own_links = Counter(page_gap.clean(m['url']) for m in mentions
                        if m['url'] and (m['is_theirs'] or evidence.own(m, p)))
    _, _, _, cites = briefs._evidence(domain)
    cited = Counter()
    for c in cites.values():
        cited.update(c)
    import third_party
    found = Counter(third_party.offsite_urls(domain))   # retailer/review pages from the admin pull (free to read)
    own = _host('https://' + domain)
    out = []
    for counter in (own_links, cited, found):          # links on the store's own products first: most likely about them
        for u, _ in counter.most_common():
            h = _host(u) if u else ''
            if u and h != own and not h.endswith('.' + own) and u not in out:
                out.append(u)
    return out[:MAX_PAGES]


def _excerpts(text, title):
    """The text after the places the page names the product, best two first. Menus and breadcrumbs name it
    too, so each window is scored by how many full sentences it holds: a product description has them."""
    low, t = _norm(text), _norm(title)
    starts, i = [], low.find(t)
    while i >= 0:
        if not starts or i - starts[-1] > EXCERPT // 2:
            starts.append(i)
        i = low.find(t, i + len(t))
    windows = [text[max(0, i - 100): i + EXCERPT] for i in starts]
    windows.sort(key=lambda w: -len(re.findall(r'[a-z][.!?] [A-Z]', w)))
    return ' … '.join(windows[:2])


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS offsite_searches (store_domain TEXT NOT NULL, handle TEXT NOT NULL, '
                  'query TEXT, results TEXT, cost_usd REAL, at REAL, PRIMARY KEY (store_domain, handle))')


def enabled():
    import config
    return config.env('PRODUKTO_OFFSITE_SEARCH') != '0'


def searches_left(domain):
    """Searches still allowed this month: the store's page-fix allowance minus searches already run."""
    import content_plan
    init()
    cap = content_plan.allowance(domain, 'fixes')
    cap = SEARCH_CAP_UNLIMITED if cap is None else cap
    start, end = content_plan.month_bounds(domain)
    n = db.one('SELECT COUNT(*) n FROM offsite_searches WHERE store_domain=? AND at>=? AND at<?',
               (domain, start, end))['n']
    return max(0, cap - n)


def _due(domain, handle):
    row = db.one('SELECT at FROM offsite_searches WHERE store_domain=? AND handle=?', (domain, handle))
    return not row or time.time() - (row['at'] or 0) > SEARCH_TTL


def _apify_search(queries, country):
    """[(query, [url])] from one Apify run, and what the run cost in dollars (None if Apify didn't say)."""
    import apify_answers
    run = apify_answers._request('POST', '/acts/%s/runs?waitForFinish=240' % ACTOR, dict(
        queries='\n'.join(queries), maxPagesPerQuery=1, resultsPerPage=10, countryCode=country,
        mobileResults=False, saveHtml=False, saveHtmlToKeyValueStore=False, includeIcons=False), timeout=300)['data']
    for _ in range(20):
        if run.get('status') in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'):
            break
        time.sleep(10)
        run = apify_answers._request('GET', '/actor-runs/%s' % run['id'])['data']
    if run.get('status') != 'SUCCEEDED':
        raise RuntimeError('Google search run %s' % run.get('status'))
    items = apify_answers._request('GET', '/datasets/%s/items?clean=true' % run['defaultDatasetId'], timeout=120)
    out = []
    for it in items:
        term = ((it.get('searchQuery') or {}).get('term') or '').strip()
        out.append((term, [r['url'] for r in it.get('organicResults') or [] if r.get('url')]))
    return out, run.get('usageTotalUsd')


def search(domain, products, brand):
    """Search for products not searched recently, within this month's cap. Returns {handle: [url]} for
    every product with stored results (new or earlier). $0.0025 per new search (Apify Bronze)."""
    init()
    todo = [p for p in products if _due(domain, p['handle'])][:searches_left(domain)] if enabled() else []
    if todo:
        queries = ['"%s" "%s"' % (brand, p['title']) for p in todo]
        country = ((db.brand(domain) or {}).get('country') or 'US').upper()
        results, cost = _apify_search(queries, country.lower())
        by_query = dict(results)
        now = time.time()
        with db.conn() as c:
            for p, q in zip(todo, queries):
                c.execute('INSERT OR REPLACE INTO offsite_searches VALUES (?,?,?,?,?,?)',
                          (domain, p['handle'], q, json.dumps(by_query.get(q, [])),
                           (cost or 0) / len(todo), now))
    return stored(domain, products)


def stored(domain, products):
    """{handle: [url]} from searches already run for these products (free to reuse)."""
    init()
    out = {}
    for p in products:
        row = db.one('SELECT results FROM offsite_searches WHERE store_domain=? AND handle=?', (domain, p['handle']))
        if row:
            out[p['handle']] = json.loads(row['results'] or '[]')
    return out


def for_products(domain, products, brand=''):
    """{handle: [dict(id, url, site, text)]}: off-site pages naming the brand and the product. Fetches up to
    MAX_PAGES uncached pages (free)."""
    urls = candidate_urls(domain)
    page_gap.init()
    _read(urls, MAX_PAGES)
    brand_name = brand or (db.brand(domain) or {}).get('brand_name') or ''
    brand = _norm(brand_name)
    pages = [(u, (page_gap.facts(u) or {}).get('text') or '') for u in urls]
    out, n = {}, 0
    found = {p['handle'] for p in products if any(_names(t, brand, p['title']) for _, t in pages)}
    searched = {}
    if brand:
        try:
            search(domain, [p for p in products if p['handle'] not in found], brand_name)
        except Exception as e:                          # noqa: BLE001 - the paid step never blocks setup
            import sys
            sys.stderr.write('offsite search: %s\n' % e)
    searched = stored(domain, products)                 # earlier searches count too, at no extra cost
    own = _host('https://' + domain)
    for prod in products:
        title = prod['title']
        extra = [u for u in (page_gap.clean(x) for x in searched.get(prod['handle'], []))
                 if u and _host(u) != own and not _host(u).endswith('.' + own)
                 and not any(_host(u) == h or _host(u).endswith('.' + h) for h in SKIP_HOSTS)][:RESULTS_READ]
        _read(extra, RESULTS_READ)
        for u, text in pages + [(u, (page_gap.facts(u) or {}).get('text') or '') for u in extra]:
            if not _names(text, brand, title) or any(w['url'] == u for w in out.get(prod['handle'], [])):
                continue
            n += 1
            out.setdefault(prod['handle'], []).append(
                dict(id='W%d' % n, url=u, site=_host(u), text=_excerpts(text, title)))
            if len(out[prod['handle']]) >= PER_PRODUCT:
                break
    return out


def _names(text, brand, title):
    low = _norm(text)
    return bool(text) and _norm(title) in low and (not brand or brand in low)


def _read(urls, limit):
    try:
        page_gap.fetch_all([u for u in urls if u], limit=limit)
    except Exception:                                   # noqa: BLE001 - reading is a bonus, never a blocker
        pass


def supported(value, text):
    """Is a suggested answer actually written on the page? Every number and most of its words must be."""
    v, t = _norm(value), _norm(text)
    if not v:
        return False
    if v in t:
        return True
    nums = re.findall(r'\d+(?:[.,]\d+)?', v)
    if any(x not in t for x in nums):
        return False
    words = [w for w in re.findall(r'[a-z]{3,}', v)]
    return bool(words or nums) and sum(w in t for w in words) >= max(1, round(len(words) * 0.8))
