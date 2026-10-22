"""Build a fictional demo store for website screenshots. Illustrative data only.

Scarnhill (outdoor apparel, US) and every competitor in it are invented, and
so is every answer, citation and number. It exists so the marketing site can
show the real dashboard without showing a real brand's data (Kelian,
2026-10-13).

It writes its own database file and never opens the real one:

    python3 demo_site_seed.py            # builds produkto.db.demo-site
    PORT=8013 PRODUKTO_DB=produkto.db.demo-site PRODUKTO_SCANS=0 \
      PRODUKTO_DAILY_SCANS=0 PRODUKTO_OPPORTUNITIES=1 python3 app.py

The file name matches the `produkto.db*` rsync exclude and `*.db.*` in
.gitignore, so it can't reach the server or the repo. Costs nothing: no API
or Apify calls. A sign-in session for the local test user is written to
`produkto.db.demo-site.session` (git-ignored by the same `*.db.*` rule) so the
dashboard can be opened without a password.
"""

import json
import math
import os
import random
import secrets
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_FILE = HERE / "produkto.db.demo-site"
os.environ["PRODUKTO_DB"] = str(DB_FILE)
os.environ["PRODUKTO_DAILY_SCANS"] = "0"
os.environ["PRODUKTO_SCANS"] = "0"

import config  # noqa: E402

assert Path(config.DB_PATH).name == "produkto.db.demo-site", config.DB_PATH

import accounts  # noqa: E402
import db  # noqa: E402
import scoring  # noqa: E402
import support  # noqa: E402
import waitlist  # noqa: E402
import opportunities  # noqa: E402
import page_gap  # noqa: E402
import topics as topics_mod  # noqa: E402

DOMAIN = "scarnhill.com"
BRAND = "Scarnhill"
DAYS = 90
DAY = 86400
rng = random.Random(20261013)

# --- the catalog -------------------------------------------------------------

OWN = [  # id, title, price, type, handle
    (1, "Stormshell 3L Rain Jacket", "229", "Rain jackets", "stormshell-3l-rain-jacket"),
    (2, "Ridgeline Down Hoodie", "289", "Insulated jackets", "ridgeline-down-hoodie"),
    (3, "Switchback Hiking Pant", "119", "Hiking pants", "switchback-hiking-pant"),
    (4, "Drift 20°F Down Sleeping Bag", "349", "Sleeping bags", "drift-20-down-sleeping-bag"),
    (5, "Scree Mid Waterproof Boot", "189", "Hiking boots", "scree-mid-waterproof-boot"),
    (6, "Ember Merino Base Layer", "89", "Base layers", "ember-merino-base-layer"),
    (7, "Cache 28L Daypack", "139", "Daypacks", "cache-28l-daypack"),
    (8, "Lumen Grid Fleece", "129", "Fleece", "lumen-grid-fleece"),
    (9, "Cirque Full-Zip Rain Pant", "139", "Rain pants", "cirque-full-zip-rain-pant"),
    (10, "Trailhead Merino Sock 3-Pack", "39", "Socks", "trailhead-merino-sock-3-pack"),
]

COMPETITORS = {  # brand: (domain, base strength, drift over the month)
    "Alpenfeld": ("alpenfeld.com", 1.00, -0.10),
    "Halvard": ("halvardgear.com", 0.85, 0.25),
    "Peakwise": ("peakwisegear.com", 0.75, -0.30),
    "Vandre": ("vandregear.com", 0.60, 0.05),
    "Cairnwell Outdoor": ("cairnwelloutdoor.com", 0.45, 0.10),
    "Brightscree": ("brightscree.com", 0.40, 0.00),
}

