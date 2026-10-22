# What makes AI recommend or cite a product: research for the agent's skills

*21 Oct 2026. Written to give each skill in `AGENT-V2-2026-10-21.md` real know-how instead of guesses. Read-only research: no app code, server or database was changed.*

## How to read this

Every claim carries one of four labels:

- **Official**: the engine's own documentation says it. Strongest about *what data they use*, weakest about *how they rank*, because none of them publish ranking rules.
- **Measured**: someone counted it in real AI answers (an independent study or our own data). The size and who ran it are given, because most studies come from vendors who sell AI visibility tools.
- **Opinion**: vendor or agency advice with no data behind it.
- **Guess**: my own inference. Treat it as something to test, not a rule.

Two facts sit under everything below:

1. **AI answers change on every run.** SparkToro and Gumshoe had 600 volunteers run the same 12 prompts ~3,000 times across ChatGPT, Claude and Google's AI: there was less than a 1-in-100 chance of getting the same brand list twice (Measured, vendor-partnered, Jan 2026). One answer proves nothing; only rates over many answers do.
2. **Nobody has shown that changing a page moves AI recommendations in real engines at scale.** The lab studies below show it in simulated engines; the one large real-world controlled test (Ahrefs, schema) found no effect. That is still the open question, and it is why the agent needs its measure → re-fix loop.

---

## 1. Per engine: what it says it reads

### ChatGPT (OpenAI)

