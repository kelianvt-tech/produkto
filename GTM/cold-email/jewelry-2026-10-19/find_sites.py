"""Jewelry call batch, step 1 (free): the lead file has no websites, so guess each brand's
domain from its company name and LinkedIn headline, then check the live site.

Usage: python3 -I find_sites.py raw.csv
Writes sites.csv: every lead with the domain found (if any), homepage title/description,
whether it's a Shopify shop (products.json) and sample product titles/prices.
A guess only counts if the homepage title/description shares a word with the brand name.
"""
import csv, html, json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
STOP = {"llc", "inc", "the", "and", "co", "company", "official", "page", "ltd", "group", "of", "by", "at"}


def get(url, limit=300_000):
    p = subprocess.run(["curl", "-sL", "-m", "12", "-A", UA, "-w", "\n%{http_code} %{url_effective}", url],
                       capture_output=True, text=True, errors="ignore")
    body, _, tail = p.stdout.rpartition("\n")
    code, _, final = tail.partition(" ")
    return (int(code) if code.isdigit() else 0), body[:limit], final


def names(row):
    out = []
    c = row["current_company"].strip()
    if c and c.lower() not in ("self-employed",):
        out.append(c)
    h = re.sub(r"\.\.\.|…", "", row["linkedin_headline"])
    for pat in (r"(?:at|of|@|Founder|Owner|Director|Designer|CEO)[,:]?\s+([A-Z][\w&'.\- ]{2,40})", r",\s*([A-Z][\w&'.\- ]{2,40})$", r"-\s*([A-Z][\w&'.\- ]{2,40})$"):
        for m in re.findall(pat, h):
            m = re.split(r"\s[|•▏]|,", m)[0].strip()
            if m and m not in out and not re.match(r"(Founder|Owner|CEO|Co|Creative|Jewelry Designer|Designer)\b", m):
                out.append(m)
    out.append(row["name"])  # designer-name brands (Sara Weinstock, Jean Dousset)
    return out


def slugs(n):
    n = re.sub(r"\[.*?\]|™|®|\(.*?\)", "", n)
    w = [x for x in re.findall(r"[a-z0-9]+", n.lower().replace("&", " and ").replace("'", "")) if x not in STOP]
    if not w:
        return []
    base = "".join(w)
    core = "".join(x for x in w if x not in ("jewelry", "jewelers", "jewels", "fine", "designs", "design", "diamonds"))
    s = [base, base + "jewelry"]
    if core and core != base:
        s += [core, core + "jewelry"]
    return list(dict.fromkeys(s))


def tokens(n):
    return {x for x in re.findall(r"[a-z0-9]{3,}", n.lower()) if x not in STOP | {"jewelry", "fine", "designs", "design", "founder", "owner"}}


def check(row):
    tried = []
    for n in names(row):
        for s in slugs(n):
            d = s + ".com"
            if d in tried:
                continue
            tried.append(d)
            code, page, final = get("https://" + d)
            if code != 200 or len(page) < 500:
                continue
            t = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', page, re.S | re.I)
            clean = lambda x: html.unescape(re.sub(r"\s+", " ", x.group(1))).strip()[:200] if x else ""
            title, desc = clean(t), clean(m)
            text = (title + " " + desc + " " + final).lower()
            if not (tokens(n) & tokens(text)) or re.search(r"domain (is )?for sale|buy this domain|parked", page[:20000], re.I):
                continue
            host = re.sub(r"^https?://(www\.)?", "", final).split("/")[0]
            prods = []
            c2, pj, _ = get("https://%s/products.json?limit=30" % host)
            try:
                prods = json.loads(pj)["products"]
            except Exception:
                pass
            sample = "; ".join("%s ($%s)" % (p["title"], (p.get("variants") or [{}])[0].get("price", "")) for p in prods[:6])
            return dict(row, domain=host, matched_name=n, title=title, description=desc,
                        shopify="yes" if prods else "no", products=len(prods), sample=sample,
                        has_cart="yes" if re.search(r"add to (cart|bag)|/cart\b|shop now", page, re.I) else "no")
    return dict(row, domain="", matched_name="", title="", description="", shopify="", products="", sample="", has_cart="")


rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
with ThreadPoolExecutor(12) as ex:
    out = list(ex.map(check, rows))
w = csv.DictWriter(open("sites.csv", "w", newline=""), fieldnames=list(out[0].keys()))
w.writeheader(); w.writerows(out)
print("found site for", sum(1 for r in out if r["domain"]), "of", len(out),
      "| shopify", sum(1 for r in out if r["shopify"] == "yes"))
