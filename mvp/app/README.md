# Produkto MVP v1

## Accounts — 28 September 2026

Every page now needs a sign-in. Invite-only: no public sign-up, because each
store costs real money in daily scans.

- **First admin:** `python3 mvp/app/app.py --create-admin you@example.com` (asks for a password; run it once, on each machine/server).
- **Inviting a brand:** sign in as admin → `/admin` → email + plan (Starter 25, Growth 75, Custom) → send the one-time link. The brand sets a password and lands in onboarding.
- **What a customer sees:** only the store they add (one store per account by default). Any other store, scan, product or `/admin` / `/costs` returns Not found. The admin sees everything, including the Clubhouse Skin demo.
- **Plan cap:** saving more buyer questions than the plan allows is refused with a message. The cap follows the store's owner, so it holds for daily scans too.
- On the server set `PRODUKTO_BASE_URL=https://app.getprodukto.com` (invite links) and `PRODUKTO_SECURE_COOKIES=1` (HTTPS-only cookies).

- **Forgotten password:** the sign-in page tells customers to email kelian@getprodukto.com. At `/admin`, "Reset link" next to their account gives a one-time link (24 hours). Setting a new password signs them out everywhere else. No email is sent by the app yet.
- **Backups (server):** `produkto-backup.timer` copies the database nightly at 02:30 to `/opt/produkto/backups/produkto-YYYY-MM-DD.db.gz` (integrity-checked, 14 days kept). Restore: stop `produkto`, `gunzip -c <file> > /opt/produkto/app/produkto.db`, fix ownership, start. These live on the same server, so they don't survive the server itself failing.

Code: `accounts.py`; the sign-in and store-access check runs first in `Handler._accounts` (`app.py`). Tests: `test_accounts.py`.

## Visual system — 22 September 2026

The workspace now shares one navy and soft-blue visual system across Overview,
Buyer questions, Answers and Citations. Merchant identity is separated from the
page title; each destination has its own title and explanatory line. Catalog
images are larger, evidence uses continuous rows, and typography, controls and
surfaces share consistent sizing. Empty category labels are omitted from product
rows. The chart watermark is hidden. Setup surfaces use the same visual language.

`workspace.css` is the presentation layer loaded after the existing component
styles. Chart data and scan logic are unchanged. Ranking scroll selection reads
the rendered row height rather than assuming a fixed pixel size. Verified with
the existing 62-test suite and desktop/mobile browser checks against stored data.

## Prompt creation — 21 September 2026

The Buyer questions page now includes a Types summary (Organic, Product-specific,
Competitor comparison), name filter and Create prompts menu. Custom multiline
prompts, CSV/TXT uploads, AI generation and keyword-guided generation all go
through an editable review with explicit product relevance before saving.
Intents and a prompt explorer are not included.

`prompt_creation.py` owns the workflow. New prompts create an immutable superset
of the previous prompt set; old scans retain their original set and evidence.
The next scan uses the newest version. Until then additions appear as ready for
the next scan. Trend periods remain within one prompt version. Running scans
block saves, stale browser versions require a refresh, and duplicates and
out-of-catalog product IDs are rejected. No scan is started by adding prompts.

The database migration removes the one-set-per-store constraint, preserving IDs
and taking a `.pre-prompt-versions-*.bak` backup first. Scan workers and recovery
read their own frozen version. AI options call the helper model only when the
user requests generation; browser verification uses an isolated test store and
stubbed generation. Validation: 58 tests, plus desktop/mobile checks covering
custom save, CSV review, generation review, search, and dialog keyboard close.

One product in, its AI visibility insights out.

```
paste Shopify URL → pick one product → buyer questions are written for it
                  → Run insights → ~1–2 min → dashboard
```

Built 16 Sep 2026 from [`../PLAN.md`](../PLAN.md). Standard library Python only, so there's nothing to install.

---

## First run

1. **Add your keys.** Copy `.env.example` to `.env` in this folder, then paste your OpenAI key after `OPENAI_API_KEY=` and your Apify token after `APIFY_TOKEN=`. The `.env` file stays on your computer.

   Two keys, because they do different jobs. **Apify** buys the answers themselves, by scraping — every question goes to all three engines: ChatGPT ($0.005 an answer), Google's AI Overview ($0.002) and Perplexity ($0.013), so $0.020 per question per run. Which engines a scan buys is `SCAN_ENGINES` in `config.py`; the dashboard's engine selector filters what you already collected. **OpenAI** runs the helper model that writes the buyer questions and reads each answer into a product list; that part is a fraction of a cent. Buying the answers from OpenAI instead costs about $0.096 each, which is the same measurement for nineteen times the money — see [`../../DECISIONS.md`](../../DECISIONS.md), 20 Sep. To switch back, set `ANSWER_SOURCE = "openai"` in `config.py`.
2. **Check the key and models work.** This makes two tiny calls:
   ```bash
   python3 mvp/app/app.py --check
   ```
3. **Start the app** from the `AEO-for-eccomerce-brands` folder:
   ```bash
   python3 mvp/app/app.py
   ```
   Then open <http://localhost:8010>. Press Ctrl-C to stop it.

