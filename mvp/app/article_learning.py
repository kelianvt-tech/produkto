"""Article learning: the agent learns from every change the merchant makes to an article (19 Oct 2026).

Kelian: when the merchant previews a draft article and asks for changes ("remove this", "use a
different font", "no sunscreen talk"), the agent must learn from them as it goes.

Two ways in:
  * Ask for changes: the merchant types what they want. One helper-model call (~0.3 cent) rewrites
    the article's blocks, may change the look (only to fonts the store itself uses, or its colours),
    and decides whether the request is a lasting preference ("never mention sunscreen", "shorter
    intros", "headings in the body font") or about this article only. The fact check runs again on
    the rewrite, so a change can never bring in an invented fact.
  * Edits by hand: when the merchant saves edited text, one cheap call compares before and after and
    keeps 0-2 lasting lessons, in the background so saving stays instant.

Lessons live in content_settings['article_lessons'] and go into every future article's prompt
(drafts.article). Look changes live in content_settings['brand_style_overrides'] (brand_style.get).
Both are listed in the agent's Settings, where the merchant can remove any of them.
examples.py still shows the writer the merchant's approved, edited drafts on top of this.
"""
import json
import threading
import time
import uuid

MAX_LESSONS = 25
LESSONS_IN_PROMPT = 15


# ---- stored lessons --------------------------------------------------------------------------------

def lessons(domain, active_only=True):
    import content_setup
    ls = content_setup.get(domain).get('article_lessons') or []
    return [l for l in ls if l.get('active', True)] if active_only else ls


def add_lesson(domain, text, source, example=''):
    import content_setup
    text = (text or '').strip()
    if not text:
        return None
    s = content_setup.get(domain)
    ls = s.get('article_lessons') or []
    low = text.lower().rstrip('.')
    if any(l['text'].lower().rstrip('.') == low for l in ls):
        return None
    lesson = dict(id=uuid.uuid4().hex[:10], text=text, source=source, example=(example or '')[:200],
                  at=time.time(), active=True)
    s['article_lessons'] = (ls + [lesson])[-MAX_LESSONS:]
    content_setup.put(domain, s)
    return lesson


def remove_lesson(domain, lesson_id):
    import content_setup
    s = content_setup.get(domain)
    s['article_lessons'] = [l for l in s.get('article_lessons') or [] if l['id'] != lesson_id]
    content_setup.put(domain, s)


def set_override(domain, key, value):
    import content_setup
    s = content_setup.get(domain)
    o = s.get('brand_style_overrides') or {}
    if value in (None, ''):
        o.pop(key, None)
    else:
        o[key] = value
    s['brand_style_overrides'] = o
    content_setup.put(domain, s)


def prompt(domain):
    """The lessons as a writer's prompt section ('' when there are none)."""
    try:
        ls = lessons(domain)[-LESSONS_IN_PROMPT:]
    except Exception:                                                       # noqa: BLE001 - fresh store, tests
        return ''
    if not ls:
        return ''
    return ('\n\nWHAT THIS STORE\'S OWNER HAS ASKED FOR IN EARLIER ARTICLES (always follow; the fact rules still win):\n'
            + '\n'.join('- ' + l['text'] for l in ls))


# ---- ask for changes -------------------------------------------------------------------------------

REVISE_RULES = """You are the writer of an online store's blog article. The store's owner previewed it and asked for a change. Apply it.

Return the whole article again in the same structure, with the change made and everything else kept as it was. Rules:
- Do exactly what was asked. Removing something means removing it, not rewording it.
- Never add a product fact, number, ingredient, benefit or claim that isn't already in the article or in PRODUCT FACTS. If the request needs a fact you don't have, leave that part out and say so in reply.
- Product ids (P1, P2...) must stay valid; only products listed under PRODUCT FACTS may appear.
- style: only fill a field when the owner asked about the look (font, capitals, colours, corners). Fonts must be chosen from STORE FONTS (or "" to keep). Colours are hex values from STORE COLOURS (or "" to keep). Use "" for everything else.
- lessons: every lasting preference in the request that should apply to FUTURE articles too, each as one short instruction for next time (e.g. "Never tell readers to see a professional", "Keep intros to one sentence", "Headings in the body font", "No FAQ"). Words like "we never", "always", "don't ever" mark a lasting preference. Nothing about this article only (a typo, this one heading): then return [].
- reply: one short sentence to the owner saying what you changed (and anything you couldn't do)."""


