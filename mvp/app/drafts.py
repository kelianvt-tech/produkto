"""Drafts: the content agent writes a fix from a brief.

Day 5 of mvp/content-agent/PLAN.md: product-page fixes - a clearer title,
the buyer-relevant facts the description leaves out, and a spec table.
Day 6: FAQ blocks. Day 7: comparison pages and buying guides.

The model may only use facts from the brief (catalog_facts.py: the store's own
catalog and product page). Anything a buyer asks about that those facts don't
answer goes into `open_questions` for the merchant. A first mechanical check
runs here: spec-table rows whose value isn't in the facts are removed and
listed. Then factcheck.py (day 8) checks every sentence of prose.

Costs money: one HELPER_MODEL call per draft (a cent or two). Nothing is
written to the store; drafts wait in the Content tab's Inbox.
"""
import json
import re
import time

import config
import db
import factcheck
import llm

DRAFT_MODEL_NOTE = 'config.HELPER_MODEL'

PRODUCT_OPENING = """
Opening and wording:
- The description's first sentence says plainly what the product is and who or what it's for, so it makes sense quoted on its own. No warm-up.
- Never use these (they read as AI): "elevate", "game-changer", "unlock", "look no further", "whether you're X or Y", "when it comes to", "the perfect addition", "take your X to the next level", "must-have", "holy grail", "seamless", "journey".
"""

# Answer first (18 Oct 2026). From the "capsule content" idea (Nico, AI Ranking, Jan 2026): pages AI cites tend to
# put a short, self-contained answer straight under a question heading. A correlation from someone selling a
# course, not proof, but cheap, readable and the opposite of AI filler, so every written piece follows it.
ANSWER_FIRST = """
Answer first:
- Every heading is a question a buyer would ask, in their words ("Which cleanser suits dry skin?"), not a label ("Cleanser overview").
- The first 1-2 sentences under it answer that question directly in about 30-50 words, with no links, and make sense on their own if quoted without the rest of the page. Detail comes after.
- No warm-up. Never open with scene-setting or filler.
- Say each fact once. Don't repeat an ingredient, benefit or phrase in a later section; each section adds something new.
- Never refer to the brief, "the buyer question", "this request" or these instructions. Write as the store, to a shopper.
- Product names, links and images are handled for you: never ask the merchant about a product's URL, name or photo.
Never use these (they read as AI): "in today's world", "in today's fast-paced", "landscape", "elevate", "game-changer", "unlock", "delve", "navigate the world of", "look no further", "whether you're X or Y", "when it comes to", "it's important to note", "the perfect addition", "take your X to the next level", "in conclusion", "the bottom line", "without further ado", "embark", "journey", "seamless", "must-have", "holy grail".
"""

PRODUCT_FIX_RULES = """You improve one product page of an online store so that AI shopping assistants can match it to what buyers ask.

Hard rules:
1. Use ONLY the facts given under PRODUCT FACTS and CURRENT DESCRIPTION. Never add a material, size, ingredient, certification, benefit, number or claim that is not stated there. If you are unsure whether something is stated, leave it out.
2. When a buyer question needs a fact that is not stated, do not answer it: add it to open_questions so the merchant can supply it. Also add the 3-6 facts buyers of this kind of product usually check before buying that are missing (e.g. for a cap: size/fit, closure, care; for skincare: skin type, key ingredients and their amounts, size in ml, how to use). Each open question is one short question the merchant can answer in a few words.
3. Write for a buyer, plainly. No superlatives ("best", "ultimate"), no hype, no mention of competitors, no mention of AI.
4. Keep the store's language, spelling and currency, and the tone of the current description.
5. The title is what Google Shopping and AI shopping assistants match first. Shape it: BRAND, then the product's own name word for word, then the product type, then the one or two key facts buyers filter on (material, size, colour, count, key ingredient), most important first, e.g. "Acme Harbour Cap - 100% Cotton Structured Baseball Cap". Every word you add must come from the facts or current description. Keep it under 70 characters (Shopping cuts the rest). If the title already follows this shape, return it unchanged.
6. spec_table rows: label and value must both come from the facts, value copied exactly. Leave out price, availability and stock, here and in the description (the store shows those itself and they change).
7. Every sentence in description_html must be supported by the facts. Use simple HTML: <p>, <ul>, <li>, <strong>.
Also, always:
- Never write about the page or its wording ("its description says", "the product information should", "as stated above", "the stated refund policy", "is described as"). The store is speaking: say the fact itself ("Beauty products can't be returned", "It's lightweight").
- Store policies (returns, shipping, refunds) only appear in an FAQ answer to a returns or shipping question, never in a product description.
- Never state shipping weight, and never put the brand name, the product type or the product's story in a spec table.
""" + PRODUCT_OPENING