Port 8010, not 8000: the old 29 Aug prototype (`mvp/server/`) was still running on 8000.

---

## What each file does

| File | In plain language |
|---|---|
| `app.py` | The web app: every page, and the dashboard. |
| `catalog.py` | Downloads a Shopify store's public product list. Reused from the 29 Aug prototype. |
| `questions.py` | Asks an AI model to write the buyer questions for **the chosen product**, from its own listing. No templates. The page shows a loading state while the questions are written. |
| `llm.py` | Talks to OpenAI. Retries rate limits and hiccups, and stops with a readable message on a bad key or model name. |
| `scan.py` | Asks ChatGPT each question several times with web search on, turns each answer into a ranked list, and decides which mention is your product. |
| `scoring.py` | Turns the stored answers into the dashboard numbers. |
| `db.py` | One SQLite file, `produkto.db`, created on first run. |
| `config.py` | Every setting: models, runs per question, match strictness. |
| `replay.py` | **Development only.** Rebuilds a past scan's numbers from answers already paid for, so building the dashboard costs nothing. Never imported by the app. |
| `bench_cost.py` | **Development only.** Measures what the cost settings save and whether they change the answer. |

## The dashboard

- **Visibility score (/100):** how often the product is named, weighted by position. 1st = 1.00, 2nd = 0.63, 3rd = 0.50 and so on. Below it: the % of answers that name the product, the average position when named, and the % of answers that name the brand at all.
- **Trend:** one point per scan. Day one shows "Reading 1". "Run a new scan" adds the next point. There's no automatic weekly job, because recurring jobs are out of scope.
- **Share of voice:** your product's share of all products recommended. Competitors are whatever ChatGPT actually named.
- **Positioning:** the brands ChatGPT recommends instead, with average position and % of answers, and your product pinned on top.
- **By question:** how the product did on each question.
- **Every answer:** a link to the raw ChatGPT text and how each answer was read. Use it to check the matching.

## Rules built in

- **Questions lock at the first scan** (enforced in `db.py`). After that, "Write new questions" disappears, so every scan in the trend asks the same questions.
- **Answers are never edited or deleted.** Re-scoring never costs another API call.
- **No fake results.** If a call fails, it's left out and the page says so. If more than half fail, the scan is marked failed and nothing is scored.
- **Percentages, not "X of 25"** anywhere on screen.

## Matching: how "your product" is decided

A mention counts as your product if:

- it links to the product's own page, **or**
- it names your brand **and** most of the product's name. The colour/variant suffix is ignored, so "Men's Tree Runner - Blizzard" matches "Tree Runner".

If it names your brand but a different product, it counts as a brand mention, not your product. Close calls are flagged under the dashboard with a link to the answers.

**Check this on the first real stores.** Read the answers page for 2–3 products and confirm the "(yours)" marks are right before trusting any score. `TITLE_MATCH_THRESHOLD` in `config.py` is the dial.

---

## Known limits / guesses

- **Model names are a guess at what chatgpt.com serves.** `gpt-5.6` answers and `gpt-5.6-luna` reads the answers. Both were checked against OpenAI's model list on 16 Sep 2026, but OpenAI doesn't say which model ChatGPT uses. Change them in `config.py`. `--check` shows the exact version OpenAI ran.
- **The API isn't identical to chatgpt.com.** It has a different system prompt and no memory. The dashboard labels itself "Measured via the ChatGPT API".
- **Cost isn't shown in dollars yet.** Web searches are counted (in the footer), and the tokens used are stored in the `scans` table. Check OpenAI's pricing page for current rates before quoting a cost.
- **Scores will usually be low** (0–5). That's the honest reading, not a bug.
- **Tested only with stand-in OpenAI replies** (clearly labelled test data, separate database) against the real allbirds.com catalogue. The flow, scoring maths and dashboard were verified. Real answers haven't been run yet.

## Dashboard design update — 17 September 2026

The overview follows Searchable’s panel layout: Visibility and Product rankings above Average position and Share of voice. Product rankings include verified product photos when available, with initials as the fallback. The photo source URLs and verification date are recorded in `product-images.json`; images are loaded from the original sites, not invented.

Visibility supports Over time and By question views, hover and keyboard details, and a Compare products switch for the three highest-visibility competitors. One scan displays one real point; the question view compares saved answers. Product ranking scores use the existing weighting formula and share-of-voice grouping. No stored scores or answers are rewritten.

The Share of voice panel has a coloured donut and a percentage legend. Average position links to each question’s saved answers. The answer browser retains question, ownership and text filters, readable formatting, sources and original text.

Presentation lives in `dashboard.py`, `insight_panels.py` and `dashboard.css`; routing remains in `app.py`. No extra Python dependencies or model calls are needed to view results. The existing question about “around 39” remains unchanged.

