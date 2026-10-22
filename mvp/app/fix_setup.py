"""Your product pages: the questions every store answers before the agent rewrites its product pages (20 Oct 2026).

The product page version of article_setup.py (Kelian: give product page fixes the same context the articles got).
Common questions for every store (how a description opens, length, layout, spec tables, title style, what every
page should mention, words never to use, what every FAQ covers, claims the industry doesn't allow) plus 4-8 written
for the store's niche (skincare: skin types, how to use, ingredient wording; pets: sizes and breeds, materials and
washing; coffee: roast, tasting notes, brew methods). One helper call (~0.3 cent) writes the niche questions and
pre-fills every answer from the store's pages and products; the owner reviews. Nothing is invented: an answer the
pages don't support stays empty.

Stored in content_settings['fix_brief']. Used by drafts.product_fix / drafts.faq (prompt, keep-titles, no spec
table), content_setup.brand_facts (answers marked as facts, "every page should mention"), and content_setup.rules
(words never to use, claims not allowed).
"""
import json
import time

import db

COMMON = (
    ('opening', 'What should the first sentence of a description say?', '',
     ('What it is and who it\'s for', 'The main benefit', 'What makes it different')),
    ('length', 'How long should a description be?', '', ('Short (40-80 words)', 'Standard (80-150 words)', 'Detailed (150-250 words)')),
    ('layout', 'How should it be laid out?', '', ('Short paragraphs', 'A short paragraph, then bullet points', 'Mostly bullet points')),
    ('specs', 'A spec table under the description?', 'Rows are copied exactly from your product facts.',
     ('Yes, when there are facts for it', 'No spec table')),
    ('titles', 'Product titles', 'Titles are what Google Shopping and AI assistants match first.',
     ('Improve them: brand, name, type and key fact', 'Keep my titles exactly as they are')),
    ('mention', 'What should every product page mention?', 'One per line, only what\'s true for every product, e.g. "Vegan and cruelty-free".', 'lines'),
    ('never_words', 'Words never to use', 'One per line.', 'lines'),
    ('faq_topics', 'What should every FAQ cover?', 'One per line, e.g. how to use it, who it suits, shipping.', 'lines'),
    ('compliance', 'Claims your industry doesn\'t allow', 'One per line. Sentences making them are held back.', 'lines'),
)
FACT_COMMON = ('mention',)

GEN_RULES = """You help set up the product page writer for one online store. You get the store's profile, its products and its pages.

1. niche: the store's niche in 2-5 words (e.g. "Natural skincare", "Dog accessories", "Speciality coffee").
2. questions: 4-8 questions SPECIFIC to this niche that a writer needs answered to write this store's product pages well, which the common questions don't cover. Think about what buyers in this niche check on a product page before buying: for skincare, skin types, how and when to use it, how ingredients are named; for pets, sizes and breeds, materials and washing, fit; for coffee, roast level, tasting notes, brew methods, origin; for supplements, how dosage may be described, who should not take it; for apparel, fit and sizing advice, fabric and care. Each with id (snake_case), question, hint (short), kind ("text", "lines" or "choice"), options (for choice, else []), is_fact (true only if the answer states something true about the products that pages may say, e.g. "Which skin types do your products suit?"), and a pre-filled answer (answer for text/choice, answer_lines for lines).
3. common: pre-filled answers for the COMMON questions listed, by key.

Pre-fill rules: use only what the pages, profile and products support. Preferences (opening, length, layout, specs) follow how the store's current product pages read. titles: "Improve them: brand, name, type and key fact". Facts (anything is_fact, and mention) only when the pages state them for every product; otherwise empty. compliance: the claims a store in this niche must not make (e.g. supplements: "cures", "treats", "prevents disease"; skincare: medical claims). never_words: usually []. faq_topics: 3-5 that fit this niche."""


def _gen_schema():
    common = {}
    for key, _, _, kind in COMMON:
        if kind == 'lines':
            common[key] = {"type": "array", "items": {"type": "string"}}
        elif isinstance(kind, tuple):
            common[key] = {"type": "string", "enum": list(kind)}
        else:
            common[key] = {"type": "string"}
    import article_setup
    q = article_setup._gen_schema()['properties']['questions']
    return {"type": "object", "additionalProperties": False, "required": ["niche", "questions", "common"],
            "properties": {"niche": {"type": "string"}, "questions": q,
                           "common": {"type": "object", "additionalProperties": False, "required": list(common),
                                      "properties": common}}}


