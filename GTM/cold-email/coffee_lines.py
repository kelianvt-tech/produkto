"""Step 3: pick one competitor product per coffee/tea answer and write the email line.
Reads coffee-answers-2026-10-15.json + 2026-10-13-coffee-main.csv. Writes coffee-lines-2026-10-15.json."""
import csv, json, re

A = json.load(open("coffee-answers-2026-10-15.json"))
NAMES = {}
for r in csv.DictReader(open("2026-10-13-coffee-main.csv")):
    d = re.sub(r"^https?://(www\.)?", "", r["website"] or r["email"].split("@")[1]).strip("/").lower()
    NAMES.setdefault(d, r["company_name"])

FIX = {"COBA COFFEE": "COBA Coffee", "COMMUNAL COFFEE": "Communal Coffee", "DRINK COFFEE DO STUFF": "Drink Coffee Do Stuff",
 "Dobra Tea (Pittsburgh, PA)": "Dobra Tea", "Javita International (dba Dollar Coffee Club)": "Dollar Coffee Club",
 "NATURE'S TEA COMPANY": "Nature's Tea Company", "PERC COFFEE": "PERC Coffee", "ROOSROAST COFFEE": "Roosroast Coffee",
 "SENS - SPECIALTY COFFEE & ROBO CAFÉ": "SENS Coffee", "SEXTANT COFFEE ROASTERS": "Sextant Coffee Roasters",
 "SHADRACHS COFFEE": "Shadrachs Coffee", "STEREOSCOPE COFFEE": "Stereoscope Coffee", "Throne SPORT COFFEE": "Throne Sport Coffee",
 "URBAN SAILOR COFFEE": "Urban Sailor Coffee", "UTOPIAN Coffee Co": "Utopian Coffee",
 "UEndure Tea Co. - Premium Organic Loose Leaf Tea Blends, and BPA-Free Sustainable Accessories": "UEndure Tea"}
def short(c):
    c = FIX.get(c.strip(), c)
    c = c.replace("®", "").replace("™", "").replace("​", "").strip()
    c = re.sub(r",?\s+(inc\.?|llc\.?|ltd\.?|pbc\.?|, inc\.?)$", "", c, flags=re.I)
    return c.strip(" ,.")

def words(s):
    return {w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) > 2 and w not in
            {"coffee", "tea", "the", "and", "company", "roasters", "roasting", "roastery", "co", "brewing", "beans", "cafe"}}

def picks(ans):
    ans = re.sub(r"[*`]", "", ans)
    out = []
    for m in re.finditer(r"\d\)\s*([^:;]+?):\s*([^;]+)", ans):
        b, p = m.group(1).strip(" .-"), m.group(2).strip(" .")
        b = re.sub(r"^\d+\.\s*", "", b)
        out.append((b, p))
    return out

def tidy(p, b):
    p = re.sub(r"\s*\(.*?\)", "", p)
    p = re.sub(r",?\s*\d+(\.\d+)?\s*(oz|ounce|lb|lbs|pound|ct|count|pack|g|kg)\b.*$", "", p, flags=re.I).strip(" ,.-–—")
    if p.lower().startswith(b.lower()): p = p[len(b):].strip(" :-–—")
    return re.sub(r"^the\s+", "", p, flags=re.I)

out = {}
for dom, v in A.items():
    co = short(NAMES.get(dom, dom))
    own = words(co) | words(dom.split(".")[0])
    q = v["question"]
    rec = dict(company=co, question=q, flag="no answer", raw=v["answer"][:300])
    ps = picks(v["answer"]) if v["answer"] else []
    own_named = any(words(b) & own for b, _ in ps)
    for b, p in ps:
        if words(b) & own: continue                      # the prospect itself
        if words(b) & words(q): continue                 # brand word in the question (Sophie's rule)
        p = tidy(p, b)
        if not p or len(p) > 70: continue
        rec.update(flag="ok", competitor_brand=b, competitor_product=p, own_named=own_named,
                   line='I asked ChatGPT "%s" today. One of its picks was the %s by %s, a competitor of %s.' % (q, p, b, co))
        break
    else:
        if ps: rec["flag"] = "no usable pick"
    out[dom] = rec
json.dump(out, open("coffee-lines-2026-10-15.json", "w"), indent=1)
ok = [r for r in out.values() if r["flag"] == "ok"]
print("ok", len(ok), "of", len(out), "| own brand named by ChatGPT:", sum(r.get("own_named", False) for r in ok))
