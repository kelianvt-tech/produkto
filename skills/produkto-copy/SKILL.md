---
name: "produkto-copy"
description: "Produkto's copy rules — the voice, the claims that are allowed, and the ones that are banned with sources. Use for ANY user-facing Produkto words: the marketing site, the MVP dashboard and its onboarding, support and docs pages, waitlist and agent copy, product names, empty states, error messages, button labels. Also use when reviewing existing Produkto copy or when a sentence makes a claim about the market, a competitor, or what Produkto will achieve for a merchant. Do NOT use for M&O Living (that is marketing-team:copywriter), for Kelian's LinkedIn (that is linkedin-growth), or for cold outreach emails (that is the Cold Email Outreach agent)."
---

# Produkto copy

Every user-facing word in Produkto. This exists because the same four mistakes kept shipping and getting caught by hand.

**The product, in one line:** paste your store URL, Produkto measures how your whole catalog shows up in AI answers, and tells you where you stand against whoever is actually being recommended.

**Who reads it:** a mid-market DTC founder or marketing lead, mostly American, who is not technical and is not sure this category is real yet. They are skeptical, they will check a claim, and they have been pitched by four AI-visibility tools this month.

---

## Voice

Plain, specific, unhurried. Closer to a good analytics tool than to a growth-hack landing page.

- **Cut every word that doesn't change the meaning.** This is the single biggest lever. Draft, then delete.
- **Say the thing, then stop.** No sentence whose only job is to soften the one before it.
- **Concrete over abstract.** "The AI named 12 products; three were yours" beats "unlock catalog-wide visibility intelligence."
- **Plain words.** The reader is not technical. Any jargon that survives has to earn it and be explained on the spot.
- **American spelling.** The customers are American and the app already uses it 232 times to 11. `catalog`, not `catalogue`. `optimize`, `analyze`, `recognize`.
- **No exclamation marks. No emoji. No "unlock", "supercharge", "game-changing", "seamlessly", "effortlessly", "leverage".**

---

## The banned moves

Each of these shipped at least once and had to be pulled.

### 1. The hedge-and-tease paragraph

**Banned:** any paragraph that gestures at unnamed future scope.

> ~~"There's more we haven't pinned down yet. The list above is where we're starting, not where it stops."~~

Tells: *"this is just the beginning"*, *"and much more"*, *"where we're starting, not where it stops"*, *"there's more we haven't pinned down"*. It reads as AI, and it is doing no work.

**Instead:** if a capability is real, give it its own plain line in the list. If it is not real yet, write nothing. An honest gap beats a teased one.

This holds even when Kelian asked for the future scope to be mentioned — he approves the *content*, not that shape of paragraph.

### 2. "Nobody does X"

**Banned in every wording**, including casual drafts and internal messages: *"nobody does this for ecommerce"*, *"nobody does product-level AI visibility"*, *"nobody has locked down mid-market"*, and the hedged versions — *"almost nobody"*, *"nobody at mid-market"*.

**Why it's false:** the category is populated. Glara does ecommerce-only attribute auditing at product level and sells to mid-market right now ($120/mo "growing brands", $345/mo "scaling brands"). ReFiBuy raised $13.6M seed in May 2026 for evaluate → enrich → distribute → monitor. Azoma, Yotpo Discover, Alhena, plus Shopping modules at Profound, Semrush and Searchable.

**Why it's worse than false:** with zero customer conversations there is no evidence about who owns a segment. It dresses absence of evidence as a finding. **Any sentence of the form "nobody has X" needs a source or it does not get written.**

**Use this instead — it is checkable and survives a prospect verifying it:** everyone selling product-level AEO at mid-market prices caps the number of SKUs. Glara tracks up to 20 products on Starter, 50 on Advanced. Alhena optimizes 25–50 product pages a month. At 2,000 SKUs a merchant either buys enterprise or leaves most of the catalog uncovered. **Whole-catalog coverage at mid-market price** is the specific gap.

### 3. Promising the result instead of the work

**Banned:** any claim that Produkto, or a content agent, will improve a merchant's AI visibility, rankings, traffic or sales.

Nobody has demonstrated that remediation moves AI visibility — not us, not the funded competitors. It is one of the two open questions the product exists to answer. Promising it is how you get a bad sales call later.

