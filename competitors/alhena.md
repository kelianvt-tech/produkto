# Alhena AI

**Date:** 5 August 2026
**Confidence:** good on pricing and product claims — taken from their own live pages. Low on adoption, revenue and how well any of it works. No trial run.

**Short version:** less threatening than the first pass suggested, and threatening in a different way than expected. The product overlap is real but shallower than their marketing implies. The dangerous parts are their data position and their price anchor, not their remediation capability.

---

## Who they are

| | |
|---|---|
| **Formerly** | Gleen AI. Rebranded February 2025. |
| **Legal entity** | Helix3 Labs Inc, Pleasanton, California |
| **Founded** | 2022, by ex-LinkedIn and Meta engineers |
| **Founders** | Ashu Dubey (CEO), Nagendra |
| **Funding** | **$4.9M seed, September 2023**, led by Slow Ventures (6th Man Ventures, South Park Commons, Spartan Group, Script Capital, CoinShares, Krust Group) |
| **Last round** | Sept 2023 — no raise in ~3 years |

**The funding number corrects the landscape file.** I listed them as a top threat partly on vibes; $4.9M seed with no follow-on is *less* than Peec AI ($29M), Evertune ($19M), Scrunch ($15M pre-acquisition), and a rounding error next to Profound's $155M. They are running four product lines — support concierge, shopping assistant, voice, AI visibility — on seed money raised three years ago.

**Their actual core business is a chatbot.** The Shopify listing is "Alhena: AI Shopping Concierge." AI Visibility is tagged **"New"** in their own pricing table. This is a support-and-shopping bot company that has bolted AEO on, not an AEO company.

Also worth noting: the Shopify app shows **4 reviews**. That's a weak adoption signal for a company four years old, though app reviews undercount enterprise/direct deals.

---

## Pricing — and where it breaks

All plans are priced on **conversation credits** (chatbot volume). AI visibility rides along with small allowances.

| Plan | Price (annual) | Conversations | AI questions tracked | **Optimisation credits** | Refresh |
|---|---|---|---|---|---|
| Free | $0 | 25 | 5 | — | Snapshot |
| Essentials | $199/mo | 200 | 25 | **5** | Monthly |
| Growth | $499/mo | 550 | 75 | **25** | Weekly |
| Scale | $999/mo | 1,200 | 150 | **50** | Weekly |
| Enterprise | custom | unlimited | custom | custom | custom |

Monthly billing is ~20% higher. Overage is $1.20/credit flat.

### The crack

**One PDP optimisation = 1 credit.**

- Growth ($499/mo) → **25 product pages per month**
- Scale ($999/mo) → **50 product pages per month**

Run that against a real mid-market catalog:

> **2,000 SKUs on the Scale plan = 40 months** to cover the catalog once.
>
> Or buy it as overage: PDP optimisation costs 3 credits ($3.60) beyond the allowance. **2,000 × $3.60 = $7,200**, on top of $999/month.

Their "SKU-level" claim is genuine for *tracking* — they monitor which products get recommended. It does not extend to *fixing* at catalog scale. The credit model is inherited from a chatbot business where the unit is a conversation, and it doesn't stretch to 2,000 product pages.

**That $7,200 overage figure is worth memorising.** It's within range of our $3–12k remediation project, and it comes from their own pricing page.

---

## What the product actually does

From their AI Visibility page:

