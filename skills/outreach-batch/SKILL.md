---
name: "outreach-batch"
description: "Build a new batch of e-commerce founders to email or DM for Kelian's AEO customer-discovery interviews. Use when he asks for more brands to contact, another batch of leads, more people to email, a new send list, or wants to extend the prospect list. Produces a send-ready markdown file with each brand's email, Instagram, site, source article, subject line and finished message. Do NOT use for LinkedIn content or posting, which belongs to the linkedin-growth skill."
---

# Outreach batch

Builds a fresh batch of e-commerce founders for Kelian to interview, ending in a markdown file he can work straight down: email address, Instagram handle, site, source article, subject line, finished email, finished DM.

**Working folder:** `AEO-for-eccomerce-brands/prospecting/`

**The goal is conversations, not sales.** Kelian is pre-validation with zero customers. These are research interviews for a report. Nothing in this pipeline pitches anything.

---

## The pipeline

Three steps. Steps 1 and 3 are yours; step 2 is his, because the sandbox cannot reach brand websites.

### 1. Find brands, build `brands-batchN.csv`

Scrape a source (below), strip anything that isn't a real store, and write:

```
brand,founder,slug_guess,category,size_signal,episode_url
```

- `founder` — only if the source names them. Leave blank rather than guess.
- `slug_guess` — likely domain stem, used only as a fallback.
- `size_signal` — revenue or scale if stated. Put `spec-heavy` here for catalogs where buyer questions contain numbers or materials (watches, filtration, grills, furniture, lighting, sports equipment). Those surface in the output.
- `episode_url` — the article. Essential: it supplies both the domain and the personal line.

**Always dedupe against every existing `brands*.csv` before writing.** He has contacted ~160 brands already and a repeat message is worse than no message.

### 2. He runs the enrichment

```bash
cd ~/Desktop/"Kelian OS"/AEO-for-eccomerce-brands
python3 prospecting/enrich.py prospecting/brands-batchN.csv
```

Roughly a minute per brand, unattended. Resolves the real domain from the article, then visits the store for Instagram, published emails and the founder's name. Writes `enriched-<date>.csv`.

Tell him to start it and walk away. Do not offer to do this part; the network is blocked here and pretending otherwise wastes his time.

### 3. Generate the send file

```bash
python3 prospecting/make-send-file.py prospecting/enriched-<date>.csv
```

Writes `send-today-<date>.md`, sorted best-first, in batches of 25. The template lives in that script and is locked. If he wants wording changed, edit the constants at the top rather than regenerating by hand.

---

## Where to find brands

**Shopify's blog, Podcasts tag** — `https://www.shopify.com/blog/topics/podcasts?page=N`. Every brand is a Shopify merchant and the founder has given a long-form interview, which is the single best predictor that they will reply to a stranger. Pages 1 to 5 are used up (~160 brands); page 6 onward is untouched.

**Other interview sources**, same logic:

- My Wife Quit Her Job (Steve Chou) — every guest is bootstrapped, no VC, no gatekeeper. Highest reply odds on this list.
- eCommerce Conversations (Eric Bandholz) — wide category spread
- Unofficial Shopify Podcast (Kurt Elster)
- EcommerceFuel (Andrew Youderian) — 5 to 9 figure operators
- Shopify case studies

**Exclude, every time.** The Podcasts tag is not all merchants:

- Agencies, consultancies, design studios, PR firms
- Course and education businesses
- Investors, private equity, VC guests
- Shopify's own staff and executives
- Multi-founder roundups and generic how-to articles with no brand attached
- Anyone who isn't running a catalog they control

### Selection signals

Ranked above category, which does not predict replies:

- Has given a long-form interview
- Founder publicly named
- Under ~30 people, no careers page
- Bootstrapped
- Posts regularly

**Category does not matter for interviews.** The audit tool only scores furniture, which is irrelevant here — he is asking questions, not auditing. Do not filter by category, and do not repeat the mistake of narrowing to furniture because the tool prefers it.

---

## The message

Locked in `make-send-file.py`. Every clause was fought over:

> Hi {First},
>
> My name's Kelian, I'm a student at IE University in Madrid.
>
> I came across your story on the Shopify blog about {phrase}. I'm putting together a report on how e-commerce founders are thinking about AI search, whether buyers asking ChatGPT for products is actually showing up for you yet, or whether it's still mostly noise. I'd rather just ask the actual people running real stores than read another article about it.
>
> Would you have 20 minutes for a short interview? Happy to work around your schedule.
>
> By the way, I really admire what you've built.
>
> Thanks,
> Kelian

**Subject:** Student report on AI search

**Rules that produced it:**

