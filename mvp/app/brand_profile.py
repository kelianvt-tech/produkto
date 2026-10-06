"""AI-filled brand profile for onboarding step 2.

Reads the catalog Produkto already fetched plus the store's own homepage and
about page, and proposes Description, Industry, Brand identity, Products &
Services and Target markets for the merchant to verify.

These fields are identity, not measurement: nothing here reaches question
generation, which still builds from the product record alone (see
`questions.py` and MEMORY.md, 2026-09-24).
"""
import html
import json
import re
import urllib.error
import urllib.request

import config
import db
import llm

UA = "Mozilla/5.0 (compatible; ProduktoBot/1.0; +https://produkto.ai)"
PAGE_PATHS = ("", "/pages/about", "/pages/about-us", "/about")
PAGE_CHARS = 2500

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["description", "industry", "identity", "services", "markets"],
    "properties": {
        "description": {"type": "string"},
        "industry": {"type": "string"},
        "identity": {"type": "array", "items": {"type": "string"}},
        "services": {"type": "array", "items": {"type": "string"}},
        "markets": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTIONS = """You are filling in a brand profile a merchant will verify.
Work only from the catalog and site text supplied. Never invent facts.

description: 1-2 sentences, 45 words maximum, plain and factual. Say what the
  brand sells, where it is based if the text states it, and what characterises
  the range. No marketing superlatives.
industry: a short retail category, 2-4 words, title case (e.g. "Furniture
  Retail", "Skincare", "Outdoor Equipment").
identity: 4-8 short adjective phrases describing the brand's character, title
  case, 1-3 words each (e.g. "Modern Design", "Craftsmanship"). Base them on
  the language the site and product copy actually use.
services: the product categories the brand sells, title case, taken from the
  catalog's own product types where possible (e.g. "Sofas", "Dining Tables").
  6-10 entries.
markets: countries or cities the text says the brand sells to or operates in.
  If the text says nothing, return an empty array. Never guess.

Leave a string empty or an array empty rather than guessing."""


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        if r.status != 200:
            return ""
        return r.read(400_000).decode("utf-8", "replace")


def _visible_text(markup):
    """Strip a page to its readable words. Crude on purpose: the model only
    needs positioning language, not structure."""
    markup = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", markup)
    text = re.sub(r"(?s)<[^>]+>", " ", markup)
    return " ".join(html.unescape(text).split())


def site_text(domain):
    """Homepage plus about page, best effort.

    Bot protection, TLS failures and timeouts are ordinary here, so a miss
    returns what we have rather than failing the profile.
    """
    out = []
    for path in PAGE_PATHS:
        if sum(len(t) for t in out) >= PAGE_CHARS:
            break
        for scheme in ("https://", "http://"):
            try:
                text = _visible_text(_fetch(scheme + domain + path))
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
                continue
            if len(text) > 200:
                out.append(text[:PAGE_CHARS])
            break
    return " ".join(out)[:PAGE_CHARS * 2]


def catalog_text(domain, limit=60):
    """Titles, types and a little body copy. `product_type` and the
    description live inside `raw_json`, not in their own columns."""
    rows = db.all_("SELECT title, price, raw_json FROM products "
                   "WHERE store_domain=? ORDER BY title LIMIT ?", (domain, limit))
    lines, types = [], set()
    for r in rows:
        p = dict(r)
        kind = db.product_type(p)
        if kind:
            types.add(kind)
        raw = json.loads(p.get("raw_json") or "{}")
        body = _visible_text(raw.get("body_html") or raw.get("description") or "")[:160]
        lines.append("- %s | %s | %s | %s" % (p.get("title") or "", kind,
                                              p.get("price") or "", body))
    return "Product types: %s\n\nProducts:\n%s" % (
        ", ".join(sorted(types)) or "unknown", "\n".join(lines))


FIELDS = ("DESCRIPTION", "INDUSTRY", "IDENTITY", "SERVICES", "MARKETS")


def scraped_question(domain, brand):
    """One short line for ChatGPT via Apify. It has web search, so it reads
    the site itself; we only add the catalog's own product types. The actor
    stalls on long queries (a ~6,000-character prompt never started on
    2026-09-25), so this stays well under 1,000 characters."""
    rows = db.all_("SELECT title, raw_json FROM products WHERE store_domain=?", (domain,))
    types = sorted({db.product_type(dict(r)) for r in rows} - {""})[:15]
    return ("Look at the online store %s (brand: %s). Reply ONLY with these 5 lines, no other text, "
            "no citations: DESCRIPTION: 1-2 factual sentences, max 45 words, what it sells and where "
            "it is based, no superlatives | INDUSTRY: 2-4 word retail category | IDENTITY: 4-8 short "
            "adjective phrases from the brand's own language, separated by ; | SERVICES: 6-10 product "
            "categories it sells, separated by ; | MARKETS: up to 5 main countries or cities the brand "
            "says it is based in or focuses on, separated by ; - not a shipping-country list, empty if "
            "not stated. Use Title Case for INDUSTRY, IDENTITY and SERVICES. Product types in its catalog: %s"
            % (domain, brand.get("brand_name") or domain, ", ".join(types) or "unknown"))


def parse_scraped(text):
    out = {}
    text = text.replace("**", "").replace("\\", "")
    for field in FIELDS:
        m = re.search(r"%s\s*:\s*(.*?)(?=\s*\|?\s*(?:%s)\s*:|$)" % (field, "|".join(FIELDS)),
                      text, re.S | re.I)
        value = re.sub(r"\s*\[\d+\]|\s*\(\[.*?\)\)", "", m[1]).strip(" |\n") if m else ""
        out[field.lower()] = value
    split = lambda v: [x.strip(" .") for x in re.split(r"[;\n]", v) if x.strip(" .")]
    return {"description": out["description"], "industry": out["industry"],
            "identity": split(out["identity"]), "services": split(out["services"]),
            "markets": split(out["markets"])}


def _generate_scraped(domain, brand, usage):
    import apify_answers
    run_id, dataset = apify_answers.start_run([scraped_question(domain, brand)])
    status = apify_answers.wait(run_id, poll=3, timeout=240)
    for text, _, _ in apify_answers.collect(dataset, status, run_id).values():
        if usage:
            usage.add_scraped(1)
        return parse_scraped(text)
    raise llm.LLMError("ChatGPT returned no brand profile. Fill it in by hand or try again.")


def generate(domain, usage=None):
    """Propose a profile. Raises llm.LLMError if the model call fails."""
    brand = db.brand(domain) or {}
    if config.ONBOARDING_SOURCE == "apify":
        out = _generate_scraped(domain, brand, usage)
        return {
            "description": " ".join(out["description"].split())[:600],
            "industry": " ".join(out["industry"].split())[:80],
            "identity": db._tags(out["identity"], 10),
            "services": db._tags(out["services"], 14),
            "markets": db._tags(out["markets"], 10),
        }
    payload = "Brand: %s\nWebsite: %s\n\n%s\n\nSite text:\n%s" % (
        brand.get("brand_name") or domain, domain, catalog_text(domain),
        site_text(domain) or "(site text unavailable)")
    out = llm.json_call(INSTRUCTIONS, payload, "brand_profile", SCHEMA, usage,
                        attempts=2)
    return {
        "description": " ".join((out.get("description") or "").split())[:600],
        "industry": " ".join((out.get("industry") or "").split())[:80],
        "identity": db._tags(out.get("identity"), 10),
        "services": db._tags(out.get("services"), 14),
        "markets": db._tags(out.get("markets"), 10),
    }


STATUS = {}          # domain -> "running" | "done" | "failed", this process only


def start(domain):
    """Run `ensure` in the background. Through Apify an answer takes 1-5
    minutes (17 once on 2026-09-25), far too long to hold the catalog
    request open, so step 2 opens at once and polls `status`."""
    import threading
    if STATUS.get(domain) == "running":
        return
    STATUS[domain] = "running"

    def run():
        try:
            brand = ensure(domain)
            STATUS[domain] = "done" if brand and brand.get("identity") else "failed"
        except Exception:                                   # noqa: BLE001
            STATUS[domain] = "failed"
    threading.Thread(target=run, daemon=True).start()


def status(domain):
    brand = db.brand(domain) or {}
    state = STATUS.get(domain, "idle")
    return {"status": state, "profile": {k: brand.get(k) or ("" if k in ("description", "industry") else [])
                                         for k in ("description", "industry", "identity", "services", "markets")}}


INDUSTRIES = (   # first match on the catalog's product types wins; empty if none
    ("Skincare", ("cleanser", "serum", "moistur", "skincare", "face oil", "sunscreen", "toner")),
    ("Beauty & Cosmetics", ("makeup", "lipstick", "mascara", "foundation", "fragrance", "perfume")),
    ("Hair Care", ("shampoo", "conditioner", "hair")),
    ("Supplements & Nutrition", ("supplement", "vitamin", "protein", "collagen", "electrolyte", "capsule")),
    ("Furniture Retail", ("sofa", "chair", "table", "bed", "sideboard", "shelf", "furniture", "stool")),
    ("Home & Lighting", ("lamp", "lighting", "rug", "cushion", "vase", "candle", "decor")),
    ("Apparel", ("shirt", "dress", "jacket", "trouser", "jeans", "hoodie", "apparel", "knitwear")),
    ("Footwear", ("shoe", "boot", "sneaker", "trainer", "sandal")),
    ("Jewellery & Accessories", ("ring", "necklace", "earring", "bracelet", "jewel", "watch", "bag")),
    ("Pet Supplies", ("dog", "cat", "pet")),
    ("Outdoor Equipment", ("tent", "backpack", "hiking", "camping", "knife")),
    ("Food & Drink", ("coffee", "tea", "snack", "chocolate", "sauce", "wine")),
)
COUNTRY_NAMES = {"GB": "United Kingdom", "US": "United States", "IE": "Ireland", "ES": "Spain",
                 "FR": "France", "DE": "Germany", "IT": "Italy", "NL": "Netherlands", "BE": "Belgium",
                 "PT": "Portugal", "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "FI": "Finland",
                 "PL": "Poland", "CH": "Switzerland", "AT": "Austria", "CA": "Canada",
                 "AU": "Australia", "NZ": "New Zealand", "JP": "Japan", "IN": "India"}


def quick(domain):
    """The instant fill, no AI and no cost: Shopify's own /meta.json gives the
    brand's description, city and country; the catalog gives the product
    categories and, through a keyword table, a first guess at the industry.
    One request, well under a second, so step 2 opens already filled in."""
    import catalog
    meta = {}
    try:
        status, body = catalog._get("https://%s/meta.json" % domain, timeout=6)
        if status == 200:
            meta = json.loads(body)
    except Exception:                                       # noqa: BLE001
        pass
    rows = db.all_("SELECT title, raw_json FROM products WHERE store_domain=?", (domain,))
    counts = {}
    for r in rows:
        kind = db.product_type(dict(r))
        if kind and kind.lower() not in ("uncategorised", "uncategorized", "other", "default", "all"):
            counts[kind] = counts.get(kind, 0) + 1
    services = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:10]
    # Score each industry by how many products match at a word start
    # ("chair" must not count as "hair"); the best-supported one wins.
    labels = [(db.product_type(dict(r)) + " " + dict(r)["title"]).lower() for r in rows]
    score = {name: sum(1 for t in labels if any(re.search(r"\b" + re.escape(w), t) for w in words))
             for name, words in INDUSTRIES}
    best = max(score, key=score.get) if score else ""
    industry = best if score.get(best) else ""
    country = meta.get("country") or ""
    markets = [m for m in (meta.get("city"), COUNTRY_NAMES.get(country, country)) if m]
    description = _visible_text(meta.get("description") or "")
    return {"description": description, "industry": industry, "identity": [],
            "services": services, "markets": markets}


