"""Your articles: the questions every store answers before the agent writes its articles (19 Oct 2026).

Kelian: learn this for every single user, by asking specific questions, because stores will be in very
different niches (skincare, pets, coffee, supplements...) and each needs to know exactly how its articles
should look and read.

Two kinds of question, both pre-filled by the agent so the merchant only reviews (rule of 15 Oct: the
setup asks as much as it usefully can, and the AI fills in every answer it can support):

  * COMMON: the same for every store. Who reads the articles, length, which blocks, photo style, the byline,
    blog categories, how hard to sell, topics and products to leave out, products to feature, claims the
    store's industry doesn't allow, a standard disclaimer, and articles they love by any brand (those join the
    niche examples, niche_examples.py).
  * NICHE: 4-8 questions written for this store's category by one helper-model call (skincare: skin types,
    morning/evening routines; pets: species and sizes, vet advice; coffee: brew methods, roast levels;
    supplements: dosage wording, regulated claims). Answers marked as facts can be stated in articles.

One helper call (~0.5 cent) writes the niche questions and pre-fills every answer from the store's pages,
profile and the niche playbook. Nothing is invented: an answer the pages don't support stays empty.
Stored in content_settings['article_brief']; used by drafts.article (prompt, length, products to skip,
byline, disclaimer) and by the fact check (claims not allowed).
"""
import json
import time

import db

# (key, question, hint, kind). kind: 'text', 'lines' (one per line), a tuple of choices, or ('multi', choices).
BLOCKS = ('At a glance box', 'Step-by-step sections', 'Comparison table', 'Product cards', 'Wide lifestyle photos',
          'FAQ', 'Closing banner for a set or bestseller', 'Pros and cons', 'Expert tips')
COMMON = (
    ('readers', 'Who reads your articles?', 'Their situation and how much they already know.', 'text'),
    ('level', 'How much do they know already?', '', ('Beginners', 'Some experience', 'Enthusiasts and experts', 'A mix')),
    ('help_with', 'What should your articles help buyers with?', 'One per line: the decisions and problems they come to you with.', 'lines'),
    ('length', 'How long should an article be?', '', ('Short (600-800 words)', 'Standard (900-1,200 words)', 'In-depth (1,500+ words)')),
    ('blocks', 'Which building blocks do you want?', 'Tick every one you like. The agent uses them where they fit.', ('multi', BLOCKS)),
    ('photos', 'Photo style', '', ('Lifestyle photos', 'Product shots', 'A mix of both')),
    ('selling', 'How should articles point to your products?', '',
     ('Gently: name them where they help', 'Clearly: a product card per recommendation', 'Strongly: a clear call to buy')),
    ('feature', 'Products to feature most', 'One per line, e.g. bestsellers or sets.', 'lines'),
    ('never_products', 'Products never to put in articles', 'One per line.', 'lines'),
    ('avoid_topics', 'Topics never to write about', 'One per line.', 'lines'),
    ('author', 'Whose name goes on the articles?', 'e.g. the brand name, the founder, "The team".', 'text'),
    ('expert', 'Founder or expert background the articles may mention', 'Only what\'s true, e.g. "Formulated with a cosmetic chemist".', 'text'),
    ('categories', 'Your blog categories', 'One per line, e.g. Routines, Guides, Ingredients.', 'lines'),
    ('compliance', 'Claims your industry doesn\'t allow', 'One per line. Sentences making them are held back.', 'lines'),
    ('disclaimer', 'A standard line at the end of every article', 'Optional, e.g. a health disclaimer. Leave empty for none.', 'text'),
    ('loved', 'Articles you love, from any brand', 'One link per line. The agent studies how they are built (never copies them).', 'lines'),
)
FACT_COMMON = ('expert',)

