# Cold email sequence, v3 (DRAFT, not approved)

Written 2026-10-08 from the Hormozi/Instantly video (youtube.com/watch?v=j5uPj9A7zlE). Changes from v2 and the pet emails:

- Subject line names the product AI recommended (Hormozi's "calling about Burger King" open loop). This is naming, not knocking, so it fits the no-negative-pitch rule.
- The offer is a free thing they know costs money, a snapshot of their own products, instead of "a 15–20 minute demo". The demo becomes the way they get it.
- Shorter, plainer words (target: under 70 words, grade 3–5 reading level).
- One niche per batch only. Every `{field}` must be filled from a real capture, or the brand is dropped.

## Email 1: day 0

**Subject:** {competitor_product}

Hi {first_name},

I asked ChatGPT "{buyer_question}" today. It picked the {competitor_product}.

I run Produkto. We show which of your products AI picks, and who it picks instead.

[Pet batches only:] I currently work with pet e-commerce and DTC brands such as Wild One. For Wild One, AI picked their products in 23% of the answers we checked.

Want a free check of {company}? I'll show you the results in a 15-20 minute demo.

Kelian van Tulder
Founder, Produkto

## Email 2: day 3, same thread

Hi {first_name},

Same offer: a free check of how AI picks your products, shown to you in a 15-20 minute demo. It covers your whole catalog, not just the bestsellers.

Should I set it up for {company}?

Kelian van Tulder
Founder, Produkto

## Email 3: day 8, same thread

Hi {first_name},

Last one from me. If you'd like the free check later, just reply "yes" and I'll run it.

Kelian van Tulder
Founder, Produkto

---

## Signature

Every email ends with "Kelian van Tulder / Founder, Produkto", in plain text with no logo or links. From 12 Oct, once warm-up is done, add the LinkedIn URL as plain text (test it on half the email 1 sends first).

## Open questions for Kelian

1. Is a free check per reply affordable? We only run one when someone says yes. Check the cost in `mvp/app/config.py` before agreeing to it.
2. Wild One: 23% (Kelian, 2026-10-08). Check Wild One is OK with the figure being quoted.
3. The mixed 665 batch has no niche, so this email can't be written for it. Should we split it by niche (and run one compare.py question per niche) or leave it unsent?
