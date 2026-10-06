# Produkto landing page: design review against B2B AI references

**Date:** 15 September 2026
**Scope:** Research and recommendations only. Nothing on the site has been changed.
**Page reviewed:** https://produkto-catalog-intelligence.info101972.chatgpt.site (source in `dist/`)

---

## How this was done, and its limits

I reviewed 21 full-page captures on Lapa Ninja, grouped by what you asked for:

| Group | References |
|---|---|
| B2B AI SaaS | Readily, Greptile, Solidroad, Antimetal, Parallel, Alex |
| Product UI shown inside the marketing page | Linear, Granola, Index, Superhuman, Polar |
| Enterprise AI / infrastructure | Cantor8, Atlassian Teamwork Graph, Restate, Mintlify |
| Integration ecosystems | Segment, Nylas, plus the integration sections of Antimetal, Teamwork Graph, Index, Restate and Solidroad |
| Software marketplaces / platforms | Stripe Connect, LeafLink, Shopify Dev |

Limits worth knowing:
- I viewed the captures at reduced resolution. Layout, hierarchy and section order are reliable; small body copy is not.
- Some captures are old. Segment and Nylas look like 2018-era pages, and Stripe Connect is an older version too. I used them for structure, not visual style.
- Lapa Ninja's "integrations" search returned nothing. Integration patterns come from the integration sections of the pages above.
- Lapa Ninja has few marketplace examples in this space. Three is a thin sample.
- The patterns below show up across several references. None of them comes from copying one page.

---

## 1. Where the current page feels generic or mismatched

**The headline doesn't name the category or the buyer.** "Great products. Ready for the next search." and the eyebrow "Product discovery, reimagined" would fit a search plugin, a PIM (product information management tool) or an SEO agency. Across the references, the headline states what the thing is and who it's for in plain words, e.g. "compliance for healthcare" or "a payments platform for platforms". Produkto's hero says neither "DTC brands" nor "AI assistants".

**The styling repeats one move until it looks like a template.** Five section headings end in the same serif-italic accent ("next search", "Different questions", "a clearer picture", "A measurable starting point", "Straight answers"). Each sits under a numbered eyebrow ("01 / Follow the question"). Navy, DM Sans and an Instrument Serif italic accent is a very common generated-site look. Granola also uses an italic accent word, so the device itself is fine. Using it on every heading is what makes it feel templated. *(This is my judgement, not a measured finding.)*

**The product preview shows a SaaS app that doesn't exist.** The demo has a "Workspace / Catalog overview" sidebar, an "Example store" picker and dashboard tiles. That implies a login and a self-serve tool. `CLAUDE.md` rules both out ("No login, no UI"), and `BUSINESS.md` positions *against* dashboards ("They sell software. We sell the result."). So the page's main visual pitches the category you say you're not in.

**Two scores on different scales sit a few sections apart.** The demo shows "42/100, facts stated in the sample" (illustrative). The proof section shows "16.8/100 spec-query retrievability" (real). A visitor can't tell which number means what.

**Proof and action come too late or don't exist.**
- The only real evidence (the M&O audit) is section 04 of 5, just above the FAQ.
- Every button scrolls within the page ("Explore the demo", "Explore your category"). Nothing lets a visitor request anything. Every reference has a real conversion action in the hero and repeats it at the end.

**It's broad where the business says go deep.** The page features six categories at equal weight. `BUSINESS.md` says "We go deep in one category at a time", and the only real data is furniture. Six shallow categories read as a generic tool. One deep one reads as expertise.

**The trust signals are thin, and one is inaccurate.** There's no named person, no methodology detail, no sample of the deliverable beyond a markdown link, and no price or timeline. The M&O card says "Independent review of public product data". Per `Kelian OS/CLAUDE.md` it's your family's shop, so "independent" should go (flagged earlier). The FAQ is the most credible part of the page because it states limits honestly. Keep it.

---

## 2. Recurring patterns in the strongest references