Checks: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s mvp/app -p test_dashboard.py -v`. Browser checks at 1440px and 375px covered image loading, comparison switching, question charts, keyboard tooltips and horizontal overflow. Images for other products may need to be added to the verified image list; unverified products retain initials.

Product citations now separates the selected product’s own page from other cited URLs associated with its identified recommendations. Counts use actual saved API citations, deduplicate repeated links per answer and remove tracking parameters. Each source links to its exact saved answers. Brand-only citations are excluded. The first-scan chart explicitly explains that a second scan is needed; real rising and falling history segments are green and red.

The dedicated **Mentions & Citations** tab (`/r/<token>/citations`) shows two side-by-side trend charts above the source list. Mentions measures the percentage of answers recommending the selected product. Citations separates its own page from other identified product listings. History uses completed scans with the same frozen questions, up to the viewed scan. No earlier zeroes are added. Rising/falling primary lines use green/red; other listings have a separate dashed line. Each chart includes a readable history table. Desktop/mobile layout, answer links, saved rates (20%, 8%, 16%), and rising/falling/flat/empty states were checked.

Update: Mentions & Citations now uses counts throughout its charts, totals, source rows and history tables. A mention counts once per answer recommending the product; a citation counts each distinct product-page URL once per answer. Own-page and other-listing citations remain separate. Current saved counts are 5 mentions, 2 own-page citations and 4 other-listing citations. Overview visibility now defaults to By question; Over time remains available. This supersedes the earlier percentage-only display guidance for the citations tab.

Overview visibility now defaults to **By date**, showing the combined score for each saved scan. By question remains a secondary view. This supersedes the previous default.

The overview visibility chart is now exclusively date-based, with exact scan timestamps in the tooltip. The question-view switch was removed; buyer-question details remain below.

A single-scan visibility chart includes an explicitly labelled, dashed illustrative zero baseline. It is presentation only, has no invented date, and is excluded from saved data, history and change calculations. With multiple scans only real trend segments are shown.

## Headline number change — 17 September 2026

The Overview's main number is now **"Mentioned in X% of answers"**, with **average position** shown beside it. The Visibility chart, Product rankings ("Mentioned in" column, ranked by it) and the scan-history table all use this mention rate. The position-weighted score is still calculated and saved (`scores.visibility`, and `weighted` in `insight_panels.py`) but is no longer displayed. Reason and date are in `../../DECISIONS.md`. Tests: 6 pass, including one that checks a lower position doesn't change the mention rate.

## Share of voice panel — 17 September 2026

Clicking the Share of voice donut, a slice, a legend row or "See details →" slides in a panel (`sov_drawer.py`, styles at the end of `dashboard.css`), modelled on Searchable's Share of Voice view but for the selected product:
- Cards: your share of voice (with change since the previous scan), your rank among all recommended products, and how many competing products ChatGPT named.
- Chart: share of voice per scan for your product and the top 5 competing products. It animates in and has a labelled date axis. With one scan it uses the dashed "Start · not measured" line; nothing is invented.
- "All competitors" table with search, SOV, change ("—" until a second scan) and a share badge. A clicked competitor's row is highlighted.
The panel always describes your product. It closes with ×, the breadcrumb, a click outside, or Esc.

## Period filter bar — 17 September 2026

Above the Overview panels: a **date range** (Last 7 / 30 / 90 / 365 days, or a custom From–To range, plus Reset and "Save as my default") and a **Group by** menu with **Daily (the default), Weekly, Monthly and Quarterly**. Daily is the default because `scheduler.py` runs one scan per store per day, so each day's scan is its own point; the other groupings pool those daily scans. A day with no scan is a gap, drawn dashed, never a zero. The choice is kept in the page address (`?range=30&group=day`) and, if "Save as my default" is on, in the browser.

The period controls the Visibility chart and the "Mentioned in" / average position numbers above it. All answers from scans inside the same week, month or quarter are pooled: answers naming the product ÷ all answers. Periods without a scan show as empty ticks with no point, and nothing is filled in. With a single scan, the dashed "not measured" line is still used. **Update, same day:** every Overview panel now follows the period: Visibility, Product rankings, Average position, Share of voice (including its slide-out panel) and the Buyer questions table. `period.py` works out the range and the weeks/months/quarters. `insight_panels.period_context()` pools all answers from the scans in the period. Changing the filter reloads the page so the server recalculates everything, and a saved default is added to the page address on load. In the Share of voice panel, the chart is one point per week/month/quarter, and "Change" compares the latest period with a scan against the one before it. Periods with no scans show "No scans in this period". The Answers and Mentions & Citations tabs still show the viewed scan only. Tests: 8 pass.

**Answers and Mentions & Citations follow the period too (17 Sep).** Both tabs show the same filter bar. The Answers tab lists every answer from the scans in the period, and its question/result/search filters keep the period. Mentions & Citations totals cover the whole period, its two trend charts use one point per week/month/quarter, and "change" compares the last two periods with scans. Every internal link (tabs, "View answers", position rows, citation links) carries the period, via `carry()` in `insight_panels.FILTER_SCRIPT`, which all three tabs share. The chart code in `CHART_SCRIPT` reads the period from `window.PK`. Tests: 9 pass.

**Removed at Kelian's request:** the "date · ChatGPT API · web search" line under the tabs, and the "Measured via the ChatGPT API…" line under the answers. The same sentence was then removed from the collapsed "Measurement details" on the Overview.

## Currency and country — 17 September 2026

Every Shopify store publishes `/meta.json` with its own currency and country (Clubhouse Skin: GBP, GB). `catalog.store_meta()` reads it, `db` stores it on the `stores` row, and:

- **Buyer questions include the currency** ("a vitamin C face oil under £50"), never a bare number. The first scan's question "best gentle face cleansers around 39" was read by ChatGPT as an age; that is what this fixes. If a store publishes no currency, the model is told to leave prices out of the questions rather than guess.
- **Scans ask from the store's own country** (`user_location` on the web-search tool), unless `BUYER_COUNTRY` in `config.py` is set.

Questions already frozen are untouched, so the Frontier Cleanser scan keeps its original five.

## Top cited domains — 17 September 2026

A ranked table on the Mentions & Citations tab (`citation_panel.domains()` / `domain_panel()`), modelled on the same panel in a competitor's product: #, domain (with its own favicon, letter fallback), Frequency (share of answers in the period citing it) and Cites (total links). Your own site is highlighted "Your site"; a domain matching a recommended brand gets that brand's name beside it. Top 10 shown, "View all N domains" expands. It follows the period like every other panel, and uses citations already saved with the answers, so it costs no API calls.

First real data (2 scans, 50 answers): aad.org 46%, cetaphil.com 22%, cerave.co.uk 20%, clubhouseskin.com 18%.

## Onboarding: brand card, editable tagged questions, steps — 17 September 2026

From `mvp/ONBOARDING-INSPIRATION-2026-09-17.md` (items 1–4), adapted to Produkto: product-level measurement, with a brand section for **identity, not analysis**.

- **"Your brand" card on the product page.** Brand name, "Also known as" aliases, store country and currency, all pre-filled from the store's `/meta.json` and Shopify vendor, all editable, saved on change (`/api/brand` → `db.save_brand`). The aliases feed `scan.brand_aliases()`, which decides whether a mention counts as the merchant's product — the most error-prone number in the tool. Changes apply to future scans; saved mentions are never re-judged.
- **Questions are tagged and editable.** The generator now returns a tag per question (best / budget / spec / use case / compare, stored in `prompt_sets.tags`). Before the first scan a merchant can edit, delete or add questions; saves are queued so a delete can't be overtaken by an earlier edit. After the freeze the list is read-only and "Write new questions" disappears.
- **Three-step indicator** (Store → Product → Questions) on all three pages.

Deliberately not copied from Promptwatch: testimonials/logo wall (no customers — would be invented), the "About you" step, personas, tone of voice, brand descriptions, and asking for competitors up front (ours are discovered from the answers).

## PromptWatch-inspired onboarding layout — 17 September 2026

The live setup at `/new` now uses a shared split layout: narrow form, logo and segmented progress, a persistent explanatory panel, and sticky Back/Next controls. The sequence is **Welcome → Brand Hub → Choose your product → Prompts to Monitor**. Brand identity is confirmed and saved before selecting a product or generating questions. The first page says “Welcome” and asks for brand name and website. Brand aliases have individual editable rows. Product selection requires Next, and prompts have their own tagged cards.

`onboarding.py` and `onboarding.css` contain the frame and styles; dashboard presentation stays separate. The layout follows the supplied PromptWatch screenshots while keeping fields relevant to product measurement. No testimonials, agency/account setup, brand personas or invented competitors were added. Existing questions remain frozen after the first scan. Returning to a previously loaded store preserves confirmed aliases, country and currency.

Checks: 9 dashboard tests and 4 setup tests pass. A separate browser checked all four pages at 1440px and 375px, product selection, empty search, adding/removing aliases, and frozen prompts. No live scan was started during verification. Local screenshots are in `../qa/`.

## Competitor logos — 17 September 2026

Rankings used to fall back to initials for almost every competitor, because `product-images.json` only covers a handful of hand-verified product photos. Now `insight_panels.brand_site()` works out the brand's own domain (the link ChatGPT gave when it points at the brand's site, otherwise the brand name as .com — retailer links like Boots or LookFantastic are skipped so their logo never appears next to someone else's product), and `icons.py` fetches that site's declared `<link rel="icon">`, falling back to `/favicon.ico`.

Icons are cached on disk under `mvp/app/icons/` and served from `/icon?d=<domain>`; failures are cached as `.miss` files and retried after a week. Nothing is sent to a third-party favicon service. Fetching uses a browser user-agent because several brand sites (Aveeno, La Roche-Posay, Boots) refuse anything else. A brand with no usable logo keeps its initials tile. First real result: 37 of 48 ranked products show a logo.

## Six-product competitor comparison — 18 September 2026

Onboarding now follows Store → Brand → Catalog → Competitors → Questions.
`competitor_setup.py` suggests up to three competitors using a web-enabled research call and structured extraction, based on six selected catalog products. Suggestions are cached by store and selected product IDs; their usage is stored separately from scan spend. Users review six paired names and product URLs, select candidates, add their own competitors, or skip. Up to five competitors can be saved, all compared with the same six merchant products. Suggestions are not measured results.

`competitor_comparison.py` adds a chart for each saved competitor to catalog Overview. It reuses processed answers in the dashboard period, restricted to questions relevant to the selected merchant products. Both groups use the identical answer denominator. Visibility counts distinct answers with at least one selected product; average position uses the first selected product per answer. Comparison share counts distinct selected products per answer across only the two groups. The original all-competitor share-of-voice donut is unchanged. Empty periods and no recommendations have explicit missing states. Matched-answer links provide review evidence. URL or brand-and-name matching is local; ambiguous name matches are left unassigned. Existing answers, mentions and scores are not rewritten.

Validation: 30 automated tests pass, including duplicate recommendations, period emptiness, ambiguous names, saved selections, cached suggestions and no-AI manual setup. Generation tests use stubbed provider responses. Isolated Chrome checks covered manual setup on desktop/mobile, six pair fields, dashboard integration, no horizontal overflow and no browser errors; no live suggestions or scan calls were made during those checks.

Competitor selection is now required during onboarding (18 Sep correction). The skip link and dashboard setup card are removed. Questions redirect to Competitors until a valid selection is saved; the scan endpoint also blocks incomplete setup and routes the user back. Existing scans remain readable without fabricated competitor selections. Regression suite: 31 tests pass.

## Dashboard design review implementation — 19 September 2026

The primary chart and metric selectors now share one full-width card. Responsive plot dimensions preserve readable labels; mobile charts and ranking tables scroll within their cards. Navy controls, the soft page glow and muted comparison fills remain. Chart titles, scope captions and keyboard/tap tooltips follow the selected metric. Position uses dots with an explicit lower-is-better caption. Share of voice uses one decimal throughout the headline and donut.

The primary comparison consistently groups discovered competitors by brand, using the same selected-period answers in all views. This replaces the previous latest-scan brand fallback. The own series covers selected products; competitor series cover mentioned products from each brand. Saved six-versus-six comparisons remain separate, using their existing shared-question calculation. No stored evidence is rewritten. Missing time buckets remain on the axis and line segments do not bridge unmeasured buckets.

Your products now follow the main chart and any saved selected-competitor comparisons. Mobile product rows are compact; buyer questions initially show a short preview and expand through the button or navigation link. Rankings and share of voice sit together; supporting typography and image fallbacks are standardised. Catalogue wording and citation breakdowns are simplified. Catalog-level share-of-voice details no longer claim a product rank. Invalid display brand names use a neutral fallback.

Validation: 32 Python tests pass, including a new pooled-brand test checking repeated products do not inflate answer frequency. Chrome checks at 1135px, 1440px and 390px covered all metric modes, focus tooltips, drawer close, questions expansion, empty periods and a synthetic missing-week history. No browser errors or page-level horizontal overflow. The mobile overview measured 5,541px versus 8,873px before. Screenshots: `../qa/design-refresh-2026-09-19/`. No new scan or model call was made. PromptWatch authenticated access remains unavailable; this implements the screenshot-based review.


## Free rebuilds while building — 19 September 2026

Buying answers is the whole cost of a scan: about 10c an answer, about $5 a
catalog scan. What ChatGPT said is then stored forever and never changes.
Everything after that — reading an answer into a product list, deciding which
mentions are the merchant's, and every number on the dashboard — is arithmetic
over text already on disk.

`replay.py` re-runs that arithmetic instead of re-buying the answers.

| Command | What it redoes | Cost |
|---|---|---|
| `python3 replay.py --list` | shows every stored scan | $0 |
| `python3 replay.py --score all` | every dashboard number — run after changing `scoring.py` or `insight_panels.py` | $0 |
| `python3 replay.py --rematch all` | which mentions are theirs, then rescores — run after changing `match_catalog`, `TITLE_MATCH_THRESHOLD` or the brand aliases | $0 |
| `python3 replay.py --extract 5 --yes` | re-reads stored answers into product lists — run after changing `EXTRACT_INSTRUCTIONS` | ~$0.02 per scan |

Verified on 19 Sep against all five stored scans: `--score all` reproduced every
stored number byte-identically, and `--rematch all` changed 0 of 472 mentions.
If either ever reports a change you did not intend, that is a regression in the
code you just edited, not in the replay.

**Replay is a development tool and must stay one.** `app.py` does not import it
and must not. When a merchant clicks "scan", `scan.start()` buys real answers
from the API — that is the product, and it does not change when this ships or
when testers use it. Replay only re-reads scans that really happened; it never
invents one, and `--extract` is the only path that calls the API at all.

`--extract` rewrites the `mentions` table for the scans named, so it backs the
database up to `produkto.db.pre-replay-<time>.bak` first. It never touches
`answers`, which stay append-only — they are the only record of what the engine
actually said.

One supporting change in `evidence.py`: the answer cache is now keyed on the
database file's timestamp as well as the in-process revision counter, so a
rewrite from `replay.py` shows up in a running app on reload, without a restart.

## Share of voice over time — 19 September 2026

The Share of voice tab used to draw one bar per brand for the whole period, so
the dates were invisible. It is now a **100% stacked column per date**, modelled
on the PromptWatch reference: dotted guides at 25/50/75/100%, one column per
bucket of the period filter, and a neutral grey **Every other product** band on
top so every column totals 100%.

Visibility-by-competitor and Average position stay as bars — they are not a
split of a fixed whole, so stacking them would mean nothing.

- Shares are **pooled by weight**, not averaged: a bucket's share is its
  mentions over its own total mentions, so a bucket holding a big scan and a
  small one is not distorted. That needed raw counts per scan (`mt`, `sv` in
  the chart payload) — a stored percentage cannot be pooled.
- A lone measured bucket gets the same empty-calendar padding as the visibility
  trend (`padAroundSingle`, now shared by both date charts). The padding is
  display only: no scan, value or column is invented for an empty date.
- Brand colours come from the same `brand_colors` map as every other chart, so
  a brand is one colour across the trend, the bars, the legends and here.
- The tooltip shows the real scan date, not the bucket start, when a bucket
  holds exactly one scan.

Built and verified entirely against the stored 18 Sep scan. No API spend.

## Trend gaps and tooltips — 19 September 2026

Two changes to **Visibility over time**, following the PromptWatch reference.

**Gaps are now drawn, dashed.** Before, two readings with an unmeasured week
between them were simply not joined, so a series looked like scattered dots. A
dashed segment (`.plot-gap`) now connects them: it says the two readings belong
to one series without claiming anything was measured in between. Consecutive
readings stay solid.

**No week-on-week change sentence.** The "↘ −9 percentage points vs the
previous week with a scan" line under the chart was removed on Kelian's
instruction. The lines carry the movement and the tooltip gives exact figures
for any date. The "First reading · your trend will build as you scan" note
stays, because it explains a chart that has no line yet.

**Tooltip headings match the axis tick.** A weekly bucket's tick reads
"14 Sep" while the scan inside it ran on 18 September, and the tooltip used to
show the scan date as its heading — the two dates looked like a contradiction.
The heading is now the bucket ("Week of 14 Sep 2026") with the reading's own
date beneath it ("Scanned 18 Sep"). Both date charts share the `subline` helper.

**Markers appear on hover only.** At rest the trend is bare lines, as in the
reference. Hovering a date drops a marker onto every series at that date,
alongside the vertical guide and the tooltip. The one exception is a single
reading: it has no line to draw, so its markers stay visible or the chart would
be blank.

**Coincident markers stack, they are never spread.** Brands that share a
percentage on the same date sit on top of each other, exactly on their date.
An earlier version nudged them apart horizontally; that was rejected. Nothing
is hidden, because the date tooltip lists every brand and its percentage — four
brands tied at 9% read as one dot and four tooltip rows.

**Tooltips fit the card.** With six brands the trend tooltip ran past the bottom
of the panel and the last rows were unreadable. Every competitor row repeated
"All mentioned products", so that sub-label is now shown only on your own row,
and `.chart-tooltip.compact` tightens the row spacing. Same treatment on the
stacked share-of-voice tooltip.

### Previewing a design with more dates than exist

One scan makes every date-based chart hard to judge. To see a layout with more
readings, copy `produkto.db` to a scratch file, add scans to the **copy** built
from samples of real stored answers, and run the app against it on another port
(`config.DB_PATH` and `config.PORT` are both overridable before `app.main()`).
Reach any period with `?range=custom&from=YYYY-MM-DD&to=YYYY-MM-DD&group=week`,
which sidesteps "today" on both the server and the browser.

**Never do this to `produkto.db`.** Preview scans are fictional dates and must
not enter the real history or any screenshot shown to a merchant.

## Chart hover — 19 September 2026

Hovering any column now focuses it: the column keeps full colour and gains a
soft shadow, its value and brand label darken to navy, and every other column
fades to 42%. 160ms transitions, disabled under `prefers-reduced-motion`.
Applies to all three column charts — visibility bars, share-of-voice stacks and
position dots.

The old effect was `brightness(.97)`, which is not visible to a human eye.

Two things it needed:

- **The value label's inline `fill` had to go.** It was set in the `style`
  attribute, which outranks any stylesheet, so the label could never react. The
  colour is now a presentation attribute and the inline style carries only the
  font size that `draw()` rescales.
- **Every column got a transparent hit area** spanning its whole slot. A tall
  bar is easy to hover; the position chart's 6px dot is not, and hovering above
  a short bar did nothing at all.

Dimming uses `:has()`, so the rest of the chart only fades while a column is
genuinely hovered. Where `:has()` is unsupported nothing fades and the chart
still works.

## Tooltip placement — 19 September 2026

The chart tooltip was pinned to `right:24px`: it covered right-hand columns,
and for the rest it sat a long way from the mark being read. It now follows the
hovered mark — 18px to its side, flipping to the mark's other side when it
would overflow, clamped inside the plot. One `placeTip(cx)` helper, called by
all three charts.

`placeTip` must be called **after** the content is in and `shown` is set: a
`display:none` element measures as zero wide, so the flip decision would use
the wrong width.

The SVG `<title>` elements were also removed from the columns. The browser
rendered them as a second, native tooltip that floated over the custom one with
the same text in it. Each column is still named for assistive tech by
`role="button"` plus `aria-label`, which is what a screen reader reads anyway
when both are present.

## Headline numbers: average of dates, and latest — 19 September 2026

Following the PromptWatch reference, where "Visibility over time" reads `avg`
and "Visibility" reads `latest`, and the two carry different figures.

- **Visibility over time** is now the **mean of the dates drawn on the chart**,
  each date counting once. Add the plotted points up, divide by how many there
  are, and you get the number in the card.
- **Visibility** is now the **newest date in the period**, labelled `latest`,
  not a pooled period figure.

It previously pooled every answer in the period — 16 mentions over 143 answers
= 11% — while the five plotted points averaged 12%. Both are defensible, but
pooling weights a date by how many answers it happens to hold, which is not
what the chart draws, and the label said "avg". A half-failed scan storing 30
answers instead of 55 would have quietly counted less than a full week while
showing at full height on the line.

Both cards are recomputed in `updateHeadline()` whenever the period changes, so
they stay in step with the chart rather than with the server's first paint.
Average position stays pooled across all answers in the period — it is a
position, not a rate, and averaging per-date averages would distort it.

## Product rankings beside the chart — 19 September 2026

Following the PromptWatch reference, where the brand list sits to the right of
the chart under the same KPI strip. The **Product rankings** panel moved out of
the two-column grid lower down and now shares a row with **Visibility over
time** inside the analysis card (`.analysis-main`, 1.6fr / 1fr).

- The grid below now holds **Average position** and **Share of voice** only.
- The panel keeps its existing content and rules: competitors capped at eight,
  the merchant's own products always shown at their true rank (Frontier
  Cleanser still appears at #26 on 2%).
- Rows are compacted for the narrower column — smaller thumbnail, product name
  clamped to two lines, `SOV` column hidden, `Mentioned in` and `Avg. pos.`
  kept. The list fills the chart's height with its footer pinned to the bottom.
- It stacks below the chart under 820px.

The chart SVG's `min-width` went from 620px to 420px. At 620px the two columns
could not both fit in the app's preview pane and the layout silently stacked.

The panel kept the title **Product rankings**: "Your products" is already the
heading of the searchable catalog table further down the page.

## Rankings isolate a line — 19 September 2026

Hovering a row in **Product rankings** leaves only that brand's line drawn in
the trend; every other line and legend entry fades. Matches the reference,
where hovering a brand isolates its line.

A ranking row is a *product* and a chart series is a *brand*, so the mapping is
resolved server-side: `series_index` maps each tracked brand to its plotted
index and each row carries `data-si`. Own products map to series 0, the
catalog total. Rows outside the plotted cohort get no `data-si` and simply do
not highlight — the chart draws six series, and the list can run longer than
that.

Each line carries `data-si` too, so `focusSeries()` can dim by series rather
than by colour.

Watch the legend selector: each legend item is a `<span>` containing another
`<span>` for the label, so `#chart-legend span` returns twice as many nodes as
there are series and the highlight lands one series early. It must be
`#chart-legend > span`.

