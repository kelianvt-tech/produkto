"""Opportunities: a ranked list of fixes, copied from Searchable's Actions →
Opportunities (screenshots from Kelian, 8 Oct 2026).

Layout: a Categories panel (Setup / On Page / Off Page, each with sub-types
and counts) beside a list of compact cards - type tag, impact level, title,
one evidence line, Done / Decline. Off Page appears once "Sites to get onto"
(plan step 2) exists; a category with nothing in it is not shown.

Everything here comes from answers already collected in the last 30 days, so
it costs nothing extra per scan.

Impact levels copy Searchable's Critical / High / Medium labels (Kelian,
8 Oct 2026). Searchable does not publish how it sets them, so ours follow the
written rules in IMPACT_RULES below, and those rules are the only source.

Hidden behind config.SHOW_OPPORTUNITIES until it is ready: with the switch
off there is no rail item and the page returns Not found.

Copy rule: describe what the answers show, never promise that a fix will move
visibility. Nobody has shown that yet.
"""
import json
import re
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from html import escape as E

import config
import db
import evidence
import page_gap
import period
import storetime

WINDOW = {'range': '30', 'group': 'day', 'frm': '', 'to': ''}
STATUSES = ('done', 'declined')
ORDER = {'critical': 0, 'high': 1, 'medium': 2}

# Category -> sub-types, in Searchable's order. Label shown in the panel and
# on each card's tag.
CATEGORIES = [
    ('setup', 'Setup', [('stale', 'Stale Data'), ('prompt', 'Prompt Quality')]),
    ('onpage', 'On Page', [('missing', 'Missing Visibility'), ('topic', 'Topic Gap'),
                           ('low', 'Low Visibility'), ('competitor', 'Competitor Gap'),
                           ('position', 'High Position'), ('details', 'Content Gap'), ('feed', 'Product Data')]),
    ('offpage', 'Off Page', [('retailer', 'Retailer Gap'), ('citation', 'Citation Gap')]),
]

# Shops a product gets stocked on rather than written about, so the fix is a
# listing, not coverage. A domain is matched with or without its subdomain.
RETAILERS = {'amazon.com', 'amazon.co.uk', 'walmart.com', 'target.com', 'sephora.com', 'ulta.com',
             'nordstrom.com', 'macys.com', 'bloomingdales.com', 'saksfifthavenue.com', 'neimanmarcus.com',
             'revolve.com', 'dermstore.com', 'lookfantastic.com', 'cultbeauty.co.uk', 'boots.com',
             'johnlewis.com', 'selfridges.com', 'harrods.com', 'asos.com', 'zalando.com', 'mrporter.com',
             'net-a-porter.com', 'farfetch.com', 'ssense.com', 'endclothing.com', 'urbanoutfitters.com',
             'costco.com', 'cvs.com', 'walgreens.com', 'etsy.com', 'ebay.com', 'bestbuy.com', 'rei.com',
             'dickssportinggoods.com', 'zappos.com', 'kohls.com', 'credobeauty.com', 'thedetoxmarket.com', 'superdrug.com', 'shop.tiktok.com',
             'feelunique.com', 'spacenk.com', 'beautybay.com', 'hollandandbarrett.com', 'iherb.com'}
TYPE_LABEL = {k: label for _, _, types in CATEGORIES for k, label in types}
TYPE_CATEGORY = {k: cat for cat, _, types in CATEGORIES for k, _ in types}

# The written rule behind every impact level. Shown nowhere yet; kept here so
# anyone asking "why is this Critical?" gets a checkable answer.
IMPACT_RULES = {
    'stale': 'Critical: no finished scan for 3+ days. High: 2 days.',
    'prompt': 'One card per buyer question that fails any check. High: names your brand or product, or '
              '70%+ of its words come from your product page. Medium: 50%+ from your page (4+ words), '
              '3+ requirements stacked, 4 words or fewer, or 3+ answers in 30 days and none named a product.',
    'missing': 'Your products in no answer. Critical: competitors named in 90%+ of answers. '
               'High: 60%+. Medium: below that.',
    'low': 'Your products in under 30% of answers. High: under 10%. Medium: 10-29%.',
    'competitor': 'One competitor named in at least twice as many answers as your products. '
                  'High: 5x or more. Medium: 2-5x.',
    'position': 'Medium: your products in 30%+ of answers at an average position of 2 or better.',
    'details': 'A buyer question you are losing where most of the product pages AI recommended instead state '
               'something yours does not (the question\'s own words, or review rating / brand / barcode / price in '
               'the page data). High: 3+ missing words, or a review rating. Medium: anything less.',
    'feed': 'feed_check.py. Critical: robots.txt blocks a crawler AI answers rely on; a US store missing a policy '
            'Shopify needs before it shares products with ChatGPT; a non-US store absent from Google Shopping (ChatGPT '
            'picks products from Google Shopping outside the US). High: product pages with no product data, or without '
            'price/stock in it; the one-time ChatGPT channel check for US stores. Medium: no barcode (GTIN), no review '
            'rating on any page, no refund or shipping policy page.',
    'topic': 'A topic (2+ buyer questions) where your products are in under 20% of answers. '
             'High: in none. Medium: 1-19%.',
    'retailer': 'A shop cited in at least 5% (and 3+) of the answers where competitors were named and none of your products. '
                'Critical: 20%+ of those answers. High: 10%+. Medium: below that.',
    'citation': 'Any other site (not a brand\'s own) cited in at least 5% (and 3+) of the answers where competitors were named and '
                'none of your products. Critical: 20%+ of those answers. High: 10%+. Medium: below that.',
}


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS opportunity_status (store_domain TEXT NOT NULL, '
                  'kind TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL, at REAL, '
                  'PRIMARY KEY (store_domain, kind, key))')
        # "Dismiss" became "Decline" to match Searchable, 8 Oct 2026.
        c.execute("UPDATE opportunity_status SET status='declined' WHERE status='dismissed'")


