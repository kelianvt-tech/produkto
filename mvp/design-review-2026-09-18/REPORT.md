# Produkto dashboard design review

18 September 2026 · Internal review · Recommendations, not implemented changes

## Recommendation

Keep Produkto’s navy identity, white cards, soft background and recently approved muted chart palette. The largest improvement will come from making the primary chart larger, making every comparison’s scope obvious, and reducing the amount of small text and repeated information. Another colour experiment will have less impact than these changes.

PromptWatch’s supplied screenshots work because the chart occupies the space, values and brand identities are easy to connect, and the metric selector belongs visually to the chart. Borrow those principles while keeping Produkto centred on six selected products.

## What was inspected

- Live Produkto Overview, Answers and Mentions & Citations for the saved Clubhouse Skin scan, at 1135px desktop width. Overview also captured at 390px mobile width.
- The supplied PromptWatch screenshots showing the metric strip, comparison bars and date tooltip. These are the visual reference, not evidence of its full application behaviour.
- Relevant local chart code to confirm interaction and date-axis behaviour.
- A Firecrawl scrape of [the requested PromptWatch dashboard](https://app.promptwatch.com/molivings/molivings?chartType=bar) returned its sign-in page. The existing-browser connection also failed. **The authenticated dashboard was not scraped successfully.** Unseen PromptWatch navigation, settings, onboarding and responsive behaviour are outside this comparison.

No scans, paid model calls, account changes or MVP design changes were made. The local bar view rendered six bars without browser errors. Mobile had no horizontal page overflow; this does not establish readability or full accessibility.

## Highest-priority changes

### 1. Make the primary chart the main visual

**Observed:** The desktop plot is small inside a tall half-width card. The six bars occupy a shallow band, surrounded by substantial blank space. Axis labels and brand names are much smaller than the surrounding interface. PromptWatch’s reference devotes considerably more of the available area to its plot.

**Change:** Combine the metric strip and primary chart into one full-width analysis card. Place rankings below, beside the share-of-voice panel. Aim for a 280–320px desktop plot height, with labels rendered at 12–13px minimum at actual screen size. Use responsive chart dimensions rather than shrinking a fixed drawing and all its text together. Remove the large central watermark from the working dashboard: it competes with the marks without helping interpretation.

**Done when:** Six brand names and values are readable without zooming at 1135px; the plot fills its card naturally; the selected metric visibly controls the chart immediately beneath it.

### 2. Make comparison scope explicit

**Observed:** The bar chart names brands, the trend legend names individual rival products, the rankings list products, and the donut combines “Catalog overview” with individual competitor products. The bars currently describe competitors as brands ChatGPT named most. That is different from the requested selected-six-versus-selected-six comparison.

**Change:** Use two explicit labels: “Your six vs selected competitors” for saved comparable catalogues, and “All products mentioned” for wider discovery results. Show the selected brand name plus “6 selected products” in the catalogue comparison. Keep wider market evidence available below or in details. Never present a historical scan without saved selections as if those selections existed.

For share of voice, explain the denominator beside the title or in a short accessible tooltip: either all product recommendations, or only the two selected six-product groups. Label catalogue totals as catalogue totals; avoid a catalogue total appearing to be one ranked product.

**Done when:** A reader can identify what is compared and what the percentage means without opening methodology. The same brand/product scope stays consistent when switching metrics.

### 3. Finish the metric-switching interaction

**Observed:** Selecting Visibility displays comparison bars but retains “Weekly” and the footer about needing two weeks for a trend. The chart heading remains generic “Visibility”. The bar implementation uses native SVG title tooltips rather than the structured date tooltip used by the trend.

**Change:** Update the title, caption, accessible chart name and footer together for each mode. Use “Visibility over time”, “Visibility by competitor”, “Share of voice by competitor” and “Average position by competitor”. Only show trend instructions in the time view. Give bars a compact tooltip with brand, metric, value and scope, accessible by pointer, keyboard and tap.

**Done when:** All four selectors produce a coherent title, chart and explanation; no stale trend copy remains on bars. Hover details are equally available to keyboard and touch users.

### 4. Improve text size and numerical consistency

**Observed:** The headline share of voice rounds to 5%, while the donut shows 4.9%. Ranking headings, chart ticks, source notes and badges are very small. The MVP is clean but the supporting information is harder to read than it needs to be.

**Change:** Use one decimal for share of voice consistently across the headline, donut and related details. Use one decimal for average position and a consistent visibility precision. Set body/table text to 13–14px, secondary labels to 12px minimum, card titles to 14–16px and headline values to 28–32px. Keep numbers aligned with tabular numerals. Check text contrast against its actual background; keep pale colours for fills, not small labels.

**Done when:** Identical metrics appear with identical precision and supporting text can be read at normal zoom. Validate contrast and focus states rather than relying on palette appearance alone.

## Next changes

| Priority | Finding | Recommended change | Completion check |
|---|---|---|---|
| High | First-scan information is repeated in several places. | One short chart caption: “First reading · your trend will build as you scan.” Keep real points and dates; do not add illustrative history. | One clear explanation, no fabricated movement. |
| High | The trend implementation filters out empty buckets before spacing dates equally. Missing weeks can therefore collapse visually. | Preserve calendar spacing and show gaps or clearly indicate unmeasured periods. | A test history with a missed week leaves a visible time gap. |
| Medium | Position is presented with bars; the metric switch draws inverted rank bars, which take effort to interpret. | Use a ranked dot plot or a simple ordered list with “1 = first”. Keep missing recommendations as “—”, not a poor invented position. | Better and worse positions are understandable without decoding bar direction. |
| Medium | The palette now matches the requested restraint, but other panels use different colour systems. | Preserve the approved muted bars and navy controls. Define stable colours within each comparison context, tied to identity rather than current rank. Maintain the approved brighter trend series as a deliberate exception. | Sorting or rescanning does not arbitrarily change a competitor’s colour. |
| Medium | Product rankings mix product photos, logos and initials. Initials sometimes remain visible around small logos. | Standardise one image tile size, fallback treatment, baseline and padding. Distinguish product photo from brand logo without overlapping both. | No double identity marks; long names wrap cleanly and numerical columns align. |
| Medium | Catalogue wording still contains single-product remnants. | Replace “Check another product” with “Switch catalog”; “Where ChatGPT links when discussing Catalog overview” with “Where ChatGPT links to your products”; “your catalog products page” with “your product pages”. | Catalogue pages consistently refer to products or the catalogue, not a fictional product named Catalog overview. |
| Medium | The citations page repeats the same own-page count in the top card and the detailed section. | Keep the top metric, make the lower section a source breakdown, and label the second series “Other listings of your products”. | Each section adds information instead of restating the headline. |
| Medium | A brand field in the extracted share-of-voice detail contains `about:blank`. | Validate display identity fields and show “Brand unavailable” when a name is invalid. Preserve the underlying evidence for review. | Technical placeholders never appear as competitor names. |
| Medium | The mobile overview is approximately 8,873px tall, despite having only six merchant products. | Use compact product summaries with expandable details; show a short buyer-question preview with a clear route to the full list. Keep key metrics and comparison near the top. | A merchant reaches their six-product summary without traversing every secondary panel. |
| Lower | The overview exposes detailed measurement text between prominent sections. | Put methodology and sensitivity details in one consistent disclosure, while retaining essential comparison-scope captions. | Main reading order remains result → comparison → products → evidence. |

## Proposed desktop order

1. Compact store identity, “Catalog overview” and Run catalog scan.
2. Existing navigation, then date range and grouping in one consistent toolbar.
3. Full-width analysis card: clickable metric strip, substantial chart, concise scope/first-reading caption.
4. Saved six-product competitor comparison, when available; avoid duplicating it if it already supplies the primary chart.
5. Product rankings and share of voice, with explicit scope labels.
6. Your six products, with coverage and a route to evidence.
7. Short buyer-question preview; detailed questions and methodology available on demand.

On mobile, stack the same sequence, retain readable labels and use compact expandable rows. Do not simply reduce the desktop chart and its typography proportionally.

## Visual specification to keep

| Element | Direction |
|---|---|
| Primary controls, selected navigation, headings | Logo navy `#0b1b35` |
| Page background | Existing faint cool/warm glow; no decorative grid |
| Cards | White, subtle neutral border, consistent 12–16px corner radius |
| Comparison bar fills | Soft blue `#c5d1f7`, grey `#d5d5d5`, blue-grey `#c3d2e5`, restrained green `#2f966d` |
| Time-series marks | Existing approved blue, deeper blue, green and grey |
| Chart guides | Faint horizontal dotted rules only where useful |
| Spacing | Consistent 8px steps; approximately 20–24px card padding on desktop |
| Motion | Short transitions on meaningful changes; respect reduced motion |

These are proposed implementation targets, not measurements extracted from PromptWatch’s private styling.

## Recommended implementation sequence

**Pass 1 — clarity and composition:** larger unified chart, scope labels, correct metric-switch copy, consistent precision and catalogue wording. This should deliver the most visible improvement.

**Pass 2 — interaction and detail:** structured bar tooltips, date-gap behaviour, position representation, consistent image fallbacks and compact mobile summaries.

**Pass 3 — verification:** inspect desktop at 1135px and 1440px, mobile at 390px, keyboard operation, long brand names, zero results, first scan and real multi-period history. Confirm that presentation changes do not alter saved results or their denominators.

Do not add sentiment, personas, extra model dashboards or decorative widgets solely because a competitor has them. They do not solve the current readability and comparison problems.

## Evidence files

- [Current desktop comparison bars](overview-desktop.png)
- [Full overview, time view](overview-full.png)
- [Mobile overview](overview-mobile.png)
- [Answers](answers-full.png)
- [Mentions & Citations](citations-full.png)
- [Local inspection text and mobile overflow result](inspection.json)

The supplied PromptWatch images remain in the conversation. Authenticated PromptWatch access is still needed to extend this into a full navigation and interaction comparison; this report does not imply that work was completed.
