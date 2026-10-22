"""Step 1 of a cold-email batch: pull the store list from Apify Store Leads 14M.

Usage: python3 store_list.py <category> <out_dir> <first_page> <last_page>
e.g.   python3 store_list.py coffee storeleads-coffee-2026-10-12 1 24

One actor run per page (100 stores, ~$0.56). US Shopify stores only.
Writes one CSV per page into out_dir. Token is read from mvp/app/.env.
"""
import csv, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

ACTOR = "ecommerce_leads~store-leads-14m-e-commerce-leads"
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, "..", "..", "mvp", "app", ".env")


def token():
    for line in open(ENV):
        if line.startswith("APIFY_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("APIFY_TOKEN not found")


def run_page(category, page, tok, out_dir):
    url = (f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
           f"?token={tok}&timeout=300")
    body = json.dumps({"platform": "shopify", "page": page,
                       "country": "US", "category": category}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    rows = json.load(urllib.request.urlopen(req, timeout=320))
    path = os.path.join(out_dir, f"page-{page:02d}.csv")
    if rows:
        fields = sorted({k for r in rows for k in r})
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return page, len(rows)


def main():
    category, out_dir, first, last = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    out_dir = os.path.join(HERE, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    tok = token()
    with ThreadPoolExecutor(4) as ex:
        for page, n in ex.map(lambda p: run_page(category, p, tok, out_dir), range(first, last + 1)):
            print(f"page {page}: {n} stores", flush=True)


if __name__ == "__main__":
    main()
