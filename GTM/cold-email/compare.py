"""One niche batch of leads -> ONE ChatGPT question (via Apify) -> one competitor
product used in every email of the batch. Each brand's own best-seller in the
niche is still named in its email.

Kelian prepares each lead batch so it is all one niche (2026-10-02).

Usage:  python3 compare.py <leads.csv> <niche> [domain ...]
  leads.csv  any pull-leads CSV (needs first_name, organization_name,
             organization_primary_domain, email)
  niche      a key in NICHES below
  domain     optional: only these domains (for tests)

Writes comparisons-<niche>-<date>.csv next to this file: one row per brand,
with the question, the raw answer, the comparison line, a flag, and the
finished first email. Only rows flagged `ok` are meant to be sent.
"""
import csv, datetime, html, json, os, re, subprocess, sys

APP = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app"
sys.path.insert(0, APP)
for line in open(os.path.join(APP, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip("\"'"))
START = os.getcwd()
os.chdir(APP)
import apify_answers  # noqa: E402

NICHE_NOUN = ""
HERE = os.path.dirname(os.path.abspath(__file__))

# One buyer question per niche. {price} is filled from the brand's own best-seller,
# so ChatGPT compares like with like. Must stay one line: Apify splits on newlines.
NICHES = {
    "candles": dict(
        noun="candle", match=r"\bcandles?\b",
        exclude=r"match(es)?\b|wick trimmer|snuffer|holder|lid\b|dish|tray|diffuser|room spray|lighter|warmer",
        question="What's the best scented candle to buy online for around ${price}?"),
    "running-shoes": dict(
        noun="running shoe", match=r"\brunning\b|\brun shoe|road shoe|trail shoe",
        exclude=r"slip[- ]?on|sandal|slide|loafer|boot|lounger|mule|clog|casual|lifestyle|kids?\b|toddler|sock|insole|lace",
        question="What's the best running shoe for everyday training for around ${price}?"),
}
FORMAT = (" Recommend three specific products. Reply ONLY with three lines in this format: "
          "Brand | Exact product name")
SKIP = re.compile(r"gift ?card|sample|bundle|kit|set of|e-?gift|subscription|membership|"
                  r"donation|shipping|protection|insurance|deposit|refill|sock|lace", re.I)


def get(url):
    return subprocess.run(["curl", "-sL", "--max-time", "20", "-A", "Mozilla/5.0", url],
                          capture_output=True).stdout.decode("utf-8", "ignore")


def best_seller(domain, match, exclude):
    """First real product on the store's own best-selling sort, else first in products.json."""
    page = get("https://%s/collections/all?sort_by=best-selling" % domain)
    handles = []
    for h in re.findall(r'/products/([a-z0-9][a-z0-9\-]+)', page):
        if h not in handles:
            handles.append(h)
    source = "best-selling sort"
    if not handles:
        try:
            handles = [p["handle"] for p in json.loads(get("https://%s/products.json?limit=50" % domain))["products"]]
            source = "products.json (not a best-seller list)"
        except Exception:
            return None
    for h in handles[:30]:
        try:
            p = json.loads(get("https://%s/products/%s.js" % (domain, h)))
        except Exception:
            continue
        title = html.unescape(p.get("title", ""))
        price = (p.get("price") or 0) / 100
        # Must be the niche's product on its title, type or tags, and not an accessory
        # or a look-alike (a slip-on "Runner" is not a running shoe).
        tags = p.get("tags") or []
        about = " ".join([title, p.get("type") or ""] + (tags if isinstance(tags, list) else [tags]))
        if not re.search(match, about, re.I) or re.search(exclude, title + " " + (p.get("type") or ""), re.I):
            continue
        if price < 5 or SKIP.search(title) or SKIP.search(p.get("type") or ""):
            continue
        return dict(title=clean_name(title, NICHE_NOUN), raw_title=title, price=price, url="https://%s/products/%s" % (domain, h), source=source)
    return None


def clean_name(title, noun):
    """Store title -> how a person would write it in an email.
    'Sabrina • Patchouli & Bergamot Tall Candle' -> 'Sabrina candle'
    'HARD WOOD' -> 'Hard Wood candle'
    "Men's Runner NZ Slip On - Mushroom (Mushroom Sole)" -> 'Runner NZ Slip On shoe'
    """
    t = html.unescape(title)
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", t)                    # (Mushroom Sole), [2-pack]
    t = re.split(r"\s+[•|–—-]\s+|\s*[•|]\s*|,\s", t)[0]        # drop variant / scent after a separator
    t = re.sub(r"^(men'?s|women'?s|unisex|kids'?)\s+", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -–")
    if t.isupper() and len(t) > 3:                                # HARD WOOD -> Hard Wood
        t = " ".join(w if len(w) <= 3 and w.isalpha() and w in ("NZ", "USA", "NYC") else w.capitalize()
                     for w in t.split())
    last = noun.split()[-1]
    if not re.search(r"\b%ss?\b" % last, t, re.I):                # 'Rattan' -> 'Rattan candle'
        t = "%s %s" % (t, last)
    return t


def squash(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def picks(text):
    out = []
    for line in text.replace("*", "").splitlines():
        m = re.match(r"\s*(?:\d+[.)]\s*)?([^|]{2,60}?)\s*\|\s*([^|]{3,120})", line)
        if m:
            out.append((m[1].strip(), m[2].strip(" .[]")))
    return out


def first_email(first, product, noun, q, cb, cp):
    return (
        "Hi %s,\n\n"
        "I asked ChatGPT \"%s\" today. One of the products it recommended was %s, made by %s, another brand in your category.\n\n"
        "I thought you'd want to see how AI picks between products like your %s.\n\n"
        "I run Produkto. It shows which of your products different AI models "
        "recommend, for which buyer questions, across your whole catalog.\n\n"
        "Would you be open to a 15-20-minute demo?\n\nKelian"
    ) % (first, q, cp, cb, product)


def main():
    src, niche, only = os.path.join(START, sys.argv[1]), sys.argv[2], set(sys.argv[3:])
    spec = NICHES[niche]
    global NICHE_NOUN
    NICHE_NOUN = spec["noun"]
    leads = [r for r in csv.DictReader(open(src, encoding="utf-8-sig"))
             if not only or r["organization_primary_domain"] in only]

    # 1. Each brand's own best-seller in the niche (named in their email).
    rows = []
    for r in leads:
        p = best_seller(r["organization_primary_domain"], spec["match"], spec["exclude"])
        rows.append((r, p))
        print(r["organization_primary_domain"], "->", p and p["title"], flush=True)
    prices = sorted(p["price"] for _, p in rows if p)
    if not prices:
        sys.exit("No brand in this file has a %s product. Nothing asked." % spec["noun"])

    # 2. ONE question for the whole batch, at the batch's typical (median) price.
    price = prices[len(prices) // 2]
    q = spec["question"].format(price=round(price))
    print("Asking ChatGPT once for the batch:", q, flush=True)
    text = (apify_answers.ask_batch([q + FORMAT], engine="chatgpt", timeout=1500).get(q + FORMAT) or ("",))[0]
    found = picks(text)
    if not found:
        sys.exit("ChatGPT's answer couldn't be read, nothing written. Raw answer:\n" + text[:600])
    named = {squash(b)[:6] for b, _ in found}

    # 3. One competitor product for every email: the first pick that isn't a brand in this batch.
    batch_keys = {k for r, _ in rows for k in (squash(r["organization_primary_domain"].split(".")[0])[:6],
                                                squash(r["organization_name"])[:6])}
    rivals = [(b, c) for b, c in found if squash(b)[:6] not in batch_keys]
    if not rivals:
        sys.exit("Every brand ChatGPT named is in this batch; no competitor to use.")
    cb, cp = rivals[0]
    print("Competitor for the batch: %s from %s" % (cp, cb), flush=True)

    today = datetime.date.today().isoformat()
    out = []
    for r, p in rows:
        d = r["organization_primary_domain"]
        own = {squash(d.split(".")[0])[:6], squash(r["organization_name"])[:6]}
        if not p:
            flag = "drop: no %s product found (or not a Shopify store)" % spec["noun"]
        elif own & named:
            flag = "drop: AI already recommends them"
        else:
            flag = "ok"
        out.append({
            "send_date": "", "captured": today, "brand": r["organization_name"], "domain": d,
            "founder_first_name": r["first_name"], "email": r["email"], "niche": niche,
            "hero_product": p["title"] if p else "", "hero_raw_title": p["raw_title"] if p else "",
            "hero_price": ("$%.0f" % p["price"]) if p else "",
            "hero_url": p["url"] if p else "", "hero_source": p["source"] if p else "",
            "buyer_question": q, "ai_engine": "chatgpt (apify)",
            "competitor_brand": cb, "competitor_product": cp,
            "comparison_line": "ChatGPT recommended the %s from %s" % (cp, cb),
            "flag": flag, "raw_answer": text[:600],
            "email_1": first_email(r["first_name"], p["title"], spec["noun"], q, cb, cp) if flag == "ok" else "",
        })
    path = os.path.join(HERE, "comparisons-%s-%s.csv" % (niche, today))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print("wrote", path)
    for o in out:
        print(o["flag"], "|", o["brand"], "|", o["hero_product"], o["hero_price"])


if __name__ == "__main__":
    main()
