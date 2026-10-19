"""Buyer question suggestions: what to add, and what to swap (18 Oct 2026).

Lives under Buyer questions > Suggestions. Two kinds of card:

  swap   a tracked question that makes a poor test, with a better one in its place. Evidence from our own
         answers: AI names products in almost none of its answers (it gives general advice, so nothing can
         win it), or the question copies the product page, names the brand, stacks too many requirements
         or reads like a keyword (the checks that used to be "Improve buyer question" in Opportunities).
  add    a new question worth tracking, while the store is under its plan's cap. Sources: the store's own
         ingredients and materials, where it is and ships to, competitors AI keeps naming, questions on the
         pages AI cites, the buyer journey stages nobody tracks yet, and the season ahead.

Kelian's points, kept as rules: specific (ingredient, material, location) questions are where a small brand
can win, but they must be phrased the way a buyer asks, never copied from the product page, or they only
measure the page describing itself. Nobody knows real prompt volumes (Promptwatch, Oct 2026), so the goal
is covering the buyer journey with enough variety.

A swap edits the question: the new one starts its own trend line, the old one's history stays.
Suggestions are refreshed at most once a week, in the background; one helper-model call (about a cent).
"""
import json
import re
import threading
import time
from collections import Counter
from html import escape as E

import db
import storetime

REFRESH = 7 * 86400
DEAD = 0.15              # products named in fewer than 15% of answers: AI answers with general advice
MAX_ADDS, MAX_SWAPS = 8, 5
SOURCES = {'ingredient': 'Ingredient', 'material': 'Material', 'location': 'Location', 'competitor': 'Competitor',
           'cited': 'Cited page', 'journey': 'Buyer journey', 'season': 'Season', 'catalog': 'Catalog gap'}
_running = set()


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS question_suggestions (id INTEGER PRIMARY KEY, store_domain TEXT NOT NULL, '
                  'kind TEXT NOT NULL, old_q TEXT, new_q TEXT NOT NULL, reason TEXT, evidence TEXT, source TEXT, '
                  "products TEXT, status TEXT NOT NULL DEFAULT 'open', created_at REAL, decided_at REAL)")


def open_rows(domain):
    init()
    return db.all_("SELECT * FROM question_suggestions WHERE store_domain=? AND status='open' "
                   "ORDER BY kind DESC, id", (domain,))


def count(domain):
    try:
        return len(open_rows(domain))
    except Exception:                                            # noqa: BLE001 - a badge never breaks the rail
        return 0


def _fresh(domain):
    init()
    row = db.one('SELECT MAX(created_at) t FROM question_suggestions WHERE store_domain=?', (domain,))
    return bool(row and row['t'] and time.time() - row['t'] < REFRESH)


# ---- evidence ------------------------------------------------------------------------------

def _stats(domain):
    """question -> {answers, own, named}: answers in the last 30 days, ones naming the store, ones naming
    any product at all."""
    import evidence
    import opportunities
    import period
    ps = db.get_prompt_set(domain)
    _, _, start, end = period.bounds(opportunities.WINDOW, tz=storetime.zone(domain))
    scans = period.done_scans(ps['id'], start, end)
    if not scans:
        return {}
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    named, own = Counter(), Counter()
    by = {}
    for m in mentions:
        by.setdefault(m['answer_id'], []).append(m)
    out = {}
    for a in answers:
        ms = by.get(a['id'], [])
        s = out.setdefault(a['prompt'], dict(answers=0, own=0, named=0))
        s['answers'] += 1
        s['named'] += bool(ms)
        s['own'] += any(m['is_theirs'] or evidence.own(m, p) for m in ms)
    return out


def _quality(domain):
    """question -> plain reasons it makes a poor test (opportunities' question checks, as text)."""
    import opportunities
    out = {}
    for r in opportunities.find(domain, questions=True):
        if r['type'] == 'prompt':
            text = re.sub(r'\s*<a [^>]*>.*?</a>\s*$', '', r['text'], flags=re.S)
            out[r['key']] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text)).replace('&rsquo;', "'").strip()
    return out


def _catalog(domain):
    """Compact product records: title, price and the useful part of the page (ingredients, materials, sizes,
    who it's for). Trimmed so one call stays small."""
    import catalog_facts
    out = []
    for r in catalog_facts.get(domain)[:25]:
        text = (r.get('page') or {}).get('text') or ''
        i = text.rfind(r['title'])
        text = text[i:] if i > 0 else text
        price = next((f['value'] for f in r['facts'] if f['label'] == 'Price'), '')
        out.append('- %s (%s): %s' % (r['title'], price, re.sub(r'\s+', ' ', text)[:900]))
    return '\n'.join(out)