def _revise_schema():
    import drafts
    s = json.loads(json.dumps(drafts.ARTICLE_SCHEMA))
    style = {"type": "object", "additionalProperties": False,
             "required": ["heading_font", "body_font", "label_font", "heading_upper", "accent", "ink", "soft", "radius"],
             "properties": {k: {"type": "string"} for k in ("heading_font", "body_font", "label_font", "heading_upper",
                                                             "accent", "ink", "soft", "radius")}}
    return {"type": "object", "additionalProperties": False, "required": ["article", "style", "lessons", "reply"],
            "properties": {"article": s, "style": style, "reply": {"type": "string"},
                           "lessons": {"type": "array", "items": {"type": "string"}}}}


_BLOCK_KEYS = ('title', 'dek', 'category', 'glance', 'sections', 'picks', 'tables', 'faqs', 'faq_heading', 'closing',
               'open_questions')


def blocks(body):
    return {k: body.get(k) for k in _BLOCK_KEYS}


def revise(domain, draft_id, instruction, usage=None, remember=True):
    """Apply a change request to an article draft. Returns (reply, [lessons added], style changes)."""
    import brand_style
    import content_review
    import drafts
    import llm
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    style = brand_style.get(domain)
    raw = brand_style.learn(domain)                      # fonts the store loads, before any override
    fonts = brand_style.families(raw)
    colours = sorted({v for v in raw['colors'].values()})
    facts = drafts.article_facts_text(body)
    text = ('OWNER\'S REQUEST:\n%s\n\nSTORE FONTS: %s\nSTORE COLOURS: %s\nCURRENT LOOK: %s\n\nPRODUCT FACTS:\n%s\n\n'
            'THE ARTICLE NOW (JSON):\n%s') % (instruction.strip()[:1500], ', '.join(fonts) or '(none read)',
                                             ', '.join(colours), brand_style.summary(style), facts,
                                             json.dumps(blocks(body), ensure_ascii=False)[:24000])
    res = llm.json_call(REVISE_RULES, text, 'article_revise', _revise_schema(), usage=usage, attempts=3)
    import factcheck
    new = dict(body)
    new.update(res['article'])
    drafts.article_checks(new, domain, usage=usage, verified=factcheck.verified_sentences(body, 'article', with_gaps=True))
    new.setdefault('requests', []).append(dict(text=instruction.strip()[:500], reply=res.get('reply', ''), at=time.time()))
    new['change_note'] = 'Asked: %s' % instruction.strip()[:80]
    content_review.rebuild(new, row['draft_type'], domain)
    content_review.save_version(draft_id, new, prev, title=new.get('title'))
    changed = {}
    st = res.get('style') or {}
    for k in ('heading_font', 'body_font', 'label_font'):
        if st.get(k) and st[k] in fonts:
            set_override(domain, k, st[k])
            changed[k] = st[k]
    for k in ('accent', 'ink', 'soft'):
        if st.get(k) and st[k].lower() in colours:
            set_override(domain, k, st[k].lower())
            changed[k] = st[k].lower()
    if st.get('heading_upper') in ('true', 'false'):
        set_override(domain, 'heading_upper', st['heading_upper'] == 'true')
        changed['heading_upper'] = st['heading_upper'] == 'true'
    if (st.get('radius') or '').isdigit():
        set_override(domain, 'radius', int(st['radius']))
        changed['radius'] = int(st['radius'])
    if changed:                                          # a new look applies to this article straight away
        _, body2, prev2 = content_review.load(draft_id, domain)
        content_review.rebuild(body2, row['draft_type'], domain)
        content_review.save_version(draft_id, body2, prev2, author='agent')
    added = []
    for t in (res.get('lessons') or [])[:3] if remember else []:
        l = add_lesson(domain, t, 'request', example=instruction)
        if l:
            added.append(l)
    if changed and not added and remember:
        l = add_lesson(domain, 'Keep the article look the owner chose: %s.' % ', '.join(
            '%s %s' % (k.replace('_', ' '), v) for k, v in changed.items()), 'request', example=instruction)
        added += [l] if l else []
    return res.get('reply', ''), added, changed