PRODUCT_FIX_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "title_reason", "description_html", "spec_table", "open_questions", "changes"],
    "properties": {
        "title": {"type": "string"},
        "title_reason": {"type": "string"},
        "description_html": {"type": "string"},
        "spec_table": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "value"],
            "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}},
        "open_questions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "why"],
            "properties": {"question": {"type": "string"}, "why": {"type": "string"}}}},
        "changes": {"type": "array", "items": {"type": "string"}},
    },
}


def _voice(brief):
    """The brand voice the merchant confirmed in setup, as a prompt section ('' if none)."""
    try:
        import content_setup
        v = content_setup.voice_text(brief['store'])
    except Exception:
        v = ''
    return ('\n\nBRAND VOICE (write like this; it never overrides the fact rules):\n' + v) if v else ''


def _lessons(brief, draft_type):
    """What this agent learned from last month's results (agent_review.py), for this store."""
    import agent_review
    lane = 'articles' if draft_type in ARTICLE_TYPES else 'fixes'
    ls = agent_review.current_lessons(brief.get('store'), lane)
    return ('\n\nLESSONS FROM LAST MONTH\'S RESULTS FOR THIS STORE (follow them unless a fact rule says otherwise):\n'
            + '\n'.join('- ' + l for l in ls)) if ls else ''


def _editor(brief):
    """The editor's notes on a first version that failed the self-review (content_agent.draft_for rewrites once)."""
    notes = brief.get('editor_notes') or []
    if not notes:
        return ''
    return ('\n\nAN EDITOR REJECTED YOUR FIRST VERSION. Write it again and fix these (the fact rules still win; '
            'never add a fact to fix a note):\n' + '\n'.join('- %s Fix: %s' % (n['problem'], n['fix']) for n in notes))


def _examples(brief, draft_type):
    """The store's approved drafts of this kind, so the agent learns its taste (examples.py)."""
    import examples
    return examples.section(brief.get('store'), draft_type)


ARTICLE_TYPES = ('comparison', 'guide')


