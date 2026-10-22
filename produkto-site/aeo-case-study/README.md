# Produkto's own AI visibility (case study)

Does doing AEO on getprodukto.com change whether AI names Produkto? Measured on the buyer questions in `questions.txt`, on ChatGPT, Google AI Overviews and Perplexity, via the app's Apify actors (~$0.20 a run).

Since 2026-10-22 the server runs this every Monday by itself (`mvp/app/self_visibility.py`, timer `produkto-self-vis.timer`) and the admin page shows it. `python3 track.py` still works for a manual run → `results/<date>.md` (summary) and `.json` (raw answers).
Keep `questions.txt` stable; add new questions at the bottom, never reword old ones.

## Change log

| Date | Change |
|---|---|
| 2026-10-20 | **Baseline taken before any change.** Named in 0 of 28 answers, cited 0 times. Tools AI named most: Profound (11), Peec (9), Ahrefs, Otterly, Semrush (8 each), Scrunch, Yotpo (6). |
| 2026-10-20 | Deployed after the baseline: robots.txt, sitemap.xml, llms.txt, JSON-LD (Organization, SoftwareApplication, FAQPage) on home + pricing, canonical tags, pricing meta description fixed. |
| 2026-10-20 | Published guide: /what-is-ai-shopping-visibility (definition page, Article + DefinedTerm + FAQPage schema). |
| 2026-10-20 | Footer "Guides" link on every page, /guides index page, guide build script (`../guides-src/build.py`). |
| 2026-10-20 | Published guide: /check-if-ai-recommends-your-products (step-by-step manual check, Article + FAQPage schema). |
| 2026-10-20 | Guides redesigned (AndromedAI-style layout, navy hero), 6 sourced stats added (Adobe, McKinsey, Pew), each checked against its original source. |
| 2026-10-20 | Published research: /how-ai-recommends-products-856-answers (anonymised Produkto data, one UK skincare brand, 856 answers Sep 18–Oct 8 2026; source DB snapshot mvp/app/produkto.db.server-copy of Oct 20). |
| 2026-10-20 | Published comparison: /best-ai-visibility-tools-for-ecommerce (11 tools, prices checked on each vendor's own page Oct 20; targets the 3 'tools' baseline questions). |
