"""Shared content for the guide design variations: same facts as the live
'What is AI shopping visibility?' guide, so only the design changes."""

TITLE = "What is AI shopping visibility?"
DEK = ("Shoppers now ask AI what to buy and get a few named products back. "
       "What AI shopping visibility is, how it differs from SEO, how to measure it, and what you can work on.")
DEFINITION = ("AI shopping visibility is how often AI assistants like ChatGPT, Google AI Overviews and Perplexity "
              "name your products when a shopper asks what to buy.")
DEFINITION_MORE = ("It is measured per product, on the questions your buyers actually ask, and compared against "
                   "the competing products AI recommends instead.")
AUTHOR = "Kelian Van Tulder"
DATE = "October 20, 2026"

POINTS = [
    "Shoppers now ask ChatGPT, Perplexity and Google what to buy. They get back an answer that names a few products, not ten blue links.",
    "A product that isn't named in that answer is never considered. There is no page two.",
    "AI shopping visibility is the share of those answers that name your product, measured per product, on the questions your buyers actually ask.",
    "Answers change from one run to the next, so it is measured across many answers and tracked over time, not checked once.",
    "It is also called AEO, GEO, AI search visibility or LLM visibility. “Shopping” narrows it to the thing a store sells: products.",
]

AD = "https://business.adobe.com/assets/pdfs/resources/sdk/ai-traffic-trends-report-august-2026/ai-traffic-trends-report-2026-08-19.pdf"
AH = "https://business.adobe.com/resources/holiday-shopping-report.html"
MK = "https://www.mckinsey.com/capabilities/growth-marketing-and-sales/our-insights/new-front-door-to-the-internet-winning-in-the-age-of-ai-search"
PEW = "https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/"
# value, sentence, source name, url, numeric (for charts) or None
STATS = [
    ("42%", "of consumers have used AI assistants for online shopping, up 4 points since March 2026.", "Adobe Consumer Survey, July 2026", AD, 42),
    ("+127%", "year-over-year growth in AI-driven traffic to US retail sites in August 2026.", "Adobe Digital Insights", AH, None),
    ("60%", "higher conversion rate for AI-referred retail visitors than for non-AI traffic, July 2026.", "Adobe Digital Insights", AD, None),
    ("~50%", "of consumers already use AI-powered search.", "McKinsey", MK, 50),
    ("$750B", "in US revenue projected to flow through AI-powered search by 2028.", "McKinsey projection", MK, None),
    ("8% vs 15%", "of Google visits led to a click on a search result when an AI summary appeared, versus without one.", "Pew Research Center, 2025", PEW, None),
]

SEO_ROWS = [  # label, SEO, AEO/GEO, AI shopping visibility
    ("Goal", "Rank pages in search results", "Be quoted or cited in AI answers", "Be one of the products AI recommends"),
    ("Where", "Google, Bing", "ChatGPT, Perplexity, Google AI Overviews, Gemini", "The same assistants, on shopping questions"),
    ("Unit", "A web page", "A piece of content or a brand", "A single product"),
    ("Metric", "Rankings, clicks", "Mentions, citations", "Share of answers naming the product, position, share of voice"),
    ("Stability", "Rankings move slowly", "Answers vary by run", "Answers vary by run, so it’s measured repeatedly"),
]
SEO_RULE = ("SEO asks whether a page is relevant to a search. AI shopping visibility asks whether a product gets named "
            "when a shopper describes what they need.")
SEO_PARA = ("Strong SEO still helps. Assistants with web search read the same pages search engines rank. But a page can rank "
            "well and still leave out the details an assistant needs to match the product to a specific need, like who it "
            "suits, what it’s made of or what it can’t do.")

STEPS = [
    ("The shopper asks with a need", "“A waterproof jacket for hiking in heavy rain, under $250.” One question carries a category, a use, a condition and a budget."),
    ("The assistant searches", "It runs one or more web searches built from the question. Google describes running several related searches at once for AI Mode."),
    ("It reads sources", "Product pages, editorial roundups, retailer listings, reviews and forum threads."),
    ("It matches products to the need", "Products whose pages confirm the conditions (waterproof rating, use, price) are easy to recommend. Vague pages give it nothing to work with."),
    ("It names the few it can justify", "Usually three to five products, often with links to the sources it used."),
]
EXAMPLE_Q = "What’s a good waterproof jacket for hiking in heavy rain, under $250?"
EXAMPLE_A = "For steady heavy rain, look for a 3-layer shell with fully taped seams. Good options:"
EXAMPLE = [  # rank, name, note, state
    ("1", "Ridgeline Storm Shell", "3-layer, 20K waterproof rating, pit zips", "named"),
    ("2", "Northpass Rain Jacket", "Light, packs into its pocket", "named"),
    ("3", "Your jacket", "Named third: its page states the rating and seam taping", "yours"),
    ("—", "Your other jacket", "Not named: its page doesn’t say how waterproof it is", "missing"),
]

METRICS = [
    ("Visibility", "The share of answers that name your product."),
    ("Average position", "Where your product appears when it’s named. First beats fourth."),
    ("Share of voice", "Your mentions as a share of all product mentions in those answers."),
    ("Citations", "The sites AI cites, and whether they mention you."),
]
MEASURE_RULE = ("An assistant can recommend one of your products for one need and never mention the rest of your catalog. "
                "A brand-level number hides that.")

WORK = [
    ("Who it’s for and what it’s for", "“For hiking in heavy rain” can be matched to a question. “For any adventure” can’t."),
    ("The specs buyers filter on", "Materials or ingredients, sizes, weight, ratings, compatibility. Written in text, not only in images."),
    ("Stated limits", "What it isn’t suited for. It helps AI recommend the product for the right question."),
    ("Answers on the page", "The questions customers ask support, answered in a sentence or two on the product page."),
    ("Complete structured data", "Product markup with price, availability and reviews, matching what the page says."),
    ("Mentions where AI looks", "The roundups, retailers and forums that keep showing up in the citations for your questions."),
]
HONEST = ("Which of these moves visibility most is still an open question, for us and for everyone working on it. "
          "Measure first, change one thing, and measure again on the same questions.")

FAQ = [
    ("Is AI shopping visibility the same as AEO or GEO?", "Close. AEO and GEO cover any content an AI might quote or cite. AI shopping visibility is the part that matters to an online store: whether your products get recommended."),
    ("Does ranking on Google mean AI will recommend my products?", "Not necessarily. Assistants read pages that rank well, but they recommend specific products for specific needs. A product page that doesn’t state what the product is for can rank and still be left out of the answer."),
    ("Why does my product show up in one answer but not the next?", "AI answers are generated fresh each time, so they vary. That is why visibility is measured as a share of many answers, not from a single check."),
    ("Can I measure it for my whole catalog?", "Checking by hand works for a few products. Produkto measures every product in a Shopify catalog on your buyer questions, daily, across ChatGPT, Google AI Overviews and Perplexity, and shows the competing products AI picks instead."),
]

SECTIONS = [  # id, heading (used by variants that build a contents list)
    ("short", "The short version"),
    ("why-now", "Why it matters now"),
    ("vs-seo", "How it differs from SEO"),
    ("how-ai-chooses", "How AI assistants choose products"),
    ("measure", "How to measure it"),
    ("work-on", "What you can work on"),
    ("faq", "Questions people ask"),
]
