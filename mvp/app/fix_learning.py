"""Product page fixes learn from the owner, like the AEO articles do (20 Oct 2026).

Kelian: do for product page fixes what we did for articles: the owner sees the fix on their real product page
(product_preview.py), clicks any part of it and changes just that part (Shorter, Simpler, In our voice, Make it a
list, Remove, own words, Type it yourself), and the agent keeps every lasting preference as a lesson for future
product pages.

Parts (paths): title, desc.<n> (n-th block of the description), spec_table, spec_table.<n>, faqs.<n>,
faqs.<n>.answer. A rewrite is fact-checked again (only the changed sentences), and a change that would need facts
the store doesn't state is retried once, then refused with the part unchanged, exactly like articles.

Lessons live in content_settings['fix_lessons'] and go into every product fix and FAQ prompt (drafts._input).
Settings > Look and lessons lists them with Remove. Undo and History reuse article_learning.restore.
"""
import json
import re
import threading
import time
import uuid

MAX_LESSONS = 25
LESSONS_IN_PROMPT = 15
KINDS = ('product_fix', 'faq')


# ---- lessons ---------------------------------------------------------------------------------------------

def lessons(domain):
    import content_setup
    return [l for l in content_setup.get(domain).get('fix_lessons') or [] if l.get('active', True)]


def add_lesson(domain, text, source, example=''):
    import content_setup
    text = (text or '').strip()
    if not text:
        return None
    s = content_setup.get(domain)
    ls = s.get('fix_lessons') or []
    if any(l['text'].lower().rstrip('.') == text.lower().rstrip('.') for l in ls):
        return None
    lesson = dict(id=uuid.uuid4().hex[:10], text=text, source=source, example=(example or '')[:200], at=time.time(), active=True)
    s['fix_lessons'] = (ls + [lesson])[-MAX_LESSONS:]
    content_setup.put(domain, s)
    return lesson


def remove_lesson(domain, lesson_id):
    import content_setup
    s = content_setup.get(domain)
    s['fix_lessons'] = [l for l in s.get('fix_lessons') or [] if l['id'] != lesson_id]
    content_setup.put(domain, s)


def prompt(domain):
    try:
        ls = lessons(domain)[-LESSONS_IN_PROMPT:]
    except Exception:                                                       # noqa: BLE001 - fresh store, tests
        return ''
    if not ls:
        return ''
    return ('\n\nWHAT THIS STORE\'S OWNER HAS ASKED FOR ON EARLIER PRODUCT PAGES (always follow; the fact rules still win):\n'
            + '\n'.join('- ' + l['text'] for l in ls))


# ---- the parts of a fix ----------------------------------------------------------------------------------

def label(path):
    p = path.split('.')
    if p[0] == 'title':
        return 'Title'
    if p[0] == 'desc':
        return 'Paragraph'
    if p[0] == 'spec_table':
        return 'Spec row' if len(p) > 1 else 'Spec table'
    if p[0] == 'faqs':
        return 'Answer' if len(p) > 2 else 'Question and answer'
    return 'Part'


def _blocks(body):
    import product_preview
    return product_preview.blocks(body.get('description_html', ''))


def _get(body, path):
    p = path.split('.')
    try:
        if p == ['title']:
            return body.get('title') or (body.get('current') or {}).get('title') or ''
        if p[0] == 'desc' and len(p) == 2:
            return _blocks(body)[int(p[1])]
        if p[0] == 'faqs' and len(p) == 2:
            f = body['faqs'][int(p[1])]
            return dict(question=f['question'], answer=f['answer'])
        if p[0] == 'faqs' and len(p) == 3 and p[2] in ('answer', 'question'):
            return body['faqs'][int(p[1])][p[2]]
    except (KeyError, IndexError, ValueError, TypeError):
        pass
    raise ValueError('That part has changed since you opened it. Reload and try again.')


def _set(body, path, value):
    p = path.split('.')
    if p == ['title']:
        body['title'] = value
    elif p[0] == 'desc':
        bl = _blocks(body)
        bl[int(p[1])] = value
        body['description_html'] = '\n'.join(b for b in bl if b.strip())
    elif p[0] == 'faqs' and len(p) == 2:
        body['faqs'][int(p[1])].update(value)
    else:
        body['faqs'][int(p[1])][p[2]] = value


def _product(domain, body):
    """The product as the writer saw it (facts + the owner's setup facts), for the fact check."""
    import drafts
    import product_preview
    rec = product_preview._product(domain, body)
    if not rec.get('facts'):
        raise ValueError('The agent can\'t find this product\'s facts any more, so it can\'t check a rewrite.')
    rec = dict(rec, description=(body.get('current') or {}).get('description') or rec.get('description') or [])
    return drafts._with_brand(dict(store=domain), rec)