def _statuses(domain):
    return {(r['kind'], r['key']): r for r in db.all_(
        'SELECT * FROM opportunity_status WHERE store_domain=?', (domain,))}


def _pct(n, d):
    return n / d if d else 0


def _plural(n, word):
    return '%d %s%s' % (n, word, '' if n == 1 else 's')


def _answers_link(token, index, status=''):
    if token is None or index is None:
        return ''
    return ' <a class="opp-link" href="/r/%s/answers?q=%d%s&range=30">Read the answers</a>' % (
        E(token), index, '&status=' + status if status else '')


def find(domain, questions=False):
    """Every opportunity for this store, open or not, most important first. Question-quality items
    ("Improve buyer question") moved to Buyer questions > Suggestions on 18 Oct 2026, so they are left out
    unless questions=True (question_suggestions.py asks for them)."""
    import copy
    out = copy.deepcopy(db.memo(("opportunities", domain, time.strftime("%Y-%m-%d %H")), lambda: _find(domain)))
    return out if questions else [r for r in out if r['type'] != 'prompt']


def _find(domain):
    ps = db.get_prompt_set(domain)
    if not ps:
        return []
    out = []
    _, _, start, end = period.bounds(WINDOW, tz=storetime.zone(domain))
    scans = period.done_scans(ps['id'], start, end)
    last = period.done_scans(ps['id'])
    last_at = last[-1]['run_at'] if last else None
    if last_at is not None:
        days = int((time.time() - last_at) // 86400)
        if days >= 2:
            out.append(dict(type='stale', key='scan', impact='critical' if days >= 3 else 'high', weight=days,
                            title='Scans have not run for %s' % _plural(days, 'day'),
                            text='The last finished scan was on <b>%s</b>. Every number on the dashboard is '
                                 'from that date or earlier.' % E(time.strftime('%-d %b %Y', time.localtime(last_at)))))
    if not scans:
        return _sorted(out)
    token = scans[-1]['token']
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    by_answer = defaultdict(list)
    for m in mentions:
        by_answer[m['answer_id']].append(m)
    index = {q: i for i, q in enumerate(ps['prompts'])}

    stats = {}
    sites = defaultdict(lambda: dict(answers=0, questions=set(), pages=Counter(), brands=Counter()))
    brand_sites, lost_answers = set(), 0
    win_urls = defaultdict(Counter)     # question -> competitor product pages named when you were not
    for a in answers:
        ms = by_answer.get(a['id'], [])
        s = stats.setdefault(a['prompt'], dict(answers=0, any=0, own=0, theirs=0, ranks=[], brands=Counter()))
        s['answers'] += 1
        mine = [m for m in ms if m['is_theirs'] or evidence.own(m, p)]
        theirs = [m for m in ms if m not in mine]
        s['any'] += bool(ms)
        s['own'] += bool(mine)
        s['theirs'] += bool(theirs)
        if mine:
            s['ranks'].append(min(m['rank'] or 99 for m in mine))
        brand_sites.update(_site(m['url']) for m in ms if m['url'])
        if theirs and not mine:
            lost_answers += 1
            for m in theirs:
                win_urls[a['prompt']][_winner(m)] += 1
            seen = set()
            for c in _citations(a):
                site = _site(c.get('url', ''))
                if site and site not in seen:
                    seen.add(site)
                    sites[site]['answers'] += 1
                    sites[site]['questions'].add(a['prompt'])
                    sites[site]['pages'][c['url']] += 1
                    for b in {(m['brand'] or '').strip() for m in theirs} - {''}:
                        sites[site]['brands'][b] += 1
        for b in {(m['brand'] or m['product_name'] or '').strip() for m in theirs} - {''}:
            s['brands'][b] += 1

    for q, s in stats.items():
        n, i = s['answers'], index.get(q)
        quoted = '&ldquo;%s&rdquo;' % E(q)
        rate = _pct(s['own'], n)
        top = s['brands'].most_common(3)
        named = ', '.join('<b>%s</b>' % E(b) for b, _ in top)
        if n >= 3 and not s['any']:
            continue    # a question that names no products: see _prompt_quality
        if not s['own'] and s['theirs']:
            share = _pct(s['theirs'], n)
            out.append(dict(type='missing', key=q, weight=s['theirs'],
                            impact='critical' if share >= .9 else 'high' if share >= .6 else 'medium',
                            title='Get recommended for %s' % quoted,
                            text='AI named a competitor in <b>%d of %d</b> answers and none of your products. '
                                 'Named instead: %s.' % (s['theirs'], n, named) + _answers_link(token, i, 'absent')))
            continue
        if s['own'] and rate < .3:
            out.append(dict(type='low', key=q, weight=n - s['own'], impact='high' if rate < .1 else 'medium',
                            title='Raise your visibility for %s' % quoted,
                            text='Your products appear in <b>%d of %d</b> answers (%d%%). Named more often: %s.'
                                 % (s['own'], n, round(rate * 100), named) + _answers_link(token, i)))
        if s['own'] and top and top[0][1] >= 2 * s['own']:
            brand, c = top[0]
            out.append(dict(type='competitor', key=q, weight=c - s['own'],
                            impact='high' if c >= 5 * s['own'] else 'medium',
                            title='Close the gap with %s on %s' % (E(brand), quoted),
                            text='<b>%s</b> is named in <b>%d</b> answers; your products in <b>%d</b>.'
                                 % (E(brand), c, s['own']) + _answers_link(token, i)))
        if rate >= .3 and s['ranks'] and sum(s['ranks']) / len(s['ranks']) <= 2:
            avg = sum(s['ranks']) / len(s['ranks'])
            out.append(dict(type='position', key=q, weight=s['own'], impact='medium',
                            title='Keep your top spot for %s' % quoted,
                            text='Your products appear in <b>%d of %d</b> answers at an average position of '
                                 '<b>%.1f</b>. Check these answers still describe your products correctly.'
                                 % (s['own'], n, avg) + _answers_link(token, i, 'yours')))
    out += _prompt_quality(domain, ps, stats, index, token)
    out += _details(ps, stats, win_urls, index, token)
    out += _topics(ps, stats, index, token)
    out += _off_page(domain, sites, brand_sites, lost_answers)
    out += _feed(domain)
    return _sorted(out)


def _feed(domain):
    try:
        import feed_check
        return feed_check.cards(domain)
    except Exception:                                   # noqa: BLE001 - never break the page
        return []


_STOP = set("""a an and are as at be best but by can do does for from good have how i if in is it its
 my of on or should that the their them there this to use using want what whats when where which while who
 why will with without you your get choose buy keep keeps all every day daily me im more most than very
 good better""".split())
_WORDS = re.compile(r"[a-z0-9%£$€]+")
# Words that join one requirement to the next: "brightens, protects AND absorbs WITHOUT ...".
_JOINERS = re.compile(r",| and | without | while | under ")


def _content(text):
    return [w for w in _WORDS.findall(text.lower().replace("’", "'").replace("'s", "")) if len(w) > 2 and w not in _STOP]


def _strip_html(html):
    return re.sub(r"<[^>]+>", " ", html or "")


def _prompt_quality(domain, ps, stats, index, token):
    """Buyer questions that make a poor test, so their numbers flatter or say nothing.

    Four checks from the question and our own catalog, plus one from the
    answers. They are rules of thumb, so a card can be a judgement call;
    Decline is there for those."""
    import json
    brand = db.brand(domain) or {}
    own_names = [n for n in [brand.get('brand_name') or ''] + (brand.get('aliases') or '').split(',') if len(n.strip()) > 2]
    catalog = {c['id']: c for c in ps['catalog_snapshot']}
    out = []
    for i, q in enumerate(ps['prompts']):
        reasons, level = [], 'medium'
        low = q.lower()
        named = [n.strip() for n in own_names if n.strip().lower() in low]
        ids = ps['relevance'][i] if i < len(ps['relevance']) else []
        products = [catalog[x] for x in ids if x in catalog]
        named += [p['title'] for p in catalog.values() if len(p['title']) > 4 and p['title'].lower() in low]
        if named:
            level = 'high'
            reasons.append('It names <b>%s</b>, so AI is told about you instead of finding you.' % E(named[0]))
        words = _content(q)
        best, page = [], None
        for p in products:
            raw = json.loads(p.get('raw_json') or '{}')
            vocab = set(_content(p['title'] + ' ' + _strip_html(raw.get('body_html'))))
            hit = [w for w in words if w in vocab]
            if len(hit) > len(best):
                best, page = hit, p
        if words and len(best) >= 4 and len(best) / len(words) >= .5:
            if len(best) / len(words) >= .7:
                level = 'high'
            reasons.append('<b>%d of %d</b> of its key words appear on your <b>%s</b> page (%s), so it reads like '
                           'your product description rather than a buyer&rsquo;s question.'
                           % (len(best), len(words), E(page['title']), E(', '.join(dict.fromkeys(best)))))
        joins = len(_JOINERS.findall(' %s ' % low))
        if joins >= 3:
            reasons.append('It stacks <b>%d</b> requirements into one question. Few buyers ask that narrowly, so '
                           'results here may not reflect what most buyers see.' % (joins + 1))
        if len(q.split()) <= 4:
            reasons.append('At <b>%d words</b> it reads like a search keyword. AI answers full questions '
                           'differently.' % len(q.split()))
        s = stats.get(q)
        if s and s['answers'] >= 3 and not s['any']:
            reasons.append('None of the %s to it in the last 30 days named a product, so it measures nothing.'
                           % _plural(s['answers'], 'answer'))
        if reasons:
            out.append(dict(type='prompt', key=q, impact=level, weight=len(reasons),
                            title='Improve buyer question: &ldquo;%s&rdquo;' % E(q),
                            text=' '.join(reasons) + _answers_link(token, index.get(q))))
    return out


def _detail_pages(ps, stats, win_urls, find=False):
    """(question, your product, winning page urls) for every question you lost outright.

    With find=True, competitor products named without a link are looked up
    on their brand's store (network); otherwise only earlier lookups count."""
    catalog = {c['id']: c for c in ps['catalog_snapshot']}
    index = {q: i for i, q in enumerate(ps['prompts'])}
    out = []
    for q, s in stats.items():
        i = index.get(q)
        if s['own'] or not s['theirs'] or i is None or not win_urls.get(q):
            continue
        ids = ps['relevance'][i] if i < len(ps['relevance']) else []
        urls = []
        for w, _ in win_urls[q].most_common(12):
            u = _page_of(w, find)
            if u and u not in urls:
                urls.append(u)
            if len(urls) >= page_gap.WINNER_PAGES:
                break
        for pid in ids:
            if pid in catalog:
                out.append((q, catalog[pid], urls))
    return out


def page_targets(domain):
    """Every page step 3 compares for this store: yours and the winners'."""
    ps = db.get_prompt_set(domain)
    if not ps:
        return []
    _, _, start, end = period.bounds(WINDOW, tz=storetime.zone(domain))
    scans = period.done_scans(ps['id'], start, end)
    if not scans:
        return []
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    by_answer = defaultdict(list)
    for m in mentions:
        by_answer[m['answer_id']].append(m)
    stats, win_urls = {}, defaultdict(Counter)
    for a in answers:
        ms = by_answer.get(a['id'], [])
        mine = [m for m in ms if m['is_theirs'] or evidence.own(m, p)]
        theirs = [m for m in ms if m not in mine]
        s = stats.setdefault(a['prompt'], dict(own=0, theirs=0))
        s['own'] += bool(mine)
        s['theirs'] += bool(theirs)
        if theirs and not mine:
            for m in theirs:
                win_urls[a['prompt']][_winner(m)] += 1
    urls = []
    for _q, item, wins in _detail_pages(ps, stats, win_urls, find=True):
        urls += [item['url']] + wins
    # The most-cited page behind every "Get featured on / stocked on" card.
    urls += [page_gap.clean(r['page']) for r in find(domain) if r.get('page')]
    return list(dict.fromkeys(u for u in urls if u))


def _winner(m):
    """A competitor product: (its link if it is a product page, its brand's site, its name)."""
    import insight_panels
    row = dict(brand=m['brand'] or '', url=m['url'] or '', name=m['product_name'] or '')
    return (page_gap.clean(m['url']), insight_panels.brand_site(row) if row['brand'] else '', row['name'])


def _page_of(winner, find=False):
    url, site, name = winner
    if url:
        return url
    if not site or not name:
        return ''
    return page_gap.lookup(site, name) if find else page_gap.lookup_cached(site, name)


_REFRESHING = {}


def refresh_pages(domain):
    """Fetch step 3's pages in the background, at most once an hour per store."""
    if time.time() - _REFRESHING.get(domain, 0) < 3600:
        return
    _REFRESHING[domain] = time.time()

    def run():
        try:
            import feed_check
            feed_check.refresh(domain)
        except Exception:                               # noqa: BLE001
            import traceback
            traceback.print_exc()
        try:
            page_gap.fetch_all(page_targets(domain))
            if config.PAGE_EXPLAIN:
                for r in find(domain):
                    if r.get('page'):
                        page_gap.explain(r['page'], r.get('brands') or [])
        except Exception:                               # noqa: BLE001 - never break the page
            import traceback
            traceback.print_exc()
    threading.Thread(target=run, daemon=True).start()


def _details(ps, stats, win_urls, index, token):
    """Missing product details: what the winners' pages state and yours doesn't."""
    page_gap.init()
    found = {}                           # (question, gaps) -> card; a set question covers several products
    for q, item, urls in _detail_pages(ps, stats, win_urls):
        winners = [(u, f) for u in urls for f in [page_gap.facts(u)] if f]
        if not winners:
            continue                     # not fetched yet, or every page blocked us
        mine = page_gap.facts(item['url'])
        raw = json.loads(item.get('raw_json') or '{}')
        own_text = mine['text'] if mine else item['title'] + ' ' + _strip_html(raw.get('body_html'))
        missing, data = page_gap.gaps(q, own_text, mine, [f for _, f in winners])
        if not mine:
            data = []                    # we could not read your live page, so we can't judge its data
        if not missing and not data:
            continue
        hosts = {}
        for u, _ in winners:
            hosts.setdefault(urllib.parse.urlsplit(u).netloc.removeprefix('www.'), u)
        sites = ', '.join('<a class="opp-link" href="%s" target="_blank" rel="noopener">%s</a>'
                          % (E(u), E(h)) for h, u in hosts.items())
        parts = []
        if missing:
            parts.append('mention <b>%s</b>' % E(', '.join(missing)))
        if data:
            parts.append('publish %s in their product data' % ', '.join('<b>%s</b>' % E(d) for d in data))
        reviews = [f['reviews'] for _, f in winners if f.get('reviews')]
        extra = (' The most-reviewed shows <b>%s</b> reviews.' % format(max(reviews), ',')) if 'a review rating' in data and reviews else ''
        card = found.setdefault((q, tuple(missing), tuple(data)), dict(
            type='details', key=q, weight=stats[q]['theirs'] * (len(missing) + len(data)),
            impact='high' if len(missing) >= 3 or 'a review rating' in data else 'medium',
            products=[], q=q, sites=sites, parts=parts, extra=extra))
        card['products'].append(item['title'])
    out = []
    for card in found.values():
        names = card.pop('products')
        q, sites, parts, extra = card.pop('q'), card.pop('sites'), card.pop('parts'), card.pop('extra')
        page = ('%s page' % E(names[0])) if len(names) == 1 else ('%s and %s pages' % (', '.join(E(n) for n in names[:-1]), E(names[-1])))
        card.update(title='Add what buyers ask to your %s' % page,
                    text='For &ldquo;%s&rdquo;, the pages AI recommended instead (%s) %s. Your %s.%s'
                         % (E(q), sites, ' and '.join(parts), 'page doesn&rsquo;t' if len(names) == 1 else 'pages don&rsquo;t', extra)
                         + _answers_link(token, index.get(q), 'absent'))
        out.append(card)
    return out


def _topics(ps, stats, index, token):
    """Topics (the question groups from onboarding) where you barely appear."""
    groups = defaultdict(list)
    for q, s in stats.items():
        i = index.get(q)
        topic = ps['clusters'][i] if i is not None and i < len(ps['clusters']) else ''
        if topic:
            groups[topic].append(s)
    out = []
    for topic, rows in groups.items():
        n, own = sum(r['answers'] for r in rows), sum(r['own'] for r in rows)
        if len(rows) < 2 or not n or own / n >= .2:
            continue
        brands = sum((r['brands'] for r in rows), Counter())
        named = ', '.join('<b>%s</b>' % E(b) for b, _ in brands.most_common(3))
        out.append(dict(type='topic', key=topic, weight=n - own, impact='high' if not own else 'medium',
                        title='Improve your %s presence' % E(topic),
                        text='Across %d buyer questions about <b>%s</b>, your products appear in <b>%d of %d</b> '
                             'answers. Named most: %s.' % (len(rows), E(topic), own, n, named or 'no brand')))
    return out


def _site(url):
    import citation_explorer
    url = citation_explorer.clean_url(url or '')
    return urllib.parse.urlsplit(url).netloc.removeprefix('www.') if url else ''


def _citations(a):
    import json
    try:
        rows = json.loads(a['citations'] or '[]')
    except ValueError:
        return []
    return [c for c in rows if isinstance(c, dict) and c.get('url')]


def _squash(text):
    return ''.join(ch for ch in text.lower() if ch.isalnum())


def _off_page(domain, sites, brand_sites, lost):
    """Sites AI cites when it recommends competitors and not you. A brand's own
    site is left out: you can't get onto Cetaphil's website."""
    own = domain.removeprefix('www.')
    brand = db.brand(domain) or {}
    own_names = [n.strip() for n in [brand.get('brand_name') or ''] + (brand.get('aliases') or '').split(',') if len(n.strip()) > 2]
    out = []
    for site, s in sites.items():
        brands = {_squash(b) for b in s['brands']}
        root = _squash(site.split('.')[-2] if site.count('.') else site)
        if (s['answers'] < max(3, .05 * lost) or site == own or site.endswith('.' + own) or site in brand_sites
                or any(len(b) > 3 and (b in _squash(site) or root in b) for b in brands)):
            continue
        share = _pct(s['answers'], lost)
        retailer = site in RETAILERS or any(site.endswith('.' + r) for r in RETAILERS)
        page, _ = s['pages'].most_common(1)[0]
        named = ', '.join('<b>%s</b>' % E(b) for b, _ in s['brands'].most_common(3))
        qs = len(s['questions'])
        # What the most-cited page itself says: which of the brands AI picked
        # instead it names, and whether it names you (fetched for free in
        # the background by refresh_pages; nothing is shown until it is).
        read = ''
        f = page_gap.facts(page)
        if f:
            rivals = page_gap.names_on_page(f, [b for b, _ in s['brands'].most_common(8)])
            mine = page_gap.names_on_page(f, own_names)
            label = '&ldquo;%s&rdquo;' % E(f['title']) if f.get('title') else 'That page'
            if rivals:
                read = ' %s names %s, %s.' % (label, ', '.join('<b>%s</b>' % E(b) for b in rivals[:4]),
                                              'and you too' if mine else 'and not you')
            elif mine:
                read = ' %s names you.' % label
            why = page_gap.explained(page)
            if why:
                read += ' <span class="opp-why">%s</span>' % E(why)
        out.append(dict(type='retailer' if retailer else 'citation', key=site, weight=s['answers'], page=page,
                        brands=[b for b, _ in s['brands'].most_common(3)],
                        impact='critical' if share >= .2 else 'high' if share >= .1 else 'medium',
                        title=('Get stocked on %s' if retailer else 'Get featured on %s') % E(site),
                        text='AI cited <b>%s</b> in <b>%d</b> answers that recommended competitors and none of your '
                             'products, across %s. Named alongside it: %s. '
                             '<a class="opp-link" href="%s" target="_blank" rel="noopener">Most-cited page</a>%s'
                             % (E(site), s['answers'], _plural(qs, 'buyer question'), named or 'no brand', E(page), read)))
    return out


def _sorted(rows):
    rows.sort(key=lambda r: (ORDER[r['impact']], -r['weight'], r['title']))
    return rows


def counts(domain):
    """How many open opportunities there are, for the rail badge."""
    init()
    try:
        rows = find(domain)
    except Exception:
        return 0
    st = _statuses(domain)
    return sum(1 for r in rows if (r['type'], r['key']) not in st)


def _store(q):
    import sys
    import accounts
    import scheduler
    want = q.get('d', '')
    if not want:
        # The running app is __main__; `import app` would load a second copy whose memory is empty.
        main = sys.modules.get('__main__')
        if not hasattr(main, '_LAST_STORES'):
            import app as main
        user = accounts.current()
        want = main._LAST_STORES.get(user['id'] if user else 0, {}).get('domain', '')
    if not want:
        stores = accounts.visible(scheduler.scannable())
        want = stores[0] if len(stores) == 1 else ''
    return want if want and accounts.can_see(want) else ''


_BARS = {'high': 3, 'medium': 2}
_TICK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5 6.5 11.5 12.5 4.5"/></svg>'
_BIN = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5"/>'
        '<path d="M7 7v4M9 7v4"/></svg>')
