"""The draft view: before/after, gaps to fill, edit in place, approve or reject.

Day 10 of mvp/content-agent/PLAN.md. Opened from an Inbox card
(/content?view=draft&id=N).

  * Before / after: what the store's page says now beside what the draft would
    make it say. Comparisons and guides are new pages, so "before" says so.
  * Gaps: every "[ask merchant: ...]" the fact check left. The merchant answers
    in a few words (their answer becomes a stated fact) or leaves the sentence
    out. A draft with gaps can't be approved (content_agent.act refuses).
  * Edit: every piece of text as a plain form field, so nobody edits HTML.
    The page HTML and FAQ markup are rebuilt from the fields on save.

Every save is a new row in content_draft_versions (author 'merchant'), so the
agent's original is never lost. Nothing here calls an AI model or touches the store.
"""
import json
import re
import time
import urllib.parse
from html import escape as E

import db
import drafts
import storetime

GAP = re.compile(r'\[ask merchant: (.*?)\]')
# Body keys that hold text the merchant reads and may edit. Everything else
# (sources, fact-check report, product records) is bookkeeping.
_SKIP = {'html', 'open_questions', 'fact_check', 'current', 'product', 'products', 'names', 'competitors_used',
         'facts_used', 'removed', 'removed_specs', 'removed_faqs', 'removed_picks', 'removed_paragraphs',
         'cost_cents', 'answers', 'changes', 'title_reason', 'columns', 'id', 'review', 'title_reverted',
         # designed articles (19 Oct 2026): bookkeeping and layout, not text
         'layout', 'store', 'cover', 'competitor_brands', 'playbook_sources', 'theme_title', 'product_id',
         'requests', 'checked', 'images', 'image', 'price', 'url', 'handle', 'edited_at', 'shopify_draft', 'questions', 'author'}
_HTML_KEYS = {'description_html'}
_ALLOWED_TAGS = ('p', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'br', 'h2', 'h3')


# ---- reading and writing the latest version ---------------------------------

def load(draft_id, domain):
    row = db.one('SELECT * FROM content_drafts WHERE id=? AND store_domain=?', (draft_id, domain))
    if not row:
        return None, None, None
    v = db.one('SELECT * FROM content_draft_versions WHERE draft_id=? ORDER BY id DESC LIMIT 1', (draft_id,))
    return row, json.loads(v['body'] or '{}') if v else {}, v


def save_version(draft_id, body, prev, author='merchant', title=None):
    now = time.time()
    with db.conn() as c:
        c.execute('INSERT INTO content_draft_versions (draft_id, body, author, sources, open_facts, created_at) '
                  'VALUES (?,?,?,?,?,?)', (draft_id, json.dumps(body), author, prev['sources'] if prev else '[]',
                                           json.dumps(body.get('open_questions') or []), now))
        if title:
            c.execute('UPDATE content_drafts SET title=?, updated_at=? WHERE id=?', (title, now, draft_id))
        else:
            c.execute('UPDATE content_drafts SET updated_at=? WHERE id=?', (now, draft_id))


# ---- text fields --------------------------------------------------------------

