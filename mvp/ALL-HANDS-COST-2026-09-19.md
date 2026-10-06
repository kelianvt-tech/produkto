# All-hands: what a catalog scan really costs, and how we get it down

**Date:** 19 September 2026
**Called because:** the 18 Sep catalog scan billed **$5.30** on the OpenAI account against our $5.46 estimate, and the question was raised of whether scanning is simply too expensive to run for multiple products, weekly, across multiple customers.
**Status:** analysis and recommendations. Nothing here is decided. Sections 6 and 7 are what needs a yes or no.
**Supersedes the cost sections of:** `UNIT-ECONOMICS-2026-09-18.md` (written before the rearchitecture shipped; its per-SKU cost tables no longer describe the code).

---

## 0. The headline, before the meeting notes

**The $0.88-per-product figure is an artefact of a one-product-in-six catalog, and it does not generalise.** The rearchitecture landed on 18 September. Scans are no longer per-SKU. Scan 5 asked **11 questions covering the whole catalog** and matched every answer against all six products. The same 11 questions would have covered an 86-product catalog for the same $5.30.

Cost now scales with **how many buyer questions a catalog competes on**, not with how many SKUs it has:

| Catalog | Cost per scan (20 clusters, 3 runs) | Cost per product |
|---|---|---|
| 6 SKUs | $5.96 | $0.99 |
| 86 SKUs | $5.96 | $0.069 |
| 300 SKUs | $5.96 | $0.020 |
| 2,000 SKUs | $5.96 | $0.003 |

**The second thing:** at current, untouched settings — 20 question clusters, 5 runs, weekly, ChatGPT only — a customer costs **$43/month** in API spend. Against a €500/month price that is a 91% gross margin. Before any optimisation, the unit economics already work.

**The thing that is actually bleeding money is development, not customers.** Five scans have been run. Four of them were to look at the dashboard. Every dashboard iteration currently costs $5 and there is no way to re-render a scan without re-buying the answers. That is the fix with the shortest payback in this document, and it is free to build.

---

## 1. Finance — where the $5.30 went

Measured from `mvp/app/produkto.db`, scan 5, priced with `config.PRICES`. Our estimate was $5.46; the bill was $5.30, so the price table is ~3% high — accurate enough to plan on.

**11 questions × 5 runs = 55 answers.**

| Line | Cost | Share |
|---|---|---|
| Input tokens, uncached (`gpt-5.6-sol`) | $3.34 | **61.1%** |
| Web search tool calls (113 × $0.01) | $1.13 | **20.7%** |
| Output tokens, incl. reasoning | $0.88 | **16.0%** |
| Input tokens, cached | $0.09 | 1.7% |
| Helper model (questions + extraction) | $0.02 | 0.4% |
| **Total** | **$5.46** | |

**Per answer: $0.0993.** Per answer the model consumed **19,479 input tokens**, made **2.05 web searches**, and produced **795 output tokens**.

The question "why is it so expensive" has a one-line answer: **we are paying to read the internet.** Nineteen thousand input tokens per answer is not our prompt — our prompt is about twenty tokens. It is the content of the pages the model retrieved, billed back to us at the answer model's full input rate. Tidying prompts saves nothing.

What `UNIT-ECONOMICS-2026-09-18.md` got wrong: it attributed ~83% to input tokens and treated that as unfixable physics. The real split is 61% input / 21% search calls / 16% output, and **§4 shows all three are controllable by parameters we are currently leaving at their defaults.**

---

## 2. Data — how many runs do we actually need?

This is the lever with hard evidence behind it, measured across all five scans in the database.

**Own-product visibility is nearly deterministic.** Across 26 question-sets (5 scans × their questions), the hit/miss pattern was identical across all five runs in **23 of 26 cases**. Three questions ever flipped.

```
[0,0,0,0,0]  ×  9 questions in scan 5     — stable miss
[1,1,1,1,1]  ×  1 question  in scan 5     — stable hit
[0,0,0,0,1]  ×  1 question  in scan 5     — flipped once
```

**Competitor discovery is where the runs earn their keep — and it saturates at three.** Pooling scan 5's mentions:

| | Value |
|---|---|
| Brands appearing in ≥3 of 5 runs ("the stable competitive set") | **18** |
| Found in run 1 alone | 12 (67%) |
| Found in runs 1–2 | 16 (89%) |
| **Found in runs 1–3** | **18 (100%)** |
| New (question, brand) pairs added by run 4 | 13 |
| New pairs added by run 5 | 7 |

Runs 4 and 5 added 20 new pairs and **not one of them was a brand that appeared more than twice.** They are the long tail — noise we then have to filter out of the share-of-voice panel.

