"""Load a hand-read source into the agent's brain (brain.py).

For a talk, study or post Kelian wants in the brain now, read in full by a person rather than by the
nightly reader (which keeps at most 5 claims per item and may never find it). The seed file lives in
mvp/content-agent/brain-seeds/ so it can be loaded again on any database, including the server's
when the brain ships.

Grading still goes through brain.store(): only an engine's own page can be Official, Measured needs who
ran it and a sample with a real count (otherwise it becomes an Opinion), and settle() decides the status.
"related_like" is a SQL LIKE on an existing finding's claim, so a seed doesn't depend on row ids.

    PRODUKTO_DB=<file> python3 brain_seed.py ../content-agent/brain-seeds/<file>.json

Free (no model, no Apify). Loading the same seed twice does nothing.
"""
import json
import sys
import time

import brain
import db


def load(path):
    seed = json.load(open(path))
    it = seed['item']
    brain.init()
    if brain._seen('manual', it['url']):
        return dict(status='already loaded', url=it['url'])
    item_id = brain._queue(None, 'manual', it['source'], it['url'], title=it.get('title', ''),
                           author=it.get('author', ''), published=it.get('published', ''),
                           vendor=it.get('vendor', 0), official=it.get('official', 0),
                           status='read', note=it.get('note', ''))
    item = dict(db.one('SELECT * FROM brain_items WHERE id=?', (item_id,)))
    claims = []
    for c in seed['claims']:
        c = dict(c)
        like = c.pop('related_like', None)
        row = db.one('SELECT id FROM brain_findings WHERE claim LIKE ? ORDER BY id LIMIT 1', (like,)) if like else None
        c['related_id'] = row['id'] if row else 0
        if like and not row:
            c['verdict'] = 'new'
        c.setdefault('verdict', 'new')
        c.setdefault('measured_by_vendor', bool(it.get('vendor')))
        claims.append(c)
    ids = []
    for i in range(0, len(claims), 5):                          # store() keeps 5 claims per call
        ids += brain.store(item, dict(relevant=True, kind='study', announcement='', claims=claims[i:i + 5]))
    db.write("UPDATE brain_items SET read_at=?, cost_usd=0, note=? WHERE id=?",
             (time.time(), '%d findings, loaded by hand. %s' % (len(ids), it.get('note', '')), item_id))
    brain._mark('manual', [it['url']])
    if it.get('youtube_id'):
        brain._mark('youtube', [it['youtube_id']])              # the nightly collector skips it
    return dict(status='loaded', item=item_id, findings=ids)


if __name__ == '__main__':
    out = load(sys.argv[1])
    print(json.dumps(out))
    for fid in out.get('findings') or []:
        f = db.one('SELECT status, evidence, confirmed_by, claim FROM brain_findings WHERE id=?', (fid,))
        print('%4d  %-9s %-8s %s  %s' % (fid, f['status'], f['evidence'],
                                         ('confirmed by %s' % f['confirmed_by']) if f['confirmed_by'] else '',
                                         f['claim'][:90]))
