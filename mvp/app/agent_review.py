"""Monthly self-review for both agents: Product page fixes and AEO articles (18 Oct 2026).

On the 1st of each month (store time), before the monthly writer runs, each agent looks back at what it put
live and learns from it. It is the re-fix loop of mvp/content-agent/PLAN.md (day 39b) plus a lessons note:

  1. Measure. For every live fix and article: how often AI named its product(s) on the buyer questions it
     was written for, in the 14 days before it went live vs. the days since. Same questions, same engines.
  2. Verdict, honestly: "moved" or "dropped" only when the change is bigger than daily noise (a simple
     two-proportion test), "no change" when there are enough answers and no real difference, and
     "too early" when it has been live under 14 days or has fewer than MIN_AFTER answers since. With one
     answer per question a day, most early verdicts are "too early"; the report says so.
  3. Lessons. One short note per store and agent, written by the helper model from the verdicts and what
     each change was (about a cent). It goes into next month's drafts beside the approved examples
     (drafts._lessons). It describes what went with movement; it never claims a fix caused it.
  4. Re-fix. A product page fix with "no change" or "dropped" after 30 days gets a new draft with a
     different angle: the writer is told what the live version tried and how it did. It lands in Needs
     your facts / Ready like any draft, needs approval, and counts toward the month's allowance.
  5. Report. The agent's Results tab shows the month: what went live, before vs. after, the verdict,
     the lessons and what was queued next. Every verdict is kept for METHODOLOGY.md, including fixes that
     did nothing.

Copy rule (produkto-copy): show what changed, never claim the fix caused it.
"""
import json
import math
import threading
import time
from html import escape as E

import db
import storetime

BEFORE_DAYS = 14
MIN_DAYS = 14              # live at least this long before a verdict
MIN_AFTER = 10             # answers since going live before a verdict
REFIX_DAYS = 30            # a fix that hasn't moved after this long gets a new version
REFIX_SHARE = 0.2          # re-fixes use at most this share of the month's fix allowance
LANE_TYPES = {'fixes': ('product_fix', 'faq'), 'articles': ('comparison', 'guide')}
VERDICTS = {'moved': 'Named more often', 'dropped': 'Named less often', 'flat': 'No change', 'early': 'Too early to tell',
            'unmeasured': "Can't measure"}
_running = set()


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS agent_reviews (id INTEGER PRIMARY KEY, store_domain TEXT NOT NULL, '
                  'month TEXT NOT NULL, lane TEXT NOT NULL, rows TEXT, lessons TEXT, refixes TEXT, created_at REAL, '
                  'UNIQUE(store_domain, month, lane))')


def _month(domain):
    return storetime.today(storetime.zone(domain)).strftime('%Y-%m')


# ---- 1-2: measure and judge ---------------------------------------------------------------

def _named(ps, qs, product_ids, start, end):
    """(answers naming one of these products, answers) to these questions in [start, end)."""
    import evidence
    import period
    scans = period.done_scans(ps['id'], start, end)
    if not scans or not qs:
        return 0, 0
    p = evidence.product_context(ps)
    answers, mentions = evidence.load(tuple(s['id'] for s in scans), p)
    want = set(qs)
    answers = [a for a in answers if a['prompt'] in want and start <= (a['created_at'] or 0) < end]
    ids = {a['id'] for a in answers}
    hit = {m['answer_id'] for m in mentions if m['answer_id'] in ids and m['matched_product_id'] in product_ids}
    return len(hit), len(answers)


def verdict(b_hit, b_n, a_hit, a_n, days):
    """'moved' / 'dropped' only past daily noise (two-proportion z > 1.96), else 'flat'; 'early' before enough."""
    if days < MIN_DAYS or a_n < MIN_AFTER:
        return 'early'
    if not b_n:
        return 'early'
    p1, p2 = b_hit / b_n, a_hit / a_n
    pool = (b_hit + a_hit) / (b_n + a_n)
    se = math.sqrt(pool * (1 - pool) * (1 / b_n + 1 / a_n)) if 0 < pool < 1 else 0
    if not se:
        return 'flat'
    z = (p2 - p1) / se
    return 'moved' if z > 1.96 else 'dropped' if z < -1.96 else 'flat'


