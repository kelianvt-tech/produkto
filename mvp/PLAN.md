# MVP — GEO Insights dashboard

**Written:** 24 August 2026
**Status:** v1 code written 16 Sep 2026 in `mvp/app/` (see its README). Not yet run against the real OpenAI API.

The simplest version that produces the four panels. One product, one LLM, one button, one dashboard.

---

## The whole product

```
1. Paste Shopify URL
        ↓
2. Their catalogue appears — searchable grid
        ↓
3. Select one product
        ↓
4. Click "Run GEO insights"
        ↓
5. ~30 seconds
        ↓
6. Dashboard: visibility score, trend, share of voice, positioning
```

No login, no setup form, no competitor entry, no settings. Paste, pick, run.

Step 2 already works — `capture.py` pulls `/products.json` straight off any Shopify store.

---

## What a scan is

**5 buyer questions × ChatGPT × 5 runs each = 25 answers.**

The 5 questions are generated from the selected product — its title, type, price band, options. For a €1,400 solid-oak 3-seater that's things like *"best solid wood 3-seater sofa under €1500"* or *"3 seater sofa with removable covers"*. The questions a buyer actually types where this product should be one of the answers.

Each answer gets parsed into a ranked list of products. Every panel below comes from those 25 answers.

**Three rules that matter:**

- **The 5 questions freeze at the first scan.** Regenerate them next week and the trend chart compares different questions, which makes it meaningless. One database column, but it has to be there from day one.
- **Web search on.** Off, the model answers from memory, which measures something the merchant can't influence at all.
- **5 runs per question, not 1.** ChatGPT's answers aren't repeatable — ask the same question twice, get different products. Cutting to one model freed the budget, so runs went from 3 to 5; it's the cheapest place to spend it.

Runs per question is a config value, not a design decision. Raise it later without touching any code structure.

**Cost:** ~50 API calls per scan (25 answers + 25 extraction passes). Roughly $0.10–0.30.

**One accuracy note, then I'll leave it alone:** this measures the OpenAI API with web search enabled, which is close to but not identical to chatgpt.com — different system prompt, no memory. Label it on the page as "measured via the ChatGPT API" and it's honest.

---

## Panel 1 — Visibility score /100

How often the product gets named, weighted by where it lands in the answer.

| Named at rank | Credit |
|---|---|
| 1 | 1.00 |
| 2 | 0.63 |
| 3 | 0.50 |
| 4 | 0.43 |
| 5 | 0.39 |
| not named | 0.00 |

Score = average credit across all 25 answers × 100.

**On screen:** the big number, and under it two lines that explain it —

- *Named in 3 of 25 answers (12%)*
- *Average position when named: 3.4*

Those two answer the first question anyone asks: am I not showing up, or showing up badly?

---

## Panel 2 — Trend

Line chart of the visibility score, one point per scan, **weekly**.

**Day one shows a single point.** The data doesn't exist until a second scan. Empty state reads *"Reading 1 — trend from next week."* No backfilled or simulated history.

At 25 answers the chart is coarse: a single extra mention moves the appearance rate by 4 points, so week-to-week wiggles are mostly sampling noise. One line under the chart handles it — *"changes under ~12 points are within measurement noise."* Raising runs per question tightens that number; it's the dial mentioned above.

This is the panel that pays for the small scan. The other three describe a snapshot and are unaffected.

---

## Panel 3 — Share of voice

Their product's share of every product recommendation in the scan.

Across the 25 answers, count every product recommended. Their share = their mentions ÷ all mentions, as a percentage.

**Competitors are discovered, not entered.** Whatever ChatGPT actually recommends becomes the comparison set — no setup step, and it surfaces the products they're losing to, which they usually don't know.

**On screen:** a horizontal ranked bar list. Their product highlighted at its true position, top 6 competing products named with percentages, the rest collapsed into "other."

---

## Panel 4 — Average positioning

With one LLM this stops being a matrix and becomes a leaderboard — a ranked table of the brands ChatGPT recommends, their product pinned on top.

| | Avg. position | Named in |
|---|---|---|
| **Your product** | 3.4 | 12% of answers |
| Article | 1.4 | 87% |
| Burrow | 2.2 | 67% |
| Castlery | 2.8 | 53% |

Both columns, because either alone misleads. Appear once at rank 2 out of 25 runs and your "average position" is 2.0 — better-looking than a competitor at 1.9 who shows up every single time. Together they can't be misread.

Their row is their product; the rows below are brands, as you described it. Heatmap colouring on the position column.

**This is the panel that grows back when you add models.** The `answers` table already stores which model produced each answer, so a second LLM adds a column — no restructuring, no migration. Build it as a table that renders N columns from day one and adding Claude or Perplexity later is an afternoon.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Storage | SQLite — one file |
| Job | Background thread, page polls for status |
| Frontend | Server-rendered Jinja + Chart.js from CDN |
| Auth | None. Results live at an unguessable URL. |

No npm, no build step, no framework. The HTML stays readable and editable by you.

### Data model

```
products     (id, store_domain, shopify_id, title, url, price, raw_json)
prompt_sets  (id, product_id, prompts[], frozen_at)
scans        (id, prompt_set_id, run_at, status, cost_cents, model_versions)
answers      (id, scan_id, prompt, model, run_n, raw_text)
mentions     (id, answer_id, product_name, brand, rank, is_theirs)
scores       (id, scan_id, visibility, appearance_rate, avg_rank, sov_pct)
```

`model` stays on `answers` even though there's only one — it's what makes adding LLMs later additive instead of a rewrite.

`answers` is append-only. It's the only record of what ChatGPT actually said, and keeping it means re-parsing never costs another API call.

---

## Build order

| Phase | What | Est. |
|---|---|---|
| 1 | URL → catalogue grid → product picker | 0.5 day |
| 2 | Generate + freeze the 5 questions | 0.5 day |
| 3 | Scan runner — ChatGPT, 5 runs, retries, cost log | 1 day |
| 4 | Parse answers into ranked products, match theirs | 1.5 days |
| 5 | Scoring — all four panels' numbers | 0.5 day |
| 6 | Dashboard UI — panels 1, 3, 4 | 1.5 days |
| 7 | Panel 2 chart + weekly re-scan | 0.5 day |

**~5.5 working days.**

Phase 4 carries the risk. Models name products loosely — *"the Sven 3-seater from Article"* has to resolve to a specific SKU in their catalogue. That's fuzzy matching with a confidence threshold, and low-confidence matches get logged rather than silently counted.

---

## Before giving it to real users

Decided 17 Sep 2026 (see `../DECISIONS.md`). Not built yet.

- **Automatic scans, spread across the week.** Each product's questions are asked in small batches on different days, not as one big scan. The trend is built from those answers, one point per week (or per day). This replaces the manual "Run new scan" as the main way data comes in.
- **Hosting.** Automatic scans only run while the app is running, so real users need it on a server, not a laptop.

---

## One open decision

**Open or email-gated?** Open is the stronger door-opener — paste a URL, get a score, nothing to decline. Recommend open, with a soft email ask once the results are on screen.

---

## Risks

- **Scores will be low.** Most products land between 0 and 5 out of 100. That's the honest reading and it's the reason to sell them something — but expect it, so it doesn't read as a bug.
- **Product matching won't be perfect.** Some mentions get missed, some miscounted. Measure the match rate during Phase 4 before trusting the numbers.
- **Model versions change underneath you.** A score shift can be OpenAI shipping a new model rather than anything the merchant did. Log the version string per scan.
