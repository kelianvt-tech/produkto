---
name: pull-leads
description: Pull a batch of US e-commerce founder leads (name, email, mobile) for Produkto cold calls, emails and DMs, using the Apify Leads Finder actor, then split them into a with-phone CSV and a no-phone CSV. Use whenever Kelian asks for more leads, founders, phone numbers, a new batch, or "run another batch of N".
---

# Pull leads

Cheap founder leads for Produkto outreach. ~$0.0017 per lead plus $0.01 per mobile found (charged only when found). Tested 2026-09-29: 37% of leads came back with a mobile.

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
     "company_industry": ["Cosmetics", "Health, Wellness & Fitness", "Consumer Goods"],
     "keywords": ["ecommerce", "e-commerce", "direct to consumer", "dtc", "online store", "shopify"],
     "not_keywords": ["clinic", "gym", "studio", "coaching", "agency", "software", "app", "winery", "consulting", "medical practice", "telehealth"],
     "email_status": ["verified"]
   }
   ```
   Large runs take minutes; poll with `get-actor-run`.

3. **Download as CSV** to `prospecting/cold-calls/leads/<date>-<label>.csv` via the dataset API (`format=csv`), fields:
   `first_name,last_name,title,organization_name,organization_primary_domain,email,mobile_number_formatted,state,time_zone,linkedin_url`

4. **Dedupe** against every earlier file in `prospecting/cold-calls/leads/` (by email, else by name + domain), plus anyone already emailed (`Cold Email Outreach agent/Research/sent-log-*.csv`). Trim to N.

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
