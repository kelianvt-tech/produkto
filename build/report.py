"""
Turn a run into something a brand owner will actually read.

Tone rule: name specific products and specific missing attributes, and tie each
one to a buyer query. "You score 34/100" gets deleted. "You cannot be retrieved
for 'sofa with removable washable covers' because no product states it" gets a
reply.
"""

STATUS_MARK = {"structured": "yes", "prose": "prose only", "missing": "no", "n/a": "—"}

# An attribute has to touch at least this share of the catalog before we call it
# a blind spot or recommend fixing it.
MATERIAL_SHARE = 0.10


def _material(summary, product_count):
    """Attributes that apply to enough of the catalog to be worth acting on."""
    floor = max(3, product_count * MATERIAL_SHARE)
    return [
        c for c in summary["attribute_coverage"].values()
        if c.get("applicable", 0) >= floor
    ]


def render(run, prior=None):
    s = run["summary"]
    lines = []
    add = lines.append

    add("# Catalog visibility audit — %s" % run["store"].split("//", 1)[-1])
    add("")
    add("Run %s · %d products · category: %s"
        % (run["run_at"].replace("T", " "), run["product_count"], run["category"]))
    if not run["pages_fetched"]:
        add("")
        add("> Feed-only run — product pages were not fetched, so JSON-LD and "
            "on-page specs were not read. Scores understate reality.")
    add("")

    # ---------------------------------------------------------------- headline
    add("## The number")
    add("")
    add("| | Score | What it measures |")
    add("|---|---:|---|")
    add("| **Spec-query retrievability** | **%.1f/100** | Whether your catalog states "
        "the attributes buyers actually ask for |" % s["catalog_attribute_score"])
    add("| Schema completeness | %.1f/100 | Whether the machine-readable markup is "
        "filled in |" % s["catalog_schema_score"])
    add("")
    add("The first number is the one that matters. Schema is plumbing — it can be "
        "fixed by a theme change. The first number is about whether the facts exist "
        "at all.")
    add("")

    if prior:
        add(_diff_section(run, prior))

    # ------------------------------------------------------------- the gap
    add("## What buyers ask that you can't answer")
    add("")
    add("Each row is an attribute that appeared in real buyer queries which "
        "returned ranked products. \"Prose only\" means the fact is in your "
        "description text but not as a labelled field — a model has to infer it "
        "rather than read it.")
    add("")
    add("Percentages are over the products each attribute actually applies to — "
        "a decorative bowl is not marked down for lacking a seat count.")
    add("")
    add("| Attribute | Buyer query it serves | Applies to | Structured | Prose only | Missing |")
    add("|---|---|---:|---:|---:|---:|")

    coverage = sorted(
        s["attribute_coverage"].items(),
        key=lambda kv: (kv[1]["any_pct"], -kv[1]["weight"]),
    )
    for _key, c in coverage:
        add("| %s | *%s* | %d | %d%% | %d%% | **%d%%** |" % (
            c["label"], c["query"], c.get("applicable", 0),
            round(c["structured_pct"]),
            round(c["any_pct"] - c["structured_pct"]),
            round(100 - c["any_pct"]),
        ))
    add("")

    # Only call something a blind spot if it applies to a meaningful slice of
    # the catalog -- otherwise we would flag an attribute that affects 2 SKUs.
    material = _material(s, run["product_count"])
    blind = [c for c in material if c["any_pct"] < 1]
    if blind:
        add("**Total blind spots** — never stated on any product they apply to:")
        add("")
        for c in blind:
            add("- **%s** (%d products) → invisible for queries like *\"%s\"*"
                % (c["label"], c["applicable"], c["query"]))
        add("")

    # ----------------------------------------------------------- worst products
    add("## The 20 products losing the most")
    add("")
    add("Ranked by how little a model can match against them.")
    add("")
    worst = sorted(run["products"], key=lambda p: (p["attribute_score"], p["title"]))[:20]
    add("| # | Product | Type | Score | Missing |")
    add("|---:|---|---|---:|---|")
    for i, p in enumerate(worst, 1):
        missing = [
            s["attribute_coverage"][k]["label"]
            for k, status in p["attributes"].items() if status == "missing"
        ]
        shown = ", ".join(missing[:4])
        if len(missing) > 4:
            shown += ", +%d more" % (len(missing) - 4)
        add("| %d | %s | %s | %.0f | %s |" % (
            i, p["title"], p.get("family", "—"), p["attribute_score"], shown or "—"))
    add("")

    # ------------------------------------------------------------------ schema
    add("## Machine-readable markup")
    add("")
    add("%d of %d products expose Product schema."
        % (s.get("products_with_schema", 0), run["product_count"]))
    add("")
    add("| Field | Present on |")
    add("|---|---:|")
    for _field, c in sorted(s["schema_coverage"].items(), key=lambda kv: kv[1]["pct"]):
        add("| %s | %d%% |" % (c["label"], round(c["pct"])))
    add("")

    # ----------------------------------------------------------------- reviews
    add("## Reviews")
    add("")
    labels = {
        "review_text_in_html": "Review text readable without JavaScript — good",
        "some_review_markers_in_html": "Some review signal in raw HTML",
        "rating_only_text_likely_js": "Star rating visible but review text likely "
                                      "JavaScript-only — the richest signal is invisible",
        "no_review_signal": "No review signal at all",
    }
    for state, count in sorted(s["review_states"].items(), key=lambda kv: -kv[1]):
        add("- %d products — %s" % (count, labels.get(state, state)))
    add("")
    add("*Heuristic: based on markers in the raw HTML, not a rendered page.*")
    add("")

    # ------------------------------------------------------------------ robots
    add(_robots_section(run["robots"]))

    # ------------------------------------------------------------------- fixes
    add("## Two things worth doing first")
    add("")
    # Rank by impact: how much of the catalog it touches x how much the
    # attribute is worth x how much of it is missing.
    ranked = sorted(
        _material(s, run["product_count"]),
        key=lambda c: -(c["applicable"] * c["weight"] * (100 - c["any_pct"])),
    )[:2]
    if not ranked:
        add("Not enough catalog coverage to rank fixes.")
    for i, c in enumerate(ranked, 1):
        add("%d. **State %s on the %d products it applies to.** Currently on %d%% "
            "of them. Unlocks queries like *\"%s\"*."
            % (i, c["label"].lower(), c["applicable"], round(c["any_pct"]), c["query"]))
    add("")

    if run["fetch_failures"]:
        add("---")
        add("")
        add("*%d product pages could not be fetched and were scored from feed data "
            "only.*" % len(run["fetch_failures"]))
        add("")

    return "\n".join(lines)


