"""Keep only domains that are real Shopify stores selling their own products.

Checks each domain's public /products.json (free, no API). Pet sitters,
groomers, agencies and apps don't have one, so they drop out before we pay
for any leads.

Usage: python3 find_stores.py domains.txt stores.csv [--exclude leads_dir]
domains.txt: one domain or URL per line (duplicates fine).
--exclude: skip domains already present in any CSV in that folder.
Writes stores.csv (domain, products, sample_title) and a plain
stores.txt list ready to paste into the leads finder's company_domains.
"""

import csv
import glob
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

# Marketplaces and big retailers that show up in search but aren't targets.
SKIP = {"amazon.com", "chewy.com", "petco.com", "petsmart.com", "walmart.com",
        "target.com", "etsy.com", "ebay.com", "reddit.com", "youtube.com",
        "facebook.com", "instagram.com", "pinterest.com", "tiktok.com",
        "shopify.com", "google.com", "akc.org", "wikipedia.org"}


def clean(line):
    line = line.strip()
    if not line:
        return ""
    host = urlparse(line if "//" in line else "https://" + line).netloc.lower()
    return host.removeprefix("www.")


def check(domain):
    try:
        req = urllib.request.Request(
            f"https://{domain}/products.json?limit=250",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            products = json.load(r).get("products", [])
        if products:
            return domain, len(products), products[0].get("title", "")
    except Exception:
        pass
    return None


def known_domains(folder):
    seen = set()
    for f in glob.glob(f"{folder}/*.csv"):
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                d = clean(row.get("organization_primary_domain") or "")
                if d:
                    seen.add(d)
    return seen


def main(src, out, exclude=None):
    domains = {clean(l) for l in Path(src).read_text().splitlines()}
    domains = {d for d in domains if d and not any(d == s or d.endswith("." + s) for s in SKIP)}
    if exclude:
        domains -= known_domains(exclude)
    with ThreadPoolExecutor(16) as pool:
        hits = sorted(r for r in pool.map(check, sorted(domains)) if r)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["domain", "products", "sample_title"])
        w.writerows(hits)
    Path(out).with_suffix(".txt").write_text("\n".join(h[0] for h in hits) + "\n")
    print(f"{len(domains)} checked, {len(hits)} are Shopify stores -> {out}")


if __name__ == "__main__":
    args = sys.argv[1:]
    ex = None
    if "--exclude" in args:
        i = args.index("--exclude")
        ex = args[i + 1]
        del args[i:i + 2]
    main(*args, exclude=ex)