# ---- edits by hand ---------------------------------------------------------------------------------

EDIT_RULES = """An online store's owner edited a blog article the agent wrote, before approving it. Compare the versions and say what the agent should do differently in FUTURE articles.

Return 0-2 lessons, each one short instruction ("Keep intros to one sentence", "Don't mention sunscreen", "Use 'moisturiser', never 'cream'"). Only lasting preferences about style, tone, length, structure, words or topics. Ignore typo fixes, fixes to one fact, removing a sentence that was waiting for a fact, and changes that only make sense for this article. When in doubt, return none."""

EDIT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lessons"],
               "properties": {"lessons": {"type": "array", "items": {"type": "string"}}}}


def _ungap(t):
    import re
    return re.sub(r'\s*\[ask merchant:[^\]]*\]\s*', ' ', t or '').strip()


def changes(before, after):
    """[(field, old, new)] for the article text that changed. Gaps are left out on both sides: filling or
    dropping one is answering a question, not a lesson about style."""
    import content_review
    old = {p: _ungap(t) for p, _, t in content_review._walk(blocks(before))}
    out = []
    for p, _, t in content_review._walk(blocks(after)):
        t = _ungap(t)
        if old.get(p, '') != t:
            out.append(('.'.join(str(x) for x in p), old.get(p, ''), t))
    removed = [p for p in old if old[p] and p not in {q for q, _, _ in content_review._walk(blocks(after))}]
    out += [('.'.join(str(x) for x in p), old[p], '(removed)') for p in removed]
    return out


def learn_from_edit(domain, before, after, usage=None):
    """Keep 0-2 lessons from a hand edit. Returns the lessons added."""
    import llm
    diff = changes(before, after)
    if not diff or sum(abs(len(n) - len(o)) + (o != n) for _, o, n in diff) < 25:
        return []
    text = '\n'.join('- %s\n  BEFORE: %s\n  AFTER: %s' % (f, o[:400], n[:400]) for f, o, n in diff[:20])
    try:
        res = llm.json_call(EDIT_RULES, text, 'article_edit_lessons', EDIT_SCHEMA, usage=usage, attempts=2)
    except Exception:                                                       # noqa: BLE001
        return []
    out = []
    for t in (res.get('lessons') or [])[:2]:
        l = add_lesson(domain, t, 'edit', example=diff[0][2])
        if l:
            out.append(l)
    return out


def learn_in_background(domain, before, after):
    threading.Thread(target=learn_from_edit, args=(domain, before, after), daemon=True).start()


# ---- change one part (the pencil, 20 Oct 2026) --------------------------------------------------------
# Kelian: a pencil at the top right of the preview, so the owner can select any part of the article and change just
# that, like editing in Claude. The preview tags every piece with its path (article_render.render(marks=True));
# the owner clicks it (or highlights words inside it), picks a quick change or types one, and only that part is
# rewritten and re-checked. "Remember this for future articles" decides whether it also becomes a lesson.

QUICK = {
    'shorter': 'Make it shorter. Keep the meaning and every fact; cut words.',
    'simpler': 'Make it simpler to read: shorter sentences, plainer words.',
    'voice': "Rewrite it in the brand's voice (see BRAND VOICE).",
    'list': 'Turn it into a short list where that reads better, or into tighter sentences if it is already a list.',
}
LABELS = (('title', 'Title'), ('dek', 'Intro'), ('category', 'Category'), ('glance', 'At a glance box'), ('closing', 'Closing banner'),
          ('faqs', 'Question and answer'), ('tables', 'Table'), ('picks', 'Product card text'))


