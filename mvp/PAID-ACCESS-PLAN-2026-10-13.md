# From payment to dashboard: plan

*13 Oct 2026. Approved by Kelian (all three decisions: yes) and **built and deployed the same day**. Still needs the two Stripe steps under "What you'd do in Stripe" before it switches on. Until then `/welcome` shows "we couldn't confirm your payment yet" with the support email.*

## What happens today if someone pays

1. They click **Get started** on the pricing page and pay on Stripe.
2. Stripe's thank-you page says: *"You'll get your Produkto login within 24 hours."*
3. **Nothing happens automatically.** Stripe emails you about the payment. You open `app.getprodukto.com/admin`, create an invite (their email + plan), copy the link and email it to them yourself.
4. They open the link, choose a password, and land in onboarding: **Store → Brand → Catalog → Topics → Questions**. The question step is already capped by their plan (25 or 75).
5. The first scan runs, the dashboard fills in, and daily scans take over.

This works today with no new code. The weak spot is step 3. The customer has just paid and then waits for you, possibly overnight, since they're mostly in the US and you're in Barcelona.

## Recommended: they go straight from paying to onboarding

What the customer sees:

1. **Pricing page → Get started → Stripe checkout.** No change.
2. **They pay.** Instead of the "within 24 hours" message, Stripe sends them straight to `app.getprodukto.com/welcome`.
3. **"Create your account."** Their email is already filled in from checkout, so they only choose a password. The plan (Starter 25 / Growth 75) is set automatically from what they bought.
4. **Onboarding, exactly as today:** store URL, check brand details, catalog, topics, buyer questions.
5. **First scan starts**, the dashboard fills in, daily scans after that.

What you see: Stripe's usual "new payment" email, and the new customer appears in `/admin`, marked as paid through Stripe. You don't have to do anything.

### What I'd build

| Piece | What it does |
|---|---|
| `/welcome` page in the app | Asks Stripe whether this checkout was really paid and which plan it was, then creates the account invite. A fake or unpaid link gets a polite "we couldn't find your payment, book a demo" page. |
| One invite per payment | Refreshing or reopening the page can't create a second account. The link keeps working until they've set a password, so a closed tab isn't fatal. |
| `/admin` | Shows whether each account came from Stripe or a manual invite, and adds a **Disable** button for cancellations (there isn't one today). |
| Demo history clean-up | If the brand already had a demo scan, the simulated past days `demo_history.py` adds for demos are deleted automatically when they claim their store. Otherwise invented history would appear as their real trend. |

Manual invites at `/admin` keep working for Custom plans and demos.

### What you'd do in Stripe (about 10 minutes, I'll walk you through it)

1. On both payment links, set **After payment → Redirect to your website** to the welcome address I give you.
2. Create a **restricted API key** that can only *read* checkout sessions, and paste it into the server's `.env` yourself. I never need to see it.

**Cost:** €0. The Stripe API is free, and nothing new runs on the server.
**Time:** about half a day, tested end to end with Stripe's test mode before switching on.

## Not now (at ~5–10 paying customers)

- **Automatic cancellations.** For now Stripe emails you when someone cancels or a card fails, and you press Disable in `/admin`. Later, Stripe can tell the app directly (a webhook).
- **A welcome email** sent from the app. It can't send email today. Stripe's receipt and the redirect cover the first customers.
- **"Manage billing" in Settings** (Stripe's customer portal), so customers can change card, plan or cancel themselves.
- **Upgrading Starter → Growth from inside the app.**

## Decisions for you

1. **Build the automatic redirect now, or stay manual for the first customers?** I recommend building it: it's small, free, and the first minutes after paying are when a customer judges you. One conflict to flag: the Stripe memory note says "no code integration until about 5–10 paying customers". This would be a small exception to that.
2. **Cancellations handled by hand for now** (Stripe email → Disable button): OK?
3. **Brands that had a demo first:** keep their real demo scan in their history but delete the simulated days, as above. OK?

## Status — live and tested (13 Oct 2026)

Both Stripe steps done: payment links redirect to `/welcome`, and a read-only Checkout Sessions key is in the server `.env`. Tested with a real live checkout using a 100%-off code: it landed on "Thanks, your payment went through", set up as Starter (25 questions). The test invite was deleted and the test subscription cancelled. Payment links now allow promotion codes. Not yet seen end to end: setting the password and onboarding as a new customer email.
