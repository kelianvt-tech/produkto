"""Fetch any Shopify store's catalogue from its public /products.json.

This is the piece the artifact mockup could never do: an Artifact's CSP blocks
every outbound request, so reading someone else's store has to happen
server-side. Nothing here is store-specific.

Note on counting: catalogue size is reported in VARIANTS as well as products.
A footwear brand listing 140 "products" can be a 6,825-SKU catalogue once
colour x size is counted, and the SKU count is what decides whether a brand
sits inside the ICP band.
"""

import json
import re
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; ProduktoAudit/0.1; +https://produkto.example)"
PAGE_LIMIT = 250
MAX_PAGES = 20


class CatalogError(Exception):
    """Raised with a message meant to be shown to the user as-is."""


def normalise_domain(raw):
    """'https://www.Shop.com/collections/all?x=1' -> 'shop.com'"""
    d = (raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0].strip()
    if d.startswith("www."):
        d = d[4:]
    if not d or "." not in d or " " in d:
        raise CatalogError(
            "That doesn't look like a store domain. Try something like "
            "yourstore.com or yourstore.myshopify.com."
        )
    return d


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


SYMBOLS = {'GBP': '£', 'USD': '$', 'EUR': '€', 'CAD': 'CA$', 'AUD': 'A$',
           'NZD': 'NZ$', 'CHF': 'CHF', 'SEK': 'kr', 'DKK': 'kr', 'NOK': 'kr',
           'JPY': '¥', 'INR': '₹', 'PLN': 'zł', 'CZK': 'Kč'}


def store_meta(domain):
    """Currency and country, straight from the store's own /meta.json.

    Shopify publishes this next to the catalogue. Getting it right matters:
    a question written without a currency ("cleansers around 39") gets read
    as an age by ChatGPT. Falls back to /cart.js, then to nothing - never a
    guess, because the wrong currency is worse than none.
    """
    for path, keys in (('/meta.json', ('currency', 'country')), ('/cart.js', ('currency',))):
        try:
            status, body = _get('https://%s%s' % (domain, path), timeout=15)
            if status != 200:
                continue
            data = json.loads(body)
            out = {k: (data.get(k) or '') for k in keys}
            if out.get('currency'):
                out.setdefault('country', '')
                out['symbol'] = SYMBOLS.get(out['currency'], '')
                return out
        except Exception:                                       # noqa: BLE001
            continue
    return {'currency': '', 'country': '', 'symbol': ''}


def fetch(domain):
    """Return (products, meta). Raises CatalogError with a readable message."""
    products, page = [], 1
    while page <= MAX_PAGES:
        url = "https://%s/products.json?limit=%d&page=%d" % (domain, PAGE_LIMIT, page)
        try:
            status, body = _get(url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise CatalogError(
                    "%s blocked the request (HTTP %d). The store is probably "
                    "behind a bot filter or password. Nothing we can read from "
                    "here." % (domain, e.code)
                )
            if e.code == 404:
                raise CatalogError(
                    "%s has no public /products.json. That usually means it "
                    "isn't a Shopify store." % domain
                )
            raise CatalogError("%s returned HTTP %d." % (domain, e.code))
        except urllib.error.URLError as e:
            raise CatalogError("Couldn't reach %s (%s)." % (domain, e.reason))
        except Exception as e:                                  # noqa: BLE001
            raise CatalogError("Couldn't reach %s (%s)." % (domain, e))

        if status != 200:
            raise CatalogError("%s returned HTTP %s." % (domain, status))
        try:
            batch = json.loads(body).get("products", [])
        except ValueError:
            raise CatalogError(
                "%s returned something that isn't JSON. It may be a "
                "storefront password page rather than a Shopify catalogue."
                % domain
            )
        if not batch:
            break
        products.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        page += 1

    if not products:
        raise CatalogError(
            "%s published an empty catalogue. Nothing to audit." % domain
        )

    rows = [_normalise(p, domain) for p in products]
    cats = categories(domain)
    for r in rows:
        r["raw"]["category"] = cats.get(r["handle"], "")
    meta = {
        "domain": domain,
        "products": len(rows),
        "variants": sum(r["variants"] for r in rows),
        "vendor": _mode([p.get("vendor") for p in products if p.get("vendor")]),
    }
    meta.update(store_meta(domain))
    return rows, meta


def _mode(values):
    best, seen = None, {}
    for v in values:
        seen[v] = seen.get(v, 0) + 1
        if best is None or seen[v] > seen[best]:
            best = v
    return best


def _price_range(variants):
    prices = []
    for v in variants:
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            continue
    return [min(prices), max(prices)] if prices else []

# Collections that hold (nearly) everything say nothing about what a product is.
CATCH_ALL = {"frontpage", "all", "home", "home-page", "shop", "shop-all",
             "all-products", "new", "new-arrivals", "sale", "best-sellers",
             "bestsellers", "featured"}


def categories(domain):
    """Map product handle -> its most specific store collection title.

    Stores organise their catalog into collections (Beds, Sofas,
    Decorations...), which is far more reliable than product_type, which many
    merchants leave blank. Each product gets the smallest collection it sits
    in, so "Lounge Chair" wins over a parent like "Seating". Catch-all
    collections are skipped. Best effort: any failure returns {} and the
    caller falls back to product_type and tags."""
    try:
        status, body = _get("https://%s/collections.json?limit=250" % domain)
        cols = json.loads(body).get("collections", []) if status == 200 else []
    except Exception:                                           # noqa: BLE001
        return {}
    members = []
    for c in cols:
        handle = (c.get("handle") or "").lower()
        if handle in CATCH_ALL:
            continue
        handles, page = set(), 1
        while page <= MAX_PAGES:
            try:
                status, body = _get("https://%s/collections/%s/products.json?limit=%d&page=%d"
                                    % (domain, handle, PAGE_LIMIT, page))
                batch = json.loads(body).get("products", []) if status == 200 else []
            except Exception:                                   # noqa: BLE001
                break
            handles.update(p.get("handle") for p in batch)
            if len(batch) < PAGE_LIMIT:
                break
            page += 1
        if handles:
            members.append(((c.get("title") or handle).strip(), handles))
    total = len(set().union(*(h for _, h in members))) if members else 0
    # A collection with most of the catalog is a catch-all under another name.
    members = [m for m in members if len(m[1]) <= max(1, total * 0.6)]
    out = {}
    for title, handles in sorted(members, key=lambda m: -len(m[1])):
        for h in handles:
            out[h] = title          # smaller collections overwrite larger ones
    return out


def _normalise(p, domain):
    variants = p.get("variants") or []
    price = None
    for v in variants:
        try:
            price = float(v.get("price"))
            break
        except (TypeError, ValueError):
            continue
    images = p.get("images") or []
    return {
        "shopify_id": p.get("id"),
        "handle": p.get("handle"),
        "title": (p.get("title") or "").strip(),
        "url": "https://%s/products/%s" % (domain, p.get("handle")),
        "price": ("%.0f" % price) if price is not None else "",
        "image": (images[0].get("src") if images else "") or "",
        "variants": len(variants),
        "raw": {
            "body_html": p.get("body_html") or "",
            # Lowest and highest variant price, for the product page's
            # "Catalog price" range. Stored in raw so no column is needed.
            "price_range": _price_range(variants),
            "product_type": p.get("product_type") or "",
            "tags": p.get("tags") or [],
            "vendor": p.get("vendor") or "",
            "options": [o.get("name") for o in (p.get("options") or [])],
        },
    }
