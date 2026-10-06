# The first 20 — runbook

**Date:** 5 August 2026
**Goal:** answer *"do mid-market DTC brands care enough to pay?"* — the first unproven item in `BUSINESS.md`.
**Not the goal:** closing anyone. Selling this week corrupts the signal.

---

## What I could and couldn't do

**Did:** wrote `triage.py`, assembled a candidate pool, drafted the outreach and the interview set.

**Couldn't:** run anything against a live store. My sandbox has no network egress to arbitrary sites (403 at the proxy). So SKU counts, platform checks and Yotpo detection in `candidates.txt` are **unverified guesses** — the script exists precisely because I can't do this part and you can.

**Constraint you should keep in view:** `attributes.py` has `CATEGORIES = {"furniture": FURNITURE}`. Every audit below is scored against the furniture table. The sleep, kids and workspace brands in the pool are deliberate stress tests — if their reports read as nonsense, that tells you what extending the tool costs before you spend a week on it.

---

## Step 1 — Triage (30 min, mostly waiting)

```bash
cd ~/Desktop/"Kelian OS"/AEO-for-eccomerce-brands
python3 prospecting/triage.py prospecting/candidates.txt --delay 1.0
```

Checks each domain for: reachable, Shopify, product count via `/products.json`, Yotpo, review app, and whether robots.txt blocks AI crawlers. Applies the three hard exclusions plus the 150-SKU floor. Writes `prospecting/triage-<date>.md` with a ready-to-paste block of audit commands.

**Expect roughly half the pool to fail.** That's why there are 34 names for a target of 20.

**The one output worth reading closely:** the `Blocks AI` column. A brand disallowing GPTBot has already decided this channel doesn't matter. That's not a reason to skip them — it's a finding, and arguably the most interesting conversation on the list. Log it either way.

### If fewer than 20 survive

Don't pad with brands you haven't checked. Better sources, in order of signal:

1. **Reverse-engineer from the problem.** Ask ChatGPT ten spec-shaped furniture queries. Note which brands get recommended. Then find competitors in the same category who don't. The report writes itself — you already know who's beating them, and that comparison is the most persuasive line in a cold email.
2. **Store Leads / BuiltWith** — filter Shopify + furniture + traffic band. Cleanest targeted list, costs money.
3. **Shopify's own store directory**, plus `site:myshopify.com` searches for the category.

---

## Step 2 — Run all 20 before sending any

```bash
python3 build/audit.py https://brand.com --category furniture --delay 0.35
```

Batch it. Two reasons: you'll spot cross-brand patterns you'd miss one at a time, and those patterns are the raw material for the LinkedIn teardown pillar.

**Read every report before it goes out.** The tool guesses product family from title and tags. A bad guess produces a confident wrong claim, and one wrong claim in a cold email costs you the whole conversation. Budget ~5 minutes per report.

**Log the cross-brand numbers as you go** — which attributes are missing everywhere, what the score spread looks like, whether any category is systematically worse. That aggregate is more valuable than any individual audit: it's original data nobody else has, and it's the only thing that gets you out of citing a single family-shop catalog forever.

---

## Step 3 — The email

Send from your own address, one at a time, no sequencer. Twenty is small enough to do by hand and hand-sent mail doesn't look like a campaign.

### Template

> **Subject:** {Brand} — 1,240 products, 6 attributes missing from all of them
>
> Hi {Name},
>
> I ran an audit across {Brand}'s catalog this week — {N} products, scored on whether the pages state the facts an AI assistant needs to recommend a product.
>
> The short version: {headline finding, one sentence}. {Specific attribute} doesn't appear on any product, so a question like "{realistic buyer query}" has nothing in your catalog to match against.
>
> Full report attached. It's free and there's nothing attached to it — I'm building in this space and running audits to find out whether it's a problem anyone actually cares about.
>
> If it's useful, I'd value 20 minutes to hear whether this matches anything you're seeing. If not, no reply needed.
>
> Kelian
> {one line: what you do} · {link}

### Why it's shaped like that

- **Subject carries a number and their brand.** Donnelly's data is unambiguous: hooks that open on a hard figure outperform. Same principle in an inbox.
- **The finding is in the second paragraph**, not the fifth. If they read two sentences, they get the value.
- **The buyer query is the whole trick.** Abstract scores don't land; "a sofa with removable covers for a covered terrace" makes the gap concrete and slightly uncomfortable in a useful way.
- **"Nothing attached to it" is literal.** No call link, no PS, no follow-up sequence. The report is the gift; the ask is optional and small.
- **Saying you're building and don't know yet** is the honest framing and it lowers their guard. You're asking for help, not selling. People answer that.

### Rules

- Never call M&O a client or case study. If it comes up: *"a Barcelona furniture brand — full disclosure, it's my family's shop, which is why I had a catalog to test on."*
- Never claim fixing this will get them recommended. It's unproven. Say what's missing, not what fixing it earns.
- One follow-up maximum, one week later, two lines. Then stop.
- EU recipients: cold B2B email runs on legitimate interest under GDPR — keep it relevant to their actual job, identify yourself properly, and honour any opt-out immediately. Twenty hand-written emails to relevant founders is fine; a scraped blast is not.

---

## Step 4 — The conversation

The trap: *"would you pay for this?"* Everyone says yes to be polite, you collect fifteen false positives, and you build for another six months on nothing.

Ask about **past behaviour**, not future intent:

1. What did you do the last time you thought traffic was dropping?
2. Who owns product page content, and when did they last touch it at scale?
3. Have you spent money on anything AI-search related? What happened?
4. Walk me through the last time you updated 100+ product pages. What did that cost you in time or money?
5. When you saw the report — what was your first reaction? Did you show it to anyone?
6. What would have to be true for this to be worth €5,000 to you?
7. Who else would need to agree?

**Question 5 is the one that matters.** Whether they forwarded it internally is a stronger buying signal than anything they say about budget.

### Fill in the empty section of ICP.md

`## How they'd describe the problem themselves` is deliberately blank. Filling it is arguably the highest-value output of this whole exercise. Capture **exact phrasing**, not paraphrase:

- What do they call this when nobody's selling to them?
- "AI search," "ChatGPT," "LLMs," or something else?
- Brand level or product level? **Settled — they think product-level** (see `context/ICP.md`). Still worth capturing *how* they phrase it, but this is no longer a test the wedge has to pass.

---

## What counts as a real signal

| Strong | Weak |
|---|---|
| Asks what it costs, unprompted | "This is really interesting" |
| Forwards it internally | Likes your LinkedIn post |
| Asks if you can do it for them | "Definitely something we should look at" |
| Asks how you'd measure improvement | Books a call and no-shows |
| Pushes back on the methodology | Polite thanks |

Pushback is a good sign. Someone arguing with the report has read it and cares about being wrong.

**Scoreboard for this batch:** 20 sent · replies · calls booked · calls held · anyone asking about price · anyone forwarding internally.

**If 20 reports produce zero replies**, the problem is upstream of the email — either the ICP or the premise. That's the answer you came for, and it's worth more than a year of building. Honour the kill criteria rather than rationalising them.

---

## Order of operations

1. Triage the pool → get to 20
2. Run all 20 audits, read every report
3. Log the cross-brand pattern (this becomes LinkedIn pillar 1 and the "original data" hook)
4. Find the founder's name and email for each — LinkedIn to identify, then the site or a finder tool
5. Send, one at a time, by hand
6. One follow-up at day 7, then stop
7. Fill in `ICP.md`'s empty language section from real quotes