def _context(domain):
    import catalog_facts
    import content_setup
    b = db.brand(domain) or {}
    profile = 'Name: %s\nDescription: %s\nIndustry: %s\nProducts: %s\nCountry: %s' % (
        b.get('brand_name', ''), b.get('description', ''), b.get('industry', ''), ', '.join(b.get('services', [])), b.get('country', ''))
    recs = catalog_facts.get(domain)[:20]
    products = '\n'.join('- %s (%s): %s' % (r['title'], r.get('product_type') or '', ' '.join(r.get('description') or [])[:400])
                         for r in recs)
    try:
        pages = '\n\n'.join('[%s]\n%s' % (p, t[:1500]) for p, t in content_setup.store_pages(domain))
    except Exception:                                                     # noqa: BLE001 - offline
        pages = ''
    common = '\n'.join('- %s: %s' % (k, q) for k, q, _, _ in COMMON)
    return 'PROFILE:\n%s\n\nPRODUCTS:\n%s\n\nSTORE PAGES:\n%s\n\nCOMMON QUESTIONS:\n%s' % (
        profile, products or '(none read)', pages or '(none found)', common)


def prefill(domain, usage=None):
    """The niche questions and every answer pre-filled. Raises llm.LLMError when the writing service is down."""
    import llm
    res = llm.json_call(GEN_RULES, _context(domain), 'fix_setup', _gen_schema(), usage=usage, attempts=3)
    qs, raws, seen = [], [], {k for k, _, _, _ in COMMON}
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
        raws.append(q)
    answers = dict(res.get('common') or {})
    for q, raw in zip(qs, raws):
        answers['n.' + q['id']] = raw.get('answer_lines') if q['kind'] == 'lines' else raw.get('answer', '')
    return dict(niche=(res.get('niche') or '')[:60], questions=qs, answers=answers, prefilled_at=time.time())


# ---- stored brief ----------------------------------------------------------------------------------

def get(domain):
    import content_setup
    try:
        return content_setup.get(domain).get('fix_brief') or {}
    except Exception:                                                     # noqa: BLE001 - fresh database
        return {}


def ensure(domain, usage=None):
    """The brief, pre-filled once if the store never opened the step (drafts run unattended)."""
    fb = get(domain)
    if fb.get('answers') is not None:
        return fb
    import content_setup
    try:
        fb = prefill(domain, usage=usage)
    except Exception:                                                     # noqa: BLE001 - no credit: write without it
        return {}
    s = content_setup.get(domain)
    s['fix_brief'] = fb
    content_setup.put(domain, s)
    return fb


def answer(domain, key):
    return (get(domain).get('answers') or {}).get(key)


def save_form(domain, form):
    import content_setup
    s = content_setup.get(domain)
    fb = s.get('fix_brief') or {}
    answers = {}
    for key, _, _, kind in COMMON:
        raw = form.get('a.' + key, '')
        if kind == 'lines':
            answers[key] = [x.strip(' -•\t') for x in raw.splitlines() if x.strip(' -•\t')]
        elif isinstance(kind, tuple):
            answers[key] = raw if raw in kind else ''
        else:
            answers[key] = raw.strip()
    for q in fb.get('questions') or []:
        raw = form.get('a.n.' + q['id'], '')
        if q['kind'] == 'lines':
            answers['n.' + q['id']] = [x.strip(' -•\t') for x in raw.splitlines() if x.strip(' -•\t')]
        elif q['kind'] == 'choice':
            answers['n.' + q['id']] = raw if raw in q['options'] else ''
        else:
            answers['n.' + q['id']] = raw.strip()
    fb['answers'] = answers
    fb['done_at'] = time.time()
    s['fix_brief'] = fb
    content_setup.put(domain, s)
    return fb


