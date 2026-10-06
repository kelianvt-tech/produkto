"""Small text helpers shared by matching and scoring."""

import re
from functools import lru_cache

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

STOP = {"the", "and", "with", "for", "in", "of", "a", "an", "by", "set",
        "new", "size", "color", "colour", "men", "mens", "women", "womens",
        "unisex", "kids"}


def norm(s):
    """'M&O Living' -> 'moliving' - for comparing names loosely.

    Memoised: the dashboard compares the same few hundred names millions of
    times per page (6.8M calls, ~7 of 9 seconds, on 2026-09-25)."""
    return _norm(s) if isinstance(s, str) else _NON_ALNUM.sub("", (s or "").lower() if s else "")


@lru_cache(maxsize=65536)
def _norm(s):
    return _NON_ALNUM.sub("", s.lower())


def words(s):
    """Meaningful lowercase words, minus filler like 'the' and 'with'."""
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) > 1 and w not in STOP]


def core_title(title):
    """'Men's Tree Runner - Blizzard (Blizzard Sole)' -> "Men's Tree Runner".

    Shopify titles often carry the colour or variant after a dash or in
    brackets; ChatGPT almost never repeats that part.
    """
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title or "")
    t = re.split(r"\s[-\u2013\u2014|/]\s", t)[0]
    return t.strip() or (title or "")
