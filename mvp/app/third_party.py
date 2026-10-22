"""Third-party context: what Google Shopping, the wider web and Trustpilot say about a store.

Built 22 Oct 2026 from the one-off pull in mvp/content-agent/third-party-data/2026-10-21/
($2.31 for two stores), which found gaps the agent couldn't see from the store and the AI
answers alone: Clubhouse Skin missing from Google Shopping, 5Strands listing the same test
as 640 / 800+ / 955 / 1030 items, Clubhouse stocked by retailers but unreviewed.

One pull, for one store, runs three Apify actors on Produkto's account:

  Shopping    epctex/google-shopping-scraper: top 20 Google Shopping results for each
              buyer question, searched from the store's country. ~$0.0044 a result, so
              most of the cost (11 questions: ~$0.97).
  Web         apify/google-search-scraper: '"Brand" -site:domain' and '"Brand" <top
              product> review', 2 pages each. ~$0.0025 a page.
  Trustpilot  automation-lab/trustpilot: the latest 20 reviews for the domain. ~$0.005
              a run plus $0.0005 a review.

Rows land in third_party_runs / _shopping / _web / _reviews (db.py) with fetched_at.
facts() turns the latest pull into what the agent can use, and context() hands each
agent step its slice: diagnose, citations, feed, reviews. Everything here is RESEARCH:
nothing becomes a fact about the store's products. Drafts may use it to decide what to
fix, never as a source for a number or claim on the page.

Cost guard (guard()): estimate first; refuse if it exceeds the per-store cap
(PRODUKTO_THIRD_PARTY_CAP, default $3) or if the Apify account would end within
HEADROOM ($10) of its monthly limit, because the daily scans share that account. No
schedule: an admin starts a pull by hand (/admin/third-party, or `python3 third_party.py
<domain>`), and only while PRODUKTO_THIRD_PARTY=1.
"""
import json
import re
import threading
import time
import urllib.parse
from collections import Counter, defaultdict

import config
import db

SHOPPING_ACTOR = 'epctex~google-shopping-scraper'
SEARCH_ACTOR = 'apify~google-search-scraper'
TRUSTPILOT_ACTOR = 'automation-lab~trustpilot'

# Bronze prices, checked 21-22 Oct 2026 (Apify store pages and the 21 Oct pull's bill).
SHOPPING_PER_RESULT = 0.0044
SHOPPING_RESULTS = 20            # per question
SEARCH_PER_PAGE = 0.0025
SEARCH_PAGES = 2                 # per query
TRUSTPILOT_START = 0.005
TRUSTPILOT_PER_REVIEW = 0.0005
TRUSTPILOT_REVIEWS = 20
RUN_START = 0.001                # actor start events, rounded up
HEADROOM = 10.0                  # never run within this many dollars of the account's monthly limit
DEFAULT_CAP = 3.0                # per store per pull

_running = set()
_lock = threading.Lock()


# --- Switch, estimate, guard -------------------------------------------------

def enabled():
    return config.THIRD_PARTY


def store_cap():
    try:
        return float(config.env('PRODUKTO_THIRD_PARTY_CAP') or DEFAULT_CAP)
    except ValueError:
        return DEFAULT_CAP


def _questions(domain):
    ps = db.get_prompt_set(domain)
    return [q for q in (ps or {}).get('prompts') or [] if q and q.strip()]


def _country(domain):
    return ((db.brand(domain) or {}).get('country') or 'US').strip().lower() or 'us'


def _brand(domain):
    return ((db.brand(domain) or {}).get('brand_name') or domain.split('.')[0]).strip()


def top_product(domain):
    """The catalog product the most buyer questions fit (prompt_sets.relevance), else the first one."""
    ps = db.get_prompt_set(domain) or {}
    counts = Counter(pid for ids in ps.get('relevance') or [] for pid in ids or [])
    for pid, _ in counts.most_common():
        row = db.one('SELECT id, title FROM products WHERE id=? AND store_domain=?', (pid, domain))
        if row:
            return dict(row)
    row = db.one('SELECT id, title FROM products WHERE store_domain=? ORDER BY id LIMIT 1', (domain,))
    return dict(row) if row else None


def search_queries(domain):
    brand = _brand(domain)
    out = ['"%s" -site:%s' % (brand, domain)]
    top = top_product(domain)
    if top:
        out.append('"%s" %s review' % (brand, _strip_brand(top['title'], brand)))
    return out