GEN_RULES = """You help set up the article writer for one online store. You get the store's profile, its products, its pages and how the best brands in its niche build articles.

1. niche: the store's niche in 2-5 words (e.g. "Natural skincare", "Dog joint supplements", "Speciality coffee").
2. questions: 4-8 questions SPECIFIC to this niche that a writer needs answered to write this store's articles well, which the common questions don't cover. Think about what differs by niche: for skincare, skin types and concerns, morning/evening use, ingredient wording; for pets, which animals, sizes and ages, whether to advise seeing a vet; for coffee, brew methods, roast levels, grind; for supplements, how dosage may be described, which health claims are regulated, who should not take it. Each with id (snake_case), question, hint (short), kind ("text", "lines" or "choice"), options (for choice, else []), is_fact (true only if the answer states something true about the products that articles may say, e.g. "Which skin types do your products suit?"), and a pre-filled answer (answer for text/choice, answer_lines for lines).
3. common: pre-filled answers for the COMMON questions listed, by key.

Pre-fill rules: use only what the pages, profile and products support. Preferences (length, blocks, photos, selling) may follow the niche playbook. Facts (anything is_fact, and expert) only when the pages state them; otherwise empty. compliance: the claims a store in this niche must not make (e.g. supplements: "cures", "treats", "prevents disease"). disclaimer: only when the niche usually carries one (supplements, health), else "". loved: always []. never_products and avoid_topics: usually []. categories: 2-4 fitting this niche. feature: sets or bestsellers if obvious, else []."""


def _gen_schema():
    common = {}
    for key, _, _, kind in COMMON:
        if kind == 'lines':
            common[key] = {"type": "array", "items": {"type": "string"}}
        elif isinstance(kind, tuple) and kind[0] == 'multi':
            common[key] = {"type": "array", "items": {"type": "string", "enum": list(kind[1])}}
        elif isinstance(kind, tuple):
            common[key] = {"type": "string", "enum": list(kind)}
        else:
            common[key] = {"type": "string"}
    q = {"type": "object", "additionalProperties": False,
         "required": ["id", "question", "hint", "kind", "options", "is_fact", "answer", "answer_lines"],
         "properties": {"id": {"type": "string"}, "question": {"type": "string"}, "hint": {"type": "string"},
                        "kind": {"type": "string", "enum": ["text", "lines", "choice"]},
                        "options": {"type": "array", "items": {"type": "string"}}, "is_fact": {"type": "boolean"},
                        "answer": {"type": "string"}, "answer_lines": {"type": "array", "items": {"type": "string"}}}}
    return {"type": "object", "additionalProperties": False, "required": ["niche", "questions", "common"],
            "properties": {"niche": {"type": "string"}, "questions": {"type": "array", "items": q},
                           "common": {"type": "object", "additionalProperties": False, "required": list(common),
                                      "properties": common}}}


def _context(domain):
    import catalog_facts
    import content_setup
    b = db.brand(domain) or {}
    profile = 'Name: %s\nDescription: %s\nIndustry: %s\nProducts: %s\nMarkets: %s\nCountry: %s' % (
        b.get('brand_name', ''), b.get('description', ''), b.get('industry', ''), ', '.join(b.get('services', [])),
        ', '.join(b.get('markets', [])), b.get('country', ''))
    recs = catalog_facts.get(domain)[:20]
    products = '\n'.join('- %s (%s): %s' % (r['title'], r.get('product_type') or '', ' '.join(r.get('description') or [])[:300])
                         for r in recs)
    try:
        pages = '\n\n'.join('[%s]\n%s' % (p, t[:1500]) for p, t in content_setup.store_pages(domain))
    except Exception:                                                     # noqa: BLE001 - offline
        pages = ''
    brief = content_setup.get(domain).get('brief') or {}
    try:
        import niche_examples
        pb = niche_examples.prompt(niche_examples.get(domain))
    except Exception:                                                     # noqa: BLE001
        pb = ''
    common = '\n'.join('- %s: %s' % (k, q) for k, q, _, _ in COMMON)
    return ('PROFILE:\n%s\n\nPRODUCTS:\n%s\n\nSTORE PAGES:\n%s\n\nBRAND BRIEF ALREADY GIVEN: %s\n%s\n\nCOMMON QUESTIONS:\n%s'
            % (profile, products or '(none read)', pages or '(none found)',
               json.dumps({k: brief.get(k) for k in ('customers', 'story', 'no_claims')}, ensure_ascii=False), pb, common))