## Legend locks a line — 19 September 2026

Clicking a legend entry locks that brand's line; clicking it again releases.
The locked entry is underlined and `aria-pressed="true"`; entries are keyboard
reachable and respond to Enter and Space.

Locking and the rankings hover share one state. `applyFocus()` does the
dimming, `focusSeries()` is the preview, and a preview that ends falls back to
whatever is locked rather than to nothing — so hovering a row while a line is
locked previews that row and returns to the lock on the way out.

The legend is rebuilt on every `drawTrend()`, so the handlers are attached
there and the lock is re-applied at the end. It survives switching to another
KPI tab and back. If the tracked cohort ever shrinks below the locked index the
lock is dropped rather than pointing at a series that no longer exists.

## Rankings level with the KPI strip — 19 September 2026

The analysis card is now two columns for its full height, matching the
reference where the brand list's header is the fifth cell of the KPI row:

- **Left** (`.analysis-left`): the four KPI figures, then the chart.
- **Right** (`.analysis-right`): a `.rank-head` cell carrying "Product
  rankings" and the period's total product mentions, then the list.

The ranking card's own `insight-heading` is hidden — `.rank-head` is its title
now, and showing both put the words on screen twice. The table's sticky header
row is raised to 57px so it occupies the same band as the chart's heading and
the two columns stay level.

