# Produkto MVP — rearchitecture spec: per-SKU scanning → per-question-cluster scanning

**Written:** 18 September 2026
**For:** whoever implements this (a model or a person) with no access to the conversation that produced it.
**Codebase:** `mvp/app/` — Python 3, standard library only, SQLite, no npm, no build step.

Read this whole document before changing any file. Section 9 lists rules that must not be broken; several of them were learned by getting them wrong.

---

## 1. Why this change exists

The MVP asks **5 buyer questions × 5 runs = 25 answers per product**. Each answer is matched against exactly one product — see `mvp/app/scan.py:99`, `match(mention, product, aliases)`, singular.

Measured from four real scans in `mvp/app/produkto.db`, one scan costs **~$3.79** (670k input tokens, 31k output tokens, 68 web searches). `mvp/PLAN.md` budgeted $0.10–0.30. The account ran out of credit mid-scan on 17 Sep.

Cost therefore scales with **SKU count**. An 86-product catalog scanned weekly across four AI engines costs ~$3,631/month in API spend — more than the product could be sold for.

The waste is structural, not a pricing problem:

- A single answer names ~12 products. Eleven are discarded as "competitors".
- Questions overlap heavily between products. Prompt set 1 (Frontier Cleanser) and prompt set 2 (Essentials Set) in the existing database both ask about gentle cleansers that don't strip skin and protect the barrier — nearly the same scan, bought twice.
- Scan 3 cost $3.82 and returned **zero** mentions of its product, while collecting 25 answers full of cleansers that were never checked against the store's other five products.

**Buyer questions are category-shaped, not SKU-shaped.** *"Best gentle face cleanser under £40"* speaks to every cleanser in a catalog at once.

**The change:** scan a frozen set of question clusters per store, and match every answer against the entire catalog. Cost then scales with the number of distinct buyer questions a catalog competes on, not with SKU count. Projected effect for an 86-product catalog on four engines: **$3,631/mo → ~$51/mo** (fortnightly, 3 runs/question, ~20 clusters).

Full cost analysis: `mvp/UNIT-ECONOMICS-2026-09-18.md`.

### An assumption the implementer must not treat as fact

**"~20 question clusters covers an 86-product catalog" is an untested guess.** It has never been measured on a real catalog. It sets the entire cost case. Build the cluster count as a **configurable value**, never a hard-coded 20, and do not write the figure into any user-facing copy, pricing page or projection.

---

## 2. What stays exactly as it is

Do not touch these. They carry design decisions that were argued over and settled, and several are logged as rules in `mvp/MEMORY.md` and `MEMORY.md`.

### Files that need no changes at all

| File | What it does | Why it survives |
|---|---|---|
| `mvp/app/llm.py` | OpenAI Responses API calls, retries, usage counting | Provider plumbing, product-agnostic |
| `mvp/app/catalog.py` | Pulls `/products.json` and `/meta.json` from Shopify | Already fetches whole catalogs |
| `mvp/app/config.py` | All tunables in one place | Gains values (§6), loses none |
| `mvp/app/period.py` | Date range + weekly/monthly/quarterly grouping | No product coupling |
| `mvp/app/text.py` | `norm`, `words`, `core_title` helpers | Pure string helpers |
| `mvp/app/icons.py` | Favicon fetching for competitor domains | No product coupling |
| `mvp/app/sov_drawer.py` | Share-of-voice slide-out panel | Already renders a competitive set |
| `mvp/app/dashboard.css` | All dashboard styling | No structural change needed |
| `mvp/app/onboarding.css` | All onboarding styling | No structural change needed |
| `mvp/app/logo.png`, `sky-glyphs.svg`, `icons/` | Brand assets | — |

### Behaviour that must be preserved unchanged