def label(path):
    p = path.split('.')
    if p[0] == 'sections':
        if len(p) == 2:
            return 'Section %d' % (int(p[1]) + 1)
        return 'Heading' if p[2] == 'heading' else 'Paragraph'
    if p[0] == 'glance' and len(p) > 1:
        return 'At a glance row'
    if p[0] == 'faqs' and len(p) > 2:
        return 'Answer'
    if p[0] == 'card':
        return 'Product card'
    return dict(LABELS).get(p[0], 'Part')


def _parse(path):
    return tuple(int(x) if x.isdigit() else x for x in (path or '').split('.') if x)


def _part_schema(value):
    """The JSON schema for one part, from the article's own schema, so a change can't break the structure."""
    import drafts
    props = drafts.ARTICLE_SCHEMA['properties']
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):                                   # e.g. the glance rows
        return {"type": "array", "items": props['glance']['items']}
    keys = set(value)
    for name in ('sections', 'faqs', 'tables', 'glance', 'picks'):
        item = props[name]['items']
        if keys <= set(item['properties']) | {'checked', '_i'}:
            return item
    if keys <= set(props['closing']['properties']):
        return props['closing']
    raise ValueError('This part can\'t be changed on its own.')


PART_RULES = """You are the writer of an online store's blog article. The owner selected ONE PART of it and asked for a change. Rewrite only that part and return it in the same structure.

Rules:
- Do exactly what was asked, to this part only. If SELECTED WORDS are given, change those words and as little around them as needed.
- Shorter, simpler or a list: keep what each sentence is about and what it says; only cut or plainer words. Never turn general advice into a statement about what the products or the routine do.
- Never add a product fact, number, ingredient, benefit or claim that isn't in the part already or in PRODUCT FACTS. Widely accepted general knowledge is fine. If the request needs a fact you don't have, leave it out and say so in reply.
- Keep product ids (P1, P2...) valid. Keep the store's spelling and voice.
- lesson: one short instruction for FUTURE articles that captures the owner's preference behind this change (e.g. "Keep intros to one sentence", "Never mention sunscreen"), or "" if it's only about this article.
- reply: one short sentence to the owner on what you changed."""


def change_part(domain, draft_id, path, instruction='', quick='', selection='', remember=True, usage=None):
    """Rewrite one part of an article draft. Returns (reply, lesson or None)."""
    import content_review
    import drafts
    import factcheck
    import llm
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    keys = _parse(path)
    if not keys or keys[0] not in ('title', 'dek', 'category', 'glance', 'sections', 'faqs', 'tables', 'closing', 'picks'):
        raise ValueError('Pick a part of the article to change.')
    try:
        old = content_review._get(body, keys)
    except (KeyError, IndexError, TypeError):
        raise ValueError('That part has changed since you opened it. Reload and try again.')
    ask = (QUICK.get(quick, '') + ' ' + (instruction or '')).strip()
    if not ask:
        raise ValueError('Say what should change.')
    schema = {"type": "object", "additionalProperties": False, "required": ["part", "lesson", "reply"],
              "properties": {"part": _part_schema(old), "lesson": {"type": "string"}, "reply": {"type": "string"}}}
    try:
        import content_setup
        voice = content_setup.voice_text(domain)
    except Exception:                                                       # noqa: BLE001
        voice = ''
    clean = {k: v for k, v in old.items() if k not in ('checked', '_i')} if isinstance(old, dict) else old
    what = ('the new wording of this %s, as plain text' % label(path).lower()) if isinstance(old, str) \
        else 'this %s in the same structure, rewritten' % label(path).lower()
    text = ('OWNER\'S REQUEST: %s\nSELECTED WORDS: %s\nTHE PART TO CHANGE (a %s of the article), currently:\n%s\n\n'
            'Return in "part": %s.\n\nARTICLE TITLE: %s\nBRAND VOICE:\n%s\n\nPRODUCT FACTS:\n%s%s'
            % (ask[:1500], (selection or '(the whole part)')[:600], label(path).lower(),
               clean if isinstance(clean, str) else json.dumps(clean, ensure_ascii=False), what,
               body.get('title', ''), voice or '(none)', drafts.article_facts_text(body), prompt(domain)))
    before = json.loads(json.dumps(body))
    gaps_before = _gaps(old)
    held = []
    for attempt in range(2):
        extra = ('' if not held else '\n\nYOUR LAST TRY WAS HELD BACK: these sentences said things the store doesn\'t state:\n'
                 + '\n'.join('- ' + h for h in held) + '\nStay closer to the original wording and facts; only make the change asked for.')
        res = llm.json_call(PART_RULES, text + extra, 'article_part', schema, usage=usage, attempts=3)
        body = json.loads(json.dumps(before))
        new = res['part']
        if isinstance(old, str) and (not new.strip() or new.strip().lower() == label(path).lower()
                                     or len(new) < 0.15 * len(_ungap(old))):
            raise ValueError('The agent sent back something that isn\'t a rewrite of this part, so nothing changed. Try again.')
        if isinstance(old, dict) and old.get('checked'):
            new = dict(new, checked=True) if isinstance(new, dict) else new
        content_review._set(body, keys, new)
        drafts.article_checks(body, domain, usage=usage, verified=factcheck.verified_sentences(before, 'article', with_gaps=True))
        try:
            changed = content_review._get(body, keys)
        except (KeyError, IndexError, TypeError):
            changed = None
        if _gaps(changed) <= gaps_before:
            break
        held = [c['sentence'] for c in (body.get('fact_check') or {}).get('claims', [])][:5]
    else:
        # A quick change must never leave the owner with new questions to answer: keep the part as it was.
        raise ValueError('The agent couldn\'t make that change without saying things your store doesn\'t state, '
                         'so the part is unchanged. Try saying exactly what to change.')
    note = '%s: %s' % (label(path), (quick and quick.capitalize() or instruction)[:80])
    _save(draft_id, body, prev, row, note)
    lesson = add_lesson(domain, res['lesson'], 'request', example=ask) if remember and res.get('lesson') else None
    return res.get('reply', ''), lesson


