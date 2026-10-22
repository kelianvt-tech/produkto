"""The agent's Drafts board, week calendar and Live feed.

Chosen by Kelian on 16 Oct 2026 from five prototypes (mvp/design/agent-variations/):
  Drafts    version 4, a board: Needs your facts -> Ready to review -> Scheduled -> Live.
            Drag a card from Ready to Scheduled to approve it, or back to unschedule it.
            Clicking a card opens it in a sheet beside the board.
  Calendar  version 4, one week of day columns; drag a card to another day to move it.
  Live      version 3, a feed of what went live, newest first, with View and Undo.

Every drag posts the same form the buttons do, so the server's checks (gaps block
approval, past days refused, the plan's monthly allowance) apply unchanged.
"""
import datetime as dt
import json
import urllib.parse
from html import escape as E

import db
import storetime

COLS = (('facts', 'Needs your facts', 'var(--cb-warn)', 'Answer a question to move it on'),
        ('ready', 'Ready to review', 'var(--cb-accent)', 'Read it, then drag it to Live'),
        ('scheduled', 'Scheduled', 'var(--cb-ok)', 'Comparisons and guides, on their date'),
        ('live', 'Live', 'var(--cb-ink)', 'On your store. Drag back to take it down'))
PAGE_TYPES = ('product_fix', 'faq')        # go live when dropped on Live (16 Oct); articles can be scheduled
ARTICLE_TYPES = ('comparison', 'guide')
# Two agents since 18 Oct 2026 (Kelian): Product page fixes and AEO articles, each its own sub-tab. A lane's
# board shows only its own drafts; product fixes have no Scheduled column, they go Ready -> Live.
LANE_TYPES = {'fixes': PAGE_TYPES + ('collection',), 'articles': ARTICLE_TYPES}
LANE_COLS = {'fixes': ('facts', 'ready', 'live'), 'articles': ('facts', 'ready', 'scheduled', 'live')}
HINTS = {('fixes', 'ready'): 'Read it, then drag it to Live', ('articles', 'ready'): 'Read it, then drag it to Scheduled'}


def _rows(domain, lane=None):
    import content_agent
    out = []
    for r in content_agent.drafts(domain, ('draft', 'approved', 'scheduled', 'published')):
        if lane and r['draft_type'] not in LANE_TYPES[lane]:
            continue
        body, _ = content_agent._latest(r['id'])
        gaps = content_agent.placeholders(body)
        approved = r['status'] in ('approved', 'scheduled')
        # Live means on the store. An approved product page that isn't published yet waits in Ready.
        col = ('live' if r['status'] == 'published' else 'scheduled' if approved and r['draft_type'] not in PAGE_TYPES
               else 'facts' if gaps else 'ready')
        out.append(dict(row=r, body=body, gaps=gaps, col=col))
    return out


def _url(domain, **kw):
    return '/content?' + urllib.parse.urlencode(dict(d=domain, **kw))


def _tile(domain, it, tz, href, sel, cal=False):
    import content_agent
    r, body = it['row'], it['body']
    p = body.get('product') or {}
    img = ('<img class="cb-thumb" src="%s" alt="" loading="lazy">' % E(p['image'])) if p.get('image') \
        else '<span class="cb-thumb"></span>'
    import content_review
    n = len(content_review.gaps(body)) or it['gaps'] if it['col'] == 'facts' else 0   # distinct questions
    bar = ('<span class="cb-gapbar" aria-label="%d facts needed">%s</span>' % (
        n, ''.join('<i%s></i>' % ('' if k < n else ' class="cb-off"') for k in range(max(3, n)))
    )) if it['col'] == 'facts' else ''
    when = ('Live' if r['status'] == 'published' else 'Approved' if r['status'] in ('approved', 'scheduled')
            and it['col'] == 'ready' else storetime.date_of(r['planned_at'], tz).strftime('%b %-d') if r['planned_at'] else 'No date')
    # Board: Ready, Scheduled and Live cards move. Calendar (articles only): anything not live can change day.
    # Needs-facts cards drag too (17 Oct), so they feel like cards; a drop says which facts to answer first.
    movable = it['col'] != 'live' if cal else it['col'] in ('facts', 'ready', 'scheduled', 'live')
    kind = 'page' if r['draft_type'] in PAGE_TYPES else 'article'
    drag = ' draggable="true" data-id="%d" data-kind="%s" data-facts="%d"' % (r['id'], kind, it['gaps']) if movable else ''
    if not cal:
        # Board card (18 Oct 2026, mockup "1 · Board"): photo, the product or article, what changes, one status.
        change = {'product_fix': 'New title and description', 'faq': 'FAQ on the product page',
                  'comparison': 'New comparison page', 'guide': 'New buying guide'}.get(r['draft_type'], '')
        date = storetime.date_of(r['planned_at'], tz).strftime('%b %-d') if (r['planned_at'] and kind == 'article') else ''
        return ('<a class="cb-tile cb-card2" href="%s"%s%s><span class="cb-top">%s<span><strong>%s</strong>'
                '<span class="cb-chg">%s</span></span></span>%s<span class="cb-foot">%s<span>%s</span></span></a>') % (
            E(href), ' aria-current="true"' if sel == r['id'] else '', drag, _img(it, 'cb-thumb'), E(_name(it)),
            E(change), bar, _flag(it), E(date))
    return ('<a class="cb-tile%s" href="%s"%s%s><span class="cb-top">%s<strong>%s</strong></span>%s'
            '<span class="cb-meta"><span class="cb-type cb-t-%s"><i></i>%s</span><span>%s</span></span></a>') % (
        ' cb-pend' if cal and r['status'] == 'draft' else '', E(href),
        ' aria-current="true"' if sel == r['id'] else '', drag, img, E(r['title'] or 'Untitled'), bar,
        E(r['draft_type']), E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), E(when))


def _sel(q):
    try:
        return int(q.get('id', ''))
    except ValueError:
        return None


# ---- the sheet: one draft beside the board or the week ---------------------------------

