# Produkto MVP — server

Phases 1 and 2 of [`../PLAN.md`](../PLAN.md):

```
paste a Shopify URL → read the catalogue → pick a product
                    → five buyer questions → freeze them
```

This is the part the artifact mockup could never do. A published Artifact runs
under a CSP that blocks every outbound network request, so reading *someone
else's* store has to happen on a server. Nothing here is hardcoded to M&O
Living or to furniture.

---

## Run it

```bash
python3 "mvp/server/app.py"
```

Then open <http://localhost:8000>. Stop it with Ctrl-C.

**Use this, not the published artifact.** They are two separate programs. The
artifact at `claude.ai/code/artifact/124df7ad…` is a static page whose CSP
blocks every network request, so its catalogue, Brand Hub and questions are
permanently hardcoded to M&O Living regardless of what URL is typed into it.
Only the local server can read a real store.

Paste a domain on the home page and it lands on the **real onboarding UI** at
`/onboarding?domain=…` — the same 7-step design as the artifact, filled with
that store's live data.

No `pip install`, no virtualenv — standard library only. It creates
`mvp/server/mvp.db` on first run. Delete that file to start clean.

---

## What each file does, in plain language

| File | What it does |
|---|---|
| `app.py` | The web server. Four steps: paste a URL → Brand Hub → pick a product → questions. |
| `catalog.py` | Downloads any Shopify store's public product list and tidies it up. |
| `brand.py` | Reads the store's homepage for its name, description and industry. |
| `render.py` | Serves the 7-step onboarding UI with the live store's data injected. |
| `questions.py` | Turns one product into five buyer questions. |
| `store.py` | The database — saves catalogues and question sets to one SQLite file. |

### `brand.py`

Reads the store's own homepage — `<title>`, meta description, `og:` tags — plus
the vendor and product_type fields on its own products. **Nothing is invented.**
If a store publishes no description, the field stays empty and says so, because
a Brand Hub that quietly writes its own description is indistinguishable from
one that read the site correctly until the merchant notices, and then nothing
in the report is trusted again.

Every field shows where it came from (`og:site_name`, `meta description`,
`product types`) so a wrong value is traceable rather than mysterious.

Two filters earn their place:

- **Aliases reject internal codes.** M&O's catalogue carries the vendor
  `MC7O-Living` next to `M&O`. It's real data, but no buyer types it into
  ChatGPT, so it isn't something to search AI answers for.
- **Industry prefers `product_type` over tags.** Tags are an unbounded
  merchandising dump — Allbirds publishes `allbirds::complete => true`,
  `YCRF_socks` and `onsite @ wc 5.26` alongside real categories. Filtering tags
  is whack-a-mole, so the curated field wins outright and tags are used only
  for stores like M&O that leave `product_type` empty on every product.

The step also flags when a catalogue is **below the 150-SKU floor** in the ICP —
Clubhouse Skin is 6 products, which is an afternoon of hand-fixing, not a
project worth selling.

### `catalog.py`

Every Shopify store publishes `yourstore.com/products.json` — a machine-readable
list of everything it sells. This fetches it page by page and normalises each
product to title, price, image, URL and variant count.

It counts **variants as well as products**, because that's the number that
matters. Allbirds lists 293 "products" but 2,855 variants once colour × size is
counted, and the variant count is what decides whether a brand sits in the
500–5,000 SKU band the ICP targets.

Failures return a message meant to be read by a person: a store behind a bot
filter, a non-Shopify site, a password page and a typo'd domain each say what
actually happened.

### `questions.py`

Builds five questions from **that product's own record** — its title, price,
and whatever material and dimensions are stated in its description. A €140
brass skull, a 160 cm marble dining table and a pair of wool runners each get
different questions.

The five deliberately probe the attributes the audit tool scores: price band,
dimensions, material, durability/care, and availability. Those are the
spec-shaped things buyers ask AI assistants, and the ones most catalogues fail
to state.

The product page also shows which of those four things the page actually
states. That's the same gap the audit measures — an assistant can only
recommend on facts a page states.

**This is a deterministic stand-in for the LLM call in PLAN.md phase 2.** It
reads real product data and produces sound questions, but it is rules, not a
model. Swapping in a real model call touches only `generate()`; the rest of the
app consumes a list of five strings either way.

### `store.py`

One SQLite file. The schema is the full one from PLAN.md — the `scans`,
`answers`, `mentions` and `scores` tables exist but are unused until phase 3, so
adding scanning later isn't a migration.

**Freezing is enforced here, not in the UI.** Once a question set is frozen,
`save_prompt_set` refuses to change it. A visibility score is only comparable
week to week if the questions stay identical, so this is a data-integrity rule
rather than a screen behaviour. Tested: a second freeze POST does not overwrite.

---

## Deliberate deviations from PLAN.md

- **`http.server` instead of FastAPI.** This machine has Python 3.9 with no
  FastAPI, and installing it means setting up a virtualenv first. Routing lives
  in one dispatch table (`ROUTES_GET` / `ROUTES_POST`), so moving to FastAPI is
  a small, contained change.
- **Questions are generated by rules, not a model.** See above.

---

## What is *not* built yet

Phases 3–7 — the actual scan. No OpenAI calls, no answer parsing, no scoring,
no dashboard. The tables are there; the code is not.

The honest state: this proves a merchant can paste their URL and get
product-specific questions out. It does not yet tell them whether ChatGPT
recommends them, which is the thing they'd pay for.

---

## Verified

Run against two real stores:

| Store | Products | Variants | Brand name read | Industry read |
|---|---|---|---|---|
| clubhouseskin.com | 6 | 6 | Clubhouse Skin | clubhouse, skin, skincare |
| molivings.com | 87 | 326 | M&O Living | bed, sofa |
| allbirds.com | 293 | 2,855 | Allbirds | shoes, socks, apparel |

Three stores, three different results, one code path — which is the property
the artifact mockup could never have.

Error paths checked: non-Shopify site (`example.com`), malformed input, and a
domain that doesn't resolve. Freeze immutability checked by attempting an
overwrite after freezing.
