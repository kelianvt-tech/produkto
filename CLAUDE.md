# AEO for ecommerce brands

Making ecommerce catalogs readable by AI, so a brand's individual products can be recommended when a buyer asks ChatGPT for something.

**Stage:** MVP built. Produkto — the scan-and-dashboard product in `mvp/` — works end to end: paste a Shopify URL, pick a product, run a scan, read the dashboard. The older audit tool in `build/` still works and is now the static-catalog half of the picture. No paying customers yet; demand still unproven.

---

## Read before you answer

**Always read these four, before any task, no exceptions:**

1. `CLAUDE.md` — this file
2. `context/BUSINESS.md` — what the business is, model, positioning
3. `context/ICP.md` — who we target and why
4. `00-BRIEF.md` — long-form background, research findings, kill criteria

Read them even for small tasks. This project has more unknowns than knowns, and answers given without the full picture tend to be confidently wrong.

Where `00-BRIEF.md` and the `context/` files disagree, **`context/` wins** — it is the newer version. Say so out loud when you notice a conflict rather than silently picking one.

**Then load what the specific task needs:**

| Task | Also read |
|---|---|
| Go-to-market (cold email, cold calling) | `GTM/MEMORY.md`, then the plan for that channel in `GTM/` |
| Competitive questions | `context/COMPETITORS.md` *(not written yet)* |
| Working on Produkto (the MVP) | `mvp/PLAN.md`, `mvp/app/README.md`, the newest dated file in `mvp/`, then the code |
| Working on the static audit tool | `build/README.md`, then the code |
| What we've learned from real catalogs | `METHODOLOGY.md` *(not written yet — this is the asset)* |
| Why a past decision was made | `DECISIONS.md` *(not written yet)* |

---

## Memory — you get smarter every week

Your memory lives in `MEMORY.md`, and this line loads it into every session along with this file:

@MEMORY.md

When I correct you, write the lesson into `MEMORY.md` as a new rule. Check it before every task. This is how you go from "good assistant" to "knows exactly how I like things done."

---

## Where things stand

**Built — Produkto (`mvp/`), the MVP, and the main artefact now.** Paste a Shopify URL → catalogue grid → pick a product → confirm the brand → edit the buyer questions → run a scan → dashboard with three tabs. A scan asks buyer questions against ChatGPT with web search on, several runs each, and reports how often the product gets mentioned, share of voice, average position, and the sources cited. Questions freeze at the first scan so the trend stays comparable. Real scans have run against the live OpenAI API. A Flask app on `localhost:8010`; the API key lives in `mvp/app/.env` and never gets printed or pasted anywhere.

**Built — `build/`, the static audit tool.** Point it at a Shopify store, it crawls product pages and scores whether the catalog states the attributes buyers actually ask about. Two scores: spec-query retrievability (the one that matters) and schema completeness (plumbing). Output goes to `audits/<store>/<timestamp>.{json,md}`, never overwritten, so re-runs produce a diff. It measures the catalog; Produkto measures what the model says. Both matter, and they answer different questions.

**Measured:** M&O Living (a test catalog — Barcelona DTC furniture, no formal relationship with us) — 86 products, **16.8/100** spec-query retrievability. Six attributes buyers search on appear on **zero** products: care instructions, indoor/outdoor suitability, removable covers, load capacity, assembly requirement, fabric durability.

**Known about cost:** a scan bills roughly $5–6 at current settings, and cost scales with how many buyer questions a catalog competes on, not with SKU count — so it barely moves between 86 and 2,000 products. See `mvp/ALL-HANDS-COST-2026-09-19.md` before quoting any per-product number.

**Not proven, and these are the real risks:**
1. That mid-market DTC brands care enough to pay. No customers, and the conversations are still thin.
2. That remediation actually moves AI visibility. Nobody has demonstrated this — not us, not the funded competitors. Produkto can now measure whether it does; that is the point of having built it.
3. That the ROI works today rather than in two years.

---

## Current priority

**Getting Produkto in front of brands through demos.** The product is good enough to show.

The sales motion (decided 2026-09-28, see `DECISIONS.md`):
1. Brands book a demo on the website (Calendly).
2. On the call, Kelian walks them through Produkto using **Clubhouse Skin** as the demo catalog and shows how it would look for their brand.
3. A brand that pays gets the **onboarding link** and sets itself up (brand name, store website, onboarding steps), then uses the dashboard itself.

- Record every demo and conversation in `research/`, one file per conversation
- Build only what a real conversation asks for — plus what step 3 needs before the first paying customer (below)

---

## Direction of travel

Manual service now → methodology accumulates → agent later.

The agent is the destination and it's what makes this scale. But it's only worth building once we know **which fixes actually move visibility**, and that's the open question in the whole market. The manual work is how we find out. Everything learned from a real catalog goes into `METHODOLOGY.md` — that file is the only genuinely proprietary asset here.

---

## Out of scope right now

No write access to anyone's store, except the content agent's Shopify publishing (decided 2026-10-15, see `DECISIONS.md`): merchant-approved drafts only, with undo. Building the agent before knowing which fixes actually move visibility means automating a guess.

**Required before the first paying customer gets the onboarding link** (2026-09-28): hosting (the app runs on a laptop at `localhost:8010`), accounts so each customer sees only their own store, and daily scans that don't depend on Kelian's Mac being awake. Until someone pays, Produkto stays a local tool Kelian demos from.

---

## Folder structure

```
CLAUDE.md          this file — entry point                    ALWAYS READ
MEMORY.md          append-only rules from corrections        @-IMPORTED ABOVE
00-BRIEF.md        long-form background, superseded by context/  ALWAYS READ
METHODOLOGY.md     what we've learned about what actually works  (to write)
DECISIONS.md       append-only log: decision, date, why, what would reverse it  (to write)
context/
  BUSINESS.md      what the business is, model, positioning     ALWAYS READ
  ICP.md           who we target, and why the filters are loose  ALWAYS READ
  COMPETITORS.md   the landscape  (to write)
research/          interview notes, one file per conversation
audits/            reports, one folder per brand, never overwritten
competitors/       trial notes, screenshots, pricing
build/             the static catalog audit tool
mvp/               Produkto — the MVP: app, server, design reviews, cost and QA notes
  PLAN.md          what the MVP is meant to be
  app/             the Flask app and its README
  MEMORY.md        MVP-specific rules, separate from the project MEMORY.md
produkto-site/     the marketing site
prospecting/       outreach lists and research on target brands
GTM/               go-to-market: COLD-EMAIL-PLAN.md, COLD-CALLING-PLAN.md, MEMORY.md
```

Two kinds of file, and don't mix them: **current-state** files get overwritten (`BUSINESS.md`, `ICP.md`), **logs** only get appended (`DECISIONS.md`, `MEMORY.md`, `research/`).

---

## How to work with the owner

- Non-technical but capable. Explain what code does in plain language; don't leave jargon unexplained.
- Prefer Python, minimal dependencies, standard library where possible.
- Say when something is a guess. This project has more unknowns than knowns and pretending otherwise is worse than useless.
- Push back when the reasoning is weak. Overclaiming here turns into a bad sales call later.
- Don't claim "nobody does this for ecommerce" — Yotpo Discover and Goodie both do. The defensible claim is narrower: nobody does catalog-scale remediation for mid-market DTC with a human accountable for the result.

**When the owner corrects you:** write the lesson into `MEMORY.md` as a new rule, in the same session, before continuing the task. Don't wait to be asked. State the rule as an instruction for next time, not as an apology for this time. Then say in one line what was added. See the Memory section above.