def estimate(domain):
    """{shopping, web, trustpilot, total} in dollars: the most a pull can cost at today's prices."""
    n_q = len(_questions(domain))
    parts = dict(shopping=n_q * SHOPPING_RESULTS * SHOPPING_PER_RESULT + RUN_START if n_q else 0.0,
                 web=len(search_queries(domain)) * SEARCH_PAGES * SEARCH_PER_PAGE + RUN_START,
                 trustpilot=TRUSTPILOT_START + TRUSTPILOT_REVIEWS * TRUSTPILOT_PER_REVIEW + RUN_START)
    parts = {k: round(v, 4) for k, v in parts.items()}
    parts['total'] = round(sum(parts.values()), 4)
    parts['questions'] = n_q
    return parts


def account_usage():
    """(used, limit) in dollars this billing month for Produkto's Apify account."""
    import apify_answers
    d = apify_answers._request('GET', '/users/me/limits')['data']
    return float(d['current'].get('monthlyUsageUsd') or 0), float(d['limits'].get('maxMonthlyUsageUsd') or 0)


def guard(domain, usage=None):
    """(ok, reasons, estimate). `usage` = (used, limit) for tests; read from Apify otherwise."""
    est = estimate(domain)
    reasons = []
    if not enabled():
        reasons.append('Third-party pulls are switched off (PRODUKTO_THIRD_PARTY=1 turns them on).')
    if not db.one('SELECT domain FROM stores WHERE domain=?', (domain,)):
        reasons.append('No store %s.' % domain)
    if not est['questions']:
        reasons.append('This store has no buyer questions to search.')
    if est['total'] > store_cap():
        reasons.append('Estimated $%.2f is over the $%.2f cap for one store.' % (est['total'], store_cap()))
    with _lock:
        if domain in _running:
            reasons.append('A pull for this store is already running.')
    try:
        used, limit = usage if usage is not None else account_usage()
        if limit and limit - used - est['total'] < HEADROOM:
            reasons.append('The Apify account has $%.2f left of its $%.0f monthly limit; a pull must leave $%.0f '
                           'for the daily scans.' % (max(0, limit - used), limit, HEADROOM))
    except Exception as e:                                          # noqa: BLE001 - unknown balance = don't spend
        reasons.append('Could not read the Apify balance (%s).' % e)
    return not reasons, reasons, est


# --- Running the actors ------------------------------------------------------

def _run_actor(actor, body, wait=300):
    """(items, cost in dollars or None) from one Apify run."""
    import apify_answers
    run = apify_answers._request('POST', '/acts/%s/runs?waitForFinish=240' % actor, body, timeout=300)['data']
    deadline = time.time() + wait
    while run.get('status') not in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT') and time.time() < deadline:
        time.sleep(10)
        run = apify_answers._request('GET', '/actor-runs/%s' % run['id'])['data']
    if run.get('status') != 'SUCCEEDED':
        raise RuntimeError('%s run %s' % (actor, run.get('status')))
    items = apify_answers._request('GET', '/datasets/%s/items?clean=true' % run['defaultDatasetId'], timeout=120)
    run = apify_answers._request('GET', '/actor-runs/%s' % run['id'])['data']   # final bill
    return items, run.get('usageTotalUsd')


def _shopping(domain, questions, country):
    return _run_actor(SHOPPING_ACTOR, dict(queries=questions, countryCode=country,
                                           maxItemsPerQuery=SHOPPING_RESULTS,
                                           maxItems=len(questions) * SHOPPING_RESULTS,
                                           includeSponsoredResults=False), wait=900)


ENGLISH = ('us', 'gb', 'uk', 'ca', 'au', 'ie', 'nz')


def _web(queries, country):
    body = dict(queries='\n'.join(queries), maxPagesPerQuery=SEARCH_PAGES, resultsPerPage=10, countryCode=country,
                mobileResults=False, saveHtml=False, saveHtmlToKeyValueStore=False, includeIcons=False)
    if country in ENGLISH:              # 22 Oct: a UK search came back from a Portuguese-language proxy
        body['languageCode'] = 'en'
    return _run_actor(SEARCH_ACTOR, body)


def _trustpilot(domain):
    return _run_actor(TRUSTPILOT_ACTOR, dict(companyUrls=[domain], maxReviewsPerCompany=TRUSTPILOT_REVIEWS,
                                             sort='recency', includeCompanyInfo=True))