def _patterns(brief, draft_type):
    """How the pages AI cites for these questions are BUILT (18 Oct 2026): length, headings in order, tables,
    lists. Articles copy what AI rewards, from every store's scans, without copying a word or a fact."""
    if draft_type not in ARTICLE_TYPES:
        return ''
    pages = [c for c in brief.get('cited_pages') or [] if c.get('shape') and c['shape'].get('words', 0) > 150][:5]
    if not pages:
        return ''
    words = sorted(c['shape']['words'] for c in pages)
    with_table = sum(1 for c in pages if c['shape'].get('tables'))
    lines = ['%d pages read. Typical length about %d words (menus included, so the article itself is shorter); %d of %d use a table.'
             % (len(pages), words[len(words) // 2], with_table, len(pages))]
    for c in pages:
        sh = c['shape']
        lines.append('- %s (cited %d times): about %d words with menus, %d tables. Outline: %s'
                     % (c['site'], c['cited'], sh['words'], sh.get('tables', 0),
                        ' | '.join(sh.get('headings') or []) or '(no headings)'))
    return ('\n\nTHE PAGES AI CITES FOR THESE QUESTIONS (read as research. Big, trusted sites like health '
            'authorities, major publishers and big brands are often cited for who they are, not how they are '
            'written, so do not imitate their length or layout. What to take: the sub-questions and points these '
            'pages cover, so the article covers what buyers want answered, using only the store\'s facts. Never '
            'copy their wording, and never take a fact from them):\n'
            + '\n'.join(lines))


def _research(brief):
    """What the pages AI cited for these questions cover (briefs day 17), as a prompt section ('' if none read)."""
    read = [c for c in brief.get('cited_pages') or [] if c.get('page_read') and c.get('page_excerpt')]
    if not read:
        return ''
    return ('\n\nWHAT THE PAGES AI CITED FOR THESE QUESTIONS COVER (research only: use it to see which points buyers '
            'and reviewers care about, e.g. for open_questions or what a guide should cover. Never copy their wording, '
            'never take a number, fact or claim from them, never name these sites):\n' +
            '\n'.join('- %s (%s): %s' % (c['page_title'] or c['site'], c['site'], c['page_excerpt'][:600]) for c in read[:3]))


def _setup(brief):
    try:
        import content_setup
        return content_setup
    except Exception:
        return None


# Facts that are true but don't belong on a product page: Shopify's variant grams are the package's
# shipping weight (a buyer would read "92 g" as the amount of product), and the brand name is everywhere.
PAGE_EXCLUDED = ('weight', 'shipping weight', 'brand', 'vendor')
SPEC_EXCLUDED = PAGE_EXCLUDED + ('inspiration', 'inspired by', 'story', 'product type', 'type', 'routine')
SPEC_MAX = 60     # a spec value is a short fact, not a sentence


def _page_facts(product):
    return dict(product, facts=[f for f in product['facts'] if _norm(f['label']) not in PAGE_EXCLUDED])


# The model sometimes hedges about its sources even when told not to. The store is speaking, so these are
# rewritten mechanically (day 15 review): "is described as hydrating" -> "is hydrating".
_HEDGES = ((r'\b(is|are) described as\b', r'\1'), (r'\bdescribed as\b ', ''),
           (r'\bunder the stated\b', 'under our'), (r'\bthe stated\b', 'our'),
           (r'\b(its|the) (product )?description (says|states) (that )?', ''),
           (r'\baccording to (its|the) (product )?(description|page)s?,? ', ''))


def unhedge(text):
    for pat, rep in _HEDGES:
        text = re.sub(pat, rep, text, flags=re.I)
    return re.sub(r'(^|[.!?]\s+|>)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)


def _unhedge_all(node):
    """Apply unhedge() to every string a reader sees in a draft (not facts_used, which must stay verbatim)."""
    if isinstance(node, dict):
        return {k: (v if k in ('facts_used', 'product', 'products', 'current') else _unhedge_all(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_unhedge_all(v) for v in node]
    return unhedge(node) if isinstance(node, str) else node


def _with_brand(brief, product):
    """The product with the facts the merchant stated in setup added (certifications, policies, what's different)."""
    product = _page_facts(product)
    cs = _setup(brief)
    extra = (cs.product_facts(brief['store'], product['handle']) + cs.brand_facts(brief['store'])) \
        if cs and brief.get('store') else []
    return dict(product, facts=list(product['facts']) + extra) if extra else product


def _rules(brief):
    cs = _setup(brief)
    return cs.rules(brief['store']) if cs and brief.get('store') else {}


def _input(brief, product, draft_type='product_fix'):
    facts = '\n'.join('- %s: %s  [%s]' % (f['label'], f['value'], f['source']) for f in product['facts'])
    qs = '\n'.join('- "%s" (your products named in %d of %d answers)' % (q['question'], q['own'], q['answers'])
                   for q in brief['questions'])
    comps = '\n'.join('- %s %s (named %d times)' % (c['brand'], c['product'], c['named'])
                      for c in brief['competitors'][:5])
    return ('BRAND: %s\nPRODUCT: %s\nURL: %s\n\nPRODUCT FACTS:\n%s\n\nCURRENT DESCRIPTION:\n%s\n\n'
            'BUYER QUESTIONS THIS PAGE SHOULD ANSWER:\n%s\n\n'
            'PRODUCTS AI RECOMMENDED INSTEAD (context only - never mention them on the page):\n%s'
            % (_brand_name(brief), product['title'], product['url'], facts or '(none)', '\n'.join(product['description']) or '(empty)',
               qs, comps or '(none)')) + _research(brief) + _voice(brief) + _examples(brief, draft_type) + _lessons(brief, draft_type) + _editor(brief)


def _norm(s):
    return re.sub(r'\s+', ' ', (s or '').lower()).strip()


def check_specs(result, product):
    """Drop spec rows whose value isn't stated in the facts or description. Returns the dropped rows."""
    known = ' | '.join(_norm(f['value']) for f in product['facts']) + ' | ' + _norm(' '.join(product['description']))
    kept, dropped = [], []
    for row in result['spec_table']:
        ok = (_stated(row['value'], known) and _norm(row['label']) not in SPEC_EXCLUDED
              and len(row['value']) <= SPEC_MAX)
        (kept if ok else dropped).append(row)
    result['spec_table'] = kept
    return dropped


TITLE_MAX = 70
_TITLE_FILLER = {'and', 'with', 'for', 'the', 'a', 'an', 'of', 'in', 'by', 'to', 'on', 'from', 'set'}


def _brand_name(brief):
    try:
        return (db.brand(brief['store']) or {}).get('brand_name') or ''
    except Exception:
        return ''


def check_title(result, product, brand=''):
    """Day 19: a rewritten title may only add words stated in the facts, description or brand name, must keep
    the product's own name, and must fit Shopping's 70 characters. Otherwise the old title is kept.
    Returns why it was reverted, or ''."""
    old, new = product['title'], (result.get('title') or '').strip()
    if not new or new == old:
        result['title'] = old
        return ''
    words = lambda t: re.findall(r'[a-z0-9%]+', _norm(t))
    known = set(words(' '.join([old, brand, ' '.join(product['description'])] +
                               ['%s %s' % (f['label'], f['value']) for f in product['facts']])))
    why = ''
    if len(new) > TITLE_MAX:
        why = 'longer than %d characters' % TITLE_MAX
    elif _norm(old) not in _norm(new):
        why = "doesn't keep the product's own name"
    else:
        added = [w for w in words(new) if w not in known and w not in _TITLE_FILLER]
        if added:
            why = 'adds words the store never states: %s' % ', '.join(sorted(set(added)))
    if why:
        result['title'], result['title_reason'] = old, 'Kept the current title (the rewrite %s).' % why
    return why


def product_fix(brief, product=None, usage=None):
    """Draft a product-page fix for the brief's (first) product. Returns the result dict."""
    product = product or brief['products'][0]
    if not product.get('facts_ready'):
        raise ValueError('No catalog facts for %s yet: run catalog_facts.build first.' % product['title'])
    product = _with_brand(brief, product)
    result = _unhedge_all(llm.json_call(PRODUCT_FIX_RULES, _input(brief, product), 'product_fix', PRODUCT_FIX_SCHEMA,
                           usage=usage))
    result['removed_specs'] = check_specs(result, product)
    result['title_reverted'] = check_title(result, product, _brand_name(brief))
    factcheck.check(result, 'product_fix', [product], usage=usage, rules=_rules(brief))
    result['product'] = dict(handle=product['handle'], title=product['title'], url=product['url'],
                             image=product.get('image', ''))
    result['current'] = dict(title=product['title'], description=product['description'])
    return result



FAQ_RULES = """You write the FAQ block for one product page of an online store, so the page answers the questions buyers ask AI shopping assistants.

Hard rules:
1. Use ONLY the facts under PRODUCT FACTS and CURRENT DESCRIPTION. Never add a material, size, ingredient, certification, benefit, number or claim that is not stated there.
2. Write 3-6 questions in the buyer's own words, based on the BUYER QUESTIONS (rephrased to be about this product) and the obvious follow-ups. Each answer is 1-3 plain sentences that start with the direct answer.
3. Only include a question if the facts answer it. If they don't, put it in open_questions for the merchant instead (one short question, answerable in a few words). Also add the 2-5 follow-ups buyers of this kind of product usually ask that the facts can't answer.
4. No superlatives, no hype, no competitors, no AI, no price or stock levels.
5. Keep the store's language, spelling and tone.
6. facts_used: copy, word for word, the fact values or description phrases the answer relies on.
Also, always:
- Never write about the page or its wording ("its description says", "the product information should", "as stated above", "the stated refund policy", "is described as"). The store is speaking: say the fact itself ("Beauty products can't be returned", "It's lightweight").
- Store policies (returns, shipping, refunds) only appear in an FAQ answer to a returns or shipping question, never in a product description.
- Never state shipping weight, and never put the brand name, the product type or the product's story in a spec table.
""" + ANSWER_FIRST

FAQ_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["faqs", "open_questions"],
    "properties": {
        "faqs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "answer", "facts_used"],
            "properties": {"question": {"type": "string"}, "answer": {"type": "string"},
                           "facts_used": {"type": "array", "items": {"type": "string"}}}}},
        "open_questions": PRODUCT_FIX_SCHEMA["properties"]["open_questions"],
    },
}


def faq_html(faqs):
    """The FAQ block for the page, plus FAQPage markup so assistants can read it as questions and answers."""
    import html as _h
    body = ''.join('<h3>%s</h3><p>%s</p>' % (_h.escape(f['question']), _h.escape(f['answer'])) for f in faqs)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f['question'],
         "acceptedAnswer": {"@type": "Answer", "text": f['answer']}} for f in faqs]}
    return body + '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False)


