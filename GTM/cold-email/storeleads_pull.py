"""Pull Store Leads pages for a niche via the Apify API and save each page as JSON.

Usage: python3 storeleads_pull.py <out_dir> <category> <first_page> <last_page>
Reads the Apify token from mvp/app/.env (never printed).
"""
import json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV = ROOT / "mvp/app/.env"
TOKEN = next(l.split("=", 1)[1].strip().strip("'\"") for l in ENV.read_text().splitlines()
             if l.startswith(("APIFY_TOKEN=", "APIFY_API_TOKEN=")))
ACTOR = "ecommerce_leads~store-leads-14m-e-commerce-leads"


def call(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req, timeout=120))


def main():
    out, cat, a, b = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    # Refuse to spend if another pull for this niche exists (2026-10-12: two sessions
    # pulled the same 24 coffee pages in parallel and paid twice).
    def others():
        here = out.resolve()
        return [d.name for d in out.parent.glob(f"storeleads-*{cat}*") if d.is_dir() and d.resolve() != here]
    if others():
        sys.exit(f"STOP: existing pull for '{cat}': {others()}. Ask Kelian before spending.")
    out.mkdir(parents=True, exist_ok=True)
    for page in range(a, b + 1):
        if others():  # re-check before every paid page: a parallel session may have started
            sys.exit(f"STOP before page {page}: another pull for '{cat}' appeared: {others()}")
        dest = out / f"{cat}-p{page:02d}.json"
        if dest.exists():
            continue
        run = call(f"https://api.apify.com/v2/acts/{ACTOR}/runs?maxTotalChargeUsd=0.6",
                   {"platform": "shopify", "country": "US", "category": cat, "page": page})["data"]
        while run["status"] in ("READY", "RUNNING"):
            time.sleep(5)
            run = call(f"https://api.apify.com/v2/actor-runs/{run['id']}")["data"]
        items = call(f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?clean=1")
        dest.write_text(json.dumps(items))
        print(cat, page, run["status"], len(items), "cost", run.get("usageTotalUsd"), flush=True)
        if len(items) < 100:
            print(cat, "ran out of results at page", page)
            break


if __name__ == "__main__":
    main()