**A. The hero names the category, then shows proof straight away.** A plain-language headline, one sentence on how it works, a primary action (book a demo, start, contact sales) and a secondary one. Directly under that sits a proof strip: customer logos, or "backed by" for early companies (Readily). Seen in Readily, Solidroad, Greptile, Linear, Superhuman, Index, Mintlify, Segment and Alex.

**B. The real product appears large and early, full of realistic content.**
- Linear, Index, Mintlify and Superhuman put the product *in* the hero at near full width.
- The content is realistic and dense: actual issue text, full tables, readable charts. A few placeholder tiles would not pass.
- When the product isn't visual, they show its *output*: Parallel's benchmark chart against named alternatives, code from Restate and Polar.
- Readily and Stripe Connect crop fragments of the product (a rule card, a KPI card) and float them over brand panels as callouts, instead of showing full app chrome.

**C. The mechanism is 3 steps, each with its own visual.** Greptile's "how it reviews", Granola's "how it works", Solidroad's three product cards, Segment's three components. Each step gets a specific image, not an icon.

**D. Integrations are the tools you already use, arranged around the product.** Antimetal places stack logos in an orbit, Teamwork Graph uses a logo cloud and a logo rail, Index has "connect your data", Restate "deploys to your stack", Solidroad shows "made for your CX stack" chips, and Segment has a tabbed integration catalogue. The message is that it fits in without replacing anything.

**E. Marketplaces and platforms prove scale and split their audience.** LeafLink runs a row of four network numbers, a press-logo strip and a "for brands / for retailers" split. Shopify Dev pairs "launch to millions of merchants" with a stats card. Stripe Connect organises the page by the account types it supports.

**F. Outcomes are specific numbers with a source.** Readily 90% / $734K / 20→150; Solidroad "1 hour" and "2000+" next to a named quote; Antimetal 5x / 234K+; Mintlify 300M+ / 99.99%; Parallel's benchmarks against competitors.

**G. They have an enterprise-readiness band.** Greptile has "security-first" (self-hosted, SOC 2, enterprise-ready), Readily "built for the trust healthcare runs on" with certification badges, and Solidroad "engineered for enterprises". The band answers "is this safe to let near our data?" before anyone asks.

**H. Testimonials carry a name, role, company and usually a face.** Card rows (Readily, Linear, Restate), a single large quote under the logo bar (Greptile, Segment), a social wall (Granola) or video (Alex).

**I. One signature visual element, used consistently.** Painterly landscapes (Readily), illustrated landscapes (Solidroad), line-art glyphs (Polar), grid lines and hatching (Greptile), a single blue with thin line diagrams (Cantor8), dark UI (Linear). A restrained palette, one type system, and the signature element carries the brand. Where a serif is used, it's used consistently rather than as a decorative accent.

**J. Signs of momentum.** A changelog (Linear), "latest updates" (Mintlify), a newsroom (Cantor8), a resource library (LeafLink).

**K. A closing CTA band repeats the primary action.** Every reference has one.

---

## 3. Recommendations

### The key constraint

About half of these patterns rely on assets Produkto doesn't have yet: customer logos, quantified outcomes, testimonials, security certifications, scale numbers. Borrowing the *look* of those sections without the substance is the fastest way to seem less credible, and it's exactly the overclaiming `CLAUDE.md` warns against. So:

- **Use now:** A (hero clarity), B (the real artifact, large), C (3-step mechanism), D (stack fit, only for what's true), I (signature element), K (closing CTA).
- **Adapt honestly:** F, G and H, using the pre-customer substitutes listed under trust signals below.
- **Hold until real:** logo walls, customer numbers, testimonials, certifications, network-scale stats (E).

### Visual direction: evidence-first and editorial

- **Ground:** light, white or warm-paper background, one ink colour.
- **Signal colour:** one accent, reserved for a single meaning: *a missing fact*. Everywhere it appears, it marks a gap. That becomes the ownable signature element (pattern I), and it's tied to what the product actually does, not decoration.
- **Signature device:** real product copy set as quoted evidence, with the missing attributes marked inline (a bracket, highlight or margin note). The brand becomes "we read your catalog and show you what isn't there."
- **Typography:** one sans for headings and UI. Keep the serif, but give it one job: quoting product-page text (the evidence). Drop the italic accent from section headings and the numbered eyebrows.
- **Imagery:** drop the generated furniture illustration. Use the annotated evidence device instead. If you use real product images, get permission, including from M&O.

### Page structure

1. **Hero.** A headline that names who it's for and what they get, in the "[what it is] for [who]" shape the references use. A subline with the mechanism plus the human-accountability point from `BUSINESS.md`. Primary CTA: request a catalog audit. Secondary: see a sample report.
   *The primary CTA needs a real capture form with proper data handling. The README says none exists yet, and without one the page can't generate any demand signal.*
   Under the hero, an honest proof strip, e.g. "86-product catalog audited · 11 buyer attributes checked · public pages only, no store login".
2. **The deliverable, large.** A preview of the actual audit report (see below). This replaces the mock workspace.
3. **How it works, in 3 steps** (read → match to buyer questions → fix list), each with its own visual. Add **what you get and when** (report format, turnaround) and, if you're comfortable, a price anchor. Services pages that publish ranges read as more credible. *This is a business decision, not a design one.*
4. **One category in depth.** Furniture: buyer question → attribute → missing on N products. Show the other categories as a single "also works for" line, not six equal cards.
5. **Fits your stack.** Only list what's true today: Shopify storefronts, public product pages, structured product data. No integration logos for things the tool doesn't connect to.
6. **Trust band, pre-customer version** (see below).
7. **FAQ.** Keep the current honest answers.
8. **Closing CTA**, repeating the hero action.

### Product preview

- **Show the real artifact, not a fake app.** `sample-audit.md` already has what a strong preview needs: the two scores, the attribute-gap table (structured / prose only / missing), and the 20 weakest products. Design it as a document or report, not a dashboard with a sidebar.
- **Make it dense and realistic.** Show all the attribute rows and a real-length product list, like Linear and Index do. Three product rows reads as a mock-up.
- **Annotate with 2–3 cropped callouts** floating beside the report (the Readily / Stripe Connect approach). For example, one product's actual description with the missing attributes marked, and one gap row enlarged.
- **Use one scoring scale on the whole page.** If the preview uses M&O data, disclose it right there. If it's anonymised or illustrative, say so and don't show a second score.
- **Don't show a before/after visibility change.** Whether remediation moves AI visibility is unproven (`BUSINESS.md`). A before/after of *stated facts* is fine. A before/after of *rankings or traffic* is not.

### Trust signals

**Available now, and honest:**
- A named, accountable person: founder name, photo and a direct contact. This is the substitute for testimonials (H) and the differentiation `BUSINESS.md` describes.
- A dated sample report with the family relationship disclosed.
- Methodology transparency: how attributes are chosen, where buyer questions come from, what the score measures and what it doesn't. This is the substitute for benchmark charts (F).
- A data-safety band: public pages only, read-only, no store login, no changes to the store. This is the honest version of the enterprise-readiness band (G).
- The existing FAQ limits ("will this guarantee an AI recommendation? No").

**Add only once they're real:** client logos, named quotes, before/after fact coverage on a paying catalog, case studies, counts of catalogs or products audited.

**Never use:** security or compliance badges you don't hold, a "trusted by" row, invented counts, or outcome claims about AI visibility.

---

## Documents that disagree

- `context/BUSINESS.md` says **"Name: Not chosen yet"**, but the site is live as **Produkto**. `BUSINESS.md` is out of date.
- `CLAUDE.md` says **"No login, no UI"**, but the site's main visual is a workspace UI. The site is the outlier here.
- `CLAUDE.md` makes `00-BRIEF.md` required reading, but **the file isn't in the project folder**. This review used `context/` only.
