# Unit economics — what a scan actually costs, and why the current design can't scale

**Written:** 18 September 2026
**Trigger:** the OpenAI account ran out of credit after four scans. €10 gone in about 25 hours.
**Status:** analysis, not a decision. Nothing here has been agreed yet.
**Superseded in part:** the rearchitecture shipped on 18 Sep. The per-SKU cost tables in §3 no longer describe the code, and the 83%/17% cost split in §1 was measured before the catalog scan existed. For current figures see `ALL-HANDS-COST-2026-09-19.md`. The diagnosis in §4 and the design in §5 stand — they are what was built.

---

## 1. What the four scans cost

Measured from `mvp/app/produkto.db` — the token and web-search counts the app already stores per scan — priced against developers.openai.com/docs/pricing, read 18 Sep 2026.

| Scan | Product | Estimated cost |
|---|---|---|
| 1 | Frontier Cleanser, 16 Sep | $3.95 |
| 2 | Frontier Cleanser, 17 Sep | $3.52 |
| 3 | Essentials Set, 17 Sep | $3.82 |
| 4 | Amalfi Vit-C, 17 Sep (died mid-scan, out of credit) | $3.86 |
| | **Total** | **~$15** |

`PLAN.md` budgeted **$0.10–0.30 per scan**. The real figure is **~19× that**.

**Accuracy caveat:** the database sums both models' tokens into one counter, so the split between the answer model and the helper model is estimated, and some input may have been billed at the cheaper cached rate. Treat these as ±30%. The order of magnitude is not in doubt. The authoritative figure is on the OpenAI usage page and is worth checking.

### Where the money goes

Per scan: **670,000 input tokens**, 31,000 output tokens, 68 web searches.

| Line item | Share |
|---|---|
| Input tokens on the answer model | ~83% |
| Web searches ($10 / 1,000 calls) | ~17% |
| Helper model (question writing, answer parsing) | ~0.3% |

That's ~27,000 input tokens per answer call. The cause is web search: retrieved page content is fed back into the model as input, and it is billed at the answer model's full input rate ($4.00/1M on gpt-5.6-sol). **The cost is search content, not our prompts.** No amount of prompt tidying touches it.

This is inherent to measuring what an AI engine says *with browsing on* — which is the only thing worth measuring. It is not a bug and not fixable by optimisation.

---

## 2. The cost of one answer

Because cost is driven by search content volume rather than anything provider-specific, the workload shape is roughly constant across engines. Only the per-token price changes.

| Engine | Model | Cost per web-searched answer |
|---|---|---|
| ChatGPT | gpt-5.6-sol ($4 / $20) | $0.159 |
| Claude | Opus 5 ($5 / $25) | $0.192 |
| Claude | Sonnet 5 ($2 / $10) | $0.093 |
| Gemini | Flash tier | ~$0.038 *(estimated — not verified)* |
| Grok | — | ~$0.100 *(estimated — not verified)* |

**One web-searched answer costs roughly 4¢ to 19¢.** Everything below is that number multiplied.

Gemini and Grok figures are estimates. Verify before quoting them to anyone.

---

## 3. Why the current design breaks

The MVP generates **5 questions per product × 5 runs = 25 answers per product**. Cost therefore scales with **SKU count**.

Weekly scanning, at the blended average across four engines:

| Catalog | 1 engine | 4 engines |
|---|---|---|
| 6 products (Clubhouse Skin) | $78/mo | $314/mo |
| 50 products | $654/mo | $2,616/mo |
| **86 products (M&O Living)** | **$1,125/mo** | **$4,500/mo** |
| 300 products | $3,925/mo | $15,698/mo |

At a plausible price point of €500–1,500/month, a mid-size catalog on four engines loses money on every customer. **The answer to "is multi-engine too expensive?" is yes — under this architecture.**

---

## 4. The actual problem is not the API prices

It's that **each answer is matched against exactly one product.**

`mvp/app/scan.py:99` — `match(mention, product, aliases)`, singular. A single answer typically names about a dozen products, and is then checked against one SKU. Everything else in it is discarded as "competitor."

Two consequences, both visible in the existing data:

**Questions overlap heavily between products.** Prompt set 1 (Frontier Cleanser) and prompt set 2 (Essentials Set) both ask about gentle cleansers that don't strip the skin and protect the barrier. Those are close to the same scan, bought twice.