def _walk(node, path=()):
    """(path, key, text) for every editable string in the body."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in _SKIP:
                yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))
    elif isinstance(node, str) and path:
        key = next((p for p in reversed(path) if isinstance(p, str)), '')
        yield path, key, node


def _get(body, path):
    for p in path:
        body = body[p]
    return body


def _set(body, path, value):
    for p in path[:-1]:
        body = body[p]
    body[path[-1]] = value


def gaps(body):
    """Distinct gap questions, in reading order."""
    out = []
    for _, _, text in _walk(body):
        for q in GAP.findall(text):
            import html
            q = html.unescape(q)
            if q not in out:
                out.append(q)
    return out


def _tidy(text):
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return re.sub(r'\s+([.,;:!?])', r'\1', re.sub(r'(<p>|<li>)\s+', r'\1', text)).strip()


def fill(body, answers):
    """answers: {gap question: answer or '' to leave the sentence out}. Changes body in place."""
    import html
    for path, key, text in list(_walk(body)):
        new = text
        for q, a in answers.items():
            for written in {q, html.escape(q, quote=False)}:
                new = new.replace('[ask merchant: %s]' % written,
                                  html.escape(a, quote=False) if key in _HTML_KEYS else a)
        if new != text:
            _set(body, path, _tidy(new))
    body.setdefault('answers', []).extend(dict(question=q, answer=a, at=time.time()) for q, a in answers.items())
    _drop_empty(body)


def _drop_empty(body):
    """A FAQ, paragraph or pick whose whole text was left out goes away."""
    if 'faqs' in body:
        body['faqs'] = [f for f in body['faqs'] if f['answer'].strip()]
    for s in body.get('sections', []):
        s['paragraphs'] = [p for p in s['paragraphs'] if p.strip()]
    if 'picks' in body:
        body['picks'] = [k for k in body['picks'] if k['text'].strip()]
    if 'summary' in body:
        body['summary'] = [k for k in body['summary'] if k['text'].strip()]
    if 'description_html' in body:
        body['description_html'] = re.sub(r'<(p|li)>\s*</\1>', '', body['description_html'])


def clean_html(text):
    """Keep only simple formatting tags, with no attributes, from the description editor."""
    def tag(m):
        name = m.group(2).lower()
        return '<%s%s>' % (m.group(1), name) if name in _ALLOWED_TAGS else ''
    text = re.sub(r'<(script|style)\b.*?</\1\s*>', '', text or '', flags=re.I | re.S)
    text = re.sub(r'<(/?)([a-zA-Z0-9]+)\b[^>]*>', tag, text)
    return text.replace('<div>', '').replace('</div>', '')


def fix_html(body):
    """A product-page fix as it would read on the page."""
    specs = ''.join('<tr><th>%s</th><td>%s</td></tr>' % (E(r['label']), E(r['value'])) for r in body.get('spec_table', []))
    return '%s%s' % (body.get('description_html', ''), '<table class="cr-spec">%s</table>' % specs if specs else '')


def rebuild(body, draft_type, domain=None):
    """Page HTML from the fields, so FAQ markup and tables always match the text."""
    if body.get('layout') == 'article':
        import article_render
        import brand_style
        domain = domain or body.get('store', '')
        products = body.get('products') or []
        ids = ['P%d' % (i + 1) for i in range(len(products))]
        body['picks'] = [k for k in body.get('picks', []) if k.get('id') in ids]
        body['html'], body['cover'] = article_render.render(
            body, products, brand_style.get(domain), brand=body.get('author') or drafts._brand_name(dict(store=domain)),
            symbol=drafts._symbol(domain), theme_title=bool(body.get('theme_title')))
        return body
    if draft_type == 'faq':
        body['html'] = drafts.faq_html(body['faqs'])
    elif draft_type == 'comparison':
        body['html'] = drafts.comparison_html(body, body.get('names', {}))
    elif draft_type == 'guide':
        products = body.get('products', [])
        body['picks'] = [k for k in body.get('picks', []) if k['id'] in ['P%d' % (i + 1) for i in range(len(products))]]
        body['html'] = drafts.guide_html(body, products)
    elif draft_type == 'product_fix':
        body['html'] = fix_html(body)
    return body


def _label(path, body):
    """A readable label for one form field."""
    names = body.get('names', {})
    p = list(path)
    if p == ['title']:
        return 'Title'
    if p == ['description_html']:
        return 'Description'
    if p == ['intro']:
        return 'Introduction'
    if body.get('layout') == 'article':
        lab = _article_label(p, body)
        if lab:
            return lab
    if p[0] == 'spec_table':
        return 'Spec %d: %s' % (p[1] + 1, 'name' if p[2] == 'label' else 'value')
    if p[0] == 'faqs':
        return 'Question %d' % (p[1] + 1) if p[2] == 'question' else 'Answer %d' % (p[1] + 1)
    if p[0] == 'rows':
        row = body['rows'][p[1]]
        if p[2] == 'label':
            return 'Row %d name' % (p[1] + 1)
        return '%s: %s' % (row['label'], names.get(row['cells'][p[3]]['id'], ''))
    if p[0] == 'summary':
        return 'Who it suits: %s' % names.get(body['summary'][p[1]]['id'], '')
    if p[0] == 'sections':
        return 'Section %d heading' % (p[1] + 1) if p[2] == 'heading' else 'Section %d, paragraph %d' % (p[1] + 1, p[3] + 1)
    if p[0] == 'picks':
        title = next((x['title'] for i, x in enumerate(body.get('products', []))
                      if 'P%d' % (i + 1) == body['picks'][p[1]]['id']), '')
        return 'Pick %d (%s): %s' % (p[1] + 1, title, 'for whom' if p[2] == 'for_whom' else 'text')
    return ' '.join(str(x) for x in p)


def _article_label(p, body):
    names = {('P%d' % (i + 1)): x['title'] for i, x in enumerate(body.get('products') or [])}
    if p == ['dek']:
        return 'Intro under the title'
    if p == ['category']:
        return 'Blog category'
    if p == ['faq_heading']:
        return 'FAQ heading'
    if p[0] == 'glance':
        return 'At a glance %d: %s' % (p[1] + 1, 'label' if p[2] == 'label' else 'text')
    if p[0] == 'sections':
        if p[2] == 'step_label':
            return 'Section %d step label' % (p[1] + 1)
        return 'Section %d heading' % (p[1] + 1) if p[2] == 'heading' else 'Section %d, paragraph %d' % (p[1] + 1, p[3] + 1)
    if p[0] == 'picks':
        name = names.get(body['picks'][p[1]].get('id'), '')
        return 'Product card (%s): %s' % (name, 'why' if p[2] == 'text' else 'label %d' % (p[3] + 1))
    if p[0] == 'tables':
        t = body['tables'][p[1]]
        if p[2] == 'heading':
            return 'Table heading'
        if p[2] == 'note':
            return 'Table note'
        if p[2] == 'columns':
            return 'Table column %d' % (p[3] + 1)
        return 'Table row %d, cell %d' % (p[3] + 1, p[5] + 1)
    if p[0] == 'faqs':
        return 'Question %d' % (p[1] + 1) if p[2] == 'question' else 'Answer %d' % (p[1] + 1)
    if p[0] == 'closing':
        return 'Closing banner: %s' % p[1]
    return ''


def _field_name(path):
    return 'f.' + '.'.join(str(p) for p in path)


def _path_of(name, body):
    out = []
    for part in name[2:].split('.'):
        out.append(int(part) if part.isdigit() else part)
    try:
        _get(body, out)
    except (KeyError, IndexError, TypeError):
        return None
    return tuple(out)


def edit(body, form, draft_type):
    """Apply the edit form. Blank fields keep their old text (browsers send them, but parse_qsl drops them)."""
    changed = False
    for name, value in form.items():
        if not name.startswith('f.'):
            continue
        path = _path_of(name, body)
        if not path or not isinstance(_get(body, path), str) or path[0] in _SKIP:
            continue
        key = next((p for p in reversed(path) if isinstance(p, str)), '')
        value = clean_html(value) if key in _HTML_KEYS else value.strip()
        if value != _get(body, path):
            _set(body, path, value)
            changed = True
    if changed:
        body['edited_at'] = time.time()
    return changed


# ---- page ---------------------------------------------------------------------

def _before(body, draft_type):
    current = body.get('current')
    product = body.get('product') or {}
    if draft_type == 'product_fix' and current:
        return '<h3 class="cr-ptitle">%s</h3>%s' % (E(current['title']), ''.join(
            '<p>%s</p>' % E(t) for t in current.get('description') or []) or '<p class="cr-muted">No description.</p>')
    if draft_type == 'faq':
        return ('<p class="cr-muted">%s has no questions-and-answers section yet. The FAQ is added below the '
                'product description.</p>' % E(product.get('title', 'This product')))
    return '<p class="cr-muted">A new page. Nothing on your store says this yet.</p>'


def _where(body, draft_type):
    product = body.get('product') or {}
    if draft_type in ('product_fix', 'faq') and product.get('url'):
        what = 'title, description and spec table' if draft_type == 'product_fix' else 'a new FAQ section'
        return 'Goes on <a href="%s" target="_blank" rel="noopener">%s</a>: %s.' % (
            E(product['url']), E(product.get('title', '')), what)
    if draft_type == 'comparison':
        return 'A new comparison page on your store, linking to the products it compares.'
    if draft_type == 'guide':
        return 'A new article on your store\'s blog, linking to the products it recommends.'
    return ''


def _gap_form(domain, did, body, back=None):
    qs = gaps(body)
    if not qs:
        return ''
    rows = ''.join(
        '<div class="cr-gap"><label for="g%d">%s</label><input id="g%d" name="a.%d" placeholder="Your answer, in a few words">'
        '<label class="cr-skip"><input type="checkbox" name="skip.%d" value="1"> Leave this sentence out</label>'
        '<input type="hidden" name="q.%d" value="%s"></div>' % (i, E(q), i, i, i, i, E(q))
        for i, q in enumerate(qs))
    return ('<section class="cr-box cr-gaps"><h2>%d gap%s to fill before you can approve</h2>'
            '<p class="cr-muted">The agent only writes what your store already states. These sentences need a fact '
            'it couldn\'t find. Answer, or leave the sentence out.</p>'
            '<form method="post" action="/content"><input type="hidden" name="d" value="%s">'
            '<input type="hidden" name="id" value="%d"><input type="hidden" name="action" value="fill">%s%s'
            '<button class="ca-btn ca-primary">Save answers</button></form></section>') % (
        len(qs), '' if len(qs) == 1 else 's', E(domain), did,
        ('<input type="hidden" name="back" value="%s">' % E(back)) if back else '', rows)


def _edit_form(domain, did, body):
    fields = []
    for path, key, text in _walk(body):
        name = _field_name(path)
        label = E(_label(path, body))
        if key in _HTML_KEYS:
            fields.append('<div class="cr-field"><label>%s</label><div class="cr-rich" contenteditable="true" '
                          'data-for="%s">%s</div><input type="hidden" name="%s" value="%s"></div>'
                          % (label, E(name), text, E(name), E(text)))
        elif len(text) > 80 or key in ('answer', 'intro', 'text') or path[0] == 'sections' and key == 'paragraphs':
            fields.append('<div class="cr-field"><label for="%s">%s</label><textarea id="%s" name="%s" rows="%d">%s'
                          '</textarea></div>' % (E(name), label, E(name), E(name), min(8, 2 + len(text) // 90), E(text)))
        else:
            fields.append('<div class="cr-field"><label for="%s">%s</label><input id="%s" name="%s" value="%s"></div>'
                          % (E(name), label, E(name), E(name), E(text)))
    return ('<section class="cr-box"><details class="cr-edit"><summary>Edit the text</summary>'
            '<form method="post" action="/content" class="cr-form"><input type="hidden" name="d" value="%s">'
            '<input type="hidden" name="id" value="%d"><input type="hidden" name="action" value="save">%s'
            '<button class="ca-btn ca-primary">Save changes</button></form></details></section>'
            '<script>document.querySelectorAll(".cr-form").forEach(function(f){f.addEventListener("submit",function(){'
            'f.querySelectorAll(".cr-rich").forEach(function(r){f.querySelector("input[name=\'"+r.dataset.for+"\']")'
            '.value=r.innerHTML;});});});</script>') % (E(domain), did, ''.join(fields))


def _questions(body):
    answered = {a['question'] for a in body.get('answers', [])}
    gap_qs = set(gaps(body))
    rest = [q for q in body.get('open_questions') or []
            if q['question'] not in answered and q['question'] not in gap_qs
            and not any(q['question'] in g or g in q['question'] for g in gap_qs)]
    if not rest:
        return ''
    return ('<section class="cr-box"><h2>Facts that would make this page stronger</h2><p class="cr-muted">Buyers '
            'ask about these, but your store doesn\'t say. Add them to the product in Shopify and the agent can use '
            'them next time.</p><ul class="cr-qs">%s</ul></section>') % ''.join(
        '<li><strong>%s</strong>%s</li>' % (E(q['question']), (' <span class="cr-muted">%s</span>' % E(q['why'])) if q.get('why') else '')
        for q in rest)


def page(domain, q, tabs, types):
    import content_agent
    try:
        did = int(q.get('id', ''))
    except ValueError:
        return None
    row, body, _ = load(did, domain)
    if not row:
        return None
    rebuild(body, row['draft_type'])
    tz = storetime.zone(domain)
    status = {'draft': 'New', 'approved': 'Approved', 'scheduled': 'Scheduled', 'published': 'Live',
              'rejected': 'Rejected'}.get(row['status'], row['status'])
    n_gaps = len(gaps(body))
    back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))

    def button(st, label, cls='', disabled=''):
        return ('<form method="post" action="/content"><input type="hidden" name="d" value="%s"><input type="hidden" '
                'name="id" value="%d"><input type="hidden" name="status" value="%s"><input type="hidden" name="back" '
                'value="%s"><button class="ca-btn %s"%s>%s</button></form>') % (E(domain), did, st, E(back), cls,
                                                                                 disabled, label)
    import content_agent
    if row['status'] == 'draft':
        actions = button('approved', 'Approve', 'ca-primary',
                         ' disabled title="Fill the gaps first"' if n_gaps else '') + button('rejected', 'Reject')
    elif row['status'] == 'published':
        actions = content_agent.publish_buttons(domain, row, back)
    else:
        actions = content_agent.publish_buttons(domain, row, back) + button('draft', 'Move back to New')
    edited = (' · edited %s' % E(storetime.label(body['edited_at'], tz))) if body.get('edited_at') else ''
    fc = body.get('fact_check') or {}
    held = len(fc.get('numbers', [])) + len(fc.get('claims', []))
    checked = ('Fact check: %d sentence%s held back for you to confirm.' % (held, '' if held == 1 else 's')) if held \
        else ('Fact check: every sentence matched what your store states.' if fc else '')
    title = body.get('title') if row['draft_type'] in ('comparison', 'guide') else None
    head = ('<a class="cr-back" href="%s">&#8249; Drafts</a><div class="cr-top"><div><div class="ca-head">'
            '<span class="ca-type">%s</span><span class="cr-status cr-%s">%s</span></div><h2 class="cr-title">%s</h2>'
            '<p class="ca-meta">%s · drafted %s%s</p></div><div class="ca-actions">%s</div></div>') % (
        E('/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox'))), E(types.get(row['draft_type'], row['draft_type'])),
        E(row['status']), E(status), E(title or row['title'] or 'Untitled'), _where(body, row['draft_type']),
        E(storetime.label(row['created_at'], tz)), edited, actions)
    after_title = ('<h3 class="cr-ptitle">%s</h3>' % E(body['title'])) if body.get('title') else ''
    compare = ('<div class="cr-ba"><section class="cr-col"><h2>Now on your store</h2>%s</section>'
               '<section class="cr-col cr-after"><h2>With this draft</h2><div class="cr-doc">%s%s</div>%s</section></div>') % (
        _before(body, row['draft_type']), after_title, body.get('html', ''),
        '<p class="cr-check">%s</p>' % E(checked) if checked else '')
    if row['draft_type'] in ('product_fix', 'faq') and body.get('product'):
        compare = fix_preview(domain, did, row, body) + ('<p class="cr-check">%s</p>' % E(checked) if checked else '') + \
            history_box(domain, did)
    if has_preview(row, body):
        src = body.get('playbook_sources') or []
        learned = ('<p class="cr-muted">Built the way %s write their articles, in your store\'s fonts and colours.</p>'
                   % E(', '.join(src[:3]))) if src else ''
        full = '<a class="ca-btn ca-primary" href="%s" target="_blank" rel="noopener">Open full-page preview</a>' % E(
            '/content/preview?' + urllib.parse.urlencode(dict(d=domain, id=did)))
        compare = ('<section class="cr-box cr-prev"><div class="cr-prevtop"><h2>Preview</h2><div class="ca-actions">%s%s</div></div>'
                   '%s%s<p class="cr-check">%s</p></section>'
                   % (full, _store_preview(domain, did, row, body, q), learned,
                      editor_toolbar(domain, did, body) + preview_frame(body, domain=domain, did=did) + editor(domain, did, body),
                      E(checked) if checked else '')) \
            + (_ask_form(domain, did, body) + history_box(domain, did) if body.get('layout') == 'article'
               else redesign_form(domain, did, row))
    err = ('<p class="cal-warn">%s</p>' % E(q['error'])) if q.get('error') else ''
    if row['status'] == 'published' and row['live_url']:
        err += '<p class="cs-batch">Live on your store since %s.</p>' % E(storetime.label(row['published_at'], tz))
    return head + err + _gap_form(domain, did, body) + compare + _review(body) + _questions(body) + \
        _edit_form(domain, did, body)


ARTICLE_KINDS = ('guide', 'comparison')


def fix_preview(domain, did, row, body, height=900):
    """A product fix or FAQ shown on the store's real product page, with Now / With this draft and the pencil."""
    import product_preview
    full = '/content/fix-preview?' + urllib.parse.urlencode(dict(d=domain, id=did))
    return ('<section class="cr-box cr-prev"><div class="cr-prevtop"><h2>Preview on your product page</h2><div class="ca-actions">'
            '<a class="ca-btn" href="%s" target="_blank" rel="noopener">Open full page</a></div></div>%s%s%s%s</section>') % (
        E(full), product_preview.toggle(domain, did), editor_toolbar(domain, did, body, kind='fix'),
        product_preview.frame(domain, did, height), editor(domain, did, body, kind='fix'))


