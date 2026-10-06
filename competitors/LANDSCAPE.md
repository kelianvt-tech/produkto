# Competitive landscape

**Date:** 5 August 2026 (updated 12 August 2026 — see Searchable row; updated 23 August 2026 — Promptwatch added, Searchable funding verified, new §"How these companies actually acquire customers")
**Method:** desk research via web search and page scraping. No product trials, no sales calls.
**Confidence:** moderate on who exists and roughly what they sell; low on pricing and funding, which move monthly and are largely self-reported. Every vendor page cited is marketing material — including the "best tools" roundups, most of which are published *by* vendors ranking themselves first.

> **Read the "What this changes" section at the bottom before using anything else here.** One finding contradicts the current positioning in `BUSINESS.md`.

---

## The headline

`BUSINESS.md` says: *"Everyone in this market sells measurement… we do the fixing."*

**That is half right, and the wrong half is the one the whole business rests on.**

True: the pure-play AEO platforms are measurement-led, and a third-party e-commerce review of Profound put it more sharply than we ever have — *"Profound watches the shelf better than almost anyone; it just doesn't stock it."* No product feed remediation, no schema deployment, no SKU-level attribution.

False: that nobody does the fixing. **An entire product-data-enrichment category has existed for years** — Zoovu, Lily AI, Hypotenuse, Describely, Stylitics — and it does exactly what we describe as our differentiator: fill in missing product attributes at catalog scale. Zoovu's own page now reads *"Turn messy product information into clear, enriched content that powers AI search."* They got to our sentence before we did.

The real gap is narrower and needs stating precisely. See the bottom of this file.

---

## Tier 1 — Direct: pure-play AI visibility platforms

These sell measurement of whether AI mentions you. Most are B2B/SaaS-oriented; a few have shopping modules.

