"""Catalog Optimization Agent (code name: content agent): Inbox, Calendar, Published.

The agent turns Opportunities into written fixes - product-page changes, FAQs,
comparison pages, buying guides - that the merchant reviews before anything
goes anywhere. Plan and scope: mvp/content-agent/PLAN.md.

Day 1 (14 Oct 2026): the switch, the tables and the three empty views.
Day 12 (15 Oct): Download for Shopify on the Calendar (content_export.py).
Day 11c (15 Oct): first visit opens setup (content_setup.py): voice, then scope.
Day 11b (15 Oct): approving plans a draft on the next free weekday; calendar items
open a detail panel (content_calendar.py).
Day 11 (15 Oct): a "Draft fix" button on Opportunity cards (opportunity_button).
Day 10 (15 Oct): each card opens the draft view (content_review.py).
Day 9 (15 Oct): the Inbox lists drafts by status (New / Approved / Rejected)
with Approve and Reject. A draft that still holds an '[ask merchant: ...]'
gap can't be approved.

Hidden behind config.SHOW_CONTENT_AGENT (or admins only with PRODUKTO_CONTENT_AGENT=admin): with it off there is no rail
item, the old "Content agents" waitlist page stays, and /content is Not found.

Two rules, neither optional:
  * Never invent a product fact. Every fact in a draft comes from the brand's
    own catalog or page; anything else is left as a question for the merchant.
  * Describe the work, never promise a result. Nobody has shown yet that these
    fixes move AI visibility.
"""
import calendar
import datetime
import urllib.parse
from html import escape as E

import config
import db
import storetime

# What merchants see this feature called (Kelian, 15 Oct 2026). Code names stay 'content'.
NAME = 'Catalog Optimization Agent'

def enabled():
    """Is the agent visible to whoever is looking? On for everyone, or for admins only (server demos)."""
    if config.SHOW_CONTENT_AGENT:
        return True
    if config.CONTENT_AGENT_ADMIN_ONLY:
        import accounts
        return accounts.is_admin()
    return False


VIEWS = (('inbox', 'Drafts'), ('calendar', 'Calendar'), ('published', 'Live'))   # tab names: Kelian, 16 Oct

# What the agent writes. Key -> label shown on cards and the calendar.
DRAFT_TYPES = {
    'product_fix': 'Product page fix',
    'faq': 'FAQ',
    'comparison': 'Comparison page',
    'guide': 'Buying guide',
    'collection': 'Collection copy',
}

# A draft's life. Only 'published' means it is live on the store, and nothing
# reaches it in v1: the merchant imports the export file themselves.
STATUSES = ('draft', 'approved', 'scheduled', 'published', 'rejected')


def init():
    with db.conn() as c:
        # What a draft is for: the Opportunity behind it and where it goes.
        c.execute('CREATE TABLE IF NOT EXISTS content_briefs ('
                  'id INTEGER PRIMARY KEY, store_domain TEXT NOT NULL, '
                  'opportunity_kind TEXT, opportunity_key TEXT, draft_type TEXT NOT NULL, '
                  "target_kind TEXT NOT NULL DEFAULT 'product', "  # product / collection / blog
                  'target_id TEXT, target_url TEXT, target_title TEXT, target_field TEXT, '
                  'questions TEXT, competitors TEXT, data TEXT, created_at REAL)')
        cols = [r[1] for r in c.execute('PRAGMA table_info(content_briefs)')]
        if 'data' not in cols:     # tables made on day 1 lack the full-brief column
            c.execute('ALTER TABLE content_briefs ADD COLUMN data TEXT')
        c.execute('CREATE TABLE IF NOT EXISTS content_drafts ('
                  'id INTEGER PRIMARY KEY, brief_id INTEGER, store_domain TEXT NOT NULL, '
                  "draft_type TEXT NOT NULL, title TEXT, status TEXT NOT NULL DEFAULT 'draft', "
                  'planned_at REAL, approved_at REAL, approved_by TEXT, published_at REAL, '
                  'live_url TEXT, created_at REAL, updated_at REAL)')
        # Every edit is kept, by the agent or the merchant, with its sources and
        # the facts it still needs from the merchant.
        c.execute('CREATE TABLE IF NOT EXISTS content_draft_versions ('
                  'id INTEGER PRIMARY KEY, draft_id INTEGER NOT NULL, body TEXT, '
                  "author TEXT NOT NULL DEFAULT 'agent', sources TEXT, open_facts TEXT, created_at REAL)")
        c.execute('CREATE INDEX IF NOT EXISTS idx_content_drafts_store ON content_drafts(store_domain, status)')


def drafts(domain, statuses=None):
    sql, args = 'SELECT * FROM content_drafts WHERE store_domain=?', [domain]
    if statuses:
        sql += ' AND status IN (%s)' % ','.join('?' * len(statuses))
        args += list(statuses)
    return db.all_(sql + ' ORDER BY COALESCE(planned_at, created_at)', tuple(args))


def _store(q):
    # Same store choice as Opportunities: the one in the address, else the last one opened.
    import opportunities
    return opportunities._store(q)





# Two agents in the sidebar since 18 Oct 2026 (Kelian): "Product page fixes" and "AEO articles" (his name;
# not plain "Articles"). Settings are shared: voice, brand facts, missing facts and Shopify feed both.
LANES = (('fixes', 'Product page fixes'), ('articles', 'AEO articles'))
LANE_VIEWS = {'fixes': (('inbox', 'Drafts'), ('published', 'Live'), ('results', 'Results')),
              'articles': (('inbox', 'Drafts'), ('calendar', 'Calendar'), ('published', 'Live'), ('results', 'Results'))}
_LAST_LANE = {}            # user id -> the agent they last opened, so links without a lane return there


