# AEO Startup — Master Brief

**Last updated:** 3 August 2026
**Status:** Pre-validation. Idea defined, competitive landscape mapped, **first primary evidence collected (query-shape test, 3 Aug — see §9).** Demand research with real buyers still not started; that remains the blocker.

> Update this file weekly. It is the single source of truth — anyone reading it should understand where things stand without reading anything else.

---

## 1. The idea

Make ecommerce brands' **product catalogs machine-readable** so their individual SKUs get recommended inside ChatGPT, Gemini, Perplexity and AI shopping surfaces.

**Target customer:** mid-market DTC brands, roughly $1–5M/year revenue, few hundred+ SKUs, no in-house ecommerce ops person.

**Not:** AI visibility monitoring (crowded). Not brand-level authority content (crowded). The specific job is catalog-scale remediation.

---

## 2. Team

| Person | Covers | Gap |
|---|---|---|
| Kelian | Sales / marketing / distribution. Barcelona-based, some Claude Code experience. Second-degree contact at M&O Living (Barcelona DTC furniture), which supplied the first test catalog. | **No operator experience inside the ICP** — category knowledge is researched, not lived |
| Friend | Strategy — **needs to become a real function.** Proposed: product + delivery ownership. | Role not yet defined concretely |
| — | **Engineering — uncovered** | Recruit after traction, not before |

**Action:** agree the equity split between the two of you *before* recruiting a third. Co-founder engineer = 25–40%, 4-year vest, 1-year cliff.

**Base:** Barcelona. Stay — customers are remote, runway is the scarce resource, BCN has real engineering talent (Typeform, Factorial, Glovo, Wallbox) and low burn. Revisit in 6 months.

---

## 3. CODE validation — verdict

| Letter | Verdict | Key evidence |
|---|---|---|
| **C** Consumer trends | Strong | AI referral traffic to US retail **+393% YoY** (Q1 2026, Adobe). Conversion flipped from **38% worse** (Mar 2025) to **42% better** (Mar 2026). Revenue per visit +37%. 39% of consumers have shopped via AI. ChatGPT ~900M WAU. |
| **O** Opportunity | Strong but narrowing | Adobe: product detail pages score **66% machine-readable** — worst of any page type. Homepages 75%, category 74%. Adobe: *"much of the content is currently invisible to LLMs."* |
| **D** Demand | **UNVERIFIED — this is the current blocker** | Category demand proven by competitor funding + AEO-as-a-service market ($68M 2024 → $340M 2027). But demand *for catalog remediation among mid-market DTC* is untested. |
| **E** Economic sizing | Strong | 47,000 Shopify Plus stores × $36,000/yr = **$1.69B TAM**. 0.5% share = 235 customers = $8.5M ARR. |

---

## 4. Competitive landscape

### Monitoring / tracking layer — CROWDED, avoid
Profound (market leader), Scrunch ($250/mo), Goodie ($495/mo), Alhena, Semrush, Visiblie, Searchable.

### AEO agents — CROWDED, mostly content/SEO-descended
Frase (publishes to CMS with schema, auto-fixes), Quattr (GIGA agent), Siteimprove (Content Writing & Optimization Agent + remediation agent), Goodie (integrated writer), Writesonic, AEO Engine, FixAEO.
→ These optimise blog content, meta tags, page-level copy. **Not built for catalogs.**

### Searchable (the company from the source video)
- Founded 2025 by Chris Donnelly, London
- Raised $4M pre-seed at $40M val (Dec 2025) → **$14M at $85M val (May 2026)**
- ~£2M ARR in under 5 months
- Clients: American Express, KPMG, Pfizer, Siemens → **enterprise B2B, not our segment**
- Has a shopping product now: tracks product visibility, product share, vendor coverage
- v2 announced as an autonomous agent

