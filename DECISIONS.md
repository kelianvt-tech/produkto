# DECISIONS

Append-only log. Each entry: the decision, the date, why, and what would reverse it.

---

## 2026-09-17: The MVP measures ChatGPT only

**Decision:** The MVP asks ChatGPT (via the OpenAI API with web search) and no other AI engine.

**Why:** It keeps the MVP simple, and ChatGPT is the engine buyers use most. The database already records which model gave each answer, so adding an engine later is a small change, not a rebuild.

**Would reverse it:** Merchants in interviews asking for Perplexity, Gemini or Google AI results before they would use or pay for it.

---

## 2026-09-17: Automatic scans, spread across the week, are required before the MVP goes to real users

**Decision:** Before anyone outside the team gets the MVP, scans must run automatically. Each product's questions are asked in small batches spread across the week, not as one big scan repeated every day. It is not being built now; it is a launch requirement.

**Why:** Searchable runs its questions for each brand every day, so its users get a trend line without doing anything. A tool that needs a manual click for every data point loses to that. Spreading the questions across the week collects more answers per week than one scan, gives a smoother trend, and costs less per day.

**Scope change:** The project `CLAUDE.md` lists "no recurring jobs" as out of scope. For the MVP, this decision overrides that rule, by Kelian's choice.

**Open before building it:**
- Scans only run while the app is running. For real users, the app needs to live on a server, not a laptop.
- Cost per product per week is unknown until real scan costs are read from the OpenAI usage page.
- The trend chart has to switch from one point per scan to one point per week (or per day), built from the spread-out answers.

**Would reverse it:** Real users being happy with manual scans, or running costs per product being too high for the price.

---

## 2026-09-17: The headline number is "mentioned in X% of answers", not a position-weighted score

**Decision:** The dashboard's main visibility number is the share of ChatGPT answers that name the product. Average position is shown next to it as its own number. The position-weighted score (1st = 1.00, 2nd = 0.63 …) is still saved, but no longer shown.

**Why:** A weighted score mixes "how often" and "how high" into one figure, so a merchant can't tell which is the problem. Searchable's visibility figure is a plain mention rate, so merchants who have used it will read ours as a percentage anyway.

**Would reverse it:** Merchants asking for a single combined score, or finding position more important than mention rate.

---

## 2026-09-20: Two per-question signals — topic demand shown, source concentration held back

**Decision:** The buyer-questions tab gains a **Topic demand** column: monthly Google search volume for the question's topic cluster, from DataForSEO, read from a local cache. A second signal, **source concentration**, is built but deliberately not shown anywhere in the MVP.

**Why topic demand:** Our questions are generated from the catalog, and the page says so. A merchant therefore has no way to tell which of eleven 0% questions is worth fixing first — they all look identical. Demand makes the remediation pitch concrete: fix the pages behind the questions buyers actually ask. It is the missing half of the prioritisation.

**What the number honestly is:** search volume for the *topic*, not the question. Nobody sells per-prompt volume for AI assistants — OpenAI doesn't publish it, and every competitor's "Volume" column is topic-level keyword data however it's labelled. Google Ads also caps a keyword at 80 characters and 10 words, which rules out sending the question itself. The column is named "Topic demand" rather than "Volume" for that reason, and the header tooltip states it.

**Cost shape:** DataForSEO charges per *request*, not per keyword, so all of a store's topics go in one call. Page loads never call the API — they read the cache only, because a dashboard that spends money on every refresh can't be left open. Fetching is an explicit CLI step (`volume.py --store <domain>`). With no credentials set, the column does not render at all rather than showing empty bars.

**Why concentration is held back:** it measures how far the citations behind a question collapse onto a few domains (Herfindahl over cited hosts). Unlike demand it needs no external data — we already store every citation. But at five runs per question the sample is thin, and it is easy to misread as a prediction that remediation will work, which nobody can support. It needs several scans of evidence before it goes in front of a merchant. Run it with `concentration.py`.

**Rejected:** a Difficulty column. With catalog-derived questions a merchant can't choose an easier fight, so it adds a second estimated number without changing an action.

**Would reverse topic demand:** a merchant saying the topic-level figure is too loose to act on, or DataForSEO returning no data for most clusters (11 topics priced, 0 readings so far — unproven until credentials exist).
**Would reverse holding concentration back:** two or three scans showing the reading is stable per question, plus a merchant conversation where "who owns this answer" is the question being asked.

**Reversed the same day, 2026-09-20:** topic demand is removed. Kelian does not want a second paid dependency on top of the per-scan OpenAI cost. The column, `volume.py`, the `topic_volume` table, its CSS and its tests are deleted; the illustrative sample readings are gone with them. Source concentration stays — it costs nothing and runs off citations we already hold.

