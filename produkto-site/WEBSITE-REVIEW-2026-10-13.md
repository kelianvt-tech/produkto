# Website review: getprodukto.com, 13 Oct 2026

**Verdict: you're not being difficult.** The homepage describes the product as it was in late August: pick one product, get a score out of 100, re-scan weekly. The product today is catalog-wide, scans every day, measures three engines, and has Answers, Citations and Opportunities. The pricing page (written 28 Sep) matches the product. The homepage doesn't. None of the visuals come from the app either. They're hand-drawn mini widgets in a warmer, beige style with made-up brands, so a visitor never sees what they'd be buying.

Ordered by urgency.

---

## P0: Broken on the live site right now

**1. Nobody can book a demo from the site.** Netlify rewrites `pricing.html` to `/pricing` in the live HTML. `app.js` passes every nav link to `querySelector` to highlight the current section, `'/pricing'` is not a valid selector, and the script crashes there (console: *"'/pricing' is not a valid selector"*). Everything after that line never runs:
- the Calendly calendar: the section shows "Demo booking will be available here soon."
- the "Your buyer asks. AI picks three products." chat panel: it's an empty bar labelled "AI answer"
- the "send a note" form: it isn't wired up, so a submission reloads the page and the note is lost

You can't see this locally because the local file still says `pricing.html`.
**Fixed locally** (`dist/app.js`, nav links are now filtered to `#` links only). On the live page I checked that the filtered list works and that the Calendly block then loads the calendar. **Not deployed yet.**

**2. The note form has no key.** `booking-config.js` has `noteKey: ''`, so even with the fix the form answers "Notes aren't switched on yet. Please book a time above instead." Either add a free Web3Forms key or remove the form.

**3. "Book a 15-minute demo" links to a 30-minute Calendly event** (`calendly.com/kelianvtla/30min`). Pick one length.

---

## P1: Claims the product doesn't back up

| On the site | What's actually true | Fix |
|---|---|---|
| Hero rotates **ChatGPT, AI Overviews, Grok, Claude, Gemini** | The app measures **ChatGPT, Google AI Overviews, Perplexity** (`engines.py`). Grok, Claude and Gemini aren't measured, and Perplexity is missing. The FAQ on the same page gives the right list. | Rotate the three real engines. Same for the faint logos in the navy section. |
| "Pick a product" (meta description, How it works step 02, "Paste, pick, and see where you land") | The whole catalog is measured. The merchant doesn't pick a product. | Rewrite How it works around the catalog (see below). |
| "Visibility score / 100… weighted by position" | The dashboard's headline is **"mentioned in X% of answers"**, with average position shown separately. The /100 score was dropped on 17 Sep. | Show the % and position as the app does. |
| "re-scanned **every week**" (step 04) next to "re-scanned **every day**" (feature card) | Daily. Pricing also says daily. | Say daily everywhere. |
| "**Nearly 60%** of shoppers now use AI to discover products" | No source for this anywhere in the repo, and the same page later says **39%** (Adobe). A skeptical reader sees two numbers that don't match. | Use the sourced 39%, or find a source for the 60%. |
| "changes too small to trust clearly marked" | I couldn't confirm the dashboard does this (not checked; I didn't have app access, see below). | Check, then keep or cut. |
| FAQ: "Kelian will walk you through saved results from real scans" | Demos now run on a free scan of the prospect's own store (decided 12 Oct). | "Before the call we scan your store, so the demo shows your own products." |
| "catalogue", "Load catalogue", "colour" | The copy skill says American spelling. | catalog, color. |
| Hero sub: "optimize your presence to reach the next generation of shoppers" | Close to promising a result, and generic. | Say what the product does: which of your products AI recommends, which it skips, and who it picks instead. |

---

## P2: Real features the site doesn't mention

These exist in the app today and a buyer would care about them:

- **Catalog overview:** visibility over time for you and every competitor brand on one chart, plus product rankings with images. This is the strongest visual you have.
- **Answers:** read every AI answer behind the numbers.
- **Mentions & Citations:** the sites AI cites when it recommends products.
- **Opportunities:** a ranked list of fixes: questions you lose and who wins them, sites to get onto, and Content Gap (what the winners' product pages state that yours don't). Each card has Done/Dismiss, and Done cards show a before/after.
- **Buyer questions:** generated from your catalog, grouped by topic, and editable.
- **Engine filter:** ChatGPT, AI Overviews and Perplexity, separately or together.

Leave **Content agents** off the site until they exist. The copy skill bans teasing future scope.

---

## Design

1. **Use the real UI.** Swap the mini widgets (Alpenfeld, Kestrel, the "21 / 100" card) for screenshots or short screen recordings of the actual dashboard. The app's look (white/blue tint, logo navy, product images, multi-color brand lines) is different from the site's warm beige cards. The two should look like one product.
2. **Hero:** put a framed dashboard screenshot (catalog overview) under the headline, the way Peec, Promptwatch and Profound do. Move the real captured AI answer lower, where it shows the problem.
3. **Scroll length:** the navy word-reveal statement is 220vh tall, so it takes about two full screens of scrolling to read one sentence. Halve it, or make it a normal section.
4. **How it works:** match the real onboarding (Store → Brand → Catalog → Topics → Questions → dashboard), using the onboarding screens already captured in `mvp/qa/`.
5. **Reveal animations:** mid-scroll, sections sit faded grey for a moment, which makes the page look washed out. Trigger the reveal earlier or use a shorter fade.

### Proposed homepage order
1. Hero: one line, "Book a demo", dashboard screenshot
2. Engine strip: the three real engines
3. "Your buyer asks. AI picks three products.": the real captured answer (it works once P0 is deployed)
4. Product tour: Overview · Answers · Citations · Opportunities, one real screenshot each
5. How it works: four catalog-level steps
6. Why now: sourced stats only
7. Pricing teaser linking to `/pricing`
8. FAQ, updated
9. Booking

---

## Decisions needed from Kelian

1. **Deploy the P0 fix now?** It's one line, and right now the site can't take a booking.
2. **Whose data goes in the screenshots?** Options: Clubhouse Skin (a real brand, needs Ben's OK before going public), or a fictional demo store run through the real app (follows the existing "illustrative data, fictional catalog" rule). I'd recommend the fictional store.
3. **Social proof:** memory says you work with Wild One. Ask before naming them on the site.

## Not checked
- **The logged-in app.** Access was blocked in this session, so the feature list comes from the code and the 2 Oct Clubhouse Skin screenshots.
- **Mobile layout.**

Side note: `context/BUSINESS.md` still says "Name: Not chosen yet" (last updated 3 Aug). It's stale.