def prefill(domain, usage=None):
    """The niche questions and every answer pre-filled. Raises llm.LLMError when the writing service is down."""
    import llm
    res = llm.json_call(GEN_RULES, _context(domain), 'article_setup', _gen_schema(), usage=usage, attempts=3)
    qs = []
    seen = {k for k, _, _, _ in COMMON}
    for q in res.get('questions') or []:
        qid = ''.join(c for c in (q.get('id') or '').lower().replace(' ', '_') if c.isalnum() or c == '_')[:40]
        if not qid or qid in seen or not q.get('question'):
            continue
        seen.add(qid)
        kind = q['kind'] if q['kind'] in ('text', 'lines', 'choice') else 'text'
        if kind == 'choice' and len(q.get('options') or []) < 2:
            kind = 'text'
        qs.append(dict(id=qid, question=q['question'][:160], hint=(q.get('hint') or '')[:200], kind=kind,
                       options=[o[:80] for o in q.get('options') or []][:6], is_fact=bool(q.get('is_fact'))))
    answers = dict(res.get('common') or {})
    answers['loved'] = []
    for q, raw in zip(qs, [x for x in res.get('questions') or [] if x.get('question')]):
        answers['n.' + q['id']] = raw.get('answer_lines') if q['kind'] == 'lines' else raw.get('answer', '')
    if not answers.get('author'):
        answers['author'] = (db.brand(domain) or {}).get('brand_name') or ''
    return dict(niche=(res.get('niche') or '')[:60], questions=qs, answers=answers, prefilled_at=time.time())


# ---- stored brief ----------------------------------------------------------------------------------

def get(domain):
    import content_setup
    return content_setup.get(domain).get('article_brief') or {}


def done(domain):
    return bool(get(domain).get('done_at'))


def ensure(domain, usage=None):
    """The brief, pre-filling it once if the store never opened the step (the monthly writer runs unattended).
    An unreviewed brief is used as it is and stays marked as not reviewed."""
    ab = get(domain)
    if ab.get('answers') is not None:
        return ab
    import content_setup
    try:
        ab = prefill(domain, usage=usage)
    except Exception:                                                     # noqa: BLE001 - no credit: write without it
        return {}
    s = content_setup.get(domain)
    s['article_brief'] = ab
    content_setup.put(domain, s)
    return ab


def answer(ab, key):
    return (ab.get('answers') or {}).get(key)


def save_form(domain, form):
    """Store the merchant's answers from the setup form."""
    import content_setup
    s = content_setup.get(domain)
    ab = s.get('article_brief') or {}
    answers = {}
    for key, _, _, kind in COMMON:
        raw = form.get('a.' + key, '')
        if kind == 'lines':
            answers[key] = [x.strip(' -•\t') for x in raw.splitlines() if x.strip(' -•\t')]
        elif isinstance(kind, tuple) and kind[0] == 'multi':
            answers[key] = [b for i, b in enumerate(kind[1]) if form.get('a.%s.%d' % (key, i))]
        elif isinstance(kind, tuple):
            answers[key] = raw if raw in kind else ''
        else:
            answers[key] = raw.strip()
    for q in ab.get('questions') or []:
        raw = form.get('a.n.' + q['id'], '')
        if q['kind'] == 'lines':
            answers['n.' + q['id']] = [x.strip(' -•\t') for x in raw.splitlines() if x.strip(' -•\t')]
        elif q['kind'] == 'choice':
            answers['n.' + q['id']] = raw if raw in q['options'] else ''
        else:
            answers['n.' + q['id']] = raw.strip()
    ab['answers'] = answers
    ab['done_at'] = time.time()
    s['article_brief'] = ab
    content_setup.put(domain, s)
    return ab


# ---- used by the writer ----------------------------------------------------------------------------

LENGTH = {'Short (600-800 words)': 700, 'Standard (900-1,200 words)': 1050, 'In-depth (1,500+ words)': 1600}


def length(domain):
    return LENGTH.get(answer(get(domain), 'length') or '')


def facts(domain):
    """Answers the merchant marked as true about the products, as facts drafts and the fact check accept."""
    ab = get(domain)
    out = []
    v = answer(ab, 'expert')
    if v:
        out.append(dict(label='About the brand', value=v, source='merchant'))
    for q in ab.get('questions') or []:
        if not q.get('is_fact'):
            continue
        v = answer(ab, 'n.' + q['id'])
        for item in (v if isinstance(v, list) else [v] if v else []):
            out.append(dict(label=q['question'], value=item, source='merchant'))
    return out


def no_claims(domain):
    return list(answer(get(domain), 'compliance') or [])


def never_products(domain):
    return [p.strip().lower() for p in answer(get(domain), 'never_products') or [] if p.strip()]


def loved(domain):
    return [u for u in answer(get(domain), 'loved') or [] if u.startswith('http')]


