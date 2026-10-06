# Cold email plan

Written 2026-10-02. Assumes payday is **Tuesday 6 October 2026**. Prices are approximate, quoted from memory: check before buying.

**Goal:** about 350 cold emails a day to US e-commerce brands. Each email opens with one real, positive product comparison from an AI answer, and the only ask is to book a demo.

**Hard rules**
- Never send cold email from getprodukto.com. Use lookalike domains only.
- No negative pitch ("you don't show up"), and no knocking competitors or rival tools.
- The comparison line must come from a real AI answer captured that day, never guessed. Drop any brand that AI already recommends.
- Verify every address before it's sent to. Keep bounces under 2%.

---

## Before payday ($0)

**Fri 2 – Sun 4 Oct**
- **Claude:** rewrite the cold email as a 3-email sequence: a positive comparison opening, then two short follow-ups. Pick 2 new niches and write one buyer question for each.
- **Claude:** build the comparison script: one-niche lead batch → each brand's best-seller → ONE ChatGPT question for the whole batch via Apify → one competitor product used in every email. Test it on 5 brands (a few cents of existing Apify credit).
- **Kelian:** read and approve the copy (~20 min).

**Mon 5 Oct**
- **Kelian:** cold calls start, as already planned.
- **Claude:** finish the script and drop brands that AI already recommends.

## Payday

**Tue 6 Oct: buy everything (~$190)**