def _check(domain, body, draft_type, before, usage=None):
    import drafts
    import factcheck
    product = _product(domain, body)
    if draft_type == 'product_fix':
        drafts.check_specs(body, product)
        drafts.check_title(body, product, drafts._brand_name(dict(store=domain)))
    factcheck.check(body, draft_type, [product], usage=usage, rules=drafts._rules(dict(store=domain)),
                    verified=factcheck.verified_sentences(before, draft_type, with_gaps=True))


def _load(domain, draft_id):
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    if not row or row['draft_type'] not in KINDS:
        raise ValueError('Only product page fixes and FAQs can be changed this way.')
    return row, body, prev


def _save(draft_id, body, prev, row, note):
    import content_review
    body['change_note'] = note
    content_review.rebuild(body, row['draft_type'])
    content_review.save_version(draft_id, body, prev, author='merchant')


def _gaps(v):
    return json.dumps(v, ensure_ascii=False).count('[ask merchant:')


PART_RULES = """You write the product pages of an online store. The owner selected ONE PART of a product page and asked for a change. Rewrite only that part.

Rules:
- Do exactly what was asked, to this part only. If SELECTED WORDS are given, change those words and as little around them as needed.
- Shorter, simpler or a list: keep what each sentence says; only cut words or use plainer ones.
- Never add a material, size, ingredient, certification, benefit, number or claim that isn't in the part already or in PRODUCT FACTS. If the request needs a fact you don't have, leave it out and say so in reply.
- A paragraph is returned as simple HTML: one <p>...</p>, or a <ul> with <li> items for a list (you may use <strong>). A title or an answer is plain text.
- The title keeps the product's own name word for word and stays under 70 characters.
- Keep the store's spelling and voice. No hype, no superlatives, no competitors, no mention of AI.
- lesson: one short instruction for FUTURE product pages that captures the owner's preference behind this change (e.g. "Open with who it's for", "Never use the word 'luxurious'", "Keep descriptions under 80 words"), or "" if it's only about this page.
- reply: one short sentence to the owner on what you changed."""

QUICK = {
    'shorter': 'Make it shorter. Keep the meaning and every fact; cut words.',
    'simpler': 'Make it simpler to read: shorter sentences, plainer words.',
    'voice': "Rewrite it in the brand's voice (see BRAND VOICE).",
    'list': 'Turn it into a short bulleted list where that reads better, or into tighter sentences if it is already a list.',
}


def change_part(domain, draft_id, path, instruction='', quick='', selection='', remember=True, usage=None):
    """Rewrite one part of a product fix or FAQ. Returns (reply, lesson or None)."""
    import content_setup
    import llm
    row, body, prev = _load(domain, draft_id)
    if path.split('.')[0] == 'spec_table':
        raise ValueError('Spec rows are copied exactly from your product\'s facts. Remove a row, or change the fact in Shopify.')
    old = _get(body, path)
    ask = (QUICK.get(quick, '') + ' ' + (instruction or '')).strip()
    if not ask:
        raise ValueError('Say what should change.')
    part = {"type": "object", "additionalProperties": False, "required": ["question", "answer"],
            "properties": {"question": {"type": "string"}, "answer": {"type": "string"}}} if isinstance(old, dict) else {"type": "string"}
    schema = {"type": "object", "additionalProperties": False, "required": ["part", "lesson", "reply"],
              "properties": {"part": part, "lesson": {"type": "string"}, "reply": {"type": "string"}}}
    product = _product(domain, body)
    facts = '\n'.join('- %s: %s' % (f['label'], f['value']) for f in product['facts']) + \
        '\nCURRENT DESCRIPTION ON THE STORE:\n' + '\n'.join(product.get('description') or [])
    text = ('OWNER\'S REQUEST: %s\nSELECTED WORDS: %s\nTHE PART TO CHANGE (%s of the page for %s), currently:\n%s\n\n'
            'BRAND VOICE:\n%s\n\nPRODUCT FACTS:\n%s%s' % (
                ask[:1500], (selection or '(the whole part)')[:600], label(path).lower(), product.get('title', ''),
                json.dumps(old, ensure_ascii=False) if isinstance(old, dict) else old,
                content_setup.voice_text(domain) or '(none)', facts, prompt(domain)))
    before = json.loads(json.dumps(body))
    gaps_before = _gaps(old)
    held = []
    for _ in range(2):
        extra = ('' if not held else '\n\nYOUR LAST TRY WAS HELD BACK: these sentences said things the store doesn\'t state:\n'
                 + '\n'.join('- ' + h for h in held) + '\nStay closer to the original wording and facts.')
        res = llm.json_call(PART_RULES, text + extra, 'fix_part', schema, usage=usage, attempts=3)
        new = res['part']
        if isinstance(new, str):
            new = new.strip()
            if not new or len(re.sub(r'<[^>]+>', '', new)) < 0.15 * len(re.sub(r'<[^>]+>|\[ask merchant:[^\]]*\]', '', old)):
                raise ValueError('The agent sent back something that isn\'t a rewrite of this part, so nothing changed. Try again.')
            if path.startswith('desc.') and not new.startswith('<'):
                new = '<p>%s</p>' % new
        body = json.loads(json.dumps(before))
        _set(body, path, new)
        _check(domain, body, row['draft_type'], before, usage=usage)
        if path == 'title' and body.get('title_reverted'):
            raise ValueError('That title %s, so the title is unchanged.' % body['title_reverted'])
        try:
            changed = _get(body, path)
        except ValueError:
            changed = None
        if _gaps(changed) <= gaps_before:
            break
        held = [c['sentence'] for c in (body.get('fact_check') or {}).get('claims', [])][:5]
    else:
        raise ValueError('The agent couldn\'t make that change without saying things your store doesn\'t state, '
                         'so the part is unchanged. Try saying exactly what to change.')
    _save(draft_id, body, prev, row, '%s: %s' % (label(path), (quick and quick.capitalize() or instruction)[:80]))
    lesson = add_lesson(domain, res['lesson'], 'request', example=ask) if remember and res.get('lesson') else None
    return res.get('reply', ''), lesson