### Yotpo Discover — THE REAL COMPETITOR
- Ecommerce-native, SKU-level commerce data
- **Three agents:** Onsite (technical scanning), Content (review-backed blog content), Activation (loyalty base for off-site validation)
- ⚠️ Two of three agents run on data Yotpo already owns (reviews, loyalty) → much weaker for non-Yotpo brands
- **Product pages dated March–July 2026 → ~5 months old, actively shipping right now**
- 🔑 **Initial release targets $10M+ annual GMV. A version for "scaling brands" is planned but not shipped.**

### Shopify App Store — occupied at the cheap end
AIO (AI SEO Visibility Engine), StoreSEO, Frizerly. Typically $20–50/mo. Price-anchoring trap.

---

## 5. Positioning

The differentiation is **structural, not per-competitor**, and it holds against all of them at once:

- They sell measurement or software. We sell the outcome and are accountable for it.
- They serve enterprise or their own installed base. We serve mid-market brands nobody is calling.
- They build for the median customer. We go deep in one category.

**Window: 6–12 months.** Yotpo has publicly stated they're coming down-market. This is a rented position, not an owned one.

⚠️ **Do not say "nobody does this for ecommerce."** Yotpo and Goodie do. The accurate claim is: *nobody does catalog-scale remediation for mid-market DTC with a human accountable for the result.*

### The sharpened wedge (added 3 Aug, evidence-backed)

Query-shape testing (§9) showed the unit of the answer is set by the **query**, not the category:

> **Models name specific products when the buyer's query carries matchable attributes. Where buyers ask in taste language, answers stop at brand level and there is nothing for catalog remediation to bite on.**

Sales consequence — stop selling "AI visibility," sell **"win the spec-shaped queries in your category."** It is concrete, it is demonstrable on a call, and it names a deliverable. It also self-qualifies the customer: brands whose buyers only ask taste questions are not prospects, and disqualifying them early is worth more than a broader pitch.

---

## 6. Business model — current thinking

**Pricing (recommended shape):**
- One-time remediation project, scaled by catalog size: **$3k (500 SKUs) → $12k (5,000 SKUs)**
- Ongoing maintenance retainer: **$750–1,500/mo**
- Optional paid audit as entry point: **$300–500 one-time**

**Why front-loaded:** the work is front-loaded, and it's insurance against churn. At $300/mo, a month-2 churn = $600 for ~15 hours of work. At $7k + $1k/mo, a month-3 churn = $10k and the work is paid for.

**Rejected:** flat $150–300/mo recurring. Prices like software, costs like a service. Squeezed between $30 Shopify apps below and agencies above.

**Open question:** Kelian's preference is to move to a low-priced agent product. Unresolved tension — see Open Questions.

### The retention problem (identified, not solved)
Customers **will not** see revenue movement in month 1. AI models re-index slowly, AI is <5% of traffic, attribution is poor.
→ **Sell on the leading indicator (visibility), report on it monthly, and say so on the sales call before they pay.** Most churn is surprise, not disappointment.

---

## 7. What "fixing" actually means

1. **Product schema** — JSON-LD completeness: brand, SKU, GTIN, price, availability, material, dimensions, reviews
2. **Missing specs** — GSM, thread count, fibre origin, care, sizing. Can't win "linen duvet for hot sleepers" if breathability is never stated
3. **Factless copy** — brand poetry contains nothing retrievable. Needs who it's for / not for / how it compares
4. **No comparison content** — LLMs answer comparatively; if nothing compares you to the category leader, you're absent
5. **Reviews trapped in JavaScript** — review text is rich signal; if client-side rendered, invisible
6. **Crawler access** — robots.txt blocking GPTBot / ClaudeBot / PerplexityBot. ⚠️ **Largely obsolete for the Shopify ICP as of Aug 2026.** Shopify's default robots.txt now allows all agents and advertises `agents.md`, a UCP discovery file and a UCP/MCP endpoint (verified on molivings.com, 3 Aug). Keep the check for non-Shopify stores; do not build a pitch on it
7. **Feed hygiene** — missing GTINs, wrong categories, incomplete attributes
8. **Off-site presence** — third-party roundups, Reddit, retailer listings

~3–4 genuinely technical items; 4–5 are content and data hygiene.

---

## 8. MVP