- **Visual system.** Produkto navy palette, the soft cream onboarding, the Searchable-style chart-led dashboard layout, the four-step onboarding indicator, all icons and type. No redesign is authorised by this document.
- **The headline number is "mentioned in X% of answers"**, with average position shown separately beside it. The position-weighted `/100` score stays stored in `scores.visibility` and as `weighted` in `insight_panels.py`, but is never displayed.
- **Time grouping is Weekly, Monthly or Quarterly. Never Daily.**
- **Green when a visibility trend rises, red when it falls**, with a readable change label.
- **Single-scan chart behaviour:** a dashed illustrative line from zero to the first result, with the start labelled "not measured". Never stored as a scan, never used to calculate change.
- **Overview visibility chart is date-based only.** No "By question" toggle on it; question detail lives in the buyer-question section.
- **Percentages, not "X of 25"**, anywhere a user can see. Never state the number of questions or runs in user-facing copy.
- **No "ChatGPT API · web search" or "Measured via the ChatGPT API" labels** anywhere on the dashboard.
- **Every tab follows the period filter**, and internal links carry `range/group/from/to`.
- **Mentions & Citations shows counts**, following Searchable's count-led panels.
- **Never invent data.** No fake testimonials, logos, trend points or backfilled zeros. Empty states read "No scans in this period".
- **Questions freeze at the first scan**, enforced in `db.save_prompts`. Do not add a way around it — see §5.2.
- **The brand card is identity, not analysis.** Brand name, aliases, country, currency exist so the merchant's products can be recognised in AI answers and questions priced correctly. Never add persona, tone of voice or brand description fields.
- **Questions are generated by a model from real catalog data.** No templates, no keyword-to-template substitution, no pre-written question lists. Show a loading state while they are genuinely produced. Two wrong versions have already shipped; do not ship a third.
- **Buyer questions must carry a currency symbol** read from the store's own `/meta.json`, never a bare number and never a guessed currency. ChatGPT read "cleansers around 39" as an age.
- **`answers` is append-only.** Never edited, never deleted. It is the only record of what the engine actually said.

### The concept that does *not* change

Produkto still measures at **product level**. Results are still reported per product. What changes is how questions are **gathered** — per catalog instead of per SKU. Every product gets scored against every relevant question instead of only its own five, which serves product-level reporting better, not worse.

---

## 3. Architecture: before and after

```
BEFORE
  store → pick ONE product → 5 questions for it → 25 answers
                                                     ↓
                                   each answer matched against THAT product
                                                     ↓
                                   scores keyed by scan_id (one product)

AFTER
  store → confirm catalog → N question clusters for the catalog → N × runs answers
                                                     ↓
                               each answer matched against EVERY product in catalog
                                                     ↓
                     scores keyed by (scan_id, product_id) + one catalog aggregate
```

---

## 4. Database changes

The database is pre-customer. `mvp/app/produkto.db` holds 6 products, 3 prompt sets, 4 scans, 98 answers. **A destructive migration is acceptable**; preserving the four existing scans is not required. Keep the file as a backup copy before migrating.

All schema lives in `SCHEMA` in `mvp/app/db.py:22`.

### 4.1 `prompt_sets` — rekey from product to store

Current (`db.py:45`):

```sql
CREATE TABLE prompt_sets (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL UNIQUE,
    prompts    TEXT NOT NULL,
    tags       TEXT DEFAULT '',
    created_at REAL,
    frozen_at  REAL
);
```

Target:

```sql
CREATE TABLE prompt_sets (
    id           INTEGER PRIMARY KEY,
    store_domain TEXT NOT NULL UNIQUE,
    prompts      TEXT NOT NULL,   -- JSON array of question strings
    tags         TEXT DEFAULT '', -- JSON array, parallel to prompts
    clusters     TEXT DEFAULT '', -- JSON array, parallel to prompts: cluster label per question
    created_at   REAL,
    frozen_at    REAL
);
```

`product_id` is removed. `clusters` is new: a human-readable label per question (e.g. `"gentle cleansers"`, `"vitamin C serums"`) used to group questions in the onboarding UI and the dashboard.

SQLite cannot drop a `UNIQUE` constraint in place — recreate the table.

### 4.2 `mentions` — record *which* product matched

Current (`db.py:74`) has `is_theirs INTEGER` and `is_their_brand INTEGER`. Add one column:

```sql
ALTER TABLE mentions ADD COLUMN matched_product_id INTEGER;  -- NULL when not one of theirs
```

Keep `is_theirs` as "matched any product in this catalog" so existing queries in `scoring.py` and `insight_panels.py` keep working. `matched_product_id` is what makes per-product scoring possible.

Index it — this column is joined on for every per-product panel:

```sql
CREATE INDEX IF NOT EXISTS idx_mentions_product ON mentions(matched_product_id);
CREATE INDEX IF NOT EXISTS idx_mentions_answer  ON mentions(answer_id);
```

### 4.3 `scores` — split into catalog-level and product-level

`scores` is currently keyed `scan_id INTEGER PRIMARY KEY` (`db.py:82`). Keep it as the **catalog-level** aggregate for the scan. Add a second table:

```sql
CREATE TABLE IF NOT EXISTS product_scores (
    scan_id         INTEGER NOT NULL,
    product_id      INTEGER NOT NULL,
    visibility      REAL,   -- position-weighted, stored but never displayed
    appearance_rate REAL,   -- THE headline number: % of answers naming this product
    avg_rank        REAL,
    sov_pct         REAL,
    detail          TEXT,   -- JSON: per-question breakdown for this product
    PRIMARY KEY (scan_id, product_id)
);
```

`scores.detail` keeps the shared, catalog-wide content: `sov_rows`, `other_pct`, `brands`, `noise_points`. Competitor and brand leaderboards are properties of the scan, not of one product, and must not be duplicated per product.

### 4.4 `scans` — record real cost

`scans.cost_cents` exists and is **always 0.0**. Populate it. See §6.

---

## 5. Code changes, file by file

### 5.1 `mvp/app/questions.py` — generate clusters from a catalog

Current: `generate(product, currency=None)` at `questions.py:110` takes one product record, builds a brief with `product_brief()`, returns `[(question, tag), ...]`.

Target: `generate_clusters(products, currency=None, target=None)`.

- `products` — the store's full product list (rows from the `products` table).
- `target` — desired number of question clusters. Defaults to `config.QUESTION_CLUSTERS`. **Never hard-code a number.**
- Returns `[(question, tag, cluster_label), ...]`.

Changes to the prompt in `INSTRUCTIONS` (`questions.py:16`):

- The input becomes a **catalog summary** rather than one product: distinct `product_type` values, price range per type, common materials/options, and a sample of titles per type. Do not paste 86 full product records — that is the token cost this whole change exists to avoid.
- The model's job becomes: identify the distinct **buyer-question clusters** this catalog competes in, then write one question per cluster.
- Every existing rule in `INSTRUCTIONS` stays: shopper phrasing, never name the brand or product, base it on real catalog facts, never invent features, always write prices with a currency symbol or omit prices entirely.
- The `TAGS` list (`best`, `budget`, `spec`, `use case`, `compare`) stays. Extend `SCHEMA` with a `cluster` string field per question.

Keep `product_brief()` — it is still useful for a per-product deep-dive later. Add `catalog_brief(products, currency)` alongside it.

**The number of clusters should be driven by the catalog, not forced.** A single-category store might genuinely need 8; a broad homeware catalog might need 40. Let the model propose a count within a floor and ceiling from config, and show the merchant what it chose.

### 5.2 `mvp/app/db.py` — rekey the question functions

- `get_prompt_set(product_id)` (`db.py:157`) → `get_prompt_set(store_domain)`. Also JSON-decode the new `clusters` field.
- `save_prompts(product_id, prompts, tags=None)` (`db.py:168`) → `save_prompts(store_domain, prompts, tags=None, clusters=None)`.
- **The freeze check at `db.py:174` must be kept exactly as it is.** `if existing and existing["frozen_at"]: return existing` is the rule that keeps the trend chart meaningful. Do not add a force flag, an override parameter or an admin path around it.
- `freeze(prompt_set_id)` (`db.py:207`) is unchanged.
- `brand()` and `save_brand()` (`db.py:186`, `db.py:199`) are unchanged.
- `save_catalog()` (`db.py:129`) is unchanged.

### 5.3 `mvp/app/scan.py` — match against the whole catalog

This is the core change. Three functions.

**`match()` at `scan.py:99`** — currently `match(mention, product, aliases) -> (is_theirs, is_their_brand, score)`.

Target: `match_catalog(mention, products, aliases) -> (matched_product_id, is_their_brand, score)`.

- Keep the existing matching logic per product exactly as written — the URL-handle exact match, the brand-alias check, the title-word overlap scored against both `product["title"]` and `core_title(product["title"])`, the `config.TITLE_MATCH_THRESHOLD` cut-off, and the rule that brand words inside a title don't prove a product match. It works; it has been reviewed against real answers in `mvp/app/SCAN-REVIEW-2026-09-17.md`.
- Run it across every product and **return the single best scoring match above the threshold**, not all matches. A mention is one product.
- `is_their_brand` becomes true if the brand matched, regardless of which product won — unchanged in meaning.
- Return `None` for `matched_product_id` when nothing clears the threshold.
- Compute `on_their_site` and the `_host()` parse **once per mention**, not once per product. With 86 products this loop runs 86× per mention, ~12 mentions per answer, 60+ answers per scan. Precompute the per-product word sets once per scan and pass them in, rather than recomputing `set(words(title))` inside the loop.

