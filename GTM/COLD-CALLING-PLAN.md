# Cold call playbook — Produkto

*Started 2026-09-29. One goal: book demos. A call never sells Produkto; it sells 20 minutes on Zoom.*

---

## 0. Goal and stack (decided 2026-09-29)

**One channel: cold calls. Goal: 150–250 dials a day** using a parallel dialler (several lines at once).

| Job | Tool | Price (checked 2026-09-29) |
|---|---|---|
| Find brands | Store Leads (free account first) | $0 to start |
| Founder name | Apollo free web app | $0 |
| Mobile numbers | BetterContact, charged only when found, 10 credits per mobile | Starter $15 = 200 credits (20 mobiles); Pro $49 = 1,000 credits (100 mobiles, ~$0.49 each) |
| CRM + US number + dialler | Close. Parallel dialling = Predictive Dialer, **Scale plan only** | Scale $149/mo monthly ($139 annual); US numbers ~$1/mo; calls ~$0.02/min |
| Cheaper alternative | Friend's parallel dialler + Close Essentials ($49) or Solo ($19) | ask friend |

**Volume maths:** 200 dials/day with max 3 attempts each ≈ 65 new prospects/day ≈ 1,300 mobiles/month ≈ 13,000 BetterContact credits. At full volume the phone numbers, not Close, are the big cost (price of the higher credit tiers not checked yet). Start at Pro (100 mobiles) for the test week.

**Test week before committing:** 100 mobiles, parallel dialling. Measure cost per number, pickup rate, conversations, demos booked.

## 1. The daily routine

| When (Barcelona) | US time | What |
|---|---|---|
| 10:00–12:00 | — | Prep tomorrow's 25 prospects (section 3) |
| 15:30–17:30 | 9:30–11:30 ET | **Call block 1**: East Coast |
| 18:30–20:00 | 9:30–11:00 PT | **Call block 2**: West Coast |
| 20:00–20:30 | — | Follow-up emails, update tracker |

**Target per day:** 150–250 dials. Conversation and demo rates are unknown until the test week.
Best days: Tue–Thu. Avoid Monday morning and Friday afternoon US time.

---

## 2. Who to call

Use the existing ICP (`context/ICP.md`): US Shopify DTC brands, 150+ SKUs (count variants), $1–10M, in a spec-driven category (skincare with actives, supplements, outdoor, tools, pet, baby, sleep).

**Skip:** anyone in `Research/sent-log-*.csv` who already got 2+ emails with no reply (fine to call people who got one email: say "I emailed you in August"), Yotpo customers, marketplace-only sellers.

**Who picks up:** at this size it's usually the founder, the ops/customer-service person, or voicemail. You want the founder or the head of ecommerce/marketing.

**Where the numbers come from** (flagging a real problem here: many DTC brands publish no phone number):
1. The store's Contact page, footer, `/policies/contact-information`, Google Business listing. Free.
2. LinkedIn → founder name, then ask the front line for them by name.
3. BetterContact for founders' mobiles (see section 0). This is the main source.

---

## 3. No per-prospect prep (decided 2026-09-29)

Cold calls run on volume. No ChatGPT checks, screenshots or research batches before dialling: most owners won't pick up or listen, so prep is wasted. Look at the homepage for 10 seconds while it rings, and that's it.

## 4. The script

**Superseded 2026-09-30: read from `prospecting/cold-calls/SCRIPT.md` on calls.** Sections 4–6 below are the earlier draft.

Keep it under 30 seconds before the first question. Speak slowly; you're calling from abroad, so own it.

**Gatekeeper / front line:**
> "Hi, this is Kelian — could you put me through to [founder name]? It's about how [Brand] shows up in ChatGPT's product recommendations. I've got something specific to show them."

If they ask for an email instead: get their direct address, send it (section 6), and note a callback date.

**Opener (decision-maker):**
> "Hi [Name], it's Kelian from Produkto. I know I'm calling out of the blue. Do you have 30 seconds, and then you can tell me if it's worth continuing?"

