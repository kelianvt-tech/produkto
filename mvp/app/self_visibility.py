"""Produkto's own AI visibility: does AI name Produkto, or our competitors, when a buyer asks?

Built 22 Oct 2026 (Kelian: "I still want to get cited instead of my competitors for my own product").
Same questions and method as produkto-site/aeo-case-study/track.py (baseline 20 Oct 2026: named
in 0 of 28 answers), but run by the server every week and stored in the app database, so the
admin page (hub.py) shows it. The 20 Oct baseline is imported with `import <json>`.

Every Monday (systemd timer produkto-self-vis.timer): ask QUESTIONS once on each engine in
config.ENGINE_ORDER through the app's Apify actors, record every answer, and count who got
named. About $0.02 a question across the three engines, so ~$0.20 a week.

Guard: one run per ISO week unless --force; never runs within HEADROOM dollars of the shared
Apify monthly limit (the daily scans need it).

Run by hand: python3 self_visibility.py run [--force] | report | import <track.py json>
"""
import collections
import datetime as dt
import json
import re
import sys
import threading
import time
from urllib.parse import urlparse

import config
import db

# Keep this list stable so weeks compare; add new questions at the bottom, never reword old ones.
# Same as produkto-site/aeo-case-study/questions.txt.
QUESTIONS = [
    "What is the best tool to see if ChatGPT recommends my Shopify products?",
    "How can I check whether AI assistants recommend my ecommerce products?",
    "Best AI search visibility tools for ecommerce brands in 2026",
    "How do I get my products recommended in ChatGPT Shopping?",
    "AI visibility tracker for Shopify stores",
    "Alternatives to Profound for ecommerce brands",
    "How do I optimize my Shopify product pages for AI search?",
    "Best GEO tools for ecommerce product catalogs",
    "Software that monitors product mentions in ChatGPT, Perplexity and Google AI Overviews",
    "Best AEO tool for DTC brands",
]