| Item | Cost |
|---|---|
| 4 lookalike domains (Namecheap) | ~$45 |
| Instantly **Hyper Growth** (Growth's 1,000-contact cap is too small) | $97/mo |
| ~10 pre-warmed inboxes | ~$40–50/mo |
| MillionVerifier credits | ~$20 |
| Apify leads, ~5,000 raw | ~$10–25 |

- **Kelian:** buy the above. Point each domain's website at getprodukto.com.
- **Claude:** pull the first 5,000 leads (`pull-leads` skill).

**Wed 7 Oct: connect**
- Inboxes usually arrive within 1–3 days (vendor estimate).
- **Together:** add SPF, DKIM and DMARC for each domain in Namecheap, then connect each inbox to Instantly with warm-up on.
- **Claude:** verify all leads, then run the comparison on the first 1,000.

**Thu 8 Oct: test**
- **Claude:** load the campaign into Instantly.
- **Kelian:** send test emails to your own Gmail and check they land in the inbox, not spam or Promotions.

**Fri 9 Oct: first live send, ~150.** Even pre-warmed inboxes step up over a few days.

## Ramp up and run

**Mon 12 – Fri 16 Oct:** ~250 a day, then ~350 a day from Wednesday.
- **Kelian, daily (30 min):** answer replies in Instantly and book demos into Calendly.
- **Claude, twice a week:** run the comparison on the next 1,000 leads.

**From Mon 19 Oct:** full volume, ~350 a day (~1,700 a week).
- **Claude, every Monday:** pull and verify a fresh lead batch. Report sent, bounce rate, replies and demos booked.

**Checkpoint, about Mon 2 Nov** (≈2,000 sent): fewer than ~4 demos booked means the copy or offer isn't working. Pause, rewrite, then resume.

## Learning loop: improve every week

The first 5,000–10,000 emails will mostly teach us, not sell. The setup below makes sure every send leaves usable data.

### 1. Log every email with its ingredients
`GTM/cold-email-log.csv`, one row per email sent, written by the comparison script when it builds the email:

`send_date, brand, domain, founder_first_name, niche, hero_product, buyer_question, comparison_line, ai_engine, variant_id, subject_variant, opener_variant, cta_variant, sequence_step, sending_inbox`

Outcomes are joined from the Instantly export each Monday: `bounced, replied, reply_type, demo_booked, paid`.
`reply_type` is one of: positive, curious, not now, not interested, wrong person, unsubscribe, auto-reply. Claude classifies; Kelian corrects any he disagrees with.

### 2. Measure the right thing
- **Main number: positive replies per 1,000 sent.** Then demos per 1,000.
- **Opens are ignored, and open tracking is switched off.** Apple Mail fakes opens, and the tracking pixel hurts inbox placement. Link tracking off too.
- Bounces and spam-folder tests are health checks, not results. Over 2% bounce on any inbox: pause that inbox.

### 3. Test one thing at a time, and be honest about noise
- At ~1% reply rates, a variant needs **~1,000 sends** before a difference is real. With ~1,700 a week, that means **two variants per week, one variable changed**.
- Order to test (biggest effect first): who we email (niche) → subject line → opening comparison wording → ask (CTA) → follow-up timing.
- A gap smaller than about 2x after one week is noise. Keep running it; don't call a winner.

### 4. The Monday review (Claude, ~15 min of Kelian's time)
1. Export from Instantly, join to the log, write `GTM/reviews/<date>.md`: sends, bounce, replies by type, demos, each variant side by side, and results by niche.
2. Kelian reads **every positive and every "not interested"-with-a-reason reply** quoted in the review. Their own words are the best copy input there is.
3. **One decision per week**: keep the winner, write the next challenger. Log it as a dated line in `GTM/MEMORY.md` with the numbers behind it.

### 5. Make each email read as one-to-one
The personalisation is the real AI answer, not mail-merge decoration.
- **Line 1 is about their product**: their best-seller, named, and the real comparison captured that day for one buyer question in their niche. That can't be faked in bulk, and the reader can tell.
- **Sounds like a person typed it**: plain text, no images, no links in email 1, under ~90 words, sent from a first name, lowercase-style subject (2–4 words).
- **No invented facts.** Every specific detail must come from their store or the captured answer. If the script can't fill a field, the brand is dropped, not sent a generic version.
- **Follow-ups reply in the same thread** and say something new about what the demo shows, never "just bumping this". No extra AI questions: one question per batch.
- **Replies get a human answer within a working day**, by Kelian, not a template.
- Spot-check 10 random emails from each batch before it loads. If one looks wrong (bad product, odd first name, wrong niche), fix the script before sending the rest.

## Money

- **Tue 6 Oct:** ~$190 in one go.
- **Then about $150–170/month:** Instantly, inboxes, leads, verification and comparisons. That's roughly 5 cents per brand contacted.
- **Break-even each month:** one $297 customer, or two $99 customers.

### Cash flow model, Oct–Dec (industry rules of thumb, not our data)

Our only real data is 0 replies from 100 emails (batches 1–4, old copy). Assumes ~2,000 brands contacted in Oct and ~3,000 a month in Nov and Dec, a 70/30 mix of $99 and $297 plans, and 2–4 weeks from first email to payment. Churn and Stripe fees are not included.

| | Oct | Nov | Dec | 3-month total |
|---|---|---|---|---|
| Costs | −$215 | −$170 | −$170 | −$555 |
| Pessimistic revenue (1 demo per 1,000 emails, 10% close) | $0 | $0 | ~$100 | ≈ −$455 |
| Base revenue (3 demos per 1,000, 15% close) | $0 | ~$250 | ~$500 | ≈ +$200 |
| Optimistic revenue (6 demos per 1,000, 25% close) | ~$300 | ~$1,000 | ~$1,700 | ≈ +$2,450 |

## Blockers to clear in parallel
1. Stripe payment links are blocked until ID verification clears.
2. Each customer needs their own login before getting the onboarding link.

## Already done
- 2026-10-02: kelian@getprodukto.com is live on Google Workspace (SPF, DKIM and DMARC all set). It's for demos and customers only, never cold email.
- 2026-10-02: payday came early. Bought 3 sending domains (not 4): **tryprodukto.com, useprodukto.com, produktohq.com** (Namecheap). Plan: 3 inboxes per domain, 9 in total, ~315–350 emails a day.
- 2026-10-02: Instantly prices checked on screen: Growth $47/mo (1,000 contacts, 5,000 emails); **Hyper Growth $97/mo** (25,000 contacts, 125,000 emails, A/Z testing, Unibox) is the plan to buy. Free trial runs to 16 Oct (250 contacts, 1,250 emails): use it for the first 250-brand batch, upgrade before scaling. Monthly running cost is now ~$180–210, not $120–150.
- 2026-10-02: Instantly's pre-warmed inboxes are **sold out**, and its DFY/AirMail inboxes only work on domains bought through Instantly. Recommended instead: **Zapmail Workspaces Starter, $39/mo for 10 Google mailboxes** on our three domains (DNS set up automatically, connects to Instantly). New inboxes need ~2–3 weeks of warm-up, so full volume moves to ~19–23 Oct and October drops to ~1,500–2,500 emails. Optional: Zapmail pre-warmed Starter (3 mailboxes, $39 first month, $24/mo after) to send ~100/day from next week. Prices from comparison blogs, 2026-10-02; confirm at checkout.
- 2026-10-02 **(current plan, supersedes the timeline and money sections above):** budget is tight (~€300 for everything). Buy **Zapmail Workspaces Starter only ($39/mo, 10 inboxes)**, no pre-warmed extra. Warm-up starts ~3 Oct on Instantly's free trial. Sending ramps: ~50–100/day wk of 12 Oct, ~200–250/day wk of 19 Oct, ~300–350/day from 26 Oct. **October ≈ 2,800–3,500 emails (~1,100–1,400 brands)**. Instantly Growth ($47) on ~14 Oct; its 1,000-contact cap is likely hit in the last week of October, so expect to move to Hyper Growth ($97) around 26 Oct–2 Nov. **November ≈ 6,000–7,000 emails (~2,500–3,000 brands), costing ~$170–200 (Zapmail $39, Instantly Hyper Growth $97, leads $15–30, verification $20–30).**
- 2026-10-02: **Zapmail Starter bought and active** (10 mailboxes, $39/mo, renews 2 Nov; account kelian@getprodukto.com after a signup typo was fixed by support). The 3 domains are added to Zapmail, and their Namecheap nameservers now point to Zapmail (pns61–64.cloudns). The Namecheap redirects to getprodukto.com no longer apply; set forwarding again inside Zapmail. Next: create the 10 mailboxes (4/3/3) once Zapmail shows the domains connected, then export them to Instantly and turn warm-up on.
- 2026-10-02: **10 Zapmail inboxes created**, display name Kelian van Tulder, no AI profile pictures: kelian@, kelian.v@, k.vantulder@ on all three domains, plus kelianv@tryprodukto.com. Status "In Progress" (Zapmail says up to ~3 hours to activate). Next: export to Instantly, turn warm-up on, set domain forwarding to getprodukto.com in Zapmail.
- 2026-10-02: **Instantly Growth bought ($47/mo)** on 2 Oct instead of ~14 Oct: the free trial only allows 2 email accounts, and Zapmail's export requires a paid Instantly plan. Supersedes the 12–16 Oct upgrade reminder; the calendar check is now 26 Oct (Hyper Growth if near Growth's 1,000-contact cap). Zapmail export to Instantly started 2 Oct ~19:50 with Zapmail-recommended warm-up settings.
- 2026-10-02 ~20:10: **all 10 inboxes are in Instantly and warm-up is ON** (standard warm-up pool, daily send limit 30 each). Warm-up clock starts today: small real sends ~week of 12 Oct, full volume ~26 Oct. Domain forwarding to https://getprodukto.com set in Zapmail (Update Settings) for all three domains, waiting to go live.
- 2026-10-02 **PENDING (do when the other session's website edits are finished):** the 3 sending domains are added to Netlify (site dapper-cascaron-576cec) as aliases, "Pending DNS verification". To finish: (1) add `produkto-site/dist/_redirects` with `https://tryprodukto.com/* https://getprodukto.com/:splat 301!` (same for useprodukto.com, produktohq.com, and their www.), (2) deploy dist together with the other session's changes (local index.html/pricing.html differ from live as of 18:25), (3) in Zapmail DNS point each domain's @ A record to 75.2.60.5 and www CNAME to dapper-cascaron-576cec.netlify.app (leave MX/SPF/DKIM/DMARC untouched), (4) remove Zapmail's domain forwarding. Until then the domains use Zapmail's forwarding, which shows an hCaptcha page first. Doesn't affect warm-up or sending.
- 2026-10-02 ~21:15: **DONE — sending-domain redirects are live.** Website redeployed (only change: new `_redirects`; local files matched live). Zapmail forwarding removed; Zapmail DNS now has @ A 75.2.60.5 and www CNAME dapper-cascaron-576cec.netlify.app on all three; MX/SPF/DKIM checked intact. Netlify aliases verified and certificate renewed. https://tryprodukto.com, useprodukto.com, produktohq.com all 301 → https://getprodukto.com. The www. versions don't work over HTTPS (not added as Netlify aliases); low priority. Supersedes the PENDING line above.
- 2026-10-02 ~22:05: www. versions added as Netlify aliases and certificate renewed. All six addresses (with and without www) 301 → https://getprodukto.com.
- 2026-10-05 **(current timeline, supersedes first sends "week of 12 Oct"):** soft start **Wed 7 Oct at ~3 cold emails/inbox/day (~30/day total)**, warm-up kept on. Stop rule: pause if any inbox health < ~95% or bounce rate > 2%. Ramp from ~12 Oct to the 19 Oct / 26 Oct volumes above. Needs by Tue 6 Oct: candle leads pulled, verified, comparison run, new copy approved.