**A catalog visibility report.** A script → a PDF. Nothing else.

- Crawls product pages, scores the mechanical checks above
- Runs ~30 real buyer queries against ChatGPT + Perplexity for the category
- Output: score, two **named** competitors' scores, queries where rivals win, named invisible SKUs, two free fixes

**Deliberately excludes:** fixing anything, login, UI, recurring runs, Shopify app, write access.

**Why the report before the agent:** it's the lead magnet, the sales pitch, the measurement baseline for retention, *and* the learning engine that tells you what the agent should automate. Building the agent first = automating a guess.

**Validation test:** run on 20 brands, send cold with no ask. ≥5 replies = real. 0 replies = learn why before building.

---

## 9. IMMEDIATE NEXT ACTIONS

### This week
- [x] Connect project folder, install Claude Code
- [x] Run 10 buyer-intent prompts for M&O through ChatGPT / Gemini / Perplexity — **DONE 3 Aug, results below**
- [ ] Sign up for a Goodie trial and/or book the Yotpo Discover demo — find out what their agents *actually* do vs. marketing copy
- [ ] Agree equity split with friend; define his function concretely (product + delivery)

**The ten M&O test queries (indoor only):**
1. Best furniture brands for a warm minimalist living room
2. Where to buy solid teak dining tables in Europe
3. Furniture brands with a Vincent Van Duysen aesthetic but more accessible
4. Best sofa brands for a Mediterranean style home
5. Where do interior designers in Spain source handcrafted furniture
6. Alternatives to HK Living and Tine K but more refined
7. Balinese-style furniture brands that ship to Spain
8. Linen sofas that age well — which brands
9. Furnishing a second home in Ibiza, which furniture brands
10. Solid oak sideboards from European design studios

Log per query: did M&O appear · who did · were *specific products* named or only brands · what sources were cited.
→ The third one matters most. If only brands are named, catalog-level remediation is a harder sell. If specific products with specs and prices appear, that's the whole thesis on screen.

### FINDINGS — 3 August 2026

**Run 1, the ten queries above.** Almost no products named — brands only. The single exception was the query naming a concrete object ("solid teak dining tables"), which did return products.

**Diagnosis: run 1 was confounded.** Seven of the ten queries were taste-shaped ("warm minimalist", "Van Duysen aesthetic", "Mediterranean style", "more refined than HK Living"). They carry no attribute to match a SKU against, so a brand-level answer is the only answer available. Run 1 tested *query shape*, not *category*.

**Run 2, same category, spec-shaped queries** (seats 10 extendable under €2000 · removable washable covers 220cm · solid oak slatted base no particleboard · stackable upholstered chairs under €150 · storage coffee table 120cm solid wood · outdoor teak no re-oiling · 180cm soft-close sideboard · fabric over 40,000 Martindale):
→ **Products named and ranked.** Furniture is viable. The variable is the query, not the vertical.

**Consequence:** furniture stays as the beachhead. Note this rests on category logic and the M&O test catalog, not on insider access — see the sharpened wedge in §5.

⚠️ Both runs were quick and informal. The finding is robust anyway, because it concerns the *shape* of the answer, not whether M&O appeared — memory contamination can't change brand-level into product-level. Do not over-read anything else from these runs.

### M&O baseline (molivings.com, measured 3 Aug)

86 products, Shopify. `products.json` is public — catalog enumeration is trivial, for us and for anyone else.

The gap is not missing facts, it is **unstructured** facts. Descriptions are prose blobs with attributes buried in them: *"Material Solid wood frame with high density foam Fabric 100% Polyester Dimensions L 100 x W 100 x H 66"*. And `product_type` is empty on **84 of 86 products**, so the catalog carries almost no category signal.

Measured against the spec-shaped queries that *do* return products, M&O currently states none of: seat count, cover removability, washability, Martindale rating, wood species, care/maintenance requirements. The Calira Sofa says "100% Polyester" and nothing about whether the cover comes off.

→ This is the demo. A real store in a strong-fit category, eight queries it can't be retrieved for. Public data only — no store access was needed to produce it, which is the point: the same report can be built for any prospect cold.

