"""Serve the real onboarding UI with live data.

The 7-step onboarding in ../onboarding.html is the design. It was built as a
published Artifact, which means it can never fetch anything: an Artifact's CSP
blocks every outbound request, so its catalogue, brand hub and questions are
all hardcoded to M&O Living no matter what URL a user types.

This module reads that same file and swaps the hardcoded blocks for whatever
the server actually read from the store. The design, CSS and step machine are
untouched, so any styling the design session does to onboarding.html flows
through here automatically - there is no second copy to keep in sync.
"""

import json
import os
import re

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "onboarding.html")


def _swap_block(src, start_marker, end_marker, replacement):
    """Replace from start_marker to the first end_marker after it."""
    i = src.find(start_marker)
    if i == -1:
        return src
    j = src.find(end_marker, i + len(start_marker))
    if j == -1:
        return src
    return src[:i] + replacement + src[j + len(end_marker):]


def _js(value):
    """JSON safe to embed inside a <script> block."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render(domain, brand_info, products, questions_for):
    """Return the onboarding page filled with this store's real data.

    products      - rows from store.list_products()
    questions_for - callable(row) -> list of five strings
    """
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    # ---- product grid ------------------------------------------------
    # The artifact embeds base64 thumbnails because its CSP blocks
    # cdn.shopify.com. Served from localhost there is no such restriction, so
    # the store's own image URLs are used directly.
    sym0 = brand_info.get("symbol") or "€"
    grid = [[r["title"], (sym0 + r["price"]) if r["price"] else "",
             r["image"] or ""] for r in products]
    html = _swap_block(html, "  var products = [", "\n  ];",
                       "  var products = " + _js(grid) + ";")

    # ---- per-product buyer questions ---------------------------------
    qmap = {r["title"]: questions_for(r) for r in products}
    html = _swap_block(html, "  var QUESTIONS = {", "\n  };",
                       "  var QUESTIONS = " + _js(qmap) + ";")

    # ---- brand hub ---------------------------------------------------
    # Exact-line replace, NOT _swap_block: an end marker of ";" matches the
    # next semicolon anywhere in the file, which silently swallowed the
    # addAlias click handler that follows and left a dangling "});" - a syntax
    # error that killed the whole script and rendered an empty page.
    aliases = brand_info.get("aliases") or []
    old_aliases = '["M&O Creations", "MO Living", "molivings"].forEach(addAlias);'
    html = html.replace(old_aliases, _js(aliases) + ".forEach(addAlias);")

    desc = brand_info.get("description") or ""
    if not desc:
        desc = ("This store publishes no meta description, so we left this "
                "blank rather than writing one for you.")
    html = _swap_block(html, '<textarea id="bdesc" rows="5" spellcheck="false">',
                       "</textarea>",
                       '<textarea id="bdesc" rows="5" spellcheck="false">'
                       + _esc(desc) + "</textarea>")
    html = _swap_block(html, '<textarea id="bdesc2" rows="12" spellcheck="false">',
                       "</textarea>",
                       '<textarea id="bdesc2" rows="12" spellcheck="false">'
                       + _esc(desc) + "</textarea>")

    # ---- key features -------------------------------------------------
    # Derived from the catalogue, so every line is checkable against the
    # store's own feed. The artifact shipped M&O's marketing copy here
    # ("Barcelona showroom for in-person product discovery"), which is simply
    # false for anyone else.
    html = _swap_block(html, "  [\n    \"Contemporary sofas", "].forEach(addFeat);",
                       "  " + _js(_features(brand_info, products))
                       + ".forEach(addFeat);")

    # ---- persona ------------------------------------------------------
    # The brand's OWN words about who it sells to, crawled from its content
    # pages. A product feed says nothing about who buys, but most brands state
    # it outright somewhere on the site - Clubhouse Skin says it in
    # /pages/founding-letter, which no guessed URL would have found.
    # Where a site never says, both fields stay empty and the placeholder asks
    # the merchant rather than inventing an answer.
    pname = brand_info.get("persona_name") or ""
    html = re.sub(
        r'<input id="pname" type="text" value="[^"]*"',
        '<input id="pname" type="text" value="%s" '
        'placeholder="e.g. the buyer you most want to win"' % _esc(pname), html)
    pdesc = brand_info.get("persona_desc") or ""
    html = _swap_block(
        html, '<textarea id="pdesc" rows="12" spellcheck="false">', "</textarea>",
        '<textarea id="pdesc" rows="12" spellcheck="false" '
        'placeholder="This store never says who it is for. Describe your buyer '
        'in your own words - what they are choosing between, what they worry '
        'about, and the specifics they search on.">%s</textarea>' % _esc(pdesc))
    html = re.sub(r'<input id="page" type="text" value="[^"]*"',
                  '<input id="page" type="text" value="" placeholder="e.g. 28-55"',
                  html)

    n = len(products)
    variants = sum(r["variants"] for r in products)
    name = brand_info.get("name") or domain

    # ---- catalogue stats ----------------------------------------------
    sym = brand_info.get("symbol") or "€"
    cur = brand_info.get("currency") or "—"
    prices = sorted(int(float(r["price"])) for r in products if r["price"])
    prange = ("%s%s &ndash; %s%s" % (sym, "{:,}".format(prices[0]),
                                     sym, "{:,}".format(prices[-1]))
              if prices else "&mdash;")
    html = re.sub(
        r'<div><dt>Products</dt><dd>[^<]*</dd></div>\s*'
        r'<div><dt>Variants</dt><dd>[^<]*</dd></div>\s*'
        r'<div><dt>Price range</dt><dd>[^<]*</dd></div>\s*'
        r'<div><dt>Currency</dt><dd>[^<]*</dd></div>',
        '<div><dt>Products</dt><dd>%d</dd></div>'
        '<div><dt>Variants</dt><dd>%s</dd></div>'
        '<div><dt>Price range</dt><dd>%s</dd></div>'
        '<div><dt>Currency</dt><dd>%s</dd></div>'
        % (n, "{:,}".format(variants), prange, _esc(cur)), html)

    html = html.replace("Filled in from molivings.com",
                        "Filled in from " + _esc(domain))
    html = re.sub(r"Read <b>\d+ products</b> from [^<]+ in [\d.]+ seconds\.",
                  "Read <b>%d products</b> (%s variants) from %s."
                  % (n, "{:,}".format(variants), _esc(domain)), html)
    html = re.sub(
        r'(<div class="sum-row"><span class="k">Store</span><span class="v">)'
        r'[^<]*<span class="mono">[^<]*</span>',
        r'\g<1>%s &middot; <span class="mono">%s</span>'
        % (_esc(name), _esc(domain)), html)

    # ---- step 1 -------------------------------------------------------
    html = html.replace(
        '<input id="csite" type="text" placeholder="yourstore.com" spellcheck="false">',
        '<input id="csite" type="text" value="%s" spellcheck="false">' % _esc(domain))
    html = html.replace(
        '<input id="cname" type="text" placeholder="Your brand name" spellcheck="false">',
        '<input id="cname" type="text" value="%s" placeholder="Your brand name" '
        'spellcheck="false">' % _esc(name))

    # Target market and question language were hardcoded to EU / English (UK).
    # Both come from the shop's own country now, so a US store does not open
    # on a European default.
    country = (brand_info.get("country") or "").upper()
    market = {"ES": "🇪🇸 Spain", "GB": "🇬🇧 United Kingdom",
              "US": "🇺🇸 United States"}.get(country)
    if not market:
        market = ("🇪🇺 European Union" if brand_info.get("region") == "Europe"
                  else "🇺🇸 United States" if country == "US" else None)
    if market:
        html = re.sub(r'<option selected>🇪🇺 European Union</option>',
                      '<option>🇪🇺 European Union</option>', html)
        html = html.replace("<option>%s</option>" % market,
                            "<option selected>%s</option>" % market, 1)
    if country == "US":
        html = html.replace('<option selected>🇬🇧 English (UK)</option>',
                            '<option>🇬🇧 English (UK)</option>')
        html = html.replace("<option>🇺🇸 English (US)</option>",
                            "<option selected>🇺🇸 English (US)</option>", 1)

    # ---- the banner --------------------------------------------------
    html = re.sub(
        r'<div class="notice">.*?</div>',
        '<div class="notice"><b>Live.</b> Catalogue, brand and questions read '
        'from %s just now. The scan itself is not built yet.</div>'
        % _esc(domain), html, count=1, flags=re.S)

    # ---- final sweep --------------------------------------------------
    # The design file seeds every data-product / data-price placeholder with
    # "Calira Sofa" and "€1,390", and names M&O in two code comments. The page
    # JS overwrites the visible ones on load, so they never render - but they
    # are still in the bytes we serve. Anyone who views source, or sees the
    # page for the instant before the script runs, would find another brand's
    # product in their own onboarding. Nothing M&O ships to anyone else.
    first = products[0] if products else None
    if first:
        html = html.replace("Calira Sofa", _esc(first["title"]))
        if first["price"]:
            html = html.replace("€1,390", _esc(sym + first["price"]))
    html = html.replace("molivings.com", _esc(domain))
    html = html.replace("M&amp;O Living", _esc(name))
    html = html.replace("M&O Living", _esc(name))

    leftovers = [t for t in ("Calira", "molivings", "M&O") if t in html]
    if leftovers and domain != "molivings.com":
        # Loud rather than silent: a new hardcoded brand string added to the
        # design file should surface here, not in front of a prospect.
        print("  WARNING: unreplaced brand strings in render: %s" % leftovers)

    return html.encode("utf-8")


def _features(brand_info, products):
    """Catalogue facts, each one checkable against the store's own feed."""
    import questions as _q

    sym = brand_info.get("symbol") or "€"
    out = []

    types = brand_info.get("types") or []
    if not types:
        # Stores like Clubhouse Skin publish no product_type and no tags, so
        # fall back to the noun in each product title - "moisturiser",
        # "cleanser" - which is what a buyer would call the thing anyway.
        counts = {}
        for r in products:
            n = _q.noun_for(r["title"], json.loads(r["raw_json"] or "{}"))
            counts[n] = counts.get(n, 0) + 1
        types = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    for t, c in types[:3]:
        out.append("%d %s in the catalogue" % (c, t))

    prices = sorted(int(float(r["price"])) for r in products if r["price"])
    if prices:
        out.append("Prices from %s%s to %s%s"
                   % (sym, "{:,}".format(prices[0]),
                      sym, "{:,}".format(prices[-1])))

    # Option names, minus Shopify's "Title" placeholder and minus options
    # named after the product itself - M&O names an option "Elara Sofa" on the
    # Elara Sofa, which is a product name, not a thing you configure.
    counts = {}
    for r in products:
        title = r["title"].lower()
        for o in (json.loads(r["raw_json"] or "{}").get("options") or []):
            o = (o or "").strip()
            if not o or o.lower() == "title" or len(o) > 24:
                continue
            if o.lower() in title or title.startswith(o.lower().split()[0]):
                continue
            counts[o.lower()] = counts.get(o.lower(), 0) + 1
    opts = [o for o, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    if opts:
        out.append("Configurable across %s" % ", ".join(opts[:4]))

    variants = sum(r["variants"] for r in products)
    if variants > len(products):
        out.append("%s variants across %d products"
                   % ("{:,}".format(variants), len(products)))

    # The audit's own signal, stated as a fact about this catalogue. This is
    # the number the whole product exists to move, so it belongs on the page
    # the merchant reads first.
    n = len(products)
    if n:
        mat = sum(1 for r in products
                  if _q_material(json.loads(r["raw_json"] or "{}")))
        dim = sum(1 for r in products
                  if _q_dimension(json.loads(r["raw_json"] or "{}")))
        out.append("Material stated on %d of %d products" % (mat, n))
        out.append("Dimensions stated on %d of %d products" % (dim, n))

    if not out:
        out = ["", "", ""]
    return out[:6]


def _q_material(raw):
    import questions as _q
    return _q.find_material(raw)


def _q_dimension(raw):
    import questions as _q
    return _q.find_dimension(raw)


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
