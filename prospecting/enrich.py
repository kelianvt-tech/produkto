#!/usr/bin/env python3
"""
Contact enrichment for the brand list.

Takes brands.csv, resolves each brand to a live domain, then pulls whatever
contact detail the brand publishes on its own site: Instagram, LinkedIn,
X/Twitter, any mailto: addresses, and the About/Contact page URLs where a
founder is usually named. Also runs the triage checks (Shopify, product count,
Yotpo) so you get one file instead of two.

    python3 prospecting/enrich.py prospecting/brands.csv

Writes prospecting/enriched-<date>.csv and a readable .md summary.

Standard library only. Default 1.5s between requests -- these are real shops,
don't hammer them.

WHAT THIS DOES NOT DO
---------------------
It does not find personal email addresses, and it does not verify anything.
The `email_guesses` column is a pattern guess and MUST be verified through
Hunter/Apollo before you send. Sending to unverified guesses will bounce and
damage your sending domain.
"""

import argparse
import csv
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; prospect-research/1.0)"
TIMEOUT = 20

TLDS = (".com", ".co", ".shop", ".store", ".co.uk", ".ca")
ABOUT_PATHS = ("/pages/about", "/pages/about-us", "/pages/our-story",
               "/pages/contact", "/pages/contact-us", "/about", "/about-us")

YOTPO_MARKERS = ("yotpo.com", "staticw2.yotpo", "yotpo-widget")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I)
LI_RE = re.compile(r"linkedin\.com/(company|in)/([A-Za-z0-9\-_%]+)", re.I)
TW_RE = re.compile(r"(?:twitter|x)\.com/([A-Za-z0-9_]+)", re.I)

# Junk that shows up in social links but isn't the brand's handle
IG_SKIP = {"p", "explore", "reel", "reels", "accounts", "stories", "tv"}
TW_SKIP = {"share", "intent", "home", "hashtag", "i", "search"}

# Case-sensitive on the name capture, case-tolerant on the cue word.
FOUNDER_RE = re.compile(
    r"(?:[Cc]o-?[Ff]ounder|[Ff]ounded\s+by|[Ff]ounder|CEO|[Oo]wner)[^.]{0,60}?"
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){1,2})\b")


def fetch(url, timeout=TIMEOUT, retries=0, max_bytes=400_000):
    """
    GET a URL. `retries` matters for the domain confirmation step -- a single
    transient failure there used to send the whole row down the guessing path
    and land it on a squatter domain.

    `max_bytes` must be generous for JSON endpoints. The 400KB default silently
    truncated large products.json responses mid-structure, JSON parsing then
    failed, and every big catalog came back with an unknown product count --
    which the status logic then reported as "OK".
    """
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ct = r.headers.get("Content-Type", "")
                if "html" not in ct and "json" not in ct and "text" not in ct:
                    return None, None
                return r.status, r.read(max_bytes).decode("utf-8", errors="replace")
        except Exception:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return None, None


# Domains that appear on every Shopify article and are never the merchant.
# Matched as substrings, so entries need to cover the real hostnames --
# "google.com" does NOT match "googletagmanager.com", which is how the tag
# manager once got picked as a brand's storefront.
NOT_THE_STORE = (
    # Shopify's own properties
    "shopify.com", "shopifycdn", "shopify.dev", "shopifyacademy", "shopifystatus",
    "shopifyplus", "myshopify.com",
    # Social
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "youtu.be", "tiktok.com", "pinterest.com", "snapchat.com",
    "threads.net", "reddit.com",
    # Analytics, tag management, ads
    "google", "googletagmanager", "google-analytics", "googleapis",
    "gstatic", "doubleclick", "googlesyndication", "hotjar", "segment.io",
    "mixpanel", "amplitude.com", "hubspot", "klaviyo", "mailchimp",
    # CDNs and infrastructure
    "cloudflare", "jsdelivr", "unpkg.com", "cdnjs", "bootstrapcdn",
    "amazonaws.com", "akamai", "fastly", "cloudfront",
    # Platforms and misc
    "apple.com", "podcasts.apple", "spotify.com", "soundcloud.com",
    "wikipedia.org", "amazon.com", "wordpress.org", "gravatar.com",
    "w3.org", "schema.org", "gmpg.org",
)

HREF_RE = re.compile(r'href=["\'](https?://[^"\'>\s]+)', re.I)