_ICONS = {
    'setup': '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>',
    'onpage': '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/><path d="M10 12h5M10 15.5h5"/>',
    'offpage': '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z"/>',
}


def _impact(level):
    if level == 'critical':
        mark = '<span class="opp-crit" aria-hidden="true">!</span>'
    else:
        mark = '<span class="opp-bars" aria-hidden="true">%s</span>' % ''.join(
            '<i class="%s"></i>' % ('on' if k < _BARS[level] else '') for k in range(3))
    return '<span class="opp-impact opp-%s"><span class="opp-dot"></span>%s%s</span>' % (
        level, mark, level.capitalize())


def _card(r, domain, status, back):
    s = status['status'] if status else 'open'
    text = r['text']
    if status and s == 'done':
        text += before_after(domain, r, status['at'] or 0)
    if status:
        when = time.strftime('%-d %b %Y', time.localtime(status['at'] or 0))
        actions = ('<span class="opp-state">%s %s</span>'
                   '<button class="opp-btn" name="status" value="open">Reopen</button>'
                   % ('Done' if s == 'done' else 'Declined', when))
    else:
        actions = ('<button class="opp-btn" name="status" value="done">%sDone</button>'
                   '<button class="opp-btn" name="status" value="declined">%sDecline</button>' % (_TICK, _BIN))
    import content_agent
    agent_button, agent = content_agent.opportunity_button(domain, r) if s == 'open' else ('', '')
    actions += agent_button
    return """<li class="opp-card" data-search="%s">
<div class="opp-head"><span class="opp-tag">%s</span>%s</div>
<p class="opp-title">%s</p>
<p class="opp-text">%s</p>
<form class="opp-actions" method="post" action="/opportunities">
<input type="hidden" name="d" value="%s"><input type="hidden" name="kind" value="%s">
<input type="hidden" name="key" value="%s"><input type="hidden" name="back" value="%s">%s</form>%s
</li>""" % (E((r['title'] + ' ' + TYPE_LABEL[r['type']]).lower()), E(TYPE_LABEL[r['type']]),
            _impact(r['impact']), r['title'], text, E(domain), E(r['type']), E(r['key']), E(back), actions,
            agent)