def measure(domain, lane):
    """One row per live draft of this agent, with its before/after and verdict."""
    import content_agent
    ps = db.get_prompt_set(domain)
    if not ps:
        return []
    tracked = set(ps['prompts'])
    by_handle = {p['handle']: p['id'] for p in ps['catalog_snapshot']}
    out = []
    for r in content_agent.drafts(domain, ('published',)):
        if r['draft_type'] not in LANE_TYPES[lane] or not r['published_at']:
            continue
        body, _ = content_agent._latest(r['id'])
        brief = db.one('SELECT questions, opportunity_kind, opportunity_key FROM content_briefs WHERE id=?',
                       (r['brief_id'],)) if r['brief_id'] else None
        qs = [q['question'] for q in json.loads(brief['questions'] or '[]')] if brief else []
        live_qs = [q for q in qs if q in tracked]
        handles = [p.get('handle') for p in (body.get('products') or [body.get('product') or {}])]
        pids = {by_handle[h] for h in handles if h in by_handle}
        at = r['published_at']
        days = int((time.time() - at) // 86400)
        row = dict(id=r['id'], type=r['draft_type'], title=r['title'], published_at=at, days=days,
                   questions=live_qs, product=(body.get('product') or {}).get('title') or '',
                   change=_what_changed(body, r['draft_type']), live_url=r['live_url'],
                   opp=(brief['opportunity_kind'], brief['opportunity_key']) if brief else None)
        if not live_qs or not pids:
            row.update(before=[0, 0], after=[0, 0], verdict='unmeasured',
                       note='Its buyer questions are no longer tracked.' if qs and not live_qs else 'No buyer question to measure it on.')
        else:
            b = _named(ps, live_qs, pids, at - BEFORE_DAYS * 86400, at)
            a = _named(ps, live_qs, pids, at, time.time() + 1)
            row.update(before=list(b), after=list(a), verdict=verdict(b[0], b[1], a[0], a[1], days))
        out.append(row)
    return sorted(out, key=lambda x: -x['published_at'])


def _what_changed(body, t):
    if t == 'product_fix':
        cur = (body.get('current') or {}).get('title') or ''
        new = body.get('title') or ''
        bits = ['title "%s" → "%s"' % (cur, new)] if new and new != cur else []
        if body.get('spec_table'):
            bits.append('%d spec rows' % len(body['spec_table']))
        bits.append('description rewritten')
        return '; '.join(bits)
    if t == 'faq':
        return '%d FAQs added' % len(body.get('faqs') or [])
    return '%s, %d sections' % ('comparison table' if t == 'comparison' else 'buying guide',
                                len(body.get('sections') or body.get('rows') or []))


# ---- 3: lessons -----------------------------------------------------------------------------

LESSONS_RULES = """You review an AI agent's own work for an online store: page changes it put live, and whether AI shopping assistants named the store's product more or less often afterwards, on the same buyer questions.

Write 2-5 short lessons for next month's drafts, as instructions to the writer ("Lead the title with the material buyers ask about"). Base them only on the RESULTS given:
- Learn from "named more often" and "named less often" rows. "No change" rows mean that kind of change didn't show an effect yet.
- Ignore "too early" and "can't measure" rows, except to say there isn't enough evidence yet.
- Never claim a change caused a result; say what went with it ("Fixes that added the material to the title were named more often").
- If nothing has a verdict yet, return one lesson: there isn't enough evidence yet, keep following the store's approved examples.
Plain words, no hype."""

LESSONS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lessons"],
                  "properties": {"lessons": {"type": "array", "items": {"type": "string"}}}}


def lessons(rows, usage=None):
    """2-5 lessons from this month's verdicts, or a no-evidence-yet note without a model call."""
    judged = [r for r in rows if r['verdict'] in ('moved', 'dropped', 'flat')]
    if not judged:
        return ['Not enough evidence yet: nothing live has had enough answers to judge. Keep following the '
                'store\'s approved examples.']
    import llm
    text = '\n'.join('- %s (%s): %s. Named in %d of %d answers before, %d of %d since (%d days live). Verdict: %s.' % (
        r['title'], r['type'], r['change'], r['before'][0], r['before'][1], r['after'][0], r['after'][1], r['days'],
        VERDICTS[r['verdict']]) for r in rows)
    try:
        return llm.json_call(LESSONS_RULES, 'RESULTS:\n' + text, 'agent_lessons', LESSONS_SCHEMA,
                             usage=usage, attempts=2)['lessons'][:5]
    except Exception:                                            # noqa: BLE001 - the review still saves
        return []


def current_lessons(domain, lane):
    """The newest lessons for this store and agent, for drafts.py."""
    try:
        init()
        row = db.one('SELECT lessons FROM agent_reviews WHERE store_domain=? AND lane=? ORDER BY month DESC LIMIT 1',
                     (domain, lane))
    except Exception:                                            # noqa: BLE001
        return []
    return json.loads(row['lessons'] or '[]') if row else []


# ---- 4: re-fix ------------------------------------------------------------------------------