def store_from_episode(episode_url, brand):
    """
    Pull the merchant's own URL and the founder's name out of the Shopify
    article. Far more reliable than guessing the domain from the brand name --
    these articles link the store and the meta description usually names the
    guest.
    """
    status, body = fetch(episode_url)
    if status != 200 or not body:
        return None, None, None

    counts = {}
    for href in HREF_RE.findall(body):
        host = urllib.parse.urlparse(href).netloc.lower().replace("www.", "")
        if not host or any(bad in host for bad in NOT_THE_STORE):
            continue
        counts[host] = counts.get(host, 0) + 1
    if not counts:
        return None, None, body

    tokens = [t for t in re.split(r"[^a-z0-9]+", brand.lower()) if len(t) > 2]

    # Require the host to share a word with the brand. Without this the rule
    # degenerates to "most-linked surviving host", which picks whatever
    # infrastructure domain the blocklist missed rather than the merchant.
    # Better to return nothing and let the row be marked NOT FOUND than to
    # hand back a confident wrong domain.
    matching = [h for h in counts if any(t in h for t in tokens)]
    if not matching:
        return None, None, body

    best = max(matching, key=lambda h: counts[h])
    return f"https://{best}", founder_from_article(body, brand), body


# A full name. Handles O'Donnell, McCormick, Szaniewski, hyphenated and
# particle surnames (Van, De, La).
# Single space between parts, deliberately. Stripping HTML tags leaves runs of
# whitespace where the tag was, so `\s+` bridges those gaps and glues adjacent
# names together ("Meghan Coyle  Andrew"), swallowing an occurrence and
# breaking the frequency count. A real full name uses single spaces.
# Surname part: handles Benin, O'Donnell, McCormick, N'Diaye-Mbaye, Szaniewski.
_SURNAME = (r"(?:[A-Z]['‘’])?(?:Mc|Mac)?[A-Z][a-z]+(?:['‘’\-][A-Z]?[a-z]+)*")
NAME_RE = re.compile(r"\b([A-Z][a-z]{1,15}(?: " + _SURNAME + r"){1,2})\b")

# Look like names, aren't the founder.
NAME_STOP = {
    "black friday", "cyber monday", "new balance", "shopify masters",
    "united states", "new york", "los angeles", "san francisco", "start free",
    "share article", "popular posts", "privacy policy", "learn more",
    "read more", "sell anywhere", "enter email", "apple podcasts",
    "google podcasts", "subscribe anytime", "terms and", "skip to",
}

META_DESC_RE = re.compile(
    r'<meta[^>]+(?:property=["\']og:description["\']|name=["\']description["\'])'
    r'[^>]+content=["\']([^"\']{20,400})', re.I)

# The staff writer's byline links to /blog/authors/first-last
AUTHOR_RE = re.compile(r'/blog/authors/([a-z]+(?:-[a-z]+)+)')

# Capitalised words that sit immediately before a name in these subtitles and
# get swallowed by the match: "How Sean Reyes", "Founder Matthew Hassett".
LEADING_NOT_NAME = {
    "how", "why", "when", "what", "where", "who", "the", "this", "these",
    "meet", "inside", "after", "before", "founder", "founders", "cofounder",
    "co-founder", "ceo", "owner", "three", "two", "four", "both", "friends",
    "sisters", "brothers", "former", "ex", "then", "now", "today", "his",
    "her", "their", "a", "an", "and", "but", "with", "from", "for", "by",
}


# Title-case headline fragments look exactly like names: "Shared Ownership
# Model", "Brand Storytelling Lesson". If any word in a candidate is one of
# these, it is a headline, not a person.
NOT_A_SURNAME = {
    "shared", "ownership", "model", "story", "storytelling", "growth", "brand",
    "brands", "branding", "business", "success", "years", "year", "strategy", "strategies",
    "lesson", "lessons", "tips", "guide", "secrets", "journey", "revenue",
    "sales", "marketing", "retail", "design", "community", "launch", "scaling",
    "building", "built", "company", "customers", "customer", "product",
    "products", "market", "money", "profit", "profits", "team", "teams",
    "experience", "collection", "studio", "lab", "shop", "store", "co",
    "beauty", "skin", "care", "coffee", "food", "home", "living", "goods",
    # pronouns and function words that slip into title-case headlines
    "it", "its", "them", "they", "us", "we", "you", "your", "our", "my",
    "apart", "again", "back", "down", "up", "out", "off", "over", "into",
    "set", "got", "get", "made", "make", "makes", "turned", "turns", "went",
    "grew", "grow", "grows", "scaled", "scales", "sold", "sell", "sells",
}


