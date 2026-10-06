# Mentions & Citations — design review and implementation

21 September 2026. Reference: the three supplied PromptWatch screenshots. This is a review of the visible interface, not a claim about PromptWatch's underlying calculations.

## Assessment

Produkto already showed product-mention trends, product-page citation trends, a domain table and a short list of citations associated with the merchant's products. The missing part was an easy way to inspect **every cited source** and compare where the engines draw their answers from.

The reference makes this easier through a domain chart paired with citation share, followed by a compact source table. Those patterns have been implemented while retaining Produkto's product-level evidence and navy/soft-blue styling.

| Reference feature | Produkto implementation |
| --- | --- |
| Domain trends beside citation share | Shared card with Over time / Top domains modes; merchant domains pinned first, then the leading domains, up to seven |
| Domain logos and coloured series | Cached site icons, consistent series colours, hover highlighting and click-to-lock focus |
| Citation-share percentages and changes | Domain citations divided by all matching citations; change in percentage points between the last two measured periods, when both have citations |
| Search and filters | Search URL/title/product; source relationship, inferred content type, domain and product-link filters |
| URL table | Saved title, URL, associated product names, source, content type, model logo, source order, date and original-answer link |
| Pagination and export | 25 citations per page; date/source-order sorting; CSV of all filtered citations |
| Product-level relevance | Distinguishes your product page, another listing of your product, and other sources; product views follow their relevant questions |

Product mentions and product citations remain separate from the domain comparison. A general article cited by an engine is not automatically evidence that it mentioned or cited the merchant's product.

## What the existing evidence says

For the saved Clubhouse Skin catalog view, last 30 days, all engines, on this review date:

- 229 processed answers contain 1,742 citation occurrences across 327 domains.
- ChatGPT supplies 464 citations, Perplexity 1,011, and AI Overview 267.
- 10 occurrences link directly to selected product pages. Another 3 link to listings matched to those products in the same answer.
- The other 1,729 source occurrences are not confirmed citations to the selected products.
- aad.org is the most cited domain: 151 citations, about 8.7% of the total.

An occurrence means one normalized URL per answer. A URL cited by ten answers counts ten times; repeated annotations of the same URL in one answer count once. These are source counts, not unique pages, visits, revenue or search demand. Engines can return different numbers of sources per answer, so a larger citation total does not establish better product visibility.

## Accuracy decisions

1. **Source is a relationship, not an invented publisher category.** The table says Your site or External site. The saved records do not establish whether an external source is corporate, news media or a blog.
2. **Content types are inferred and labelled as such.** Conservative URL patterns and exact saved product matches identify Product, Review, News, Article, Collection or Homepage. Unclear sources remain Unclassified. No pages were crawled to classify them.
3. **Source order is not rank.** The stored citations have an order but no verified citation-placement metric. The column explicitly names the saved source-list order; it does not reuse the recommended product's position.
4. **Missing readings are not zeroes.** A bucket with processed answers and no citations to a domain is zero. A bucket without a measurement has no point. Dashed connections span unmeasured gaps; the chart data table states No scan.
5. **All citation-explorer views use the same filtered records.** Its chart, share list, table and CSV agree. Global period, engine and product scope apply first. The separate product-mention and product-citation summary charts continue to follow the global filters.
6. **Other-product-listing attribution is answer-specific.** Fixed an existing issue where a URL matched to the merchant's product in one answer could qualify as a product citation in unrelated answers. Each other-listing citation now needs a matching recommendation in that same answer.
7. **History remains within the saved prompt version.** Adding prompts does not retroactively change these results.

## Validation

Automated checks cover normalization/deduplication, invalid URLs, same-answer product attribution, engine/date/processing scope and safe embedded titles. Browser checks cover pagination, chart switching, keyboard tooltips, source filters, empty results, CSV download, original-answer links, engine filtering and mobile overflow. Desktop and mobile screenshots were inspected. All 62 automated tests pass.

No new scan, extraction or paid model call was required. Saved answers and recommendations were not rewritten. Publisher taxonomy and verified citation placement would require additional evidence before they could be presented as facts.