**Map AI visibility** — which products appear (or don't) across ChatGPT, Gemini, Perplexity and others.

**Rendering analysis** — genuinely novel, and we have nothing like it. Not just *was I cited* but: was a product card rendered with full detail? Were price and ratings surfaced? Was it positioned as premium, affordable or best value? Was the specific SKU referenced or only the brand?

**AEO FAQ Engine** — the closest thing to our work. *"Analyzes each product page, extracts key attributes like price, materials, features and target audience, then generates shopping-aligned queries and benchmarks them against competitors. Gaps are surfaced with exact Q&A pairs to add."*

**GEO citation strategy** — identifies which publishers and review sites influence AI answers in a category.

**Revenue attribution** — ties AI source to actual sales through the storefront connection.

### The distinction that survives

Their own FAQ says a PDP optimisation *"analyzes a product page and **generates recommendations**."*

Recommendations, plus FAQ Q&A pairs to bolt on. Not: sourcing the Martindale rating from a supplier PDF and writing it into the product data across 2,000 items.

So the line holds, but it is finer than the current positioning implies:

| | Alhena | Us |
|---|---|---|
| Unit | Which SKUs get recommended | Which attributes are stated |
| Output | Recommendations + FAQ pairs | Filled attributes in the catalog |
| Scale | 25–50 PDPs/month | Whole catalog as a project |
| Fact sourcing | No — works from what's on the page | Yes — that's most of the labour |
| Measurement of outcome | **Yes, revenue attribution** | **No** |

**Be careful with the FAQ Engine, though.** Appending citation-ready Q&A pairs to a product page may work perfectly well without touching the underlying spec fields — FAQ schema is highly citable. If that turns out to be as effective as proper attribute remediation, it's cheaper, faster and automatable, and our thesis weakens considerably. This is a testable question and we should test it rather than assume our approach is better.

---

## What they have that we can't match

**1. First-party behavioural intelligence.** Their chatbot sits on the merchant's storefront and sees what shoppers actually ask. `attributes.py` is derived from queries *we tested*. Theirs comes from real buyers on the real store. That is a structurally better input to the same asset, and we cannot replicate it without being installed on storefronts.

**2. Revenue attribution.** They can connect AI visibility to sales. `BUSINESS.md` lists "remediation actually moves AI visibility" as unproven by anyone including the funded competitors — **Alhena is the best-positioned company on the landscape to prove it first**, because they already have the storefront connection and the sales data. If they publish that before we do, our single durable asset evaporates.

**3. Distribution.** They're already installed as a chatbot. AI visibility is an upsell to an existing base, not a cold sale.

**4. Logos.** Victoria Beckham, Huckberry, Tatcha, Paula's Choice, Unilever, Murad, K18, DryRobe, Puffy, Commando, Inno Supps, Crocus, Butcher Crowd.

Note the category mix: **beauty, skincare, supplements, apparel.** Skincare-with-actives and supplements are both in our strong-fit list, and Alhena has recognisable brands in both. **Furniture is absent.** That's the gap in their logo wall and it happens to be the only category `attributes.py` covers.

---

## Where they're weak

- **$4.9M, three years without a raise**, four product lines. Thin.
- **AI Visibility is new and bolted on** to a chatbot company's architecture and pricing.
- **Optimisation credits don't scale** to full catalogs — the central finding above.
- **Recommendations, not execution.** The brand still has to do the writing.
- **No fact sourcing.** They work from what's already on the page. If the attribute was never stated anywhere, they can't invent it either.
- **4 Shopify app reviews.**

---

## What this means for us

**1. They validate the market more than they threaten the wedge.** A funded team built product-level AEO for e-commerce and put real brands on it. That is evidence someone believes the thesis — useful, given `BUSINESS.md` lists "brands care enough to pay" as unproven.

**2. The price anchor is the immediate practical problem.** A mid-market DTC brand that has seen Alhena now believes AI visibility costs **$199–999/month**. We quote $3–12k plus $750–1,500/mo. We cannot win that comparison on a feature grid. The framing has to be: *they tell you which products are invisible; we go and fix 2,000 of them.* Different line item, different budget.

**3. Their $7,200 overage number is our best argument.** Their own pricing says covering a 2,000-product catalog costs roughly what our project costs — except at the end of theirs you have recommendations, and at the end of ours the facts are written.

**4. Furniture is open.** Their strength is beauty/skincare/supplements. If the niche question from earlier resolves toward furniture or configurable products, Alhena is not standing there.

**5. Partnership is a legitimate reading.** A brand could sensibly run Alhena for measurement and attribution while we do the bulk remediation. Their model can't do catalog-scale writing; ours can't measure outcomes. Worth testing in a conversation before assuming we're enemies.

**6. The thing to actually watch:** whether Alhena publishes a credible before/after linking remediation to AI recommendation volume. That is the one event that would materially damage our position, and they're closer to it than we are.

---

## Do next

- **Sign up for the free tier.** 25 conversations, 5 AI questions tracked, one engine, a visibility snapshot — costs nothing and shows exactly what their audit output looks like next to ours. Do this before the cold audits go out.
- Run their free AI visibility check on a furniture catalog and compare it to our report on the same store. That comparison is the single most useful competitive artifact available, and it's an afternoon's work.
- Watch for a Series A. Three years without a raise means either quiet profitability or trouble; a big round changes the assessment.
- If a prospect names them, don't disparage — agree, then go to catalog scale and the 50-PDP ceiling.

---

## Sources

- [Alhena pricing](https://alhena.ai/pricing)
- [Alhena — AI Visibility for E-Commerce](https://alhena.ai/products/ai-visibility)
- [Shopify App Store — Alhena: AI Shopping Concierge](https://apps.shopify.com/gleen-ai)
- [Caplight — Alhena AI funding](https://www.caplight.com/company/gleen)
- [PR Newswire — Gleen AI rebrands to Alhena AI, Feb 2025](https://www.prnewswire.com/news-releases/gleen-ai-announces-rebrand-to-alhena-ai-a-new-identity-for-a-bold-future-302368825.html)
- [Alhena — $4.9M fundraise announcement](https://alhena.ai/blog/gleen-solves-hallucination-in-generative-ai-lands-4-9m-investment/)