POOLS = {
    "Rain gear": [
        ("Alpenfeld", "Torrent 3L Jacket", "$279"), ("Halvard", "Squall Shell Jacket", "$199"),
        ("Vandre", "Regnvær Rain Jacket", "$249"), ("Peakwise", "Downfall Rain Jacket", "$159"),
        ("Brightscree", "Monsoon Pro Shell", "$319"), ("Halvard", "Squall Rain Pant", "$129"),
        ("Peakwise", "Downfall Rain Pant", "$99"),
    ],
    "Insulation": [
        ("Alpenfeld", "Glacier Down Hoodie", "$329"), ("Cairnwell Outdoor", "Emberline Down Jacket", "$259"),
        ("Halvard", "Loft 800 Hoodie", "$299"), ("Peakwise", "Thermal Grid Fleece", "$89"),
        ("Vandre", "Ullsett Merino Crew", "$95"), ("Brightscree", "Merino 200 Base Layer", "$110"),
    ],
    "Hiking footwear & pants": [
        ("Vandre", "Fjell Mid GTX Boot", "$219"), ("Alpenfeld", "Trek GTX Boot", "$239"),
        ("Peakwise", "Wideload Hiker", "$169"), ("Halvard", "Scramble Pant", "$95"),
        ("Cairnwell Outdoor", "Trail Pant", "$109"), ("Brightscree", "Merino Hiker Sock", "$24"),
        ("Peakwise", "Lifetime Merino Sock", "$22"),
    ],
    "Sleeping bags": [
        ("Alpenfeld", "Nordlys 20 Down Bag", "$399"), ("Cairnwell Outdoor", "Drift Synthetic 20", "$229"),
        ("Halvard", "Ridge 15 Down Bag", "$379"), ("Brightscree", "Featherlite 20", "$429"),
        ("Peakwise", "Basecamp 20 Synthetic", "$179"),
    ],
    "Daypacks": [
        ("Halvard", "Vista 28 Daypack", "$149"), ("Peakwise", "Daytripper 26", "$99"),
        ("Alpenfeld", "Gipfel 30 Pack", "$169"), ("Cairnwell Outdoor", "Overlook 24", "$119"),
        ("Vandre", "Tur 25 Daypack", "$135"),
    ],
}

QUESTIONS = [  # question, topic, tag, own product ids, own base rate
    ("What's the best waterproof rain jacket for hiking in heavy rain?", "Rain gear", "best", [1], .75),
    ("What's a good packable rain jacket for hiking under $250?", "Rain gear", "budget", [1], .80),
    ("Which rain jacket has fully taped seams and pit zips for warm, wet hikes?", "Rain gear", "spec", [1], .70),
    ("Are full-zip rain pants worth it for hiking, and which ones are best?", "Rain gear", "use case", [9], .15),
    ("What's the warmest down hoodie for winter hiking under $300?", "Insulation", "budget", [2], .30),
    ("Should I get a down jacket or a fleece for layering on cold hikes?", "Insulation", "compare", [2, 8], .10),
    ("What's the best merino base layer for multi-day backpacking?", "Insulation", "best", [6], .05),
    ("What are the best waterproof hiking boots with a wide toe box?", "Hiking footwear & pants", "spec", [5], .10),
    ("Which hiking pants hold up best for summer hikes with lots of scrambling?", "Hiking footwear & pants", "use case", [3], .20),
    ("Which merino hiking socks last more than one season?", "Hiking footwear & pants", "spec", [10], .02),
    ("What's the best 20°F sleeping bag for backpacking under $400?", "Sleeping bags", "budget", [4], .35),
    ("Down or synthetic sleeping bag for wet shoulder-season camping?", "Sleeping bags", "compare", [4], .15),
    ("What's the best daypack for long day hikes with a hydration sleeve?", "Daypacks", "best", [7], .25),
    ("Which 28-liter daypack is comfortable for carrying a camera and extra layers?", "Daypacks", "use case", [7], .30),
    ("What gear do I need for a rainy three-day backpacking trip?", "Rain gear", "use case", [1, 1, 4, 7], .50),
]

ENGINE_LIFT = {"chatgpt": 1.10, "ai-overview": 0.75, "perplexity": 1.00}
MODELS = {"chatgpt": "apify/chatgpt-search-scraper",
          "ai-overview": "apify/google-ai-overviews-scraper",
          "perplexity": "apify/perplexity-search-scraper"}

INTROS = {
    "Rain gear": "For sustained rain on the trail, look for a three-layer shell with fully taped seams, a stiff brim on the hood and venting you can open on climbs.",
    "Insulation": "For cold hikes, warmth-to-weight and how well a layer handles sweat matter more than the fill number on the tag.",
    "Hiking footwear & pants": "Fit and durability decide this one: check the last width, the fabric weight and whether the seams are reinforced where you wear them through.",
    "Sleeping bags": "Match the comfort rating, not the lower limit, to the coldest night you expect, and think about how damp the trip will be.",
    "Daypacks": "For long days, a ventilated back panel, a real hip belt and easy access to water make the biggest difference.",
}
REASONS = [
    "consistently well reviewed for the price",
    "a strong all-rounder that testers keep coming back to",
    "lighter than most in its class without feeling fragile",
    "good venting and a comfortable fit over layers",
    "durable fabric that holds up to abrasion",
    "packs down small and is easy to live with",
    "a reliable pick if you want fewer compromises",
]
REVIEW_SITES = [
    ("trailproofreview.com", "Trailproof Review"), ("thegearjournal.com", "The Gear Journal"),
    ("pitchandpackreview.com", "Pitch & Pack Review"), ("ultralightledger.com", "Ultralight Ledger"),
]