def has_preview(row, body):
    """Every article and comparison page gets a preview in the store's look, old drafts included (Kelian, 19 Oct)."""
    return body.get('layout') == 'article' or row['draft_type'] in ARTICLE_KINDS


def styled(body, domain=''):
    """(html, cover) as the store would show it. Drafts written before the designed layout are wrapped in the
    store's fonts and colours, so they preview the same way."""
    import article_render
    import brand_style
    domain = domain or body.get('store', '')
    if body.get('layout') == 'article':
        return body.get('html', ''), body.get('cover', '')
    style = brand_style.get(domain)
    prods = body.get('products') or ([body['product']] if body.get('product') else [])
    cover = next((p.get('image') for p in prods if p.get('image')), '')
    return article_render.css(style) + '<div class="%s">%s</div>' % (article_render.FOLD, body.get('html', '')), cover


_FIT = ('var f=this;function h(){try{f.style.height=f.contentDocument.documentElement.scrollHeight+\'px\'}catch(e){}}h();'
        '[400,1200,2500].forEach(function(t){setTimeout(h,t)});if(window.pkEditorReady)window.pkEditorReady(f)')


def preview_frame(body, height=900, domain='', did=None):
    """The article as the store would show it, in its own fonts and colours, isolated in a frame. With a draft id
    it loads from /content/preview (embed=1, editable tags on) so the pencil can work on it and reload it."""
    import article_render
    import brand_style
    domain = domain or body.get('store', '')
    if did is not None:
        src = '/content/preview?' + urllib.parse.urlencode(dict(d=domain, id=did, embed=1))
        return ('<iframe class="cr-frame" id="pk-frame" title="Preview" src="%s" style="height:%dpx" onload="%s"></iframe>'
                % (E(src), height, _FIT))
    html, cover = styled(body, domain)
    page = article_render.preview_page(body.get('title', ''), html, cover, brand_style.get(domain))
    return ('<iframe class="cr-frame" title="Preview" srcdoc="%s" style="height:%dpx" onload="%s"></iframe>'
            % (E(page), height, _FIT))