- **No em dashes or en dashes anywhere.** They read as AI generated. The script checks and prints a dash report; a failed check means fix before sending.
- **"report", never "research".** His word.
- **"story on the Shopify blog", never "episode".** The Podcasts tag contains written articles as well as interviews. He sent 34 emails praising episodes that did not exist before catching it. Format-neutral wording is now permanent.
- **The student line is true.** He is enrolled at IE. It works because it is honest and low stakes. Never invent a credential.
- **No free audit, no link, no attachment, no "not a pitch".** The only ask is 20 minutes. Protesting innocence is what a pitch does.
- **The sign-off compliments what they built**, not the format of their feature.

### The opener, and its fallback

`phrase` is derived from the article slug, with brand tokens stripped from the front (including spelling and numeral variants: *sugardough* for Sugardoh, *8th* for Eighth Generation). Roughly half of any batch yields a usable phrase.

When it doesn't, the script does **not** emit a placeholder for him to fill. It writes:

> I came across your story on the Shopify blog and found it really inspiring.

Still true, claims no specific detail, needs no manual work, and reads warmly. The row is flagged noting a real detail would land better, but it is sendable as is. **Never reintroduce a `{{ WRITE ONE LINE }}` placeholder** — he sends in batches of 25 and will not stop to fill them.

---

## Founder names: three sources, three levels of trust

The `founder_source` column in the enriched CSV records provenance. This matters more than it sounds.

| Source | Trust | Why |
|---|---|---|
| Left blank in `brands-batchN.csv` | n/a | Output uses `{FIRST NAME}`, he fills it |
| `episode page` | **High** | The article's own description names them. This is the interviewee. |
| `guessed from site copy - VERIFY` | **Low, ~50% wrong** | Regex found a capitalised name near "founder / CEO / owner" on the About page |

The guessed ones fail in three distinct ways, all seen in real batches:

- **Headings mistaken for names** — "Our Founder", "Founder Story", "Family Photo", "Better Sleep"
- **Right company, wrong person** — Eighth Generation returned Colleen Echohawk, who is the CEO. It was founded by Louie Gong and later acquired by the Snoqualmie Tribe, and she was not the interviewee.
- **Long-dead historical founders** — Belstaff returned Eli Belovitch, who founded it in **1924**

`make-send-file.py` flags every guessed name with `NAME UNVERIFIED` and names the failure modes in the output. **Do not silently trust that column, and do not remove the flag.** Roughly half are right and genuinely useful (Kevin Espiritu at Epic Gardening, Bea Dixon at The Honey Pot, Andrew Benin at Graza), so the answer is verification, not deletion.

Cheapest check: open the linked article. It names the person who was actually interviewed.

---

## Honesty rules

These outrank output volume.

- **Never claim a specific detail that wasn't verified.** Where no phrase exists the script falls back to a generic but true opener rather than inventing one, and it refuses to use a revenue figure as a personal detail. "The part about $2m stuck with me" is exactly the tell being avoided.
- **Never address someone by a name you haven't confirmed.** See above.
- **M&O Living is his family's furniture shop**, used as a test catalog. Never a client, never a case study.
- **No customer results exist.** Nothing may imply otherwise.
- **He does not pitch on these calls.** If asked what he is building, answer plainly and return to their answers. He told them he was not selling anything.

---

## Known data problems

Every batch so far has had at least one. Check before he sends.

- **Founder names** — see the table above. The biggest recurring issue.
- **Not all articles are interviews.** Click three or four links per batch.
- **Not all entries are stores.** See exclusions.
- **Guessed emails bounce.** Published addresses are safe; guesses are flagged in the output.
- **LOW SKU and Yotpo flags are noise here.** They come from the audit tool's filters and have nothing to do with whether someone is worth interviewing.

---

## Sending

- Batches of 25, roughly two hours apart. Individually, never BCC, no sequencer.
- Free Gmail allows around 500 a day, so volume is not the constraint. Bursts and bounces are.
- One follow-up after a week, two lines, then stop.
- Email first. If nothing after a week, Instagram DM the brand account (business accounts are public; the founders' personal ones are not, and are not needed).

---

## When a reply comes in

Keep it a call, not anything formal. Formality produces the PR answer.

Ask about past behaviour, never future intent. "Would you pay for this?" returns a polite yes and no information.

1. What did you do the last time you thought traffic was dropping?
2. Who owns product page content, and when did they last touch it properly?
3. Have you spent money on anything AI-search related? What happened?
4. Walk me through the last time you updated a lot of product pages at once. What did it cost?
5. Are you thinking about your brand showing up, or specific products?

**Questions 3 and 4 are the ones that matter** — both ask about money already spent. Question 5 is now confirmatory rather than load-bearing: brands do think product-level (`context/ICP.md`), so ask it for their phrasing, not for the verdict.

Log their **exact phrasing**, not a paraphrase. That fills the deliberately empty section in `context/ICP.md` and becomes every subject line afterwards.

Real signals: asked what it costs unprompted, forwarded it internally, pushed back on the method. Everything else is politeness.

**Target: 15 conversations.** Stop when he gets there. Finishing the list is not the goal.