**What OpenAI says (Official)**
- Product results "are selected independently by ChatGPT and are not ads." To pick products it uses "structured metadata from first-party and third-party providers (e.g., price, product description) and other third-party content." It shows review summaries "based on reviews from public websites" and labels like "Budget-friendly" that may come from what reviewers say. ([Shopping with ChatGPT Search](https://help.openai.com/en/articles/11128490-shopping-in-chatgpt), page said "updated 2 days ago" when read on 21 Oct 2026)
- When several shops sell the same product, shops are ranked by "availability, price, quality, and whether they are the maker or primary seller of that item." (same page)
- **Shopify stores are already in:** "For merchants on Shopify, product data is already integrated into ChatGPT through Shopify Catalog… No additional work is required." Others can apply for a direct feed. (same page)
- The feed has nine required fields: `item_id, title, description, url, brand, seller_name, image_url, availability, price`; optional fields include `review_count, star_rating, material, dimensions, gtin, return_policy`. The spec says nothing about which fields affect ranking. ([Products feed reference](https://developers.openai.com/commerce/specs/file-upload/products), read 21 Oct 2026)
- **Crawler:** OAI-SearchBot decides whether a site can appear in ChatGPT search answers. "Sites that are opted out of OAI-SearchBot will not be shown in ChatGPT search answers." GPTBot is for training only; blocking it doesn't affect search. ([Overview of OpenAI crawlers](https://developers.openai.com/api/docs/bots), read 21 Oct 2026)

**What studies found (Measured, vendor)**
- **Peec AI / Search Engine Land (early 2026):** of 43,000+ ChatGPT carousel products across 10 verticals, **83% matched a product in Google Shopping's top 40 organic results, under 11% matched Bing.** Products higher in Google Shopping tended to sit earlier in the carousel. ([Search Engine Land](https://searchengineland.com/new-finding-chatgpt-sources-83-of-its-carousel-products-from-google-shopping-via-shopping-query-fan-outs-470723))
- **Profound (24 Jun 2026, ~1M shopping offers over 30 days):** ~88% of offers came from product pages on the web, not feeds; feed-sourced offers grew from 4.3% to ~20% of retrievals in six weeks, and feed-sourced products almost always took position 1. Even merchants with a feed had ~76% of their offers built from their web pages. ([Profound](https://www.tryprofound.com/blog/chatgpt-shopping-deep-dive))
- These two studies don't fully agree (Google Shopping as the source vs. web product pages). Both can be true if ChatGPT uses Google Shopping to *find* candidates and then reads the product page for details. **Guess**, not confirmed.

### Google: AI Overviews, AI Mode, Shopping

**What Google says (Official)**
- To be a supporting link a page "must be indexed and eligible to be shown in Google Search with a snippet… There are no additional technical requirements." "Specific optimization isn't required." It lists ordinary basics: crawling allowed, internal links, good page experience, "important content is available in textual form", images/video, "structured data matches the visible text", and up-to-date **Merchant Center** and Business Profile. Both features use "query fan-out" (many related searches behind one question), so the links vary. ([AI features and your website](https://developers.google.com/search/docs/appearance/ai-features), read 21 Oct 2026)
- Product markup: required `name, image, offers` (with price and currency); recommended `aggregateRating, review, brand, gtin, mpn, sku, color, material, size, pattern, audience, category, description, hasCertification`, plus `availability, shippingDetails, hasMerchantReturnPolicy` on the offer. ([Merchant listing structured data](https://developers.google.com/search/docs/appearance/structured-data/merchant-listing), last updated 8 Sep 2026)
- AI Mode shopping runs on the **Shopping Graph**, which Google described at launch as "more than 50 billion product listings, 2 billion of which are updated every hour" (I/O, May 2025; I read secondary coverage, not Google's own post).

**What studies found (Measured, vendor)**
- Ahrefs (early 2026, 863k keywords, 4M cited URLs): only ~38% of AI Overview citations rank in Google's top 10, down from ~76% in its 2025 study. Ranking in normal search helps but no longer explains most citations. ([Ahrefs](https://ahrefs.com/blog/ai-overview-citations-top-10))
- Ahrefs (26 May 2025, 75k brands): the factor most linked with a brand appearing in AI Overviews was **branded web mentions** (correlation 0.664), ahead of branded anchors (0.527) and branded search volume (0.392). Correlation, not proof of cause. ([Ahrefs](https://ahrefs.com/blog/ai-overview-brand-correlation/))
- Profound (Aug 2024–Jun 2025, ~680M citations): in AI Overviews Reddit (2.2%), YouTube (1.9%) and Quora (1.5%) led. ([Profound](https://www.tryprofound.com/blog/ai-platform-citation-patterns))

### Perplexity

**What Perplexity says (Official)**
- Product cards "aren't sponsored—they're unbiased recommendations." Its free Merchant Program, aimed at "large retailers", promises "increased chances of being a 'recommended product' because the products will be in our index, and when we have more robust details, we can better determine if a product is high quality and relevant to a user's query." ([Shop like a Pro](https://www.perplexity.ai/hub/blog/shop-like-a-pro), Nov 2024)
- The CEO told Fortune in Nov 2024 that he couldn't explain how the AI picks products. So: **richer product details help (their claim), ranking rules unknown.**
- Third-party claims that Shopify stores get automatic visibility and that in-app checkout boosts rank are **Opinion** (vendor blogs, unconfirmed).
- Profound: Reddit was Perplexity's top cited source (6.6% of citations). (link above)

### Microsoft Copilot

**What Microsoft says (Official)**
- The Copilot Merchant Program (Apr 2025) lets merchants share product specifications so Copilot can suggest items accurately. Copilot shopping draws on Microsoft Merchant Center; Microsoft Advertising is adding Universal Commerce Protocol (UCP) feeds and Copilot Checkout.
- **Shopify Catalog feeds Copilot:** Microsoft says it is "integrating Shopify Catalog into Copilot", which "automatically structures, enriches, and syndicates product data in real time", and that top Shopify merchants saw "nearly 90% growth in impression share in Copilot". ([Microsoft Advertising, 2026](https://about.ads.microsoft.com/en/blog/post/april-2026/win-across-all-three-eras-of-the-web); the URL says April, the page metadata says 22 Sep 2026: the date is unclear)
- The claim that title, brand, GTIN, price, availability and shipping matter most for Copilot is **Opinion** (agency guides). I found no Microsoft page that ranks attributes.

### The layer under all of them: Shopify Catalog

For a Shopify merchant, ChatGPT (Official) and Copilot (Official) read product data through **Shopify Catalog**, and Google uses Merchant Center. So for our customers, **the product data in Shopify (title, description, product type, variants, metafields, images) is the feed.** Shopify's "Agentic Storefronts" channel controls which AI platforms receive it; third-party guides disagree on which ones are on by default, so check the merchant's admin rather than assuming (I couldn't find Shopify's own help page in this pass).

---

## 2. Cross-engine findings, ranked by evidence strength

| # | Finding | Evidence | Strength |
|---|---|---|---|
| 1 | **Answers vary on every run, so any verdict needs many answers.** | SparkToro/Gumshoe ~3,000 runs; Profound: ~95% of carousel titles appeared in under 30% of runs for the same prompt (vendor); our own scans | Strong |
| 2 | **Product data reaches engines through the store's product data and feeds** (Shopify Catalog → ChatGPT and Copilot; Merchant Center → Google). | OpenAI, Microsoft, Google docs | Strong (Official) |
| 3 | **AI must be able to read the page: crawlers allowed, important facts in visible text.** Blocking OAI-SearchBot removes a site from ChatGPT search. | OpenAI, Google docs; searchVIU (Dec 2025) found 5 AI systems read only visible HTML when fetching a page live and ignored JSON-LD (one Feb 2026 test disagrees) | Strong for crawl access; Medium for "visible text only" |
| 4 | **Third-party ("earned") sources dominate citations: editorial lists, review sites, retailers, forums, video.** AI search leans on them far more than Google does. | Chen et al. (arXiv, Sep 2025, controlled comparisons across verticals); Profound 680M citations; our data (§3: 59–86% of citations go to articles, 7–16% to retailers) | Strong |
| 5 | **Brands mentioned widely on the web get mentioned by AI more.** | Ahrefs 75k brands (correlation 0.664); Chen et al.'s "big brand bias" | Medium (correlation) |
| 6 | **ChatGPT's product carousel mostly picks from Google Shopping results**, so Merchant Center/Google Shopping rank matters for ChatGPT too. | Peec AI 43k products (vendor); conflicts in part with Profound's product-page finding | Medium |
| 7 | **A direct feed to ChatGPT wins the top carousel slot when it's used.** | Profound ~1M offers (vendor) | Medium; only via Shopify Catalog for our customers anyway |
| 8 | **Adding schema doesn't raise citations for pages already cited.** | Ahrefs controlled test, 1,885 pages vs 4,000 controls, Aug 2025–Mar 2026: AIO −4.6%, AI Mode +2.4%, ChatGPT +2.2% ([Ahrefs](https://ahrefs.com/blog/schema-ai-citations/)) | Medium (one test, only already-cited pages) |
| 9 | **Rewriting product text can move rank in a simulated AI shopping engine.** Plain human rewrite styles mostly didn't help (10 of 15 neutral or negative; "storytelling" −4 positions, "minimalist" −1.7); prompts tuned by optimization all helped (~+0.7 to +1.2 positions), converging on: match the buyer's intent, unique selling points, compare with alternatives, use reviews as evidence, scannable headings/bullets, keep facts unchanged. | E-GEO (Columbia/MIT, arXiv Nov 2025, 7,000+ queries, GPT-4o as the engine) | Medium for the direction; lab only, not a live engine |
| 10 | **Adding statistics, quotations and cited sources made text more visible in generated answers** (up to ~40% in their measure). | GEO paper (Aggarwal et al., KDD 2024), Perplexity-style engines, not shopping-specific | Medium; lab only |
| 11 | **Fresher pages get cited more** (cited URLs ~26% younger than search results; ChatGPT prefers the newest). | Ahrefs, 17M citations, Jul 2025 | Medium (correlation) |
| 12 | **Hidden text can manipulate AI recommendations.** | Kumar & Lakkaraju (Harvard, arXiv 2024): an optimized text string on a product page made a fictional coffee machine the top pick | Measured, but **the agent must never do this**: it is a manipulation and Google's spam policies forbid hidden text |
| 13 | FAQs, llms.txt, "AI-friendly formatting" as standalone levers | Mostly vendor advice. E-GEO's plain "FAQ" rewrite scored +0.06 (no effect). No study found for llms.txt | Weak / Opinion |

**Conflict to flag:** `AGENT-V2-2026-10-21.md` lists structured data as one of the five things AI reads and plans a 3-day schema step. The evidence says schema is hygiene (needed for Google's merchant listings and Merchant Center consistency), not a visibility lever. Keep it cheap and don't sell it as one.

---

## 3. Our own data: winners vs losers

### What was looked at

- Server database, read-only, excluding `sim-` scans. **Clubhouse Skin:** 1,148 answers (440 ChatGPT, 363 Perplexity, 345 AI Overview) to 11 buyer questions, 9,058 citations. **5Strands:** 65 answers to 22 questions (one scan, ~3 per question), 382 citations.
- Then I fetched 27 pages as a plain browser would (no JavaScript run): 18 that won (named or cited) and 9 that lost, and measured words, numbers with units, headings, lists, FAQ blocks, review counts and structured data, and whether each page uses the words in the question it lost or won.

**How small this is:** two stores, one of them with **6 products** and the other with **one scan**. Clubhouse wins exactly one question; 5Strands wins in 9 answers total. The pages are 27, chosen by hand. This shows patterns worth testing, not rules. The questions were also generated *from* the merchants' own products, which makes specific questions easier for them to win than real buyer phrasing would.

### Finding 1: the merchant wins only when the question contains its product's distinctive facts

| Store | Question | Answers naming the merchant |
|---|---|---|
| Clubhouse | "Which lightweight moisturiser contains snow mushroom, squalane and niacinamide…" | **33 of 105** (ChatGPT 30/40, AI Overview 3/32, Perplexity 0/33) |
| Clubhouse | the other 10 questions (routines, budget, face oil vs moisturiser, vitamin C oil, cleanser, caps) | **1 of ~1,040** |
| 5Strands | "…checks 800+ foods… under $75" | 3 of 3 |
| 5Strands | "…checks 130+ vitamins and minerals…" | 2 of 3 |
| 5Strands | "…comprehensive horse health tests under $150…" | 2 of 3 |
| 5Strands | 19 broader questions ("best at-home food intolerance test", "best holistic pet assessment"…) | 2 of 57 |

On the broad questions the winners were big or specialist brands (CeraVe, Cetaphil, Sunday Riley, Everlywell, YorkTest) and editorial pages (aad.org was cited 551 times; Cleveland Clinic, Healthline, Vogue, Fortune's "best food sensitivity tests"). **Guess:** for a small brand, its own page can win the narrow, fact-specific questions; broad "best X" questions are won off-site.

### Finding 2: within one store, page structure didn't separate winners from losers

All six Clubhouse pages share one template: ~870–1,070 visible words (the hat 434), the same basic Product markup, no reviews, no FAQ markup. The Helsinki page won; Frontier Cleanser and Amalfi oil lost. All 5Strands pages share FAQ markup, ratings and ~1,700–2,900 words; winners and losers look the same. **So the template (schema, length, FAQ block) isn't what decided these questions.**

### Finding 3: what the winners had that the losers lacked

| Gap | Example |
|---|---|
| **The question's own words, stated many times.** | For "gentle exfoliation… natural balance": Cetaphil's winning page says *exfoliat-* 60 times, *gentle* 43, *sensitive* 17, *salicylic* 7. Clubhouse's Frontier Cleanser: 4, 1, 0, 0. For vitamin C oil, Stark's page says *brighten* 24 times and *antioxidant* 18; Amalfi says 4 and 3. |
| **A distinctive, checkable number or ingredient list.** | "800+ foods", "130+ vitamins and minerals", "snow mushroom, squalane, niacinamide". The 5Strands losers (environmental test, vitamin & mineral test) state no comparable headline number on the page. |
| **Reviews in quantity.** | Winners: Caps Apparel 2,646 reviews, Everlywell ~7,000 ratings, dermapproved 500, 5Strands food test 265, Stark 166. Losers: Clubhouse 0; 5Strands environmental 1–7. Not a clean split: the 5Strands vitamin test has 78 and lost. |
| **Presence on other sites.** | Helsinki was also cited through **myza.co**, a retailer that stocks it (16 citations, ChatGPT only). 5Strands won through Chewy listings and infohorse.com articles about it. The losing products had no third-party page cited. |
| **Category credibility.** | The Clubhouse cap page states everything the cap questions ask (100% cotton, structured, unisex, golf, '90s) and still lost every time, to cap specialists with thousands of reviews and to "best golf hats" lists. Facts are needed but not enough. |

### Finding 4: engines behave differently

| Engine | Citations per answer | Citations to articles | to product pages | to retailers | to video/social |
|---|---|---|---|---|---|
| ChatGPT | 3.5 | 59% | 25% | 16% | 0% |
| Perplexity | 17.1 | 68% | 15% | 16% | 0% |
| AI Overview | 3.8 | 59% | 10% | 7% | **23%** (YouTube, Facebook) |

(Clubhouse; 5Strands is similar.) ChatGPT cited and named the small brand's own page; Perplexity cited the Helsinki page 3 times but never named the product in our extraction (possible extraction miss: worth checking). Reddit was only 42 of 9,058 citations, far below what vendor studies report; it may be our niche, our scraper, or the reported 2025 drop in ChatGPT's Reddit citations (**Guess**).

---

## 4. Proposed agent skills

Every skill shares four rules:

1. **Facts only from the store** (products, pages, merchant answers). Never invent a number, claim, review or certification. Health wording stays behind the merchant's approval (5Strands sells health tests).
2. **No manipulation:** no hidden text, no text aimed at machines that a human wouldn't see, no fake reviews or comments, no keyword stuffing. Repeating the buyer's words is fine when every sentence is true and useful to a human reader.
3. **Every change is logged with the questions it targets**, so the measure step can judge it.
4. **No verdict before enough answers** (Guess at a floor: ~30 answers per question per engine before and after, over at least 2–4 weeks).

"Context" lists the data each skill loads. Table names are the current tables in `produkto.db`.

### 1. Diagnose a lost question

**Job:** for one buyer question the product should fit but loses, say *why* and pick the fix type.

**Rules**
- Sort the question first: **narrow** (it names attributes, ingredients, numbers, a use case) or **broad** ("best X", "routine", "X vs Y"). Narrow → on-page fix first. Broad → off-site and article first; a page fix alone rarely wins it (§3 Finding 1).
- Compare our page with the 2–3 most-cited winning pages *for that question*: does ours state the question's attributes in the question's words? A distinctive number? Reviews? Is it on any third-party page?
- Check the page is readable: fetch without JavaScript, confirm the key facts are in visible text and OAI-SearchBot / Googlebot aren't blocked.
- Output one card: the gap, the fix type (page / facts needed / collection / article / feed / citations / reviews), the target questions, and the one-line reason.
- If the product isn't a credible fit (a skincare brand's cap against cap specialists), say so instead of prescribing a rewrite.

**Context:** the question and its `prompt_sets.relevance` products; its `answers` per engine with `mentions` (winners, positions) and citations; the winners' pages (`page_facts`, `product_page_cache`); our product (`products.raw_json`, `catalog_facts`); `offsite_searches`; past fixes on this product and their verdicts.

### 2. Rewrite a product page

**Job:** title, description, key facts block, FAQ, for one existing product.

**Rules**
- Lead with what it is and who it's for, in the words buyers use in the questions it targets.
- State every distinctive fact as a plain, checkable line with units and the exact name: "7% tetrahexyldecyl ascorbate", "tests 800+ foods", "100% cotton, structured, unisex".
- Labelled lines (Good for / Key ingredients or materials / How to use / Size) and feature → benefit bullets. Keep stated limits.
- Keep it short; our cited small-brand pages ran 60–170 words of description (`PRODUCT-PAGE-RESEARCH-2026-10-19.md`). Length didn't decide wins here.
- No hype or storytelling: E-GEO measured storytelling as the worst style. Don't copy E-GEO's "urgency" or "persuasive tone" either: they conflict with our copy rules and are measured in a lab only.
- Title: product type + the main distinguishing fact, not just a brand name ("Helsinki Moisturiser" → also say "snow mushroom & squalane lightweight moisturiser" where the store states it). **Guess** that this matters for feeds: Shopify Catalog passes the title through.
- No prices in the text (prices live in the feed).

**Context:** the product (`products.raw_json`: description, variants, options, tags, product type, metafields), `catalog_facts`, store pages (`page_facts`: About/FAQ/policies), brand voice (`content_settings`), the questions it targets with the winners' cited pages, the merchant's answered facts, and review text if available.

### 3. Write a page from scratch

**Job:** a full product page for a thin or empty product, or a new store page for a narrow buyer question.

**Rules**
- Same rules as skill 2; any fact the store doesn't state anywhere becomes a question to the merchant, never a guess.
- Build a new page only for a narrow question the catalog genuinely answers and no existing page covers. One page per question; never near-duplicate pages per variant.

**Context:** as skill 2, plus the full catalog list (to link related products) and the existing store pages (to avoid duplicates).

### 4. Collection pages

**Job:** a short intro, a buying guide block and FAQs on category pages.

**Rules**
- Answer the category's broad questions directly on the page ("which cleanser for sensitive skin?"), then point to the products with the facts that separate them.
- A comparison table of the store's own products by the attributes buyers ask about.
- Keep it on the page as text (not inside a tab that loads later).
- **Guess:** collection pages are the store's best shot at broad questions; untested.

**Context:** the collection's products and facts; the broad questions mapped to that category; the cited editorial pages for those questions (to see what a good answer covers).

### 5. Comparison pages

**Job:** "X vs Y" and "alternatives to [big brand]" pages.

**Rules**
- Name the competitor products AI actually recommends for the question (from our answers); compare on attributes buyers ask about, with sources.
- Fair and checkable: competitor facts come from their own pages, with a link. Never criticise them; state differences.
- Say who each option suits, including when the competitor is the better pick. **Guess:** honest comparisons get cited as sources; one-sided ones read as ads.
- E-GEO found "compare with alternatives" was the strongest single human rewrite style (+0.71 positions, lab only).

**Context:** the winners for the target question (`mentions`), their cited pages, our product facts, brand voice.

### 6. Buying guides (AEO articles)

**Job:** guides that answer broad questions.

**Rules**
- Open with the direct answer; then the decision criteria; then products with checkable facts.
- Use statistics, quotes and cited sources where the store or a reputable source has them (GEO paper: these raised visibility, lab).
- Show a real date and keep guides updated (Ahrefs freshness finding).
- **Expect little from the store's own blog on broad questions:** our broad questions were won by aad.org, Healthline and magazine lists. A guide also gives the citations skill (9) something to point editors at.

**Context:** the broad questions, the top-cited articles for them (what they cover), catalog facts, brand style, past article results.

### 7. Structured data and technical

**Job:** make sure every engine can read the page; tidy markup.

**Rules**
- First the things that are proven to matter: OAI-SearchBot, Googlebot, Bingbot and PerplexityBot allowed in `robots.txt` and not blocked by the CDN/bot protection; key facts present in the page HTML without JavaScript; the page indexed.
- Product markup that matches the visible page: name, image, offer (price, currency, availability), brand, GTIN/SKU, material/size/colour where they exist, ratings only from real reviews. Fix mismatches between markup and visible text (Google asks for this).
- Don't sell schema as a visibility lever (Ahrefs found no lift); it's hygiene and Google eligibility.
- `llms.txt`: skip unless free; no evidence it helps.

**Context:** the live page HTML (with and without JavaScript), `robots.txt`, theme markup, `link_checks`.

### 8. Feeds

**Job:** make the product data that engines receive complete and accurate.

**Rules**
- For Shopify, the feed *is* the product data: fill product type, a fact-rich title, description, variant options, GTIN where the merchant has one, and Google product category.
- Google Merchant Center (Google Shopping, AI Mode, and per Peec, ChatGPT's carousel): titles with product type + key attribute, all attributes filled, no disapprovals, price and availability matching the page.
- Check Shopify's AI sales channels (Agentic Storefronts) are on for ChatGPT, Copilot and Google.
- Never put claims in the feed that the page doesn't state.

**Context:** `products.raw_json` (all fields), `feed_checks`, Merchant Center diagnostics (needs a Google connection: not built), the store's channel settings.

### 9. Citations (off-site)

**Job:** get the brand onto the pages AI already cites for its questions.

**Rules**
- Start from data: for each lost question, list the cited pages, ranked by how often they're cited and by which engine. Separate editorial lists, review sites, retailers, forums and video.
- For each: is the brand there? Who edits it? What would make it fit (a sample, a fact, a stockist link)? Draft a short, factual pitch for Kelian or the merchant to send.
- Retailer listings count: Helsinki was cited through myza.co, 5Strands through Chewy. Suggest stockists where the brand isn't listed.
- AI Overviews cite YouTube/Facebook for ~23% of citations in our data: a short how-to video is a real lever there (merchant-made).
- Never post on the brand's behalf, never write fake reviews or forum posts, never pay for placement without saying so.

**Context:** citations per question per engine (`answers.citations`), `offsite_searches`, `page_facts` for cited pages, brand facts, the merchant's stockists and press list.

### 10. Reviews

**Job:** get more real reviews that mention what buyers ask about.

**Rules**
- Merchant-run through their review app: draft the request email and a prompt such as "how did it feel on sensitive skin?" that invites reviewers to mention the attributes in the target questions. Never write or edit reviews.
- Make sure reviews render in the page HTML, not only after JavaScript loads (**Guess** that this matters; OpenAI says review summaries come from public websites).
- Count reviews on third-party sites too (Amazon, retailers): those are what engines read most.

**Context:** review app in use (`page_gap` review/Q&A detection), review count and text, target questions, the attributes winners' reviews mention.

### Measure and re-fix (skills 10–12 in `AGENT-V2`)

These research findings set the rules for them:
- Judge each change only on the questions it targeted, per engine, compared with similar untouched products over the same weeks (answers drift for everyone).
- Narrow questions should move first; broad ones may never move from page work alone. Report them separately.
- If nothing moved after enough answers, switch fix type (page → feed → citations), don't rewrite the same page a third time.

---

### Added later the same day: third-party data ($2.31 of Apify)

Full detail in `third-party-data/2026-10-21/README.md`. In short:
- Only 33% (Clubhouse) and 16% (5Strands) of the products ChatGPT named also appeared in Google Shopping's top 20 for the same question, far below Peec's 83%. The comparison is rough. 5Strands holds Shopping positions 1–5 on 15 of 19 questions and is still rarely named by ChatGPT, so **a Shopping rank alone didn't win it.**
- Clubhouse isn't in Google Shopping at all (likely no Merchant Center).
- 5Strands lists the same test as 640 / 800+ / 955 / 1030 / 1250 items across channels.
- Clubhouse is stocked by ~11 retailers but has no reviews or editorial coverage, and Google confuses its name with Clean Skin Club. 5Strands has plenty of coverage, some of it negative.

## 5. What I'd test first (Guess)

1. **Fingerprint facts on Clubhouse's losing products.** Amalfi oil and Frontier Cleanser state their key facts weakly. Rewrite them to state their distinctive facts in the buyer's words, then watch the narrow questions they fit. This is the cheapest test of "remediation moves visibility".
2. **Merchant Center for one store.** If Peec is right, Google Shopping rank feeds ChatGPT's carousel; that would make feeds the biggest lever for Shopify brands.
3. **One stockist or editorial placement**, tracked on the broad questions, to see whether off-site moves what on-site can't.

---

## Sources

**Official**
- OpenAI, [Shopping with ChatGPT Search](https://help.openai.com/en/articles/11128490-shopping-in-chatgpt) (read 21 Oct 2026)
- OpenAI, [Products feed reference](https://developers.openai.com/commerce/specs/file-upload/products) (read 21 Oct 2026)
- OpenAI, [Overview of OpenAI crawlers](https://developers.openai.com/api/docs/bots) (read 21 Oct 2026)
- Google, [AI features and your website](https://developers.google.com/search/docs/appearance/ai-features) (read 21 Oct 2026)
- Google, [Merchant listing structured data](https://developers.google.com/search/docs/appearance/structured-data/merchant-listing) (updated 8 Sep 2026)
- Perplexity, [Shop like a Pro / Merchant Program](https://www.perplexity.ai/hub/blog/shop-like-a-pro) (Nov 2024)
- Microsoft Advertising, [Win across all three eras of the web](https://about.ads.microsoft.com/en/blog/post/april-2026/win-across-all-three-eras-of-the-web) (2026); [Copilot Checkout and Brand Agents](https://about.ads.microsoft.com/en/blog/post/january-2026/conversations-that-convert-copilot-checkout-and-brand-agents) (Jan 2026)

**Academic (lab measurements)**
- Aggarwal et al., [GEO: Generative Engine Optimization](https://arxiv.org/abs/2311.09735) (KDD 2024)
- Bagga et al., [E-GEO: a testbed for GEO in e-commerce](https://arxiv.org/html/2511.20867v1) (Nov 2025)
- Chen et al., [Generative Engine Optimization: How to Dominate AI Search](https://arxiv.org/abs/2509.08919) (Sep 2025)
- Kumar & Lakkaraju, [Manipulating LLMs to Increase Product Visibility](https://arxiv.org/abs/2404.07981) (2024)

**Industry studies (measured, by vendors)**
- Peec AI via Search Engine Land, [83% of ChatGPT carousels use Google Shopping data](https://searchengineland.com/new-finding-chatgpt-sources-83-of-its-carousel-products-from-google-shopping-via-shopping-query-fan-outs-470723) (2026)
- Profound, [What ChatGPT actually looks for in AI Shopping](https://www.tryprofound.com/blog/chatgpt-shopping-deep-dive) (24 Jun 2026); [AI platform citation patterns](https://www.tryprofound.com/blog/ai-platform-citation-patterns) (2025)
- Ahrefs, [Schema and AI citations](https://ahrefs.com/blog/schema-ai-citations/) (May 2026); [AI Overview citations and the top 10](https://ahrefs.com/blog/ai-overview-citations-top-10) (2026); [AI Overview brand factors, 75k brands](https://ahrefs.com/blog/ai-overview-brand-correlation/) (May 2025); [AI assistants prefer fresher content](https://ahrefs.com/blog/do-ai-assistants-prefer-to-cite-fresh-content/) (Jul 2025)
- SparkToro / Gumshoe via [Search Engine Journal](https://www.searchenginejournal.com/ai-recommendations-change-with-nearly-every-query-sparktoro/566242) (2026)
- searchVIU, [What AI systems really see of schema](https://www.searchviu.com/en/schema-markup-and-ai-in-2025-what-chatgpt-claude-perplexity-gemini-really-see/) (Dec 2025)

**Our data:** `produkto.db` on the server, read-only queries, 21 Oct 2026; the 27 fetched pages are listed in §3's tables.