def full_preview(q):
    """GET /content/preview?d=&id=: the article on its own page, full width, in the store's look (19 Oct 2026,
    Kelian: the merchant must see how the article will look). Signed-in owners and admins only."""
    import accounts
    import article_render
    import brand_style
    import content_agent
    domain = q.get('d', '')
    if not content_agent.enabled() or not accounts.can_see(domain):
        return 404, '<h1>Not found</h1>'
    try:
        row, body, _ = load(int(q.get('id', '')), domain)
    except ValueError:
        row = None
    if not row or not has_preview(row, body):
        return 404, '<h1>Not found</h1>'
    rebuild(body, row['draft_type'])
    if q.get('embed') and body.get('layout') == 'article':
        import drafts
        html, cover = article_render.render(body, body.get('products') or [], brand_style.get(domain),
                                            brand=body.get('author') or drafts._brand_name(dict(store=domain)),
                                            symbol=drafts._symbol(domain), marks=True)
        return 200, article_render.preview_page(body.get('title', ''), html, cover, brand_style.get(domain), marks=True)
    html, cover = styled(body, domain)
    page = article_render.preview_page(body.get('title', ''), html, cover, brand_style.get(domain))
    if q.get('embed'):
        return 200, page
    bar = ('<div style="position:sticky;top:0;z-index:5;background:#0b1b35;color:#fff;font:600 13px/1.4 -apple-system,'
           'Helvetica,Arial,sans-serif;padding:10px 16px;display:flex;justify-content:space-between;gap:12px">'
           '<span>Preview: how this article will look on your store. Not live.</span><a style="color:#fff" href="%s">'
           'Back to the draft</a></div>') % E('/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=row['id'])))
    return 200, page.replace('<body>', '<body>' + bar, 1)


def _store_preview(domain, did, row, body, q):
    """'Preview on your store': the article as a hidden draft in the merchant's own Shopify theme."""
    import shopify_connect
    if row['status'] == 'published' or not shopify_connect.configured() or not shopify_connect.connection(domain) \
            or shopify_connect.mismatch(domain):
        return ''
    sd = body.get('shopify_draft') or {}
    link = q.get('store_preview') or (shopify_connect.admin_article_url(sd['shop'], sd['id']) if sd.get('id') else '')
    open_ = ('<a class="ca-btn" href="%s" target="_blank" rel="noopener">Open the hidden draft in Shopify</a>' % E(link)) if link else ''
    return ('<div class="ca-actions">%s<form method="post" action="/content"><input type="hidden" name="d" value="%s">'
            '<input type="hidden" name="id" value="%d"><input type="hidden" name="action" value="store_preview">'
            '<button class="ca-btn" title="Puts it on your store as a hidden draft. Customers can\'t see it.">%s</button></form></div>') % (
        open_, E(domain), did, 'Update the hidden draft' if sd.get('id') else 'Preview on your store')


def redesign_form(domain, did, row, back=''):
    """Drafts written before the designed layout: one click writes them again in it (the old one is rejected)."""
    import config
    if not config.ARTICLES_V2 or row['status'] == 'published':
        return ''
    return ('<section class="cr-box cr-ask"><h2>Written in the old layout</h2><p class="cr-muted">This draft was written '
            'before articles got your store\'s design, photos and product cards. Rewrite it in the new design (about a '
            'minute); this version is set aside.</p><form method="post" action="/content" class="cr-askf">'
            '<input type="hidden" name="d" value="%s"><input type="hidden" name="id" value="%d">'
            '<input type="hidden" name="action" value="redesign">%s<button class="ca-btn ca-primary">Rewrite in the new design</button>'
            '</form><script>document.querySelectorAll(".cr-askf").forEach(function(f){f.addEventListener("submit",function(){'
            'var b=f.querySelector("button");b.disabled=true;b.textContent="Rewriting\u2026 (about a minute)";});});</script>'
            '</section>') % (E(domain), did, ('<input type="hidden" name="back" value="%s">' % E(back)) if back else '')


def redesign(domain, did):
    """Write an old-layout article again with the designed writer. Returns (new draft id, None) or (None, reason)."""
    import content_agent
    row = db.one('SELECT d.*, b.opportunity_kind k, b.opportunity_key key FROM content_drafts d LEFT JOIN content_briefs b '
                 'ON b.id=d.brief_id WHERE d.id=? AND d.store_domain=?', (did, domain))
    if not row or not row['k']:
        return None, 'The agent can\'t find what this draft was written for any more.'
    new, err = content_agent.draft_for(domain, row['k'], row['key'], only=(row['draft_type'],))
    if not new:
        return None, err
    now = time.time()
    with db.conn() as c:
        c.execute("UPDATE content_drafts SET planned_at=? WHERE id=? AND planned_at IS NULL", (row['planned_at'], new))
        c.execute("UPDATE content_drafts SET status='rejected', planned_at=NULL, updated_at=? WHERE id=?", (now, did))
    return new, None


# ---- the pencil: change any part of the preview (20 Oct 2026) ----------------------------------------------

def editor_toolbar(domain, did, body, kind='article'):
    """kind 'fix': a product page fix or FAQ (fix_learning.py): no Look button, it's the store's own page."""
    if kind == 'article' and body.get('layout') != 'article':
        return ''
    what = 'the product page' if kind == 'fix' else 'the article'
    out = ('<div class="pk-tools" data-d="%s" data-id="%d"><button type="button" class="pk-pencil" aria-pressed="false" '
            'title="Select any part of the article to change it"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 14.5V17h2.5'
            'l8.6-8.6-2.5-2.5L3 14.5zm13.7-7.6a.9.9 0 000-1.3l-1.3-1.3a.9.9 0 00-1.3 0l-1 1 2.5 2.5 1.1-.9z" fill="currentColor"/>'
            '</svg><span>Edit</span></button><button type="button" class="pk-undo" title="Undo the last change">&#8630; Undo</button>'
            '<button type="button" class="pk-lookb" title="Fonts, capitals and colour for all your articles">Look</button>'
            '<span class="pk-dev" role="group" aria-label="Preview size"><button type="button" data-dev="desktop" aria-pressed="true">Desktop</button>'
            '<button type="button" data-dev="phone" aria-pressed="false">Phone</button></span>'
            '<span class="pk-hint">Click any part of the article, or highlight words in it.</span></div>') % (E(domain), did)
    if kind == 'fix':
        out = re.sub(r'<button type="button" class="pk-lookb".*?</button>', '', out).replace('the article', what) \
            .replace('Click any part of the product page', 'Click any new part of the page')
    return out


def editor(domain, did, body, kind='article'):
    """The pop-up that edits the selected part: quick changes, your own words, remember-for-next-time; answering a
    gap in place; swapping a photo for another of the store's photos. Posts to /content with ajax=1, then reloads.
    kind 'fix': product page fixes and FAQs (fix_learning.py) use the same pop-up on the real product page."""
    if kind == 'fix':
        return '<script type="application/json" id="pk-data">%s</script><div class="pk-pop" hidden></div><script>%s</script>' % (
            json.dumps(dict(kind='fix', photos=[], ig=[], products=[], fonts=[], colours=[], look={}, sections=0)), _EDITOR_JS)
    if body.get('layout') != 'article':
        return ''
    import article_learning
    import brand_style
    raw = brand_style.learn(domain)
    cur = brand_style.get(domain)
    import social_photos
    data = dict(photos=article_learning.store_photos(domain, body), ig=social_photos.photos(domain), products=article_learning.catalog_choices(domain),
                fonts=brand_style.families(raw), colours=sorted(set(raw['colors'].values())),
                look=dict(heading=cur['fonts']['heading']['family'], body=cur['fonts']['body']['family'],
                          upper=bool(cur.get('heading_upper')), accent=cur['colors']['accent']),
                sections=len(body.get('sections') or []))
    return '<script type="application/json" id="pk-data">%s</script><div class="pk-pop" hidden></div><script>%s</script>' % (
        json.dumps(data).replace('</', '<\\/'), _EDITOR_JS)


_EDITOR_JS = r"""
(function(){
var tools=document.querySelector('.pk-tools'); if(!tools) return;
var D=tools.dataset.d, ID=tools.dataset.id, pop=document.querySelector('.pk-pop'), on=false, frame=null, sel=null, typing=null;
var DATA={photos:[],ig:[],products:[],fonts:[],colours:[],look:{},sections:0}; try{DATA=JSON.parse(document.getElementById('pk-data').textContent)}catch(e){}
var pencil=tools.querySelector('.pk-pencil');
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function head(t){return '<div class="pk-pop-h"><b>'+esc(t)+'</b><button type="button" class="pk-x" data-x aria-label="Close">&times;</button></div>'}
function post(data,busy){
  var b=new URLSearchParams(Object.assign({d:D,id:ID,ajax:'1'},data));
  pop.hidden=false; pop.innerHTML='<p class="pk-busy">'+(busy||'Saving…')+'</p>';
  return fetch('/content',{method:'POST',body:b,headers:{'Content-Type':'application/x-www-form-urlencoded'}}).then(function(r){return r.json()})
   .then(function(j){ if(j.ok){ try{sessionStorage.setItem('pk-edit',on?'1':'');sessionStorage.setItem('pk-dev',tools.dataset.dev||'');
       var fw=frame&&frame.contentWindow; sessionStorage.setItem('pk-scroll',JSON.stringify([fw?fw.scrollY:0,(document.scrollingElement||{}).scrollTop||0]))}catch(e){} location.reload() }
     else { pop.innerHTML='<p class="pk-err">'+esc(j.error||'That didn’t work.')+'</p><button type="button" class="ca-btn" data-x>Close</button>' } })
   .catch(function(){ pop.innerHTML='<p class="pk-err">No connection. Try again.</p><button type="button" class="ca-btn" data-x>Close</button>' });
}
function place(el){
  var inFrame=el.ownerDocument!==document, f=inFrame?frame.getBoundingClientRect():{top:0,left:0}, r=el.getBoundingClientRect();
  pop.hidden=false;
  var tall=inFrame&&r.height>240, y=(tall?r.top+16:r.bottom+8)+f.top, left=Math.max(12,Math.min(window.innerWidth-392,f.left+r.left+(tall?16:0)));
  var host=pop.offsetParent||document.body, hr=host.getBoundingClientRect();
  pop.style.top=(y-hr.top+(host===document.body?0:host.scrollTop))+'px'; pop.style.left=(left-hr.left)+'px';
  try{pop.scrollIntoView({block:'nearest',behavior:'smooth'})}catch(e){}
}
function stopTyping(){ if(typing){ typing.contentEditable='false'; typing=null } }
function closePop(){ stopTyping(); pop.hidden=true; pop.innerHTML=''; if(sel){sel.classList.remove('pk-sel');sel=null} }
function select(el){ if(sel) sel.classList.remove('pk-sel'); sel=el; if(el.classList) el.classList.add('pk-sel') }
var NAMES={title:'Title',dek:'Intro',category:'Category',glance:'At a glance box',closing:'Closing banner'};
var FIX=DATA.kind==='fix';
function name(p){var k=p.split('.');if(FIX){if(k[0]==='title')return 'Title';if(k[0]==='desc')return 'Paragraph';if(k[0]==='spec_table')return k.length>1?'Spec row':'Spec table';
  if(k[0]==='faqs')return k.length>2?'Answer':'Question and answer';return 'Part'}if(k[0]==='sections')return k.length===2?'Section '+(+k[1]+1):(k[2]==='heading'?'Heading':'Paragraph');
  if(k[0]==='glance')return k.length>1?'At a glance row':'At a glance box'; if(k[0]==='faqs')return k.length>2?'Answer':'Question and answer';
  if(k[0]==='tables')return 'Table'; if(k[0]==='picks')return 'Product card text'; if(k[0]==='card')return 'Product card'; return NAMES[k[0]]||'Part'}
function isText(p){var k=p.split('.');if(FIX)return p==='title'||k[0]==='desc'||(k[0]==='faqs'&&k.length===3);return p==='title'||p==='dek'||p==='category'||(k[0]==='sections'&&k.length>2)||(k[0]==='glance'&&k.length===3)||(k[0]==='faqs'&&k.length===3)||(k[0]==='picks'&&k.length===3)}
function rewriteBlock(path,removable){
  return '<div class="pk-quick"><button type="button" data-quick="shorter">Shorter</button><button type="button" data-quick="simpler">Simpler</button>'+
   '<button type="button" data-quick="voice">In our voice</button><button type="button" data-quick="list">Make it a list</button>'+
   (removable?'<button type="button" data-remove="'+esc(path)+'" class="pk-del">Remove</button>':'')+'</div>'+
   '<textarea name="instruction" rows="2" placeholder="Or say what to change…"></textarea>'+
   '<label class="pk-rem"><input type="checkbox" name="remember" checked> Remember this for future '+(FIX?'product pages':'articles')+'</label>'+
   '<div class="pk-row"><button class="ca-btn ca-primary">Apply</button>'+(isText(path)?'<button type="button" class="ca-btn" data-type="1">Type it yourself</button>':'')+
   '<button type="button" class="ca-btn" data-x>Cancel</button></div>';
}
function pick(el){
  stopTyping(); select(el);
  var path=el.dataset.pk, words=''; try{words=String(el.ownerDocument.getSelection()).trim()}catch(e){}
  if(words&&!el.textContent.includes(words)) words='';
  var outer=el.parentElement&&el.parentElement.closest('[data-pk]'), k=path.split('.');
  var html='<form><input type="hidden" name="path" value="'+esc(path)+'"><input type="hidden" name="quick" value=""><input type="hidden" name="selection" value="'+esc(words)+'">'+
   '<div class="pk-pop-h"><b>'+esc(name(path))+'</b>'+(outer?' <button type="button" class="pk-link" data-wider="1">Select the whole '+esc(name(outer.dataset.pk)).toLowerCase()+'</button>':'')+
   '<button type="button" class="pk-x" data-x aria-label="Close">&times;</button></div>'+(words?'<p class="pk-quote">“'+esc(words.slice(0,140))+'”</p>':'');
  if(k[0]==='card'){
    html+='<p class="pk-small">Show another of your products here:</p><div class="pk-prods">'+DATA.products.map(function(p){
      return '<button type="button" data-swap="'+esc(p.handle)+'" data-pid="'+esc(k[1])+'">'+(p.image?'<img src="'+esc(p.image+(p.image.indexOf('?')<0?'?':'&')+'width=120')+'" alt="">':'')+'<span>'+esc(p.title)+'</span></button>'}).join('')+'</div>'+
      '<div class="pk-row"><button type="button" class="ca-btn" data-remove="'+esc(path)+'">Remove the card</button><button type="button" class="ca-btn" data-x>Cancel</button></div>'+
      '<input type="hidden" name="instruction"><input type="hidden" name="remember">';
  } else if(FIX&&k[0]==='spec_table'){
    html+='<p class="pk-small">Spec rows are copied exactly from your product’s facts. To change one, change the fact in Shopify.</p>'+
      '<div class="pk-row"><button type="button" class="ca-btn" data-remove="'+esc(path)+'">Remove '+(k.length>1?'this row':'the table')+'</button><button type="button" class="ca-btn" data-x>Cancel</button></div>'+
      '<input type="hidden" name="instruction"><input type="hidden" name="remember">';
  } else if(k[0]==='sections'&&k.length===2){
    var i=+k[1];
    html+='<div class="pk-quick">'+(i>0?'<button type="button" data-move="up" data-i="'+i+'">↑ Move up</button>':'')+(i<DATA.sections-1?'<button type="button" data-move="down" data-i="'+i+'">↓ Move down</button>':'')+
      '<button type="button" data-remove="'+esc(path)+'" class="pk-del">Remove section</button></div>'+
      '<div class="pk-add"><input name="topic" placeholder="Add a section after this one about…"><button type="button" class="ca-btn" data-add="'+i+'">Add</button></div>'+
      '<p class="pk-small">Or rewrite the whole section:</p>'+rewriteBlock(path,false);
  } else {
    html+=rewriteBlock(path,path!=='title');
  }
  if(FIX) html=html.replace('Type straight into the article','Type straight into the page');
  pop.innerHTML=html+'</form>';
  place(el); var ta=pop.querySelector('textarea'); if(ta&&!words) ta.focus();
}
function typeIt(){
  if(!sel||!sel.dataset) return; var el=sel, path=el.dataset.pk;
  typing=el; el.contentEditable='true'; el.focus();
  try{var r=el.ownerDocument.createRange();r.selectNodeContents(el);r.collapse(false);var s=el.ownerDocument.getSelection();s.removeAllRanges();s.addRange(r)}catch(e){}
  pop.innerHTML=head('Typing: '+name(path))+'<p class="pk-small">Type straight into the '+(FIX?'page':'article')+', then save. Your own words aren’t rewritten.</p>'+
    '<div class="pk-row"><button type="button" class="ca-btn ca-primary" data-savetext="'+esc(path)+'">Save</button><button type="button" class="ca-btn" data-x>Cancel</button></div>';
  place(el);
}
function shrink(file,cb){
  var rd=new FileReader(); rd.onload=function(){ var im=new Image(); im.onload=function(){
    var s=Math.min(1,2000/Math.max(im.width,im.height)), c=document.createElement('canvas'); c.width=Math.round(im.width*s); c.height=Math.round(im.height*s);
    c.getContext('2d').drawImage(im,0,0,c.width,c.height); cb(c.toDataURL('image/jpeg',0.86)) }; im.onerror=function(){cb(null)}; im.src=rd.result };
  rd.readAsDataURL(file);
}
pop.addEventListener('click',function(e){
  var t=e.target.closest('button,img')||e.target;
  if(t.hasAttribute&&t.hasAttribute('data-x')){ if(typing){ location.reload(); return } return closePop() }
  if(t.dataset.quick){ var f=pop.querySelector('form'); f.quick.value=t.dataset.quick; return go(f) }
  if(t.dataset.remove){ return post({action:'remove_part',path:t.dataset.remove},'Removing…') }
  if(t.dataset.url){ return post({action:'photo',slot:t.dataset.slot,url:t.dataset.url},'Changing the photo…') }
  if(t.dataset.wider){ var w=sel&&sel.parentElement&&sel.parentElement.closest('[data-pk]'); if(w) pick(w); return }
  if(t.dataset.type){ return typeIt() }
  if(t.dataset.savetext){ return post({action:'set_text',path:t.dataset.savetext,text:typing?typing.innerText:''},'Saving your words…') }
  if(t.dataset.move){ return post({action:'move_section',index:t.dataset.i,dir:t.dataset.move},'Moving…') }
  if(t.dataset.add){ var tp=pop.querySelector('input[name=topic]').value; if(!tp.trim()) return pop.querySelector('input[name=topic]').focus();
    return post({action:'add_section',after:t.dataset.add,topic:tp},'Writing the new section… (about 30 seconds)') }
  if(t.dataset.swap){ return post({action:'swap_product',pid:t.dataset.pid,handle:t.dataset.swap},'Swapping the product…') }
  if(t.dataset.upload){ var inp=pop.querySelector('input[type=file]'); inp.onchange=function(){ var fl=inp.files&&inp.files[0]; if(!fl) return;
      pop.innerHTML='<p class="pk-busy">Uploading your photo…</p>'; shrink(fl,function(d){ if(!d){ pop.innerHTML='<p class="pk-err">That file isn’t a photo we can use.</p><button type="button" class="ca-btn" data-x>Close</button>'; return }
      post({action:'upload_photo',slot:t.dataset.upload,data:d},'Uploading your photo…') }) }; inp.click(); return }
  if(t.dataset.look){ var L=pop.querySelector('.pk-look'); return post({action:'look_quick',heading_font:L.heading.value,body_font:L.body.value,heading_upper:L.upper.checked?'1':'0',accent:L.accent.value},'Changing the look…') }
  if(t.dataset.sw){ pop.querySelectorAll('[data-sw]').forEach(function(b){b.classList.toggle('on',b===t)}); pop.querySelector('.pk-look').accent.value=t.dataset.sw }
});
function go(f){
  var d={action:'change_part',path:f.path.value,instruction:f.instruction.value,quick:f.quick.value,selection:f.selection.value};
  if(f.remember&&f.remember.checked) d.remember='1';
  if(!d.instruction.trim()&&!d.quick) return;
  post(d,'Rewriting this part… (about 20 seconds)');
}
pop.addEventListener('submit',function(e){
  e.preventDefault(); var f=e.target;
  if(f.dataset.kind==='gap'){ var d={action:'fill','q.0':f.q.value}; if(f.skip.checked) d['skip.0']='1'; else d['a.0']=f.a.value;
    if(!f.skip.checked&&!f.a.value.trim()) return; return post(d,'Saving your answer…') }
  go(f);
});
function gap(el){
  stopTyping(); select(el);
  pop.innerHTML='<form data-kind="gap"><input type="hidden" name="q" value="'+esc(el.dataset.gap)+'">'+head('Answer the question')+'<p class="pk-small">'+esc(el.dataset.gap)+'</p>'+
   '<input name="a" placeholder="Your answer, in a few words"><label class="pk-rem"><input type="checkbox" name="skip"> Leave this sentence out</label>'+
   '<div class="pk-row"><button class="ca-btn ca-primary">Save</button><button type="button" class="ca-btn" data-x>Cancel</button></div></form>';
  place(el); pop.querySelector('input[name=a]').focus();
}
function photo(el){
  stopTyping(); select(el);
  var slot=el.dataset.photo;
  pop.innerHTML=head('Choose another photo')+'<div class="pk-grid"><button type="button" class="pk-up" data-upload="'+esc(slot)+'"><span>+</span>Upload<br>from your computer</button>'+
   DATA.photos.map(function(u){var t=u.indexOf('/content/media/')>0?u:u+(u.indexOf('?')<0?'?':'&')+'width=200';
   var ig=(DATA.ig||[]).indexOf(u)>=0;
   return '<img src="'+esc(t)+'" data-url="'+esc(u)+'" data-slot="'+esc(slot)+'" alt=""'+(ig?' class="pk-ig" title="From your Instagram"':'')+' loading="lazy">'}).join('')+'</div><input type="file" accept="image/jpeg,image/png,image/webp" hidden>';
  place(el);
}
function look(){
  stopTyping(); select(tools);
  var L=DATA.look||{}, opt=function(cur){return DATA.fonts.map(function(f){return '<option'+(f===cur?' selected':'')+'>'+esc(f)+'</option>'}).join('')};
  pop.innerHTML=head('Look of all your articles')+'<form class="pk-look"><label>Headings<select name="heading">'+opt(L.heading)+'</select></label>'+
   '<label>Text<select name="body">'+opt(L.body)+'</select></label><label class="pk-rem"><input type="checkbox" name="upper"'+(L.upper?' checked':'')+'> Headings in capitals</label>'+
   '<span class="pk-small">Accent colour</span><div class="pk-sws">'+DATA.colours.map(function(c){return '<button type="button" data-sw="'+esc(c)+'" class="'+(c===L.accent?'on':'')+'" style="background:'+esc(c)+'" title="'+esc(c)+'"></button>'}).join('')+'</div>'+
   '<input type="hidden" name="accent" value="'+esc(L.accent||'')+'"><p class="pk-small">Only fonts and colours from your own site. Changes every article’s preview.</p>'+
   '<div class="pk-row"><button type="button" class="ca-btn ca-primary" data-look="1">Save the look</button><button type="button" class="ca-btn" data-x>Cancel</button></div></form>';
  place(tools.querySelector('.pk-lookb'));
}
function arm(f){
  frame=f; var doc; try{doc=f.contentDocument}catch(e){return} if(!doc||doc.pkArmed) return; doc.pkArmed=true;
  var st=doc.createElement('style');
  st.textContent='body.pk-editing [data-pk]:hover,body.pk-editing [data-photo]:hover,body.pk-editing mark[data-gap]:hover{outline:2px dashed #3b6fd8;outline-offset:3px;cursor:pointer}'+
   'body.pk-editing .pk-sel{outline:2px solid #3b6fd8!important;outline-offset:3px;background:rgba(59,111,216,.06)}body.pk-editing a{pointer-events:none}'+
   '[contenteditable=true]{outline:2px solid #12a150!important;outline-offset:3px;background:#f3fbf6!important;cursor:text!important}mark[data-gap]{cursor:pointer}';
  doc.head.appendChild(st);
  doc.body.classList.toggle('pk-editing',on);
  doc.addEventListener('click',function(e){
    if(typing&&typing.contains(e.target)) return;
    var g=e.target.closest('mark[data-gap]'); if(g){ e.preventDefault(); return gap(g) }
    if(!on) return;
    e.preventDefault();
    var p=e.target.closest('[data-photo]'); if(p) return photo(p);
    var el=e.target.closest('[data-pk]'); if(el) pick(el);
  },true);
  doc.addEventListener('mouseup',function(){ if(!on||typing) return; var s=String(doc.getSelection()).trim(); if(!s) return;
    var n=doc.getSelection().anchorNode; var el=n&&(n.nodeType===1?n:n.parentElement); el=el&&el.closest('[data-pk]'); if(el) pick(el) });
}
window.pkEditorReady=arm;
function setOn(v){ on=v; pencil.setAttribute('aria-pressed',v?'true':'false'); tools.classList.toggle('pk-on',v);
  if(frame&&frame.contentDocument) frame.contentDocument.body.classList.toggle('pk-editing',v); if(!v) closePop() }
function setDev(d){ tools.dataset.dev=d; tools.querySelectorAll('[data-dev]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.dev===d?'true':'false')});
  var f=document.getElementById('pk-frame'); if(!f) return; f.classList.toggle('pk-phone',d==='phone');
  setTimeout(function(){try{f.style.height=f.contentDocument.documentElement.scrollHeight+'px'}catch(e){}},300) }
pencil.addEventListener('click',function(){ setOn(!on) });
tools.querySelector('.pk-undo').addEventListener('click',function(){ place(tools); post({action:'undo'},'Undoing…') });
var lb=tools.querySelector('.pk-lookb'); if(lb) lb.addEventListener('click',look);
tools.querySelectorAll('[data-dev]').forEach(function(b){ b.addEventListener('click',function(){ setDev(b.dataset.dev) }) });
document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&!pop.hidden){ e.stopImmediatePropagation(); if(typing){ location.reload(); return } closePop() } },true);
var f0=document.getElementById('pk-frame'); if(f0&&f0.contentDocument&&f0.contentDocument.readyState==='complete') arm(f0);
try{ if(sessionStorage.getItem('pk-edit')==='1'){ sessionStorage.removeItem('pk-edit'); setOn(true) }
  var dv=sessionStorage.getItem('pk-dev'); if(dv){ sessionStorage.removeItem('pk-dev'); setDev(dv) }
  var st=sessionStorage.getItem('pk-scroll'); if(st){ sessionStorage.removeItem('pk-scroll'); st=JSON.parse(st);
    var back=function(){ try{ var f=document.getElementById('pk-frame'); f.contentWindow.scrollTo(0,st[0]); if(document.scrollingElement) document.scrollingElement.scrollTop=st[1] }catch(e){} };
    back(); setTimeout(back,700); setTimeout(back,1600) } }catch(e){}
})();
"""


def history_box(domain, did):
    import article_learning
    import storetime
    tz = storetime.zone(domain)
    rows = article_learning.history(did)
    if len(rows) < 2:
        return ''
    items = []
    for n, (vid, at, who, note) in enumerate(rows):
        btn = '' if n == 0 else ('<form method="post" action="/content"><input type="hidden" name="d" value="%s"><input type="hidden" '
                                 'name="id" value="%d"><input type="hidden" name="action" value="restore"><input type="hidden" '
                                 'name="version" value="%d"><button class="ca-btn ca-small">Restore</button></form>') % (E(domain), did, vid)
        items.append('<li><span><b>%s</b> <em class="cr-muted">%s%s</em></span>%s</li>' % (
            E(note), E(storetime.label(at, tz)), ' · current' if n == 0 else '', btn))
    return ('<section class="cr-box"><details class="cr-hist"><summary>History (%d versions)</summary><ul class="cs-lessons">%s'
            '</ul></details></section>') % (len(rows), ''.join(items))


def _ask_form(domain, did, body):
    import article_learning
    done = body.get('requests') or []
    last = ('<p class="cr-said"><strong>Done:</strong> %s</p>' % E(done[-1]['reply'])) if done and done[-1].get('reply') else ''
    n = len(article_learning.lessons(domain))
    remembered = ('The agent remembers lasting requests for your future articles (%d so far, in Settings).' % n) if n \
        else 'Lasting requests ("never mention sunscreen", "shorter intros") are remembered for your future articles.'
    return ('<section class="cr-box cr-ask"><h2>Ask for changes</h2><p class="cr-muted">Say what to change, in your own words: '
            'text, sections, photos or the look. %s</p>%s<form method="post" action="/content" class="cr-askf">'
            '<input type="hidden" name="d" value="%s"><input type="hidden" name="id" value="%d">'
            '<input type="hidden" name="action" value="revise"><textarea name="instruction" rows="3" required '
            'placeholder="e.g. Remove the sunscreen note. Make the headings smaller. Use our body font for headings."></textarea>'
            '<label class="cr-remember"><input type="checkbox" name="remember" value="1" checked> Remember this for future articles</label>'
            '<button class="ca-btn ca-primary">Apply changes</button></form>'
            '<script>document.querySelectorAll(".cr-askf").forEach(function(f){f.addEventListener("submit",function(){'
            'var b=f.querySelector("button");b.disabled=true;b.textContent="Rewriting\u2026 (about a minute)";});});</script>'
            '</section>') % (E(remembered), last, E(domain), did)


def _review(body):
    """The self-review's grades and problems (selfreview.py), for the agent's own draft."""
    import selfreview
    rev = body.get('review')
    if not rev:
        return ''
    scores = ''.join('<li>%s <strong>%d/5</strong></li>' % (E(label), rev['scores'].get(k, 0))
                     for k, label in selfreview.LABELS)
    issues = ''.join('<li>%s <span class="cr-muted">%s</span></li>' % (E(i['problem']), E(i['fix']))
                     for i in rev.get('issues') or [])
    note = ('Graded on the agent\'s first version, before your edits.' if body.get('edited_at')
            else 'Ready as far as the editor can tell.' if rev.get('passed') else 'Worth a closer look before you approve.')
    return ('<section class="cr-box"><h2>Editor\'s check</h2><p class="cr-muted">A second pass by the agent. %s</p>'
            '<ul class="cs-traits">%s</ul>%s</section>') % (
        E(note), scores, ('<h3 class="cs-h3">What to fix</h3><ul class="cs-traits">%s</ul>' % issues) if issues else '')


def act(form):
    """Save answers to gaps, or edits. Returns (code, redirect)."""
    domain = form.get('d', '')
    try:
        did = int(form.get('id', ''))
    except ValueError:
        return 400, '<h1>Bad request</h1>'
    row, body, prev = load(did, domain)
    if not row:
        return 400, '<h1>Bad request</h1>'
    if form.get('action') == 'fill':
        answers = {}
        for k, q in form.items():
            if k.startswith('q.'):
                i = k[2:]
                if form.get('skip.' + i):
                    answers[q] = ''
                elif form.get('a.' + i, '').strip():
                    answers[q] = form['a.' + i].strip()
        if answers:
            fill(body, answers)
            body['change_note'] = 'Answered %d question%s' % (len(answers), '' if len(answers) == 1 else 's')
            rebuild(body, row['draft_type'])
            save_version(did, body, prev, title=body.get('title') if row['draft_type'] in ('comparison', 'guide') else None)
    elif form.get('action') == 'save':
        import copy
        before = copy.deepcopy(body)
        if edit(body, form, row['draft_type']):
            body['change_note'] = 'You edited the text'
            rebuild(body, row['draft_type'])
            save_version(did, body, prev, title=body.get('title') if row['draft_type'] in ('comparison', 'guide') else None)
            if body.get('layout') == 'article':
                import article_learning
                article_learning.learn_in_background(domain, before, body)
            elif row['draft_type'] in ('product_fix', 'faq'):
                import fix_learning
                fix_learning.learn_in_background(domain, before, body)
    elif form.get('action') in ('change_part', 'remove_part', 'photo', 'undo', 'restore', 'set_text', 'move_section',
                                'add_section', 'swap_product', 'look_quick', 'upload_photo'):
        import article_learning
        import llm
        a = form['action']
        if row['draft_type'] in ('product_fix', 'faq') and a in ('change_part', 'remove_part', 'set_text'):
            import fix_learning                        # product page fixes learn too (20 Oct 2026)
            try:
                if a == 'change_part':
                    fix_learning.change_part(domain, did, form.get('path', ''), form.get('instruction', ''),
                                             form.get('quick', ''), form.get('selection', ''), bool(form.get('remember')))
                elif a == 'remove_part':
                    fix_learning.remove_part(domain, did, form.get('path', ''))
                else:
                    fix_learning.set_text(domain, did, form.get('path', ''), form.get('text', ''))
            except (ValueError, llm.LLMError) as e:
                return 409, '<h1>%s</h1>' % E(str(e))
            return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))
        try:
            if a == 'change_part':
                article_learning.change_part(domain, did, form.get('path', ''), form.get('instruction', ''),
                                             form.get('quick', ''), form.get('selection', ''), bool(form.get('remember')))
            elif a == 'remove_part':
                article_learning.remove_part(domain, did, form.get('path', ''))
            elif a == 'photo':
                article_learning.set_photo(domain, did, form.get('slot', ''), form.get('url', ''))
            elif a == 'set_text':
                article_learning.set_text(domain, did, form.get('path', ''), form.get('text', ''))
            elif a == 'move_section':
                article_learning.move_section(domain, did, int(form.get('index', '-1')), form.get('dir', ''))
            elif a == 'add_section':
                article_learning.add_section(domain, did, int(form.get('after', '-1')), form.get('topic', ''))
            elif a == 'swap_product':
                article_learning.swap_product(domain, did, form.get('pid', ''), form.get('handle', ''))
            elif a == 'look_quick':
                article_learning.look_quick(domain, form)
            elif a == 'upload_photo':
                article_learning.upload_photo(domain, did, form.get('slot', ''), form.get('data', ''))
            elif a == 'undo':
                article_learning.restore(domain, did)
            else:
                article_learning.restore(domain, did, int(form.get('version', '0') or 0))
        except (ValueError, llm.LLMError) as e:
            return 409, '<h1>%s</h1>' % E(str(e))
    elif form.get('action') == 'redesign':
        new, err = redesign(domain, did)
        if err:
            return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did, error=err[:200]))
        back = form.get('back', '')
        if back.startswith('/content?'):
            return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox', id=new))
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=new))
    elif form.get('action') == 'revise' and form.get('instruction', '').strip():
        import article_learning
        import llm
        try:
            article_learning.revise(domain, did, form['instruction'], remember=bool(form.get('remember')))
        except (ValueError, llm.LLMError) as e:
            return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did, error=str(e)[:200]))
    back = form.get('back', '')
    if back.startswith('/content?'):                 # the board's sheet sends you back to the board
        return 303, back
    return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))


