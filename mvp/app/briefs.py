"""Briefs: what the content agent needs to know before it drafts a fix.

Day 3 of mvp/content-agent/PLAN.md. A brief turns one Opportunity into:

  * the buyer questions it is about, with how the store does on each now
    (answers in the last 30 days, how many named the merchant's products,
    how many named a competitor instead);
  * the merchant's products those questions are about, each with its
    catalog facts record (catalog_facts.py) - the only facts a draft may use;
  * the competitor products AI named instead, how often, and what their
    pages say (page_gap's cached page facts, when we could read them).

Nothing here calls an AI model or costs money: it reuses answers already
collected and pages already fetched.

Day 17 (16 Oct): research sources. Building a brief now also reads (free,
plain request, cached 14 days) the competitor pages not fetched yet, and the
web pages AI cited most when answering these questions (review articles,
retailer pages, guides), so a draft knows what the pages AI trusts cover.
Those cited pages are research only: drafts may use them to decide what to
cover, never as a source of facts about the store's products. Top Google
results are not read yet: that needs a paid search actor.

Day 4: choose_types() picks what to write, by written rules (no AI call), and
says why in plain words for the calendar's detail panel. When no rule matches,
the helper model picks instead (added 15 Oct), and the reason says so.
"""
import json
import re
import time
import urllib.parse
from collections import Counter, defaultdict

import catalog_facts
import db
import evidence
import opportunities
import page_gap
import period
import storetime

# Opportunity types a page or article on the merchant's own site can address.
# Left out: stale scans, question quality, Sites to get onto (other people's
# sites) and Keep your top spot (nothing is missing).
BRIEFABLE = ('missing', 'low', 'competitor', 'details', 'topic')
MAX_COMPETITORS = 8
MAX_CITED = 4          # cited pages kept in a brief
READ_NEW = 4           # uncached pages fetched per kind per brief, so drafting stays quick
_TAGS = re.compile(r'<[^>]+>')


def _plain(html_text):
    import html
    return re.sub(r'\s+', ' ', html.unescape(_TAGS.sub('', html_text or ''))).strip()


def _evidence(domain):
    """(prompt set, per-question stats, per-question competitor wins, per-question cited pages)
    for the last 30 days."""
    ps = db.get_prompt_set(domain)
    if not ps:
        return None, {}, {}, {}
    _, _, start, end = period.bounds(opportunities.WINDOW, tz=storetime.zone(domain))
    scans = period.done_scans(ps['id'], start, end)
    if not scans:
        return ps, {}, {}, {}
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    by_answer = defaultdict(list)
    for m in mentions:
        by_answer[m['answer_id']].append(m)
    stats, wins, cites = {}, defaultdict(Counter), defaultdict(Counter)
    for a in answers:
        try:
            urls = {page_gap.clean(c.get('url')) for c in json.loads(a.get('citations') or '[]') if isinstance(c, dict)}
        except ValueError:
            urls = set()
        cites[a['prompt']].update(u for u in urls if u)
        ms = by_answer.get(a['id'], [])
        mine = [m for m in ms if m['is_theirs'] or evidence.own(m, p)]
        theirs = [m for m in ms if m not in mine]
        s = stats.setdefault(a['prompt'], dict(answers=0, own=0, theirs=0))
        s['answers'] += 1
        s['own'] += bool(mine)
        s['theirs'] += bool(theirs)
        for m in theirs:
            wins[a['prompt']][((m['brand'] or '').strip(), (m['product_name'] or '').strip(),
                               page_gap.clean(m['url']) if m['url'] else '')] += 1
    return ps, stats, wins, cites


def _questions(ps, opp):
    if opp['type'] == 'topic':
        return [q for i, q in enumerate(ps['prompts']) if i < len(ps['clusters']) and ps['clusters'][i] == opp['key']]
    return [opp['key']] if opp['key'] in ps['prompts'] else []