def sheet(domain, it, tz, back, close):
    import content_agent
    import content_review
    r, body = it['row'], it['body']
    stage = ['facts', 'ready', 'scheduled', 'live'].index(it['col'])
    when = ('goes live %s' % storetime.label(r['planned_at'], tz, '%a %b %-d, %H:%M')) if r['planned_at'] else 'no date yet'

    def post(status, label, cls=''):
        return ('<form method="post" action="/content"><input type="hidden" name="d" value="%s"><input type="hidden" '
                'name="id" value="%d"><input type="hidden" name="status" value="%s"><input type="hidden" name="back" '
                'value="%s"><button class="ca-btn %s">%s</button></form>') % (E(domain), r['id'], status, E(back), cls, label)

    def live(action, label, cls=''):
        return ('<form method="post" action="/content"><input type="hidden" name="d" value="%s"><input type="hidden" '
                'name="id" value="%d"><input type="hidden" name="action" value="%s"><input type="hidden" name="back" '
                'value="%s"><button class="ca-btn %s">%s</button></form>') % (E(domain), r['id'], action, E(back), cls, label)

    import shopify_connect
    shop = shopify_connect.configured() and bool(shopify_connect.connection(domain))
    connect = '<a class="ca-btn ca-primary" href="%s">Connect Shopify to put it live</a>' % E(
        _url(domain, view='setup', step='shopify'))
    article = r['draft_type'] not in PAGE_TYPES
    if it['col'] == 'facts':
        actions = post('rejected', 'Reject')
    elif it['col'] == 'ready':
        actions = post('rejected', 'Reject') + (post('approved', 'Schedule') if article else '') + (
            live('golive', 'Put live', 'ca-primary') if shop else connect)
    elif it['col'] == 'scheduled':
        actions = post('draft', 'Unschedule') + (live('golive', 'Put live', 'ca-primary') if shop else connect)
    elif r['status'] == 'published':
        actions = (('<a class="ca-btn" href="%s" target="_blank" rel="noopener">View live</a>' % E(r['live_url']))
                   if r['live_url'] else '') + live('unlive', 'Take it down')
    else:
        actions = live('unlive', 'Move back to Ready')
    after = ('<h4 class="cb-h">%s</h4>' % E(body['title'])) if body.get('title') else ''
    if r['draft_type'] in PAGE_TYPES and body.get('product'):   # 20 Oct: the fix on the store's real product page
        import product_preview
        cur = body.get('current') or {}
        title_note = ('<dl class="rv-dl"><dt>Title now</dt><dd class="rv-old">%s</dd><dt>New title</dt><dd class="rv-new">%s</dd></dl>'
                      % (E(cur.get('title') or ''), E(body.get('title') or cur.get('title') or ''))) \
            if r['draft_type'] == 'product_fix' and body.get('title') and body.get('title') != cur.get('title') else ''
        return ('<aside class="cb-sheet cb-sheet-split" aria-label="Draft"><header><div class="cb-sheet-top"><span class="cb-type cb-t-%s"><i></i>%s</span>'
                '<a class="cb-x" href="%s" aria-label="Close">&times;</a></div><h2>%s</h2><p class="cb-when">%s</p>'
                '<div class="cb-stage">%s</div></header><div class="cb-body cb-split"><aside class="cb-side">%s%s%s'
                '<p class="cb-more"><a href="%s" target="_blank" rel="noopener">Open the full page</a><br><a href="%s">Open the full view</a> '
                'to edit the text or read the editor\'s check.</p></aside><div class="cb-main">%s%s%s%s</div></div>'
                '<footer>%s</footer></aside>') % (
            E(r['draft_type']), E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), E(close),
            E(r['title'] or 'Untitled'), E(when),
            ''.join('<span class="%s">%s</span>' % ('cb-on' if i == min(stage, 2) else 'cb-past' if i < min(stage, 2) else '', s)
                    for i, s in enumerate(('Facts', 'Review', 'Live'))),
            title_note, content_review._gap_form(domain, r['id'], body, back=back), content_review.history_box(domain, r['id']),
            E('/content/fix-preview?' + urllib.parse.urlencode(dict(d=domain, id=r['id']))),
            E(_url(domain, view='draft', id=r['id'])),
            product_preview.toggle(domain, r['id']), content_review.editor_toolbar(domain, r['id'], body, kind='fix'),
            product_preview.frame(domain, r['id'], 900), content_review.editor(domain, r['id'], body, kind='fix'), actions)
    if content_review.has_preview(r, body):               # articles and comparisons (19 Oct): the styled preview, not raw HTML
        return ('<aside class="cb-sheet cb-sheet-split" aria-label="Draft"><header><div class="cb-sheet-top"><span class="cb-type cb-t-%s"><i></i>%s</span>'
                '<a class="cb-x" href="%s" aria-label="Close">&times;</a></div><h2>%s</h2><p class="cb-when">%s</p>'
                '<div class="cb-stage">%s</div></header><div class="cb-body cb-split"><aside class="cb-side">%s'
                '<p class="cb-more"><a href="%s" target="_blank" rel="noopener">Open full-page preview</a><br><a href="%s">Open the full view</a> '
                'to ask for changes, edit the text or read the editor\'s check.</p></aside><div class="cb-main">%s</div></div>'
                '<footer>%s</footer></aside>') % (
            E(r['draft_type']), E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), E(close),
            E(r['title'] or 'Untitled'), E(when),
            ''.join('<span class="%s">%s</span>' % ('cb-on' if i == stage else 'cb-past' if i < stage else '', s)
                    for i, s in enumerate(('Facts', 'Review', 'Scheduled', 'Live'))),
            content_review._gap_form(domain, r['id'], body, back=back) + (
                content_review.redesign_form(domain, r['id'], r, back) if body.get('layout') != 'article'
                else content_review.history_box(domain, r['id'])),
            E('/content/preview?' + urllib.parse.urlencode(dict(d=domain, id=r['id']))),
            E(_url(domain, view='draft', id=r['id'])),
            (content_review.editor_toolbar(domain, r['id'], body)
             + content_review.preview_frame(body, 900, domain=domain, did=r['id']) + content_review.editor(domain, r['id'], body))
            if body.get('layout') == 'article' else content_review.preview_frame(body, 900, domain=domain), actions)
    return ('<aside class="cb-sheet" aria-label="Draft"><header><div class="cb-sheet-top"><span class="cb-type cb-t-%s"><i></i>%s</span>'
            '<a class="cb-x" href="%s" aria-label="Close">&times;</a></div><h2>%s</h2><p class="cb-when">%s</p>'
            '<div class="cb-stage">%s</div></header><div class="cb-body">%s'
            '<h3>Now on your store</h3><div class="cb-before">%s</div><h3>With this draft</h3><div class="cb-doc">%s%s</div>'
            '<p><a href="%s">Open the full view</a> to edit the text or read the editor\'s check.</p></div>'
            '<footer>%s</footer></aside>') % (
        E(r['draft_type']), E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), E(close),
        E(r['title'] or 'Untitled'), E(when),
        ''.join('<span class="%s">%s</span>' % ('cb-on' if i == stage else 'cb-past' if i < stage else '', s)
                for i, s in enumerate(('Facts', 'Review', 'Scheduled', 'Live'))),
        content_review._gap_form(domain, r['id'], body, back=back),
        content_review._before(body, r['draft_type']), after, body.get('html', ''),
        E(_url(domain, view='draft', id=r['id'])), actions)


# ---- Drafts: the board ---------------------------------------------------------------

def board(domain, q, lane='fixes'):
    tz = storetime.zone(domain)
    items = _rows(domain, lane)
    sel = _sel(q)
    rejected = db.one("SELECT COUNT(*) n FROM content_drafts WHERE store_domain=? AND status='rejected'", (domain,))['n']
    cols = ''
    for key, label, colour, hint in COLS:
        if key not in LANE_COLS[lane]:
            continue
        hint = HINTS.get((lane, key), hint)
        mine = [it for it in items if it['col'] == key]
        cols += ('<section class="cb-col" data-col="%s"><header><i style="background:%s"></i><h2>%s</h2>'
                 '<span>%d</span></header><p class="cb-hint">%s</p>%s</section>') % (
            key, colour, E(label), len(mine), E(hint),
            ''.join(_tile(domain, it, tz, _url(domain, view='inbox', id=it['row']['id']), sel) for it in mine)
            or '<p class="cb-empty">Nothing here yet</p>')
    picked = next((it for it in items if it['row']['id'] == sel), None)
    head = _meters(domain, lane)
    note = ('<p class="cb-note">%s %s</p>' % ('Drag a card to Live to put it on your store, and back to take it down.'
            if lane == 'fixes' else 'Drag a card to Scheduled to approve it for its date, or straight to Live.',
            (('<a href="%s">%d rejected</a>' % (E(_url(domain, view='inbox', show='rejected')), rejected)) if rejected else '')))
    if q.get('show') == 'rejected':
        return _rejected(domain)
    import shopify_connect
    if not (shopify_connect.configured() and shopify_connect.connection(domain)):
        note = ('<div class="cb-connect"><p><b>Connect Shopify</b> so a card you drag to Live goes live on your store, '
                'and dragging it back takes it down.</p><a class="ca-btn ca-primary" href="%s">Connect Shopify</a></div>'
                % E(_url(domain, view='setup', step='shopify'))) + note
    elif shopify_connect.mismatch(domain):
        note = ('<div class="cb-connect"><p><b>Wrong Shopify store.</b> This is connected to %s, which doesn\'t have '
                '%s\'s products, so nothing can go live. Disconnect it and connect %s.</p>'
                '<a class="ca-btn ca-primary" href="%s">Fix in Settings</a></div>' % (
                    E(shopify_connect.mismatch(domain)), E(domain), E(shopify_connect.expected_shop(domain)),
                    E(_url(domain, view='setup', step='shopify')))) + note
    if not items:
        if lane == 'articles':
            return head + ('<div class="ca-empty"><p>No AEO articles yet. The agent writes them on the 1st of each '
                           'month from the buyer questions you\'re losing, and nothing goes live until you approve '
                           'it.</p></div>')
        return head + ('<div class="ca-empty"><p>No product page fixes yet. They appear here when you ask the agent to fix '
                'an Opportunity, and nothing goes to your store until you approve it.</p></div>')
    back = _url(domain, view='inbox', id=sel) if sel else _url(domain, view='inbox')
    flow = '<div class="cb-flow cb-n%d" id="cb-board">%s</div>' % (len(LANE_COLS[lane]), cols)
    if picked:
        # A clicked card opens full screen over the board (Kelian, 19 Oct 2026: "it should be full, covering the
        # whole screen, because I clicked on it. It's the most important."). Esc, the cross or the backdrop close it.
        close = _url(domain, view='inbox')
        return head + note + flow + ('<div class="cb-overlay" role="dialog" aria-modal="true" data-close="%s">%s</div>'
                                     '<script>(function(){var o=document.querySelector(".cb-overlay");if(!o)return;'
                                     'document.documentElement.style.overflow="hidden";var go=function(){location.href=o.dataset.close};'
                                     'document.addEventListener("keydown",function(e){if(e.key==="Escape")go()});'
                                     'o.addEventListener("click",function(e){if(e.target===o)go()});})();</script>') % (
            E(close), sheet(domain, picked, tz, back, close)) + _drag(domain, back)
    return head + note + flow + _drag(domain, back)


