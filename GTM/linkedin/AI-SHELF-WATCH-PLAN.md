# AI Shelf Watch: plan (not built yet)

**Written:** 19 October 2026 · **Status:** planned, nothing running, nothing spent.

A LinkedIn content series built on our own data, like Searchable's "ChatGPT's drop of UTM tags was temporary" chart, but for products: ask AI the same buyer questions every day and report what changes.

## What it measures

A fixed panel of **50 buyer questions**, 10 each in 5 categories: coffee & tea, pet, skincare, apparel, home. Real phrasing with a price, e.g. "What's the best whole bean coffee to buy online for around $24?" Frozen once chosen, so the trend stays comparable.

Asked **once a day on ChatGPT** through Apify (`apify/chatgpt-search-scraper`, the same actor Produkto's scans use). For each answer, store: date, question, products named, brands, cited sources, whether product cards appeared.

## What it lets Kelian post

- "ChatGPT changed its top pick for X% of coffee questions this week."
- "Reddit's share of cited sources in pet went from X% to Y%."
- "Product cards now show in X% of answers, up from Y% a month ago."
- When OpenAI changes something (like the 8–15 Oct UTM episode), we see it in our own data that week.

Every post states the sample: "50 buyer questions, 5 categories, ChatGPT, asked daily since [date]."

## Cost

| Option | Answers/month | Price | Per month |
|---|---|---|---|
| **ChatGPT only, daily (recommended start)** | ~1,500 | $0.005/answer | **~$7.50** |
| + Perplexity, weekly | +~215 | $0.013/answer | +~$2.80 |
| + Google AI Overview, daily | +~1,500 | $0.002/answer | +~$3.00 |

Prices from `mvp/app/config.py` (Bronze tier). Extraction of products from each answer can be done locally (no OpenAI cost) because the answers are short lists.

## Risks

- **Shares the Apify account with Produkto's daily scans.** If the monthly cap is hit, client scans stop. Add a budget check before each run, or use a separate Apify account.
- Small samples move a lot day to day. Report weekly averages, not single days, unless something drops off a cliff.
- One engine, one account, one location: say so in small print.

## To build (when Kelian says go)

1. Pick the 50 questions (reuse the coffee and pet phrasings from `GTM/cold-email/*-questions-*.json`, add 30 for skincare, apparel, home).
2. Small script: daily Apify call → SQLite → weekly summary file in `GTM/linkedin/shelf-watch/`.
3. Run on the Hetzner server (it's always on), not Kelian's Mac.
4. After 2 weeks of data, first post.