`.analysis-main` holds **four grid children**, not two nested columns: the KPI
strip and `.rank-head` share grid row 1, the chart and the list share row 2.
Row 1 stretches to its tallest cell, so the two headers are the same height
without either padding itself out to guess the other's. An earlier version
reserved two label lines in `.rank-head` to match the wrapped KPI labels, which
left a visible gap between "Product rankings" and its figure.

On narrow screens the grid collapses to one column and `order` restores the
reading sequence: KPIs, chart, rankings header, list.

## The rankings list is the colour key — 19 September 2026

The colour key under the chart axis is gone. Each row in **Product rankings**
now leads with its brand's dot, the way the reference keys its brand list —
and since every line's colour is already sitting next to a named product, the
strip of swatches under the axis was saying it twice.

- Row dots come from the same `brand_colors` map the chart draws with, passed
  through `series_color`. A product outside the plotted cohort gets a pale grey
  dot rather than a wrong colour.
- **Clicking a row locks that brand's line**; hovering still previews it. The
  lock moved off the legend with the legend. Rows are keyboard reachable and
  carry `aria-pressed`; two rows of the same brand both mark as locked, which
  is correct — they are the same line.
- The share-of-voice chart keeps exactly one key: **Every other product**. That
  band is the only colour with no row of its own.

