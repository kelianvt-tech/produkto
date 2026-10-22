# Third-party data pull, 21 Oct 2026

Pulled with Produkto's Apify account (key in `mvp/app/.env`) for Clubhouse Skin and 5Strands. **Cost: $2.31** in total. App, server and database untouched; these files are the only output.

| File | What it is | Scraper | Cost |
|---|---|---|---|
| `google-shopping-clubhouseskin.com.json` | Google Shopping top 20 for each of Clubhouse's 11 buyer questions, searched from the UK | `epctex/google-shopping-scraper` | $0.72 |
| `google-shopping-5strands.com.json` | Same for 5Strands' 22 questions, searched from the US (19 returned results) | same | $1.56 |
| `google-offsite-mentions.json` | Google results (2 pages) for 8 brand and product searches, own site excluded | `apify/google-search-scraper` | $0.04 |
| `trustpilot.json` | Trustpilot reviews for both domains | `automation-lab/trustpilot` | $0.005 |

The buyer questions were searched word for word. ChatGPT's own behind-the-scenes searches are probably shorter, so treat the Shopping comparison as rough.

## What it shows

**1. Google Shopping and ChatGPT pick different products here.** Of the products ChatGPT named most for each question, 29 of 88 (33%) for Clubhouse and 4 of 25 (16%) for 5Strands also appeared in Google Shopping's top 20. Peec AI's study reported 83%. Our matching is rough (product names compared word by word) and our scraper reads ChatGPT's written answer rather than its product carousel, so this doesn't disprove Peec. It does mean **ranking in Google Shopping alone didn't get these brands named.**

**2. 5Strands is all over Google Shopping and still rarely named by ChatGPT.** It holds positions 1–5 on 15 of 19 questions, often several of them, through its own store, Walmart, Amazon and eBay. ChatGPT named it in 2 of 57 answers to the broad questions. **Guess:** for health tests, AI prefers clinics and lab brands (Everlywell, Labcorp) and medical sources, and hair-based intolerance testing is disputed. Some of 5Strands' press is negative: a TV news "put to the test" piece, an Amazon video titled "Regret Your Life Choices", and a sceptical Rover article.

**3. 5Strands' own numbers disagree across channels.** The same food test is listed as "640 items", "800+ foods", "955", "1030" and "1250 items" depending on the listing and the pet or human version. **Guess:** conflicting facts make AI less likely to repeat any of them. This is a fix the feed skill should catch: one product, one set of numbers, everywhere.

**4. Clubhouse is missing from Google Shopping entirely.** Its only appearance is an eBay resale listing at position 17. It probably has no Merchant Center or free listings set up. That's a free fix, and the feed skill's first check.

**5. Clubhouse is stocked by many shops but nobody reviews it.** Retailers carry it (Goodhood, FWRD, Earl of East, Amniki, Kings Cross, Myza, Kleonne, Solefeed, Calm Era, Editorialist, ModeSens), but there were no review articles, no forum threads and no Trustpilot page. Google also confuses the name with *Clean Skin Club* and a med spa called *ClubHouse Skin and Laser*. Each retailer page is a third-party source AI can cite (Myza already is). Reviews and editorial coverage are the gap.

**6. 5Strands has a lot of earned coverage of mixed quality.** Walmart, Chewy and Amazon review pages, about 10 Facebook group threads ("Has anyone tried…"), review blogs (essentialmedicalkitreviews, nebula.org, littledogtips, thepetpicks, pethub), YouTube, Reddit and JustAnswer. Trustpilot: only 2 reviews, a 3.2 score, and the latest complains about slow results.

## How the agent should use this (proposed, not built)

- **Feed skill:** check that the store appears in Google Shopping for its questions (Clubhouse: no), and that facts are the same on the site, the feed and marketplaces (5Strands: no).
- **Citations skill:** start from the off-site pages already found. Ask stockists to carry the full fact set and to show reviews. For 5Strands, answer the sceptical coverage with sources the brand has (lab, method), never by disputing it.
- **Reviews skill:** a brand with retailers but no reviews (Clubhouse) needs review requests first. A brand with complaints (5Strands' turnaround time) needs that answered on the product page.
- **Diagnose skill:** note the brand-name collision for Clubhouse, so the agent doesn't count Clean Skin Club pages as coverage.