def product_row(pid, title, price, ptype, handle):
    raw = {"product_type": ptype, "tags": [ptype],
           "body_html": "<p>%s by %s.</p>" % (title, BRAND)}
    return dict(id=pid, store_domain=DOMAIN, shopify_id=900000 + pid, handle=handle,
                title=title, url="https://%s/products/%s" % (DOMAIN, handle), price=price,
                image="", variants=4, vendor=BRAND, raw_json=json.dumps(raw))


def slug(s):
    return "-".join("".join(c if c.isalnum() else " " for c in s.lower()).split())


def build():
    if DB_FILE.exists():
        DB_FILE.unlink()
    db.init()
    waitlist.init()
    support.init()
    accounts.init()
    opportunities.init()
    page_gap.init()
    topics_mod._table()

    now = time.time()
    first_day = now - DAYS * DAY
    start = first_day - first_day % DAY  # midnight UTC

    db.write("INSERT INTO stores(domain,brand,products,variants,fetched_at,currency,country,brand_name,aliases) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (DOMAIN, BRAND, len(OWN), len(OWN) * 4, start, "USD", "US", BRAND, "[]"))
    for col, val in (("description", "Technical outdoor apparel and gear for hikers and backpackers."),
                     ("industry", "Outdoor apparel")):
        try:
            db.write("UPDATE stores SET %s=? WHERE domain=?" % col, (val, DOMAIN))
        except Exception:
            pass

    catalog = [product_row(*p) for p in OWN]
    for p in catalog:
        db.write("INSERT INTO products(id,store_domain,shopify_id,handle,title,url,price,image,variants,vendor,raw_json) "
                 "VALUES (:id,:store_domain,:shopify_id,:handle,:title,:url,:price,:image,:variants,:vendor,:raw_json)", p)
    ids = [p["id"] for p in catalog]
    topics = list(POOLS)
    db.write("INSERT INTO catalog_scope VALUES (?,?,?)", (DOMAIN, json.dumps(ids), "[]"))
    db.write("INSERT INTO topics(store_domain,topics,chosen,stale) VALUES (?,?,?,0)",
             (DOMAIN, json.dumps(topics), json.dumps(topics)))
    ps_id = db.write(
        "INSERT INTO prompt_sets(store_domain,clusters,relevance,product_ids,excluded_types,catalog_snapshot,prompts,tags,created_at,frozen_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (DOMAIN, json.dumps([q[1] for q in QUESTIONS]), json.dumps([q[3] for q in QUESTIONS]),
         json.dumps(ids), "[]", json.dumps(catalog), json.dumps([q[0] for q in QUESTIONS]),
         json.dumps([q[2] for q in QUESTIONS]), start, start))

    titles = {p["id"]: p for p in catalog}
    scan_ids = []
    for day in range(DAYS):
        t = day / (DAYS - 1)
        run_at = start + day * DAY + 10 * 3600 + rng.randint(0, 900)  # ~6am US Eastern
        sid = db.write("INSERT INTO scans(token,prompt_set_id,run_at,finished_at,status,done,total,cost_cents,model_versions) "
                       "VALUES (?,?,?,?,?,?,?,?,?)",
                       ("demo-%s" % secrets.token_hex(6), ps_id, run_at, run_at + 300, "done", 0, 0, 0, "{}"))
        n = 0
        by_engine = {}
        for q, topic, tag, own_ids, base in QUESTIONS:
            for engine in config.ENGINE_ORDER:
                if engine == "ai-overview" and rng.random() < 0.12:
                    continue  # Google shows no AI Overview for some searches
                n += 1
                by_engine[engine] = by_engine.get(engine, 0) + 1
                # Own visibility climbs over the month; competitors drift. Each
                # rival product is included on its own odds, so daily lines move
                # smoothly rather than jumping with every reshuffle.
                p_own = min(.9, base * ENGINE_LIFT[engine] * (0.45 + 1.1 * t))
                pool = POOLS[topic]
                picks = []
                for b, name, price in pool:
                    w = max(.05, COMPETITORS[b][1] + COMPETITORS[b][2] * (t - .5) * 2)
                    if rng.random() < min(.85, .55 * w):
                        picks.append(dict(brand=b, name=name, price=price, own=None, w=w * rng.uniform(.8, 1.2)))
                picks.sort(key=lambda m: -m["w"])
                picks = picks[:5]
                if rng.random() < p_own:
                    pid = rng.choice(own_ids)
                    pos = min(len(picks), rng.choice([0, 0, 1, 1, 2, 3]))
                    picks.insert(pos, dict(brand=BRAND, name=titles[pid]["title"], price="$" + titles[pid]["price"], own=pid))
                if not picks:
                    pool_pick = pool[0]
                    picks = [dict(brand=pool_pick[0], name=pool_pick[1], price=pool_pick[2], own=None)]
                lead = {"chatgpt": "Here are the strongest options right now:",
                        "ai-overview": "Popular picks from reviews and retailers include:",
                        "perplexity": "Based on recent reviews, these stand out:"}[engine]
                lines = [INTROS[topic], "", lead, ""]
                for r, m in enumerate(picks, 1):
                    lines.append("%d. **%s %s** (%s): %s." % (r, m["brand"], m["name"], m["price"], rng.choice(REASONS)))
                lines += ["", "If you can, try the fit in person or check the return policy before a long trip."]
                cites = []
                for site, label in rng.sample(REVIEW_SITES, rng.randint(1, 3)):
                    cites.append(dict(url="https://www.%s/%s" % (site, slug(q)[:60]), title="%s: %s" % (label, q)))
                if rng.random() < .6:
                    cites.append(dict(url="https://www.reddit.com/r/hiking/comments/%s/" % secrets.token_hex(3),
                                      title="r/hiking: %s" % q))
                if rng.random() < .3:
                    cites.append(dict(url="https://www.youtube.com/watch?v=%s" % secrets.token_hex(5),
                                      title="Tested: %s" % topic.lower()))
                for m in picks[:2]:
                    if m["own"]:
                        cites.append(dict(url=titles[m["own"]]["url"], title="%s | %s" % (m["name"], BRAND)))
                    else:
                        cites.append(dict(url="https://%s/products/%s" % (COMPETITORS[m["brand"]][0], slug(m["name"])),
                                          title="%s | %s" % (m["name"], m["brand"])))
                aid = db.write("INSERT INTO answers(scan_id,prompt,model,run_n,raw_text,citations,created_at,engine) "
                               "VALUES (?,?,?,?,?,?,?,?)",
                               (sid, q, MODELS[engine], 1, "\n".join(lines), json.dumps(cites), run_at, engine))
                db.write("INSERT INTO answer_processing VALUES (?,?,NULL)", (aid, "done"))
                for r, m in enumerate(picks, 1):
                    url = (titles[m["own"]]["url"] if m["own"] else
                           "https://%s/products/%s" % (COMPETITORS[m["brand"]][0], slug(m["name"])))
                    db.write("INSERT INTO mentions(answer_id,product_name,brand,url,rank,is_theirs,is_their_brand,match_score,matched_product_id,price) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (aid, m["name"], m["brand"], url, r, 1 if m["own"] else 0, 1 if m["own"] else 0,
                              1.0 if m["own"] else 0.0, m["own"], m["price"]))
        db.write("UPDATE scans SET done=?,total=?,model_versions=? WHERE id=?",
                 (n, n, json.dumps({"by_engine": by_engine, "demo": True}), sid))
        scan_ids.append(sid)

    for sid in scan_ids:
        scoring.score(sid)

    uid = accounts.create_user("demo@scarnhill.test", secrets.token_urlsafe(24))
    db.write("INSERT INTO user_stores VALUES (?,?)", (uid, DOMAIN))
    token = accounts.new_session(uid)
    (HERE / "produkto.db.demo-site.session").write_text(token)
    print("Built %s: %d scans, %d questions, %d products." % (DB_FILE.name, len(scan_ids), len(QUESTIONS), len(OWN)))


if __name__ == "__main__":
    build()