# ---- Drafts: review list + detail (chosen 18 Oct 2026, mvp/design/agent-pages-variations "2 · Review") ------
# Replaces the drag board for both agents: drafts listed by stage on the left, the selected one opened on the
# right with what changes, the facts it still needs, the editor's grades and its actions. Switching drafts
# happens in the page (no reload); actions post the same forms as before, so every server check still applies.

_SVG = {
    'ok': '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    'look': '<circle cx="12" cy="12" r="9"/><path d="M12 8v4.5M12 16h.01"/>',
}


def _svg(name):
    return '<svg class="rv-i" viewBox="0 0 24 24" aria-hidden="true">%s</svg>' % _SVG[name]


def _name(it):
    r, body = it['row'], it['body']
    if r['draft_type'] in PAGE_TYPES:
        return (body.get('product') or {}).get('title') or (r['title'] or '').rsplit(':', 1)[0]
    return r['title'] or 'Untitled'


def _flag(it):
    rev = it['body'].get('review') or {}
    if it['col'] == 'facts':
        import content_review
        n = len(content_review.gaps(it['body'])) or it['gaps']      # distinct questions, as the form counts them
        return '<span class="rv-flag rv-warn">%s%d fact%s needed</span>' % (_svg('look'), n, '' if n == 1 else 's')
    if it['col'] == 'live':
        return '<span class="rv-flag rv-ok">%sLive on your store</span>' % _svg('ok')
    if it['row']['status'] in ('approved', 'scheduled') and it['col'] == 'ready':
        return '<span class="rv-flag rv-ok">%sApproved, not live yet</span>' % _svg('ok')
    if rev and not rev.get('passed') and not it['body'].get('edited_at'):
        return '<span class="rv-flag rv-warn">%sWorth a closer look</span>' % _svg('look')
    return '<span class="rv-flag rv-ok">%sReady</span>' % _svg('ok')


def _img(it, cls=''):
    import json as _j
    body = it['body']
    p = body.get('product') or (body.get('products') or [{}])[0]
    src = p.get('image') if isinstance(p, dict) else ''
    return ('<img class="rv-img %s" src="%s" alt="" loading="lazy">' % (cls, E(src))) if src \
        else '<span class="rv-img %s"></span>' % cls


def _plain_html(html):
    import re
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


def _detail(domain, it, tz, back, lane):
    import content_agent
    import content_review
    import selfreview
    import shopify_connect
    r, body = it['row'], it['body']
    stage = dict(STAGE_LABELS)[it['col']]
    when = (storetime.label(r['planned_at'], tz, '%a %b %-d') if r['planned_at'] else '')

    def form(field, value, label, cls=''):
        return ('<form method="post" action="/content"><input type="hidden" name="d" value="%s"><input type="hidden" '
                'name="id" value="%d"><input type="hidden" name="%s" value="%s"><input type="hidden" name="back" '
                'value="%s"><button class="rv-btn %s">%s</button></form>') % (
            E(domain), r['id'], field, value, E(back), cls, label)
    linked = shopify_connect.configured() and bool(shopify_connect.connection(domain))
    wrong = linked and shopify_connect.mismatch(domain)
    golive = form('action', 'golive', 'Put live', 'rv-go') if (linked and not wrong) else (
        '<a class="rv-btn rv-go" href="%s">%s</a>' % (E(_url(domain, view='setup', step='shopify')),
                                                      'Fix the Shopify connection' if wrong else 'Connect Shopify to put it live'))
    article = r['draft_type'] not in PAGE_TYPES
    edit = '<a class="rv-btn" href="%s">Edit</a>' % E(_url(domain, view='draft', id=r['id']))
    reject = form('status', 'rejected', 'Reject', 'rv-quiet')
    if it['col'] == 'facts':
        actions = reject + edit
    elif it['col'] == 'ready':
        actions = reject + edit + '<span class="rv-sp"></span>' + (
            form('status', 'approved', 'Schedule', 'rv-go') if article else golive)
    elif it['col'] == 'scheduled':
        actions = form('status', 'draft', 'Unschedule', 'rv-quiet') + edit + '<span class="rv-sp"></span>' + golive
    else:
        actions = form('action', 'unlive', 'Take it down', 'rv-quiet') + '<span class="rv-sp"></span>' + (
            ('<a class="rv-btn rv-go" href="%s" target="_blank" rel="noopener">View live</a>' % E(r['live_url']))
            if r['live_url'] else '')

    if r['draft_type'] == 'product_fix':
        cur = body.get('current') or {}
        change = ('<dl class="rv-dl"><dt>Title now</dt><dd class="rv-old">%s</dd><dt>New title</dt><dd class="rv-new">%s</dd>'
                  '</dl>' % (E(cur.get('title') or ''), E(body.get('title') or cur.get('title') or '')))
        label = 'New description'
    else:
        change, label = '', ('FAQ' if r['draft_type'] == 'faq' else 'The page')
    import re
    doc = re.sub(r'\[ask merchant:[^\]]*\]', '<mark class="rv-gap">fact needed</mark>',
                 body.get('html') or body.get('description_html') or '')
    preview = '<div class="rv-sec"><h3>%s</h3><div class="rv-doc">%s</div></div>' % (label, doc)
    gaps = content_review._gap_form(domain, r['id'], body, back=back)
    rev = body.get('review') or {}
    grades = ''
    if rev.get('scores'):
        grades = '<div class="rv-grades">%s%s</div>' % (''.join(
            '<span>%s <b>%d/5</b></span>' % (E(lbl), rev['scores'].get(k, 0)) for k, lbl in selfreview.LABELS),
            ' <span class="rv-note">Graded on the first version, before your edits.</span>' if body.get('edited_at') else '')
        if rev.get('issues') and not rev.get('passed') and not body.get('edited_at'):
            grades += '<ul class="rv-issues">%s</ul>' % ''.join('<li>%s</li>' % E(x['problem']) for x in rev['issues'][:3])
    why = ('<p class="rv-why">%s</p>' % E(body['why'])) if body.get('why') else ''
    return ('<section class="rv-detail" data-detail="%d" aria-label="%s"%s><header class="rv-head">%s<div>'
            '<h2>%s</h2><div class="rv-meta"><span class="rv-type rv-t-%s"><i></i>%s</span><span class="rv-stage rv-s-%s">'
            '<i></i>%s</span>%s</div></div></header>%s%s%s%s%s<footer class="rv-bar">%s</footer></section>') % (
        r['id'], E(_name(it)), '', _img(it, 'rv-img-l'), E(_name(it)), E(r['draft_type']),
        E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])), it['col'], E(stage),
        ('<span class="rv-date">%s</span>' % E(when)) if (when and article) else '',
        why, change, gaps, preview, grades, actions)


STAGE_LABELS = (('facts', 'Needs your facts'), ('ready', 'Ready to review'), ('scheduled', 'Scheduled'),
                ('live', 'Live'))