def _trim_name(name):
    """Drop leading words that are not part of the name, then sanity check."""
    parts = name.split()
    while parts and parts[0].lower() in LEADING_NOT_NAME:
        parts.pop(0)
    if len(parts) < 2:
        return None
    if any(p.lower() in NOT_A_SURNAME for p in parts):
        return None
    return " ".join(parts)


def founder_from_article(body, brand):
    """
    Pull the interviewed founder's name out of a Shopify blog article.

    The subtitle under the headline names them nearly every time, and that same
    sentence is the page's og:description:

        "Three friends, Bart Szaniewski, Grant Eastey, and Ejay O'Donnell,
         built a hat company to foster community among dads."
        "Founder Matthew Hassett explains why hardware financing is brutal."
        "How Sean Reyes turned an information gap in car parts into a business."

    So that is the primary source. Cue-word matching and frequency scoring are
    fallbacks. The Shopify staff writer is always excluded.

    The previous version only read the first 6000 characters of raw HTML, which
    is entirely <head> boilerplate, and required a cue word like "founder" to
    precede the name. Sentences like "Three friends, Bart..." matched nothing,
    which is why so many rows came back blank.
    """
    brand_tokens = {t for t in re.split(r"[^a-z0-9]+", brand.lower()) if len(t) > 2}
    authors = {a.replace("-", " ").lower() for a in AUTHOR_RE.findall(body)}

    def clean(raw):
        """Trim leading noise, then reject authors, brand words and non-names."""
        name = _trim_name(raw)
        if not name:
            return None
        low = name.lower()
        if low in authors or low in NAME_STOP:
            return None
        # Reject only when the FIRST word is a brand word. That kills headline
        # fragments ("Graza Branding", "Hotel Lobby") while keeping founders
        # whose surname is the brand, which is common: Adrian Solgaard,
        # Jono Pandolfi, Inder Bedi.
        if low.split()[0] in brand_tokens:
            return None
        return name

    text = re.sub(r"<[^>]+>", " ", body)

    # 1. Subtitle / meta description. Most reliable by a wide margin, but a
    #    title-case headline looks identical to a name ("Second Chance for
    #    Sustainable Fashion"). Word blocklists never catch them all, so
    #    validate structurally instead: a real person is either introduced by a
    #    cue word or mentioned again later in the piece. A headline fragment
    #    appears exactly once, in the headline.
    m = META_DESC_RE.search(body)
    if m:
        desc = m.group(1)
        for raw in NAME_RE.findall(desc):
            name = clean(raw)
            if not name:
                continue
            near_cue = re.search(
                r"(?:[Cc]o-?[Ff]ounder|[Ff]ounded|[Ff]ounder|CEO|[Oo]wner)[^.]{0,40}"
                + re.escape(name), desc)
            # `text` excludes the meta tag itself (tag-stripping removes the
            # whole element including its content attribute), so one hit here
            # means the name is used in the article body, not just the headline.
            if near_cue or text.count(name) >= 1:
                return name

    # 2. A name sitting next to a founder cue word.
    for m in FOUNDER_RE.finditer(text):
        name = clean(m.group(1))
        if name:
            return name

    # 3. Frequency. An interview write-up names its subject repeatedly.
    freq = {}
    for raw in NAME_RE.findall(text):
        name = clean(raw)
        if name:
            freq[name] = freq.get(name, 0) + 1
    if freq:
        name, n = max(freq.items(), key=lambda kv: kv[1])
        if n >= 2:
            return name
    return None


# Parked / for-sale / squatter pages. These reliably contain the brand name --
# that is the entire business model of a squatter -- so a name match alone is
# not evidence that we found the real store.
PARKED_MARKERS = (
    "domain is for sale", "buy this domain", "this domain is parked",
    "domain for sale", "is for sale", "parkingcrew", "sedoparking",
    "afternic", "dan.com", "hugedomains", "godaddy.com/domainsearch",
    "related searches", "domain name is available",
)

# Signals that a page is an actual storefront rather than a landing page.
STORE_MARKERS = (
    "add to cart", "add to bag", "/cart", "shopping cart", "checkout",
    "/collections/", "/products/", "shopify", "woocommerce", "bigcommerce",
    "my account", "free shipping",
)