Free routes exist if this comes back: a Google Keyword Planner CSV export (free with an Ads account, but bucketed ranges and manual), or Google Trends (relative interest only, unofficial endpoints). Neither was built. What was learned and is worth keeping: DataForSEO charges per request rather than per keyword, `tasks[].status_code` can fail inside an HTTP 200, and the language code must follow the store's country or a Spanish catalog gets priced on English demand.

---

## 2026-09-20: Buy ChatGPT answers by scraping (Apify), not through the OpenAI API

**Decision:** Scans stop buying answers from the OpenAI Responses API and start buying scraped ChatGPT answers from Apify's `apify/chatgpt-search-scraper`. The OpenAI API stays in the code for the helper model (question generation and extraction), which is 0.4% of the bill and is not affected.

**Why:** cost, and it is not close. Measured cost per answer is **$0.096 via the API** (scan 5, $5.30 billed) against **$0.005** scraped on Apify's entry paid tier, falling to $0.002 at the top tier. That is roughly 19x. It moves 50 questions scanned daily across three engines from about $1,296/month to about $99/month, and it is what makes daily multi-engine scanning possible at all.

**It also explains the competition.** PromptWatch's tiers decode to 1 sample per prompt per model per day (`competitors/LANDSCAPE.md` §"The sampling-rate finding"); their $579 tier buys 42,000 responses/month, which costs $4,032 at our API rate and ~$210 scraped. Their pricing only works on scraped answers. We were solving the wrong problem when we spent 19 September optimising token settings.

**The API was never actually chosen.** The 17 September entry above records "measures ChatGPT only (via the OpenAI API with web search)" but argues only ChatGPT-vs-other-engines; the API sits in a parenthesis and was never weighed against scraping. `mvp/PLAN.md:50` noticed the API is "close to but not identical to chatgpt.com" and resolved it by labelling the page.

**What the 5-question test on 2026-09-20 actually showed** (Clubhouse Skin scan-5 questions, one scraped run vs the stored API runs, ~$1):

| Question | API brands per run | Scraped |
|---|---|---|
| 1990s golf caps | 5–7 | 6 |
| Cotton cap under £30 | 1–3 | 9 |
| Skincare under £40 | 5–6 | 3 |
| Natural glow | 0–3 | 0 |
| Cleans without stripping | 0–2 | 1 |

Citations come back structured (title + url per source), so extraction is unaffected. **Stated precisely: the data is comparable in brand coverage and better on one question, where the scrape returned ChatGPT's shopping carousel — product names, prices and merchants — which the API does not return at all.** That carousel is the surface Produkto is about and is a real gain, but it appeared in 2 of 5 questions. "Way better data" is not yet supportable as a claim to anyone outside this project; "same coverage, plus the shopping carousel, at 1/19th the cost" is.

**Known regression, accepted, to be fixed after the switch:** the actor's input schema is `queries` and nothing else — no country, no location, no proxy. The scraped answers came back priced in euros and one said "if you're in France". `llm.ask_buyer_question()` currently sets `user_location` from the store's country, and `catalog.store_meta()` reads the store's currency for the questions (17 Sep rule). Scraping loses both. Kelian's call on 2026-09-20: switch first, solve geography after, because the cost difference dwarfs it.

**Other things not yet known:** what Apify's paid plan costs per month on top of per-answer pricing; whether the scraper's throughput holds at 13,500 answers/month (the test ran ~48s per query); whether Apify's supply can be cut off by OpenAI, and what the fallback is if it is.

**Would reverse it:** the geography gap proving unfixable for a merchant outside the scraper's default region; Apify's answers drifting from what a real buyer sees; or the supply becoming unreliable enough that scans fail. The OpenAI path stays behind a config switch so reversing is a one-line change, not a rebuild.

---

## 2026-09-21: Every scan asks all three engines — ChatGPT, AI Overview and Perplexity

**Decision:** a scan buys every buyer question from three engines instead of one. The dashboard gains an engine selector (PromptWatch-style checkboxes: Select all, ChatGPT, AI Overview, Perplexity) that filters every tab. Engine is stored per answer, so the filter is a fact about the record rather than a setting.

| Engine | Apify actor | Price/answer, BRONZE |
|---|---|---|
| ChatGPT | `apify/chatgpt-search-scraper` | $0.005 |
| AI Overview | `apify/google-ai-overviews-scraper` | $0.002 |
| Perplexity | `apify/perplexity-search-scraper` | $0.013 |

**Why the cost is acceptable:** $0.020 per question-run for all three. At 20 questions x 5 runs, weekly, that is **$9.32/month per customer — against $43/month for ChatGPT alone on the OpenAI API**. Measuring three engines is 4.6x cheaper than measuring one used to be. Verified live on 2026-09-21: a real 2-question, 1-run, 3-engine scan billed $0.0425, against $0.04 predicted.

