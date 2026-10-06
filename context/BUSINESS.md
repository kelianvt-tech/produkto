# BUSINESS.md

*What this business is. Current state — overwrite this file as things change, don't append to it.*

**Last updated:** 3 August 2026
**Stage:** Pre-validation. Audit tool built and tested on one catalog. Demand unproven.
**Name:** Not chosen yet.

---

## In one sentence

We make ecommerce catalogs readable by AI, so that when a buyer asks ChatGPT for a product, the brand's individual products can actually be recommended.

---

## The problem

Buyers have started asking AI assistants for products instead of searching Google. The assistant reads product data and recommends two or three options. The buyer usually takes one of them.

The catch: AI reads *facts*, not marketing. It needs stated attributes — dimensions, material, capacity, care, durability. Most ecommerce brands spent a decade writing product pages for humans and for Google, so those facts were never written down. The products are excellent and the pages are beautiful, and the model skips them anyway because there is nothing to match against.

Adobe measured this across US retail: product detail pages score **66% machine-readable**, the worst of any page type on a retail site. Their words: *"Retailers have thousands of SKUs, and much of the content is currently invisible to LLMs."*

We found the same thing on the first catalog we ran the tool against. M&O Living — a Barcelona DTC furniture brand, used as a test case — 86 products, **16.8/100** on spec-query retrievability. Six attributes buyers actively search on — care instructions, indoor/outdoor suitability, removable covers, load capacity, assembly requirement, fabric durability — appear on **zero** products. Not badly written. Absent.

---

## Why now

The channel flipped from marginal to valuable inside twelve months.

| Signal | Figure |
|---|---|
| AI referral traffic to US retail, Q1 2026 | **+393% YoY** |
| AI traffic conversion vs. other channels, Mar 2026 | **+42% better** |
| The same comparison, Mar 2025 | **38% worse** |
| Revenue per visit, AI vs. non-AI | **+37%** |
| Consumers who have used AI to shop | **39%** |

Source: Adobe, across 1T+ visits to US retail sites.

That reversal is the whole reason this is a business now and wasn't last year — a channel converting better than anything else, growing at triple digits, that most brands are structurally invisible to.

**The counterweight, stated honestly:** AI is still under 5% of most brands' traffic. We are selling position in a channel that is arriving, not one that has arrived. That shapes how we price, what we promise, and what we measure.

---

## What we sell

**Diagnosis, then remediation.**

**1. The audit.** Point our tool at a store, get a report: what the catalog fails to state, which products are worst, which buyer queries they are invisible for, how they compare to named competitors. Free or low-cost. This is the lead magnet, the sales pitch, and the measurement baseline in a single artifact.

**2. The remediation.** Actually fill in the missing attributes across the catalog. Priced as a project scaled to catalog size — roughly $3k at 500 SKUs to $12k at 5,000.

**3. Maintenance.** New products, re-audits, tracking movement. $750–1,500/month.

**Why front-loaded rather than a flat monthly fee.** The work is front-loaded, and front-loaded pricing is insurance against churn. At $300/month, a customer who leaves in month two paid $600 for fifteen hours of work. At $7k plus $1k/month, a customer who leaves in month three paid $10k and the work is covered.

**Where this is heading:** an agent that does the remediation automatically. That is the destination and it is what makes this scalable. But an agent is only worth building once we know *which fixes actually move visibility* — and nobody knows that yet, including the funded competitors. The manual work is how we find out. See METHODOLOGY.md.

---

## How we sell (2026-09-28)

Demo first, then the tool. A brand books a demo on the website; Kelian walks them through Produkto on the Clubhouse Skin demo catalog and shows how it would read for their brand. If they pay, they get the onboarding link, set up their own brand and store, and use the dashboard themselves. This sits alongside the audit / remediation / maintenance offers above rather than replacing them in this file; which of them survive contact with real demos is still open.

**Produkto pricing, to test in demos (2026-09-28, see `DECISIONS.md`):** monthly subscription, priced by buyer questions tracked. All plans: unlimited products, daily scans, competitors found automatically.

| Plan | Price | Buyer questions |
|---|---|---|
| Starter | $99/mo | 25 |
| Growth | $297/mo | 75 |
| Custom | per question, from 150 | brand chooses |

Scan cost (~$0.65 per question per month) is absorbed, kept under ~15–20% of the price. Published at `produkto-site/dist/pricing.html`. No customer has paid at any price yet.

**Tension to resolve:** the "Why front-loaded rather than a flat monthly fee" argument above argues against exactly this kind of ~$297/month subscription. That argument was written for the manual remediation service; Produkto is a self-serve tool with near-zero labour per customer, so churn costs less. Both stand until demos show which model brands buy.

---

## Who we sell to

Mid-market DTC brands. Roughly $1–5M a year, a few hundred SKUs or more, no in-house ecommerce ops person to run a tool on their behalf.

The real filter is **catalog size × budget**, not revenue. A brand with 3,000 products doing $80k/month is a better customer than one with 40 products doing $300k/month — the second can fix their whole catalog in an afternoon and doesn't need us.

Works best where buyers ask spec-shaped questions: furniture, technical apparel, skincare with actives, supplements, tools. Works poorly for impulse and aesthetic-driven purchases — nobody asks ChatGPT which t-shirt looks cool.

Full detail in ICP.md.

---

## How we're different

Everyone in this market sells **measurement**. Profound, Scrunch, Alhena, Searchable, Semrush — they hand you a dashboard that says you're invisible. Then the brand stares at it and nothing happens, because there is nobody at a 20-person DTC company whose job is to action a visibility dashboard across 2,000 products.

We do the work, and we're accountable for the outcome.

The differentiation is structural rather than feature-level, which is why it holds against every competitor at once:

- They sell software. We sell the result.
- They serve enterprise or their own installed base. We serve mid-market brands nobody is calling.
- They build for the median customer. We go deep in one category at a time.

**Do not claim nobody does this for ecommerce.** Yotpo Discover and Goodie both do, and a prospect will catch it. The accurate claim: *nobody does catalog-scale remediation for mid-market DTC with a human accountable for the result.* See COMPETITORS.md.

---

## The window

**Six to twelve months.**

Yotpo Discover is the closest competitor — ecommerce-native, SKU-level, with agents that act rather than report. Their current release targets **$10M+ GMV brands**, and they have publicly stated that a version for smaller brands is planned. Their product pages have been shipping through mid-2026, so they are actively in motion.

We are renting this position, not owning it. That's acceptable — a good business can be built inside a window — but it means speed matters more than polish, and what we accumulate along the way (the methodology) matters more than what we ship first.

---

## What's actually true today, and what isn't

**Proven:**

- The problem is real and measurable. The one catalog we've scored came in at 16.8/100.
- The tool works. 86 products audited, specific gaps identified, repeatable.
- Budget exists in the category. AEO-as-a-service went $68M (2024) → $340M projected (2027); mid-market retainers run $3–10k/month.

**Not proven — and these are the ones that matter:**

- That mid-market DTC brands care enough to pay. No customer conversations yet.
- That remediation actually moves AI visibility. Nobody has demonstrated this, us included.
- That the ROI works today rather than in two years.

Until those three are answered, everything above is a well-researched hypothesis rather than a business.

---

## Next milestone

Fifteen conversations with DTC brands, and twenty cold audits sent. Kill criteria are written down and should be honoured rather than rationalised.
