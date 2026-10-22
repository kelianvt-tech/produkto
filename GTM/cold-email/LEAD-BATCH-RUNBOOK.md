# Lead batch runbook

How one cold-email batch is built, from a niche to live Instantly campaigns. Written 2026-10-09 from the pet batch (7–8 Oct): 771 contacts, 242 brands, ~$24.85.

**Before you start:** pick ONE niche. Check the Apify monthly limit: Produkto's daily scans share the account and stop if it's hit. Check Instantly's contact cap (Growth = 1,000 uploaded contacts; we're at ~800 after the pet batch).

---

## Cost per batch (pet batch numbers)

| Step | Tool | Cost |
|---|---|---|
| 1. Store list | Apify Store Leads 14M | $6.50 (12 pages) |
| 2. Contacts + email check | Export Apollo + MillionVerifier | $16.50 (1,000 leads) |
| 3–4. Clean, best-sellers, questions | scripts + by hand | $0 |
| 5. ChatGPT answers | Apify ChatGPT scraper | $1.14 per 230 questions (+$0.71 lost to a failed run) |
| 6–7. Lines, upload | scripts + Instantly | $0 |
| **Total** | | **~$25 → ~3 cents per contact, ~$100 per 1,000 brands** |

Funnel to expect: 1,161 stores → 432 real niche brands → 1,000 leads → 771 usable contacts → 242 brands (~3 contacts per brand).

---

## Step 1: Find stores in the niche (Apify, ~$0.56 per page)

- Actor: **`ecommerce_leads/store-leads-14m-e-commerce-leads`**, one run per page of results for the niche. This is the ONLY store source. Never use the saswave storeleads-scraper.
- Pet batch: 12 runs → 1,161 rows. Save the CSVs in `GTM/cold-email/storeleads-<niche>-<date>/`.
- Check every homepage for free (curl title + description) and sort into: **niche brands / dropped / check by hand**. Open the site, never judge by company name. Pet: 432 / 458 / 88.
- Write the brand domains, one per line, to `storeleads-<niche>-<date>/apollo-domains.txt`.
- ⚠ The homepage-sorting script was run inside the session and not saved. Save it as `store_check.py` on the next batch.

## Step 2: Buy contacts (Export Apollo, $16.50 per 1,000)

- Kelian orders from Export Apollo (leadus.in): Apollo people search on the domains from `apollo-domains.txt`, founders/owners/CEOs, with MillionVerifier email check included.
- Log the payment with the `log-cost` skill.
- ⚠ Exactly how the domain list was handed over isn't recorded. Kelian to fill in.

## Step 3: Clean the list (free)

- Drop: non-niche companies, Wild One (named as a customer), anyone already emailed (all `sent-log-*.csv`, every Instantly campaign), invalid emails.
- Keep retailers but mark `retailer=yes`: they get email 1 without the ChatGPT line.
- Split by MillionVerifier result: `ok` → good file, `catch_all`/`unknown` → catch-all file.
- Give every contact a `wave` number: one contact per brand per wave, grouped by **company website**, not email domain.
- Output: `<date>-<niche>-apollo-good.csv` and `<date>-<niche>-apollo-catch_all.csv` (columns: email, first_name, last_name, company_name, title, website, city, state, country, email_result, wave, retailer).
- ⚠ Done in-session last time. Record counts dropped at each filter this time (1,000 → 771 wasn't written down).

## Step 4: One buyer question per brand (free)

- `python3 pet_questions.py`: finds each store's best-seller (Shopify best-selling collection, falls back to `/products.json`), skipping gift cards, bundles, samples and under-$5 items. Pet: 248 of 262 found.
- Write a buyer phrase per brand by hand in `pet_question_phrases.py` (e.g. "freeze-dried raw dog food"). Mark `R` = retailer, `N` = not a niche brand, `SKIP` = exclude.
- Question: *"What's the best {phrase} to buy online for around ${price}?"*. Leave the price out where it reads wrong (`NOPRICE` list in `pet_ask.py`).
- Scripts have the date and file names hard-coded: copy and rename them per batch.

## Step 5: Ask ChatGPT (Apify, ~half a cent per question)

- `python3 pet_ask.py`: sends every unique question in one batch to `apify/chatgpt-search-scraper` through `mvp/app/apify_answers.py`. Run it in the background; it takes a while.
- Questions must be one line (the actor splits on newlines and bills each line).
- If a run fails partway, it is still billed. Pet: run 1 failed after 144 of 230 ($0.71), run 2 got all 230 ($1.14).

## Step 6: Write the ChatGPT line (free)

- From each answer, pick a competitor product: a real brand that isn't the prospect itself. Mark brands with no usable competitor. Pet: 224 ok, 6 no usable competitor.
- Save as `pet-apollo-lines-<date>.json` with `question`, `competitor_brand`, `competitor_product`, `flag` (`ok` or a reason).
- Line in the email: *I asked ChatGPT "{question}" today. One of the products it recommended was the {product}, made by {brand}, another brand in your category.*
- ⚠ The picking was done in-session with no script. Write `pet_lines.py` next batch and check a sample by eye.

## Step 7: Build files and upload to Instantly (free)

- `python3 pet_build_upload.py` → three upload files, each with a `-wave1` version:
  - **good**: verified emails with a line
  - **catch_all**: catch-all emails with a line
  - **noline**: retailers + brands without a usable line
- Instantly campaigns, wave 1 only, created PAUSED, Kelian launches:
  - good → 4 inboxes, 30/day cap
  - catch-all and no-line → the other 3 inboxes, 9/day cap each
  - US Eastern office hours, Mon–Fri, plain text, tracking off
  - Copy from `SEQUENCE.md` (current version)
- Add wave N+1 only after wave N has fully sent, so no brand gets two emails on one day.

## After launch

- Log every Apify run and the lead purchase with the `log-cost` skill.
- Add the batch to `GTM/MEMORY.md`: campaign names, counts, and that these contacts are now emailed and off-limits.
