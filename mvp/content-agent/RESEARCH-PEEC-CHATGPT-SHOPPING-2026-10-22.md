# How ChatGPT Shopping picks products: what Peec AI's BrightonSEO talk means for our agents

**Source:** Malte Landwehr (Peec AI), *How ChatGPT Shopping Picks Products: US vs Europe*, BrightonSEO, published 13 Oct 2026. https://www.youtube.com/watch?v=CMAXaoFMF9o (20 min; full transcript read 22 Oct 2026).

**Loaded into the brain:** 17 findings, from `content-agent/brain-seeds/2026-10-13-peec-chatgpt-shopping-us-vs-europe.json` via `app/brain_seed.py`. So far they're only in the brain's test database (`produkto.db.brain-test-20261022`, findings 420–436), because the brain isn't on the server yet. **Load the seed on the server when the brain ships** (command at the end).

---

## How much to trust it

- **Peec AI is a vendor** (it sells AI-visibility tracking and competes with us). Their numbers count as vendor evidence.
- There are two kinds of evidence in the talk:
  1. **Debug logs.** A Peec team member (Metehan) found an OpenAI debugging API that returns about 150,000 lines per prompt, covering the whole product- and source-retrieval process with sub-scores. This shows how the system actually works, which is stronger than correlation, but it comes from **a few sessions** (often one query) at one point in time. The brain grades these as **Opinion** because no sample size was given. That's its rule, and the rule is right: one query is not a measurement.
  2. **Peec's database** (the description says 1M+ products across 250M+ chats; the UK figures come from "millions of chats in recent weeks"). These are **Measured, vendor**.
- What each finding is worth after the brain graded it:
  - **Playbook (1):** marketplaces are rarely cited and shops are cited most. Peec's finding agrees with LLM Pulse's earlier finding (64.7% of citations went to brand sites, 2.9% to retailers and marketplaces), and the two sources are independent.
  - **Candidate (5):** the UK and global source patterns, and the Domain Rating 20 floor. Each needs a second independent source.
  - **Test (11):** everything that comes from the debug logs, plus the short-vs-detailed prompt test.

---

## The big picture: there are now two ChatGPT Shopping systems

| | **US** (since about late Sep/early Oct 2026) | **Europe/UK** |
|---|---|---|
| Where products come from | OpenAI's own index, **"Labrador"**, filled from **merchant feeds**. That means a direct feed to OpenAI, or **Shopify** (Shopify Catalog). About 669 feeds: around 70 direct partners (e.g. Nike), about 500 that OpenAI built itself by scraping sites via Bright Data, plus Shopify, Salesforce and Stripe feeds | **Google Shopping**, scraped through SerpAPI |
| How products are picked | 41 candidates → 32 put into a "prompt block" (title, description, ratings, GTIN…) → 5 shown. Scored with embeddings, **BM25 (literal keyword match)**, ANN and RRF | About 5 fan-out searches on Google Shopping, merged round-robin (113 products) → 18 kept. **No** embeddings, keyword scoring, GTIN or trust check |
| Description length that counts | **Cut at 50 tokens (about 40 words, about 250 characters)** at the scoring stage | Not relevant: the Google Shopping listing does the work |
| Trust | A **"verified seller"** flag. Shops without it are dropped entirely. The lowest-trust shop had 25 candidates and got none shown | Any shop in Google Shopping counts as trusted |
| Personalisation | Location (current and home), inferred gender, and merchants already shown to or clicked by this user | Not mentioned |
| Click tracking | Links end in **`utm_medium=feed`** | Not mentioned |

**Why this matters for us:** most Produkto customers are American (MEMORY, 2026-09-27). For them **the Shopify product data *is* the feed** that ChatGPT scores, which matches what we already wrote in `RESEARCH-AI-PRODUCT-SELECTION-2026-10.md` §1 (Official, from OpenAI and Shopify). The title and **the first 40 words of the description** decide whether a product even reaches the shortlist.

**This settles an earlier conflict.** Our research doc flagged that Peec's early-2026 finding (83% of carousel products came from Google Shopping) disagreed with Profound's finding that most products came from product pages and feeds. The talk explains both: **Google Shopping is the source in Europe; the US moved to feeds.** Profound saw feed retrieval jump from 8% to 62% on 10 July (brain finding 36). So the 83% figure should now be read as **Europe only**.

