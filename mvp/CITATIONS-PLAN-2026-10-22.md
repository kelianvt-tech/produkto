# Citations tab v2: plan (2026-10-22)

Modelled on Searchable's citations features: their docs "Why aren't we being cited?" and their sources API, read 22 Oct 2026. **Their actual screen was not seen.** This plan matches what data they expose, not their layout. If Kelian can record or screenshot their citations tab, the layout gets matched before step 3 ships.

Status: **waiting for Kelian's approval. Nothing built yet.**

## The goal

The tab answers: **"Which pages does AI read before it answers my buyer questions, do those pages name me, and what do I do about the ones that don't?"**

Searchable stops at naming the sites. Produkto goes further on four points:
- it reads each cited page and says whether it names you,
- it ties every page to the buyer questions and products it affects,
- it gives a different fix for each type of source,
- it drafts the ask and checks afterwards whether it worked.

## What already exists (reuse, don't rebuild)

- `citation_explorer.py`: every cited URL per answer, with domain, guessed content type, links to your product, engine, order and date. Top domains and the citations-over-time chart.
- `citation_panel.py`: the product-page version.
- `opportunities.py` → `_off_page`: **Retailer Gap** and **Citation Gap** cards. These already list sites cited when competitors won and you didn't, and they read the most-cited page to say "names X and Y, and not you".
- `page_gap.py`: free page fetch (`fetch_all`, cached 14 days in `page_facts`) and `names_on_page`.
- `RETAILERS` list in `opportunities.py`.
- The agent's setup questions (`fix_setup.py`, content agent settings), which get the new merchant questions in step 8.

## Ground rules

- Everything sits behind one switch, `PRODUKTO_CITATIONS_V2` (laptop `.env` only until Kelian says deploy). Development runs on `produkto.db.server-copy`, port 8011, with scans off.
- All merchant-facing words follow `skills/produkto-copy`.
- Nothing is sent to anyone by Produkto. The merchant sends.
- Nothing is guessed: a page we can't read says "couldn't read", a contact we can't find says "not found".

## Steps

### 1. Enough answers to trust (free)
One answer per question per day means a "top page" can rest on three citations.
- The tab defaults to the **last 30 days**, not the last scan.
- Every count shows how many answers it comes from.
- A page or domain with fewer than **5 citations** in the period is greyed and labelled "Too few answers to trust yet". It's still listed, but never turned into an Opportunity card.
- The threshold lives in `config.py` (`CITATION_MIN = 5`) so it can be tuned once real data shows where the noise stops.

### 2. Your citation share (free)
A headline number: your links as a % of all citations in the period, with the trend and the top 5 competitor brands' shares beside it. "Your links" = your own site plus other sites' listings of your products (the existing `relation` field). It follows the period filter like every tab.

### 3. Source type for every domain (free)
Each domain gets one label: **Retailer / marketplace, Review site, Editorial / listicle, Reddit & forums, YouTube & video, Social, Brand site, Your site, Other.**
- Built from a hand-made list of the ~200 domains most cited in our stored answers, plus URL and domain rules (reddit.com → forum, `/best-` in the path → listicle).
- Shown as a split bar ("42% of the pages AI used were review sites") and as a column/filter in the domains table.
- New module `source_types.py` so the opportunities and citations code share one list. `RETAILERS` moves into it.
- Anything not on the list stays "Other". Nothing is guessed by AI.

### 4. "Does this page name you?" for every cited page (free, the core step)
A pages table: page title, domain, source type, times cited, the buyer questions it was cited for, the page's date, and two read columns:
- **Names you:** yes (with which products), no, or "couldn't read" (blocked page, shown as such).
- **Names instead:** the competitor brands on the page.

Reads use `page_gap.fetch_all` in the background, at most hourly, top 40 pages per store per refresh, cached 14 days. Matching uses brand name + aliases + product titles, whole words only, the same rule as `evidence.merge_brands`. Default sort: most-cited pages that don't name you.

### 5. Freshness (free)
When a page is read, store its published and updated dates: from `datePublished` / `dateModified` in the page's structured data, `article:modified_time`, or a visible "Updated" line. If none is found, the date stays blank.
- The pages table shows "Updated 14 months ago".
- A frequently cited page that is over 12 months old and doesn't name you is flagged **"Stale roundup: good time to pitch an update"**. Editors refresh "best of" lists, and an update is the natural moment to get added.
- Your own cited pages that are going stale are flagged too, which feeds the product-page and articles agents.

### 6. Pages behind each buyer question (free)
A "By buyer question" view: for each question, the pages AI cited, whether each names you, and whether you were recommended in that answer. On a product page this narrows to that product's questions, so the merchant sees "for *best leash for a golden retriever*, these 4 pages decide the answer".

### 7. Engine filter (free)
ChatGPT / AI Overview / Perplexity filter on the whole tab, plus citation share per engine. Data is already stored per engine. Following Searchable's reading guide: if one engine cites you far less than the others, that's how the engine picks sources, not something to fix on your site.

### 8. What the merchant can offer (free, setup questions)
Added to the agent's setup, pre-filled where the store states it, otherwise left blank (the 2026-10-15 rule: never pre-fill a fact the store doesn't state):
- Do you send product samples to reviewers? (yes / no / case by case)
- Affiliate program? Link and commission, pre-filled if an affiliate page or link is found on the site.
- Discount code you'd give an editor's readers?
- Press contact name and email.
- Press kit or media page link (pre-filled if found).
- Awards, certifications or press coverage you already have (pre-filled from the about/press pages).
- Founder available for a quote? (yes / no)
- Anything you won't do (e.g. no paid placements).