def review(domain, q, lane='fixes'):
    tz = storetime.zone(domain)
    if q.get('show') == 'rejected':
        return _rejected(domain)
    items = _rows(domain, lane)
    order = [k for k in LANE_COLS[lane]]
    items.sort(key=lambda it: (order.index(it['col']) if it['col'] in order else 9, it['row']['planned_at'] or 0))
    sel = _sel(q)
    if not any(it['row']['id'] == sel for it in items):
        sel = next((it['row']['id'] for it in items if it['col'] != 'live'), items[0]['row']['id'] if items else None)
    head = _meters(domain, lane) + _notes(domain)
    if not items:
        empty = ('No AEO articles yet. The agent writes them on the 1st of each month from the buyer questions '
                 'you\'re losing, and nothing goes live until you approve it.' if lane == 'articles' else
                 'No product page fixes yet. They appear here when you ask the agent to fix an Opportunity, and '
                 'nothing goes to your store until you approve it.')
        return head + '<div class="ca-empty"><p>%s</p></div>' % E(empty) + REVIEW_CSS
    groups = ''
    for key, _ in STAGE_LABELS:
        mine = [it for it in items if it['col'] == key]
        groups += '<div class="rv-grp" data-col="%s">' % key
        if mine:
            groups += '<div class="rv-g"><span>%s</span><span class="rv-n">%d</span></div>' % (
                E(dict(STAGE_LABELS)[key]), len(mine))
        groups += ''.join(
            ('<a class="rv-it" href="%s" data-pick="%d" role="option" aria-selected="%s">%s<span class="rv-it-t">'
             '<span>%s</span>%s</span></a>') % (
                E(_url(domain, lane=lane, view='inbox', id=it['row']['id'])), it['row']['id'],
                'true' if it['row']['id'] == sel else 'false', _img(it), E(_name(it)), _flag(it)) for it in mine)
        groups += '</div>'
    rejected = db.one("SELECT COUNT(*) n FROM content_drafts WHERE store_domain=? AND status='rejected'", (domain,))['n']
    if rejected:
        groups += '<a class="rv-rej" href="%s">%d rejected</a>' % (
            E(_url(domain, lane=lane, view='inbox', show='rejected')), rejected)
    details = ''.join(_detail(domain, it, tz, _url(domain, lane=lane, view='inbox', id=it['row']['id']), lane)
                      .replace('data-detail="%d" aria-label' % it['row']['id'],
                               'data-detail="%d"%s aria-label' % (it['row']['id'], '' if it['row']['id'] == sel else ' hidden'))
                      for it in items)
    return head + ('<div class="rv"><nav class="rv-list" role="listbox" aria-label="Drafts">%s</nav>'
                   '<div class="rv-pane">%s</div></div>' % (groups, details)) + REVIEW_JS + REVIEW_CSS


def _notes(domain):
    import shopify_connect
    if not (shopify_connect.configured() and shopify_connect.connection(domain)):
        return ('<div class="cb-connect"><p><b>Connect Shopify</b> so you can put approved drafts live on your store, '
                'and take them down again.</p><a class="ca-btn ca-primary" href="%s">Connect Shopify</a></div>'
                % E(_url(domain, view='setup', step='shopify')))
    if shopify_connect.mismatch(domain):
        return ('<div class="cb-connect"><p><b>Wrong Shopify store.</b> This is connected to %s, which doesn\'t have '
                '%s\'s products, so nothing can go live. Disconnect it and connect %s.</p>'
                '<a class="ca-btn ca-primary" href="%s">Fix in Settings</a></div>' % (
                    E(shopify_connect.mismatch(domain)), E(domain), E(shopify_connect.expected_shop(domain)),
                    E(_url(domain, view='setup', step='shopify'))))
    return ''


REVIEW_JS = """<script>(function(){var list=document.querySelector('.rv-list');if(!list)return;
list.addEventListener('click',function(e){var a=e.target.closest('[data-pick]');if(!a||e.metaKey||e.ctrlKey)return;e.preventDefault();
 var id=a.getAttribute('data-pick');list.querySelectorAll('[data-pick]').forEach(function(x){x.setAttribute('aria-selected',x===a)});
 document.querySelectorAll('[data-detail]').forEach(function(d){d.hidden=d.getAttribute('data-detail')!==id});
 try{history.replaceState(null,'',a.href)}catch(_){}
 var p=document.querySelector('.rv-pane');if(p&&window.innerWidth<900)p.scrollIntoView({behavior:'smooth',block:'start'});});
document.addEventListener('keydown',function(e){if(e.target.closest('input,textarea,select'))return;if(e.key!=='j'&&e.key!=='k')return;
 var its=[].slice.call(list.querySelectorAll('[data-pick]')),i=its.findIndex(function(x){return x.getAttribute('aria-selected')==='true'});
 var n=its[Math.max(0,Math.min(its.length-1,i+(e.key==='j'?1:-1)))];if(n){e.preventDefault();n.click();n.focus();}});})();</script>"""


REVIEW_CSS = """<style>
.rv{--rv-text:#0b1b35;--rv-muted:#5b6577;--rv-faint:#7a8494;--rv-line:#e3e8ef;--rv-surface:#ffffff;--rv-raised:#f5f7fa;--rv-bg:#fafbfd;
 --rv-ok:#18804b;--rv-warn:#b45f06;--rv-blue:#2f6fdb;--rv-violet:#7a4fd6;--rv-guide:#c27618;--rv-cut:#b8432e;--rv-ink:#0b1b35;--rv-on-ink:#fff;--rv-focus:#2f6fdb;
 display:grid;grid-template-columns:340px minmax(0,1fr);border:1px solid var(--rv-line);border-radius:14px;background:var(--rv-surface);overflow:hidden;min-height:600px;color:var(--rv-text)}
html.dark .rv{--rv-text:#e4e8ee;--rv-muted:#a7b0bd;--rv-faint:#8a94a3;--rv-line:#262a30;--rv-surface:#16181c;--rv-raised:#1c1f24;--rv-bg:#121418;
 --rv-ok:#45d08c;--rv-warn:#e8a54a;--rv-blue:#7aa7ff;--rv-violet:#a58cf5;--rv-guide:#e8a54a;--rv-cut:#f0846f;--rv-ink:#e9edf3;--rv-on-ink:#0f1114;--rv-focus:#7aa7ff}
.rv-i{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;flex:none}
.rv-list{border-right:1px solid var(--rv-line);overflow:auto;max-height:78vh;padding-bottom:8px}
.rv-g{display:flex;justify-content:space-between;padding:14px 16px 6px;font-size:12px;font-weight:500;color:var(--rv-faint)}
.rv-n{font-variant-numeric:tabular-nums}
.rv-it{display:flex;gap:11px;align-items:center;padding:9px 16px;text-decoration:none;color:inherit;transition:background .12s}
.rv-it:hover{background:var(--rv-raised);text-decoration:none}
.rv-it[aria-selected=true]{background:var(--rv-raised);box-shadow:inset 2px 0 0 var(--rv-focus)}
.rv-it-t{display:flex;flex-direction:column;gap:2px;min-width:0}
.rv-it-t>span:first-child{font-size:13.5px;line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.rv-img{width:34px;height:34px;border-radius:7px;object-fit:cover;background:#f4f1ea;flex:none;display:block}
.rv-img-l{width:56px;height:56px;border-radius:10px}
.rv-flag{display:inline-flex;align-items:center;gap:5px;font-size:12px}.rv-ok{color:var(--rv-ok)}.rv-warn{color:var(--rv-warn)}
.rv-rej{display:block;padding:12px 16px 4px;font-size:12.5px;color:var(--rv-faint)}
.rv-pane{min-width:0;display:flex}
.rv-detail{flex:1;display:flex;flex-direction:column;gap:20px;padding:26px 30px 0;min-width:0}
.rv-detail[hidden]{display:none}
.rv-head{display:flex;gap:16px;align-items:center}
.rv-head h2{margin:0 0 5px;font-size:19px;letter-spacing:-.015em;line-height:1.3}
.rv-meta{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--rv-muted)}
.rv-type,.rv-stage{display:inline-flex;align-items:center;gap:6px}
.rv-type i,.rv-stage i{width:7px;height:7px;border-radius:50%;background:var(--rv-blue)}
.rv-t-comparison i{background:var(--rv-violet)}.rv-t-guide i{background:var(--rv-guide)}.rv-t-faq i{background:var(--rv-ok)}
.rv-s-facts i{background:var(--rv-warn)}.rv-s-ready i{background:var(--rv-blue)}.rv-s-scheduled i{background:var(--rv-ok)}.rv-s-live i{background:var(--rv-ink)}
.rv-why{margin:0;font-size:13.5px;color:var(--rv-muted);max-width:72ch}
.rv-dl{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px 16px;margin:0;font-size:14px}
.rv-dl dt{color:var(--rv-faint);font-size:12.5px;padding-top:2px}.rv-dl dd{margin:0}
.rv-old{color:var(--rv-muted);text-decoration:line-through;text-decoration-color:color-mix(in srgb,var(--rv-cut) 55%,transparent)}
.rv-new{font-weight:600}
.rv-sec h3{margin:0 0 8px;font-size:12.5px;font-weight:500;color:var(--rv-faint)}
.rv-doc{border:1px solid var(--rv-line);border-radius:10px;padding:14px 18px;background:var(--rv-bg);font-size:14px;line-height:1.65;max-height:340px;overflow:auto}
.rv-doc h2,.rv-doc h3{font-size:15px;margin:14px 0 6px;color:var(--rv-text)}.rv-doc p{margin:0 0 10px}.rv-doc table{border-collapse:collapse;font-size:13px}.rv-doc td,.rv-doc th{border:1px solid var(--rv-line);padding:5px 8px}
.rv-gap{background:color-mix(in srgb,var(--rv-warn) 22%,transparent);color:var(--rv-warn);border-radius:4px;padding:0 5px;font-size:12px;font-weight:600}
.rv-grades{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--rv-muted)}.rv-grades b{color:var(--rv-text);font-variant-numeric:tabular-nums}
.rv-note{color:var(--rv-faint)}
.rv-issues{margin:-8px 0 0;padding-left:18px;font-size:13px;color:var(--rv-muted)}
.rv-bar{position:sticky;bottom:0;margin-top:auto;display:flex;gap:8px;align-items:center;padding:14px 0 18px;border-top:1px solid var(--rv-line);background:var(--rv-surface);flex-wrap:wrap}
.rv-bar form{margin:0}.rv-sp{flex:1}
.rv-btn{display:inline-flex;align-items:center;height:32px;padding:0 14px;border-radius:8px;border:1px solid var(--rv-line);background:var(--rv-surface);color:var(--rv-text);font:inherit;font-size:13px;font-weight:500;cursor:pointer;text-decoration:none;transition:background .12s}
.rv-btn:hover{background:var(--rv-raised);text-decoration:none}
.rv-go{background:var(--rv-ink);color:var(--rv-on-ink);border-color:var(--rv-ink)}.rv-go:hover{background:var(--rv-ink);opacity:.9}
.rv-quiet{border-color:transparent;background:none;color:var(--rv-muted)}
.rv-btn:focus-visible,.rv-it:focus-visible{outline:2px solid var(--rv-focus);outline-offset:-2px}
@media (max-width:900px){.rv{grid-template-columns:1fr}.rv-list{max-height:none;border-right:0;border-bottom:1px solid var(--rv-line)}.rv-detail{padding:20px 16px 0}.rv-dl{grid-template-columns:1fr;gap:2px}}
@media (prefers-reduced-motion:reduce){.rv *{transition:none!important}}
</style>"""