def faq(brief, product=None, usage=None):
    """Draft an FAQ block for the brief's (first) product. Returns the result dict."""
    product = product or brief['products'][0]
    if not product.get('facts_ready'):
        raise ValueError('No catalog facts for %s yet: run catalog_facts.build first.' % product['title'])
    product = _with_brand(brief, product)
    result = _unhedge_all(llm.json_call(FAQ_RULES, _input(brief, product, 'faq'), 'faq', FAQ_SCHEMA, usage=usage))
    # Mechanical check: an answer must lean on at least one stated fact.
    known = ' | '.join(_norm(f['value']) for f in product['facts']) + ' | ' + _norm(' '.join(product['description']))
    kept, dropped = [], []
    for f in result['faqs']:
        used = [u for u in f['facts_used'] if _stated(u, known)]
        (kept if used else dropped).append(f)
    result['faqs'], result['removed_faqs'] = kept, dropped
    factcheck.check(result, 'faq', [product], usage=usage, rules=_rules(brief))
    result['html'] = faq_html(result['faqs'])
    result['product'] = dict(handle=product['handle'], title=product['title'], url=product['url'],
                             image=product.get('image', ''))
    return result


def _many_input(brief, products, competitors, draft_type='comparison'):
    """Facts for several products, each tagged with an id the model must cite."""
    parts = []
    for i, p in enumerate(products):
        facts = '\n'.join('  - %s: %s' % (f['label'], f['value']) for f in p['facts'])
        parts.append('[P%d] %s (your product) %s\n%s\n  Description: %s'
                     % (i + 1, p['title'], p['url'], facts or '  (no facts)', ' '.join(p['description'])[:1200] or '(empty)'))
    for i, c in enumerate(competitors):
        parts.append('[C%d] %s %s (another brand; AI named it %d times) %s\n  Their page says: %s'
                     % (i + 1, c['brand'], c['product'], c['named'], c['url'], c['page_excerpt'][:1500]))
    qs = '\n'.join('- "%s" (your products named in %d of %d answers)' % (q['question'], q['own'], q['answers'])
                   for q in brief['questions'])
    return ('BUYER QUESTIONS:\n%s\n\nPRODUCTS:\n%s' % (qs, '\n\n'.join(parts)) + _research(brief) + _voice(brief)
            + _patterns(brief, draft_type) + _examples(brief, draft_type) + _lessons(brief, draft_type) + _editor(brief))


