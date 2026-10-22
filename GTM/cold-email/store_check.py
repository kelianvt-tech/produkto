"""Step 1b of a cold-email batch: open every store's homepage (free) and sort it.

Usage: python3 store_check.py <store_dir> <niche_words> <drop_words>
e.g.   python3 store_check.py storeleads-coffee-2026-10-12 "coffee,tea,matcha,espresso,roast" "wholesale,cafe menu,merch,band"

Reads every page-*.csv in store_dir, fetches each homepage's <title> and
meta description, and writes three files into store_dir:
  brands.csv          site loads and its title/description names the niche
  check-by-hand.csv   site loads but the niche words aren't on it, or a drop word is
  dropped.csv         site doesn't load, password page, or duplicate
plus apollo-domains.txt (brand domains, one per line).
Never judges by company name alone: the decision uses the live homepage.
"""
import csv, glob, html, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def fetch(domain):
    try:
        req = urllib.request.Request(f"https://{domain}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            page = r.read(300_000).decode("utf-8", "ignore")
            final = r.geturl()
    except Exception as e:
        # urllib trips on some TLS setups that browsers accept; retry with curl
        p = subprocess.run(["curl", "-sL", "-m", "15", "-A", UA["User-Agent"], "-w", "\n%{http_code} %{url_effective}",
                            f"https://{domain}"], capture_output=True, text=True, errors="ignore")
        body, _, tail = p.stdout.rpartition("\n")
        code, _, final = tail.partition(" ")
        if p.returncode != 0 or not code.startswith("2"):
            return {"status": f"error: {type(e).__name__}"}
        page = body[:300_000]
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', page, re.S | re.I)
    clean = lambda m: html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return {"status": "ok", "final_url": final, "title": clean(title), "description": clean(desc),
            "password": "/password" in final or 'id="password' in page.lower()}


def main():
    store_dir, niche, drop = sys.argv[1], sys.argv[2].lower().split(","), sys.argv[3].lower().split(",")
    rows, seen = [], set()
    for f in sorted(glob.glob(os.path.join(store_dir, "page-*.csv"))):
        for r in csv.DictReader(open(f)):
            d = r["domain"].lower().removeprefix("www.")
            if d in seen:
                continue
            seen.add(d)
            r["domain"] = d
            rows.append(r)
    with ThreadPoolExecutor(32) as ex:
        results = list(ex.map(lambda r: fetch(r["domain"]), rows))

    out = {"brands": [], "check-by-hand": [], "dropped": []}
    for r, res in zip(rows, results):
        row = {"domain": r["domain"], "merchant": r.get("merchant", ""), "categories": r.get("categories", ""),
               "emails": r.get("emails", ""), **{k: res.get(k, "") for k in ("status", "final_url", "title", "description")}}
        text = f'{row["title"]} {row["description"]}'.lower()
        if res["status"] != "ok" or res.get("password"):
            row["reason"] = "password page" if res.get("password") else res["status"]
            out["dropped"].append(row)
        elif any(w and w in text for w in drop):
            row["reason"] = "drop word on homepage"
            out["check-by-hand"].append(row)
        elif any(w and w in text for w in niche):
            row["reason"] = "niche word on homepage"
            out["brands"].append(row)
        else:
            row["reason"] = "no niche word on homepage"
            out["check-by-hand"].append(row)

    for name, items in out.items():
        with open(os.path.join(store_dir, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(items[0].keys()) if items else ["domain"])
            w.writeheader()
            w.writerows(items)
        print(f"{name}: {len(items)}")
    with open(os.path.join(store_dir, "apollo-domains.txt"), "w") as f:
        f.write("\n".join(r["domain"] for r in out["brands"]) + "\n")
    print(f"unique stores: {len(rows)}")


if __name__ == "__main__":
    main()