def _products(ps, questions, domain):
    """The merchant's products these questions are about, with their catalog facts."""
    snap = {c['id']: c for c in ps['catalog_snapshot']}
    index = {q: i for i, q in enumerate(ps['prompts'])}
    ids = []
    for q in questions:
        i = index[q]
        for pid in (ps['relevance'][i] if i < len(ps['relevance']) else []):
            if pid in snap and pid not in ids:
                ids.append(pid)
    facts = {r['handle']: r for r in catalog_facts.get(domain)}
    out = []
    for pid in ids:
        item = snap[pid]
        rec = facts.get(item['handle'])
        out.append(dict(handle=item['handle'], title=item['title'], url=item['url'], image=item.get('image') or '',
                        facts=rec['facts'] if rec else [],
                        description=rec['description'] if rec else [],
                        facts_ready=bool(rec)))
    return out


def _competitors(questions, wins):
    total = Counter()
    for q in questions:
        total.update(wins.get(q, {}))
    picked = []
    import insight_panels
    for (brand, name, url), n in total.most_common():
        if not brand and not name:
            continue
        if not url and brand:
            # Named without a link: use the page found earlier on the brand's own store, if any.
            site = insight_panels.brand_site(dict(brand=brand, url='', name=name))
            url = opportunities._page_of(('', site, name))
        picked.append((brand, name, url, n))
        if len(picked) >= MAX_COMPETITORS:
            break
    _read([url for _, _, url, _ in picked])
    out = []
    for brand, name, url, n in picked:
        page = page_gap.facts(url) if url else None
        out.append(dict(brand=brand, product=name, url=url, named=n,
                        page_read=bool(page),
                        page_title=(page or {}).get('title', ''),
                        page_excerpt=((page or {}).get('text') or '')[:1500],
                        reviews=(page or {}).get('reviews', 0)))
    return out


def _read(urls):
    """Fetch the pages not cached yet (free; at most READ_NEW per call). A page that blocks us stays unread."""
    try:
        page_gap.fetch_all([u for u in urls if u], limit=READ_NEW)
    except Exception:                                           # noqa: BLE001 - reading is a bonus, never a blocker
        pass


def _host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith('www.') else h


def _cited(questions, cites, domain, skip):
    """The pages AI cited most for these questions, not the store's own and not a competitor product
    page already in the brief, with what they say when we could read them."""
    total = Counter()
    for q in questions:
        total.update(cites.get(q, {}))
    own = _host('https://' + domain)
    urls = [u for u, _ in total.most_common() if u not in skip and _host(u) != own
            and not _host(u).endswith('.' + own)][:MAX_CITED]
    _read(urls)
    # Pages cached before 18 Oct have no shape yet: read those again (free, same limit).
    stale = [u for u in urls if (page_gap.facts(u) or {}).get('shape') is None and page_gap.facts(u)]
    if stale:
        db.write('UPDATE page_facts SET fetched_at=0 WHERE url IN (%s)' % ','.join('?' * len(stale)),
                 tuple(page_gap.clean(u) for u in stale))
        _read(stale)
    out = []
    for u in urls:
        page = page_gap.facts(u)
        out.append(dict(url=u, site=_host(u), cited=total[u], page_read=bool(page),
                        page_title=(page or {}).get('title', ''),
                        page_excerpt=((page or {}).get('text') or '')[:1200],
                        shape=(page or {}).get('shape')))
    return out


# Sites AI tends to cite for who they are (18 Oct 2026): big retailers, health authorities, major publishers,
# encyclopedias. A small DTC brand rarely out-ranks them, so questions they dominate are harder to win. An
# estimate from the names alone (no paid authority data), shown as a guide, never as a promise.
BIG_SITES = set('''amazon.com amazon.co.uk walmart.com target.com costco.com ebay.com bestbuy.com homedepot.com
lowes.com ikea.com wayfair.com sephora.com ulta.com boots.com nordstrom.com macys.com johnlewis.com
lookfantastic.com cultbeauty.co.uk superdrug.com cvs.com walgreens.com chewy.com petco.com petsmart.com
healthline.com webmd.com mayoclinic.org clevelandclinic.org medicalnewstoday.com verywellhealth.com
aad.org nhs.uk who.int hopkinsmedicine.org harvard.edu
wikipedia.org nytimes.com wirecutter.com forbes.com theguardian.com bbc.co.uk bbc.com cnn.com washingtonpost.com
businessinsider.com insider.com consumerreports.org goodhousekeeping.com vogue.com allure.com byrdie.com
elle.com harpersbazaar.com cosmopolitan.com glamour.com refinery29.com womenshealthmag.com menshealth.com gq.com
esquire.com self.com thestrategist.com nymag.com usatoday.com today.com people.com buzzfeed.com
techradar.com cnet.com tomsguide.com pcmag.com theverge.com rtings.com youtube.com'''.split())