**Recommendation: `RUNS_PER_QUESTION` 5 → 3. A 40% cut with no measurable loss on the data we have.**

**The honest caveat:** this is one catalog, eleven questions, one engine, one day. It is enough to act on for the MVP and not enough to write into a pricing page. Re-run the check on the second real catalog before it hardens into a rule.

**What runs must NOT be cut to:** 1. The top-3 ranked set was completely unstable between runs — Jaccard against run 1 hit 0.0 on four of eleven questions. A single run gives a confident-looking ranking that is mostly a coin flip.

---

## 3. Engineering — three parameters we are paying full price to ignore

Verified against developers.openai.com, 19 September 2026.

**a) `search_context_size`.** The `web_search` tool takes `"low"`, `"medium"` or `"high"`; omitting it gives **medium**, which is what we are on. It controls exactly the thing that is 61% of the bill — how much retrieved page content is fed back to the model. There is also a `return_token_budget` parameter on the same tool. `mvp/app/llm.py:141` builds the tool as `{"type": "web_search"}` and sets neither.

**b) `reasoning: {"effort": ...}`.** GPT-5.6 defaults to **medium** effort, and reasoning tokens bill as output at $20/1M. That is the 16% line. Effort also influences how many searches the model chooses to run, so it may pull the search-call line down as well. We set nothing.

**c) `service_tier: "flex"`.** A 50% discount on tokens for slower, best-effort processing. A scan already runs in a background thread with a progress bar, so latency is close to free for us. **Caveats that make this the least certain of the three:** it is in beta, the docs do not confirm `gpt-5.6-sol` is a supported model, they do not say whether built-in tools like `web_search` work under it, and it can return `429 Resource Unavailable` (unbilled) under load. Batch API gives the same 50% and is more established but is a poor fit for an interactive "scan now" button.

**None of these three has been measured.** `mvp/app/bench_cost.py` (written today) measures all of them on real buyer questions and reports both the cost change and how much of the baseline's recommended brand set survives:

```bash
cd "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app" && python3 bench_cost.py --yes --questions 3
```

Upper bound $1.20, and the cheaper arms come in under it. Running it without `--yes` prints the plan and spends nothing.

---

## 4. The stack, with assumptions labelled

| Lever | Effect on $/answer | Evidence |
|---|---|---|
| Baseline, as shipped | **$0.0993** | Measured |
| `search_context_size="low"` | $0.068 | **Assumed −50% input. Unmeasured.** |
| + `reasoning={"effort":"low"}` | $0.059 | **Assumed −60% output. Unmeasured.** |
| + flex / batch 50% on tokens | $0.040 | Published discount; applicability unverified |
| + `gpt-5.6-terra` instead of `-sol` | $0.031 | Published prices; **changes what we measure** |

Monthly API cost per customer, 20 question clusters, ChatGPT only:

| Runs | Cadence | As shipped | + context/reasoning | + flex |
|---|---|---|---|---|
| 5 | weekly | $42.99 | $25.34 | $17.21 |
| **3** | **weekly** | **$25.79** | **$15.20** | **$10.32** |
| 3 | fortnightly | $12.93 | $7.62 | $5.17 |
| 3 | monthly | $5.96 | $3.51 | $2.38 |

Multiply by roughly 4 for four engines. Even the most expensive cell in that table — 5 runs, weekly, four engines, nothing optimised — is ~$172/month, against a €500–1,500 price point.

**The one to be careful with is the model swap.** `config.ANSWER_MODEL` is set to `"gpt-5.6"`, which the API resolves to `gpt-5.6-sol`, the most expensive tier. `-terra` would halve token prices. But the whole premise is measuring what a buyer's ChatGPT actually serves. Measuring a cheaper model measures something nobody experiences. *Against that:* `config.py` already concedes nobody outside OpenAI knows which model chatgpt.com serves, so the fidelity we would be protecting is partly notional. This deserves to be an explicit, logged bet rather than a silent default — and `bench_cost.py` can be pointed at `-terra` to see whether the recommended brand set even changes.

---

## 5. Product — the bill that has nothing to do with customers

Five scans exist. Scans 1–4 were the per-SKU architecture; scan 5 is the only one under the current design. At least four were run to look at the dashboard, not to learn something about a catalog.

**There is no way to re-render a scan without re-buying the answers.** `grep` for `replay`, `fixture`, `offline`, `dry_run` across `mvp/app/` returns one comment in a test file. This is a real gap, and the architecture is already 90% of the way to closing it:

- `answers` is append-only and stores `raw_text` and `citations`. The expensive part is already on disk — **$15 of purchased answers sitting in `produkto.db`.**
- `scoring.score(scan_id)` recomputes every dashboard number from stored mentions. **Costs $0.**
- Re-extraction (re-running the helper model over stored `raw_text`) costs **~$0.02 per scan** — 0.4% of a scan.

So: a `--replay` path that re-scores, and optionally re-extracts, an existing scan turns a $5 dashboard iteration into a free one. It also makes the matching logic testable against real answers, which is how the `TITLE_MATCH_THRESHOLD` check on 18 Sep was done by hand.

Related, and still open from `UNIT-ECONOMICS` §8: **scan 4 reported `done 25/25` while storing 23 answers.** A scan that dies on credit still bills for what it bought and then computes percentages over a smaller base than it claims. `completion_status()` exists now; confirm it actually catches this case.

---

## 6. Go-to-market — does the cost even matter?

Three things follow from the numbers, and one of them argues against optimising at all right now.

**Nothing in this document should delay the validation work.** `CLAUDE.md`'s current priority is 15 conversations and 20 cold audits — not building. A scan at $5.30 is not what is stopping a customer from existing. Optimising a cost base for customers we do not have is the same mistake as building the agent before knowing what to automate. **Do the free items; defer the rest until someone is paying.**

**The per-scan cost is now a sales asset, not a liability.** Cost independent of catalog size is precisely the gap `MEMORY.md` says is our one checkable claim: Glara caps at 20–50 tracked products, Alhena optimises 25–50 product pages a month. We can scan a 2,000-SKU catalog for the same $6 as a 6-SKU one. That is *why* whole-catalog coverage at mid-market price is possible for us and not for them — and it is now a costed statement rather than an assertion.

**Four engines is still an assumption nobody has tested on a merchant.** It multiplies the bill by four and it has never appeared in an interview. It belongs on the interview list before it appears in a build.

---

## 7. What we are actually deciding

**Do now — free, zero risk:**

| # | Action | Where | Saving |
|---|---|---|---|
| 1 | `RUNS_PER_QUESTION` 5 → 3 | `config.py:30` | **40%** |
| 2 | Build a `--replay` path (re-score free, re-extract ~$0.02) | `scan.py` / `scoring.py` | ~$5 per dev iteration |
| 3 | Store `reasoning_tokens` and `search_context_size` per scan | `llm.py` `Usage` | none — makes the next decision measurable |
| 4 | Confirm a credit-exhausted scan cannot report `done` | `scan.py` `completion_status` | correctness |

**Measure before deciding — $1.20:**

| # | Action | If it lands |
|---|---|---|
| 5 | Run `bench_cost.py --yes` | −41% more, on top of #1 |

**Decide after a customer exists:**

| # | Question | Why it waits |
|---|---|---|
| 6 | flex / batch 50% | beta, unverified with `web_search`, adds failure modes for no current need |
| 7 | `-sol` → `-terra` | trades measurement fidelity for money we are not short of |
| 8 | Cadence: weekly vs fortnightly | a product decision about how fast a trend should move, not a cost decision |
| 9 | How many engines | untested assumption; put it in the interviews |

**Expected outcome of doing only #1–#5:** **$43/month → ~$15/month** per customer at weekly cadence on ChatGPT, with no change to what we measure. Combined with items 6–7 if they are ever needed, ~$5/month.

---

## 8. What is still not known

- **How many question clusters a real catalog needs.** Still the guess that sets the whole cost base — `QUESTION_CLUSTERS = 20` in `config.py` is a configurable hypothesis, and the one catalog we have produced 11. An 86-product furniture catalog has never been clustered. **This, not the per-token price, is the number that decides what a customer costs.**
- **Whether three runs holds on a second catalog.** One catalog, one day, one engine.
- **Whether `search_context_size="low"` degrades the answer.** `bench_cost.py` answers this for $1.20.
- **Whether flex supports `web_search` on `gpt-5.6-sol`.** Docs are silent.
- **Gemini and Grok per-answer costs.** Still the unverified estimates from `UNIT-ECONOMICS-2026-09-18.md`. Do not quote them.
- **Whether a merchant wants four engines.** Never asked.

---

## 9. Housekeeping

`CLAUDE.md` names `00-BRIEF.md` as a file to read before every task. **It does not exist at the project root.** Either it was moved or it was never written; the read-order in `CLAUDE.md` should be corrected so it stops pointing at a missing file.

`UNIT-ECONOMICS-2026-09-18.md` should stay where it is — it is the record of how the per-SKU problem was found — but its §3 cost tables now describe an architecture that no longer exists. A pointer at the top of that file to this one would stop the wrong numbers being quoted.

Nothing has been written to `DECISIONS.md`. That happens when §7 is approved, not before.