def remove_part(domain, draft_id, path):
    row, body, prev = _load(domain, draft_id)
    p = path.split('.')
    try:
        if p == ['title']:
            raise ValueError('A product needs a title. Ask for a different one instead.')
        if p[0] == 'desc':
            bl = _blocks(body)
            del bl[int(p[1])]
            if not bl:
                raise ValueError('That would leave the description empty.')
            body['description_html'] = '\n'.join(bl)
        elif p == ['spec_table']:
            body['spec_table'] = []
        elif p[0] == 'spec_table':
            del body['spec_table'][int(p[1])]
        elif p[0] == 'faqs':
            del body['faqs'][int(p[1])]
            if not body['faqs'] and row['draft_type'] == 'faq':
                raise ValueError('That would leave the FAQ empty. Reject the draft instead.')
        else:
            raise ValueError('That part can\'t be removed on its own.')
    except (IndexError, KeyError, TypeError):
        raise ValueError('That part has changed since you opened it. Reload and try again.')
    _save(draft_id, body, prev, row, 'Removed: %s' % label(path))
    return 'Removed.'


def set_text(domain, draft_id, path, text):
    """The owner typed the new wording. Their words aren't fact-checked; the agent learns from it in the background."""
    import html as _h
    row, body, prev = _load(domain, draft_id)
    old = _get(body, path)
    if not isinstance(old, str):
        raise ValueError('Type into one piece of text at a time.')
    text = re.sub(r'[ \t]+', ' ', (text or '').replace('\r', '')).strip()[:4000]
    if not text:
        raise ValueError('Type something, or remove the part instead.')
    if path.startswith('desc.'):
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if re.match(r'<(ul|ol)\b', old, re.I) and len(lines) > 1:
            text = '<ul>%s</ul>' % ''.join('<li>%s</li>' % _h.escape(l.lstrip('-•* ')) for l in lines)
        else:
            text = ''.join('<p>%s</p>' % _h.escape(l) for l in lines)
    before = json.loads(json.dumps(body))
    _set(body, path, text)
    body['edited_at'] = time.time()
    _save(draft_id, body, prev, row, 'You typed: %s' % label(path))
    learn_in_background(domain, before, body)
    return 'Saved.'


EDIT_RULES = """An online store's owner edited a product page the agent wrote. Compare BEFORE and AFTER and say what lasting preference, if any, the edit shows for FUTURE product pages.

Return 0-2 lessons, each one short instruction (e.g. "Never call products 'luxurious'", "Lead with the skin type it suits", "Keep it to two short paragraphs"). Fixing a typo, a fact or this product's own detail is not a lesson: return []."""
EDIT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lessons"],
               "properties": {"lessons": {"type": "array", "items": {"type": "string"}}}}


def _plain(body):
    return dict(title=body.get('title', ''), description=re.sub(r'<[^>]+>', ' ', body.get('description_html', '')),
                faqs=[(f.get('question'), f.get('answer')) for f in body.get('faqs') or []])


def learn_from_edit(domain, before, after, usage=None):
    import llm
    a, b = _plain(before), _plain(after)
    if a == b:
        return []
    try:
        res = llm.json_call(EDIT_RULES, 'BEFORE:\n%s\n\nAFTER:\n%s' % (json.dumps(a, ensure_ascii=False)[:3000],
                                                                    json.dumps(b, ensure_ascii=False)[:3000]),
                            'fix_edit_lessons', EDIT_SCHEMA, usage=usage, attempts=2)
    except Exception:                                                       # noqa: BLE001
        return []
    return [l for l in (add_lesson(domain, t, 'edit') for t in (res.get('lessons') or [])[:2]) if l]


def learn_in_background(domain, before, after):
    threading.Thread(target=learn_from_edit, args=(domain, before, after), daemon=True).start()