Pitches use only what's filled in here. If nothing is filled in, the pitch panel asks for it first instead of drafting a generic pitch.

### 9. A different fix for each source type
Each "doesn't name you" page gets a fix that fits what the site is:

| Source type | The fix shown | What the agent drafts |
|---|---|---|
| Review site / editorial listicle | Pitch the editor to add or test your product | Editor pitch (step 11) |
| Stale roundup (step 5) | Pitch for the next update | Update pitch |
| YouTube & video | Reach out to the creator | Creator message: sample or affiliate offer |
| Retailer / marketplace | Get stocked, or fix your listing there | No pitch. Opens the existing Retailer Gap card |
| Reddit & forums | Don't pitch. Brands that pitch threads get banned. Answer honestly as the brand, or just watch the thread | A short guide on taking part honestly, plus the thread link |
| Social | Reach out to the creator | Creator message |
| Brand site (a competitor's own) | Nothing to do | Shown for context only |

The exact advice per type comes from the playbook in step 10, not from this table.

### 10. The `citation-pitch` skill and outside research (research work, no running cost)
Two pieces, both built from third-party sources (the 2026-10-22 rule: general findings come from outside research, graded by source):
- **`skills/citation-pitch/SKILL.md`**: how digital PR people pitch listicle and review editors and creators. Subject lines, length, what editors say yes to (samples, data, exclusives, affiliate), follow-up timing, what gets brands blocked, and Reddit etiquette. Each rule carries its source and grade (vendor study / practitioner / independent). Where two independent sources agree, that wins. The drafting code reads its rules from this skill.
- **`mvp/content-agent/CITATION-RESEARCH-2026-10.md`**: published studies on which sources AI assistants cite for shopping questions (Profound, Semrush, Searchable, Ahrefs and others: which domains and source types each engine favours). It's used to label how much a source type usually matters ("Review sites are among the most-cited sources for product questions", with its source). Vendor studies are marked as vendor studies.

### 11. Pitch panel on Citation Gap cards (low cost)
Each Citation Gap card, and each "doesn't name you" row in the pages table, gets a **Pitch this page** panel:
- **Who to contact** (step 12).
- **The draft**, written by the agent following the `citation-pitch` skill: what the page covers, which of your products fit it and why, facts only from the store's own pages, the offer from step 8, under 120 words, never knocks the competitors on the page.
- Copy button, "Mark as sent", and a follow-up reminder at the playbook's timing.
- Cost: one OpenAI call per draft, about $0.002, only when the merchant clicks "Draft pitch".

### 12. Finding who to contact
Two tiers, free first:
- **Free:** read the page and the site for the author byline, author page, contact page, "submit a product" / "work with us" / "advertise" pages, and any email printed on them. Every email found is screened against the placeholder list (`your@email.com`, `example.com`, `test@`…).
- **Paid, only when the free tier finds no email:** an email finder for the named author at that domain, then a verifier so we never hand over an unverified address (the 2026-08-12 rule). **Not chosen yet.** Before building this tier, compare the cheapest options (Hunter, Apollo paid, an Apify finder, plus Millionverifier/NeverBounce to verify), state the price per found email and ask Kelian. It runs only on the merchant's click ("Find email"), capped per store per month, and counts against the Apify/plan budget guard (the 2026-10-16 rule).

Output: name, role, email (verified / not verified), source link, or "not found".

### 13. Did it work? (free)
After "Mark as sent", Produkto re-reads the page weekly and shows on the card: "Page now names you: yes/no", plus visibility on that page's buyer questions before vs after (the same before/after logic as Done cards). Marked as unproven: one page change is one data point, not proof that outreach works.

### 14. Wiring
- Add a `get_citation_pages` tool to `mcp_server.py` (the rule: every new feature gets an MCP tool).
- Tests for each module, written to the temp-DB pattern in `test_dashboard.py`, run in one process with the others, with real DB row counts checked as unchanged.
- Dark mode via `theme_graphite.py`.

## Order and size

| Step | What | Cost to run | Rough build time |
|---|---|---|---|
| 1 | Trust threshold, 30-day default | free | 2 hours |
| 2 | Citation share | free | half a day |
| 3 | Source types | free | half a day |
| 4 | Names you / names instead | free | 1 day |
| 5 | Freshness | free | half a day |
| 6 | By buyer question | free | half a day |
| 7 | Engine filter | free | 2 hours |
| 8 | Merchant offer questions | free | half a day |
| 9 | Fix per source type | free | half a day |
| 10 | Pitch skill + citation research | free (research time) | 1 day |
| 11 | Pitch panel | ~$0.002 per draft | 1 day |
| 12 | Contact finding | free tier; paid tier priced before building | 1 day |
| 13 | Re-check after sending | free | half a day |

Steps 1–7 are the Searchable-equivalent tab. Steps 8–13 are where Produkto goes further. Step 10 runs before step 11 so the drafts follow the playbook from day one.

Checkpoints: Kelian sees a screenshot after step 4, after step 9 and after step 11, before anything deploys.

## Decisions for Kelian

1. **Approve the plan as written?**
2. Drafts use OpenAI (~$0.002 each, only on click). OK, or Apify/ChatGPT instead?
3. Pitch panel on Growth only, or on every plan?
4. Paid contact finding (step 12): price options come back before it's built. Any monthly cap you already want?

## What this can't tell you

Whether a site will accept a mention, what it costs, or whether a pitch will move visibility. The tab names the targets, says how much evidence sits behind each, and drafts the ask. It doesn't promise the result.
