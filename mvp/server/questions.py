"""Generate the five buyer questions for one product.

Store-agnostic. Everything comes from the product's own Shopify record -
its product_type, tags, title, price and whatever specs are stated in
body_html. Nothing is hardcoded to a category or a brand.

The five questions deliberately probe the attributes the audit tool scores
(build/attributes.py): price band, dimensions, material, durability/care and
availability. Those are the spec-shaped things buyers ask AI assistants, and
they are exactly what most catalogues fail to state.

This is a deterministic stand-in for the LLM call in PLAN.md phase 2. The
output shape - a list of five strings - is what the rest of the app consumes,
so swapping in a model call later touches only generate().
"""

import re

# ---------------------------------------------------------------- helpers


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def price_band(price):
    """Round a price up to a number a buyer would actually type."""
    try:
        n = int(float(price))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    step = 50 if n < 200 else 100 if n < 1000 else 500 if n < 3000 else 1000
    up = -(-n // step) * step
    if up == n:                      # "under 1500" would exclude a 1500 product
        up += step
    return "{:,}".format(up)


MATERIALS = [
    "travertine", "marble", "granite", "terrazzo", "rattan", "bamboo",
    "walnut", "oak", "ash wood", "teak", "larch", "suar wood", "mango wood",
    "solid wood", "plywood", "veneer", "leather", "linen", "velvet",
    "bouclé", "boucle", "cotton", "wool", "merino", "polyester", "nylon",
    "stainless steel", "steel", "aluminium", "aluminum", "brass", "copper",
    "ceramic", "porcelain", "glass", "concrete", "titanium", "silicone",
]


def find_material(raw):
    """First material named in the spec text, product type or tags."""
    hay = " ".join([
        _text(raw.get("body_html", "")),
        raw.get("product_type", "") or "",
        " ".join(raw.get("tags") or []),
    ]).lower()
    m = re.search(r"material\s*:?\s*([^.;|]{3,60})", hay)
    scope = m.group(1) if m else hay
    for mat in MATERIALS:
        if mat in scope:
            return "bouclé" if mat == "boucle" else mat
    for mat in MATERIALS:
        if mat in hay:
            return "bouclé" if mat == "boucle" else mat
    return None


def find_dimension(raw):
    """Largest plausible centimetre figure stated anywhere in the specs."""
    txt = _text(raw.get("body_html", ""))
    vals = []
    for m in re.finditer(r"(?:ø|[LWHD]\s*)(\d{2,3}(?:\.\d)?)", txt):
        vals.append(float(m.group(1)))
    for m in re.finditer(r"(\d{2,3})\s*(?:cm|CM)", txt):
        vals.append(float(m.group(1)))
    vals = [v for v in vals if 15 <= v <= 400]
    return int(max(vals)) if vals else None


# Product nouns worth recognising in a title. Longest match wins, so
# "Floor lamp Chicken Cage Medium" gives "floor lamp" rather than the last two
# words ("cage medium"), which is what a naive tail-of-title guess produces.
NOUNS = [
    "chaise longue", "lounge chair", "dining chair", "office chair",
    "dining table", "coffee table", "side table", "bedside table",
    "console table", "floor lamp", "table lamp", "pendant light",
    "wall panel", "bed frame", "chest of drawers", "tv stand",
    "sofa bed", "sofa", "couch", "armchair", "chair", "stool", "bench",
    "table", "desk", "shelf", "cabinet", "sideboard", "wardrobe",
    "mattress", "headboard", "bed", "lamp", "light", "mirror", "rug",
    "cushion", "throw", "curtain", "vase", "bowl", "tray", "sculpture",
    "panel", "mask", "ornament", "candle", "planter",
    "hiking boot", "boot", "sneaker", "trainer", "sandal", "shoe",
    "jacket", "coat", "hoodie", "sweater", "shirt", "t-shirt", "trouser",
    "legging", "sock", "base layer", "long sleeve tee", "tee", "top",
    "vest", "dress", "shorts", "hat", "cap", "glove", "scarf", "belt",
    "backpack", "rucksack", "tote", "wallet", "duffel", "bag",
    "pocket knife", "knife", "multi-tool", "axe",
    "serum", "moisturiser", "moisturizer", "cleanser", "sunscreen",
    "shampoo", "conditioner", "supplement", "powder", "capsule",
]


def noun_for(title, raw):
    """What to call the thing, in the words a buyer would use.

    Title first: a Shopify product_type is often blank or an internal label,
    whereas the title almost always contains the real noun.
    """
    t = " " + re.sub(r"[^a-zA-Z ]", " ", title).lower() + " "
    best = None
    for n in NOUNS:
        if re.search(r"\b%s(s|es)?\b" % re.escape(n), t):
            if best is None or len(n) > len(best):
                best = n
    if best:
        return best
    pt = (raw.get("product_type") or "").strip()
    if pt and len(pt) < 40:
        return pt.lower()
    for tag in (raw.get("tags") or []):
        tag = str(tag).strip()
        if tag and len(tag) < 30 and not re.match(r"^[A-Z]{2,}\d", tag):
            return tag.lower()
    words = [w for w in re.sub(r"[^a-zA-Z ]", " ", title).split() if len(w) > 2]
    return " ".join(words[-2:]).lower() if words else "product"


# Category families. `size` decides how question 2 is phrased: asking a
# footwear buyer about centimetres is as wrong as asking a sofa buyer about
# half sizes. A noun matching nothing here still produces sound questions.
_FAMILIES = [
    (r"sofa|couch|sectional|loveseat", "room", "living room", "sitting on it daily"),
    (r"chair|stool|bench|seat",        "room", "living room", "daily use"),
    (r"bed|mattress|headboard",        "room", "bedroom",     "nightly use"),
    (r"table|desk|console|stand|shelf|cabinet", "room", "living room", "daily use"),
    (r"lamp|light|sconce|pendant",     "room", "living room", "everyday use"),
    (r"rug|carpet",                    "room", "living room", "heavy foot traffic"),
    (r"bowl|vase|sculpt|panel|mask|decor|art|orna", "room", "living room", "display"),
    (r"boot|shoe|sneaker|sandal|trainer", "fit", "wide feet", "long days on your feet"),
    (r"jacket|coat|shirt|layer|hoodie|tee|top|vest|dress|short|sock|"
     r"trouser|legging|apparel|clothing|glove|hat|cap|scarf",
                                       "fit", "a slim build", "regular washing"),
    (r"knife|blade|axe|multi.?tool",   "blade", "everyday carry", "hard use"),
    (r"bag|pack|luggage|tote|wallet",  "cap",  "a 15 inch laptop", "daily commuting"),
    (r"serum|cream|cleanser|moisturi|sunscreen|shampoo",
                                       "skin", "sensitive skin", "daily use"),
]

# Nouns that read as plural, so "shoes fit" not "shoes fits".
_PLURAL = re.compile(r"(?<!\bgla)(?<!\bdre)s$|ware$|wear$|gear$", re.I)


def _is_plural(noun):
    return bool(_PLURAL.search(noun.strip().split()[-1]))


def _agree(noun, singular, plural):
    return plural if _is_plural(noun) else singular


def _family(noun):
    for pat, kind, ctx, wear in _FAMILIES:
        if re.search(pat, noun):
            return kind, ctx, wear
    return "room", "your home", "daily use"


def _a(noun):
    """'a sofa', 'an oak table', but never 'a shoes'."""
    if _is_plural(noun):
        return noun
    return ("an " if noun[:1] in "aeiou" else "a ") + noun


def _place(ctx, small=False):
    """'a living room' / 'a small living room', but 'your home' takes no
    article - 'for a your home' was the bug this exists to prevent."""
    if ctx.startswith(("your ", "a ", "an ", "the ")):
        return ctx
    return ("a small " if small else "a ") + ctx


def generate(title, price, raw, currency="€", region="Europe"):
    """Return exactly five buyer questions for this product."""
    raw = raw or {}
    noun = noun_for(title, raw)
    mat = find_material(raw)
    dim = find_dimension(raw)
    band = price_band(price)
    kind, ctx, wear = _family(noun)
    matp = (mat + " ") if mat else ""
    phrase = matp + noun                       # "solid wood sofa" / "shoes"

    q1 = ("best %s under %s%s" % (phrase, currency, band)) if band \
        else ("best %s to buy" % phrase)

    if kind in ("fit", "skin"):
        q2 = "%s %s %s" % (noun, _agree(noun, "that suits", "that suit"), ctx)
    elif kind == "blade":
        q2 = ("%s with a blade around %d cm" % (noun, dim)) if dim \
            else ("%s that is legal to carry every day" % noun)
    elif kind == "cap":
        q2 = "%s %s %s" % (noun, _agree(noun, "that fits", "that fit"), ctx)
    elif dim:
        q2 = "%s around %d cm for %s" % (noun, dim, _place(ctx))
    else:
        q2 = "%s for %s" % (noun, _place(ctx, small=True))

    if kind == "skin":
        q3 = "%s %s good for %s" % (
            _a(phrase), _agree(noun, "that is", "that are"), ctx)
    elif mat:
        q3 = "how durable %s %s for %s" % (
            _agree(noun, "is", "are"), _a(phrase), wear)
    else:
        q3 = "%s %s up to %s" % (
            noun, _agree(noun, "that holds", "that hold"), wear)

    # Consumables are used up, not maintained - "how to clean a serum" is
    # the kind of line that makes a prospect stop trusting the whole report.
    if kind == "skin":
        q4 = "how to use %s in a daily routine" % _a(phrase)
    else:
        q4 = "how to clean and care for %s" % _a(phrase)
    # "delivered in Europe" is wrong for a US store.
    q5 = ("%s delivered in %s" % (phrase, region)) if region \
        else ("where to buy %s online" % phrase)

    out = [re.sub(r"\s+", " ", q).strip() for q in (q1, q2, q3, q4, q5)]
    return out


def confidence(raw):
    """How much real spec data backed the questions. Shown to the user so a
    thin result reads as thin data rather than as a broken generator."""
    raw = raw or {}
    have = {
        "material":   find_material(raw) is not None,
        "dimensions": find_dimension(raw) is not None,
        "type":       bool((raw.get("product_type") or "").strip()
                           or (raw.get("tags") or [])),
        "description": len(_text(raw.get("body_html", ""))) > 120,
    }
    return have, sum(have.values())