def _meters(domain, lane='fixes'):
    """One meter per plan allowance (17 Oct 2026): product page fixes and articles, this calendar month."""
    import content_plan
    month = storetime.today(storetime.zone(domain)).strftime('%B')
    out = ''
    for kind, title, colour in (('fixes', 'Product page fixes', 'var(--cb-accent)'), ('articles', 'AEO articles', '#7a4fd6')):
        if kind != lane:
            continue
        a, u = content_plan.allowance(domain, kind), content_plan.used(domain, kind)
        if a == 0:
            continue
        pct = min(100, round(100 * u / a)) if a else 0
        line = ('<b>%d</b> approved · no monthly limit' % u if a is None
                else '<b>%d</b> of %d approved · %d left' % (min(u, a), a, max(0, a - u)))
        if kind == 'articles':
            line += _monthly(domain)
        out += ('<div class="cb-meter"><div class="cb-mh"><strong>%s</strong><span>%s</span></div>'
                '%s<p>%s</p></div>') % (
            E(title), E(month), '' if a is None else
            '<div class="cb-mbar"><b style="width:%d%%;background:%s"></b></div>' % (pct, colour), line)
    return '<div class="cb-meters">%s</div>' % out if out else ''


def _monthly(domain):
    """The monthly writer's line under the Articles meter, with a button when this month hasn't run."""
    import monthly_articles
    n, st = monthly_articles.count(domain), monthly_articles.state(domain)
    line = monthly_articles.note(domain)
    out = ('<br><span class="cb-mnote">%s</span>' % E(line)) if line else ''
    if st and st.get('short'):
        out += ' <a href="/questions?%s">Add buyer questions</a>' % E(urllib.parse.urlencode(dict(d=domain)))
    if not st:
        out += ('<form method="post" action="/content" class="cb-mform"><input type="hidden" name="d" value="%s">'
                '<input type="hidden" name="action" value="monthly_write"><button class="ca-btn">Write %d articles for '
                'this month now</button></form>' % (E(domain), n or monthly_articles.DEMO_COUNT))
    elif not st.get('finished_at'):
        out += '<meta http-equiv="refresh" content="20">'
    return out


def _filter():
    """All · Product pages · Articles. Hides cards in place and recounts each column; nothing reloads."""
    return ('<div class="cb-filter" role="group" aria-label="Show">'
            '<button type="button" class="cb-f-on" data-f="">All</button>'
            '<button type="button" data-f="page">Product pages</button>'
            '<button type="button" data-f="article">Articles</button></div>'
            '<script>(function(){var g=document.currentScript.previousElementSibling;g.onclick=function(e){'
            'var b=e.target.closest("button");if(!b)return;g.querySelectorAll("button").forEach(function(x){x.classList.remove("cb-f-on")});'
            'b.classList.add("cb-f-on");var f=b.getAttribute("data-f");'
            'document.querySelectorAll("#cb-board [data-col]").forEach(function(c){var n=0;c.querySelectorAll(".cb-tile").forEach(function(t){'
            'var show=!f||t.getAttribute("data-kind")===f;t.style.display=show?"":"none";if(show)n++;});'
            'var s=c.querySelector("header span");if(s)s.textContent=n;});};})();</script>')


def _rejected(domain):
    import content_agent
    rows = content_agent.drafts(domain, ('rejected',))
    return ('<p class="cb-note"><a href="%s">&#8249; Back to the board</a></p>' % E(_url(domain, view='inbox'))) + (
        '<ul class="ca-list">%s</ul>' % ''.join(
            '<li><strong>%s</strong><form method="post" action="/content"><input type="hidden" name="d" value="%s">'
            '<input type="hidden" name="id" value="%d"><input type="hidden" name="status" value="draft">'
            '<input type="hidden" name="back" value="%s"><button class="ca-btn">Move back</button></form></li>'
            % (E(r['title'] or 'Untitled'), E(domain), r['id'], E(_url(domain, view='inbox', show='rejected')))
            for r in rows) if rows else '<div class="ca-empty"><p>Nothing rejected.</p></div>')