def _diff_section(run, prior):
    now = run["summary"]["catalog_attribute_score"]
    before = prior["summary"]["catalog_attribute_score"]
    delta = now - before
    arrow = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    out = [
        "## Change since last run",
        "",
        "Previous run %s scored %.1f. Now %.1f — **%s %+.1f points**."
        % (prior["run_at"].replace("T", " "), before, now, arrow, delta),
        "",
    ]

    moved = []
    prior_cov = prior["summary"]["attribute_coverage"]
    for key, c in run["summary"]["attribute_coverage"].items():
        if key in prior_cov:
            change = c["any_pct"] - prior_cov[key]["any_pct"]
            if abs(change) >= 1:
                moved.append((change, c["label"]))
    if moved:
        moved.sort(key=lambda x: -abs(x[0]))
        out.append("| Attribute | Coverage change |")
        out.append("|---|---:|")
        for change, label in moved[:10]:
            out.append("| %s | %+d pts |" % (label, round(change)))
        out.append("")
    return "\n".join(out)


def _robots_section(robots):
    out = ["## Crawler access", ""]
    if not robots["fetched"]:
        out.append("robots.txt could not be fetched.")
        out.append("")
        return "\n".join(out)

    blocked = [bot for bot, info in robots["allows"].items() if not info["allowed"]]
    if blocked:
        out.append("**Blocked: %s.** These crawlers cannot read the catalog at all, "
                   "which caps everything else in this report."
                   % ", ".join(blocked))
    else:
        out.append("All major AI crawlers are allowed.")
        if robots["mentions_ucp_mcp"]:
            out.append("")
            out.append("This store runs Shopify's current agent-open robots.txt, which "
                       "also advertises UCP/MCP endpoints. That is the platform default "
                       "now — it is not an advantage over competitors, it just means "
                       "crawler access is not the bottleneck here.")
    out.append("")
    return "\n".join(out)