def lane(q, domain=''):
    """The agent in view: from the address, else implied by the view (Calendar = articles, a draft = its own
    kind), else the one this person last opened."""
    import accounts
    import content_board
    user = (accounts.current() or {}).get('id', 0)
    pick = q.get('lane')
    if pick not in dict(LANES):
        pick = None
        if q.get('view') == 'calendar':
            pick = 'articles'
        elif q.get('view') == 'draft' and str(q.get('id', '')).isdigit():
            row = db.one('SELECT draft_type FROM content_drafts WHERE id=? AND store_domain=?', (int(q['id']), domain))
            if row:
                pick = 'articles' if row['draft_type'] in content_board.ARTICLE_TYPES else 'fixes'
    pick = pick or _LAST_LANE.get(user, 'fixes')
    _LAST_LANE[user] = pick
    return pick


def _tabs(domain, view, ln='fixes'):
    return '<nav class="ca-tabs" aria-label="%s views"' % E(dict(LANES)[ln]) + '>' + ''.join(
        '<a %shref="/content?%s">%s</a>' % ('aria-current="page" ' if k == view else '',
                                           E(urllib.parse.urlencode(dict(d=domain, lane=ln, view=k))), E(l))
        for k, l in LANE_VIEWS[ln] + (('setup', 'Settings'),)) + '</nav>'


def _empty(text):
    return '<div class="ca-empty"><p>%s</p></div>' % text


# Inbox filters: (key, label, statuses). "New" is the stored 'draft' status.
INBOX_FILTERS = (('new', 'New', ('draft',)), ('approved', 'Approved', ('approved', 'scheduled')),
                 ('rejected', 'Rejected', ('rejected',)))
PLACEHOLDER = '[ask merchant'


def _latest(draft_id):
    import json
    row = db.one('SELECT body, open_facts FROM content_draft_versions WHERE draft_id=? ORDER BY id DESC LIMIT 1',
                 (draft_id,))
    if not row:
        return {}, []
    return json.loads(row['body'] or '{}'), json.loads(row['open_facts'] or '[]')


def placeholders(body):
    """How many "[ask merchant: ...]" gaps the draft still holds. A draft with any can't be approved."""
    import json
    return json.dumps(body, ensure_ascii=False).count(PLACEHOLDER)


def _card(r, domain, show, tz):
    body, open_facts = _latest(r['id'])
    gaps = placeholders(body)
    product = body.get('product') or {}
    img = ('<img class="ca-thumb" src="%s" alt="" loading="lazy">' % E(product['image'])) if product.get('image') \
        else '<span class="ca-thumb"></span>'
    target = product.get('title') or ''
    if body.get('products') and len(body['products']) > 1:
        target = '%s + %d more' % (target, len(body['products']) - 1)
    bits = ['Drafted %s' % E(storetime.label(r['created_at'], tz))]
    if r['status'] in ('approved', 'scheduled') and r['approved_at']:
        bits = ['Approved %s%s' % (E(storetime.label(r['approved_at'], tz)),
                                   ' by %s' % E(r['approved_by']) if r['approved_by'] else '')]
    if open_facts:
        bits.append('%d question%s for you' % (len(open_facts), '' if len(open_facts) == 1 else 's'))
    fc = body.get('fact_check') or {}
    flagged = len(fc.get('numbers', [])) + len(fc.get('claims', []))
    if flagged:
        bits.append('%d sentence%s held back by the fact check' % (flagged, '' if flagged == 1 else 's'))
    import selfreview
    weak = selfreview.weakest(body.get('review')) if r['status'] == 'draft' and not body.get('edited_at') else ''
    if weak:
        bits.append('Worth a closer look: %s' % E(weak))
    back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox', show=show))

    def button(status, label, cls='', disabled=''):
        return ('<form method="post" action="/content"><input type="hidden" name="d" value="%s">'
                '<input type="hidden" name="id" value="%d"><input type="hidden" name="status" value="%s">'
                '<input type="hidden" name="back" value="%s"><button class="ca-btn %s"%s>%s</button></form>'
                % (E(domain), r['id'], status, E(back), cls, disabled, label))

    open_url = '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=r['id']))
    if r['status'] == 'draft' and gaps:
        # Approve waits for the gaps; say where to fill them instead of showing a dead button.
        actions = ('<a class="ca-btn ca-primary" href="%s">Fill %d gap%s</a>' % (E(open_url), gaps, '' if gaps == 1 else 's')
                   + button('rejected', 'Reject'))
    elif r['status'] == 'draft':
        actions = button('approved', 'Approve', 'ca-primary') + button('rejected', 'Reject')
    else:
        actions = button('draft', 'Move back to New')
    gap_note = ('<p class="ca-gap">%d fact%s the agent needs from you before this can be approved.</p>'
                % (gaps, '' if gaps == 1 else 's')) if gaps and r['status'] == 'draft' else ''
    return ('<li class="ca-card">%s<div class="ca-main"><div class="ca-head"><span class="ca-type">%s</span>'
            '<a class="ca-open" href="%s">%s</a></div><p class="ca-meta">%s%s</p>%s</div><div class="ca-actions">%s</div></li>') % (
        img, E(DRAFT_TYPES.get(r['draft_type'], r['draft_type'])),
        E('/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=r['id']))), E(r['title'] or 'Untitled'),
        ('For %s · ' % E(target)) if target and target not in (r['title'] or '') else '',
        ' · '.join(bits), gap_note, actions)


def _inbox(domain, q):
    show = q.get('show', 'new')
    if show not in [k for k, _, _ in INBOX_FILTERS]:
        show = 'new'
    counts = {k: len(drafts(domain, st)) for k, _, st in INBOX_FILTERS}
    chips = '<nav class="ca-chips" aria-label="Filter drafts">' + ''.join(
        '<a %shref="%s">%s <span>%d</span></a>' % (
            'aria-current="true" ' if k == show else '',
            E('/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox', show=k))), E(l), counts[k])
        for k, l, _ in INBOX_FILTERS) + '</nav>'
    rows = sorted(drafts(domain, dict((k, st) for k, _, st in INBOX_FILTERS)[show]),
                  key=lambda r: -(r['updated_at'] or r['created_at'] or 0))
    if not rows:
        text = {'new': 'No drafts waiting. Drafts appear here when you ask the agent to fix an Opportunity, '
                       'and nothing goes to your store until you approve it.',
                'approved': 'Nothing approved yet.', 'rejected': 'Nothing rejected.'}[show]
        return chips + _empty(text)
    tz = storetime.zone(domain)
    return chips + '<ul class="ca-list">' + ''.join(_card(r, domain, show, tz) for r in rows) + '</ul>'