def _drag(domain, back):
    """Board drops (16 Oct 2026): Ready -> Live puts a page live (Shopify) or approves it for import; Ready ->
    Scheduled schedules an article; Scheduled -> Ready unschedules; Live -> Ready takes it down. Week: a drop on a
    day moves the article there. The card moves at once and the change saves in the background (ajax=1, see
    content_agent.act); if the server refuses, the card goes back and says why. Going live offers Undo for 10 s."""
    return ('<div class="cb-toast" id="cb-toast" role="status" hidden></div><script>(function(){'
            'var D=%s,id=null,from=null,kind=null,tile=null;'
            'var ALLOW={ready:{live:1,scheduled:"article"},scheduled:{live:1,ready:1},live:{ready:1}};'
            'function toast(t,bad,undo){var e=document.getElementById("cb-toast");e.textContent=t;e.className="cb-toast"+(bad?" cb-bad":"");'
            'if(undo){var b=document.createElement("button");b.type="button";b.textContent="Undo";b.onclick=function(){e.hidden=true;undo();};e.appendChild(b);}'
            'e.hidden=false;clearTimeout(e._t);e._t=setTimeout(function(){e.hidden=true},bad?6000:undo?10000:2200);}'
            'function count(col,n){var s=col&&col.querySelector("header span");if(s)s.textContent=Math.max(0,+s.textContent+n);'
            'if(col){var em=col.querySelector(".cb-empty");if(em&&col.querySelector(".cb-tile"))em.remove();}}'
            'function send(params){var b=new URLSearchParams(params);b.set("d",D);b.set("ajax","1");'
            'return fetch("/content",{method:"POST",body:b,credentials:"same-origin",headers:{"Content-Type":"application/x-www-form-urlencoded"}})'
            '.then(function(r){return r.json()}).then(function(j){if(!j.ok)throw new Error(j.error);return j;});}'
            'function place(t,col,home,next){var old=t.closest("[data-col]");if(col){col.appendChild(t);}else{home.insertBefore(t,next);}'
            'var now=t.closest("[data-col]");if(old!==now){count(old,-1);count(now,1);}}'
            'function label(t,w){var x=t.querySelector(".cb-meta span:last-child");if(x)x.textContent=w;}'
            'document.addEventListener("dragstart",function(e){var t=e.target.closest&&e.target.closest("[data-id]");if(!t)return;'
            'tile=t;id=t.getAttribute("data-id");kind=t.getAttribute("data-kind");var c=t.closest("[data-col]");from=c?c.getAttribute("data-col"):null;'
            'e.dataTransfer.effectAllowed="move";e.dataTransfer.setData("text/plain",id);'
            'setTimeout(function(){t.classList.add("cb-dragging");document.body.classList.add("cb-on");'
            'document.querySelectorAll("[data-col]").forEach(function(c){var k=c.getAttribute("data-col"),ok=(ALLOW[from]||{})[k];'
            'if(ok&&!(ok==="article"&&kind!=="article"))c.classList.add("cb-can");});},0);});'
            'document.addEventListener("dragend",function(){if(tile)tile.classList.remove("cb-dragging");id=null;document.body.classList.remove("cb-on");'
            'document.querySelectorAll(".cb-drop,.cb-can,.cb-no").forEach(function(x){x.classList.remove("cb-drop","cb-can","cb-no")});});'
            'function land(t){t.classList.remove("cb-landed");void t.offsetWidth;t.classList.add("cb-landed");}'
            'function target(e){var c=e.target.closest&&(e.target.closest("[data-day]")||e.target.closest("[data-col]"));if(!c||!id||c.contains(tile))return null;'
            'var col=c.getAttribute("data-col");if(from==="facts")return col&&col!=="facts"?c:null;if(col){var ok=(ALLOW[from]||{})[col];if(!ok||(ok==="article"&&kind!=="article"))return null;}return c;}'
            'document.addEventListener("dragover",function(e){var c=target(e);if(c){e.preventDefault();c.classList.add(from==="facts"?"cb-no":"cb-drop");}});'
            'document.addEventListener("dragleave",function(e){var c=e.target.closest&&(e.target.closest("[data-day]")||e.target.closest("[data-col]"));if(c&&!c.contains(e.relatedTarget))c.classList.remove("cb-drop","cb-no");});'
            'document.addEventListener("drop",function(e){var c=target(e);if(!c)return;e.preventDefault();c.classList.remove("cb-drop","cb-no");'
            'if(from==="facts"){var n=+(tile.getAttribute("data-facts")||0);land(tile);toast("Answer "+(n===1?"the missing fact":"the "+n+" missing facts")+" first. Open the card to fill them in.",true);return;}'
            'var t=tile,did=id,src=from,home=t.parentNode,next=t.nextSibling,oldLabel=(t.querySelector(".cb-meta span:last-child")||{}).textContent,'
            'isDay=c.hasAttribute("data-day"),col=c.getAttribute("data-col"),p={id:did};'
            'if(isDay){p.action="move";p.day=c.getAttribute("data-day");}'
            'else if(col==="live")p.action="golive";else if(col==="scheduled")p.status="approved";'
            'else if(src==="live")p.action="unlive";else p.status="draft";'
            'if(isDay)c.appendChild(t);else place(t,c);land(t);'
            'send(p).then(function(j){label(t,j.when);'
            'if(p.action==="golive"){toast(j.when==="Live"?"Live on your store":"Approved · ready to import",false,function(){'
            'send({id:did,action:"unlive"}).then(function(k){place(t,document.querySelector("[data-col=ready]"));label(t,k.when);toast("Back in Ready");})'
            '.catch(function(err){toast(err.message,true);});});}'
            'else if(p.action==="unlive")toast("Taken down · back in Ready");'
            'else if(isDay)toast("Moved to "+j.when);else toast(j.status==="approved"?"Scheduled for "+j.when:"Moved back to Ready");'
            'if(t.getAttribute("aria-current"))location.reload();})'
            '.catch(function(err){if(isDay)home.insertBefore(t,next);else place(t,null,home,next);land(t);label(t,oldLabel);'
            'toast(err&&err.message&&err.message.indexOf("JSON")<0?err.message:"That didn’t save. Try again.",true);});'
            '});})();</script>') % json.dumps(domain)


# ---- Calendar: one week -------------------------------------------------------------------

def week(domain, q):
    import content_agent
    import content_calendar
    import content_export
    import content_setup
    tz = storetime.zone(domain)
    today = storetime.today(tz)
    try:
        start = dt.date.fromisoformat(q.get('week', ''))
    except ValueError:
        start = today
    start = start - dt.timedelta(days=(start.weekday() + 1) % 7)          # weeks start on Sunday
    days = [start + dt.timedelta(days=i) for i in range(7)]
    on, pace, hour = content_setup.schedule(domain)
    items = _rows(domain)
    sel = _sel(q)
    by_day = {}
    for it in items:
        if it['row']['planned_at'] and it['row']['draft_type'] not in PAGE_TYPES:
            by_day.setdefault(storetime.date_of(it['row']['planned_at'], tz), []).append(it)
    cols = ''
    for d in days:
        off = d.weekday() not in on
        tiles = ''.join(_tile(domain, it, tz, _url(domain, view='calendar', week=start.isoformat(), id=it['row']['id']),
                              sel, cal=True) for it in by_day.get(d, []))
        cols += ('<section class="cb-day%s%s"%s><h3>%s<b>%d</b></h3>%s%s</section>') % (
            ' cb-off' if off else '', ' cb-today' if d == today else '',
            ' data-day="%s"' % d.isoformat() if d >= today else '', d.strftime('%a'), d.day, tiles,
            '<p class="cb-hint">No publishing</p>' if off and not tiles else '')
    nav = lambda delta: E(_url(domain, view='calendar', week=(start + dt.timedelta(days=delta)).isoformat()))
    end = days[-1]
    head = ('<div class="cb-weeknav"><a class="ca-btn" href="%s" aria-label="Previous week">&#8249;</a><h2>%s &ndash; %s</h2>'
            '<a class="ca-btn" href="%s" aria-label="Next week">&#8250;</a>%s<span class="cb-note">Drag a card to another '
            'day to move it &middot; %s</span></div>') % (
        nav(-7), start.strftime('%b %-d'), end.strftime('%b %-d') if end.month != start.month else end.day, nav(7),
        ('<a class="ca-btn" href="%s">This week</a>' % E(_url(domain, view='calendar'))) if not start <= today <= end else '',
        E(storetime.abbrev(tz)))
    grid = '<div class="cb-week">%s</div>' % cols
    picked = next((it for it in items if it['row']['id'] == sel), None)
    back = _url(domain, view='calendar', week=start.isoformat(), **({'id': sel} if sel else {}))
    top = content_setup.batch_note(domain) + content_export.bar(domain) + content_calendar.connect_box(domain)
    if picked:
        # The calendar keeps the full detail panel (what, where, when, why, sources, after publishing, move).
        body = '<div class="cb-wrap"><div class="cb-scroll">%s</div>%s</div>' % (
            grid, content_calendar.panel(domain, picked['row']['id'], content_agent.DRAFT_TYPES, back))
    else:
        body = grid
    # AEO articles only (18 Oct 2026): product page fixes live in their own agent, with no calendar.
    types = {k: v for k, v in content_agent.DRAFT_TYPES.items() if k in ARTICLE_TYPES}
    return top + head + body + content_calendar.legend(types) + _drag(domain, back)


# ---- Live: what went live, as a feed -------------------------------------------------------

