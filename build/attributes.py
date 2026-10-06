"""
Category attribute tables.

This is the asset. Everything else in the tool is plumbing.

Each attribute is something a real buyer query asks for. We know these matter
because spec-shaped queries containing them returned ranked products in the
3 Aug test, while taste-shaped queries returned only brand names.

`weight` is how much the attribute counts toward the score. Higher = it showed
up in more of the queries that actually returned products.

To add a category: copy the structure, derive the attributes from queries you
have actually tested. Do not invent them from imagination -- the whole point is
that the list is evidence-backed.
"""

import re


def _rx(*patterns):
    """Compile patterns case-insensitively. Kept tiny so the tables stay readable."""
    return [re.compile(p, re.I) for p in patterns]


# Product families within a category. An attribute is only scored against the
# families it applies to -- marking a decorative bowl down for not stating how
# many people it seats is wrong, drags the catalog score down artificially, and
# makes the report easy to dismiss.
#
# Inferred from title/tags/product_type because product_type is empty on most
# real Shopify catalogs (84 of 86 on molivings.com).
FAMILY_PATTERNS = {
    "seating": _rx(
        r"\b(sofa|couch|settee|sectional|armchair|arm chair|lounge chair|"
        r"dining chair|chair|stool|bench|ottoman|pouf|daybed)\b"
    ),
    "table": _rx(
        r"\b(dining table|coffee table|side table|console|desk|nightstand|"
        r"bedside table|table)\b"
    ),
    "bed": _rx(r"\b(bed|headboard|bed frame|mattress)\b"),
    "storage": _rx(
        r"\b(sideboard|cabinet|dresser|drawer|wardrobe|shelf|shelving|"
        r"bookcase|credenza|chest)\b"
    ),
    "lighting": _rx(r"\b(lamp|pendant|chandelier|sconce|light|lantern)\b"),
    "textile": _rx(r"\b(rug|carpet|cushion|pillow|throw|curtain|blanket|runner)\b"),
    "decor": _rx(
        r"\b(bowl|vase|decoration|decor|sculpture|statue|tray|mirror|"
        r"carved|ornament|candle|basket|frame|artwork|figurine)\b"
    ),
}

# Order matters: first match wins, so more specific families come first.
FAMILY_ORDER = ["seating", "bed", "storage", "table", "lighting", "textile", "decor"]


def infer_family(title, tags=(), product_type=""):
    """
    Best-effort product family. Returns a family name or 'unknown'.

    Deliberately conservative: 'unknown' scores against the universal
    attributes only, so a misclassification never invents a false gap.
    """
    haystack = " ".join(
        [str(product_type or ""), str(title or "")] + [str(t) for t in (tags or [])]
    )
    for family in FAMILY_ORDER:
        for pattern in FAMILY_PATTERNS[family]:
            if pattern.search(haystack):
                return family
    return "unknown"


ALL_FAMILIES = tuple(FAMILY_ORDER) + ("unknown",)


