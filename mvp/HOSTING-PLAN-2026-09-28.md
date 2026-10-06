# Hosting plan — Produkto MVP (draft for Kelian's approval)

28 September 2026. Accounts are planned separately, after this plan is agreed.

## Goal

A paying brand opens a link (e.g. `app.produkto.com`), and Produkto works there all day, every day: onboarding, dashboard, and a daily scan that runs whether or not Kelian's laptop is on.

## What the app needs (checked in the code)

- **Plain Python, no extra packages.** Standard library only, Python 3.9+. Nothing to install.
- **One database file** (`produkto.db`, 5 MB today). It must live on a disk that survives restarts and redeploys. The location is already configurable (`PRODUKTO_DB`).
- **Two secret keys**: `OPENAI_API_KEY`, `APIFY_TOKEN`. Today in `mvp/app/.env`; on the server they become protected settings, never files.
- **The daily scan runs inside the app** (a background thread). So the app must never sleep, and there must be exactly **one** copy running — two copies would scan every store twice.
- **One code change:** the app only accepts connections from the same computer (`127.0.0.1`). On a server it must listen publicly (`0.0.0.0`). Small, configurable change.

## Recommendation: Railway, one always-on service with a disk

| Option | Monthly | Effort for you | Verdict |
|---|---|---|---|
| **Railway** (service + volume) | ~$5–10 | Low: web dashboard, deploy from a folder, HTTPS included | **Recommended** |
| Fly.io (machine + volume) | ~$3–7 | Medium: command-line setup | Good, fiddlier |
| Render (paid instance + disk) | ~$10–15 | Low | Free tier sleeps, which kills daily scans |
| Hetzner VPS | ~€5 | High: you'd run a server yourself | Cheapest, most maintenance |

Why Railway: it runs one always-on copy, gives it a permanent disk, handles HTTPS and a custom domain, and stores the keys as protected settings — without you managing a server. Prices are my current understanding; confirm on their pricing page before signing up.

## Steps

**I prepare (in the code):**
1. Make the listen address configurable (`HOST`, default stays `127.0.0.1` locally, `0.0.0.0` on the server).
2. Add a start file for Railway (one line: `python3 app.py`) and a health check page (`/health`) so the host knows the app is alive.
3. Add a nightly database backup: a safe copy of `produkto.db` kept on the disk (last 14 days), plus a way to download it.
4. **A temporary password on the whole site** until accounts exist, so nobody who finds the URL can see the stores. Removed when accounts ship.
5. A short `DEPLOY.md`: every step, in plain language.

**You do (accounts and payment are yours):**
6. Create a Railway account and add a card.
7. Create the service, attach a volume, paste the two keys and the temporary password into its settings. I walk you through each screen.
8. Point a subdomain (e.g. `app.produkto.com`) at it once the marketing domain exists.

**Then together:**
9. Decide what data goes up: **recommended** — copy today's database, so Clubhouse Skin keeps its scan history for demos; test catalogs can be deleted first.
10. Switch off the laptop's daily scans (and the launchd job) once the server's scans run, or both will scan and bill twice.
11. Watch the first two daily scans run on the server before calling it done.

## Costs

- Hosting: ~$5–10/month (estimate).
- Domain: ~€10–15/year (shared with the marketing site).
- Scans: unchanged, ~$13 per store per month at current settings, paid from your OpenAI and Apify accounts.

## What a merchant sees if something fails

- **Server down:** the page doesn't load. A free uptime monitor (UptimeRobot) emails you within 5 minutes.
- **A daily scan fails:** that day is a gap in the chart, and the dashboard's "Updated…" line shows the data's age. Not retried the same day (existing rule). You'd see it in the app log.
- **Disk lost:** restore from the nightly backup; at most one day of scans lost.

## Not in this plan

- Accounts and per-brand privacy — the next plan.
- Payment / billing.
- The marketing site's hosting (separate, free: Cloudflare Pages or Netlify).

## Open questions for Kelian

1. Railway OK, or do you prefer cheapest (Hetzner) at the cost of more upkeep?
2. Copy today's database up (keeps Clubhouse Skin history), or start empty?
3. Domain: do you already own one for Produkto?
