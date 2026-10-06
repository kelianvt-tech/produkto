#!/usr/bin/env python3
"""
Catalog visibility audit.

Question it answers: when a buyer asks a spec-shaped question in this brand's
category, does the catalog contain anything an AI model could match against?

Usage:
    python3 build/audit.py https://molivings.com
    python3 build/audit.py https://molivings.com --limit 10        # quick test
    python3 build/audit.py https://molivings.com --no-fetch-pages  # feed only, fast

Results are written to audits/<brand>/<timestamp>.json and a readable report
next to it. Runs are kept, never overwritten, so a re-audit after remediation
can be diffed against the baseline. That diff is the whole point -- it is the
only way to answer whether the fixes actually move visibility.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import attributes as attrs_mod
import extract
import report as report_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDITS_DIR = os.path.join(ROOT, "audits")

# Credit for an attribute that is present but buried in prose rather than
# exposed as a structured field. Half credit: the fact exists, but a model has
# to parse it out of a sentence instead of reading a labelled value.
PROSE_CREDIT = 0.5


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# --------------------------------------------------------------------------
# Per-product analysis
# --------------------------------------------------------------------------

def collect_sources(product, page_text, schema):
    """
    Split everything we know about a product into structured vs. prose text.

    structured = labelled fields a model can read as key/value
    prose      = free text a model has to interpret
    """
    structured_parts = []
    structured_labels = []

    # Shopify option names and values ("Size: 220cm", "Material: Oak")
    for option in product.get("options") or []:
        name = option.get("name") or ""
        structured_labels.append(name)
        structured_parts.append(name)
        structured_parts.extend(str(v) for v in (option.get("values") or []))

    if product.get("product_type"):
        structured_parts.append(product["product_type"])
        structured_labels.append("product_type")

    for tag in product.get("tags") or []:
        structured_parts.append(str(tag))

    # JSON-LD additionalProperty is the canonical place for specs
    if schema:
        for prop in _as_list(schema.get("additionalProperty")):
            if isinstance(prop, dict):
                name = str(prop.get("name") or "")
                value = str(prop.get("value") or "")
                structured_labels.append(name)
                structured_parts.append("%s %s" % (name, value))
        # Explicit schema.org fields that carry spec meaning
        for field in ("material", "color", "width", "height", "depth", "size", "weight"):
            value = schema.get(field)
            if value:
                structured_labels.append(field)
                structured_parts.append("%s %s" % (field, _scalar(value)))

    prose_parts = [extract.strip_html(product.get("body_html"))]
    if page_text:
        prose_parts.append(page_text)

    return {
        "structured": " ".join(p for p in structured_parts if p),
        "structured_labels": [l.lower() for l in structured_labels if l],
        "prose": " ".join(p for p in prose_parts if p),
    }


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _scalar(value):
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or "")
    if isinstance(value, list):
        return " ".join(_scalar(v) for v in value)
    return str(value)


def applies(attr, family):
    """Does this attribute make sense for this product family?"""
    scope = attr.get("applies_to", "*")
    if scope == "*":
        return True
    # 'unknown' family is scored against universal attributes only, so an
    # unrecognised product never invents a false gap.
    return family in scope


def score_attributes(sources, table, family):
    """
    Classify each category attribute as structured / prose / missing / n/a.

    Attributes that do not apply to the product's family are marked 'n/a' and
    excluded from both the numerator and the denominator.
    """
    results = {}
    earned = 0.0
    possible = 0.0

    for attr in table:
        if not applies(attr, family):
            results[attr["key"]] = "n/a"
            continue

        possible += attr["weight"]
        status = "missing"

        # A labelled field whose NAME matches the attribute counts as structured
        # even if the value is odd -- the merchant has modelled the concept.
        for label in sources["structured_labels"]:
            if any(key in label for key in attr["schema_keys"]):
                status = "structured"
                break

        if status == "missing":
            if any(p.search(sources["structured"]) for p in attr["patterns"]):
                status = "structured"
            elif any(p.search(sources["prose"]) for p in attr["patterns"]):
                status = "prose"

        if status == "structured":
            earned += attr["weight"]
        elif status == "prose":
            earned += attr["weight"] * PROSE_CREDIT

        results[attr["key"]] = status

    score = (earned / possible * 100.0) if possible else 0.0
    return results, round(score, 1)


def score_schema(schema):
    """Table-stakes schema.org completeness. Separate from the query attributes."""
    found = {}
    earned = 0.0
    possible = 0.0

    for field, _label, weight in attrs_mod.SCHEMA_FIELDS:
        possible += weight
        present = False
        if schema:
            if "." in field:
                parent, child = field.split(".", 1)
                for offer in _as_list(schema.get(parent)):
                    if isinstance(offer, dict) and offer.get(child):
                        present = True
                        break
            else:
                value = schema.get(field)
                if field == "gtin":
                    # MPN deliberately excluded -- it is not a GTIN, and AI
                    # shopping surfaces resolve products by GTIN. Counting MPN
                    # here would inflate the score and hide a real gap.
                    present = any(
                        schema.get(k)
                        for k in ("gtin", "gtin13", "gtin12", "gtin8", "gtin14")
                    )
                else:
                    present = bool(value)
        found[field] = present
        if present:
            earned += weight

    score = (earned / possible * 100.0) if possible else 0.0
    return found, round(score, 1)


_REVIEW_MARKERS = re.compile(
    r"verified (?:purchase|buyer)|wrote a review|customer reviews?|"
    r"\b\d+\s*(?:reviews?|ratings?)\b|out of 5 stars",
    re.I,
)


def check_reviews(schema, page_text):
    """
    Heuristic. Reports whether review signal survives without JavaScript.

    'rating_only' is the interesting failure: the star rating is in the markup
    but the review TEXT is loaded client-side, so the richest signal on the
    page is invisible to a crawler.
    """
    has_rating = bool(schema and schema.get("aggregateRating"))
    has_schema_text = False
    if schema:
        for review in _as_list(schema.get("review")):
            if isinstance(review, dict) and review.get("reviewBody"):
                has_schema_text = True
                break
    has_page_text = bool(page_text and _REVIEW_MARKERS.search(page_text))

    if has_schema_text:
        state = "review_text_in_html"
    elif has_rating and not has_page_text:
        state = "rating_only_text_likely_js"
    elif has_page_text:
        state = "some_review_markers_in_html"
    else:
        state = "no_review_signal"

    return {
        "state": state,
        "has_aggregate_rating": has_rating,
        "has_review_text_in_schema": has_schema_text,
        "has_review_markers_in_page": has_page_text,
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def audit_store(store_url, category="furniture", limit=None, delay=0.5,
                fetch_pages=True, log=print):
    base = extract.normalise_store_url(store_url)
    table = attrs_mod.get_category(category)
    started = datetime.datetime.now()

    log("Auditing %s" % base)
    log("Category: %s (%d attributes)" % (category, len(table)))

    log("Checking robots.txt ...")
    robots = extract.analyse_robots(base, attrs_mod.AI_CRAWLERS)

    log("Enumerating catalog ...")
    raw_products = extract.enumerate_shopify(base, limit=limit, delay=delay, log=log)
    log("Catalog: %d products" % len(raw_products))

    results = []
    failures = []
    for index, product in enumerate(raw_products, 1):
        handle = product.get("handle")
        url = "%s/products/%s" % (base, handle) if handle else None
        page_text, schema = "", None

        if fetch_pages and url:
            try:
                html_text = extract.fetch(url, delay=delay)
                page_text, objects = extract.parse_page(html_text)
                schema = extract.find_product_schema(objects)
            except extract.FetchError as exc:
                failures.append({"url": url, "error": str(exc)})
            time.sleep(delay)

        family = attrs_mod.infer_family(
            product.get("title"), product.get("tags"), product.get("product_type")
        )
        sources = collect_sources(product, page_text, schema)
        attr_status, attr_score = score_attributes(sources, table, family)
        schema_found, schema_score = score_schema(schema)
        reviews = check_reviews(schema, page_text)

        results.append({
            "title": product.get("title") or "(untitled)",
            "handle": handle,
            "url": url,
            "family": family,
            "attribute_score": attr_score,
            "attributes": attr_status,
            "schema_score": schema_score,
            "schema_present": bool(schema),
            "schema_fields": schema_found,
            "reviews": reviews,
            "description_chars": len(extract.strip_html(product.get("body_html"))),
        })

        if index % 10 == 0 or index == len(raw_products):
            log("  scored %d/%d" % (index, len(raw_products)))

    run = {
        "store": base,
        "category": category,
        "run_at": started.isoformat(timespec="seconds"),
        "duration_seconds": round((datetime.datetime.now() - started).total_seconds(), 1),
        "pages_fetched": fetch_pages,
        "product_count": len(results),
        "robots": robots,
        "products": results,
        "fetch_failures": failures,
        "summary": summarise(results, table),
    }
    return run


def summarise(results, table):
    if not results:
        return {"catalog_attribute_score": 0.0, "catalog_schema_score": 0.0,
                "attribute_coverage": {}, "schema_coverage": {}, "review_states": {}}

    n = len(results)
    attr_coverage = {}
    for attr in table:
        key = attr["key"]
        # Percentages are over the products the attribute APPLIES to, not the
        # whole catalog. Otherwise a store that sells mostly decor looks broken
        # for not stating seat counts on its vases.
        relevant = [r for r in results if r["attributes"].get(key) != "n/a"]
        denominator = len(relevant) or 1
        structured = sum(1 for r in relevant if r["attributes"][key] == "structured")
        prose = sum(1 for r in relevant if r["attributes"][key] == "prose")
        attr_coverage[key] = {
            "label": attr["label"],
            "weight": attr["weight"],
            "query": attr["query"],
            "applicable": len(relevant),
            "structured": structured,
            "prose": prose,
            "missing": len(relevant) - structured - prose,
            "structured_pct": round(structured / denominator * 100, 1),
            "any_pct": round((structured + prose) / denominator * 100, 1),
        }

    families = {}
    for r in results:
        families[r.get("family", "unknown")] = families.get(r.get("family", "unknown"), 0) + 1

    schema_coverage = {}
    for field, label, _w in attrs_mod.SCHEMA_FIELDS:
        present = sum(1 for r in results if r["schema_fields"].get(field))
        schema_coverage[field] = {
            "label": label,
            "present": present,
            "pct": round(present / n * 100, 1),
        }

    review_states = {}
    for r in results:
        state = r["reviews"]["state"]
        review_states[state] = review_states.get(state, 0) + 1

    return {
        "catalog_attribute_score": round(sum(r["attribute_score"] for r in results) / n, 1),
        "catalog_schema_score": round(sum(r["schema_score"] for r in results) / n, 1),
        "products_with_schema": sum(1 for r in results if r["schema_present"]),
        "families": families,
        "attribute_coverage": attr_coverage,
        "schema_coverage": schema_coverage,
        "review_states": review_states,
    }


def save_run(run):
    brand = slugify(run["store"].split("//", 1)[-1])
    out_dir = os.path.join(AUDITS_DIR, brand)
    os.makedirs(out_dir, exist_ok=True)
    stamp = run["run_at"].replace(":", "").replace("-", "").replace("T", "-")
    json_path = os.path.join(out_dir, "%s.json" % stamp)
    with open(json_path, "w") as handle:
        json.dump(run, handle, indent=2)
    return json_path, out_dir


def previous_run(out_dir, current_path, current_count):
    """
    Most recent comparable earlier run, for diffing.

    Comparable means a similar catalog size. Diffing a full run against a
    --limit smoke test produces a real-looking but meaningless delta, which is
    worse than no diff at all.
    """
    candidates = sorted(
        f for f in os.listdir(out_dir)
        if f.endswith(".json") and os.path.join(out_dir, f) != current_path
    )
    for name in reversed(candidates):
        try:
            with open(os.path.join(out_dir, name)) as handle:
                prior = json.load(handle)
        except (ValueError, OSError):
            continue
        prior_count = prior.get("product_count", 0)
        if not prior_count:
            continue
        if abs(prior_count - current_count) <= max(2, current_count * 0.1):
            return prior
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("store", help="Store URL, e.g. https://molivings.com")
    parser.add_argument("--category", default="furniture")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only audit the first N products")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between requests (default 0.5)")
    parser.add_argument("--no-fetch-pages", action="store_true",
                        help="Use the product feed only, skip fetching each page")
    args = parser.parse_args(argv)

    run = audit_store(
        args.store,
        category=args.category,
        limit=args.limit,
        delay=args.delay,
        fetch_pages=not args.no_fetch_pages,
    )

    json_path, out_dir = save_run(run)
    prior = previous_run(out_dir, json_path, run["product_count"])
    report_path = json_path.replace(".json", ".md")
    with open(report_path, "w") as handle:
        handle.write(report_mod.render(run, prior))

    print("")
    print("Catalog attribute score: %.1f/100" % run["summary"]["catalog_attribute_score"])
    print("Schema completeness:     %.1f/100" % run["summary"]["catalog_schema_score"])
    print("")
    print("Data:   %s" % json_path)
    print("Report: %s" % report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