def prompt(domain):
    """The owner's answers as a writer's prompt section ('' when there are none)."""
    ab = get(domain)
    a = ab.get('answers') or {}
    if not a:
        return ''
    lines = []
    for key, q, _, _ in COMMON:
        if key in ('loved', 'never_products', 'compliance'):
            continue
        v = a.get(key)
        if v:
            lines.append('- %s %s' % (q, '; '.join(v) if isinstance(v, list) else v))
    for q in ab.get('questions') or []:
        v = a.get('n.' + q['id'])
        if v:
            lines.append('- %s %s' % (q['question'], '; '.join(v) if isinstance(v, list) else v))
    if not lines:
        return ''
    head = ('THE OWNER\'S ARTICLE BRIEF%s (follow it; it wins over the niche examples; only the fact rules win over it. '
            'Pick the category from their categories; use only the blocks they ticked; name products they feature where '
            'they genuinely fit)' % (' FOR %s' % ab['niche'].upper() if ab.get('niche') else ''))
    return '\n\n' + head + ':\n' + '\n'.join(lines)


# ---- the setup step --------------------------------------------------------------------------------

def page(domain, hidden, busy, E, back_url):
    ab = get(domain)
    if ab.get('answers') is None:
        return ('<section class="cr-box"><h2>Your articles</h2><p class="cr-muted">A few questions about how your articles '
                'should read and look, some of them specific to your niche. The agent fills in a first draft from your pages; '
                'you correct it.</p><form method="post" action="/content" id="cs-art" %s>%s<button class="ca-btn ca-primary">'
                'Fill in from my pages</button></form></section>'
                '<script>document.getElementById("cs-art").requestSubmit();</script>') % (
            busy('Writing questions for your niche', 40), hidden('articles_prefill'))
    a = ab['answers']

    def field(name, label, hint, kind, val, fact=False):
        hint_html = '<span class="cs-hint">%s</span>' % E(hint) if hint else ''
        tag = ' <span class="cs-fact">Articles may state this as a fact</span>' if fact else ''
        if isinstance(kind, tuple) and kind and kind[0] == 'multi':
            opts = ''.join('<label class="cs-opt"><input type="checkbox" name="%s.%d" value="1"%s> %s</label>'
                           % (name, i, ' checked' if o in (val or []) else '', E(o)) for i, o in enumerate(kind[1]))
            return '<div class="cs-q"><span class="cs-label">%s</span>%s<div class="cs-opts">%s</div></div>' % (E(label), hint_html, opts)
        if isinstance(kind, (tuple, list)):
            opts = ''.join('<label class="cs-opt"><input type="radio" name="%s" value="%s"%s> %s</label>'
                           % (name, E(o), ' checked' if o == val else '', E(o)) for o in kind)
            return '<div class="cs-q"><span class="cs-label">%s%s</span>%s<div class="cs-opts">%s</div></div>' % (E(label), tag, hint_html, opts)
        text = '\n'.join(val) if isinstance(val, list) else (val or '')
        rows = max(2, min(8, text.count('\n') + 2)) if kind == 'lines' else max(2, min(5, len(text) // 70 + 1))
        return ('<div class="cs-q"><label class="cs-label" for="%s">%s%s</label>%s<textarea id="%s" name="%s" rows="%d">%s</textarea></div>'
                % (E(name), E(label), tag, hint_html, E(name), E(name), rows, E(text)))
    niche = ''.join(field('a.n.' + q['id'], q['question'], q.get('hint', ''),
                          q['options'] if q['kind'] == 'choice' else q['kind'], a.get('n.' + q['id']), q.get('is_fact'))
                    for q in ab.get('questions') or [])
    common = ''.join(field('a.' + k, q, h, kind, a.get(k), k in FACT_COMMON) for k, q, h, kind in COMMON)
    status = 'Reviewed' if ab.get('done_at') else 'Filled in from your pages, not reviewed yet'
    return ('<form method="post" action="/content">%s<section class="cr-box"><h2>Questions for %s</h2><p class="cr-muted">%s. '
            'These are written for your niche. Correct anything that\'s wrong; answers marked as facts can appear in your '
            'articles, so only write what\'s true.</p><div class="cs-brief">%s</div></section>'
            '<section class="cr-box"><h2>How your articles work</h2><div class="cs-brief">%s</div></section>'
            '<div class="cs-row"><a class="ca-btn" href="%s">Back</a><button class="ca-btn ca-primary">Save and continue</button>'
            '</div></form><form method="post" action="/content" class="cs-again">%s<button class="ca-btn ca-small">'
            'Write the questions again</button></form>') % (
        hidden('articles'), E(ab.get('niche') or 'your niche'), E(status), niche or '<p class="cr-muted">None.</p>',
        common, E(back_url), hidden('articles_prefill'))