## Two panels removed — 20 September 2026

**Average position (Q1–Q11) and the Share of voice donut are gone**, with the
`searchable-grid` that held them. Both restated numbers that already live
elsewhere on the page.

- *Average position* showed each buyer question's position as `Q3`, `Q7`…
  The **Buyer questions** table lower down shows the same figure with the
  question's actual text beside it, plus the mention rate and links to the
  answers. Its own footer already linked there.
- *Share of voice* showed 4.9% (in the KPI strip), the split by product (a
  column in the **Your products** table) and the split over time (the main
  chart, when the Share of voice KPI cell is selected).

**Rescued:** the share held outside the tracked cohort, which only the donut
showed. It is now the Share of voice cell's sub-label — `59% untracked` — on
its own line under the figure, since inline it either wraps mid-label or runs
off the cell.

That figure is **not** the donut's old "Other products 74.0%". The donut
measured everything outside the merchant's catalog and the top five
*products*; this measures everything outside the catalog and the five
*brands* the chart plots, so it is smaller and it matches what the chart
actually draws.

**Deleted with them:** `sov_drawer.py` (the donut was its only entry point),
the Python `buckets()` helper and the `COLORS` / `color_map` per-product
palette, all of which existed only to serve those two panels.

`body:has(.searchable-grid)` and `main:has(.searchable-grid)` set the page's
width and background. With the grid gone they key off `.product-head`, which
marks the same pages and already keys the palette. The dead `.donut-*`,
`.position-*` and `.searchable-grid` rules are left in the stylesheet; nothing
matches them.

