"""Fill in past daily results for a demo store from its one real scan.

For sales demos: run one real scan for the prospect's store, then this script
copies that scan back over the previous N days, randomly dropping some
mentions so each day differs and the store's own visibility climbs towards
today's real figure. Nothing on the dashboard marks these as simulated -
Kelian says so on the call (2026-10-11).

Every copied scan's token starts with "sim-", so they never mix with real
scans and can be removed in one go:

    python3 demo_history.py clubhouseskin.com            # add 30 days
    python3 demo_history.py clubhouseskin.com --days 14
    python3 demo_history.py clubhouseskin.com --remove   # delete them all (and demo_agents.py's drafts)

Then `python3 demo_agents.py <store>` fills in the two agents on top of this history.

Costs nothing: no API or Apify calls.
"""

import argparse
import random
import uuid

import db
import scoring

DAY = 86400
SIM = 'sim-%'


def _store_scans(domain, simulated):
    return db.all_(
        "SELECT s.* FROM scans s JOIN prompt_sets ps ON ps.id = s.prompt_set_id "
        "WHERE ps.store_domain = ? AND s.status IN ('done','partial') AND s.token "
        + ("LIKE ?" if simulated else "NOT LIKE ?") + " ORDER BY s.run_at",
        (domain, SIM))


def remove(domain):
    import demo_agents
    demo_agents.remove(domain)          # the agents' demo drafts and review go with the simulated days
    scans = _store_scans(domain, True)
    with db._lock, db.conn() as c:
        for s in scans:
            ids = [r[0] for r in c.execute('SELECT id FROM answers WHERE scan_id=?', (s['id'],))]
            for a in ids:
                c.execute('DELETE FROM mentions WHERE answer_id=?', (a,))
                c.execute('DELETE FROM answer_processing WHERE answer_id=?', (a,))
            for table in ('answers', 'scores', 'product_scores'):
                c.execute('DELETE FROM %s WHERE scan_id=?' % table, (s['id'],))
            c.execute('DELETE FROM scans WHERE id=?', (s['id'],))
    return len(scans)


def add(domain, days):
    real = _store_scans(domain, False)
    if not real:
        raise SystemExit('No finished real scan for %s. Run one scan first.' % domain)
    base = real[-1]  # newest real scan supplies the answers...
    start = real[0]['run_at']  # ...dated back from the oldest one
    offset = base['run_at'] - start
    rng = random.Random(domain)
    answers = db.all_('SELECT * FROM answers WHERE scan_id=?', (base['id'],))
    mentions = {a['id']: db.all_('SELECT * FROM mentions WHERE answer_id=? ORDER BY rank', (a['id'],))
                for a in answers}
    for d in range(days, 0, -1):
        shift = d * DAY + offset
        # Own-product mentions kept: ~45% a month back, rising to ~100% today.
        keep_own = min(1.0, 0.45 + 0.55 * (1 - d / days) + rng.uniform(-0.08, 0.08))
        with db._lock, db.conn() as c:
            scan_id = c.execute(
                'INSERT INTO scans(token,prompt_set_id,run_at,finished_at,status,done,total,cost_cents,model_versions) '
                'VALUES(?,?,?,?,?,?,?,0,?)',
                ('sim-' + uuid.uuid4().hex, base['prompt_set_id'], base['run_at'] - shift,
                 (base['finished_at'] or base['run_at']) - shift, base['status'],
                 base['done'], base['total'], base['model_versions'])).lastrowid
            for a in answers:
                aid = c.execute(
                    'INSERT INTO answers(scan_id,prompt,model,engine,run_n,raw_text,citations,created_at) '
                    'VALUES(?,?,?,?,?,?,?,?)',
                    (scan_id, a['prompt'], a['model'], a['engine'], a['run_n'], a['raw_text'],
                     a['citations'], (a['created_at'] or base['run_at']) - shift)).lastrowid
                c.execute("INSERT INTO answer_processing(answer_id,status) VALUES(?,'done')", (aid,))
                rank = 0
                for m in mentions[a['id']]:
                    own = m['is_theirs'] or m['is_their_brand']
                    if rng.random() > (keep_own if own else 0.88):
                        continue
                    rank += 1
                    c.execute(
                        'INSERT INTO mentions(answer_id,product_name,brand,url,rank,is_theirs,is_their_brand,'
                        'matched_product_id,match_score,price) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (aid, m['product_name'], m['brand'], m['url'], rank if m['rank'] else m['rank'],
                         m['is_theirs'], m['is_their_brand'], m['matched_product_id'], m['match_score'], m['price']))
        scoring.score(scan_id)
    return days


# Everything a store accumulates, by table. Used by fresh_start().
_BY_STORE = ('agent_reviews', 'feed_checks', 'question_suggestions', 'catalog_facts', 'catalog_scope',
             'competitor_comparisons', 'competitor_suggestions', 'offsite_searches', 'opportunity_status', 'topics',
             'content_media', 'content_settings', 'shopify_connections', 'content_publish_log')


def fresh_start(domain):
    """A paying customer adds a store we set up for a demo: delete everything from the demo - scans, answers,
    buyer questions, topics, brand profile, agent drafts and settings - so onboarding and the Catalog
    Optimization Agent start exactly as for a new store (Kelian, 2026-10-21). The product list stays; onboarding
    re-reads it straight away. Returns how many scans were deleted."""
    with db._lock, db.conn() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sets = [r[0] for r in c.execute('SELECT id FROM prompt_sets WHERE store_domain=?', (domain,))]
        scans = [r[0] for s in sets for r in c.execute('SELECT id FROM scans WHERE prompt_set_id=?', (s,))]
        for sid in scans:
            answers = [r[0] for r in c.execute('SELECT id FROM answers WHERE scan_id=?', (sid,))]
            for a in answers:
                c.execute('DELETE FROM mentions WHERE answer_id=?', (a,))
                c.execute('DELETE FROM answer_processing WHERE answer_id=?', (a,))
            for t in ('answers', 'scores', 'product_scores', 'scan_batches'):
                if t in tables:
                    c.execute('DELETE FROM %s WHERE scan_id=?' % t, (sid,))
            c.execute('DELETE FROM scans WHERE id=?', (sid,))
        for s in sets:
            if 'prompt_types' in tables:
                c.execute('DELETE FROM prompt_types WHERE prompt_set_id=?', (s,))
            c.execute('DELETE FROM prompt_sets WHERE id=?', (s,))
        drafts = [r[0] for r in c.execute('SELECT id FROM content_drafts WHERE store_domain=?', (domain,))] \
            if 'content_drafts' in tables else []
        for d in drafts:
            c.execute('DELETE FROM content_draft_versions WHERE draft_id=?', (d,))
        for t in ('content_drafts', 'content_briefs') + _BY_STORE:
            if t in tables:
                c.execute('DELETE FROM %s WHERE store_domain=?' % t, (domain,))
        c.execute('DELETE FROM stores WHERE domain=?', (domain,))
    return len(scans)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('domain')
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--remove', action='store_true')
    args = p.parse_args()
    db.init()
    removed = remove(args.domain)
    if removed:
        print('Removed %d earlier simulated days for %s.' % (removed, args.domain))
    if not args.remove:
        print('Added %d simulated days for %s.' % (add(args.domain, args.days), args.domain))
