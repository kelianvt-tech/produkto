# Produkto

Responsive marketing website built as standalone HTML, CSS and JavaScript, with no build step. Public site files are in `dist/`; hosting is configured in `.openai/hosting.json`.

The page describes the MVP in `../mvp/PLAN.md`: paste a Shopify URL, pick one product, ask ChatGPT five buyer questions five times each, then show visibility score, trend, share of voice and competitor positioning, plus a fix list.

## Data on the page

Everything shown is illustrative and labelled as such:

- **AI shopping answers:** fictional questions, products and ratings.
- **Buyer-question search and categories:** example questions, not live AI results.
- **Adobe figures (Why now):** from `context/BUSINESS.md`.

No real brand's catalogue, audit or visibility data appears on the site.

## What the page promises vs. what exists

`mvp/server/README.md` says phases 1–2 are built (URL → catalogue → product → five frozen questions). The scan itself (phases 3–7) is not. The page therefore sells **early access**, labels examples as sample data, and the FAQ says so plainly. Update the copy when scanning ships.

## Before publishing

1. **Connect the early-access form.** Set `CONFIG.requestEndpoint` (receives a JSON POST with `store`, `email`, `catalogSize`) or `CONFIG.contactEmail` (opens the visitor's email app) at the top of `dist/app.js`. Until one is set, the form validates input but tells visitors plainly that nothing was sent or stored.
2. **Confirm the founder card** in the Principles section (name, role, wording).

## Local preview

```bash
python3 -m http.server 4173 --directory dist
```

Fonts come from Google Fonts (Geist, Geist Mono), with system fallbacks. There is no analytics, account creation or persistent visitor data.
