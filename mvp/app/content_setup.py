"""Agent setup, part 1: the brand's voice and what the agent may change.

Day 11c of mvp/content-agent/PLAN.md. Shown the first time the merchant opens
Catalog Optimization Agent, and again from its Settings link.

  1. Voice: the agent reads the brand's longest product descriptions, its
     About page and homepage, and the brand profile (onboarding step 2), writes
     down how the brand sounds (a few plain traits), keeps 2-3 lines copied
     word for word from those pages as tone examples, and shows a sample
     written that way from one product's stated facts. The merchant says
     "Sounds like us" or tells it what to change, and it tries again. One
     helper-model call per try (a fraction of a cent). Day 16 (16 Oct) added
     the About/homepage, the profile and the example lines.
  2. Brand brief: 15 questions a writer at the brand would know the answers to
     (customers, story, what's different, proof, policies, objections, words to
     use and avoid, claims never to make, brands never to name, length, layout,
     spelling...). The agent pre-fills them from the store's pages and profile
     (one call); the merchant corrects. Answers marked as facts become usable
     facts; banned words, forbidden claims and unnamed brands are checked.
  3. Scope: which kinds of change the agent may make, and products to leave
     alone. Collections come later: the catalog we read has none yet.

Both are enforced, not just stored: drafts.py writes in the saved voice, and
content_agent.draft_for() skips types and products the merchant ruled out.
Day 11d (15 Oct) adds: time zone (pre-filled from the country, overrides it
app-wide via storetime), pace / days / hour, the approval note, missing facts
per product (the agent lists what buyers check that each page doesn't state,
suggesting an answer only when the store states it elsewhere; answers become
product facts), then drafts the top Opportunities into the first two weeks in
the background and lands on the calendar.
"""
import json
import re
import time
import urllib.parse
from html import escape as E

import db

CHANGES = (
    ('titles', 'Product titles'),
    ('descriptions', 'Product descriptions'),
    ('specs', 'Spec tables'),
    ('faqs', 'FAQs on product pages'),
    ('comparisons', 'Comparison pages'),
    ('guides', 'Buying guides on your blog'),
)
# Draft type -> the change it needs. A product-page fix is allowed if any of its parts is.
TYPE_NEEDS = {'faq': ('faqs',), 'comparison': ('comparisons',), 'guide': ('guides',),
              'product_fix': ('titles', 'descriptions', 'specs')}


# The brand brief: everything a writer at the brand would know. (key, label, hint, kind)
# kind: 'text' one answer, 'lines' one item per line, or a tuple of choices.
# 'fact' fields are things the merchant states as true: drafts may use them as facts.
BRIEF = (
    ('customers', 'Who buys from you?', 'Age, situation, what they care about, what they\'re trying to solve.', 'text'),
    ('story', 'Your brand in one or two sentences', 'How you\'d explain it to a friend.', 'text'),
    ('different', 'What makes your products different?', 'One per line. Only things that are true; the agent will state them.', 'lines'),
    ('proof', 'Certifications, awards, press, tests', 'One per line, e.g. "Vegan Society certified", "Featured in Vogue, 2025". Only true ones.', 'lines'),
    ('policies', 'Shipping, returns and guarantees', 'One per line, e.g. "Free UK shipping over £40", "30-day returns".', 'lines'),
    ('objections', 'What customers ask or worry about most', 'One per line: questions from emails, reviews, DMs. These become FAQs.', 'lines'),
    ('naming', 'How should products be referred to?', 'e.g. "Always the full name, Frontier Cleanser, never just the cleanser".', 'text'),
    ('always_words', 'Words and phrases you like to use', 'One per line.', 'lines'),
    ('never_words', 'Words you never want used', 'One per line. Drafts using them are flagged automatically.', 'lines'),
    ('no_claims', 'Claims you can\'t or won\'t make', 'One per line, e.g. "treats acne", "anti-ageing", "clinically proven". Sentences making them are held back.', 'lines'),
    ('never_name', 'Brands never to name', 'One per line. Comparison pages name competitors by default; list any you want left out.', 'lines'),
    ('love_page', 'Writing you love', 'A link or a pasted paragraph, yours or anyone\'s, that sounds the way you want to sound.', 'text'),
    ('length', 'How long should pages be?', '', ('Short and scannable', 'Medium', 'Long and detailed')),
    ('format', 'How should they be laid out?', '', ('Short paragraphs', 'Bullet points where possible', 'A mix')),
    ('spelling', 'Spelling', '', ('British', 'American')),
)
FACT_FIELDS = ('different', 'proof', 'policies')


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS content_settings (store_domain TEXT PRIMARY KEY, data TEXT, '
                  'updated_at REAL)')


def get(domain):
    init()
    row = db.one('SELECT data FROM content_settings WHERE store_domain=?', (domain,))
    data = json.loads(row['data']) if row and row['data'] else {}
    data.setdefault('allowed', [k for k, _ in CHANGES])
    data.setdefault('leave_alone', [])
    return data


def put(domain, data):
    init()
    with db.conn() as c:
        c.execute('INSERT OR REPLACE INTO content_settings VALUES (?,?,?)', (domain, json.dumps(data), time.time()))


def done(domain):
    return bool(get(domain).get('part1_done_at'))


def allowed_types(domain):
    allowed = set(get(domain)['allowed'])
    return {t for t, needs in TYPE_NEEDS.items() if allowed & set(needs)}


def voice_text(domain):
    """Everything drafts should know about how to write for this brand, or '' if setup gave nothing."""
    s = get(domain)
    v = s.get('voice') or {}
    out = []
    if v.get('confirmed'):
        out += ['- ' + _trait_text(t) for t in v.get('traits', [])]
        if v.get('examples'):
            out.append('- Lines from the brand\'s own pages (match their tone; never reuse their facts): ' +
                       ' / '.join('"%s"' % x for x in v['examples']))
        if v.get('adjust'):
            out.append('- The merchant asked: ' + '; '.join(v['adjust']))
    b = s.get('brief') or {}
    for key, label, _, kind in BRIEF:
        val = b.get(key)
        if not val or key in FACT_FIELDS:
            continue
        val = '; '.join(val) if isinstance(val, list) else val
        out.append('- %s %s' % (label.rstrip('?') + ':', val))
    return '\n'.join(out)


def brand_facts(domain):
    """Facts the merchant stated in setup, in catalog_facts' shape, so drafts and the fact check can use them."""
    b = get(domain).get('brief') or {}
    names = {'different': 'Brand fact', 'proof': 'Certification or award', 'policies': 'Store policy'}
    out = [dict(label=names[k], value=v, source='merchant') for k in FACT_FIELDS for v in b.get(k) or []]
    import article_setup
    import fix_setup
    return out + article_setup.facts(domain) + fix_setup.facts(domain)   # niche answers marked as true (19-20 Oct)


def rules(domain):
    """Mechanical writing rules: words never to use, claims never to make, brands never to name."""
    b = get(domain).get('brief') or {}
    import article_setup
    import fix_setup
    claims = list(b.get('no_claims') or [])
    claims += [c for c in article_setup.no_claims(domain) + fix_setup.no_claims(domain) if c not in claims]
    words = list(b.get('never_words') or [])
    words += [w for w in fix_setup.never_words(domain) if w not in words]
    return dict(never_words=words, no_claims=claims, never_name=b.get('never_name') or [])


# ---- voice ----------------------------------------------------------------------

VOICE_RULES = """You describe how an online store writes, so a writer can match it.

From the PAGES (the store's own product descriptions) and BRAND PAGES (its homepage and About page, if found):
1. traits: 3-5 concrete traits a writer can follow, each with name (2-4 words a merchant recognises at a glance, e.g. "Short, paired sentences") and how (one sentence on how to write that way). Cover things like sentence length, person, spelling (e.g. British), how products are introduced, words or images the brand returns to, what it avoids). No vague praise like "engaging". The PROFILE's identity words are how the brand sees itself: use them only where the pages bear them out.
2. examples: 2-3 sentences copied WORD FOR WORD from PAGES or BRAND PAGES that best show the voice. Pick brand writing, not specs, ingredient lists, policies or navigation text.
3. sample: rewrite the SAMPLE PRODUCT's description in that voice, 2-4 sentences. Use ONLY facts stated in its facts and description. No new claims, numbers, ingredients or benefits, no superlatives.
Apply every point under MERCHANT ADJUSTMENTS, if any."""