def live(domain, lane=None):
    import content_agent
    tz = storetime.zone(domain)
    rows = sorted((r for r in content_agent.drafts(domain, ('published',))
                   if not lane or r['draft_type'] in LANE_TYPES[lane]), key=lambda r: -(r['published_at'] or 0))
    if not rows:
        return ('<div class="ca-empty"><p>Nothing live on your store yet. When an approved page is published, it '
                'shows up here with a link and an undo.</p></div>')
    out, last = '', None
    for r in rows:
        day = storetime.date_of(r['published_at'], tz) if r['published_at'] else None
        if day != last:
            today = storetime.today(tz)
            out += '<p class="cb-feed-day">%s</p>' % ('Today' if day == today else 'Yesterday'
                                                    if day and day == today - dt.timedelta(days=1)
                                                    else day.strftime('%A, %B %-d') if day else 'Earlier')
            last = day
        body, _ = content_agent._latest(r['id'])
        p = body.get('product') or {}
        img = ('<img class="cb-thumb" src="%s" alt="" loading="lazy">' % E(p['image'])) if p.get('image') \
            else '<span class="cb-thumb"></span>'
        back = _url(domain, view='published')
        out += ('<div class="cb-ev"><span class="cb-ico" aria-hidden="true"><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="2.4"/>'
                '<path d="M5.5 5.5a6.4 6.4 0 000 9M14.5 5.5a6.4 6.4 0 010 9"/></svg></span><p class="cb-line">Published '
                '<b>%s</b><time>%s</time></p><div class="cb-card">%s<div><strong>%s</strong><p>%s &middot; Mentions before '
                'and after: too early to read</p></div><div class="cb-actions">%s</div></div></div>') % (
            E(r['title'] or 'Untitled'), E(storetime.label(r['published_at'], tz, '%H:%M')) if r['published_at'] else '',
            img, E(p.get('title') or ''), E(content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])),
            content_agent.publish_buttons(domain, r, back) or (
                ('<a class="ca-btn" href="%s" target="_blank" rel="noopener">View live</a>' % E(r['live_url']))
                if r['live_url'] else ''))
    return '<div class="cb-feed">%s</div>' % out


