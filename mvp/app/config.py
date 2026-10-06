"""Every setting you might want to change, in one place.

The OpenAI key is NOT here. It lives in mvp/app/.env (see .env.example),
which you create yourself so the key never passes through anyone else.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Models -----------------------------------------------------------------
# Checked against developers.openai.com/api/docs/models on 16 Sep 2026.
# ANSWER_MODEL plays "ChatGPT": it answers the buyer question with web search.
# Nobody outside OpenAI knows exactly which model chatgpt.com serves, so this
# is a best guess - change it here and nothing else needs touching.
ANSWER_MODEL = "gpt-5.6"
# HELPER_MODEL writes the buyer questions and reads answers into lists.
# Cheap model, because it never faces the buyer.
HELPER_MODEL = "gpt-5.6-luna"

# --- Where the answers come from --------------------------------------------
# "apify"  - scrape ChatGPT Search through Apify. ~$0.005 an answer.
# "openai" - the OpenAI Responses API with web search. ~$0.096 an answer.
# Same measurement either way; the API path is kept so reversing is one line.
# The helper model always goes through OpenAI - it never faces the buyer.
# Trade-off: the Apify actor accepts queries and nothing else, so answers come
# from wherever its proxy sits and can be priced in the wrong currency.
# See DECISIONS.md, 2026-09-20.
ANSWER_SOURCE = "apify"

# Where onboarding's brand-profile fill is answered. "apify" asks ChatGPT
# through Apify (~half a cent, no OpenAI credits); "openai" uses the API.
# Buyer questions stay on OpenAI: their prompt carries the catalog, and the
# Apify actor never finished a ~5,000-character question (2026-09-25).
ONBOARDING_SOURCE = "apify"

# --- The engines ------------------------------------------------------------
# Every scan asks all three. They are three different places a buyer asks the
# same question, so a product can be recommended in one and invisible in the
# others - which is the whole point of measuring them separately.
#
# All three actors happen to take the same input (a newline-separated
# `queries` string and nothing else) and return the same shape
# ({query, text, sources:[{url,title,...}]}), so one collector serves all of
# them. Verified against live runs on 2026-09-21.
#
# `price` is the per-answer charge at the account's Apify tier. Set these to
# the tier actually in use or the scan cost shown on the dashboard is wrong.
# ChatGPT's tiers, for reference, since it is the one with a published table:
#   FREE $0.20  BRONZE $0.005  SILVER $0.004  GOLD $0.003  PLATINUM $0.0025
#   DIAMOND $0.002                                    (checked 2026-09-20)
# On FREE, scraping costs MORE than the OpenAI API ($0.096); the saving only
# arrives with a paid plan.
ENGINES = {
    "chatgpt": dict(
        label="ChatGPT", actor="apify/chatgpt-search-scraper", price=0.005),
    # `may_be_empty`: Google shows no AI Overview for plenty of searches, so a
    # question with no answer here is a finding, not a broken scan.
    "ai-overview": dict(
        label="AI Overview", actor="apify/google-ai-overviews-scraper", price=0.002,
        may_be_empty=True),
    "perplexity": dict(
        label="Perplexity", actor="apify/perplexity-search-scraper", price=0.013),
}
# Display order, and the order scans buy in. Matches the dashboard selector.
ENGINE_ORDER = ["chatgpt", "ai-overview", "perplexity"]
# Answers stored before multi-engine support came in were all ChatGPT.
DEFAULT_ENGINE = "chatgpt"
# Which engines a scan buys. Drop one from this list to stop paying for it;
# answers already collected from it stay readable on the dashboard.
SCAN_ENGINES = list(ENGINE_ORDER)


def engine_label(engine):
    """Name for an engine id, including one retired from ENGINES."""
    spec = ENGINES.get(engine)
    return spec["label"] if spec else (engine or DEFAULT_ENGINE)


def engine_price(engine):
    spec = ENGINES.get(engine)
    return spec["price"] if spec else 0.0

# --- Scan size --------------------------------------------------------------
QUESTION_CLUSTERS_MIN = 8
QUESTION_CLUSTERS_MAX = 40
QUESTION_CLUSTERS = 20  # Configurable hypothesis, not a coverage guarantee
# One run a day, every day, rather than several runs once a week. A week now
# carries 7 draws instead of 5, and each one lands on its own date so the
# trend has a daily point. Owner's call, 2026-09-22.
RUNS_PER_QUESTION = 1
PARALLEL_CALLS = 5         # how many OpenAI calls run at the same time

# Where the simulated buyer is. Leave country empty for no location hint.
BUYER_COUNTRY = ""         # e.g. "US", "GB", "ES"

# --- Matching ---------------------------------------------------------------
# How much of the product's title must appear in ChatGPT's product name
# (0-1) for it to count as "your product".
TITLE_MATCH_THRESHOLD = 0.6

# --- Storage ----------------------------------------------------------------
# PRODUKTO_DB points the app at a different database file - a copy, when you
# want to try something without touching the real scans. Unset, it is the one
# beside this file.
DB_PATH = os.environ.get("PRODUKTO_DB", "").strip() or os.path.join(HERE, "produkto.db")
PORT = int(os.environ.get("PORT", "8010"))


def env(name):
    """Read a setting from the environment, or from mvp/app/.env."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def api_key():
    """Read OPENAI_API_KEY from the environment, or from mvp/app/.env."""
    return env("OPENAI_API_KEY")

# Dated estimates from the rearchitecture research; reconcile with provider billing.
PRICE_DATE = '2026-09-18 (spec estimate; not billing-verified)'
PRICES = {'gpt-5.6-sol': (4.0, .40, 20.0), 'gpt-5.6': (4.0, .40, 20.0),
          'gpt-5.6-terra': (2.0, .20, 12.0), 'gpt-5.6-luna': (.20, .02, 1.20)}
SEARCH_PRICE = .01
# --- Cadence ----------------------------------------------------------------
# Every store that has finished onboarding is scanned daily, so opening any
# dashboard shows today's reading without anyone pressing anything. A store
# earns this by having saved buyer questions; nothing else is needed.
DAILY_SCANS = True
# Stores held back from the daily scan. A domain listed here still scans when
# the operator starts one by hand; it just doesn't scan on its own.
DAILY_SCAN_EXCLUDE = ("molivings.com",)

# Scans before this date (UTC) are left out of every dashboard view for that
# store. Clubhouse Skin's 18 and 20 Sep scans used the OpenAI API and a
# ChatGPT-only run; from 21 Sep every scan asks all three engines the same
# way, so earlier readings would show method changes as movement. The old
# scans stay in the database and stay reachable by their own link.
HISTORY_START = {"clubhouseskin.com": "2026-09-21"}
# Local hour a store's daily scan may start from. Stores are spread over the
# window by domain so they don't all hit Apify at once.
SCAN_WINDOW_START = 3
SCAN_WINDOW_HOURS = 6
# How often the scheduler wakes to look for stores that are due.
SCHEDULER_TICK_SECONDS = 300
SCANS_PER_MONTH = 30