**What it means for our two stores (store facts, not findings):**
- **Clubhouse Skin is a GB store**, so the Google Shopping system applies, and Clubhouse is in **none** of Google Shopping's top 20 for any of its questions (third-party pull, 22 Oct). For Clubhouse, getting into Google Shopping (Merchant Center) is very likely the gate to ChatGPT's product carousel. The "Get your products into Google Shopping" card (`feed_check`) is the right top card for it.
- **5Strands** holds Google Shopping positions 1–5 on 15 of 19 questions and is still rarely named by ChatGPT. If it's a US store, the US switch away from Google Shopping is a likely explanation. **This is a guess:** I haven't checked 5Strands' store country, and the scans would have to be from after the switch.

---

## All 17 points, and what each one changes for us

**Grade** = the brain's grade. **For us** = the part of Produkto it affects.

### A. Product data and product page fixes

1. **The description is cut at about 40 words at the scoring stage (US).** *Test.*
   For us: product page fixes must put the product type and the attributes buyers filter on into the first 40 words. **Done today**, see "What changed" below.
2. **Products are scored partly by literal keyword match (BM25)** as well as by embeddings. *Test.*
   For us: write a fact with the buyer's own word ("fragrance-free", not "no added scent"). **Done today.** Optional later: run BM25 locally on each product's first 40 words against its buyer questions. It's free and Malte suggests it, and it would give the agent a before/after score for each fix.
3. **GTIN is in each candidate's record (US).** *Test.*
   For us: we already have the "Publish barcodes (GTIN)" card (`feed_check`). Treat it as a ChatGPT lever too, not only a Google one.
4. **Sizes of the same product are merged; Peec advises sending every variant as its own feed item to take more slots.** *Test (advice).*
   For us: this is unclear. The merge removed size variants, so separate *colours* might each count while sizes don't. Don't tell merchants to split products until a scan shows it works.
5. **No "verified seller" flag = dropped entirely; low-trust shops get nothing shown.** *Test.*
   For us: we can't see this flag yet, and nobody knows where it comes from. Watch for it in the brain. It may connect to Shopify's ChatGPT channel or OpenAI merchant onboarding.
6. **Shopify is one of the feed paths into the US index.** *Test, but agrees with Official OpenAI/Shopify docs.*
   For us: a new Opportunities card, "Check the ChatGPT channel is switched on in Shopify (Agentic Storefronts)". It's free, and if the channel is off, nothing else we fix reaches ChatGPT's carousel.

### B. Europe/UK stores

7. **Europe = Google Shopping round-robin, with no trust or keyword scoring.** *Test.*
   For us: for non-US stores, rank the Google Shopping and Merchant Center cards **first**: Shopping presence decides the carousel. The agent should look at the store's country before choosing which card goes first.

### C. Sources around the carousel (citations and articles)

8. **When a product gallery shows, listicles and category pages are cited more.** *Candidate.*
   For us: the store's own **collection pages** are a target, not only articles. `briefs.py` already knows a "collection page copy" type, but no agent writes it yet. That's a strong candidate for the next fix type.
9. **Shops are the most common source domains; marketplaces and aggregators are rarely cited.** *Playbook.*
   For us: a brand's own store *can* be the cited source. Product pages and collections on the store are worth fixing. In citation pitches, don't prioritise marketplaces.
10. **Non-commercial sites (reviews, manufacturers) are the most likely to get the inline citation.** *Playbook (same finding as 9).*
    For us: off-site citation targets should be review and advice sites first.
11. **Since GPT-5.6, listicles are down (still the biggest type), Reddit is down sharply, product pages are up.** *Candidate.*
    For us: this supports fixing product pages first, which is our wedge. Don't build a Reddit play.
12. **Short prompts bring retailers and listicles into the sources; detailed prompts bring advice and comparison articles.** *Test.*
    For us: AEO articles should pick the article type by how specific the buyer question is. A short, generic question ("best vitamin C serum") gets a roundup or collection-style page. A detailed one (budget, skin type, use) gets a comparison or advice article. Our buyer questions are mostly detailed, so comparisons should be the default.
