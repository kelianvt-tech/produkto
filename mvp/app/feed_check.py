"""Feed readiness: can AI shopping tools read the store's product data at all?

Day 21 of mvp/content-agent/PLAN.md. Shown as "Product Data" cards on the
Opportunities page (On Page). Free: plain requests only, no AI call.

  Crawlers   robots.txt must let the crawlers behind AI answers into product
             pages: OAI-SearchBot and ChatGPT-User (ChatGPT search),
             PerplexityBot, Googlebot (AI Overviews, Shopping), Bingbot (Copilot).
  Markup     each product page's machine-readable product data (JSON-LD):
             is there any, does it state price and stock, a barcode (GTIN),
             a review rating.
  Barcodes   whether the catalog itself has barcodes, so the card says where
             the fix is: add barcodes in Shopify, or the theme leaves them out.
  Policies   refund and shipping policy pages at Shopify's standard addresses,
             plus terms of service and privacy policy, which Shopify requires
             before it shares a store's products with ChatGPT.
  ChatGPT    (22 Oct 2026) Shopify shares products with ChatGPT through Shopify
             Catalog, on by default for stores selling to US customers, but only
             with Terms of service, Privacy policy and Return and refund policy
             filled in (help.shopify.com/en/manual/online-sales-channels/
             agentic-storefronts/chatgpt, read 22 Oct 2026). We can't read the
             channel switch itself, so with the policies in place the card is a
             one-time check the merchant marks Done.
  Country    (22 Oct 2026) the store's country orders the cards. US ChatGPT
             Shopping reads merchant feeds (Shopify Catalog); outside the US it
             still picks from Google Shopping (Peec AI: OpenAI debug logs, Oct
             2026, and 43,000 carousel products, early 2026; vendor evidence).
             See mvp/content-agent/RESEARCH-PEEC-CHATGPT-SHOPPING-2026-10-22.md.

Results are cached per store for a day (`feed_checks`) and refreshed in the
background with the Opportunities page's other page reads; cards() only reads
the cache, so the page never waits on the network.

Copy rule: say what the pages show and where to fix it. Never promise that a
fix moves visibility.
"""
import json
import time
from collections import defaultdict
import urllib.parse
import urllib.robotparser
from html import escape as E

import db
import page_gap

TTL = 86400
MAX_PAGES = 40            # own product pages checked per store
CRAWLERS = (('OAI-SearchBot', 'ChatGPT search'), ('ChatGPT-User', 'ChatGPT, when a user asks it to open a page'),
            ('PerplexityBot', 'Perplexity'), ('Googlebot', 'Google, including AI Overviews and Shopping'),
            ('Bingbot', 'Bing, which Copilot reads'))
POLICIES = (('refund', '/policies/refund-policy', 'refund policy'),
            ('shipping', '/policies/shipping-policy', 'shipping policy'))
# What Shopify needs before it shares products with ChatGPT (Shopify Help Center, read 22 Oct 2026).
CHATGPT_POLICIES = (('terms', '/policies/terms-of-service', 'Terms of service'),
                    ('privacy', '/policies/privacy-policy', 'Privacy policy'),
                    ('refund', '/policies/refund-policy', 'Return and refund policy'))


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS feed_checks (store_domain TEXT PRIMARY KEY, data TEXT, at REAL)')


def _snapshot(domain):
    ps = db.get_prompt_set(domain)
    return (ps or {}).get('catalog_snapshot') or []


def _barcodes(item):
    try:
        variants = json.loads(item.get('raw_json') or '{}').get('variants') or []
    except ValueError:
        return False
    return any((v.get('barcode') or '').strip() for v in variants if isinstance(v, dict))


def blocked_crawlers(robots_txt, path):
    """[crawler name] that robots.txt keeps out of `path`."""
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return [name for name, _ in CRAWLERS if not rp.can_fetch(name, path)]


def run(domain):
    """Check the store now (a few seconds to a minute) and cache the result."""
    init()
    items = [i for i in _snapshot(domain) if i.get('url')][:MAX_PAGES]
    sample = urllib.parse.urlsplit(items[0]['url']).path if items else '/products/'
    try:
        robots = page_gap.fetch('https://%s/robots.txt' % domain)
        blocked = blocked_crawlers(robots, sample)
        robots_ok = True
    except Exception:                                   # noqa: BLE001 - no robots.txt means nothing is blocked
        blocked, robots_ok = [], False
    policies = {}
    for key, path, _ in POLICIES + CHATGPT_POLICIES[:2]:
        try:
            policies[key] = len(page_gap.parse(page_gap.fetch('https://%s%s' % (domain, path)))['text']) > 200
        except Exception:                               # noqa: BLE001 - a 404 means there is no page
            policies[key] = False
    page_gap.fetch_all([i['url'] for i in items], limit=MAX_PAGES)
    pages = []
    for i in items:
        f = page_gap.facts(i['url'])
        if f is not None:
            pages.append(dict(url=i['url'], title=i.get('title', ''), product=f.get('product', False),
                              price=f.get('price', False), availability=f.get('availability'),
                              gtin=f.get('gtin', False), rating=f.get('rating', False), barcode=_barcodes(i),
                              id=i.get('id'), review_app=f.get('review_app'), qa=f.get('qa')))
    data = dict(blocked=blocked, robots_read=robots_ok, sample_path=sample, policies=policies, pages=pages)
    db.write('INSERT INTO feed_checks(store_domain,data,at) VALUES(?,?,?) ON CONFLICT(store_domain) DO UPDATE SET '
             'data=excluded.data, at=excluded.at', (domain, json.dumps(data), time.time()))
    return data