- Banned: ~~"product pages designed to rank well in AI answers"~~, ~~"get recommended more"~~, ~~"improve your visibility"~~ as an outcome.
- Allowed: *"Finds the details buyers ask about that your pages leave out."* *"Drafts the updates for you to review."* *"You review everything before it goes near your store."*

Say what it **does**. Never what it **gets**.

### 4. Publishing the recipe

**Never state how many buyer questions a scan uses, how many times each is asked, or the total answer count.** No "five questions", "asked five times", "25 answers". A stated recipe invites *"I can do that myself."*

- Instead: *"your buyer questions, each asked several times."*
- Report percentages, not "X of 25".

The method lives in `mvp/PLAN.md`, never in user-facing copy.

### 5. "Talk to Kelian" and naming the engines

**Banned: "Talk to Kelian"** (and "Talk to sales", "Contact Kelian") on any button or call to action. Every demo CTA says **"Book a demo"**, including the Custom pricing plan. Kelian's words, 2026-09-28: "stop saying 'talk to Kelian.' Just say 'book a demo'." Leave existing uses of his name elsewhere (e.g. the booking section heading) alone unless asked.

**On the pricing page and in plan features, don't name the AI engines** (ChatGPT, Perplexity, Google AI Overviews) or count them ("3 AI engines"). Say **"AI"**: *"Every plan measures how AI recommends your whole catalog."* The engine list stays in the FAQ and the rotating hero logos. **Exception (Kelian, 2026-10-14), supersedes the line above for engines on plans:** the pricing page names the engines as logo + name pills (logos alone were unreadable; Gemini and the AI Overview sparkle looked alike, so Google engines use the Google "G"). Starter card: ChatGPT, AI Overviews, Perplexity. Growth card: "+3" Gemini, AI Mode, Copilot. The comparison table lists all of them per plan. The hero line "Every plan measures how AI recommends…" still says "AI".

---

## Evidence rules

**Real AI answers only.** Any example of an AI response must be a captured real one, with the prompt, answer, date and source recorded (see `produkto-site/chatgpt-captures-2026-09-16.md`). Never label web research or generated text as an actual ChatGPT result. Never pair a real answer with an invented product name.

**No M&O Living anywhere public.** Keep the name, molivings.com, the audit numbers (86 products, 16.8/100, the six blind spots), M&O product quotes and any link to that audit out of the Produkto site and app entirely. It is Kelian's family's shop, not an arm's-length case study. Where a page needs example data, use clearly labelled illustrative data for a **fictional, non-furniture** catalog.

**Say when something is a guess.** This project has more unknowns than knowns. A flagged uncertainty costs nothing; a confident wrong number costs a customer.

---

## Describing the product correctly

- **It is catalog-level.** Paste your store URL and the whole catalog is measured. The merchant does **not** pick one product. (`mvp/PLAN.md` still says "Select one product" — that is out of date, superseded 2026-09-18.) A single-product page exists as a drill-down, not the entry point.
- **The comparison is against every competitor found in the answers.** Nothing to configure, no competitor selection. Do not describe it as a comparison against one rival.
- **Visibility is "mentioned in X% of answers"**, with average position shown separately. Not a blended "/100" score.
- **Measurement, not attribution.** Produkto measures what AI answers say. It does not measure traffic, sales, or whether a mention led to anything — and docs should say so plainly.

---

## Support and timing copy

- Response promise: **same day, 9:00–18:00 CET, Monday to Friday** — always with the Eastern equivalent (3:00am–12:00pm ET) beside it. Most merchants are American; a merchant writing in their afternoon needs to know that is the next working morning.
- Any date, time or "today" shown to a merchant is in **their** timezone, and copy should never assume the reader shares Kelian's.
- Contact address is **`kelian@getprodukto.com`** (forwards to Kelian's Gmail via Namecheap; set 2026-09-28). Never put the Gmail address in user-facing copy.

---

## Before shipping any Produkto copy

1. Does any sentence claim what nobody has proven? Cut or rewrite as what it does.
2. Does any sentence say "nobody"? Source it or cut it.
3. Is there a paragraph teasing unnamed future scope? Cut it.
4. Does it state the number of questions, runs or answers? Rewrite.
4b. Any "Talk to Kelian" CTA, or named/counted AI engines on pricing? Change to "Book a demo" / "AI".
5. Is every AI answer real and recorded? Is every number sourced?
6. Any trace of M&O Living? Remove.
7. Read it aloud. Delete every word that didn't change the meaning.