def refix(domain, rows):
    """New versions for live product page fixes that haven't moved after REFIX_DAYS. Returns draft ids."""
    import briefs
    import content_agent
    import content_plan
    import drafts as _drafts
    import llm
    import selfreview
    a = content_plan.allowance(domain, 'fixes')
    cap = max(1, int((a if a is not None else 50) * REFIX_SHARE))
    out = []
    for r in rows:
        if len(out) >= cap:
            break
        if r['type'] != 'product_fix' or r['verdict'] not in ('flat', 'dropped') or r['days'] < REFIX_DAYS or not r['opp']:
            continue
        if db.one("SELECT d.id FROM content_drafts d JOIN content_briefs b ON b.id=d.brief_id WHERE d.store_domain=? "
                  "AND b.opportunity_key=? AND d.draft_type='product_fix' AND d.status IN ('draft','approved') "
                  "AND d.created_at>?", (domain, r['opp'][1], r['published_at'])):
            continue                                             # a re-fix is already waiting
        b = briefs.build(domain, *r['opp'])
        if not b:
            continue
        note = dict(problem='The live version (%s), published %s, was named in %d of %d answers since (%s).' % (
            r['change'], time.strftime('%-d %b', time.localtime(r['published_at'])), r['after'][0], r['after'][1],
            VERDICTS[r['verdict']].lower()), fix='Take a different angle from the live version; don\'t repeat what it tried.')
        b['editor_notes'] = [note]
        usage = llm.Usage()
        try:
            res = _drafts.product_fix(b, usage=usage)
        except (ValueError, llm.LLMError):
            continue
        res['why'] = 'Re-fix: %s %s' % (note['problem'], 'This version tries a different angle.')
        res['review'] = selfreview.review(res, 'product_fix', b, usage=usage)
        out.append(_drafts.save(briefs.save(b, 'product_fix'), b, res, 'product_fix', usage=usage))
    return out


# ---- the monthly run ------------------------------------------------------------------------

def review(domain, lane, force=False):
    """Measure, learn, re-fix and save this month's review for one agent. Returns the saved row."""
    init()
    month = _month(domain)
    if not force and db.one('SELECT id FROM agent_reviews WHERE store_domain=? AND month=? AND lane=?',
                            (domain, month, lane)):
        return None
    rows = measure(domain, lane)
    learnt = lessons(rows)
    queued = refix(domain, rows) if lane == 'fixes' else []
    with db.conn() as c:
        c.execute('INSERT OR REPLACE INTO agent_reviews (store_domain, month, lane, rows, lessons, refixes, created_at) '
                  'VALUES (?,?,?,?,?,?,?)', (domain, month, lane, json.dumps(rows), json.dumps(learnt),
                                             json.dumps(queued), time.time()))
    return dict(rows=rows, lessons=learnt, refixes=queued)


def run_due():
    """Scheduler: each store with the agent set up gets both reviews once a month, before the monthly writer."""
    import content_setup
    content_setup.init()
    started = []
    for r in db.all_('SELECT store_domain FROM content_settings'):
        d = r['store_domain']
        if d in _running or not content_setup.done(d):
            continue
        init()
        if db.one('SELECT id FROM agent_reviews WHERE store_domain=? AND month=? AND lane=?', (d, _month(d), 'fixes')):
            continue
        _running.add(d)

        def go(d=d):
            try:
                for lane in ('fixes', 'articles'):
                    review(d, lane)
            except Exception as e:                               # noqa: BLE001
                print('agent review: %s failed (%s)' % (d, e))
            finally:
                _running.discard(d)
        threading.Thread(target=go, daemon=True).start()
        started.append(d)
    return started


def reviewing(domain):
    return domain in _running


# ---- 5: the Results tab ---------------------------------------------------------------------