def refresh(domain):
    """Run the check if the cached one is older than a day. Call from a background thread."""
    init()
    row = db.one('SELECT at FROM feed_checks WHERE store_domain=?', (domain,))
    if not row or time.time() - (row['at'] or 0) > TTL:
        run(domain)


def cached(domain):
    init()
    row = db.one('SELECT data FROM feed_checks WHERE store_domain=?', (domain,))
    return json.loads(row['data']) if row else None


def _names(pages, n=3):
    shown = ', '.join(E(p['title']) for p in pages[:n])
    return shown + (' and %d more' % (len(pages) - n) if len(pages) > n else '')


def _qa_card(domain, pages):
    """(key, impact, weight, title, text) for product pages with no questions section, listing the buyer questions
    each one fits, or None. The questions come from the store's own tracked buyer questions, so this is free."""
    ps = db.get_prompt_set(domain)
    if not ps or not pages:
        return None
    by_id = defaultdict(list)
    for q, ids in zip(ps.get('prompts') or [], ps.get('relevance') or []):
        for pid in ids or []:
            by_id[pid].append(q)
    fits = [(p, by_id[p['id']]) for p in pages if by_id.get(p.get('id'))]
    if not fits:
        return None
    fits.sort(key=lambda x: -len(x[1]))
    p, qs = fits[0]
    shown = ''.join('<br>&bull; %s' % E(q) for q in qs[:3])
    return ('customer-qa', 'medium', len(fits),
            'Add a customer Q&amp;A to %s' % ('%d product pages' % len(fits) if len(fits) > 1 else E(p['title'])),
            '%s %s no questions section. Buyers ask AI questions like these about %s:%s<br>'
            'Answer them on the page, in a Q&amp;A or FAQ block. Questions your own customers send you count too. '
            'The Product page fixes agent can draft the answers from your product facts.'
            % (_names([f[0] for f in fits]), 'has' if len(fits) == 1 else 'have', E(p['title']), shown))


def cards(domain):
    """Opportunities (type 'feed') from the cached check. Nothing if the store was never checked."""
    data = cached(domain)
    if not data:
        return _third_party(domain)
    out = []

    def add(key, impact, weight, title, text):
        out.append(dict(type='feed', key=key, impact=impact, weight=weight, title=title, text=text))

    labels = dict(CRAWLERS)
    if data['blocked']:
        add('robots', 'critical', len(data['blocked']), 'Let AI crawlers read your product pages',
            'Your robots.txt keeps %s out of <b>%s</b>, so those tools can\'t read your product pages '
            'directly. In Shopify this is the <b>robots.txt.liquid</b> theme file.' % (
                '; '.join('<b>%s</b> (%s)' % (E(n), E(labels[n])) for n in data['blocked']),
                E(data['sample_path'])))
    pages = data['pages']
    n = len(pages)
    if n:
        none = [p for p in pages if not p['product']]
        if none:
            add('markup', 'high', len(none), 'Add product data to %d of %d product pages' % (len(none), n),
                '%s publish no machine-readable product data (JSON-LD), so a crawler has to guess name, price '
                'and stock from the page text. Most Shopify themes add it; yours leaves it out.' % _names(none))
        marked = [p for p in pages if p['product']]
        offers = [p for p in marked if not p['price'] or p.get('availability') is False]
        if offers:
            add('offers', 'high', len(offers), 'State price and stock in your product data',
                '%s publish product data without a price or stock status. Shopping tools read both from that data.'
                % _names(offers))
        gtin = [p for p in marked if not p['gtin']]
        if gtin:
            in_catalog = [p for p in gtin if p['barcode']]
            where = ('Your catalog has barcodes for %d of them, so the theme is leaving them out of the page data.'
                     % len(in_catalog)) if in_catalog else \
                'Your catalog has none either: add them in Shopify under each variant\'s <b>Barcode</b> field.'
            add('gtin', 'medium', len(gtin), 'Publish barcodes (GTIN) on %d of %d product pages' % (len(gtin), n),
                '%s publish no barcode. Google Shopping asks for the GTIN of any product that has one. %s'
                % (_names(gtin), where))
        # Reviews (19 Oct 2026, from mvp/content-agent/PRODUCT-PAGE-RESEARCH-2026-10-19.md): every top product
        # page studied shows customer reviews. Pages checked before that date have no review_app value: skip them.
        known = [p for p in pages if p.get('review_app') is not None]
        no_reviews = [p for p in known if not p['review_app'] and not p['rating']]
        if no_reviews:
            add('show-reviews', 'high' if len(no_reviews) == len(known) else 'medium', len(no_reviews),
                'Show customer reviews on %d of %d product pages' % (len(no_reviews), len(known)),
                '%s show no customer reviews. AI answers often repeat what reviewers say about fit, results or '
                'quality, and the top product pages we studied all show them. A review app (Judge.me, Okendo, '
                'Yotpo and others) adds them to the page and to its product data.' % _names(no_reviews))
        rating = [p for p in marked if not p['rating'] and p.get('review_app')]
        if rating and len(rating) == len([p for p in marked if p.get('review_app')]):
            add('reviews', 'medium', len(rating), 'Publish your review ratings as product data',
                'Your product pages show reviews but don\'t publish the rating in their product data, so crawlers '
                'can\'t read it. Most review apps have a setting to add it.')
        elif not known and len([p for p in marked if not p['rating']]) == len(marked) and marked:
            add('reviews', 'medium', len(marked), 'Publish your review ratings as product data',
                'None of your product pages publish a review rating in their product data, so crawlers can\'t '
                'read your ratings. If you collect reviews, most review apps can add it.')
        qa = _qa_card(domain, [p for p in pages if p.get('qa') is False])
        if qa:
            add(*qa)
    us = is_us(domain)
    chatgpt = _chatgpt_card(data, us)
    for key, path, label in POLICIES:
        if data['policies'].get(key) is False and not (chatgpt and key in chatgpt.get('covers', ())):
            add('policy-' + key, 'medium', 1, 'Publish a %s page' % label,
                'No %s found at <b>%s</b>. Buyers ask about it before they buy. Shopify can generate one in '
                '<b>Settings &gt; Policies</b>.' % (label, E(path)))
    if chatgpt:
        chatgpt.pop('covers', None)
        out.append(chatgpt)
    return by_country(out + _third_party(domain), us)


