# Product

<!-- impeccable:product-schema 1 -->

Scope: the Produkto app (app.getprodukto.com — onboarding and dashboard). The marketing site (`produkto-site/`) is out of scope for this file.

## Platform

web

## Users
Founders and marketing leads at mid-market US DTC e-commerce brands (roughly $1–5M/year, a few hundred to a few thousand SKUs, no in-house e-commerce ops person). They set up their own store after paying, then check the dashboard themselves to see whether AI assistants recommend their products and what to fix. Secondary user today: Kelian, demoing the app live on the Clubhouse Skin catalog.

## Product Purpose
Paste a Shopify store URL and Produkto measures, daily, how often AI answers to real buyer questions mention each product in the catalog — visibility, average position, share of voice, and cited sources — against every competitor found in those answers. Opportunities turns lost questions into ranked fixes. Success: a merchant understands where they stand at product level and acts on it, and the trend shows whether fixes move visibility.

## Positioning
Self-serve tool. Whole-catalog, product-level AI visibility at a mid-market price: plans are priced by buyer questions tracked, with unlimited products, where comparable tools cap SKUs (Glara 20–50 products, Alhena 25–50 pages/month). Never claim "nobody does this."

## Operating Context
- Onboarding: Store → Brand (AI-filled profile the merchant verifies) → Catalog → Topics → Questions → scan.
- Dashboard: catalog overview and a per-product drill-down; tabs Overview, Answers, Mentions & Citations, Opportunities. Every tab follows the period filter (Daily/Weekly/Monthly/Quarterly).
- Daily scans run on a hosted server; buyer questions stay editable (edits start a new trend line).
- Merchants are mostly American: dates, times and "today" must read correctly on a US clock.
- Used in live sales demos — first impression on a call matters.

## Capabilities and Constraints
- Flask app, server-rendered, minimal dependencies; Python standard library preferred.
- Comparison is always against every competitor found in answers; nothing to configure.
- Generic advice with no brand or URL is never shown or counted as a product.
- Features in development hide behind switches in `config.py`.
- Open: pricing model and whether a done-for-you tier exists (no customer has paid yet).

## Brand Commitments
- Name: Produkto. Logo: navy P app-icon; animated P mark used in onboarding (keep it fully in its canvas at its approved size).
- Copy follows `skills/produkto-copy/SKILL.md`: American spelling ("catalog"), plain language, no promised results, no hedge-and-tease paragraphs, never publish the scan recipe.
- AI engines identified by their logos (ChatGPT, Google AI Overview, Perplexity), not colored dots.
- Reference products the owner copies deliberately: PromptWatch (overview KPI strip, trend), Peec AI (product page, brand profile), Searchable (chart-led layout, Opportunities). Detailed visual decisions live in the project `MEMORY.md`.

## Evidence on Hand
- Real scan data in the server database; Clubhouse Skin is the demo catalog.
- No paying customers, testimonials or case studies — never fabricate them.
- M&O Living is the owner's family business: never present it as a customer.

## Product Principles
1. Measure the product, not the brand — every number is about specific products.
2. Honest data over impressive data: show age and gaps, never invent trend or freshness.
3. Judge from the merchant's side, on the morning something fails.
4. Build only what a real conversation asks for.
5. Plain numbers a non-analyst reads at a glance (mention rate, not blended scores).