VOICE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["traits", "examples", "sample"],
                "properties": {"traits": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["name", "how"],
                    "properties": {"name": {"type": "string"}, "how": {"type": "string"}}}},
                               "examples": {"type": "array", "items": {"type": "string"}},
                               "sample": {"type": "string"}}}

# Where a brand writes as itself rather than about one product. Policy pages are left out: legal tone.
VOICE_PAGES = (('/pages/about', 'About page'), ('/pages/about-us', 'About page'),
               ('/pages/our-story', 'Our story page'), ('/', 'Homepage'))


def _squash(s):
    return re.sub(r'\s+', ' ', re.sub(r'[\u2018\u2019]', "'", re.sub(r'[\u201c\u201d]', '"', s or ''))).strip().lower()


def _trait_text(t):
    """A trait as one line. Traits saved before 16 Oct are plain sentences; newer ones have a name."""
    return '%s: %s' % (t.get('name', ''), t.get('how', '')) if isinstance(t, dict) else str(t)


def best_pages(domain, n=3):
    """The longest product descriptions, skipping repeats (variants or ranges that share one text)."""
    import catalog_facts
    out, seen = [], set()
    for r in sorted(catalog_facts.get(domain), key=lambda r: -len(' '.join(r['description']))):
        key = _squash(' '.join(r['description']))[:200]
        if key and key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) == n:
            break
    return out


def page_text(url, limit=3000):
    """Plain visible text of a page's main content, or '' if it can't be read. Free."""
    import html as _h
    import page_gap
    try:
        raw = page_gap.fetch(url)
    except Exception:
        return ''
    raw = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else (raw or '')
    main = re.search(r'<main\b.*?</main>', raw, re.S | re.I)
    text = re.sub(r'<(script|style|nav|header|footer|form)\b.*?</\1>', ' ', main.group(0) if main else raw,
                  flags=re.S | re.I)
    return re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', ' ', text))).strip()[:limit]


def brand_pages(domain):
    """[(label, text)] for the store's About page (first one found) and homepage. A few seconds, free."""
    out, labels = [], set()
    for path, label in VOICE_PAGES:
        if label == 'About page' and label in labels:
            continue
        text = page_text('https://%s%s' % (domain, path), 2000)
        if len(text) > 200:
            out.append((label, text))
            labels.add(label)
    return out


def _profile_text(domain):
    b = db.brand(domain) or {}
    parts = [('Description', b.get('description') or ''), ('Identity', ', '.join(b.get('identity') or [])),
             ('Industry', b.get('industry') or '')]
    return '\n'.join('%s: %s' % (k, v) for k, v in parts if v) or '(none)'


def keep_examples(examples, sources):
    """Only lines that really are copied from the brand's pages (the model sometimes polishes them)."""
    hay = _squash(' '.join(sources))
    out = []
    for ex in examples or []:
        ex = ex.strip().strip('"').strip()
        if 20 <= len(ex) <= 300 and _squash(ex) in hay and ex not in out:
            out.append(ex)
    return out[:3]


def make_voice(domain, adjust=None, usage=None):
    """Read the best pages and propose a voice. Raises ValueError if the store has no descriptions."""
    import catalog_facts
    import llm
    if not catalog_facts.get(domain):
        catalog_facts.build(domain)
    pages = [p for p in best_pages(domain) if ' '.join(p['description']).strip()]
    if not pages:
        raise ValueError('Your products have no descriptions yet, so there is no voice to learn from.')
    sample = pages[0]
    extra = brand_pages(domain)
    text = ('PAGES:\n%s\n\nBRAND PAGES:\n%s\n\nPROFILE:\n%s\n\nSAMPLE PRODUCT: %s\nFacts:\n%s\nDescription: %s\n\n'
            'MERCHANT ADJUSTMENTS:\n%s') % (
        '\n\n'.join('[%s]\n%s' % (p['title'], ' '.join(p['description'])[:2000]) for p in pages),
        '\n\n'.join('[%s]\n%s' % (label, t) for label, t in extra) or '(none found)', _profile_text(domain),
        sample['title'], '\n'.join('- %s: %s' % (f['label'], f['value']) for f in sample['facts']),
        ' '.join(sample['description'])[:2000], '\n'.join('- ' + a for a in adjust or []) or '(none)')
    res = llm.json_call(VOICE_RULES, text, 'brand_voice', VOICE_SCHEMA, usage=usage, attempts=3)
    sources = [' '.join(p['description']) for p in pages] + [t for _, t in extra]
    return dict(traits=res['traits'][:5], examples=keep_examples(res.get('examples'), sources),
                sample=res['sample'], sample_product=sample['title'],
                pages=[p['title'] for p in pages] + [label for label, _ in extra],
                adjust=list(adjust or []), confirmed=False, at=time.time())


PREFILL_RULES = """You help an online store fill in a brief for a writer, from the store's own pages and profile.

For each field, write what the PAGES and PROFILE support, in the merchant's voice, as a first draft the merchant will correct:
- customers, story, naming: a short answer, or "" if the pages give nothing to go on.
- different, proof, policies: ONLY things the pages or STORE PAGES state outright (no guesses, no generic claims). Each item is a statement the store could print, never a note about what is missing (if shipping isn't stated, just leave it out).
  - proof is only certifications, awards, press mentions, test results or memberships. Ingredients and product features are not proof (leave them out; the agent reads them from the product pages anyway). Usually empty.
  - policies: the concrete terms (shipping cost and times, return window, guarantee), one per line.
- objections: questions a buyer of these products would likely ask before buying (4-8); use the store's FAQ page if there is one.
- always_words: words and phrases the pages return to (3-8).
- never_words: hype words the brand clearly avoids, e.g. superlatives (3-6). Suggestions.
- no_claims: claims a store in this category must not make without proof (e.g. skincare: medical or "clinically proven" claims) (2-5). Suggestions.
- never_name: always [] (comparison pages name competitors unless the merchant lists some here).
- love_page: "" (filled in by code).
- length, format, spelling: pick the option that matches the pages."""


def _prefill_schema():
    props = {}
    for key, _, _, kind in BRIEF:
        if kind == 'lines':
            props[key] = {"type": "array", "items": {"type": "string"}}
        elif kind == 'text':
            props[key] = {"type": "string"}
        else:
            props[key] = {"type": "string", "enum": list(kind)}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


# Public pages every Shopify store has (or usually has) that answer brief questions directly.
STORE_PAGES = ('/policies/shipping-policy', '/policies/refund-policy', '/pages/about', '/pages/about-us',
               '/pages/our-story', '/pages/faq', '/pages/faqs')


def store_pages(domain):
    """[(path, plain text)] for the store's policy, about and FAQ pages that exist. Free; a few seconds."""
    out = []
    for path in STORE_PAGES:
        text = page_text('https://%s%s' % (domain, path))
        if len(text) > 200:
            out.append((path, text))
    return out


def prefill(domain, usage=None):
    """A first draft of the brief from the store's product pages, policy/about/FAQ pages and brand profile."""
    import llm
    pages = best_pages(domain, 5)
    extra = store_pages(domain)
    b = db.brand(domain) or {}
    profile = 'Name: %s\nDescription: %s\nIndustry: %s\nIdentity: %s\nProducts: %s\nMarkets: %s\nCountry: %s' % (
        b.get('brand_name', ''), b.get('description', ''), b.get('industry', ''), ', '.join(b.get('identity', [])),
        ', '.join(b.get('services', [])), ', '.join(b.get('markets', [])), b.get('country', ''))
    text = 'PROFILE:\n%s\n\nPAGES:\n%s\n\nSTORE PAGES (policies, about, FAQ):\n%s' % (profile, '\n\n'.join(
        '[%s]\n%s' % (p['title'], ' '.join(p['description'])[:2000]) for p in pages),
        '\n\n'.join('[%s]\n%s' % (path, t) for path, t in extra) or '(none found)')
    res = llm.json_call(PREFILL_RULES, text, 'brand_brief', _prefill_schema(), usage=usage, attempts=3)
    res['never_name'] = []
    best = pages[0] if pages else None
    res['love_page'] = best['url'] if best and best.get('url') else ''   # their own best-written page, to keep or replace
    res['read'] = [path for path, _ in extra]
    return res


# ---- page -----------------------------------------------------------------------

_TICK = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8" fill="none" '
         'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
