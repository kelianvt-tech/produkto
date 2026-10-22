"""Coffee & tea batch, step 4 (free): clean the Export Apollo file into wave files.

Usage: python3 coffee_clean.py
Reads  2026-10-13-coffee-tea-apollo-raw.csv  (Export Apollo xlsx -> csv via xlsx2csv.py)
       2026-10-13-coffee-tea-sites.csv       (coffee_site_check.py)
Writes 2026-10-13-coffee-apollo-good.csv / -catch_all.csv  (kept contacts, `wave` column)
       2026-10-13-coffee-apollo-setaside.csv               (every contact not kept, with the reason)
and prints how many each filter dropped. Nothing is deleted: set-aside rows stay on file.
"""
import collections, csv, re
from urllib.parse import urlparse

RAW, SITES = "2026-10-13-coffee-tea-apollo-raw.csv", "2026-10-13-coffee-tea-sites.csv"

# Sites that don't sell coffee or tea to consumers (checked by eye from coffee_site_check output, 2026-10-13)
NOT_NICHE = {
    "francesvalentine.com": "fashion", "metier.cc": "bike shop", "metaflexglove.com": "recovery glove",
    "happydad.com": "hard seltzer", "beautyonwheels.ae": "beauty retailer", "herb-pharm.com": "herbal supplements",
    "crestone-group.com": "wholesale bakery", "elidabeauty.com": "beauty", "shopfloorbrands.com": "no site content",
    "coldcyclecoffee.com": "commercial cold-brew machine (B2B)", "voluspa.com": "candles",
}
WHOLESALE = {  # green-coffee importers and wholesale/private-label only: B2B, not a consumer shop
    "royalcoffee.com", "copantrade.com", "passportcoffee.com", "colonialcoffee.com", "roomservicecoffee.com",
}
PROSPECTED = {"artoftea.com", "coppercowcoffee.com", "vervecoffee.com"}  # August prospecting lists, may be emailed
# brand's own second domain, checked by eye 2026-10-13 (the token rule in same_brand() misses these)
SAME_BRAND = {"unchartedcoffee.com", "cbrccoffee.com", "thewoodscoffee.com", "tradecoffeeco.com", "justicetea.com",
              "by.coffee", "toccoacoffee.com", "californiacoffee.com"}
GENERIC = {"coffee", "roasters", "roaster", "roasting", "company", "brands", "shop", "teas", "house", "drink", "direct"}
CAFE = re.compile(r"caf[eé]s?\b|coffee shop|coffee bar|locations|tearoom|restaurant|bakery|brunch|cocktail", re.I)


def domain(w):
    w = (w or "").strip()
    return re.sub(r"^www\.", "", urlparse(w if "://" in w else "http://" + w).netloc.lower())


def tokens(s):
    return {t for t in re.split(r"[^a-z]+", s.lower()) if len(t) >= 4 and t not in GENERIC}


def same_brand(r, d):
    """Email is the brand's own address: same domain, its own second domain, or a founder's personal webmail."""
    ed = r["Email"].lower().split("@")[1]
    if ed == d or ed.endswith("." + d) or ed in SAME_BRAND or r["free"] == "yes":
        return True
    a, b = ed.split(".")[0], d.split(".")[0]
    return a[:6] == b[:6] or bool(tokens(a) & (tokens(b) | tokens(r["Company Name"])))


def score(title):
    t = title.lower()
    if re.search(r"\b(founder|co-founder|cofounder|owner|ceo|chief executive|president)\b", t) and "vice" not in t:
        return 1
    if re.search(r"(marketing|e-?commerce|growth|digital|dtc|brand|cmo)", t) and re.search(r"(chief|vp|vice|head|director|cmo)", t):
        return 2
    if re.search(r"\b(coo|chief operating|general manager)\b", t):
        return 3
    if re.search(r"(marketing|e-?commerce|brand|growth|digital)", t):
        return 4
    return 9  # finance, HR, sales, supply chain, roasting/café staff...