def _sources(products, competitors):
    """id -> normalised text the claims about that product must be found in."""
    out = {}
    for i, p in enumerate(products):
        out['P%d' % (i + 1)] = ' | '.join(_norm(f['value']) for f in p['facts']) + ' | ' + _norm(' '.join(p['description']))
    for i, c in enumerate(competitors):
        out['C%d' % (i + 1)] = _norm(c['page_excerpt'])
    return out


def _stated(value, source):
    # Whole words only: "Yes" must not count as stated because "polyester" contains it.
    v = _norm(value)
    return bool(v) and re.search(r'(?<!\w)%s(?!\w)' % re.escape(v), source) is not None


NOT_STATED = 'Not stated'

COMPARISON_RULES = """You write a side-by-side comparison page for an online store, so a buyer choosing between options can see the differences at a glance.

Hard rules:
1. Columns are the products given, by id (P1, P2... are the store's own; C1, C2... are other brands). Use every P product; use C products only if their page text states something useful.
2. Rows are the attributes buyers compare when asking the BUYER QUESTIONS. Each cell value must be copied word for word from that product's own facts, description or page text. If it isn't stated, the value is exactly "Not stated". Never infer, round or convert.
3. Leave out price, availability, stock and reviews.
4. intro: 1-2 neutral sentences saying who the comparison is for. summary: one short line per product on who it suits, using only stated facts. Never call a product better, best or worse, never criticise another brand, no hype, no mention of AI.
5. Keep the store's language and spelling.
6. open_questions: attributes buyers would compare that the store's own products don't state, as short questions for the merchant.
Also, always:
- Never write about the page or its wording ("its description says", "the product information should", "as stated above", "the stated refund policy", "is described as"). The store is speaking: say the fact itself ("Beauty products can't be returned", "It's lightweight").
- Store policies (returns, shipping, refunds) only appear in an FAQ answer to a returns or shipping question, never in a product description.
- Never state shipping weight, and never put the brand name, the product type or the product's story in a spec table.
""" + ANSWER_FIRST