### Next two weeks — DEMAND RESEARCH (the blocker)
- [ ] Build the audit tool with Claude Code
- [ ] Run it on 20 target brands, send reports cold, no ask
- [ ] 15 conversations with DTC founders/marketers — **never pitch, only ask about their world**
- [ ] Daily hour logging r/shopify, r/ecommerce, r/SEO_for_AI, DTC groups

**Interview questions that work** (past behaviour, not hypotheticals):
- Walk me through how customers found you last month
- Has anything shifted in your traffic mix this past year?
- Have you looked into AI search at all — what did you actually do?
- What are you paying for on SEO/marketing tools right now?
- Who at your company would own this if you decided to act?
- What made you look into it in the first place?

**Never ask:** "would you pay for X?" / "do you think AI search matters?" — people are polite and the answers are worthless.

**Signal quality.** Strong: already tried a tool, can name a budget line, complained before you raised it, asks follow-ups. Weak: "sounds interesting," "keep me posted."

### ⚠️ KILL CRITERIA — decided in advance
If after 15 conversations: fewer than 4 have actively looked into this, none can name an owner, and nobody is spending on anything adjacent → **demand isn't there for this segment.** Move upmarket, wait, or change problem.

---

## 10. Open questions

1. **Service vs. agent.** Kelian prefers an agent (scalable, sellable with conviction). Concern: going straight to agent means competing with Yotpo without knowing which fixes actually work. Proposed resolution: compressed 4-week learning sprint in parallel with building, not a 6-month service phase. **Unresolved.**
2. **Does the remediation actually move visibility?** Nobody knows — including the funded competitors. This is the core unknown behind everything.
3. **Is the ROI real today?** At a $150k/mo brand, doubling AI visibility ≈ +$4k/mo against a $3k/mo fee. Thin now; the bet is on the trajectory. ~~Category selection matters~~ → **partially answered 3 Aug.** It's less about category than about how buyers phrase queries in it. Aesthetic categories still qualify *if* a meaningful share of real buyer queries are spec-shaped — true for furniture. Still unknown: **what that share actually is.** Nobody has query-volume data by shape.
4. **US vs. EU market focus** — test in interviews. Data is US-centric; US/UK brands are more aware and more willing to pay a remote vendor.
5. **Does Shopify commoditize this platform-side?** (new, 3 Aug) Shopify already ships agent-open robots.txt, `agents.md`, and a UCP/MCP catalog endpoint. The pipes are built. What's empty is the merchant's own attribute data — which is the remediation job, and arguably makes it *more* valuable, since the last remaining bottleneck is the only one Shopify can't fill for you. But if Shopify ships attribute auto-enrichment, much of item §7.1–7.2 evaporates. **Watch their changelog.** This is the biggest platform risk on the board.

6. **Is the paid audit ($300–500, §6) sellable?** Probably not as specced — a scan report is close to what Yotpo bundles free into a demo. Either cut it, or reframe it as a qualifying fee credited against the remediation project.

---

## Sources

- [Adobe: AI traffic grows but retail sites lag in AI search visibility (Apr 2026)](https://business.adobe.com/blog/ai-traffic-surge-retail-sites-not-machine-readable)
- [AI Traffic to US Retailers Jumps 393% in Q1](https://finance.yahoo.com/sectors/technology/articles/ai-traffic-us-retailers-jumps-160141756.html)
- [Yotpo Discover](https://www.yotpo.com/discover/)
- [Searchable raises $14M (Tech Startups)](https://techstartups.com/2026/05/18/searchable-raises-14m-to-help-brands-win-visibility-in-the-age-of-ai-search/)
- [AEO/GEO Pricing Guide 2026](https://thedigitalelevator.com/blog/aeo-and-geo-pricing-guide/)
- [GEO Market Size](https://dimensionmarketresearch.com/report/generative-engine-optimization-geo-market/)
- [Shopify Statistics 2026](https://www.demandsage.com/shopify-statistics/)