def is_us(domain):
    """The store's country is the US, or unknown (most of our customers are American)."""
    return ((db.brand(domain) or {}).get('country') or 'US').strip().upper() in ('US', 'USA', '')


def _chatgpt_card(data, us):
    """Can Shopify share this store's products with ChatGPT? Missing policies are a fact we can see;
    otherwise the channel switch is something only the merchant can check, once."""
    pol = data.get('policies') or {}
    missing = [(key, path, label) for key, path, label in CHATGPT_POLICIES if pol.get(key) is False]
    who = '' if us else ' This applies if you sell to customers in the US.'
    if missing:
        names = ', '.join('<b>%s</b> (%s)' % (E(label), E(path)) for _, path, label in missing)
        return dict(type='feed', key='chatgpt-policies', impact='critical' if us else 'high', weight=len(missing) + 100,
                    covers=tuple(k for k, _, _ in missing),
                    title='Add the policies ChatGPT needs to list your products',
                    text='Shopify only shares your products with ChatGPT when your Terms of service, Privacy policy '
                         'and Return and refund policy are filled in. We couldn\'t find your %s. Add %s in Shopify '
                         'under <b>Settings &gt; Policies</b>.%s' % (names, 'it' if len(missing) == 1 else 'them', who))
    if not all(pol.get(k) for k, _, _ in CHATGPT_POLICIES[:2]):
        return None                                     # checked before 22 Oct 2026: wait for the next check
    return dict(type='feed', key='chatgpt-catalog', impact='high' if us else 'medium', weight=100,
                title='Check that ChatGPT can see your products',
                text='ChatGPT reads your products straight from Shopify for its shopping results. Shopify turns this '
                     'on by default for stores that sell to US customers. To check, open <b>Sales channels &gt; '
                     'Agentic</b> in Shopify, click <b>ChatGPT</b> and make sure <b>Shopify Catalog access</b> is on, '
                     'then mark this done.%s' % who)


def by_country(cards, us):
    """Order Product Data cards by where the store sells. Outside the US, ChatGPT's product results come from
    Google Shopping, so being there is the gate; in the US, ChatGPT reads Shopify's product data directly."""
    for c in cards:
        if c['key'] == 'google-shopping':
            if not us:
                c['impact'] = 'critical'
                c['text'] += (' Outside the US, ChatGPT also picks the products it shows from Google Shopping, so this '
                              'is where it would find yours.')
        elif c['key'] == 'gtin' and us:
            c['text'] += ' ChatGPT\'s shopping results read barcodes too.'
    return cards


def _third_party(domain):
    """Google Shopping, listing numbers and Trustpilot cards from the admin pull (third_party.py, 22 Oct 2026)."""
    try:
        import third_party
        return third_party.cards(domain)
    except Exception:                       # noqa: BLE001 - never blocks the page
        return []


if __name__ == '__main__':
    import sys
    print(json.dumps(run(sys.argv[1]), indent=1)[:3000])
    for c in cards(sys.argv[1]):
        print(c['impact'], c['title'])