COMPARISON_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "intro", "columns", "rows", "summary", "open_questions"],
    "properties": {
        "title": {"type": "string"},
        "intro": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "cells"],
            "properties": {"label": {"type": "string"}, "cells": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "value"],
                "properties": {"id": {"type": "string"}, "value": {"type": "string"}}}}}}},
        "summary": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "text", "facts_used"],
            "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                           "facts_used": {"type": "array", "items": {"type": "string"}}}}},
        "open_questions": PRODUCT_FIX_SCHEMA["properties"]["open_questions"],
    },
}


def check_comparison(result, sources):
    """Blank cells and drop summary lines not stated in that product's own source. Returns what was removed."""
    removed = []
    # Columns come from the cells, in source order: the model sometimes lists names, not ids, here.
    ids = {c['id'] for r in result['rows'] for c in r['cells']}
    result['columns'] = [k for k in sources if k in ids]
    for row in result['rows']:
        cells = []
        for cell in row['cells']:
            if cell['id'] not in result['columns']:
                continue
            if cell['value'] != NOT_STATED and not _stated(cell['value'], sources[cell['id']]):
                removed.append(dict(label=row['label'], id=cell['id'], value=cell['value']))
                cell = dict(cell, value=NOT_STATED)
            cells.append(cell)
        row['cells'] = cells
    # A row only one product states compares nothing (with two or more columns).
    need = 2 if len(result['columns']) >= 2 else 1
    result['rows'] = [r for r in result['rows'] if sum(c['value'] != NOT_STATED for c in r['cells']) >= need
                      and _norm(r['label']) not in SPEC_EXCLUDED]
    kept = []
    for s in result['summary']:
        ok = s['id'] in sources and any(_stated(u, sources[s['id']]) for u in s['facts_used'])
        (kept if ok else removed).append(s if ok else dict(s, removed='summary'))
    result['summary'] = kept
    return removed


def comparison_html(result, names):
    """The table. The store's own products link to their pages (internal links, 18 Oct 2026); other brands
    are named, not linked, so the page never sends buyers away."""
    import html as _h
    e = _h.escape
    cols = result['columns']
    urls = {'P%d' % (i + 1): p.get('url', '') for i, p in enumerate(result.get('products') or [])}
    name = lambda c: ('<a href="%s">%s</a>' % (e(urls[c]), e(names[c]))) if urls.get(c) else e(names[c])
    head = '<tr><th></th>%s</tr>' % ''.join('<th>%s</th>' % name(c) for c in cols)
    body = ''.join('<tr><th>%s</th>%s</tr>' % (e(r['label']), ''.join(
        '<td>%s</td>' % e(next((c['value'] for c in r['cells'] if c['id'] == col), NOT_STATED)) for col in cols))
        for r in result['rows'])
    summ = ''.join('<li><strong>%s</strong>: %s</li>' % (name(s['id']), e(s['text'])) for s in result['summary'])
    return '<p>%s</p><table>%s%s</table>%s' % (e(result['intro']), head, body, '<ul>%s</ul>' % summ if summ else '')


def _ready(products):
    products = [p for p in products if p.get('facts_ready')]
    if not products:
        raise ValueError('No catalog facts for these products yet: run catalog_facts.build first.')
    return products


def _names(products, competitors):
    n = {'P%d' % (i + 1): p['title'] for i, p in enumerate(products)}
    n.update({'C%d' % (i + 1): ('%s %s' % (c['brand'], c['product'])).strip() for i, c in enumerate(competitors)})
    return n