# Attribute names as they commonly appear in Shopify metafields / spec tables.
# Used to decide 'structured' vs 'prose' -- see extract.py.
FURNITURE = [
    {
        "key": "dimensions",
        "label": "Dimensions (L/W/H in cm)",
        "weight": 3,
        "applies_to": "*",
        "query": "extendable dining table that seats 10 when open",
        "patterns": _rx(
            r"\b[LWHD]\s*[:=]?\s*\d{2,3}\s*(?:cm|mm)?\s*[x×]\s*",
            r"\b\d{2,3}\s*[x×]\s*\d{2,3}\s*[x×]\s*\d{2,3}\b",
            r"\b(?:length|width|height|depth)\b[^.]{0,20}\b\d{2,3}\s*(?:cm|mm)\b",
        ),
        "schema_keys": ("dimensions", "size", "measurements", "width", "height", "depth", "length"),
    },
    {
        "key": "seat_count",
        "label": "Seat / capacity count",
        "weight": 3,
        "applies_to": ("seating", "table"),
        "query": "sofa that seats 4, dining table that seats 10",
        "patterns": _rx(
            r"\b\d\s*[-\s]?seater\b",
            r"\bseats?\s+(?:up\s+to\s+)?\d+\b",
            r"\bcapacity\b[^.]{0,15}\b\d+\s*(?:people|persons|seats)\b",
        ),
        "schema_keys": ("seats", "seating", "seat count", "capacity"),
    },
    {
        "key": "wood_species",
        "label": "Wood species named",
        "weight": 3,
        "applies_to": "*",
        "query": "solid oak bed frame, outdoor teak table",
        "patterns": _rx(
            r"\b(oak|teak|walnut|suar|mango wood|acacia|pine|ash wood|beech|birch|"
            r"mahogany|rosewood|cherry wood|maple|rattan|bamboo|cedar)\b"
        ),
        "schema_keys": ("wood", "wood type", "species", "timber", "material"),
    },
    {
        "key": "solid_vs_engineered",
        "label": "Solid vs. veneer / MDF stated",
        "weight": 3,
        "applies_to": ("seating", "table", "bed", "storage", "decor", "lighting"),
        "query": "solid oak, no particleboard",
        "patterns": _rx(
            r"\bsolid\s+(?:wood|oak|teak|walnut|acacia|pine|mango)\b",
            r"\b(veneer|mdf|particleboard|chipboard|plywood|engineered wood)\b",
        ),
        "schema_keys": ("construction", "material", "wood type"),
    },
    {
        "key": "cover_removable",
        "label": "Cover removable / washable",
        "weight": 3,
        "applies_to": ("seating", "textile"),
        "query": "sofa with removable washable covers",
        "patterns": _rx(
            r"\bremovable\s+(?:cover|covers|cushion covers|upholstery)\b",
            r"\b(?:machine[- ]?wash(?:able)?|dry[- ]?clean|washable\s+cover)\b",
            r"\bslip[- ]?cover(?:ed|s)?\b",
        ),
        "schema_keys": ("cover", "removable cover", "washable", "care"),
    },
    {
        "key": "fabric_durability",
        "label": "Fabric durability rating",
        "weight": 2,
        "applies_to": ("seating", "textile"),
        "query": "fabric rated over 40,000 Martindale",
        "patterns": _rx(
            r"\bmartindale\b",
            r"\b(?:rub|abrasion)\s+(?:test|count|resistance)\b",
            r"\b\d{2},?\d{3}\s*(?:rubs|cycles)\b",
            r"\bwyzenbeek\b",
        ),
        "schema_keys": ("martindale", "durability", "abrasion", "rub count"),
    },
    {
        "key": "upholstery_material",
        "label": "Upholstery fabric composition",
        "weight": 2,
        "applies_to": ("seating", "textile"),
        "query": "linen sofa, boucle armchair",
        "patterns": _rx(
            r"\b\d{1,3}\s*%\s*(?:polyester|linen|cotton|wool|viscose|acrylic|nylon)\b",
            r"\b(bou?cl[ée]|chenille|velvet|full[- ]grain leather|top[- ]grain leather|"
            r"aniline leather|performance fabric)\b",
        ),
        "schema_keys": ("fabric", "upholstery", "material", "composition"),
    },
    {
        "key": "care_maintenance",
        "label": "Care & maintenance instructions",
        "weight": 2,
        "applies_to": "*",
        "query": "outdoor teak that doesn't need re-oiling",
        "patterns": _rx(
            r"\bcare\s+(?:instructions|guide|advice)\b",
            r"\b(?:re[- ]?oil|oiling|wax(?:ing)?|reseal|sealant|treat(?:ment)?)\b[^.]{0,40}"
            r"\b(?:year|month|annual|regular)\w*\b",
            r"\bwipe\s+(?:clean|with)\b",
            r"\bmaintenance\b",
        ),
        "schema_keys": ("care", "maintenance", "care instructions", "cleaning"),
    },
    {
        "key": "indoor_outdoor",
        "label": "Indoor / outdoor suitability",
        "weight": 2,
        "applies_to": "*",
        "query": "outdoor teak table",
        "patterns": _rx(
            r"\b(?:suitable for |for )?outdoor(?:s| use)?\b",
            r"\bindoor(?:s| use)?\s+(?:only|use)\b",
            r"\b(?:weather|uv|water)[- ]resistant\b",
            r"\ball[- ]weather\b",
        ),
        "schema_keys": ("indoor/outdoor", "use", "suitability", "environment"),
    },
    {
        "key": "assembly",
        "label": "Assembly requirement",
        "weight": 1,
        "applies_to": ("seating", "table", "bed", "storage"),
        "query": "flat pack vs. fully assembled",
        "patterns": _rx(
            r"\b(?:self[- ]|easy )?assembl(?:y|ed|e)\b",
            r"\bflat[- ]?pack(?:ed)?\b",
            r"\bready\s+to\s+use\b",
            r"\bno\s+assembly\s+required\b",
        ),
        "schema_keys": ("assembly", "assembly required", "flatpack"),
    },
    {
        "key": "weight_capacity",
        "label": "Weight / load capacity",
        "weight": 1,
        "applies_to": ("seating", "table", "bed", "storage"),
        "query": "bed frame that supports 200kg",
        "patterns": _rx(
            r"\b(?:max(?:imum)?\s+)?(?:load|weight)\s+(?:capacity|limit|bearing)\b",
            r"\bsupports?\s+up\s+to\s+\d+\s*kg\b",
            r"\bholds?\s+up\s+to\s+\d+\s*kg\b",
        ),
        "schema_keys": ("weight capacity", "max load", "load capacity"),
    },
]


CATEGORIES = {
    "furniture": FURNITURE,
}


# Schema.org fields that AI shopping surfaces read directly. Table stakes --
# scored separately from the query attributes because they are a different
# kind of problem (a theme/plumbing fix, not a content fix).
SCHEMA_FIELDS = [
    ("name", "Product name", 1),
    ("brand", "Brand", 2),
    ("sku", "SKU", 1),
    ("gtin", "GTIN / barcode", 2),
    ("mpn", "MPN (manufacturer part no.)", 1),
    ("offers.price", "Price", 2),
    ("offers.availability", "Availability", 2),
    ("description", "Description", 1),
    ("image", "Image", 1),
    ("aggregateRating", "Aggregate rating", 2),
    ("review", "Review text in schema", 2),
]


# Crawlers that matter for AI shopping surfaces.
AI_CRAWLERS = [
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "PerplexityBot",
    "Perplexity-User",
    "Google-Extended",
    "Bingbot",
    "Amazonbot",
    "Applebot-Extended",
    "meta-externalagent",
]


def get_category(name):
    """Look up an attribute table by category name."""
    try:
        return CATEGORIES[name]
    except KeyError:
        known = ", ".join(sorted(CATEGORIES))
        raise SystemExit("Unknown category '%s'. Known categories: %s" % (name, known))