**`start(product_id)` at `scan.py:130`** → `start(store_domain)`.

- `db.get_prompt_set(store_domain)`.
- The "already running" guard, the `db.freeze()` call, the token generation and the `total = len(prompts) * config.RUNS_PER_QUESTION` calculation all stay.
- Pass `store_domain` to `_run` instead of `product_id`.

**`_run(scan_id, product_id, prompts)` at `scan.py:148`** → `_run(scan_id, store_domain, prompts)`.

- Load **all** products for the store: `SELECT * FROM products WHERE store_domain=?`.
- `brand_aliases()` (`scan.py:80`) currently takes a product to reach `store_domain` and `vendor`. Change it to take `store_domain` plus the product list, unioning distinct vendors. Its logic is otherwise unchanged.
- Country lookup and `config.BUYER_COUNTRY` fallback are unchanged.
- In `job()`, the `INSERT INTO mentions` gains `matched_product_id`.
- **`answers` insertion must stay exactly where it is** — the answer is written the moment it arrives, before extraction, so a crash or a credit failure loses nothing already paid for.

**Status reporting — fix a real bug while you are here.** Scan 4 in the existing database reports `status='done'`, `done=25`, `total=25` while storing only **23** answers, because `done` is incremented in the `finally` block whether or not the call succeeded. A scan that lost calls currently reports as complete and its percentages are computed over a smaller base than it claims.

Fix: add a `status='partial'` state when `answered < len(jobs)` but more than half succeeded. Surface it on the dashboard as a visible caveat on that scan's numbers. Keep `'failed'` for `answered == 0` or `answered < len(jobs) / 2`. Do not silently drop the distinction.

### 5.4 `mvp/app/scoring.py` — score every product, plus the catalog

`score(scan_id)` at `scoring.py:58` currently computes one product's numbers from `is_theirs`.

Target: `score(scan_id)` computes, in one pass over the scan's mentions:

1. **Per product** (for every product with at least one mention): `appearance_rate`, `avg_rank`, `sov_pct`, `visibility`, and the per-question breakdown. Write to `product_scores`.
2. **Catalog aggregate**: appearance rate for "any of this catalog's products named", plus the shared `sov_rows`, `other_pct`, `brands`, `noise_points`, `borderline`. Write to `scores`.

Preserve exactly:

- `credit(rank) = 1 / log2(rank + 1)` (`scoring.py:26`) — still computed, still stored, still never displayed.
- `_cluster()` (`scoring.py:30`), the loose competitor grouping by brand key plus Jaccard ≥ 0.5 on title words. ChatGPT rarely writes a product name the same way twice; this is what stops one competitor appearing as six.
- `TOP_PRODUCTS = 6`, `TOP_BRANDS = 8`.
- `noise_points = round(300.0 / n)` — the measurement-noise band shown under the chart. With fewer answers per product this number gets **larger**, and it must be recomputed from the real per-product answer count, not the catalog total. A product only appearing in 3 clusters has a wider noise band than one appearing in 12. Do not hide this.
- `borderline` — the count of brand-matched-but-not-product-matched mentions above 0.3. Under catalog-wide matching this becomes more informative, not less.

`_cluster()` currently skips mentions where `is_theirs` is set. Keep that: the merchant's own products must not appear in their own competitor list.

### 5.5 `mvp/app/app.py` — routing and the onboarding flow

Routes are plain dict lookups at `app.py:559-561`.

```python
ROUTES_GET  = {"/": view_latest, "/new": view_home, "/brand": view_brand,
               "/store": view_store, "/product": view_product, ...}
ROUTES_POST = {"/store": act_store, "/brand": act_brand,
               "/api/questions": api_questions, ...}
```

Changes:

| Current | Target | Note |
|---|---|---|
| `view_product(q)` `app.py:322` | `view_catalog(q)` | Step 2 becomes "confirm your catalog", not "pick one product" |
| `api_questions(q, form)` `app.py:449` | keyed by `store_domain` | Calls `questions.generate_clusters()` |
| `api_scan_start(q, form)` `app.py:481` | takes `store_domain` | Calls `scan.start(store_domain)` |
| `app.py:514` `SELECT * FROM products WHERE id=?` | load the catalog | In the scan-status/result path |
| `view_result(token, query)` `app.py:509` | gains an optional `product` parameter | `/r/<token>` = catalog view; `/r/<token>?product=<id>` = one product |

`/r/<token>` dispatch is at `app.py:616`, splitting on `/`. The `answers` and `citations` sub-paths keep working; they gain an optional `product` query parameter that filters to one product's mentions.

