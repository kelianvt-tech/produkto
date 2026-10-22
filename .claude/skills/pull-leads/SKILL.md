---
name: pull-leads
description: Pull a batch of US e-commerce founder leads (name, email, mobile) for Produkto cold calls, emails and DMs, using the Apify Leads Finder actor, then split them into a with-phone CSV and a no-phone CSV. Use whenever Kelian asks for more leads, founders, phone numbers, a new batch, or "run another batch of N".
---

# Pull leads

## Kelian's lead rules (2026-10-05, non-negotiable)

1. **One niche per batch.** Every lead in a batch sells the same kind of product (e.g. scented candles, protein powder, beard care). Ask Kelian for the niche if he hasn't named one; never pull a mixed bag across industries. Put the niche in the file name and set `keywords` to that niche.
2. **B2C e-commerce only.** The company sells its own products online to consumers. Drop anyone selling to businesses: ingredient or pigment suppliers, wholesalers, private-label / white-label makers, manufacturers, distributors, B2B marketplaces, agencies, software, services, clinics, gyms, retailers of other brands. Check each company's website when unsure (homepage title/description); a "wholesale" or "for brands" homepage means drop. (First live calls on 2026-10-05: RK Pigments sold D&C colour pigments to cosmetics makers and said "we're B2B".)
3. **Every lead has the owner's name and the owner's own phone number**, not a generic company line. Only rows with a mobile/direct number go to the call list; the rest go to the no-phone file.
4. **Phones in +1 E.164 form (`+1XXXXXXXXXX`) and US only.** Close is set to Spain, so a number without +1 gets saved as +34 and the dialer calls Spain (happened 2026-10-05). After import into Close, count phone prefixes: all must be `+1`.

Cheap founder leads for Produkto outreach. ~$0.0017 per lead plus $0.01 per mobile found (charged only when found). Tested 2026-09-29: 37% of leads came back with a mobile.

## The target is phone numbers

When Kelian asks for N leads for calling, N is the number of **mobiles** he wants. The actor can't filter to phone-only, so pull ~3.5× N and say so before running. Report the phone count first.

## Steps

1. **Check the Apify budget first.** Produkto's daily scans run on the same Apify account; if lead runs use up the monthly limit, scans stop (including the Clubhouse Skin demo catalog).
   ```bash
   set -a; . mvp/app/.env; set +a
   curl -s "https://api.apify.com/v2/users/me/limits?token=$APIFY_TOKEN"
   ```
   Estimate cost = N × $0.0017 + ~0.4 × N × $0.01. If it would leave less than ~$5 for scans, tell Kelian before running. Never print the token.

2. **Run `microworlds/leads-finder`** (Apify MCP `call-actor`) with `maxTotalChargeUsd` set. Ask for ~20% more than N to cover duplicates. Default input:
   ```json
   {
     "max_result": N,
     "include_mobile": true,
     "contact_job_titles": ["founder", "co-founder", "ceo", "owner"],
     "company_num_employees_range": ["1-10", "11-20", "21-50"],
     "company_locations": ["United States"],
     "contact_location": ["United States"],
     "company_industry": ["Consumer Goods"],
     "company_not_industry": ["Consumer Services", "Internet", "Computer Software", "Hospital & Health Care", "Marketing & Advertising", "Facilities Services"],
     "contact_job_not_titles": ["sitter", "walker", "groomer", "trainer", "cleaning", "franchise", "former"],
     "keywords": ["ecommerce", "e-commerce", "direct to consumer", "dtc", "online store", "shopify"],
     "not_keywords": ["clinic", "gym", "studio", "coaching", "agency", "software", "app", "winery", "consulting", "medical practice", "telehealth", "pet sitting", "dog walking", "grooming", "boarding", "daycare", "cleaning", "pest control", "wholesale", "distributor", "manufacturer", "private label", "franchise"],
     "email_status": ["verified"]
   }
   ```
   Large runs take minutes; poll with `get-actor-run`.

   **Industry: Consumer Goods only.** The 2026-10-05 pet pull also allowed "Consumer Services" and "Internet" and 176 of 300 leads were pet sitters, walkers, groomers, carpet cleaners and apps, all dropped. Those two industries are where service businesses live; keep them excluded. Set `keywords` to the niche's *products* (e.g. "dog treats", "pet supplements"), not the category word alone ("pet" pulls every pet business).

   **Warning, tested 2026-10-05 (pet batch 2):** with Consumer Goods only plus product keywords, the 240 results were general DTC brands (snacks, beauty, footwear, tea) — only 1 was a pet brand. The `keywords` field does NOT reliably restrict to the niche. So: industry filter alone loses the niche; keyword "pet" alone pulls services. Before any full run, do a 30-lead test and count how many are actually in the niche; if under ~70%, change the inputs before paying for the full batch.

   **What you pay for, and what can't be filtered.** Every lead costs ~$0.0017 whether or not it has a phone; the $0.01 mobile charge is only taken when a mobile is found. The actor has **no "has phone" filter**, so pulling only phone leads is not possible here; a no-phone lead costs a fraction of a cent and goes to the email/DM list. Size runs by callable leads: expect ~30% of kept leads to have a mobile, so N ≈ callable target ÷ 0.3 ÷ (share that survives the B2C check).

   **Store-first (tested 2026-10-05, doesn't scale yet).** `prospecting/cold-calls/find_stores.py` takes a list of domains (e.g. from `apify/google-search-scraper`, ~$0.004 per query) and keeps only ones with a Shopify `/products.json`, for free. That gives a clean list of real stores, but feeding 16 of them into this actor's `company_domains` returned founders for only 2 and one mobile: its database barely covers small Shopify brands. Use it to *check* doubtful companies in a pulled batch, not as the main source, unless a better contact database is found.

3. **Download as CSV** to `prospecting/cold-calls/leads/<date>-<label>.csv` via the dataset API (`format=csv`), fields:
   `first_name,last_name,title,organization_name,organization_primary_domain,email,mobile_number_formatted,state,time_zone,linkedin_url`

4. **Dedupe** against every earlier file in `prospecting/cold-calls/leads/` (by email, else by name + domain), plus anyone already emailed (`Cold Email Outreach agent/Research/sent-log-*.csv`). Trim to N.

4b. **Niche check — mandatory, before split, lists or Close.** Print every kept company name and count how many are actually in the niche. Report that count to Kelian with the names. If it's low, don't label the batch as that niche and don't import it until he says so. (2026-10-06: 77 "pet" leads went into Close with zero pet brands.)

5. **Always split** — Kelian's standing requirement:
   ```bash
   python3 prospecting/cold-calls/split_leads.py prospecting/cold-calls/leads/<file>.csv
   ```
   Produces `-with-phone.csv` (to call) and `-no-phone.csv` (to email/DM).

6. **Rebuild the two master files** `leads/ALL-with-phone.csv` and `leads/ALL-no-phone.csv` by merging every dated `*-with-phone.csv` / `*-no-phone.csv` (dedupe by email, else name + domain; strip the BOM from headers; add a `batch` column). Kelian works from these two files.

7. **Report:** total leads, with phone, without phone (and how many of those have email), actual cost, Apify balance left, and any obvious non-ICP rows (clinics, services, apps, non-US).

## Rules
- The mobile numbers are private personal data: keep files local, never share or publish them.
- Numbers are not guaranteed live or current. Don't claim they all work.
- No per-brand ChatGPT checks or research for cold calls (see `MEMORY.md`, 2026-09-29).
