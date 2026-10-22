---
name: log-cost
description: Add or change a cost in Kelian's cost tracker Google Sheet - subscriptions/memberships, API usage, credit top-ups, one-off purchases - and keep the monthly total and forecast right. Use whenever Kelian says he paid for, bought, subscribed to, upgraded, cancelled or topped up anything, or a session buys something on his behalf, or he asks what he is spending.
---

# Log a cost

The tracker is one Google Sheet: "cost-tracker", https://docs.google.com/spreadsheets/d/1mcls2aG51pno6hZ7xqeIb3Rg8lDnXwWSoFe6WYkNQ34/edit (the old cost-tracker.xlsx in Drive is retired). Never re-import files into it and never edit the local `Kelian OS/cost-tracker.xlsx` any more: that file is the pre-2026-10-05 copy.

Every change goes through `log_cost.py`, which posts to a script inside the sheet. The URL and token live in `~/.produkto-cost-tracker`; never print them.

```bash
python3 .Codex/skills/log-cost/log_cost.py '{"action":"read"}'
```

## Steps

1. **Read first** (`read`) so you don't add a duplicate and you know the current rows.
2. **Pick the tab by what the money is:**

| Kind of cost | Action | Tab |
|---|---|---|
| Membership / subscription / plan (recurring) | `add_subscription`, or `update_subscription` if the tool is already there | Subscriptions |
| Plan upgrade, downgrade, price change, cancellation | `update_subscription` (`amount`, `plan`, `status`: Active / Cancelled) | Subscriptions |
| Metered API or usage charge | `add_usage`, type `Usage` | API & Usage Costs |
| Credit / balance top-up | `add_usage`, type `Top-up` | API & Usage Costs |
| One-off purchase (domain, a tool, a credit pack) | `add_usage`, type `One-off`; if it renews yearly, also `add_subscription` with cycle `Yearly` | both |
| A future change that's planned (e.g. "upgrade in November") | `set_forecast` for that month | Forecast |

3. **Send it.** Field formats:
   - `add_subscription`: `{"action":"add_subscription","row":{"tool","purpose","plan","cycle":"Monthly|Yearly|Quarterly|Usage","amount":number,"currency":"USD|EUR","started":"yyyy-mm-dd","renews":"yyyy-mm-dd","status":"Active","notes"}}`
   - `update_subscription`: `{"action":"update_subscription","tool":"Instantly","fields":{"plan":"Hyper Growth","amount":97}}`
   - `add_usage`: `{"action":"add_usage","row":{"date":"yyyy-mm-dd","provider","what","amount":number_in_USD,"type":"Usage|Top-up|One-off","source","notes"}}`
   - `set_forecast`: `{"action":"set_forecast","cost":"Instantly","month":"2026-11","value":97,"note":"..."}`
4. **Read again and check** the row landed and the totals moved as expected (Subscriptions "Total per month", Forecast totals).
5. **Tell Kelian in one or two lines** what was added and the new monthly total.

## Rules

- **Amounts come from Kelian or a receipt.** If he doesn't give one, ask once. If you must estimate, write `ESTIMATE` in notes and say so.
- **Money is entered in the currency it was paid in** on Subscriptions (EUR is converted by the sheet). The usage tab is USD only: convert EUR at the rate in Subscriptions ("EUR to USD rate") and say so in notes.
- **Don't log the same money twice**: a top-up and the usage it paid for are the same money. Per provider, log one or the other (see the note on the usage tab).
- **When a session buys something** (Twilio credit, Apify run, domains, a plan), log it in the same session.
- Usage-only providers that are already rows on Subscriptions (OpenAI, Apify overage, Twilio minutes) get their charges on the usage tab, not a new subscription row.

## Setup (done once; redo only if the sheet is replaced)

1. Sheet must be a native Google Sheet (File → Save as Google Sheets if it shows an .XLSX badge).
2. Extensions → Apps Script → paste `cost-tracker-script.gs`, set `TOKEN` to a long random string → Deploy → New deployment → Web app, execute as **Me**, access **Anyone** → authorise.
3. Save `{"url":"<web app URL>","token":"<same token>"}` to `~/.produkto-cost-tracker` (chmod 600).