def page(domain, lane):
    init()
    rows = db.all_('SELECT * FROM agent_reviews WHERE store_domain=? AND lane=? ORDER BY month DESC LIMIT 6',
                   (domain, lane))
    import urllib.parse
    run = ('<form method="post" action="/content" class="ar-run"><input type="hidden" name="d" value="%s">'
           '<input type="hidden" name="lane" value="%s"><input type="hidden" name="action" value="review_now">'
           '<button class="ca-btn">Review now</button></form>' % (E(domain), E(lane)))
    if reviewing(domain):
        return ('<div class="ca-empty"><p><b>Reviewing this month\'s results…</b> About a minute.</p></div>'
                '<meta http-equiv="refresh" content="15">' + CSS)
    if not rows:
        return ('<div class="ar-top"><p class="ar-lead">On the 1st of each month this agent looks back at what it put '
                'live: how often AI named those products before and since, what to learn from it, and what to '
                'try next. The first review runs on the 1st.</p>%s</div>' % run) + CSS
    tz = storetime.zone(domain)
    out = ''
    for i, rv in enumerate(rows):
        items = json.loads(rv['rows'] or '[]')
        learnt = json.loads(rv['lessons'] or '[]')
        queued = json.loads(rv['refixes'] or '[]')
        month = time.strftime('%B %Y', time.strptime(rv['month'], '%Y-%m'))
        counts = {k: sum(1 for x in items if x['verdict'] == k) for k in VERDICTS}
        summary = ', '.join('%d %s' % (counts[k], VERDICTS[k].lower()) for k in VERDICTS if counts[k]) or 'nothing live yet'
        table = ''.join(
            '<tr><td><strong>%s</strong><span>%s</span></td><td class="ar-num">%s</td><td class="ar-num">%s</td>'
            '<td><span class="ar-v ar-%s">%s</span>%s</td></tr>' % (
                E(x['product'] or x['title']), E(x['change']), _pct(x['before']), _pct(x['after']), x['verdict'],
                E(VERDICTS[x['verdict']]), ('<span class="ar-note">%s</span>' % E(x.get('note') or
                                             ('%d days live' % x['days']))) if x['verdict'] in ('early', 'unmeasured') else '')
            for x in items)
        next_line = ('<p class="ar-next"><b>Queued next:</b> %d new version%s of fixes that didn\'t move, in Drafts. '
                     'They need your approval.</p>' % (len(queued), '' if len(queued) == 1 else 's')) if queued else ''
        out += ('<section class="ar-month"%s><header><h2>%s</h2><span>%s</span></header>%s'
                '<div class="ar-lessons"><h3>What it learned</h3><ul>%s</ul></div>%s</section>') % (
            '' if i == 0 else ' data-old', E(month), E(summary),
            ('<table class="ar-t"><thead><tr><th>%s</th><th>Before</th><th>Since</th><th>Result</th></tr></thead>'
             '<tbody>%s</tbody></table>' % ('Page' if lane == 'fixes' else 'Article', table)) if items else
            '<p class="ar-lead">Nothing was live during this month.</p>',
            ''.join('<li>%s</li>' % E(l) for l in learnt) or '<li>No lessons this month.</li>', next_line)
    return ('<div class="ar-top"><p class="ar-lead">Before = the 14 days before a page went live. Since = every day '
            'after, on the same buyer questions. It shows what changed, not why.</p>%s</div>%s' % (run, out)) + CSS


def _pct(pair):
    hit, n = pair
    return '%d of %d <em>%d%%</em>' % (hit, n, round(100 * hit / n)) if n else '<em>no answers</em>'


CSS = """<style>
.ar-top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin:0 0 18px}
.ar-lead{margin:0;color:var(--muted,#5b6577);font-size:14px;max-width:70ch}
.ar-run{margin:0}
.ar-month{border:1px solid var(--line,#e3e8ef);border-radius:14px;padding:18px 20px;margin:0 0 16px;background:var(--surface,#fff)}
.ar-month header{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}
.ar-month h2{margin:0;font-size:17px;letter-spacing:-.01em}.ar-month header span{color:var(--muted,#5b6577);font-size:13px}
.ar-t{width:100%;border-collapse:collapse;font-size:13.5px}
.ar-t th{text-align:left;font-size:12px;font-weight:500;color:var(--muted,#5b6577);padding:8px 10px;border-bottom:1px solid var(--line,#e3e8ef)}
.ar-t td{padding:10px;border-bottom:1px solid var(--line,#e3e8ef);vertical-align:top}
.ar-t td strong{display:block;font-weight:600}.ar-t td span{font-size:12.5px;color:var(--muted,#5b6577)}
.ar-num{font-variant-numeric:tabular-nums;white-space:nowrap}.ar-num em{font-style:normal;color:var(--muted,#5b6577);margin-left:4px}
.ar-v{display:inline-block;font-size:12.5px;font-weight:600}
.ar-moved{color:#18804b}.ar-dropped{color:#b8432e}.ar-flat{color:var(--text,#0b1b35)}.ar-early,.ar-unmeasured{color:var(--muted,#5b6577)}
.ar-note{display:block;font-size:12px}
.ar-lessons{margin-top:14px}.ar-lessons h3{font-size:13px;margin:0 0 6px}.ar-lessons ul{margin:0;padding-left:18px;font-size:13.5px;line-height:1.6}
.ar-next{margin:12px 0 0;font-size:13.5px}
html.dark .ar-month{background:#16181c;border-color:#262a30}html.dark .ar-t th,html.dark .ar-t td{border-color:#262a30}
html.dark .ar-moved{color:#45d08c}html.dark .ar-dropped{color:#f0846f}html.dark .ar-flat{color:#e4e8ee}
</style>"""
