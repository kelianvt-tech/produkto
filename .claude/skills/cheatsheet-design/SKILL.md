---
name: cheatsheet-design
description: Make LinkedIn cheat sheets, lead-magnet covers and the posts that go with them for Produkto (Kelian's and Gabe's accounts), using Chris Donnelly's proven system (Searchable CEO; his Creator Accelerator webinar) pointed at e-commerce and AI shopping. Covers picking a pre-validated idea, the delivery test, eight HTML templates (3-way versus, layered funnel, "How To Master" panels, named framework, buyer-journey flowchart, before/after stack, annotated funnel, 3D book-cover lead magnet), a render script for ready-to-post PNGs, the caption, the comment-keyword CTA and the follow-up. Use whenever Kelian asks for a cheat sheet, infographic, LinkedIn image or carousel, a lead magnet, "a sheet like Donnelly's", or wants to start a new LinkedIn post.
---

# Cheat sheet design

LinkedIn cheat sheets and lead magnets for Produkto, built the way Chris Donnelly builds his, rewritten for e-commerce. Donnelly is Searchable's CEO, the biggest creator in AI search, and a direct competitor: **copy his structure and method, never his topics or his stats.**

Kelian approved the look on 18 Oct 2026 ("these are nice") and added the webinar slides the same day. Sources in this folder:
- `reference/donnelly-*.jpg`: his real sheets
- `reference/webinar/*.png`: 14 slides from his Creator Accelerator webinar (13 Aug 2026). Full replay: https://www.youtube.com/watch?v=JY9pukcAex4 (sent by email; YouTube refuses embedding/lookup, so it may be private or expire)
- `reference/ours-*.png`: our finished versions
- Scrape of what's working across 10 creators: `GTM/linkedin/research/2026-10-18-top-creators.md`

---

## When Kelian says "let's make a new post" — the flow

> **Always ask first (Kelian, 2026-10-19):** "Do you want to do an AI shopping news post this time?" Check the newest brief in `GTM/linkedin/news/` (written every Monday by the `ai-shopping-news-brief` scheduled task) and offer its pick. If the AI Shelf Watch data series (`GTM/linkedin/AI-SHELF-WATCH-PLAN.md`) still isn't built, ask whether to build it.



Run these in order. Ask only what you can't decide yourself; otherwise pick and say what you picked.

### 1. Find a pre-validated idea (webinar slides 08–10)
**Pre-validated content = an idea that has already performed disproportionately well, for us or for another creator.** Originality is a tax.
- **Creators in our niche** (AI search, e-commerce, DTC: Donnelly, Lily Ray, Peec, Profound, Chase Dimond, Nik Sharma…): take the **hot topics, then find a different angle** (ours is always *e-commerce, product level*), and their visual styles. Don't copy; it's a fine line.
- **Creators in other niches** (finance, design, fitness, AI tools): take **visual formats and hooks**. "Massive opportunity": a format that's proven elsewhere is often new to e-commerce readers.
- Pre-validation also applies to **ideas from other platforms, hook structures, lead magnets and formats.**
- To refresh the evidence, re-scrape (Apify `harvestapi/linkedin-profile-posts`, ~$0.002/post; say the cost first) and rank by reactions, comments and reposts.

### 2. Run the delivery test (slide 02; full four-part test in `reference/webinar/NOTES.md`)
Before anything else, check the **sender**: the posting account's headline and About must say AI shopping / e-commerce, or LinkedIn won't deliver the post to that niche. Post ~9am–noon US Eastern (15:00–18:00 Madrid).

