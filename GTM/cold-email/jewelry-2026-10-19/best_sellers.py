"""Step 2 (free): each kept brand's best-selling jewelry piece -> jewelry type + price, for its ChatGPT question."""
import csv, html, json, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor
SKIP = re.compile(r"gift ?card|sample|cleaning|kit|e-?gift|subscription|deposit|repair|consult|appointment|reserve|insurance|shipping|box\b|pouch|blank", re.I)
TYPES = [("engagement ring", r"engagement|solitaire"), ("wedding band", r"wedding band|eternity band|\bband\b"),
         ("tennis bracelet", r"tennis bracelet"), ("bracelet", r"bracelet|bangle|cuff"), ("hoop earrings", r"hoop|huggie"),
         ("stud earrings", r"stud"), ("earrings", r"earring|drop|ear\b"), ("necklace", r"necklace|pendant|chain|lariat|choker"),
         ("ring", r"\bring\b"), ("watch band", r"watch band|apple watch")]
def get(u):
    return subprocess.run(["curl", "-sL", "-m", "15", "-A", "Mozilla/5.0", u], capture_output=True).stdout.decode("utf-8", "ignore")
def kind(t):
    for name, pat in TYPES:
        if re.search(pat, t, re.I): return name
    return ""
def best(d):
    page = get("https://%s/collections/all?sort_by=best-selling" % d)
    hs = list(dict.fromkeys(re.findall(r'/products/([a-z0-9][a-z0-9\-]+)', page)))
    if not hs:
        try: hs = [p["handle"] for p in json.loads(get("https://%s/products.json?limit=30" % d))["products"]]
        except Exception: return d, None
    for h in hs[:15]:
        try: p = json.loads(get("https://%s/products/%s.js" % (d, h)))
        except Exception: continue
        t, price = html.unescape(p.get("title", "")), (p.get("price") or 0) / 100
        k = kind(t + " " + (p.get("type") or ""))
        if price < 10 or SKIP.search(t) or not k: continue
        return d, dict(title=t, type=k, price=price)
    return d, None
doms = sorted({r["domain"] for r in csv.DictReader(open("keep.csv"))})
with ThreadPoolExecutor(8) as ex: out = dict(ex.map(best, doms))
json.dump(out, open("best-sellers.json", "w"), indent=1)
for d, v in out.items(): print(d, "|", v and "%s | %s | $%d" % (v["type"], v["title"][:50], v["price"]))