def act(q, form):
    """Board and calendar drags send ajax=1: they get a short JSON answer instead of a redirect, so the card
    moves at once and the page doesn't reload (a reload rebuilds the whole rail, ~2 seconds). Same checks."""
    code, out = _act(q, form)
    if form.get('ajax') != '1':
        return code, out
    import json
    import re
    if code == 303:
        row = db.one('SELECT planned_at, status FROM content_drafts WHERE id=? AND store_domain=?',
                     (form.get('id', ''), form.get('d', '')))
        when = (storetime.date_of(row['planned_at'], storetime.zone(form.get('d', ''))).strftime('%b %-d')
                if row and row['planned_at'] else 'Live' if row and row['status'] == 'published'
                else 'Approved' if row and row['status'] in ('approved', 'scheduled') else 'No date')
        return 200, ('json', json.dumps(dict(ok=True, when=when, status=row['status'] if row else '')))
    text = re.sub(r'</h1>\s*', '. ', out) if isinstance(out, str) else ''
    import html as _html
    text = _html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).replace('..', '.').strip())
    return 200, ('json', json.dumps(dict(ok=False, error=text or 'That didn\'t work. Try again.')))


def _act(q, form):
    """Approve, reject or move a draft back to New. Nothing is sent to the store."""
    if not enabled():
        return 404, '<h1>Not found</h1>'
    import time
    import accounts
    init()
    domain, status = form.get('d', ''), form.get('status', '')
    if form.get('action') in ('shopify_connect', 'shopify_disconnect', 'publish', 'unpublish', 'store_preview'):
        return _shopify_act(domain, form)
    if form.get('action') in ('voice', 'voice_ok', 'brief_prefill', 'brief', 'scope', 'schedule', 'missing', 'facts',
                              'look_save', 'look_relearn', 'lesson_remove', 'playbook_relearn', 'articles_prefill', 'articles',
                              'fix_lesson_remove', 'fixpages_prefill', 'fixpages'):
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import content_setup
        return content_setup.act(domain, form)
    if form.get('action') in ('stories_publish', 'stories_remove', 'stories_instagram', 'instagram_handle', 'instagram_fetch'):
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        return _stories_act(domain, form)
    if form.get('action') == 'draft':
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import content_setup
        if not content_setup.done(domain):
            return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup'))
        did, err = draft_for(domain, form.get('kind', ''), form.get('key', ''), avoid=covered(domain), reuse=True)
        if err:
            return 200, ('<div class="ca-page" data-rail-page="content">%s<div class="ca-empty"><p>%s</p>'
                         '<p><a href="/opportunities?d=%s">Back to Opportunities</a></p></div></div>') % (
                title(), E(err), E(urllib.parse.quote(domain)))
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))
    if form.get('action') == 'review_now':
        # "Review now" on the Results tab: the monthly self-review (agent_review.py), run in the background.
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import agent_review
        import threading
        ln = form.get('lane') if form.get('lane') in dict(LANES) else 'fixes'
        if not agent_review.reviewing(domain):
            agent_review._running.add(domain)

            def go():
                try:
                    agent_review.review(domain, ln, force=True)
                finally:
                    agent_review._running.discard(domain)
            threading.Thread(target=go, daemon=True).start()
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, lane=ln, view='results'))
    if form.get('action') == 'monthly_write':
        # "Write this month's articles now" on the board: also switches it on for stores with no plan limit.
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import content_setup
        import monthly_articles
        st = content_setup.get(domain)
        st['monthly_articles'] = True
        content_setup.put(domain, st)
        monthly_articles.run(domain)
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox'))
    if form.get('action') in ('golive', 'unlive'):
        return _live_act(q, form)
    if form.get('action') == 'ical_reset':
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import content_calendar
        content_calendar.feed_token(domain, new=True)
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar'))
    if form.get('action') == 'move':
        import content_calendar
        try:
            did = int(form.get('id', ''))
        except ValueError:
            return 400, '<h1>Bad request</h1>'
        if not accounts.can_see(domain) or not content_calendar.move(domain, did, form.get('day', '')):
            return 400, '<h1>That date can\'t be used</h1><p>Pick today or a later day.</p>'
        # Follow the item to its new month.
        row = db.one('SELECT planned_at FROM content_drafts WHERE id=?', (did,))
        day = storetime.date_of(row['planned_at'], storetime.zone(domain)).isoformat()
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar', week=day, id=did))
    if form.get('action') in ('fill', 'save', 'revise', 'redesign', 'change_part', 'remove_part', 'photo', 'undo', 'restore',
                              'set_text', 'move_section', 'add_section', 'swap_product', 'look_quick', 'upload_photo'):
        if not accounts.can_see(domain):
            return 400, '<h1>Bad request</h1>'
        import content_review
        return content_review.act(form)
    try:
        did = int(form.get('id', ''))
    except ValueError:
        return 400, '<h1>Bad request</h1>'
    row = db.one('SELECT * FROM content_drafts WHERE id=? AND store_domain=?', (did, domain))
    if not row or not accounts.can_see(domain) or status not in ('approved', 'rejected', 'draft'):
        return 400, '<h1>Bad request</h1>'
    if status == 'approved' and placeholders(_latest(did)[0]):
        return 409, '<h1>This draft still has gaps to fill</h1><p>Answer its open questions first.</p>'
    if status == 'approved' and row['status'] != 'approved':
        import content_plan
        kind = content_plan.kind_of(row['draft_type'])
        if content_plan.left(domain, kind) == 0:
            many = content_plan.LABEL[kind][1]
            return 409, ('<h1>You\'ve used this month\'s %s</h1><p>%s Your plan includes %d %s a month. Approve this '
                         'draft next month%s.</p>') % (
                many, E(content_plan.summary(domain)), content_plan.allowance(domain, kind), many,
                ', or <a href="/settings">add more articles</a>' if kind == 'articles' else '')
    now = time.time()
    user = accounts.current()
    with db.conn() as c:
        if status == 'approved':
            c.execute('UPDATE content_drafts SET status=?, approved_at=?, approved_by=?, updated_at=? WHERE id=?',
                      (status, now, user['email'] if user else None, now, did))
        else:
            c.execute('UPDATE content_drafts SET status=?, approved_at=NULL, approved_by=NULL, planned_at=NULL, '
                      'updated_at=? WHERE id=?', (status, now, did))
    if status == 'approved' and row['draft_type'] in ARTICLE_TYPES:
        import content_calendar
        content_calendar.plan(domain, did)           # articles: next free slot, 09:00 store time
    elif status == 'approved':                         # page fixes go live when the merchant drags them there
        db.write('UPDATE content_drafts SET planned_at=NULL WHERE id=?', (did,))
    back = form.get('back', '')
    if not back.startswith('/content?'):
        back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox'))
    return 303, back


