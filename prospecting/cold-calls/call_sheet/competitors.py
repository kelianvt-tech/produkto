"""One ChatGPT question per lead (via Produkto's Apify scraper): which product
it recommends for that lead's product type and price. Writes competitors.json."""
import json, re, sys, csv, os
APP = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app"
sys.path.insert(0, APP); os.chdir(APP)
for line in open('.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip('"\''))
import apify_answers
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, 'products.json')))
rows = list(csv.DictReader(open(sys.argv[1])))
qs = {}
for r in rows:
    d = r['organization_primary_domain']; p = P.get(d)
    if not p or not p['title']:
        continue
    what = (p['type'] or p['title']).strip()
    q = ("What is the best %s to buy online for around $%d? Recommend one specific product. "
         "Reply ONLY with one line in this format: Brand | Exact product name" % (what, round(p['price'])))
    qs[d] = q.replace('\n', ' ')
print(len(qs), 'questions'); sys.stdout.flush()
res = apify_answers.ask_batch(sorted(set(qs.values())), engine='chatgpt', timeout=1500)
out = {}
for d, q in qs.items():
    text = (res.get(q) or ('',))[0]
    m = re.search(r'([^|\n*]{2,60}?)\s*\|\s*([^|\n]{3,120})', text.replace('*', ''))
    out[d] = dict(question=q, brand=m[1].strip() if m else '', product=m[2].strip(' .[]0-9') if m else '', raw=text[:300])
json.dump(out, open(os.path.join(HERE, 'competitors.json'), 'w'), indent=1)
print(sum(1 for v in out.values() if v['product']), 'with a competitor product')
