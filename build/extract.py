"""
Fetching and parsing. Standard library only.

Important: we fetch RAW HTML and never execute JavaScript. That is deliberate.
It approximates what an AI crawler actually receives. If a brand's specs or
reviews only appear after JS runs, they are invisible here -- which is exactly
the finding we want to surface, not a bug to fix.
"""

import gzip
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

USER_AGENT = (
    "AEO-Audit/0.1 (catalog visibility research; contact via store owner)"
)

TIMEOUT = 25


class FetchError(Exception):
    pass


def fetch(url, retries=2, delay=0.5):
    """GET a URL and return decoded text. Retries transient failures once or twice."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip",
                    "Accept-Language": "en",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
    raise FetchError("%s -> %s" % (url, last))


# --------------------------------------------------------------------------
# HTML parsing
# --------------------------------------------------------------------------

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class PageParser(HTMLParser):
    """Single pass: collect JSON-LD blocks and visible text."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.jsonld_blocks = []
        self._text = []
        self._skip_depth = 0
        self._in_jsonld = False
        self._jsonld_buf = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            script_type = (attrs.get("type") or "").lower()
            if "ld+json" in script_type:
                self._in_jsonld = True
                self._jsonld_buf = []
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._jsonld_buf))
            self._in_jsonld = False
            self._jsonld_buf = []
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        elif self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    @property
    def text(self):
        return re.sub(r"\s+", " ", " ".join(self._text))


def parse_page(html_text):
    """Return (visible_text, [parsed json-ld objects])."""
    parser = PageParser()
    try:
        parser.feed(html_text)
    except Exception:
        # Malformed markup is common; keep whatever we got rather than failing
        # the whole product.
        pass

    objects = []
    for block in parser.jsonld_blocks:
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except ValueError:
            continue
        objects.extend(_flatten_jsonld(data))
    return parser.text, objects


def _flatten_jsonld(data):
    """JSON-LD arrives as objects, lists, or @graph wrappers. Flatten to a list."""
    out = []
    if isinstance(data, list):
        for item in data:
            out.extend(_flatten_jsonld(item))
    elif isinstance(data, dict):
        if "@graph" in data:
            out.extend(_flatten_jsonld(data["@graph"]))
        else:
            out.append(data)
            for value in data.values():
                if isinstance(value, (dict, list)):
                    out.extend(_flatten_jsonld(value))
    return out


def find_product_schema(objects):
    """Return the first JSON-LD object that is a Product, or None."""
    for obj in objects:
        types = obj.get("@type")
        if isinstance(types, list):
            types = [str(t) for t in types]
        else:
            types = [str(types)] if types else []
        if any(t.lower() in ("product", "productgroup") for t in types):
            return obj
    return None


def strip_html(fragment):
    """Turn an HTML fragment (e.g. Shopify body_html) into plain text."""
    if not fragment:
        return ""
    parser = PageParser()
    try:
        parser.feed(fragment)
    except Exception:
        pass
    return parser.text


# --------------------------------------------------------------------------
# Shopify catalog enumeration
# --------------------------------------------------------------------------

def normalise_store_url(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    return "%s://%s" % (parts.scheme, parts.netloc)


def enumerate_shopify(base_url, limit=None, delay=0.5, log=print):
    """
    Page through /products.json. Returns a list of product dicts.

    This endpoint is public on virtually every Shopify store. If it 404s the
    store is either not Shopify or has it disabled, and we fall back to the
    sitemap.
    """
    products = []
    page = 1
    while True:
        url = "%s/products.json?limit=250&page=%d" % (base_url, page)
        try:
            payload = json.loads(fetch(url, delay=delay))
        except (FetchError, ValueError) as exc:
            if page == 1:
                raise FetchError("products.json unavailable: %s" % exc)
            break
        batch = payload.get("products") or []
        if not batch:
            break
        products.extend(batch)
        log("  fetched page %d (%d products, %d total)" % (page, len(batch), len(products)))
        if limit and len(products) >= limit:
            break
        page += 1
        time.sleep(delay)
    return products[:limit] if limit else products


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------

def analyse_robots(base_url, crawlers):
    """
    Check whether named AI crawlers are permitted.

    Note: as of Aug 2026 Shopify ships an agent-open default that allows all
    user-agents and advertises UCP/MCP endpoints. A clean result here is
    increasingly the norm for Shopify stores and is NOT a selling point.
    """
    result = {
        "fetched": False,
        "allows": {},
        "wildcard_disallow_all": False,
        "mentions_ucp_mcp": False,
        "raw_excerpt": "",
    }
    try:
        body = fetch("%s/robots.txt" % base_url)
    except FetchError:
        return result

    result["fetched"] = True
    result["raw_excerpt"] = body[:1500]
    result["mentions_ucp_mcp"] = bool(re.search(r"ucp|/mcp|agents\.md", body, re.I))

    groups = _parse_robots_groups(body)
    wildcard = groups.get("*", [])
    result["wildcard_disallow_all"] = any(
        rule == ("disallow", "/") for rule in wildcard
    )

    for bot in crawlers:
        rules = groups.get(bot.lower())
        if rules is None:
            # No specific group -> falls back to the wildcard group.
            blocked = result["wildcard_disallow_all"]
            result["allows"][bot] = {
                "allowed": not blocked,
                "explicit": False,
            }
        else:
            blocked = any(rule == ("disallow", "/") for rule in rules)
            result["allows"][bot] = {
                "allowed": not blocked,
                "explicit": True,
            }
    return result


def _parse_robots_groups(body):
    """Map user-agent (lowercased) -> list of (directive, path) tuples."""
    groups = {}
    current = []
    expecting_agent = True
    for line in body.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if not expecting_agent:
                current = []
                expecting_agent = True
            agent = value.lower()
            groups.setdefault(agent, [])
            current.append(agent)
        elif field in ("allow", "disallow"):
            expecting_agent = False
            for agent in current:
                groups[agent].append((field, value))
    return groups