**Answers that could have scored several products only score one.** Scan 3 cost $3.82 and returned zero mentions of the Essentials Set — but it collected 25 answers full of cleansers and moisturisers, which were never checked against the other five Clubhouse products.

This is the whole problem. Buyer questions are **category-shaped**, not SKU-shaped. *"Best gentle face cleanser under £40"* is one question that speaks to every cleanser in the catalog at once.

---

## 5. The alternative

**Scan question clusters, not products. Match every answer against the whole catalog.**

Cost then scales with **how many distinct buyer questions the catalog competes on** — not with SKU count. An 86-product furniture catalog might have 20 real question clusters; a 300-SKU catalog probably has 30, not 300.

M&O Living, 86 products, 4 engines:

| Design | Answers per scan | $/month |
|---|---|---|
| Per product, weekly (current) | 2,150 | $3,631 |
| Per question cluster, weekly | 100 | $169 |
| + 3 runs instead of 5 | 60 | $101 |
| + fortnightly instead of weekly | 60 | **$51** |

**A ~72× reduction**, and the data gets *better*, not worse: every answer is scored against every product, so one scan tells the merchant which of their products wins in each category — which is a more saleable insight than a single SKU's mention rate.

Cost becomes near-independent of catalog size:

| Question clusters | 4 engines, fortnightly | Applies to |
|---|---|---|
| 10 | $25/mo | any catalog size |
| 20 | $51/mo | any catalog size |
| 40 | $102/mo | any catalog size |
| 80 | $203/mo | any catalog size |

Gross margin at 60 answers/scan, 4 engines, fortnightly ($51/mo API cost):

| Price | Gross margin |
|---|---|
| $300/mo | 83% |
| $500/mo | 90% |
| $1,000/mo | 95% |

That is a normal SaaS margin. The business works — under the other architecture.

---

## 6. What this costs to change

Not a rewrite, but not trivial either.

- `prompt_sets` currently hangs off `product_id`. It would hang off the store, with a category or cluster label.
- `match()` takes one product. It would take the catalog and return which product matched, if any.
- The dashboard is built around one product. It would need a catalog view, with per-product drill-down.
- The freeze rule still applies, and matters more: clusters must freeze so the trend stays comparable.

The house rule in `MEMORY.md` — *"product level, not brand level"* — is **not** violated by this. Results stay per-product. What changes is how the questions are *gathered*, not how results are reported. Arguably it serves that rule better, since every product gets scored on every relevant question rather than only its own five.

---

## 7. Cheaper levers, for completeness

Ranked by saving per unit of damage. None of these fix the scaling problem on their own.

| Lever | Saving | Cost to accuracy |
|---|---|---|
| Question clusters instead of per-product | ~20×+ | None — improves data |
| Fortnightly instead of weekly | 50% | Slower trend |
| 5 runs → 3 per question | 40% | Noisier; noise band widens |
| Cheaper model per engine | up to 50% | **High** — a cheaper model isn't what the buyer's ChatGPT actually serves |
| Fewer engines at launch | linear | Less coverage; may be what merchants want anyway |

The model-swap lever is the one to be most careful with. The whole premise is measuring what a buyer actually sees. Measuring a cheaper model measures something nobody experiences.

---

## 8. Open questions

- **How many question clusters does a real catalog have?** Guessed at 20 for M&O Living. Unverified. This number sets the entire cost base and should be measured on a real catalog before any price is quoted.
- **Actual spend vs this estimate.** Check the OpenAI usage page against the ~$15 figure.
- **Gemini and Grok pricing.** Estimated here. Not verified.
- **Does a merchant want four engines?** Assumed, not asked. Worth putting into the interviews before building for it.
- **Does credit run out mid-scan again?** Scan 4 reported `done 25/25` while storing only 23 answers. A partly-failed scan should not report as complete — its percentages are computed over a smaller base than it claims.

---

## 9. The honest summary

The €10 was not wasted. It bought the number that `DECISIONS.md` listed as unknown on 17 September, and it surfaced an architectural problem *before* a customer was paying for it rather than after.

The finding is not "AI visibility monitoring is too expensive." It is **"scanning per-SKU is too expensive, and it was never the right unit anyway."**