## Scroll-driven product comparison — 20 September 2026

Product rankings now offers **All products / My products** and a **7, 14, 21,
or 28** product limit. My products is the onboarding selection, including
products with zero recommendations. Six rows fit in the scroll area; scrolling
updates the trend, latest visibility, share-of-voice and position charts to those
six individual products. Rows from the same brand remain separate products.

The chart and ranking use the overview's common saved-answer scope. Share of
voice retains every recommendation in its denominator, with the remaining share
shown as Every other product. Headline KPIs still describe the selected catalog.
No new scans or API calls are needed.

Verified: 34 automated tests; browser checks for 28 rows, scrolling to rows
23–28, six onboarding products, all chart modes, and mobile overflow.

## Dead CSS pruned — 20 September 2026

`dashboard.css` 55,616 → 51,413 bytes, **74 selectors removed**: the donut,
the per-question position panel, the `searchable-grid` that held them, the
`legend-toggle` entries from the old chart key, and `mini-stat`.

Method, because delete-by-search on a 55k stylesheet is where this goes wrong:

1. Every candidate class was checked against the files that generate HTML.
   Two survived that check and stayed: **`chart-summary`** is used by
   `citation_panel.py`, and **`trend-series-label`** still labels the
   share-of-voice chart's "Every other product" key.