def _cited_questions(domain, questions):
    """Question-shaped headings on the pages AI cited for this store's questions (page_gap shapes)."""
    import briefs
    import page_gap
    _, _, _, cites = briefs._evidence(domain)
    total = Counter()
    for q in questions:
        total.update(cites.get(q, {}))
    out = []
    for url, _ in total.most_common(15):
        f = page_gap.facts(url) or {}
        for h in (f.get('shape') or {}).get('headings') or []:
            t = h.split(' ', 1)[-1]
            if t.endswith('?') and 15 < len(t) < 120:
                out.append('%s (on %s)' % (t, briefs._host(url)))
    return list(dict.fromkeys(out))[:20]


def _competitors(domain):
    import briefs
    _, _, wins, _ = briefs._evidence(domain)
    brands = Counter()
    for c in wins.values():
        for (brand, _product, _url), n in c.items():
            if brand:
                brands[brand] += n
    return [b for b, _ in brands.most_common(8)]


# ---- writing --------------------------------------------------------------------------------

RULES = """You help an online store choose the buyer questions it tracks in AI assistants (ChatGPT, Perplexity, Google AI). Each tracked question is asked every day and the store sees whether AI recommends its products.

Write two lists.

swaps: for each POOR QUESTION given, one better question that tests the same products. Keep what the buyer wanted, fix the problem named. A question AI answers with general advice must become a request for a product: "which [product] should I buy for [who / need / price]". Never keep a choice between two types of product ("face oil or moisturiser?", "set or separately?") or a "which is better value" question: AI answers those with advice too, however narrow they get.

adds: up to 8 NEW questions worth tracking, each from a different angle where possible, and each with its source:
- ingredient / material: a key ingredient or material the store's products really contain (from PRODUCTS), asked the way a shopper would ("best moisturiser with squalane for dry skin").
- location: where the store is or ships to, when buyers would ask by place ("men's skincare brands in the UK").
- competitor: alternatives to, or a choice between, brands AI already names (COMPETITORS).
- cited: a question from CITED PAGE QUESTIONS, rephrased for a shopper.
- journey: a stage of buying the TRACKED QUESTIONS miss: the problem, joined to what to buy ("my skin feels tight after washing, which cleanser should I use?"), or deciding ("is a 3-step skincare set worth it for a beginner?"). Never a pure how-to question: AI answers those with advice, not products.
- season: a gifting or seasonal need in the next two months (TODAY is given).
- catalog: a product no tracked question covers.

Rules for every question:
- Write like a shopper typing into ChatGPT: natural, 6-18 words. Never name the store's brand or a product's name.
- Never copy the product page's wording: use the ingredient or material as the hook, but the words are the buyer's.
- Only ingredients, materials, sizes and attributes the products really have. Never invent one.
- Prices always with the currency symbol given.
- Each must be answerable by recommending specific products, and at least one of the store's products must fit it: list their exact titles in products.
- No near-duplicates of TRACKED QUESTIONS or of each other.
reason: one plain sentence for the owner on why this question is worth tracking."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["swaps", "adds"], "properties": {
    "swaps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
              "required": ["old", "new"], "properties": {"old": {"type": "string"}, "new": {"type": "string"}}}},
    "adds": {"type": "array", "items": {"type": "object", "additionalProperties": False,
             "required": ["question", "reason", "source", "products"], "properties": {
                 "question": {"type": "string"}, "reason": {"type": "string"},
                 "source": {"type": "string", "enum": list(SOURCES)},
                 "products": {"type": "array", "items": {"type": "string"}}}}}}}


def poor(domain, ps, stats):
    """[(question, reason, evidence)] for tracked questions that make a poor test, worst first."""
    quality = _quality(domain)
    dead, out = [], []
    for q in ps['prompts']:
        s = stats.get(q) or {}
        if s.get('answers', 0) >= 10 and s['named'] / s['answers'] < DEAD:
            dead.append((q, 'AI answers it with general advice: it named products in only %d of %d answers, so no '
                           'product can win it.' % (s['named'], s['answers']),
                        'Products named in %d%% of answers' % round(100 * s['named'] / s['answers'])))
        elif q in quality:
            out.append((q, quality[q], ''))
    return (dead + out)[:MAX_SWAPS]          # the strongest evidence first


def _words(t):
    import opportunities
    return set(opportunities._content(t))


def _too_close(q, others):
    w = _words(q)
    return any(w and len(w & _words(o)) / max(1, min(len(w), len(_words(o)))) >= 0.75 for o in others)


def _copies_page(q, domain):
    """True when most of the question's words are on one product page: it would test the page, not demand."""
    import catalog_facts
    w = _words(q)
    if len(w) < 4:
        return False
    # The product's own description only: full page text carries menus and cross-sells that mention every
    # product, so almost any question would "match" it (18 Oct 2026: four good swaps were thrown out).
    for r in catalog_facts.get(domain):
        page = _words(r['title'] + ' ' + ' '.join(r.get('description') or []))
        if len(w) >= 5 and len(w & page) / len(w) >= 0.85:
            return True
    return False