BEFORE_DAYS = 14   # the "before" window: the two weeks before a fix was marked Done
MIN_AFTER = 5      # fewer answers than this since Done is too early to read


def _gone(k, status):
    kind, key = k
    subject = key.split('|')[0]
    return dict(type=kind, key=key, impact='medium', weight=0,
                title='%s: &ldquo;%s&rdquo;' % (E(TYPE_LABEL[kind]), E(subject)),
                text='This no longer shows up as a problem in the last 30 days of answers.')


def _card_questions(ps, r):
    """The buyer questions a card is about: one question, a topic's questions, or all of them."""
    qs = ps['prompts']
    if r['type'] in ('missing', 'low', 'competitor', 'position', 'prompt', 'details'):
        q = r['key'].split('|')[0]
        return [q] if q in qs else []
    if r['type'] == 'topic':
        return [q for i, q in enumerate(qs) if i < len(ps['clusters']) and ps['clusters'][i] == r['key']]
    return list(qs)     # off-page and setup cards concern the whole catalog


def _rate(domain, ps, qs, start, end):
    """(answers naming one of your products, answers) to these questions in [start, end)."""
    scans = period.done_scans(ps['id'], start, end)
    if not scans or not qs:
        return 0, 0
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    want = set(qs)
    answers = [a for a in answers if a['prompt'] in want and start <= (a['created_at'] or 0) < end]
    ids = {a['id'] for a in answers}
    named = {m['answer_id'] for m in mentions if m['answer_id'] in ids and (m['is_theirs'] or evidence.own(m, p))}
    return len(named), len(answers)