def _published(domain):
    rows = drafts(domain, ('published',))
    if not rows:
        return _empty('Nothing live on your store yet. Pages appear here once they\'re published.')
    return '<ul class="ca-list">' + ''.join(
        '<li><span class="ca-type">%s</span><strong>%s</strong></li>'
        % (E(DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), E(r['title'] or 'Untitled'))
        for r in rows) + '</ul>'


def _month(q, tz):
    today = storetime.today(tz)
    try:
        y, m = (int(x) for x in q.get('month', '').split('-'))
        return datetime.date(y, m, 1), today
    except ValueError:
        return today.replace(day=1), today


def _calendar(domain, q):
    """Month grid in the merchant's own time zone, with each draft on its planned day."""
    tz = storetime.zone(domain)
    first, today = _month(q, tz)
    by_day = {}
    for r in drafts(domain, ('draft', 'approved', 'scheduled', 'published')):
        if r['planned_at']:
            by_day.setdefault(storetime.date_of(r['planned_at'], tz), []).append(r)
    prev = (first - datetime.timedelta(days=1)).replace(day=1)
    nxt = (first + datetime.timedelta(days=32)).replace(day=1)

    def link(d):
        return E('/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar', month=d.strftime('%Y-%m'))))

    sel = q.get('item', '')

    def item(r):
        href = '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar', month=first.strftime('%Y-%m'),
                                                         item=r['id']))
        drag = '' if r['status'] == 'published' else ' draggable="true" data-id="%d"' % r['id']
        return '<a class="ca-item ca-%s%s%s" href="%s"%s%s>%s</a>' % (
            E(r['draft_type']), ' cal-sel' if str(r['id']) == sel else '', ' cal-pending' if r['status'] == 'draft' else '',
            E(href), ' title="Needs your approval"' if r['status'] == 'draft' else '', drag, E(r['title'] or 'Untitled'))

    cells = ''
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(first.year, first.month):
        for day in week:
            items = ''.join(item(r) for r in by_day.get(day, []))
            cells += '<div class="ca-day%s%s"%s><span class="ca-num">%d</span>%s</div>' % (
                '' if day.month == first.month else ' ca-out', ' ca-today' if day == today else '',
                ' data-day="%s"' % day.isoformat() if day >= today else '', day.day, items)
    heads = ''.join('<div class="ca-dow">%s</div>' % d for d in ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'))
    import content_export
    import content_setup
    import content_calendar
    note = content_setup.batch_note(domain) + content_export.bar(domain) + content_calendar.connect_box(domain) + ('' if by_day else (
        '<p class="ca-note">Planned drafts appear here on their day, in your store\'s time zone (%s). Dashed ones '
        'still need your approval.</p>' % E(storetime.abbrev(tz))))
    side = ''
    if sel.isdigit():
        import content_calendar
        back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar', month=first.strftime('%Y-%m'),
                                                         item=sel))
        side = content_calendar.panel(domain, int(sel), DRAFT_TYPES, back)
    return ('<div class="ca-cal-bar"><a class="ca-nav" href="%s" aria-label="Previous month">&#8249;</a>'
            '<h2>%s</h2><a class="ca-nav" href="%s" aria-label="Next month">&#8250;</a></div>%s'
            '<div class="cal-wrap%s"><div class="ca-cal" id="ca-cal">%s%s</div>%s</div>%s%s') % (
        link(prev), first.strftime('%B %Y'), link(nxt), note, ' cal-open' if side else '', heads, cells, side,
        content_calendar.legend(DRAFT_TYPES), content_calendar.drag_script(domain))