| Vendor | Funding / status | Price signal | Notes |
|---|---|---|---|
| **Profound** | $155M total; $96M Series C Feb 2026 at $1B valuation (Sequoia, Kleiner Perkins, NVIDIA Ventures, Khosla) | $99 Starter (ChatGPT only) / $399 Growth / custom | Category leader. ~700 enterprise customers incl. Target, Walmart, Ramp, MongoDB. Has a **Shopping Analysis module** and an **Amazon Rufus** module. "Profound Agents" moves toward autonomous fixes. Claims 19 of the 20 recognised AEO experts. ~150 people. |
| **Scrunch AI** | $15M Series A (Decibel); **acquired by Sitecore June 2026, reported $225M** (Bloomberg) | $250–300/mo Core, $500/mo agency | 500+ brands (Lenovo, Skims, Clerk). **AXP (Agent Experience Platform)** serves machine-readable pages to AI agents while leaving the human site untouched — conceptually the closest thing to our thesis. Was still waitlisted as of April 2026. Sitecore ownership likely pulls it upmarket. |
| **Alhena AI** (formerly Gleen) | $4.9M seed Sept 2023, Slow Ventures. No raise since. | $199 / $499 / $999 per month | Sells *"SKU-level AI visibility and revenue attribution."* **Assessment revised down after full review — see [`alhena.md`](alhena.md).** It's a support chatbot company with AEO bolted on; optimisation is capped at 25–50 product pages/month, so it cannot do catalog-scale remediation. Still dangerous for its first-party query data, revenue attribution, and price anchor. |
| **Peec AI** | $29M raised ($21M Series A Nov 2025, Singular); $100M+ valuation | €89 Starter / €199 Pro | Berlin. 3,000+ marketing teams. Clients include Zalando, Hugo Boss, Fielmann, TUI. **European mid-market — closest to us geographically and on price.** |
| **Promptwatch** | €1.2M pre-seed Sept 2025 (Arches Capital); **€6M seed 14 July 2026** led by seed + speed Ventures, with Blum Ventures and Arches following on | Free Explore / $95 Essential / $245 Professional / $579 Business | **Amsterdam. Founded 2025 by Gijs de Groot (CEO, commercial) and Klaas Foppen (technical). Launched 1 April 2025; €2M ARR by May 2026 on €1.2M raised; 1,840+ organisations, adding 150+/month. NY office opening.** Logos are B2B SaaS, not e-commerce — Duolingo, Fireflies, Yelp, Valley, ABN AMRO, WPP, Monks, iO Digital. Early customers all Dutch (DPG Media, Independer, Crisp, Erasmus). **€2M ARR ÷ 1,840 orgs ≈ €90/mo average — the median customer sits on the entry tier. Low-ACV, high-volume, self-serve.** Collects data by **scraping the LLM chat UIs** (their words), plus a JS snippet, GSC integration and server-log analysis for attribution. Content agents produce **5–10 blog articles/month** — brand-and-content level, not catalog or product-attribute level. **Shopping Insights is gated at the $579 tier**, so almost none of their base uses it. See §"The sampling-rate finding" below. **Threat to us: low directly, high as a price anchor** — a prospect who has seen $95/mo AI visibility will need the service frame explained before our number makes sense. |
| **Evertune** | $19M; founded by early Trade Desk team | not public | NYC, 40+ staff. Samples every prompt 100× per model across 11+ models. Moving into **AI advertising** — connects brands to ChatGPT Ads and The Trade Desk. |
| **AthenaHQ** | YC-backed, $2.2M | $295/mo self-serve | Ex-Google Search / DeepMind founders. All 8 engines at entry tier. |
| **Otterly.ai** | Gartner Cool Vendor 2025 | $29/mo Lite | 20,000+ users, 40+ countries. The cheap entry point everyone starts at. |
| **Searchable** | **€3.4M raised, announced December 2025** (verified 23 Aug 2026 via EU-Startups) | not public | **Founded 2025 by Chris Donnelly (CEO), Sam Hogan and Arya Nagabhyru** — "Autonomous SEO & AEO Growth Engineer." Donnelly previously scaled Verb Brands to an eight-figure exit; Forbes 30 Under 30 Europe 2020. Claimed publicly *"0 → $85M in 5 months"*, basis unstated — **still unverified, and the €3.4M raise does not corroborate it.** Treat as unverified. Most media-visible founder in the category by a wide margin (1.2M LinkedIn followers). **Now ships a Shopping/product-tracking feature** (confirmed 12 Aug 2026, [live page](https://www.searchable.com/features/shopping)): tracks which buyer prompts trigger AI product-carousel results across ChatGPT, Gemini and Google AI Mode, surfacing product counts and the top brand per prompt (demo data shows 47 tracked shopping prompts in a bike-gear vertical). Same category as Profound's Shopping Analysis module and Semrush's Shopping Experience Tracking (row below) — measurement of *which products/brands surface*, not remediation. Doesn't (on this page) claim to fix attributes or write catalog data, so it doesn't contradict the Tier 2 gap, but it does mean Searchable — not just Profound/Semrush — now competes directly for the "are we visible in AI shopping" conversation that opens a lot of our outreach. **Also runs a free "UCP Readiness Score" lead magnet** ([searchable.com/ucp-readiness](https://www.searchable.com/ucp-readiness), confirmed 12 Aug 2026): free scored audit, results emailed in minutes, framed as "is your store ready for AI shopping agents (Google AI Mode, Gemini, ChatGPT, Claude)." **Structurally identical lead-gen mechanism to ours** — free instant audit as the wedge into a paid engagement. UCP itself is a real, newly-emerging **Google-led open standard** (co-designed with industry, open-source on GitHub, [developers.google.com/merchant/ucp](https://developers.google.com/merchant/ucp)) that lets AI agents complete *purchases* directly inside Google's AI surfaces — it's about checkout/transaction plumbing (Merchant Center feeds, native/embedded checkout, interoperating with AP2, A2A, and MCP protocols), **not** about whether an LLM has enough written facts to recommend a product. That's a genuinely different layer from what `attributes.py` measures: UCP asks "can an agent complete a purchase here," we ask "does the AI know enough to recommend this product at all." Worth watching rather than panicking about — clean structured attribute data plausibly feeds UCP-readiness too, which could make our remediation work a prerequisite rather than a competitor to it, but that link is unconfirmed. Risk: if we ever borrow "is your store AI-shopping-ready" as an outreach hook, a prospect who's seen Searchable's free UCP score first may assume we mean the same (checkout) thing. |
| **Bluefish** | not verified | enterprise | Enterprise AI visibility. |
| **Brandlight** | not verified | not public | — |
| **Gauge** | not verified | not public | Full-stack GEO toolkit. |
| **Goodie** | not verified | not public | — |
| **Citate.ai** | not verified | not public | — |
| **LLMrefs** | not verified | not public | — |
| **LLM Pulse** | not verified | budget | — |
| **Dageno AI** | not verified | not public | Emerging GEO platform. |
| **Revere AI** | not verified | not public | — |
| **Passionfruit** | not verified | not public | — |
| **Search Party** | not verified | not public | — |

### Tier 1b — the same thing, but cheaper and with execution bolted on

This group matters more to us than the leaders, because they're moving toward our position from below on price.

| Vendor | Price | Why it matters |
|---|---|---|
| **Ayzeo** (Fyrma Inc., NY/Berlin) | $39/mo + $29 per extra engine | **Generates JSON-LD schema, LLMs.txt files, WordPress plugin.** Monitoring *plus* implementation, at 1% of our project price. |
| **GEOforge** | $1,250/mo, $2,500 managed | Explicitly sells *"execution in addition to measurement"* for mid-market. Closest business model to ours. |
| **Vismore** | not public | "Full-loop AEO: monitor → strategy → one-click publish." |
| **MaxAEO** | $15–399 | Monitoring + prioritised action list. |
| **AIclicks** | $59–499/mo | AI agents draft and publish content to close citation gaps. |
| **AirOps** | not public | Citation tracking wired to content production workflows. |
| **Writesonic GEO** | not public | Content-first: write → optimise → distribute. |
| **Geoptie** | budget | Monitoring + content studio. |

---

## Tier 2 — Product data enrichment (the category we missed)

**These are the ones that actually do the work we claim is unique to us.** They came from the PIM/merchandising world rather than the SEO world, which is why they were invisible to us — but they are converging on the same pitch.

| Vendor | What they do | Threat level |
|---|---|---|
| **Zoovu** | Powers 10,000+ e-commerce experiences. Data cleansing, attribute standardisation, enrichment across ERP/PIM/CRM. Now explicitly markets enrichment as *"powers AI search."* | **High.** Established, enterprise, and already telling our story. |
| **Lily AI** | Reads product images and descriptions, generates attribute tags *"written the way real people search, not the way an internal merchandising team labels things."* | **High.** That sentence is our thesis. Retail-native. |
| **Hypotenuse AI** | Enriches attributes, **fills missing data from images and PDFs**, generates publish-ready content, integrates with PIM. | **High.** The PDF ingestion directly attacks our "the fact only exists in a supplier PDF" moat. |
| **Describely** | Product data enrichment service for retailers. | Medium |
| **Stylitics** | AI catalog enrichment, auto-tagging, conversion-ready content. | Medium |
| **Bayezon** | AI enrichment tooling for e-commerce brands. | Medium |
| **AdNabu** | Shopify-focused product data tooling. | Medium — Shopify-native, our platform. |
| **Hootcore** | Enrichment *services* — "thousands of SKUs in hours, not weeks." | Medium — services model, like ours. |

---

## Tier 3 — Incumbent SEO suites adding AI visibility

Distribution is their weapon. They already have the customer.

| Vendor | Price | Notes |
|---|---|---|
| **Semrush AI Visibility Toolkit** | $99/domain; $199/$299/$549 tiers | **Enterprise AIO includes "Shopping Experience Tracking" — which products surface in ChatGPT shopping, and *which attributes drive recommendations*.** That last clause is uncomfortably close to `attributes.py`. |
| **Ahrefs Brand Radar** | $199 / $398 / $699 | Third-party citation mapping; plots AI visibility against a decade of branded search volume. |
| **BrightEdge (AI Catalyst)** | enterprise | 19 years of enterprise retail relationships. Deep on Google surfaces. Argues — plausibly — that Google AI Overviews/AI Mode/Gemini is where the actual volume is. |
| **Conductor** | enterprise | AEO + SEO unified. Claims Forrester's highest enterprise rating in the category. |
| **Adobe LLM Optimizer** | enterprise | Adobe also publishes the market data we cite. |
| **SE Ranking** | €87–188 | SEO platform now doing GEO. |
| **Similarweb / Yext / Brandwatch / Clearscope / Nightwatch** | various | Feature add-ons, low direct threat. |

---

## Tier 4 — Platform and ecosystem

| Player | Notes |
|---|---|
| **Yotpo (Discover)** | Already the hard exclusion in `ICP.md` — sold as an upsell to an installed base. Triage checks for the widget before we spend effort. |
| **Shopify itself** | The existential one. Shopify publishes guides on product data enrichment and controls the product schema. If they ship catalog attribute completeness as a native feature, most of the low end of this market disappears overnight. Not a matter of if they *can*. |
| **OpenAI / Google directly** | If ChatGPT Shopping builds direct merchant feed ingestion with required attribute fields, the problem changes shape entirely — from "write facts on your page" to "fill in this form." Watch this closely. |
| **Google UCP (Universal Commerce Protocol)** | New (surfaced 12 Aug 2026 via Searchable's readiness-score tool). Open standard, co-designed with industry, for AI agents to complete purchases directly in Google AI Mode/Gemini — Merchant Center feeds, native/embedded checkout, interoperates with AP2/A2A/MCP. Not the attribute-completeness problem we solve, but adjacent: if UCP-compliant feeds require the same structured attributes we fill in, remediation work could double as UCP prep. Needs proper research — this entry is desk research from one session, same caveats as the rest of this file. |

---

## Tier 5 — Services

Not researched in depth, and probably where our real competition sits for the first ten customers.

- **SEO/e-commerce agencies pivoting to AEO.** Every agency with a mid-market DTC book is adding this to a retainer. Scrunch runs an agency partner programme with up to 20% referral commission and co-marketing funds — actively arming them.
- **Freelancers and content shops** doing bulk PDP rewrites.
- **Offshore data-entry providers** — the unglamorous, genuinely cheap option for attribute population.
- **`ICP.md` flags this already:** the agency may be the gatekeeper who defends territory, or may become a channel. Still untested.

---

## Tier 6 — Doing nothing, and doing it themselves

The most likely outcome for any brand we approach, and the honest default competitor.

- **Do nothing.** AI is under 5% of their traffic. Nothing forces the decision.
- **DIY with an LLM.** A competent ops person with Claude and the supplier PDFs can bulk-draft attribute copy in days. This was hard in 2024 and is getting easier every quarter. It is the fastest-eroding part of our moat.

---

## The sampling-rate finding

*Added 23 August 2026. This is the most useful technical thing in this file and it applies to the whole of Tier 1.*

Promptwatch's pricing page lets you derive their measurement methodology exactly:

- Essential: 50 prompts × 4 models × 30 days = **6,000 responses**
- Professional: 150 × 4 × 30 = **18,000 responses**
- Business: 350 × 4 × 30 = **42,000 responses**

All three land precisely. So a "response" is **one sample, per prompt, per model, per day** — and only **4 models are tracked at every tier**, including the $579 one, despite eight engine logos being displayed.

**Why this matters.** LLM answers are non-deterministic; ask the same question twice and the brand set changes. Evertune samples every prompt **100× per model** for this reason. A single daily draw means a customer watching their visibility score move day to day is frequently watching noise, not movement. This is the methodologically hard part of the entire measurement category, and a daily refresh does not solve it — it produces a chart that looks as though it did.

**Two consequences for us:**

1. **It is a real, checkable weakness in the dashboards we compete against for attention.** Not a "nobody does X" claim — it is arithmetic off a public pricing page, and a prospect can verify it in a minute.
2. **It applies to our own work too.** Our gate-3 visibility checks are single-run. If we ever publish a before/after claiming remediation moved visibility, single-run sampling will not survive scrutiny, and it would be the exact overclaim `BUSINESS.md` warns against. Sample repeatedly before asserting movement. This is the measurement design question `METHODOLOGY.md` has to answer.

**Also worth noting:** "hundreds of millions of data points daily" (Promptwatch marketing) cannot be coming from prompt tracking. 1,840 orgs mostly on the entry tier is roughly 368,000 responses/day platform-wide. The volume figure is **server-log rows from AI crawlers**, counted per line. A log line is not an insight.

---

## How these companies actually acquire customers

*Added 23 August 2026. Relevant to the current priority, which is outreach rather than building.*

Two GTM patterns show up repeatedly, and both are copyable.

**1. Outbound into a free, zero-friction artifact.**

Promptwatch is the clearest case, and the founders' history explains it. De Groot and Foppen previously built **Sparkbase**, an AI SDR whose agent scraped prospects and wrote personalised cold email at volume (450 business clients incl. Revolut, BCG). They **sold Sparkbase on 27 March 2025 and launched Promptwatch on 1 April 2025 — five days later**, claiming 100 customers in the first week.

*Inference, not stated anywhere: they pointed the outbound machine — and the Sparkbase customer list — at the new product. The timing, De Groot's commercial role and the category overlap all support it, but no source confirms it.*

The arithmetic is less impressive than the headline. At a ~2% cold-email-to-free-signup rate, 100 signups needs ~5,000 sends — a slow week for two people who had just spent a year building an outbound tool. And with a free Explore tier, "customer" plausibly means "free signup". Even at 100 paying on the entry plan that is ~€9k MRR.

**What made it convert was the shape of the ask, not the send volume:** paste a URL, pick 5 prompts, get your score free in 30 seconds. No demo, no call, nothing to decline.

**2. The data-backed lead magnet.**

Searchable runs this hardest — the free UCP Readiness Score (already logged in the Tier 1 row), plus gated research PDFs. A representative example, Aug 2026: *"We captured 95,000 records across 3,000 prompts"* for a free guide, headline finding *"Claude only searches the web on 35% of prompts."*

**How that data is actually obtained, since it looks more impressive than it is:** whether Claude invokes web search is a binary, directly observable event — the response either carries citations or it doesn't. 95,000 ÷ 3,000 ≈ 32 records per prompt, consistent with ~10 samples × ~3 citations. That is roughly 30,000 API calls, i.e. **a few hundred dollars and a weekend script.** No privileged access required.

**Where it stops being sound, which is the part to learn from:**

- **35% is a property of their prompt set, not of Claude.** Search-triggering depends entirely on what you ask. Without the prompt list it is unfalsifiable — and a lead magnet never ships the prompt list.
- **claude.ai or the API is unstated.** They trigger search differently and the consumer product has a memory feature the API lacks.
- *"You have to earn your place in Claude's understanding over time"* has **no data behind it at all.** It is a claim about training-data inclusion, unobservable outside Anthropic. It converts a measurement into a justification for a retainer. It is also our own open unproven — *does remediation move visibility* — asserted rather than demonstrated.
- *"Converts 10% more than ChatGPT"* comes from a different data source entirely (referral analytics), is unsourced, and is confounded by Claude's user base skewing technical.

### What we should take from this

**The play is within reach and our version is stronger.** We have a crawler, an audit tool, and a question nobody has published a number on: *how machine-readable are mid-market DTC product catalogs, and which attributes are missing across them?* Running `attributes.py` across the ~229 brands already in `prospecting/` would yield a bigger, more specific and more defensible figure than 95,000 scraped responses — on a question that is ours. `METHODOLOGY.md` doing double duty as a lead magnet, at compute cost we already have.

**Do not copy the conclusion-stretching.** The measurement is the asset; the causal claim is what gets us caught.

**Do not copy the funnel wholesale, either.** Their outbound works because the product is self-serve at $95/mo — cold email → free score → credit card, no human. Ours is a $3–12k project with a person accountable for the outcome. Volume outbound feeds a self-serve funnel; it does not feed a five-figure service sale, which needs fewer and warmer conversations. **Their "150 new customers a month" is not a benchmark our cold batches should be measured against.** Different ask, different denominator, different business.

---

## Pricing reality

| Segment | Typical price |
|---|---|
| Budget AEO monitoring | $29–99/mo |
| Mid-market AEO | $250–500/mo |
| Execution-inclusive (GEOforge) | $1,250–2,500/mo |
| Enterprise | custom, five figures |
| **Us** | **$3–12k project + $750–1,500/mo** |

**Verified anchor (23 Aug 2026):** Promptwatch's public tiers are $95 / $245 / $579 with a free tier below — and their *average* customer pays ~€90/mo (€2M ARR ÷ 1,840 orgs). This is the most concrete price anchor in the file, because it is derived from reported revenue rather than a list price nobody pays.

We are priced 3–10× the mid-market category norm. That is defensible **only** if we're sold as a service with an outcome, never compared feature-to-feature against a dashboard. The moment a prospect puts us in a spreadsheet next to Peec at €89, we lose — not on merit, on framing.

`BUSINESS.md` justifies front-loaded pricing as churn insurance, which is sound. But it assumes the buyer accepts the frame. Untested.

---

## What this changes

**1. The differentiator as written is wrong.** "Everyone sells measurement, nobody fixes" is false — the enrichment category fixes. The accurate claim is narrower:

> *Nobody combines AI-retrievability-specific diagnosis with remediation, at mid-market DTC scale. The AEO platforms score but don't write. The enrichment vendors write but don't score against what AI actually gets asked. We do both, at product level, for brands too small for Zoovu and too big to hand-fix.*

Still a real gap. Much narrower. And "too small for Zoovu, too big to hand-fix" is a niche someone else can enter next quarter.

**⚠️ The Friday LinkedIn post in `linkedin-strategy-and-week-1.md` asserts the old, wrong version.** Rewrite it before posting. Publishing a differentiator that a prospect can disprove with one search is worse than posting nothing.

**2. The category is consolidating, fast.** Scrunch acquired at ~$225M inside three years. Profound at $1B. $200M+ of VC into pure-plays. This validates the market and shortens our window simultaneously — `BUSINESS.md` already says we're renting a position, and this is the evidence for it.

**3. The methodology is the only durable asset.** Everything else here is copyable or fundable. Nobody — Profound, Scrunch, Zoovu, us — has publicly demonstrated that remediation moves AI recommendations. The re-audit diff is the only mechanism we have for answering it, and answering it first is worth more than any feature.

**4. Two vendors to study properly before the outreach goes out.** **Alhena** (SKU-level AI visibility, e-commerce-native) and **Zoovu** (enrichment, already using our language). If a prospect names either one, we need a real answer, not a surprised one.

---

## Gaps in this research

- No pricing verified by trial or quote. All self-reported.
- Funding figures from vendor pages and roundups, not filings.
- **The Searchable "$85M in 5 months" claim is still unverified** and comes from a LinkedIn post by an interested party. *Partially chased 23 Aug 2026: they raised €3.4M in Dec 2025 (EU-Startups). That confirms the company is real and funded; it does nothing to support $85M. A company at $85M of anything does not raise €3.4M. Treat the claim as marketing until a filing says otherwise — Companies House still unchecked.* *(Separately confirmed 12 Aug 2026: Searchable's product now includes a live Shopping/product-visibility tracking feature — see Tier 1 row. That part is verified from the product page itself, not from a claim.)*
- The enrichment tier (Tier 2) was found late and is under-researched relative to its threat level. **Do this next.**
- No agency/services research beyond inference.
- Nothing here reflects what a customer would actually say. That comes from the fifteen interviews, and it will matter more than any of the above.

---

## Sources

**Added 23 August 2026 — Promptwatch, Searchable, GTM:**

- [Promptwatch — About](https://promptwatch.com/about) *(vendor; source of "100 customers in first week", launch date, €2M ARR — self-reported, "customer" undefined)*
- [Promptwatch — pricing](https://promptwatch.com/pricing) *(vendor; source of the sampling-rate arithmetic — this one is derivable, not just claimed)*
- [Tech.eu — Promptwatch raises €6M](https://tech.eu/2026/07/14/promptwatch-raises-eur6m-to-expand-its-end-to-end-ai-search-optimisation-platform/)
- [Quote (NL) — Promptwatch pre-seed](https://www.quotenet.nl/zakelijk/a67851468/seo-ai-bedrijf-promptwatch-gijs-de-groot-klaas-foppen/) *(founder ages, Dutch customer list)*
- [Silicon Canals — Sparkbase acquired by Squeezely founders](https://siliconcanals.com/sparkbase-gets-acquired-by-squeezely-founders/) *(the 27 March 2025 acquisition date — five days before Promptwatch launched)*
- [EU-Startups — Searchable raises €3.4M](https://www.eu-startups.com/2025/12/searchable-raises-e3-4-million-to-help-teams-understand-their-brand-in-the-ai-age/)
- [generatemore.ai — Promptwatch review](https://generatemore.ai/blog/my-promptwatch-review) *(third-party; UX criticism, older pricing — they have since repriced upward from $89/$199)*

**Original set (5–12 August 2026):**

- [Scrunch — best AEO/GEO tools 2026](https://scrunch.com/blog/best-answer-engine-optimization-aeo-generative-engine-optimization-geo-tools-2026) *(vendor, ranks itself first)*
- [NoGood — best AEO & GEO tools for e-commerce](https://nogood.io/blog/best-aeo-geo-tools-ecommerce-brands/) *(the most useful e-commerce-specific read)*
- [Nick Lafferty — Profound vs Scrunch](https://nicklafferty.com/blog/profound-vs-scrunch/) *(carries the Sitecore/Bloomberg acquisition figure)*
- [Alhena — best AI visibility tools for B2B](https://alhena.ai/blog/best-ai-visibility-tools-b2b/) *(vendor)*
- [Ayzeo comparisons hub](https://ayzeo.com/comparisons) *(vendor; best price table)*
- [Evertune — 10 best AI visibility tools](https://www.evertune.ai/resources/insights-on-ai/the-10-best-ai-visibility-tools-for-2026) *(vendor)*
- [MaxAEO — 12 best AEO & GEO tools](https://maxaeo.ai/blog/the-12-best-aeo-geo-tools-for-2026-monitor-and-optimize-your-ai-search-visibility/) *(vendor; unusually honest about labelling unverified data)*
- [Zoovu — product data enrichment](https://zoovu.com/data-enrichment)
- [Yotpo — best AI tools for e-commerce operations](https://www.yotpo.com/blog/best-ai-tools-ecommerce-operations/) *(source for Lily AI)*
- [Hypotenuse AI — product data enrichment](https://www.hypotenuse.ai/blog/product-data-enrichment-what-it-is-and-why-you-need-it)
- [Profound vs Scrunch](https://www.tryprofound.com/resources/articles/profound-vs-scrunch) *(vendor)*
