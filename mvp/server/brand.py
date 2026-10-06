"""Read a store's brand identity from its own homepage.

Everything here is taken from the site itself - the <title>, the meta
description, og: tags, and the vendor/type fields on its own products. Nothing
is invented. If a field isn't published, it comes back empty and the UI says
"not found" rather than filling the gap with a plausible sentence.

That rule matters more than it looks: a Brand Hub that quietly invents a
description is indistinguishable from one that read the site correctly, right
up until the merchant reads it and stops trusting the whole report.
"""

import html as _html
import re
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; ProduktoAudit/0.1; +https://produkto.example)"

_STOP = {"the", "and", "for", "with", "your", "our", "shop", "store", "online",
         "official", "home", "buy", "best", "new", "all", "collection"}


def _clean(s):
    if not s:
        return ""
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _meta(doc, attr, value):
    m = re.search(
        r'<meta[^>]+%s=["\']%s["\'][^>]+content=["\']([^"\']*)["\']'
        % (attr, re.escape(value)), doc, re.I)
    if m:
        return _clean(m.group(1))
    m = re.search(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+%s=["\']%s["\']'
        % (attr, re.escape(value)), doc, re.I)
    return _clean(m.group(1)) if m else ""


def _plausible_alias(a):
    """Reject internal codes masquerading as brand names.

    M&O's own catalogue carries the vendor 'MC7O-Living' beside 'M&O' - a
    digit wedged inside a word is the tell. It's real data, but it is not a
    name a buyer would ever type into ChatGPT, so it does not belong in the
    list we search AI answers for.
    """
    a = a.strip()
    if len(a) < 2 or len(a) > 40:
        return False
    if re.search(r"[a-zA-Z]\d|\d[a-zA-Z]", a) and not a.lower().endswith(".com"):
        return False
    return len(re.findall(r"[a-zA-Z]", a)) >= 2


def fetch_site(domain, timeout=20):
    """Homepage HTML, or '' if it can't be read. Never raises."""
    try:
        req = urllib.request.Request("https://%s/" % domain,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:                                           # noqa: BLE001
        return ""


CURRENCY_SYMBOL = {"GBP": "£", "EUR": "€", "USD": "$", "CAD": "CA$",
                   "AUD": "A$", "SEK": "kr", "DKK": "kr", "NOK": "kr",
                   "CHF": "CHF", "JPY": "¥", "PLN": "zł"}

# Where "delivered in Europe" is the right phrasing and where it isn't.
_EU = {"ES", "FR", "DE", "IT", "NL", "BE", "PT", "IE", "AT", "SE", "DK",
       "FI", "PL", "CZ", "GR", "RO", "HU", "SK", "SI", "HR", "BG", "LU",
       "EE", "LV", "LT", "MT", "CY", "GB", "NO", "CH"}


def read_meta(domain, timeout=12):
    """Shopify exposes /meta.json with the shop's real currency and country.

    Worth the extra request: Clubhouse Skin prices in GBP, so rendering its
    catalogue with a euro sign is simply wrong, and a buyer question reading
    "under €50" for a £39 product is wrong in a way a merchant will spot.
    """
    import json as _json
    try:
        req = urllib.request.Request("https://%s/meta.json" % domain,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = _json.loads(r.read())
        cur = (d.get("currency") or "").upper()
        country = (d.get("country") or "").upper()
        return {
            "currency": cur,
            "symbol": CURRENCY_SYMBOL.get(cur, (cur + " ") if cur else "€"),
            "country": country,
            "region": "Europe" if country in _EU else (
                "the US" if country == "US" else None),
            "shop_name": (d.get("name") or "").strip(),
        }
    except Exception:                                           # noqa: BLE001
        return {"currency": "", "symbol": "€", "country": "",
                "region": None, "shop_name": ""}


def _blocks(doc):
    """Paragraph-ish text blocks from a page, chrome included."""
    d = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", doc)
    d = re.sub(r"(?is)<br\s*/?>|</(p|div|li|h[1-6]|section)>", "\n", d)
    out = []
    for line in re.sub(r"<[^>]+>", " ", d).split("\n"):
        t = _clean(line)
        if len(t) >= 45:
            out.append(t)
    return out


def _site_pages(domain, limit=6, timeout=15):
    """Follow sitemap.xml to the store's own content pages.

    /pages/about guessing does not work - Clubhouse Skin's brand page is
    /pages/founding-letter, which no guess would find. The sitemap index also
    carries query strings, so the child sitemaps must be unescaped first.
    """
    idx = fetch_site(domain)          # warms nothing; separate call below
    urls = []
    try:
        req = urllib.request.Request("https://%s/sitemap.xml" % domain,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            root = r.read().decode("utf-8", "replace")
        for child in [_html.unescape(u) for u in
                      re.findall(r"<loc>([^<]+)</loc>", root)]:
            if "pages" not in child:
                continue
            with urllib.request.urlopen(
                    urllib.request.Request(child, headers={"User-Agent": UA}),
                    timeout=timeout) as r2:
                sub = r2.read().decode("utf-8", "replace")
            urls += [_html.unescape(u) for u in
                     re.findall(r"<loc>([^<]+)</loc>", sub)]
    except Exception:                                           # noqa: BLE001
        pass
    urls = [u for u in urls if not _LEGAL_URL.search(u)]
    return urls[:limit], idx


# Policy pages talk about "customers" too, but in a way that has nothing to do
# with who the brand sells to. Allbirds' privacy policy was outranking its
# actual brand copy until these were excluded.
_LEGAL_URL = re.compile(
    r"privacy|terms|policy|policies|legal|cookie|shipping|returns?|refund|"
    r"accessibility|warranty|faq|help|track|gift-card|careers?", re.I)

_LEGAL_TEXT = re.compile(
    r"personal information|applicable laws?|third part|process(ing)? your data|"
    r"we collect|governing law|liabilit|terms of (use|service)|"
    r"you agree|cookies?\b", re.I)


# A brand almost always states its audience in one of these shapes.
_AUDIENCE = re.compile(
    r"\b(is for|are for|made for|built for|designed for|created for|"
    r"for the person|for people who|for those who|for anyone who|"
    r"our customers?|we serve|you'?re the kind of)\b", re.I)


def persona(domain):
    """The brand's own words about who it sells to, or ('', '') if unstated.

    Nothing is written on the brand's behalf. If the site never says who it
    is for, both fields come back empty and the UI asks the merchant.
    """
    urls, home_doc = _site_pages(domain)
    chrome = set(_blocks(home_doc))
    found = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                doc = r.read().decode("utf-8", "replace")
        except Exception:                                       # noqa: BLE001
            continue
        for b in _blocks(doc):
            if b in chrome or b in found:
                continue
            if _AUDIENCE.search(b) and not _LEGAL_TEXT.search(b):
                found.append(b)
    if not found:
        for b in _blocks(home_doc):
            if (_AUDIENCE.search(b) and not _LEGAL_TEXT.search(b)
                    and b not in found):
                found.append(b)
    if not found:
        return "", ""

    # Name: the noun phrase the brand itself uses, not one we made up.
    name = ""
    m = re.search(r"\bfor (the person|people|those|anyone) ([^.;]{5,90})",
                  found[0], re.I)
    if m:
        name = _clean("%s %s" % (m.group(1), m.group(2))).rstrip(",")
        name = name[:1].upper() + name[1:]
    return name, "\n\n".join(found[:3])


def read(domain, products=None):
    """Return the brand fields we could actually find, plus their sources."""
    doc = fetch_site(domain)
    products = products or []
    meta = read_meta(domain)

    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.S | re.I)
    if m:
        title = _clean(m.group(1))

    site_name = _meta(doc, "property", "og:site_name")
    if not site_name and title:
        # "Clubhouse Skin - skincare made with intent" -> "Clubhouse Skin"
        site_name = re.split(r"\s+[|–—-]\s+", title)[0].strip()

    desc = (_meta(doc, "name", "description")
            or _meta(doc, "property", "og:description"))

    vendors = []
    for p in products:
        v = (p.get("raw", {}) or {}).get("vendor", "")
        if v and v not in vendors:
            vendors.append(v)

    pname, pdesc = persona(domain)
    name = (meta.get("shop_name") or site_name
            or (vendors[0] if vendors else ""))
    root = domain.split(".")[0]

    aliases = []
    for a in [name, root, root.replace("-", " "), domain] + vendors:
        a = (a or "").strip()
        if not a or not _plausible_alias(a):
            continue
        if a.lower() not in [x.lower() for x in aliases]:
            aliases.append(a)
    if name and " " in name:
        squashed = name.replace(" ", "")
        if squashed.lower() not in [x.lower() for x in aliases]:
            aliases.append(squashed)

    return {
        "name": name,
        "aliases": aliases[:6],
        "description": desc,
        "industry": _industry(products, desc, title),
        "types": _top_types(products),
        "persona_name": pname,
        "persona_desc": pdesc,
        "currency": meta["currency"],
        "symbol": meta["symbol"],
        "country": meta["country"],
        "region": meta["region"],
        "sources": {
            "name": "meta.json" if meta.get("shop_name") else (
                "og:site_name" if site_name else
                ("product vendor" if vendors else "not found")),
            "description": "meta description" if desc else "not found",
            "industry": "product types" if _types(products) else "page text",
            "persona": "the brand's own pages" if pdesc else "not stated on site",
        },
        "reachable": bool(doc),
    }


def _top_types(products, n=4):
    counts = {}
    for t in _types(products):
        k = t.strip().lower()
        counts[k] = counts.get(k, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(t, c) for t, c in ranked[:n]]


# Shopify tags are a dumping ground for operational plumbing as well as real
# categories. Allbirds publishes "allbirds::complete => true", "shoprunner" and
# "SF OUTLET INVENTORY" alongside nothing useful; presenting those back to a
# merchant as their "industry" reads as broken software.
_TAG_JUNK = re.compile(
    r"[:=]|\bshoprunner\b|\boutlet\b|\binventory\b|\breturnable\b|"
    r"\bwarehouse\b|\barchive\b|\bhidden\b|\bexclude\b|\bpreorder\b|"
    r"\bfinal[ _-]?sale\b|\bgift[ _-]?card\b|^\d+$", re.I)


def _usable_tag(tag):
    tag = str(tag).strip()
    if not tag or len(tag) > 28 or len(tag) < 3:
        return False
    if _TAG_JUNK.search(tag):
        return False
    if re.match(r"^[A-Z]{2,}\d", tag):          # SKU-ish, e.g. MOIS007
        return False
    # Underscores in a Shopify tag are a machine convention, never a
    # customer-facing category. Allbirds namespaces merchandising rules as
    # YCRF_socks, YCRF_womens-move-shoes and so on; a merchant reading
    # "your industry: YCRF_socks" would rightly conclude the tool is broken.
    if "_" in tag:
        return False
    if tag.isupper() and " " in tag:            # ops labels: DNAM BRANDS
        return False
    return bool(re.search(r"[a-zA-Z]{3}", tag))


def _types(products):
    """product_type if the store fills it in, tags only as a fallback.

    Mixing the two is what let "onsite @ wc 5.26" outrank "Apparel" for
    Allbirds: product_type is a single curated field, whereas tags are an
    unbounded merchandising dumping ground. Filtering tags will always be
    whack-a-mole, so prefer the curated field outright and drop to tags only
    for stores like M&O that leave product_type empty on every product.
    """
    out = []
    for p in products:
        raw = p.get("raw", {}) or {}
        t = (raw.get("product_type") or "").strip()
        if t:
            out.append(t)
            continue
        # Per-product fallback, not catalogue-wide. M&O fills product_type on
        # exactly 2 of its 87 products ("SOFA", "BED"); a catalogue-wide rule
        # let those two outvote the tags on the other 85 and reported the
        # store as having one bed and one sofa.
        for tag in (raw.get("tags") or []):
            if _usable_tag(tag):
                out.append(str(tag).strip())
    return out


def _industry(products, desc, title):
    """Most common product type or tag. Falls back to salient page words."""
    types = _types(products)
    if types:
        counts = {}
        for t in types:
            k = t.lower()
            counts[k] = counts.get(k, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ", ".join(t for t, _ in ranked[:3])
    words = re.findall(r"[a-z]{4,}", (desc + " " + title).lower())
    counts = {}
    for w in words:
        if w in _STOP:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(w for w, _ in ranked[:3])
