# Stripe payment links

Live links for Produkto plans. Send one to a brand after the demo, when they say yes.

| Plan | Price | Link | Created |
|---|---|---|---|
| Starter | $99 USD / month | https://buy.stripe.com/fZu9AUcmkfJK5vI72w4ko00 | 2026-10-02 |
| Growth | $297 USD / month | https://buy.stripe.com/aFaeVe0DC9lm9LY72w4ko01 | 2026-10-02 |

Settings on each link: customer and business name, billing address, promotion codes, required "Store URL" field, confirmation message "Thanks! You'll get your Produkto login within 24 hours." No Managed Payments, no automatic tax.

**Check, 2026-10-02:** both links load and show the right USD price. But neither checkout page showed a Store URL field, a promotion-code box, business name or address. Either those options weren't saved, or Stripe shows them only after an email is entered. Not confirmed yet.

**2026-10-13:** the pricing page's Starter and Growth buttons now link here. Each link's *After payment* should redirect to `https://app.getprodukto.com/welcome?session_id={CHECKOUT_SESSION_ID}`, which checks the payment and creates the account (see `mvp/PAID-ACCESS-PLAN-2026-10-13.md`). The app reads the plan from the price before discounts: $99 → Starter (25), $297 → Growth (75). If a price changes, update `STRIPE_PLANS` in `mvp/app/accounts.py` too.
