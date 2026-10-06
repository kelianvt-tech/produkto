"""Measure what the cheap-scan levers actually cost and actually change.

Two of the three biggest savings in ALL-HANDS-COST-2026-09-19.md are
*assumptions*: that `search_context_size="low"` cuts the search content fed
back into the model, and that `reasoning={"effort":"low"}` cuts the output
(reasoning) tokens. This script measures both on real buyer questions, and
- just as important - checks whether the answer still recommends the same
brands. A cheaper setting that changes the answer is not cheaper, it is a
different measurement.

It does NOT touch the database and does NOT record a scan. It is a lab
bench, not a product feature.

Run:
    python3 bench_cost.py               # prints the plan and the cost, runs nothing
    python3 bench_cost.py --yes         # actually spends money
    python3 bench_cost.py --yes --questions 5

Every call is real API spend. The estimate printed before you confirm is
based on the measured cost of scan 5 ($0.099 per answer at the current
settings) and is an upper bound: the cheaper arms cost less.
"""

import argparse
import json
import sys
import urllib.error

import config
import llm

# Real buyer questions from the Clubhouse Skin catalog scan (scan 5), so the
# search workload is representative rather than a toy.
QUESTIONS = [
    "What skincare products can I get for under £40 that cleanse gently or "
    "hydrate without feeling heavy?",
    "What's the best simple three-step skincare routine for cleansing, "
    "brightening and hydrating?",
    "Which lightweight moisturiser contains snow mushroom, squalane and "
    "niacinamide for deep hydration?",
    "What are the best structured unisex cotton caps inspired by 1990s golf "
    "style?",
    "Which vitamin C face oil can brighten skin, support environmental "
    "protection and absorb without feeling greasy?",
]

# name -> (extra web_search tool keys, extra request body keys)
ARMS = [
    ("baseline (as shipped)", {}, {}),
    ("context=low", {"search_context_size": "low"}, {}),
    ("reasoning=low", {}, {"reasoning": {"effort": "low"}}),
    ("context=low + reasoning=low",
     {"search_context_size": "low"}, {"reasoning": {"effort": "low"}}),
]

MEASURED_COST_PER_ANSWER = 0.0993   # scan 5, 18 Sep 2026


def ask(question, tool_extra, body_extra, country):
    """One answer call with the arm's settings. Returns (resp, usage_row)."""
    tool = {"type": "web_search"}
    tool.update(tool_extra)
    if country:
        tool["user_location"] = {"type": "approximate", "country": country}
    body = {"model": config.ANSWER_MODEL, "tools": [tool], "input": question}
    body.update(body_extra)
    resp = llm._post(body)
    u = resp.get("usage") or {}
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens") or 0
    row = {
        "input": u.get("input_tokens") or 0,
        "cached": cached,
        "output": u.get("output_tokens") or 0,
        "reasoning": (u.get("output_tokens_details") or {}).get(
            "reasoning_tokens") or 0,
        "searches": sum(1 for o in resp.get("output") or []
                        if o.get("type") == "web_search_call"),
        "model": resp.get("model") or config.ANSWER_MODEL,
    }
    return resp, row


def price(row):
    p = config.PRICES.get(row["model"])
    if p is None:
        candidates = [k for k in config.PRICES if row["model"].startswith(k + "-")]
        p = config.PRICES[max(candidates, key=len)] if candidates else None
    if p is None:
        return None
    uncached = max(0, row["input"] - row["cached"])
    return ((uncached * p[0] + row["cached"] * p[1] + row["output"] * p[2])
            / 1e6) + row["searches"] * config.SEARCH_PRICE


def brands(text):
    """Cheap agreement check: which of the baseline's brands survive.

    Uses the same helper model and schema the scanner uses, so the comparison
    is against what Produkto would actually have recorded, not against raw
    prose. Costs about $0.0004 per call.
    """
    import scan
    items = llm.json_call(scan.EXTRACT_INSTRUCTIONS,
                          "Shopping question: -\n\nAnswer:\n" + text,
                          "recommendations", scan.EXTRACT_SCHEMA).get("items") or []
    return {(i.get("brand") or i.get("product_name") or "").strip().lower()
            for i in items if (i.get("brand") or i.get("product_name"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually spend money")
    ap.add_argument("--questions", type=int, default=3,
                    help="how many of the %d questions to use" % len(QUESTIONS))
    ap.add_argument("--country", default=config.BUYER_COUNTRY)
    args = ap.parse_args()

    qs = QUESTIONS[:max(1, min(args.questions, len(QUESTIONS)))]
    calls = len(qs) * len(ARMS)
    upper = calls * MEASURED_COST_PER_ANSWER + calls * 0.0005

    print("Model:      %s" % config.ANSWER_MODEL)
    print("Questions:  %d" % len(qs))
    print("Arms:       %s" % ", ".join(a[0] for a in ARMS))
    print("API calls:  %d answers + %d extractions" % (calls, calls))
    print("Upper-bound cost: $%.2f  (cheaper arms will come in under this)"
          % upper)
    if not args.yes:
        print("\nNothing was spent. Re-run with --yes to measure for real.")
        return 0

    results = {}
    baseline_brands = {}
    for qi, q in enumerate(qs, 1):
        for name, tool_extra, body_extra in ARMS:
            try:
                resp, row = ask(q, tool_extra, body_extra, args.country)
            except (llm.LLMError, urllib.error.URLError) as e:
                print("  ! %s / q%d failed: %s" % (name, qi, e))
                continue
            text, _ = llm._text_and_citations(resp)
            row["cost"] = price(row)
            try:
                found = brands(text)
            except llm.LLMError:
                found = set()
            if name == ARMS[0][0]:
                baseline_brands[qi] = found
            base = baseline_brands.get(qi, set())
            row["kept"] = (len(found & base) / len(base)) if base else None
            results.setdefault(name, []).append(row)
            print("  q%d %-28s in=%6d out=%5d (reason %5d) srch=%d $%.4f kept=%s"
                  % (qi, name, row["input"], row["output"], row["reasoning"],
                     row["searches"], row["cost"] or 0,
                     "-" if row["kept"] is None else "%.0f%%" % (100 * row["kept"])))

    print("\n%-30s %9s %9s %9s %8s %9s %8s"
          % ("arm", "in/ans", "out/ans", "srch/ans", "$/ans", "vs base", "kept"))
    base_cost = None
    for name, _, _ in ARMS:
        rows = results.get(name) or []
        if not rows:
            continue
        n = len(rows)
        c = sum(r["cost"] or 0 for r in rows) / n
        base_cost = base_cost if base_cost is not None else c
        kept = [r["kept"] for r in rows if r["kept"] is not None]
        print("%-30s %9.0f %9.0f %9.1f %8.4f %8.0f%% %7s"
              % (name, sum(r["input"] for r in rows) / n,
                 sum(r["output"] for r in rows) / n,
                 sum(r["searches"] for r in rows) / n, c,
                 100 * c / base_cost if base_cost else 0,
                 "-" if not kept else "%.0f%%" % (100 * sum(kept) / len(kept))))

    print("\n`kept` = share of the baseline's recommended brands that the "
          "cheaper arm still names.\nA saving is only real if `kept` stays "
          "high. Write the numbers into ALL-HANDS-COST-2026-09-19.md §4.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