13. **Brands are added to fan-out searches far more than merchants. When yours is, you're close to guaranteed about 10 source slots.** *Candidate.*
    For us: possible new dashboard metric, "how often AI searches your brand by name vs competitors". Malte says that if a rival of similar size gets added more often, that's worth investigating. Needs checking: do our Apify ChatGPT captures return the fan-out searches? (Searchable counted them, so they can be collected.)
14. **Domains below Ahrefs DR 20 are rarely cited. Above it, citation rate per URL is similar.** *Candidate.*
    For us, there are two consequences. (a) **Off-site pitches** should target sites with DR 20+. (b) **This is a caveat for AEO articles on small stores:** an article on a DR<20 store is unlikely to be cited by itself. For those stores, product data, collection pages and earned mentions come first, and articles are mainly for buyers and for Google. Say this to merchants honestly; never promise article citations.

### D. Measurement and context

15. **`utm_medium=feed` marks US ChatGPT Shopping clicks.** *Test.*
    For us: a one-line setup tip for merchants ("filter by utm_medium=feed in Shopify Analytics or GA4"), and later the Results tab could read it if we connect analytics. It's the clearest proof of revenue a merchant can get today.
16. **The US shopping system personalises by location, gender and past merchant clicks.** *Test.*
    For us: our scans are logged-out, single-location answers, so they're a **baseline, not what every shopper sees**. Say it that way on demos if asked. It doesn't change any number.
17. **Amazon is the top merchant almost everywhere in the UK; there's a "No Amazon" A/B test in the US.** *Candidate / Test.*
    For us: background for sales calls only.

Also in the talk, not stored: ChatGPT uses separate indexes for Reddit, news, PDFs, YouTube and Wikipedia (42 sources fetched, 1 cited in one example). The retrieval steps run on small models (GPT-4o, 4.1 nano, 5 mini). Malte skipped his last two sections for time.

---

## What changed today (22 Oct 2026)

1. **Product page fix rules** (`app/drafts.py`, `PRODUCT_OPENING` and rule 8):
   - The first 40 words carry the product type and the facts buyers filter on.
   - The opening paragraph is now at most 40 words.
   - Facts are written in the buyer's own words when the facts support it.

   The existing rules are unchanged (facts only, no prices, 60–170 words). Tests pass (`test_drafts`, `test_brain`, `test_content_agent`: 50 OK). **Not deployed.**
2. **Brain:** the 17 findings above are in the test database. There's a new loader, `app/brain_seed.py`, for any source Kelian wants read by hand. It grades through `brain.store()`, so the brain's evidence rules still apply. It's safe to load twice, and it marks the video as seen so the weekly YouTube collector doesn't read it again.

## Proposed next, not built (ranked by value ÷ effort)

1. ~~Shopify ChatGPT channel check card~~ **Built 22 Oct** (`feed_check._chatgpt_card`, not deployed). Shopify's help page (read 22 Oct) says ChatGPT access is on by default for stores selling to US customers, but needs Terms of service, Privacy policy and Return and refund policy filled in. We check those three for free: if one is missing, the card says which (Critical for US stores). If all three are there, it's a one-time "check Sales channels > Agentic > ChatGPT" card.
2. ~~Order the cards by store country~~ **Built 22 Oct** (`feed_check.by_country`): for non-US stores, "Get your products into Google Shopping" goes to Critical. On Clubhouse Skin (GB) it now tops the Product Data cards.
3. **Pick the article type by question specificity** (point 12): a small change in `briefs.py`'s type choice.
4. **BM25 score per product** (point 2): free and local, gives each fix a before/after number.
5. **Collection page copy as a fix type** (point 8).
6. **Fan-out brand share metric** (point 13): first check whether our captures include the fan-out searches.
7. **Small-store caveat on AEO articles** (point 14): honest positioning for stores with DR<20.

## Load this on the server when the brain ships

```bash
cd /opt/produkto/app && python3 brain_seed.py /opt/produkto/content-agent/brain-seeds/2026-10-13-peec-chatgpt-shopping-us-vs-europe.json
```
(The seeds folder has to be copied to the server too. Change the path if it's put elsewhere.)
