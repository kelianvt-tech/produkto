# Cold email sequence, v1

Written 2026-10-02; Kelian's edits applied the same day (approved v1). Three emails, same thread, plain text, no links or images in email 1, open and link tracking off. Fields in {braces} come from `compare.py`. If any field is empty, that brand isn't sent to.

**Niches for the first sends**

| Niche | Buyer question (price filled from their own best-seller) |
|---|---|
| Scented candles | What's the best scented candle to buy online for around ${price}? |
| Running shoes | What's the best running shoe for everyday training for around ${price}? |

Both are new (not used in batches 1–4) and both already show up in our lead pulls.

---

## Email 1: day 0

**Subject (A):** {hero_product} on ChatGPT
**Subject (B):** a ChatGPT question

Hi {first_name},

I asked ChatGPT "{buyer_question}" today. One of the products it recommended was {competitor_product}, made by {competitor_brand}, another brand in your category.

I thought you'd want to see how AI picks between products like your {hero_product}.

I run Produkto. It shows which of your products different AI models recommend, for which buyer questions, across your whole catalog.

Would you be open to a 15-20-minute demo?

Kelian

*(~70 words.)*

---

## Email 2: day 3, reply in thread

Hi {first_name},

The question I asked is one of many your buyers type in. In the demo I'd show you the full picture for a real brand's catalog: which products get named, for which questions, and next to which competitors.

Worth 20 minutes this week or next?

Kelian

---

## Email 3: day 8, reply in thread

Hi {first_name},

I'll leave it here. If AI recommendations become something you want to look at, you can reply to this and I'll send you a time :)

Kelian

---

## What I checked against the rules
- Positive: never says they're missing or not ranking. It names what AI recommended and lets them draw the conclusion.
- No knocking anyone: the competitor is named, not criticised.
- The comparison is a real ChatGPT answer captured that day. Brands ChatGPT already recommends are dropped.
- No promise of results, no count of questions or runs, no "nobody does this".
- Ask is "Book a demo" in spirit; no Calendly link in email 1 (deliverability). Link goes in the reply when they say yes.

**Rule (2026-10-08):** the buyer question must not contain a word from the competitor's brand name (Sophie's Pet Food read "small-batch … SmallBatch" as a mix-up and replied "Wrong company, wrong product").