def _gaps(part):
    return json.dumps(part, ensure_ascii=False).count('[ask merchant:') if part is not None else 0


def remove_part(domain, draft_id, path):
    """Remove a part outright (no AI). Returns a short reply."""
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    keys = _parse(path)
    if keys and keys[0] == 'card' and len(keys) == 2:                     # a product card: unlink it from its section
        for s in body.get('sections') or []:
            if s.get('product_id') == keys[1]:
                s['product_id'] = ''
    else:
        try:
            parent = content_review._get(body, keys[:-1]) if len(keys) > 1 else body
            if keys[0] == 'sections' and len(keys) == 2:
                _remove_section(body, keys[1])
            elif isinstance(parent, list):
                del parent[keys[-1]]
            elif keys[-1] == 'title':
                raise ValueError('An article needs a title. Ask for a different one instead.')
            elif keys[-1] in ('dek', 'text', 'heading', 'answer', 'category'):
                parent[keys[-1]] = ''
            elif keys == ('closing',):
                body['closing'] = dict(heading='', text='', product_id='')
            elif keys == ('glance',):
                body['glance'] = []
            else:
                raise ValueError('That part can\'t be removed on its own.')
        except (KeyError, IndexError, TypeError):
            raise ValueError('That part has changed since you opened it. Reload and try again.')
    _save(draft_id, body, prev, row, 'Removed: %s' % label(path))
    return 'Removed.'


def set_photo(domain, draft_id, slot, url):
    """Use another of the store's own photos for the cover or a section."""
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    if url not in store_photos(domain, body):
        raise ValueError('Pick one of your store\'s photos.')
    if slot != 'cover' and not (slot.startswith('s.') and slot[2:].isdigit()):
        raise ValueError('Pick a photo in the article.')
    o = body.setdefault('photo_overrides', {})
    o[slot] = url
    _save(draft_id, body, prev, row, 'Changed a photo')
    return 'Photo changed.'


