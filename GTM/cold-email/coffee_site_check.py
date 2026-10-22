"""Coffee & tea batch, step 2 (free): check every brand site in the Export Apollo file.

Usage: python3 coffee_site_check.py 2026-10-13-coffee-tea-apollo-raw.csv
Writes 2026-10-13-coffee-tea-sites.csv: one row per website with homepage title/description,
whether /products.json answers (Shopify shop), product count and sample product titles/types.
Decision is made later (coffee_clean.py) from what the site says, never from the company name.
"""
import csv, html, json, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def domain(w):
    w = w.strip()
    return re.sub(r"^www\.", "", urlparse(w if "://" in w else "http://" + w).netloc.lower())


def get(url, limit=400_000):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(limit).decode("utf-8", "ignore"), r.geturl()
    except Exception:
        p = subprocess.run(["curl", "-sL", "-m", "15", "-A", UA, "-w", "\n%{http_code} %{url_effective}", url],
                           capture_output=True, text=True, errors="ignore")
        body, _, tail = p.stdout.rpartition("\n")
        code, _, final = tail.partition(" ")
        return (int(code) if code.isdigit() else 0), body[:limit], final


def check(d):
    out = {"domain": d}
    code, page, final = get(f"https://{d}")
    out["home_status"], out["final_url"] = code, final
    t = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', page, re.S | re.I)
    clean = lambda x: html.unescape(re.sub(r"\s+", " ", x.group(1))).strip()[:200] if x else ""
    out["title"], out["description"] = clean(t), clean(m)
    out["password"] = "/password" in final or 'id="password' in page.lower()
    host = domain(final) or d
    code, body, _ = get(f"https://{host}/products.json?limit=250", 3_000_000)
    try:
        prods = json.loads(body).get("products", []) if code == 200 else None
    except Exception:
        prods = None
    out["shopify"] = prods is not None
    out["n_products"] = len(prods) if prods else 0
    out["product_types"] = "; ".join(sorted({p.get("product_type", "") for p in prods or [] if p.get("product_type")}))[:300]
    out["sample_products"] = " | ".join(p.get("title", "") for p in (prods or [])[:8])[:400]
    return out


def main():
    rows = list(csv.DictReader(open(sys.argv[1])))
    doms = sorted({domain(r["Website"]) for r in rows if r["Website"]})
    with ThreadPoolExecutor(32) as ex:
        res = list(ex.map(check, doms))
    with open("2026-10-13-coffee-tea-sites.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(res[0].keys()))
        w.writeheader()
        w.writerows(res)
    print("sites", len(res), "load", sum(r["home_status"] == 200 for r in res),
          "shopify", sum(r["shopify"] for r in res), "password", sum(r["password"] for r in res))


if __name__ == "__main__":
    main()


def retry_throttled(path="2026-10-13-coffee-tea-sites.csv", threads=3):
    """Re-check sites that answered 429 (Shopify throttles ~30 parallel fetches), slowly."""
    import time
    rows = list(csv.DictReader(open(path)))
    todo = [r for r in rows if r["shopify"] != "True" and r["home_status"] != "200"]
    def slow(r):
        time.sleep(1.5)
        return check(r["domain"])
    with ThreadPoolExecutor(threads) as ex:
        fixed = {r["domain"]: r for r in ex.map(slow, todo)}
    rows = [fixed.get(r["domain"], r) for r in rows]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("retried", len(todo), "now shopify", sum(str(r["shopify"]) == "True" for r in rows),
          "still not loading", sum(str(r["shopify"]) != "True" and str(r["home_status"]) != "200" for r in rows))