def run(domain, usage=None, actors=None):
    """One pull for one store. Refuses (ValueError with the reasons) unless guard() passes.
    `actors` replaces the three Apify calls in tests: dict(shopping=fn, web=fn, trustpilot=fn)."""
    ok, reasons, est = guard(domain, usage)
    if not ok:
        raise ValueError(' '.join(reasons))
    with _lock:
        if domain in _running:
            raise ValueError('A pull for this store is already running.')
        _running.add(domain)
    try:
        return _run(domain, est, actors or {})
    finally:
        with _lock:
            _running.discard(domain)


def _run(domain, est, actors):
    now = time.time()
    run_id = db.write('INSERT INTO third_party_runs (store_domain, status, estimate_usd, started_at) '
                      'VALUES (?,?,?,?)', (domain, 'running', est['total'], now))
    questions, country, queries = _questions(domain), _country(domain), search_queries(domain)
    detail, cost = {}, 0.0
    steps = (('shopping', lambda: (actors.get('shopping') or _shopping)(domain, questions, country)),
             ('web', lambda: (actors.get('web') or _web)(queries, country)),
             ('trustpilot', lambda: (actors.get('trustpilot') or _trustpilot)(domain)))
    for name, call in steps:
        try:
            items, usd = call()
            globals()['_save_' + name](domain, run_id, items or [], time.time())
            detail[name] = dict(status='ok', items=len(items or []), cost_usd=usd)
            cost += usd or 0
        except Exception as e:                                      # noqa: BLE001 - one failed actor keeps the others
            detail[name] = dict(status='failed', error=str(e)[:300])
    failed = [k for k, v in detail.items() if v['status'] != 'ok']
    status = 'done' if not failed else ('failed' if len(failed) == len(detail) else 'partial')
    db.write('UPDATE third_party_runs SET status=?, cost_usd=?, detail=?, finished_at=? WHERE id=?',
             (status, round(cost, 4), json.dumps(dict(detail, queries=queries, country=country)), time.time(), run_id))
    return dict(run_id=run_id, status=status, cost_usd=round(cost, 4), estimate_usd=est['total'], detail=detail)


def start(domain):
    """Admin button: run in a background thread. Returns (ok, message)."""
    ok, reasons, est = guard(domain)
    if not ok:
        return False, ' '.join(reasons)

    def go():
        try:
            run(domain)
        except Exception as e:                                      # noqa: BLE001
            import sys
            sys.stderr.write('third_party %s: %s\n' % (domain, e))
    threading.Thread(target=go, daemon=True).start()
    return True, 'Started. Estimated at most $%.2f.' % est['total']


# --- Saving ------------------------------------------------------------------

def _save_shopping(domain, run_id, items, at):
    brand = _brand(domain)
    products = _catalog(domain)
    with db.conn() as c:
        for it in items:
            title, merchant = it.get('productName') or '', it.get('merchantName') or ''
            listed = _has_brand(title, brand) or _has_brand(merchant, brand)
            own = _own_merchant(merchant, brand, domain)
            pid = _match_product(title, products, brand) if listed else None
            c.execute('INSERT INTO third_party_shopping (run_id, store_domain, question, position, title, merchant, '
                      'price, rating, reviews, is_brand, is_own_store, product_id, fetched_at) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (run_id, domain, it.get('searchKeyword') or '', it.get('positionOnSearchPage'), title, merchant,
                       it.get('price') or '', _num(it.get('reviewsScore')), int(_num(it.get('reviewsCount')) or 0),
                       int(listed), int(own), pid, at))


def _save_web(domain, run_id, items, at):
    brand = _brand(domain)
    seen = set()
    with db.conn() as c:
        for it in items:
            q = (it.get('searchQuery') or {}).get('term') or ''
            for r in it.get('organicResults') or []:
                url = r.get('url') or ''
                key = _clean(url)
                if not url or key in seen:
                    continue
                seen.add(key)
                title, snippet = r.get('title') or '', r.get('description') or ''
                if _own_host(url, domain):
                    continue
                c.execute('INSERT INTO third_party_web (run_id, store_domain, query, position, url, title, snippet, '
                          'kind, collision, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (run_id, domain, q, r.get('position'), url, title, snippet, kind(url, title),
                           int(collision(url, title, snippet, brand, domain)), at))


