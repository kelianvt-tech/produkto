"""Calendar, basic version: when each approved draft is planned, and everything about it.

Day 11b of mvp/content-agent/PLAN.md.

  * Approving a draft plans it on the next free slot in the store's own time
    zone, following the days, pace and hour chosen in setup (day 11d; default
    weekdays, 3 a week, 09:00). Drafts the agent planned itself (first two
    weeks) sit on the calendar marked "needs approval". Day 24 adds dragging.
  * Clicking an item on the month grid opens its detail panel (spec in
    PLAN.md "Calendar detail panel"): what, where it goes, when, why, sources,
    the content itself, what happened after publishing, and actions.

Nothing here calls an AI model or touches the store. "Published" stays empty
until the merchant imports the export file (day 12) or phase 3 publishes.
"""
import datetime as dt
import html
import json
import re
import time
import urllib.parse
from html import escape as E

import db
import storetime

PUBLISH_HOUR = 9          # local time a planned item goes out, in the store's zone
WEEKDAYS = (0, 1, 2, 3, 4)


def _ts(day, tz, hour=PUBLISH_HOUR):
    if tz is None:
        return dt.datetime.combine(day, dt.time(hour)).timestamp()
    return dt.datetime.combine(day, dt.time(hour), tz).timestamp()


def taken_days(domain, tz, skip_id=None):
    rows = db.all_("SELECT id, planned_at FROM content_drafts WHERE store_domain=? AND planned_at IS NOT NULL "
                   "AND status != 'rejected'", (domain,))
    return {storetime.date_of(r['planned_at'], tz) for r in rows if r['id'] != skip_id}


def _week(day):
    return day - dt.timedelta(days=day.weekday())


def free_slots(domain, weeks=None, count=None, skip_id=None):
    """Free publish slots from tomorrow, following the merchant's days, pace and hour (setup step 4).
    Either the slots in the next `weeks` weeks, or the next `count` slots."""
    import content_setup
    tz = storetime.zone(domain)
    days, pace, hour = content_setup.schedule(domain)
    taken = taken_days(domain, tz, skip_id)
    per_week = {}
    for d in taken:
        per_week[_week(d)] = per_week.get(_week(d), 0) + 1
    out = []
    day = storetime.today(tz) + dt.timedelta(days=1)
    end = day + dt.timedelta(weeks=weeks) if weeks else None
    while (end and day < end) or (count and len(out) < count):
        if day.weekday() in days and day not in taken and per_week.get(_week(day), 0) < pace:
            out.append(_ts(day, tz, hour))
            per_week[_week(day)] = per_week.get(_week(day), 0) + 1
        day += dt.timedelta(days=1)
        if (day - storetime.today(tz)).days > 400:
            break
    return out


def next_slot(domain, tz=None, skip_id=None):
    """Next free slot at the merchant's pace, days and hour."""
    return free_slots(domain, count=1, skip_id=skip_id)[0]


def plan(domain, did):
    """Give an approved draft a date if it has none. Returns the planned timestamp."""
    row = db.one('SELECT planned_at FROM content_drafts WHERE id=?', (did,))
    if row and row['planned_at']:
        return row['planned_at']
    at = next_slot(domain, skip_id=did)
    db.write('UPDATE content_drafts SET planned_at=?, updated_at=? WHERE id=?', (at, time.time(), did))
    return at


def move(domain, did, day_text):
    """Move a planned item to another day (same 09:00 local time). Returns True if moved."""
    try:
        day = dt.date.fromisoformat(day_text)
    except (TypeError, ValueError):
        return False
    tz = storetime.zone(domain)
    if day < storetime.today(tz):
        return False
    import content_setup
    db.write('UPDATE content_drafts SET planned_at=?, updated_at=? WHERE id=? AND store_domain=?',
             (_ts(day, tz, content_setup.schedule(domain)[2]), time.time(), did, domain))
    return True


# ---- detail panel -------------------------------------------------------------

def _words(text):
    return len(re.findall(r"\w[\w'’-]*", html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))))