def before_after(domain, r, at):
    """One line on a Done card: how often AI named you before and after it was marked Done.

    Same questions, same engines, two windows. It shows what changed, never
    why: an answer can move for reasons that have nothing to do with the fix."""
    ps = db.get_prompt_set(domain)
    qs = _card_questions(ps, r) if ps else []
    if not qs:
        return ''
    b_hit, b_n = _rate(domain, ps, qs, at - BEFORE_DAYS * 86400, at)
    a_hit, a_n = _rate(domain, ps, qs, at, time.time() + 1)
    scope = 'this question' if len(qs) == 1 else ('these %d questions' % len(qs))
    def pct(h, n):
        return '<b>%d of %d</b> answers (%d%%)' % (h, n, round(100 * h / n)) if n else 'none of the answers (there were none)'
    if a_n < MIN_AFTER:
        after = 'Since then: %s so far, too early to compare.' % _plural(a_n, 'answer')
    else:
        d = round(100 * a_hit / a_n) - (round(100 * b_hit / b_n) if b_n else 0)
        trend = ('<span class="opp-up">up %d points</span>' % d if d > 0 else
                 '<span class="opp-down">down %d points</span>' % -d if d < 0 else 'no change')
        after = 'Since then: %s, %s.' % (pct(a_hit, a_n), trend if b_n else 'no earlier answers to compare')
    return ('<span class="opp-track"><b>Before and after.</b> Your products were named in %s to %s '
            'in the %d days before you marked this done. %s It shows what changed, not why.</span>'
            % (pct(b_hit, b_n), scope, BEFORE_DAYS, after))