def _names_brand(q, domain):
    brand = db.brand(domain) or {}
    names = [n.strip().lower() for n in [brand.get('brand_name') or ''] + (brand.get('aliases') or '').split(',')
             if len(n.strip()) > 2]
    return any(n in q.lower() for n in names)


def build(domain, usage=None):
    """Write fresh suggestions for a store and save them. Returns how many were saved."""
    import catalog
    import catalog_facts
    import llm
    init()
    ps = db.get_prompt_set(domain)
    if not ps:
        return 0
    if not catalog_facts.get(domain):
        catalog_facts.build(domain)
    stats = _stats(domain)
    bad = poor(domain, ps, stats)
    meta = catalog.store_meta(domain)
    import accounts
    cap = accounts.question_limit(domain)
    room = (cap - len(ps['prompts'])) if cap else MAX_ADDS
    text = ('TODAY: %s\nSTORE COUNTRY: %s\nCURRENCY SYMBOL: %s\n\nTRACKED QUESTIONS:\n%s\n\nPOOR QUESTIONS:\n%s\n\n'
            'PRODUCTS:\n%s\n\nCOMPETITORS AI NAMES:\n%s\n\nCITED PAGE QUESTIONS:\n%s') % (
        time.strftime('%-d %B %Y'), meta.get('country') or 'unknown', meta.get('symbol') or meta.get('currency') or '',
        '\n'.join('- ' + q for q in ps['prompts']),
        '\n'.join('- %s (problem: %s)' % (q, why) for q, why, _ in bad) or '(none)',
        _catalog(domain), ', '.join(_competitors(domain)) or '(none yet)',
        '\n'.join('- ' + c for c in _cited_questions(domain, ps['prompts'])) or '(none read yet)')
    res = llm.json_call(RULES, text, 'question_suggestions', SCHEMA, usage=usage, attempts=2)

    titles = {p['title'].lower(): p['id'] for p in ps['catalog_snapshot']}
    relevance = {q: (ps['relevance'][i] if i < len(ps['relevance']) else []) for i, q in enumerate(ps['prompts'])}
    dismissed = {r['new_q'].lower() for r in db.all_(
        "SELECT new_q FROM question_suggestions WHERE store_domain=? AND status='dismissed'", (domain,))}
    tracked = list(ps['prompts'])
    rows, taken = [], []

    def ok(q, replacing=None):
        return (q and q.lower() not in dismissed and not _names_brand(q, domain) and not _copies_page(q, domain)
                and not _too_close(q, [t for t in tracked if t != replacing] + taken))

    why = {q: (reason, ev) for q, reason, ev in bad}
    for s in res['swaps']:
        if s['old'] in why and ok(s['new'], s['old']):
            taken.append(s['new'])
            rows.append(('swap', s['old'], s['new'], why[s['old']][0], why[s['old']][1], '', relevance.get(s['old'], [])))
    if room > 0:
        for a in res['adds'][:min(MAX_ADDS, room)]:
            ids = [titles[t.lower()] for t in a['products'] if t.lower() in titles]
            if ids and a['source'] in SOURCES and ok(a['question']):
                taken.append(a['question'])
                rows.append(('add', None, a['question'], a['reason'], '', a['source'], ids))
    now = time.time()
    with db.conn() as c:
        c.execute("DELETE FROM question_suggestions WHERE store_domain=? AND status='open'", (domain,))
        for kind, old, new, reason, ev, src, ids in rows:
            c.execute('INSERT INTO question_suggestions (store_domain, kind, old_q, new_q, reason, evidence, source, '
                      'products, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                      (domain, kind, old, new, reason, ev, src, json.dumps(ids), now))
        if not rows:       # remember the attempt, so an empty week doesn't call the model on every visit
            c.execute("INSERT INTO question_suggestions (store_domain, kind, new_q, status, created_at) "
                      "VALUES (?, 'none', '', 'none', ?)", (domain, now))
    return len(rows)


def refresh(domain, force=False):
    """Build in the background when the store's suggestions are older than a week."""
    if domain in _running or (_fresh(domain) and not force):
        return False
    _running.add(domain)

    def go():
        try:
            build(domain)
        except Exception as e:                                   # noqa: BLE001
            print('question suggestions: %s failed (%s)' % (domain, e))
        finally:
            _running.discard(domain)
    threading.Thread(target=go, daemon=True).start()
    return True


# ---- acting ---------------------------------------------------------------------------------

def decide(domain, sid, action, text=''):
    """add / swap: change the tracked questions (a new prompt-set version; kept questions keep their history).
    dismiss: never show this one again. Returns an error message or ''."""
    import accounts
    import catalog_setup
    import app
    row = db.one("SELECT * FROM question_suggestions WHERE id=? AND store_domain=? AND status='open'", (sid, domain))
    if not row:
        return 'That suggestion is gone. Refresh the page.'
    if action == 'dismiss':
        db.write("UPDATE question_suggestions SET status='dismissed', decided_at=? WHERE id=?", (time.time(), sid))
        return ''
    ps = db.get_prompt_set(domain)
    new = (text or row['new_q']).strip()
    if not new:
        return 'Write a question first.'
    items = catalog_setup.items_out(ps)
    old = next((x for x in items if x['q'] == row['old_q']), None) if row['kind'] == 'swap' else None
    if row['kind'] == 'swap' and not old:
        return 'That question is no longer tracked.'
    if old:
        items = [x for x in items if x is not old]
    items.append(dict(q=new, tag=old['tag'] if old else '', cluster=old['cluster'] if old else 'Buyer questions',
                      products=json.loads(row['products'] or '[]') or (old['products'] if old else [])))
    try:
        accounts.check_question_limit(domain, len(items))
    except Exception as e:                                       # noqa: BLE001
        return str(e) or 'Your plan has no room for another question.'
    code, out = app.api_questions(dict(d=domain), dict(questions=json.dumps(items)))[:2]
    if isinstance(out, tuple):
        data = json.loads(out[1])
        if isinstance(data, dict) and data.get('error'):
            return data['error']
    db.write("UPDATE question_suggestions SET status='done', new_q=?, decided_at=? WHERE id=?", (new, time.time(), sid))
    return ''


def act(q, form):
    import accounts
    domain = form.get('d', '')
    if not accounts.can_see(domain):
        return 400, '<h1>Bad request</h1>'
    if form.get('action') == 'refresh':
        refresh(domain, force=True)
        err = ''
    else:
        try:
            sid = int(form.get('id', ''))
        except ValueError:
            return 400, '<h1>Bad request</h1>'
        err = decide(domain, sid, form.get('action', ''), form.get('text', ''))
    if form.get('ajax') == '1':
        # The page acts in place (no reload): it gets a short answer and moves the row to its done state.
        return 200, ('json', json.dumps(dict(ok=not err, error=err, left=count(domain))))
    import urllib.parse
    return 303, '/question-suggestions?' + urllib.parse.urlencode(dict(d=domain, **({'error': err} if err else {})))


# ---- page -----------------------------------------------------------------------------------
# Layout chosen 18 Oct 2026 (mvp/design/suggestions-variations, "1 · Review"), made plainer: "Now" and
# "Suggested" instead of diff symbols, and the reason shown, not only told: one dot per answer with the
# ones that named a product lit, or the product page's own words highlighted inside the old question.

def tabs(domain, here):
    import urllib.parse
    d = urllib.parse.urlencode(dict(d=domain))
    n = count(domain)
    return ('<nav class="qs-tabs" aria-label="Buyer questions"><a href="/buyer-questions?%s"%s>Your questions</a>'
            '<a href="/question-suggestions?%s"%s>Suggestions%s</a></nav>') % (
        E(d), ' aria-current="page"' if here == 'questions' else '', E(d),
        ' aria-current="page"' if here == 'suggestions' else '',
        ' <span class="qs-n" data-qs-count>%d</span>' % n if n else '')


_ICONS = {
    'advice': '<path d="M4 5.5h16v10H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    'page': '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 15.5h5"/>',
    'ingredient': '<path d="M9 3h6M10 3v5l-4.5 8.5A2.5 2.5 0 0 0 7.7 20h8.6a2.5 2.5 0 0 0 2.2-3.5L14 8V3"/><path d="M7.5 14h9"/>',
    'material': '<path d="M4 7c4-3 12-3 16 0v10c-4-3-12-3-16 0z"/>',
    'location': '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    'competitor': '<circle cx="8" cy="9" r="3.2"/><circle cx="16.5" cy="9" r="3.2"/><path d="M2.5 19a5.5 5.5 0 0 1 11 0M11 19a5.5 5.5 0 0 1 11 0"/>',
    'cited': '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    'journey': '<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18h6a3 3 0 0 0 0-6h-2a3 3 0 0 1 0-6h6"/>',
    'season': '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    'catalog': '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><path d="M16.5 13.5v6M13.5 16.5h6"/>',
    'check': '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    'arrow': '<path d="M12 5v14M6 13l6 6 6-6"/>',
}


def _icon(name):
    return '<svg class="qs-i" viewBox="0 0 24 24" aria-hidden="true">%s</svg>' % _ICONS.get(name, '')


def _highlight(text, words):
    """The old question with the product page's own words marked."""
    if not words:
        return E(text)
    pat = re.compile(r'\b(%s)\b' % '|'.join(re.escape(w) for w in sorted(words, key=len, reverse=True)), re.I)
    out, last = [], 0
    for m in pat.finditer(text):
        out += [E(text[last:m.start()]), '<mark>%s</mark>' % E(m.group(0))]
        last = m.end()
    return ''.join(out + [E(text[last:])])


def _row(domain, r, stats, products):
    s = stats.get(r['old_q'] or '') or {}
    advice = r['kind'] == 'swap' and s.get('answers') and s['named'] / s['answers'] < DEAD
    m = re.search(r'\(([^)]+)\)', r['reason'] or '')
    copied = [w.strip() for w in m.group(1).split(',')] if (m and r['kind'] == 'swap' and not advice) else []
    fits = [products[i] for i in json.loads(r['products'] or '[]') if i in products]
    fit = ('<span class="qs-fits">%s<span>%s</span></span>' % (
        ''.join('<img src="%s" alt="" loading="lazy">' % E(p.get('image') or '') for p in fits[:4] if p.get('image')),
        E('Tests ' + ', '.join(p['title'] for p in fits[:3])))) if fits else ''
    if r['kind'] == 'swap' and advice:
        n, total = s['named'], s['answers']
        why = ('<div class="qs-why">%s<p><b>AI gives advice here, not products.</b> It recommended a product in only '
               '<b class="qs-num">%d of %d</b> answers, so no product can win this question.</p></div>'
               '<div class="qs-dots" role="img" aria-label="%d of %d answers named a product">%s</div>') % (
            _icon('advice'), n, total, n, total,
            ''.join('<i%s></i>' % (' class="on"' if k < n else '') for k in range(total)))
        old = E(r['old_q'])
    elif r['kind'] == 'swap':
        why = ('<div class="qs-why">%s<p><b>It repeats your product page.</b> The highlighted words are on your page, '
               'so it tests the page describing itself, not what buyers ask.</p></div>') % _icon('page')
        old = _highlight(r['old_q'], copied)
    else:
        why = '<div class="qs-why">%s<p><b>%s.</b> %s</p></div>' % (
            _icon(r['source']), E(SOURCES.get(r['source'], 'New question')), E(r['reason'] or ''))
        old = ''
    now = ('<div class="qs-line qs-now"><span class="qs-lab">Now</span><p>%s</p></div>'
           '<div class="qs-to">%s</div>' % (old, _icon('arrow'))) if r['kind'] == 'swap' else ''
    verb = 'Swap' if r['kind'] == 'swap' else 'Add'
    done = ('Swapped. The new question starts its own trend from the next scan.' if r['kind'] == 'swap'
            else 'Added. It\'s asked from the next scan.')
    return ('<article class="qs-row" data-sid="%d" data-kind="%s" data-done="%s" tabindex="-1">'
            '<form method="post" action="/question-suggestions" class="qs-form">'
            '<input type="hidden" name="d" value="%s"><input type="hidden" name="id" value="%d">'
            '<div class="qs-body">%s<div class="qs-line qs-new"><span class="qs-lab">%s</span>'
            '<textarea name="text" rows="1" aria-label="Suggested question" spellcheck="true">%s</textarea></div>'
            '%s%s</div>'
            '<div class="qs-act"><button class="qs-btn qs-go" name="action" value="%s">%s</button>'
            '<button class="qs-btn qs-quiet" type="button" data-edit>Edit</button>'
            '<button class="qs-btn qs-quiet" name="action" value="dismiss">Not for us</button></div>'
            '</form><div class="qs-done" hidden>%s<span></span></div></article>') % (
        r['id'], r['kind'], E(done), E(domain), r['id'], now, 'Suggested' if r['kind'] == 'swap' else 'New question',
        E(r['new_q']), why, fit, r['kind'], verb, _icon('check'))


def page(q):
    import accounts
    import app
    domain = q.get('d') or app._LAST_STORES.get((accounts.current() or {}).get('id', 0), {}).get('domain', '')
    if not domain or not accounts.can_see(domain):
        return 404, '<h1>Not found</h1>'
    ps = db.get_prompt_set(domain)
    brand = db.brand(domain) or {}
    wrap = ('<div class="qs-page" data-rail-page="questions" data-rail-sub="suggestions" data-rail-store="%s" '
            'data-rail-name="%s">%s{BODY}</div><style>{CSS}</style>') % (
        E(domain), E(brand.get('brand_name') or domain), tabs(domain, 'suggestions'))
    fill = lambda body: wrap.replace('{CSS}', CSS).replace('{BODY}', body)
    if not ps:
        return 200, fill('<h1>Suggestions</h1><p class="qs-lead">Finish onboarding first.</p>')
    refresh(domain)
    rows = open_rows(domain)
    cap = accounts.question_limit(domain)
    used = len(ps['prompts'])
    err = ('<p class="qs-err" role="alert">%s</p>' % E(q['error'])) if q.get('error') else ''
    refresh_btn = ('<form method="post" action="/question-suggestions" class="qs-refresh"><input type="hidden" '
                   'name="d" value="%s"><button class="qs-btn qs-quiet" name="action" value="refresh">Look again'
                   '</button></form>' % E(domain))
    capline = ('<span class="qs-cap"><span class="qs-num">%d of %d</span> questions used<span class="qs-track">'
               '<b style="width:%d%%"></b></span></span>' % (used, cap, min(100, round(100 * used / cap)))
               if cap else '<span class="qs-cap"><span class="qs-num">%d</span> questions tracked</span>' % used)
    if domain in _running:
        body = ('<div class="qs-empty"><p><b>Looking for better questions…</b> Reading your products, the answers AI '
                'gave and the pages it cites. About a minute.</p></div><meta http-equiv="refresh" content="15">')
        lead = ''
    elif not rows:
        body = ('<div class="qs-empty"><p><b>Nothing to change right now.</b> Your questions get product answers '
                'from AI. We look again every week.</p></div>')
        lead = ''
    else:
        stats = _stats(domain)
        products = {p['id']: p for p in ps['catalog_snapshot']}
        swaps = [r for r in rows if r['kind'] == 'swap']
        adds = [r for r in rows if r['kind'] == 'add']
        parts = []
        if swaps:
            parts.append('%d of your questions could test you better' % len(swaps))
        if adds:
            parts.append('%d new question%s worth tracking' % (len(adds), '' if len(adds) == 1 else 's'))
        lead = ('<p class="qs-lead">%s. Each one shows why. Nothing changes until you choose.</p>'
                % E(' and '.join(parts)).capitalize())
        sec = lambda title, rs: ('<section class="qs-sec"><h2>%s <span class="qs-num">%d</span></h2>%s</section>'
                                 % (title, len(rs), ''.join(_row(domain, r, stats, products) for r in rs))) if rs else ''
        body = ('<div class="qs-progress" aria-live="polite"><span><b class="qs-num" data-qs-done>0</b> of '
                '<span class="qs-num">%d</span> reviewed</span><span class="qs-bar"><b data-qs-bar></b></span></div>'
                % len(rows) + sec('Better versions of your questions', swaps) + sec('New questions to track', adds)
                + '<div class="qs-finished" hidden><b>All reviewed.</b> We look for new suggestions every week.</div>'
                + '<p class="qs-keys"><kbd>J</kbd><kbd>K</kbd> move <kbd>S</kbd> swap or add <kbd>X</kbd> not for us</p>'
                + SCRIPT)
    return 200, fill('<header class="qs-top"><div><h1>Suggestions</h1>%s</div><div class="qs-side">%s%s</div>'
                        '</header>%s%s' % (lead, capline, refresh_btn, err, body))


SCRIPT = """<script>(function(){
var rows=[].slice.call(document.querySelectorAll('.qs-row')),done=0,total=rows.length,cur=0;
function fit(t){if(CSS.supports('field-sizing','content'))return;t.style.height='auto';t.style.height=t.scrollHeight+'px';}
var tas=[].slice.call(document.querySelectorAll('.qs-row textarea'));function fitAll(){tas.forEach(fit)}
tas.forEach(function(t){t.addEventListener('input',function(){fit(t)})});fitAll();
if(document.fonts)document.fonts.ready.then(fitAll);window.addEventListener('resize',fitAll);
function progress(){var d=document.querySelector('[data-qs-done]'),b=document.querySelector('[data-qs-bar]');
 if(d)d.textContent=done;if(b)b.style.width=(100*done/Math.max(1,total))+'%';
 var n=total-done;document.querySelectorAll('[data-qs-count],.rail-sub .rail-badge').forEach(function(c){c.textContent=n;c.hidden=!n;});
 if(done>=total){var f=document.querySelector('.qs-finished');if(f)f.hidden=false;}}
function focus(i){cur=Math.max(0,Math.min(rows.length-1,i));rows.forEach(function(r,k){r.classList.toggle('qs-sel',k===cur)});
 if(rows[cur]){rows[cur].focus({preventScroll:true});rows[cur].scrollIntoView({block:'nearest',behavior:'smooth'});}}
function send(row,action){var f=row.querySelector('form'),b=new URLSearchParams(new FormData(f));b.set('action',action);b.set('ajax','1');
 row.classList.add('qs-busy');
 return fetch('/question-suggestions',{method:'POST',body:b,credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){
  row.classList.remove('qs-busy');
  if(!j.ok){alert(j.error||'That didn\\u2019t save. Try again.');return;}
  var msg=row.querySelector('.qs-done span');msg.textContent=action==='dismiss'?'Not for us. We won\\u2019t suggest it again.':row.dataset.done;
  row.querySelector('.qs-done').hidden=false;row.classList.add(action==='dismiss'?'qs-dismissed':'qs-applied');
  done++;progress();var nx=rows.findIndex(function(r,k){return k>cur&&!r.classList.contains('qs-applied')&&!r.classList.contains('qs-dismissed')});
  if(nx>-1)setTimeout(function(){focus(nx)},350);
 }).catch(function(){row.classList.remove('qs-busy');alert('That didn\\u2019t save. Try again.')});}
rows.forEach(function(row,k){var f=row.querySelector('form');
 f.addEventListener('submit',function(e){e.preventDefault();send(row,(e.submitter||{}).value||row.dataset.kind)});
 row.querySelector('[data-edit]').addEventListener('click',function(){var t=row.querySelector('textarea');t.focus();t.setSelectionRange(t.value.length,t.value.length)});
 row.addEventListener('mousedown',function(){cur=k;rows.forEach(function(r,j){r.classList.toggle('qs-sel',j===k)})});});
document.addEventListener('keydown',function(e){if(e.target.closest('textarea,input')||e.metaKey||e.ctrlKey)return;var r=rows[cur];
 if(e.key==='j'){e.preventDefault();focus(cur+1)}else if(e.key==='k'){e.preventDefault();focus(cur-1)}
 else if(r&&!r.classList.contains('qs-applied')&&!r.classList.contains('qs-dismissed')){
  if(e.key==='s'){e.preventDefault();send(r,r.dataset.kind)}else if(e.key==='x'){e.preventDefault();send(r,'dismiss')}}});
if(rows.length)rows[0].classList.add('qs-sel');
})();</script>"""


CSS = """
.qs-page{--qs-text:#0b1b35;--qs-muted:#5b6577;--qs-faint:#7a8494;--qs-line:#e3e8ef;--qs-surface:#ffffff;--qs-raised:#f5f7fa;
 --qs-sel:#f0f4fa;--qs-add:#18804b;--qs-add-bg:#eaf6ef;--qs-cut:#b8432e;--qs-cut-bg:#fbf0ed;--qs-mark:#f9e3a6;--qs-ink:#0b1b35;--qs-on-ink:#ffffff;
 --qs-dot:#dfe4ec;--qs-focus:#2f6fdb;max-width:920px;color:var(--qs-text)}
html.dark .qs-page{--qs-text:#e4e8ee;--qs-muted:#a7b0bd;--qs-faint:#8a94a3;--qs-line:#262a30;--qs-surface:#16181c;--qs-raised:#1b1e23;
 --qs-sel:#1b1f25;--qs-add:#45d08c;--qs-add-bg:rgba(63,207,134,.08);--qs-cut:#f0846f;--qs-cut-bg:rgba(240,113,90,.07);--qs-mark:rgba(232,176,74,.28);
 --qs-ink:#e9edf3;--qs-on-ink:#0f1114;--qs-dot:#2c3138;--qs-focus:#7aa7ff}
.qs-page .qs-num{font-variant-numeric:tabular-nums}
.qs-i{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex:none}
.qs-tabs{display:inline-flex;gap:2px;background:var(--qs-raised);border:1px solid var(--qs-line);border-radius:10px;padding:3px;margin:0 0 22px}
.qs-tabs a{padding:6px 14px;border-radius:7px;font-size:14px;font-weight:500;color:var(--qs-muted);text-decoration:none}
.qs-tabs a[aria-current]{background:var(--qs-surface);color:var(--qs-text);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.qs-n{display:inline-block;min-width:18px;padding:0 6px;border-radius:9px;background:var(--qs-ink);color:var(--qs-on-ink);font-size:11.5px;line-height:18px;text-align:center;margin-left:4px}
.qs-n[hidden]{display:none}
.qs-top{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;margin-bottom:22px}
.qs-top h1{margin:0 0 6px;font-size:24px;letter-spacing:-.02em}
.qs-lead{margin:0;color:var(--qs-muted);font-size:15px;max-width:62ch}
.qs-side{display:flex;align-items:center;gap:14px}
.qs-cap{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--qs-muted)}
.qs-track{display:inline-block;width:90px;height:4px;border-radius:4px;background:var(--qs-dot);overflow:hidden;margin-left:4px}.qs-track b{display:block;height:100%;background:var(--qs-ink)}
.qs-refresh{margin:0}
.qs-progress{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--qs-muted);margin:0 0 18px}
.qs-progress b{color:var(--qs-text)}
.qs-bar{flex:1;max-width:240px;height:6px;border-radius:4px;background:var(--qs-dot);overflow:hidden}
.qs-bar b{display:block;height:100%;width:0;background:var(--qs-add);border-radius:4px;transition:width .5s cubic-bezier(.2,.8,.2,1)}
.qs-sec{margin:0 0 26px;border:1px solid var(--qs-line);border-radius:14px;background:var(--qs-surface);overflow:hidden}
.qs-sec h2{margin:0;padding:12px 18px;font-size:13.5px;font-weight:600;background:var(--qs-raised);border-bottom:1px solid var(--qs-line);display:flex;gap:8px}
.qs-sec h2 .qs-num{color:var(--qs-faint);font-weight:500}
.qs-row{position:relative;border-bottom:1px solid var(--qs-line);transition:background .15s;outline:none}
.qs-row:last-child{border-bottom:0}
.qs-row.qs-sel{background:var(--qs-sel)}
.qs-row.qs-sel::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--qs-focus)}
.qs-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;padding:14px 16px 14px 18px;margin:0}
.qs-body{min-width:0}
.qs-line{display:grid;grid-template-columns:96px minmax(0,1fr);gap:10px;align-items:start;border-radius:8px;padding:6px 10px}
.qs-lab{font-size:11.5px;font-weight:600;letter-spacing:.02em;padding-top:2px;white-space:nowrap}
.qs-now{background:var(--qs-cut-bg)}.qs-now .qs-lab{color:var(--qs-cut)}
.qs-now p{margin:0;color:var(--qs-muted);font-size:14px;line-height:1.5}
.qs-now mark{background:var(--qs-mark);color:inherit;border-radius:3px;padding:0 2px}
.qs-to{display:flex;padding:2px 0 2px 46px;color:var(--qs-faint)}
.qs-new{background:var(--qs-add-bg)}.qs-new .qs-lab{color:var(--qs-add)}
.qs-new textarea{all:unset;field-sizing:content;display:block;width:100%;min-height:1.5em;font-size:15px;font-weight:600;line-height:1.5;color:var(--qs-text);white-space:pre-wrap;overflow:hidden;resize:none;cursor:text;border-radius:4px}
.qs-new textarea:focus{box-shadow:0 0 0 2px var(--qs-focus)}
.qs-why{display:flex;gap:9px;align-items:flex-start;margin:10px 10px 0;color:var(--qs-muted);font-size:13.5px;line-height:1.5}
.qs-why .qs-i{margin-top:2px;color:var(--qs-faint)}.qs-why p{margin:0;max-width:66ch}.qs-why b{color:var(--qs-text);font-weight:600}
.qs-dots{display:flex;flex-wrap:wrap;gap:2px;margin:8px 10px 0 35px;max-width:none}
.qs-dots i{width:5px;height:12px;border-radius:1.5px;background:var(--qs-dot)}.qs-dots i.on{background:var(--qs-add)}
.qs-fits{display:flex;align-items:center;gap:8px;margin:10px 10px 0 35px;font-size:12.5px;color:var(--qs-faint)}
.qs-fits img{width:24px;height:24px;border-radius:6px;object-fit:cover;background:#f4f1ea;margin-right:-4px;border:2px solid var(--qs-surface)}
.qs-fits span{margin-left:8px}
.qs-act{display:flex;flex-direction:column;gap:4px;align-items:stretch;min-width:112px}
.qs-btn{font:inherit;font-size:13px;font-weight:500;height:32px;padding:0 14px;border-radius:8px;border:1px solid var(--qs-line);background:var(--qs-surface);color:var(--qs-text);cursor:pointer;transition:background .12s,transform .12s}
.qs-btn:hover{background:var(--qs-raised)}.qs-btn:active{transform:scale(.98)}
.qs-go{background:var(--qs-ink);color:var(--qs-on-ink);border-color:var(--qs-ink)}.qs-go:hover{background:var(--qs-ink);opacity:.9}
.qs-quiet{border-color:transparent;background:none;color:var(--qs-muted)}
.qs-btn:focus-visible{outline:2px solid var(--qs-focus);outline-offset:2px}
.qs-busy{opacity:.6;pointer-events:none}
.qs-done{display:flex;align-items:center;gap:10px;padding:16px 20px;font-size:14px;color:var(--qs-text);animation:qs-in .35s cubic-bezier(.2,.8,.2,1)}
.qs-done .qs-i{width:20px;height:20px;padding:3px;border-radius:50%;background:var(--qs-add);color:var(--qs-on-ink);stroke-width:2.4}
.qs-applied .qs-form,.qs-dismissed .qs-form{display:none}
.qs-dismissed .qs-done{color:var(--qs-muted)}.qs-dismissed .qs-done .qs-i{background:var(--qs-dot);color:var(--qs-muted)}
@keyframes qs-in{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
.qs-finished{padding:16px 18px;border-radius:12px;background:var(--qs-add-bg);color:var(--qs-text);margin:0 0 20px}
.qs-keys{font-size:12px;color:var(--qs-faint);display:flex;gap:6px;align-items:center}
.qs-keys kbd{font:500 11px ui-monospace,monospace;border:1px solid var(--qs-line);border-bottom-width:2px;border-radius:5px;padding:0 5px;color:var(--qs-muted);background:var(--qs-surface)}
.qs-empty{padding:20px;border:1px dashed var(--qs-line);border-radius:12px;color:var(--qs-muted)}.qs-empty b{color:var(--qs-text)}
.qs-err{padding:10px 14px;border-radius:10px;background:var(--qs-cut-bg);color:var(--qs-cut)}
@media (max-width:760px){.qs-form{grid-template-columns:1fr}.qs-act{flex-direction:row;flex-wrap:wrap}.qs-line{grid-template-columns:1fr;gap:2px}
 .qs-to{padding-left:10px}.qs-dots,.qs-fits{margin-left:10px}.qs-keys{display:none}}
@media (prefers-reduced-motion:reduce){.qs-page *{transition:none!important;animation:none!important}}
"""