def page(q):
    if not enabled():
        return 404, '<h1>Not found</h1>'
    init()
    domain = _store(q)
    if not domain:
        import accounts
        import scheduler
        stores = [d for d in accounts.visible(scheduler.scannable()) if accounts.can_see(d)]
        links = ''.join('<li><a href="%s">%s</a></li>' % (
            E('/content?' + urllib.parse.urlencode(dict(d=d))), E((db.brand(d) or {}).get('brand_name') or d))
            for d in stores)
        return 200, ('<div class="plain-page" data-rail-page="content">%s'
                     '<p class="page-description">%s</p>%s</div>') % (
            title(), 'Which store?' if links else 'Add a store first.',
            '<ul class="ca-pick">%s</ul>' % links if links else '')
    view = q.get('view', 'inbox')
    ln = lane(q, domain)
    import content_plan
    import content_setup
    if content_plan.locked(domain):
        return 200, ('<div class="ca-page" data-rail-page="content" data-rail-lane="%s" data-rail-store="%s">%s'
                     '<div class="ca-empty"><p>%s</p></div></div>') % (ln, E(domain), title(ln), content_plan.UPGRADE)
    if view == 'setup' or not content_setup.done(domain):
        name = (db.brand(domain) or {}).get('brand_name') or domain
        return 200, ('<div class="ca-page" data-rail-page="content" data-rail-lane="%s" data-rail-store="%s" '
                     'data-rail-name="%s">%s%s<section class="ca-view">%s</section></div>') % (
            ln, E(domain), E(name), title(ln), _tabs(domain, 'setup', ln) if content_setup.done(domain) else '',
            content_setup.page(domain, q))
    if view == 'draft':
        import content_review
        inner = content_review.page(domain, q, None, DRAFT_TYPES)
        if inner is None:
            return 404, '<h1>Draft not found</h1>'
        name = (db.brand(domain) or {}).get('brand_name') or domain
        return 200, ('<div class="ca-page" data-rail-page="content" data-rail-lane="%s" data-rail-store="%s" '
                     'data-rail-name="%s">%s%s<section class="ca-view">%s</section></div>') % (
            ln, E(domain), E(name), title(ln), _tabs(domain, 'inbox', ln), inner)
    if view not in dict(LANE_VIEWS[ln]):
        view = 'inbox'
    import content_board                      # board, week and live feed: Kelian's pick, 16 Oct 2026
    inner = {'inbox': lambda: content_board.board(domain, q, ln), 'calendar': lambda: content_board.week(domain, q),
             'published': lambda: (__import__('stories_hub').panel(domain, q) if ln == 'articles' else '') +
             content_board.live(domain, ln),
             'results': lambda: __import__('agent_review').page(domain, ln)}[view]()
    name = (db.brand(domain) or {}).get('brand_name') or domain
    return 200, ('<div class="ca-page" data-rail-page="content" data-rail-lane="%s" data-rail-store="%s" '
                 'data-rail-name="%s">%s%s<section class="ca-view">%s</section></div>') % (
        ln, E(domain), E(name), title(ln), _tabs(domain, view, ln), inner)


def title(ln=None):
    """The agent's name as on the pricing page: two sparkles and the violet-to-blue name. With a lane, that
    agent's own name (Product page fixes / AEO articles)."""
    return ('<h1 class="ca-title"><svg class="ca-spark" viewBox="0 0 20 20" aria-hidden="true"><defs>'
            '<linearGradient id="ca-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c3aed"/>'
            '<stop offset="1" stop-color="#2f80ff"/></linearGradient></defs>'
            '<path class="ca-spark-big" d="M8 2.5l1.5 4.2 4.2 1.5-4.2 1.5L8 13.9 6.5 9.7 2.3 8.2l4.2-1.5z" fill="url(#ca-grad)"/>'
            '<path class="ca-spark-small" d="M15 11.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" fill="url(#ca-grad)"/></svg>'
            '<span class="ca-name">%s</span></h1>') % E(dict(LANES).get(ln, NAME))


CSS = """
.ca-page{max-width:1320px;margin:0 auto;padding:0 0 60px}
.ca-page h1.ca-title{display:flex;align-items:center;gap:10px}
.ca-spark{width:24px;height:24px;flex:none;overflow:visible}
.ca-spark-big{transform-origin:8px 8.2px;animation:ca-spark 2.8s ease-in-out infinite}
.ca-spark-small{transform-origin:15px 14.3px;animation:ca-spark 2.8s ease-in-out 1.4s infinite}
@keyframes ca-spark{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(.82);opacity:.75}}
@media (prefers-reduced-motion:reduce){.ca-spark-big,.ca-spark-small{animation:none}}
.ca-name{background-image:linear-gradient(90deg,#7c3aed,#2f80ff);-webkit-background-clip:text;background-clip:text;color:transparent}
.ca-page h1{font-size:24px;font-weight:700;margin:4px 0 18px}
.ca-tabs{display:inline-flex;gap:2px;padding:3px;border-radius:10px;background:#eef2f8;margin-bottom:22px}
.ca-tabs a{padding:7px 16px;border-radius:8px;font-size:14px;font-weight:600;color:#586579;text-decoration:none}
.ca-tabs a:hover{color:#0b1b35}
.ca-tabs a[aria-current]{background:#ffffff;color:#0b1b35;box-shadow:0 1px 2px rgba(11,27,53,.12)}
.ca-empty{border:1px dashed #d5dbe5;border-radius:12px;padding:40px 24px;text-align:center;color:#586579;font-size:15px;background:#ffffff}
.ca-empty p{max-width:520px;margin:0 auto;line-height:1.55}
.ca-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.ca-list li{display:flex;align-items:center;gap:12px;border:1px solid #e6e9ef;border-radius:10px;background:#ffffff;padding:14px 18px}
.opp-agent-form{display:none}
.opp-btn.opp-agent{margin-left:auto;background:#0b1b35;border-color:#0b1b35;color:#ffffff;text-decoration:none}
.opp-btn.opp-busy{opacity:.7;cursor:progress}
.ca-used{margin:-10px 0 14px;font-size:13.5px;color:#586579}
.ca-chips{display:flex;gap:8px;margin:0 0 14px}
.ca-chips a{padding:6px 12px;border:1px solid #e6e9ef;border-radius:999px;background:#ffffff;font-size:13.5px;font-weight:600;color:#586579;text-decoration:none}
.ca-chips a span{margin-left:4px;color:#8a94a3;font-weight:500}
.ca-chips a[aria-current]{border-color:#0b1b35;color:#0b1b35}
.ca-list li.ca-card{align-items:flex-start;position:relative;cursor:pointer}
.ca-list li.ca-card:hover{border-color:#0b1b35}
.ca-card .ca-open::after{content:"";position:absolute;inset:0;border-radius:inherit}
.ca-card .ca-actions{position:relative;z-index:1}
.ca-thumb{width:48px;height:48px;border-radius:8px;object-fit:cover;flex:none;background:#eef2f8}
.ca-main{flex:1;min-width:0}
.ca-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ca-head strong,.ca-open{font-size:15px;font-weight:700;color:#0b1b35;text-decoration:none}
.ca-open:hover{text-decoration:underline}
.ca-meta{margin:6px 0 0;font-size:13px;color:#586579}
.ca-gap{margin:6px 0 0;font-size:13px;color:#9a3412}
.ca-actions{display:flex;gap:8px;flex:none}
.ca-actions form{margin:0}
.ca-btn{padding:7px 14px;border:1px solid #d5dbe5;border-radius:8px;background:#ffffff;font-family:inherit;font-size:13.5px;font-weight:600;color:#0b1b35;cursor:pointer}
.ca-btn:hover{border-color:#0b1b35}
.ca-btn.ca-primary{background:#0b1b35;border-color:#0b1b35;color:#ffffff}
.ca-btn[disabled]{opacity:.45;cursor:not-allowed}
@media (max-width:720px){.ca-list li.ca-card{flex-wrap:wrap}.ca-actions{width:100%}}
.ca-type{font-size:12px;font-weight:600;padding:4px 10px;border-radius:7px;background:#eef2f8;color:#0b1b35}
.ca-cal-bar{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.ca-cal-bar h2{font-size:18px;font-weight:700;margin:0;min-width:170px;text-align:center}
.ca-nav{display:grid;place-items:center;width:32px;height:32px;border:1px solid #e6e9ef;border-radius:8px;background:#ffffff;color:#0b1b35;text-decoration:none;font-size:18px}
.ca-note{color:#586579;font-size:13.5px;margin:0 0 12px}
.ca-cal{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:1px solid #e6e9ef;border-radius:12px;overflow:hidden;background:#ffffff}
.ca-dow{padding:8px 10px;font-size:12px;font-weight:600;color:#586579;background:#f4f6fa;border-bottom:1px solid #e6e9ef}
.ca-day{min-height:104px;padding:6px 8px;border-right:1px solid #eef1f5;border-bottom:1px solid #eef1f5;display:flex;flex-direction:column;gap:4px}
.ca-day:nth-child(7n){border-right:0}
.ca-out{background:#fafbfc}.ca-out .ca-num{color:#a9b1bd}
.ca-num{font-size:12.5px;font-weight:600;color:#1a2436}
.ca-today .ca-num{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#0b1b35;color:#ffffff}
.ca-pick{list-style:none;padding:0;margin:16px 0 0;display:grid;gap:8px;max-width:420px}
.ca-pick a{display:block;padding:12px 14px;border:1px solid #e6e9ef;border-radius:10px;background:#ffffff;color:#0b1b35;font-weight:600;text-decoration:none}
.ca-pick a:hover{border-color:#0b1b35}
.ca-item{display:block;font-size:12px;font-weight:500;padding:3px 6px;border-radius:5px;background:#e7eefb;color:#0b1b35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media (max-width:720px){.ca-day{min-height:64px}.ca-item{font-size:0;height:6px;padding:0}}
"""


