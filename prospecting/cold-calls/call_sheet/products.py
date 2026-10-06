import csv, json, re, sys, urllib.request, concurrent.futures as cf
SRC = sys.argv[1]
SKIP = re.compile(r'gift ?card|sample|bundle|kit|set of|e-?gift|subscription|membership|donation|shipping|protection|insurance|test|deposit|consultation|session|class|appointment|ticket', re.I)
def get(dom):
    try:
        import subprocess, time
        for attempt in range(3):
            raw = subprocess.run(['curl','-sL','--max-time','20','-A','Mozilla/5.0','https://%s/products.json?limit=250' % dom],capture_output=True).stdout
            try:
                data = json.loads(raw)['products']; break
            except Exception:
                time.sleep(3)
        else:
            return dom, None
    except Exception as e:
        return dom, None
    best = None
    for p in data:
        prices = [float(v.get('price') or 0) for v in p.get('variants', [])]
        price = max(prices or [0])
        if price < 5 or SKIP.search(p['title']) or SKIP.search(p.get('product_type') or ''):
            continue
        best = dict(title=p['title'], type=p.get('product_type') or '', price=price, handle=p['handle'], n=len(data))
        break   # products.json lists newest-edited first; first real product is a fair guess, flagged for checking
    return dom, best or {'title': '', 'type': '', 'price': 0, 'handle': '', 'n': len(data)}
rows = list(csv.DictReader(open(SRC)))
doms = sorted({r['organization_primary_domain'] for r in rows})
out = {}
with cf.ThreadPoolExecutor(4) as ex:
    for d, r in ex.map(get, doms):
        out[d] = r
json.dump(out, open('products.json', 'w'), indent=1)
ok = sum(1 for v in out.values() if v and v['title'])
print(len(doms), 'domains;', ok, 'with a product;', sum(1 for v in out.values() if v is None), 'not Shopify/blocked')