`view_home`, `act_store`, `view_store`, `view_brand`, `act_brand`, `api_brand` are **unchanged** — pasting a URL, fetching a catalog and confirming brand identity all work the same way.

### 5.6 `mvp/app/onboarding.py` — one screen changes

`page(title, body, active, actions)` at `onboarding.py:8` renders the four-step indicator. **The step count, the styling and the indicator stay.**

Step 2 changes from "pick one product" to "confirm your catalog". The product grid, its styling, the search box and the card layout are all reused. What changes is what selection means: instead of choosing one product, the merchant confirms the catalog and optionally excludes product types they don't want scanned.

Step 3 (questions) keeps the same editable, tagged list. It gains **grouping by cluster label** — questions listed under their cluster heading. Same components, one level of grouping.

**Keep brand setup before catalog selection, and questions on a separate final screen.** That order was set deliberately.

### 5.7 `mvp/app/dashboard.py`, `insight_panels.py`, `citation_panel.py`

These are the five lines of product coupling in the presentation layer:

| File | Line | Current | Change |
|---|---|---|---|
| `dashboard.py` | 83 | `p = db.one('SELECT * FROM products WHERE id=?', (ps['product_id'],))` | Load the catalog, or the selected product when `?product=` is present |
| `app.py` | 514 | same query | same |
| `insight_panels.py` | 36 | builds the single `own=True` entry | Build one entry per catalog product that was mentioned |
| `citation_panel.py` | 23 | `own = canonical(product['url'])` | Match against any catalog product URL |
| `citation_panel.py` | 50 | `own_domain = (product['store_domain'] or '').lower()` | Read from the store, not a product |

`insight_panels.period_context(ps, p, query)` at `insight_panels.py:75` pools data across scans in the selected period. Its signature changes from a product to a store plus an optional product filter. **Every new panel must still pool over `period_context()` rather than reading the single scan in the address.**

`filter_bar()` (`insight_panels.py:143`), `buckets()` (`:86`), `thumb()` (`:120`), `box()` (`:138`) are unchanged.

**New: a catalog view.** The Overview gains a product table — each row a product, with its mention rate, average position and share of voice, sorted by mention rate. Clicking a row drills into that product's existing dashboard, which is the current single-product view essentially unchanged. Products with zero mentions must be listed with a real zero, not hidden. That list is the merchant's actual problem and the reason to buy the product.

`sov_drawer.render()` is unchanged — it already renders a competitive set.

---

## 6. Cost tracking (currently missing entirely)

`scans.cost_cents` is `0.0` on every scan. Token counts and web-search counts **are** already collected, by `llm.Usage` (`llm.py:38`) into `scans.model_versions` as JSON: `{"models": [...], "input_tokens": N, "output_tokens": N, "searches": N}`.

Add a price table to `config.py` and compute real cost at the end of `scan._run()`.

Prices per 1M tokens, from developers.openai.com/docs/pricing, **read 18 September 2026 — re-check before trusting**:

| Model | Input | Cached input | Output |
|---|---|---|---|
| `gpt-5.6-sol` (what `gpt-5.6` resolves to) | $4.00 | $0.40 | $20.00 |
| `gpt-5.6-terra` | $2.00 | $0.20 | $12.00 |
| `gpt-5.6-luna` | $0.20 | $0.02 | $1.20 |

Web search: **$10.00 per 1,000 calls**, plus search content tokens billed at the model's own input rate. Those content tokens are ~83% of the bill and are already included in `input_tokens`.

**A known limitation to fix while implementing:** `llm.Usage` sums tokens across *both* models into one counter, so answer-model and helper-model spend cannot be separated. Split the counters by model. Without that, any cost figure is an estimate with roughly ±30% error.

Display: cost per scan, and a projected cost per month at the current cadence. Internal-facing is fine — this is for Kelian to see what he is spending, not a customer feature.

---

## 7. Config changes

In `mvp/app/config.py`:

```python
# --- Scan size -------------------------------------------------------------
QUESTION_CLUSTERS_MIN = 8     # floor on clusters per catalog
QUESTION_CLUSTERS_MAX = 40    # ceiling
QUESTION_CLUSTERS     = 20    # target; UNVERIFIED — see §1
RUNS_PER_QUESTION     = 5     # consider 3; halves cost, widens the noise band
PARALLEL_CALLS        = 5
```

