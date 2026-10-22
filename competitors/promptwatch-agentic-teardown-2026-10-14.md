# Promptwatch "Agentic AI Search Optimization": teardown, and how we'd build it for e-commerce

**Date:** 14 October 2026
**Source video:** [Agentic AI Search Optimization from Promptwatch](https://www.youtube.com/watch?v=iBA_Ee10MmY) (70 s, no voiceover or captions, 450k views, so it's a paid ad). I watched it frame by frame.
**Method:** the video, Promptwatch's own pages (features, pricing, case studies, data reports, blog), two outside studies, and a free check of the Apify actor Produkto already uses. No product trial and no sales call. Everything Promptwatch says about itself is vendor marketing unless noted.

---

## The short version

1. **The agent is a content writer bolted onto a tracker.** It finds the questions AI asks that your site has no page for, drafts the page or edits an existing one, publishes it to your CMS, and then watches for AI crawlers reading it and AI answers citing it. Nothing in it is technically out of reach for us.
2. **"100 million data points a day" is a counting choice, not a secret dataset.** Every crawler log line, every citation, every hidden search query and every answer counts as a "point". Crawler logs from customers' CDNs make up most of it. What the volume does buy them is real aggregate findings (below), and those findings are useful.
3. **There is no proof model.** The video's "absent → Rank #1, cited 78 times this week" is an animation. None of their four case studies shows an agent moving visibility. The single before/after number they publish (200 → 1,700 daily citations in 90 days) is an unnamed domain, measured by themselves, with no control group. What they have is an *attribution story*: page published → crawled on day X → first cited on day Y. That looks like proof, but it isn't, and the same caveat applies to us.
4. **For e-commerce, writing blog posts is the weakest lever.** Promptwatch's own 5,000-carousel study found **83% of ChatGPT shopping-carousel products matched a Google Shopping top-40 result**, and Profound's data says **~65% of ChatGPT product recommendations come from merchant feeds** (Shopify Catalog / OpenAI's feed). For a product to be recommended, the feed, the Google Shopping rank, the product page's facts and the reviews matter more than another article.
5. **We can build an e-commerce version, and two-thirds of it already exists in Produkto** (daily scans, competitors, Opportunities with lost questions, citation gaps and content gaps, before/after on Done cards). What's missing is listed in §6, with costs.

---

## 1. What the video shows, scene by scene

| Time | On screen | What it's claiming |
|---|---|---|
| 0–7 s | "In today's [AI] world. Customers make their buying decision with [Perplexity, Gemini, DeepSeek, Claude, ChatGPT] AI." Customer logos float past (Duolingo, Yelp, Valley…) | AI is where buying decisions happen |
| 7–13 s | A ChatGPT answer to *"What is the best GTM stack for a SaaS?"* lists HubSpot CRM, Apollo.io and Mixpanel with prices and star ratings. **Valley ($395/mo) is greyed out: not recommended.** | The customer is invisible |
| 14–18 s | "Agentic AI Search Optimization", then the Promptwatch logo | — |
| 19–24 s | "We collect **100,000,000+ data points every day**", with stacked layers showing ChatGPT, Claude and Gemini icons | The moat is data |
| 25–31 s | Lines run from the data into Valley's website. A new blog post appears: *"How to Simplify Your LinkedIn Outbound Tech Stack"* | The agent writes and publishes pages on your site |
| 31–34 s | More posts: *"Valley vs HeyReach vs Expandi: Which LinkedIn Outreach Tool Is Right for Your Team?"*, *"The Safest LinkedIn Automation Tools in 2026"*, *"Why B2B Teams Are Replacing Clay, PhantomBuster and HeyReach With One Tool"* | Its output is **comparison posts and listicles** |
| 34–38 s | An existing post gets an "Updates" checklist: ✓ H1, H2, H3 titles structured · ✓ Internal linking · ✓ Thumbnail updated | It also edits old pages (structure and links, nothing deeper) |
| 38–43 s | Promptwatch "Citations" table: URL · Citation clicks · Citation crawls · Responses · Prompts · Change · First seen, with sources split into Corporate / Organic / Social | It measures which pages get crawled, cited and clicked |
| 44–49 s | Same ChatGPT answer, now **Valley at #1**, tagged "[Rank: #1]" and "[Cited 78 times this week]" | The "proof" |
| 50–54 s | "Increase your citations → traffic → sales" over a rising curve | The promised chain |
| 55–70 s | "Talk to an expert today". Trusted by: Fireflies, Monks, SHARP, Shutterstock, Typeform, Valley, WPP, Yelp | Sales-led, demo CTA |

Three things worth noticing:

- **The example is B2B SaaS, and so is every logo.** The agent's whole output in the video is blog content. There isn't a single product page, feed or catalog in it.
- **The proof scene is a mock-up.** No dates, no baseline, no number of runs. "Cited 78 times this week" has no denominator.
- **The CTA is "Talk to an expert", not "Start free".** The agentic product is only on the $579/month Business plan and it's sold through a demo. That suggests it's partly done by hand and still early.

---

## 2. How the Promptwatch machine actually works

Pieced together from their feature pages, blog and FAQ. It runs as a loop:

```
 1. TRACK      their prompts × 4 models × once a day, scraped from the real chat UIs (not APIs)
      ↓
 2. FAN-OUTS   record the hidden search queries each model runs for a prompt
               (their example: one prompt → 140 fan-outs; the most common appeared 21 times)
      ↓
 3. GAP        index the customer's sitemap at paragraph level and run each fan-out against it
               with semantic search. No matching passage = a "gap"
      ↓
 4. DRAFT      the Content Agent writes a brief (your brand voice + Google results, news,
               YouTube transcripts, scraped competitor pages) → a new page, or git-diff-style
               edits to an existing one
      ↓
 5. PUBLISH    review inbox by default. An optional "hands-off" mode auto-publishes drafts that
               pass a quality check, on a schedule, to the CMS (Webflow, Framer, WordPress per a
               third-party write-up; their own page names no CMS)
      ↓
 6. CRAWL      CDN integration (Cloudflare Logpush/Worker, Fastly, Vercel, Akamai, CloudFront,
               Netlify) logs every AI-bot request: page, status code, time
      ↓
 7. CITE       does the new page now show up as a citation in tracked answers?
               "crawled but never cited" = content problem, "never crawled" = access problem
      ↓
 8. REFRESH    their rule of thumb: a citation holds 8–14 weeks, then the page needs a refresh
      ↓  back to 1
```

**Pricing tells you what's real.** Essential $95 has no articles. Professional $245 includes 5 "AEO articles" a month. Business $579 includes 10, plus crawler logs, Shopping Insights and the agentic product. So the "fully managed" agent produces **about 10 articles a month** at the top tier. That's a content subscription, not a catalog tool.

**Their own playbook** ([How to Grow AI Citations](https://promptwatch.com/blog/how-to-grow-citations-in-ai)) is the same loop written out for a human: 80% unbranded category prompts, read the fan-outs, one page per recurring sub-question with the answer in the first sentence, track time-to-crawl and time-to-cite, then double down, refresh or retire. The agent is that playbook automated.

---

## 3. "Hundreds of millions of data points a day": how they get there

The video says 100M+ a day, the YouTube description says "hundreds of millions", the homepage says **26,520,890,000** in total, and the data page's metadata says "4B+". The figures don't agree with each other, and none of them is defined.

Rough arithmetic for where the volume comes from (my estimate, not theirs):

| Source | Rough daily volume | Why |
|---|---|---|
| Answers | ~0.4M | ~1,840 orgs, mostly on the 50-prompt plan, 4 models, 1 run a day (see `LANDSCAPE.md` §"The sampling-rate finding") |
| Citations inside those answers | ~4–8M | Their data: almost half of ChatGPT answers cite 10+ domains |
| Fan-out queries | ~4M+ | ~10+ hidden searches per answer |
| Entities, sentiment, positions | a few M | One row per brand or product named |
| **AI-crawler log lines from customer CDNs** | **tens to hundreds of M** | Each bot request to a connected site is one line. A mid-size site easily gets thousands to hundreds of thousands a day |

So the headline number is mostly **crawler log lines**, which confirms what `LANDSCAPE.md` already concluded. **A log line is not an insight.**

**What the volume genuinely buys them is cross-customer findings**, published on [promptwatch.com/data](https://promptwatch.com/data). These matter to us:

- **Product pages are the #1 cited page type in ChatGPT:** 22.4% of citations (week of 28 Sep–4 Oct 2026). They were about a third in July. Listicles and how-tos are growing.
- **83% of ChatGPT shopping-carousel products strongly matched a Google Shopping top-40 organic result.** ~60% came from the top 10, 45.8% matched a Google Shopping title exactly, and Bing-only products were 0.16% (5,000 carousels, study dated 5 March 2026). Shopping fan-outs average ~7 words.
- **Reddit's share of ChatGPT citations fell from ~4% to 0.5%** on 14 Aug 2026.
- **Mid-authority domains (DR 46–75) earned almost half of citations** in August, while DR 91–100 got ~3%. Small brands aren't locked out.
- **Crawl → cite takes days to a few weeks**, and a citation lasts 8–14 weeks.

The real asset isn't any one customer's data. It's the **priors**: which page types, formats and sources get cited, by vertical, this month. Those priors are what point the agent toward listicles and comparison posts.

**Can we collect data like this?** Yes, at our scale and cost. Every scan already stores answers and citations. Aggregating across stores gives the same kind of priors for *e-commerce categories*. That's exactly what `METHODOLOGY.md` is meant to become.

---

## 4. The "proof model": what proof they actually have

You asked how they prove it increases AI visibility. Here's what exists:

| Claimed proof | What it actually is |
|---|---|
| Video: Valley goes from absent to #1, "cited 78 times this week" | Animation. No dates, no baseline, no sample size |
| Own domain: **200 → 1,700+ daily citations in ~90 days** | Their only quantified before/after. The domain is unnamed, they measured it themselves, there was no control group, and it was a new domain growing from near zero (any new site's citations grow) |
| TreeHouse: "AI Search drives 25% of organic conversions" | A share of conversions, not a lift caused by the agent. They automated *reporting* via MCP |
| Crisp: "2x higher CVR" | AI traffic converts better than other channels. True everywhere ([Adobe](../context/BUSINESS.md)). It doesn't show that Promptwatch caused anything. They also scaled to 5–10 articles **a day** |
| OpenUp, Monks | Qualitative only ("an article became the top cited result") |
| Per-page timeline: published → first crawled → first cited | The convincing part. It's **attribution, not causation**: it shows a page got cited after it was published, not that visibility rose because of it, or that it wouldn't have risen anyway |

**Why their measurement can't prove it even in principle:** one sample per prompt per model per day. Answers vary run to run, so a daily score mostly moves on noise. There's no holdout: nothing is left untreated to compare against. Model updates (e.g. the Reddit collapse) shift everyone at once.

**This is the same open question as our risk #2, "does remediation move visibility?" Nobody has answered it, Promptwatch included.** Their marketing just doesn't say so. Don't copy the animation. If we ever claim a result, it needs the design in §7.

---

## 5. Why it doesn't transfer to e-commerce as-is

| Promptwatch assumption | E-commerce reality |
|---|---|
| Visibility = getting your **page cited** in a text answer | For products, visibility = being one of the **product cards** in the carousel, or named in the text. Cards come largely from **feeds**: Shopify Catalog, OpenAI's merchant feed (ACP), Google Shopping. Profound's tracking: feed-sourced recommendations jumped from 8% to 62% on 10 July 2026 and reached ~65% by September ([summary](https://www.botrank.ai/post/chatgpt-shopping-now-favors-product-feeds-over-the-open-web), one vendor's data). |
| More articles = more citations | For products, the evidence points first to **Google Shopping rank, feed completeness and title/price/availability consistency** ([Promptwatch's own carousel post](https://promptwatch.com/blog/how-to-get-into-chatgpt-shopping-carousels)), then **product-page facts and reviews**. Articles mostly shape the *written* part of the answer. |
| Connect your CDN to see AI crawlers | **Shopify merchants can't.** Shopify runs its own CDN and doesn't expose bot logs (I believe this; worth confirming on one store). Crawler analytics is mostly unavailable for our ICP. |
| Click and revenue attribution is fuzzy | **Shopify is better here:** orders record the referrer and UTM. ChatGPT tags links `utm_source=chatgpt.com`, so with read access to orders we can count *actual AI-referred revenue per product*, which Promptwatch can't do for a SaaS site. |
| Publish to Webflow/WordPress | Shopify's Admin API can write product descriptions, metafields and blog posts, but that's **write access to the store**, which `CLAUDE.md` puts out of scope right now. Draft-and-export works without it. |
| ~10 articles/month | A 2,000-SKU catalog needs fixes across hundreds of product pages. That's **catalog-scale work, not an article quota**, and it's where every mid-market competitor caps out (Glara 20–50 products, Alhena 25–50 pages/month). |

What *does* transfer: the loop itself (track → find gap → draft → publish → watch → refresh), fan-out reading, and aggregate priors.

---

## 6. Can we build it? Component by component

| Piece | Promptwatch | Produkto today | What's missing for e-commerce | Cost |
|---|---|---|---|---|
| Daily tracking | 4 models, 1 run/day, UI-scraped | ChatGPT, AI Overview, Perplexity via Apify, 1 run/day | Nothing to start | Already paid |
| **Product cards** in ChatGPT answers | "Shopping Insights" ($579 tier) | **Not captured.** Our actor (`apify/chatgpt-search-scraper`) returns only `text`, `sources`, `query`; I checked a recent run | Switch or add an actor that returns product cards. [`parseforge/chatgpt-search-scraper`](https://apify.com/parseforge/chatgpt-search-scraper) claims product cards and claim-level citations at **$0.007/answer** (vs our $0.005). Small actor (28 users), so test before trusting it | ~$0.10 test run |
| **Fan-out queries** | Core of their gap analysis | Not captured | UI fan-outs on Apify are expensive ($0.45/check). The API-based [`plainrows`](https://apify.com/plainrows/ai-search-brand-visibility) returns fan-outs for ~$0.02/question, but API fan-outs may differ from the app's. Lower priority for products, because their carousel data says the *shopping* fan-out is a short ~7-word query we can approximate | Later |
| **Google Shopping rank** per product for short shopping queries | Advice only | Not tracked | Google SERP scrapers return the Shopping block for ~$0.002/query. This is the strongest *leading indicator* for ChatGPT carousels per their own study, and it moves faster than AI answers | Cents per store per day |
| **Feed / catalog readiness** audit | Not offered | Partly in `build/` (attributes, schema) | Per product: in Shopify Catalog/agentic channel? GTIN present? Title leads with brand + model + key spec? JSON-LD price/availability matches the page? Reviews in structured data? OAI-SearchBot allowed? Policy pages complete? All from public data | Free |
| Gap finding | Fan-outs vs sitemap embeddings | **Opportunities:** lost questions, retailer/citation gap, Content Gap (competitor page facts vs ours) | Add the facts buyers ask about that the winning *products* state and ours don't (E-GEO-style) | Free |
| **Drafting agent** | Blog posts + structural edits | Content agents page is a waitlist (`agents.py`) | Draft per product: missing attributes, spec table, FAQ answering the lost questions, a title rewrite for Shopping; plus comparison pages and collection copy. Review inbox, never auto-publish | ~1–3¢ per product draft on a mid model |
| Publishing | CMS integrations | None | **Phase 1:** export a Shopify-importable CSV (merchant uploads it, no write access needed). **Phase 2**, only after a paying brand asks: Admin API write | Free |
| Crawl tracking | CDN logs | None | Mostly impossible on Shopify. Skip | — |
| **Revenue attribution** | Fuzzy | None | Read-only Shopify access to orders → AI-referred orders and revenue per product. Needs the merchant to grant read access | Free |
| Proof | Per-page timeline | Before/after on Done cards (14 days) | Holdout design, §7 | Small extra scan cost |

**Verdict:** buildable by us with Claude Code, no new subscriptions, all on top of what already runs. The hard part isn't engineering. It's knowing which fixes work, which is §7.

---

## 7. How to make the e-commerce version work as well as it can

### The levers, strongest first (my ranking from the evidence above; it's a judgement, not a measurement)

1. **Be in the candidate set.** Shopify Catalog / agentic channel active, feed complete (GTINs, price, availability, media), policies done, OAI-SearchBot not blocked. Binary, cheap, checkable. A product that isn't in the feed can't be in a card.
2. **Rank in Google Shopping for the short query.** Title leads with brand, model and the key spec buyers type ("Linen sofa 220cm removable covers"). Exact title matches dominated their carousel study.
3. **State the facts buyers ask about on the product page.** This is our original thesis (M&O-type gaps: covers, care, dimensions). Outside evidence: in the [E-GEO study](https://arxiv.org/html/2511.20867v1) (GPT-4o re-ranking 10 products per query), the best-performing rewrites of product descriptions aligned with buyer intent, compared against competitors and used reviews and ratings, and kept facts intact: roughly **+1 to +1.6 rank positions**. "Storytelling" rewrites *lost* ~4 positions. Caveats: a simulation, one model, retrieval held fixed.
4. **Reviews:** volume and rating appear on every card.
5. **Third-party presence:** roundups, retailers, review sites. Already in Opportunities as "Sites to get onto".
6. **Own content:** buying guides and comparison pages, which is what Promptwatch's agent makes. Real but weakest for product cards; it shapes the written answer.

### The agent, scoped for e-commerce

**"Opportunities that write their own fix."** Each Opportunity card gets a **Draft fix** button. It produces the change for that product (title, missing attributes, FAQ, spec table) or a comparison page. The merchant approves it, it goes into an export file, and the merchant imports it into Shopify. Done is recorded. The before/after already exists. That's Promptwatch's loop with the e-commerce levers in it, and nothing new to host.

### Proof, done properly (this is the differentiator)

Promptwatch can't show causation. We can come closer, cheaply:

- **Holdout:** for a brand with several similar products, fix half and leave the other half untouched. Compare the two groups over the same weeks. A model update hits both groups equally, so the difference is ours.
- **More samples on the experiment questions only:** e.g. 5 runs per question per week for the products in the test, not daily single runs. That's a few dollars per brand per month at Apify prices.
- **Fast signal first:** Google Shopping rank and feed eligibility move in days. AI mentions take weeks. Report them separately.
- **Money last:** AI-referred orders per product from Shopify, if the brand grants read access.
- **Write every result into `METHODOLOGY.md`**, including null results. A fix that did nothing is a finding too.

It still won't be airtight with one brand's catalog, so say that plainly. But "we fixed 20 products, left 20 alone, and here's the difference" is a far stronger claim than anything in Promptwatch's case studies.

---

## 8. What I'd do next, cheapest first

Fits the current priority (demos first, build only what a conversation asks for):

1. **Free:** add the feed/catalog readiness checks (§6) to Opportunities. It's a strong demo moment ("23 of your products are missing GTINs, and ChatGPT's carousel reads those feeds"), and it's all public data.
2. **~$0.10:** one test run of the product-card actor on a demo store's buyer questions. If cards come back reliably, product cards become the headline metric for e-commerce, which Promptwatch only sells at $579.
3. **Cents a day:** Google Shopping rank for each product's short query, as the fast leading indicator.
4. **When a brand asks for it:** the Draft fix button with CSV export. Write access and auto-publish wait until someone pays.
5. **With the first willing brand:** the holdout experiment, so the proof exists before we need it in a sales call.

**Don't build:** CDN crawler logs (Shopify blocks it), an article quota (wrong lever for products), or a "fully managed" autopilot that publishes without review (it automates a guess, which `CLAUDE.md` warns against).

---

## Disagreements and caveats to flag

- **Data-volume claims conflict on Promptwatch's own site** (100M+/day, hundreds of millions/day, 26.5B total, 4B+). None is defined.
- **Feed vs web share** (~65% feed) is one vendor's (Profound's) observation, reported second-hand. OpenAI hasn't published the split.
- **The carousel study (83% Google Shopping match)** is Promptwatch's own, dated March 2026. ChatGPT Shopping changed a lot in July 2026, so it may have moved since.
- **Shopify crawler logs being unavailable** is my understanding, not verified on a store.
- **`LANDSCAPE.md` still says "4 models at every tier".** Pricing confirms that's still true as of today.

## Sources

- [Promptwatch video](https://www.youtube.com/watch?v=iBA_Ee10MmY)
- [Promptwatch home](https://promptwatch.com), [Content Agents](https://promptwatch.com/features/content-agents), [Agent Analytics](https://promptwatch.com/features/agent-analytics), [Pricing](https://promptwatch.com/pricing), [Case studies](https://promptwatch.com/case-studies), [Data reports](https://promptwatch.com/data)
- [Promptwatch €6M seed post](https://promptwatch.com/blog/promptwatch-raises-6-million-in-seed-funding)
- [How to Grow AI Citations (their playbook + 200→1,700 claim)](https://promptwatch.com/blog/how-to-grow-citations-in-ai)
- [How to get into ChatGPT shopping carousels (5,000-carousel study)](https://promptwatch.com/blog/how-to-get-into-chatgpt-shopping-carousels)
- [BotRank summary of Profound's feed-vs-web data](https://www.botrank.ai/post/chatgpt-shopping-now-favors-product-feeds-over-the-open-web)
- [E-GEO: A Testbed for GEO in E-Commerce (arXiv 2511.20867)](https://arxiv.org/html/2511.20867v1)
- Apify Store listings: [parseforge/chatgpt-search-scraper](https://apify.com/parseforge/chatgpt-search-scraper), [plainrows/ai-search-brand-visibility](https://apify.com/plainrows/ai-search-brand-visibility)