def _big(host):
    return host in BIG_SITES or any(host.endswith('.' + b) for b in BIG_SITES) or host.endswith(('.gov', '.edu'))


def winnable(questions, cites):
    """How much of what AI cites for these questions comes from big, established sites.
    {level: 'winnable'|'mixed'|'hard'|'', big_share: 0-100, big: [sites], small: [sites]}."""
    total = Counter()
    for q in questions:
        total.update(cites.get(q, {}))
    hosts = Counter()
    for u, n in total.items():
        hosts[_host(u)] += n
    n = sum(hosts.values())
    if not n:
        return dict(level='', big_share=0, big=[], small=[])
    big = sum(v for h, v in hosts.items() if _big(h))
    share = round(100 * big / n)
    return dict(level='winnable' if share < 40 else 'mixed' if share < 70 else 'hard', big_share=share,
                big=[h for h, _ in hosts.most_common() if _big(h)][:4],
                small=[h for h, _ in hosts.most_common() if not _big(h)][:4])


def build(domain, opp_type, opp_key):
    """The brief for one Opportunity, or None if it isn't one the agent can write for."""
    if opp_type not in BRIEFABLE:
        return None
    opp = next((r for r in opportunities.find(domain) if r['type'] == opp_type and r['key'] == opp_key), None)
    if not opp:
        return None
    ps, stats, wins, cites = _evidence(domain)
    if not ps:
        return None
    page_gap.init()
    questions = _questions(ps, opp)
    competitors = _competitors(questions, wins)
    return dict(
        store=domain,
        opportunity=dict(type=opp_type, key=opp_key, impact=opp.get('impact', ''),
                         title=_plain(opp.get('title')), text=re.sub(r'\s*Read the answers\.?$', '', _plain(opp.get('text')))),
        questions=[dict(question=q, **stats.get(q, dict(answers=0, own=0, theirs=0))) for q in questions],
        products=_products(ps, questions, domain),
        competitors=competitors,
        cited_pages=_cited(questions, cites, domain, {c['url'] for c in competitors if c['url']}),
        winnable=winnable(questions, cites),
        built_at=time.time(),
    )


# "or" alone is too loose ("cleanse gently or hydrate" is one shopping wish), so a
# choice needs a choosing word: "choose a face oil or a moisturiser".
_COMPARE = re.compile(r"\b(vs\.?|versus|better|compare|comparison|instead of|difference|between)\b"
                      r"|\b(choose|pick|go for|opt for)\b.+\bor\b", re.I)
_GUIDE = re.compile(r"\b(routine|set|kit|bundle|steps?|starter|what do i need|everything)\b", re.I)
_DIRECT = re.compile(r"^(is|are|can|does|do|should|will|how)\b", re.I)


TYPE_NAMES = {'product_fix': 'product-page fix', 'faq': 'FAQ on the product page', 'comparison': 'comparison page',
              'guide': 'buying guide (blog)', 'collection': 'collection page copy'}

PICK_RULES = """You choose what an online store should write so its page answers the buyer questions shoppers ask AI assistants.
Pick 1-2 types from the list, best first, and give each a one-sentence reason a store owner understands (no jargon, no mention of AI models).
A product-page fix or FAQ needs one of the store's products; with none listed, choose a buying guide."""