# ---- Day 11: "Draft fix" from an Opportunity card ------------------------------

DRAFTERS = ('product_fix', 'faq', 'comparison', 'guide')   # types drafts.py can write today


def existing_draft(domain, kind, key):
    """The newest draft (not rejected) already made for this Opportunity, or None."""
    init()
    return db.one('SELECT d.id FROM content_drafts d JOIN content_briefs b ON b.id=d.brief_id '
                  "WHERE d.store_domain=? AND b.opportunity_kind=? AND b.opportunity_key=? AND d.status!='rejected' "
                  'ORDER BY d.id DESC LIMIT 1', (domain, kind, key))


def covered(domain):
    """(draft type, product handle) pairs that already have an open draft: one rewrite per page at a time."""
    import json
    out = set()
    for r in db.all_("SELECT d.draft_type, b.target_id FROM content_drafts d LEFT JOIN content_briefs b ON b.id=d.brief_id "
                     "WHERE d.store_domain=? AND d.status IN ('draft','approved','scheduled')", (domain,)):
        if r['target_id'] and r['draft_type'] in ('product_fix', 'faq'):
            out.add((r['draft_type'], r['target_id']))
    return out


def draft_for(domain, kind, key, avoid=None, reuse=False, only=None):
    """Brief -> pick a type -> draft -> fact check -> Inbox. Returns (draft id, None) or (None, reason).
    Costs a fraction of a cent (two or three helper-model calls)."""
    import briefs
    import catalog_facts
    import drafts as _drafts
    import llm
    if not catalog_facts.get(domain):
        catalog_facts.build(domain)              # first draft for this store: read its catalog once
    b = briefs.build(domain, kind, key)
    if not b:
        return None, 'The agent can\'t write a fix for this kind of opportunity.'
    import content_setup
    rules = content_setup.get(domain)
    b['products'] = [p for p in b['products'] if p['handle'] not in set(rules['leave_alone'])]
    if not b['products'] and kind != 'topic':
        return None, 'You asked the agent to leave the products in this opportunity alone.'
    allowed = content_setup.allowed_types(domain)
    usage = llm.Usage()
    import content_plan
    chosen = briefs.choose_types(b, usage=usage)
    if only:
        # The monthly writer (monthly_articles.py) asks for an article: keep the article types the rules chose,
        # then fall back to a guide or a comparison so a question that fits one still gets one.
        chosen = [(t, why) for t, why in chosen if t in only] + [
            (t, why) for t, why in (('guide', 'Monthly article: a buying guide that answers this buyer question.'),
                                    ('comparison', 'Monthly article: a comparison for buyers choosing between options.'))
            if t in only and t not in [c for c, _ in chosen]]
    fitting = [(t, why) for t, why in chosen if t in DRAFTERS and t in allowed
               and content_plan.can_draft(domain, t)]
    picks = [(t, why) for t, why in fitting
             if not (avoid and b['products'] and (t, b['products'][0]['handle']) in avoid)]
    if fitting and not picks and not reuse:
        return None, COVERED
    if not picks:
        if reuse and avoid and b['products']:
            # Every fitting type already has an open draft for this page: open that one, don't write a rival.
            row = db.one("SELECT d.id FROM content_drafts d JOIN content_briefs b ON b.id=d.brief_id WHERE d.store_domain=? "
                         "AND b.target_id=? AND d.status IN ('draft','approved','scheduled') ORDER BY d.id DESC LIMIT 1",
                         (domain, b['products'][0]['handle']))
            if row:
                return row['id'], None
        return None, 'The kinds of page that fit this opportunity are switched off in Settings.'
    errors = []
    for t, why in picks:
        try:
            res = getattr(_drafts, t)(b, usage=usage)
        except ValueError as e:              # e.g. no stated facts, or too few products to compare
            errors.append(str(e))
            continue
        except llm.LLMError as e:
            return None, 'The writing service didn\'t answer (%s). Try again in a minute.' % e
        if t == 'product_fix':
            _limit_fix(res, set(rules['allowed']))
        res['why'] = why
        import selfreview
        res['review'] = selfreview.review(res, t, b, usage=usage)
        if res['review'] and not res['review']['passed'] and res['review'].get('issues'):
            # One rewrite with the editor's notes (18 Oct 2026). The drafter runs its fact check again, so a
            # rewrite can't bring back an invented fact; the better-graded version is kept.
            try:
                res2 = getattr(_drafts, t)(dict(b, editor_notes=res['review']['issues']), usage=usage)
                if t == 'product_fix':
                    _limit_fix(res2, set(rules['allowed']))
                res2['why'] = why
                res2['review'] = selfreview.review(res2, t, b, usage=usage)
                score = lambda r: sum((r.get('review') or {}).get('scores', {}).values())
                if res2['review'] and score(res2) > score(res):
                    res2['rewritten'] = True
                    res = res2
            except (ValueError, llm.LLMError):
                pass
        return _drafts.save(briefs.save(b, t), b, res, t, usage=usage), None
    return None, errors[0] if errors else 'Nothing the agent can write fits this opportunity yet.'


