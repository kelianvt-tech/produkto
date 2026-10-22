"""Step 2: ask ChatGPT (via Apify) one buyer question per coffee/tea brand. Writes coffee-answers-2026-10-15.json."""
import json, os, sys
from coffee_question_phrases import phrase, D
HERE = os.path.dirname(os.path.abspath(__file__))
qs = {}
for dom in D:
    ph, use_price = phrase(dom)
    if ph == "N": continue
    p = D[dom]["product"]
    qs[dom] = "What's the best %s to buy online%s?" % (ph, " for around $%d" % round(p["price"]) if use_price and p else "")
json.dump(qs, open(os.path.join(HERE, "coffee-questions-final-2026-10-15.json"), "w"), indent=1)
FORMAT = " Name three specific products. Reply in ONE line exactly like: 1) Brand: product name; 2) Brand: product name; 3) Brand: product name"
APP = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app"
sys.path.insert(0, APP)
for line in open(os.path.join(APP, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip("\"'"))
os.chdir(APP)
import apify_answers
print("asking", len(set(qs.values())), "questions", flush=True)
res = apify_answers.ask_batch([q + FORMAT for q in set(qs.values())], engine="chatgpt", timeout=3000,
                              on_start=lambda r, ds: print("run", r, ds, flush=True))
out = {dom: dict(question=q, answer=(res.get(q + FORMAT) or ("",))[0]) for dom, q in qs.items()}
json.dump(out, open(os.path.join(HERE, "coffee-answers-2026-10-15.json"), "w"), indent=1)
print("answered", sum(1 for v in out.values() if v["answer"]), "of", len(out), flush=True)
