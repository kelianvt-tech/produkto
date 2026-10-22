# Opportunities list — next product step (planned 2026-10-05; steps 1-2 built 2026-10-06, step 3 built 2026-10-09; all behind SHOW_OPPORTUNITIES, not live)

Modelled on Searchable's Actions → Opportunities (walkthrough video, 5 Oct 2026). Kelian approved the plan and parked it: this is the next thing to build when product development resumes.

## What it is
A sidebar item **Opportunities** (under Buyer questions) with a count badge. A list of fixes, most important first. Each fix can be marked **Done** or **Dismissed**; Dismissed moves to a reopenable "Dismissed" tab (my recommendation, not yet confirmed by Kelian).

## Three kinds of fix, all from data we already collect
1. **Questions you're losing.** A buyer question where competitors are named and the merchant's products are not. Shows the winners. Source: `answers` + `mentions`.
2. **Sites to get onto.** The domains ChatGPT cites most for the questions the merchant loses, which mention competitors but not the merchant. Source: `answers.citations`.
3. **Missing product details.** Attributes the winners' product pages state and ours doesn't (e.g. skin type). Source: `build/attributes.py`, run on our page and on the winners' URLs from the answers.

## Ranking
How many answers the problem affects in the last 30 days. No invented impact score.

## Each fix shows
One plain sentence, the evidence (answers + winners, click to read), the product with its image, Done / Dismiss.

## Deliberately not included
- No promised results. Frame as "what the winners have that you don't". Remediation moving visibility is still unproven.
- No outreach emails or automatic page writing (that's the Content agents page, later).
- Done records a date only. Before/after scans can later show whether anything moved, which is the evidence `METHODOLOGY.md` needs.

## Build order
1. Lost questions + list page + Done/Dismiss (all data exists, quickest).
2. Sites to get onto.
3. Missing product details (needs fetching competitor pages, plus the `build/` checker).

Cost: steps 1–2 are free per scan (reuse saved answers). Step 3 fetches pages: free via plain fetch, a few cents with Firecrawl for blocked stores.

## Step 3 as built (2026-10-09)
`app/page_gap.py`, "Content Gap" cards under On Page (renamed from Missing Details to match Searchable, 9 Oct). For each buyer question you lost outright, the competitor product pages AI named (its link, or found through the brand's Shopify `/search/suggest.json` when ChatGPT gave none) are compared with your page for that question: the question's own words, and the product data the page publishes (review rating, brand, barcode, price). A gap needs two or more winning pages. A set question covering several of your products is one card. Plain-request fetch only (free); pages that block it (Boots, Next, John Lewis) are skipped, never guessed. Cached 14 days in `page_facts`, refreshed in the background at most hourly when the page opens. `build/attributes.py` was not used: its attributes are furniture-only.

## Also built 2026-10-09
- **Before and after on Done cards** (`opportunities.before_after`): how often your products were named in answers to the card's question(s) in the 14 days before Done vs since, same engines. Says "too early" under 5 answers, and always says it shows what changed, not why. A Done card whose problem has gone away stays in the Done tab. Free.
- **Reading the most-cited page** behind each Retailer/Citation Gap card: its title, which competitor brands it names, and whether it names you. Plain fetch, free.
- **AI sentence per cited page** (`page_gap.explain`): built, OFF (`PRODUKTO_PAGE_EXPLAIN=1`). Roughly $0.05-0.10/store/month.
- **Paid browser for blocked pages** (Apify RAG Web Browser, $0.0019/page): built, OFF (`PRODUKTO_PAGE_BROWSER=1`). Tested 9 Oct: Boots still returns its bot wall, John Lewis returns a title and no product data. Not worth switching on yet.
