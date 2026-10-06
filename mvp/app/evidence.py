"""Shared, read-only evidence scope for catalog and product reporting.

Two filters live here, and both are applied at the single choke point in
`load()` so that no panel can forget one:

* the questions this product actually competes on, and
* the engines currently selected on the dashboard.

The engine selection rides on the context dict as `_engines` rather than being
passed to every call. There are a dozen `evidence.load(ids, p)` call sites and
an engine filter that only some of them honoured would quietly produce panels
that disagree with each other.
"""
import json
import os
import db
import config
from functools import lru_cache


def prompt_set(ps):
    return db.decode_prompts(ps) if isinstance(ps['prompts'],str) else ps


def product_context(ps, product_id=None):
    ps=prompt_set(ps)
    catalog=ps['catalog_snapshot']
    domain=ps['store_domain'] or (catalog[0]['store_domain'] if catalog else '')
    if product_id is not None:
        p=next((dict(p) for p in catalog if p['id']==int(product_id)),None)
        if p is None:
            return None
    else:
        brand=db.brand(domain) or {}
        p=dict(id=None,title='Catalog overview',vendor=brand.get('brand_name') or domain,
               store_domain=domain,image='',url='',raw_json='{}')
    p['_ps']=ps
    p['_catalog']=catalog
    # Every engine, until a caller narrows it (the dashboard does, from the
    # address; scoring deliberately does not, so stored scores stay whole).
    p['_engines']=None
    return p


def with_engines(p,selected):
    """The same context, showing only these engines. None means all of them."""
    out=dict(p)
    out['_engines']=None if selected is None else list(selected)
    return out


def relevant_questions(p):
    ps=p['_ps']
    if p['id'] is None:
        return ps['prompts']
    return [q for q,ids in zip(ps['prompts'],ps['relevance']) if p['id'] in ids]


def state(p):
    if p['id'] is None:
        return 'Measured'
    if p['id'] not in p['_ps']['product_ids']:
        return 'Excluded'
    return 'Measured' if relevant_questions(p) else 'Not covered'


def own(m,p):
    if p['id'] is None:
        return m['matched_product_id'] in p['_ps']['product_ids']
    return m['matched_product_id']==p['id']


@lru_cache(maxsize=32)
def _raw(path, ids, revision):
    marks=','.join('?'*len(ids))
    answers=tuple(dict(a) for a in db.all_('SELECT a.*,ap.status AS processing_status FROM answers a LEFT JOIN answer_processing ap ON ap.answer_id=a.id WHERE a.scan_id IN (%s) ORDER BY a.id'%marks,ids))
    # Generic advice ("a gentle, fragrance-free cleanser") carries no brand and
    # no link. It is not a buyable product, so it is not a competitor and must
    # not sit in the share-of-voice denominator.
    identifiable="AND (COALESCE(TRIM(m.brand),'')<>'' OR COALESCE(TRIM(m.url),'')<>'' OR m.matched_product_id IS NOT NULL)"
    mentions=tuple(dict(m) for m in db.all_('SELECT m.* FROM mentions m JOIN answers a ON a.id=m.answer_id WHERE a.scan_id IN (%s) '%marks+identifiable+' ORDER BY a.id,m.rank',ids))
    return answers,mentions


def _mtime():
    try:
        return os.path.getmtime(config.DB_PATH)
    except OSError:
        return 0


def clear_cache():
    _raw.cache_clear()


def load(scan_ids,p,include_unprocessed=False):
    ids=(scan_ids,) if isinstance(scan_ids,int) else tuple(scan_ids)
    if not ids:
        return [],[]
    # The file's own timestamp is part of the key so a rewrite from another
    # process (replay.py) is picked up without restarting the app.
    rows,mentions=_raw(str(config.DB_PATH),ids,(db._revision,_mtime()))
    questions=set(relevant_questions(p))
    # Answers stored before engines existed carry no engine; they were all
    # ChatGPT, and the migration backfills them, but an empty value here must
    # still read as ChatGPT rather than vanishing from every panel.
    picked=p.get('_engines')
    picked=None if picked is None else set(picked)
    answers=[a for a in rows if a['prompt'] in questions
             and (include_unprocessed or a['processing_status']=='done')
             and (picked is None or (a['engine'] or config.DEFAULT_ENGINE) in picked)]
    # One answer per question per run PER ENGINE. A crash between buying a
    # scraped batch and storing it can leave the same answer written twice
    # (scan 6, 20 Sep 2026), and showing or counting it twice is wrong either
    # way. The extracted copy wins; the rows themselves are never deleted.
    # The engine belongs in this key: three engines answering the same
    # question on the same run are three real answers, not three duplicates,
    # and leaving it out would silently discard two thirds of every scan.
    def dedupe_key(a):
        return (a['scan_id'],a['prompt'],a['run_n'],a['engine'] or config.DEFAULT_ENGINE)
    best={}
    for a in answers:
        key=dedupe_key(a)
        kept=best.get(key)
        if kept is None or (kept['processing_status']!='done' and a['processing_status']=='done'):
            best[key]=a
    answers=[a for a in answers if best[dedupe_key(a)] is a]
    aid={a['id'] for a in answers}
    return answers,[m for m in mentions if m['answer_id'] in aid]