COVERED = 'A draft for this page already covers it.'
# Product pages go live when the merchant puts them there (drag to Live); articles keep a calendar slot.
PAGE_TYPES = ('product_fix', 'faq')
ARTICLE_TYPES = ('comparison', 'guide')


def _live_act(q, form):
    """golive: approve (same checks: gaps, the month's allowance), then publish to Shopify. Shopify must be
    connected: Live means live on the store. unlive: take it back down (Shopify undo) and return it to Ready.
    Kelian, 16 Oct 2026: the merchant chooses what goes live by dragging it there."""
    import accounts
    import shopify_connect
    domain = form.get('d', '')
    try:
        did = int(form.get('id', ''))
    except ValueError:
        return 400, '<h1>Bad request</h1>'
    row = db.one('SELECT * FROM content_drafts WHERE id=? AND store_domain=?', (did, domain))
    if not row or not accounts.can_see(domain):
        return 400, '<h1>Bad request</h1>'
    back = form.get('back', '')
    if not back.startswith('/content?'):
        back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='inbox'))
    if form['action'] == 'unlive':
        if row['status'] == 'published':
            try:
                shopify_connect.undo(domain, did)
            except shopify_connect.ShopifyError as e:
                return 409, '<h1>Couldn\'t take it down</h1><p>%s</p>' % E(str(e))
        import time
        db.write("UPDATE content_drafts SET status='draft', approved_at=NULL, approved_by=NULL, planned_at=NULL, "
                 "updated_at=? WHERE id=?", (time.time(), did))
        return 303, back
    if row['status'] == 'published':
        return 303, back
    if not (shopify_connect.configured() and shopify_connect.connection(domain)):
        # Live means live on the store (Kelian, 16 Oct): no Shopify, no going live.
        return 409, ('<h1>Connect Shopify first</h1><p>Pages go live on your store through Shopify. Connect it under '
                     'Settings, Shopify.</p>')
    wrong = shopify_connect.mismatch(domain)
    if wrong:
        return 409, ('<h1>Wrong Shopify store</h1><p>This is connected to %s, which isn\'t %s. Reconnect under '
                     'Settings, Shopify.</p>' % (E(wrong), E(domain)))
    if row['status'] not in ('approved', 'scheduled'):
        code, out = _act(q, dict(d=domain, id=str(did), status='approved', back=back))
        if code != 303:
            return code, out
    user = accounts.current()
    try:
        shopify_connect.publish(domain, did, by=user['email'] if user else None)
    except shopify_connect.ShopifyError as e:
        return 409, '<h1>Shopify didn\'t take it</h1><p>%s It\'s approved and waiting.</p>' % E(str(e))
    db.write('UPDATE content_drafts SET planned_at=NULL WHERE id=? AND status!=?', (did, 'published'))
    return 303, back


def _limit_fix(res, allowed):
    """Undo the parts of a product-page fix the merchant didn't allow."""
    current = res.get('current') or {}
    if 'titles' not in allowed:
        res['title'] = current.get('title', res['title'])
    if 'specs' not in allowed:
        res['spec_table'] = []
    if 'descriptions' not in allowed:
        res['description_html'] = ''.join('<p>%s</p>' % E(t) for t in current.get('description') or [])


def opportunity_button(domain, r):
    """The card's agent button, for the card's action row: (button html, form html to place outside that form).
    The button points at its own form with form="...", since forms can't nest."""
    import briefs
    if not enabled() or r['type'] not in briefs.BRIEFABLE:
        return '', ''
    import content_plan
    if content_plan.locked(domain):
        return '<a class="opp-btn" href="/settings" title="Included from the Growth plan">Draft fix (Growth)</a>', ''
    row = existing_draft(domain, r['type'], r['key'])
    if row:
        return '<a class="opp-btn opp-agent" href="%s">Open draft</a>' % E(
            '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=row['id']))), ''
    fid = 'agent-%08x' % (hash((r['type'], r['key'])) & 0xffffffff)
    button = '<button class="opp-btn opp-agent" form="%s">Draft fix</button>' % fid
    form = ('<form id="%s" class="opp-agent-form" method="post" action="/content" onsubmit="var b=document.querySelector('
            '\'[form=%s]\');b.disabled=true;b.classList.add(\'opp-busy\');pLoad(\'Drafting your fix\',30);">'
            '<input type="hidden" name="d" value="%s"><input type="hidden" name="action" value="draft">'
            '<input type="hidden" name="kind" value="%s"><input type="hidden" name="key" value="%s"></form>') % (
        fid, fid, E(domain), E(r['type']), E(r['key']))
    return button, form


# ---- Day 12: export -----------------------------------------------------------

def export(q):
    """(200, zip bytes, filename) or (code, html, None). Records what was exported."""
    import accounts
    import content_export
    if not enabled():
        return 404, '<h1>Not found</h1>', None
    domain = q.get('d', '')
    if not domain or not accounts.can_see(domain):
        return 404, '<h1>Not found</h1>', None
    data, ids, counts = content_export.build(domain, include_exported=bool(q.get('all')))
    if not data:
        return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='calendar')), None
    content_export.mark(ids)
    stamp = storetime.label(__import__('time').time(), storetime.zone(domain), '%Y-%m-%d')
    return 200, data, 'produkto-%s-%s.zip' % (domain.split('.')[0], stamp)