def looks_like_a_store(body):
    """True if the page reads like a real shop and not a parked domain."""
    blob = body.lower()
    if any(m in blob for m in PARKED_MARKERS):
        return False
    # Squatter pages are usually tiny; real storefronts are not.
    if len(body) < 20_000:
        return False
    return sum(1 for m in STORE_MARKERS if m in blob) >= 2


def resolve_domain(brand, slug):
    """
    Fallback only: try slug + common TLDs.

    Requires the brand name AND storefront signals, which screens out parked
    pages. It does NOT screen out counterfeit clones: avocadogreenmattress.shop
    is a full WooCommerce copy of the real brand, and no content heuristic
    separates a good clone from the original. That is why the episode link is
    retried hard before this function is ever reached, and why anything
    resolved here is labelled GUESSED and must be eyeballed before use.
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", brand.lower()) if t]
    candidates = []
    if slug:
        candidates.append(slug)
    joined = "".join(tokens)
    if joined and joined not in candidates:
        candidates.append(joined)

    for cand in candidates:
        for tld in TLDS:
            url = f"https://{cand}{tld}"
            status, body = fetch(url, timeout=12, retries=1)
            if status == 200 and body:
                blob = body.lower()
                key = max(tokens, key=len) if tokens else cand
                if (key in blob or cand in blob) and looks_like_a_store(body):
                    return url, body
            time.sleep(0.3)
    return None, None


def first_match(rx, text, group=1, skip=frozenset()):
    for m in rx.finditer(text):
        val = m.group(group)
        if val and val.lower() not in skip and len(val) > 1:
            return val
    return None


def product_count(base):
    total, page = 0, 1
    while page <= 20:
        # 20MB cap: a 250-product page with rich descriptions and many variants
        # runs well past the 400KB default and must not be truncated.
        status, body = fetch(f"{base}/products.json?limit=250&page={page}",
                             max_bytes=20_000_000)
        if status != 200 or not body:
            return total if page > 1 else None
        try:
            items = json.loads(body).get("products", [])
        except json.JSONDecodeError:
            return total if page > 1 else None
        if not items:
            break
        total += len(items)
        if len(items) < 250:
            break
        page += 1
        time.sleep(0.4)
    return total


def guess_emails(domain, founder):
    host = urllib.parse.urlparse(domain).netloc.replace("www.", "")
    out = []
    if founder:
        parts = [p for p in re.split(r"\s+", founder.strip()) if p]
        if parts:
            first = parts[0].lower()
            last = parts[-1].lower() if len(parts) > 1 else ""
            out.append(f"{first}@{host}")
            if last:
                out.append(f"{first}.{last}@{host}")
                out.append(f"{first[0]}{last}@{host}")
    out.append(f"hello@{host}")
    return out


def enrich(row, delay):
    brand = row.get("brand", "").strip()
    slug = row.get("slug_guess", "").strip()
    founder = row.get("founder", "").strip()
    out = dict(row)

    # 1. Best source: the Shopify article links the store and names the guest.
    domain, home = None, None
    unreachable = False
    episode = row.get("episode_url", "").strip()
    if episode:
        domain, ep_founder, _ = store_from_episode(episode, brand)
        if ep_founder and not founder:
            founder = ep_founder
            out["founder"] = founder
            out["founder_source"] = "episode page"
        if domain:
            # Retry before giving up. A transient failure here is NOT evidence
            # that the domain is wrong, and treating it as such is how a row
            # ends up pointed at a squatter.
            status, home = fetch(domain, retries=2)
            if status != 200:
                unreachable = True
                home = None
            out["domain_source"] = "episode page link"
        time.sleep(delay)

    # 2. Fallback: guess the domain from the brand name. Only ever reached when
    #    the article gave us nothing -- never because a fetch flaked.
    if not domain:
        domain, home = resolve_domain(brand, slug)
        if domain:
            out["domain_source"] = "GUESSED from name - VERIFY"

    out["domain"] = domain or ""
    if not domain:
        out["status"] = "DOMAIN NOT FOUND"
        return out

    if unreachable and not home:
        # Keep the domain -- the article link is good evidence -- but say
        # plainly that nothing below was measured.
        out["status"] = "UNREACHABLE - retry manually"
        return out

    pages = [home]
    for path in ABOUT_PATHS:
        status, body = fetch(domain + path, timeout=12)
        if status == 200 and body:
            pages.append(body)
            out.setdefault("about_url", domain + path)
            if len(pages) >= 3:
                break
        time.sleep(0.25)

    blob = "\n".join(p for p in pages if p)

    out["instagram"] = first_match(IG_RE, blob, 1, IG_SKIP) or ""
    li = LI_RE.search(blob)
    out["linkedin"] = f"linkedin.com/{li.group(1)}/{li.group(2)}" if li else ""
    out["twitter"] = first_match(TW_RE, blob, 1, TW_SKIP) or ""

    host = urllib.parse.urlparse(domain).netloc.replace("www.", "")
    emails = sorted({e.lower() for e in EMAIL_RE.findall(blob)
                     if host.split(".")[0] in e.lower()
                     and not e.lower().endswith((".png", ".jpg", ".webp"))})
    out["emails_published"] = "; ".join(emails[:4])

    if not founder:
        m = FOUNDER_RE.search(blob)
        if m:
            founder = m.group(1)
            out["founder"] = founder
            out["founder_source"] = "guessed from site copy - VERIFY"

    out["email_guesses"] = "; ".join(guess_emails(domain, founder))

    low = blob.lower()
    out["shopify"] = "yes" if ("cdn.shopify.com" in low or "shopify" in low) else "no"
    out["yotpo"] = "YES" if any(m in low for m in YOTPO_MARKERS) else ""

    time.sleep(delay)
    n = product_count(domain)
    out["products"] = n if n is not None else ""

    if out["yotpo"]:
        out["status"] = "EXCLUDE - Yotpo"
    elif n is None:
        # Never let an uncounted catalog pass as OK. The 150-SKU floor is a hard
        # filter, and an unknown count is not a pass -- it's an unknown.
        out["status"] = "COUNT FAILED - check manually"
    elif n < 150:
        out["status"] = f"LOW SKU ({n})"
    elif out["shopify"] == "yes":
        out["status"] = f"OK ({n})"
    else:
        out["status"] = "CHECK - not obviously Shopify"
    return out


FIELDS = ["brand", "founder", "founder_source", "domain", "domain_source",
          "status", "products", "shopify", "yotpo", "instagram", "linkedin",
          "twitter", "emails_published", "email_guesses", "about_url",
          "category", "size_signal", "episode_url", "slug_guess"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    with open(args.file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[:args.limit]

    results = []
    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row.get('brand','?')} ... ", end="", flush=True)
        try:
            r = enrich(row, args.delay)
        except Exception as e:
            print(f"error: {e}")
            r = dict(row, status=f"ERROR {e}")
        results.append(r)
        print(f"{r.get('status','?')}  {r.get('domain','')}")
        time.sleep(args.delay)

    stamp = dt.date.today().isoformat()
    out_csv = f"prospecting/enriched-{stamp}.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)

    # startswith, not ==: the status now carries the SKU count, e.g. "OK (195)".
    ok = [r for r in results if (r.get("status") or "").startswith("OK")]
    with open(f"prospecting/enriched-{stamp}.md", "w", encoding="utf-8") as f:
        f.write(f"# Enriched prospects - {stamp}\n\n")
        f.write(f"{len(ok)} of {len(results)} passed the hard filters.\n\n")
        f.write("| Brand | Founder | Domain | Domain source | Products | Instagram | Published email | Best guess |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for r in sorted(ok, key=lambda x: -(x.get("products") or 0)):
            f.write(f"| {r['brand']} | {r.get('founder','')} | {r.get('domain','')} | "
                    f"{r.get('domain_source','')} | "
                    f"{r.get('products','')} | {r.get('instagram','')} | "
                    f"{r.get('emails_published','')} | "
                    f"{(r.get('email_guesses','') or '').split(';')[0]} |\n")

        guessed = [r for r in results if "GUESSED" in (r.get("domain_source") or "")]
        if guessed:
            f.write(f"\n## {len(guessed)} domains were guessed, not confirmed\n\n")
            f.write("Open each one before auditing or emailing. A guessed domain can "
                    "land on a counterfeit clone of the real store — "
                    "`avocadogreenmattress.shop` is a full WooCommerce copy of "
                    "Avocado Green Mattress.\n\n")
            for r in guessed:
                f.write(f"- {r['brand']} → {r.get('domain','')}\n")

        f.write("\n**Verify every guessed email before sending.**\n")

    print(f"\nWrote {out_csv}")
    print(f"OK: {len(ok)} / {len(results)}")


if __name__ == "__main__":
    main()
