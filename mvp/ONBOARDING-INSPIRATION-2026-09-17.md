# What to take from Promptwatch's onboarding

**Written:** 17 September 2026, from 9 screenshots of Promptwatch's signup flow (`~/Desktop/Onboarding promptwatch/`).
**Status:** proposal only. Nothing has been built or changed.

---

## What their flow actually is

Five steps, shown as five dots at the top:

| # | Step | What it asks |
|---|---|---|
| 1 | **Welcome** | Company name, website, Brand vs Agency, target country, tracking language |
| 2 | **About you** | First name, last name, "How did you hear about us?" |
| 3 | **Brand Hub** | Reads your website, then shows editable fields: brand aliases, short description, industry, tone of voice, long description, ~10 key features, and a buyer persona (name, description, age range, education, gender) |
| 4 | **Competitors** | 8 competitors pre-filled with logos and URLs, editable, "list at least 5" |
| 5 | **Prompts to Monitor** | Pre-written questions, each tagged (Brand Specific + Navigational / Informational / Transactional), "list at least 3" |

Down the right side of every step, never changing: a G2 rating, the one-line pitch, three ticks, "Join 1,840+ brands and agencies", rotating customer logos, and two named testimonials. Bottom bar: Back / Next, a chat bubble, "Wrong account? Logout".

---

## The five ideas worth stealing

### 1. The AI fills it in; the user only corrects it
Their Brand Hub is not a form to complete. It shows "Analyzing your website" with a progress bar, then comes back with everything already written: description, industry, features, persona. The user's job is to correct, not to compose. Every field also says *why* it's asked, e.g. aliases "help improve detection accuracy".

**For us:** we already do this for the buyer questions. The same move would fit a short confirm step after the catalogue loads.

### 2. Brand aliases — our single highest-value steal
They ask for alternative names and spellings for the brand, and say plainly that it improves detection.

**Why this matters more for us than for them:** deciding whether a ChatGPT mention *is* your product is the riskiest part of our tool, and it currently guesses aliases from the domain and the Shopify vendor field. One text box would let a merchant fix that themselves. It's also the cheapest thing on this list to build.

### 3. Tagged questions
Each prompt carries a type. It tells the user at a glance that the set covers different buyer situations rather than five versions of the same question.

**For us:** our generator already writes to different angles (a "best X" question, a budget question, a specific need, a use case, a comparison). We just don't show it. Tagging our five would make the set look deliberate, and would expose a weak set immediately (e.g. five near-identical questions).

### 4. Let people edit the questions before they lock
They can delete and add prompts. Ours are generated, shown, and then frozen at the first scan with no way to remove a bad one.

**For us:** the "around 39" question would have been caught by the merchant in two seconds. The currency fix is in, but the general point stands: one bad question wastes a fifth of every future scan, permanently. Editing must happen before the freeze, and the freeze must be explained on screen.

### 5. Naming what the machine is doing while you wait
"Analyzing your website" with a bar, then "Loading your brand information". It's a progress bar with a job title attached.

**For us:** your new scanning screen already does this ("Checking for visibility…"). The catalogue fetch and the question writing could use the same treatment.

---

## What NOT to copy

- **The testimonials, logo wall and G2 badge.** You have zero customers. Anything in that slot would be invented, and this is exactly the thing your own rules say not to fake. Leave the space for something true (see below).
- **Step 2, "About you".** Names and a referral dropdown serve their CRM, not the user. Our flow has no accounts at all, which is a genuine advantage: paste a URL and go.
- **Brand vs Agency, tone of voice, persona fields.** These exist because they write content for you. We measure one product. None of it would change a single number on our dashboard.
- **The length.** Their Brand Hub is a long scroll of ten-plus fields before anyone sees a result. Our whole appeal is three clicks to an answer. Copying the depth would throw that away.
- **Asking for competitors up front.** Ours are discovered from what ChatGPT actually recommends, which is better evidence than a merchant's own guess, and it's a genuine talking point. At most, ask afterwards: "who did you expect to see here?"

---

## Proposed changes to our onboarding

Our flow today: paste URL → product grid → pick product → questions appear → Run insights → dashboard.

| Priority | Change | Effort | Why |
|---|---|---|---|
| **1** | **"Anything else you're called?"** — one aliases box on the product step, pre-filled with the brand name we detected, feeding the matching rules | Small | Directly improves the number most likely to be wrong |
| **2** | **Edit the questions before the first scan** — delete, edit, add one, with "these lock when you run your first scan" stated on screen | Small | Stops a bad question being baked in forever |
| **3** | **Tag each question** (budget / spec / use case / comparison / best-in-category) | Small | Makes the set look deliberate; exposes a weak set |
| **4** | **Step indicator** — three dots: Store → Product → Questions | Small | Sets the expectation that this is short |
| **5** | **Confirm what we detected** — brand, country and currency ("Asking as a shopper in the UK · £"), each editable | Medium | We read these automatically now; showing them builds trust and catches a wrong read |
| **6** | **Use the right-hand space honestly** — what you're about to get (the four panels), and what a scan is, instead of borrowed credibility | Medium | Fills the same slot without inventing proof |
| **7** | **"Who did you expect to see?"** after the first dashboard | Medium | Their competitor step, moved to where it's a finding rather than a chore — and a genuinely useful sales question |

---

## One honest caveat

Promptwatch onboards a brand; we onboard one product. Their flow spends five steps collecting what their content agent needs to write for you. Ours only needs a URL and a product, and everything else is measured rather than declared. Every idea above should be judged against that: does it make the measurement more accurate, or is it just more form?

By that test, items 1–4 earn their place. Items 5–7 are worth doing, but only after the automatic scans, which are still the thing standing between this and a first user.
