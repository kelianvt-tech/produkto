# GTM session summary — Friday 2 October 2026

What was set up today for cold email and cold calls, what it cost, and the plan for the week of 5 October.

---

## What we did

### Cold email: plan and copy
- **3-email sequence** written and approved, with Kelian's edits (`cold-email/SEQUENCE.md`).
- **Comparison script** (`cold-email/compare.py`): one-niche lead batch → each brand's best-seller → **one ChatGPT question per batch** → one competitor product used in every email. Cleans up product names and skips wrong products (accessories, look-alikes). Tested on 5 candle/shoe stores (~3 cents).
- **Weekly learning loop** added to `COLD-EMAIL-PLAN.md`: log every email, judge results by positive replies per 1,000 sent (opens ignored), test one change a week, one decision each Monday.
- **First niche: scented candles.** Lead search ready (`cold-email/batch1-candles-leads-input.json`), not run yet.

### Cold email: sending setup
- **3 sending domains** bought at Namecheap: tryprodukto.com, useprodukto.com, produktohq.com. Never send cold email from getprodukto.com.
- **Zapmail Starter** bought; support fixed a sign-up typo (getproducto → getprodukto).
- **10 inboxes** created as Kelian van Tulder: kelian@, kelian.v@, k.vantulder@ on all three domains, plus kelianv@tryprodukto.com. SPF, DKIM, DMARC and MX all live.
- **Instantly Growth** bought (the free trial only allows 2 inboxes). All 10 inboxes exported to Instantly, **warm-up ON** for every one.
- **Sending domains redirect to getprodukto.com** via Netlify (done late evening, 2 Oct). Zapmail's own forwarding showed a captcha page first, so it was removed. Instead:
  - website redeployed with a `_redirects` rule (`produkto-site/dist/_redirects`); local files matched live, so nothing else changed;
  - all six addresses (each domain with and without www) added as Netlify aliases, with the certificate renewed to cover them;
  - Zapmail DNS for each domain: `@` A record → 75.2.60.5, `www` CNAME → dapper-cascaron-576cec.netlify.app. MX, SPF and DKIM checked intact afterwards.
  - Result: all six addresses 301 → https://getprodukto.com.

### Cold calls
- **Twilio** upgraded, compliance profile complete, **US number bought: (984) 360-8788** (Raleigh, NC). Connected to the dialer on the server (replaced the old +49 trial number); dialer healthy.
- **SHAKEN/STIR skipped**: it needs a registered business. Do it once registered as autónomo. Until then keep to ~80–100 dials a day per number.

### Other
- Ben (Clubhouse Skin) asked for a screenshot: took a 7-day dashboard screenshot (`research/ben-clubhouse/`) and drafted the reply asking for a weekend demo. Not confirmed sent.
- **Stripe payment links** created (Starter $99, Growth $297, both USD), checkout branded with Produkto logo and colours. Links in `research/stripe-payment-links.md`.
- **Calendar:** Mon 26 Oct, 10:00, check Instantly's 1,000-contact limit; move to Hyper Growth ($97) if near it.

---

## What we paid today

| Item | Cost |
|---|---|
| 3 domains (Namecheap) | ~$33 (estimate; check receipt) |
| Zapmail, 10 inboxes | $39/month (renews 2 Nov) |
| Instantly Growth | $47/month |
| Twilio credit + US number | ~$20 + $1.15/month |
| ChatGPT test answers (Apify) | ~3 cents |
| **Total today** | **≈ $140** |

**Monthly running cost from here:** ~$87 (Zapmail + Instantly) plus leads, verification and Twilio usage. Rises to ~$170–200 in November when Instantly moves to Hyper Growth.

---

## Next week (5–9 October)

| Day | Calls | Email |
|---|---|---|
| **Weekend 3–4 Oct** | Test the dialer on your own phone. Call Ben if he's free. | Warm-up runs on its own. |
| **Mon 5 Oct** | Calling starts, ~80–100 dials a day | Warm-up continues |
| **Tue–Wed** | Calling | Claude pulls candle leads (~$2–3). Kelian buys MillionVerifier (~$20) to verify emails. |
| **Thu–Fri** | Calling. The 222 phone leads run out; a new phone-number batch is needed. | Claude runs the ChatGPT comparison; Kelian spot-checks 10 emails. |
| **Mon 12 Oct** | | First real emails, ~50–100 a day |

**Email ramp after that:** ~200–250 a day from 19 Oct, ~300–350 a day from 26 Oct. October total ≈ 2,800–3,500 emails (~1,100–1,400 brands).

### Still open
- Kelian's **Close phone number** for dialer callbacks (`DIALER_CALLBACK_NUMBER`, still empty).
- **One test call** on the dialer before Monday.
- **SHAKEN/STIR** once registered as autónomo.