OURS = re.compile(r"\bprodukto\b", re.I)
# Who AI names instead of us. Name -> pattern (whole words; spellings AI uses).
COMPETITORS = {
    "Profound": r"profound", "Peec AI": r"peec(?: ai)?", "Promptwatch": r"prompt ?watch", "Ahrefs": r"ahrefs",
    "Semrush": r"semrush", "Otterly": r"otterly", "Scrunch": r"scrunch", "Yotpo": r"yotpo",
    "Searchable": r"searchable", "AndromedAI": r"andromed ?ai", "Sixthshop": r"sixth ?shop", "Glara": r"glara",
    "Goodie": r"goodie(?: ai)?", "Azoma": r"azoma", "Alhena": r"alhena", "ReFiBuy": r"refibuy",
    "AthenaHQ": r"athena ?hq", "Evertune": r"evertune", "Writesonic": r"writesonic", "Rankscale": r"rankscale",
    "Gauge": r"withgauge|\bgauge\b", "Bluefish": r"bluefish", "HubSpot AI Grader": r"ai (?:search )?grader",
}
_PATTERNS = {k: re.compile(r"\b(?:%s)\b" % v, re.I) for k, v in COMPETITORS.items()}
PRICE_PER_QUESTION = sum(config.ENGINES[e]["price"] for e in config.ENGINE_ORDER)
HEADROOM = 10.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS self_vis (
    id INTEGER PRIMARY KEY, day TEXT NOT NULL, engine TEXT NOT NULL, question TEXT NOT NULL,
    text TEXT, citations TEXT, named INTEGER DEFAULT 0, cited INTEGER DEFAULT 0, created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_self_vis_day ON self_vis(day);
"""
_lock = threading.Lock()
_running = False


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)


def domain(url):
    d = urlparse(url or "").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def estimate():
    return round(len(QUESTIONS) * PRICE_PER_QUESTION, 2)


def _week(day):
    return dt.date.fromisoformat(day).isocalendar()[:2]


def guard(force=False, usage=None):
    """(ok, reasons). `usage` = (used, limit) for tests; read from Apify otherwise."""
    init()
    reasons = []
    last = db.one("SELECT MAX(day) d FROM self_vis")["d"]
    if last and not force and _week(last) == _week(dt.date.today().isoformat()):
        reasons.append("Already ran this week (%s)." % last)
    if _running:
        reasons.append("A run is already going.")
    try:
        if usage is None:
            import hub
            usage = hub.apify_usage()
        if usage is None:
            raise RuntimeError("no reading")
        used, limit = usage
        if limit and limit - used - estimate() < HEADROOM:
            reasons.append("Apify has $%.2f left of $%.0f; a run must leave $%.0f for the daily scans."
                           % (max(0, limit - used), limit, HEADROOM))
    except Exception as e:                                        # noqa: BLE001 - unknown balance = don't spend
        reasons.append("Could not read the Apify balance (%s)." % e)
    return not reasons, reasons


def store(day, engine, question, text, citations):
    init()
    doms = {domain(c.get("url")) for c in citations or []}
    db.write("INSERT INTO self_vis(day,engine,question,text,citations,named,cited,created_at) VALUES (?,?,?,?,?,?,?,?)",
             (day, engine, question, text, json.dumps(citations or []), int(bool(OURS.search(text or ""))),
              int(any("getprodukto" in d for d in doms)), time.time()))


def run(force=False, ask=None):
    """Ask every question on every engine. `ask(questions, engine)` is patched in tests."""
    global _running
    ok, reasons = guard(force)
    if not ok:
        return dict(ok=False, reasons=reasons)
    with _lock:
        _running = True
    try:
        if ask is None:
            import apify_answers
            ask = lambda qs, engine: apify_answers.ask_batch(qs, engine=engine)  # noqa: E731
        day, out = dt.date.today().isoformat(), {}
        for engine in config.ENGINE_ORDER:
            try:
                answers = ask(QUESTIONS, engine)
            except Exception as e:                                # noqa: BLE001 - one engine failing keeps the others
                out[engine] = "failed: %s" % e
                continue
            for q, (text, cites, _model) in answers.items():
                store(day, engine, q, text, cites)
            out[engine] = "%d answers" % len(answers)
        return dict(ok=True, day=day, engines=out)
    finally:
        with _lock:
            _running = False


def start(force=True):
    """Run in the background (the admin page's button). Returns (started, message)."""
    ok, reasons = guard(force)
    if not ok:
        return False, " ".join(reasons)
    threading.Thread(target=run, kwargs=dict(force=force), daemon=True, name="self-vis").start()
    return True, "Started. About $%.2f; results appear here in 5 to 15 minutes." % estimate()


def import_track(path):
    """Load a produkto-site/aeo-case-study/results/<date>.json (the 20 Oct baseline)."""
    init()
    data = json.load(open(path))
    if db.one("SELECT 1 FROM self_vis WHERE day=?", (data["date"],)):
        return 0
    n = 0
    for engine, answers in data["answers"].items():
        for q, a in answers.items():
            store(data["date"], engine, q, a["text"], a["citations"])
            n += 1
    return n


def report():
    """Every run, newest first, with who got named and what got cited."""
    init()
    runs = []
    for d in [r["day"] for r in db.all_("SELECT DISTINCT day FROM self_vis ORDER BY day DESC")]:
        rows = db.all_("SELECT * FROM self_vis WHERE day=?", (d,))
        rivals, sites, by_engine = collections.Counter(), collections.Counter(), {}
        for r in rows:
            rivals.update(k for k, p in _PATTERNS.items() if p.search(r["text"] or ""))
            sites.update({domain(c.get("url")) for c in json.loads(r["citations"] or "[]")} - {""})
            e = by_engine.setdefault(r["engine"], [0, 0])
            e[0] += 1
            e[1] += r["named"]
        runs.append(dict(day=d, answers=len(rows), named=sum(r["named"] for r in rows),
                         cited=sum(r["cited"] for r in rows), rivals=rivals.most_common(), sites=sites.most_common(15),
                         by_engine=by_engine,
                         questions={(r["engine"], r["question"]): (r["named"], r["cited"]) for r in rows}))
    return runs


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "run":
        print(json.dumps(run(force="--force" in sys.argv), indent=1))
    elif cmd == "import":
        print("imported", import_track(sys.argv[2]), "answers")
    else:
        for r in report():
            print(r["day"], "named %d/%d cited %d" % (r["named"], r["answers"], r["cited"]), r["rivals"][:8])
