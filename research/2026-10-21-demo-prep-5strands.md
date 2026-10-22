# Demo prep: 5Strands (Ethan Steed, COO), 21 Oct 2026

Built from Karol's feedback on the 20 Oct mock demo (`2026-10-20-mock-demo-kll-digital.md`).

**Who:** Ethan Steed, COO, 5Strands Affordable Testing (affordableallergytest.com / 5strands.com). They sell at-home intolerance tests for pets and people. He came from the pet cold-email batch (8 Oct Apollo pull).

**Status:** Produkto has **no 5Strands store and no scan** (checked 21 Oct). You're showing Clubhouse Skin unless you run a 5Strands scan before the call.

---

## The call shape (about 30 min)

| Part | Time | Who talks | Goal |
|---|---|---|---|
| 1. Frame | 2 min | You | Why he should listen to you |
| 2. Discovery | 12 min (40%) | **Him, about 70%** | Find the problem and why it has to be fixed now |
| 3. Label it | 2 min | You | Say his problem back in his own words. He agrees. |
| 4. Pitch | **5 min max** | You, asking questions | Three steps, each tied to something he said |
| 5. Offer + close | 5 min | Both | Card on the call |
| 6. Objections | rest | Him | Dig until you hit the real one |

**Karol's main point: the sale happens in discovery, not in the demo.** If Ethan can't say what the problem is and why it matters now, he'll say "I need to think about it". A good dashboard doesn't change that.

---

## 1. Frame (keep it short)

- "Thanks for making time. Quick context on us: we track what ChatGPT, Google's AI and Perplexity say when people ask for products like yours, then we fix the product pages so AI can recommend them."
- Proof you can honestly use: the pet email already told him you work with **Wild One**. Don't add claims beyond that.
- Set the agenda so you're running the call: "I'll ask you a few questions about the business first, then show you only the parts that matter to you. Sound good?"

## 2. Discovery: questions to ask

Ask one, then **keep digging** ("What makes you say that?", "How long has that been going on?", "What did that cost you?"). Shut up and write down his exact words. You'll quote them back later.

**Why he's here**
1. "What made you take the call today?"
2. "When you read the email about AI recommending products, what went through your head?"

**Where sales come from today**
3. "Where do most of your customers come from right now: Google, Amazon, ads, vets, word of mouth?"
4. "What's working, and what's getting more expensive or slowing down?"
5. "Pets or people: which side of the business is bigger, and which one do you want to grow?"

**AI specifically**
6. "Have you ever asked ChatGPT for a pet food sensitivity test? What came up?" (If he hasn't, ask him to try it live. Strong move.)
7. "Are any customers telling you they found you through ChatGPT or AI?"
8. "Who do you see as your main competitors? Do you think AI recommends them over you?"
9. "Have you done anything for AI search yet: an agency, SEO, content? Why or why not?"

**Cost and urgency** (this is what turns interest into a sale)
10. "If more people start buying through AI and 5Strands isn't in the answer, what happens to the business in a year?"
11. "Why fix this now rather than in six months?"
12. "If we fixed this, what would that be worth to you?"

**Pet-specific risk to know before you go in (unverified, check it):** vets and mainstream sources often say hair or saliva intolerance tests are unreliable. So ChatGPT may not just leave 5Strands out of the answer, it may warn buyers off the whole product category. If that's what ChatGPT says, it's the sharpest problem you can show him. Run "best at-home food intolerance test for dogs" in ChatGPT before the call and screenshot what it says.

## 3. Label the problem

"So if I've got it right: [his words]. And it matters now because [his words]. Is that fair?" Don't move on until he says yes.

## 4. Pitch: 5 minutes, three steps, interactive

Each step: "You told me X → here's how we handle it → does that make sense?"

1. **See it.** Dashboard: which buyer questions he shows up in, who wins them, how often. (Clubhouse Skin unless you've scanned 5Strands.)
2. **Know what to fix.** Opportunities: specific questions he can win, and what's missing on his pages.
3. **Fix it.** The Catalog Optimization Agent rewrites product pages and writes AEO articles. He approves, it goes live on Shopify, and every month you measure what moved.

Show outcomes, not how it works. Only go deeper if he asks or comes across as technical.

## 5. Offer and close

- Price anchor: Growth is **$297/month**.
- Karol's advice: get a **card on the call**, even at a low amount, because if he pays, he pays attention. Something like: "Normally $297 a month. If you want to start today, the first month is [$X], basically what it costs us to run it, because we want to show you the trend moving."
- **Decide [$X] before the call** (Karol said $100 to $500 is fine), and set up a Stripe coupon for it on the Growth link. The app reads the plan from the price before discounts, so a coupon on Growth still creates a Growth account. Check the coupon field actually shows on checkout.
- Growth link: https://buy.stripe.com/aFaeVe0DC9lm9LY72w4ko01

## 6. Objections

**Anything that isn't paying is an objection, and they all come down to trust.** "I need to think about it" → "Sure. What specifically would you want to think through?" Keep asking until you get the real reason.

---

## Don't say

- **"Nobody else does this for e-commerce."** You said it in the mock and Karol pushed back. It's also false (Glara, ReFiBuy and others exist). Defensible version: others cap how many products they cover. Produkto covers the whole catalog.
- **"This is still in demo / not live yet / I finished it yesterday."** You said the first one in the mock. Gabe: don't tell them.
- **Any promise of more sales or a guaranteed visibility number.** Say what you do and how you'll measure it. Karol: you don't need to guarantee anything.
- **How many questions or runs a scan uses** (copy rule).
- **Negative digs** at him ("you're invisible") or at competitors' tools. Show the numbers and let them do the work.

## After the call

- Run `python3 research/import_wispr.py` and save the notes as `research/2026-10-21-demo-5strands.md`.
- If you have a Fathom-type recorder, record it. Karol: rewatch every call.

---

## Kelian's dashboard walkthrough (5–10 min, after Gabe's discovery)

Open first: https://app.getprodukto.com/?d=5strands.com (pre-loaded, opens instantly). **Don't change the date range or filters on the call**: a new view takes ~6 s to build.

Bridge in: "Gabe said you mentioned [his words]. Let me show you what that looks like for 5Strands right now."

1. **Headline: AI names 5Strands in about 15% of answers** (today's real scan). Ask: *"Is that more or less than you expected?"*
2. **Which questions they win and lose.** They only appear when the question practically describes their product ("tests 800+ foods", "checks 130+ vitamins"). On broad ones like "best at-home food intolerance test" or "best pet health test", AI names others. Ask: *"Which of these do your customers actually type?"*
3. **Who AI recommends instead:** Test My Food Sensitivity, Check My Body Health, Quest, Labcorp, EasyDNA. Ask: *"Are these the brands you lose to?"*
4. **One product, pet side:** Pet Nutritional Imbalance Test (Digital), 12%: app.getprodukto.com/r/SnssQWswLKajbPAP?product=172
5. **Opportunities:** top card, "What nutrition imbalance test can I get for under $70?": AI named a competitor in every answer and never 5Strands. Say "every answer", not the count (the count includes the generated days).
6. **The fix:** Catalog Optimization Agent → Product page fixes → open the Pet Food Intolerance card → flip "Now on your store" / "With this draft" on their real page. Ask: *"Is there anything on there that's wrong or that you'd never say?"* Don't drag it to Live (Shopify isn't connected, so the board refuses).
7. Hand back to Gabe for the offer.

**Avoid:** the "Recommended instead" panel on product pages (lists doctors and clinics), the Food Intolerance Test (Digital) product page (shows 0%), the agents' Results tabs (empty), and calling the 30-day trend his history. Only today is measured.
