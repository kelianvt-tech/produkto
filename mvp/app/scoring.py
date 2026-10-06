"""Turn one scan's stored answers into the dashboard numbers.

Visibility score: for every answer, credit = 1 / log2(rank + 1) for the
best position their product was named at (1st = 1.00, 2nd = 0.63,
3rd = 0.50, 4th = 0.43, 5th = 0.39 ...), 0 if not named. Score is the
average credit x 100.

Share of voice: their product's mentions / every product mention.
Competitor products are grouped loosely (same brand, mostly the same name
words) because ChatGPT rarely writes a product name the same way twice.

Positioning: per brand, how often it is named and its average position.
"""

import json
import math
from collections import defaultdict

import db
from text import norm, words

TOP_PRODUCTS = 6
TOP_BRANDS = 8


def credit(rank):
    return 1.0 / math.log2(rank + 1)


def _cluster(mentions):
    """Group mentions that are probably the same product."""
    clusters = []   # each: {brand, name, words, count, answers}
    for m in mentions:
        if m["is_theirs"]:
            continue
        b = norm(m["brand"])
        w = set(words(m["product_name"]))
        home = None
        for c in clusters:
            if c["bkey"] != b:
                continue
            if not w and not c["words"]:
                home = c
                break
            if w and c["words"]:
                j = len(w & c["words"]) / len(w | c["words"])
                if j >= 0.5:
                    home = c
                    break
        if home is None:
            home = {"bkey": b, "brand": m["brand"], "name": m["product_name"],
                    "words": w, "count": 0, "own": bool(m["is_their_brand"])}
            clusters.append(home)
        home["count"] += 1
    return clusters


def score(scan_id):
    import evidence
    import insight_panels
    evidence.clear_cache()
    scan=db.one('SELECT * FROM scans WHERE id=?',(scan_id,))
    ps=db.one('SELECT * FROM prompt_sets WHERE id=?',(scan['prompt_set_id'],))
    catalog=evidence.product_context(ps)
    contexts=[catalog]+[evidence.product_context(ps,p['id']) for p in catalog['_catalog']]
    # Read each scan once; product metrics use the same recorded evidence.
    for p in contexts:
        rows=insight_panels.products(scan_id,p)
        own=next(r for r in rows if r['own'])
        answers,mentions=evidence.load(scan_id,p)
        n=len(answers)
        per_q=[dict(question=q,rate=own['questions'][q],avg_rank=own['q_rank'].get(q)) for q in own['questions']]
        detail=dict(answers=n,questions=per_q,noise_points=round(300/n) if n else None,
                    coverage=evidence.state(p),borderline=sum(1 for m in mentions if m['is_their_brand'] and not m['is_theirs'] and m['match_score']>=.3))
        values=(own['weighted'],own['rate'],own['avg'],own['share']) if n else (None,None,None,None)
        if p['id'] is not None:
            db.write('INSERT OR REPLACE INTO product_scores VALUES (?,?,?,?,?,?,?)',(scan_id,p['id'])+values+(json.dumps(detail),))
            continue
        competitors=sorted([r for r in rows if not r['own']],key=lambda r:-r['share'])[:TOP_PRODUCTS]
        detail['sov_rows']=[dict(label=r['name'],brand=r['brand'],pct=r['share'],own_brand=False) for r in competitors]
        detail['other_pct']=max(0,100-own['share']-sum(r['share'] for r in competitors)) if mentions else 0
        by_brand=defaultdict(dict)
        brand_names={}
        brand_mentions=defaultdict(int)
        for m in mentions:
            if not m['is_their_brand'] and norm(m['brand']):
                key=norm(m['brand']);brand_names[key]=m['brand']
                brand_mentions[key]+=1
                by_brand[key][m['answer_id']]=min(by_brand[key].get(m['answer_id'],999),m['rank'])
        # share: this brand's mentions over every recommendation in the scan,
        # so it is comparable with the merchant's own share of voice.
        total_mentions=len(mentions)
        detail['brands']=sorted([dict(brand=brand_names[b],rate=100*len(hits)/n,
                                      avg_rank=sum(hits.values())/len(hits),
                                      share=100*brand_mentions[b]/total_mentions if total_mentions else None)
                                 for b,hits in by_brand.items()],key=lambda r:-r['rate'])[:TOP_BRANDS] if n else []
        brand_rate=100*len({m['answer_id'] for m in mentions if m['is_their_brand']})/n if n else None
        db.write('INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)',(scan_id,)+values+(brand_rate,json.dumps(detail)))