def page(q):
    if not config.SHOW_OPPORTUNITIES:
        return 404, '<h1>Not found</h1>'
    init()
    domain = _store(q)
    if not domain:
        return 200, '<div class="plain-page"><h1>Opportunities</h1><p class="page-description">Choose a catalog first.</p></div>'
    refresh_pages(domain)
    rows = find(domain)
    st = _statuses(domain)
    status = q.get('status', 'open')
    if status not in ('open',) + STATUSES:
        status = 'open'
    shown = [r for r in rows if (st[(r['type'], r['key'])]['status'] if (r['type'], r['key']) in st else 'open') == status]
    if status == 'done':
        # A fix marked Done whose problem no longer shows up would otherwise
        # vanish, and that is exactly the case worth seeing.
        live = {(r['type'], r['key']) for r in rows}
        shown += [_gone(k, v) for k, v in st.items() if v['status'] == 'done' and k not in live and k[0] in TYPE_LABEL]
    by_type = Counter(r['type'] for r in shown)
    by_cat = Counter(TYPE_CATEGORY[r['type']] for r in shown)
    # Setup is always listed, as on Searchable; other groups only once they have cards.
    cats = [c for c in CATEGORIES if by_cat[c[0]] or c[0] == 'setup']
    cat = q.get('cat', '')
    if cat not in [c[0] for c in cats]:
        cat = cats[0][0] if cats else ''
    kind = q.get('type', '')
    if kind and TYPE_CATEGORY.get(kind) != cat:
        kind = ''
    d = urllib.parse.quote(domain)

    def href(**kw):
        args = dict(d=domain, status=status, cat=cat, type=kind)
        args.update(kw)
        return '/opportunities?' + urllib.parse.urlencode({k: v for k, v in args.items() if v})

    panel = ''
    for key, label, types in cats:
        is_open = key == cat
        panel += ('<a class="opp-cat%s" href="%s"><svg viewBox="0 0 24 24" aria-hidden="true">%s</svg>'
                  '<span>%s</span><em>%d</em><svg class="opp-chev" viewBox="0 0 16 16" aria-hidden="true">'
                  '<path d="%s"/></svg></a>') % (
            ' open' if is_open else '', E(href(cat=key, type='')), _ICONS[key], E(label), by_cat[key],
            'M4 6l4 4 4-4' if is_open else 'M6 4l4 4-4 4')
        if is_open:
            subs = [('', 'All', by_cat[key])] + [(t, l, by_type[t]) for t, l in types
                                                 if by_type[t] or key == 'setup']
            panel += '<div class="opp-subs">' + ''.join(
                '<a %shref="%s">%s<em>%d</em></a>' % ('aria-current="page" ' if t == kind else '',
                                                      E(href(cat=key, type=t)), E(l), n) for t, l, n in subs) + '</div>'
    if not panel:
        panel = '<p class="opp-none">Nothing here.</p>'

    listed = [r for r in shown if TYPE_CATEGORY[r['type']] == cat and (not kind or r['type'] == kind)]
    back = href()
    cards = ''.join(_card(r, domain, st.get((r['type'], r['key'])), back) for r in listed)
    if not cards:
        cards = '<li class="opp-empty">%s</li>' % {
            'open': 'No open opportunities for the last 30 days.',
            'done': 'Nothing marked done yet.', 'declined': 'Nothing declined.'}[status]
    filters = ''.join('<option value="%s"%s>%s</option>' % (k, ' selected' if k == status else '', l)
                      for k, l in (('open', 'Open'), ('done', 'Done'), ('declined', 'Declined')))
    name = (db.brand(domain) or {}).get('brand_name') or domain
    body = """<div class="opp-page" data-rail-page="opportunities" data-rail-store="%s" data-rail-name="%s">
<h1 class="sr-only">Opportunities</h1>
<aside class="opp-panel"><h2>Categories</h2>%s</aside>
<section class="opp-main">
<div class="opp-bar"><span class="opp-count">%s</span>
<form class="opp-filter" method="get" action="/opportunities"><input type="hidden" name="d" value="%s">
<label><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 4h11M4.5 8h7M6.5 12h3"/></svg><span class="sr-only">Filter</span>
<select name="status" onchange="this.form.submit()">%s</select></label></form>
<label class="opp-search"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>
<input type="search" id="opp-q" placeholder="Search..." aria-label="Search opportunities"></label></div>
<ol class="opp-list" id="opp-list">%s</ol></section></div>
<script>
(()=>{const q=document.getElementById('opp-q');q&&q.addEventListener('input',()=>{const t=q.value.trim().toLowerCase();
document.querySelectorAll('#opp-list .opp-card').forEach(c=>{c.hidden=!!t&&!c.dataset.search.includes(t)})})})();
</script>""" % (E(domain), E(name), panel, _plural(len(listed), 'opportunity').replace('opportunitys', 'opportunities'),
                E(domain), filters, cards)
    return 200, body


