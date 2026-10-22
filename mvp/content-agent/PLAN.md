# Agentic AI Search Optimization (code name: content agent): build plan, day by day

Written 14 October 2026. "Day" means one working day of Kelian + Claude Code. Total: **~52 working days (~10.5 weeks)**, including the off-site days added 15 Oct, plus Shopify's app-review wait in phase 3.

Each phase ends with something showable in a demo. Stop after any phase if demos say nobody wants the next one.

---

## Phase 1: v1, drafts only (days 1–15)

Goal: from an Opportunity card, the merchant gets a drafted fix, reviews it and downloads a file to import into Shopify. Everything is hidden behind `SHOW_CONTENT_AGENT`.

| Day | Work |
|---|---|
| 1 | Switch in `config.py`. Database tables: `briefs`, `drafts`, `draft_versions`. **Own sidebar tab "Content"** with three views: Inbox, Calendar, Published |
| 2 | Catalog facts store: pull every product's title, description, options, metafields and JSON-LD into one record. This is the only allowed source of product facts |
| 3 | Brief builder, part 1: Opportunity → which product(s), which lost questions, which competitors won, what their pages say (reuses `page_gap.py`) |
| 4 | Brief builder, part 2: choose the draft type (product-page fix, FAQ, comparison page, buying guide, collection copy) |
| 5 | Drafting: product-page fix (improved title, missing attributes, spec table) |
| 6 | Drafting: FAQ block answering the lost buyer questions |
| 7 | Drafting: comparison page and buying guide |
| 8 | **Fact check:** every number and claim in a draft must match the catalog facts store. Unknown facts become "[ask merchant: …]" placeholders, never guesses |
| 9 | Review inbox UI: list of drafts, status (new / approved / rejected) |
| 10 | Draft view: before/after side by side, edit in place, approve or reject |
| 11 | "Draft fix" button on every Opportunity card, with a loading state while it drafts |
| 11b | Calendar, basic version: month grid showing each approved draft on its planned date (merchant's US time zone). Clicking an item opens its detail panel (spec below) |
| 11c | **Agent onboarding, part 1** (shown the first time the Content tab opens): voice sample from the brand's best pages ("sounds like us" / adjust), and what the agent may change (titles, descriptions, specs, FAQs, articles; products/collections to leave alone) |
| 11d | **Agent onboarding, part 2:** time zone (pre-filled from the store's country, merchant confirms or changes it; the calendar and publish times use it), missing-facts questions (answer now or skip), pace and days per week, approval rule (always on in v1), then land on a calendar already holding the first two weeks of planned drafts. All editable later in settings |
| 12 | Export: Shopify product CSV (title, body, metafields) + blog posts as HTML |
| 13 | Test import of the CSV on a test Shopify store; fix whatever breaks |
| 14 | Tests (temp database in `setUp`, per MEMORY.md), cost check per draft |
| 15 | Run it on Clubhouse Skin, read 20 drafts by hand, fix the worst problems. **Demo-ready** |

## Calendar detail panel (spec, agreed 14 Oct 2026)

The calendar is its own view inside the Content tab. Clicking any item opens a panel that shows everything about it:

- **What:** title, type (product-page fix / FAQ / comparison page / buying guide / collection copy), status (draft / approved / scheduled / published / rejected), word count
- **Where it goes:** the exact destination: product page (with image and link), collection/category, or blog. Which field changes (title, description, metafield, new section)
- **When:** planned publish date and time in the merchant's time zone; who approved it and when
- **Why:** the Opportunity behind it, the buyer questions it targets, which competitors currently win those questions, and how often the merchant's product is named today
- **Sources:** the catalog facts used, competitor pages read, and any "[ask merchant]" gaps still open
- **Content:** full preview and before/after against the current page
- **After publishing:** live link, date first cited (if ever), and before/after mention rate from the Done tracking. Labelled "too early" until there are enough answers
- **Actions:** edit, move date, approve, reject, open in review inbox

Filters above the calendar: by type, product, collection and status.

## Phase 2: quality matching Promptwatch (days 16–27)

Goal: drafts good enough that a merchant approves most without editing.

| Day | Work |
|---|---|
| 16 | Brand voice: learn tone from the brand's existing best pages and the brand profile (step 2 of onboarding) |
| 17 | Research sources: top Google results and the competitor pages AI cited, scraped into the brief |
| 18 | Google Shopping rank check for each product's short query (the fast signal, ~cents/day) |
| 19 | Title rewriting rules for Shopping: brand + model + key spec first |
| 20 | Product-card capture: switch or add the ChatGPT actor that returns product cards (test first, ~$0.10) |
| 21 | Feed readiness checks as Opportunities: GTIN, price/availability matching, reviews markup, OAI-SearchBot access, policy pages |
| 22 | Self-review pass: a second model call scores each draft (facts, answers the question, readable) and fixes or flags it |
| 23 | Refresh suggestions for already-published pages (edits shown as tracked changes, like Promptwatch's git-diff) |
| 24 | Calendar, full version: drag drafts to another day, pace setting (e.g. 3 a week), colours by type (product fix / FAQ / comparison / guide) |
| 24b | **Connect your calendar:** a private subscribe link (iCal feed) that adds every planned draft to Google Calendar, Apple Calendar or Outlook, updating itself when dates change. Each event links back to the draft's detail panel. One-click "Add to Google Calendar" button; others paste the link |
| 25 | Bulk mode: draft fixes for 50+ products in one go, running in the background |
| 26–27 | Quality round on two more catalogs in different categories; tune the prompts |
| 27b | **Off-site tracking, part 1** (added 15 Oct 2026, to match Promptwatch's Offsite Mentions / Reddit / YouTube views): from citations scans already store, list the individual Reddit threads, YouTube videos, review sites and "best of" articles AI cites for the merchant's questions, and which of them name the merchant or a competitor. Free |
| 27c | **Off-site tracking, part 2:** mentions without a link (the merchant's brand or product named on a cited page that doesn't link back), by reading those cited pages (reuses `page_gap` fetching). Shown as Opportunities next to "Sites to get onto" |
| 27d | **Off-site drafts:** the agent writes the outreach for each off-site Opportunity: a pitch email to the site behind a cited roundup, an honest Reddit reply that answers the thread (discloses the brand), a request to a retailer or review site. Same fact rules and fact check as on-site drafts |
| 27e | Off-site drafts in the Inbox and Calendar with their own type; the merchant copies or sends them. **Never auto-posted** (Reddit bans automated brand accounts); later only email can be sent from Produkto |
| 27f | Track off-site results: did the roundup add the product, did the thread get cited, before/after mention rate |

## Phase 3: publishing to Shopify (days 28–37)

**Only starts once a brand pays.** Needs write access to the store (see `CLAUDE.md`).

| Day | Work |
|---|---|
| 28–29 | Shopify custom app: login (OAuth), read/write products, metafields, blog articles |
| 29b | **Metafields into catalog facts** (gap found on day 2): with store access, read every product's metafields and Shopify category attributes into `catalog_facts`, tagged source 'metafield', so drafts can use them and stop asking the merchant for facts already stored there |
| 30 | One-click "Publish" from the review inbox to the store |
| 31 | Undo: keep the old version and restore it with one click |
| 32 | Publish log: what changed, when, by whom |
| 33 | Mark the matching Opportunity as Done automatically on publish (starts the before/after) |
| 34 | Read-only orders access: AI-referred orders and revenue per product (`utm_source=chatgpt.com`) |
| 35–36 | Test on a real store with the merchant watching; fix issues |
| 37 | Deploy to the server behind the switch for that brand only |
| — | Public Shopify App Store listing: only if many brands need it; review takes weeks |

## Phase 4: the "fully managed" agent and proof (days 38–45)

| Day | Work |
|---|---|
| 38 | Autopilot setting: auto-publish only drafts that pass the self-review, on the calendar; always off by default |
| 39 | Weekly loop: new scans → new Opportunities → new drafts, without the merchant asking. **Includes the re-fix loop below.** |
| 39b | **Re-fix loop (Kelian, 16 Oct 2026: "constant optimization").** See the section below the table. |
| 40 | Weekly email summary: what was drafted, published, and what changed |
| 41–42 | **Holdout experiment:** fix half of similar products, leave half alone, extra scan runs on those questions only |
| 43 | Results view comparing the two groups, honestly labelled ("too early" until enough answers) |
| 44 | Write findings to `METHODOLOGY.md`, including fixes that did nothing |
| 45 | ~~Pricing as an add-on~~ Decided 15 Oct: agent work is part of the plans, as two allowances (Starter none; Growth 50 product page fixes a month and no articles, article packs of 10 at $10 each, Promptwatch-style; Custom agreed); built in `content_plan.py`. Left here: a Stripe add-on for the packs, and the pricing page (`produkto-copy` skill, no promised results) |

### The re-fix loop (day 39b)

Why: the monthly fix allowance pays for continuous optimization, not one rewrite per page. Without this, a six-product brand on Growth runs out of things to fix in a week.

1. **A fix is tied to buyer questions.** Each published fix records the tracked buyer questions its product fits (the questions behind its Opportunity, `opportunities._card_questions`). A product that fits no tracked question gets no fix, because nothing could measure it. Suggest adding a question instead.
2. **Measure on those questions only.** Reuse `opportunities.before_after`: answers naming the product, over the 14 days before publish vs. the days since.
3. **Verdict per fix, after enough answers** (`MIN_AFTER` or more, and at least 14 days live): *moved* (named more often), *no change*, or *dropped*.
4. **No change or dropped: draft a new version.** The agent rewrites using a different angle. It reads which pages the AI cited for those questions (Content Gap / `page_gap`) and what the previous version already tried, so it doesn't repeat it. The new draft goes to the Inbox with a line like "Version 1 published 3 Oct; named in 0 of 18 answers since. This version adds …". The merchant still approves.
5. **Moved: leave it alone** and keep monitoring. If it later drops, it re-enters step 4.
6. **Each re-fix counts as one fix** in the monthly allowance, like any fix.
7. **Every verdict is logged** (fix, version, questions, before/after, what changed) as raw material for `METHODOLOGY.md`, including fixes that did nothing.

Copy rule stays: the card shows what changed, never claims the fix caused it.

---

## Running costs
**Measured 15 Oct 2026 (day 14), on Clubhouse Skin, fact check included:** product page fix ~0.13¢, FAQ ~0.06¢, buying guide ~0.28¢, comparison page ~0.41¢ per draft. Setup ~0.5¢ once (voice, brand brief, missing facts); the first two weeks ~1.2¢. A Growth store at its full allowance (50 fixes, assume twice as many drafted as approved) costs ~15¢ a month; each 10-article pack ~4–8¢. So drafting is well under $1 per store per month; scans are the real cost. Costs come from the app's own per-token price table (`llm.Usage`), not from the OpenAI invoice; check the invoice once a paying store runs a full month. Needs OpenAI credit.
- *(Earlier estimate, superseded: a few cents per draft → ~$5–20 per brand per month.)*
- Google Shopping rank: cents per brand per day
- Product-card actor: ~$0.007 per answer vs $0.005 today
- Hosting: no change (same Hetzner server)

## Biggest risks
1. **Invented facts on product pages.** The day-8 fact check is the most important day in the plan.
2. **Not knowing whether fixes move visibility.** Phase 4's holdout is how we find out; until then, sell the work, not the result.
3. **Store write access.** Phase 3 waits for a paying brand.