def store_photos(domain, body=None):
    """The owner's uploads, then the store's Instagram photos (social_photos.py), then every photo of the store's
    products (the article's own first), for the picker."""
    import catalog_facts
    import social_photos
    out = uploaded_photos(domain)
    out += [u for u in social_photos.photos(domain) if u not in out]
    for p in (body or {}).get('products') or []:
        out += [u for u in p.get('images') or [] if u not in out]
    for r in catalog_facts.get(domain):
        out += [u for u in (r.get('images') or [r.get('image')]) if u and u not in out]
    return out[:120]


def _save(draft_id, body, prev, row, note):
    import content_review
    body['change_note'] = note
    content_review.rebuild(body, row['draft_type'])
    content_review.save_version(draft_id, body, prev, author='merchant', title=body.get('title'))


def history(draft_id, limit=12):
    """[(version id, when, who, note)] newest first."""
    import db
    out = []
    for v in db.all_('SELECT id, author, created_at, body FROM content_draft_versions WHERE draft_id=? ORDER BY id DESC LIMIT ?',
                     (draft_id, limit)):
        try:
            b = json.loads(v['body'] or '{}')
        except ValueError:
            b = {}
        note = b.get('change_note') or ('Written by the agent' if v['author'] == 'agent' else 'You edited the text')
        out.append((v['id'], v['created_at'], v['author'], note))
    return out


def restore(domain, draft_id, version_id=None):
    """Bring back an earlier version as a new one (so nothing is ever lost). No version_id = undo the last change."""
    import content_review
    import db
    row, body, prev = content_review.load(draft_id, domain)
    if not row:
        raise ValueError('Draft not found.')
    vs = db.all_('SELECT id, body, created_at FROM content_draft_versions WHERE draft_id=? ORDER BY id DESC', (draft_id,))
    target = vs[1] if version_id is None and len(vs) > 1 else next((v for v in vs if v['id'] == version_id), None)
    if not target or target['id'] == vs[0]['id']:
        raise ValueError('Nothing to undo.' if version_id is None else 'That version is already the current one.')
    old = json.loads(target['body'] or '{}')
    old['change_note'] = 'Undid the last change' if version_id is None else 'Restored an earlier version'
    content_review.rebuild(old, row['draft_type'])
    content_review.save_version(draft_id, old, prev, author='merchant', title=old.get('title'))
    return old['change_note'] + '.'


# ---- 6-10 and uploads (20 Oct 2026) --------------------------------------------------------------------

def set_text(domain, draft_id, path, text):
    """The owner typed the new wording themselves. Their words aren't fact-checked (they're the store's), and the
    agent learns from the edit in the background, like any hand edit."""
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    keys = _parse(path)
    try:
        old = content_review._get(body, keys)
    except (KeyError, IndexError, TypeError):
        raise ValueError('That part has changed since you opened it. Reload and try again.')
    if not isinstance(old, str):
        raise ValueError('Type into one piece of text at a time.')
    import re as _re
    text = _re.sub(r'[ \t]+', ' ', (text or '').replace('\r', '')).strip()
    if not text and keys[-1] == 'title':
        raise ValueError('An article needs a title.')
    before = json.loads(json.dumps(body))
    content_review._set(body, keys, text[:4000])
    body['edited_at'] = time.time()
    _save(draft_id, body, prev, row, 'You typed: %s' % label(path))
    learn_in_background(domain, before, body)
    return 'Saved.'


def _renumber(body):
    """Keep "Step 1, Step 2..." in order after sections move, arrive or go."""
    import re as _re
    n = 0
    for sec in body.get('sections') or []:
        m = _re.match(r'^(\s*step\s*)\d+(.*)$', sec.get('step_label') or '', _re.I)
        if m:
            n += 1
            sec['step_label'] = '%s%d%s' % (m.group(1), n, m.group(2))


def _reindex(body, mapping):
    """Sections moved or removed: keep tables and chosen photos with the section they belonged to.
    mapping: {old index: new index or None}."""
    for t in body.get('tables') or []:
        a = int(t.get('after_section', -1))
        if a in mapping:
            t['after_section'] = mapping[a] if mapping[a] is not None else max(-1, a - 1)
    o = body.get('photo_overrides') or {}
    new = {k: v for k, v in o.items() if not k.startswith('s.')}
    for k, v in o.items():
        if k.startswith('s.') and k[2:].isdigit():
            i = int(k[2:])
            j = mapping.get(i, i)
            if j is not None:
                new['s.%d' % j] = v
    if o:
        body['photo_overrides'] = new
    _renumber(body)