| Low delivery (don't) | High delivery (do) |
|---|---|
| Personal stories with universal lessons | **Educational carousels and cheat sheets** |
| Hot takes and opinion | **Named IP, frameworks and methods** |
| Motivational posts | **Technical breakdowns for one role or industry** |
| Broad observations | **Case studies with the industry and numbers stated** |
| Written to appeal to everyone | **Written for specific titles and people** |

Ours: written for **DTC founders and heads of e-commerce**, about **their products in AI answers**. If any founder in any industry could use the sheet, it's too broad.

### 3. Pick the format (table below)
His slide "What Is Working" (03) names three: **cheat sheets, carousels, lead magnets**. Default to a cheat sheet; use the book cover when the post is a lead magnet.

### 4. Build, render, check (see Workflow)

### 5. Write the caption (see Pairing with a post)

### 6. Decide the CTA and the follow-up (see Capture)

### 7. After 48 hours, log the numbers in `GTM/linkedin/posts/LOG.md`
One row per post: date, account, format, hook, reactions, comments, reposts, CHECK comments, demos. This is our own pre-validation data. Before choosing a format, read the log and prefer what has worked for us.

---

## The anatomy of a cheat sheet that converts (slide 04)

His three best: **SEO vs AEO vs GEO** (3,873 reactions, 486 comments, 538 reposts), **How To Master Claude Skills** (3,401 / 341 / 321), **The "PLAY" Framework**. What they share:

1. **A title with one highlighted phrase** (serif, the key words in a colour block). In the feed thumbnail, the eye lands there first.
2. **A one-line italic subtitle** saying who it's for or what it achieves ("Use this sheet to achieve personal leverage and freedom").
3. **3–5 blocks, identical structure inside each.** SEO/AEO/GEO runs *name → mock screenshot → "X = definition" → How it works → Pros → Cons → How to rank higher* in every column. Repetition is what makes it scannable.
4. **Show, don't just tell:** mock screenshots of the actual interface (Google results, a ChatGPT answer), small icons, mini flows with arrows, a formula row (TIME × MONEY × LOCATION = FREEDOM), stat tiles, a "Without / With" comparison, a "types and when to use them" table, a "4 mistakes that kill your…" list.
5. **Dense but ordered.** Far more text than looks advisable; the grid does the work whitespace usually does. Don't sparsify.
6. **A footer strip:** photo, the offer, where to get it ("Download this high-res sheet from my newsletter… Join 400,000 people"). The image is the advert; what's behind the footer is the product.

**Comparison sheets (X vs Y vs Z) beat single-topic sheets**: they hand the reader a decision.

---

## Templates

All in `templates/` (copy with `d.css` and `logo.png`). Look at the matching `reference/` image before building.

| Template | Our version | Donnelly original / source | Use for |
|---|---|---|---|
| `versus.html` | Google Shopping vs ChatGPT vs Perplexity | SEO vs AEO vs GEO (his #1) | Comparing 3 channels, tools or approaches. **Default.** |
| `master.html` | How To Master AI Shopping | How To Master Claude Skills (#2) | A complete guide to one topic in 6 panels |
| `framework.html` | The "SHELF" Framework | The PLAY Framework | Named IP. **Reuse SHELF** so it gets known; new acronyms only for genuinely new methods |
| `layers.html` | 6 Layers Of AI Shopping | 6 Layers Of SEO In 2026 | An ordered process, foundation → payoff |
| `funnel.html` | The AI Shopping Funnel, Updated For 2027 | The Content Marketing Funnel (2,274 reactions, 344 reposts; his "pre-validated format" example) | Stages with "Where it happens / KPIs" left and "Strategy" right |
| `journey.html` | "ChatGPT doesn't send us any sales." The reality | "AI models aren't sending any traffic" | Rebutting an objection with a journey flowchart |
| `before-after.html` | Shopping Before AI vs After AI | Search Before AI / After AI | Showing how much the job has grown |
| `lead-magnet-cover.html` | The AI Shelf Playbook (3D book) | The LinkedIn GPT Operating System; Searchable's AI Search Ranking Guide | The image for a lead-magnet post |

**Formats seen but not yet templated** (build from the reference, then save as a template once Kelian approves):
- Hub ecosystem (`reference/donnelly-hub-ecosystem.jpg`)
- Venn + 4 cards with Focus on / Measured by (`reference/donnelly-venn-4-cards.jpg`)
- Puzzle "X, Y, Z Explained" (Searchable, 1,675 reactions, 266 reposts; `webinar/13`)
- Multi-acronym grid "8 ChatGPT Prompt Frameworks" (`webinar/11`)
- Centre stack with notes on both sides, "Executive's Guide To Types Of AI" (`webinar/10`)
- Carousel: PDF document posts. Not built yet; ask before making the first one.

---

## Workflow

1. Copy the template, `d.css` and `logo.png` into `GTM/linkedin/posts/<date>/sheets/`.
2. Write the content into the copy: keep the structure, change every word, follow the content rules.
3. Render:
   ```
   .claude/skills/cheatsheet-design/render.sh GTM/linkedin/posts/<date>/sheets <file>.html
   ```
   Output: `<name>.png` at 2400×3000 (LinkedIn 4:5) and `_preview/<name>.png`.
4. **Read the preview and fix it before showing Kelian.** Every first render so far needed one of these:
   - **Empty space at the bottom:** scale fonts and padding up 10–20%, give the main block a fixed height (`height:1150px`) or `flex:1`, or add one useful row ("What to track", "Power move").
   - **Overflow** into the CTA bar: trim pills to ~7 per row, then padding, then font size.
   - **Misplaced badges, arrows or 3D text** (absolute positions, mirrored text on rotated faces): adjust and re-render.
5. Send the PNGs with SendUserFile (`display: "render"`) and a short table: format, what it's based on, which to post first.

## Design system (`templates/d.css`)
- **Canvas** 1200×1500 CSS px at 2×. Faint vertical grid lines, off-white.
- **Headline:** DM Serif Display, centred, 60–84px, one phrase in *italic* blue on a pale blue block: `<h1>6 Layers Of <em>AI Shopping</em></h1>`. Optional caps kicker bar above.
- **Body:** Outfit 15–21px; caps section labels on tinted backgrounds.
- **Colour:** navy `#0b1b35`, blue `#2350c8`, six pastels with darker badge colours (`--y/--yb --l/--lb --p/--pb --m/--mb --b/--bb --o/--ob`). **Never Donnelly's green as the main colour.**
- **Pieces:** numbered square badges, ▶ tag pills, Start Here / Finish Here circles, dotted connectors, ▶ bullets, mock UI blocks.
- **Footer:** `.cta` bar (logo, one line, `Comment "CHECK"`) and the faint `KELIAN VAN TULDER` watermark. For Gabe, change the name (confirm his spelling).
- Fonts load from Google Fonts, so rendering needs internet.

---

## Content rules

Same as `linkedin-growth` and `skills/produkto-copy/SKILL.md`. In short:
- **E-commerce, product level, always.** Stores, product pages, catalogs, shoppers.
- **No unsourced numbers.** Donnelly's sheets are full of stats; we copy the structure, not the stats. Only use our own captured data or a named public source, with the source in small print.
- **Every block ends in an action** ("Do this today", "How to rank higher", "Power move", a fix).
- **No promised results**, no "nobody does X", no knocking competitors, no M&O Living, no scan recipe.
- **Made-up examples are labelled as made-up.** AI answers shown as real must be captured, with date.
- **"Case studies with numbers" are the top delivery item, but only with the client's permission** (Wild One, Stumptown, Partners Coffee: ask Kelian first).
- American spelling, plain words, no emoji in the copy (icons inside the graphic are fine).

### Writing with AI: be incredibly specific (slide 11)
Vague prompt, generic output. When drafting copy for a sheet or caption, write the brief to yourself first: **who it's for** (DTC founder, title, category), **the hook type** (challenge a common belief, a number, a named situation), **one concrete example** (a product, a buyer question), **the tone** (short sentences, plain language, Hemingway-simple, no clichés). Then draft.

---

## Pairing with a post

The sheet is the advert; the caption does the work. Write it with `linkedin-growth`, in Donnelly's sheet-caption shape:
- a 2-line hook that challenges a belief or names the reader's situation
- a numbered walk through the sheet, a "Do this today" per point
- a closing question
- sign-off "Let's keep building, Kelian"
- the offer in a **P.S.**
- links in the first comment, never in the post

## Capture: lead magnets and follow-up

**Lead-magnet posts get the most comments.** Searchable's examples (slide 13): "Comment AI SEARCH if you want the credits… Spaces are limited!" with a product video got **2,117 comments**. A 3D book "AI Search Ranking Guide" with a "+ FREE AI VISIBILITY AUDIT" badge got 921 comments. "SEO, GEO, AIO, AEO, SXO Explained" got 411 comments and 266 reposts.

Our version:
- **Comment keyword:** `Comment "CHECK"` → free check of their store (real, we run it). Scarcity ("I can do 10 this week") only if it's true.
- **Book-cover post** (`lead-magnet-cover.html`): **only advertise a playbook that exists.** "The AI Shelf Playbook" exists since 2026-10-19: `GTM/linkedin/lead-magnets/ai-shelf-playbook/The-AI-Shelf-Playbook.pdf` (18 pages: intro, 7 sheets each with a how-to page, scorecard, Produkto page). Edit the text in `build.py`, re-run it, then print to PDF (command in the folder's README). Post the cover with `Comment "PLAYBOOK"` and DM the PDF. When a new sheet is approved, add it as a chapter.
- **High-res sheet:** "Comment SHEET for the high-res version" works too (Donnelly's footer), but only once there's somewhere to send people.
- **Reply to every keyword comment the same day**, DM the deliverable, and ask one qualifying question (category, catalog size). That DM is where the demo gets booked.

**Nurture after capture (slide 12):** tag each lead by ICP (e.g. "Coffee, 200–1,000 SKUs"), then 4 emails: (1) personal story on the pain point, (2) deep education using our IP (SHELF), (3) a case study matched to their tag (client permission needed; until then a category Shelf Report), (4) a subtle offer with social proof → demo.

## Where this sits, and the time it should take
- **Donnelly's LinkedIn Revenue Engine (slide 01):** Positioning → **Content** → Compounding → **Capture** → Conversion. A sheet is Content; its CTA is Capture. A sheet without a CTA skips the step he calls the standard failure.
- **The 4-hour content system (slides 06–07):** 1h ideation, 1h writing, 1h design, 1h community engagement a week. It only fits in 4 hours with **a proven content system (this skill), AI (us) and delegation (Gabe's account).** Keep ideation and engagement human; this skill compresses writing and design.
- "Posting on LinkedIn" is ~90 tasks (slide 05). When Kelian feels behind, point at the 4 hours, not the 90.

## Housekeeping
- First set of sheets: `GTM/linkedin/posts/cheatsheets/v2/`. New ones go with their week's posts.
- When Kelian approves a new format: add the HTML to `templates/`, a preview to `reference/ours-*.png`, and a row to the template table.
- `render.sh` uses a throwaway Chrome profile and deletes it afterwards. Never point it at Kelian's real profile.