# ---- Shopify: connect, publish, undo -----------------------------------------------

def _shopify_act(domain, form):
    import accounts
    import shopify_connect
    if not accounts.can_see(domain):
        return 400, '<h1>Bad request</h1>'
    action = form.get('action')
    settings = lambda **k: '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='shopify', **k))
    if action == 'shopify_connect':
        shop = shopify_connect.clean_shop(form.get('shop', ''))
        if not shop or not shopify_connect.configured():
            return 303, settings(error='Type your store\'s address, like your-store.myshopify.com.')
        want = shopify_connect.expected_shop(domain)
        if want and shop != want:
            return 303, settings(error='%s isn\'t %s\'s Shopify store. Its address is %s.' % (shop, domain, want))
        return 303, shopify_connect.install_url(domain, shop)
    if action == 'shopify_disconnect':
        shopify_connect.disconnect(domain)
        return 303, settings()
    try:
        did = int(form.get('id', ''))
    except ValueError:
        return 400, '<h1>Bad request</h1>'
    back = form.get('back', '')
    if not back.startswith('/content?'):
        back = '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))
    user = accounts.current()
    if action == 'store_preview':
        wrong = shopify_connect.mismatch(domain)
        sep = '&' if '?' in back else '?'
        if wrong:
            return 303, back + sep + urllib.parse.urlencode(dict(error='This is connected to %s, which isn\'t %s.' % (wrong, domain)))
        try:
            link = shopify_connect.preview(domain, did)
        except shopify_connect.ShopifyError as e:
            return 303, back + sep + urllib.parse.urlencode(dict(error=str(e)))
        return 303, back + sep + urllib.parse.urlencode(dict(store_preview=link))
    try:
        if action == 'publish':
            shopify_connect.publish(domain, did, by=user['email'] if user else None)
        else:
            shopify_connect.undo(domain, did)
    except shopify_connect.ShopifyError as e:
        sep = '&' if '?' in back else '?'
        return 303, back + sep + urllib.parse.urlencode(dict(error=str(e)))
    return 303, back


def _stories_act(domain, form):
    """The stories page (Live tab of AEO articles) and the Instagram photos (Settings > Look and lessons)."""
    import shopify_connect
    import social_photos
    import stories_hub
    a = form['action']
    live = '/content?' + urllib.parse.urlencode(dict(d=domain, lane='articles', view='published'))
    look = '/content?' + urllib.parse.urlencode(dict(d=domain, lane='articles', view='setup', step='look'))
    try:
        if a == 'stories_publish':
            stories_hub.publish(domain)
        elif a == 'stories_remove':
            stories_hub.take_down(domain)
        elif a == 'stories_instagram':
            stories_hub.set_instagram(domain, form.get('on') == '1')
            stories_hub.sync(domain)
        elif a == 'instagram_handle':
            social_photos.set_handle(domain, form.get('handle', ''))
            return 303, look + '#instagram'
        else:
            social_photos.start(domain)
            return 303, look + '#instagram'
    except shopify_connect.ShopifyError as e:
        return 303, live + '&' + urllib.parse.urlencode(dict(error=str(e)[:200]))
    except ValueError as e:
        return 303, (look if a.startswith('instagram') else live) + '&' + urllib.parse.urlencode(dict(error=str(e)[:200])) + \
            ('#instagram' if a.startswith('instagram') else '')
    return 303, live


def shopify_callback(q):
    """GET /shopify/callback: Shopify sends the merchant back here after they approve access."""
    import accounts
    import shopify_connect
    user = accounts.current()
    try:
        domain = shopify_connect.finish(q, user['email'] if user else None)
    except shopify_connect.ShopifyError as e:
        return 200, '<div class="ca-page">%s<div class="ca-empty"><p>%s</p></div></div>' % (title(), E(str(e)))
    return 303, '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='shopify', connected=1))


def publish_buttons(domain, row, back):
    """Publish / Undo / Connect, for the draft view and the calendar panel."""
    import shopify_connect
    if not shopify_connect.configured():
        return ''
    hidden = lambda action: ('<input type="hidden" name="d" value="%s"><input type="hidden" name="id" value="%d">'
                             '<input type="hidden" name="action" value="%s"><input type="hidden" name="back" value="%s">'
                             % (E(domain), row['id'], action, E(back)))
    if row['status'] == 'published':
        live = ('<a class="ca-btn" href="%s" target="_blank" rel="noopener">View live</a>' % E(row['live_url'])) \
            if row['live_url'] else ''
        undo = ('<form method="post" action="/content">%s<button class="ca-btn">Undo</button></form>' % hidden('unpublish')) \
            if shopify_connect.last_publish(row['id']) else ''
        return live + undo
    if row['status'] not in ('approved', 'scheduled'):
        return ''
    if not shopify_connect.connection(domain):
        return '<a class="ca-btn" href="%s">Connect Shopify to publish</a>' % E(
            '/content?' + urllib.parse.urlencode(dict(d=domain, view='setup', step='shopify')))
    return ('<form method="post" action="/content" onsubmit="this.querySelector(\'button\').disabled=true;'
            'this.querySelector(\'button\').textContent=\'Publishing\u2026\';">%s<button class="ca-btn ca-primary">'
            'Publish now</button></form>') % hidden('publish')
