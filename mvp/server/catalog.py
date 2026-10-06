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
    meta = {
        "domain": domain,
        "products": len(rows),
        "variants": sum(r["variants"] for r in rows),
        "vendor": _mode([p.get("vendor") for p in products if p.get("vendor")]),
    }
    return rows, meta


def _mode(values):
    best, seen = None, {}
    for v in values:
        seen[v] = seen.get(v, 0) + 1
        if best is None or seen[v] > seen[best]:
            best = v
    return best


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
            "product_type": p.get("product_type") or "",
            "tags": p.get("tags") or [],
            "vendor": p.get("vendor") or "",
            "options": [o.get("name") for o in (p.get("options") or [])],
        },
    }
