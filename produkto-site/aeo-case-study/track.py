"""Produkto's own AI visibility: ask our buyers' questions, record who gets named.

Run weekly:  python3 track.py
Writes results/<date>.json (raw answers) and results/<date>.md (summary).
Uses the same Apify actors and key as the app (mvp/app/.env).
Cost: questions x engines, about $0.02 per question across the three engines.
"""
import collections, datetime, json, os, re, sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "..", "mvp", "app")
sys.path.insert(0, APP)
os.chdir(APP)  # config reads .env from the app folder
import apify_answers, config  # noqa: E402

QUESTIONS = [l.strip() for l in open(os.path.join(HERE, "questions.txt"))
             if l.strip() and not l.startswith("#")]
OURS = re.compile(r"produkto", re.I)


def domain(url):
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def main():
    today = datetime.date.today().isoformat()
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    raw = {}
    for engine in config.ENGINE_ORDER:
        print("asking", engine, "...", flush=True)
        try:
            ans = apify_answers.ask_batch(QUESTIONS, engine=engine)
        except Exception as e:  # one engine failing shouldn't lose the others
            print("  failed:", e)
            ans = {}
        raw[engine] = {q: {"text": t, "citations": c} for q, (t, c, _) in ans.items()}

    json.dump({"date": today, "questions": QUESTIONS, "answers": raw},
              open(os.path.join(HERE, "results", today + ".json"), "w"), indent=1)

    lines = ["# Produkto AI visibility - %s" % today, ""]
    total = mentioned = cited = 0
    sites = collections.Counter()
    for engine, answers in raw.items():
        lines += ["## %s" % config.ENGINES[engine]["label"], "",
                  "| Question | Named | Cited |", "|---|---|---|"]
        for q in QUESTIONS:
            a = answers.get(q)
            if not a:
                lines.append("| %s | no answer | |" % q)
                continue
            total += 1
            doms = {domain(c["url"]) for c in a["citations"]}
            sites.update(doms)
            m = bool(OURS.search(a["text"]))
            c = any("getprodukto" in d for d in doms)
            mentioned += m
            cited += c
            lines.append("| %s | %s | %s |" % (q, "yes" if m else "-", "yes" if c else "-"))
        lines.append("")
    lines[1:1] = ["Named in %d of %d answers, cited in %d." % (mentioned, total, cited), ""]
    lines += ["## Most-cited sites", ""] + ["- %s (%d)" % kv for kv in sites.most_common(25)]
    open(os.path.join(HERE, "results", today + ".md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))


if __name__ == "__main__":
    main()
