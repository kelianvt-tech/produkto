# Produkto — proposed MVP experience

18 September 2026 · Proposal for Kelian’s review · No application changes made

## Recommendation

Keep Produkto’s current visual identity and change the starting point of the dashboard: the merchant opens their catalog, sees which products appear in AI answers, and opens any product for the supporting detail. A shared set of buyer questions powers all those views. Opening a product, changing a date filter or reading an answer uses saved results and does not buy another scan.

The experience should feel like an expanded version of the current MVP. The substantial change is what is measured and how the results connect.

This proposal follows `REARCHITECTURE-SPEC-2026-09-18.md`, the existing presentation code and the September memory rules. The August brief still describes a script/PDF with no UI; the current request and September spec establish this task’s scope. The brief also prioritises furniture; the newer ICP explicitly keeps the initial sample broad. No furniture audit evidence is used as product proof here.

## Design inspiration researched on Lapa Ninja

Firecrawl scraped the pages below. I also inspected their archived website screenshots through full-page captures of the Lapa Ninja entries. These are landing-page references containing product UI previews, not a usability review of the live applications.

| Reference | What is visible in the reference | How I would apply it |
| --- | --- | --- |
| [Steep](https://www.lapa.ninja/post/steep/) | Light analytics workspace, a substantial central chart, fine dividers, and a metric list with small category labels. Soft mint/cream marketing surfaces surround its UI. | Preserve a large chart as the anchor; make the new catalog table quiet, aligned and easy to scan. Use restrained separators and generous panel padding. |
| [June](https://www.lapa.ninja/post/june-3/) | A company detail view with a clear identity area, contextual metrics, charts and a “Back to companies” link. White panels sit on a pale surface. | Give product detail a clear identity header and “Back to catalog” link. Keep the same reporting frame when the selected product changes. |

These are refinements to Produkto’s established Searchable-inspired dashboard. Keep Geist, navy, existing icons, product imagery and the current chart/panel hierarchy. The proposal does not adopt Steep’s serif headlines, June’s playful display type, their pricing sections or testimonial blocks.

Source extraction: `.firecrawl/lapa-inspiration-2026-09-18.json` beside this report. Linear was also surfaced in the initial search; its dark marketing treatment is not part of the recommended direction.

## Exactly what the merchant sees

### 1. Store

The opening screen keeps the existing logo, four-step indicator and split onboarding layout. The left is the softly lit form surface; the right keeps the existing navy sky illustration and the “Your products. The next way to shop.” heading. The current code already contains that navy right-hand panel, despite the spec’s shorthand description of “cream onboarding.” Preserve the actual approved styling.

The merchant pastes a Shopify store URL and continues. While catalog data loads, show real loading feedback. An invalid URL or failed import produces an inline explanation and a retry action; it never advances to an empty success screen. No Shopify installation or account creation is introduced.

### 2. Brand

Keep brand name, aliases, country and currency. These identify products correctly and establish the market being measured. No persona, brand strategy or tone-of-voice fields.

Populate currency from store metadata. If it is unavailable, flag it for correction or omit prices from generated questions; do not guess a currency. Keep brand setup before catalog confirmation.

### 3. Catalog — the first visible change

The indicator now reads **Store → Brand → Catalog → Questions**. Heading: **“Confirm your catalog”**. Supporting line: **“Choose the product types you want to track.”**

Keep the existing searchable image grid. Each card shows the actual product image, title and price. Above it, product-type checkboxes let the merchant exclude categories. All available types begin included. Excluded products remain visible but subdued, with a text label as well as the changed appearance. Product-card clicks no longer select a single winner.

The right preview represents the selected catalog rather than enlarging one product. Reuse actual product thumbnails inside the existing preview card. The primary action is **“Continue”**, disabled if everything is excluded.

Product totals can be shown; question/run totals cannot. Label catalog records as “products,” not “SKUs”: the existing data model tracks product listings, not individually measured size/colour variants.

If product types are missing, put those products in “Uncategorised” rather than silently dropping them. Category inference or a richer catalog editor would be a separate decision.

### 4. Questions — grouped around buyer needs

Questions remain on their own final screen. First show **“Preparing buyer questions from your catalog…”** while the model actually generates them. Then show the existing editable question rows, grouped under plain-language headings such as a product category or buying need, using only labels generated from the real catalog.

Each row retains its existing intent tag: best, budget, spec, use case or compare. Price-based questions use the store currency symbol. The questions must be grounded in real catalog facts; the design preview’s labels are not a question-generation template.

Recommended addition for review: a compact **“Relevant products”** disclosure under each group, so the merchant can see which products that question can reasonably evaluate. This requires a product-to-question mapping that the current spec does not define; see the decisions below.

Before the primary **“Start scan”** action, show: **“These questions will stay fixed after your first scan so future results can be compared.”** Editing remains available only before scanning. Show the generated groups themselves, with no numeric question-count badge.

### 5. Scan in progress

Reuse the current progress screen with the store identity and a simple stage label: collecting answers, then matching products and preparing results. Show progress as a percentage only when based on real work completed. Do not announce completion merely because all attempts ended.

There is one store scan in progress at a time. A merchant should not be able to accidentally launch duplicate scans from repeated clicks or from a product detail page.

### 6. Catalog overview — the new default landing screen

At desktop width, the top header shows the store identity on the left, **“Catalog overview”**, and the scan action on the right. Immediately below are the existing navigation links: **Overview · Answers · Buyer questions · Mentions & Citations**. Buyer questions still opens the section within Overview.

The date range and **Weekly / Monthly / Quarterly** grouping sit above the panels. These settings follow the merchant through every tab and into each product. ChatGPT is the MVP’s measured engine; there is no decorative multi-engine selector.

The first row retains the existing chart-led, two-column reporting layout:

- **Visibility panel:** large headline **“Mentioned in X% of answers”**, followed by a readable explanation: **“At least one of your catalog’s products was named.”** Average position is separate. Keep the existing ranking definition and document how catalog-level positions are pooled before implementation.
- **Share of voice panel:** the existing competitive view, with clear labels, product imagery or favicons when available, and the existing expanded drawer. Multiple own products must be recognised as yours. They must never appear as external competitors.

Below the primary panels comes a new full-width **“Your products”** table. It is the key addition, not another row of summary tiles.

| Column | Appearance and behaviour |
| --- | --- |
| Product | Small product image, title, muted product type; the name is a keyboard-accessible link. |
| Mentioned in answers | Percentage, aligned consistently down the column. Default descending sort. |
| Average position | A rank where a product was named; an em dash when it was never named. |
| Share of voice | Percentage with an accessible definition of the denominator. |
| Coverage, proposed | “Measured”, “Not covered” or “Excluded”; partial results have an explicit warning. |

Keep measured products with 0% in the table. Recommended lightweight filters: product search, product type, and “No mentions.” These are presentation filters over saved data and do not start scans. The merchant can quickly isolate the products requiring investigation without changing the default descending sort.

The existing competitive product rankings, buyer-question section and scan history continue underneath. Buyer questions gain their group headings. No automatic fixes, inferred causes, revenue claims or invented optimisation advice are added to this measurement MVP.

### 7. Product detail — one click deeper

Clicking a product replaces the catalog header with its actual image, name and store. **“Back to catalog”** restores the catalog context and selected period. A product switcher is an optional convenience, not required for this first build.

The same Overview, Answers, Buyer questions and Mentions & Citations navigation remains. The main percentage now describes that product, and average position remains separate. The chart stays date-based. Questions appear in the buyer-question section, not as a second chart mode.

The proposed relevant-question mapping should also constrain the product’s measurement denominator. Do not judge a cleanser against unrelated sunscreen questions. A small definition under the headline can say **“Across the buyer questions relevant to this product.”** That wording must only ship once the mapping actually exists.

Competitor context needs an explicit scope: either recompute the view from the relevant saved answers or retain the shared leaderboard and label it **“Catalog competitors.”** Do not present an unchanged catalog leaderboard as a product-specific one. Recommended: relevant-answer comparisons, calculated locally from the same saved scan; flag this as additional work beyond merely preserving the drawer renderer.

If the rescan action remains on product detail, label it **“Run catalog scan”** so the merchant understands its scope. It must not restart separate paid scanning for that product.

### 8. Answers and Mentions & Citations

**Answers:** readable saved answers with question, group, date and matching product references. At catalog level, highlight all matched own products. At product level, highlight the selected product. Recommended default is all relevant answers, including those that did not mention it, with a “Mentions this product” filter. Filtering only to positive mentions hides the evidence behind a low score.

**Mentions & Citations:** keep the existing count-led panels. Counts are the explicit exception to percentage-led visibility reporting. Product detail must distinguish citations of that product’s page from brand/domain citations; a link to the store homepage does not prove that the selected product was cited. All values follow the period filter.

Clicking a citation opens its original source. Reading a saved answer, opening citations or switching views does not call an AI model.

## Appearance and responsive behaviour

Reuse the current styling: navy `#0b1b35`, white dashboard panels, light dividers, Geist type and restrained corners. Keep the dashboard’s current roughly equal chart-panel columns, 22px gaps and 16px card corners. Titles remain modest; the visibility number and chart carry the hierarchy. The catalog table has thin row separators, no border around every cell and a subtle hover state.

Green indicates a rising measured trend and red a falling measured trend, always with readable change text. Changes should be expressed in percentage points. Product rows do not become red simply because they have never appeared. Uncertainty should be legible beside the metric, not buried inside a tooltip.

On phones, the chart precedes Share of voice in one column. Product rows become stacked summaries with the same measurements and an explicit product link. Keep controls touch-friendly, preserve all filters and avoid horizontal page scrolling. Onboarding’s form comes first, with the illustration below. Respect reduced-motion settings throughout.

## Honest result states

| Situation | What the interface says or does |
| --- | --- |
| No scan in selected period | “No scans in this period”; values show em dashes. No fabricated zero. |
| First valid scan | One measured endpoint. Preserve the approved dashed illustrative lead-in from “not measured”; no trend-change claim. |
| Relevant answers exist, product absent | Real 0% mention rate; average position is an em dash. Keep the product visible. |
| No relevant questions cover a product | Proposed “Not covered” state, not 0%. |
| Product type excluded | “Excluded”; no visibility result implied. |
| Partial scan | Amber warning next to the affected metrics and in scan history: “Partial scan — some answers could not be collected.” Do not treat it as fully comparable. |
| Failed scan | Clear failure message and retry action; previously saved results remain available with their own dates. |

The first-scan illustration is never saved as historical data. Raw answers remain append-only. Measurement-noise guidance must use the actual relevant answer base; it is not a statistical confidence interval unless separately justified.

## What makes it cheaper

The saving comes from asking shared questions once per scan and checking each answer against the catalog. An answer that names several own products can inform several product dashboards. This avoids buying overlapping questions separately for every product.

The quoted **~$51/month is an unvalidated scenario**, not a measured operating cost or launch promise. It combines an assumed cluster count, a reduced repetition count, a fortnightly cadence and multiple engines. The MVP itself is ChatGPT-only. The retained configuration still uses five repetitions; moving from five to three reduces that part of the workload by 40%, not half. The source documents also contain inconsistent old-design totals. Do not put any of these monthly numbers on the customer interface or pricing page.

Recommended internal view for Kelian: scan date, status, recorded usage by model, estimated provider spend using dated rates, and a monthly projection based on an explicitly chosen cadence. Label the cost as an estimate until reconciled with billing, and include helper calls and failed-call spend where observable. A maximum scan budget would be a useful additional safeguard, but it is an addition for approval, not already provided by this spec.

## Decisions to settle before implementation

1. **Product relevance and coverage — recommended addition.** Persist which questions apply to which products before the first scan, and freeze that mapping alongside the question set. Relevant successful answers are the product denominator, including answers where the product is absent. Otherwise the system can dilute a cleanser’s visibility with unrelated questions or make 0% indistinguishable from lack of coverage. The spec’s target schema currently has no place for this mapping.
2. **Catalog scope over time — recommended addition.** Persist excluded types and the measured product set with the baseline. New products or categories should not silently rewrite old comparisons. Show new categories as not covered until a separately designed baseline-change flow exists; do not bypass the frozen-question rule.
3. **Scan cadence — still your decision.** The earlier automatic weekly requirement and the new fortnightly cost scenario conflict. I recommend proving one catalog scan’s coverage and cost first, then choosing the automatic cadence. Do not ship a schedule claim based on the illustrative cost table.
4. **Question generation target — still unvalidated.** Let real category coverage drive the configurable count. A question per cluster and a grouping of several questions per category are not quite the same thing; clarify the terminology internally without exposing recipe counts in the UI.
5. **Boundary statuses — clarify in the spec.** “More than half” and “less than half” leave exactly half successful unspecified. Recommended: exactly half counts as failed; partial results require more than half. Also distinguish answer collection from extraction failures before publishing product scores.
6. **Small spec contradictions — resolve consistently.** Use Store → Brand → Catalog → Questions despite its “step 2” wording. Create zero-mention product result rows, as its verification section requires, despite the earlier “at least one mention” scoring sentence. Keep ordinary question totals out of the UI even though the generation section says to show the chosen count.

The report’s recommended additions are review items, not silently accepted changes to the implementation spec.

## Approval scope

Approve or revise: the catalog-first dashboard; the preserved visual direction; category exclusions during setup; product drill-down using shared results; and the proposed coverage distinction. Separately settle the measurement mapping and automatic scan cadence before implementing their dependent behaviour.

The accompanying interactive preview illustrates catalog confirmation, the catalog dashboard and product drill-down using explicitly fictional product labels and unmeasured states. It contains no claimed scan results. The live MVP, database, question sets and website were not modified, and no paid visibility scans were run.