`QUESTIONS_PER_PRODUCT` is removed. `RUNS_PER_QUESTION`, `PARALLEL_CALLS`, `BUYER_COUNTRY`, `TITLE_MATCH_THRESHOLD`, `DB_PATH`, `PORT` and `api_key()` are unchanged.

---

## 8. Suggested build order

Each step should leave the app runnable.

1. **Schema + migration.** Back up `produkto.db`. Rebuild `prompt_sets`, add `mentions.matched_product_id` and its indexes, add `product_scores`. Verify the app still starts.
2. **`match_catalog()` in `scan.py`.** Change the function, keep `start()` on a single product for now. Test it against the 98 answers already stored — re-matching costs no API calls, which is the point of `answers` being append-only. Confirm known matches still resolve (`Frontier Cleanser`, `Skin Frontier Cleanser`, `Amalfi Vitamin‑C Face Oil` with a non-ASCII hyphen) and check whether any of the other five Clubhouse products now match in scans 1–3.
3. **`scoring.py`.** Per-product plus catalog aggregate, run against the re-matched existing data. Still no API calls.
4. **`questions.generate_clusters()`** and `catalog_brief()`. Costs a few cheap helper-model calls.
5. **`db.py` rekeying**, then `scan.start(store_domain)` and `_run`.
6. **Onboarding step 2 and 3.**
7. **Dashboard catalog view and drill-down.**
8. **Cost tracking.**
9. **Scan status `partial`.**

Steps 1–3 are verifiable with **zero API spend** against data already in the database. Do them first.

---

## 9. Rules that must not be broken

1. **Never invent data.** No fabricated trend points, no backfilled zeros, no placeholder competitors, no sample products presented as real. Empty states say so.
2. **Questions freeze at the first scan.** No override, no force flag, no admin bypass.
3. **`answers` is append-only.** Re-parsing existing answers must never require another API call.
4. **Never state the number of questions or runs in user-facing copy.** Use percentages, never "X of 25".
5. **No Daily grouping.**
6. **No "measured via the ChatGPT API" labelling on the dashboard.**
7. **Product level, not brand level.** The brand card is identity only.
8. **Never print, echo, log or commit the OpenAI key.** It lives in `mvp/app/.env`.
9. **Keep domain terms and existing copy.** This is a refactor of what data is gathered, not a rewrite of the product's voice.
10. **The cluster count is an untested assumption.** Keep it configurable and out of any external-facing claim.
11. **Report honestly.** If a step is skipped or a test fails, say so rather than reporting completion.

---

## 10. Known open questions

These are genuinely unresolved. Do not resolve them by guessing — flag them.

- **How many question clusters does a real catalog actually need?** Never measured. Sets the entire cost case.
- **Does a merchant want multiple AI engines?** Assumed, never asked. The MVP measures ChatGPT only, by a decision recorded in `DECISIONS.md` on 17 Sep 2026.
- **Automatic scans spread across the week** were made a launch requirement on 17 Sep 2026, costed against the per-SKU design. That decision's arithmetic no longer holds and the entry needs revisiting by Kelian — not by the implementer.
- **Gemini and Grok per-answer costs** quoted in `UNIT-ECONOMICS-2026-09-18.md` are estimates. Verify before using them anywhere.
- **Does catalog-wide matching raise the false-positive rate?** Matching one mention against 86 products instead of 1 gives 86 chances to clear the threshold. `TITLE_MATCH_THRESHOLD` (currently 0.6) may need raising. Measure the borderline count before and after on the existing 307 mentions.

---

## 11. Verification

Existing tests: `mvp/app/test_dashboard.py` (9 tests) and `mvp/app/test_onboarding.py`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s mvp/app -p 'test_*.py'
```

Both will need updating for the new signatures. Add coverage for:

- `match_catalog()` returns the **best** match, not the first, when several products score above the threshold.
- `match_catalog()` returns `None` when nothing clears the threshold.
- A product mentioned in zero answers gets a `product_scores` row with `appearance_rate = 0`, and is displayed, not hidden.
- `save_prompts()` still refuses to change questions after `frozen_at` is set.
- `noise_points` is computed from the per-product answer count, not the catalog total.

Running the app: `python3 mvp/app/app.py`, then <http://localhost:8010>. `/new` is the start page. If the port is busy: `lsof -ti tcp:8010 | xargs kill`. **Restarting kills any scan in progress** — check `scans.status` first.

**The OpenAI account was out of credit as of 18 September 2026.** Live scans will fail with `HTTP 429: You have no credits remaining` until it is topped up. Steps 1–3 of the build order do not need credit.