def move_section(domain, draft_id, index, direction):
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    secs = body.get('sections') or []
    j = index + (1 if direction == 'down' else -1)
    if not row or not 0 <= index < len(secs) or not 0 <= j < len(secs):
        raise ValueError('That section can\'t move further.')
    secs[index], secs[j] = secs[j], secs[index]
    _reindex(body, {index: j, j: index})
    _save(draft_id, body, prev, row, 'Moved section %d %s' % (index + 1, direction))
    return 'Moved.'


def _remove_section(body, index):
    n = len(body.get('sections') or [])
    del body['sections'][index]
    _reindex(body, {i: (None if i == index else i - 1 if i > index else i) for i in range(n)})


ADD_RULES = """You are the writer of an online store's blog article. The owner asked for a NEW SECTION about a topic, to go after a given section. Write that one section in the article's style.

Rules: the heading is a buyer's question (or "Step N: ..." style only if the neighbouring sections use steps; then fill step_label). 2-3 short paragraphs; the first sentence answers the heading directly. Facts about a product only from PRODUCT FACTS; general category knowledge is fine, carefully worded; no numbers that aren't stated, no medical claims, no other brands. product_id: a product (P1, P2...) only if this section genuinely recommends it, else "". photo: false unless it's a product section. reply: one short sentence to the owner."""


def add_section(domain, draft_id, after, topic, usage=None):
    import content_review
    import drafts
    import factcheck
    import llm
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    if not (topic or '').strip():
        raise ValueError('Say what the new section should be about.')
    secs = body.get('sections') or []
    after = max(-1, min(int(after), len(secs) - 1))
    schema = {"type": "object", "additionalProperties": False, "required": ["section", "reply"],
              "properties": {"section": drafts.ARTICLE_SCHEMA['properties']['sections']['items'], "reply": {"type": "string"}}}
    around = [s.get('heading') for s in secs]
    text = ('TOPIC FOR THE NEW SECTION: %s\nIT GOES AFTER: %s\nTHE ARTICLE: %s\nALL HEADINGS: %s\n\nPRODUCT FACTS:\n%s%s'
            % (topic.strip()[:500], around[after] if after >= 0 else '(the start)', body.get('title', ''),
               ' | '.join(around), drafts.article_facts_text(body), prompt(domain)))
    res = llm.json_call(ADD_RULES, text, 'article_add_section', schema, usage=usage, attempts=3)
    before = json.loads(json.dumps(body))
    n = len(secs)
    secs.insert(after + 1, res['section'])
    _reindex(body, {i: (i + 1 if i > after else i) for i in range(n)})
    drafts.article_checks(body, domain, usage=usage, verified=factcheck.verified_sentences(before, 'article', with_gaps=True))
    _save(draft_id, body, prev, row, 'Added a section: %s' % topic.strip()[:60])
    return res.get('reply', 'Added.')


def catalog_choices(domain):
    """[{handle, title, image}] the store's products, for swapping a product card."""
    import catalog_facts
    return [dict(handle=r['handle'], title=r['title'], image=r.get('image') or '') for r in catalog_facts.get(domain)][:80]


def swap_product(domain, draft_id, old_pid, handle):
    """Show another of the store's products in a card. Its card line is the first sentence its own page states,
    so nothing new needs checking."""
    import catalog_facts
    import content_review
    import drafts
    import re as _re
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ValueError('Only AEO articles can be changed this way.')
    rec = next((r for r in catalog_facts.get(domain) if r['handle'] == handle), None)
    if not rec:
        raise ValueError('Pick one of your products.')
    prods = body.setdefault('products', [])
    idx = next((i for i, p in enumerate(prods) if p['handle'] == handle), None)
    if idx is None:
        prods.append(drafts._slim(domain, rec))
        idx = len(prods) - 1
    new_pid = 'P%d' % (idx + 1)
    for s in body.get('sections') or []:
        if s.get('product_id') == old_pid:
            s['product_id'] = new_pid
    if not any(k.get('id') == new_pid for k in body.get('picks') or []):
        desc = ' '.join(rec.get('description') or [])
        first = (_re.split(r'(?<=[.!?])\s+', desc.strip()) or [''])[0][:220]
        body.setdefault('picks', []).append(dict(id=new_pid, text=first, labels=[], facts_used=[first], checked=True))
    _save(draft_id, body, prev, row, 'Swapped a product card to %s' % rec['title'])
    return 'Swapped.'