def status(s):
    fb = s.get('fix_brief') or {}
    if fb.get('done_at'):
        return True, '%d niche question%s answered' % (len(fb.get('questions') or []), '' if len(fb.get('questions') or []) == 1 else 's')
    return False, 'Filled in, not reviewed' if fb.get('answers') is not None else 'To do'


# ---- used by the writer and the fact check -----------------------------------------------------------

def keep_titles(domain):
    return answer(domain, 'titles') == 'Keep my titles exactly as they are'


def no_specs(domain):
    return answer(domain, 'specs') == 'No spec table'


def facts(domain):
    fb = get(domain)
    out = [dict(label='Every product', value=v, source='merchant') for v in (fb.get('answers') or {}).get('mention') or []]
    for q in fb.get('questions') or []:
        if not q.get('is_fact'):
            continue
        v = (fb.get('answers') or {}).get('n.' + q['id'])
        for item in (v if isinstance(v, list) else [v] if v else []):
            out.append(dict(label=q['question'], value=item, source='merchant'))
    return out


def no_claims(domain):
    return list(answer(domain, 'compliance') or [])


def never_words(domain):
    return list(answer(domain, 'never_words') or [])


def prompt(domain):
    fb = get(domain)
    a = fb.get('answers') or {}
    lines = []
    for key, q, _, _ in COMMON:
        if key in ('compliance', 'never_words', 'mention'):
            continue
        v = a.get(key)
        if v:
            lines.append('- %s %s' % (q, '; '.join(v) if isinstance(v, list) else v))
    for q in fb.get('questions') or []:
        v = a.get('n.' + q['id'])
        if v:
            lines.append('- %s %s' % (q['question'], '; '.join(v) if isinstance(v, list) else v))
    if a.get('never_words'):
        lines.append('- Never use these words: %s' % ', '.join(a['never_words']))
    if not lines:
        return ''
    return ('\n\nTHE OWNER\'S PRODUCT PAGE BRIEF%s (follow it; only the fact rules win over it):\n'
            % (' FOR %s' % fb['niche'].upper() if fb.get('niche') else '')) + '\n'.join(lines)


# ---- the setup step --------------------------------------------------------------------------------

def page(domain, hidden, busy, E, back_url):
    fb = get(domain)
    if fb.get('answers') is None:
        return ('<section class="cr-box"><h2>Your product pages</h2><p class="cr-muted">A few questions about how your product '
                'pages should read, some of them specific to your niche. The agent fills in a first draft from your pages; '
                'you correct it.</p><form method="post" action="/content" id="cs-fix" %s>%s<button class="ca-btn ca-primary">'
                'Fill in from my pages</button></form></section>'
                '<script>document.getElementById("cs-fix").requestSubmit();</script>') % (
            busy('Writing questions for your niche', 30), hidden('fixpages_prefill'))
    a = fb['answers']

    def field(name, label, hint, kind, val, fact=False):
        hint_html = '<span class="cs-hint">%s</span>' % E(hint) if hint else ''
        tag = ' <span class="cs-fact">Pages may state this as a fact</span>' if fact else ''
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
                    for q in fb.get('questions') or [])
    common = ''.join(field('a.' + k, q, h, kind, a.get(k), k in FACT_COMMON) for k, q, h, kind in COMMON)
    st = 'Reviewed' if fb.get('done_at') else 'Filled in from your pages, not reviewed yet'
    return ('<form method="post" action="/content">%s<section class="cr-box"><h2>Product page questions for %s</h2><p class="cr-muted">%s. '
            'These are written for your niche. Correct anything that\'s wrong; answers marked as facts can appear on your '
            'product pages, so only write what\'s true.</p><div class="cs-brief">%s</div></section>'
            '<section class="cr-box"><h2>How your product pages read</h2><div class="cs-brief">%s</div></section>'
            '<div class="cs-row"><a class="ca-btn" href="%s">Back</a><button class="ca-btn ca-primary">Save and continue</button>'
            '</div></form><form method="post" action="/content" class="cs-again">%s<button class="ca-btn ca-small">'
            'Write the questions again</button></form>') % (
        hidden('fixpages'), E(fb.get('niche') or 'your niche'), E(st), niche or '<p class="cr-muted">None.</p>',
        common, E(back_url), hidden('fixpages_prefill'))