def comparison(brief, usage=None, max_own=4, max_other=2):
    """Draft a comparison page: the store's products, plus up to two competitor products whose page we read."""
    products = [_with_brand(brief, p) for p in _ready(brief['products'])[:max_own]]
    never = {_norm(b) for b in _rules(brief).get('never_name', [])}
    competitors = [c for c in brief['competitors'] if c['page_read'] and c['page_excerpt']
                   and _norm(c['brand']) not in never][:max_other]
    if len(products) + len(competitors) < 2:
        raise ValueError('A comparison needs at least two products with stated facts.')
    sources = _sources(products, competitors)
    result = _unhedge_all(llm.json_call(COMPARISON_RULES, _many_input(brief, products, competitors), 'comparison',
                           COMPARISON_SCHEMA, usage=usage))
    result['removed'] = check_comparison(result, sources)
    factcheck.check(result, 'comparison', products, competitors, usage=usage, rules=_rules(brief))
    names = _names(products, competitors)
    result['names'] = names
    result['products'] = [dict(handle=p['handle'], title=p['title'], url=p['url'], image=p.get('image', ''))
                          for p in products]
    result['html'] = comparison_html(result, names)
    result['competitors_used'] = [dict(brand=c['brand'], product=c['product'], url=c['url']) for c in competitors]
    result['product'] = result['products'][0]
    return result


GUIDE_RULES = """You write a short buying guide for an online store's blog that answers the BUYER QUESTIONS and points to the store's own products.

Hard rules:
1. Only the store's own products (P1, P2...) may be recommended. Never name or criticise another brand. No mention of AI.
2. General buying advice (what to look for, how to choose) is allowed but must be cautious and generic: no numbers, ingredients, certifications, health or performance claims unless they are stated in a product's facts.
3. Every sentence about a specific product must rest on that product's stated facts. For each product pick, list in facts_used the fact values or description phrases, copied word for word.
4. 3-5 sections, each a heading and 1-3 short paragraphs. Plain, no superlatives ("best", "ultimate"), no hype. Leave out price and stock.
5. Keep the store's language and spelling. The title reads like a buyer's question or a plain "How to choose..." heading.
6. open_questions: facts the guide needed but the store's products don't state, as short questions for the merchant.
7. picks: for_whom is a few words on who it suits ("For daily use on oily skin"); text is ONE short sentence on why, that doesn't repeat what the sections already said. With one product, keep it to that single line.
Also, always:
- Never write about the page or its wording ("its description says", "the product information should", "as stated above", "the stated refund policy", "is described as"). The store is speaking: say the fact itself ("Beauty products can't be returned", "It's lightweight").
- Store policies (returns, shipping, refunds) only appear in an FAQ answer to a returns or shipping question, never in a product description.
- Never state shipping weight, and never put the brand name, the product type or the product's story in a spec table.
""" + ANSWER_FIRST

GUIDE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "intro", "sections", "picks", "open_questions"],
    "properties": {
        "title": {"type": "string"},
        "intro": {"type": "string"},
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["heading", "paragraphs"],
            "properties": {"heading": {"type": "string"},
                           "paragraphs": {"type": "array", "items": {"type": "string"}}}}},
        "picks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "for_whom", "text", "facts_used"],
            "properties": {"id": {"type": "string"}, "for_whom": {"type": "string"}, "text": {"type": "string"},
                           "facts_used": {"type": "array", "items": {"type": "string"}}}}},
        "open_questions": PRODUCT_FIX_SCHEMA["properties"]["open_questions"],
    },
}


def _sentence(t):
    """'For shoppers seeking X.' -> one clean sentence ending in a full stop."""
    t = (t or '').strip().rstrip('.:;,- ')
    return (t[:1].upper() + t[1:] + '.') if t else ''