STEP_NAMES = (('voice', 'Your voice'), ('brand', 'Your brand'), ('scope', 'What it may change'),
              ('schedule', 'Time zone and pace'), ('facts', 'Missing facts'), ('shopify', 'Shopify'))
# Designed articles (19 Oct 2026): the look the agent read from the store and what it learned from the owner.
LOOK_STEP = ('look', 'Look and lessons')
ARTICLES_STEP = ('articles', 'Your articles')     # article_setup.py: common + niche questions (19 Oct 2026)
FIXPAGES_STEP = ('fixpages', 'Your product pages')   # fix_setup.py: the same for product pages (20 Oct 2026)


def _step_names():
    import config
    if not config.ARTICLES_V2:
        return STEP_NAMES
    return STEP_NAMES[:2] + (ARTICLES_STEP, FIXPAGES_STEP) + STEP_NAMES[2:] + (LOOK_STEP,)


def _after_brand():
    import config
    return 'articles' if config.ARTICLES_V2 else 'scope'


def step_status(domain):
    """{step: (done, one line on where it stands)}, for the setup grid."""
    s = get(domain)
    v = s.get('voice') or {}
    days, pace, hour = schedule(domain)
    day_names = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    when = 'weekdays' if list(days) == [0, 1, 2, 3, 4] else ', '.join(day_names[d] for d in days)
    answered = sum(len(v2) for v2 in (s.get('product_facts') or {}).values())
    try:
        import shopify_connect
        shop = bool(shopify_connect.connection(domain))
    except Exception:                                   # noqa: BLE001
        shop = False
    allowed = len(s.get('allowed') or [])
    return {
        'voice': (bool(v.get('confirmed')), '%d traits confirmed' % len(v.get('traits') or []) if v.get('confirmed') else 'Not confirmed yet'),
        'brand': (bool(s.get('brief_done_at')), 'Filled in from your pages' if s.get('brief_done_at') else 'To do'),
        'scope': (bool(s.get('scope_done_at')), ('%d of %d kinds of change allowed' % (allowed, len(CHANGES))) if s.get('scope_done_at') else 'To do'),
        'schedule': (bool(s.get('schedule_done_at')), ('%d a week, %s at %02d:00' % (pace, when, hour)) if s.get('schedule_done_at') else 'To do'),
        'facts': (bool(s.get('part1_done_at')), ('%d fact%s answered' % (answered, '' if answered == 1 else 's')) if s.get('part1_done_at') else 'To do'),
        'shopify': (shop, 'Connected' if shop else 'Not connected'),
        'articles': _articles_status(s),
        'fixpages': __import__('fix_setup').status(s),
        'look': (True, '%d lesson%s learned' % (len(s.get('article_lessons') or []), '' if len(s.get('article_lessons') or []) == 1 else 's')
                 if s.get('brand_style') else 'Read from your site with the first article'),
    }


def _articles_status(s):
    ab = s.get('article_brief') or {}
    if ab.get('done_at'):
        return True, '%d niche question%s answered' % (len(ab.get('questions') or []), '' if len(ab.get('questions') or []) == 1 else 's')
    return False, 'Filled in, not reviewed' if ab.get('answers') is not None else 'To do'


