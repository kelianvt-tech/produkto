"""Step 1 of the per-brand ChatGPT line: each brand's best-seller -> one buyer question.
Free (store pages only). Writes coffee-questions-2026-10-15.json for review before Apify."""
import csv, html, json, re, subprocess, time
SKIP = re.compile(r"gift ?card|sample|bundle|kit|set of|e-?gift|subscription|membership|donation|shipping|protection|insurance|deposit|refill|variety|sampler|trial", re.I)

def get(url):
    return subprocess.run(["curl", "-sL", "--max-time", "20", "-A", "Mozilla/5.0", url], capture_output=True).stdout.decode("utf-8", "ignore")

def best_seller(d):
    page = get("https://%s/collections/all?sort_by=best-selling" % d)
    handles = list(dict.fromkeys(re.findall(r'/products/([a-z0-9][a-z0-9\-]+)', page)))
    if not handles:
        try: handles = [p["handle"] for p in json.loads(get("https://%s/products.json?limit=30" % d))["products"]]
        except Exception: return None
    for h in handles[:12]:
        time.sleep(0.3)
        try: p = json.loads(get("https://%s/products/%s.js" % (d, h)))
        except Exception: continue
        title, typ, price = html.unescape(p.get("title", "")), (p.get("type") or "").strip(), (p.get("price") or 0) / 100
        if price < 5 or SKIP.search(title) or SKIP.search(typ): continue
        return dict(title=title, type=typ, price=price, url="https://%s/products/%s" % (d, h))
    return None

brands = {}
for f in ("2026-10-13-coffee-main.csv",):
    for r in csv.DictReader(open(f)):
        d = re.sub(r"^https?://(www\.)?", "", r["website"] or r["email"].split("@")[1]).strip("/").lower()
        brands.setdefault(d, r["company_name"])
out = {}
for i, (d, name) in enumerate(brands.items(), 1):
    out[d] = dict(company=name, product=best_seller(d))
    if i % 25 == 0: print("done", i, "of", len(brands), flush=True)
json.dump(out, open("coffee-questions-2026-10-15.json", "w"), indent=1)
print("found", sum(1 for v in out.values() if v["product"]), "of", len(out))
