---
name: "linkedin-growth"
description: "LinkedIn strategy and content for Produkto (Kelian's and Gabe's accounts) — writing posts, hooks, cheat sheets, lead-magnet posts, conversion posts, comments and DMs; optimising the LinkedIn profile, headline or About section; defining content pillars; planning a posting calendar; or turning real AI answers and free checks into inbound leads. Use for any request involving LinkedIn posts, personal-brand content, or founder-led client acquisition. Do NOT use for M&O Living social media (Instagram, TikTok, Pinterest) — that belongs to the marketing-team plugin skills."
---


# LinkedIn Growth

A founder-led client-acquisition system for LinkedIn, adapted from Chris Donnelly's *2026 LinkedIn Bible* and his Creator Accelerator webinar (attended August 2026), pointed at one specific job: getting mid-market DTC e-commerce brands to book a Produkto demo.

**Last updated 18 October 2026** for Produkto as it is now: a live product with clients, a free-check offer, two founder accounts. The channel plan (cadence, connection agent, metrics) lives in `GTM/linkedin/LINKEDIN-PLAN.md`; this file is how to write.

**The premise:** LinkedIn has ~1.2B users and under 1% post. Attention is abundant, content is scarce. That gap is the opportunity — but only if every post serves a business outcome rather than a follower count.

---

## Before writing anything

> **Always ask first (Kelian, 2026-10-19):** "Do you want to do an AI shopping news post this time?" Check the newest brief in `GTM/linkedin/news/` (written every Monday by the `ai-shopping-news-brief` scheduled task) and offer its pick. If the AI Shelf Watch data series (`GTM/linkedin/AI-SHELF-WATCH-PLAN.md`) still isn't built, ask whether to build it.



Four checks, every time. If any is unclear, ask rather than guess.

1. **Which post type is this?** (Educational / Story / Lead magnet / Conversion — see below.) Each has a different job and a different structure. Writing without picking one produces mush.
2. **Which content pillar does it sit in?** If it fits none, either it shouldn't be posted or the pillars need revisiting.
3. **Does it pass the delivery test?** See the table below. "Interesting" is not the bar.
4. **Would the ICP save it or send it to a colleague?** If not, it isn't finished.

---

## The engine this sits inside

Five stages, in order. Most requests touch one, and naming which keeps the answer from drifting.

| Stage | What it settles |
|---|---|
| 1. Positioning | Who you're for and why you're the one |
| 2. Content | The engine that creates attention |
| 3. Compounding | The systems and delegation that make it run without you |
| 4. Capture | Turning attention into an owned audience |
| 5. Conversion | Offers and funnels that turn leads into revenue |

Stages 1 and 2 are the bulk of this file. Stage 3 is the four-hour rhythm. Stage 4 is deplatforming and lead magnets. Stage 5 is conversion posts and the nurture sequence. **Skipping 4 is the standard failure** — Donnelly's stated biggest regret was reaching 250,000 followers with zero email subscribers.

---

## The delivery test

Run every idea against this before drafting. It is a harder filter than "is it interesting."

| Low delivery | High delivery |
|---|---|
| Personal stories with universal lessons | Educational carousels and cheat sheets |
| Hot takes and opinion | Named IP, frameworks and methods |
| Motivational posts | Technical breakdowns for one role or industry |
| Broad observations | Case studies with the industry and numbers stated |
| Written to appeal to everyone | Written for specific titles and people |

**A tension worth stating rather than hiding:** the left column contains "personal stories," and the post mix below allocates 25% to them. Both can hold — the low-delivery version is a story whose lesson is *universal* ("what failure taught me about persistence"). A first-person story anchored to the ICP's specific problem, with the catalog detail intact, sits on the right. **Test: if any founder in any industry could tell this story, it's the left column and shouldn't be posted.**

**Case studies with numbers** are now possible but gated: Produkto has clients, and each one must agree before being named or quoted in public (see Honesty rules). Until a client says yes, the strongest right-hand material is **real AI answers in one category with the numbers stated** — see the AI Shelf Report below.

---

## Named IP — the AI Shelf Report

"Named IP, frameworks and methods" is the highest-leverage item in the right-hand column. Donnelly's own examples — the PLAY Framework, the LinkedIn Revenue Engine — work because a *named* thing gets referenced, screenshotted and repeated by other people. An unnamed insight can't be.

**The named thing is the AI Shelf Report**: real buyer questions in one category, asked to ChatGPT, and which brands and products came back. It's real work we already do for every outreach batch (see `GTM/cold-email/*-answers-*.json`), it's specific to one category, and the data is ours. Run it as a recurring series, one category at a time, matched to that week's outreach niche.