2. Pruning runs **per selector, not per rule**, so `.chart-legend i,.donut-key>i`
   keeps its live half. Same for `.chart-summary span,.share-intro>span`.
3. Comments are lifted out of each prelude as whole units first. The first
   attempt did not, cut two comments in half, and left the file with two
   unclosed `/*` — which would have commented out everything after them. The
   script now asserts comment and brace balance before writing.
4. Verified by probing every tab under both stylesheets and diffing the
   computed size, colour, font, padding, border, grid and flex of each
   element: 26 on the Overview, 11 on Mentions & Citations, 27 on Answers
   (the filter bar, the response cards, the result labels, the feedback
   controls). Every probe identical on all three.

**The test suite cannot catch a CSS regression**: it checks the HTML the server
returns, not how it renders. The before/after probe is what stands in for that.

`@keyframes` blocks are copied verbatim; `from`/`to` are not selectors.

### Product visibility bars match rankings — 20 September 2026

Comparison bars and their tooltips now use the ranking's selected-period rate.
Previously the bar substituted the newest date's rate, so Frontier Cleanser
could show 0% beside a 2% ranking. The catalog KPI labelled latest keeps its
existing meaning. Verified all six selected products' rendered bar labels
against their ranking rows and Frontier Cleanser's 2% tooltip; 34 tests pass.