def _brief(brief_id):
    row = db.one('SELECT data FROM content_briefs WHERE id=?', (brief_id,)) if brief_id else None
    return json.loads(row['data']) if row and row['data'] else {}


def _section(title, body):
    return '<section class="cal-sec"><h3>%s</h3>%s</section>' % (E(title), body)


def panel(domain, did, types, back):
    import content_review
    row, body, version = content_review.load(did, domain)
    if not row:
        return ''
    content_review.rebuild(body, row['draft_type'])
    tz = storetime.zone(domain)
    zone = storetime.abbrev(tz)
    brief = _brief(row['brief_id'])
    status = {'draft': 'New', 'approved': 'Approved', 'scheduled': 'Scheduled', 'published': 'Live',
              'rejected': 'Rejected'}.get(row['status'], row['status'])
    open_link = '/content?' + urllib.parse.urlencode(dict(d=domain, view='draft', id=did))

    what = ('<dl class="cal-dl"><dt>Type</dt><dd>%s</dd><dt>Status</dt><dd>%s</dd><dt>Length</dt><dd>%d words</dd></dl>'
            % (E(types.get(row['draft_type'], row['draft_type'])), E(status), _words(body.get('html', ''))))

    product = body.get('product') or {}
    if row['draft_type'] in ('product_fix', 'faq') and product.get('url'):
        img = ('<img src="%s" alt="">' % E(product['image'])) if product.get('image') else ''
        field = 'Title, description and spec table' if row['draft_type'] == 'product_fix' else 'New FAQ section below the description'
        where = ('<div class="cal-target">%s<div><a href="%s" target="_blank" rel="noopener">%s</a><p>%s</p></div></div>'
                 % (img, E(product['url']), E(product.get('title', '')), field))
    elif row['draft_type'] == 'comparison':
        where = '<p>A new page on your store, linking to %s.</p>' % E(', '.join(p['title'] for p in body.get('products', [])))
    else:
        where = '<p>A new article on your blog, linking to %s.</p>' % E(', '.join(p['title'] for p in body.get('products', [])))

    if row['planned_at']:
        when = '<p><strong>%s</strong> (%s)</p>' % (E(storetime.label(row['planned_at'], tz, '%A %-d %B, %H:%M')), E(zone))
    else:
        when = '<p class="cr-muted">Not planned yet. Approving a draft puts it on the next free slot.</p>'
    if row['planned_at'] and row['status'] == 'draft':
        when += '<p class="cal-warn">Needs your approval before it can go out.</p>'
    if row['approved_at']:
        when += '<p class="cr-muted">Approved %s%s.</p>' % (E(storetime.label(row['approved_at'], tz)),
                                                            ' by %s' % E(row['approved_by']) if row['approved_by'] else '')

    why = ''
    opp = brief.get('opportunity') or {}
    if opp.get('title'):
        why += '<p><strong>%s</strong></p>' % E(opp['title'])
    if body.get('why'):
        why += '<p class="cr-muted">Why this kind of page: %s</p>' % E(body['why'])
    qs = brief.get('questions') or []
    if qs:
        why += '<ul class="cal-qs">%s</ul>' % ''.join(
            '<li>&ldquo;%s&rdquo;<span>Your products named in %d of %d answers</span></li>'
            % (E(q['question']), q.get('own', 0), q.get('answers', 0)) for q in qs)
    comps = brief.get('competitors') or []
    if comps:
        why += '<p class="cr-muted">Named instead: %s.</p>' % E(', '.join(
            ('%s %s' % (c['brand'], c['product'])).strip() + ' (%d)' % c['named'] for c in comps[:5]))
    w = brief.get('winnable') or {}
    if w.get('level'):
        why += '<p class="cal-win cal-win-%s"><strong>%s</strong> %s</p>' % (E(w['level']), E(
            {'winnable': 'Winnable.', 'mixed': 'Mixed.', 'hard': 'Hard to win.'}[w['level']]), E(
            '%d%% of what AI cites for this comes from big, established sites%s%s.' % (
                w['big_share'], (' (%s)' % ', '.join(w['big'][:3])) if w['big'] else '',
                ('; the rest from smaller sites like %s' % ', '.join(w['small'][:3])) if w['small'] else '')))
    why = why or '<p class="cr-muted">No Opportunity recorded for this draft.</p>'

    sources = json.loads(version['sources'] or '[]') if version else []
    src = '<p>%d fact%s from your catalog and product pages.</p>' % (len(sources), '' if len(sources) == 1 else 's')
    read = [c for c in comps if c.get('page_read')]
    if read:
        src += '<p class="cr-muted">Competitor pages read: %s.</p>' % ', '.join(
            '<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(c['url']), E(c['brand'] or c['url'])) for c in read[:5])
    cited = [c for c in brief.get('cited_pages') or [] if c.get('page_read')]
    if cited:
        src += '<p class="cr-muted">Pages AI cited, read for research only (no facts taken from them): %s.</p>' % ', '.join(
            '<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(c['url']), E(c['site'])) for c in cited)
    gaps = content_review.gaps(body)
    if gaps:
        src += '<p class="cal-warn">%d gap%s still to fill.</p>' % (len(gaps), '' if len(gaps) == 1 else 's')

    content = '<div class="cal-doc">%s%s</div><p><a href="%s">Open before / after</a></p>' % (
        ('<h4>%s</h4>' % E(body['title'])) if body.get('title') else '', body.get('html', ''), E(open_link))

    if row['status'] == 'published':
        after = '<p>Live at <a href="%s" target="_blank" rel="noopener">%s</a>.</p>' % (E(row['live_url'] or ''), E(row['live_url'] or ''))
        after += '<p class="cr-muted">Mentions before and after: too early to read.</p>'
    else:
        after = '<p class="cr-muted">Not published yet. Once it is live, this shows the link, when AI first cited it, and mentions before and after.</p>'

    def post(fields, label, cls=''):
        hidden = ''.join('<input type="hidden" name="%s" value="%s">' % (E(k), E(str(v))) for k, v in fields.items())
        return '<form method="post" action="/content">%s<button class="ca-btn %s">%s</button></form>' % (hidden, cls, label)

    import content_agent
    base = dict(d=domain, id=did, back=back)
    actions = content_agent.publish_buttons(domain, row, back)
    if row['status'] != 'published':
        actions += '<a class="ca-btn" href="%s">Edit</a>' % E(open_link)
    if row['status'] == 'draft':
        if not gaps:
            actions += post(dict(base, status='approved'), 'Approve', 'ca-primary')
        actions += post(dict(base, status='rejected'), 'Reject')
    elif row['status'] in ('approved', 'scheduled'):
        actions += post(dict(base, status='rejected'), 'Reject')
    move_form = ''
    if row['status'] in ('approved', 'scheduled') and row['planned_at']:
        move_form = ('<form class="cal-move" method="post" action="/content"><input type="hidden" name="d" value="%s">'
                     '<input type="hidden" name="id" value="%d"><input type="hidden" name="action" value="move">'
                     '<input type="hidden" name="back" value="%s"><label>Move to <input type="date" name="day" value="%s" min="%s">'
                     '</label><button class="ca-btn">Move</button></form>') % (
            E(domain), did, E(back), storetime.date_of(row['planned_at'], tz).isoformat(), storetime.today(tz).isoformat())

    close = '/content?' + urllib.parse.urlencode({k: v for k, v in urllib.parse.parse_qsl(back.split('?', 1)[1]) if k not in ('item', 'id')})
    return ('<aside class="cal-panel" aria-label="Item details"><div class="cal-ph"><span class="ca-type">%s</span>'
            '<a class="cal-x" href="%s" aria-label="Close">&times;</a></div><h2>%s</h2><div class="cal-actions">%s</div>%s%s%s%s%s%s%s%s</aside>') % (
        E(types.get(row['draft_type'], row['draft_type'])), E(close), E(body.get('title') if row['draft_type'] in ('comparison', 'guide') else row['title'] or 'Untitled'),
        actions, move_form, _section('What', what), _section('Where it goes', where), _section('When', when),
        _section('Why', why), _section('Sources', src), _section('Content', content), _section('After publishing', after))


CSS = """
.cal-wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;align-items:start}
.cal-wrap.cal-open{grid-template-columns:minmax(0,1fr) 380px}
.ca-item{text-decoration:none}
a.ca-item:hover{outline:1px solid #0b1b35}
a.ca-item.cal-sel{background:#0b1b35;color:#ffffff}
a.ca-item.cal-pending{background:transparent;border:1px dashed #8a94a3;color:#586579}
a.ca-item.ca-product_fix,.cal-key .ca-product_fix{background:#e7eefb;border-left:3px solid #2f6fdb}
a.ca-item.ca-faq,.cal-key .ca-faq{background:#e5f4eb;border-left:3px solid #1f8a4c}
a.ca-item.ca-comparison,.cal-key .ca-comparison{background:#efe9fb;border-left:3px solid #7a4fd6}
a.ca-item.ca-guide,.cal-key .ca-guide{background:#fcf0df;border-left:3px solid #c27618}
a.ca-item.cal-pending{background:transparent}
a.ca-item.cal-sel{background:#0b1b35;color:#ffffff}
a.ca-item[draggable=true]{cursor:grab}
.ca-day.cal-drop{background:#eef3fc;outline:2px dashed #2f6fdb;outline-offset:-3px}
.cal-key{display:flex;flex-wrap:wrap;gap:8px 16px;margin:10px 0 0;padding:0;list-style:none;font-size:12.5px;color:#586579}
.cal-key li{display:flex;align-items:center;gap:6px}
.cal-key i{display:inline-block;width:14px;height:10px;border-radius:3px}
.cal-key .cal-k-pending{border:1px dashed #8a94a3}
.cal-connect{margin:0 0 12px;font-size:14px}
.cal-connect summary{cursor:pointer;font-weight:600;color:#0b1b35}
.cal-connect .cs-row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.cal-link{display:grid;gap:4px;font-size:13px;color:#586579;margin:6px 0}
.cal-link input{padding:7px 9px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;font-size:12.5px;background:#ffffff;color:#1a2436;width:100%;max-width:620px}
.cal-reset form{display:inline;margin:0}
.ca-link-btn{border:0;background:none;padding:0;font:inherit;color:#0b1b35;text-decoration:underline;cursor:pointer}
.cal-panel{border:1px solid #e6e9ef;border-radius:12px;background:#ffffff;padding:16px 18px;position:sticky;top:12px;max-height:calc(100vh - 40px);overflow:auto;font-size:14px;line-height:1.5;color:#1a2436}
.cal-win{padding:8px 10px;border-radius:8px;background:#eef6f0;font-size:13.5px}.cal-win-mixed{background:#fdf3e2}.cal-win-hard{background:#fdecea}
.cal-ph{display:flex;justify-content:space-between;align-items:center}
.cal-x{font-size:22px;line-height:1;color:#586579;text-decoration:none}
.cal-panel h2{font-size:17px;font-weight:700;margin:10px 0 12px;color:#0b1b35}
.cal-actions{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.cal-actions form{margin:0}
a.ca-btn{display:inline-block;text-decoration:none}
.cal-move{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 6px;font-size:13px;color:#586579}
.cal-move input{padding:6px 8px;border:1px solid #d5dbe5;border-radius:8px;font:inherit;background:#ffffff;color:#1a2436}
.cal-sec{border-top:1px solid #eef1f5;padding:12px 0 2px}
.cal-sec h3{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#8a94a3;margin:0 0 6px}
.cal-sec p{margin:0 0 6px}
.cal-dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0}
.cal-dl dt{color:#586579}.cal-dl dd{margin:0;font-weight:600}
.cal-target{display:flex;gap:10px;align-items:center}
.cal-target img{width:44px;height:44px;border-radius:8px;object-fit:cover}
.cal-target p{margin:2px 0 0;color:#586579;font-size:13px}
.cal-qs{margin:6px 0;padding-left:18px;display:grid;gap:6px}
.cal-qs span{display:block;color:#586579;font-size:12.5px}
.cal-warn{color:#9a3412;font-weight:600}
.cal-doc{max-height:260px;overflow:auto;border:1px solid #eef1f5;border-radius:8px;padding:8px 10px;font-size:13px}
.cal-doc h2{font-size:14px}.cal-doc h3,.cal-doc h4{font-size:13.5px;margin:8px 0 4px}
.cal-doc table{border-collapse:collapse;width:100%}.cal-doc th,.cal-doc td{border:1px solid #eef1f5;padding:4px 6px;text-align:left}
@media (max-width:980px){.cal-wrap.cal-open{grid-template-columns:minmax(0,1fr)}.cal-panel{position:static;max-height:none}}
"""


# ---- connect your calendar (day 24b) ---------------------------------------------
# A private subscribe link (iCal feed). Calendar apps fetch it without signing in, so the link itself is the
# key: long and random, and "Make a new link" replaces it (the old one stops working). It shows draft titles,
# types and dates, nothing else, and every event links back to the draft's detail panel, which needs a login.

def _base():
    import config
    return (config.env('PRODUKTO_BASE_URL') or 'http://localhost:%d' % config.PORT).rstrip('/')


def feed_token(domain, new=False):
    import secrets
    import content_setup
    s = content_setup.get(domain)
    if new or not s.get('ical_token'):
        s['ical_token'] = secrets.token_urlsafe(24)
        content_setup.put(domain, s)
    return s['ical_token']


def feed_url(domain):
    return '%s/content/cal/%s.ics' % (_base(), feed_token(domain))


def _domain_of(token):
    import content_setup
    content_setup.init()
    for r in db.all_('SELECT store_domain, data FROM content_settings'):
        try:
            if token and json.loads(r['data'] or '{}').get('ical_token') == token:
                return r['store_domain']
        except ValueError:
            continue
    return None


def _ics_text(s):
    return (s or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _fold(line):
    """iCal lines are at most 75 octets; longer ones continue on the next line after a space."""
    raw = line.encode('utf-8')
    if len(raw) <= 75:
        return line
    parts, cur = [], b''
    for ch in line:
        b = ch.encode('utf-8')
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode('utf-8'))
            cur = b''
        cur += b
    parts.append(cur.decode('utf-8'))
    return '\r\n '.join(parts)


def ical(token):
    """(200, calendar text) for a valid subscribe link, or (404, '')."""
    domain = _domain_of(token)
    if not domain:
        return 404, ''
    import content_agent
    tz = storetime.zone(domain)
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Produkto//Catalog Optimization Agent//EN',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:%s (%s)' % (_ics_text(content_agent.NAME), domain),
             'REFRESH-INTERVAL;VALUE=DURATION:PT6H', 'X-PUBLISHED-TTL:PT6H']
    rows = db.all_("SELECT * FROM content_drafts WHERE store_domain=? AND status IN ('draft','approved','scheduled',"
                   "'published') ORDER BY id", (domain,))
    for r in rows:
        at = r['published_at'] if r['status'] == 'published' and r['published_at'] else r['planned_at']
        if not at:
            continue
        kind = content_agent.DRAFT_TYPES.get(r['draft_type'], r['draft_type'])
        state = {'draft': 'Needs your approval', 'approved': 'Approved, publishes on this date',
                 'scheduled': 'Approved, publishes on this date', 'published': 'Live on your store'}[r['status']]
        link = '%s/content?%s' % (_base(), urllib.parse.urlencode(dict(
            d=domain, view='calendar', month=storetime.date_of(at, tz).strftime('%Y-%m'), item=r['id'])))
        summary = '%s%s' % (r['title'] or kind, ' (needs approval)' if r['status'] == 'draft' else '')
        lines += ['BEGIN:VEVENT', 'UID:produkto-draft-%d@getprodukto.com' % r['id'], 'DTSTAMP:' + stamp,
                  'DTSTART:' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(at)), 'DURATION:PT30M',
                  'SUMMARY:' + _ics_text(summary),
                  'DESCRIPTION:' + _ics_text('%s. %s.\nOpen it: %s' % (kind[:1].upper() + kind[1:], state, link)),
                  'URL:' + link, 'TRANSP:TRANSPARENT', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return 200, '\r\n'.join(_fold(l) for l in lines) + '\r\n'


def legend(types):
    keys = [k for k in ('product_fix', 'faq', 'comparison', 'guide') if k in types]
    return '<ul class="cal-key" aria-label="Colours">%s<li><i class="cal-k-pending"></i>Needs your approval</li>' \
        '<li>Drag an item to another day to move it</li></ul>' % ''.join(
            '<li><i class="ca-%s"></i>%s</li>' % (k, E(types[k])) for k in keys)


def drag_script(domain):
    """Drag a planned item onto another day: posts the same 'move' the detail panel's date field uses.
    Past days aren't drop targets, and the server refuses them anyway."""
    return ('<form id="cal-move-f" method="post" action="/content" hidden><input name="d" value="%s">'
            '<input name="action" value="move"><input name="id"><input name="day"></form><script>(function(){'
            'var cal=document.getElementById("ca-cal"),f=document.getElementById("cal-move-f"),id=null;if(!cal)return;'
            'cal.addEventListener("dragstart",function(e){var a=e.target.closest("[data-id]");if(!a)return;'
            'id=a.getAttribute("data-id");e.dataTransfer.effectAllowed="move";e.dataTransfer.setData("text/plain",id);});'
            'function cell(e){return e.target.closest&&e.target.closest("[data-day]");}'
            'cal.addEventListener("dragover",function(e){var c=cell(e);if(c&&id){e.preventDefault();c.classList.add("cal-drop");}});'
            'cal.addEventListener("dragleave",function(e){var c=cell(e);if(c)c.classList.remove("cal-drop");});'
            'cal.addEventListener("drop",function(e){var c=cell(e);if(!c||!id)return;e.preventDefault();'
            'f.elements.id.value=id;f.elements.day.value=c.getAttribute("data-day");f.submit();});'
            'cal.addEventListener("dragend",function(){id=null;});})();</script>') % E(domain)


def connect_box(domain):
    """The Calendar view's 'Connect your calendar' section."""
    url = feed_url(domain)
    webcal = re.sub(r'^https?://', 'webcal://', url)
    google = 'https://calendar.google.com/calendar/render?' + urllib.parse.urlencode(dict(cid=webcal))
    local = url.startswith('http://localhost') or url.startswith('http://127.')
    return ('<details class="cal-connect"><summary>Connect your calendar</summary>'
            '<p class="cr-muted">Every planned page shows up in Google Calendar, Apple Calendar or Outlook, and moves '
            'when you move it here. Calendar apps refresh it every few hours.</p>'
            '<div class="cs-row"><a class="ca-btn ca-primary" href="%s" target="_blank" rel="noopener">Add to Google '
            'Calendar</a><a class="ca-btn" href="%s">Open in Apple Calendar or Outlook</a></div>'
            '<label class="cal-link">Or paste this link into any calendar app (Subscribe / From URL)'
            '<input readonly value="%s" onclick="this.select()"></label>'
            '<div class="cr-muted cal-reset">Anyone with this link can see your planned page titles and dates. '
            '<form method="post" action="/content"><input type="hidden" name="d" value="%s">'
            '<input type="hidden" name="action" value="ical_reset"><button class="ca-link-btn">Make a new link</button>'
            '</form> and the old one stops working.</div>%s</details>') % (
        E(google), E(webcal), E(url), E(domain),
        '<p class="cal-warn">This copy runs on a laptop, so calendar apps can\'t reach the link. It works on '
        'app.getprodukto.com.</p>' if local else '')
