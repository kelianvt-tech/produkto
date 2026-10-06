# Opportunities list — next product step (planned 2026-10-05, not started)

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