def look_quick(domain, form):
    """The look controls above the preview: fonts, capitals, accent. They apply to all the store's articles."""
    import brand_style
    raw = brand_style.learn(domain)
    fonts = brand_style.families(raw)
    colours = set(raw['colors'].values())
    for role in ('heading', 'body'):
        v = form.get(role + '_font')
        if v is not None:
            set_override(domain, role + '_font', v if v in fonts and v != raw['fonts'][role]['family'] else '')
    if form.get('heading_upper') in ('0', '1'):
        up = form['heading_upper'] == '1'
        set_override(domain, 'heading_upper', up if up != bool(raw.get('heading_upper')) else '')
    v = (form.get('accent') or '').lower()
    if v:
        set_override(domain, 'accent', v if v in colours and v != raw['colors']['accent'] else '')
    return 'Look saved.'


# ---- the owner's own photos ---------------------------------------------------------------------------------
# Uploaded from their computer in the photo picker. Resized in the browser (max 2000 px, JPEG), kept in the database
# (so backups include them) and served at a random public link, which the article and Shopify (the cover) can load.

MAX_PHOTO = 4_000_000


def _media_init():
    import db
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS content_media (token TEXT PRIMARY KEY, store_domain TEXT NOT NULL, '
                  'mime TEXT, data BLOB, created_at REAL)')


def media_url(token):
    import config
    import os
    base = (config.env('PRODUKTO_BASE_URL') or os.environ.get('PRODUKTO_BASE_URL') or
            'http://localhost:%d' % config.PORT).rstrip('/')
    return '%s/content/media/%s.jpg' % (base, token)


def save_upload(domain, data_url):
    import base64
    import db
    import re as _re
    import secrets
    m = _re.match(r'data:(image/(?:jpeg|png|webp));base64,(.+)$', data_url or '', _re.S)
    if not m:
        raise ValueError('Choose a JPG, PNG or WebP photo.')
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except ValueError:
        raise ValueError('That photo couldn\'t be read.')
    if len(raw) > MAX_PHOTO:
        raise ValueError('That photo is too large (4 MB at most).')
    sig = raw[:12]
    if not (sig.startswith(b'\xff\xd8') or sig.startswith(b'\x89PNG') or (sig[:4] == b'RIFF' and sig[8:12] == b'WEBP')):
        raise ValueError('That file isn\'t a photo.')
    _media_init()
    token = secrets.token_urlsafe(18)
    db.write('INSERT INTO content_media (token, store_domain, mime, data, created_at) VALUES (?,?,?,?,?)',
             (token, domain, m.group(1), raw, time.time()))   # named: later columns (shopify, source) exist
    return media_url(token)


def media(token):
    """(mime, bytes) for GET /content/media/<token>.jpg, or None."""
    import db
    _media_init()
    row = db.one('SELECT mime, data FROM content_media WHERE token=?', (token,))
    return (row['mime'], row['data']) if row else None


def uploaded_photos(domain):
    import db
    try:
        _media_init()
        import social_photos
        social_photos.init()
        return [media_url(r['token']) for r in db.all_(
            "SELECT token FROM content_media WHERE store_domain=? AND (source IS NULL OR source='upload') "
            "ORDER BY created_at DESC LIMIT 40", (domain,))]
    except Exception:                                                       # noqa: BLE001
        return []


def upload_photo(domain, draft_id, slot, data_url):
    url = save_upload(domain, data_url)
    return set_photo(domain, draft_id, slot, url)
