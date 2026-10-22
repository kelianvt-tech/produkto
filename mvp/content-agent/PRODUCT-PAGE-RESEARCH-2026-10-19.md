# What AI-friendly product pages do: takeaways for the Product page fixes agent

Researched 2026-10-19. Read live in a browser: Crutchfield (Sony WH-1000XM5), Sweetwater (Shure SM58), REI (Half Dome 2), Sephora (The Ordinary Niacinamide), Anker (Nano 30W), Patagonia (Better Sweater). **Chewy and B&H blocked the browser** (blank page / Cloudflare check), so they're not covered.

## First, the evidence check (read this before the takeaways)

The pasted list of 8 stores is a list of strong *SEO* pages. It came with no proof that AI cites them. I checked what we can check for free: the citations in Produkto's own 1,150 collected answers (almost all skincare, from Clubhouse Skin's scans).

- Sephora: cited 81 times. The others: Crutchfield 1, the rest 0. That is because our questions are about skincare, not proof that the others aren't cited elsewhere.
- **The most useful finding:** small DTC brands get their own product pages cited, and those pages are **short**:

| Cited page | Times cited | Description length |
|---|---|---|
| mychelle.com Instant Radiance Vitamin C Oil | 26 | 173 words |
| dermae.com Vitamin C Glow Face Oil | 21 | 58 words |
| cetaphil.com Extra Gentle Daily Scrub | 18 | – |
| bynatureskincare.com Brightening Face Oil | 16 | 78 words |
| medik8.com C-Tetra | 10 | 97 words |
| byoma.com Creamy Jelly Cleanser | 8 | 97 words |

What they share is not depth. They **state the exact things buyers ask, in the buyer's words**: "suitable for all skin types, including sensitive skin", "non-comedogenic", "fragrance-free", "7% vitamin C (tetrahexyldecyl ascorbate)", "Perfect for: dull skin, uneven tone", "the perfect option for those new to vitamin C". Each sentence is a ready-made answer to a buyer question.

Caveat: citation also depends on brand recognition, the question, and luck. One niche, one month of data. It's a pattern to act on, not a proven rule.

## Takeaways the agent can write itself (only from facts the store states)

1. **Labelled fields beat prose** (Sephora, Anker, Patagonia). "What it is:", "Skin type:", "Good for:", "Free of:", "Key ingredients:" with the value after it. AI lifts a labelled line as an answer. Our spec table does this partly; extend it to a short "Good for / Not for" block.
2. **Say who it's for and what problem it solves, in buyer words.** "Best for oily skin" is in Sephora's H1; MyChelle has "Perfect for:". Our rule 3 bans superlatives, which is right, but "best for <skin type/use>" is a fit statement, not hype. Allow it when the store states the fit.
3. **Put use-case and key spec in the title** (Sephora: "…Serum for Oily Skin"). Our title rule already does this. Keep it.
4. **Feature → why it matters, one line each** (REI, Patagonia): "Raglan sleeves, so the pack straps don't rub." Bullets with a benefit beat bare feature lists.
5. **State honest limits** (Crutchfield: "headband does not fold up"; Patagonia: "knitted garments are prone to pilling"). Buyers ask "does it fold?"; a stated "no" still gets the page used as the answer. Allowed only when the store states it.
6. **Exact numbers, with units and the named form** (Anker output per voltage; Medik8 "7% tetrahexyldecyl ascorbate"). Never round; never drop the unit.
7. **How to use / care** as its own short block (Sephora, Patagonia). A common buyer question we currently only cover if the facts mention it.
8. **"Compared with" lines** (Crutchfield "Frequently compared", REI "updated from previous version"). For a store's *own* products only: "Lighter than our X", "the 50 ml version of Y". Comparisons with other brands belong to AEO articles, not the product page.
9. **Structured data.** Every store had Product schema with brand, GTIN/MPN, rating and offers; Sweetwater, Sephora and Medik8 add **FAQPage** schema; REI and Sephora use ProductGroup with variants. Shopify themes cover the basics. Our FAQ drafts should ship with FAQPage markup when published (to check: does `shopify_connect` publish it today?).

## Takeaways for Opportunities (things only the merchant can add)

These came up on almost every top page, and the agent can't write them. Each could be its own Opportunities card, triggered when a page lacks it:

- **Customer reviews on the page** (all six). Card: "This product has no reviews showing. Install or turn on a review app; AI repeats what reviewers say."
- **Customer Q&A** (Crutchfield, Byoma, Sweetwater). Card: "Buyers asked AI X about this product; add it as a Q&A." We already know the questions from scans, so this card can list them.
- **Video demo** (Crutchfield, Sweetwater, Sephora "See it in real life"). Card: "Add a short how-to or demo video; it gets marked up as VideoObject."
- **Expert or founder note with a name** (Crutchfield "Jeff Miller, expert since 2006"; Sweetwater "Product Research Team"; Medik8 "Dr. Nora"). A named person behind the advice. The agent can draft it from the founder's own words, but the merchant has to supply and sign it.
- **Clinical / test results** (Sephora: "35 subjects, 8 weeks"). Only if the brand has them.
- **Manual or spec-sheet download** (Anker). For technical products.
- **Make sure bots can read the page** (Chewy and B&H blocked a normal browser). Card when our own fetch of the product page fails: "AI crawlers may be blocked from this page."
- **Link to a buying guide** (REI "How to choose a backpacking tent"). Links to an AEO article when one exists.

## What to change in the agent (proposed, not built)

- `drafts.PRODUCT_FIX_RULES`: add a labelled "Good for / Key facts / How to use" block, allow stated fit statements ("for oily skin"), feature → benefit bullets, and stated limits.
- Keep the short length: the cited DTC pages are 60–170 words. Don't chase Crutchfield's 1,400.
- Opportunities: add the merchant-only cards above, starting with Reviews and Customer Q&A (we already have the questions).

## Bug seen along the way

The Peau De Clubhouse Hat draft says "Priced at £25.00" (the store shows €30,95), although rule 6 forbids price in the description. The fact check passed it, so it needs a look.
