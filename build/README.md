# The audit tool

## What it does, in one sentence

It asks: *when a buyer types a spec-shaped question into ChatGPT, does this brand's catalog contain anything the model could match against?*

## Run it

```bash
python3 build/audit.py https://molivings.com
```

Options:

| Flag | What it does |
|---|---|
| `--limit 10` | Only the first 10 products. Use this while testing |
| `--delay 0.35` | Seconds between requests. Be polite; don't go below 0.2 |
| `--no-fetch-pages` | Feed only, skips loading each product page. Fast but less accurate |
| `--category furniture` | Which attribute table to score against |

Needs nothing installed — Python 3 standard library only.

## Where results go

```
audits/<store>/20260803-140346.json   full data
audits/<store>/20260803-140346.md     the readable report
```

**Runs are never overwritten.** Re-audit the same store later and the report gets a "Change since last run" section comparing the two. That diff is the point of the whole tool: it is the only way to answer whether the fixes we make actually move visibility — the open question nobody in this market has answered, including the funded competitors.

## How the scoring works

**Two separate scores, deliberately.**

*Spec-query retrievability* is the one that matters. For each product we check whether the catalog states the attributes that appear in buyer queries — dimensions, seat count, wood species, whether covers come off, and so on. Scoring:

- stated as a **labelled field** (a spec table, a Shopify option, JSON-LD) → full credit
- stated **only in the description prose** → half credit
- **not stated** → nothing

Half credit for prose is the important idea. M&O's Calira Sofa says *"Material Solid wood frame ... Dimensions L 100 x W 100 x H 66"* — the facts exist, but as a sentence rather than as data. A model has to interpret them instead of reading them.

*Schema completeness* is the second score and it matters less. It's the machine-readable markup — brand, SKU, GTIN, price. Usually a theme-level fix rather than a content problem.

**Attributes only count against products they apply to.** A decorative bowl isn't marked down for not stating how many people it seats. Product family is guessed from the title and tags; anything unrecognised is scored against the universal attributes only, so a bad guess never invents a fake problem.

## The files

| File | What's in it |
|---|---|
| `attributes.py` | **The asset.** The list of attributes per category, and which product types each applies to |
| `extract.py` | Fetching pages, reading JSON-LD, checking robots.txt |
| `audit.py` | Runs the audit and does the scoring |
| `report.py` | Turns a run into the markdown report |

Everything except `attributes.py` is plumbing. `attributes.py` is the part worth protecting — it encodes which attributes actually matter, derived from queries we tested rather than from guesswork.

## Adding a category

Copy the `FURNITURE` list in `attributes.py` and change the entries. **Derive them from queries you have actually run**, not from imagination. The furniture list exists because those specific queries returned ranked products on 3 August; that evidence is what makes the list worth anything.

## Known limits — be honest about these

- **Attribute detection is pattern matching, not comprehension.** It looks for phrases. Unusual wording will be missed, so scores are a floor, not a precise measure.
- **Review detection is a heuristic.** It looks for markers in raw HTML. It can't tell a genuinely review-less store from one whose reviews render in a way we don't recognise.
- **No JavaScript is executed** — on purpose, since that approximates what a crawler sees. But it means a store using client-side rendering will score worse here than a browser would suggest.
- **Product family inference is keyword-based** and will misfile odd product names.
- **It does not measure visibility.** It measures whether the raw material for visibility exists. Whether fixing these attributes actually changes what ChatGPT recommends is unproven — that's what the re-run diff is for.