def _steps(current, domain=None):
    """Setup and Settings both open on this grid (version 4 of the 16 Oct prototypes): every step with where it
    stands, the open one highlighted, and a progress line. Steps link once they're done, or once setup is."""
    st = step_status(domain) if domain else {}
    names = _step_names()
    finished = sum(1 for k, _ in names if st.get(k, (False,))[0])
    all_done = domain and done(domain)
    cells = ''
    for i, (k, label) in enumerate(names):
        ok, line = st.get(k, (False, ''))
        inner = '<i>%s</i><div><b>%s</b><span>%s</span></div>' % (_TICK if ok else i + 1, E(label), E(line))
        cls = 'cs-step%s' % (' cs-done' if ok else '')
        cur = ' aria-current="step"' if k == current else ''
        if all_done or ok or k == current:
            cells += '<a class="%s" href="%s"%s>%s</a>' % (
                cls, E('/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step=k))), cur, inner)
        else:
            cells += '<div class="%s"%s>%s</div>' % (cls, cur, inner)
    note = ('Everything is set. Change any step here.' if all_done and finished == len(names) else
            'Set up. Connect Shopify so pages you drag to Live go live on your store.' if all_done else
            'The agent starts drafting when you finish Missing facts.')
    return ('<div class="cs-progress"><span class="cs-meter" role="progressbar" aria-valuemin="0" aria-valuemax="%d" '
            'aria-valuenow="%d"><i style="width:%d%%"></i></span><span><b>%d of %d done.</b> %s</span></div>'
            '<nav class="cs-grid" aria-label="Setup steps">%s</nav>') % (
        len(names), finished, round(100 * finished / len(names)), finished, len(names), note, cells)


def _hidden(domain, action):
    return ('<input type="hidden" name="d" value="%s"><input type="hidden" name="action" value="%s">'
            % (E(domain), action))


def page(domain, q):
    s = get(domain)
    step = q.get('step') or ('voice' if not (s.get('voice') or {}).get('confirmed') else
                             'brand' if not s.get('brief_done_at') else
                             'articles' if _after_brand() == 'articles' and not (s.get('article_brief') or {}).get('done_at') else
                             'fixpages' if _after_brand() == 'articles' and not (s.get('fix_brief') or {}).get('done_at') else
                             'scope' if not s.get('scope_done_at') else
                             'schedule' if not s.get('schedule_done_at') else 'facts')
    if step == 'brand':
        return _steps('brand', domain) + _brand(domain, s)
    if step == 'schedule':
        return _steps('schedule', domain) + _schedule_page(domain, s)
    if step == 'facts':
        return _steps('facts', domain) + _facts_page(domain, s)
    if step == 'shopify':
        return _steps('shopify', domain) + shopify_section(domain, q)
    if step == 'look':
        return _steps('look', domain) + look_page(domain, s, q)
    if step == 'fixpages':
        import fix_setup
        return _steps('fixpages', domain) + fix_setup.page(
            domain, lambda a: _hidden(domain, a), _busy, E,
            '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='articles')))
    if step == 'articles':
        import article_setup
        return _steps('articles', domain) + article_setup.page(
            domain, lambda a: _hidden(domain, a), _busy, E,
            '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='brand')))
    intro = ('<p class="cr-muted">Before it writes anything, the agent needs to know how you sound and what it may '
             'touch. You can change both later under Settings.</p>')
    if step == 'scope':
        return _steps('scope', domain) + intro + _scope(domain, s)
    return _steps('voice', domain) + intro + _voice(domain, s)


def look_page(domain, s, q=None):
    """The article look read from the store, the owner's corrections, and every lesson the agent keeps."""
    import brand_style
    raw = s.get('brand_style')
    o = s.get('brand_style_overrides') or {}
    if not raw:
        look = ('<p class="cr-muted">Nothing read yet. The agent reads your fonts and colours from your site when it '
                'writes your first article.</p><form method="post" action="/content">%s<button class="ca-btn">Read my site now'
                '</button></form>' % _hidden(domain, 'look_relearn'))
    else:
        st = brand_style.apply_overrides(raw, o)
        fonts = brand_style.families(raw)

        def font_select(role, label):
            cur = st['fonts'][role]['family']
            opts = ''.join('<option%s>%s</option>' % (' selected' if f == cur else '', E(f)) for f in fonts)
            return '<label class="cs-field"><span>%s</span><select name="%s_font">%s</select></label>' % (label, role, opts)

        colours = sorted(set(raw['colors'].values()))

        def colour_select(key, label):
            cur = st['colors'][key]
            opts = ''.join('<option value="%s"%s>%s</option>' % (c, ' selected' if c == cur else '', c) for c in colours)
            return ('<label class="cs-field"><span>%s <i class="cs-sw" style="background:%s"></i></span><select name="%s">%s'
                    '</select></label>' % (label, E(cur), key, opts))
        look = ('<p class="cr-muted">Read from your site: %s Change anything here; your articles use it from the next '
                'preview.</p><form method="post" action="/content" class="cs-look">%s%s%s%s%s%s'
                '<label class="cs-check"><input type="checkbox" name="heading_upper" value="1"%s> Headings in capitals</label>'
                '<label class="cs-check"><input type="checkbox" name="square" value="1"%s> Square buttons</label>'
                '<div class="cs-row"><button class="ca-btn ca-primary">Save the look</button></div></form>'
                '<form method="post" action="/content">%s<button class="ca-btn">Read my site again</button></form>') % (
            E(brand_style.summary(raw)), _hidden(domain, 'look_save'), font_select('heading', 'Headings'),
            font_select('body', 'Text'), font_select('label', 'Small labels'), colour_select('accent', 'Accent colour'),
            colour_select('ink', 'Text colour'), ' checked' if st.get('heading_upper') else '',
            ' checked' if not st.get('radius') else '', _hidden(domain, 'look_relearn'))
    ls = s.get('article_lessons') or []
    lessons = ''.join(
        '<li><span>%s <em class="cr-muted">%s</em></span><form method="post" action="/content">%s'
        '<input type="hidden" name="lesson" value="%s"><button class="ca-btn ca-small">Remove</button></form></li>' % (
            E(l['text']), 'from your request' if l.get('source') == 'request' else 'from your edits',
            _hidden(domain, 'lesson_remove'), E(l['id'])) for l in reversed(ls)) or \
        '<li class="cr-muted">None yet. Ask for changes on an article preview, or edit its text, and lasting preferences show up here.</li>'
    pb = s.get('niche_playbook') or {}
    src = ', '.join(x.get('site', '') for x in pb.get('sources') or [])
    niche = ('<p class="cr-muted">Built the way %s write their articles (the brand articles AI cites for your buyer '
             'questions). Refreshed monthly.</p>' % E(src)) if src else \
        '<p class="cr-muted">The agent studies the brand articles AI cites for your buyer questions when it writes your first article.</p>'
    return ('<section class="cr-box"><h2>How your articles look</h2>%s</section>'
            '<section class="cr-box"><h2>What the agent learned from you</h2><p class="cr-muted">Every future article follows '
            'these. Remove any that are wrong.</p><ul class="cs-lessons">%s</ul></section>'
            '<section class="cr-box"><h2>Learned from your niche</h2>%s<form method="post" action="/content">%s'
            '<button class="ca-btn">Look again</button></form></section>') % (look, lessons, niche, _hidden(domain, 'playbook_relearn')) + \
        fix_lessons_box(domain) + instagram_box(domain, q or {})


def fix_lessons_box(domain):
    """What the agent learned from the owner's changes to product page fixes (fix_learning.py, 20 Oct 2026)."""
    import fix_learning
    ls = fix_learning.lessons(domain)
    items = ''.join(
        '<li><span>%s <em class="cr-muted">%s</em></span><form method="post" action="/content">%s'
        '<input type="hidden" name="lesson" value="%s"><button class="ca-btn ca-small">Remove</button></form></li>' % (
            E(l['text']), 'from your request' if l.get('source') == 'request' else 'from your edits',
            _hidden(domain, 'fix_lesson_remove'), E(l['id'])) for l in reversed(ls)) or \
        '<li class="cr-muted">None yet. Change a product page fix on its preview, and lasting preferences show up here.</li>'
    return ('<section class="cr-box"><h2>What the agent learned for your product pages</h2><p class="cr-muted">Every future '
            'product page fix and FAQ follows these. Remove any that are wrong.</p><ul class="cs-lessons">%s</ul></section>' % items)


def instagram_box(domain, q):
    """The store's own Instagram photos for articles and the stories page (social_photos.py, 20 Oct 2026)."""
    import social_photos
    h = social_photos.handle(domain)
    st = social_photos.state(domain)
    pics = social_photos.photos(domain)
    err = ('<p class="ca-error">%s</p>' % E(q['error'])) if q.get('error') else ''
    if social_photos.running(domain) or (st.get('status') == 'running' and time.time() - (st.get('started') or 0) < 600):
        status = ('<p class="cr-muted">Reading @%s now. It takes a minute or two; refresh this page.</p>'
                  '<meta http-equiv="refresh" content="20">' % E(h))
    elif st.get('status') == 'failed':
        status = '<p class="ca-error">%s</p>' % E(st.get('error') or 'Reading Instagram didn\'t work.')
    elif pics:
        status = ('<p class="cr-muted">%d photo%s from @%s, read %s. They show in the photo picker when you edit an article '
                  '(pink edge), and can go at the bottom of your stories page.</p>' % (
                      len(pics), '' if len(pics) == 1 else 's', E(st.get('read_handle') or h),
                      E(time.strftime('%b %-d', time.localtime(st.get('at') or time.time())))))
    else:
        status = ('<p class="cr-muted">Your own Instagram is often where your best lifestyle photos are. The agent can copy '
                  'your recent photo posts (up to %d) so you can use them in articles. Videos are skipped. Costs about '
                  '5 cents a read.</p>' % social_photos.MAX_POSTS)
    wait = social_photos.wait_left(domain)
    btn = '' if not h or social_photos.running(domain) else (
        '<form method="post" action="/content">%s<button class="ca-btn%s"%s>%s</button></form>' % (
            _hidden(domain, 'instagram_fetch'), '' if pics else ' ca-primary', ' disabled' if wait else '',
            ('Read again in %d days' % max(1, wait // 86400)) if wait else
            ('Get new photos from Instagram' if pics else 'Get photos from Instagram')))
    grid = ''.join('<img src="%s" alt="" loading="lazy">' % E(u) for u in pics[:12])
    return ('<section class="cr-box" id="instagram"><h2>Photos from your Instagram</h2>%s%s'
            '<form method="post" action="/content" class="cs-ig">%s<label>Instagram handle <input name="handle" value="%s" '
            'placeholder="yourbrand"></label><button class="ca-btn">Save</button></form>%s%s</section>') % (
        status, err, _hidden(domain, 'instagram_handle'), E(('@' + h) if h else ''),
        ('<div class="cs-iggrid">%s</div>' % grid) if grid else '', btn)


def _busy(label, seconds):
    """The filling-P loader while the agent works (p_loader.py)."""
    import p_loader
    return p_loader.busy(label, seconds)


def _voice(domain, s):
    v = s.get('voice')
    if not v:
        return ('<section class="cr-box"><h2>Your voice</h2><p class="cr-muted">The agent reads your longest product '
                'descriptions, your About page and homepage, and describes how you write, so its drafts sound like you, not like a robot.</p>'
                '<form method="post" action="/content" id="cs-read" %s>%s<button class="ca-btn ca-primary">'
                'Read my product pages</button></form></section>'
                '<script>document.getElementById("cs-read").requestSubmit();</script>') % (
            _busy('Reading your product pages', 20), _hidden(domain, 'voice'))
    def trait(t):
        if isinstance(t, dict):
            return '<li class="cs-trait"><strong>%s</strong><span>%s</span></li>' % (E(t.get('name', '')), E(t.get('how', '')))
        return '<li class="cs-trait"><span>%s</span></li>' % E(t)
    traits = ''.join(trait(t) for t in v['traits'])
    adjusted = ('<p class="cs-asked">You asked: %s</p>' % E('; '.join(v['adjust']))) if v.get('adjust') else ''
    lines = ('<div class="cs-block"><h3 class="cs-label">Lines from your pages it will match</h3><ul class="cs-quotes">%s</ul></div>'
             % ''.join('<li>\u201c%s\u201d</li>' % E(x) for x in v['examples'])) if v.get('examples') else ''
    return ('<section class="cr-box cs-voice"><header class="cs-head"><h2>This is how you write</h2>'
            '<p class="cs-from">Read from %s</p></header>'
            '<div class="cs-block"><h3 class="cs-label">Your style</h3><ul class="cs-trait-grid">%s</ul></div>%s'
            '<div class="cs-block"><h3 class="cs-label">A sample in your voice</h3><figure class="cs-sample-card">'
            '<figcaption>%s</figcaption><blockquote>%s</blockquote></figure></div>%s'
            '<div class="cs-actions"><form method="post" action="/content">%s<button class="ca-btn ca-primary">Sounds like us'
            '</button></form>'
            '<form method="post" action="/content" class="cs-adjust" %s>%s<label for="cs-adj">Not quite? Tell it what to change</label>'
            '<div class="cs-adjust-row"><input id="cs-adj" name="adjust" placeholder="e.g. shorter sentences, less poetic, no exclamation marks">'
            '<button class="ca-btn">Try again</button></div></form></div></section>') % (
        E(', '.join(v['pages'])), traits, lines, E(v['sample_product']), E(v['sample']), adjusted,
        _hidden(domain, 'voice_ok'), _busy('Rewriting your sample', 20), _hidden(domain, 'voice'))


def _brand(domain, s):
    b = s.get('brief')
    if b is None:
        return ('<section class="cr-box"><h2>Your brand</h2><p class="cr-muted">The more the agent knows, the more its '
                'drafts sound like someone who works at your brand. It fills in a first draft from your pages; you '
                'correct it.</p><form method="post" action="/content" id="cs-brief" %s>%s<button class="ca-btn ca-primary">'
                'Fill in from my pages</button></form></section>'
                '<script>document.getElementById("cs-brief").requestSubmit();</script>') % (
            _busy('Reading your pages', 30), _hidden(domain, 'brief_prefill'))
    rows = []
    for key, label, hint, kind in BRIEF:
        val = b.get(key)
        hint_html = '<span class="cs-hint">%s</span>' % E(hint) if hint else ''
        if isinstance(kind, tuple):
            opts = ''.join('<label class="cs-opt"><input type="radio" name="b.%s" value="%s"%s> %s</label>'
                           % (key, E(o), ' checked' if o == val else '', E(o)) for o in kind)
            rows.append('<div class="cs-q"><span class="cs-label">%s</span>%s<div class="cs-opts">%s</div></div>'
                        % (E(label), hint_html, opts))
            continue
        text = '\n'.join(val) if isinstance(val, list) else (val or '')
        lines = max(2, min(8, text.count('\n') + 2)) if kind == 'lines' else max(2, min(6, len(text) // 70 + 1))
        fact = ' <span class="cs-fact">The agent may state these as facts</span>' if key in FACT_FIELDS else ''
        rows.append('<div class="cs-q"><label class="cs-label" for="b-%s">%s%s</label>%s<textarea id="b-%s" name="b.%s" rows="%d">%s</textarea></div>'
                    % (key, E(label), fact, hint_html, key, key, lines, E(text)))
    return ('<form method="post" action="/content">%s<section class="cr-box"><h2>Your brand</h2>'
            '<p class="cr-muted">Filled in from your pages as a first draft. Correct anything that\'s wrong and add what '
            'only you know: this is what every draft is written from. Anything in a box marked "may state as facts" '
            'can appear on your pages, so only write what\'s true.</p><div class="cs-brief">%s</div></section>'
            '<div class="cs-row"><a class="ca-btn" href="%s">Back</a><button class="ca-btn ca-primary">Save and continue</button>'
            '</div></form>') % (_hidden(domain, 'brief'), ''.join(rows),
                                E('/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='voice'))))


def _scope(domain, s):
    import catalog_facts
    allowed = set(s['allowed'])
    leave = set(s['leave_alone'])
    boxes = ''.join('<label class="cs-check"><input type="checkbox" name="allow.%s" value="1"%s> %s</label>'
                    % (k, ' checked' if k in allowed else '', E(l)) for k, l in CHANGES)
    products = sorted(catalog_facts.get(domain), key=lambda r: r['title'].lower())
    plist = ''.join('<label class="cs-check cs-prod"><input type="checkbox" name="leave.%s" value="1"%s>%s %s</label>'
                    % (E(p['handle']), ' checked' if p['handle'] in leave else '',
                       ('<img src="%s" alt="">' % E(p['image'])) if p.get('image') else '', E(p['title']))
                    for p in products)
    return ('<form method="post" action="/content">%s<section class="cr-box"><h2>What the agent may change</h2>'
            '<p class="cr-muted">It only drafts these. Nothing reaches your store until you approve it.</p>'
            '<div class="cs-grid">%s</div></section>'
            '<section class="cr-box"><h2>Products to leave alone</h2><p class="cr-muted">The agent won\'t draft changes '
            'for these, for example a bestseller whose page you don\'t want touched.</p><div class="cs-plist">%s</div></section>'
            '<div class="cs-row"><a class="ca-btn" href="%s">Back</a><button class="ca-btn ca-primary">Save and continue</button></div></form>') % (
        _hidden(domain, 'scope'), boxes, plist or '<p class="cr-muted">No products read yet.</p>',
        E('/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='brand'))))


def act(domain, form):
    """Returns (code, redirect or html)."""
    import llm
    s = get(domain)
    back = lambda step: '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step=step))
    action = form.get('action')
    if action == 'voice':
        adjust = list((s.get('voice') or {}).get('adjust') or [])
        if form.get('adjust', '').strip():
            adjust.append(form['adjust'].strip()[:300])
        try:
            s['voice'] = make_voice(domain, adjust)
        except ValueError as e:
            s['voice'] = dict(traits=[], sample=str(e), sample_product='', pages=[], adjust=adjust, confirmed=False)
        except llm.LLMError as e:
            return 200, ('<div class="ca-page" data-rail-page="content"><div class="ca-empty"><p>The writing service '
                         'didn\'t answer (%s). <a href="%s">Try again</a>.</p></div></div>') % (E(str(e)), E(back('voice')))
        put(domain, s)
        return 303, back('voice')
    if action == 'articles_prefill':
        import article_setup
        try:
            ab = article_setup.prefill(domain)
        except llm.LLMError:
            ab = dict(niche='', questions=[], answers={}, prefilled_at=time.time())   # the common questions, empty
        s = get(domain)
        s['article_brief'] = ab
        put(domain, s)
        return 303, back('articles')
    if action == 'articles':
        import article_setup
        article_setup.save_form(domain, form)
        return 303, back('fixpages') if not (get(domain).get('fix_brief') or {}).get('done_at') else \
            back('scope') if not done(domain) else back('look')
    if action == 'fixpages_prefill':
        import fix_setup
        try:
            fb = fix_setup.prefill(domain)
        except llm.LLMError:
            fb = dict(niche='', questions=[], answers={}, prefilled_at=time.time())
        s = get(domain)
        s['fix_brief'] = fb
        put(domain, s)
        return 303, back('fixpages')
    if action == 'fixpages':
        import fix_setup
        fix_setup.save_form(domain, form)
        return 303, back('scope') if not done(domain) else back('look')
    if action == 'fix_lesson_remove':
        import fix_learning
        fix_learning.remove_lesson(domain, form.get('lesson', ''))
        return 303, back('look')
    if action in ('look_save', 'look_relearn', 'lesson_remove', 'playbook_relearn'):
        return _look_act(domain, form, back('look'))
    if action == 'voice_ok' and s.get('voice'):
        s['voice']['confirmed'] = True
        put(domain, s)
        return 303, back('brand' if not s.get('brief_done_at') else _after_brand())
    if action == 'brief_prefill':
        try:
            s['brief'] = prefill(domain)
        except llm.LLMError:
            s['brief'] = {}                     # empty form: the merchant fills it in
        put(domain, s)
        return 303, back('brand')
    if action == 'brief':
        b = {}
        for key, _, _, kind in BRIEF:
            raw = form.get('b.' + key, '').strip()
            b[key] = [x.strip(' -\u2022\t') for x in raw.splitlines() if x.strip(' -\u2022\t')] if kind == 'lines' \
                else (raw if not isinstance(kind, tuple) or raw in kind else '')
        s['brief'] = b
        s['brief_done_at'] = time.time()
        put(domain, s)
        return 303, back(_after_brand())
    if action == 'scope':
        s['allowed'] = [k for k, _ in CHANGES if form.get('allow.' + k)]
        s['leave_alone'] = [k[6:] for k in form if k.startswith('leave.')]
        s['scope_done_at'] = time.time()
        put(domain, s)
        return 303, back('schedule') if not done(domain) else '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox'))
    if action == 'schedule':
        import storetime
        tz = form.get('tz', '')
        if tz in zone_choices(storetime.zone_name(domain)):
            s['timezone'] = tz
        s['days'] = [i for i in range(7) if form.get('day.%d' % i)] or [0, 1, 2, 3, 4]
        try:
            s['pace'] = max(1, min(7, int(form.get('pace', 3))))
            s['hour'] = max(0, min(23, int(form.get('hour', 9))))
        except ValueError:
            pass
        s['schedule_done_at'] = time.time()
        put(domain, s)
        storetime.forget(domain)
        return 303, back('facts') if not done(domain) else '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar'))
    if action == 'missing':
        s['missing'] = find_missing(domain)
        put(domain, s)
        return 303, back('facts')
    if action == 'facts':
        pf = {}
        for k, v in form.items():
            if k.startswith('m.') and v.strip():
                handle, label = k[2:].split('.', 1)
                pf.setdefault(handle, []).append(dict(label=label, value=v.strip()[:300]))
        s['product_facts'] = pf
        first = not s.get('part1_done_at')
        s['part1_done_at'] = s.get('part1_done_at') or time.time()
        put(domain, s)
        if first:
            plan_first_weeks(domain)
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar'))
    return 400, '<h1>Bad request</h1>'


CSS = """
.cs-look{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px 16px;margin:0 0 12px}
.cs-field{display:grid;gap:5px;font-size:13px;font-weight:600;color:#586579}
.cs-field select{padding:8px 10px;border:1px solid #d5dbe5;border-radius:8px;background:#fff;font:inherit;font-size:14px;color:#1a2436}
.cs-sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;border:1px solid #d5dbe5}
.cs-check{display:flex;gap:8px;align-items:center;font-size:14px;color:inherit}
.cs-look .cs-row{grid-column:1/-1}
.cs-ig{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin:10px 0 12px}
.cs-ig label{display:flex;flex-direction:column;gap:4px;font-size:13px;font-weight:600}
.cs-ig input{padding:8px 10px;border:1px solid #d6dce5;border-radius:8px;font:inherit;min-width:220px}
.cs-iggrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(84px,1fr));gap:6px;margin:0 0 12px}
.cs-iggrid img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px}
.cs-lessons{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.cs-lessons li{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 0;border-top:1px solid #eef1f5;font-size:14px}
.cs-lessons em{font-style:normal;font-size:12.5px;margin-left:6px}
.ca-small{padding:5px 10px;font-size:12.5px}
.cs-progress{display:flex;align-items:center;gap:14px;margin:0 0 14px;font-size:14px;font-weight:500;color:#586579;flex-wrap:wrap}
.cs-progress b{color:#0b1b35}
.cs-meter{flex:0 0 240px;height:8px;border-radius:999px;background:#eef1f5;overflow:hidden}
.cs-meter i{display:block;height:100%;background:#1c7a46;border-radius:inherit;transition:width .4s ease}
.cs-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 20px}
.cs-step{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:start;padding:14px 16px;border-radius:14px;background:#ffffff;border:1px solid #e6e9ef;text-decoration:none;color:inherit;transition:border-color .15s,box-shadow .15s}
a.cs-step:hover{border-color:#0b1b35}
.cs-step[aria-current]{border-color:#0b1b35;box-shadow:0 0 0 3px #eef1f5}
.cs-step i{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;font-style:normal;font-weight:700;font-size:13px;background:#eef1f5;color:#586579}
.cs-step i svg{width:15px;height:15px}
.cs-step.cs-done i{background:#e3f4ea;color:#1c7a46}
.cs-step b{display:block;color:#0b1b35;font-size:15px}
.cs-step span{font-size:13px;font-weight:500;color:#586579}
div.cs-step{opacity:.6}
@media (max-width:900px){.cs-grid{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.cs-grid{grid-template-columns:1fr}.cs-meter{flex-basis:100%}}
.cs-batch-live{display:flex;align-items:center;gap:16px;padding:14px 18px}
.cs-batch-text{display:grid;gap:4px;flex:1;min-width:0}
.cs-batch-text strong{font-size:15px;font-weight:700;color:#0b1b35}
.cs-batch-text span{font-size:13.5px;font-weight:500;color:#586579}
.cs-bar{height:6px;border-radius:999px;background:#e6ebf3;overflow:hidden;margin-top:4px;max-width:420px}
.cs-bar i{display:block;height:100%;border-radius:inherit;background:#0b1b35;transition:width .6s ease}
.cs-traits{margin:0 0 12px;padding-left:18px;display:grid;gap:4px;font-size:14.5px}
.cs-voice{padding:24px 26px}
.cs-head h2{font-size:21px;font-weight:700;color:#0b1b35;margin:0}
.cs-from{margin:4px 0 0;font-size:13.5px;font-weight:500;color:#586579}
.cs-block{margin:22px 0 0}
.cs-label{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#7a8597;margin:0 0 10px}
.cs-trait-grid{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.cs-trait{display:grid;gap:4px;align-content:start;padding:14px 16px;border:1px solid #e6e9ef;border-radius:10px;background:#fafbfd}
.cs-trait strong{font-size:15px;font-weight:700;color:#0b1b35}
.cs-trait span{font-size:13.5px;font-weight:500;line-height:1.5;color:#4a5568}
.cs-quotes{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.cs-quotes li{padding:7px 12px;border-radius:999px;background:#eef2f8;font-size:13.5px;font-weight:600;color:#0b1b35}
.cs-sample-card{margin:0;padding:18px 20px;border-radius:12px;background:#eef3fc;border:1px solid #d5e1f7}
.cs-sample-card figcaption{font-size:13px;font-weight:700;color:#2f6fdb;margin:0 0 8px}
.cs-sample-card blockquote{margin:0;font-size:16px;font-weight:500;line-height:1.65;color:#1a2436}
.cs-asked{margin:12px 0 0;font-size:13.5px;font-weight:500;color:#586579}
.cs-actions{margin:24px 0 0;padding:20px 0 0;border-top:1px solid #eef1f5;display:grid;gap:16px}
.cs-actions form{margin:0}
.cs-adjust-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.cs-adjust-row input{flex:1;min-width:220px}
.cs-actions .cs-adjust{border-top:0;padding-top:0}
.cs-h3{font-size:13px;font-weight:700;color:#586579;margin:14px 0 6px}
.cs-sample{margin:0 0 14px;padding:12px 14px;border-left:3px solid #0b1b35;background:#f6f8fb;border-radius:0 8px 8px 0;font-size:14.5px;line-height:1.6}
.cs-row{display:flex;gap:8px;margin:0 0 14px}
.cs-row form{margin:0}
.cs-adjust{display:grid;gap:6px;border-top:1px solid #eef1f5;padding-top:12px}
.cs-adjust label{font-size:13px;font-weight:600;color:#586579}
.cs-adjust input{padding:9px 11px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:14px;background:#ffffff;color:#1a2436}
.cs-adjust .ca-btn{justify-self:start}
.cs-brief{display:grid;gap:16px}
.cs-q{display:grid;gap:4px}
.cs-label{font-size:14px;font-weight:600;color:#1a2436}
.cs-hint{font-size:12.5px;color:#586579}
.cs-fact{margin-left:6px;font-size:11.5px;font-weight:600;padding:2px 7px;border-radius:999px;background:#e6f4ec;color:#047857}
.cs-q textarea{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:14px;line-height:1.5;background:#ffffff;color:#1a2436}
.cs-opts{display:flex;flex-wrap:wrap;gap:8px}
.cs-opt{display:flex;gap:6px;align-items:center;font-size:14px;padding:7px 10px;border:1px solid #eef1f5;border-radius:8px}
.cs-select{padding:8px 10px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:14px;background:#ffffff;color:#1a2436}
.cs-in{padding:9px 11px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:14px;background:#ffffff;color:#1a2436}
.cs-ph{display:flex;align-items:center;gap:10px}.cs-ph img{width:36px;height:36px;border-radius:8px;object-fit:cover}
.cs-batch{padding:10px 12px;border-radius:8px;background:#eef4ff;color:#0b1b35;font-size:14px;font-weight:600;margin:0 0 12px}
.cs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.cs-check{display:flex;align-items:center;gap:8px;font-size:14px;padding:8px 10px;border:1px solid #eef1f5;border-radius:8px}
.cs-plist{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;max-height:360px;overflow:auto}
.cs-prod img{width:28px;height:28px;border-radius:6px;object-fit:cover}
"""


# ---- Day 11d: part 2 - schedule, missing facts, first two weeks ----------------

DAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
FACT_PRODUCTS = 25          # products asked about in setup, most-needed first; the rest come later in Settings
FIRST_WEEKS = 2


def _look_act(domain, form, back):
    import article_learning
    import brand_style
    action = form.get('action')
    if action == 'look_relearn':
        try:
            brand_style.learn(domain, force=True)
        except Exception:                                                   # noqa: BLE001 - site unreachable
            pass
    elif action == 'playbook_relearn':
        import niche_examples
        try:
            niche_examples.learn(domain, force=True)
        except Exception:                                                   # noqa: BLE001
            pass
    elif action == 'lesson_remove':
        article_learning.remove_lesson(domain, form.get('lesson', ''))
    elif action == 'look_save':
        raw = get(domain).get('brand_style')
        if raw:
            fonts = brand_style.families(raw)
            colours = set(raw['colors'].values())
            for role in ('heading', 'body', 'label'):
                v = form.get(role + '_font', '')
                article_learning.set_override(domain, role + '_font', v if v in fonts and v != raw['fonts'][role]['family'] else '')
            for k in ('accent', 'ink'):
                v = form.get(k, '').lower()
                article_learning.set_override(domain, k, v if v in colours and v != raw['colors'][k] else '')
            up = bool(form.get('heading_upper'))
            article_learning.set_override(domain, 'heading_upper', up if up != bool(raw.get('heading_upper')) else '')
            radius = 0 if form.get('square') else (raw.get('radius') or 6)
            article_learning.set_override(domain, 'radius', radius if radius != (raw.get('radius') or 0) else '')
    return 303, back


def schedule(domain):
    """(publish days as weekday numbers, items per week, publish hour) with defaults."""
    s = get(domain)
    import content_plan
    days = s.get('days') or [0, 1, 2, 3, 4]
    cap = min(len(days), content_plan.max_pace(domain))
    return days, max(1, min(cap, int(s.get('pace') or 3))), int(s.get('hour') or 9)


def zone_choices(current):
    import storetime
    zones = sorted(set(storetime.ZONES.values()) | {
        'America/New_York', 'America/Chicago', 'America/Denver', 'America/Phoenix', 'America/Los_Angeles',
        'America/Anchorage', 'Pacific/Honolulu', 'Europe/London', 'UTC', current})
    return zones


def product_facts(domain, handle):
    """Facts the merchant answered for one product in setup, in catalog_facts' shape."""
    pf = (get(domain).get('product_facts') or {}).get(handle) or []
    return [dict(label=f['label'], value=f['value'], source='merchant') for f in pf if f.get('value')]


MISSING_RULES = """For each product of an online store, list the facts a buyer of that kind of product checks before buying that the product's FACTS and DESCRIPTION do not state (e.g. skincare: skin type, size in ml, how to use, key ingredient amounts, fragrance; a cap: sizes, fit, material, care).
3-6 per product, most important first. label: short (e.g. "Skin type"). question: plain, answerable in a few words.
suggestion: ONLY if the answer is stated somewhere in OTHER STORE TEXT; otherwise "". Never guess.
web_suggestion and web_source: ONLY if one of THAT product's OFF-SITE PAGES states the answer outright: the answer, copied as written, and the page's id (e.g. "W2"). Otherwise both "". Skip a page that seems to be about a different product, size or version."""

MISSING_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["products"], "properties": {
    "products": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "required": ["handle", "missing"], "properties": {
                     "handle": {"type": "string"},
                     "missing": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                 "required": ["label", "question", "suggestion", "web_suggestion", "web_source"],
                                 "properties": {
                                     "label": {"type": "string"}, "question": {"type": "string"},
                                     "suggestion": {"type": "string"}, "web_suggestion": {"type": "string"},
                                     "web_source": {"type": "string"}}}}}}}}}


def _priority(domain):
    """Product handles, the ones in open Opportunities first."""
    import catalog_facts
    order = []
    try:
        import briefs
        ps = db.get_prompt_set(domain)
        snap = {c['id']: c['handle'] for c in (ps or {}).get('catalog_snapshot', [])}
        index = {q: i for i, q in enumerate((ps or {}).get('prompts', []))}
        for r in briefs.candidates(domain):
            for q in ([r['key']] if r['key'] in index else []):
                for pid in ps['relevance'][index[q]] if index[q] < len(ps['relevance']) else []:
                    h = snap.get(pid)
                    if h and h not in order:
                        order.append(h)
    except Exception:
        pass
    for r in catalog_facts.get(domain):
        if r['handle'] not in order:
            order.append(r['handle'])
    return order


def find_missing(domain, usage=None):
    """{handle: [missing fact]} for the most-needed products. One helper call per 5 products."""
    import catalog_facts
    import llm
    recs = {r['handle']: r for r in catalog_facts.get(domain)}
    handles = [h for h in _priority(domain) if h in recs][:FACT_PRODUCTS]
    brief = get(domain).get('brief') or {}
    other = ' '.join(' '.join(v) if isinstance(v, list) else str(v) for v in brief.values())[:3000]
    try:
        import offsite_facts
        web = offsite_facts.for_products(domain, [recs[h] for h in handles])
    except Exception:                                   # noqa: BLE001 - off-site pages are a bonus
        web = {}
    out = {}
    for i in range(0, len(handles), 5):
        chunk = [recs[h] for h in handles[i:i + 5]]
        text = 'PRODUCTS:\n%s\n\nOTHER STORE TEXT:\n%s' % ('\n\n'.join(
            '[%s] %s\nFACTS:\n%s\nDESCRIPTION: %s\nOFF-SITE PAGES:\n%s' % (
                r['handle'], r['title'], '\n'.join('- %s: %s' % (f['label'], f['value']) for f in r['facts']),
                ' '.join(r['description'])[:1500],
                '\n'.join('[%s] %s: %s' % (w['id'], w['site'], w['text']) for w in web.get(r['handle'], [])) or '(none)')
            for r in chunk), other or '(none)')
        try:
            res = llm.json_call(MISSING_RULES, text, 'missing_facts', MISSING_SCHEMA, usage=usage, attempts=3)
        except llm.LLMError:
            continue
        for p in res['products']:
            if p['handle'] in recs:
                out[p['handle']] = [_web(it, web.get(p['handle'], [])) for it in p['missing'][:6]]
    return out


def _web(item, pages):
    """Keep an off-site suggestion only if its page really states it, and remember where it came from."""
    import offsite_facts
    val, src = (item.pop('web_suggestion', '') or '').strip(), item.pop('web_source', '')
    page = next((w for w in pages if w['id'] == src), None)
    if val and page and offsite_facts.supported(val, page['text']):
        item['web'] = dict(value=val[:200], url=page['url'], site=page['site'])
    return item


def _schedule_page(domain, s):
    import storetime
    current = storetime.zone_name(domain)
    days, pace, hour = schedule(domain)
    zones = ''.join('<option value="%s"%s>%s</option>' % (E(z), ' selected' if z == current else '', E(z.replace('_', ' ')))
                    for z in zone_choices(current))
    day_boxes = ''.join('<label class="cs-opt"><input type="checkbox" name="day.%d" value="1"%s> %s</label>'
                        % (i, ' checked' if i in days else '', d) for i, d in enumerate(DAYS))
    import content_plan
    paces = ''.join('<option value="%d"%s>%d a week</option>' % (n, ' selected' if n == pace else '', n)
                    for n in range(1, content_plan.max_pace(domain) + 1))
    fx, ar = content_plan.allowance(domain, 'fixes'), content_plan.allowance(domain, 'articles')
    plan_note = ((' Your plan includes %d product page fixes%s a month.' % (fx, ' and %d articles' % ar if ar else ''))
                 if fx is not None else '')
    hours = ''.join('<option value="%d"%s>%02d:00</option>' % (h, ' selected' if h == hour else '', h) for h in range(6, 22))
    return ('<form method="post" action="/content">%s<section class="cr-box"><h2>Your time zone</h2><p class="cr-muted">'
            'Filled in from your store\'s country. The calendar and publish times use it.</p><select name="tz" class="cs-select">%s'
            '</select></section><section class="cr-box"><h2>How often</h2><p class="cr-muted">How many pages the agent '
            'plans each week, and on which days.%s</p><div class="cs-opts"><select name="pace" class="cs-select">%s</select>'
            '<select name="hour" class="cs-select">%s</select></div><div class="cs-opts" style="margin-top:10px">%s</div></section>'
            '<section class="cr-box"><h2>Approval</h2><p class="cr-muted">Every draft waits for your approval. Nothing '
            'reaches your store until you say yes.</p></section><div class="cs-row"><a class="ca-btn" href="%s">Back</a>'
            '<button class="ca-btn ca-primary">Save and continue</button></div></form>') % (
        _hidden(domain, 'schedule'), zones, E(plan_note), paces, hours, day_boxes,
        E('/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='scope'))))


def _web_hint(n, web):
    """An off-site answer is offered, never filled in: the merchant clicks to use it."""
    return ('<span class="cs-hint cs-web">%s says <strong>%s</strong>. <a href="%s" target="_blank" rel="noopener">See the '
            'page</a> \u00b7 <button type="button" class="ca-link-btn" onclick="document.getElementById(\'m%d\').value=%s">'
            'Use this</button><br>It\'s not on your store, so check it\'s right for this product before using it.</span>') % (
        E(web['site']), E(web['value']), E(web['url']), n, E(json.dumps(web['value'])))


def _facts_page(domain, s):
    import catalog_facts
    missing = s.get('missing')
    if missing is None:
        return ('<section class="cr-box"><h2>Facts your pages leave out</h2><p class="cr-muted">AI recommends products whose '
                'pages state what buyers ask. The agent checks each product for the facts buyers look for.</p>'
                '<form method="post" action="/content" id="cs-missing" %s>%s<button class="ca-btn ca-primary">Check my products'
                '</button></form></section><script>document.getElementById("cs-missing").requestSubmit();</script>') % (
            _busy('Checking your products', 60), _hidden(domain, 'missing'))
    recs = {r['handle']: r for r in catalog_facts.get(domain)}
    answered = s.get('product_facts') or {}
    blocks = []
    n = 0
    for handle, items in missing.items():
        r = recs.get(handle)
        if not r or not items:
            continue
        have = {f['label']: f['value'] for f in answered.get(handle, [])}
        rows = ''
        for it in items:
            val = have.get(it['label'], it.get('suggestion', ''))
            rows += ('<div class="cs-q"><label class="cs-label" for="m%d">%s</label><input id="m%d" class="cs-in" '
                     'name="m.%s.%s" value="%s" placeholder="Leave empty if you don\'t know">%s</div>') % (
                n, E(it['question']), n, E(handle), E(it['label']), E(val),
                '<span class="cs-hint">Suggested from your store\'s other pages. Check it.</span>' if it.get('suggestion') and it['label'] not in have else
                _web_hint(n, it['web']) if it.get('web') and not val else '')
            n += 1
        img = ('<img src="%s" alt="">' % E(r['image'])) if r.get('image') else ''
        blocks.append('<section class="cr-box"><h2 class="cs-ph">%s%s</h2><div class="cs-brief">%s</div></section>' % (img, E(r['title']), rows))
    if not blocks:
        blocks = ['<section class="cr-box"><p class="cr-muted">Nothing obvious is missing.</p></section>']
    return ('<form method="post" action="/content">%s<p class="cr-muted">The facts below aren\'t on your product pages, and '
            'buyers ask about them. Answer what you know: every answer becomes a fact the agent can put on your pages. '
            'Skip anything you\'re unsure of.</p>%s<div class="cs-row"><a class="ca-btn" href="%s">Back</a>'
            '<button class="ca-btn ca-primary">Save and plan my first two weeks</button></div></form>') % (
        _hidden(domain, 'facts'), ''.join(blocks),
        E('/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='schedule'))))


# ---- first two weeks, drafted in the background ---------------------------------

_running = set()


def plan_first_weeks(domain, resume=False):
    """Draft the top Opportunities into the first two weeks' slots, in a background thread.

    resume=True carries on a batch a server restart cut short (the thread dies with the process):
    only the drafts still missing, counts kept. batch_note() does that when the calendar is opened."""
    import threading
    if domain in _running:
        return
    _running.add(domain)
    import content_calendar
    import content_plan
    slots = content_calendar.free_slots(domain, weeks=FIRST_WEEKS)
    s = get(domain)
    if resume and s.get('first_batch'):
        b = s['first_batch']
        slots = slots[:max(0, b['total'] - b['done'])]
        b['resumed_at'] = time.time()
    else:
        a = content_plan.monthly_total(domain)
        if a is not None:
            slots = slots[:max(1, -(-a // 2))]      # two weeks = about half the month's pages
        s['first_batch'] = dict(total=len(slots), done=0, failed=0, started_at=time.time())
    put(domain, s)

    def run():
        import briefs
        import content_agent
        try:
            todo = list(slots)
            for r in briefs.candidates(domain):
                if not todo:
                    break
                if content_agent.existing_draft(domain, r['type'], r['key']):
                    continue
                did, err = content_agent.draft_for(domain, r['type'], r['key'], avoid=content_agent.covered(domain))
                st = get(domain)
                if did:
                    db.write('UPDATE content_drafts SET planned_at=? WHERE id=?', (todo.pop(0), did))
                    st['first_batch']['done'] += 1
                elif err == content_agent.COVERED:
                    st['first_batch']['covered'] = st['first_batch'].get('covered', 0) + 1   # same page, already drafted
                else:
                    st['first_batch']['failed'] += 1
                    if st['first_batch']['failed'] > 2 * len(slots):
                        break
                put(domain, st)
        finally:
            st = get(domain)
            st['first_batch']['finished_at'] = time.time()
            put(domain, st)
            _running.discard(domain)
    threading.Thread(target=run, daemon=True).start()


def batch_note(domain):
    """A progress banner on the calendar while the first two weeks are being drafted."""
    b = get(domain).get('first_batch')
    if not b or b.get('finished_at'):
        return ''
    if domain not in _running:
        plan_first_weeks(domain, resume=True)       # the server restarted mid-batch: carry on
    import p_loader
    total, done = max(1, b['total']), b['done']
    return ('<div class="cs-batch cs-batch-live">%s<div class="cs-batch-text"><strong>Drafting your first two weeks</strong>'
            '<span>%d of %d drafts written. Each takes about 30 seconds; they appear on the calendar as they finish.</span>'
            '<div class="cs-bar" role="progressbar" aria-valuemin="0" aria-valuemax="%d" aria-valuenow="%d">'
            '<i style="width:%d%%"></i></div></div></div><meta http-equiv="refresh" content="15">') % (
        p_loader.mini(done / total, 30 * (total - done)), done, b['total'], b['total'], done, round(100 * done / total))


# ---- Shopify connection (Settings) -----------------------------------------------

def shopify_section(domain, q=None):
    import shopify_connect
    q = q or {}
    note = ''
    if q.get('connected'):
        note = '<p class="cs-batch">Connected. Approved drafts can now go live on your store.</p>'
    elif q.get('error'):
        note = '<p class="cal-warn">%s</p>' % E(q['error'])
    conn = shopify_connect.connection(domain)
    if not shopify_connect.configured():
        return note + ('<section class="cr-box"><h2>Publish to Shopify</h2><p class="cr-muted">Publishing isn\'t set up on '
                       'this server yet. Until it is, download your approved drafts from the Calendar and import them '
                       'in Shopify.</p></section>')
    if conn and not shopify_connect.can_upload(domain):
        note += ('<section class="cr-box cr-gaps"><h2>Reconnect once to store your photos in Shopify</h2><p class="cr-muted">'
                 'Photos you upload for an article now go into your store\'s own Shopify Files when the article goes live. '
                 'Shopify needs you to approve that once. Until then they stay on Produkto\'s server.</p>'
                 '<form method="post" action="/content">%s<input type="hidden" name="shop" value="%s">'
                 '<button class="ca-btn ca-primary">Reconnect Shopify</button></form></section>') % (
            _hidden(domain, 'shopify_connect'), E(conn['shop']))
    if conn:
        import storetime
        return note + ('<section class="cr-box"><h2>Publish to Shopify</h2><p>Connected to <strong>%s</strong> since %s.</p>'
                       '<p class="cr-muted">Approved drafts go live on their calendar date, or when you click Publish now. '
                       'Every change can be undone, and nothing goes live without your approval.</p>'
                       '<form method="post" action="/content">%s<button class="ca-btn">Disconnect</button></form></section>') % (
            E(conn['shop']), E(storetime.label(conn['connected_at'], storetime.zone(domain), '%-d %b %Y')),
            _hidden(domain, 'shopify_disconnect'))
    return note + ('<section class="cr-box"><h2>Publish to Shopify</h2><p class="cr-muted">Connect your store once and '
                   'approved drafts go live by themselves on their calendar date: new titles and descriptions on your '
                   'product pages, FAQs, comparison pages and blog posts. Every change can be undone. Shopify will ask '
                   'you to approve access.</p><form method="post" action="/content" class="cs-adjust">%s'
                   '<label for="cs-shop">Your Shopify address</label><input id="cs-shop" name="shop" '
                   'placeholder="your-store.myshopify.com" required><button class="ca-btn ca-primary">Connect Shopify'
                   '</button></form></section>') % _hidden(domain, 'shopify_connect')

