# Handoff: the AEO articles agent, 19–20 Oct 2026

Start here when picking up work on the **AEO articles** agent (part of the Catalog Optimization Agent). Read this, then `mvp/content-agent/README.md` § "Designed AEO articles", then the code. The project `MEMORY.md` has the rules Kelian set along the way (search it for 2026-10-19).

## What Kelian wants (in his words, condensed)

- Articles must look like **the best article-writing brand in the merchant's own niche** (Patagonia was only an outdoor example), in **the merchant's own fonts, colours and photos**, never Produkto's look.
- **Ask every store specific questions** (common + niche-specific), pre-filled by AI, so the agent knows how each store's articles should read and look.
- The merchant must **see the article before it goes live**, full screen, and be **in charge of every change**, like editing in Claude: select a part, say what to change, and the agent **learns from every change**.
- Short chat updates. Verify on the **live site with the real existing drafts** before saying something works (he caught me once: "It doesn't even work").

## What's built and live (app.getprodukto.com, admins only)

Switches in the server `.env`: `PRODUKTO_CONTENT_AGENT=admin` (agent visible to admins only), `PRODUKTO_ARTICLES_V2=1` (designed articles). Customers see nothing.

| Piece | File | What it does |
|---|---|---|
| Brand look | `brand_style.py` | Reads the store's homepage + a product page + CSS (free); a mini CSS cascade finds the font on the real product title/description/price; one helper call (~0.1¢) settles roles + colours from what's on the page only. Cached a month in `content_settings['brand_style']`; owner overrides in `brand_style_overrides`. Clubhouse: PS Times headings (capitals), Helvetica Neue text, GT America Mono labels, square buttons. |
| Niche examples | `niche_examples.py` | From the store's scans: brand article pages AI cites (not `briefs.BIG_SITES`), up to 8 read free, one helper call (~0.2¢) keeps brands only and writes a playbook (length, blocks, headings, photos, tone). Articles the owner said they love come first. |
| Your articles questions | `article_setup.py` | Setup step "Your articles": 16 common questions + 4–8 niche questions generated per store (~0.25¢), all pre-filled. Feeds the writer (length, byline, disclaimer, categories, blocks), the fact check (compliance claims), brand facts (answers marked as facts), and drops "never use" products. Tested on Clubhouse (skincare), Wild One (pets), Onyx (coffee). |
| Writer | `drafts.article()` | Blocks, not HTML: dek, at-a-glance, 4–7 sections (step labels), product cards, photos, one table, FAQ, closing banner. ~1,000 words, ~1.7–2¢ incl. fact check + self-review. Comparisons use the same writer (`COMPARISON_SHAPE`, no "Not stated" rows). `drafts.guide`/`comparison` dispatch here when the switch is on. |
| Fact check | `factcheck.py` | New verdict `knowledge` (general category knowledge / ordinary how-to, articles only); the store's other product pages count as facts; numbers may come from the buyer question; `verified` = sentences not to re-check (a change re-checks only what changed). |
| Render | `article_render.py` | Blocks to HTML in the brand look, scoped under `.pk-a`; store's own photos (packshots in cards, lifestyle wide, no repeats; `photo_overrides` win); FAQPage markup; gaps highlighted; lists from "- " lines. `marks=True` (preview only) tags every part with `data-pk="<path>"`, photos `data-photo`, gaps `data-gap`. |
| Learning | `article_learning.py` | "Ask for changes" (whole article), lessons in `content_settings['article_lessons']` (Settings › Article look and lessons, removable), hand-edit lessons in the background. The pencil actions: `change_part`, `remove_part`, `set_text`, `move_section`, `add_section`, `swap_product`, `set_photo`, `upload_photo`, `look_quick`, `restore` (undo/history). |
| Draft screens | `content_review.py`, `content_board.py` | Clicking a board card opens a **full-screen overlay**: preview left (scrolls on its own, toolbar fixed above), questions/history right (scrolls on its own). Toolbar: **Edit · Undo · Look · Desktop/Phone**. Edit mode: click/highlight any part → Shorter / Simpler / In our voice / Make it a list / Remove / own words / Type it yourself, "Remember this for future articles"; sections: move up/down, remove, add one about…; cards: swap product; photos: pick store photo or **Upload from your computer**; yellow gaps: answer in place. `/content/preview?d=&id=` = full-page preview (`embed=1` = editable frame). Old-layout drafts show the styled preview + "Rewrite in the new design". |
| Shopify | `shopify_connect.py` | "Preview on your store" = hidden article draft; publish turns that same article visible with cover, summary, category tag. Uploaded photos (`content_media` table, public `/content/media/<token>.jpg`) are copied into the store's **Shopify Files** on publish/preview (`host_uploads`, needs new `read_files,write_files` scopes → older connections see "Reconnect Shopify"). Verified live on produkto-test. |

