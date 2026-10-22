"""Collect email addresses each brand publishes on its own site (free: plain page fetches).

Usage: python3 find_site_emails.py <store_dir>
Reads apollo-domains.txt, opens homepage + contact/about pages, keeps addresses on the
brand's own domain. Also merges the store-list email column. Writes site-emails.csv
(domain, email, kind = named/generic, where_found). Placeholders are screened out.
"""
import csv, glob, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
PATHS = ["", "/pages/contact", "/pages/contact-us", "/pages/about", "/pages/about-us", "/pages/our-story", "/pages/wholesale"]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GENERIC = {"info", "hello", "support", "contact", "sales", "admin", "orders", "store", "shop", "hi", "help", "team",
           "customerservice", "service", "care", "wholesale", "office", "mail", "inquiries", "general", "returns"}
JUNK = ("example.", "sentry", "wixpress", "your@", "name@", "email@", "johndoe", "test@", "@2x", ".png", ".jpg", "shopify.com")


def page(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
            return r.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return ""


def scan(domain):
    found = {}
    root = domain.split(".", domain.count(".") - 1)[-1] if domain.count(".") > 1 else domain
    for p in PATHS:
        for e in set(EMAIL.findall(page(f"https://{domain}{p}"))):
            e = e.lower().strip(".")
            if any(j in e for j in JUNK) or not e.endswith(root):
                continue
            found.setdefault(e, f"https://{domain}{p}")
    return domain, found


def main():
    d = sys.argv[1]
    domains = [l.strip() for l in open(f"{d}/apollo-domains.txt") if l.strip()]
    store = {}
    for f in glob.glob(f"{d}/page-*.csv"):
        for r in csv.DictReader(open(f)):
            store[r["domain"].lower().removeprefix("www.")] = [e.strip().lower() for e in r.get("emails", "").split(",") if "@" in e]
    with ThreadPoolExecutor(24) as ex:
        results = dict(ex.map(scan, domains))
    rows = []
    for dom in domains:
        emails = dict(results.get(dom, {}))
        for e in store.get(dom, []):
            if not any(j in e for j in JUNK):
                emails.setdefault(e, "store list")
        for e, where in emails.items():
            kind = "generic" if e.split("@")[0] in GENERIC else "named"
            rows.append({"domain": dom, "email": e, "kind": kind, "where_found": where})
    with open(f"{d}/site-emails.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["domain", "email", "kind", "where_found"])
        w.writeheader(); w.writerows(rows)
    brands = {r["domain"] for r in rows}
    named = {r["domain"] for r in rows if r["kind"] == "named"}
    print(f"{len(rows)} emails across {len(brands)} of {len(domains)} brands; {len(named)} brands have a named (non-generic) address")


if __name__ == "__main__":
    main()