def _merge(brand, profile):
    """Fill only what is still empty; never overwrite a value already there."""
    out, changed = {}, False
    for key in ("description", "industry", "identity", "services", "markets"):
        have = brand.get(key)
        out[key] = have if have else profile.get(key) or ("" if key in ("description", "industry") else [])
        changed = changed or (not have and bool(profile.get(key)))
    return out, changed


def fill_now(domain):
    """Instant part, called during the catalog fetch."""
    brand = db.brand(domain)
    if not brand:
        return None
    profile, changed = _merge(brand, quick(domain))
    if not changed:
        return brand
    return db.save_brand(domain, brand["brand_name"], brand["aliases"],
                         brand.get("country") or "", brand.get("currency") or "", profile)


def ensure(domain, usage=None):
    """AI top-up, in the background after `fill_now`: adds brand-identity
    adjectives and anything else still empty. Never overwrites a field the
    instant fill or the merchant has already set, and fails silently."""
    brand = db.brand(domain)
    if not brand:
        return None
    if brand.get("identity") and brand.get("industry") and brand.get("description"):
        return brand
    # No key means no AI top-up: skip the network, so tests and key-less
    # runs never touch it.
    if not (config.env("APIFY_TOKEN") if config.ONBOARDING_SOURCE == "apify"
            else config.api_key()):
        return brand
    try:
        ai = generate(domain, usage)
    except Exception as e:                                  # noqa: BLE001
        import sys
        sys.stderr.write("brand_profile: %s: %s\n" % (type(e).__name__, e))
        return brand
    brand = db.brand(domain)          # re-read: the merchant may have saved meanwhile
    profile, changed = _merge(brand, ai)
    if not changed:
        return brand
    return db.save_brand(domain, brand["brand_name"], brand["aliases"],
                         brand.get("country") or "", brand.get("currency") or "", profile)