Tests: `test_articles.py` (~40 tests); the full suite (282+) must pass in one process with the real DB untouched.

## State of the data

- **Clubhouse Skin** (`clubhouseskin.com`) on the server: AEO drafts **7** (comparison) and **8** (guide) are the designed versions; 5 and 6 are the old ones, rejected. Its Shopify connection points at `produkto-test` with OLD scopes and can't be reconnected (wrong-store guard, by design) → nothing of Clubhouse's can go live or use Preview on your store. Fix only when Clubhouse's owner connects `clubhouse-skin.myshopify.com`.
- **produkto-test** is also its own store in Produkto (`produkto-test.myshopify.com`), connected with `write_files`; used for the Shopify Files test (draft 9 there, rejected, its article deleted). One test photo is still in produkto-test's Shopify Files.
- Server DB backup before the first deploy: `/opt/produkto/backups/pre-articles-v2-20261019.db`.

## How to work on it safely

- **Never test on the live DB.** Snapshot: `ssh … "sqlite3 /opt/produkto/app/produkto.db '.backup /tmp/arttest/snap.db'"`, scp it down, copy to the session scratchpad, run with `PRODUKTO_DB=<copy> PRODUKTO_DAILY_SCANS=0 PRODUKTO_SCANS=0 PRODUKTO_ARTICLES_V2=1 PRODUKTO_CONTENT_AGENT=1`.
- **Running the app locally:** the preview runner can't read the Desktop folder, so rsync `mvp/app` (excluding `produkto.db*`, `__pycache__`, `icons/`; exclude `.env` unless the test needs OpenAI) into the scratchpad, add a temporary `.claude/launch.json` entry pointing there (port 8014), sign in by inserting a session for the admin user into the scratch DB (`accounts.new_session(1)`) and setting the `pk_session` cookie in the pane. Remove the launch entry and the scratch copy (it may hold the API key) afterwards.
- **Deploy:** run the full suite and only deploy if it says OK (`grep -q "^OK"`, not `tail && rsync`: that once deployed past a failing test). Diff each shared file against the server first (other sessions edit `app.py`, `accounts.py`, etc.). Then `rsync` only the changed files, `chown -R produkto:produkto /opt/produkto/app`, `systemctl restart produkto`, curl the login page, run `test_articles` on the server.
- **Verify in Kelian's Chrome** ("Browser 1", signed in to Produkto and Shopify) on the real drafts.
- Money: OpenAI drafting is cents (article ~2¢, part change <1¢). Cash is tight: say the cost before anything paid.

## Known weak spots / next ideas

- Fact check is still strict: new drafts land with 3–6 questions for the merchant; "Shorter" is sometimes refused on general-advice paragraphs (safe, but annoying).
- Built and deployed 20 Oct (admins only): the **stories page** (`stories_hub.py`) and **Instagram photos** (`social_photos.py`), see README § Stories page. Also fixes broken uploads on the server (positional insert).
- Not built: **notes, then apply all**; stock or generated images; a Stripe add-on for article packs.
- Demo Wednesday 21 Oct: Tuesday prep per `mvp/HANDOFF-2026-10-18.md` (`demo_agents.py`/`demo_history.py` are still NOT deployed; Kelian must choose honest vs simulated Results). The demo agents now write designed articles because the switch is on.