def guide_html(result, products):
    import html as _h
    e = _h.escape
    by_id = {'P%d' % (i + 1): p for i, p in enumerate(products)}
    out = ['<p>%s</p>' % e(result['intro'])]
    for s in result['sections']:
        out.append('<h2>%s</h2>%s' % (e(s['heading']), ''.join('<p>%s</p>' % e(t) for t in s['paragraphs'])))
    if result['picks']:
        out.append('<h2>Which one should you choose?</h2><ul>%s</ul>' % ''.join(
            '<li><a href="%s"><strong>%s</strong></a>: %s %s</li>' % (
                e(by_id[k['id']]['url']), e(by_id[k['id']]['title']), e(_sentence(k['for_whom'])), e(k['text']))
            for k in result['picks']))
    return ''.join(out)


def guide(brief, usage=None, max_own=6):
    """Draft a buying guide that recommends only the store's own products."""
    products = [_with_brand(brief, p) for p in _ready(brief['products'])[:max_own]]
    sources = _sources(products, [])
    result = _unhedge_all(llm.json_call(GUIDE_RULES, _many_input(brief, products, [], 'guide'), 'guide', GUIDE_SCHEMA, usage=usage))
    kept, dropped = [], []
    for k in result['picks']:
        ok = k['id'] in sources and any(_stated(u, sources[k['id']]) for u in k['facts_used'])
        (kept if ok else dropped).append(k)
    result['picks'], result['removed_picks'] = kept, dropped
    # Another brand named in the prose is not allowed (rule 1); drop the paragraph.
    brands = [_norm(c['brand']) for c in brief['competitors'] if len(_norm(c['brand'])) > 2]
    result['removed_paragraphs'] = []
    for s in result['sections']:
        ok = [t for t in s['paragraphs'] if not any(re.search(r'\b%s\b' % re.escape(b), _norm(t)) for b in brands)]
        result['removed_paragraphs'] += [t for t in s['paragraphs'] if t not in ok]
        s['paragraphs'] = ok
    factcheck.check(result, 'guide', products, usage=usage, rules=_rules(brief))
    result['html'] = guide_html(result, products)
    result['products'] = [dict(handle=p['handle'], title=p['title'], url=p['url'], image=p.get('image', ''))
                          for p in products]
    result['product'] = result['products'][0]
    return result


def save(brief_id, brief, result, draft_type='product_fix', usage=None):
    """Store a draft and its first version; it lands in the Inbox. Returns the draft id."""
    import content_agent
    content_agent.init()
    now = time.time()
    handles = [p['handle'] for p in result.get('products') or [result['product']]]
    sources = [dict(f, product=p['handle']) for p in brief['products'] if p['handle'] in handles for f in p['facts']]
    title = {'product_fix': '%s: page fix', 'faq': '%s: FAQ'}.get(draft_type)
    title = title % result['product']['title'] if title else result.get('title') or draft_type
    with db.conn() as c:
        did = c.execute('INSERT INTO content_drafts (brief_id, store_domain, draft_type, title, status, created_at, '
                        "updated_at) VALUES (?,?,?,?,'draft',?,?)",
                        (brief_id, brief['store'], draft_type, title, now, now)).lastrowid
        c.execute('INSERT INTO content_draft_versions (draft_id, body, author, sources, open_facts, created_at) '
                  "VALUES (?,?,'agent',?,?,?)",
                  (did, json.dumps(dict(result, cost_cents=usage.cost_cents() if usage else None)),
                   json.dumps(sources), json.dumps(result['open_questions']), now))
    return did


def latest(draft_id):
    row = db.one('SELECT * FROM content_draft_versions WHERE draft_id=? ORDER BY id DESC LIMIT 1', (draft_id,))
    return json.loads(row['body']) if row else None


if __name__ == '__main__':
    # python3 drafts.py <domain> [n]  - draft product fixes for the top n open opportunities
    import sys
    import briefs
    domain, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
    done = 0
    for r in briefs.candidates(domain):
        b = briefs.build(domain, r['type'], r['key'])
        if not b or not b['products'] or 'product_fix' not in [t for t, _ in briefs.choose_types(b)]:
            continue
        u = llm.Usage()
        res = product_fix(b, usage=u)
        did = save(briefs.save(b, 'product_fix'), b, res, usage=u)
        print('draft %d  %s  (%.2f cents)' % (did, res['product']['title'], u.cost_cents() or 0))
        print(json.dumps({k: res[k] for k in ('title', 'title_reason', 'description_html', 'spec_table',
                                              'open_questions', 'changes', 'removed_specs')}, indent=1))
        done += 1
        if done >= n:
            break
