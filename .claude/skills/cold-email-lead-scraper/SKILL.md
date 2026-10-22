---
name: cold-email-lead-scraper
description: Cold Email Lead Scraper. Builds a Produkto cold-email batch end to end - builds an Apollo search of e-commerce decision makers (free), buys 1,000 via Export Apollo, checks the sites for free, cleans and splits them into waves, writes a per-brand ChatGPT line, and builds the Instantly upload files. Use whenever Kelian asks for cold email leads, a new email batch, a new niche to email, or "run the lead scraper". Not for cold-call phone leads (that is pull-leads).
---

# Cold Email Lead Scraper

Turns one niche into live Instantly campaigns. Full detail, file names and the pet-batch numbers are in `GTM/cold-email/LEAD-BATCH-RUNBOOK.md`. Read it before starting.

## Gate: nothing paid runs until all four pass (added 2026-10-12 after a wasted coffee batch)

A. **No duplicate work.** List `GTM/cold-email/` for a folder with this niche and run `list_sessions`. If another session has the batch, STOP and ask Kelian which one owns it. (`storeleads_pull.py` also refuses if a pull folder for the niche exists.)
B. **Contacts first, stores second.** Export Apollo's minimum order is **1,000 leads**. Before buying any store list, build the Apollo people search in Kelian's Apollo (read-only via `/api/v1/mixed_people/search` in his logged-in Chrome — free) and confirm it shows **≥1,000 decision makers at e-commerce brands**. If it doesn't, the batch isn't viable on that route — say so before spending.
C. **E-commerce brands only, never roasters/cafés/wholesalers as the target.** Default Apollo search: US, 1–200 employees, founder/co-founder/owner/CEO/president/COO + marketing and e-commerce heads, company keyword tags `e-commerce, ecommerce, direct to consumer, dtc, online retail, subscription`, plus the niche keyword. Coffee 2026-10-12: 2,416; tea: 469.
C2. **Verify e-commerce BEFORE buying, free, in Kelian's Apollo tab** (coffee 2026-10-12: 1,362 companies → 736 real shops → 1,383 decision makers). (1) Collect company domains from the people search, partitioned by employee range × single title (free accounts cap at 5 pages × 25). (2) In the same tab, `fetch('https://<domain>/products.json')` — Shopify allows it cross-origin; keep domains returning products. (3) Paste the kept domains into People → Company → Include list → Save and Search, with the titles. That URL is what goes to Export Apollo. Apollo's companies endpoint ignores `q_keywords` — don't use it.
D. **Store Leads is no longer the default** (Kelian, 2026-10-12). Default route = Apollo search (free) → Export Apollo 1k → free website check (Shopify answers on `/products.json`; `find_site_emails.py` for shop emails). Only use Store Leads when the Apollo search can't reach 1,000. **If a store list is still wanted**, pull ONE page (~$0.56) and check how many of its domains Apollo knows before pulling more. Coffee: Apollo knew 112 of 663 (17%) → the 24-page list was mostly wasted.

Say the expected cost AND the expected contact count before Kelian pays for anything.

## Before anything

1. **Ask which niche** if Kelian didn't say. One niche per batch. Check it isn't already used (`GTM/MEMORY.md`, `MEMORY.md` niche list).
2. **State the expected cost first:** ~$18.50 per batch of ~1,000 leads: Export Apollo leads $16.50, ChatGPT ~$2. No store list on the default route.
3. **Check limits:** the Apify monthly limit (Produkto's daily scans share the account; they stop if it's hit) and Instantly's contact cap (Growth = 1,000 uploaded contacts).

## Steps

1. **Brands straight from Apollo (free).** Default route since the coffee & tea batch (2026-10-12/13, Kelian: "it worked better"): find the brands with the Apollo people search itself (gate C), NOT with a Store Leads list first. Then gate C2: keep only domains that answer `/products.json`, and put them in the Apollo Include list. Store Leads (`ecommerce_leads/store-leads-14m-e-commerce-leads`, ~$0.56/page, never the saswave scraper) only as a fallback when Apollo can't reach 1,000 (gate D).
2. **Real brands only (free).** Open every kept site and sort into brand / drop / check-by-hand; never judge by name. Show Kelian the count.
3. **Contacts (Kelian buys).** Minimum order 1,000 — the Apollo search URL must already show ≥1,000 (gate B). Kelian orders founder/owner contacts from Export Apollo, MillionVerifier check included. Never buy on his behalf. Log it with `log-cost`.
4. **Clean (free).** Drop non-niche companies, Wild One, everyone already emailed (all `sent-log-*.csv` and every Instantly campaign), and invalid emails. Mark retailers `retailer=yes`. Split good vs catch-all. Keep **at most 3 contacts per brand** (founder/CEO/president → marketing/e-commerce lead → COO; drop finance, HR, sales, supply chain, staff and other-domain addresses — see `trim_per_brand.py`), and ask Kelian before cutting. Assign `wave` = one contact per brand per wave, grouped by website, so a batch is 3 waves. **Write down how many each filter dropped.** Never cut contacts Kelian paid for without asking.
5. **Buyer questions (free).** Copy `pet_questions.py` and `pet_question_phrases.py` for the niche: best-seller per store, a hand-written buyer phrase per brand (`R` retailer, `N` not niche, `SKIP`).
6. **ChatGPT answers (Apify).** Copy `pet_ask.py`: one-line questions, one batch, run in the background. Failed runs still bill.
7. **Lines (free).** Pick one real competitor product per answer (not the prospect itself); flag the rest. Line: *I asked ChatGPT "{question}" today. One of its picks was the {product} by {brand}, a competitor of {company}.* (Name their company: the old "another brand in your category" wording made Sophie's Pet Food think we'd confused them with the competitor, 2026-10-13.) Show Kelian a sample before building.
8. **Upload files.** Copy `pet_build_upload.py` → good / catch_all / noline files plus `-wave1` versions. Create wave-1 campaigns in Instantly **paused**, settings as in the runbook; Kelian launches.

## After

- Log every Apify run with `log-cost` (run costs from the Apify run history API).
- Record the batch in `GTM/MEMORY.md`: campaign names, counts, contacts now off-limits.
- Add wave N+1 only after wave N has fully sent.
- Save any step done in-session as a script, and update the runbook if the process changed.
