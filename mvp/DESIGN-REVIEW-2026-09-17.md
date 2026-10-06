# Produkto dashboard: design review

17 September 2026 · Report only · Scope: `mvp/app/`

## Recommendation

Keep Produkto’s navy, light background and restrained typography. Change the information hierarchy: put the headline numbers together, make competitor comparisons easier to read, and connect every result to its supporting answers. Searchable is the stronger layout reference; Promptwatch supplies useful examples of connecting metrics, competitors and evidence.

The main problem is not missing decoration. Produkto currently gives a large first-scan empty trend panel more space than the evidence explaining its score. Its most valuable verification screen is reached through a small footer link.

## Evidence and limits

- **Searchable:** inspected the supplied dashboard screenshot and scraped its official [visibility page](https://www.searchable.com/features/aeo-insights/visibility), including its public dashboard example. The screenshot shows the actual reference layout; the website example corroborates its structure.
- **Promptwatch:** scraped the official [homepage](https://promptwatch.com/) and [prompt-tracking page](https://promptwatch.com/features/prompt-tracking). These expose public examples of metric summaries, competitor rankings and citation tables. A published dashboard image was located, but could not be visually inspected through the available browser tools. Exact Promptwatch spacing, typography and live interaction behaviour are therefore not verified.
- **Live accounts:** both application URLs returned sign-in pages to the scraper. Browser control failed before it could inspect existing signed-in tabs. This is a public-reference comparison, not a completed scrape of either private account.
- **Produkto:** inspected the current dashboard and answer-page code, its layout rules, and the saved Frontier Cleanser scan. The local answers page was successfully fetched during the preceding review. No fresh visual browser inspection was possible in this review.

Recommendations below are design judgments, not claims that either competitor has proven conversion benefits. Public demo numbers are not benchmarks for Produkto. Current MVP instructions supersede the older project brief’s no-interface scope.

## What to take from the references

| Reference | Observed pattern | Application to Produkto |
|---|---|---|
| Searchable screenshot | Broad two-column workspace; aligned panel headers and thin borders | Use more desktop width and a consistent panel structure |
| Searchable screenshot | Tabs above a separate filter row | Keep page navigation separate from scan context and actions |
| Searchable screenshot and public example | Rankings bring several comparable measures into one table | Show competitor names, appearance rate and position together with explicit labels |
| Searchable screenshot | Own brand has an identifiable marker; chart tooltip names the selected entity | Keep the selected product recognizable everywhere |
| Promptwatch public prompt-tracking example | Visibility, mentions and rank presented as a compact group | Put the key measures on a single summary row |
| Promptwatch public prompt-tracking example | Source table connects source, prompt and source type | Make answers and supporting source links accessible from the question that produced them |

Use these patterns selectively. Searchable’s large blank average-position panel wastes room in the supplied screenshot. Its many filters serve a broader platform. Produkto currently has one product and one engine, so copying every control would add noise. Keep horizontal share-of-voice bars: product names and close percentages are easier to compare there than around a donut.

## Priority 1 — Change the main dashboard hierarchy

### 1. Put the main numbers in one compact row

The current 64px visibility number sits beside a trend panel occupying two-thirds of the row. Supporting metrics are stacked underneath it.

Replace that arrangement with four aligned metric blocks, preferably in one shared band with subtle dividers:

| Visibility score | Appears in answers | Average position when named | Share of recommendations |
|---|---|---|---|
| **20 / 100** | **20%** | **1.0** | **7.0%** |

These are actual values from the saved Frontier Cleanser scan. Label visibility as a score out of 100, not a percentage. Keep its short explanation available: “How often your product appears, weighted by its position.” Do not add sentiment, revenue or traffic numbers without corresponding measurements.

### 2. Make the product and scan context persistent

Use a compact top row with the product thumbnail, Frontier Cleanser, Clubhouse Skin, scan date and a readable “ChatGPT · web search” label. Put “Run new scan” at the right, separate from navigation. Keep the API measurement explanation visible but secondary.

Add two clear destinations: **Overview** and **Answers**. Within Overview, link directly to **Buyer questions**. This is enough navigation for the current product; a full sidebar is unnecessary.

### 3. Reclaim space on the first scan

For one saved scan, use a short “First scan saved — run another scan to compare” strip. The current empty trend container is 200px tall before its heading and padding, and occupies the widest panel.

Once multiple scans exist, show the trend at a useful size, with actual scan dates, values on hover and a text alternative. Do not invent daily points or show a growth indicator before a comparison exists. Retain the restrained green treatment for a rising trend and respect reduced-motion settings.

## Priority 2 — Make comparison tables unambiguous

### 4. Separate product comparison from brand comparison

The current Positioning table mixes the selected product with competitor brands. A brand can represent several products, so these rows do not measure the same thing.

Keep two explicitly labelled panels:

- **Recommended products:** horizontal share-of-recommendations bars, full product name, brand below it, and the selected product highlighted in navy. Preserve its true rank; if pinned for convenience, label that separately from rank.
- **Brand presence:** brand-only rows with appearance rate and average position. Identify “Your brand” separately from “Your product.” This requires aligning the displayed rows with the appropriate stored brand calculations, not simply renaming the existing table.

Allow product names to wrap to two lines. Current share-of-voice labels are forced onto one line and cut off with an ellipsis, which can hide the distinguishing words between similar products. Keep numeric columns right-aligned with consistent decimal precision.

### 5. Promote buyer questions into useful evidence

Use a full-width table with **Buyer question**, **Product appearance**, **Average position**, and **View answers**. Each row should lead to only that question’s responses, preserving the selected scan.

Add a short factual scan takeaway above the table. For the current scan: “Your product appeared for the question naming its ingredient combination; it did not appear for the other questions.” This explains the aggregate result without implying those questions represent measured buyer demand.

The “around 39” ambiguity found during review belongs in a question-quality note, not a product-performance warning. Do not silently edit frozen questions or mix a corrected question set into the existing trend.

## Priority 3 — Turn the answers page into a readable review screen

### 6. Replace repeated collapsed question headings with a browser for answers

Today, every response is a separate collapsed detail row. Opening it reveals a comma-separated “Read as” list above raw text. This makes comparison laborious and exposes Markdown punctuation and long URLs as ordinary text.

Proposed behaviour:

1. Select a buyer question from a list or dropdown.
2. See response rows with scan time and a plain result: “Your product recommended”, “Brand only”, or “Not recommended”.
3. Open a response to see the readable answer on the left and an ordered **Products identified** list on the right.
4. Show supporting source links below the answer. Keep **Original text** available for verification.

Use a small “Your product” label next to the exact matched item. Retain names and ranks, and avoid colouring an entire answer green when only one recommendation belongs to the user. Add a search field and filters for ownership status if needed; no new AI calls are necessary to browse saved results.

Readable answer formatting must be escaped safely: render only supported Markdown structures and safe links, never execute answer-provided HTML. On narrow screens, stack the identified products below the answer. This work includes interaction and rendering changes, not only styling.

## Visual specifications for implementation

These are proposed Produkto values, not measurements copied from Promptwatch.

| Element | Proposed treatment |
|---|---|
| Desktop content | Maximum width around 1360px, 24–32px outer gutters; current maximum is 1080px |
| Layout | Two equal columns for comparisons; full width for questions; four summary columns on wide screens |
| Small screens | Two summary columns on tablets, one on phones; comparison panels stack |
| Spacing | 16–20px panel gaps; 20px content padding; consistent 8px spacing increments |
| Cards | White, 1px neutral border, 12px corners; avoid nested decorative cards |
| Panel headers | Common height and alignment, title left, relevant action right, thin bottom divider |
| Typography | Keep Geist; page title 26–28px, metrics 32–36px, body/table 14–15px, secondary labels 12–13px |
| Colour | Keep existing navy and warm light background; neutral competitor bars; green only for actual positive change |
| Table rows | Roughly 44–48px minimum; allow height to grow for wrapped product names |
| Interaction | Visible keyboard focus, clear hover states, text labels for unfamiliar icons, keyboard-accessible details |
| Missing data | “Not named” or “No completed answers”, as appropriate; never imply missing data is zero |

Do not reduce label contrast to match Searchable’s palest text. Important values, controls and chart data must remain legible. Validate body text at 4.5:1 contrast, and ensure state is communicated by words as well as colour.

## Proposed page order

```text
Product image · Product name · Brand                  Run new scan
Overview | Answers                  Scan date · ChatGPT · web search

Visibility /100 | Appears in answers | Avg. position | Recommendation share

First-scan note — or a real trend chart when history exists

Recommended products                 Brand presence
[ranked horizontal bars]             [clearly labelled brand table]

Buyer questions
[question · appearance · position · view answers]

Measurement details
```

## Implementation order and acceptance checks

**First pass:** widen the workspace, create the compact product header and metric band, standardize panel headers, and shrink the first-scan empty state. Most of this is presentation work in `mvp/app/app.py`.

**Second pass:** add direct question-to-answer navigation, ownership filters and readable answer formatting. Separate brand and product table calculations wherever needed; preserve the raw answers.

**Later:** date filtering when useful history exists, sortable larger tables, source aggregation and export. Sentiment, multiple engines, automatic scans and content agents are additional product work, not prerequisites for a polished dashboard.

Acceptance checks:

- At 1440px, the product context and all headline measures are visible together without scrolling.
- At 375px, product names and values remain readable; the page does not overflow horizontally.
- A buyer question opens its matching answers in one action.
- A user can distinguish score, appearance rate, recommendation share, product and brand without guessing.
- First-scan, zero-appearance, missing-answer and multi-scan states all have deliberate layouts.
- Keyboard navigation and reduced motion work; long product names and long answers remain usable.
- Styling changes preserve the stored scan values and never trigger a new scan just to navigate.

## Sources saved with this report

- [Searchable screenshot](design-research/2026-09-17/searchable-reference.png), supplied by the owner.
- [Searchable visibility scrape](design-research/2026-09-17/searchable-visibility.md).
- [Searchable homepage scrape](design-research/2026-09-17/searchable-home.md).
- [Promptwatch homepage scrape](design-research/2026-09-17/promptwatch-home.md).
- [Promptwatch prompt-tracking page](https://promptwatch.com/features/prompt-tracking), retrieved 17 September 2026.
- Current implementation: `mvp/app/app.py`; [first scan review](app/SCAN-REVIEW-2026-09-17.md).

No dashboard code, store data, saved answers or old prototype files were changed during this review.