def _ai_pick(brief, usage=None):
    """Ask the helper model when no rule matched. Returns [(type, reason)] or [] if the call fails."""
    import llm
    schema = {"type": "object", "additionalProperties": False, "required": ["picks"], "properties": {
        "picks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "required": ["type", "reason"], "properties": {
                      "type": {"type": "string", "enum": list(TYPE_NAMES)}, "reason": {"type": "string"}}}}}}
    text = ('TYPES:\n%s\n\nBUYER QUESTIONS:\n%s\n\nSTORE PRODUCTS INVOLVED:\n%s\n\nOPPORTUNITY: %s'
            % ('\n'.join('- %s: %s' % kv for kv in TYPE_NAMES.items()),
               '\n'.join('- ' + q['question'] for q in brief['questions']),
               '\n'.join('- ' + p['title'] for p in brief['products']) or '(none)',
               brief['opportunity'].get('text') or brief['opportunity']['type']))
    try:
        picks = llm.json_call(PICK_RULES, text, 'pick_type', schema, usage=usage, attempts=2)['picks']
    except Exception:
        return []
    out = []
    for k in picks:
        if k['type'] in ('product_fix', 'faq') and not brief['products']:
            continue
        if k['type'] not in [t for t, _ in out]:
            out.append((k['type'], k['reason'] + ' (chosen by AI: no written rule matched)'))
    return out


def choose_types(brief, usage=None):
    """[(draft type, reason)], best first. Written rules first, so the choice is explainable;
    only when none matches does the helper model pick (a fraction of a cent), and the reason says so."""
    qs = [q['question'] for q in brief['questions']]
    prods = brief['products']
    kind = brief['opportunity']['type']
    out = []

    def add(t, why):
        if t not in [x[0] for x in out]:
            out.append((t, why))

    text = ' '.join(qs)
    if kind == 'details' and prods:
        add('product_fix', 'The pages AI picked instead state details your %s page leaves out.' % prods[0]['title'])
    if _COMPARE.search(text) and qs:
        add('comparison', 'The buyer is choosing between options, so a side-by-side page answers it directly.')
    if kind == 'topic' or len(prods) >= 3 or _GUIDE.search(text):
        add('guide', 'The question spans several products, so one guide can cover them and link to each.')
    if prods and len(prods) <= 2:
        add('product_fix', 'AI recommends products whose pages state what the buyer asks; this makes '
                           '%s state it too, using only facts your catalog already has.' % prods[0]['title'])
    if any(_DIRECT.search(q) for q in qs) and prods:
        add('faq', 'The buyer asks a direct question, so an FAQ on the product page answers it in their words.')
    types = {p.get('handle') for p in prods}
    if len(prods) >= 3 and types:
        add('collection', 'Several of your products answer this, so the collection page can explain how to choose.')
    if not out:
        out = _ai_pick(brief, usage)
    if not out:
        add('guide' if not prods else 'product_fix', 'Default for this kind of opportunity.')
    return out


def save(brief, draft_type=None):
    """Store a brief; returns its id. Without a type, the first choose_types() pick is used."""
    draft_type = draft_type or choose_types(brief)[0][0]
    import content_agent
    content_agent.init()
    first = (brief['products'] or [{}])[0]
    with db.conn() as c:
        cur = c.execute(
            'INSERT INTO content_briefs (store_domain, opportunity_kind, opportunity_key, draft_type, target_kind, '
            'target_id, target_url, target_title, questions, competitors, data, created_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (brief['store'], brief['opportunity']['type'], brief['opportunity']['key'], draft_type,
             'product' if first else 'blog', first.get('handle'), first.get('url'), first.get('title'),
             json.dumps(brief['questions']), json.dumps(brief['competitors']), json.dumps(brief), time.time()))
        return cur.lastrowid


def candidates(domain):
    """Every open Opportunity the agent could write a fix for, most important first."""
    st = opportunities._statuses(domain)
    return [r for r in opportunities.find(domain) if r['type'] in BRIEFABLE
            and st.get((r['type'], r['key']), {'status': 'open'})['status'] == 'open']


if __name__ == '__main__':
    import sys
    d = sys.argv[1]
    for r in candidates(d)[:3]:
        b = build(d, r['type'], r['key'])
        print(choose_types(b))
        print(json.dumps(dict(b, products=[dict(p, description=p['description'][:2]) for p in b['products']],
                              competitors=[dict(c, page_excerpt=c['page_excerpt'][:120]) for c in b['competitors']]),
                         indent=1)[:2500])
        print('---')
