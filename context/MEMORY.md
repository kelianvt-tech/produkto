# MEMORY.md

Rules learned from corrections. Append-only — never overwrite, never delete.

**How this file works:**

- Loaded into every session via `CLAUDE.md`.
- Read before every task, alongside the always-read files.
- When the owner corrects something, write the lesson here as a new rule, same session, before moving on.
- One rule per bullet. Written as an instruction, not a story. Dated.
- If a new rule contradicts an old one, keep both and mark the old one `SUPERSEDED (YYYY-MM-DD)` — the history of why a rule changed is worth more than a clean file.

---

## Rules

<!-- Format:
- **YYYY-MM-DD** — The rule, stated as an instruction. *(Trigger: what I got wrong.)*
-->

- **2026-08-03** — Keep memory in this file. When corrected, write the lesson here as a new rule before continuing the task. *(Trigger: file created.)*

- **2026-08-06** — Never audit or email a domain that wasn't confirmed from an authoritative link. Open any domain marked `GUESSED from name - VERIFY` before it enters outreach. *(Trigger: `enrich.py` resolved Avocado Green to `avocadogreenmattress.shop`, a full WooCommerce counterfeit clone of the real store — right brand name, right page title, wrong company. A single transient fetch failure on the real `.com` was enough to trigger the fallback. No content heuristic reliably tells a good clone from the original, so the only real defence is provenance.)*

- **2026-08-06** — When a lookup can't be resolved confidently, return nothing and mark it NOT FOUND. Don't fall back to a best-guess. *(Trigger: `store_from_episode` scored candidate hosts by link count with a brand-name bonus, so when no host matched the brand it silently returned the most-linked survivor — handing back `googletagmanager.com` as Prosperity Market's storefront. A confident wrong answer costs more than a blank, because nobody re-checks a filled-in field.)*

- **2026-08-06** — Pre-validation, the goal is **interviews, not qualified leads**. The only hard exclusion is Yotpo. SKU count and revenue order the queue; they never remove anyone from it. *(Trigger: I reported "29 qualified" from a 121-brand list by applying the 150-SKU floor as a gate. Kelian corrected it — he needs founders who will talk, and doesn't care about catalog size yet. Re-cutting on Yotpo-only took the pool from 29 to 90. `ICP.md` already said this in its own opening section and I read past it.)*

- **2026-08-06** — Never let a failure mode resolve to a pass. Make unknowns say "unknown". *(Trigger: `fetch()` truncated large `products.json` at 400KB, JSON parsing failed, the count returned None, and the status logic's `else` branch reported it as OK — so the biggest catalogs in the list looked qualified precisely because they were too big to measure. I reported 43 qualified brands to Kelian before catching it; the real figure was 29.)*

- **2026-08-10** — For interview/validation outreach, the primary output is the **reachable list** — every brand with a usable email or IG handle. Do not gate on SKU/Yotpo/category, and do not *lead with* triage framing ("N passed", "OK vs LOW SKU") either — that headline is itself the error. If a brand is reachable, it's on the interview list. *(Trigger: reinforces the 2026-08-06 interviews-not-leads rule, which I violated again — I headlined "21 passed triage" and tabled brands by exclusion status when Kelian only wanted people he can contact. He corrected it with "Again, I don't care about the SKU count." Applying the rule means the reachable count (75) is the headline, not the triage count.)*