**The hook (generic):**
> "More shoppers now ask ChatGPT which product to buy, and it names two or three. We built a tool that shows which of your products it recommends, which competitors it picks instead, and tracks it daily across your whole catalog."

**The question (then stop talking):**
> "Is showing up in AI answers something you've looked at yet?"

**Ask for the meeting:**
> "I can show you in 20 minutes how your catalog reads to ChatGPT and which competitor products are winning. Would Thursday or Friday work?"

Book it in Calendly while you're still on the call. Send the invite before you hang up.

---

## 5. Objections

| They say | You say |
|---|---|
| "Not interested." | "Fair. Just so I know, is it that AI isn't a channel for you yet, or that it's not the timing?" *(their answer is research; log it)* |
| "Send me an email." | "Will do. What's the one thing that would make it worth opening?" Send the follow-up within 10 minutes. |
| "Our agency handles SEO." | "Makes sense. This is a different question from Google rankings. Happy to include them on the call." |
| "AI is tiny for us." | "It is for most brands, under 5% of traffic. It's growing fast though, and it's much cheaper to find out where you stand now than after a competitor owns the answer." |
| "How much?" | "From $99 a month. I'd rather show you the data first, so you can judge whether it's worth it." |
| "Can you fix it for us?" | **Write this down word for word.** It's the remediation question from `BUSINESS.md`. Say: "That's exactly what I want to talk about on the demo." |
| "Can you guarantee more sales?" | "No. Nobody can honestly guarantee that yet. What we give you is the measurement, so you can see whether changes move it." |

Never say "nobody else does this". Glara, Yotpo Discover, ReFiBuy and others exist.

---

## 6. Voicemail and follow-up

**Voicemail (under 20 s):**
> "Hi [Name], Kelian from Produkto. We show brands which of their products ChatGPT recommends, and who it picks instead. I'll drop you a short email. Speak soon."

**Follow-up email (same hour):**
> Subject: [Brand] in ChatGPT answers
>
> Hi [Name], I just tried calling. Produkto shows which of your products ChatGPT recommends when shoppers ask, and which competitors it picks instead.
>
> If you'd like to see how the rest of your catalog shows up, here's 20 minutes: [Calendly]
>
> Kelian

**Cadence per prospect:** call day 1 → email day 1 → call day 3 → call day 7 → stop. Max 3 dials.

---

## 7. Tracking

`prospecting/cold-calls/tracker.csv`, one row per prospect. Outcome codes:
`NA` no answer · `VM` voicemail · `GK` stuck at gatekeeper · `NI` not interested · `CB` callback set · `DEMO` booked · `BAD` wrong number/not ICP.

Every real conversation, even a "no", gets a short note in `research/<date>-call-<brand>.md`: what they said, which objection, what trigger they mentioned. Those notes are the actual output of this phase.

---

## 8. Legal (US) — read once

- Since 2021 (Facebook v. Duguid) most list-based diallers fall outside the federal TCPA autodialer definition, but some states (e.g. Florida, Oklahoma) are stricter for mobiles: skip or hand-dial those. Never use prerecorded messages.
- Rotate a few US numbers and register a caller name to avoid "Spam Likely" labels.
- Anyone who says "don't call again" goes on a do-not-call line in the tracker, permanently.
- Don't record calls without saying so. Some states (California, for example) require both parties' consent.

*I'm not a lawyer. This is the standard B2B baseline, not legal advice.*

---

## 9. When to stop and rethink

Set this now so you don't rationalise it later:

- **After 150 dials (≈ 6 call days):** fewer than 10 real conversations means the list or the numbers are bad. Fix sourcing, not the script.
- **After 30 conversations:** zero demos means the hook isn't landing. Rewrite section 4 using the objections you logged.
- **After 10 demos:** zero people asking for the onboarding link or price means pricing or product fit is wrong. That's the question that matters.