**All three actors take the same input** (a newline-separated `queries` string, nothing else) **and return the same shape** (`{query, text, sources[{url,title}]}`), so one collector serves all three. This was the main unknown and it resolved in our favour; if an actor changes shape, `apify_answers.collect()` is the single place to fix.

**AI Overview is treated as allowed to stay silent** (`may_be_empty` in `config.ENGINES`). Google shows no overview for many searches and the actor only bills for captures, so a missing answer there is a finding about the buyer's experience, not a broken scan. Without this, almost every scan would be marked `partial` and a real signal would read as a false alarm.

**What the first real 3-engine scan showed, and it needs watching:** on two broad advice questions, AI Overview answered both but named **no buyable product at all** — "use a gentle cleanser", "let me know". ChatGPT named 7 and Perplexity 8 on the same questions. So AI Overview visibility can read 0% for the merchant *and* every competitor. The dashboard now says "No products recommended" instead of showing a bare 0%, because the two mean different things and only one is the merchant's problem. **This is two questions on one catalog — not enough to generalise.** Product-shaped questions ("best vitamin C serum under £40") may well name products there. Check on the next catalog before drawing any conclusion.

**Cadence, considered and not decided:** daily 1-run scanning costs $13.08/month and gives 7 runs per weekly point; **weekdays-only 1-run costs $9.33/month — a penny more than weekly-5-runs — for the same 5 runs per weekly point, spread over 5 days instead of fired in one burst**, plus 21 trend points a month instead of 4.3. Better sampling for the same money. Not adopted, because there is no scheduler and recurring jobs are out of scope; revisit when there is one. Note that under any 1-run cadence an individual scan is a single run, whose top-3 ranking the 19 Sep all-hands found to be close to a coin flip — pooled weekly points are sound, single-scan rows are not.

**Would reverse it:** Perplexity's actor becoming unreliable (it is the likeliest to break — a third-party scraper's listing notes Perplexity began blocking shared proxy IPs in August 2026) or its $0.013 dominating the bill; AI Overview proving to never name products, which would make it $0.002 spent on nothing. Any engine can be dropped by removing it from `config.SCAN_ENGINES`; answers already collected from it stay readable.

**Unverified:** the BRONZE prices for Perplexity and AI Overview are the store's published figures and one live run, not a reconciled Apify invoice. Check the billing page before quoting them.

---

## Daily scanning, one run a day — 2026-09-22

**Decision.** `config.RUNS_PER_QUESTION = 5 → 1`, and a scheduler starts one scan per store per day. This settles the cadence left open in the 2026-09-21 entry above, and picks daily over the weekdays-only option costed there.

**Why now.** Kelian wants a fresh data point on the trend chart every day, as PromptWatch and Peec show. Daily was previously blocked on "there is no scheduler"; there is one now (`mvp/app/scheduler.py`).

**Cost.** ~$13/store/month at 20 question clusters, all three engines, one run — the figure already costed in the entry above. Measured against scan 7: $0.0070/answer all-in, of which extraction is 4%. Perplexity at $0.013/answer is ~65% of the bill; dropping it from `SCAN_ENGINES` would cut the cost to about a third.

**Sampling.** A week now carries 7 draws instead of 5, each on its own date. The caveat from the 19 Sep all-hands still stands and is now load-bearing rather than hypothetical: **a single scan is one run, whose top-3 ranking is close to a coin flip.** Daily *points* are therefore noisier than the weekly pooled points were. Raised with Kelian on 2026-09-22 along with a rolling-window alternative; he chose daily points to match competitors. Do not re-litigate — but keep competitor rankings pooled over the selected period rather than read off a single day.

**Verification that unblocked it.** The scraped path was marked "never run end to end". It has been: scan 7 (three engines, 163/165 answers, $1.15) against scan 5 (OpenAI, same 11 prompts, $5.30). Own-product visibility agreed and was *steadier* scraped — 9% on all five runs, against the API's 9,9,9,9,18%. Competitor brand sets overlap only 18%, but each path agrees with itself just 36% (API) and 19% (scraped), and cross-path 15%, so the divergence is non-determinism rather than a broken scraper.

**Design choices inside the scheduler.** A store's slot hour is a hash of its domain within `SCAN_WINDOW_START/HOURS`, so stores spread across the window and keep the same slot daily, which makes yesterday-vs-today a fair comparison. Due-ness is judged on when a scan *started*, so a running or failed scan still consumes the day — **a failed scan is not retried the same day**, because a retry would buy a second set of answers for one date and put two points on one day. A gap in the line is the honest result.