def act(q, form):
    if not config.SHOW_OPPORTUNITIES:
        return 404, '<h1>Not found</h1>'
    import accounts
    init()
    domain, kind, key, status = form.get('d', ''), form.get('kind', ''), form.get('key', ''), form.get('status', '')
    if not domain or not accounts.can_see(domain) or kind not in TYPE_LABEL or not key:
        return 400, '<h1>Bad request</h1>'
    with db.conn() as c:
        if status in STATUSES:
            c.execute('INSERT OR REPLACE INTO opportunity_status VALUES (?,?,?,?,?)',
                      (domain, kind, key, status, time.time()))
        else:
            c.execute('DELETE FROM opportunity_status WHERE store_domain=? AND kind=? AND key=?',
                      (domain, kind, key))
    back = form.get('back', '')
    if not back.startswith('/opportunities?'):
        back = '/opportunities?d=' + urllib.parse.quote(domain)
    return 303, back


CSS = """
.opp-track{display:block;margin-top:10px;padding:10px 12px;border-radius:8px;background:#f6f7f9;font-size:13.5px;line-height:1.5;color:var(--text,#1a2436)}
.opp-why{display:block;margin-top:6px;font-style:italic;color:var(--muted,#5b6577)}
.opp-up{color:#047857;font-weight:600}.opp-down{color:#be123c;font-weight:600}
.opp-page{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:calc(100vh - 40px);margin:-8px 0 0}
.opp-panel{border-right:1px solid var(--line,#e6e9ef);padding:6px 14px 40px 0}
.opp-panel h2{font-size:15px;font-weight:600;margin:4px 0 16px 6px;color:var(--text,#1a2436)}
.opp-cat{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;color:var(--text,#1a2436);text-decoration:none;font-size:15px;font-weight:500}
.opp-cat:hover{background:var(--tint,#f1f4f9)}
.opp-cat.open{background:var(--tint,#eef2f8)}
.opp-cat svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex:none}
.opp-cat span{flex:1}
.opp-cat em{font-style:normal;font-size:14px;color:var(--muted,#586579)}
.opp-cat .opp-chev{width:14px;height:14px;color:var(--muted,#586579)}
.opp-subs{display:grid;gap:2px;margin:6px 0 10px 30px}
.opp-subs a{display:flex;justify-content:space-between;padding:6px 10px;border-radius:7px;color:var(--muted,#586579);text-decoration:none;font-size:13.5px}
.opp-subs a:hover{background:var(--tint,#f1f4f9)}
.opp-subs a[aria-current]{background:var(--tint,#e9eef6);color:var(--text,#1a2436);font-weight:600}
.opp-subs em{font-style:normal;font-size:11px;color:var(--faint,#8b95a5)}
.opp-none{color:var(--muted);font-size:14px;margin-left:6px}
.opp-main{padding:0 0 60px 32px;max-width:760px;width:100%;justify-self:center}
.opp-bar{display:flex;align-items:center;gap:8px;margin-bottom:16px}
.opp-count{white-space:nowrap;font-size:12px;font-weight:500;padding:5px 12px;border-radius:999px;background:var(--tint,#eef2f8);color:var(--text,#1a2436);margin-right:auto}
.opp-filter label,.opp-search{display:flex;align-items:center;gap:6px;height:32px;padding:0 10px;border:1px solid var(--line,#e6e9ef);border-radius:8px;background:#fff;font-size:13px}
.opp-filter svg,.opp-search svg{width:14px;height:14px;fill:none;stroke:var(--muted,#586579);stroke-width:1.5;stroke-linecap:round;flex:none}
.opp-filter select{border:0;background:transparent;font:inherit;font-size:13px;color:var(--text,#1a2436);cursor:pointer;outline:none}
.opp-search input,#opp-q,#opp-q:focus,#opp-q:focus-visible{border:0;outline:none;box-shadow:none;border-radius:0;padding:0;height:auto;font:inherit;font-size:13px;width:160px;background:transparent}
.opp-search:focus-within{border-color:var(--ink,#0b1b35)}
.opp-list{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.opp-card{border:1px solid var(--line,#e6e9ef);border-radius:12px;background:#fff;padding:20px 24px 0}
.opp-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.opp-tag{font-size:12px;font-weight:500;padding:4px 10px;border-radius:7px;background:var(--tint,#f1f4f9);color:var(--text,#1a2436)}
.opp-impact{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--muted,#586579)}
.opp-dot{width:6px;height:6px;border-radius:50%;background:#e5484d}
.opp-medium .opp-dot{background:#e5484d;opacity:.75}
.opp-bars{display:inline-flex;align-items:flex-end;gap:2px;height:12px}
.opp-bars i{display:block;width:3px;background:#d3d8e0;border-radius:1px}
.opp-bars i:nth-child(1){height:5px}.opp-bars i:nth-child(2){height:8px}.opp-bars i:nth-child(3){height:12px}
.opp-bars i.on{background:#0b1b35}
.opp-crit{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;background:#e5484d;color:#fff;font-size:10px;font-weight:700}
.opp-title{margin:0 0 8px;font-size:15px;font-weight:600;color:var(--text,#1a2436);line-height:1.4}
.opp-text{margin:0;font-size:13px;line-height:1.55;color:var(--muted,#586579)}
.opp-text b{color:var(--text,#1a2436);font-weight:600}
.opp-link{color:var(--muted,#586579);text-decoration:underline;text-underline-offset:2px}
.opp-actions{display:flex;align-items:center;gap:8px;margin:20px -24px 0;padding:14px 24px;border-top:1px solid var(--line,#eef0f4)}
.opp-btn{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border:1px solid var(--line,#e6e9ef);border-radius:8px;background:#fff;font:inherit;font-size:12.5px;color:var(--text,#1a2436);cursor:pointer}
.opp-btn:hover{background:var(--tint,#f4f6fa)}
.opp-btn svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.opp-state{font-size:12.5px;color:var(--muted,#586579);margin-right:4px}
.opp-empty{padding:32px;text-align:center;color:var(--muted,#586579);border:1px dashed var(--line,#e6e9ef);border-radius:12px;font-size:14px}
.rail-badge{margin-left:auto;font-size:11px;font-weight:700;background:#0b1b35;color:#fff;border-radius:999px;padding:1px 7px}
@media (max-width:860px){.opp-page{grid-template-columns:1fr}.opp-panel{border-right:0;border-bottom:1px solid var(--line,#e6e9ef);padding:0 0 12px}
.opp-main{padding:16px 0 40px}.opp-bar{flex-wrap:wrap}.opp-search input{width:110px}}
"""
