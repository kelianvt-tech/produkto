"""Fill in the two agents for a sales demo: drafts, pages that went live, and a monthly review.

Kelian's demo flow (2026-10-11): one real scan of the prospect's store, then demo_history.py simulates the
past 30 days. This adds the agents on top (2026-10-18), so Product page fixes and AEO articles aren't empty:

  1. Real drafts written from the prospect's own catalog: product page fixes and AEO articles (a few cents).
  2. Some are marked as having gone live on past dates, inside the simulated history. Nothing is sent to
     Shopify: the status changes in Produkto's database only, with no live link.
  3. The real self-review (agent_review.py) runs on that history, so Results shows before/since numbers,
     verdicts and lessons. One fix goes live only 5 days back, so at least one row honestly reads
     "too early to tell".

Nothing on the dashboard marks this as simulated; Kelian says so on the call. Everything added is listed in
the store's content_settings under 'demo_sim', and remove() deletes it all. demo_history.remove() calls it, so
`python3 demo_history.py <store> --remove` and a paying brand claiming its store clean up both.

    python3 demo_history.py prospect.com          # first: 30 simulated days
    python3 demo_agents.py prospect.com           # then: the agents
    python3 demo_agents.py prospect.com --remove
"""
import argparse
import time

import db

DAY = 86400
FIX_DAYS = (20, 16, 5)        # fixes live this many days ago; the rest stay in Ready to review
ARTICLE_DAYS = (12,)          # articles live this many days ago; the next is scheduled ahead
SCHEDULE_AHEAD = 5


def _state(domain):
    import content_setup
    return content_setup.get(domain)


def add(domain, fixes=4, articles=2, log=print):
    """Draft, back-date and review. Returns the ids of the drafts it made."""
    import briefs
    import content_agent
    import content_review
    import content_setup
    import monthly_articles
    import agent_review
    content_agent.init()
    if not db.get_prompt_set(domain):
        raise SystemExit('No buyer questions for %s. Onboard the store and run one scan first.' % domain)
    s = content_setup.get(domain)
    demo = s.get('demo_sim') or {}
    if demo.get('drafts'):
        raise SystemExit('%s already has demo agent data. Run with --remove first.' % domain)
    if not content_setup.done(domain):
        s['part1_done_at'] = time.time()              # skip setup for the demo; remove() puts it back
        demo['setup'] = True
    s['demo_sim'] = demo
    content_setup.put(domain, s)

    made_fixes, made_articles = [], []
    for r in briefs.candidates(domain):
        if len(made_fixes) >= fixes:
            break
        did, err = content_agent.draft_for(domain, r['type'], r['key'], avoid=content_agent.covered(domain),
                                           only=('product_fix',))
        if did and did not in made_fixes:
            made_fixes.append(did)
            log('Drafted product page fix %d.' % did)
    for r in monthly_articles.ranked(domain):
        if len(made_articles) >= articles:
            break
        did, err = content_agent.draft_for(domain, r['type'], r['key'], only=monthly_articles.ARTICLE_TYPES)
        if did and did not in made_articles:
            made_articles.append(did)
            log('Drafted AEO article %d.' % did)

    def gaps(did):
        body, _ = content_agent._latest(did)
        return len(content_review.gaps(body))
    now = time.time()

    def go_live(did, days):
        at = now - days * DAY
        db.write("UPDATE content_drafts SET status='published', approved_at=?, approved_by='demo', published_at=?, "
                 "planned_at=NULL, live_url=NULL, updated_at=? WHERE id=?", (at, at, at, did))
    # Back-date the drafts with no open facts first: a live page shouldn't still be asking questions.
    for did, days in zip(sorted(made_fixes, key=gaps), FIX_DAYS):
        go_live(did, days)
    ordered = sorted(made_articles, key=gaps)
    for did, days in zip(ordered, ARTICLE_DAYS):
        go_live(did, days)
    for did in ordered[len(ARTICLE_DAYS):]:
        status = 'approved' if not gaps(did) else 'draft'
        db.write('UPDATE content_drafts SET status=?, planned_at=?, approved_at=? WHERE id=?',
                 (status, now + SCHEDULE_AHEAD * DAY, now if status == 'approved' else None, did))

    s = content_setup.get(domain)
    s['demo_sim']['drafts'] = made_fixes + made_articles
    content_setup.put(domain, s)
    for lane in ('fixes', 'articles'):
        rv = agent_review.review(domain, lane, force=True)
        log('Reviewed %s: %s.' % (lane, ', '.join('%s %s' % (x['product'] or x['title'], x['verdict'])
                                                 for x in rv['rows']) or 'nothing live'))
    return made_fixes + made_articles


def remove(domain):
    """Delete everything add() made. Returns how many drafts were removed."""
    import content_setup
    try:
        s = content_setup.get(domain)
    except Exception:                                            # noqa: BLE001 - no agent tables yet
        return 0
    demo = s.get('demo_sim') or {}
    ids = demo.get('drafts') or []
    with db._lock, db.conn() as c:
        for did in ids:
            row = c.execute('SELECT brief_id FROM content_drafts WHERE id=?', (did,)).fetchone()
            c.execute('DELETE FROM content_draft_versions WHERE draft_id=?', (did,))
            c.execute('DELETE FROM content_drafts WHERE id=?', (did,))
            if row and row[0]:
                c.execute('DELETE FROM content_briefs WHERE id=?', (row[0],))
        if demo:
            try:
                c.execute('DELETE FROM agent_reviews WHERE store_domain=?', (domain,))
            except Exception:                                    # noqa: BLE001 - table not made yet
                pass
    if demo:
        if demo.get('setup'):
            s.pop('part1_done_at', None)
        s.pop('demo_sim', None)
        content_setup.put(domain, s)
    return len(ids)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('domain')
    p.add_argument('--fixes', type=int, default=4)
    p.add_argument('--articles', type=int, default=2)
    p.add_argument('--remove', action='store_true')
    a = p.parse_args()
    db.init()
    n = remove(a.domain)
    if n:
        print('Removed %d demo drafts for %s.' % (n, a.domain))
    if not a.remove:
        print('Added %d demo drafts for %s.' % (len(add(a.domain, a.fixes, a.articles)), a.domain))