**Would reverse it:** the daily points reading as visible noise to a merchant (fall back to plotting a rolling window while still collecting daily); Apify rate-limiting or per-run overhead making one-run-a-day cost more than the batch math predicts; a paying customer with 40 clusters making $25/month uncomfortable at their price.

**Not yet done:** the dashboard still has no Daily grouping — `group=day` in the period bar and `buckets()`/`axisBuckets()` in `insight_panels.py`. Until that ships, daily scans accumulate but the chart still pools them weekly.

---

## 2026-09-28: Sales motion is demo → payment → self-serve onboarding

**Decision:** Brands book a demo through the website (Calendly). On the call Kelian walks them through Produkto using **Clubhouse Skin** as the demo catalog, explaining how the same dashboard would look for their brand. A brand that pays receives the **onboarding link** and sets itself up: brand name, store website, then the onboarding steps (Store → Brand → Catalog → Topics → Questions), and from then on uses the dashboard itself.

**Why:** Kelian's choice. The product is complete enough to demonstrate on a real catalog, and a paying brand should get the tool itself rather than a service where Kelian runs scans on its behalf.

**What this changes:** It supersedes "Kelian runs Produkto on a brand's behalf" and "send scans cold, no ask attached" as the sales motion in `CLAUDE.md`. It also means the `CLAUDE.md` out-of-scope items **hosted deployment, login and multi-tenancy** become required **before the first paying customer receives the link**, because:
- the app runs on Kelian's laptop at `localhost:8010`, which a customer cannot reach, and daily scans only run while that laptop is awake;
- there are no accounts, so anyone with the link would see every store in the database (Clubhouse Skin and all test catalogs), including via "Switch catalog";
- scan costs (~$13/store/month at current settings) are paid from Kelian's API/Apify accounts.

**Not decided yet:** whether payment comes before or after onboarding. (Price: see the pricing entry below.)

**Would reverse it:** demos converting poorly while brands ask for done-for-you work instead of a tool; or hosting and accounts costing more to build and run than early customers pay.

---

## 2026-09-28: Pricing to test in demos — three plans, priced by prompts

**Decision:** Scan costs are absorbed into the subscription (no pass-through). Plans are priced by number of prompts (buyer questions), following the competitor shape (Peec-style tiers), but with fewer prompts per euro because our per-answer cost is higher.

| Plan | Price | Prompts | Our scan cost | Share of price |
|---|---|---|---|---|
| Starter | €89/mo (~$104) | 25 | ~$16 | ~16% |
| Growth | €249/mo (~$291) | 75 | ~$49 | ~17% |
| Custom | ~€2.50 per prompt/mo, minimum 150 prompts | brand chooses | $0.65/prompt | ~22% |

All plans: unlimited products, daily scans, all three engines (ChatGPT, Perplexity, Google AI Overview). Unlimited products is the checkable difference from Glara, which caps products per tier.

**Why:** Cost is ~$0.65 per prompt per month (daily, 3 engines, 1 run, Apify Bronze — $13 ÷ 20 prompts). Copying the competitor allowances outright (50/150/350 prompts at €85/€205/€425) would put scan cost at 33–46% of the price before Apify's plan fee and hosting. Competitors likely buy answers far cheaper (own scrapers, volume) — our cost is a scale problem, not a product flaw. Keeping scan cost under ~20% of price leaves room for those unknowns. Starter sits near Peec's €85 so we don't read as expensive; Custom is priced per prompt so no brand size can lose money.

**Guardrail:** scan cost stays under ~15–20% of a customer's price. If a customer breaches it, adjust prompts or runs, don't absorb it silently.

**Levers if margins tighten:** drop Perplexity (~65% of the bill) from Starter; move to Apify Scale ($199/mo, 30% startup discount → ~$139, Silver pricing — check each actor's Silver per-answer rate first) once there are a few paying stores. Business/Gold ($999/mo, ~$0.002/answer) only pays off around 50+ stores, since unused prepaid usage expires.

**Unknown / guesses:** no one has paid at any price — these are demo test prices, not final. Apify plan fee and hosting cost not yet included. Perplexity and AI Overview per-answer prices not yet reconciled against an Apify invoice.

**Would reverse it:** demos showing prospects anchor hard on Peec's larger allowances and balk at 25/75; brands asking for fewer prompts at a lower price; or real invoices putting cost per prompt materially above $0.65.

**Update, same day (2026-09-28): prices shown in dollars — Starter $99/mo, Growth $299/mo** (rounded from ~$104 / ~$291), because customers are mostly American. Scan cost share barely moves (~16% / ~16%). Published on its own page, `produkto-site/dist/pricing.html`.

**Update, same day (2026-09-28): Growth set to $297/mo** (Kelian), making the per-question price identical to Starter ($3.96). No volume discount between Starter and Growth.