def _save_trustpilot(domain, run_id, items, at):
    with db.conn() as c:
        for it in items:
            c.execute('INSERT INTO third_party_reviews (run_id, store_domain, review_id, rating, title, text, published, '
                      'company_score, company_total, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                      (run_id, domain, it.get('reviewId') or '', it.get('rating'), it.get('title') or '',
                       (it.get('text') or '')[:2000], it.get('publishedDate') or '', _num(it.get('companyTrustScore')),
                       int(_num(it.get('companyTotalReviews')) or 0), at))


# --- Matching helpers --------------------------------------------------------

def _num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _squash(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _words(s):
    return re.findall(r'[a-z0-9]+', (s or '').lower().replace('’', "'"))


def _host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith('www.') else h


def _clean(url):
    p = urllib.parse.urlsplit(url)
    return (_host(url) + p.path).rstrip('/')


def _own_host(url, domain):
    h = _host(url)
    return h == domain or h.endswith('.' + domain)


def _has_brand(text, brand):
    """The brand's name written in the text, with or without spaces ('5 Strands' = '5Strands')."""
    b = _squash(brand)
    return bool(b) and b in _squash(text)


def _own_merchant(merchant, brand, domain):
    m = _squash(merchant)
    return bool(m) and (m.startswith(_squash(brand)) or m.startswith(_squash(domain.split('.')[0])))


def _strip_brand(title, brand):
    t = re.sub(re.escape(brand), '', title or '', flags=re.I).strip(' -|:')
    return t or title


STOP = {'the', 'and', 'for', 'with', 'a', 'an', 'of', 'in', 'to', 'by', 'at', 'on', 'set', 'kit'}


def _catalog(domain):
    return [dict(r) for r in db.all_('SELECT id, title, raw_json FROM products WHERE store_domain=?', (domain,))]


def _match_product(text, products, brand):
    """The store product whose title words (minus the brand) all appear in `text`, longest title first."""
    have = set(_words(text))
    best = None
    for p in products:
        ws = [w for w in _words(_strip_brand(p['title'], brand)) if w not in STOP]
        if ws and all(w in have for w in ws) and (not best or len(ws) > best[0]):
            best = (len(ws), p['id'])
    return best[1] if best else None


VIDEO = ('youtube.com', 'youtu.be', 'tiktok.com', 'vimeo.com')
FORUM = ('reddit.com', 'quora.com', 'justanswer.com', 'facebook.com/groups', 'mumsnet.com')
SOCIAL = ('instagram.com', 'facebook.com', 'x.com', 'twitter.com', 'pinterest.', 'linkedin.com')
MARKETS = ('amazon.', 'walmart.com', 'ebay.', 'etsy.com', 'chewy.com', 'target.com', 'mercari.com', 'ubuy.',
           'desertcart.', 'modesens.com', 'trustpilot.com')


def kind(url, title=''):
    """retailer / review / forum / video / social / other, from the address and title only."""
    u, t = url.lower(), (title or '').lower()
    if any(h in u for h in VIDEO) or '/live/video' in u or '/reel/' in u:
        return 'video'
    if any(h in u for h in FORUM) or '/forum' in u or t.startswith(('has anyone', 'any experience', 'is the ')):
        return 'forum'
    if 'trustpilot.com' in u or 'review' in t or '/review' in u or 'staff-pick' in u or '/blog' in u:
        return 'review'
    if any(h in u for h in SOCIAL):
        return 'social'
    if any(h in u for h in MARKETS) or re.search(r'/(products?|dp|ip|item|itm|shop|collections|brands?|category)[/-]', u) \
            or 'category.jsp' in u:
        return 'retailer'
    return 'other'


def collision(url, title, snippet, brand, domain):
    """True when the result is not about this brand: its name isn't written there at all (Google matched
    'Clean Skin Club' for "Clubhouse Skin"), or it is a different business whose name starts the same way
    ('ClubHouse Skin and Laser', clubhouseskinandlaser.com)."""
    text = ' '.join((title, snippet, urllib.parse.unquote(url)))
    if not _has_brand(text, brand):
        return True
    b = _squash(brand)
    h = _squash(_host(url).split('.')[0])
    if b in h and h != b and h != _squash(domain.split('.')[0]):
        return True
    words = r'\W*'.join(re.escape(w) for w in _words(brand))
    if re.search(words + r'\s*(and|&)\s+(laser|spa|clinic|salon|aesthetics|dermatology|medical)', text, re.I):
        return True
    return False


# Counts with a noun after them: "640 Items Tested", "800+ foods", "75ml". Pack and size words are
# grouped so "items" and "foods" compare (5Strands writes both for the same test).
_COUNT = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(\+?)\s*(items?|foods?|ingredients?|ml|g|oz|fl\.? ?oz|capsules?|'
                    r'tablets?|servings?|pack|count|pieces?|pcs)\b', re.I)
UNIT = {'item': 'items', 'items': 'items', 'food': 'items', 'foods': 'items', 'ingredient': 'items',
        'ingredients': 'items', 'capsule': 'capsules', 'tablet': 'tablets', 'serving': 'servings',
        'piece': 'pieces', 'pcs': 'pieces', 'fl oz': 'oz', 'fl.oz': 'oz', 'fl. oz': 'oz', 'floz': 'oz'}


def counts(text):
    """{unit: {value}} for every count written in the text."""
    out = defaultdict(set)
    for n, plus, unit in _COUNT.findall(text or ''):
        u = UNIT.get(unit.lower(), unit.lower())
        out[u].add(n.replace(',', '') + plus)
    return out


def _plain(html_text):
    import html
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', html_text or ''))).strip()


# --- What the agent sees -----------------------------------------------------

def _latest(domain, table):
    row = db.one('SELECT MAX(run_id) r FROM %s WHERE store_domain=?' % table, (domain,))
    return row['r'] if row else None


def latest_run(domain):
    row = db.one("SELECT * FROM third_party_runs WHERE store_domain=? AND status IN ('done','partial') "
                 "ORDER BY id DESC LIMIT 1", (domain,))
    return dict(row) if row else None


def facts(domain):
    """Everything the latest pull says, derived. None if the store was never pulled."""
    last = latest_run(domain)
    if not last:
        return None
    detail = json.loads(last.get('detail') or '{}')
    brand = _brand(domain)
    products = {p['id']: p for p in _catalog(domain)}
    out = dict(fetched_at=last['finished_at'] or last['started_at'], cost_usd=last['cost_usd'], brand=brand,
               shopping=None, offsite=None, trustpilot=None, conflicts=[])

    rid = _latest(domain, 'third_party_shopping')
    shop_rows = [dict(r) for r in db.all_('SELECT * FROM third_party_shopping WHERE store_domain=? AND run_id=? '
                                         'ORDER BY question, position', (domain, rid))] if rid else []
    if rid:
        per_q = defaultdict(list)
        for r in shop_rows:
            per_q[r['question']].append(r)
        qs = []
        for q, rows in per_q.items():
            mine = [r for r in rows if r['is_brand']]
            qs.append(dict(question=q, results=len(rows),
                           brand=[dict(position=r['position'], title=r['title'], merchant=r['merchant'],
                                       own_store=bool(r['is_own_store']), product_id=r['product_id']) for r in mine],
                           top=[dict(position=r['position'], title=r['title'], merchant=r['merchant'])
                                for r in rows[:3]]))
        seen = Counter(r['product_id'] for r in shop_rows if r['product_id'])
        out['shopping'] = dict(
            questions=qs, searched=len(qs),
            with_brand=sum(1 for q in qs if q['brand']),
            with_own_store=sum(1 for q in qs if any(b['own_store'] for b in q['brand'])),
            products=[dict(id=pid, title=products[pid]['title'], listings=n,
                           best=min(r['position'] for r in shop_rows if r['product_id'] == pid))
                      for pid, n in seen.most_common() if pid in products])

    rid = _latest(domain, 'third_party_web')
    web = [dict(r) for r in db.all_('SELECT * FROM third_party_web WHERE store_domain=? AND run_id=? ORDER BY id',
                                    (domain, rid))] if rid else []
    if rid:
        keep = [w for w in web if not w['collision']]
        clash = [w for w in web if w['collision']]
        names = Counter()
        for w in clash:
            m = re.match(r'\s*([^|:\-–(]+)', w['title'] or '')
            if m and _squash(m.group(1)) != _squash(brand) and not m.group(1).strip().lower().startswith('http') \
                    and len(re.findall(r'[A-Za-z]', m.group(1))) >= 3:
                names[m.group(1).strip()[:40]] += 1
        out['offsite'] = dict(pages=[dict(url=w['url'], site=_host(w['url']), title=w['title'], kind=w['kind'],
                                          snippet=w['snippet']) for w in keep],
                              by_kind=dict(Counter(w['kind'] for w in keep)),
                              collisions=len(clash), collision_names=[n for n, _ in names.most_common(3)])

    t = detail.get('trustpilot') or {}
    if t.get('status') == 'ok':
        rid = _latest(domain, 'third_party_reviews')
        revs = [dict(r) for r in db.all_('SELECT * FROM third_party_reviews WHERE store_domain=? AND run_id=? '
                                         'ORDER BY published DESC', (domain, rid))] if rid else []
        if rid != last['id'] and t.get('items') == 0:
            revs = []                                   # the latest pull found none; older rows are out of date
        out['trustpilot'] = dict(
            count=max([r['company_total'] or 0 for r in revs] + [len(revs)]) if revs else 0,
            score=next((r['company_score'] for r in revs if r['company_score'] is not None), None),
            complaints=[dict(rating=r['rating'], title=r['title'], text=r['text'][:300], date=r['published'][:10])
                        for r in revs if (r['rating'] or 5) <= 3][:3])

    out['conflicts'] = _conflicts(domain, brand, products, shop_rows, web)
    return out


def _conflicts(domain, brand, products, shop_rows, web):
    """Product counts that disagree across the store and its listings, per product and unit.
    [{product_id, product, unit, values: {value: [where]}}]."""
    found = defaultdict(lambda: defaultdict(set))       # (pid, unit) -> value -> {where}
    catalog = list(products.values())

    def add(pid, text, where):
        for unit, vals in counts(text).items():
            for v in vals:
                found[(pid, unit)][v].add(where)

    for p in catalog:
        raw = json.loads(p.get('raw_json') or '{}')
        add(p['id'], p['title'] + ' ' + _plain(raw.get('body_html') or ''), 'your store')
    for r in shop_rows:
        if r['is_brand'] and r['product_id']:
            add(r['product_id'], r['title'], (r['merchant'] or 'Google Shopping') + ' (Google Shopping)')
    for w in web:
        if w['collision']:
            continue
        pid = _match_product(w['title'] + ' ' + w['snippet'], catalog, brand)
        if pid:
            add(pid, w['title'] + ' ' + w['snippet'], _host(w['url']))
    out = []
    for (pid, unit), vals in found.items():
        if len(vals) > 1 and any(w != 'your store' for ws in vals.values() for w in ws):
            out.append(dict(product_id=pid, product=products[pid]['title'], unit=unit,
                            values={v: sorted(ws) for v, ws in sorted(vals.items())}))
    out.sort(key=lambda c: -len(c['values']))
    return out


STEPS = ('diagnose', 'citations', 'feed', 'reviews')
GUARD = ('research only: use it to decide what to fix. Never put a number, claim or review from it on the page, '
         'and never name these sites')


def context(domain, step, questions=None, product_ids=None):
    """Plain-text slice of the latest pull for one agent step ('' if nothing useful). `questions` and
    `product_ids` narrow it to what the task is about."""
    if step not in STEPS:
        raise ValueError(step)
    f = facts(domain)
    if not f:
        return ''
    lines = []
    when = time.strftime('%d %b %Y', time.gmtime(f['fetched_at']))
    sh, off, tp = f['shopping'], f['offsite'], f['trustpilot']
    want = set(questions or [])
    pids = set(product_ids or [])

    if step == 'diagnose':
        if sh:
            for q in sh['questions']:
                if want and q['question'] not in want:
                    continue
                if q['brand']:
                    b = ', '.join('#%d via %s%s' % (x['position'], x['merchant'], '' if x['own_store'] else ' (not your store)')
                                  for x in q['brand'][:3])
                    lines.append('- Google Shopping for "%s": %s listed at %s.' % (q['question'], f['brand'], b))
                else:
                    lines.append('- Google Shopping for "%s": %s not in the top %d. Top: %s.' % (
                        q['question'], f['brand'], q['results'],
                        '; '.join('%s (%s)' % (t['title'][:60], t['merchant']) for t in q['top'])))
        if off and off['collision_names']:
            lines.append('- Name clash: Google mixes %s up with %s. Pages about those are not coverage.'
                         % (f['brand'], ', '.join(off['collision_names'])))
        lines += _conflict_lines(f, pids)

    elif step == 'feed':
        if sh:
            if not sh['with_own_store']:
                lines.append('- The store itself is in none of the Google Shopping top %d results for its %d buyer '
                             'questions%s. Likely no Merchant Center or free listings.' % (
                                 SHOPPING_RESULTS, sh['searched'],
                                 ' (only resellers list it, on %d)' % sh['with_brand'] if sh['with_brand'] else ''))
            else:
                lines.append('- The store is in Google Shopping for %d of %d buyer questions.'
                             % (sh['with_own_store'], sh['searched']))
            for p in sh['products'][:5]:
                lines.append('- In Google Shopping: %s (%d listings, best position %d).' % (p['title'], p['listings'], p['best']))
        lines += _conflict_lines(f, pids)

    elif step == 'citations':
        if off:
            for k in ('retailer', 'review', 'forum', 'video'):
                pages = [p for p in off['pages'] if p['kind'] == k][:6]
                if pages:
                    lines.append('- %s pages naming the brand: %s' % (k.capitalize(), '; '.join(
                        '%s (%s)' % (p['site'], p['title'][:60]) for p in pages)))
            if not off['by_kind'].get('review') and not off['by_kind'].get('forum'):
                lines.append('- No review articles or forum threads found about the brand.')
            if off['collisions']:
                lines.append('- %d results were not about this brand (unrelated pages or similar names%s); left out.' % (
                    off['collisions'], ': %s' % ', '.join(off['collision_names']) if off['collision_names'] else ''))

    elif step == 'reviews':
        if tp is not None:
            if not tp['count']:
                lines.append('- Trustpilot: no reviews found.')
            else:
                lines.append('- Trustpilot: %d reviews%s.' % (tp['count'], ', score %.1f' % tp['score'] if tp['score'] else ''))
                for c in tp['complaints']:
                    lines.append('  - %s stars, %s: "%s" %s' % (c['rating'], c['date'], c['title'][:80], c['text'][:200]))
        if off:
            rev = [p for p in off['pages'] if p['kind'] == 'review'][:5]
            if rev:
                lines.append('- Review pages: ' + '; '.join('%s (%s)' % (p['site'], p['title'][:60]) for p in rev))
    if not lines:
        return ''
    return 'THIRD-PARTY CONTEXT, %s (pulled %s; %s):\n%s' % (step.upper(), when, GUARD, '\n'.join(lines))


def _conflict_lines(f, pids):
    out = []
    for c in f['conflicts'][:4]:
        if pids and c['product_id'] not in pids:
            continue
        out.append('- %s: listed with different %s counts: %s.' % (c['product'], c['unit'], '; '.join(
            '%s at %s' % (v, ', '.join(ws[:3])) for v, ws in c['values'].items())))
    return out


def for_brief(domain, questions, products):
    """{step: text} for a content brief (briefs.build). Free: reads stored rows only."""
    if not enabled():
        return {}
    pids = [p['id'] for p in products if p.get('id')]
    for p in products:
        if not p.get('id') and p.get('handle'):
            row = db.one('SELECT id FROM products WHERE store_domain=? AND handle=?', (domain, p['handle']))
            if row:
                pids.append(row['id'])
    out = {}
    for step in STEPS:
        try:
            t = context(domain, step, questions=questions, product_ids=pids)
        except Exception:                                           # noqa: BLE001 - context is a bonus
            t = ''
        if t:
            out[step] = t
    return out


def offsite_urls(domain, limit=10):
    """Retailer and review pages from the latest pull, for offsite_facts to read for missing facts (free)."""
    if not enabled():
        return []
    f = facts(domain)
    if not f or not f['offsite']:
        return []
    return [p['url'] for p in f['offsite']['pages'] if p['kind'] in ('retailer', 'review')][:limit]


# --- Opportunities (Product Data cards) ------------------------------------------

def cards(domain):
    """Feed and review cards from the latest pull, in feed_check.cards' shape. Nothing unless switched on."""
    from html import escape as E
    if not enabled():
        return []
    f = facts(domain)
    if not f:
        return []
    out = []

    def add(key, impact, weight, title, text):
        out.append(dict(type='feed', key=key, impact=impact, weight=weight, title=title, text=text))

    sh = f['shopping']
    if sh and sh['searched'] and not sh['with_own_store']:
        add('google-shopping', 'high', sh['searched'], 'Get your products into Google Shopping',
            'We searched Google Shopping for your %d buyer questions. Your store was in none of the top %d results%s. '
            'Google Shopping and AI Mode read product data from Google Merchant Center; Shopify\'s Google &amp; '
            'YouTube app connects it for free.' % (sh['searched'], SHOPPING_RESULTS,
                                                    ' (resellers listed you on %d)' % sh['with_brand'] if sh['with_brand'] else ''))
    for c in f['conflicts'][:3]:
        vals = '; '.join('<b>%s</b> at %s' % (E(v), E(', '.join(ws[:3]))) for v, ws in c['values'].items())
        add('numbers-' + str(c['product_id']) + '-' + c['unit'], 'medium', len(c['values']),
            'Use one %s count for %s everywhere' % (E(c['unit']), E(c['product'])),
            'Listings of %s give different %s counts: %s. Pick the right number and use it on your page and '
            'every listing.' % (E(c['product']), E(c['unit']), vals))
    tp = f['trustpilot']
    if tp and tp['complaints']:
        shown = ''.join('<br>&bull; %s stars: %s' % (c['rating'], E(c['title'][:90])) for c in tp['complaints'])
        add('trustpilot-complaints', 'medium', len(tp['complaints']), 'Answer what reviewers complain about',
            'Recent Trustpilot reviews raise:%s<br>If a complaint is about something buyers ask before buying '
            '(delivery or result times), state the plain answer on your product pages.' % shown)
    return out


# --- Admin page (/admin/third-party) -----------------------------------------------

def admin_body(q, note=''):
    """Internal page: pick a store, see the estimate and guard, start a pull, read what the agent now sees."""
    from html import escape as E
    stores = [r['domain'] for r in db.all_('SELECT domain FROM stores ORDER BY domain')]
    d = q.get('d') or (stores[0] if stores else '')
    opts = ''.join('<option%s>%s</option>' % (' selected' if s == d else '', E(s)) for s in stores)
    html = ['<h1>Third-party context</h1><p class="small">Google Shopping, Google web results and Trustpilot for '
            'one store, for the Catalog Optimization Agent. Internal, admin only. Costs real Apify money.</p>',
            '<form method="get" action="/admin/third-party"><select name="d">%s</select> '
            '<button type="submit" style="width:auto">Show</button></form>' % opts]
    if note:
        html.append('<p><b>%s</b></p>' % E(note))
    if d:
        ok, reasons, est = guard(d)
        html.append('<p>Estimate for %s: <b>$%.2f</b> (Shopping $%.2f for %d questions, web $%.3f, Trustpilot $%.3f). '
                    'Cap $%.2f per store.</p>' % (E(d), est['total'], est['shopping'], est['questions'], est['web'],
                                                   est['trustpilot'], store_cap()))
        if ok:
            html.append('<form method="post" action="/admin/third-party"><input type="hidden" name="d" value="%s">'
                        '<button type="submit" style="width:auto">Run pull (about $%.2f)</button></form>' % (E(d), est['total']))
        else:
            html.append('<p>Can\'t run: %s</p>' % E(' '.join(reasons)))
        runs = db.all_('SELECT * FROM third_party_runs WHERE store_domain=? ORDER BY id DESC LIMIT 5', (d,))
        if runs:
            html.append('<table><thead><tr><th>Started</th><th>Status</th><th>Estimate</th><th>Billed</th></tr></thead>'
                        '<tbody>%s</tbody></table>' % ''.join(
                            '<tr><td>%s</td><td>%s</td><td>$%.2f</td><td>%s</td></tr>' % (
                                time.strftime('%d %b %H:%M', time.localtime(r['started_at'])), E(r['status']),
                                r['estimate_usd'] or 0, '$%.3f' % r['cost_usd'] if r['cost_usd'] is not None else '…')
                            for r in runs))
        for step in STEPS:
            t = context(d, step)
            if t:
                html.append('<pre style="white-space:pre-wrap;font-size:.8rem">%s</pre>' % E(t))
    return ''.join(html)


if __name__ == '__main__':
    import sys
    d = sys.argv[1]
    if '--estimate' in sys.argv:
        ok, why, est = guard(d)
        print(json.dumps(dict(ok=ok, reasons=why, estimate=est), indent=1))
    elif '--facts' in sys.argv:
        print(json.dumps(facts(d), indent=1)[:6000])
        for s in STEPS:
            print('\n' + (context(d, s) or '(%s: nothing)' % s))
    else:
        print(json.dumps(run(d), indent=1))
