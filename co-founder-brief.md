# Making e-commerce catalogs readable by AI

*A brief. Written August 2026. No name chosen yet.*

---

## The short version

When someone asks ChatGPT "what's a good outdoor sofa with removable covers under €1,500," the model reads product data and recommends two or three options. The buyer usually takes one of them.

To be one of those options, a product page has to *state* facts — dimensions, material, load capacity, care instructions. Most e-commerce brands spent a decade writing product pages for humans and for Google, so those facts were never written down anywhere a machine can read them. The products are fine. The pages are beautiful. The model skips them because there's nothing to match against.

I built a tool that measures this across a whole catalog, and the plan is to sell the fix, not the dashboard.

---

## 1. Why catalogs are invisible

AI reads stated facts, not marketing copy. "Crafted with care in our Barcelona workshop" is unmatched against any query. "Seat height 42cm, removable machine-washable cover, suitable for outdoor use" matches dozens.

Adobe measured machine-readability across US retail and found **product detail pages score 66% — the worst of any page type on a retail site.** Their words: *"Retailers have thousands of SKUs, and much of the content is currently invisible to LLMs."*

The gap isn't quality. It's that nobody wrote the specs down.

---

## 2. Why now

The channel flipped from marginal to valuable inside twelve months.

| Signal | Figure |
|---|---|
| AI referral traffic to US retail, Q1 2026 | +393% YoY |
| AI traffic conversion vs other channels, Mar 2026 | +42% better |
| The same comparison, Mar 2025 | 38% *worse* |
| Revenue per visit, AI vs non-AI | +37% |
| Consumers who have used AI to shop | 39% |

*Source: Adobe, across 1T+ visits to US retail sites.*

That reversal — from 38% worse to 42% better in twelve months — is why this is a business now and wasn't last year.

**The counterweight, stated plainly:** AI is still under 5% of most brands' traffic. This is a channel that is arriving, not one that has arrived. It changes what we can honestly promise and how we price.

---

## 3. What's actually built

A Python audit tool. Minimal dependencies, mostly standard library.

- Point it at a Shopify store, it crawls the product pages
- Scores the catalog on two things: **spec-query retrievability** (can a model answer a buyer's spec-shaped question from this page?) and **schema completeness** (is the structured-data plumbing there?)
- Output goes to `audits/<store>/<timestamp>.{json,md}` — never overwritten, so re-runs produce a diff and the diff is the proof of work

It's not a product. There's no UI, no login, no recurring jobs, no Shopify app, and it has write access to nobody's store. That constraint is deliberate — see section 8.

---

## 4. The one real result

I ran it end to end on **M&O Living**, a Barcelona DTC furniture brand. 86 products.

**Spec-query retrievability: 16.8 / 100.**

Six attributes that buyers actively search on appear on **zero** products:

- care instructions
- indoor/outdoor suitability
- removable covers
- load capacity
- assembly requirement
- fabric durability

Not badly written. Absent.

**Important caveat, and I'd rather you hear it from me:** M&O Living is my father's shop. I run their marketing. It's a real catalog with real revenue and the numbers are real, but it is not an arm's-length customer and it is not a case study. It's a test catalog that proved the tool works. Anyone who calls it a client is overselling.

---

## 5. The business

**Diagnosis, then remediation.**

1. **The audit** — free or low-cost. Simultaneously the lead magnet, the sales pitch, and the measurement baseline.
2. **The remediation** — actually fill in the missing attributes across the catalog. Priced by catalog size: roughly $3k at 500 SKUs to $12k at 5,000.
3. **Maintenance** — new products, re-audits, tracking movement. $750–1,500/month.

Front-loaded rather than a flat monthly fee, because the work is front-loaded and it's insurance against churn. At $300/month a customer who leaves in month two paid $600 for fifteen hours of work. At $7k plus $1k/month, a customer who leaves in month three paid $10k and the work is covered.

Market context: AEO-as-a-service went $68M (2024) → $340M projected (2027). Mid-market retainers in adjacent categories run $3–10k/month, so budget exists at this price point.

---

## 6. Who it's for

Mid-market DTC brands. Roughly $1–10M/year, 500–5,000 SKUs, under ~25 people, no in-house e-commerce ops hire.

The real filter is **catalog size × budget**, not revenue. A brand with 3,000 products doing $80k/month is a better customer than one with 40 products doing $300k/month — the second can fix their whole catalog in an afternoon and doesn't need anyone.

Works where buyers ask spec-shaped questions: furniture, mattresses, technical apparel, tools, skincare with actives, supplements, pet and baby products. Rule of thumb: if you can picture the buyer's question containing a number or a material, the category qualifies. Works poorly for aesthetic-driven purchases — nobody asks an AI which cushion looks nicer.

---

## 7. Competition, honestly

Almost everyone in this market sells **measurement**. Profound, Scrunch, Alhena, Searchable, Semrush — they hand a brand a dashboard saying it's invisible. Then nothing happens, because there is nobody at a 20-person DTC company whose job is to action a visibility dashboard across 2,000 SKUs.

The intended difference is structural rather than feature-level: they sell software, we sell the result and stay accountable for it.

**What I won't claim:** that nobody does this for e-commerce. Yotpo Discover and Goodie both do adjacent versions and a prospect would catch it. The accurate, narrower claim is that *nobody does catalog-scale remediation for mid-market DTC with a human accountable for the outcome.*

**Yotpo Discover is the real threat.** E-commerce-native, SKU-level, agents that act rather than report. Their current release targets $10M+ GMV brands and they've publicly said a version for smaller brands is planned. Their product pages have been shipping through mid-2026.

Realistic window: **six to twelve months.** We'd be renting this position, not owning it.

---

## 8. What is not proven

This is the section that matters most, and I'd rather lead you to it than have you find it.

1. **That mid-market DTC brands care enough to pay.** Zero customers. Zero customer conversations so far. This is a well-researched hypothesis, not a validated business.
2. **That remediation actually moves AI visibility.** Nobody has demonstrated this — not us, not the funded competitors. We can show a catalog is unreadable. We cannot yet show that fixing it gets you recommended.
3. **That the ROI works today rather than in two years.** At under 5% of traffic, a brand paying $7k is buying position in a channel that hasn't fully arrived.

Number 2 is the interesting one. It's the open question in the entire category, and whoever answers it first has something durable.

There are written kill criteria, and the intention is to honour them rather than rationalise around them.

---

## 9. Where it goes

**Manual service now → methodology accumulates → agent later.**

The agent is the destination and it's what makes this scale. But it's only worth building once we know *which fixes actually move visibility* — and that's precisely unproven #2. Building the agent first means automating a guess.

So the manual work isn't a stopgap, it's the instrument. Everything learned from a real catalog goes into a methodology document, and that file is the only genuinely proprietary asset in the whole thing.

---

## 10. Where I am, and what I need

**Current priority is demand validation, not building.** The tool is good enough. The next milestone is twenty cold audits sent and fifteen conversations with DTC founders — asking about their world, not pitching.

Honest picture of the next 90 days: it's outreach, manual catalog work, and interviews. It is not architecture. If you came in expecting to design the agent on day one you'd be bored by week three, and I'd rather say that now.

What I'm short of is engineering. I can build enough to prove a point; I can't build the thing this becomes. That's the gap.

---

## Open questions I'd want to argue about

- Is the wedge product-level or brand-level? I think product-level, but it's worth pressure-testing.
- Is remediation a service business that later becomes software, or is that a story people tell themselves before building a services company by accident?
- Does the six-to-twelve-month window mean move fast, or mean don't start?