Every Shelf Report states: the category, how many questions, the date, the engine, and how the question was asked (e.g. "asked for three products"). The numbers come from a saved file, never from memory.

The product's own metrics are the vocabulary: **visibility** (share of answers that mention a product), **average position**, **share of voice**. Use them the way the dashboard does.

Name things that correspond to real work. Do not invent a framework.

---

## The context this skill assumes

**The business:** Produkto. A merchant pastes their store URL; Produkto asks AI assistants the questions their buyers ask, across the whole catalog, every day, and shows how often each product is recommended, where it ranks, and which competitors get picked instead — every competitor found in the answers, nothing to configure. The **Catalog Optimization Agent** then finds the details buyers ask about that the product pages leave out and drafts the fixes; the merchant reviews and approves each one before anything goes live.

**Stage:** live product, early clients, demand still being proven. Current priority is **booked demos**. Clients so far include Wild One (pet), Stumptown and Partners Coffee (coffee) — **ask Kelian before naming any of them on LinkedIn.**

**The offer:** a free check. "Comment CHECK" (or reply "yes") and we run Produkto on their catalog and send the results. Same offer as the cold emails, so one thing gets tested everywhere.

**Positioning — the claim that survives a prospect checking it:**
> Produkto measures how AI recommends your whole catalog, product by product, against every competitor it names — and drafts the product page fixes for you to approve.

The checkable gap: tools selling product-level AI visibility at mid-market prices cap the number of products (Glara tracks 20 on Starter, 50 on Advanced; Alhena optimizes 25–50 pages a month). Whole-catalog coverage at a mid-market price is the specific difference. Never say "nobody does this", "every competitor only measures" or "not another dashboard" — Produkto *is* a dashboard, and the category is crowded (Glara, ReFiBuy, Azoma, Yotpo Discover, Alhena, Profound, Semrush, Searchable). Never knock a competitor by name.

**The ICP:** DTC founders and heads of e-commerce, roughly $1–10M/year, 500–5,000 SKUs, under ~25 people, no in-house e-commerce ops hire. Spec-driven categories — furniture, mattresses, technical apparel, tools, skincare with actives, supplements, pet and baby products. Rule of thumb: if a buyer would type the question with a number or a material in it, the category qualifies.

> Note: `context/BUSINESS.md` says $1–5M and `context/ICP.md` says $1–10M. The wider range is used here. Reconcile the two files when convenient.

> Note on targeting: `ICP.md` warns against narrow targeting before validation. That warning governs *who we accept*, not *who we write for*. Content pillars stay narrow because vague content lands with nobody; the sales filter stays wide. If an off-pattern brand replies, that's a finding worth recording in `research/`, not an off-target lead.

**What keeps them up at night:** traffic is getting more expensive, they can feel search changing under them, and they have no idea whether AI assistants can see their products at all. They've probably tried an SEO agency that didn't move much.

**The Authority Triangle** — what earns the right to talk about this:

| Leg | Strength | What to use |
|---|---|---|
| Experience | Strong | Built Produkto; it runs real buyer questions across real catalogs every day; hundreds of captured ChatGPT answers per category from outreach research |
| Expertise | **Strongest — lead with this** | Knows what AI actually recommends in specific categories and what the picked product pages state that others don't. Product level, not website level. |
| Evidence | Real but gated | Captured answers with dates (usable now). Client numbers (only with that client's OK). No proof yet that fixes move visibility. |

**Lead with what the answers show.** The content edge is real AI answers in one category, stated with numbers — not credentials, and not results we can't show.

---

## Honesty rules — non-negotiable

LinkedIn rewards confident claims. Do not let it manufacture them. These match `skills/produkto-copy/SKILL.md`; when in doubt, that file wins.

- **Real AI answers only.** Every answer shown or counted is a captured one, with prompt, engine and date saved in a file. Say how it was asked ("asked for three products"). Never present invented or "typical" answers as ChatGPT output.
- **No promise of results.** It is not proven that fixing product pages moves AI visibility — not by us, not by the funded competitors. Say what Produkto *does* (measures, finds gaps, drafts fixes). Never "get recommended", "rank higher in ChatGPT", "more sales from AI".
- **Clients are named only with their permission.** Until then: "a pet brand we work with". Never invent a client, a quote or a number.
- **No M&O Living** anywhere public — no name, no audit numbers, no products. It's Kelian's family's shop.
- **No "nobody does X"**, in any wording, without a source. No knocking competitors.
- **Never state the scan recipe** (how many questions a Produkto scan uses or how many times each is asked). Outreach research numbers ("we asked 251 coffee questions") are fine; they describe a one-off study, not the product.
- Market figures (Adobe etc.) are fine when attributed. Always pair with the counterweight: AI is still a small share of most brands' traffic.

Uncertainty stated plainly reads as credibility here, not weakness. Most of this category is overclaiming.

---

## Content pillars

Four. Everything posted fits one.

**1. AI is becoming a shopping channel**
What's actually changing in how people buy, backed by real figures. Adobe: AI referral traffic to US retail +393% YoY in Q1 2026; AI traffic converting 42% better than other channels in March 2026, having been 38% *worse* a year earlier; 39% of consumers have used AI to shop. Always pair with the counterweight — AI is still under 5% of most brands' traffic. This is a channel arriving, not arrived. *Why the ICP cares: they can feel the shift and have no framework for it.*

**2. Why catalogs are invisible**
The mechanical explanation. AI reads stated facts, not marketing copy. Adobe found product detail pages score 66% machine-readable — worst of any retail page type. Concrete examples: the facts a buyer types into the question (size, material, ingredient, price, use case) that the product page never states. *Why the ICP cares: it reframes a vague fear as a fixable, specific problem.*

**3. AI Shelf Reports and teardowns**
The highest-value pillar and the hardest to fake. Real answers in one category: which brands and products ChatGPT picks, how concentrated or scattered the picks are, what the picked product pages state that the others don't. Tied to the week's outreach niche. *Why the ICP cares: it's the closest they get to seeing their own category's AI shelf, and it makes the free check the obvious next step.*

**4. Building in public**
What's built, what a merchant asked for, what a demo taught, what was wrong. Kelian's lane: the product and the data. Gabe's lane: the sales side — calls, objections, what founders didn't know. *Why the ICP cares: it builds trust and shows real people behind the product.*

To generate posts from a pillar, ask: what are the common mistakes here? the best practices? my contrarian view? my framework? a story from doing the work? a myth to bust? Each answer is a post.

---

## The four post types and the mix

Target ratio across any month:

| Type | Share | Job |
|---|---|---|
| Educational (cheat sheets, frameworks, how-tos) | 50% | Reach, followers, authority |
| Personal story | 25% | Trust, differentiation |
| Lead magnet | 15% | Email list — the owned asset |
| Conversion | 10% | Actual pipeline |

### 1. Educational / cheat sheets
Currently the highest-reach format, because they get reposted. A specific actionable topic, complex information broken into digestible numbered steps, clean visual hierarchy, genuinely worth saving. Text post plus a designed image.

Strong fits here: "What Google reads vs what AI reads on a product page." "The AI shelf for coffee: who gets picked." "What a product page needs to state before AI can recommend it."

**Anatomy of one that converts.** Drawn from three sheets that each cleared 300+ comments (SEO vs AEO vs GEO; How To Master Claude Skills; the PLAY Framework):

- **Title with one highlighted keyword.** The subject sits inside a coloured block. In a feed thumbnail the eye lands on it before anything is read.
- **A subtitle naming who it's for or what it achieves.** One line, directly beneath the title. *"What businesses need to know to win Search in 2026."*
- **Three to five columns or blocks.** One per element of the framework. Three is the most common, five is the ceiling.
- **Identical sub-structure inside every block.** The SEO/AEO/GEO sheet runs *definition → how it works → pros → cons → how to rank higher* in all three columns. That repetition is what makes it scannable; breaking the pattern in one column breaks the whole sheet.
- **Dense, but ordered.** These carry far more text than looks advisable and it works, because the grid does the job whitespace usually does. Don't sparsify them.
- **A footer strip:** name and photo, the download instruction, and where to get it. All three examples have one.
- **The download is the point.** The image is the advertisement; the high-res version behind an email address is the product.

**To make the image, use the `cheatsheet-design` skill** (`.claude/skills/cheatsheet-design/`): six Donnelly-style formats as HTML templates plus a render script.

**Comparison sheets outperform single-topic sheets** — X vs Y vs Z hands the reader a decision, not just information. The obvious first one here (SEO vs AEO vs GEO) has already been published by someone else, so take a different cut: the same three lenses applied to a *product page* rather than to a website.

### 2. Lead magnet posts
How attention becomes email. Structure: hook positioning the resource as essential → brief description of what's inside → clear instruction to get it (comment a keyword, link in comments) → visual of the resource.

**The free check is the lead magnet.** It's the diagnostic, the sales pitch and the demo opener at once. Two ladder rungs:

- *Low friction:* a category Shelf Report as a PDF (who AI picks in coffee, in pet) — email capture.
- *High friction, high intent:* "Comment CHECK and I'll run a free check of your catalog and send you the results." Every comment is a lead; reply, DM, run it, book the demo.

**Format conventions worth copying:** show the resource as a rendered book or report cover mockup rather than a flat PDF page; put a badge on the cover for the second offer (*"+ free check of your catalog"*); make the CTA comment-a-keyword rather than a link, because links suppress reach; reserve scarcity framing (*"spaces are limited"*) for the higher-friction ask.

**This exact lane is already contested.** Searchable — named as a competitor in `context/BUSINESS.md` — is running this play in AEO right now: a gated *AI Search Ranking Guide* plus a free AI visibility audit, pulling 900–2,100 comments per post. That's direct evidence the format works on this audience, and equally that a generic "AI search guide" is now a commodity. The differentiator has to be the same one the business runs on: **e-commerce catalogs at product level, not websites at brand level.** Log this in `competitors/LANDSCAPE.md`.

### 3. Personal story posts
First person, specific details that make it real, building to a lesson the reader can use. Early-stage is an asset: a founder seeing their AI shelf for the first time, a cold call that went sideways, a feature a merchant asked for. Include the awkward parts — the unproven link between fixes and visibility, the 100 cold emails that got zero replies. Every detail must have actually happened; Gabe's stories come from Gabe.

### 4. Conversion posts
Used sparingly but genuinely used. States the offer, who it's for, the outcome, and a clear CTA. Most founders educate forever and never ask; conversion posts serve people already ready to move. The ask is the free check or a demo. Name a client result only once that client has agreed.

---

## What's working now (scrape, 18 Oct 2026)

400 recent posts from 10 AI search and e-commerce creators: `GTM/linkedin/research/2026-10-18-top-creators.md`. Default formats, in order: **(1) cheat sheet** with numbered blocks and a "Do this today:" action in each (Donnelly), **(2) resource roundup**, a numbered list of free tools or guides with links in the first comment (Donnelly's best: 270 shares), **(3) 2-minute self-check** the reader can run on their own store (Lily Ray), **(4) data post** with the method in small print (Ethan Smith, Kevin Indig). Offer goes in a **P.S.**, sign off "Let's keep building, Kelian". Kelian prefers these proven formats over posts built around our own data; our data is optional seasoning, never the reason for a post. Re-scrape every ~2 months.

---

## Sourcing ideas — the pre-validated swipe file

**Pre-validated content = an idea, format or hook that has already performed disproportionately well, for you or for someone else.** Originality is not the goal and is usually a tax. The goal is a proven shape carrying your specific expertise.

Build a list of top creators in two lanes and keep it as a file in the workspace, not in your head.

**Lane 1 — creators inside the niche** (AEO, e-commerce, SEO, DTC operators)
Take: which topics are running hot, the angles in use, visual formats, and which posts actually earned engagement. Then find the different angle. **Do not copy** — it's a fine line, and in a niche this small the audiences overlap enough to notice.

**Lane 2 — creators in unrelated niches.** This is where the leverage is.
Take: hook structures, content formats, credibility framings. A format that's working in finance, design education or fitness is often new to e-commerce readers. Being the person who carries a proven format into a category that hasn't encountered it is the cheapest edge available.

Pre-validation applies to more than post ideas — **hook structures, lead magnets, formats, and ideas from other platforms** (Reddit threads, YouTube titles, newsletter subject lines) are all fair to lift structurally.

Before drafting anything from scratch, ask: is there a shape that already worked that this insight could sit inside?

---

## Writing mechanics

- **The hook is the first two lines.** Everything after "…see more" only gets read if those earn it. Specific number, uncomfortable claim, or a sentence that names the reader's exact situation. No throat-clearing, no "In today's fast-paced world."
- **One idea per post.** Two ideas is two posts.
- Short lines, generous line breaks, no dense paragraphs.
- Concrete over abstract: "ChatGPT named 309 coffee brands; 70% of them only once" beats "AI recommendations are fragmented."
- American spelling (catalog, optimize). No emoji, no exclamation marks, no "unlock", "game-changing", "leverage".
- No emoji bullets, no "Agree?", no engagement bait, no fake vulnerability.
- Sound like a person who does the work — not a marketer describing it. Direct, plain, willing to say what isn't known. Cut every word that doesn't change the meaning.
- **Links kill reach.** Put them in the first comment.
- End with something that invites a real reply, not a demand for one.

---

## Profile

The profile is a landing page, not a CV. Every visitor decides in seconds whether to follow.

- **Headline** (220 chars, follows you everywhere): `[What you do] for [who you help] | [proof point]`. Example shape: *"Founder, Produkto | I show DTC brands how AI recommends their products, product by product."* Describe the work, not a promised outcome.
- **About:** opening hook that names the ICP's problem → short credibility story → what you do and the outcome → who it's for, so they self-identify → one clear CTA.
- **Featured:** 3–5 items max, all serving conversion — the CHECK post, the best Shelf Report, getprodukto.com.
- **Experience:** outcomes, not responsibilities. "Built and scaled a team 3→15, +140% revenue in 18 months," not "managed a team."
- **Skills:** keywords the ICP actually searches.

---

## Engagement — 30/30/30/10

Half the game. Do it for 30 minutes *before* posting, not after.

- **30% on the ICP** — DTC founders and e-comm leads. Puts you on their radar before any pitch.
- **30% on larger creators** — a substantive comment on a big post is a borrowed audience.
- **30% on industry peers** — e-commerce, SEO, AEO. Partnerships and referrals live here.
- **10% on friends and colleagues.**

Comments must add an insight, ask a real question, share relevant experience, or respectfully disagree with reasoning. "Great post!" earns nothing. On your own posts: reply to everything, especially in the first 30 minutes, and reply to the specific point they made.

---

## The weekly operating rhythm — four hours

The claim is that the whole thing fits in four hours a week once it's systematised:

| Block | Hours |
|---|---|
| Ideation | 1 |
| Writing | 1 |
| Design | 1 |
| Community engagement | 1 |

The slide behind this listed roughly ninety distinct tasks that "posting on LinkedIn" actually contains — strategy, profile, planning, production, engagement, network, DMs, capture, conversion, measurement, admin. The point of that list is that four hours is only achievable with three things in place: **a proven content system, AI, and delegation.**

All three apply now. The system is this file. AI absorbs the writing and design blocks (Claude drafts both accounts' week every Sunday). Delegation is the second founder account: Gabe posts in his own lane. Connection requests run on the in-house agent (`GTM/linkedin/agent/`).

Keep engagement human: the 15 minutes of comments before posting and the replies in the first 30 minutes after are the non-negotiable part. It's the only block that puts you in front of named ICP accounts.

---

## Deplatforming — build the list

LinkedIn is rented land; reach can halve on an algorithm change. Donnelly's stated biggest regret was reaching 250,000 followers with zero email subscribers.

Flow: lead magnet → LinkedIn post → landing page → **tag by ICP segment** → nurture sequence → offer. Start the list from post one, not from month twelve.

**The tag matters more than the sequence.** Segment on category and catalog size, not on activity. *"Furniture, 500–3,000 SKUs"* is a tag; *"downloaded something"* is not. The entire point is being able to send the right case study to the right person.

**The four-email sequence:**

| Email | Job |
|---|---|
| 1 | Personal story on the pain point |
| 2 | Deep education using your IP or system |
| 3 | Specific case study matched to their tag |
| 4 | Subtle offer promotion with social proof |

**Emails 3 and 4 need client permission to be specific.** Until a client agrees to be named:

- **Email 3 →** a Shelf Report for their category (real answers, dated), or "a [category] brand we work with" with no invented numbers.
- **Email 4 →** the free-check offer. Swap in a named client result the moment one agrees.

---

## Repurposing

When something performs, run it through: cheat sheet or infographic? carousel? newsletter section? short video? broken into several smaller posts? referenced in future content? Never cross-post to M&O Living's channels — separate brand, separate skills.

---

## Expectations

Months 1–2: foundations, finding voice, minimal growth. Months 3–4: content improving, follower growth visible. Months 5–6: inbound starting, list growing. Months 7–12: compounding, consistent lead flow.

Most people quit in months 1–2. Given the current priority is demand validation, judge the first 90 days on **demos booked and free checks requested**, not followers.

---

## Two accounts

Kelian and Gabe each post once per weekday (a second post within ~24h splits reach). Different lanes so the accounts don't echo each other: **Kelian = the data and the product; Gabe = the sales side and founder conversations.** Gabe reshares or comments on Kelian's Shelf Report with his own take rather than writing a second version. Both posts in a week target the same niche as that week's cold emails and connection requests.

---

## Output format

Deliver posts ready to paste — no commentary wrapped around them unless asked. For each post give: the post text, the type and pillar it belongs to, and a one-line note on any visual needed. If drafting several, vary the hooks; three posts opening the same way is a tell.

Save any multi-post batch or calendar as a file in the workspace folder rather than leaving it in chat.