CSS = """
.cr-back{display:inline-block;margin:0 0 12px;font-size:14px;font-weight:600;color:#586579;text-decoration:none}
.cr-back:hover{color:#0b1b35}
.cr-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}
.cr-title{font-size:20px;font-weight:700;margin:8px 0 0;color:#0b1b35}
.cr-status{font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;background:#eef2f8;color:#586579}
.cr-approved{background:#e6f4ec;color:#047857}.cr-rejected{background:#fdecec;color:#b42318}
.cr-box{border:1px solid #e6e9ef;border-radius:12px;background:#ffffff;padding:18px 20px;margin:0 0 16px}
.cr-box h2,.cr-col h2{font-size:15px;font-weight:700;margin:0 0 6px;color:#0b1b35}
.cr-muted{color:#586579;font-size:13.5px;line-height:1.5;margin:0 0 12px}
.cr-gaps{border-color:#f3c9a5;background:#fff8f1}
.cr-gap{display:grid;gap:6px;padding:12px 0;border-top:1px solid #f1e2d3}
.cr-gap label{font-size:14px;font-weight:600;color:#1a2436}
.cr-gap input:not([type]),.cr-field input,.cr-field textarea{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #d5dbe5;border-radius:8px;background:#ffffff;font:inherit;font-size:14px;color:#1a2436}
.cr-gap .cr-skip{font-weight:500;font-size:13px;color:#586579;display:flex;gap:6px;align-items:center}
.cr-gaps .ca-btn{margin-top:10px}
.cr-ba{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:0 0 16px}
.cr-col{border:1px solid #e6e9ef;border-radius:12px;background:#ffffff;padding:18px 20px;min-width:0;font-size:14.5px;line-height:1.6;color:#1a2436}
.cr-after{border-color:#b9cbe8}
.cr-ptitle{font-size:16px;font-weight:700;margin:6px 0 10px;color:#0b1b35}
.cr-doc h2{font-size:15.5px;margin:16px 0 6px}.cr-doc h3{font-size:14.5px;margin:12px 0 4px}
.cr-doc table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13.5px}
.cr-doc th,.cr-doc td{border:1px solid #e6e9ef;padding:7px 9px;text-align:left;vertical-align:top}
.cr-doc th{background:#f4f6fa;font-weight:600}
.cr-check{margin:14px 0 0;padding-top:10px;border-top:1px solid #eef1f5;font-size:13px;color:#586579}
.cr-qs{margin:0;padding-left:18px;display:grid;gap:6px;font-size:14px}
.cr-qs .cr-muted{display:block;margin:2px 0 0}
.cr-edit summary{cursor:pointer;font-size:15px;font-weight:700;color:#0b1b35}
.cr-form{display:grid;gap:12px;margin-top:14px}
.cr-field{display:grid;gap:5px}
.cr-field label{font-size:13px;font-weight:600;color:#586579}
.cr-rich{min-height:90px;padding:9px 11px;border:1px solid #d5dbe5;border-radius:8px;background:#ffffff;font-size:14px;line-height:1.55;color:#1a2436}
.cr-rich p{margin:0 0 8px}
.cr-form .ca-btn{justify-self:start}
.cr-frame{width:100%;border:1px solid #e6e9ef;border-radius:10px;background:#fff;display:block;min-height:500px}
.cr-ask textarea{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:14px;margin:0 0 10px}
.cr-said{font-size:13.5px;color:#047857;margin:0 0 10px}
.cr-prevtop{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 6px}
.cr-remember{display:flex;gap:8px;align-items:center;font-size:13.5px;margin:0 0 10px}
.cr-hist summary{cursor:pointer;font-weight:700;font-size:14.5px}
.pk-tools{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin:0 0 8px;flex-wrap:wrap}
.pk-tools .pk-hint{display:none;font-size:13px;color:#586579;margin-right:auto}
.pk-tools.pk-on .pk-hint{display:inline}
.pk-pencil,.pk-undo{display:inline-flex;align-items:center;gap:6px;font:600 13.5px/1 inherit;padding:8px 12px;border-radius:8px;border:1px solid #d5dbe5;background:#fff;color:#0b1b35;cursor:pointer}
.pk-pencil svg{width:16px;height:16px}
.pk-pencil[aria-pressed=true]{background:#0b1b35;color:#fff;border-color:#0b1b35}
.pk-pop{position:absolute;z-index:400;width:380px;max-width:calc(100vw - 24px);background:#fff;color:#1a2436;border:1px solid #d5dbe5;border-radius:12px;box-shadow:0 18px 50px -12px rgba(11,27,53,.35);padding:14px;font-size:14px}
.pk-pop-h{display:flex;align-items:center;gap:8px;margin:0 0 10px}.pk-pop-h b{font-size:14.5px}
.pk-x{margin-left:auto;border:0;background:none;font-size:22px;line-height:1;color:#586579;cursor:pointer}
.pk-link{border:0;background:none;color:#3b6fd8;font-size:12.5px;cursor:pointer;padding:0}
.pk-quote{margin:0 0 10px;font-size:13px;color:#586579;font-style:italic}
.pk-quick{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.pk-quick button{border:1px solid #d5dbe5;background:#f6f8fb;border-radius:999px;padding:5px 10px;font-size:12.5px;cursor:pointer;color:#1a2436}
.pk-quick .pk-del{color:#b42318;border-color:#f3c3bd;background:#fff6f5}
.pk-pop textarea,.pk-pop input[name=a]{width:100%;box-sizing:border-box;border:1px solid #d5dbe5;border-radius:8px;padding:8px 10px;font:inherit;font-size:14px;margin:0 0 8px;background:#fff;color:#1a2436}
.pk-rem{display:flex;gap:8px;align-items:center;font-size:13px;margin:0 0 10px;color:#1a2436}
.pk-row{display:flex;gap:8px}
.pk-small{font-size:13px;color:#586579;margin:0 0 10px}
.pk-busy{margin:4px 0;font-weight:600}.pk-err{margin:0 0 10px;color:#b42318}
.pk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;max-height:320px;overflow:auto}
.pk-grid img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;cursor:pointer;border:2px solid transparent}
.pk-grid img.pk-ig{border-color:#f0c2d8}
.pk-grid img:hover{border-color:#3b6fd8}
.pk-up{aspect-ratio:1;border:1.5px dashed #9fb3d6;border-radius:6px;background:#f6f8fb;color:#0b1b35;font-size:11px;line-height:1.3;cursor:pointer;padding:4px}
.pk-up span{display:block;font-size:20px;line-height:1}
.pk-lookb{font:600 13.5px/1 inherit;padding:8px 12px;border-radius:8px;border:1px solid #d5dbe5;background:#fff;color:#0b1b35;cursor:pointer}
.pk-dev{display:inline-flex;border:1px solid #d5dbe5;border-radius:8px;overflow:hidden}
.pk-dev button{font:600 12.5px/1 inherit;padding:8px 10px;border:0;background:#fff;color:#586579;cursor:pointer}
.pk-dev button[aria-pressed=true]{background:#0b1b35;color:#fff}
.cr-frame.pk-phone{width:390px!important;margin:0 auto;display:block}
.pk-prods{display:grid;gap:6px;max-height:260px;overflow:auto;margin:0 0 10px}
.pk-prods button{display:flex;align-items:center;gap:10px;text-align:left;border:1px solid #e3e8ef;background:#fff;border-radius:8px;padding:6px;cursor:pointer;font-size:13px;color:#1a2436}
.pk-prods button:hover{border-color:#3b6fd8}
.pk-prods img{width:38px;height:38px;object-fit:cover;border-radius:6px}
.pk-add{display:flex;gap:6px;margin:0 0 10px}
.pk-add input{flex:1;border:1px solid #d5dbe5;border-radius:8px;padding:8px 10px;font:inherit;font-size:13.5px;background:#fff;color:#1a2436}
.pk-look{display:grid;gap:8px}
.pk-look label{display:grid;gap:4px;font-size:12.5px;font-weight:600;color:#586579}
.pk-look .pk-rem{display:flex;font-weight:500;color:#1a2436;font-size:13px}
.pk-look select{border:1px solid #d5dbe5;border-radius:8px;padding:7px 9px;font:inherit;font-size:13.5px;background:#fff;color:#1a2436}
.pk-sws{display:flex;flex-wrap:wrap;gap:6px}
.pk-sws button{width:26px;height:26px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #d5dbe5;cursor:pointer}
.pk-sws button.on{box-shadow:0 0 0 2px #3b6fd8}
@media (max-width:820px){.cr-ba{grid-template-columns:1fr}.cr-top{flex-direction:column}}
"""