def main():
    sites = {r["domain"]: r for r in csv.DictReader(open(SITES))}
    raw = list(csv.DictReader(open(RAW)))
    keep, aside = [], []
    drops = collections.Counter()

    def put_aside(r, why):
        r["reason"] = why
        aside.append(r)
        drops[why.split(":")[0]] += 1

    seen = set()
    for r in raw:
        d = domain(r["Website"])
        s = sites.get(d, {})
        email = r["Email"].strip().lower()
        r.update(email=email, website=f"https://{d}", dom=d,
                 site_checked="yes" if s.get("home_status") == "200" else "no",
                 cafe="yes" if CAFE.search(f'{s.get("title","")} {s.get("description","")}') else "")
        if email in seen:
            put_aside(r, "duplicate email"); continue
        seen.add(email)
        if r["result"] not in ("ok", "catch_all", "unknown"):
            put_aside(r, "invalid email"); continue
        if d in NOT_NICHE:
            put_aside(r, f"not coffee/tea: {NOT_NICHE[d]}"); continue
        if d in WHOLESALE:
            put_aside(r, "wholesale/importer only"); continue
        if d in PROSPECTED:
            put_aside(r, "already in August prospecting lists"); continue
        if "wildone" in email:
            put_aside(r, "Wild One"); continue
        if not same_brand(r, d):
            put_aside(r, "email on another domain"); continue
        keep.append(r)

    # at most 3 per brand: founder/CEO/president -> marketing/e-commerce lead -> COO; one per brand per wave
    brands = collections.defaultdict(list)
    for r in keep:
        brands[r["dom"]].append(r)
    final = []
    for d, rs in brands.items():
        rs.sort(key=lambda r: (score(r["Title"]), r["result"] != "ok"))
        ok = [r for r in rs if score(r["Title"]) < 9]
        if not ok:  # no decision maker on file: one director/manager rather than nobody
            ok = [r for r in rs if re.search(r"director|manager", r["Title"], re.I)][:1]
        ok = ok[:3]
        for i, r in enumerate(ok):
            r["wave"] = i + 1
        final += ok
        for r in rs:
            if r not in ok:
                put_aside(r, "over 3 per brand / not a decision maker")

    cols = ["email", "First Name", "Last Name", "Company Name for Emails", "Title", "website", "City", "State",
            "Country", "result", "wave", "cafe", "site_checked"]
    names = ["email", "first_name", "last_name", "company_name", "title", "website", "city", "state",
             "country", "email_result", "wave", "cafe", "site_checked"]
    for kind, test in [("good", lambda r: r["result"] == "ok"), ("catch_all", lambda r: r["result"] != "ok")]:
        with open(f"2026-10-13-coffee-apollo-{kind}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(names)
            for r in sorted(filter(test, final), key=lambda r: (r["wave"], r["Company Name for Emails"].lower())):
                w.writerow([r[c] for c in cols])
    with open("2026-10-13-coffee-apollo-setaside.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(names[:10] + ["reason"])
        for r in aside:
            w.writerow([r[c] for c in cols[:10]] + [r["reason"]])

    print("raw contacts:", len(raw))
    for why, n in drops.most_common():
        print(f"  set aside - {why}: {n}")
    print("kept contacts:", len(final), "| brands:", len({r['dom'] for r in final}))
    print("  good:", sum(r["result"] == "ok" for r in final), "| catch-all/unknown:", sum(r["result"] != "ok" for r in final))
    print("  waves:", dict(sorted(collections.Counter(r["wave"] for r in final).items())))
    print("  café-led brands (kept, flagged):", len({r['dom'] for r in final if r['cafe']}))
    print("  brands whose site isn't checked yet:", len({r['dom'] for r in final if r['site_checked'] == 'no'}))


if __name__ == "__main__":
    main()