CSS = """
.ca-page{--cb-ink:#0b1b35;--cb-accent:#2f6fdb;--cb-ok:#1c7a46;--cb-warn:#b45309;--cb-line:#e3e8ef;--cb-soft:#f0f3f8;--cb-card:#ffffff;--cb-muted:#586579}
.cb-note{font-size:13.5px;color:var(--cb-muted);margin:0 0 12px}
.cb-flow{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:14px;align-items:start;overflow-x:auto;padding-bottom:6px}
.cb-mini{grid-template-columns:repeat(4,210px)}
.cb-flow.cb-n3{grid-template-columns:repeat(3,minmax(240px,1fr))}.cb-flow.cb-n3.cb-mini{grid-template-columns:repeat(3,210px)}
.cb-col{background:var(--cb-soft);border-radius:14px;padding:12px;min-height:380px;transition:background .15s,box-shadow .15s}
.cb-col header{display:flex;align-items:center;gap:8px;padding:4px 4px 10px}
.cb-col header i{width:9px;height:9px;border-radius:50%}
.cb-col header h2{font-size:14.5px;margin:0;color:var(--cb-ink)}
.cb-col header span{margin-left:auto;font-size:13px;font-weight:700;color:var(--cb-muted)}
.cb-hint{font-size:12.5px;color:var(--cb-muted);margin:-4px 4px 12px}
.cb-empty{border:1px dashed #d3dae5;border-radius:12px;padding:14px;color:var(--cb-muted);font-size:13.5px;text-align:center;margin:0}
.cb-tile{display:block;background:var(--cb-card);border:1px solid var(--cb-line);border-radius:12px;padding:12px;margin-bottom:10px;text-decoration:none;color:inherit;transition:border-color .15s,box-shadow .15s,opacity .15s,transform .15s}
.cb-tile:hover{border-color:var(--cb-ink);box-shadow:0 1px 2px rgba(11,27,53,.06),0 8px 24px -12px rgba(11,27,53,.14)}
.cb-tile[draggable=true]{cursor:grab}
.cb-tile[aria-current]{border-color:var(--cb-accent);box-shadow:0 0 0 3px #e8f0fd}
.cb-tile.cb-pend{border-style:dashed}
.cb-tile[draggable=true]:active{cursor:grabbing}
.cb-dragging{opacity:.4;transform:scale(.97);border-style:dashed}
.cb-on .cb-can{box-shadow:inset 0 0 0 1px rgba(47,111,219,.35)}
.cb-no{box-shadow:inset 0 0 0 2px rgba(214,69,51,.5)}
.cb-landed{animation:cb-land .32s cubic-bezier(.2,.8,.3,1)}
@keyframes cb-land{0%{transform:scale(1.035);box-shadow:0 10px 26px -12px rgba(11,27,53,.35)}100%{transform:none}}
@media (prefers-reduced-motion:reduce){.cb-landed{animation:none}.cb-dragging{transform:none}}
.cb-top{display:flex;gap:10px;align-items:flex-start}
.cb-chg{display:block;font-size:12.5px;color:var(--cb-muted);margin-top:2px}
.cb-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;padding-top:9px;border-top:1px solid var(--cb-line);font-size:12px;color:var(--cb-muted)}
.cb-foot .rv-flag{display:inline-flex;align-items:center;gap:5px}.cb-foot .rv-ok{color:#18804b}.cb-foot .rv-warn{color:#b45f06}
html.dark .cb-foot .rv-ok{color:#45d08c}html.dark .cb-foot .rv-warn{color:#e8a54a}
.cb-foot .rv-i{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.cb-card2 .cb-thumb{display:block}
.cb-thumb{width:38px;height:38px;border-radius:9px;object-fit:cover;background:var(--cb-soft);flex:none}
.cb-tile strong{display:block;font-size:14px;line-height:1.35;color:var(--cb-ink)}
.cb-gapbar{display:flex;gap:3px;margin-top:10px}
.cb-gapbar i{flex:1;height:4px;border-radius:2px;background:var(--cb-warn)}
.cb-gapbar i.cb-off{background:#d3dae5}
.cb-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;font-size:12.5px;color:var(--cb-muted)}
.cb-type{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;background:var(--cb-soft);color:#1a2436;white-space:nowrap}
.cb-type i{width:8px;height:8px;border-radius:50%;background:#2f6fdb}
.cb-t-faq i{background:#1c8a52}.cb-t-comparison i{background:#7a4fd6}.cb-t-guide i{background:#c27618}
.cb-drop{background:#e8f0fd;box-shadow:inset 0 0 0 2px #2f6fdb}
.cb-meters{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.cb-meter{flex:1 1 260px;background:var(--cb-soft);border-radius:12px;padding:12px 14px}
.cb-mh{display:flex;justify-content:space-between;font-size:14px;color:var(--cb-ink)}.cb-mh span{color:var(--cb-muted);font-size:13px}
.cb-mbar{height:6px;border-radius:4px;background:#d3dae5;margin:9px 0 6px;overflow:hidden}.cb-mbar b{display:block;height:100%}
.cb-meter p{margin:0;font-size:13px;color:var(--cb-muted)}.cb-meter p b{color:var(--cb-ink)}
.cb-mnote{display:inline-block;margin-top:4px}.cb-mform{margin:8px 0 0}
.cb-filter{display:inline-flex;gap:2px;background:var(--cb-soft);border-radius:10px;padding:3px;margin:0 0 12px}
.cb-filter button{font:inherit;font-size:13.5px;font-weight:600;border:0;background:none;color:var(--cb-muted);padding:5px 12px;border-radius:8px;cursor:pointer}
.cb-filter .cb-f-on{background:#ffffff;color:var(--cb-ink)}
.cb-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:60;padding:10px 16px;border-radius:10px;background:#0b1b35;color:#ffffff;font-size:14px;font-weight:600;box-shadow:0 10px 30px -12px rgba(11,27,53,.5);max-width:min(560px,90vw)}
.cb-toast.cb-bad{background:#b42318}
.cb-connect{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 18px;margin:0 0 14px;border-radius:12px;background:#fdf0dc;color:#5c3a00;flex-wrap:wrap}
.cb-connect p{margin:0;font-size:14.5px}.cb-connect b{color:#3d2700}
.cb-toast button{margin-left:14px;border:0;background:none;color:#9cc0ff;font:inherit;font-weight:700;cursor:pointer;text-decoration:underline}
.cb-wrap{display:grid;grid-template-columns:minmax(0,1fr) min(560px,50%);gap:18px;align-items:start}
.cb-scroll{min-width:0;overflow-x:auto}
.cb-sheet{background:var(--cb-card);border:1px solid var(--cb-line);border-radius:16px;box-shadow:0 1px 2px rgba(11,27,53,.06),0 12px 32px -16px rgba(11,27,53,.2);position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}
.cb-sheet header{padding:18px 22px 14px;border-bottom:1px solid var(--cb-line);position:sticky;top:0;background:var(--cb-card);z-index:1}
.cb-sheet-top{display:flex;align-items:center;justify-content:space-between}
.cb-x{font-size:24px;line-height:1;color:var(--cb-muted);text-decoration:none}
.cb-sheet h2{font-size:19px;line-height:1.3;margin:8px 0 2px;color:var(--cb-ink)}
.cb-when{margin:0;font-size:13.5px;color:var(--cb-muted)}
.cb-stage{display:flex;gap:4px;margin-top:12px}
.cb-stage span{flex:1;font-size:11.5px;font-weight:700;text-align:center;padding:5px 0;border-radius:6px;background:var(--cb-soft);color:var(--cb-muted)}
.cb-stage .cb-on{background:var(--cb-ink);color:#ffffff}
.cb-stage .cb-past{background:#e3f4ea;color:var(--cb-ok)}
.cb-body{padding:16px 22px}
.cb-body h3{font-size:13px;color:var(--cb-muted);margin:16px 0 8px}
.cb-body .cr-box{margin:0;padding:14px 16px}
.cb-full{float:right;font-size:13px;font-weight:600}
.cb-overlay{position:fixed;inset:0;z-index:300;background:rgba(5,12,25,.6);display:flex;justify-content:center;padding:24px}
.cb-overlay .cb-sheet{position:relative;top:0;width:min(1200px,100%);height:100%;max-height:none;overflow:auto;border-radius:16px}
.cb-overlay .cb-sheet header{padding:22px 32px 16px}
.cb-overlay .cb-sheet h2{font-size:24px}
.cb-overlay .cb-body{padding:22px 32px;max-width:none}
.cb-overlay .cb-body > *{max-width:980px;margin-left:auto;margin-right:auto}
.cb-overlay .cb-body > .cr-frame{max-width:none}
.cb-overlay .cb-sheet footer{padding:16px 32px}
.cb-overlay .cb-x{font-size:30px}
.cb-overlay .cb-body.cb-split{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;align-items:start}
.cb-overlay .cb-split > *{max-width:none;margin:0}
.cb-split .cb-main{order:1;min-width:0}
.cb-split .cb-side{order:2;position:sticky;top:0;display:grid;gap:12px}
.cb-split .cb-side .cr-box{margin:0}
.cb-more{font-size:13.5px;line-height:1.6;margin:0}
/* The article preview and the questions beside it scroll on their own (Kelian, 20 Oct 2026): the sheet itself doesn't. */
.cb-overlay .cb-sheet-split{display:flex;flex-direction:column;overflow:hidden}
.cb-overlay .cb-sheet-split header,.cb-overlay .cb-sheet-split footer{flex:none;position:static}
.cb-overlay .cb-sheet-split .cb-body.cb-split{flex:1;min-height:0;overflow:hidden;padding-top:16px;padding-bottom:0}
.cb-overlay .cb-sheet-split .cb-main{height:100%;overflow:visible;position:relative;display:flex;flex-direction:column;padding-bottom:16px}
.cb-overlay .cb-sheet-split .cb-main .pk-tools{flex:none}
.cb-overlay .cb-sheet-split .cb-main .cr-frame{flex:1;height:auto!important;min-height:0}
.cb-overlay .cb-sheet-split .cb-side{height:100%;overflow:auto;position:static;padding-bottom:24px;align-content:start;overscroll-behavior:contain}
@media (max-width:1000px){.cb-overlay .cb-body.cb-split{grid-template-columns:1fr}.cb-split .cb-side{order:0;position:static}
.cb-overlay .cb-sheet-split{overflow:auto}.cb-overlay .cb-sheet-split .cb-body.cb-split{overflow:visible}
.cb-overlay .cb-sheet-split .cb-main,.cb-overlay .cb-sheet-split .cb-side{height:auto;overflow:visible}
.cb-overlay .cb-sheet-split .cb-main .cr-frame{height:80vh!important;flex:none}}
@media (max-width:700px){.cb-overlay{padding:0}.cb-overlay .cb-sheet{border-radius:0}.cb-overlay .cb-sheet header,.cb-overlay .cb-body,.cb-overlay .cb-sheet footer{padding-left:16px;padding-right:16px}}
.cb-before{padding:12px 14px;border-radius:10px;background:var(--cb-soft);font-size:14px;color:var(--cb-muted)}
.cb-before p{margin:0 0 6px}
.cb-doc{font-size:14.5px;line-height:1.6}
.cb-doc table{border-collapse:collapse;width:100%;font-size:13.5px}
.cb-doc th,.cb-doc td{border:1px solid var(--cb-line);padding:6px 9px;text-align:left}
.cb-h{font-size:16px;margin:0 0 8px;color:var(--cb-ink)}
.cb-sheet footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;padding:14px 22px;border-top:1px solid var(--cb-line);position:sticky;bottom:0;background:var(--cb-card)}
.cb-sheet footer form{margin:0}
.cb-weeknav{display:flex;align-items:center;gap:10px;margin:0 0 12px;flex-wrap:wrap}
.cb-weeknav h2{margin:0;font-size:17px;color:var(--cb-ink)}
.cb-weeknav .cb-note{margin:0 0 0 auto}
.cb-week{display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:10px;overflow-x:auto;margin-bottom:12px}
.cb-wrap .cb-week{grid-template-columns:repeat(7,150px)}
.cb-day{background:var(--cb-soft);border-radius:12px;padding:10px;min-height:300px;transition:background .15s,box-shadow .15s}
.cb-day h3{font-size:13px;margin:0 0 10px;color:var(--cb-muted);display:flex;justify-content:space-between}
.cb-day h3 b{font-size:16px;color:var(--cb-ink)}
.cb-day.cb-today h3 b{color:var(--cb-accent)}
.cb-day.cb-off{opacity:.6}
.cb-day .cb-tile{padding:10px}
.cb-feed{position:relative;padding-left:34px;max-width:860px}
.cb-feed::before{content:"";position:absolute;left:11px;top:6px;bottom:6px;width:1px;background:#d3dae5}
.cb-feed-day{font-size:13px;font-weight:700;color:var(--cb-muted);margin:20px 0 10px}
.cb-feed-day:first-child{margin-top:0}
.cb-ev{position:relative;margin-bottom:16px}
.cb-ico{position:absolute;left:-34px;top:1px;width:23px;height:23px;border-radius:50%;display:grid;place-items:center;background:#e3f4ea;color:var(--cb-ok)}
.cb-ico svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round}
.cb-line{margin:0;font-size:14.5px;color:#1a2436}
.cb-line b{color:var(--cb-ink)}
.cb-line time{font-size:12.5px;color:#8a94a3;margin-left:6px}
.cb-card{margin-top:10px;background:var(--cb-card);border:1px solid var(--cb-line);border-radius:12px;padding:14px 16px;display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:14px;align-items:center}
.cb-card .cb-thumb{width:48px;height:48px}
.cb-card strong{display:block;color:var(--cb-ink);font-size:15px}
.cb-card p{margin:2px 0 0;font-size:13.5px;color:var(--cb-muted)}
.cb-actions{display:flex;gap:8px}
.cb-actions form{margin:0}
@media (max-width:1100px){.cb-wrap{grid-template-columns:1fr}.cb-sheet{position:static;max-height:none}.cb-flow{grid-template-columns:repeat(4,240px)}.cb-card{grid-template-columns:48px 1fr}.cb-actions{grid-column:1/-1}}
"""
