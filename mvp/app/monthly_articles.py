"""Monthly articles: the agent writes the month's buying guides and comparison pages by itself (18 Oct 2026).

On the 1st of each month (store time; the first scheduler tick of the month, so a missed day still runs)
the agent drafts as many articles as the plan includes and spreads them over the month's calendar slots.
It never publishes them: each still needs the merchant's approval, and an unapproved one just waits.

Which questions get an article. Only TRACKED buyer questions, so every article can be measured before and
after. Ranked by how much the store is losing that question (the Opportunity's weight) times how winnable
it is (briefs.winnable: questions where AI mostly cites big, established sites are harder for a small brand;
Kelian's point, 18 Oct). A question that already has an article (not rejected) is skipped.

When there aren't enough questions worth an article, it writes fewer and says so, pointing the merchant to
add buyer questions, instead of writing about questions nobody measures.

Cost: a few helper-model calls per article (a cent or two each), only for stores that have articles in
their plan (or that switched it on, for admin and demo stores).
"""
import threading
import time

import db
import storetime

QUESTION_TYPES = ('missing', 'competitor', 'low')       # Opportunities keyed by one buyer question
ARTICLE_TYPES = ('guide', 'comparison')
WEIGHT = {'winnable': 1.0, 'mixed': 0.6, 'hard': 0.25, '': 0.5}
DEMO_COUNT = 10                                       # stores with no plan limit, when switched on
_running = set()


def count(domain):
    """Articles to write this month: the plan's article allowance (packs), or DEMO_COUNT for stores with no
    limit when the merchant switched it on. 0 means the writer doesn't run."""
    import content_plan
    import content_setup
    s = content_setup.get(domain)
    a = content_plan.allowance(domain, 'articles')
    if a is None:
        return DEMO_COUNT if s.get('monthly_articles') else 0
    return a if s.get('monthly_articles', True) else 0


def month(domain):
    return storetime.today(storetime.zone(domain)).strftime('%Y-%m')


def state(domain):
    import content_setup
    return (content_setup.get(domain).get('monthly') or {}).get(month(domain))


def _has_article(domain, key):
    return db.one("SELECT d.id FROM content_drafts d JOIN content_briefs b ON b.id=d.brief_id WHERE d.store_domain=? "
                  "AND b.opportunity_key=? AND d.draft_type IN ('guide','comparison') AND d.status!='rejected' LIMIT 1",
                  (domain, key))


def ranked(domain):
    """[{type, key, score, level, big_share}] best first: tracked questions the store is losing, weighted by
    how winnable they are, without the ones that already have an article."""
    import briefs
    import opportunities
    ps, _, _, cites = briefs._evidence(domain)
    if not ps:
        return []
    st = opportunities._statuses(domain)
    best = {}
    for r in opportunities.find(domain):
        if r['type'] not in QUESTION_TYPES or st.get((r['type'], r['key']), {'status': 'open'})['status'] != 'open':
            continue
        w = briefs.winnable([r['key']], cites)
        score = (r.get('weight') or 0) * WEIGHT[w['level']]
        if r['key'] not in best or score > best[r['key']]['score']:
            best[r['key']] = dict(type=r['type'], key=r['key'], score=score, level=w['level'], big_share=w['big_share'])
    return sorted((b for b in best.values() if b['score'] > 0 and not _has_article(domain, b['key'])),
                  key=lambda b: -b['score'])


def _slots(domain, n):
    """n publish slots spread evenly over the rest of the month (at the merchant's days, pace and hour);
    past the month's end only when it has too few."""
    import content_calendar
    tz = storetime.zone(domain)
    this = month(domain)
    free = [t for t in content_calendar.free_slots(domain, count=60)
            if storetime.date_of(t, tz).strftime('%Y-%m') == this]
    if len(free) < n:
        return content_calendar.free_slots(domain, count=n)
    step = len(free) / n
    return [free[int(i * step)] for i in range(n)]


def run(domain, force=False):
    """Write this month's articles in a background thread. Runs once a month per store unless force."""
    import content_setup
    n = count(domain)
    import agent_review
    if not n or domain in _running or (state(domain) and not force) or not content_setup.done(domain):
        return False
    if not force and agent_review.reviewing(domain):
        return False          # wait for the self-review, so this month's articles use its lessons
    _running.add(domain)
    s = content_setup.get(domain)
    s.setdefault('monthly', {})[month(domain)] = dict(total=n, done=0, failed=0, ids=[], started_at=time.time())
    content_setup.put(domain, s)

    def save(**kw):
        st = content_setup.get(domain)
        st['monthly'][month(domain)].update(kw)
        content_setup.put(domain, st)

    def go():
        import content_agent
        done, failed, ids = 0, 0, []
        try:
            slots = _slots(domain, n)
            for r in ranked(domain):
                if done >= n:
                    break
                did, err = content_agent.draft_for(domain, r['type'], r['key'], only=ARTICLE_TYPES)
                if did:
                    db.write('UPDATE content_drafts SET planned_at=? WHERE id=? AND planned_at IS NULL',
                             (slots[done], did))
                    done += 1
                    ids.append(did)
                else:
                    failed += 1
                save(done=done, failed=failed, ids=ids)
        finally:
            save(done=done, failed=failed, ids=ids, short=max(0, n - done), finished_at=time.time())
            _running.discard(domain)
    threading.Thread(target=go, daemon=True).start()
    return True


def run_due():
    """Called by the scheduler each tick: start the month's articles for every store that hasn't had them."""
    import content_setup
    content_setup.init()
    started = []
    for r in db.all_('SELECT store_domain FROM content_settings'):
        try:
            if run(r['store_domain']):
                started.append(r['store_domain'])
        except Exception as e:                                   # noqa: BLE001 - one store never stops the rest
            print('monthly articles: %s failed (%s)' % (r['store_domain'], e))
    return started


def note(domain):
    """One line for the Articles meter on the board: what the writer did or will do this month."""
    n = count(domain)
    st = state(domain)
    if not n and not st:
        return ''
    if domain in _running and st:
        return 'Writing this month\'s articles: %d of %d done.' % (st['done'], st['total'])
    if st and st.get('finished_at'):
        line = '%d written on %s from the questions you\'re losing and can win.' % (
            st['done'], storetime.label(st['started_at'], storetime.zone(domain), '%-d %b'))
        if st.get('short'):
            line += (' %d fewer than planned: not enough tracked buyer questions need one. '
                     'Track more buyer questions to give the agent more.' % st['short'])
        return line
    return 'This month\'s articles are written on the 1st from the questions you\'re losing and can win.'
