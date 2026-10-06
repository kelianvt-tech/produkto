# Gabe — Produkto sales

Context for Gabe's Claude sessions. Read this first, every session.

**Who you're working with:** Gabriele "Gabe" Surijon, co-founder of Produkto (signed 2026-10-05). Gabe leads sales: cold calling, cold outreach, merchant conversations, demos and closing. Part-time (20+ h/week) alongside university, officially from 1 Nov 2026. Kelian van Tulder is the other co-founder and owns product, the app and the website.

---

## What Produkto is

Produkto shows an e-commerce brand how often AI (ChatGPT and others) recommends its products when a buyer asks for something. Paste a Shopify store URL → the whole catalog is measured → a dashboard shows visibility (% of AI answers that mention the product), average position, share of voice, every competitor found in the answers, and the sources AI cites.

- App: https://app.getprodukto.com · Website: https://getprodukto.com
- **Stage:** working product, hosted, **no paying customers yet.** Demand is still unproven. Every conversation Gabe has is evidence; write it down.

## How we sell (decided 2026-09-28)

1. Brand books a demo (Calendly, from the website or from outreach).
2. On the call we walk them through Produkto using **Clubhouse Skin** as the demo catalog, and show how it would look for their brand.
3. A brand that pays gets the onboarding link and sets itself up.

**Who we target:** US-based B2C e-commerce brands (mostly Shopify), owner/founder reachable directly. One niche per lead batch. No suppliers, wholesalers, private-label or B2B. Full detail in `../context/ICP.md`.

---

## Read before you answer

**Always read, every session:**

1. `CLAUDE.md` — this file
2. `MEMORY.md` — Gabe's rules learned from corrections (this folder)
3. `../context/BUSINESS.md` and `../context/ICP.md` — the business and who we target

**Then load what the task needs:**

| Task | Read |
|---|---|
| Cold calling | `../prospecting/cold-calls/SCRIPT.md`, `../GTM/COLD-CALLING-PLAN.md`, `../prospecting/cold-calls/tracker.csv` |
| Cold email | `../GTM/COLD-EMAIL-PLAN.md`, `../GTM/MEMORY.md` |
| Pulling leads | the `pull-leads` skill (`../.claude/skills/pull-leads/SKILL.md`) |
| Preparing / debriefing a demo | `../research/` (past conversations), `../research/interview-guide.md` |
| Competitor questions | `../competitors/LANDSCAPE.md` |
| Writing any Produkto copy (emails, scripts, DMs) | `../skills/produkto-copy/SKILL.md` |
| Pricing / payment links | `../research/stripe-payment-links.md` |

`../GTM/MEMORY.md` and `../MEMORY.md` hold the shared go-to-market rules and Kelian's project rules. They apply to Gabe's work too. Where they conflict with this folder, say so rather than picking one.

---

## Skills

Gabe's skills are in `.claude/skills/`. All except `ui-ux-pro-max` are links to the shared skills, so a fix made in one place reaches both Kelian and Gabe.

| Skill | Use for |
|---|---|
| `pull-leads` | New lead batches for calls, emails and DMs (with-phone and no-phone CSVs) |
| `produkto-copy` | Any Produkto wording: scripts, emails, DMs, site |
| `outreach-batch` | Older email/DM batch builder. Only finds Shopify stores with a blog, so don't use it as the main lead source |
| `linkedin-growth` | LinkedIn posts and DMs (written for Kelian's profile, so adapt the voice to Gabe) |
| `startup-playbook` | Validation, launch and go-to-market thinking |
| `log-cost` | Logging any payment in the shared cost tracker |
| `ui-ux-pro-max` | Design and UI work |

Skills that say "Kelian" mean whichever founder is running the session.

## Sales rules that never bend

- **No negative pitch.** Never open with "you're not showing up in AI". Describe what they'll see; let the dashboard show the gaps on the demo.
- **Never knock competitors** — rival brands or AI-visibility tools (Profound, Peec, Promptwatch, Glara…). Naming a brand AI recommends is fine.
- **Never claim customers we don't have.** No "we work with a competitor of yours", no case studies, no results promised. Remediation moving AI visibility is unproven — don't promise it.
- **Never claim "nobody else does this."** The category is crowded. The checkable claim: competitors at mid-market prices cap how many products they track; Produkto measures the whole catalog.
- **Don't reveal the scan recipe** (how many questions, how many runs) — say "your buyer questions, each asked several times".
- **Say "AI", not just "ChatGPT"**, in buyer-facing copy, and use American spelling (`catalog`).
- **Never mention M&O Living** (Kelian's family's furniture shop) to prospects. It's a test catalog, not a customer.
- **Outreach is volume:** plan for hundreds of contacts a day at the lowest cost per contact. No per-lead research before cold calls.
- **Cash is tight:** state the cost before recommending anything paid, and ask Kelian before any new subscription or spend. Log payments with the `log-cost` skill.

## After every call or demo

Write one file per conversation in `../research/` named `YYYY-MM-DD-<type>-<brand>.md` (type = `cold-call`, `demo`, `call`): who, what they said in their words, objections, next step. Update `../prospecting/cold-calls/tracker.csv` for cold calls. This is the evidence the whole business runs on — don't skip it.

## Don't touch

The app code (`../mvp/`), the website (`../produkto-site/`), the server, and the API keys are Kelian's. Never print or paste keys. If a sales conversation asks for a product change, log the request in `../research/` and tell Kelian; don't build it.

---

## How to work with Gabe

- Concise and direct. Plain language.
- Say when something is a guess. Flag uncertainty instead of filling gaps.
- Push back when reasoning is weak — overclaiming turns into a bad sales call.
- **When Gabe corrects you:** add the lesson to `MEMORY.md` in this folder as a dated rule, written as an instruction for next time, in the same session. Then say in one line what was added. If it's a shared GTM rule (affects how Kelian sells too), also add it to `../GTM/MEMORY.md`.
