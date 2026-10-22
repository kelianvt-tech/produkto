"""Stricter DTC check: is the brand's own online store its main sales channel?
Free: fetches each homepage and Shopify /products.json. Run: python3 dtc_check.py in.csv out_prefix"""
import csv, json, re, sys, ssl, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

def get(url):
    for wait in (0,):
        time.sleep(wait)
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15, context=CTX)
            return r.read(800000).decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return None
        except Exception:
            return None
    return None

def check(row):
    d = row["organization_primary_domain"].strip()
    html = (get("https://" + d) or get("https://www." + d) or "").lower()
    pj, n_products, priced = get("https://%s/products.json?limit=250" % d), 0, 0
    try:
        prods = json.loads(pj)["products"]
        n_products = len(prods)
        priced = sum(1 for p in prods if any(float(v.get("price") or 0) > 0 for v in p.get("variants", [])))
    except Exception:
        pass
    cart = len(re.findall(r"add to cart|add to bag|addtocart|/cart|checkout", html))
    prices = len(re.findall(r"\$\s?\d{1,4}\.\d{2}", html))
    shop = "cdn.shopify.com" in html or "bigcommerce" in html or "woocommerce" in html
    retail = len(re.findall(r"wholesale|store locator|find (us )?in (a )?stores?|where to buy|stockists?|find a retailer|available at", html))
    if not html and not n_products:
        verdict, why = "drop", "site unreachable"
    elif priced >= 3 and retail <= 3:
        verdict, why = "keep", "own store: %d priced products" % priced
    elif priced >= 3:
        verdict, why = "review", "own store (%d priced) but %d wholesale/retail mentions" % (priced, retail)
    elif shop and cart >= 2 and prices >= 3 and retail <= 3:
        verdict, why = "keep", "store platform, cart and %d prices on homepage" % prices
    elif cart >= 2:
        verdict, why = "review", "cart on site, not Shopify-readable (%d retail mentions)" % retail
    else:
        verdict, why = "drop", "no online store found"
    return dict(row, dtc_verdict=verdict, dtc_reason=why, products=n_products, retail_mentions=retail)

rows = list(csv.DictReader(open(sys.argv[1])))
out = []
with ThreadPoolExecutor(12) as ex:
    for i, r in enumerate(ex.map(check, rows), 1):
        out.append(r)
        if i % 25 == 0:
            print("done", i, "of", len(rows), flush=True)
for v in ("keep", "review", "drop"):
    sel = [r for r in out if r["dtc_verdict"] == v]
    if sel:
        w = csv.DictWriter(open("%s-dtc-%s.csv" % (sys.argv[2], v), "w", newline=""), fieldnames=list(sel[0]))
        w.writeheader(); w.writerows(sel)
    print(v, len(sel))
